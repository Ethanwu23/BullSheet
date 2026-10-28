"""Yahoo chart API provider（默认，无需 API key）。

实测（2026-10-28）：
  https://query1.finance.yahoo.com/v8/finance/chart/^GSPC?range=5d&interval=1d
  → 200，返回 meta.* 与 indicators.quote[0].close 日线序列
  → 支持原始指数代码 ^GSPC / ^IXIC / ^DJI（Finnhub 免费档不支持）

**重要口径修正（2026-10-28，用户实测反馈触发）**：
  meta.regularMarketPrice / meta.chartPreviousClose 不能用于计算昨日涨跌幅：
  - chartPreviousClose 在 range=5d 下是「窗口前一日」收盘（≈5 日累计涨跌幅的基数），
    实测 TSLA 显示 +9.03%，而真实昨收涨幅为 +4.04%（META -10.67% vs 真实 -1.64%）。
  - regularMarketPrice 在盘前/盘中会混入当日最新价。
  因此一律使用日线收盘序列：取「最近已收盘交易日」bar 的 close 作为 price，
  其前一根 bar 的 close 作为 previous_close —— 这才是真正的收盘数据。

风险：该接口是 Yahoo 面向自家前端的非公开接口，无 SLA。
      失败时返回 quality=MISSING，绝不编造（见 docs/decisions.md ADR-002）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from typing import Any

from usmarket.http_client import HttpError, fetch_json
from usmarket.market_data.base import missing_quote
from usmarket.market_data.calendar import regular_close_hour
from usmarket.market_data.models import (
    MarketPhase,
    Quote,
    QuoteQuality,
    QuoteSnapshot,
    compute_change,
    compute_change_percent,
)
from usmarket.market_data.phases import (
    classify_phase,
    is_stale,
    last_session_close,
    market_tz,
)

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# 涨跌幅绝对值超过该阈值判定为异常（需要人工复核，不静默展示）
ANOMALY_THRESHOLD_PERCENT = 40.0


def _as_utc_datetime(epoch: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(epoch), tz=UTC)
    except (TypeError, ValueError):
        return None


def _daily_bars(result: dict[str, Any]) -> list[tuple[int, float, int | None]]:
    """解析日线序列：[(bar时间戳, 收盘价, 成交量), ...]，跳过缺收盘价的 bar。"""
    try:
        ts = result.get("timestamp") or []
        quote0 = result["indicators"]["quote"][0]
        closes = quote0.get("close") or []
        volumes = quote0.get("volume") or []
    except (KeyError, IndexError, TypeError):
        return []
    bars: list[tuple[int, float, int | None]] = []
    for i, t in enumerate(ts):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        volume = volumes[i] if i < len(volumes) else None
        bars.append(
            (
                int(t),
                float(close),
                int(volume) if isinstance(volume, (int, float)) else None,
            )
        )
    return bars


def _session_close_utc(bar_ts: int) -> datetime:
    """bar 时间戳为当日开盘（09:30 ET）；返回该交易日收盘时刻（UTC，含提前收盘）。"""
    local = datetime.fromtimestamp(bar_ts, tz=UTC).astimezone(market_tz())
    day = local.date()
    close_local = datetime.combine(day, time(regular_close_hour(day)), tzinfo=market_tz())
    return close_local.astimezone(UTC)


class YahooQuoteProvider:
    """Yahoo chart API 行情 provider（收盘数据口径）。"""

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

    def fetch_quote(
        self, symbol: str, display_name: str, *, now: datetime | None = None
    ) -> Quote:
        now = now or datetime.now(tz=UTC)
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

        # ---- 首选：日线收盘序列（真实收盘价与逐日涨跌幅）----
        bars = _daily_bars(result)
        target_idx: int | None = None
        for i in range(len(bars) - 1, -1, -1):
            if now >= _session_close_utc(bars[i][0]):
                target_idx = i
                break

        if target_idx is not None:
            bar_ts, price, volume = bars[target_idx]
            previous_close = bars[target_idx - 1][1] if target_idx > 0 else None
            as_of = _session_close_utc(bar_ts)
            raw_bars = [
                {"ts": t, "close": c, "completed": now >= _session_close_utc(t)}
                for t, c, _ in bars
            ]
            quality = QuoteQuality.OK
            note = ""
            change_percent = compute_change_percent(price, previous_close)
            if previous_close is None:
                quality = QuoteQuality.STALE
                note = "缺少前一根日线，涨跌幅不可用"
            elif change_percent is not None and abs(change_percent) > ANOMALY_THRESHOLD_PERCENT:
                quality = QuoteQuality.ANOMALOUS
                note = f"涨跌幅 {change_percent:.2f}% 超出异常阈值 {ANOMALY_THRESHOLD_PERCENT}%"
            elif as_of < last_session_close(now):
                quality = QuoteQuality.STALE
                note = "日线数据滞后于最近已收盘交易日"
            return Quote(
                symbol=symbol,
                display_name=display_name,
                price=price,
                change=compute_change(price, previous_close),
                change_percent=change_percent,
                previous_close=previous_close,
                volume=volume,
                as_of=as_of,
                market_phase=classify_phase(now),
                provider=self.name,
                # Yahoo 非公开接口无实时保证，一律标记延迟（不得伪装成实时，FR-015）
                is_delayed=True,
                quality=quality,
                quality_note=note,
                raw={
                    "url": url,
                    "price_source": "daily_close",
                    "target_bar_ts": bar_ts,
                    "bars": raw_bars,
                    "meta": {
                        "symbol": meta.get("symbol"),
                        "currency": meta.get("currency"),
                        "exchangeTimezoneName": meta.get("exchangeTimezoneName", "America/New_York"),
                        "regularMarketPrice": meta.get("regularMarketPrice"),
                        "chartPreviousClose": meta.get("chartPreviousClose"),
                        "regularMarketTime": meta.get("regularMarketTime"),
                    },
                },
            )

        # ---- 回退：日线不可用时使用 meta 现价（含已知口径问题，见模块 docstring）----
        LOGGER.warning("[%s] 日线序列不可用，回退 meta 现价口径", symbol)
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
        note = "meta 现价口径（日线不可用），涨跌幅可能为多日累计"
        change_percent = compute_change_percent(price, previous_close)
        if previous_close is None:
            quality = QuoteQuality.STALE
            note = "缺少前收盘价，涨跌幅不可用"
        elif change_percent is not None and abs(change_percent) > ANOMALY_THRESHOLD_PERCENT:
            quality = QuoteQuality.ANOMALOUS
            note = f"涨跌幅 {change_percent:.2f}% 超出异常阈值 {ANOMALY_THRESHOLD_PERCENT}%"
        elif is_stale(as_of, now, self.stale_minutes):
            quality = QuoteQuality.STALE
            note = f"行情时间超过 {self.stale_minutes} 分钟新鲜度阈值"

        return Quote(
            symbol=symbol,
            display_name=display_name,
            price=price,
            change=compute_change(price, previous_close),
            change_percent=change_percent,
            previous_close=previous_close,
            volume=volume,
            as_of=as_of,
            market_phase=classify_phase(now),
            provider=self.name,
            is_delayed=True,
            quality=quality,
            quality_note=note,
            raw={
                "url": url,
                "price_source": "meta_fallback",
                "meta": {
                    "symbol": meta.get("symbol"),
                    "currency": meta.get("currency"),
                    "exchangeTimezoneName": meta.get("exchangeTimezoneName", "America/New_York"),
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
        now = as_of or datetime.now(tz=UTC)
        quotes: list[Quote] = []
        errors: list[str] = []
        for symbol, display_name in symbols.items():
            quote = self.fetch_quote(symbol, display_name, now=now)
            if not quote.is_usable():
                errors.append(f"{symbol}: {quote.quality.value} {quote.quality_note}".strip())
            quotes.append(quote)

        phases = [q.market_phase for q in quotes if q.as_of]
        phase = phases[0] if phases else MarketPhase.UNKNOWN

        return QuoteSnapshot(
            date=now.astimezone(UTC).date().isoformat(),
            as_of=now,
            market_phase=phase,
            indices=tuple(quotes),
            provider=self.name,
            errors=tuple(errors),
            is_delayed=True,
        )
