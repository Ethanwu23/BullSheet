"""来源与数据清单：记录数据源、使用限制、配额与许可说明（FR-010）。"""

from __future__ import annotations

from usmarket.collectors.models import SourceResult
from usmarket.config import AppConfig
from usmarket.market_data.models import QuoteSnapshot

# 数据源条款与使用限制（依据 docs/research.md 实测结论）
SOURCE_NOTES: dict[str, str] = {
    "Yahoo Finance (chart API)": (
        "非公开接口（query1.finance.yahoo.com/v8/finance/chart），无 SLA、可能限流或变更；"
        "返回值为延迟行情，不得标注为实时。商用前请自行评估 Yahoo 服务条款。"
    ),
    "Finnhub": "免费档 60 次/分钟；不支持原始指数代码（^GSPC/^IXIC/^DJI），需改用 ETF。",
    "Google News RSS": "公开 RSS；内容为第三方媒体版权所有，仅引用标题与摘要并保留原链接。",
    "CNBC RSS": "公开 RSS；同上，仅做标题/摘要引用。",
    "MarketWatch RSS": "Dow Jones 公开 RSS；仅做标题/摘要引用。",
    "Federal Reserve RSS": "官方公开新闻稿，可自由引用，须注明来源。",
    "Investing.com RSS": "公开 RSS；仅做标题/摘要引用。",
    "SEC EDGAR": (
        "公共数据；SEC 要求声明式 User-Agent（应用名/版本 + 联系邮箱），"
        "否则返回 403。请求频率限制 10 次/秒。"
    ),
    "fixture": "离线样本数据，仅用于测试，不代表真实市场。",
}


def render_sources_doc(
    cfg: AppConfig,
    snapshot: QuoteSnapshot,
    results: list[SourceResult],
) -> str:
    lines: list[str] = []
    lines.append(f"# 来源与数据清单 — {snapshot.date}")
    lines.append("")
    lines.append("## 一、行情数据源")
    lines.append("")
    lines.append("| 标的 | 代码 | 最新 | 涨跌幅 | 时间(UTC) | 阶段 | 质量 | provider |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for quote in snapshot.all_quotes():
        price = f"{quote.price:,.2f}" if quote.price is not None else "数据缺失"
        pct = (
            f"{quote.change_percent:+.2f}%"
            if quote.change_percent is not None
            else "数据缺失"
        )
        as_of = quote.as_of.strftime("%Y-%m-%d %H:%M") if quote.as_of else "未知"
        lines.append(
            f"| {quote.display_name} | {quote.symbol} | {price} | {pct} | {as_of} | "
            f"{quote.market_phase.label_zh} | {quote.quality.label_zh} | {quote.provider} |"
        )
    lines.append("")
    lines.append(f"- 快照时间：{snapshot.as_of.isoformat() if snapshot.as_of else '未知'}")
    lines.append(f"- 是否延迟行情：{'是（不得标注为实时）' if snapshot.is_delayed else '否'}")
    lines.append(f"- 交易日历可信度：{snapshot.calendar_confidence}")
    if snapshot.errors:
        lines.append("- 采集异常：")
        for err in snapshot.errors:
            lines.append(f"  - {err}")
    lines.append("")

    lines.append("## 二、新闻来源")
    lines.append("")
    lines.append("| 来源 | 状态 | 条数 | 耗时(s) | 说明 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in results:
        status = "成功" if r.ok else "失败"
        lines.append(
            f"| {r.source} | {status} | {len(r.items)} | {r.elapsed_seconds:.2f} | "
            f"{r.error or ''} |"
        )
    lines.append("")

    lines.append("## 三、数据源条款与使用限制")
    lines.append("")
    for name, note in SOURCE_NOTES.items():
        lines.append(f"- **{name}**：{note}")
    lines.append("")
    lines.append(
        "- **通用**：所有新闻内容版权归原媒体所有，本项目仅引用标题与摘要并保留原始链接，"
        "不做全文转载。"
    )
    lines.append("")
    return "\n".join(lines)
