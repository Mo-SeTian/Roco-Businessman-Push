import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from app.history import HistoryStore
from app.models import AppConfig, ChannelInstance, TaskConfig
from app.scheduler import SchedulerService
from app.state import StateStore


class HistoryPushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.history = HistoryStore(str(root / "history.json"))
        self.now = datetime.now().astimezone().replace(hour=13, minute=0)
        self.payload = json.loads(Path("sample_data.json").read_text())
        self.payload["data"]["meta"]["queried_at"] = self.now.isoformat()
        self.cfg = AppConfig(shop_ids=["3009"],
            channels=[ChannelInstance(id="c", name="test", type="bark", config={"key": "YOUR_API_KEY_HERE"})],
            tasks=[TaskConfig(id="t", name="test", times=["12:05"], channel_ids=["c"])])
        self.store = Mock()
        self.store.load.return_value = self.cfg
        self.store.env.api_base = "https://example.com"
        self.scheduler = SchedulerService(self.store, StateStore(str(root / "state.json")), self.history)
        clock = patch("app.scheduler.datetime").start()
        clock.now.return_value = self.now
        self.fetch = patch("app.scheduler.MerchantClient.fetch_merchant", return_value=self.payload).start()
        self.send = patch("app.scheduler.send_instance", return_value=(True, "ok")).start()
        self.addCleanup(patch.stopall)

    def test_history_hit_sends_without_request(self):
        self.history.add("3009", self.payload)
        self.scheduler.run_task_now("t", source="history")
        self.fetch.assert_not_called()
        self.send.assert_called_once()
        self.assertIn("美妙球", self.send.call_args.args[2])

    def test_missing_history_fetches_and_saves(self):
        self.scheduler.run_task_now("t", source="history")
        self.fetch.assert_called_once_with("3009")
        self.send.assert_called_once()
        self.assertEqual(self.history.current_payload("3009", self.now), self.payload)

    def test_fresh_request_replaces_history_and_persists(self):
        self.history.add("3009", self.payload)
        updated = deepcopy(self.payload)
        updated["goods_mapping"][0]["goods_name"] = "更新后的商品"
        self.fetch.return_value = updated
        self.scheduler.run_task_now("t", source="api")
        reloaded = HistoryStore(str(self.history.path))
        self.assertEqual(reloaded.current_payload("3009", self.now), updated)
        entry = reloaded.query(1)["3009"][self.now.date().isoformat()]["12:00"]
        self.assertEqual(entry["goods"][0]["name"], "更新后的商品")
        self.assertNotIn("payload", entry)
        self.fetch.reset_mock()
        self.scheduler.run_task_now("t", source="history")
        self.fetch.assert_not_called()
        self.assertIn("更新后的商品", self.send.call_args.args[2])

    def test_failed_request_keeps_previous_history(self):
        self.history.add("3009", self.payload)
        self.fetch.side_effect = RuntimeError("HTTP 503")
        self.scheduler.run_task_now("t", source="api")
        self.send.assert_not_called()
        self.assertEqual(self.history.current_payload("3009", self.now), self.payload)

    def test_other_slot_day_shop_and_before_open_do_not_match(self):
        self.history.add("3009", self.payload)
        for now in (self.now.replace(hour=16), self.now.replace(hour=7),
                    self.now.replace(year=self.now.year + 1)):
            with self.subTest(now=now):
                self.assertIsNone(self.history.current_payload("3009", now))
        self.assertIsNone(self.history.current_payload("3019", self.now))

    def test_old_history_falls_back(self):
        self.history._data = {"3009": {self.now.date().isoformat(): {"12:00": {"goods": []}}}}
        self.scheduler.run_task_now("t", source="history")
        self.fetch.assert_called_once()
        self.send.assert_called_once()

    def test_default_execution_requests_interface(self):
        self.history.add("3009", self.payload)
        self.scheduler.run_task_now("t")
        self.fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
