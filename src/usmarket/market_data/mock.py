"""离线/测试用行情 provider。

数据来源是一个本地 JSON fixture，格式：
{
  "as_of": "2026-10-24T20:00:00Z",
  "quotes": {
    "^GSPC": {"price": 6791.5, "previous_close": 6750.1, "volume": 3200000000}
  }
}

未包含某标的时返回 quality=MISSING —— 与真实 provider 行为一致，
保证"缺失不会被虚构数据填补"在离线模式下同样可测（FR-014）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from usmarket.config import PROJECT_ROOT
from usmarket.market_data.base import display_name_for, missing_quote
from usmarket.market_data.models import (
    MarketPhase,
    Quote,
    QuoteQuality,
    QuoteSnapshot,
    compute_change,
    compute_change_percent,
)
from usmarket.market_data.phases import classify_phase

DEFAULT_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "quotes.json"


class MockQuoteProvider:
    """基于 fixture 的行情 provider（离线可测）。"""

    name = "mock"

    def __init__(self, fixture_path: Path | None = None, *, phase: MarketPhase | None = None):
        self.fixture_path = Path(fixture_path) if fixture_path else DEFAULT_FIXTURE
        self._data = self._load()
        self._phase_override = phase

    def _load(self) -> dict:
        if not self.fixture_path.exists():
            return {}
        with self.fixture_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def fetch_quote(self, symbol: str, display_name: str) -> Quote:
        entry = (self._data.get("quotes") or {}).get(symbol.upper())
        if not entry:
            return missing_quote(
                symbol, display_name, self.name, "fixture 中未包含该标的"
            )

        price = entry.get("price")
        previous_close = entry.get("previous_close")
        price = float(price) if isinstance(price, (int, float)) else None
        previous_close = (
            float(previous_close) if isinstance(previous_close, (int, float)) else None
        )
        if price is None:
            return missing_quote(symbol, display_name, self.name, "fixture 未提供 price")

        as_of_raw = entry.get("as_of") or self._data.get("as_of")
        as_of = datetime.fromisoformat(as_of_raw) if as_of_raw else None
        if as_of and as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=UTC)

        phase = self._phase_override or (classify_phase(as_of) if as_of else MarketPhase.UNKNOWN)
        volume = entry.get("volume")
        volume = int(volume) if isinstance(volume, (int, float)) else None

        return Quote(
            symbol=symbol,
            display_name=display_name or display_name_for(symbol),
            price=price,
            change=compute_change(price, previous_close),
            change_percent=compute_change_percent(price, previous_close),
            previous_close=previous_close,
            volume=volume,
            as_of=as_of,
            market_phase=phase,
            provider=self.name,
            is_delayed=True,
            quality=QuoteQuality.OK,
            raw={"source": str(self.fixture_path), "entry": entry},
        )

    def fetch_snapshot(
        self, symbols: dict[str, str], *, as_of: datetime | None = None
    ) -> QuoteSnapshot:
        quotes = [self.fetch_quote(sym, name) for sym, name in symbols.items()]
        errors = tuple(
            f"{q.symbol}: {q.quality.value}" for q in quotes if not q.is_usable()
        )
        now = as_of or datetime.now(tz=UTC)
        phases = [q.market_phase for q in quotes if q.as_of]
        return QuoteSnapshot(
            date=now.date().isoformat(),
            as_of=now,
            market_phase=phases[0] if phases else MarketPhase.UNKNOWN,
            indices=tuple(quotes),
            provider=self.name,
            errors=errors,
            is_delayed=True,
        )


__all__ = ["MockQuoteProvider"]
