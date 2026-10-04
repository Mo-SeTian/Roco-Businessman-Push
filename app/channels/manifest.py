"""渠道类型清单：声明每种渠道的字段（label/required/secret/default）。

WebUI 表单和后端校验都由这里驱动；新增渠道类型只需在此登记并实现 sender。
"""

from __future__ import annotations

CHANNEL_TYPES: dict[str, dict] = {
    "serverchan": {
        "label": "Server 酱",
        "fields": [
            {"name": "sendkey", "label": "SendKey", "required": True, "secret": True},
        ],
    },
    "bark": {
        "label": "Bark",
        "fields": [
            {"name": "server", "label": "服务器地址", "default": "https://api.day.app"},
            {"name": "device_key", "label": "设备 Key", "required": True, "secret": True},
            {"name": "sound", "label": "铃声（可选）"},
            {"name": "group", "label": "分组（可选）"},
            {"name": "icon", "label": "图标 URL（可选）"},
        ],
    },
    "pushplus": {
        "label": "PushPlus",
        "fields": [
            {"name": "token", "label": "Token", "required": True, "secret": True},
            {"name": "topic", "label": "群组编码（留空发本人）"},
        ],
    },
    "wecom": {
        "label": "企业微信应用",
        "fields": [
            {"name": "corp_id", "label": "企业 ID（CorpID）", "required": True, "secret": True},
            {"name": "corp_secret", "label": "应用 Secret", "required": True, "secret": True},
            {"name": "agent_id", "label": "应用 AgentId", "required": True},
            {"name": "touser", "label": "接收人（@all 或用户账号）", "default": "@all"},
        ],
    },
    "wxpusher": {
        "label": "WxPusher",
        "fields": [
            {"name": "app_token", "label": "AppToken", "required": True, "secret": True},
            {"name": "uids", "label": "接收者 UID（逗号分隔）"},
            {"name": "topic_ids", "label": "主题 ID（逗号分隔）"},
        ],
    },
}


def channel_label(channel_type: str) -> str:
    return CHANNEL_TYPES.get(channel_type, {}).get("label", channel_type)


def channel_fields(channel_type: str) -> list[dict]:
    return CHANNEL_TYPES.get(channel_type, {}).get("fields", [])


def required_fields(channel_type: str) -> set[str]:
    return {f["name"] for f in channel_fields(channel_type) if f.get("required")}


def secret_fields(channel_type: str) -> set[str]:
    return {f["name"] for f in channel_fields(channel_type) if f.get("secret")}


def field_default(channel_type: str, field_name: str) -> str | None:
    for f in channel_fields(channel_type):
        if f["name"] == field_name and "default" in f:
            return f["default"]
    return None
