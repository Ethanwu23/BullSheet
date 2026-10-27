"""离线端到端测试：完整的采集 → 生成 → 校验 → 渲染 → 待审核链路。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from usmarket.cli.pipeline import day_paths, run_generate_command
from usmarket.config import AppConfig
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import TaskStatus

NOW = datetime(2026, 10, 26, 20, 5, tzinfo=UTC)
DATE = "2026-10-26"


def test_offline_pipeline_end_to_end(offline_cfg: AppConfig):
    task = run_generate_command(offline_cfg, DATE, render=True)

    paths = day_paths(offline_cfg, DATE)

    # 原始数据落盘（行情与文本分开存储）
    assert paths["raw_news"].exists()
    assert paths["raw_quotes"].exists()
    assert paths["source_results"].exists()
    assert paths["deduped"].exists()

    # 内容产物
    assert paths["content_json"].exists()
    assert paths["report"].exists()
    assert paths["sources"].exists()
    assert (paths["base"] / "REVIEW.md").exists()

    # 图片
    assert (paths["images"] / "cover.png").exists()
    pages = sorted(paths["images"].glob("page_*.png"))
    assert 5 <= len(pages) <= 7
    for image_path in [paths["images"] / "cover.png", *pages]:
        with Image.open(image_path) as img:
            assert img.size == (offline_cfg.image.width, offline_cfg.image.height)

    # 任务状态
    assert task.status == TaskStatus.REVIEW
    assert task.content_fingerprint
    assert task.generator == "rule_based"


def test_content_json_is_valid_and_complete(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    paths = day_paths(offline_cfg, DATE)
    data = json.loads(paths["content_json"].read_text(encoding="utf-8"))

    for key in (
        "date", "summary", "index_moves", "top_news", "watchlist_moves",
        "earnings_and_macro", "next_session", "risk_notes", "xhs",
        "sources", "disclaimer",
    ):
        assert key in data, f"缺少字段 {key}"

    assert 3 <= len(data["top_news"]) <= 5
    assert data["xhs"]["title"]
    assert data["xhs"]["body"]
    assert data["xhs"]["tags"]
    for entry in data["top_news"]:
        assert entry["source_url"].startswith("http")
        assert entry["source_title"]
    for src in data["sources"]:
        assert src["url"].startswith("http")


def test_news_dedup_applied_in_pipeline(offline_cfg: AppConfig):
    """fixture 中有 2 条同标题转载，管线中应只计 1 条。"""
    run_generate_command(offline_cfg, DATE, render=False)
    paths = day_paths(offline_cfg, DATE)
    raw = [
        json.loads(line)
        for line in paths["raw_news"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    deduped = [
        json.loads(line)
        for line in paths["deduped"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(deduped) < len(raw)

    titles = [d["title"] for d in deduped]
    assert (
        sum(1 for t in titles if "beats estimates as data center revenue climbs" in t) == 1
    )


def test_old_news_filtered_out(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    paths = day_paths(offline_cfg, DATE)
    deduped = [
        json.loads(line)
        for line in paths["deduped"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert not any("last month" in item["title"] for item in deduped)


def test_html_injection_is_stripped(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    paths = day_paths(offline_cfg, DATE)
    text = paths["report"].read_text(encoding="utf-8")
    assert "<script>" not in text
    assert "\u200b" not in text


def test_quotes_are_traceable_in_report(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    paths = day_paths(offline_cfg, DATE)
    quotes = json.loads(paths["raw_quotes"].read_text(encoding="utf-8"))
    report = paths["report"].read_text(encoding="utf-8")

    for quote in quotes["indices"]:
        if quote["quality"] == "ok":
            assert f"{quote['price']:,.2f}" in report


def test_pipeline_is_idempotent_on_rerun(offline_cfg: AppConfig):
    """同一日期重复运行产生相同指纹，且不产生第二条任务。"""
    first = run_generate_command(offline_cfg, DATE, render=False)
    second = run_generate_command(offline_cfg, DATE, render=False)
    assert first.content_fingerprint == second.content_fingerprint

    store = FileTaskStore(Path(offline_cfg.data_dir))
    assert len(store.list_all()) == 1


def test_rerun_from_rejected_state(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    store = FileTaskStore(Path(offline_cfg.data_dir))
    store.transition(DATE, TaskStatus.REJECTED, note="内容不够吸引人")
    assert store.get(DATE).status == TaskStatus.REJECTED

    store.transition(DATE, TaskStatus.PENDING, note="重跑")
    run_generate_command(offline_cfg, DATE, render=False)
    assert store.get(DATE).status == TaskStatus.REVIEW


def test_sources_doc_lists_limits(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    paths = day_paths(offline_cfg, DATE)
    text = paths["sources"].read_text(encoding="utf-8")
    assert "来源与数据清单" in text
    assert "延迟" in text or "非实时" in text
    assert "条款" in text


def test_review_file_contains_actions(offline_cfg: AppConfig):
    run_generate_command(offline_cfg, DATE, render=False)
    text = (Path(offline_cfg.data_dir) / DATE / "REVIEW.md").read_text(encoding="utf-8")
    assert "usmarket approve" in text
    assert "usmarket reject" in text
    assert "usmarket publish" in text


def test_low_confidence_flagged_when_no_quotes(tmp_path: Path, base_config: AppConfig):
    """行情全部缺失时必须标记低置信度，且不出现编造数字。"""
    empty_quotes = tmp_path / "empty_quotes.json"
    empty_quotes.write_text('{"as_of": "2026-10-26T20:05:00Z", "quotes": {}}', encoding="utf-8")

    cfg = base_config.with_overrides(offline=True, data_dir=tmp_path / "data")
    from unittest.mock import patch

    from usmarket.market_data.mock import MockQuoteProvider

    with patch(
        "usmarket.market_data.service.build_provider",
        return_value=MockQuoteProvider(empty_quotes),
    ):
        task = run_generate_command(cfg, DATE, render=False)

    paths = day_paths(cfg, DATE)
    content = json.loads(paths["content_json"].read_text(encoding="utf-8"))
    assert content["low_confidence"] is True
    for move in content["index_moves"]:
        assert move["price"] is None
        assert move["change_percent"] is None
    report = paths["report"].read_text(encoding="utf-8")
    assert "数据缺失" in report
    assert task.content_fingerprint


@pytest.mark.parametrize("template", ["daily_review", "flash_brief"])
def test_both_templates_produce_pages(offline_cfg: AppConfig, template: str):
    from dataclasses import replace

    cfg = replace(
        offline_cfg, image=replace(offline_cfg.image, template=template)
    )
    run_generate_command(cfg, DATE, render=True)
    paths = day_paths(cfg, DATE)
    assert (paths["images"] / "cover.png").exists()
    assert len(list(paths["images"].glob("page_*.png"))) >= 5
