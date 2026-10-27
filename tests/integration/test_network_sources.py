"""真实数据源验证测试（默认跳过，需 NETWORK_TESTS=1）。

目的：验证 docs/research.md 中"实测可用"的结论可复现。
这些测试依赖外部服务，可能因为服务端变更而失败 —— 失败即说明数据源失效，
需要更新配置与文档。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.network


def test_yahoo_chart_api_returns_index_quotes():
    from usmarket.market_data.yahoo import YahooQuoteProvider

    provider = YahooQuoteProvider(timeout_seconds=20, retries=2)
    quotes = [provider.fetch_quote(sym, sym) for sym in ("^GSPC", "^IXIC", "^DJI")]
    usable = [q for q in quotes if q.is_usable()]
    assert len(usable) >= 2, "至少一个主要指数应能取到行情"
    for quote in usable:
        assert quote.price is not None and quote.price > 0
        assert quote.provider == "yahoo"
        assert quote.is_delayed is True  # 不得伪装成实时
        assert quote.raw["meta"]["exchangeTimezoneName"] == "America/New_York"


def test_live_rss_feeds_parse():
    from usmarket.collectors.rss import RssSource

    feeds = [
        ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("FederalReserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ]
    for name, url in feeds:
        result = RssSource(name, url, timeout_seconds=20, retries=1).fetch(
            fetched_at=datetime.now(tz=UTC)
        )
        assert result.ok, f"{name} 抓取失败: {result.error}"
        assert len(result.items) > 0


def test_sec_edgar_requires_declared_user_agent():
    """SEC 对未声明身份的请求返回 403（实测结论）。"""
    from usmarket.http_client import HttpError, fetch_text

    url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        "&CIK=1045810&type=8-K&dateb=&owner=include&count=5&output=atom"
    )
    with pytest.raises(HttpError):
        fetch_text(url, timeout=20, retries=0, user_agent="Mozilla/5.0")

    body = fetch_text(
        url, timeout=20, retries=1,
        user_agent="USMarketDailyXHS/0.1 (test@example.com)",
    )
    assert "<feed" in body or "entry" in body


def test_known_dead_feed_still_dead():
    """记录已失效的源：若该源恢复可用，应更新配置启用它。"""
    from usmarket.http_client import HttpError, fetch_text

    with pytest.raises(HttpError):
        fetch_text("https://finance.yahoo.com/news/rssindex", timeout=20, retries=0)
