"""控制台密码哈希：PBKDF2-SHA256 加盐存储。

- 新密码一律写 PBKDF2（password_hash 字段，含迭代次数与随机盐）；
- 旧版无盐 SHA256（password_sha256）登录验证仍可用，验证通过后由登录流程透明升级；
- 供 store.py（播种/改密）与 web/auth.py（验证/升级）共用，保持格式单一出处。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

_ITERATIONS = 300_000
_PREFIX = "pbkdf2_sha256"
_LEGACY_RE = re.compile(r"[0-9a-f]{64}")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_PREFIX}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def is_legacy_hash(stored: str) -> bool:
    """旧版无盐 SHA256 的十六进制形态。"""
    return bool(_LEGACY_RE.fullmatch(str(stored or "")))


def verify_password(stored: str, password: str) -> bool:
    stored = str(stored or "")
    if stored.startswith(f"{_PREFIX}$"):
        try:
            _, iterations, salt_hex, hash_hex = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
            )
            return hmac.compare_digest(dk.hex(), hash_hex)
        except (ValueError, TypeError):
            return False
    if is_legacy_hash(stored):
        return hmac.compare_digest(_sha256(password), stored)
    return False


def is_upgraded(stored: str) -> bool:
    return str(stored or "").startswith(f"{_PREFIX}$")


def upgrade_auth(old_auth: dict, password: str) -> dict:
    """把通过验证的旧 SHA256 凭据替换为 PBKDF2，返回新的 console_auth 副本。"""
    new_auth = {k: v for k, v in old_auth.items() if k != "password_sha256"}
    new_auth["password_hash"] = hash_password(password)
    return new_auth
