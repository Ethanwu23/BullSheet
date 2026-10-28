"""Markdown 日报渲染。"""

from __future__ import annotations

from usmarket.config import AppConfig
from usmarket.market_data.models import Quote, QuoteSnapshot
from usmarket.validation.schema import DailyContent


def _quote_row(quote: Quote) -> str:
    if quote.is_usable():
        price = f"{quote.price:,.2f}"
        pct = f"{quote.change_percent:+.2f}%"
        prev = f"{quote.previous_close:,.2f}" if quote.previous_close is not None else "—"
    else:
        price = pct = prev = f"数据缺失（{quote.quality.label_zh}）"
    volume = f"{quote.volume:,}" if quote.volume else "—"
    return f"| {quote.display_name} | {quote.symbol} | {price} | {pct} | {prev} | {volume} |"


def render_report(
    content: DailyContent,
    snapshot: QuoteSnapshot,
    cfg: AppConfig,
    *,
    warnings: list[str] | None = None,
) -> str:
    """渲染完整 Markdown 日报。"""
    lines: list[str] = []
    phase_zh = {
        "pre": "盘前", "regular": "盘中", "post": "盘后",
        "closed": "收盘/休市", "unknown": "未知",
    }.get(content.market_phase, content.market_phase)

    lines.append(f"# {content.date} 美股日报（{phase_zh}）")
    lines.append("")
    lines.append(
        f"> 生成方式：`{content.generator}`　|　行情来源：`{snapshot.provider}`　|　"
        f"行情延迟：{'是' if snapshot.is_delayed else '否'}　|　"
        f"交易日历可信度：`{snapshot.calendar_confidence}`"
    )
    if content.low_confidence:
        lines.append("> ⚠️ **低置信度**：可用新闻不足或行情缺失，发布前必须人工复核。")
    lines.append("")

    lines.append("## 一、今日市场概览")
    lines.append("")
    lines.append(content.summary)
    lines.append("")

    if content.evening_summary:
        lines.append("## 盘后总结（可配图直接分享）")
        lines.append("")
        lines.append(content.evening_summary)
        lines.append("")

    lines.append("## 二、三大指数")
    lines.append("")
    lines.append("| 名称 | 代码 | 最新 | 涨跌幅 | 前收 | 成交量 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for quote in snapshot.indices:
        lines.append(_quote_row(quote))
    lines.append("")

    lines.append("## 三、重要新闻")
    lines.append("")
    if content.top_news:
        for i, entry in enumerate(content.top_news, 1):
            published = (
                entry.published_at.strftime("%Y-%m-%d %H:%M UTC")
                if entry.published_at
                else "发布时间未知"
            )
            conf_zh = {"fact": "事实", "analysis": "分析", "speculation": "推测"}.get(
                entry.confidence.value, entry.confidence.value
            )
            tickers = "、".join(entry.tickers) if entry.tickers else "—"
            lines.append(f"### {i}. {entry.headline}")
            lines.append("")
            lines.append(entry.body)
            lines.append("")
            lines.append(
                f"- 涉及标的：{tickers}　|　性质：{conf_zh}　|　发布时间：{published}"
            )
            lines.append(f"- 来源：[{entry.source_title}]({entry.source_url})")
            lines.append("")
    else:
        lines.append("（本次未生成新闻条目）")
        lines.append("")

    lines.append("## 四、重点个股异动")
    lines.append("")
    if content.watchlist_moves:
        lines.append("| 名称 | 代码 | 涨跌幅 | 说明 |")
        lines.append("| --- | --- | --- | --- |")
        for entry in content.watchlist_moves:
            pct = (
                f"{entry.change_percent:+.2f}%"
                if entry.change_percent is not None
                else "数据缺失"
            )
            lines.append(f"| {entry.name} | {entry.symbol} | {pct} | {entry.note} |")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 五、财报与宏观事件")
    lines.append("")
    if content.earnings_and_macro:
        for entry in content.earnings_and_macro:
            link = f"（[来源]({entry.source_url})）" if entry.source_url else ""
            lines.append(f"- **{entry.title}** {link}")
            if entry.detail:
                lines.append(f"  - {entry.detail}")
    else:
        lines.append("（无）")
    lines.append("")

    lines.append("## 六、下一交易日关注")
    lines.append("")
    for item in content.next_session:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 七、风险提示")
    lines.append("")
    for note in content.risk_notes:
        lines.append(f"- {note}")
    lines.append("")

    lines.append("## 八、小红书文案")
    lines.append("")
    lines.append(f"**标题**：{content.xhs.title}")
    lines.append("")
    lines.append("**正文**")
    lines.append("")
    lines.append(content.xhs.body)
    lines.append("")
    lines.append("**话题标签**：" + " ".join(content.xhs.tags))
    lines.append("")

    lines.append("## 九、来源与数据清单")
    lines.append("")
    if content.sources:
        for i, src in enumerate(content.sources, 1):
            published = (
                src.published_at.strftime("%Y-%m-%d %H:%M UTC")
                if src.published_at
                else "发布时间未知"
            )
            lines.append(f"{i}. [{src.title}]({src.url}) — {src.source}（{published}）")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("**行情数据**：")
    lines.append("")
    lines.append(f"- provider: `{snapshot.provider}`")
    lines.append(f"- 快照时间: {snapshot.as_of.isoformat() if snapshot.as_of else '未知'}")
    lines.append(f"- 是否延迟: {'是' if snapshot.is_delayed else '否'}")
    if snapshot.errors:
        lines.append("- 采集异常：")
        for err in snapshot.errors:
            lines.append(f"  - {err}")
    lines.append("")

    if warnings:
        lines.append("## 十、运行告警")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if content.data_notes:
        lines.append("## 十一、数据备注")
        lines.append("")
        for note in content.data_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(content.disclaimer or cfg.content.disclaimer)
    lines.append("")
    return "\n".join(lines)
