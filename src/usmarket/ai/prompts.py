"""Prompt 组装。

关键约束：行情数字由本模块以"允许引用的数字清单"形式注入，
模型只能从中选择，不得自行计算或编造（Constitution 原则 I）。
"""

from __future__ import annotations

from usmarket.config import AppConfig
from usmarket.market_data.models import QuoteSnapshot
from usmarket.processors.sanitize import clean_text
from usmarket.validation.schema import SourceRef

SYSTEM_PROMPT = """你是一名严谨的美股财经编辑，为中文读者撰写小红书风格的每日市场复盘。

硬约束（任何违反都会导致内容被系统拒绝）：
1. 只使用【可引用数据】中提供的数字，禁止自行计算、估算、编造或补全任何行情数字。
2. 行情缺失的标的，只能写"数据缺失"，不得给出任何数字。
3. 事实、分析、推测必须区分：confidence 字段取 fact / analysis / speculation。
4. 不得使用保证获利、稳赚、无风险、必涨等表述；不得给出确定性的股价或点位预测。
5. 不得制造虚假紧迫感，不得给出指令式买卖建议。
6. 每条重要新闻必须提供原始链接（source_url）与来源名称（source_title）。
7. 不得伪造引用、新闻来源、财报数字或专家观点。
8. 输出必须是纯 JSON，且符合给定的字段结构，不要输出解释或代码块标记。
9. 中文表达自然简洁，适合手机阅读，避免机械翻译腔。
10. top_news 的 headline 必须是**中文标题**（公司名/代码如 NVDA 可保留英文缩写），不得直接照抄英文原文。
11. watchlist_moves **只能包含【可引用数据】中列出的个股**（美股七姐妹 + SPCX），不得添加其他任何股票；顺序按涨跌幅绝对值从大到小。

再次强调：【可引用数据】之外的数字一律不得出现。"""

JSON_SCHEMA_HINT = """输出 JSON 结构（字段必须齐全）：
{
  "date": "YYYY-MM-DD",
  "market_phase": "closed",
  "summary": "今日市场概览，3-5 句中文",
  "index_moves": [
    {"symbol": "^GSPC", "name": "标普500", "price": 6791.5, "change_percent": -0.86, "source_ref": "quote:^GSPC"}
  ],
  "top_news": [
    {"headline": "中文标题", "body": "中文解读，1-3 句", "tickers": ["NVDA"],
     "source_title": "媒体名", "source_url": "https://原始链接",
     "published_at": "2026-10-24T13:05:00Z", "confidence": "fact"}
  ],
  "watchlist_moves": [
    {"symbol": "NVDA", "name": "英伟达", "change_percent": 2.15,
     "note": "中文解读", "confidence": "analysis", "source_ref": "quote:NVDA"}
  ],
  "earnings_and_macro": [
    {"title": "事件标题", "detail": "中文说明", "tickers": [], "confidence": "fact",
     "source_url": "https://原始链接", "published_at": "2026-10-24T13:05:00Z"}
  ],
  "next_session": ["下一交易日值得关注的事件（中文，不带数字预测）"],
  "risk_notes": ["风险提示（中文）"],
  "xhs": {"title": "小红书标题，不超过 30 字", "body": "小红书正文", "tags": ["#美股"]},
  "evening_summary": "盘后总结：120-180字中文一段，概括当日盘面脉络与主线（如科技股分化、财报驱动、宏观影响），只引用【可引用数据】中的数字，语气客观，适合与简报图片配套发文字，不要喊单、不要预测",
  "sources": [
    {"title": "新闻标题", "url": "https://原始链接", "source": "媒体名", "published_at": "2026-10-24T13:05:00Z"}
  ],
  "disclaimer": "风险提示原文"
}

字段数量要求：top_news 3-5 条；watchlist_moves 0-6 条；next_session 1-4 条；risk_notes 1-3 条。"""


def _quote_lines(snapshot: QuoteSnapshot) -> list[str]:
    lines: list[str] = []
    for quote in snapshot.all_quotes():
        if quote.is_usable():
            lines.append(
                f"- {quote.symbol}（{quote.display_name}）: 现价 {quote.price:.2f}, "
                f"涨跌幅 {quote.change_percent:+.2f}%, 前收 {quote.previous_close:.2f}, "
                f"时间 {quote.as_of.isoformat() if quote.as_of else '未知'}, "
                f"阶段 {quote.market_phase.label_zh}, 延迟={quote.is_delayed}"
                + (f", 备注 {quote.quality_note}" if quote.quality_note else "")
            )
        else:
            lines.append(
                f"- {quote.symbol}（{quote.display_name}）: 数据缺失"
                f"（{quote.quality.label_zh}"
                + (f": {quote.quality_note}" if quote.quality_note else "")
                + "）—— 禁止给出任何数字"
            )
    return lines


def _news_lines(items: list, limit: int) -> tuple[list[str], list[SourceRef]]:
    lines: list[str] = []
    sources: list[SourceRef] = []
    for item in items[:limit]:
        published = (
            item.published_at.isoformat() if item.published_at else "未知（不得编造时间）"
        )
        lines.append(
            f"- 标题: {clean_text(item.title, max_length=200)}\n"
            f"  摘要: {clean_text(item.summary, max_length=400)}\n"
            f"  来源: {item.source} | 可信度: {item.trust_level.value} | "
            f"发布时间: {published} | 链接: {item.url}"
        )
        sources.append(
            SourceRef(
                title=clean_text(item.title, max_length=200),
                url=item.url,
                source=item.source,
                published_at=item.published_at,
            )
        )
    return lines, sources


def build_user_prompt(
    cfg: AppConfig,
    snapshot: QuoteSnapshot,
    news_items: list,
    *,
    news_limit: int = 25,
) -> tuple[str, list[SourceRef]]:
    """组装 user prompt，同时返回允许引用的来源清单。"""
    data_lines = _quote_lines(snapshot)
    news_lines, sources = _news_lines(news_items, news_limit)

    parts = [
        f"目标日期: {snapshot.date}",
        f"交易阶段: {snapshot.market_phase.label_zh}",
        f"行情来源: {snapshot.provider}（{'延迟行情' if snapshot.is_delayed else '实时'}）",
        "",
        "## 可引用数据（只能使用这里的数字）",
        *data_lines,
        "",
        "## 可引用新闻（只能使用这里的链接与事实）",
        *(news_lines or ["（本次未采集到可用新闻）"]),
        "",
        f"## 免责声明原文（必须原样放入 disclaimer 字段）\n{cfg.content.disclaimer}",
        "",
        f"## 标签候选（可从中挑选，最多 {cfg.content.max_tags} 个）\n"
        + " ".join(cfg.content.tags),
        "",
        f"## 字数限制\n正文不超过 {cfg.content.body_max_chars} 字；标题不超过 "
        f"{cfg.content.title_max_chars} 字。",
        "",
        JSON_SCHEMA_HINT,
    ]
    return "\n".join(parts), sources
