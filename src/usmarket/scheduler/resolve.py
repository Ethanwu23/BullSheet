"""调度解析：触发时间 → 目标交易日。

重要：GitHub Actions cron 不保证精确到分钟，因此**不能**把触发时间当作
"当天"，而应根据美东时间判断"最近一个已收盘的交易日"（FR-049 / FR-017）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from usmarket.market_data.calendar import (
    is_early_close,
    is_full_closure,
    is_weekend,
    previous_trading_day,
)
from usmarket.market_data.phases import MARKET_TZ, classify_phase

UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class RunPlan:
    mode: str
    trigger_utc: datetime
    market_time: datetime
    target_date: str          # YYYY-MM-DD
    reason: str
    market_phase: str


def to_market_time(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(MARKET_TZ))


def resolve_target_date(
    trigger: datetime | None = None, *, mode: str = "after_close"
) -> RunPlan:
    """解析本次运行应处理的目标交易日。"""
    trigger_utc = trigger or datetime.now(tz=UTC)
    if trigger_utc.tzinfo is None:
        trigger_utc = trigger_utc.replace(tzinfo=UTC)
    market_time = to_market_time(trigger_utc)
    day = market_time.date()

    if mode == "pre_open":
        raise NotImplementedError(
            "盘前模式（pre_open）第一版不启用，见 docs/decisions.md ADR-010。"
            "如需使用请先实现并通过测试。"
        )
    if mode != "after_close":
        raise ValueError(f"未知运行模式: {mode}")

    close = time(13, 0) if is_early_close(day) else time(16, 0)
    phase = classify_phase(market_time)

    if is_weekend(day) or is_full_closure(day):
        target = previous_trading_day(day)
        reason = f"{day} 非交易日（周末或休市），回退到最近交易日 {target}"
    elif market_time.timetz().replace(tzinfo=None) >= close:
        target = day
        reason = f"{day} 已收盘（收盘 {close}），以当日为复盘目标"
    else:
        target = previous_trading_day(day)
        reason = f"{day} 尚未收盘（收盘 {close}），回退到最近完整交易日 {target}"

    return RunPlan(
        mode=mode,
        trigger_utc=trigger_utc,
        market_time=market_time,
        target_date=target.isoformat(),
        reason=reason,
        market_phase=phase.value,
    )


def parse_run_date(value: str | None) -> str | None:
    """解析 --date 参数（YYYY-MM-DD）。"""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise ValueError(f"日期格式无效（应为 YYYY-MM-DD）: {value!r}") from exc


def shift_days(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return (d + timedelta(days=days)).isoformat()
