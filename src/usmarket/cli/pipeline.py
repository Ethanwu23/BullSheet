"""端到端流水线：采集 → 生成 → 校验 → 渲染 → 待审核。"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from usmarket.ai.service import generate_daily_content
from usmarket.collectors.manager import collect_news, save_raw_news, save_source_results
from usmarket.config import AppConfig
from usmarket.content.json_store import save_content
from usmarket.content.markdown import render_report
from usmarket.content.sources_doc import render_sources_doc
from usmarket.errors import CollectionError, USMarketError, ValidationError
from usmarket.logging_setup import setup_logging
from usmarket.market_data.models import QuoteSnapshot
from usmarket.market_data.service import (
    collect_snapshot,
    save_snapshot,
    snapshot_from_dict,
)
from usmarket.processors.classify import classify
from usmarket.processors.dedupe import attach_merge_info, deduplicate
from usmarket.processors.filter import filter_by_lookback, rank
from usmarket.processors.sanitize import clean_text
from usmarket.publishing.base import compute_fingerprint
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import PublishTask, TaskStage, TaskStatus, coerce_stage
from usmarket.validation.schema import DailyContent

LOGGER = logging.getLogger(__name__)


def day_paths(cfg: AppConfig, date: str) -> dict[str, Path]:
    base = Path(cfg.data_dir) / date
    return {
        "base": base,
        "raw": base / "raw",
        "processed": base / "processed",
        "content": base / "content",
        "images": base / "images",
        "raw_news": base / "raw" / "news.jsonl",
        "raw_quotes": base / "raw" / "quotes.json",
        "source_results": base / "raw" / "source_results.json",
        "deduped": base / "processed" / "news_deduped.jsonl",
        "content_json": base / "content" / "content.json",
        "report": base / "content" / "report.md",
        "sources": base / "content" / "sources.md",
    }


def _sanitize_items(items: list) -> list:
    """清洗外部文本（去 HTML / 控制字符），不改变语义。"""
    out = []
    for item in items:
        out.append(
            replace(
                item,
                title=clean_text(item.title, max_length=300),
                summary=clean_text(item.summary, max_length=800),
            )
        )
    return out


def run_collect(
    cfg: AppConfig, date: str, now: datetime, paths: dict[str, Path]
) -> tuple[list, list]:
    """采集新闻，返回 (source_results, 去重后的新闻)。"""
    results, raw_items = collect_news(cfg, fetched_at=now)
    save_raw_news(raw_items, paths["raw_news"])
    save_source_results(results, paths["source_results"])

    items = _sanitize_items(raw_items)
    items = [classify(item, cfg.watchlist.tickers) for item in items]

    deduped, merged = deduplicate(items)
    deduped = attach_merge_info(deduped, merged)

    fresh, unknown = filter_by_lookback(
        deduped, now=now, lookback_hours=cfg.news.lookback_hours
    )
    # 未知发布时间的条目排在后面，不冒充最新
    ordered = rank(fresh) + rank(unknown)

    from usmarket.collectors.manager import save_raw_news as _save

    _save(ordered, paths["deduped"])

    if not ordered:
        LOGGER.error("过滤后无任何可用新闻", extra={"stage": "collect"})
        raise CollectionError("过滤后无任何可用新闻（可能是源全部失败或时间窗过窄）")

    LOGGER.info("新闻处理完成：原始 %d → 去重 %d → 时效过滤后 %d",
                len(raw_items), len(deduped), len(ordered),
                extra={"stage": "collect"})
    return results, ordered


def run_market(
    cfg: AppConfig, date: str, now: datetime, paths: dict[str, Path]
) -> QuoteSnapshot:
    """采集行情。"""
    snapshot = collect_snapshot(cfg, as_of=now)
    snapshot = replace(snapshot, date=date)
    save_snapshot(snapshot, paths["raw_quotes"])
    return snapshot


def run_generate(
    cfg: AppConfig, snapshot: QuoteSnapshot, news: list, now: datetime
) -> tuple[DailyContent, list[str]]:
    content, warnings = generate_daily_content(cfg, snapshot, news, now=now)
    return content, warnings


def compute_content_fingerprint(
    date: str, news: list, snapshot: QuoteSnapshot
) -> str:
    urls = [item.url for item in news]
    values: list[str] = []
    for quote in snapshot.all_quotes():
        if quote.is_usable():
            values.append(f"{quote.symbol}:{quote.price}:{quote.change_percent}")
        else:
            values.append(f"{quote.symbol}:missing")
    return compute_fingerprint(date, urls, values)


def run_generate_command(
    cfg: AppConfig,
    date: str,
    *,
    render: bool = True,
    now: datetime | None = None,
) -> PublishTask:
    """完整执行一次生成流程（不含发布）。"""
    now = now or datetime.now().astimezone()
    if cfg.offline:
        # 离线模式使用固定时刻（目标日 20:05 UTC ≈ 美东 16:05，盘后），
        # 保证 fixture 演示与测试可复现，不依赖运行时刻。
        now = datetime.strptime(f"{date} 20:05:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    paths = day_paths(cfg, date)
    for key in ("raw", "processed", "content", "images"):
        paths[key].mkdir(parents=True, exist_ok=True)

    setup_logging(cfg.log_level, log_file=paths["base"] / "run.log")

    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date) or PublishTask(date=date, created_at=now.isoformat())

    # 重新生成：显式重置为 pending 后再执行（已发布的任务不允许被静默覆盖）
    if task.status != TaskStatus.PENDING:
        if task.status == TaskStatus.PUBLISHED:
            raise USMarketError(
                f"任务 {date} 已发布，重新生成会破坏已发布产物的可追溯性；"
                f"如需重做请更换日期或先清理该目录。"
            )
        LOGGER.warning(
            "任务 %s 当前状态 %s，先重置为 pending 再重新生成", date, task.status.value
        )
        task.status = TaskStatus.PENDING
        task.error = ""
    task.stage = TaskStage.COLLECT
    store.save(task)

    try:
        results, news = run_collect(cfg, date, now, paths)
        snapshot = run_market(cfg, date, now, paths)
        task.stage = TaskStage.GENERATE
        store.save(task)

        content, warnings = run_generate(cfg, snapshot, news, now)
        task.stage = TaskStage.VALIDATION

        fingerprint = compute_content_fingerprint(date, news, snapshot)
        content = content.model_copy(update={})
        task.content_fingerprint = fingerprint
        task.generator = content.generator
        task.warnings = warnings
        store.save(task)

        # 落盘：结构化 JSON + Markdown + 来源清单
        save_content(content, paths["content_json"])
        paths["report"].write_text(
            render_report(content, snapshot, cfg, warnings=warnings), encoding="utf-8"
        )
        paths["sources"].write_text(
            render_sources_doc(cfg, snapshot, results), encoding="utf-8"
        )

        if render:
            from usmarket.image_renderer.renderer import render_images

            task.stage = TaskStage.RENDER
            store.save(task)
            result = render_images(cfg, content, snapshot, paths["images"], now=now)
            task.artifacts = {
                "content": str(paths["content_json"]),
                "report": str(paths["report"]),
                "sources": str(paths["sources"]),
                "quotes": str(paths["raw_quotes"]),
                "news": str(paths["raw_news"]),
                "cover": str(result.cover),
                "pages": ",".join(str(p) for p in result.pages),
            }
            task.template = cfg.image.template

        task.stage = TaskStage.NONE
        if task.status in {TaskStatus.PENDING, TaskStatus.FAILED, TaskStatus.REJECTED}:
            store.transition(date, TaskStatus.GENERATED, note="内容生成完成",
                             artifacts=task.artifacts,
                             content_fingerprint=fingerprint,
                             generator=content.generator,
                             warnings=warnings,
                             template=task.template)
        else:
            task.artifacts = task.artifacts
            store.save(task)

        # 自动进入待审核
        store.transition(date, TaskStatus.REVIEW, note="等待人工审核")
        task = store.get(date) or task

        _write_review_file(cfg, date, paths, task, content, snapshot)
        LOGGER.info("生成流程完成: %s", date, extra={"stage": "generate"})
        return task
    except ValidationError as exc:
        store.transition(date, TaskStatus.FAILED, note=exc.message,
                         stage=TaskStage.VALIDATION,
                         error=f"{exc.message}: {exc.detail or ''}")
        raise
    except USMarketError as exc:
        store.transition(date, TaskStatus.FAILED, note=exc.message,
                         stage=coerce_stage(exc.stage), error=exc.message)
        raise
    except Exception as exc:  # noqa: BLE001
        store.transition(date, TaskStatus.FAILED, note=f"{type(exc).__name__}: {exc}",
                         stage=task.stage, error=str(exc))
        raise


def _write_review_file(
    cfg: AppConfig,
    date: str,
    paths: dict[str, Path],
    task: PublishTask,
    content: DailyContent,
    snapshot: QuoteSnapshot,
) -> Path:
    """生成人工审核用的 Markdown 文件（FR-052）。"""
    review_path = paths["base"] / "REVIEW.md"
    lines = [
        f"# 审核：{date}",
        "",
        f"- 状态：`{task.status.value}`",
        f"- 生成方式：`{content.generator}`",
        f"- 内容指纹：`{task.content_fingerprint}`",
        f"- 行情 provider：`{snapshot.provider}`（{'延迟' if snapshot.is_delayed else '实时'}）",
        f"- 低置信度：{'是 ⚠️ 必须复核' if content.low_confidence else '否'}",
        "",
        "## 小红书标题",
        "",
        content.xhs.title,
        "",
        "## 正文预览",
        "",
        content.xhs.body[:400],
        "",
        "## 图片",
        "",
    ]
    cover = paths["images"] / "cover.png"
    if cover.exists():
        lines.append(f"- 封面：`{cover}`")
    for page in sorted(paths["images"].glob("page_*.png")):
        lines.append(f"- `{page}`")
    lines += [
        "",
        "## 审核操作",
        "",
        "```bash",
        f"usmarket approve --date {date}     # 通过",
        f"usmarket reject  --date {date} --reason '原因'  # 驳回",
        f"usmarket publish --date {date}     # 发布（需先 approve）",
        "```",
        "",
        "## 告警",
        "",
    ]
    lines += [f"- {w}" for w in task.warnings] or ["- 无"]
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return review_path


def load_generated(cfg: AppConfig, date: str) -> tuple[DailyContent, QuoteSnapshot, list[Path]]:
    """从已生成产物恢复内容（用于重新渲染或恢复审核流程）。"""
    paths = day_paths(cfg, date)
    if not paths["content_json"].exists():
        raise USMarketError(f"未找到已生成内容: {paths['content_json']}")
    from usmarket.content.json_store import load_content
    from usmarket.market_data.service import load_snapshot

    content = load_content(paths["content_json"])
    snapshot = snapshot_from_dict(load_snapshot(paths["raw_quotes"]))
    images: list[Path] = []
    cover = paths["images"] / "cover.png"
    if cover.exists():
        images.append(cover)
    images.extend(sorted(paths["images"].glob("page_*.png")))
    return content, snapshot, images
