"""新闻源抽象。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from usmarket.collectors.models import NewsItem, SourceResult


@runtime_checkable
class NewsSource(Protocol):
    name: str
    url: str

    def fetch(self, *, fetched_at: datetime | None = None) -> SourceResult:
        """抓取该来源；失败时返回带 error 的 SourceResult，不抛异常。"""
        ...


def _truncate(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def make_item(
    *,
    title: str,
    summary: str,
    url: str,
    source: str,
    fetched_at: datetime,
    published_at: datetime | None = None,
    trust_level: str = "established",
    summary_limit: int = 600,
) -> NewsItem:
    """构造 NewsItem（统一截断与清洗由 processors.sanitize 负责）。"""
    from usmarket.collectors.models import TrustLevel

    return NewsItem(
        title=(title or "").strip(),
        summary=_truncate(summary, summary_limit),
        url=(url or "").strip(),
        source=source,
        fetched_at=fetched_at,
        published_at=published_at,
        trust_level=TrustLevel(trust_level),
    )
