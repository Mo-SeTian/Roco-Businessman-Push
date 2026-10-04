"""进程内环形日志缓冲，供 Web 控制台「日志」页查看与筛选。"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from threading import Lock

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 2000):
        super().__init__()
        self._buf: deque[dict] = deque(maxlen=capacity)
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 日志格式化失败也不能抛进日志系统
            message = "<日志格式化失败>"
        entry = {
            "ts": datetime.fromtimestamp(record.created).strftime("%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": message[:2000],
        }
        with self._lock:
            self._buf.append(entry)

    def query(self, min_level: str = "DEBUG", limit: int = 500) -> list[dict]:
        floor = _LEVELS.get(min_level.upper(), 10)
        with self._lock:
            items = list(self._buf)
        return [e for e in items if _LEVELS.get(e["level"], 20) >= floor][-limit:]


# 模块级单例：setup_logging() 挂到 root logger，Web 路由读取同一实例
ring = RingBufferHandler()
