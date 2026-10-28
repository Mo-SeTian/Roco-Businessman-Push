import unittest
from unittest.mock import Mock, patch

from app.channels import send_instance
from app.models import ChannelInstance


class ChannelRetryTests(unittest.TestCase):
    def setUp(self):
        self.inst = ChannelInstance(id="c", name="Bark test", type="bark",
                                    config={"device_key": "YOUR_DEVICE_KEY_HERE"})
        self.sender = Mock()
        sender_patch = patch.dict("app.channels._SENDERS", {"bark": self.sender})
        sender_patch.start()
        self.addCleanup(sender_patch.stop)
        sleep_patch = patch("app.channels.time.sleep")
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def test_success_does_not_retry(self):
        self.assertEqual(send_instance(self.inst, "title", "md", "text"), (True, "OK"))
        self.sender.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_failure_then_success_reuses_message(self):
        self.sender.send.side_effect = [RuntimeError("HTTP 524"), None]
        ok, detail = send_instance(self.inst, "title", "md", "text", max_retries=4, retry_delay=120)
        self.assertTrue(ok)
        self.assertIn("第 2 次", detail)
        self.assertEqual(self.sender.send.call_args_list[0], self.sender.send.call_args_list[1])
        self.sleep.assert_called_once_with(120)

    def test_default_exhaustion_is_ten_retries_without_last_sleep(self):
        self.sender.send.side_effect = RuntimeError("HTTP 524")
        ok, detail = send_instance(self.inst, "title", "md", "text")
        self.assertFalse(ok)
        self.assertIn("尝试 11 次", detail)
        self.assertIn("524", detail)
        self.assertEqual(self.sender.send.call_count, 11)
        self.assertEqual(self.sleep.call_count, 10)
        self.assertTrue(all(call.args == (60,) for call in self.sleep.call_args_list))

    def test_missing_config_does_not_attempt_sending(self):
        self.inst.config = {}
        self.assertFalse(send_instance(self.inst, "title", "md", "text")[0])
        self.sender.send.assert_not_called()
        self.sleep.assert_not_called()

    def test_no_retry_when_max_attempts_is_one(self):
        self.sender.send.side_effect = RuntimeError("failed")
        self.assertFalse(send_instance(self.inst, "title", "md", "text", max_retries=1)[0])
        self.sender.send.assert_called_once()
        self.sleep.assert_not_called()

    def test_error_and_logs_redact_channel_secrets(self):
        self.sender.send.side_effect = RuntimeError("bad key YOUR_DEVICE_KEY_HERE")
        with self.assertLogs("push", level="WARNING") as logs:
            ok, detail = send_instance(self.inst, "title", "md", "text", max_retries=2)
        self.assertFalse(ok)
        self.assertNotIn("YOUR_DEVICE_KEY_HERE", detail)
        self.assertNotIn("YOUR_DEVICE_KEY_HERE", str(logs.output))


if __name__ == "__main__":
    unittest.main()
