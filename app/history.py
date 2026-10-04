"""调用历史：按 商店/日期/档位 保留每次成功拉取的商品信息。

- 只记录"成功拉取"的档位（失败/未调用的档位自然为空，供历史页展示为无数据）；
- 档位 = 查询时刻所在刷新档（8/12/16/20）；
- 存储于 /data/history.json，超出保留天数（默认 30 天）自动清理。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import format as fmt

log = logging.getLogger("history")


class HistoryStore:
    def __init__(self, path: str, days: int = 30):
        self.path = Path(path)
        self.days = max(1, days)
        self._lock = threading.Lock()
        self._data: dict[str, dict] = {}
        self._load()

    # ---- 读写 ----

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self._data = {}

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def _prune(self) -> None:
        cutoff = (date.today() - timedelta(days=self.days - 1)).isoformat()
        for shop in list(self._data):
            days = self._data.get(shop)
            if not isinstance(days, dict):
                del self._data[shop]
                continue
            for day in [d for d in days if str(d) < cutoff]:
                del days[day]
            if not days:
                del self._data[shop]

    # ---- 对外 ----

    def add(self, shop_key: str, payload: dict) -> None:
        """记录一次成功拉取。shop_key 为商店 ID 或 "default"。"""
        try:
            norm = fmt.normalize(payload)
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

            queried_dt = None
            raw_queried = str(meta.get("queried_at") or "")
            if raw_queried:
                try:
                    queried_dt = datetime.fromisoformat(
                        fmt._ISO_FRACTION.sub(r"\1", raw_queried).replace("Z", "+00:00")
                    ).astimezone()
                except ValueError:
                    queried_dt = None
            queried_dt = queried_dt or datetime.now().astimezone()

            entry = {
                "queried": queried_dt.strftime("%H:%M:%S"),
                "source": str(meta.get("source") or ""),
                "refresh": _refresh_text(norm),
                "count": len(norm.get("goods") or []),
                "goods": [
                    {
                        "name": g.get("name") or f"商品{g.get('goods_id')}",
                        "price": g.get("price") or "",
                        "limit": g.get("limit"),
                        "window": fmt._window(g),
                    }
                    for g in norm.get("goods") or []
                ],
            }
            day = queried_dt.date().isoformat()
            slot = fmt._slot_start(queried_dt).strftime("%H:%M")
            with self._lock:
                self._data.setdefault(shop_key, {}).setdefault(day, {})[slot] = entry
                self._prune()
                self._write()
        except Exception:  # noqa: BLE001 历史记录失败绝不影响推送主流程
            log.warning("历史记录写入失败（商店 %s）", shop_key, exc_info=True)

    def query(self, days: int) -> dict[str, Any]:
        """返回最近 days 天的数据：{shop: {day: {slot: entry}}}。"""
        cutoff = (date.today() - timedelta(days=max(1, days) - 1)).isoformat()
        with self._lock:
            out: dict[str, dict] = {}
            for shop, days_map in self._data.items():
                filtered = {d: v for d, v in days_map.items() if str(d) >= cutoff}
                if filtered:
                    out[shop] = filtered
            return out


def _refresh_text(norm: dict) -> str:
    rc, mr = norm.get("refresh_count"), norm.get("max_refresh_count")
    if isinstance(rc, int) and isinstance(mr, int) and mr > 0:
        return f"{rc}/{mr}"
    return ""
