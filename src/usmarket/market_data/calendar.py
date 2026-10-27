"""NYSE 交易日历。

仅覆盖常规全日/半日休市与提前收盘；特殊事件休市（如临时哀悼日）无法预测，
因此提供 calendar_confidence 标记，年份不足时降级为"仅周末判断"。
"""

from __future__ import annotations

from datetime import date, timedelta

from usmarket.errors import MarketDataError

# 支持的日历年份范围
CALENDAR_MIN_YEAR = 2025
CALENDAR_MAX_YEAR = 2027

# 全天休市（月, 日）
_FULL_CLOSURES: dict[int, set[tuple[int, int]]] = {
    2025: {
        (1, 1),   # New Year's Day
        (1, 20),  # MLK Day
        (2, 17),  # Washington's Birthday
        (4, 18),  # Good Friday
        (5, 26),  # Memorial Day
        (6, 19),  # Juneteenth
        (7, 4),   # Independence Day
        (9, 1),   # Labor Day
        (11, 27), # Thanksgiving
        (12, 25), # Christmas
    },
    2026: {
        (1, 1),
        (1, 19),  # MLK Day
        (2, 16),  # Washington's Birthday
        (4, 3),   # Good Friday
        (5, 25),  # Memorial Day
        (6, 19),  # Juneteenth
        (7, 3),   # Independence Day observed (7/4 = Saturday)
        (9, 7),   # Labor Day
        (11, 26), # Thanksgiving
        (12, 25), # Christmas
    },
    2027: {
        (1, 1),
        (1, 18),  # MLK Day
        (2, 15),  # Washington's Birthday
        (3, 26),  # Good Friday
        (5, 31),  # Memorial Day
        (6, 18),  # Juneteenth observed (6/19 = Saturday)
        (7, 5),   # Independence Day observed (7/4 = Sunday)
        (9, 6),   # Labor Day
        (11, 25), # Thanksgiving
        (12, 24), # Christmas observed (12/25 = Saturday)
    },
}

# 提前收盘（13:00 ET）
_EARLY_CLOSES: dict[int, set[tuple[int, int]]] = {
    2025: {(7, 3), (11, 28), (12, 24)},
    2026: {(11, 27), (12, 24)},
    2027: {(11, 26)},
}


def calendar_supports(d: date) -> bool:
    """日历表是否覆盖该年份。"""
    return CALENDAR_MIN_YEAR <= d.year <= CALENDAR_MAX_YEAR


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def is_full_closure(d: date) -> bool:
    return (d.month, d.day) in _FULL_CLOSURES.get(d.year, set())


def is_early_close(d: date) -> bool:
    return (d.month, d.day) in _EARLY_CLOSES.get(d.year, set())


def is_trading_day(d: date, *, strict: bool = True) -> bool:
    """是否为交易日。

    strict=True 且年份超出日历范围时抛错，避免给出不可靠结论。
    """
    if is_weekend(d) or is_full_closure(d):
        return False
    if strict and not calendar_supports(d):
        raise MarketDataError(
            f"交易日历未覆盖 {d.year} 年，无法可靠判断交易日。"
            f"请更新 market_data/calendar.py（当前支持 {CALENDAR_MIN_YEAR}-{CALENDAR_MAX_YEAR}）。"
        )
    return True


def regular_close_hour(d: date) -> int:
    """收盘小时（ET）：正常 16，提前收盘 13。"""
    return 13 if is_early_close(d) else 16


def previous_trading_day(d: date) -> date:
    """返回严格早于 d 的最近交易日。"""
    cursor = d - timedelta(days=1)
    for _ in range(15):
        if not is_weekend(cursor) and not is_full_closure(cursor):
            return cursor
        cursor -= timedelta(days=1)
    raise MarketDataError(f"无法从 {d} 回溯到交易日")


def next_trading_day(d: date) -> date:
    cursor = d + timedelta(days=1)
    for _ in range(15):
        if not is_weekend(cursor) and not is_full_closure(cursor):
            return cursor
        cursor += timedelta(days=1)
    raise MarketDataError(f"无法从 {d} 找到下一个交易日")


def latest_completed_session(d: date, *, now_et_date: date | None = None) -> date:
    """返回截至 d（含）最近一个**已完成**的交易日。

    用于"休市时自动调整为最近完整交易日复盘"（FR-017）。
    """
    ref = now_et_date or d
    if is_trading_day(ref, strict=False) and ref <= d:
        return ref
    return previous_trading_day(ref)
