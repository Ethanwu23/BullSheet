"""规则式兜底生成器（无需 API key）。

设计约束（Constitution 原则 I + FR-026）：
- 只复用 QuoteSnapshot 与 NewsItem 中**已核实**的数字；
- 不做任何推测、不补全缺失行情、不给预测；
- 产物标记 generator=rule_based，需人工复核后才可发布。

说明：本生成器不做英文→中文的机器翻译（无 LLM 时无法保证质量），
新闻标题保留原文并加中文类别前缀，以保证可追溯、不误译。
"""

from __future__ import annotations

import logging
from datetime import datetime

from usmarket.config import AppConfig
from usmarket.market_data.models import QuoteSnapshot
from usmarket.processors.sanitize import clean_text
from usmarket.validation.schema import (
    Confidence,
    DailyContent,
    EventEntry,
    IndexMove,
    MoveEntry,
    NewsEntry,
    SourceRef,
    XhsContent,
)

LOGGER = logging.getLogger(__name__)

CATEGORY_ZH = {
    "macro": "宏观",
    "earnings": "财报",
    "company": "公司动态",
    "market_move": "市场异动",
    "other": "要闻",
}


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.fromisoformat(date_str).strftime("%Y年%m月%d日")
    except ValueError:
        return date_str


def _index_summary_line(quote) -> str:
    if quote.is_usable() and quote.change_percent is not None:
        trend = "上涨" if quote.change_percent > 0 else ("下跌" if quote.change_percent < 0 else "持平")
        return f"{quote.display_name}收于 {quote.price:.2f} 点，{trend} {abs(quote.change_percent):.2f}%"
    return f"{quote.display_name}行情缺失（{quote.quality.label_zh}），本条不提供数字"


