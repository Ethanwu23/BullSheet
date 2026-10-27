"""Finnhub provider（可选，需要 API key）。

注意：Finnhub 免费档不支持原始指数代码（^GSPC / ^IXIC / ^DJI），
需改用对应 ETF（SPY / QQQ / DIA）。本 provider 检测到指数代码时返回
quality=MISSING 并给出说明，不做隐式替换（避免把 ETF 涨跌冒充指数涨跌）。

未在本机实测（无 API key），使用前请自行验证。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from usmarket.http_client import HttpError, fetch_json
from usmarket.market_data.base import missing_quote
from usmarket.market_data.models import (
    MarketPhase,
    Quote,
    QuoteQuality,
    QuoteSnapshot,
    compute_change,
    compute_change_percent,
)
from usmarket.market_data.phases import classify_phase, is_stale

LOGGER = logging.getLogger(__name__)

QUOTE_URL = "https://finnhub.io/api/v1/quote?symbol={symbol}&token={token}"

# Finnhub 免费档不支持的原始指数代码
UNSUPPORTED_INDEX_SYMBOLS = frozenset({"^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"})


class FinnhubQuoteProvider:
    name = "finnhub"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: int = 15,
        retries: int = 3,
        stale_minutes: int = 60,
        session: Any = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.stale_minutes = stale_minutes
        self._session = session

    def fetch_quote(self, symbol: str, display_name: str) -> Quote:
        if not self.api_key:
            return missing_quote(symbol, display_name, self.name, "未配置 FINNHUB_API_KEY")
        if symbol.upper() in UNSUPPORTED_INDEX_SYMBOLS:
            return missing_quote(
                symbol,
                display_name,
                self.name,
                "Finnhub 免费档不支持原始指数代码，请改用对应 ETF 或 MARKET_PROVIDER=yahoo",
            )

        url = QUOTE_URL.format(symbol=symbol, token=self.api_key)
        try:
            payload = fetch_json(
                url, session=self._session, timeout=self.timeout_seconds, retries=self.retries
            )
        except HttpError as exc:
            return missing_quote(symbol, display_name, self.name, f"请求失败: {exc.message}")

        # Finnhub /quote: {c: current, d: change, dp: change percent, h, l, o, pc, t}
        current = payload.get("c")
        previous_close = payload.get("pc")
        if not isinstance(current, (int, float)) or current == 0:
            return missing_quote(symbol, display_name, self.name, "provider 未返回有效价格")

        price = float(current)
        prev = float(previous_close) if isinstance(previous_close, (int, float)) else None
        as_of = None
        if isinstance(payload.get("t"), (int, float)):
            as_of = datetime.fromtimestamp(int(payload["t"]), tz=UTC)

        quality = QuoteQuality.OK
        note = ""
        if prev is None:
            quality = QuoteQuality.STALE
            note = "缺少前收盘价，涨跌幅不可用"
        elif is_stale(as_of, datetime.now(tz=UTC), self.stale_minutes):
            quality = QuoteQuality.STALE
            note = f"行情时间超过 {self.stale_minutes} 分钟新鲜度阈值"

        return Quote(
            symbol=symbol,
            display_name=display_name,
            price=price,
            change=compute_change(price, prev),
            change_percent=compute_change_percent(price, prev),
            previous_close=prev,
            volume=None,
            as_of=as_of,
            market_phase=classify_phase(as_of) if as_of else MarketPhase.UNKNOWN,
            provider=self.name,
            is_delayed=True,
            quality=quality,
            quality_note=note,
            raw={"url": QUOTE_URL.format(symbol=symbol, token="***REDACTED***"), "payload": payload},
        )

    def fetch_snapshot(
        self, symbols: dict[str, str], *, as_of: datetime | None = None
    ) -> QuoteSnapshot:
        quotes = [self.fetch_quote(sym, name) for sym, name in symbols.items()]
        errors = tuple(f"{q.symbol}: {q.quality.value} {q.quality_note}" for q in quotes if not q.is_usable())
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
