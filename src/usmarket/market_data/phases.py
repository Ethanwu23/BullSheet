"""交易阶段判定。

不依赖 provider 返回的 marketState —— 实测 Yahoo chart API 的 meta.marketState 为 None，
无法满足"明确区分盘前/盘中/盘后/休市"的要求（FR-013）。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from usmarket.market_data.calendar import (
    calendar_supports,
    is_full_closure,
    is_weekend,
    previous_trading_day,
    regular_close_hour,
)
from usmarket.market_data.models import MarketPhase

MARKET_TZ = "America/New_York"

PRE_OPEN_START = time(4, 0)
REGULAR_OPEN = time(9, 30)
POST_END = time(20, 0)


def market_tz() -> tzinfo:
    return ZoneInfo(MARKET_TZ)


def to_market_time(moment: datetime) -> datetime:
    """把任意 tz-aware 时间转换为美东时间。naive 时间按美东解释。"""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=market_tz())
    return moment.astimezone(market_tz())


def classify_phase(moment: datetime) -> MarketPhase:
    """判定交易阶段。

    规则（美东本地时间）：
    - 周末或全天休市 → CLOSED
    - 04:00–09:30 → PRE
    - 09:30–收盘（正常 16:00 / 提前收盘 13:00）→ REGULAR
    - 收盘–20:00 → POST
    - 其余 → CLOSED
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=market_tz())
    local = moment.astimezone(market_tz())
    d = local.date()

    if is_weekend(d) or is_full_closure(d):
        return MarketPhase.CLOSED

    t = local.time()
    close_hour = regular_close_hour(d)

    if t < PRE_OPEN_START:
        return MarketPhase.CLOSED
    if t < REGULAR_OPEN:
        return MarketPhase.PRE
    if t < time(close_hour, 0):
        return MarketPhase.REGULAR
    if t < POST_END:
        return MarketPhase.POST
    return MarketPhase.CLOSED


def phase_confidence(moment: datetime) -> str:
    """交易日历是否覆盖该日期（影响结论可信度）。"""
    local = to_market_time(moment)
    return "high" if calendar_supports(local.date()) else "low"


def last_session_close(moment: datetime) -> datetime:
    """最近一次常规交易时段的收盘时刻（美东）。

    - 若 moment 位于某交易日的收盘之后 → 当日收盘时刻；
    - 否则 → 上一个交易日的收盘时刻。
    """
    local = to_market_time(moment)
    day = local.date()
    if is_weekend(day) or is_full_closure(day):
        day = previous_trading_day(day)
        return datetime.combine(day, time(regular_close_hour(day)), tzinfo=market_tz())
    close = time(regular_close_hour(day))
    if local.timetz().replace(tzinfo=None) >= close:
        return datetime.combine(day, close, tzinfo=market_tz())
    prev = previous_trading_day(day)
    return datetime.combine(prev, time(regular_close_hour(prev)), tzinfo=market_tz())


def is_stale(as_of: datetime | None, now: datetime, stale_minutes: int) -> bool:
    """行情是否过期（**按交易时段判断，而非墙钟时间差**）。

    休市/盘前/盘后时，最新可得数据本就是"最近一次收盘"，
    若用墙钟时间差判断，隔夜数据会被误判为过期，导致整条链路不可用。

    - 盘中（REGULAR）：as_of 超过 stale_minutes 即过期；
    - 其余阶段：as_of 必须不早于"最近一次收盘 - stale_minutes"。
    - as_of 为 None 时视为过期（无法确认新鲜度），不做乐观假设。
    """
    if as_of is None:
        return True
    local_now = to_market_time(now)
    local_asof = to_market_time(as_of)

    if classify_phase(local_now) is MarketPhase.REGULAR:
        return (local_now - local_asof) > timedelta(minutes=stale_minutes)

    reference = last_session_close(local_now) - timedelta(minutes=stale_minutes)
    return local_asof < reference


def phase_label(phase: MarketPhase) -> str:
    return phase.label_zh
