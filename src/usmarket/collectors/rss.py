"""RSS / Atom 抓取。

feedparser 负责解析；发布时间解析失败时为 None（不得用抓取时间冒充，FR-004）。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import feedparser

from usmarket.collectors.base import make_item
from usmarket.collectors.models import NewsItem, SourceResult
from usmarket.config import FeedConfig
from usmarket.http_client import HttpError, fetch_text

LOGGER = logging.getLogger(__name__)


def _parse_datetime(entry: dict) -> datetime | None:
    """从 feed entry 提取发布时间；失败返回 None。"""
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=UTC)
            except (TypeError, ValueError):
                continue
    for key in ("published", "updated"):
        value = entry.get(key)
        if value:
            try:
                from email.utils import parsedate_to_datetime

                parsed = parsedate_to_datetime(value)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed.astimezone(UTC)
            except (TypeError, ValueError, IndexError):
                continue
    return None


class RssSource:
    """单个 RSS / Atom 源。"""

    def __init__(
        self,
        name: str,
        url: str,
        *,
        trust: str = "established",
        timeout_seconds: int = 15,
        max_items: int = 20,
        retries: int = 3,
    ) -> None:
        self.name = name
        self.url = url
        self.trust = trust
        self.timeout_seconds = timeout_seconds
        self.max_items = max_items
        self.retries = retries

    def fetch(self, *, fetched_at: datetime | None = None) -> SourceResult:
        now = fetched_at or datetime.now(tz=UTC)
        started = datetime.now(tz=UTC)
        try:
            raw = fetch_text(self.url, timeout=self.timeout_seconds, retries=self.retries)
        except HttpError as exc:
            LOGGER.warning("新闻源 %s 抓取失败: %s", self.name, exc.message,
                           extra={"stage": "collect", "source": self.name})
            return SourceResult(
                source=self.name,
                url=self.url,
                error=exc.message,
                elapsed_seconds=(datetime.now(tz=UTC) - started).total_seconds(),
            )

        parsed = feedparser.parse(raw)
        if parsed.get("bozo") and not parsed.get("entries"):
            return SourceResult(
                source=self.name,
                url=self.url,
                error=f"RSS 解析失败: {parsed.get('bozo_exception')}",
                elapsed_seconds=(datetime.now(tz=UTC) - started).total_seconds(),
            )

        items: list[NewsItem] = []
        for entry in list(parsed.get("entries", []))[: self.max_items]:
            link = entry.get("link") or entry.get("id") or ""
            if not link:
                continue
            summary = entry.get("summary") or entry.get("description") or ""
            items.append(
                make_item(
                    title=entry.get("title", ""),
                    summary=summary,
                    url=link,
                    source=self.name,
                    fetched_at=now,
                    published_at=_parse_datetime(entry),
                    trust_level=self.trust,
                )
            )

        LOGGER.info("新闻源 %s 抓取 %d 条", self.name, len(items),
                    extra={"stage": "collect", "source": self.name})
        return SourceResult(
            source=self.name,
            url=self.url,
            items=tuple(items),
            elapsed_seconds=(datetime.now(tz=UTC) - started).total_seconds(),
        )


def sources_from_config(feeds: Iterable[FeedConfig], *, timeout_seconds: int, max_items: int,
                        retries: int = 3) -> list[RssSource]:
    return [
        RssSource(
            f.name,
            f.url,
            trust=f.trust,
            timeout_seconds=timeout_seconds,
            max_items=max_items,
            retries=retries,
        )
        for f in feeds
        if f.enabled and f.url
    ]


def fetch_many(
    sources: list[RssSource], *, fetched_at: datetime | None = None, max_workers: int = 8
) -> list[SourceResult]:
    """并发抓取多个源；单源失败不影响其他源。"""
    if not sources:
        return []
    results: list[SourceResult] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(sources))) as pool:
        futures = {
            pool.submit(src.fetch, fetched_at=fetched_at): src.name for src in sources
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("新闻源 %s 异常: %s", name, exc,
                               extra={"stage": "collect", "source": name})
                results.append(SourceResult(source=name, url="", error=f"{type(exc).__name__}: {exc}"))
    return results
