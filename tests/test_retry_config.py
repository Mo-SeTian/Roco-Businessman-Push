import json
import tempfile
import unittest
from pathlib import Path

from app.config import GlobalEnv
from app.models import AppConfig
from app.store import AppConfigStore


class RetryConfigTests(unittest.TestCase):
    def test_defaults_equal_one_minute_and_ten_retries(self):
        for cfg in (GlobalEnv.from_env({}), AppConfig(), AppConfig.from_mapping({})):
            self.assertEqual((cfg.max_retries, cfg.retry_delay), (11, 60))
            self.assertEqual((cfg.push_max_retries, cfg.push_retry_delay), (11, 60))

    def test_environment_custom_values(self):
        cfg = GlobalEnv.from_env({"ROCOM_MAX_RETRIES": "5", "ROCOM_RETRY_DELAY": "120",
                                  "PUSH_MAX_RETRIES": "3", "PUSH_RETRY_DELAY": "180"})
        self.assertEqual((cfg.max_retries, cfg.retry_delay), (5, 120))
        self.assertEqual((cfg.push_max_retries, cfg.push_retry_delay), (3, 180))

    def test_legacy_defaults_upgrade_but_custom_settings_are_preserved(self):
        cfg = AppConfig.from_mapping({"max_retries": 3, "retry_delay": 20})
        self.assertEqual((cfg.max_retries, cfg.retry_delay), (11, 60))
        cfg = AppConfig.from_mapping({"max_retries": 5, "retry_delay": 120})
        self.assertEqual((cfg.max_retries, cfg.retry_delay), (5, 120))
        cfg = AppConfig.from_mapping({"retry_policy_version": 2, "max_retries": 3, "retry_delay": 20})
        self.assertEqual((cfg.max_retries, cfg.retry_delay), (3, 20))

    def test_settings_seed_save_and_reload(self):
        with tempfile.TemporaryDirectory() as root:
            env = GlobalEnv(config_path=str(Path(root) / "config.json"),
                            max_retries=3, retry_delay=20, push_max_retries=2, push_retry_delay=120)
            store = AppConfigStore(env)
            cfg = store.load()
            self.assertEqual((cfg.max_retries, cfg.retry_delay), (3, 20))
            saved = store.save_public(cfg.public_dict())
            reloaded = AppConfigStore(env).load()
            self.assertEqual(saved.to_dict(), reloaded.to_dict())
            self.assertEqual(reloaded.push_retry_delay, 120)
            raw = json.loads(Path(env.config_path).read_text())
            self.assertEqual(raw["retry_policy_version"], 2)

    def test_zero_retries_and_zero_interval_are_preserved(self):
        cfg = AppConfig.from_mapping({"max_retries": 1, "retry_delay": 0,
                                      "push_max_retries": 1, "push_retry_delay": 0})
        self.assertEqual((cfg.max_retries, cfg.retry_delay), (1, 0))
        self.assertEqual((cfg.push_max_retries, cfg.push_retry_delay), (1, 0))


if __name__ == "__main__":
    unittest.main()
