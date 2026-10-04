"""AppConfig 持久化：/data/config.json，环境变量做兜底/种子。

- 首次启动（无配置文件）：用环境变量播种渠道实例和默认任务（老用户的 .env 直接可用）；
- WebUI 保存：密钥字段留空 = 保留旧值；console_auth 单独保留；
- 配置文件损坏：自动备份为 .bak 并回退种子配置。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from .channels.manifest import secret_fields
from .config import GlobalEnv
from .models import AppConfig, ChannelInstance

log = logging.getLogger("store")

ENV_CHANNEL_SEEDS = [  # (类型, {字段名: 环境变量}, 实例名)
    ("serverchan", {"sendkey": "SERVERCHAN_SENDKEY"}, "Server酱(环境变量)"),
    ("bark", {"server": "BARK_SERVER", "device_key": "BARK_DEVICE_KEY",
              "sound": "BARK_SOUND", "group": "BARK_GROUP", "icon": "BARK_ICON"}, "Bark(环境变量)"),
    ("pushplus", {"token": "PUSHPLUS_TOKEN", "topic": "PUSHPLUS_TOPIC"}, "PushPlus(环境变量)"),
    ("wecom", {"corp_id": "WECOM_CORP_ID", "corp_secret": "WECOM_CORP_SECRET",
               "agent_id": "WECOM_AGENT_ID", "touser": "WECOM_TOUSER"}, "企业微信(环境变量)"),
    ("wxpusher", {"app_token": "WXPUSHER_APP_TOKEN", "uids": "WXPUSHER_UIDS",
                  "topic_ids": "WXPUSHER_TOPIC_IDS"}, "WxPusher(环境变量)"),
]
DEFAULT_TASK_TIMES = ["08:05", "12:05", "16:05", "20:05"]
DEFAULT_CONSOLE_PASSWORD = "admin"


def _default_console_auth(env: GlobalEnv) -> dict:
    """默认账号密码 admin/admin；CONSOLE_USERNAME/CONSOLE_PASSWORD 仅作首次初始化覆盖。"""
    return {
        "username": env.console_username or "admin",
        "password_sha256": _sha256(env.console_password or DEFAULT_CONSOLE_PASSWORD),
    }


class AppConfigStore:
    def __init__(self, env: GlobalEnv | None = None):
        self.env = env or GlobalEnv.from_env()
        self.path = Path(self.env.config_path)
        self.last_issue: str | None = None
        self._lock = threading.RLock()

    # ---- 读取 ----

    def load(self) -> AppConfig:
        with self._lock:
            payload = self._read_payload()
            if payload is None:  # 无文件或损坏
                return self._seed_from_env()
            return self._merge(payload)

    def _read_payload(self) -> dict | None:
        """存在且合法返回 payload；无文件/损坏返回 None（损坏时备份并记录 issue）。"""
        if not self.path.exists():
            self.last_issue = None
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("顶层不是 JSON 对象")
            self.last_issue = None
            return payload
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            backup = self.path.with_name(
                f"{self.path.name}.invalid-{datetime.now().strftime('%Y%m%d%H%M%S')}.bak"
            )
            try:
                self.path.replace(backup)
                self.last_issue = f"配置文件损坏已备份为 {backup.name}，当前使用兜底配置：{exc}"
            except OSError as backup_exc:
                self.last_issue = f"配置文件损坏且备份失败：{exc}（{backup_exc}）"
            log.warning(self.last_issue)
            return None

    def _merge(self, payload: dict) -> AppConfig:
        data = dict(payload)
        env = self.env
        if not str(data.get("rocom_api_key") or "").strip():
            data["rocom_api_key"] = env.api_key
        data.setdefault("shop_ids", ",".join(env.shop_ids))
        for key in ("wait_ms", "http_timeout", "max_retries", "retry_delay"):
            data.setdefault(key, getattr(env, key))
        data.setdefault("title_prefix", env.title_prefix)
        data.setdefault("log_retention_days", env.log_retention_days)
        data.setdefault("history_days", env.history_days)
        data.setdefault("run_on_start", env.run_on_start)
        if not data.get("channels"):
            data["channels"] = self._env_channels()
        if not data.get("tasks") and data["channels"]:
            data["tasks"] = [{
                "name": "每次刷新推送",
                "times": DEFAULT_TASK_TIMES,
                "channel_ids": [c["id"] for c in data["channels"]],
                "only_on_change": False,
            }]
        if not data.get("console_auth"):
            data["console_auth"] = _default_console_auth(env)
        return AppConfig.from_mapping(data)

    def _seed_from_env(self) -> AppConfig:
        env = self.env
        channels = self._env_channels()
        payload = {
            "rocom_api_key": env.api_key,
            "shop_ids": ",".join(env.shop_ids),
            "wait_ms": env.wait_ms,
            "http_timeout": env.http_timeout,
            "max_retries": env.max_retries,
            "retry_delay": env.retry_delay,
            "title_prefix": env.title_prefix,
            "log_retention_days": env.log_retention_days,
            "history_days": env.history_days,
            "run_on_start": env.run_on_start,
            "channels": channels,
            "tasks": [],
            "console_auth": _default_console_auth(env),
        }
        if channels:
            payload["tasks"] = [{
                "id": "task-default",
                "name": "每次刷新推送",
                "times": DEFAULT_TASK_TIMES,
                "channel_ids": [c["id"] for c in channels],
                "only_on_change": False,
            }]
        return AppConfig.from_mapping(payload)

    def _env_channels(self) -> list[dict]:
        """环境变量里配了凭据的渠道 → 播种为实例（dict 形态，与配置文件一致）。"""
        out: list[dict] = []
        for ctype, field_envs, name in ENV_CHANNEL_SEEDS:
            config = {}
            for field_name, env_name in field_envs.items():
                value = os.environ.get(env_name, "").strip()
                if value:
                    config[field_name] = value
            if not config:
                continue
            try:
                inst = ChannelInstance.from_mapping({
                    "id": f"{ctype}-env", "type": ctype, "name": name,
                    "config": config,
                })
            except ValueError:
                continue
            if not inst.missing_fields():
                out.append(inst.to_dict())
        return out

    # ---- 写入 ----

    def save_public(self, data: dict) -> AppConfig:
        """保存 WebUI 提交的配置（密钥留空保留旧值，console_auth 不经由该接口修改）。"""
        with self._lock:
            old_payload = self._read_payload()
            old_cfg = self._merge(old_payload) if old_payload is not None else self._seed_from_env()

            incoming = dict(data)
            # 全局 API Key：留空保留旧值
            if not str(incoming.get("rocom_api_key") or "").strip():
                incoming["rocom_api_key"] = old_cfg.rocom_api_key
            # 渠道实例密钥：留空保留旧值
            old_by_id = {c.id: c for c in old_cfg.channels}
            for item in incoming.get("channels") or []:
                old = old_by_id.get(str(item.get("id") or ""))
                if old is None:
                    continue
                for field_name in secret_fields(str(item.get("type"))):
                    if not str((item.get("config") or {}).get(field_name) or "").strip():
                        old_value = old.config.get(field_name)
                        if old_value:
                            item.setdefault("config", {})[field_name] = old_value

            cfg = AppConfig.from_mapping(incoming)
            cfg.console_auth = old_cfg.console_auth  # 登录凭据不经由本接口修改
            self._write(cfg.to_dict())
            return cfg

    def save_console_password(self, username: str, password: str) -> None:
        with self._lock:
            payload = self._read_payload() or self._seed_from_env().to_dict()
            payload["console_auth"] = (
                {"username": username or "admin", "password_sha256": _sha256(password)}
                if password else {}
            )
            self._write(payload)

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in payload.items() if k != "has_rocom_api_key"}
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        self.last_issue = None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
