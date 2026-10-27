"""发布幂等与有限重试。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from usmarket.publishing.base import PublishOutcome

LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=PublishOutcome)


def has_succeeded(task, fingerprint: str) -> bool:
    """是否已用相同指纹成功发布过（幂等保护，FR-039）。"""
    for record in task.publish_records:
        if record.result == "success" and record.idempotency_key.endswith(fingerprint):
            return True
    return task.content_fingerprint == fingerprint and task.has_published()


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """有限次数重试 + 指数退避（FR-040）。

    始终返回最后一次的结果，不抛异常；失败信息由调用方记录。
    """
    last: T | None = None
    for attempt in range(1, max_retries + 1):
        result = fn()
        last = result
        if result.success:
            return result
        LOGGER.warning(
            "发布失败（第 %d/%d 次）: %s", attempt, max_retries, result.error,
            extra={"stage": "publish"},
        )
        if attempt < max_retries:
            delay = backoff_seconds * (2 ** (attempt - 1))
            sleep(delay)
    assert last is not None
    return last
