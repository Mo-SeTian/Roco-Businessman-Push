import sqlite3
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

    def test_grouping_restart_and_ok_split(self):
        self.assertEqual(self.stats.query(), {"total": 0, "ok": 0, "fail": 0, "items": []})
        self.stats.record("GET", "/first", True)
        self.stats.record("GET", "/first", False)
        self.stats.record("POST", "/second", True)
        result = APIStatsStore(str(self.stats.path)).query()
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["ok"], 2)
        self.assertEqual(result["fail"], 1)
        self.assertEqual([(r["method"], r["path"], r["count"], r["ok"], r["fail"])
                          for r in result["items"]],
                         [("GET", "/first", 2, 1, 1), ("POST", "/second", 1, 1, 0)])

    def test_concurrent_counts(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda ok: self.stats.record("GET", "/first", ok), [True, False] * 10))
        result = self.stats.query()
        self.assertEqual(result["total"], 20)
        self.assertEqual(result["ok"], 10)
        self.assertEqual(result["fail"], 10)

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
        self.assertEqual((result["ok"], result["fail"]), (1, 2))  # 503 与超时计失败
        self.assertEqual(result["items"][0]["path"], "/api/v1/games/rocom/ingame/merchant/info")
        self.assertNotIn("YOUR_API_KEY_HERE", str(result))
        self.assertNotIn("3009", str(result))

    def test_auth_failure_retries_are_counted(self):
        client = MerchantClient("YOUR_API_KEY_HERE", api_stats=self.stats, max_retries=3)
        self.addCleanup(client.session.close)
        with patch.object(client.session, "get", return_value=Mock(status_code=401, text="invalid")), \
             patch("app.rocom.time.sleep"):
            with self.assertRaises(RocomAPIError):
                client.fetch_merchant()
        result = self.stats.query()
        self.assertEqual((result["total"], result["ok"], result["fail"]), (3, 0, 3))

    def test_failed_statistics_write_does_not_block_request(self):
        client = MerchantClient("YOUR_API_KEY_HERE", api_stats=self.stats)
        self.addCleanup(client.session.close)
        success = Mock(status_code=200)
        success.json.return_value = {"code": 0}
        with patch.object(self.stats, "_connect", side_effect=OSError("read only")), \
             patch.object(client.session, "get", return_value=success), \
             self.assertLogs("api_stats", level="WARNING"):
            self.assertEqual(client.fetch_merchant(), {"code": 0})

    def test_legacy_schema_migrated(self):
        # 旧版只有 count 列：打开时自动补 ok_count 并把历史计数视为成功
        db = Path(self.tmp.name) / "legacy.sqlite3"
        conn = sqlite3.connect(str(db))
        conn.execute("""CREATE TABLE calls (
            method TEXT NOT NULL, path TEXT NOT NULL, count INTEGER NOT NULL,
            last_called_at TEXT NOT NULL, PRIMARY KEY (method, path))""")
        conn.execute("INSERT INTO calls VALUES ('GET', '/old', 7, '2026-10-01T08:00:00+08:00')")
        conn.commit()
        conn.close()
        result = APIStatsStore(str(db)).query()
        self.assertEqual((result["total"], result["ok"], result["fail"]), (7, 7, 0))
        # 迁移后继续正常累计
        APIStatsStore(str(db)).record("GET", "/old", False)
        result = APIStatsStore(str(db)).query()
        self.assertEqual((result["total"], result["ok"], result["fail"]), (8, 7, 1))


if __name__ == "__main__":
    unittest.main()
