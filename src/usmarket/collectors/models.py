"""新闻数据模型。

关键信息：published_at（源提供，可能为 None）与 fetched_at（系统生成）严格分离，
不得互相替代（Constitution 原则 II）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class TrustLevel(StrEnum):
    OFFICIAL = "official"        # 官方来源：美联储、SEC、公司 IR
    ESTABLISHED = "established"  # 主流媒体
    AGGREGATOR = "aggregator"    # 聚合器

    @property
    def rank(self) -> int:
        return {"official": 0, "established": 1, "aggregator": 2}[self.value]


class NewsCategory(StrEnum):
    MACRO = "macro"
    EARNINGS = "earnings"
    COMPANY = "company"
    MARKET_MOVE = "market_move"
    OTHER = "other"

    @property
    def label_zh(self) -> str:
        return {
            "macro": "宏观",
            "earnings": "财报",
            "company": "公司动态",
            "market_move": "市场异动",
            "other": "其他",
        }[self.value]


# 归一化 URL 时移除的追踪参数
_TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_STOPWORDS = frozenset({"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "is"})


def normalize_url(url: str) -> str:
    """URL 归一化：去 fragment、去追踪参数、去末尾斜杠、小写 host。"""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def title_fingerprint(title: str) -> str:
    """标题指纹：小写、去标点、去停用词后取 sha1。"""
    text = title.lower()
    text = _PUNCT_RE.sub(" ", text)
    tokens = [t for t in _WS_RE.sub(" ", text).split() if t and t not in _STOPWORDS]
    return hashlib.sha1(" ".join(tokens).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    url: str
    source: str
    fetched_at: datetime
    published_at: datetime | None = None
    tickers: tuple[str, ...] = ()
    category: NewsCategory = NewsCategory.OTHER
    trust_level: TrustLevel = TrustLevel.ESTABLISHED
    language: str = "en"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_url(self) -> str:
        return normalize_url(self.url)

    @property
    def fingerprint(self) -> str:
        return title_fingerprint(self.title)

    @property
    def published_display(self) -> str:
        """展示用发布时间；未提供时明确标注，不用抓取时间冒充。"""
        if self.published_at is None:
            return "发布时间未知"
        return self.published_at.strftime("%Y-%m-%d %H:%M %Z").strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat(),
            "tickers": list(self.tickers),
            "category": self.category.value,
            "trust_level": self.trust_level.value,
            "language": self.language,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> NewsItem:
        def parse_dt(value: str | None) -> datetime | None:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

        return NewsItem(
            title=d.get("title", ""),
            summary=d.get("summary", ""),
            url=d.get("url", ""),
            source=d.get("source", "unknown"),
            fetched_at=parse_dt(d.get("fetched_at")) or datetime.now(),
            published_at=parse_dt(d.get("published_at")),
            tickers=tuple(d.get("tickers", [])),
            category=NewsCategory(d.get("category", "other")),
            trust_level=TrustLevel(d.get("trust_level", "established")),
            language=d.get("language", "en"),
        )


@dataclass(frozen=True)
class SourceResult:
    """单个来源的采集结果（含失败信息）。"""

    source: str
    url: str
    items: tuple[NewsItem, ...] = ()
    error: str | None = None
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None
