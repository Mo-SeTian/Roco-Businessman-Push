"""多任务调度器：任务自带触发时间与渠道组合。

- 触发时刻 = 所有启用任务时间的并集；到点只拉一次接口，由命中的任务各自决定推给谁；
- 指纹按 任务+商店+渠道 记录，任务可独立开关"仅变化时推送"；
- 配置保存后 wake() 立即重算下一次执行。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .api_stats import APIStatsStore
from .channels import send_instance
from .channels.common import redact_text
from .format import build_message
from .models import AppConfig, TaskConfig
from .rocom import MerchantClient
from .state import StateStore, fingerprint

log = logging.getLogger("scheduler")


class SchedulerService:
    def __init__(self, store, state_store: StateStore, history_store=None):
        self.store = store  # AppConfigStore
        self.state_store = state_store
        self.api_stats = APIStatsStore(str(Path(state_store.path).parent / "api_stats.sqlite3"))
        self.history = history_store  # HistoryStore，可为 None
        self.state: dict[str, Any] = {
            "running": False,
            "in_progress": False,
            "next_run_at": None,
            "last_fire_at": None,
            "last_message": "尚未执行",
            "last_results": [],
            "run_history": [],   # 最近执行记录（新在前，最多 50 次），随快照持久化
        }
        # 执行历史持久化到 /data，重启后状态页仍可见
        self._snapshot_path = Path(state_store.path).parent / "scheduler_state.json"
        self._restore_snapshot()
        self._wake = threading.Event()
        self._run_lock = threading.Lock()
        self._state_lock = threading.Lock()  # 只护 run_history 等原地修改，快照不必等长执行结束
        self._stop_flag = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot_state(self) -> dict[str, Any]:
        """完整状态深拷贝，供 Web 线程序列化，避免读到执行中被原地改写的 run_history。"""
        with self._state_lock:
            return deepcopy(self.state)

    def _restore_snapshot(self) -> None:
        try:
            data = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            for key in ("last_results", "last_message", "last_fire_at", "run_history"):
                if key in data:
                    self.state[key] = data[key]

    def _save_snapshot(self) -> None:
        try:
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {k: self.state[k] for k in ("last_results", "last_message", "last_fire_at", "run_history")}
            fd, tmp = tempfile.mkstemp(dir=str(self._snapshot_path.parent), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._snapshot_path)
        except OSError as exc:
            log.warning("调度状态保存失败：%s", exc)

    # ---- 生命周期 ----

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag.set()
        self._wake.set()

    def wake(self) -> None:
        """配置变更后立即打断睡眠，重算计划。"""
        self._wake.set()

    # ---- 调度循环 ----

    def _loop(self) -> None:
        self.state["running"] = True
        try:
            if self.store.load().run_on_start:
                self._run_locked("启动执行", force=False)
            while not self._stop_flag.is_set():
                cfg = self.store.load()
                now = datetime.now()
                next_run = self.next_run_time(cfg, now)
                self.state["next_run_at"] = next_run.isoformat(sep=" ", timespec="minutes") if next_run else None
                if next_run is None:
                    self.state["last_message"] = "没有启用的任务，等待配置…"
                    self._wake.wait(timeout=60)
                    self._wake.clear()
                    continue
                wait_s = max(0.0, (next_run - datetime.now()).total_seconds())
                log.info("下一次执行：%s（%.0f 分钟后）", next_run.strftime("%m-%d %H:%M"), wait_s / 60)
                woken = self._wake.wait(timeout=wait_s)
                self._wake.clear()
                if woken and not self._stop_flag.is_set():
                    continue  # 配置变了，重算
                if self._stop_flag.is_set():
                    break
                self._run_locked("定时执行", force=False, due_time=next_run.strftime("%H:%M"))
        finally:
            self.state["running"] = False

    @staticmethod
    def next_run_time(cfg: AppConfig, now: datetime) -> datetime | None:
        """所有启用任务时间的并集中，晚于 now 的最近时刻。"""
        candidates: set[datetime] = set()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        for task in cfg.tasks:
            if not task.enabled:
                continue
            for text in task.times:
                hour, minute = int(text[:2]), int(text[3:5])
                for day in (today, tomorrow):
                    candidate = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
                    if candidate > now:
                        candidates.add(candidate)
        return min(candidates) if candidates else None

    def _wake_wait(self, timeout: float) -> bool:
        return self._wake.wait(timeout=timeout)

    # ---- 执行 ----

    def run_task_now(self, task_id: str, source: str = "api") -> str:
        """手动执行指定任务（无视时间表，强制推送）。"""
        if source not in ("api", "history"):
            raise ValueError("无效的数据来源")
        reason = "手动执行（历史优先）" if source == "history" else "手动执行（重新获取）"
        return self._run_locked(reason, force=True, task_id=task_id, source=source)

    def run_all_now(self) -> str:
        return self._run_locked("手动执行", force=True)

    def _run_locked(self, reason: str, *, force: bool, task_id: str | None = None,
                    due_time: str | None = None, source: str = "api") -> str:
        if not self._run_lock.acquire(blocking=False):
            return "已有任务正在执行，请稍候"
        try:
            self.state["in_progress"] = True
            self.state["last_message"] = f"{reason}中…"
            try:
                cfg = self.store.load()
                if task_id:
                    task = next((t for t in cfg.tasks if t.id == task_id), None)
                    if task is None:
                        return "任务不存在"
                    tasks = [task]
                elif due_time:
                    tasks = [t for t in cfg.tasks if t.enabled and t.due_at(datetime.now())]
                    if not tasks:
                        self.state["last_message"] = f"{reason}：无命中任务"
                        return self.state["last_message"]
                else:
                    tasks = [t for t in cfg.tasks if t.enabled]
                    if not tasks:
                        self.state["last_message"] = "没有启用的任务"
                        return self.state["last_message"]
                self._fire(cfg, tasks, force=force, reason=reason, source=source)
                return self.state["last_message"]
            except Exception as exc:  # noqa: BLE001
                log.exception("执行异常")
                self.state["last_message"] = f"{reason}异常：{exc}"
                return self.state["last_message"]
            finally:
                self.state["in_progress"] = False
                self.state["last_fire_at"] = datetime.now().isoformat(sep=" ", timespec="seconds")
        finally:
            self._run_lock.release()

    def _fire(self, cfg: AppConfig, tasks: list[TaskConfig], *, force: bool, reason: str = "", source: str = "api") -> None:
        shop_keys = cfg.shop_ids or [None]
        client = MerchantClient(
            cfg.rocom_api_key,
            api_base=self.store.env.api_base,
            wait_ms=cfg.wait_ms,
            http_timeout=cfg.http_timeout,
            max_retries=cfg.max_retries,
            retry_delay=cfg.retry_delay,
            api_stats=self.api_stats,
        )

        payloads: dict[str, dict] = {}
        errors: dict[str, str] = {}
        now = datetime.now().astimezone()
        for shop in shop_keys:
            key = shop or "default"
            if source == "history":
                cached = self.history.current_payload(key, now) if self.history is not None else None
                if cached is not None:
                    payloads[key] = cached
                    log.info("商店 %s 使用当前时段历史记录", key)
                    continue
                log.info("商店 %s 当前时段无完整历史记录，自动请求接口", key)
            log.info("开始拉取远行商人数据（商店：%s）", key)
            try:
                payloads[key] = client.fetch_merchant(shop)
                if self.history is not None:
                    self.history.add(key, payloads[key])  # 成功拉取即记入历史，失败/未调用自然为空
            except Exception as exc:  # noqa: BLE001
                detail = redact_text(str(exc))
                if cfg.rocom_api_key:
                    detail = detail.replace(cfg.rocom_api_key, "<REDACTED>")
                log.error("[%s] 拉取失败：%s", key, detail)
                errors[key] = detail[:300]

        report: list[dict] = []
        failure_notices: dict[tuple[str, str], tuple[bool, str]] = {}
        pushed_any = False
        for task in tasks:
            channels = cfg.enabled_channels_of(task)
            for shop in shop_keys:
                key = shop or "default"
                entry = {"task": task.name, "shop": key, "channels": [], "skipped": False}
                if key in errors:
                    entry["channels"].append({"channel": "(接口)", "ok": False, "detail": errors[key]})
                    title = f"{cfg.title_prefix}｜商店数据获取失败"
                    text = (
                        f"商店：{shop or '3009（默认）'}\n"
                        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"已耗尽接口请求次数（最多 {cfg.max_retries} 次，"
                        f"重试间隔 {cfg.retry_delay / 60:g} 分钟）。\n"
                        f"最后错误：{errors[key]}"
                    )
                    for inst in channels:
                        notice_key = (key, inst.id)
                        if notice_key not in failure_notices:
                            failure_notices[notice_key] = send_instance(
                                inst, title, text, text,
                                max_retries=cfg.push_max_retries, retry_delay=cfg.push_retry_delay,
                            )
                        ok, detail = failure_notices[notice_key]
                        entry["channels"].append({
                            "channel": f"{inst.name}（失败通知）", "ok": ok, "detail": detail,
                        })
                    report.append(entry)
                    continue
                if not channels:
                    entry["channels"].append({"channel": "(渠道)", "ok": False, "detail": "任务未配置可用渠道"})
                    report.append(entry)
                    continue

                msg = build_message(payloads[key], cfg)
                fp = fingerprint(msg["fingerprint_src"])
                pending = [inst for inst in channels if force or not task.only_on_change or
                           self.state_store.get_fingerprint(f"{task.id}:{key}:{inst.id}") != fp]
                if not pending:
                    entry["skipped"] = True
                    report.append(entry)
                    log.info("[任务:%s | %s] 数据无变化，跳过", task.name, key)
                    continue

                for inst in pending:
                    ok, detail = send_instance(
                        inst, msg["title"], msg["markdown"], msg["text"],
                        max_retries=cfg.push_max_retries, retry_delay=cfg.push_retry_delay,
                    )
                    entry["channels"].append({"channel": inst.name, "ok": ok, "detail": detail})
                    if ok:
                        pushed_any = True
                        self.state_store.set_pushed(f"{task.id}:{key}:{inst.id}", fp)
                report.append(entry)

        with self._state_lock:
            self.state["last_results"] = report[-50:]
            self.state["last_fire_at"] = datetime.now().isoformat(sep=" ", timespec="seconds")
            runs = self.state.setdefault("run_history", [])
            runs.insert(0, {"time": self.state["last_fire_at"], "reason": reason, "results": report})
            del runs[50:]
        ok_count = sum(1 for e in report for c in e["channels"] if c["ok"])
        total = sum(len(e["channels"]) for e in report)
        self.state["last_message"] = (
            f"完成：{ok_count}/{total} 项推送成功" if total else "无推送项"
        )
        if errors:
            self.state["last_message"] += f"（{len(errors)} 个商店获取失败，失败通知结果见渠道记录）"
        if not pushed_any and total and ok_count == 0:
            self.state["last_message"] += "（注意：全部失败）"
        log.info(self.state["last_message"])
        self._save_snapshot()
