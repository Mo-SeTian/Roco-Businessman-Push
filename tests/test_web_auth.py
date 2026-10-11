"""控制台密码哈希升级（P2-2）与登录失败锁定（P2-1）。"""

import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from app import security
from app.models import AppConfig
from app.web import auth


def cfg_with(auth_dict: dict) -> AppConfig:
    return AppConfig.from_mapping({"channels": [], "tasks": [], "console_auth": auth_dict})


def legacy_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PasswordHashTests(unittest.TestCase):
    def test_pbkdf2_format_and_verify(self):
        stored = security.hash_password("s3cret")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(security.verify_password(stored, "s3cret"))
        self.assertFalse(security.verify_password(stored, "wrong"))
        self.assertNotEqual(security.hash_password("s3cret"), stored)  # 每次盐不同

    def test_legacy_sha256_still_verifies(self):
        legacy = legacy_hash("admin")
        self.assertTrue(security.is_legacy_hash(legacy))
        self.assertFalse(security.is_upgraded(legacy))
        self.assertTrue(security.verify_password(legacy, "admin"))
        self.assertFalse(security.verify_password(legacy, "x"))

    def test_malformed_pbkdf2_rejected(self):
        for bad in ("pbkdf2_sha256$abc$zz$dd", "pbkdf2_sha256$1$aa$", "", "not-a-hash"):
            self.assertFalse(security.verify_password(bad, "admin"), bad)

    def test_credentials_valid_both_formats(self):
        legacy_cfg = cfg_with({"username": "admin", "password_sha256": legacy_hash("pw")})
        self.assertTrue(auth.credentials_valid(legacy_cfg, "admin", "pw"))
        self.assertFalse(auth.credentials_valid(legacy_cfg, "admin", "nope"))
        upgraded = security.upgrade_auth(legacy_cfg.console_auth, "pw")
        self.assertNotIn("password_sha256", upgraded)
        new_cfg = cfg_with(upgraded)
        self.assertTrue(auth.credentials_valid(new_cfg, "admin", "pw"))
        self.assertFalse(auth.credentials_valid(new_cfg, "admin", "nope"))

    def test_upgrade_if_legacy(self):
        auth_dict = {"username": "admin", "password_sha256": legacy_hash("pw")}
        self.assertIsNone(auth.upgrade_if_legacy(auth_dict, "nope"))  # 密码不对不升级
        out = auth.upgrade_if_legacy(auth_dict, "pw")
        self.assertIn("password_hash", out)
        self.assertNotIn("password_sha256", out)
        self.assertIsNone(auth.upgrade_if_legacy(out, "pw"))  # 已是 PBKDF2 不再处理

    def test_auth_enabled_either_field(self):
        self.assertFalse(auth.auth_enabled(cfg_with({})))
        self.assertTrue(auth.auth_enabled(cfg_with({"password_sha256": "a" * 64})))
        self.assertTrue(auth.auth_enabled(cfg_with({"password_hash": security.hash_password("x")})))


class LoginLockoutTests(unittest.TestCase):
    def setUp(self):
        auth._failures.clear()
        self.addCleanup(auth._failures.clear)

    def test_locks_after_five_consecutive_failures(self):
        for _ in range(4):
            auth.register_login_failure("admin")
        self.assertEqual(auth.login_lock_remaining("admin"), 0)
        auth.register_login_failure("admin")
        remaining = auth.login_lock_remaining("admin")
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 301)

    def test_check_then_fail_sequence_locks(self):
        # 回归：登录路由每次都是先查锁定状态再记失败，查询不得清空计数（曾导致锁定永不触发）
        for _ in range(5):
            self.assertEqual(auth.login_lock_remaining("admin"), 0)
            auth.register_login_failure("admin")
        self.assertGreater(auth.login_lock_remaining("admin"), 0)

    def test_success_resets_counter(self):
        for _ in range(4):
            auth.register_login_failure("admin")
        auth.register_login_success("admin")
        auth.register_login_failure("admin")
        self.assertEqual(auth.login_lock_remaining("admin"), 0)

    def test_lock_expiry_resets_counting(self):
        for _ in range(5):
            auth.register_login_failure("admin")
        count, _ = auth._failures["admin"]
        auth._failures["admin"] = (count, time.time() - 1)  # 模拟锁定到期
        self.assertEqual(auth.login_lock_remaining("admin"), 0)
        auth.register_login_failure("admin")
        self.assertEqual(auth.login_lock_remaining("admin"), 0)  # 过期后从头计数

    def test_lockout_covers_wrong_username_too(self):
        # key 取配置中的用户名：无论提交的用户名是什么，失败都记在同一把锁上
        for _ in range(5):
            auth.register_login_failure("admin")
        self.assertGreater(auth.login_lock_remaining("admin"), 0)


if __name__ == "__main__":
    unittest.main()
