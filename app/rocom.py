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
        max_retries: int = 3,
        retry_delay: int = 20,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.wait_ms = wait_ms
        self.http_timeout = http_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-API-Key": api_key,
                "Accept": "application/json",
                "User-Agent": "rocom-merchant-pusher/1.0",
            }
        )

    def fetch_merchant(self, shop_id: str | None = None) -> dict:
        """拉取远行商人信息，带 202/网络错误重试。返回响应 JSON（含 code/message/data/goods_mapping）。"""
        params: dict[str, str] = {}
        if shop_id:
            params["shop_id"] = shop_id
        if self.wait_ms > 0:
            params["wait_ms"] = str(self.wait_ms)
        url = f"{self.api_base}/api/v1/games/rocom/ingame/merchant/info"

        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.http_timeout
                )
            except requests.RequestException as exc:
                last_err = exc
                log.warning("请求失败(第 %d 次): %s", attempt, exc)
            else:
                if resp.status_code == PENDING_HTTP:
                    log.warning(
                        "数据未就绪(HTTP 202, 第 %d 次)，%ds 后重试", attempt, self.retry_delay
                    )
                    time.sleep(self.retry_delay)
                    continue
                if resp.status_code >= 400:
                    raise RocomAPIError(
                        f"HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                try:
                    payload = resp.json()
                except ValueError as exc:
                    raise RocomAPIError(f"响应不是 JSON: {resp.text[:300]}") from exc
                code = payload.get("code")
                if code in SUCCESS_CODES:
                    return payload
                if code == PENDING_HTTP:  # 业务层 202：数据仍在查询中
                    log.warning("数据未就绪(code=202, 第 %d 次)", attempt)
                    time.sleep(self.retry_delay)
                    continue
                raise RocomAPIError(
                    f"接口返回失败 code={code} message={payload.get('message')!r}"
                )
            if attempt < self.max_retries:
                time.sleep(self.retry_delay)
        raise RocomAPIError(f"重试 {self.max_retries} 次后仍失败: {last_err}")
