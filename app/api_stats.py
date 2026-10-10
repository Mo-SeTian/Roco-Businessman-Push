"""远行商人接口调用计数：按请求方法和路径持久化，不保存请求参数或凭据。"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger("api_stats")


class APIStatsStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.execute("""CREATE TABLE IF NOT EXISTS calls (
            method TEXT NOT NULL, path TEXT NOT NULL, count INTEGER NOT NULL,
            last_called_at TEXT NOT NULL, PRIMARY KEY (method, path)
        )""")
        return conn

    def record(self, method: str, path: str) -> None:
        # 统计写入失败不影响接口请求；并发更新由数据库事务保证。
        try:
            conn = self._connect()
            try:
                with conn:
                    conn.execute("""INSERT INTO calls VALUES (?, ?, 1, ?)
                        ON CONFLICT(method, path) DO UPDATE SET
                        count = count + 1, last_called_at = excluded.last_called_at""",
                        (method, path, datetime.now().astimezone().isoformat(timespec="seconds")))
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            log.warning("API 调用统计保存失败", exc_info=True)

    def query(self) -> dict:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT method, path, count, last_called_at FROM calls ORDER BY count DESC, method, path"
            ).fetchall()
        finally:
            conn.close()
        return {
            "total": sum(row[2] for row in rows),
            "items": [dict(zip(("method", "path", "count", "last_called_at"), row)) for row in rows],
        }
