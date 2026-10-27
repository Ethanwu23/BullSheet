"""采集编排：汇总多个来源，单源失败不影响整体。"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from usmarket.collectors.edgar import EdgarSource
from usmarket.collectors.models import NewsItem, SourceResult
from usmarket.collectors.rss import RssSource, fetch_many, sources_from_config
from usmarket.config import PROJECT_ROOT, AppConfig

LOGGER = logging.getLogger(__name__)

DEFAULT_NEWS_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "news.json"


def build_ticker_query_sources(cfg: AppConfig) -> list[RssSource]:
    """为每个 ticker / 主题生成检索型 RSS 源（Google News 搜索，实测可用）。"""
    sources: list[RssSource] = []
    template = cfg.news.ticker_query_template
    for ticker in cfg.watchlist.tickers:
        url = template.format(query=f"{ticker} stock")
        sources.append(
            RssSource(
                f"Google News: {ticker}",
                url,
                trust="aggregator",
                timeout_seconds=cfg.news.request_timeout_seconds,
                max_items=cfg.news.max_items_per_source,
                retries=cfg.news.max_retries,
            )
        )
    for topic in cfg.watchlist.topics:
        url = template.format(query=f"{topic} stock market")
        sources.append(
            RssSource(
                f"Google News: {topic}",
                url,
                trust="aggregator",
                timeout_seconds=cfg.news.request_timeout_seconds,
                max_items=cfg.news.max_items_per_source,
                retries=cfg.news.max_retries,
            )
        )
    return sources


def collect_news(
    cfg: AppConfig,
    *,
    fetched_at: datetime | None = None,
    fixture_path: Path | None = None,
) -> tuple[list[SourceResult], list[NewsItem]]:
    """采集新闻。

    返回 (每个源的结果, 汇总的新闻列表)。
    离线模式从 fixture 读取，不访问网络。
    """
    now = fetched_at or datetime.now(tz=UTC)

    if cfg.offline:
        path = Path(fixture_path) if fixture_path else DEFAULT_NEWS_FIXTURE
        items = load_news_fixture(path, fetched_at=now)
        LOGGER.info("离线模式：从 fixture 载入 %d 条新闻 (%s)", len(items), path)
        return [SourceResult(source="fixture", url=str(path), items=tuple(items))], items

    sources = sources_from_config(
        cfg.news.feeds,
        timeout_seconds=cfg.news.request_timeout_seconds,
        max_items=cfg.news.max_items_per_source,
        retries=cfg.news.max_retries,
    )
    sources += build_ticker_query_sources(cfg)

    results = fetch_many(sources, fetched_at=now)

    if cfg.news.edgar_enabled:
        edgar = EdgarSource(
            cfg.watchlist.tickers,
            forms=cfg.news.edgar_forms,
            user_agent=cfg.news.edgar_user_agent,
            timeout_seconds=cfg.news.request_timeout_seconds,
            max_items=10,
        )
        results.append(edgar.fetch(fetched_at=now))

    items: list[NewsItem] = []
    for result in results:
        items.extend(result.items)

    failures = [r for r in results if not r.ok]
    if failures:
        LOGGER.warning(
            "%d/%d 个新闻源失败（继续处理可用源）: %s",
            len(failures), len(results),
            ", ".join(f"{r.source}: {r.error}" for r in failures),
            extra={"stage": "collect"},
        )
    if not items and results:
        LOGGER.error("全部新闻源均失败，未采集到任何新闻", extra={"stage": "collect"})

    LOGGER.info("新闻采集完成: %d 条，来源 %d 个", len(items), len(results),
                extra={"stage": "collect"})
    return results, items


def load_news_fixture(path: Path, *, fetched_at: datetime | None = None) -> list[NewsItem]:
    """从 JSON fixture 载入新闻（离线测试用）。"""
    now = fetched_at or datetime.now(tz=UTC)
    if not Path(path).exists():
        LOGGER.warning("新闻 fixture 不存在: %s", path)
        return []
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    raw_items = data.get("items", []) if isinstance(data, dict) else list(data)
    items: list[NewsItem] = []
    for raw in raw_items:
        item = NewsItem.from_dict(raw)
        # fixture 中的 fetched_at 保留；若缺失则用当前时间
        if "fetched_at" not in raw:
            item = replace(item, fetched_at=now)
        items.append(item)
    return items


def save_raw_news(items: list[NewsItem], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    LOGGER.info("原始新闻已保存: %s (%d 条)", path, len(items))
    return path


def save_source_results(results: list[SourceResult], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "source": r.source,
            "url": r.url,
            "ok": r.ok,
            "error": r.error,
            "count": len(r.items),
            "elapsed_seconds": round(r.elapsed_seconds, 3),
        }
        for r in results
    ]
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path
