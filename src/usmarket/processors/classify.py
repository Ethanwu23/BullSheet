"""分类：识别涉及股票代码、新闻类别。"""

from __future__ import annotations

import re
from dataclasses import replace

from usmarket.collectors.models import NewsCategory, NewsItem
from usmarket.market_data.base import _DISPLAY_NAMES

# ticker → 公司别名（用于"标题必须提到公司名或代码"的过滤，参考 stock-report 思路）
COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "NVDA": ("nvidia", "英伟达"),
    "AAPL": ("apple", "苹果"),
    "MSFT": ("microsoft", "微软"),
    "GOOGL": ("alphabet", "google", "谷歌"),
    "AMZN": ("amazon", "亚马逊"),
    "META": ("meta platforms", "facebook", "meta"),
    "TSLA": ("tesla", "特斯拉"),
    "SPCX": ("spacex", "space exploration", "starlink", "星链"),
    "AMD": ("amd", "advanced micro"),
    "AVGO": ("broadcom", "博通"),
    "TSM": ("tsmc", "taiwan semiconductor", "台积电"),
    "NFLX": ("netflix", "奈飞"),
    "JPM": ("jpmorgan", "jp morgan", "摩根大通"),
}

CATEGORY_KEYWORDS: dict[NewsCategory, tuple[str, ...]] = {
    NewsCategory.EARNINGS: (
        "earnings", "quarterly results", "q1", "q2", "q3", "q4", "guidance",
        "revenue", "eps", "财报", "业绩",
    ),
    NewsCategory.MACRO: (
        "fed", "federal reserve", "inflation", "cpi", "ppi", "interest rate",
        "fomc", "payroll", "jobless", "unemployment", "gdp", "treasury",
        "美联储", "通胀", "就业", "利率",
    ),
    NewsCategory.MARKET_MOVE: (
        "rally", "selloff", "sell-off", "slump", "surge", "jump", "plunge",
        "record high", "pullback", "correction", "大跌", "大涨", "创新高",
    ),
    NewsCategory.COMPANY: (
        "acquisition", "acquire", "merger", "buyout", "stake", "ipo",
        "buyback", "dividend", "layoff", "recall", "antitrust",
        "并购", "收购", "回购",
    ),
}

_TICKER_RE = re.compile(r"\b([A-Z]{1,5})\b")


def detect_tickers(text: str, watchlist: tuple[str, ...]) -> tuple[str, ...]:
    """在文本中识别关注的股票代码或公司别名。"""
    lowered = text.lower()
    found: list[str] = []
    for ticker in watchlist:
        upper = ticker.upper()
        if upper in {"^GSPC", "^IXIC", "^DJI"}:
            continue
        if upper in text or re.search(rf"\b{re.escape(upper)}\b", text):
            found.append(upper)
            continue
        aliases = COMPANY_ALIASES.get(upper, ())
        if any(alias in lowered for alias in aliases):
            found.append(upper)
    return tuple(dict.fromkeys(found))


def classify(item: NewsItem, watchlist: tuple[str, ...]) -> NewsItem:
    """补充 tickers 与 category。"""
    haystack = f"{item.title} {item.summary}".lower()
    category = NewsCategory.OTHER
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            category = cat
            break

    tickers = detect_tickers(f"{item.title} {item.summary}", watchlist)
    merged = tuple(dict.fromkeys(item.tickers + tickers))
    return replace(item, category=category, tickers=merged)


def mentions_ticker(item: NewsItem, ticker: str) -> bool:
    """标题或摘要是否提到该 ticker / 公司名（用于过滤"相关新闻"噪声）。"""
    text = f"{item.title} {item.summary}"
    if ticker.upper() in text:
        return True
    aliases = COMPANY_ALIASES.get(ticker.upper(), ())
    lowered = text.lower()
    return any(alias in lowered for alias in aliases)


def display_name(symbol: str) -> str:
    return _DISPLAY_NAMES.get(symbol.upper(), symbol.upper())
