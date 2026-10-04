"""WxPusher  https://wxpusher.zjiecode.com （UID 或 主题 任配一种）"""

from __future__ import annotations


from .common import http_get, http_post

from .common import truncate_bytes

URL = "https://wxpusher.zjiecode.com/api/send/message"


def send(config: dict, title: str, markdown: str, text: str) -> None:
    def _split(value: str) -> list[str]:
        return [item.strip() for item in (value or "").split(",") if item.strip()]

    payload: dict = {
        "appToken": config["app_token"],
        "summary": truncate_bytes(f"{title}｜{text}".replace("\n", " "), 90),
        "content": f"# {title}\n{markdown}",
        "contentType": 3,  # 1 文本 / 2 HTML / 3 Markdown
    }
    uids, topics = _split(config.get("uids")), _split(config.get("topic_ids"))
    if uids:
        payload["uids"] = uids
    if topics:
        payload["topicIds"] = topics
    if not uids and not topics:
        raise RuntimeError("uids 与 topic_ids 至少配置一个")
    resp = http_post(URL, json=payload, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success", body.get("code") == 1000):
        raise RuntimeError(f"code={body.get('code')} {body.get('msg')}")
