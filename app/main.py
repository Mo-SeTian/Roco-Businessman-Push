"""入口。

  python -m app.main                 # Web 控制台 + 后台调度（默认）
  python -m app.main --scheduler     # 只跑调度，不启 Web
  python -m app.main --once          # 所有启用任务各执行一次后退出（配合外部 cron）
  python -m app.main --demo          # 用内置样例数据预览消息格式
  python -m app.main --show-config   # 打印当前生效配置（密钥打码）
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from . import format as fmt
from .config import GlobalEnv
from .history import HistoryStore
from .scheduler import SchedulerService
from .state import StateStore
from .store import AppConfigStore

SAMPLE_FILE = Path(__file__).resolve().parent.parent / "sample_data.json"


def setup_logging(level: str = "INFO", log_dir: str = "logs", retention_days: int = 7) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    # 环形缓冲供 Web 控制台「日志」页查看（采集级别跟随 LOG_LEVEL）
    from .logs import ring

    root.addHandler(ring)
    # 文件日志：按天滚动，保留 retention_days 天后自动清理
    from logging.handlers import TimedRotatingFileHandler

    try:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            Path(log_dir) / "rocom-push.log",
            when="midnight",
            backupCount=max(1, retention_days),
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
        root.addHandler(file_handler)
        from . import logs as app_logs
        app_logs.file_handler = file_handler
    except OSError as exc:
        logging.getLogger("main").warning("文件日志目录不可用（%s），仅保留控制台与内存日志", exc)


def run_once_all(store: AppConfigStore, state_store: StateStore) -> None:
    """执行所有启用任务一轮（尊重任务的"仅变化推送"），供外部 cron 调用。"""
    cfg = store.load()
    tasks = [t for t in cfg.tasks if t.enabled]
    if not tasks:
        print("没有启用的任务，退出")
        return
    scheduler = SchedulerService(store, state_store)
    scheduler._fire(cfg, tasks, force=False)  # noqa: SLF001 复用执行逻辑


def show_config(store: AppConfigStore) -> None:
    cfg = store.load()
    print(f"API: {store.env.api_base} | API Key: {'已配置' if cfg.rocom_api_key else '未配置!'}")
    print(f"商店: {','.join(cfg.shop_ids) or '默认(3009)'} | 标题前缀: {cfg.title_prefix}")
    print("渠道实例:")
    for c in cfg.channels:
        flag = "√" if not c.missing_fields() else "×缺配置"
        print(f"  [{flag}] {c.id:<16} {c.type:<10} {c.name}")
    print("任务:")
    for t in cfg.tasks:
        print(f"  [{'√' if t.enabled else '×'}] {t.name} @ {','.join(t.times)} -> {','.join(t.channel_ids) or '(无)'}")
    print(f"控制台登录: {'已启用' if cfg.console_auth.get('password_sha256') else '未启用（局域网免登录）'}")
    print(f"Web: http://{store.env.web_host}:{store.env.web_port}")


def run_demo(env: GlobalEnv) -> None:
    from types import SimpleNamespace

    payload = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    tpl = SimpleNamespace(
        title_prefix=env.title_prefix, title_template="", body_template="", goods_line_template="",
    )
    msg = fmt.build_message(payload, tpl)
    print(f"标题: {msg['title']}\n")
    print("----- Markdown（Server酱/PushPlus/企微/WxPusher）-----")
    print(msg["markdown"])
    print("\n----- 纯文本（Bark）-----")
    print(msg["text"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="洛克王国远行商人信息推送（Web 控制台版）")
    parser.add_argument("--once", action="store_true", help="执行所有启用任务一轮后退出")
    parser.add_argument("--demo", action="store_true", help="用内置样例数据预览消息格式")
    parser.add_argument("--show-config", action="store_true", help="打印当前生效配置（密钥打码）")
    parser.add_argument("--scheduler", action="store_true", help="只跑后台调度，不启动 Web 控制台")
    args = parser.parse_args(argv)

    env = GlobalEnv.from_env()
    store = AppConfigStore(env)
    cfg = store.load()
    setup_logging("INFO", env.log_dir, cfg.log_retention_days)

    if args.demo:
        run_demo(env)
        return 0

    state_store = StateStore(env.state_path)
    history_store = HistoryStore(env.history_path, cfg.history_days)

    if args.show_config:
        show_config(store)
        return 0

    if args.once:
        run_once_all(store, state_store)
        return 0

    if args.scheduler:
        scheduler = SchedulerService(store, state_store, history_store)
        scheduler.start()
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            scheduler.stop()
        return 0

    # 默认：Web 控制台 + 后台调度
    import uvicorn
    from .web import create_app

    app = create_app(store, SchedulerService(store, state_store, history_store))
    if not store.load().rocom_api_key:
        print("提示：尚未配置 API Key，请打开 Web 控制台在「全局设置」中填写。", flush=True)
    uvicorn.run(app, host=env.web_host, port=env.web_port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