def generate_content(
    cfg: AppConfig,
    snapshot: QuoteSnapshot,
    news_items: list,
    *,
    sources: list[SourceRef] | None = None,
    now: datetime | None = None,
) -> DailyContent:
    """基于真实数据生成结构化内容。"""
    date_str = snapshot.date or (now or datetime.now()).date().isoformat()

    # ---- 指数 ----
    index_moves: list[IndexMove] = []
    for quote in snapshot.indices:
        index_moves.append(
            IndexMove(
                symbol=quote.symbol,
                name=quote.display_name,
                price=quote.price if quote.is_usable() else None,
                change_percent=quote.change_percent if quote.is_usable() else None,
                source_ref=f"quote:{quote.symbol}",
            )
        )

    # ---- 要闻 ----
    top_news: list[NewsEntry] = []
    for item in news_items[: cfg.content.top_news_max]:
        top_news.append(
            NewsEntry(
                headline=f"【{CATEGORY_ZH.get(item.category.value, '要闻')}】"
                + clean_text(item.title, max_length=120),
                body=(clean_text(item.summary, max_length=220) or "（源未提供摘要）"),
                tickers=list(item.tickers),
                source_title=item.source,
                source_url=item.url,
                published_at=item.published_at,
                confidence=(
                    Confidence.FACT if item.published_at else Confidence.ANALYSIS
                ),
            )
        )

    # ---- 异动 ----
    # 相对强弱只做定性描述：任何"计算出来的数字"都会被视为无出处而被校验拦截
    index_changes = [
        q.change_percent
        for q in snapshot.indices
        if q.is_usable() and q.change_percent is not None
    ]
    index_avg = sum(index_changes) / len(index_changes) if index_changes else None

    def relative_note(pct: float | None) -> str:
        if pct is None or index_avg is None:
            return ""
        diff = pct - index_avg
        if diff > 1:
            return "明显强于大盘"
        if diff > 0:
            return "略强于大盘"
        if diff > -1:
            return "略弱于大盘"
        return "明显弱于大盘"

    watchlist_moves: list[MoveEntry] = []
    for quote in sorted(
        snapshot.stocks,
        key=lambda q: (q.change_percent is None, -abs(q.change_percent or 0)),
    ):
        if not quote.is_usable() or quote.change_percent is None:
            watchlist_moves.append(
                MoveEntry(
                    symbol=quote.symbol,
                    name=quote.display_name,
                    change_percent=None,
                    note=f"{quote.display_name}行情缺失（{quote.quality.label_zh}），不提供涨跌幅",
                    confidence=Confidence.ANALYSIS,
                    source_ref=f"quote:{quote.symbol}",
                )
            )
            continue
        watchlist_moves.append(
            MoveEntry(
                symbol=quote.symbol,
                name=quote.display_name,
                change_percent=quote.change_percent,
                # 卡片右侧已显示代码与涨跌幅，此处不再重复数字
                note=relative_note(quote.change_percent),
                confidence=Confidence.ANALYSIS,
                source_ref=f"quote:{quote.symbol}",
            )
        )
    watchlist_moves = watchlist_moves[:8]

    # ---- 财报/宏观（来自新闻分类）----
    events: list[EventEntry] = []
    for item in news_items:
        if item.category.value in {"earnings", "macro"}:
            events.append(
                EventEntry(
                    title=clean_text(item.title, max_length=120),
                    detail=f"来源：{item.source}",
                    tickers=list(item.tickers),
                    confidence=Confidence.FACT if item.published_at else Confidence.ANALYSIS,
                    source_url=item.url,
                    published_at=item.published_at,
                )
            )
        if len(events) >= 4:
            break

    # ---- 概览 ----
    index_lines = [_index_summary_line(q) for q in snapshot.indices]
    summary = (
        f"{_fmt_date(date_str)}美股{ {'pre': '盘前', 'regular': '盘中', 'post': '盘后', 'closed': '收盘', 'unknown': ''}.get(snapshot.market_phase.value, '')}概览："
        + "；".join(index_lines)
        + "。"
    )
    if not snapshot.has_any_data():
        summary += "注意：本次未获取到可用行情数据，以下内容不含行情数字。"

    # ---- 小红书文案 ----
    usable_indices = [
        q for q in snapshot.indices if q.is_usable() and q.change_percent is not None
    ]
    phase_zh = {"pre": "盘前", "regular": "盘中", "post": "盘后", "closed": "收盘"}.get(
        snapshot.market_phase.value, "复盘"
    )
    if usable_indices:
        best = max(usable_indices, key=lambda q: abs(q.change_percent or 0))
        xhs_title = (
            f"美股{phase_zh}｜{best.display_name}{best.change_percent:+.2f}%，"
            f"{len(top_news)}条要闻速览"
        )
    else:
        xhs_title = f"美股{phase_zh}｜行情数据缺失，仅呈现已核实新闻"
    body_parts = [f"📊 {_fmt_date(date_str)} 美股复盘", ""]
    body_parts.append("【三大指数】")
    for line in index_lines:
        body_parts.append(f"· {line}")
    if top_news:
        body_parts.append("")
        body_parts.append("【今日要闻】")
        for i, entry in enumerate(top_news, 1):
            body_parts.append(f"{i}. {entry.headline}")
    if watchlist_moves:
        body_parts.append("")
        body_parts.append("【重点个股】")
        for entry in watchlist_moves:
            body_parts.append(f"· {entry.note}")
    body_parts.append("")
    body_parts.append("【风险提示】")
    body_parts.append(cfg.content.disclaimer)
    xhs_body = "\n".join(body_parts)

    content = DailyContent(
        date=date_str,
        market_phase=snapshot.market_phase.value,
        generator="rule_based",
        summary=summary,
        index_moves=index_moves,
        top_news=top_news,
        watchlist_moves=watchlist_moves,
        earnings_and_macro=events,
        next_session=["关注下一交易日盘前公布的宏观数据与公司公告（以官方渠道为准）"],
        risk_notes=[cfg.content.disclaimer, "行情数据可能存在延迟，请以交易所与官方渠道为准"],
        xhs=XhsContent(
            title=xhs_title[: cfg.content.title_max_chars],
            body=xhs_body[: cfg.content.body_max_chars],
            tags=list(cfg.content.tags[: cfg.content.max_tags]),
        ),
        sources=sources or [],
        disclaimer=cfg.content.disclaimer,
        low_confidence=len(top_news) < cfg.content.top_news_min or not snapshot.has_any_data(),
        data_notes=list(snapshot.errors),
    )
    LOGGER.info("规则式生成完成（无 LLM）：要闻 %d 条", len(content.top_news),
                extra={"stage": "generate"})
    return content
