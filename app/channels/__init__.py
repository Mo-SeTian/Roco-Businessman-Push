"""渠道分发：按实例发送，逐渠道容错。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from . import bark, pushplus, serverchan, wecom, wxpusher
from .common import redact_text
from .manifest import CHANNEL_TYPES

if TYPE_CHECKING:  # 延迟引用，避免与 app.models 循环导入
    from ..models import ChannelInstance

log = logging.getLogger("push")

_SENDERS = {
    "serverchan": serverchan,
    "bark": bark,
    "pushplus": pushplus,
    "wecom": wecom,
    "wxpusher": wxpusher,
}

assert set(_SENDERS) == set(CHANNEL_TYPES), "manifest 与 sender 注册表不一致"


def send_instance(inst: "ChannelInstance", title: str, markdown: str, text: str, *,
                  max_retries: int = 11, retry_delay: int = 60) -> tuple[bool, str]:
    """向单个渠道实例推送，失败重试；max_retries 含首次发送。"""
    missing = inst.missing_fields()
    if missing:
        return False, f"缺少配置：{', '.join(missing)}"
    sender = _SENDERS.get(inst.type)
    if sender is None:
        return False, f"未知渠道类型 {inst.type}"
    attempts = max(1, max_retries)
    detail = ""
    for attempt in range(1, attempts + 1):
        try:
            sender.send(inst.resolved_config(), title, markdown, text)
            return True, "OK" if attempt == 1 else f"OK（第 {attempt} 次发送成功）"
        except Exception as exc:  # noqa: BLE001 单渠道失败不影响其他渠道
            detail = str(exc)
            for field in CHANNEL_TYPES[inst.type]["fields"]:
                value = inst.config.get(field["name"])
                if field.get("secret") and value:
                    detail = detail.replace(value, "<REDACTED>")
            detail = redact_text(detail)[:200]
            if attempt < attempts:
                log.warning("渠道 [%s(%s)] 推送失败（第 %d/%d 次）：%s；%ds 后重试",
                            inst.name, inst.type, attempt, attempts, detail, retry_delay)
                time.sleep(max(0, retry_delay))
    detail = f"尝试 {attempts} 次后仍失败：{detail}"
    log.error("渠道 [%s(%s)] 推送失败：%s", inst.name, inst.type, detail)
    return False, detail
