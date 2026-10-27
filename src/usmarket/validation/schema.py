"""结构化内容模型（DailyContent）。

下游（图片渲染、发布）只依赖本模型，不解析自由文本（FR-020）。
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class Confidence(StrEnum):
    FACT = "fact"          # 有明确来源的事实
    ANALYSIS = "analysis"  # 基于事实的分析，需表述为分析
    SPECULATION = "speculation"  # 推测，必须表述为推测


class SourceRef(BaseModel):
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    published_at: datetime | None = None

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"来源链接必须是 http(s) URL: {v!r}")
        return v


class IndexMove(BaseModel):
    symbol: str
    name: str
    price: float | None = None
    change_percent: float | None = None
    source_ref: str = Field(default="", description="形如 quote:^GSPC，用于数字追溯")


class NewsEntry(BaseModel):
    headline: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    tickers: list[str] = Field(default_factory=list)
    source_title: str = Field(..., min_length=1)
    source_url: str = Field(..., min_length=1)
    published_at: datetime | None = None
    confidence: Confidence = Confidence.FACT

    @field_validator("source_url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"新闻来源链接必须是 http(s) URL: {v!r}")
        return v


class MoveEntry(BaseModel):
    symbol: str
    name: str
    change_percent: float | None = None
    note: str = ""
    confidence: Confidence = Confidence.ANALYSIS
    source_ref: str = ""


class EventEntry(BaseModel):
    title: str = Field(..., min_length=1)
    detail: str = ""
    tickers: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.FACT
    source_url: str = ""
    published_at: datetime | None = None


class XhsContent(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)


class DailyContent(BaseModel):
    date: str
    market_phase: Literal["pre", "regular", "post", "closed", "unknown"] = "closed"
    generator: str = "unknown"
    summary: str = Field(..., min_length=1)
    index_moves: list[IndexMove] = Field(default_factory=list)
    top_news: list[NewsEntry] = Field(default_factory=list)
    watchlist_moves: list[MoveEntry] = Field(default_factory=list)
    earnings_and_macro: list[EventEntry] = Field(default_factory=list)
    next_session: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    xhs: XhsContent
    sources: list[SourceRef] = Field(default_factory=list)
    disclaimer: str = ""
    low_confidence: bool = False
    data_notes: list[str] = Field(default_factory=list)

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent, exclude_none=False)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.to_json())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyContent:
        return cls.model_validate(data)

    def all_text_fields(self) -> list[str]:
        """所有对外展示的文本字段，用于数字/合规扫描。"""
        texts = [self.summary, self.xhs.title, self.xhs.body]
        texts += [n.headline for n in self.top_news] + [n.body for n in self.top_news]
        texts += [m.note for m in self.watchlist_moves]
        texts += [e.title for e in self.earnings_and_macro]
        texts += [e.detail for e in self.earnings_and_macro]
        texts += self.next_session + self.risk_notes
        return texts
