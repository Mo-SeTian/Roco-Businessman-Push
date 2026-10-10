import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from app.api_stats import APIStatsStore
from app.rocom import MerchantClient, RocomAPIError


class APIStatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stats = APIStatsStore(str(Path(self.tmp.name) / "api_stats.sqlite3"))

    def test_grouping_and_restart(self):
        self.assertEqual(self.stats.query(), {"total": 0, "items": []})
        self.stats.record("GET", "/first")
        self.stats.record("GET", "/first")
        self.stats.record("POST", "/second")
        result = APIStatsStore(str(self.stats.path)).query()
        self.assertEqual(result["total"], 3)
        self.assertEqual([(r["method"], r["path"], r["count"]) for r in result["items"]],
                         [("GET", "/first", 2), ("POST", "/second", 1)])

    def test_concurrent_counts(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: self.stats.record("GET", "/first"), range(20)))
        self.assertEqual(self.stats.query()["total"], 20)

    def test_retries_and_network_errors_count_without_credentials(self):
        client = MerchantClient("YOUR_API_KEY_HERE", api_stats=self.stats)
        self.addCleanup(client.session.close)
        success = Mock(status_code=200)
        success.json.return_value = {"code": 0}
        with patch.object(client.session, "get", side_effect=[
            Mock(status_code=503, text="unavailable"), requests.Timeout(), success
        ]), patch("app.rocom.time.sleep"):
            client.fetch_merchant("3009")
        result = self.stats.query()
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["items"][0]["path"], "/api/v1/games/rocom/ingame/merchant/info")
        self.assertNotIn("YOUR_API_KEY_HERE", str(result))
        self.assertNotIn("3009", str(result))

    def test_auth_failure_is_one_call(self):
        client = MerchantClient("YOUR_API_KEY_HERE", api_stats=self.stats)
        self.addCleanup(client.session.close)
        with patch.object(client.session, "get", return_value=Mock(status_code=401, text="invalid")):
            with self.assertRaises(RocomAPIError):
                client.fetch_merchant()
        self.assertEqual(self.stats.query()["total"], 1)

    def test_failed_statistics_write_does_not_block_request(self):
        client = MerchantClient("YOUR_API_KEY_HERE", api_stats=self.stats)
        self.addCleanup(client.session.close)
        success = Mock(status_code=200)
        success.json.return_value = {"code": 0}
        with patch.object(self.stats, "_connect", side_effect=OSError("read only")), \
             patch.object(client.session, "get", return_value=success), \
             self.assertLogs("api_stats", level="WARNING"):
            self.assertEqual(client.fetch_merchant(), {"code": 0})


if __name__ == "__main__":
    unittest.main()
