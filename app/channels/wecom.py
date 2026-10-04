"""企业微信自建应用推送（markdown 消息，access_token 进程内缓存）。"""

from __future__ import annotations

import threading
import time

import requests

from .common import truncate_bytes

_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
_MARKDOWN_LIMIT = 4000  # 企微 markdown 消息上限 4096 字节，留余量

_token_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def _get_token(corp_id: str, corp_secret: str) -> str:
    cache_key = f"{corp_id}:{corp_secret}"
    with _lock:
        cached = _token_cache.get(cache_key)
        if cached and cached[1] > time.time():
            return cached[0]
    resp = requests.get(
        _TOKEN_URL, params={"corpid": corp_id, "corpsecret": corp_secret}, timeout=15
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("errcode") != 0:
        raise RuntimeError(f"token errcode={body.get('errcode')} {body.get('errmsg')}")
    with _lock:
        _token_cache[cache_key] = (
            body["access_token"],
            time.time() + int(body.get("expires_in", 7200)) - 300,
        )
    return body["access_token"]


def send(config: dict, title: str, markdown: str, text: str) -> None:
    token = _get_token(config["corp_id"], config["corp_secret"])
    content = truncate_bytes(f"## {title}\n{markdown}", _MARKDOWN_LIMIT)
    payload = {
        "touser": config.get("touser") or "@all",
        "msgtype": "markdown",
        "agentid": int(config["agent_id"]),
        "markdown": {"content": content},
    }
    resp = requests.post(_SEND_URL, params={"access_token": token}, json=payload, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("errcode") != 0:
        raise RuntimeError(f"send errcode={body.get('errcode')} {body.get('errmsg')}")
