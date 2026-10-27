"""行情模块测试：涨跌幅、缺失、交易阶段、交易日历、新鲜度。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from usmarket.market_data.calendar import (
    is_early_close,
    is_trading_day,
    previous_trading_day,
)
from usmarket.market_data.models import (
    MarketPhase,
    Quote,
    QuoteQuality,
    compute_change,
    compute_change_percent,
)
from usmarket.market_data.phases import classify_phase, is_stale, last_session_close
from usmarket.market_data.service import collect_snapshot

ET = ZoneInfo("America/New_York")


# ---------- 涨跌幅计算 ----------
@pytest.mark.parametrize(
    ("price", "prev", "expected"),
    [
        (110.0, 100.0, 10.0),
        (90.0, 100.0, -10.0),
        (100.0, 100.0, 0.0),
        (6791.5, 6750.1, 0.6133),
        (186.42, 182.1, 2.3723),
    ],
)
def test_compute_change_percent(price, prev, expected):
    assert compute_change_percent(price, prev) == pytest.approx(expected, abs=1e-4)


def test_compute_change_percent_missing_returns_none():
    """缺失行情不得被 0 或其他值填补（FR-014）。"""
    assert compute_change_percent(None, 100.0) is None
    assert compute_change_percent(100.0, None) is None
    assert compute_change_percent(None, None) is None
    assert compute_change_percent(100.0, 0.0) is None


def test_compute_change():
    assert compute_change(110.0, 100.0) == pytest.approx(10.0)
    assert compute_change(None, 100.0) is None


# ---------- 缺失行情不被虚构 ----------
def test_missing_quote_has_no_numbers():
    quote = Quote(
        symbol="ZZZZ",
        display_name="未知标的",
        quality=QuoteQuality.MISSING,
    )
    assert quote.price is None
    assert quote.change_percent is None
    assert quote.price_display() == "数据缺失"
    assert quote.change_percent_display() == "数据缺失"
    assert quote.is_usable() is False


def test_mock_provider_missing_symbol_returns_missing(mock_provider):
    quote = mock_provider.fetch_quote("NOPE", "不存在")
    assert quote.quality == QuoteQuality.MISSING
    assert quote.price is None
    assert "fixture" in quote.quality_note


def test_snapshot_marks_unusable_symbols(offline_cfg, mock_provider):
    cfg = offline_cfg
    from dataclasses import replace

    cfg = replace(
        cfg,
        watchlist=replace(cfg.watchlist, tickers=("NVDA", "NOT_IN_FIXTURE")),
    )
    snap = collect_snapshot(cfg, provider=mock_provider)
    missing = snap.by_symbol("NOT_IN_FIXTURE")
    assert missing is not None
    assert missing.quality == QuoteQuality.MISSING
    assert missing.price is None
    # 缺失标的不会进入 usable 列表，也不会被补成 0
    assert "NOT_IN_FIXTURE" not in snap.usable_symbols()
    assert snap.has_any_data() is True


# ---------- 交易阶段 ----------
@pytest.mark.parametrize(
    ("moment_et", "expected"),
    [
        (datetime(2026, 10, 26, 3, 0, tzinfo=ET), MarketPhase.CLOSED),
        (datetime(2026, 10, 26, 5, 0, tzinfo=ET), MarketPhase.PRE),
        (datetime(2026, 10, 26, 9, 29, tzinfo=ET), MarketPhase.PRE),
        (datetime(2026, 10, 26, 9, 30, tzinfo=ET), MarketPhase.REGULAR),
        (datetime(2026, 10, 26, 15, 59, tzinfo=ET), MarketPhase.REGULAR),
        (datetime(2026, 10, 26, 16, 0, tzinfo=ET), MarketPhase.POST),
        (datetime(2026, 10, 26, 19, 59, tzinfo=ET), MarketPhase.POST),
        (datetime(2026, 10, 26, 20, 0, tzinfo=ET), MarketPhase.CLOSED),
        (datetime(2026, 10, 24, 12, 0, tzinfo=ET), MarketPhase.CLOSED),  # 周六
    ],
)
def test_classify_phase(moment_et, expected):
    assert classify_phase(moment_et) is expected


def test_classify_phase_early_close():
    """提前收盘日（2025-11-28 感恩节次日）13:00 后进入 POST。"""
    assert is_early_close(datetime(2025, 11, 28).date())
    assert classify_phase(datetime(2025, 11, 28, 12, 59, tzinfo=ET)) is MarketPhase.REGULAR
    assert classify_phase(datetime(2025, 11, 28, 13, 5, tzinfo=ET)) is MarketPhase.POST


def test_classify_phase_in_dst_transition():
    """夏令时切换日：由 zoneinfo 处理，不手工维护偏移。"""
    # 2026-11-01 为夏令时结束日（美国），当天仍是交易日之外（周日）
    assert classify_phase(datetime(2026, 11, 1, 12, 0, tzinfo=ET)) is MarketPhase.CLOSED
    # 2026-03-08 夏令时开始（周日）
    assert classify_phase(datetime(2026, 3, 8, 12, 0, tzinfo=ET)) is MarketPhase.CLOSED
    # 切换后的周一交易日时间判定正常
    assert classify_phase(datetime(2026, 11, 2, 10, 0, tzinfo=ET)) is MarketPhase.REGULAR


# ---------- 交易日历 ----------
@pytest.mark.parametrize(
    ("date_str", "expected"),
    [
        ("2026-10-26", True),   # 周一
        ("2026-10-24", False),  # 周六
        ("2026-12-25", False),  # 圣诞
        ("2026-07-03", False),  # 独立日补假
        ("2026-04-03", False),  # Good Friday
        ("2027-03-26", False),  # Good Friday
    ],
)
def test_is_trading_day(date_str, expected):
    d = datetime.fromisoformat(date_str).date()
    assert is_trading_day(d) is expected


def test_previous_trading_day_skips_weekend_and_holiday():
    # 2026-12-26 周六 → 回溯到 12-24（12-25 休市）
    assert previous_trading_day(datetime(2026, 12, 26).date()).isoformat() == "2026-12-24"


def test_calendar_out_of_range_raises():
    from usmarket.errors import MarketDataError

    with pytest.raises(MarketDataError):
        is_trading_day(datetime(2035, 1, 2).date())


# ---------- 新鲜度 ----------
def test_is_stale_during_regular_session():
    """盘中：按墙钟时间差判断。"""
    now = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)  # 14:00 EDT 盘中
    assert is_stale(now - timedelta(minutes=10), now, 60) is False
    assert is_stale(now - timedelta(minutes=120), now, 60) is True
    # as_of 未知 → 视为过期（不做乐观假设）
    assert is_stale(None, now, 60) is True


def test_pre_market_overnight_close_is_not_stale():
    """盘前：上一交易日收盘价就是最新可得数据，不得判为过期。"""
    # 2026-10-26 12:05 UTC = 08:05 EDT（周一盘前）；上一交易日为上周五
    now = datetime(2026, 10, 26, 12, 5, tzinfo=UTC)
    friday_close = datetime(2026, 10, 23, 20, 0, tzinfo=UTC)  # 周五 16:00 EDT
    assert is_stale(friday_close, now, 60) is False
    # 更早（周四收盘）的数据应判为过期
    thursday_close = datetime(2026, 10, 22, 20, 0, tzinfo=UTC)
    assert is_stale(thursday_close, now, 60) is True


def test_weekend_close_is_not_stale():
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)  # 周日
    friday_close = datetime(2026, 10, 23, 20, 0, tzinfo=UTC)
    assert is_stale(friday_close, now, 60) is False


def test_last_session_close():
    # 盘后 → 当日收盘
    assert last_session_close(datetime(2026, 10, 26, 21, 0, tzinfo=UTC)) == \
        datetime(2026, 10, 26, 16, 0, tzinfo=ET)
    # 周末 → 上周五收盘
    assert last_session_close(datetime(2026, 10, 25, 12, 0, tzinfo=UTC)) == \
        datetime(2026, 10, 23, 16, 0, tzinfo=ET)
    # 2025-11-28 为提前收盘日，但其 10:00 UTC（05:00 EST）尚未收盘；
    # 上一交易日为 11-26（11-27 感恩节休市）
    assert last_session_close(datetime(2025, 11, 28, 10, 0, tzinfo=UTC)) == \
        datetime(2025, 11, 26, 16, 0, tzinfo=ET)
    # 同一天收盘后 → 当日提前收盘时刻 13:00
    assert last_session_close(datetime(2025, 11, 28, 19, 0, tzinfo=UTC)) == \
        datetime(2025, 11, 28, 13, 0, tzinfo=ET)


# ---------- 快照序列化往返 ----------
def test_snapshot_roundtrip(snapshot):
    from usmarket.market_data.service import snapshot_from_dict, snapshot_to_dict

    data = snapshot_to_dict(snapshot)
    restored = snapshot_from_dict(data)
    assert restored.date == snapshot.date
    assert len(restored.all_quotes()) == len(snapshot.all_quotes())
    for original, copy in zip(snapshot.all_quotes(), restored.all_quotes(), strict=False):
        assert original.symbol == copy.symbol
        assert original.price == copy.price
        assert original.quality == copy.quality


def test_snapshot_has_no_fabricated_numbers(offline_cfg, mock_provider):
    """所有可用的数字都必须来自 fixture。"""
    snap = collect_snapshot(offline_cfg, provider=mock_provider)
    for quote in snap.all_quotes():
        if quote.is_usable():
            assert quote.price is not None
            assert quote.provider == "mock"
            assert "entry" in quote.raw
