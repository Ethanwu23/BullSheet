"""统一的 HTTP 客户端：超时、有限重试与指数退避。

FR-055：外部 API 调用必须设置超时、错误处理与必要的限流。
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from usmarket.errors import USMarketError

DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_USER_AGENT = "USMarketDailyXHS/0.1 (+https://github.com/example/us-market-daily-xhs)"


class HttpError(USMarketError):
    """HTTP 请求失败。"""

    stage = "http"


def build_session(
    *,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = 1.0,
    user_agent: str = DEFAULT_USER_AGENT,
    pool_size: int = 10,
) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "*/*"})
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=pool_size, pool_connections=pool_size)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_text(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
    retries: int = DEFAULT_RETRIES,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    """GET 文本，失败抛 HttpError。"""
    own_session = session is None
    sess = session or build_session(retries=retries, user_agent=user_agent)
    try:
        resp = sess.get(url, timeout=timeout, headers=headers)
        if resp.status_code >= 400:
            raise HttpError(f"请求 {url} 失败: HTTP {resp.status_code}")
        resp.encoding = resp.encoding or "utf-8"
        return resp.text
    except requests.RequestException as exc:
        raise HttpError(f"请求 {url} 失败: {type(exc).__name__}") from exc
    finally:
        if own_session and sess is not None:
            sess.close()


def fetch_json(
    url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
    retries: int = DEFAULT_RETRIES,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Any:
    text = fetch_text(
        url,
        session=session,
        timeout=timeout,
        headers=headers,
        retries=retries,
        user_agent=user_agent,
    )
    import json

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpError(f"解析 {url} 返回的 JSON 失败: {exc}") from exc


def sleep_with_jitter(base_seconds: float, attempt: int) -> None:
    """指数退避 + 抖动，避免多个请求同时重试。"""
    delay = base_seconds * (2 ** max(0, attempt - 1))
    time.sleep(delay * (0.5 + random.random() * 0.5))  # noqa: S311 - 非安全用途
