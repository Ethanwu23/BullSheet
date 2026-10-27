"""SEC EDGAR 公司公告抓取（8-K 等）。

合规要求（实测）：SEC 会拒绝未声明身份的请求（浏览器 UA → 403）。
必须发送形如 "AppName/Version (contact-email)" 的 User-Agent。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from usmarket.collectors.base import make_item
from usmarket.collectors.models import SourceResult
from usmarket.http_client import HttpError, fetch_text

LOGGER = logging.getLogger(__name__)

EDGAR_BASE = "https://www.sec.gov/cgi-bin/browse-edgar"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# SEC CIK 映射（常用标的；缺失时回退 EDGAR 公司检索接口）
KNOWN_CIKS: dict[str, str] = {
    "NVDA": "1045810",
    "AAPL": "320193",
    "MSFT": "789019",
    "GOOGL": "1652044",
    "AMZN": "1018724",
    "META": "1326801",
    "TSLA": "1318605",
    "AMD": "2488",
    "AVGO": "1730168",
    "TSM": "1046179",
    "NFLX": "1065280",
    "JPM": "19617",
}


def _text(node: ElementTree.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def _parse_entry(entry: ElementTree.Element, *, source: str, fetched_at: datetime) -> dict:
    title = _text(entry.find("atom:title", ATOM_NS))
    link_el = entry.find("atom:link", ATOM_NS)
    url = link_el.get("href", "") if link_el is not None else ""
    updated = _text(entry.find("atom:updated", ATOM_NS))
    summary = _text(entry.find("atom:summary", ATOM_NS))

    published: datetime | None = None
    for raw in (updated,):
        if not raw:
            continue
        try:
            published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
                published = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError, IndexError):
                published = None
    return {
        "title": re.sub(r"\s+", " ", title),
        "url": url,
        "summary": re.sub(r"<[^>]+>", " ", summary)[:600],
        "published": published,
        "source": source,
        "fetched_at": fetched_at,
    }


class EdgarSource:
    """按 ticker 抓取 SEC EDGAR 指定表单类型的公告。"""

    name = "SEC EDGAR"

    def __init__(
        self,
        tickers: tuple[str, ...],
        *,
        forms: tuple[str, ...] = ("8-K",),
        user_agent: str = "USMarketDailyXHS/0.1 (contact@example.com)",
        timeout_seconds: int = 15,
        retries: int = 2,
        max_items: int = 10,
    ) -> None:
        self.tickers = tuple(tickers)
        self.forms = tuple(forms)
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.max_items = max_items
        self.url = EDGAR_BASE

    def _url_for(self, ticker: str, form: str) -> str:
        cik = KNOWN_CIKS.get(ticker.upper(), ticker.upper())
        return (
            f"{EDGAR_BASE}?action=getcompany&CIK={cik}&type={form}"
            f"&dateb=&owner=include&count={self.max_items}&output=atom"
        )

    def fetch(self, *, fetched_at: datetime | None = None) -> SourceResult:
        now = fetched_at or datetime.now(tz=UTC)
        started = datetime.now(tz=UTC)
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}

        items = []
        errors: list[str] = []
        for ticker in self.tickers:
            for form in self.forms:
                url = self._url_for(ticker, form)
                try:
                    raw = fetch_text(
                        url, timeout=self.timeout_seconds, retries=self.retries, headers=headers
                    )
                except HttpError as exc:
                    errors.append(f"{ticker}/{form}: {exc.message}")
                    continue
                try:
                    root = ElementTree.fromstring(raw)
                except ElementTree.ParseError as exc:
                    errors.append(f"{ticker}/{form}: XML 解析失败 {exc}")
                    continue
                for entry in root.findall("atom:entry", ATOM_NS)[: self.max_items]:
                    parsed = _parse_entry(entry, source=self.name, fetched_at=now)
                    if not parsed["url"] or not parsed["title"]:
                        continue
                    items.append(
                        make_item(
                            title=f"[{ticker}] {parsed['title']}",
                            summary=parsed["summary"],
                            url=parsed["url"],
                            source="SEC EDGAR",
                            fetched_at=now,
                            published_at=parsed["published"],
                            trust_level="official",
                        )
                    )

        LOGGER.info("SEC EDGAR 抓取 %d 条", len(items),
                    extra={"stage": "collect", "source": self.name})
        return SourceResult(
            source=self.name,
            url=self.url,
            items=tuple(items),
            error="; ".join(errors) if errors and not items else ("; ".join(errors) or None),
            elapsed_seconds=(datetime.now(tz=UTC) - started).total_seconds(),
        )
