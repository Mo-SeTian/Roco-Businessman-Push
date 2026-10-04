"""公共小工具：按字节数截断文本。"""

from __future__ import annotations


def truncate_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    cut = raw[: max_bytes - 3].decode("utf-8", errors="ignore")
    return cut + "..."
