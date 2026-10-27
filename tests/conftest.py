"""共享测试夹具。

所有测试默认离线运行，不访问网络、不需要 API key。
网络测试需显式设置 NETWORK_TESTS=1。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from usmarket.collectors.manager import load_news_fixture
from usmarket.config import PROJECT_ROOT, AppConfig, load_config
from usmarket.market_data.mock import MockQuoteProvider
from usmarket.market_data.service import collect_snapshot

FIXTURES = Path(__file__).parent / "fixtures"

# 固定测试时刻：2026-10-26 20:05 UTC = 周一 16:05 EDT（盘后）
TEST_NOW = datetime(2026, 10, 26, 20, 5, tzinfo=UTC)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "network: 需要联网的测试（默认跳过）")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("NETWORK_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="网络测试默认跳过；设置 NETWORK_TESTS=1 启用")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def base_config() -> AppConfig:
    """不读取环境变量的干净配置（避免受开发者 .env 影响）。"""
    return load_config(PROJECT_ROOT / "config" / "default.yaml", apply_env=False)


@pytest.fixture
def offline_cfg(base_config: AppConfig, tmp_path: Path) -> AppConfig:
    return base_config.with_overrides(offline=True, data_dir=tmp_path / "data")


@pytest.fixture
def mock_provider() -> MockQuoteProvider:
    return MockQuoteProvider(FIXTURES / "quotes.json")


@pytest.fixture
def snapshot(offline_cfg: AppConfig, mock_provider: MockQuoteProvider):
    return collect_snapshot(offline_cfg, provider=mock_provider, as_of=TEST_NOW)


@pytest.fixture
def news_items() -> list:
    return load_news_fixture(FIXTURES / "news.json", fetched_at=TEST_NOW)


@pytest.fixture
def test_now() -> datetime:
    return TEST_NOW


@pytest.fixture
def processed_news(offline_cfg: AppConfig, news_items: list) -> list:
    """清洗 + 分类 + 去重 + 时效过滤后的新闻（与 pipeline 一致）。"""
    from dataclasses import replace

    from usmarket.processors.classify import classify
    from usmarket.processors.dedupe import attach_merge_info, deduplicate
    from usmarket.processors.filter import filter_by_lookback, rank
    from usmarket.processors.sanitize import clean_text

    items = [
        replace(
            item,
            title=clean_text(item.title, max_length=300),
            summary=clean_text(item.summary, max_length=800),
        )
        for item in news_items
    ]
    items = [classify(item, offline_cfg.watchlist.tickers) for item in items]
    deduped, merged = deduplicate(items)
    deduped = attach_merge_info(deduped, merged)
    fresh, unknown = filter_by_lookback(
        deduped, now=TEST_NOW, lookback_hours=offline_cfg.news.lookback_hours
    )
    return rank(fresh) + rank(unknown)


@pytest.fixture
def content(offline_cfg: AppConfig, snapshot, processed_news: list):
    """用规则式生成器产出可校验的 DailyContent。"""
    from usmarket.ai.service import generate_daily_content

    content, _warnings = generate_daily_content(
        offline_cfg, snapshot, processed_news, now=TEST_NOW
    )
    return content
