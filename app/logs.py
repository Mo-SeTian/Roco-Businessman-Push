"""进程内环形日志缓冲，供 Web 控制台「日志」页查看与筛选。"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from threading import Lock

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class RingBufferHandler(logging.Handler):
    """内存环形缓冲。消息不截断（仅 50000 字符防御上限），前端负责长文本折叠展示。"""

    MAX_MSG = 50000

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
            "message": message[: self.MAX_MSG],
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
# 文件日志 handler 引用（setup_logging 赋值），供 WebUI 修改保留天数后即时生效
file_handler: TimedRotatingFileHandler | None = None
# 文件日志实际状态：成功时记录写入路径，失败时记录原因（供 WebUI 日志页诊断显示）
file_path: str | None = None
file_error: str | None = None


def set_file_target(path: str | None, error: str | None = None) -> None:
    global file_path, file_error
    file_path, file_error = path, error


def file_logging_status() -> dict:
    return {"path": file_path, "error": file_error}


def set_file_retention(days: int) -> None:
    if file_handler is not None:
        file_handler.backupCount = max(1, int(days))
