"""新闻去重：URL 归一化 + 标题指纹。

同一事件被多家媒体转载时只保留一条，保留发布时间最早（最原始）的那条，
其余来源记录在 also_reported_by 中，既不重复计数也不丢失出处（FR-007）。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from usmarket.collectors.models import NewsItem


def _published_key(item: NewsItem) -> datetime:
    """排序键：无发布时间的排在最后（不猜时间）。"""
    if item.published_at is None:
        return datetime.min.replace(tzinfo=UTC)
    if item.published_at.tzinfo is None:
        return item.published_at.replace(tzinfo=UTC)
    return item.published_at


def deduplicate(items: list[NewsItem]) -> tuple[list[NewsItem], dict[str, list[str]]]:
    """去重。

    返回 (去重后的列表, {保留项 fingerprint: [被合并的来源]})
    """
    by_url: dict[str, NewsItem] = {}
    by_title: dict[str, NewsItem] = {}
    merged_sources: dict[str, set[str]] = {}

    # 先按发布时间升序，保证同一事件保留最早发布的那条
    ordered = sorted(items, key=_published_key)

    kept: list[NewsItem] = []
    for item in ordered:
        url_key = item.normalized_url
        title_key = item.fingerprint

        existing = by_url.get(url_key) or by_title.get(title_key)
        if existing is not None:
            merged_sources.setdefault(existing.fingerprint, set()).add(item.source)
            continue

        kept.append(item)
        if url_key:
            by_url[url_key] = item
        if title_key:
            by_title[title_key] = item
        merged_sources.setdefault(title_key, set()).add(item.source)

    result = {
        item.fingerprint: sorted(merged_sources.get(item.fingerprint, set()))
        for item in kept
    }
    return kept, result


def attach_merge_info(
    items: list[NewsItem], merged: dict[str, list[str]]
) -> list[NewsItem]:
    """把转载来源写入 raw 字段，供来源清单展示。"""
    out: list[NewsItem] = []
    for item in items:
        sources = [s for s in merged.get(item.fingerprint, []) if s != item.source]
        if sources:
            raw = dict(item.raw)
            raw["also_reported_by"] = sources
            item = replace(item, raw=raw)
        out.append(item)
    return out
