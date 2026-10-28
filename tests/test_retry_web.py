import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from app.config import GlobalEnv
from app.store import AppConfigStore
from app.web import create_app
from app.web.auth import SESSION_COOKIE, create_session


class RetryWebTests(unittest.TestCase):
    def test_channel_test_uses_saved_retry_policy(self):
        with tempfile.TemporaryDirectory() as root:
            env = GlobalEnv(config_path=str(Path(root) / "config.json"),
                            state_path=str(Path(root) / "state.json"),
                            history_path=str(Path(root) / "history.json"),
                            push_max_retries=4, push_retry_delay=120)
            client = TestClient(create_app(AppConfigStore(env)))
            client.cookies.set(SESSION_COOKIE, create_session())
            with patch("app.web.send_instance", return_value=(True, "OK")) as send:
                result = client.post("/api/test-channel", json={"instance": {
                    "type": "bark", "name": "test", "config": {"device_key": "YOUR_DEVICE_KEY_HERE"}
                }})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(send.call_args.kwargs, {"max_retries": 4, "retry_delay": 120})
            result = client.get("/api/state").json()["config"]
            result.update(max_retries=6, retry_delay=180, push_max_retries=1, push_retry_delay=0)
            self.assertEqual(client.post("/api/config", json=result).status_code, 200)
            saved = client.get("/api/state").json()["config"]
            self.assertEqual((saved["max_retries"], saved["retry_delay"]), (6, 180))
            self.assertEqual((saved["push_max_retries"], saved["push_retry_delay"]), (1, 0))


class RetryWebConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_console_remains_responsive_during_manual_retry(self):
        with tempfile.TemporaryDirectory() as root:
            store = AppConfigStore(GlobalEnv(config_path=str(Path(root) / "config.json"),
                state_path=str(Path(root) / "state.json"), history_path=str(Path(root) / "history.json")))
            scheduler = Mock()
            scheduler.state = {"in_progress": True}
            scheduler.snapshot_state.return_value = scheduler.state
            entered, release = threading.Event(), threading.Event()
            def waiting_task(*args, **kwargs):
                entered.set()
                release.wait(timeout=3)
                return "完成"
            scheduler.run_task_now.side_effect = waiting_task
            app = create_app(store, scheduler)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                    cookies={SESSION_COOKIE: create_session()}) as client:
                pending = asyncio.create_task(client.post("/api/run-task", json={"id": "t"}))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(0.01)
                    self.assertTrue(entered.is_set())
                    result = await asyncio.wait_for(client.get("/api/state"), timeout=1)
                    self.assertEqual(result.status_code, 200)
                    self.assertTrue(result.json()["scheduler"]["in_progress"])
                finally:
                    release.set()
                    result = await pending
                self.assertEqual(result.status_code, 200)


if __name__ == "__main__":
    unittest.main()
