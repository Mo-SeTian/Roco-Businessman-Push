"""公共小工具：按字节数截断文本、带请求/响应日志的 HTTP 调用。"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

log = logging.getLogger("http")

# URL/响应中需要打码的敏感参数名片段
_SENSITIVE_KEYS = ("secret", "token", "key", "sendkey", "password")
# 响应体中的敏感字段（如企微 token 响应）
_BODY_REDACT = re.compile(r'("(?:access_token|secret|app_?token)"\s*:\s*")[^"]+(")')


def truncate_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    cut = raw[: max_bytes - 3].decode("utf-8", errors="ignore")
    return cut + "..."


def _redact_url(url: str) -> str:
    parts = urlparse(url)
    query = [
        (k, "****" if any(s in k.lower() for s in _SENSITIVE_KEYS) else v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    path = parts.path
    # Server 酱的 sendkey 嵌在路径里：/SCTxxxx.send
    if "sctapi.ftqq.com" in parts.netloc and len(path) > 1:
        segment = path[1:].split(".")[0]
        if segment:
            path = path.replace(segment, "****", 1)
    return urlunparse((parts.scheme, parts.netloc, path, "", urlencode(query), ""))


def _log_response(response: requests.Response, *_args, **_kwargs) -> None:
    try:
        body = _BODY_REDACT.sub(r"\1****\2", response.text)[:300].replace("\n", " ")
    except Exception:  # noqa: BLE001
        body = "<响应体读取失败>"
    elapsed_ms = int(response.elapsed.total_seconds() * 1000)
    log.info(
        "%s %s -> HTTP %d（%d ms）%s",
        response.request.method, _redact_url(response.request.url),
        response.status_code, elapsed_ms, body,
    )


def http_request(method: str, url: str, **kwargs) -> requests.Response:
    """带请求/响应日志的 HTTP 调用（渠道推送、接口拉取、token 获取统一走这里）。"""
    session = requests.Session()
    session.hooks["response"] = [_log_response]
    return session.request(method, url, timeout=kwargs.pop("timeout", 15), **kwargs)


def new_logged_session() -> requests.Session:
    """带响应日志钩子的持久会话（供需要复用连接的客户端使用）。"""
    session = requests.Session()
    session.hooks["response"] = [_log_response]
    return session


def http_get(url: str, **kwargs) -> requests.Response:
    return http_request("GET", url, **kwargs)


def http_post(url: str, **kwargs) -> requests.Response:
    return http_request("POST", url, **kwargs)
