"""行情 provider 抽象。

新增 provider 只需实现 QuoteProvider 协议，无需改动上层（Constitution 原则 IV）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from usmarket.market_data.models import Quote, QuoteSnapshot


@runtime_checkable
class QuoteProvider(Protocol):
    name: str

    def fetch_quote(self, symbol: str, display_name: str) -> Quote:
        """获取单个标的行情；失败时返回 quality=MISSING 的 Quote，不抛异常。"""
        ...

    def fetch_snapshot(
        self,
        symbols: dict[str, str],
        *,
        as_of: datetime | None = None,
    ) -> QuoteSnapshot:
        """获取一组标的的快照。symbols: {symbol: display_name}。"""
        ...


def missing_quote(symbol: str, display_name: str, provider: str, note: str) -> Quote:
    """构造一个"缺失"行情对象。

    绝不返回 0 或历史值冒充当前值（FR-014）。
    """
    from usmarket.market_data.models import QuoteQuality

    return Quote(
        symbol=symbol,
        display_name=display_name,
        provider=provider,
        quality=QuoteQuality.MISSING,
        quality_note=note,
    )


_DISPLAY_NAMES: dict[str, str] = {
    "^GSPC": "标普500",
    "^IXIC": "纳斯达克综合",
    "^DJI": "道琼斯工业",
    "^RUT": "罗素2000",
    "^VIX": "VIX 恐慌指数",
    "NVDA": "英伟达",
    "AAPL": "苹果",
    "MSFT": "微软",
    "GOOGL": "谷歌",
    "AMZN": "亚马逊",
    "META": "Meta",
    "TSLA": "特斯拉",
    "AMD": "AMD",
    "AVGO": "博通",
    "TSM": "台积电",
    "NFLX": "奈飞",
    "JPM": "摩根大通",
}


def display_name_for(symbol: str) -> str:
    return _DISPLAY_NAMES.get(symbol.upper(), symbol.upper())
