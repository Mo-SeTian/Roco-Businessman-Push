"""配置/任务/渠道实例的数据模型（可 JSON 序列化）。"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime

from .channels.manifest import CHANNEL_TYPES, channel_fields, required_fields

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


def normalize_times(raw: list[str] | None) -> list[str]:
    """校验并归一化 HH:MM 列表（去重、排序）。非法值抛 ValueError。"""
    out: set[str] = set()
    for item in raw or []:
        text = str(item).strip()
        m = _TIME_RE.match(text)
        if not m:
            raise ValueError(f"无效的时间：{text!r}（应为 HH:MM）")
        hour, minute = int(m.group(1)), int(m.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"无效的时间：{text!r}")
        out.add(f"{hour:02d}:{minute:02d}")
    if not out:
        raise ValueError("任务至少需要一个触发时间")
    return sorted(out)


@dataclass
class ChannelInstance:
    id: str
    type: str
    name: str
    enabled: bool = True
    config: dict = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict) -> "ChannelInstance":
        ctype = str(data.get("type", "")).strip()
        if ctype not in CHANNEL_TYPES:
            raise ValueError(f"未知渠道类型：{ctype}")
        return cls(
            id=str(data.get("id") or new_id("ch")).strip(),
            type=ctype,
            name=str(data.get("name") or "").strip() or CHANNEL_TYPES[ctype]["label"],
            enabled=bool(data.get("enabled", True)),
            config={str(k): ("" if v is None else str(v)).strip() for k, v in (data.get("config") or {}).items()},
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "name": self.name,
            "enabled": self.enabled, "config": dict(self.config),
        }

    def missing_fields(self) -> list[str]:
        """缺配置的必填字段 label 列表（可选字段不算缺失；有默认值视为已填）。"""
        missing = []
        for f in channel_fields(self.type):
            if not f.get("required"):
                continue
            if not (self.config.get(f["name"]) or f.get("default") or "").strip():
                missing.append(f["label"])
        return missing

    def public_view(self) -> dict:
        """密钥打码的对外视图（供 WebUI 回显）。"""
        data = self.to_dict()
        masked = dict(data["config"])
        for f in channel_fields(self.type):
            if f.get("secret") and masked.get(f["name"]):
                masked[f["name"]] = ""
                masked[f"has_{f['name']}"] = True
        data["config"] = masked
        return data

    def resolved_config(self) -> dict:
        """补上字段默认值后的完整配置（供发送器使用）。"""
        config = dict(self.config)
        for f in channel_fields(self.type):
            if not config.get(f["name"]) and f.get("default") is not None:
                config[f["name"]] = f["default"]
        return config


@dataclass
class TaskConfig:
    id: str
    name: str
    times: list[str]
    channel_ids: list[str]
    enabled: bool = True
    only_on_change: bool = False  # 默认每次都按接口返回推送；开启后与上次返回完全一致时跳过

    @classmethod
    def from_mapping(cls, data: dict) -> "TaskConfig":
        return cls(
            id=str(data.get("id") or new_id("task")).strip(),
            name=str(data.get("name") or "").strip() or "未命名任务",
            times=normalize_times(data.get("times")),
            channel_ids=[str(c).strip() for c in (data.get("channel_ids") or []) if str(c).strip()],
            enabled=bool(data.get("enabled", True)),
            only_on_change=bool(data.get("only_on_change", False)),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "times": list(self.times),
            "channel_ids": list(self.channel_ids), "enabled": self.enabled,
            "only_on_change": self.only_on_change,
        }

    def due_at(self, now: datetime) -> bool:
        return now.strftime("%H:%M") in self.times


def _parse_shop_ids(raw: Any) -> list[str]:
    """商店 ID 兼容字符串（"3009,3019"）与数组两种形态，并清洗历史污染数据。"""
    if isinstance(raw, str):
        parts = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        parts = [str(item) for item in raw]
    else:
        parts = []
    out = []
    for item in parts:
        # 清掉历史 bug 造成的引号/方括号包裹，如 "['3009']"
        cleaned = re.sub(r"[\[\]'\"]", "", str(item)).strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


@dataclass
class AppConfig:
    rocom_api_key: str = ""
    shop_ids: list[str] = field(default_factory=list)  # 空 = 服务端默认 3009
    wait_ms: int = 8000
    http_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 20
    title_prefix: str = "洛克王国远行商人"
    log_retention_days: int = 7    # 文件日志保留天数
    history_days: int = 30         # 调用历史保留天数
    channels: list[ChannelInstance] = field(default_factory=list)
    tasks: list[TaskConfig] = field(default_factory=list)
    console_auth: dict = field(default_factory=dict)  # {username, password_sha256}

    def to_dict(self) -> dict:
        return {
            "rocom_api_key": self.rocom_api_key,
            "shop_ids": list(self.shop_ids),
            "wait_ms": self.wait_ms,
            "http_timeout": self.http_timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "title_prefix": self.title_prefix,
            "log_retention_days": self.log_retention_days,
            "history_days": self.history_days,
            "channels": [c.to_dict() for c in self.channels],
            "tasks": [t.to_dict() for t in self.tasks],
            "console_auth": dict(self.console_auth),
        }

    def public_dict(self) -> dict:
        data = self.to_dict()
        data["rocom_api_key"] = ""
        data["has_rocom_api_key"] = bool(self.rocom_api_key)
        data["channels"] = [c.public_view() for c in self.channels]
        data.pop("console_auth", None)
        data["auth_enabled"] = bool(self.console_auth.get("password_sha256"))
        return data

    def channel_map(self) -> dict[str, ChannelInstance]:
        return {c.id: c for c in self.channels}

    def enabled_channels_of(self, task: TaskConfig) -> list[ChannelInstance]:
        cmap = self.channel_map()
        return [cmap[cid] for cid in task.channel_ids if cid in cmap and cmap[cid].enabled]

    @classmethod
    def from_mapping(cls, data: dict) -> "AppConfig":
        channels = [ChannelInstance.from_mapping(c) for c in data.get("channels") or []]
        tasks = [TaskConfig.from_mapping(t) for t in data.get("tasks") or []]
        # 任务引用的渠道必须存在
        known = {c.id for c in channels}
        for t in tasks:
            unknown = [cid for cid in t.channel_ids if cid not in known]
            if unknown:
                raise ValueError(f"任务「{t.name}」引用了不存在的渠道：{', '.join(unknown)}")
        return cls(
            rocom_api_key=str(data.get("rocom_api_key") or "").strip(),
            shop_ids=_parse_shop_ids(data.get("shop_ids")),
            wait_ms=_int(data.get("wait_ms"), 8000),
            http_timeout=_int(data.get("http_timeout"), 30),
            max_retries=_int(data.get("max_retries"), 3),
            retry_delay=_int(data.get("retry_delay"), 20),
            title_prefix=str(data.get("title_prefix") or "").strip() or "洛克王国远行商人",
            log_retention_days=_int(data.get("log_retention_days"), 7),
            history_days=_int(data.get("history_days"), 30),
            channels=channels,
            tasks=tasks,
            console_auth=dict(data.get("console_auth") or {}),
        )


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def now_ts() -> int:
    return int(time.time())
