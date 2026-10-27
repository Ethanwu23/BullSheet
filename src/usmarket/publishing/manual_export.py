"""人工发布导出适配器。

不调用任何平台接口；把可直接复制的发布包（文案 + 图片清单 + 操作清单）写到磁盘，
由运营者手动发布。这是"无法验证真实发布"时最诚实、最安全的交付方式。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from usmarket.publishing.base import PublishOutcome, PublishPayload

LOGGER = logging.getLogger(__name__)


class ManualExportPublisher:
    name = "manual_export"
    simulated = True   # 未真实调用平台
    verified = False

    def __init__(self, export_dir: Path) -> None:
        self.export_dir = Path(export_dir)

    def validate_content(self, payload: PublishPayload) -> list[str]:
        errors: list[str] = []
        if not payload.title.strip():
            errors.append("标题为空")
        if not payload.body.strip():
            errors.append("正文为空")
        if not payload.images:
            errors.append("缺少图片")
        return errors

    def upload_images(self, payload: PublishPayload) -> tuple[str, ...]:
        return tuple(str(p) for p in payload.images)

    def create_draft(self, payload: PublishPayload, image_ids: tuple[str, ...]) -> str:
        return f"manual-{payload.date}"

    def publish(self, payload: PublishPayload) -> PublishOutcome:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        errors = self.validate_content(payload)
        if errors:
            return PublishOutcome(
                success=False,
                task_id=f"manual-{payload.date}",
                simulated=True,
                verified=False,
                error="; ".join(errors),
            )

        bundle = {
            "date": payload.date,
            "title": payload.title,
            "body": payload.body,
            "tags": list(payload.tags),
            "images": [str(p) for p in payload.images],
            "content_fingerprint": payload.content_fingerprint,
            "idempotency_key": payload.idempotency_key,
            "note": (
                "本文件由 manual_export 适配器生成：系统未调用任何平台接口，"
                "请人工复制文案与图片到小红书创作者后台发布。"
            ),
        }
        bundle_path = self.export_dir / "publish_bundle.json"
        with bundle_path.open("w", encoding="utf-8") as fh:
            json.dump(bundle, fh, ensure_ascii=False, indent=2)

        readme = self.export_dir / "HOW_TO_PUBLISH.md"
        readme.write_text(
            "# 人工发布说明\n\n"
            "本目录由 `manual_export` 适配器生成，系统**未**调用小红书任何接口。\n\n"
            "## 步骤\n\n"
            "1. 打开小红书创作者后台的发布页；\n"
            "2. 复制 `publish_bundle.json` 中的 `title` 与 `body`；\n"
            "3. 按 `images` 列表顺序上传图片；\n"
            "4. 人工确认无违规表述后发布；\n"
            "5. 回到 CLI 执行 `usmarket mark-published --date <date>` 记录结果。\n\n"
            "## 注意\n\n"
            "- 真实自动发布尚未验收，请勿声称本流程为无人值守发布。\n"
            f"- 内容指纹：`{payload.content_fingerprint}`\n",
            encoding="utf-8",
        )

        LOGGER.info("已导出人工发布包: %s", bundle_path, extra={"stage": "publish"})
        return PublishOutcome(
            success=True,
            task_id=f"manual-{payload.date}",
            simulated=True,
            verified=False,
            remote_id=str(bundle_path),
            detail={"bundle": str(bundle_path), "readme": str(readme)},
        )

    def get_publish_status(self, task_id: str) -> str:
        bundle = self.export_dir / "publish_bundle.json"
        return "exported" if bundle.exists() else "unknown"
