"""行情数据模型。

约束：行情数字只能来自 provider 的真实响应；缺失为 None，质量标记说明原因。
禁止任何形式的插值、补全或 AI 生成（Constitution 原则 I）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MarketPhase(StrEnum):
    PRE = "pre"
    REGULAR = "regular"
    POST = "post"
    CLOSED = "closed"
    UNKNOWN = "unknown"

    @property
    def label_zh(self) -> str:
        return {
            "pre": "盘前",
            "regular": "盘中",
            "post": "盘后",
            "closed": "休市",
            "unknown": "未知",
        }[self.value]


class QuoteQuality(StrEnum):
    OK = "ok"
    STALE = "stale"        # 数据过期（超过新鲜度阈值）
    MISSING = "missing"    # provider 未返回该标的
    ANOMALOUS = "anomalous"  # 数值异常（非正价格、涨跌幅超阈值等）

    @property
    def label_zh(self) -> str:
        return {
            "ok": "正常",
            "stale": "数据过期",
            "missing": "数据缺失",
            "anomalous": "数据异常",
        }[self.value]


@dataclass(frozen=True)
class Quote:
    """单个标的的行情快照。"""

    symbol: str
    display_name: str
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    previous_close: float | None = None
    volume: int | None = None
    as_of: datetime | None = None
    market_phase: MarketPhase = MarketPhase.UNKNOWN
    provider: str = "unknown"
    is_delayed: bool = True
    quality: QuoteQuality = QuoteQuality.MISSING
    quality_note: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def is_usable(self) -> bool:
        return self.quality == QuoteQuality.OK and self.price is not None

    def change_percent_display(self) -> str:
        """展示用涨跌幅；不可用时返回"数据缺失"，绝不返回 0 或占位数字。"""
        if self.change_percent is None:
            return "数据缺失"
        return f"{self.change_percent:+.2f}%"

    def price_display(self) -> str:
        if self.price is None:
            return "数据缺失"
        return f"{self.price:,.2f}"


@dataclass(frozen=True)
class QuoteSnapshot:
    """一次行情采集的完整结果。"""

    date: str                      # 目标交易日 YYYY-MM-DD
    as_of: datetime | None         # 快照时间（tz-aware）
    market_phase: MarketPhase
    indices: tuple[Quote, ...] = ()
    stocks: tuple[Quote, ...] = ()
    provider: str = "unknown"
    calendar_confidence: str = "high"  # high | low
    errors: tuple[str, ...] = ()
    is_delayed: bool = True

    def all_quotes(self) -> tuple[Quote, ...]:
        return self.indices + self.stocks

    def by_symbol(self, symbol: str) -> Quote | None:
        for q in self.all_quotes():
            if q.symbol.upper() == symbol.upper():
                return q
        return None

    def usable_symbols(self) -> tuple[str, ...]:
        return tuple(q.symbol for q in self.all_quotes() if q.is_usable())

    def has_any_data(self) -> bool:
        return any(q.is_usable() for q in self.all_quotes())


def compute_change_percent(price: float | None, previous_close: float | None) -> float | None:
    """计算涨跌幅。

    任一输入为 None 时返回 None —— 不允许用 0 或其他占位值"补全"（FR-014）。
    """
    if price is None or previous_close is None:
        return None
    if previous_close == 0:
        return None
    return round((price - previous_close) / previous_close * 100.0, 4)


def compute_change(price: float | None, previous_close: float | None) -> float | None:
    if price is None or previous_close is None:
        return None
    return round(price - previous_close, 6)
