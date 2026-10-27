"""状态机：只允许合法迁移（FR-051 / FR-036）。"""

from __future__ import annotations

from usmarket.errors import StateTransitionError
from usmarket.storage.models import TaskStatus

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.GENERATED, TaskStatus.FAILED},
    TaskStatus.GENERATED: {TaskStatus.REVIEW, TaskStatus.FAILED, TaskStatus.PENDING},
    TaskStatus.REVIEW: {TaskStatus.APPROVED, TaskStatus.REJECTED, TaskStatus.FAILED},
    TaskStatus.APPROVED: {TaskStatus.SCHEDULED, TaskStatus.PUBLISHED, TaskStatus.FAILED},
    TaskStatus.SCHEDULED: {TaskStatus.PUBLISHED, TaskStatus.FAILED, TaskStatus.REVIEW},
    TaskStatus.PUBLISHED: set(),  # 终态：不得重复发布或回退
    TaskStatus.FAILED: {TaskStatus.PENDING, TaskStatus.GENERATED},
    TaskStatus.REJECTED: {TaskStatus.PENDING, TaskStatus.GENERATED},
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        raise StateTransitionError(
            f"非法状态迁移: {current.value} -> {target.value}",
            detail=f"允许的目标状态: {sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))}",
        )


def can_publish(status: TaskStatus) -> bool:
    """是否允许进入发布流程：必须已审核通过或已排期（FR-037）。"""
    return status in {TaskStatus.APPROVED, TaskStatus.SCHEDULED}
