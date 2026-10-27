"""时效过滤与排序。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from usmarket.collectors.models import NewsItem

LOGGER = logging.getLogger(__name__)


def filter_by_lookback(
    items: list[NewsItem], *, now: datetime, lookback_hours: int
) -> tuple[list[NewsItem], list[NewsItem]]:
    """按时效过滤。

    无发布时间的新闻**不**被丢弃，而是单独返回并标注 —— 因为无法判断其时效，
    丢弃会误伤；但也不参与"最新"排序的主列表（避免未知时间冒充最新）。
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    cutoff = now - timedelta(hours=lookback_hours)

    fresh: list[NewsItem] = []
    unknown_time: list[NewsItem] = []
    stale: list[NewsItem] = []

    for item in items:
        published = item.published_at
        if published is None:
            unknown_time.append(item)
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        if published >= cutoff:
            fresh.append(item)
        else:
            stale.append(item)

    LOGGER.info(
        "时效过滤 (%dh): 保留 %d，未知发布时间 %d，过期 %d",
        lookback_hours, len(fresh), len(unknown_time), len(stale),
    )
    return fresh, unknown_time


def rank(items: list[NewsItem]) -> list[NewsItem]:
    """排序：来源可信度 → 发布时间（新→旧）→ 标题。"""
    def key(item: NewsItem) -> tuple:
        published = item.published_at
        ts = (
            published.timestamp()
            if published
            else -1.0  # 未知时间排最后，不用抓取时间冒充
        )
        if published is not None and published.tzinfo is None:
            ts = published.replace(tzinfo=UTC).timestamp()
        return (item.trust_level.rank, -ts, item.title)

    return sorted(items, key=key)


def select_top(items: list[NewsItem], limit: int) -> list[NewsItem]:
    return rank(items)[:limit]
