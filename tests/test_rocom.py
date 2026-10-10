import unittest
from unittest.mock import Mock, patch

import requests

from app.rocom import MerchantClient, RocomAPIError


def response(status, payload=None, text=""):
    result = Mock(status_code=status, text=text)
    result.json.return_value = payload
    return result


class MerchantRetryTests(unittest.TestCase):
    def setUp(self):
        self.client = MerchantClient("YOUR_API_KEY_HERE", max_retries=3, retry_delay=20)
        self.addCleanup(self.client.session.close)
        self.get = patch.object(self.client.session, "get").start()
        self.sleep = patch("app.rocom.time.sleep").start()
        self.addCleanup(patch.stopall)
        self.success = {"code": 0, "data": {"shop_id": 3009}}

    def test_transient_http_error_then_success(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                self.get.reset_mock()
                self.sleep.reset_mock()
                self.get.side_effect = [
                    response(status, text='{"code":5031,"message":"暂时无法获取商店数据，请稍后重试"}'),
                    response(200, self.success),
                ]
                self.assertEqual(self.client.fetch_merchant("3009"), self.success)
                self.assertEqual(self.get.call_count, 2)
                self.sleep.assert_called_once_with(20)
                self.assertEqual(self.get.call_args.kwargs["params"]["shop_id"], "3009")

    def test_exhausted_retries_preserve_last_error(self):
        self.get.return_value = response(503, text='{"code":5031,"message":"暂时无法获取商店数据"}')
        with self.assertRaisesRegex(RocomAPIError, "3.*HTTP 503.*5031"):
            self.client.fetch_merchant()
        self.assertEqual(self.get.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_network_failure_then_success(self):
        self.get.side_effect = [requests.Timeout("timed out"), response(200, self.success)]
        self.assertEqual(self.client.fetch_merchant(), self.success)
        self.sleep.assert_called_once_with(20)

    def test_pending_exhaustion_has_reason_and_no_final_sleep(self):
        for pending in (response(202), response(200, {"code": 202})):
            with self.subTest(status=pending.status_code):
                self.get.reset_mock()
                self.sleep.reset_mock()
                self.get.return_value = pending
                with self.assertRaisesRegex(RocomAPIError, "202"):
                    self.client.fetch_merchant()
                self.assertEqual(self.get.call_count, 3)
                self.assertEqual(self.sleep.call_count, 2)

    def test_permanent_errors_do_not_retry(self):
        for failure in (response(400), response(401), response(403),
                        response(200, {"code": 4001, "message": "invalid request"})):
            with self.subTest(status=failure.status_code):
                self.get.reset_mock()
                self.get.return_value = failure
                with self.assertRaises(RocomAPIError):
                    self.client.fetch_merchant()
                self.get.assert_called_once()
                self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
