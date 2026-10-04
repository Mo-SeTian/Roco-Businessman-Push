"""控制台登录：账号密码 + 进程内会话令牌。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

from ..models import AppConfig

SESSION_COOKIE = "rocom_session"
SESSION_TTL = 7 * 24 * 3600

_tokens: dict[str, float] = {}
_lock = threading.Lock()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def auth_enabled(cfg: AppConfig) -> bool:
    return bool(cfg.console_auth.get("password_sha256"))


def credentials_valid(cfg: AppConfig, username: str, password: str) -> bool:
    auth = cfg.console_auth
    user_ok = hmac.compare_digest(str(username), str(auth.get("username") or "admin"))
    pass_ok = hmac.compare_digest(_sha256(password), str(auth.get("password_sha256") or ""))
    return user_ok and pass_ok


def create_session() -> str:
    token = secrets.token_hex(32)
    with _lock:
        _tokens[token] = time.time() + SESSION_TTL
        expired = [t for t, exp in _tokens.items() if exp < time.time()]
        for t in expired:
            _tokens.pop(t, None)
    return token


def session_valid(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        expiry = _tokens.get(token)
        if expiry is None:
            return False
        if expiry < time.time():
            _tokens.pop(token, None)
            return False
    return True


def destroy_session(token: str | None) -> None:
    with _lock:
        _tokens.pop(token or "", None)
