"""控制台登录：账号密码 + 进程内会话令牌 + 登录失败锁定。"""

from __future__ import annotations

import hmac
import secrets
import threading
import time

from .. import security
from ..models import AppConfig

SESSION_COOKIE = "rocom_session"
SESSION_TTL = 7 * 24 * 3600

_LOGIN_MAX_FAILURES = 5      # 连续失败次数达到该值即锁定
_LOGIN_LOCKOUT_SECONDS = 300  # 锁定 5 分钟，期间正确的密码也会被拒绝

_tokens: dict[str, float] = {}
_failures: dict[str, tuple[int, float]] = {}  # key -> (连续失败次数, 锁定截止时间戳)
_lock = threading.Lock()


def auth_enabled(cfg: AppConfig) -> bool:
    return bool(cfg.console_auth.get("password_hash") or cfg.console_auth.get("password_sha256"))


def credentials_valid(cfg: AppConfig, username: str, password: str) -> bool:
    auth = cfg.console_auth
    user_ok = hmac.compare_digest(str(username), str(auth.get("username") or "admin"))
    stored = str(auth.get("password_hash") or auth.get("password_sha256") or "")
    return bool(user_ok and security.verify_password(stored, password))


def upgrade_if_legacy(auth: dict, password: str) -> dict | None:
    """旧版无盐 SHA256 验证通过后返回升级为 PBKDF2 的 console_auth；无需升级返回 None。"""
    if security.is_upgraded(str(auth.get("password_hash") or "")):
        return None
    legacy = str(auth.get("password_sha256") or "")
    if security.is_legacy_hash(legacy) and security.verify_password(legacy, password):
        return security.upgrade_auth(auth, password)
    return None


# ---- 登录失败锁定（key 一般为配置中的用户名） ----

def login_lock_remaining(key: str) -> int:
    """该 key 剩余锁定秒数；0 表示可尝试。只读，不清失败计数。"""
    with _lock:
        item = _failures.get(key)
        if not item:
            return 0
        remaining = item[1] - time.time()
        return int(remaining) + 1 if remaining > 0 else 0


def register_login_failure(key: str) -> None:
    with _lock:
        count, locked_until = _failures.get(key, (0, 0.0))
        if locked_until > time.time():
            return  # 锁定期间不累计新失败，锁定结束后从头再算
        if locked_until and locked_until <= time.time():
            count = 0  # 上次锁定已过期，重新计数
        count += 1
        locked_until = time.time() + _LOGIN_LOCKOUT_SECONDS if count >= _LOGIN_MAX_FAILURES else 0.0
        _failures[key] = (count, locked_until)


def register_login_success(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


# ---- 会话令牌 ----

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


def destroy_others(keep_token: str | None) -> None:
    """销毁除 keep_token 外的所有会话（修改密码后踢掉其他登录）。"""
    with _lock:
        for token in [t for t in _tokens if t != keep_token]:
            _tokens.pop(token, None)


def destroy_session(token: str | None) -> None:
    with _lock:
        _tokens.pop(token or "", None)
