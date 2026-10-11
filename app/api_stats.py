"""远行商人接口调用计数：按请求方法与路径持久化，区分成功/失败，不保存请求参数或凭据。

成功 = 该次尝试成功取得数据（业务 code 正常）；网络错误、202 未就绪、HTTP 5xx/4xx、
业务失败均计为失败。旧版仅计总数的库文件首次打开时自动补列并把历史计数视为成功。
"""

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
            ok_count INTEGER NOT NULL DEFAULT 0,
            last_called_at TEXT NOT NULL, PRIMARY KEY (method, path)
        )""")
        self._migrate(conn)
        return conn

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(calls)")}
        if "ok_count" not in cols:
            conn.execute("ALTER TABLE calls ADD COLUMN ok_count INTEGER NOT NULL DEFAULT 0")
            conn.execute("UPDATE calls SET ok_count = count")  # 历史数据无成功标记，按成功处理
            conn.commit()

    def record(self, method: str, path: str, ok: bool) -> None:
        # 统计写入失败不影响接口请求；并发更新由数据库事务保证。
        try:
            conn = self._connect()
            try:
                with conn:
                    # 显式列名：迁移过的旧库经 ALTER TABLE 补列后物理列序与新建表不同
                    conn.execute("""INSERT INTO calls (method, path, count, ok_count, last_called_at)
                        VALUES (?, ?, 1, ?, ?)
                        ON CONFLICT(method, path) DO UPDATE SET
                        count = count + 1,
                        ok_count = ok_count + excluded.ok_count,
                        last_called_at = excluded.last_called_at""",
                        (method, path, 1 if ok else 0,
                         datetime.now().astimezone().isoformat(timespec="seconds")))
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            log.warning("API 调用统计保存失败", exc_info=True)

    def query(self) -> dict:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT method, path, count, ok_count, last_called_at FROM calls "
                "ORDER BY count DESC, method, path"
            ).fetchall()
        finally:
            conn.close()
        items = [{"method": m, "path": p, "count": c, "ok": ok, "fail": c - ok,
                  "last_called_at": t}
                 for m, p, c, ok, t in rows]
        return {
            "total": sum(i["count"] for i in items),
            "ok": sum(i["ok"] for i in items),
            "fail": sum(i["fail"] for i in items),
            "items": items,
        }
