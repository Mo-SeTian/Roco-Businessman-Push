"""状态持久化与变更检测（按 shop_id 记录数据指纹）。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time

log = logging.getLogger("state")


def fingerprint(data_src: Any) -> str:
    """对 data 部分做稳定指纹（忽略键序）。"""
    canonical = json.dumps(data_src, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = json.load(f)
            if not isinstance(self._data, dict):
                self._data = {}
        except FileNotFoundError:
            self._data = {}
        except (OSError, ValueError) as exc:
            log.warning("状态文件读取失败，忽略旧状态: %s", exc)
            self._data = {}

    def save(self) -> None:
        directory = os.path.dirname(self.path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("状态文件写入失败（去重可能失效）: %s", exc)

    def get_fingerprint(self, shop_key: str) -> str | None:
        entry = self._data.get(shop_key)
        return entry.get("fingerprint") if isinstance(entry, dict) else None

    def set_pushed(self, shop_key: str, fp: str) -> None:
        self._data[shop_key] = {"fingerprint": fp, "pushed_at": int(time.time())}
        self.save()
