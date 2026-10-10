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
from .channels.common import new_logged_session

log = logging.getLogger("rocom")

SUCCESS_CODES = (0, 200)  # 业务包装 code 的成功值
PENDING_HTTP = 202  # 查询服务尚未就绪
RETRYABLE_HTTP = (500, 502, 503, 504)


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
        max_retries: int = 3,
        retry_delay: int = 20,
        api_stats: APIStatsStore | None = None,
    ) -> None:
        self.api_stats = api_stats
        self.api_base = api_base.rstrip("/")
        self.wait_ms = wait_ms
        self.http_timeout = http_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = new_logged_session()
        self.session.headers.update(
            {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "User-Agent": "rocom-merchant-pusher/1.0",
            }
        )

    def fetch_merchant(self, shop_id: str | None = None) -> dict:
        """拉取商人信息，对 202、暂时性服务错误和网络异常进行有限次数重试。"""
        params: dict[str, str] = {}
        if shop_id:
            params["shop_id"] = shop_id
        if self.wait_ms > 0:
            params["wait_ms"] = str(self.wait_ms)
        path = "/api/v1/games/rocom/ingame/merchant/info"
        url = f"{self.api_base}{path}"

        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            if self.api_stats is not None:
                self.api_stats.record("GET", path)
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.http_timeout
                )
            except requests.RequestException as exc:
                last_err = exc
            else:
                if resp.status_code == PENDING_HTTP:
                    last_err = RocomAPIError("数据未就绪(HTTP 202)")
                elif resp.status_code in RETRYABLE_HTTP:
                    last_err = RocomAPIError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                elif resp.status_code >= 400:
                    raise RocomAPIError(
                        f"HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                else:
                    try:
                        payload = resp.json()
                    except ValueError as exc:
                        raise RocomAPIError(f"响应不是 JSON: {resp.text[:300]}") from exc
                    code = payload.get("code")
                    if code in SUCCESS_CODES:
                        return payload
                    if code == PENDING_HTTP:  # 业务层 202：数据仍在查询中
                        last_err = RocomAPIError("数据未就绪(code=202)")
                    else:
                        raise RocomAPIError(
                            f"接口返回失败 code={code} message={payload.get('message')!r}"
                        )
            if attempt < self.max_retries:
                log.warning("请求失败(第 %d/%d 次): %s；%ds 后重试",
                            attempt, self.max_retries, last_err, self.retry_delay)
                time.sleep(self.retry_delay)
        raise RocomAPIError(f"尝试 {self.max_retries} 次后仍失败: {last_err}")
