"""任务模型与状态枚举（FR-051）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    PENDING = "pending"
    GENERATED = "generated"
    REVIEW = "review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"


class TaskStage(StrEnum):
    COLLECT = "collect"
    GENERATE = "generate"
    RENDER = "render"
    VALIDATION = "validation"
    PUBLISH = "publish"
    NONE = "none"


@dataclass
class HistoryEntry:
    at: str
    status: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"at": self.at, "status": self.status, "note": self.note}


@dataclass
class PublishRecord:
    publisher: str
    task_id: str
    result: str  # success | failed | skipped
    simulated: bool
    verified: bool
    at: str
    error: str = ""
    idempotency_key: str = ""
    remote_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "publisher": self.publisher,
            "task_id": self.task_id,
            "result": self.result,
            "simulated": self.simulated,
            "verified": self.verified,
            "at": self.at,
            "error": self.error,
            "idempotency_key": self.idempotency_key,
            "remote_id": self.remote_id,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> PublishRecord:
        return PublishRecord(
            publisher=d.get("publisher", "unknown"),
            task_id=d.get("task_id", ""),
            result=d.get("result", ""),
            simulated=bool(d.get("simulated", True)),
            verified=bool(d.get("verified", False)),
            at=d.get("at", ""),
            error=d.get("error", ""),
            idempotency_key=d.get("idempotency_key", ""),
            remote_id=d.get("remote_id", ""),
        )


def coerce_status(value: Any) -> TaskStatus:
    """把任意表示（枚举或字符串）转换为 TaskStatus，非法值回退 pending。"""
    if isinstance(value, TaskStatus):
        return value
    try:
        return TaskStatus(str(value))
    except ValueError:
        return TaskStatus.PENDING


def coerce_stage(value: Any) -> TaskStage:
    """把任意表示（枚举或字符串，含异常里的 stage）转换为 TaskStage。"""
    if isinstance(value, TaskStage):
        return value
    try:
        return TaskStage(str(value))
    except ValueError:
        return TaskStage.NONE


@dataclass
class PublishTask:
    date: str
    status: TaskStatus = TaskStatus.PENDING
    stage: TaskStage = TaskStage.NONE
    generator: str = ""
    template: str = ""
    content_fingerprint: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    history: list[HistoryEntry] = field(default_factory=list)
    publish_records: list[PublishRecord] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "stage": self.stage.value if isinstance(self.stage, TaskStage) else self.stage,
            "generator": self.generator,
            "template": self.template,
            "content_fingerprint": self.content_fingerprint,
            "error": self.error,
            "warnings": list(self.warnings),
            "artifacts": dict(self.artifacts),
            "history": [h.to_dict() for h in self.history],
            "publish_records": [r.to_dict() for r in self.publish_records],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> PublishTask:
        return PublishTask(
            date=d.get("date", ""),
            status=coerce_status(d.get("status", "pending")),
            stage=coerce_stage(d.get("stage", "none")),
            generator=d.get("generator", ""),
            template=d.get("template", ""),
            content_fingerprint=d.get("content_fingerprint", ""),
            error=d.get("error", ""),
            warnings=list(d.get("warnings", [])),
            artifacts=dict(d.get("artifacts", {})),
            history=[HistoryEntry(**h) for h in d.get("history", [])],
            publish_records=[PublishRecord.from_dict(r) for r in d.get("publish_records", [])],
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def add_history(self, status: TaskStatus, note: str = "") -> None:
        now = datetime.now().astimezone().isoformat()
        self.history.append(HistoryEntry(at=now, status=status.value, note=note))
        self.updated_at = now

    def has_published(self) -> bool:
        return any(r.result == "success" for r in self.publish_records)
