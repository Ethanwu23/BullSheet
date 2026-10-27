"""图片渲染入口：选择模板、渲染封面与正文页、落盘并做基础质检。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image

from usmarket.config import AppConfig
from usmarket.errors import RenderError
from usmarket.image_renderer.sanitize import sanitize_content_for_image
from usmarket.image_renderer.theme import ResolvedTheme
from usmarket.market_data.models import QuoteSnapshot
from usmarket.validation.schema import DailyContent

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RenderResult:
    cover: Path
    pages: tuple[Path, ...]
    manifest: Path


def build_template(cfg: AppConfig, theme: ResolvedTheme):
    name = (cfg.image.template or "daily_review").lower()
    if name == "flash_brief":
        from usmarket.image_renderer.templates.flash_brief import FlashBriefTemplate

        return FlashBriefTemplate(cfg, theme)
    if name == "daily_review":
        from usmarket.image_renderer.templates.daily_review import DailyReviewTemplate

        return DailyReviewTemplate(cfg, theme)
    raise RenderError(f"未知图片模板: {name}")


def assert_not_blank(image: Image.Image, *, threshold: float = 0.995) -> None:
    """检查图片不是空白（单一颜色占比过高即视为空白）。"""
    small = image.convert("RGB").resize((64, 64))
    pixels = list(small.getdata())
    most_common = max(set(pixels), key=pixels.count)
    ratio = pixels.count(most_common) / len(pixels)
    if ratio >= threshold:
        raise RenderError(f"生成图片疑似空白（单一颜色占比 {ratio:.1%}）")


def render_images(
    cfg: AppConfig,
    content: DailyContent,
    snapshot: QuoteSnapshot,
    out_dir: Path,
    *,
    now: datetime | None = None,
) -> RenderResult:
    """渲染封面与正文页。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    theme = ResolvedTheme.from_config(cfg.image.theme)
    template = build_template(cfg, theme)

    # 图片字体不含 emoji 字形，且 Markdown 标记会原样显示 → 渲染前清洗（不改 content.json）
    drawing_content = sanitize_content_for_image(content)

    try:
        images = template.build_pages(drawing_content, snapshot, now or datetime.now())
    except Exception as exc:  # noqa: BLE001
        raise RenderError(f"图片渲染失败: {type(exc).__name__}: {exc}") from exc

    if not images:
        raise RenderError("模板未生成任何图片")

    for image in images:
        if image.size != (cfg.image.width, cfg.image.height):
            raise RenderError(
                f"图片尺寸 {image.size} 与配置 {(cfg.image.width, cfg.image.height)} 不一致"
            )
        assert_not_blank(image)

    cover_path = out_dir / "cover.png"
    images[0].save(cover_path, format="PNG")

    page_paths: list[Path] = []
    for idx, image in enumerate(images[1:], 1):
        path = out_dir / f"page_{idx:02d}.png"
        image.save(path, format="PNG")
        page_paths.append(path)

    manifest = {
        "date": content.date,
        "template": template.name,
        "size": {"width": cfg.image.width, "height": cfg.image.height},
        "cover": cover_path.name,
        "pages": [p.name for p in page_paths],
        "page_count": len(page_paths),
        "generated_at": (now or datetime.now()).isoformat(),
    }
    manifest_path = out_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    LOGGER.info(
        "图片渲染完成: 封面 1 张 + 正文 %d 张 -> %s",
        len(page_paths), out_dir, extra={"stage": "render"},
    )
    return RenderResult(cover=cover_path, pages=tuple(page_paths), manifest=manifest_path)
