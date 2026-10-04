"""Server 酱·Turbo  https://sctapi.ftqq.com/{sendkey}.send"""

from __future__ import annotations

import requests


def send(config: dict, title: str, markdown: str, text: str) -> None:
    resp = requests.post(
        f"https://sctapi.ftqq.com/{config['sendkey']}.send",
        data={"title": title[:32], "desp": markdown},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(f"code={body.get('code')} {body.get('message')}")
