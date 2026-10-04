"""环境变量兜底配置（config.json 未覆盖时生效）。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


@dataclass
class GlobalEnv:
    api_base: str = "https://wegame.shallow.ink"
    api_key: str = ""
    shop_ids: list[str] = field(default_factory=list)
    wait_ms: int = 8000
    http_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 20
    title_prefix: str = "洛克王国远行商人"
    config_path: str = "data/config.json"
    state_path: str = "data/state.json"
    log_dir: str = "logs"
    log_retention_days: int = 7
    history_path: str = "data/history.json"
    history_days: int = 30
    web_host: str = "0.0.0.0"
    web_port: int = 19892
    console_username: str = "admin"
    console_password: str = ""  # 环境变量明文；为空且 config.json 也无密码时免登录
    run_on_start: bool = True

    @classmethod
    def from_env(cls, env: dict | None = None) -> "GlobalEnv":
        e = env if env is not None else os.environ
        config_path = e.get("CONFIG_PATH") or (
            "/data/config.json" if os.path.isdir("/data") else "data/config.json"
        )
        state_path = e.get("STATE_FILE") or (
            "/data/state.json" if os.path.isdir("/data") else "data/state.json"
        )
        log_dir = e.get("LOG_DIR") or ("/logs" if os.path.isdir("/logs") else "logs")
        history_path = e.get("HISTORY_FILE") or (
            "/data/history.json" if os.path.isdir("/data") else "data/history.json"
        )
        return cls(
            api_base=e.get("ROCOM_API_BASE", cls.api_base).rstrip("/"),
            api_key=e.get("ROCOM_API_KEY", "").strip(),
            shop_ids=_split(e.get("ROCOM_SHOP_ID")),
            wait_ms=_int(e.get("ROCOM_WAIT_MS"), 8000),
            http_timeout=_int(e.get("ROCOM_HTTP_TIMEOUT"), 30),
            max_retries=_int(e.get("ROCOM_MAX_RETRIES"), 3),
            retry_delay=_int(e.get("ROCOM_RETRY_DELAY"), 20),
            title_prefix=e.get("PUSH_TITLE_PREFIX", cls.title_prefix),
            config_path=config_path,
            state_path=state_path,
            log_dir=log_dir,
            log_retention_days=_int(e.get("LOG_RETENTION_DAYS"), 7),
            history_path=history_path,
            history_days=_int(e.get("HISTORY_DAYS"), 30),
            web_host=e.get("WEB_HOST", cls.web_host),
            web_port=_int(e.get("WEB_PORT"), 19892),
            console_username=e.get("CONSOLE_USERNAME", cls.console_username).strip() or "admin",
            console_password=e.get("CONSOLE_PASSWORD", "").strip(),
            run_on_start=_bool(e.get("RUN_ON_START"), True),
        )


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on", "y")
