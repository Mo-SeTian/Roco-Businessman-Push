"""Bark  https://bark.day.app （支持自建服务器）"""

from __future__ import annotations


from .common import http_get, http_post

from .common import truncate_bytes


def send(config: dict, title: str, markdown: str, text: str) -> None:
    payload: dict = {
        "device_key": config["device_key"],
        "title": title,
        "body": truncate_bytes(text, 3800),
    }
    for key in ("sound", "group", "icon"):
        if config.get(key):
            payload[key] = config[key]
    server = config.get("server") or "https://api.day.app"
    resp = http_post(f"{server.rstrip('/')}/push", json=payload, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 200:
        raise RuntimeError(f"code={body.get('code')} {body.get('message')}")
