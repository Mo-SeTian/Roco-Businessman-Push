"""RoCom（wegame.shallow.ink）API 客户端。

接口文档: https://rocom.apifox.cn/466047235e0.md
  GET /api/v1/games/rocom/ingame/merchant/info
鉴权（三选一，本工具使用 X-API-Key）:
  X-API-Key / Authorization: Bearer <key> / X-Anonymous-Token
"""

from __future__ import annotations

import logging
import time

import requests

from .api_stats import APIStatsStore
from .channels.common import new_logged_session, redact_text

log = logging.getLogger("rocom")

SUCCESS_CODES = (0, 200)  # 业务包装 code 的成功值
PENDING_HTTP = 202  # 查询服务尚未就绪


class RocomAPIError(RuntimeError):
    """业务失败（code 不在成功范围）或认证失败。"""


class MerchantClient:
    def __init__(
        self,
        api_key: str,
        *,
        api_base: str = "https://wegame.shallow.ink",
        wait_ms: int = 8000,
        http_timeout: int = 30,
        max_retries: int = 11,
        retry_delay: int = 60,
        api_stats: APIStatsStore | None = None,
    ) -> None:
        self.api_stats = api_stats
        self.api_base = api_base.rstrip("/")
        self.wait_ms = wait_ms
        self.http_timeout = http_timeout
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0, retry_delay)
        self.session = new_logged_session()
        self.session.headers.update(
            {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "User-Agent": "rocom-merchant-pusher/1.0",
            }
        )

    def fetch_merchant(self, shop_id: str | None = None) -> dict:
        """拉取商人信息，所有请求/响应失败均重试；max_retries 包含首次请求。"""
        params: dict[str, str] = {}
        if shop_id:
            params["shop_id"] = shop_id
        if self.wait_ms > 0:
            params["wait_ms"] = str(self.wait_ms)
        path = "/api/v1/games/rocom/ingame/merchant/info"
        url = f"{self.api_base}{path}"

        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            ok = False
            try:
                resp = self.session.get(url, params=params, timeout=self.http_timeout)
                if resp.status_code == PENDING_HTTP:
                    raise RocomAPIError("数据未就绪(HTTP 202)")
                if resp.status_code >= 400:
                    raise RocomAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                try:
                    payload = resp.json()
                except ValueError as exc:
                    raise RocomAPIError(f"响应不是 JSON: {resp.text[:300]}") from exc
                if not isinstance(payload, dict):
                    raise RocomAPIError("响应 JSON 不是对象")
                code = payload.get("code")
                if code in SUCCESS_CODES:
                    ok = True
                    return payload
                if code == PENDING_HTTP:
                    raise RocomAPIError("数据未就绪(code=202)")
                raise RocomAPIError(
                    f"接口返回失败 code={code} message={payload.get('message')!r}"
                )
            except (requests.RequestException, RocomAPIError) as exc:
                last_err = redact_text(str(exc))
                api_key = self.session.headers.get("X-API-Key")
                if api_key:
                    last_err = last_err.replace(api_key, "<REDACTED>")
            finally:
                if self.api_stats is not None:
                    self.api_stats.record("GET", path, ok)
            if attempt < self.max_retries:
                log.warning("请求失败(第 %d/%d 次): %s；%ds 后重试",
                            attempt, self.max_retries, last_err, self.retry_delay)
                time.sleep(self.retry_delay)
        raise RocomAPIError(f"尝试 {self.max_retries} 次后仍失败: {last_err}")
