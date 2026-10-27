"""模拟发布适配器（默认）。

用途：在未取得真实发布授权前，完整跑通发布流程并验证幂等与重试行为（FR-043）。
产物中 simulated=true / verified=false，README 明确标注真实发布尚未验收。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from usmarket.publishing.base import PublishOutcome, PublishPayload

LOGGER = logging.getLogger(__name__)


class MockPublisher:
    """可注入失败的模拟发布器。"""

    name = "mock"
    simulated = True
    verified = False  # 未经真实平台验证（Phase 5 之前恒为 False）

    def __init__(self, *, fail_first: int = 0) -> None:
        self.fail_first = fail_first
        self._calls = 0
        self.uploaded: list[str] = []
        self.published: list[str] = []

    # ---------- 接口 ----------
    def validate_content(self, payload: PublishPayload) -> list[str]:
        errors: list[str] = []
        if not payload.title.strip():
            errors.append("标题为空")
        if not payload.body.strip():
            errors.append("正文为空")
        if not payload.images:
            errors.append("缺少图片")
        for image in payload.images:
            if not Path(image).exists():
                errors.append(f"图片不存在: {image}")
        return errors

    def upload_images(self, payload: PublishPayload) -> tuple[str, ...]:
        ids = tuple(f"mock-image-{i:02d}" for i, _ in enumerate(payload.images, 1))
        self.uploaded.extend(ids)
        return ids

    def create_draft(self, payload: PublishPayload, image_ids: tuple[str, ...]) -> str:
        return f"mock-draft-{payload.content_fingerprint[:12]}"

    def publish(self, payload: PublishPayload) -> PublishOutcome:
        self._calls += 1
        # 不输出任何凭据（本适配器也不需要凭据）
        LOGGER.info(
            "[模拟发布] 标题=%s 图片=%d 张 idempotency_key=%s",
            payload.title, len(payload.images), payload.idempotency_key,
            extra={"stage": "publish"},
        )
        if self._calls <= self.fail_first:
            return PublishOutcome(
                success=False,
                task_id=f"mock-{payload.content_fingerprint[:12]}",
                simulated=True,
                verified=False,
                error=f"模拟失败（第 {self._calls} 次调用）",
            )

        errors = self.validate_content(payload)
        if errors:
            return PublishOutcome(
                success=False,
                task_id=f"mock-{payload.content_fingerprint[:12]}",
                simulated=True,
                verified=False,
                error="; ".join(errors),
            )

        image_ids = self.upload_images(payload)
        draft_id = self.create_draft(payload, image_ids)
        task_id = f"mock-{payload.content_fingerprint[:12]}"
        self.published.append(task_id)
        return PublishOutcome(
            success=True,
            task_id=task_id,
            simulated=True,
            verified=False,
            remote_id=draft_id,
            detail={"image_ids": list(image_ids), "draft_id": draft_id, "calls": self._calls},
        )

    def get_publish_status(self, task_id: str) -> str:
        return "published" if task_id in self.published else "unknown"

    def reset(self) -> dict[str, Any]:
        calls = self._calls
        self._calls = 0
        return {"reset_calls": calls}
