"""把 /ingame/merchant/info 的返回整理成推送消息。

已按实际返回 schema 实现（code=0 成功）：
  data.goods[]:  goods_id / buy_num / limit_buy_num / price.origin|real{amount, currency_type,
                 currency_id} / next_refresh_time(秒) / disable_time(秒) / sub_goods[]
  data.shop:     shop_id / goods_count / refresh_count / max_refresh_count / version ...
  data.meta:     queried_at / source / status / cached_age_seconds / task_id ...
  顶层 goods_mapping[]: goods_id / goods_name / item_id / item_num（商品名的唯一来源）
商品名不在 goods 里，必须按 goods_id 从 goods_mapping 反查；查不到时显示“商品{goods_id}”。

时间语义（经实测与玩家确认）：
  next_refresh_time 与 disable_time 按 (是否为0) 组合出四类商品：
    (0, 0)               常驻商品，无时间窗口
    (0, disable)         全天供应：当天 8:00 开市 ~ disable（通常为当天 24:00）
    (refresh, 0)         当前档商品：当前档起点 ~ refresh（refresh = 档位轮换/撤下时刻）
    (refresh, disable)   未来档商品：refresh = 上架时间，disable = 下架时间
  接口没有独立的“开始售卖”字段，当前档商品的开始时间由档位起点推算（16:25 查询 → 16:00）。
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

# 协议货币 -> 展示名（currency_id=1 = 洛克贝；未知货币显示 货币{id}）。
CURRENCY_LABELS: dict[int, str] = {1: "洛克贝"}

# meta.queried_at 的小数秒可能超过 6 位（如 .80169216Z），Python 3.10 的 fromisoformat 不认
_ISO_FRACTION = re.compile(r"(\.\d{6})\d+")

# 远行商人每天 8:00/12:00/16:00/20:00 四档刷新，商品上架时长固定 4 小时（一档）。
# next_refresh_time 与 disable_time 都是可购窗口的“结束”时刻（秒级），取较早者。
# 接口没有“开始售卖”字段，开始时间由当前档位起点推算。
SLOT_START_HOURS = (8, 12, 16, 20)

JSON_FALLBACK_LIMIT = 3000


def _fmt_local(dt: datetime) -> str:
    # 手工拼月日，避免平台相关的 strftime 参数（Windows 不认 %-d）
    return f"{dt.month}月{dt.day}日-{dt:%H:%M}"


def _ts(value: Any) -> str:
    """unix 秒 -> 本地时间字符串；0/None 返回空串。"""
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return ""
    if ts <= 0:
        return ""
    return _fmt_local(datetime.fromtimestamp(ts))


def _fmt_price(good: dict) -> str:
    price = good.get("price")
    if not isinstance(price, dict):
        return ""
    parts: list[str] = []
    for tag in ("real", "origin"):
        p = price.get(tag)
        if not isinstance(p, dict) or p.get("amount") in (None, ""):
            continue
        amount = p["amount"]
        cur = p.get("currency_id")
        label = CURRENCY_LABELS.get(cur) if isinstance(cur, int) else None
        text = f"{amount}{label}" if label else f"{amount}(货币{cur})"
        if tag == "real":
            parts.insert(0, text)
        else:
            parts.append(text)
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    return " / ".join(parts)


def _slot_start(queried: datetime) -> datetime:
    """查询时刻所在档位的起点（8/12/16/20 中不晚于查询时刻的最近整点）。"""
    day_open = queried.replace(hour=SLOT_START_HOURS[0], minute=0, second=0, microsecond=0)
    start = day_open
    for hour in SLOT_START_HOURS:
        candidate = queried.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate <= queried:
            start = candidate
    return start


def _norm_good(good: Any, mapping: dict[str, dict], slot_start_ts: int, day_open_ts: int) -> dict | None:
    if not isinstance(good, dict):
        return None
    gid = good.get("goods_id")
    info = mapping.get(str(gid), {})
    limit = good.get("limit_buy_num")
    try:
        refresh_ts = int(good.get("next_refresh_time") or 0)   # 档位轮换 或 未来档上架时间
        disable_ts = int(good.get("disable_time") or 0)        # 显式下架时间
    except (TypeError, ValueError):
        refresh_ts, disable_ts = 0, 0
    # 四象限：(refresh,disable) 组合决定商品类型与可购窗口，见模块 docstring
    if refresh_ts > 0 and disable_ts > 0:
        start_ts, end_ts = refresh_ts, disable_ts          # 未来档商品：上架 ~ 下架
    elif refresh_ts > 0:
        start_ts, end_ts = slot_start_ts, refresh_ts       # 当前档商品：档起点 ~ 轮换
    elif disable_ts > 0:
        start_ts, end_ts = day_open_ts, disable_ts         # 全天供应：开市 ~ 下架
    else:
        start_ts, end_ts = 0, 0                            # 常驻商品
    if end_ts and end_ts <= start_ts:  # 缓存已越过档位等异常情形，退回“现在 ~ 结束”
        start_ts = 0
    subs = [_norm_good(s, mapping, slot_start_ts, day_open_ts) for s in good.get("sub_goods") or []]
    return {
        "goods_id": gid,
        "name": info.get("goods_name") or f"商品{gid}",
        "price": _fmt_price(good),
        "limit": limit if isinstance(limit, int) else None,
        "item_num": info.get("item_num"),
        # 可购窗口：start 由档位推算；推算不出时由 _window 回退为“现在”
        "start": _ts(start_ts),
        "end": _ts(end_ts),
        "sub_goods": [s for s in subs if s],
    }


def _strip_volatile(value: Any) -> Any:
    """从指纹源剔除 buy_num 等展示无关、随时变动的字段，避免无意义的变更触发推送。"""
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k != "buy_num"}
    return value


def normalize(payload: dict) -> dict:
    data = payload.get("data") or {}
    mapping = {
        str(m.get("goods_id")): m
        for m in (payload.get("goods_mapping") or [])
        if isinstance(m, dict) and m.get("goods_id") is not None
    }
    shop = data.get("shop") if isinstance(data.get("shop"), dict) else {}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}

    queried_dt = None
    queried = meta.get("queried_at") or ""
    if queried:
        try:
            queried_dt = datetime.fromisoformat(
                _ISO_FRACTION.sub(r"\1", queried).replace("Z", "+00:00")
            ).astimezone()
            queried = _fmt_local(queried_dt)
        except ValueError:
            queried_dt = None

    # 档位推算基准：优先用服务端查询时间，缺失时用本机当前时间
    now_ref = queried_dt or datetime.now().astimezone()
    slot_start_ts = int(_slot_start(now_ref).timestamp())
    day_open_ts = int(
        now_ref.replace(hour=SLOT_START_HOURS[0], minute=0, second=0, microsecond=0).timestamp()
    )
    goods = [
        g for g in (_norm_good(g, mapping, slot_start_ts, day_open_ts) for g in data.get("goods") or [])
        if g
    ]

    return {
        "shop_id": shop.get("shop_id", ""),
        "refresh_count": shop.get("refresh_count"),
        "max_refresh_count": shop.get("max_refresh_count"),
        "queried": queried,
        "source": meta.get("source", ""),
        "goods": goods,
        "_raw": data,
        # 指纹只取 goods+shop：meta 里的 queried_at/task_id/cached_age_seconds 每次请求
        # 都会变，参与指纹会让"仅变化时推送"失效（每轮误推）；buy_num 同理剔除
        "_fp_src": {"goods": _strip_volatile(data.get("goods")), "shop": data.get("shop")},
    }


def build_title(norm: dict, prefix: str) -> str:
    shop = f"商店{norm['shop_id']}" if norm.get("shop_id") not in ("", None) else ""
    head = f"{prefix}｜{shop}" if shop else prefix
    rc, mr = norm.get("refresh_count"), norm.get("max_refresh_count")
    if isinstance(rc, int) and isinstance(mr, int) and mr > 0:
        head += f"（第{rc}/{mr}次）"
    return head


def _window(good: dict) -> str:
    """可购窗口：开始 ~ 结束；同一天时结束只显示时刻。"""
    start, end = good.get("start"), good.get("end")
    if not end:
        return ""
    if not start:
        return f"可购 现在 ~ {end}"
    date_part = end.split("-")[0]
    tail = end[len(date_part) + 1:] if start.startswith(date_part + "-") else end
    return f"可购 {start} ~ {tail}"


def _good_lines(norm: dict, indent: str = "") -> list[str]:
    lines: list[str] = []
    for g in norm.get("goods", []):
        bits = [f"**{g['name']}**"]
        if g.get("price"):
            bits.append(g["price"])
        if isinstance(g.get("limit"), int):
            bits.append(f"限购 {g['limit']}")
        window = _window(g)
        if window:
            bits.append(window)
        lines.append(f"{indent}- " + "｜".join(bits))
        for s in g.get("sub_goods", []):
            sub_bits = [f"**{s['name']}**"]
            if s.get("price"):
                sub_bits.append(s["price"])
            if s.get("item_num") not in (None, ""):
                sub_bits.append(f"x{s['item_num']}")
            sub_window = _window(s)
            if sub_window:
                sub_bits.append(sub_window)
            lines.append(f"{indent}  - " + "｜".join(sub_bits))
    return lines


def build_markdown(norm: dict) -> str:
    md: list[str] = []
    meta_bits = []
    if norm.get("queried"):
        meta_bits.append(f"查询时间 {norm['queried']}")
    if norm.get("source"):
        meta_bits.append(f"来源 {norm['source']}")
    if meta_bits:
        md.append("> " + "｜".join(meta_bits))
    rc, mr = norm.get("refresh_count"), norm.get("max_refresh_count")
    if isinstance(rc, int) and isinstance(mr, int) and mr > 0:
        md.append(f"商店已刷新：**{rc}/{mr}** 次")
    lines = _good_lines(norm)
    if lines:
        md.append("")
        md.extend(lines)
        md.append("")
        md.append(f"共 {len(norm['goods'])} 件商品")
    else:
        md.append("")
        md.append("本次未获取到商品明细（可能未到刷新时间）。")
        md.append("")
        md.append("```json")
        md.append(json.dumps(norm["_raw"], ensure_ascii=False)[:JSON_FALLBACK_LIMIT])
        md.append("```")
    return "\n".join(md)


def build_text(norm: dict) -> str:
    lines: list[str] = []
    if norm.get("queried"):
        lines.append(f"查询时间：{norm['queried']}")
    rc, mr = norm.get("refresh_count"), norm.get("max_refresh_count")
    if isinstance(rc, int) and isinstance(mr, int) and mr > 0:
        lines.append(f"商店已刷新：{rc}/{mr} 次")
    for g in norm.get("goods", []):
        bits = [g["name"]]
        if g.get("price"):
            bits.append(g["price"])
        if isinstance(g.get("limit"), int):
            bits.append(f"限购{g['limit']}")
        window = _window(g)
        if window:
            bits.append(window)
        lines.append("· " + "  ".join(bits))
        for s in g.get("sub_goods", []):
            lines.append(f"    - {s['name']}")
    if not lines:
        lines.append("本次未获取到商品明细（可能未到刷新时间）。")
        lines.append(json.dumps(norm["_raw"], ensure_ascii=False)[:JSON_FALLBACK_LIMIT])
    return "\n".join(lines)


def build_message(payload: dict, prefix: str) -> dict:
    """返回 {title, markdown, text, fingerprint_src}。"""
    norm = normalize(payload)
    return {
        "title": build_title(norm, prefix),
        "markdown": build_markdown(norm),
        "text": build_text(norm),
        "fingerprint_src": norm["_fp_src"],
    }
