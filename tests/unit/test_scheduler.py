"""调度测试：时区转换、DST、周末/节假日回退、指定日期、盘前未启用。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from usmarket.scheduler.resolve import parse_run_date, resolve_target_date

UTC = ZoneInfo("UTC")


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_after_close_on_trading_day_targets_same_day():
    # 2026-10-26 21:30 UTC = 17:30 EDT（已收盘）
    plan = resolve_target_date(_utc(2026, 10, 26, 21, 30))
    assert plan.target_date == "2026-10-26"
    assert plan.market_phase == "post"


def test_before_close_falls_back_to_previous_session():
    # 2026-10-27 13:00 UTC = 09:00 EDT（盘前，当日未收盘）
    plan = resolve_target_date(_utc(2026, 10, 27, 13, 0))
    assert plan.target_date == "2026-10-26"
    assert "尚未收盘" in plan.reason


def test_weekend_falls_back_to_friday():
    # 2026-10-25 是周日
    plan = resolve_target_date(_utc(2026, 10, 25, 12, 0))
    assert plan.target_date == "2026-10-23"


def test_holiday_falls_back_to_previous_trading_day():
    # 2026-12-25 圣诞（周五）
    plan = resolve_target_date(_utc(2026, 12, 25, 23, 0))
    assert plan.target_date == "2026-12-24"


def test_dst_switching_is_handled():
    """夏令时与冬令时下，22:30 UTC 对应的美东时间不同，但均视为盘后。"""
    summer = resolve_target_date(_utc(2026, 10, 26, 22, 30))   # EDT 18:30
    winter = resolve_target_date(_utc(2026, 12, 1, 22, 30))    # EST 17:30
    assert summer.market_time.hour == 18
    assert winter.market_time.hour == 17
    assert summer.target_date == "2026-10-26"
    assert winter.target_date == "2026-12-01"


def test_dst_transition_day_parsing():
    """2026-11-01 夏令时结束当天为周日，应回退到 10-30（周五）。"""
    plan = resolve_target_date(_utc(2026, 11, 1, 22, 30))
    assert plan.target_date == "2026-10-30"


def test_pre_open_not_implemented():
    with pytest.raises(NotImplementedError):
        resolve_target_date(_utc(2026, 10, 26, 22, 30), mode="pre_open")


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        resolve_target_date(_utc(2026, 10, 26, 22, 30), mode="midnight")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("2026-10-26", "2026-10-26"), (" 2026-01-02 ", "2026-01-02")],
)
def test_parse_run_date(value, expected):
    assert parse_run_date(value) == expected


def test_parse_run_date_invalid():
    with pytest.raises(ValueError):
        parse_run_date("26/10/2026")


def test_naive_trigger_treated_as_utc():
    plan = resolve_target_date(datetime(2026, 10, 26, 22, 30))
    assert plan.trigger_utc.tzinfo is not None
    assert plan.target_date == "2026-10-26"


def test_early_close_day_is_after_close_earlier():
    """提前收盘日 13:00 ET 之后即可视为已收盘。"""
    plan = resolve_target_date(_utc(2025, 11, 28, 18, 30))
    assert plan.target_date == "2025-11-28"
