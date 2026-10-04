"""PushPlus  https://www.pushplus.plus/send"""

from __future__ import annotations


from .common import http_get, http_post

from .common import truncate_bytes

URL = "https://www.pushplus.plus/send"


def send(config: dict, title: str, markdown: str, text: str) -> None:
    payload: dict = {
        "token": config["token"],
        "title": title[:100],
        "content": truncate_bytes(markdown, 25000),
        "template": "markdown",
    }
    if config.get("topic"):
        payload["topic"] = config["topic"]
    resp = http_post(URL, json=payload, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 200:
        raise RuntimeError(f"code={body.get('code')} {body.get('msg')}")
