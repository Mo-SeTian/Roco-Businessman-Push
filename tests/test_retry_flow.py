import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from app.models import AppConfig, ChannelInstance, TaskConfig
from app.scheduler import SchedulerService
from app.state import StateStore


def response(status, payload=None):
    result = Mock(status_code=status, text=f"HTTP {status}")
    result.json.return_value = payload
    return result


class RetryFlowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = str(Path(tmp.name) / "state.json")
        self.channels = [
            ChannelInstance(id="a", name="Bark", type="bark", config={"device_key": "YOUR_DEVICE_KEY_HERE"}),
            ChannelInstance(id="b", name="Server酱", type="serverchan", config={"sendkey": "YOUR_SENDKEY_HERE"}),
        ]
        self.task = TaskConfig(id="t", name="测试任务", times=["12:05"], channel_ids=["a", "b"], only_on_change=True)
        self.cfg = AppConfig(channels=self.channels, tasks=[self.task], shop_ids=["3009"], push_max_retries=3)
        self.store = Mock()
        self.store.env.api_base = "https://example.com"
        self.store.load.return_value = self.cfg
        self.history = Mock()
        self.history.current_payload.return_value = None
        self.service = SchedulerService(self.store, StateStore(self.path), self.history)
        self.payload = json.loads(Path("sample_data.json").read_text())
        self.session = Mock(headers={})
        self.session.get.return_value = response(200, self.payload)
        self.a, self.b = Mock(), Mock()
        for patcher in [
            patch("app.rocom.new_logged_session", return_value=self.session),
            patch.dict("app.channels._SENDERS", {"bark": self.a, "serverchan": self.b}),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)
        for module in ("app.rocom", "app.channels"):
            patcher = patch(module + ".time")
            time_mock = patcher.start()
            self.addCleanup(patcher.stop)
            setattr(self, "fetch_wait" if module.endswith("rocom") else "push_wait", time_mock.sleep)

    def test_fetch_exhaustion_notifies_each_selected_channel(self):
        self.session.get.return_value = response(524)
        self.service.run_task_now("t")
        self.assertEqual(self.session.get.call_count, 11)
        self.assertEqual(self.fetch_wait.call_count, 10)
        for sender in (self.a, self.b):
            sender.send.assert_called_once()
            self.assertIn("商店数据获取失败", sender.send.call_args.args[1])
            self.assertIn("HTTP 524", sender.send.call_args.args[3])
            self.assertIn("11 次", sender.send.call_args.args[3])
        self.history.add.assert_not_called()
        self.assertIsNone(self.service.state_store.get_fingerprint("t:3009:a"))
        self.assertFalse(self.service.state["last_results"][0]["channels"][0]["ok"])
        self.assertIn("商店获取失败", self.service.state["last_message"])
        stats = self.service.api_stats.query()
        self.assertEqual((stats["total"], stats["ok"], stats["fail"]), (11, 0, 11))

    def test_fetch_recovers_then_sends_goods_without_failure_notice(self):
        self.session.get.side_effect = [response(524), response(200, self.payload)]
        self.service.run_task_now("t")
        self.assertEqual(self.session.get.call_count, 2)
        self.fetch_wait.assert_called_once_with(60)
        stats = self.service.api_stats.query()
        self.assertEqual((stats["total"], stats["ok"], stats["fail"]), (2, 1, 1))
        self.history.add.assert_called_once_with("3009", self.payload)
        for sender in (self.a, self.b):
            sender.send.assert_called_once()
            self.assertNotIn("获取失败", sender.send.call_args.args[1])
            self.assertIn("美妙球", sender.send.call_args.args[3])

    def test_failure_notice_retries_do_not_restart_fetch_or_recurse(self):
        self.cfg.max_retries = 2
        self.session.get.return_value = response(524)
        self.a.send.side_effect = RuntimeError("channel unavailable")
        self.service.run_task_now("t")
        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(self.a.send.call_count, 3)
        self.assertEqual(self.push_wait.call_count, 2)
        self.b.send.assert_called_once()
        results = self.service.state["last_results"][0]["channels"]
        self.assertFalse(results[1]["ok"])
        self.assertTrue(results[2]["ok"])

    def test_only_failed_channel_retries_and_payload_is_reused(self):
        self.b.send.side_effect = [RuntimeError("HTTP 524"), None]
        self.service.run_task_now("t")
        self.session.get.assert_called_once()
        self.a.send.assert_called_once()
        self.assertEqual(self.b.send.call_count, 2)
        self.assertEqual(self.b.send.call_args_list[0], self.b.send.call_args_list[1])
        self.push_wait.assert_called_once_with(60)

    def test_failed_channel_is_not_deduplicated_on_next_scheduled_run(self):
        self.b.send.side_effect = RuntimeError("unavailable")
        self.service._fire(self.cfg, [self.task], force=False)
        self.a.send.assert_called_once()
        self.assertEqual(self.b.send.call_count, 3)
        self.service.state_store = StateStore(self.path)
        self.assertIsNotNone(self.service.state_store.get_fingerprint("t:3009:a"))
        self.assertIsNone(self.service.state_store.get_fingerprint("t:3009:b"))
        self.b.send.side_effect = None
        self.service._fire(self.cfg, [self.task], force=False)
        self.a.send.assert_called_once()
        self.assertEqual(self.b.send.call_count, 4)
        self.service._fire(self.cfg, [self.task], force=False)
        self.assertEqual(self.b.send.call_count, 4)
        self.assertTrue(self.service.state["last_results"][0]["skipped"])

    def test_shared_channel_gets_one_failure_notice_per_shop(self):
        self.cfg.max_retries = 1
        self.cfg.tasks.append(TaskConfig(id="t2", name="任务二", times=["12:05"], channel_ids=["a"]))
        self.session.get.return_value = response(524)
        self.service.run_all_now()
        self.a.send.assert_called_once()
        self.b.send.assert_called_once()

    def test_notifications_do_not_go_to_disabled_or_unselected_channels(self):
        self.cfg.max_retries = 1
        self.channels[1].enabled = False
        self.channels.append(ChannelInstance(id="c", name="未选中", type="serverchan", config={"sendkey": "YOUR_SENDKEY_HERE"}))
        self.session.get.return_value = response(524)
        self.service.run_task_now("t")
        self.a.send.assert_called_once()
        self.b.send.assert_not_called()

    def test_concurrent_manual_run_returns_busy_without_queueing(self):
        entered, release = threading.Event(), threading.Event()
        def slow_fire(*args, **kwargs):
            entered.set()
            release.wait(timeout=5)
        with patch.object(self.service, "_fire", side_effect=slow_fire), ThreadPoolExecutor() as pool:
            first = pool.submit(self.service.run_task_now, "t")
            try:
                self.assertTrue(entered.wait(timeout=2))
                self.assertIn("正在执行", self.service.run_task_now("t"))
            finally:
                release.set()
                first.result(timeout=2)
        self.assertFalse(self.service.state["in_progress"])


if __name__ == "__main__":
    unittest.main()
