"""渠道分发：按实例发送，逐渠道容错。"""

from __future__ import annotations

import logging

from ..models import ChannelInstance
from . import bark, pushplus, serverchan, wecom, wxpusher
from .manifest import CHANNEL_TYPES

log = logging.getLogger("push")

_SENDERS = {
    "serverchan": serverchan,
    "bark": bark,
    "pushplus": pushplus,
    "wecom": wecom,
    "wxpusher": wxpusher,
}

assert set(_SENDERS) == set(CHANNEL_TYPES), "manifest 与 sender 注册表不一致"


def send_instance(inst: ChannelInstance, title: str, markdown: str, text: str) -> tuple[bool, str]:
    """向单个渠道实例推送。返回 (是否成功, 说明)。"""
    missing = inst.missing_fields()
    if missing:
        return False, f"缺少配置：{', '.join(missing)}"
    sender = _SENDERS.get(inst.type)
    if sender is None:
        return False, f"未知渠道类型 {inst.type}"
    try:
        sender.send(inst.resolved_config(), title, markdown, text)
        return True, "OK"
    except Exception as exc:  # noqa: BLE001 单渠道失败不影响其他渠道
        log.error("渠道 [%s(%s)] 推送失败：%s", inst.name, inst.type, exc)
        return False, str(exc)[:200]
