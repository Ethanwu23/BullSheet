"""发布流程编排：校验 → 幂等检查 → 发布 → 记录。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from usmarket.config import AppConfig
from usmarket.errors import PublishError
from usmarket.publishing.base import Publisher, PublishOutcome, PublishPayload
from usmarket.publishing.retry import has_succeeded, retry_with_backoff
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import PublishRecord, PublishTask, TaskStage, TaskStatus
from usmarket.storage.state_machine import can_publish

LOGGER = logging.getLogger(__name__)


def build_publisher(cfg: AppConfig, *, export_dir: Path | None = None) -> Any:
    """按配置构造发布适配器。"""
    name = (cfg.publish.publisher or "mock").lower()
    if name == "manual_export":
        from usmarket.publishing.manual_export import ManualExportPublisher

        return ManualExportPublisher(export_dir or Path(cfg.data_dir) / "export")
    if name == "browser":
        from usmarket.publishing.browser import BrowserPublisher

        return BrowserPublisher(enabled=cfg.publish.enable_browser)
    from usmarket.publishing.mock import MockPublisher

    return MockPublisher(fail_first=cfg.publish.mock_fail_first)


def build_payload(
    date: str,
    *,
    title: str,
    body: str,
    tags: list[str],
    images: list[Path],
    fingerprint: str,
) -> PublishPayload:
    return PublishPayload(
        date=date,
        title=title,
        body=body,
        tags=tuple(tags),
        images=tuple(images),
        content_fingerprint=fingerprint,
    )


def publish_task(
    cfg: AppConfig,
    store: FileTaskStore,
    task: PublishTask,
    payload: PublishPayload,
    *,
    publisher: Publisher | None = None,
    sleep: Any = None,
) -> PublishOutcome:
    """执行发布。

    前置条件：
    - 任务状态必须是 approved / scheduled（FR-037）；
    - 通过内容指纹做幂等保护（FR-039）。
    """
    if not can_publish(task.status):
        raise PublishError(
            f"任务 {task.date} 当前状态为 {task.status.value}，未通过审核，禁止发布",
            detail="需先执行 `usmarket approve --date <date>`",
        )

    # 幂等：已用相同指纹成功发布过则跳过
    if has_succeeded(task, payload.content_fingerprint):
        LOGGER.info(
            "任务 %s 已用相同指纹发布成功，跳过重复发布", task.date,
            extra={"stage": "publish"},
        )
        existing = next(
            (r for r in task.publish_records if r.result == "success"), None
        )
        return PublishOutcome(
            success=True,
            task_id=existing.task_id if existing else "",
            simulated=True if existing and existing.simulated else False,
            verified=bool(existing and existing.verified),
            remote_id=existing.remote_id if existing else "",
            detail={"skipped": True, "reason": "idempotent"},
        )

    pub = publisher or build_publisher(
        cfg, export_dir=Path(cfg.data_dir) / task.date / "publish"
    )

    errors = pub.validate_content(payload)
    if errors:
        outcome = PublishOutcome(
            success=False,
            task_id="",
            simulated=getattr(pub, "simulated", True),
            verified=getattr(pub, "verified", False),
            error="; ".join(errors),
        )
        _record(cfg, store, task, payload, outcome)
        return outcome

    outcome = retry_with_backoff(
        lambda: pub.publish(payload),
        max_retries=cfg.publish.max_retries,
        backoff_seconds=cfg.publish.backoff_seconds,
        **( {"sleep": sleep} if sleep else {} ),
    )
    _record(cfg, store, task, payload, outcome)
    return outcome


def _record(
    cfg: AppConfig,
    store: FileTaskStore,
    task: PublishTask,
    payload: PublishPayload,
    outcome: PublishOutcome,
) -> None:
    record = PublishRecord(
        publisher=getattr(cfg, "publish", None) and cfg.publish.publisher or "unknown",
        task_id=outcome.task_id,
        result="success" if outcome.success else "failed",
        simulated=outcome.simulated,
        verified=outcome.verified,
        at=datetime.now().astimezone().isoformat(),
        error=outcome.error,
        idempotency_key=payload.idempotency_key,
        remote_id=outcome.remote_id,
    )
    # 注意：store.transition 会重新从磁盘读取任务，因此记录必须随迁移一起写入，
    # 否则内存中的追加会丢失（幂等判断依赖 publish_records）。
    records = list(task.publish_records) + [record]

    if outcome.success:
        store.transition(
            task.date,
            TaskStatus.PUBLISHED,
            note=f"发布成功（simulated={outcome.simulated}, verified={outcome.verified}）",
            stage=TaskStage.PUBLISH,
            error="",
            artifacts={**task.artifacts, "publish_result": "success"},
            publish_records=records,
        )
    else:
        store.transition(
            task.date,
            TaskStatus.FAILED,
            note=outcome.error,
            stage=TaskStage.PUBLISH,
            error=outcome.error,
            publish_records=records,
        )

    # 保存发布结果（含素材版本信息）
    result_path = Path(cfg.data_dir) / task.date / "publish" / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_payload: dict[str, Any] = {
        "date": task.date,
        "publisher": cfg.publish.publisher,
        "simulated": outcome.simulated,
        "verified": outcome.verified,
        "success": outcome.success,
        "task_id": outcome.task_id,
        "remote_id": outcome.remote_id,
        "error": outcome.error,
        "idempotency_key": payload.idempotency_key,
        "content_fingerprint": payload.content_fingerprint,
        "images": [str(p) for p in payload.images],
        "recorded_at": record.at,
        "detail": outcome.detail,
    }
    with result_path.open("w", encoding="utf-8") as fh:
        json.dump(snapshot_payload, fh, ensure_ascii=False, indent=2)

    LOGGER.info(
        "发布结果已记录: %s（success=%s simulated=%s verified=%s）",
        result_path, outcome.success, outcome.simulated, outcome.verified,
        extra={"stage": "publish"},
    )
