"""行情服务：provider 选择、聚合、质量标记与落盘。

职责边界：只提供真实数据与其质量标记，不做任何插值或补全（FR-014）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from usmarket.config import AppConfig
from usmarket.market_data.base import QuoteProvider, display_name_for
from usmarket.market_data.mock import MockQuoteProvider
from usmarket.market_data.models import MarketPhase, Quote, QuoteSnapshot
from usmarket.market_data.phases import classify_phase, phase_confidence

LOGGER = logging.getLogger(__name__)


def build_provider(cfg: AppConfig) -> Any:
    """按配置构造行情 provider。"""
    provider_name = (cfg.market.provider or "yahoo").lower()
    if cfg.offline:
        LOGGER.info("离线模式：使用 mock 行情 provider")
        return MockQuoteProvider()

    if provider_name == "finnhub":
        from usmarket.market_data.finnhub import FinnhubQuoteProvider

        return FinnhubQuoteProvider(
            cfg.market.finnhub_api_key,
            timeout_seconds=cfg.market.timeout_seconds,
            retries=cfg.market.max_retries,
            stale_minutes=cfg.market.stale_minutes,
        )
    if provider_name == "alphavantage":
        # 未在本机实测；保留显式报错而非静默回退，避免误导
        raise NotImplementedError(
            "Alpha Vantage provider 尚未实现（本机无 key 无法验证）。"
            "请使用 MARKET_PROVIDER=yahoo，或按 QuoteProvider 协议自行实现。"
        )
    if provider_name == "mock":
        return MockQuoteProvider()

    from usmarket.market_data.yahoo import YahooQuoteProvider

    return YahooQuoteProvider(
        timeout_seconds=cfg.market.timeout_seconds,
        retries=cfg.market.max_retries,
        stale_minutes=cfg.market.stale_minutes,
    )


def target_symbols(cfg: AppConfig) -> dict[str, str]:
    """指数 + 个股的 {symbol: display_name}。"""
    symbols: dict[str, str] = {}
    for sym in cfg.watchlist.indices:
        symbols[sym] = display_name_for(sym)
    for sym in cfg.watchlist.tickers:
        symbols.setdefault(sym, display_name_for(sym))
    return symbols


def collect_snapshot(
    cfg: AppConfig,
    *,
    provider: QuoteProvider | None = None,
    as_of: datetime | None = None,
) -> QuoteSnapshot:
    """采集行情快照。

    返回 QuoteSnapshot；单个标的失败只影响该标的，不会中断整体。
    """
    prov = provider or build_provider(cfg)
    symbols = target_symbols(cfg)
    now = as_of or datetime.now(tz=UTC)

    snapshot = prov.fetch_snapshot(symbols, as_of=now)

    indices: list[Quote] = []
    stocks: list[Quote] = []
    index_set = {s.upper() for s in cfg.watchlist.indices}
    for quote in snapshot.all_quotes():
        (indices if quote.symbol.upper() in index_set else stocks).append(quote)

    phase = classify_phase(now)
    confidence = phase_confidence(now)

    result = QuoteSnapshot(
        date=snapshot.date,
        as_of=now,
        market_phase=phase,
        indices=tuple(indices),
        stocks=tuple(stocks),
        provider=getattr(prov, "name", "unknown"),
        calendar_confidence=confidence,
        errors=snapshot.errors,
        is_delayed=snapshot.is_delayed,
    )

    missing = [q.symbol for q in result.all_quotes() if not q.is_usable()]
    if missing:
        LOGGER.warning(
            "行情缺失标的（不做补全）: %s", ", ".join(missing),
            extra={"stage": "market_data"},
        )
    LOGGER.info(
        "行情采集完成 provider=%s phase=%s usable=%d/%d",
        result.provider, phase.value, len(result.usable_symbols()), len(result.all_quotes()),
        extra={"stage": "market_data"},
    )
    return result


def snapshot_to_dict(snapshot: QuoteSnapshot) -> dict[str, Any]:
    """序列化为可落盘的字典（保留原始片段以便追溯）。"""
    def q2d(q: Quote) -> dict[str, Any]:
        return {
            "symbol": q.symbol,
            "display_name": q.display_name,
            "price": q.price,
            "change": q.change,
            "change_percent": q.change_percent,
            "previous_close": q.previous_close,
            "volume": q.volume,
            "as_of": q.as_of.isoformat() if q.as_of else None,
            "market_phase": q.market_phase.value,
            "provider": q.provider,
            "is_delayed": q.is_delayed,
            "quality": q.quality.value,
            "quality_note": q.quality_note,
            "raw": q.raw,
        }

    return {
        "date": snapshot.date,
        "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
        "market_phase": snapshot.market_phase.value,
        "provider": snapshot.provider,
        "calendar_confidence": snapshot.calendar_confidence,
        "is_delayed": snapshot.is_delayed,
        "errors": list(snapshot.errors),
        "indices": [q2d(q) for q in snapshot.indices],
        "stocks": [q2d(q) for q in snapshot.stocks],
    }


def save_snapshot(snapshot: QuoteSnapshot, path: Path) -> Path:
    """保存原始行情到 JSON（与 AI 生成文本分开存储，Constitution 原则 III）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(snapshot_to_dict(snapshot), fh, ensure_ascii=False, indent=2)
    LOGGER.info("原始行情已保存: %s", path)
    return path


def load_snapshot(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def snapshot_from_dict(data: dict[str, Any]) -> QuoteSnapshot:
    def d2q(d: dict[str, Any]) -> Quote:
        as_of_raw = d.get("as_of")
        as_of = datetime.fromisoformat(as_of_raw) if as_of_raw else None
        return Quote(
            symbol=d["symbol"],
            display_name=d.get("display_name", d["symbol"]),
            price=d.get("price"),
            change=d.get("change"),
            change_percent=d.get("change_percent"),
            previous_close=d.get("previous_close"),
            volume=d.get("volume"),
            as_of=as_of,
            market_phase=MarketPhase(d.get("market_phase", "unknown")),
            provider=d.get("provider", "unknown"),
            is_delayed=bool(d.get("is_delayed", True)),
            quality=__import__(
                "usmarket.market_data.models", fromlist=["QuoteQuality"]
            ).QuoteQuality(d.get("quality", "missing")),
            quality_note=d.get("quality_note", ""),
            raw=d.get("raw", {}),
        )

    as_of_raw = data.get("as_of")
    as_of = datetime.fromisoformat(as_of_raw) if as_of_raw else None
    return QuoteSnapshot(
        date=data.get("date", ""),
        as_of=as_of,
        market_phase=MarketPhase(data.get("market_phase", "unknown")),
        indices=tuple(d2q(d) for d in data.get("indices", [])),
        stocks=tuple(d2q(d) for d in data.get("stocks", [])),
        provider=data.get("provider", "unknown"),
        calendar_confidence=data.get("calendar_confidence", "high"),
        errors=tuple(data.get("errors", [])),
        is_delayed=bool(data.get("is_delayed", True)),
    )
