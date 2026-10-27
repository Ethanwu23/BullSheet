"""调度任务定义。

第一版只启用 after_close（盘后复盘）；pre_open 为预留枚举，调用即报错（ADR-010）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from usmarket.config import ScheduleConfig
from usmarket.scheduler.resolve import resolve_target_date


@dataclass(frozen=True)
class ScheduledRun:
    mode: str
    target_date: str
    cron_utc: str
    timezone: str
    reason: str


def plan_run(cfg: ScheduleConfig, *, trigger: datetime | None = None) -> ScheduledRun:
    """根据配置生成一次运行的计划。"""
    plan = resolve_target_date(trigger, mode=cfg.mode)
    return ScheduledRun(
        mode=plan.mode,
        target_date=plan.target_date,
        cron_utc=cfg.cron_utc,
        timezone=cfg.timezone,
        reason=plan.reason,
    )


def assert_mode_supported(mode: str) -> None:
    if mode not in {"after_close"}:
        raise NotImplementedError(
            f"运行模式 {mode!r} 未在第一版启用（当前支持: after_close）"
        )
