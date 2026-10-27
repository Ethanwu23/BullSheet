"""Yahoo chart API provider（默认，无需 API key）。

实测（2026-10-27）：
  https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=5d&interval=1d
  → 200，返回 meta.symbol / regularMarketPrice / chartPreviousClose /
    exchangeTimezoneName=America/New_York / regularMarketTime
  → 支持原始指数代码 ^GSPC / ^IXIC / ^DJI（Finnhub 免费档不支持）

风险：该接口是 Yahoo 面向自家前端的非公开接口，无 SLA。
      失败时返回 quality=MISSING，绝不编造（见 docs/decisions.md ADR-002）。
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
from usmarket.market_data.phases import MARKET_TZ, classify_phase, is_stale

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# 涨跌幅绝对值超过该阈值判定为异常（需要人工复核，不静默展示）
ANOMALY_THRESHOLD_PERCENT = 40.0


def _as_utc_datetime(epoch: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(epoch), tz=UTC)
    except (TypeError, ValueError):
        return None


class YahooQuoteProvider:
    """Yahoo chart API 行情 provider。"""

    name = "yahoo"

    def __init__(
        self,
        *,
        timeout_seconds: int = 15,
        retries: int = 3,
        stale_minutes: int = 60,
        session: Any = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.stale_minutes = stale_minutes
        self._session = session

    def fetch_quote(self, symbol: str, display_name: str) -> Quote:
        url = BASE_URL.format(symbol=symbol) + "?range=5d&interval=1d"
        try:
            payload = fetch_json(
                url,
                session=self._session,
                timeout=self.timeout_seconds,
                retries=self.retries,
            )
        except HttpError as exc:
            LOGGER.warning("[%s] 行情获取失败: %s", symbol, exc.message)
            return missing_quote(symbol, display_name, self.name, f"请求失败: {exc.message}")

        try:
            result = payload["chart"]["result"][0]
            meta = result["meta"]
        except (KeyError, IndexError, TypeError) as exc:
            LOGGER.warning("[%s] 行情响应结构异常: %s", symbol, exc)
            return missing_quote(symbol, display_name, self.name, "响应结构异常")

        price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        price = float(price) if isinstance(price, (int, float)) else None
        previous_close = (
            float(previous_close) if isinstance(previous_close, (int, float)) else None
        )

        as_of = _as_utc_datetime(meta.get("regularMarketTime"))
        volume = meta.get("regularMarketVolume")
        volume = int(volume) if isinstance(volume, (int, float)) else None

        if price is None:
            return missing_quote(
                symbol, display_name, self.name, "provider 未返回当前价格"
            )

        quality = QuoteQuality.OK
        note = ""
        change_percent = compute_change_percent(price, previous_close)
        if previous_close is None:
            quality = QuoteQuality.STALE
            note = "缺少前收盘价，涨跌幅不可用"
        elif change_percent is not None and abs(change_percent) > ANOMALY_THRESHOLD_PERCENT:
            quality = QuoteQuality.ANOMALOUS
            note = f"涨跌幅 {change_percent:.2f}% 超出异常阈值 {ANOMALY_THRESHOLD_PERCENT}%"
        elif is_stale(as_of, datetime.now(tz=UTC), self.stale_minutes):
            quality = QuoteQuality.STALE
            note = f"行情时间超过 {self.stale_minutes} 分钟新鲜度阈值"

        phase = classify_phase(as_of) if as_of else MarketPhase.UNKNOWN

        return Quote(
            symbol=symbol,
            display_name=display_name,
            price=price,
            change=compute_change(price, previous_close),
            change_percent=change_percent,
            previous_close=previous_close,
            volume=volume,
            as_of=as_of,
            market_phase=phase,
            provider=self.name,
            # Yahoo 非公开接口无实时保证，一律标记延迟（不得伪装成实时，FR-015）
            is_delayed=True,
            quality=quality,
            quality_note=note,
            raw={
                "url": url,
                "meta": {
                    "symbol": meta.get("symbol"),
                    "currency": meta.get("currency"),
                    "exchangeTimezoneName": meta.get("exchangeTimezoneName", MARKET_TZ),
                    "regularMarketPrice": meta.get("regularMarketPrice"),
                    "chartPreviousClose": meta.get("chartPreviousClose"),
                    "previousClose": meta.get("previousClose"),
                    "regularMarketTime": meta.get("regularMarketTime"),
                    "regularMarketVolume": meta.get("regularMarketVolume"),
                },
            },
        )

    def fetch_snapshot(
        self, symbols: dict[str, str], *, as_of: datetime | None = None
    ) -> QuoteSnapshot:
        quotes: list[Quote] = []
        errors: list[str] = []
        for symbol, display_name in symbols.items():
            quote = self.fetch_quote(symbol, display_name)
            if not quote.is_usable():
                errors.append(f"{symbol}: {quote.quality.value} {quote.quality_note}".strip())
            quotes.append(quote)

        now = as_of or datetime.now(tz=UTC)
        phases = [q.market_phase for q in quotes if q.as_of]
        phase = phases[0] if phases else MarketPhase.UNKNOWN

        return QuoteSnapshot(
            date=(as_of or now).astimezone(UTC).date().isoformat(),
            as_of=now,
            market_phase=phase,
            indices=tuple(quotes),
            provider=self.name,
            errors=tuple(errors),
            is_delayed=True,
        )
