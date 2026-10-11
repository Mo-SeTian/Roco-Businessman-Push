"""配置导出/导入备份（store 层）。"""

import tempfile
import unittest
from pathlib import Path

from app.config import GlobalEnv
from app.store import AppConfigStore


def make_store(root: Path) -> AppConfigStore:
    env = GlobalEnv.from_env({
        "CONFIG_PATH": str(root / "config.json"),
        "STATE_FILE": str(root / "state.json"),
        "HISTORY_FILE": str(root / "history.json"),
        "LOG_DIR": str(root / "logs"),
        "ROCOM_API_KEY": "demo",
    })
    return AppConfigStore(env)


SAMPLE = {
    "rocom_api_key": "k1",
    "shop_ids": "3009,3019",
    "rare_goods": ["美妙球"],
    "channels": [{"id": "c1", "type": "bark", "name": "Bark", "config": {"device_key": "dk"}}],
    "tasks": [{"id": "t1", "name": "T", "times": ["08:05"], "channel_ids": ["c1"]}],
    "console_auth": {"username": "old", "password_sha256": "a" * 64},
}


class ConfigBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = make_store(Path(self.tmp.name))

    def test_import_export_roundtrip(self):
        self.store.import_config(SAMPLE)
        exported = self.store.export_config()
        self.assertEqual([c["id"] for c in exported["channels"]], ["c1"])
        self.assertEqual(exported["channels"][0]["config"]["device_key"], "dk")
        self.assertEqual(exported["shop_ids"], ["3009", "3019"])
        self.assertEqual(exported["rare_goods"], ["美妙球"])
        self.assertEqual(exported["tasks"][0]["times"], ["08:05"])

    def test_import_preserves_current_auth(self):
        self.store.import_config(SAMPLE)
        first = self.store.export_config()["console_auth"]
        self.assertNotEqual(first.get("username"), "old")  # 文件里的凭据被忽略
        changed = dict(SAMPLE, console_auth={"username": "hacker", "password_hash": "x"})
        self.store.import_config(changed)
        self.assertEqual(self.store.export_config()["console_auth"], first)  # 当前凭据始终保留

    def test_invalid_payload_rejected(self):
        for bad in ([1, 2, 3], {"channels": "abc", "tasks": []}, {"channels": 123, "tasks": []}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.store.import_config(bad)

    def test_import_reports_skipped_issues(self):
        bad_task = dict(SAMPLE, tasks=[{"name": "坏", "times": ["99:99"], "channel_ids": []}])
        cfg = self.store.import_config(bad_task)
        self.assertTrue(any("99:99" in i for i in cfg.issues))
        # 无效任务不写入；任务列表为空时加载侧会补默认任务（既有 merge 播种语义）
        names = [t["name"] for t in self.store.export_config()["tasks"]]
        self.assertNotIn("坏", names)

    def test_export_without_config_file(self):
        # 尚未写过配置文件时导出的是环境播种配置，同样完整可用
        exported = self.store.export_config()
        self.assertIn("console_auth", exported)
        self.assertTrue(exported["console_auth"].get("password_hash"))


if __name__ == "__main__":
    unittest.main()
