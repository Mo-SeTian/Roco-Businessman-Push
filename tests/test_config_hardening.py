"""配置解析加固（P1-1）与调度状态快照隔离（P1-2）。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.models import AppConfig
from app.scheduler import SchedulerService
from app.state import StateStore


class InvalidTaskConfigTests(unittest.TestCase):
    def test_invalid_time_skipped_with_issue(self):
        cfg = AppConfig.from_mapping({
            "channels": [{"id": "c1", "type": "bark", "name": "Bark", "config": {"key": "x"}}],
            "tasks": [
                {"id": "t-bad", "name": "坏时间任务", "times": ["99:99"], "channel_ids": ["c1"]},
                {"id": "t-ok", "name": "正常任务", "times": ["08:05"], "channel_ids": ["c1"]},
            ],
        })
        self.assertEqual([t.id for t in cfg.tasks], ["t-ok"])
        self.assertTrue(any("坏时间任务" in i and "99:99" in i for i in cfg.issues))

    def test_empty_times_task_skipped(self):
        cfg = AppConfig.from_mapping({
            "channels": [], "tasks": [{"name": "没时间任务", "times": [], "channel_ids": []}],
        })
        self.assertEqual(cfg.tasks, [])
        self.assertTrue(any("没时间任务" in i for i in cfg.issues))

    def test_invalid_channel_still_skipped(self):
        cfg = AppConfig.from_mapping({
            "channels": [{"id": "c1", "type": "no-such-type", "name": "坏渠道"}],
            "tasks": [],
        })
        self.assertEqual(cfg.channels, [])
        self.assertTrue(any("坏渠道" in i for i in cfg.issues))


class SnapshotStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = Mock()
        store.env.api_base = "https://example.com"
        self.scheduler = SchedulerService(store, StateStore(str(Path(self.tmp.name) / "state.json")))

    def test_snapshot_is_deep_copy(self):
        self.scheduler.state["run_history"] = [{"time": "t0", "reason": "r", "results": []}]
        snap = self.scheduler.snapshot_state()
        snap["run_history"].append({"time": "t1", "reason": "r", "results": []})
        snap["last_message"] = "改动"
        self.assertEqual(len(self.scheduler.state["run_history"]), 1)
        self.assertNotEqual(self.scheduler.state["last_message"], "改动")

    def test_snapshot_reflects_current_values(self):
        self.scheduler.state["last_message"] = "完成：1/1 项推送成功"
        self.assertEqual(self.scheduler.snapshot_state()["last_message"], "完成：1/1 项推送成功")


if __name__ == "__main__":
    unittest.main()
