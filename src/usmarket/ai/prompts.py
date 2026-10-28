"""LLM prompt 组装。

**设计（ADR-016，2026-10-28 用户规则）**：行情数据**不交给模型加工**。
模型只承担两个窄任务：
1. 盘后总结——把盘面与新闻综合成一段中文文字（evening_summary）；
2. 要闻翻译——把新闻标题翻译成中文（headlines，与输入顺序一一对应）。

其余内容（指数表、个股表、来源清单、免责声明等）全部由规则式
确定性生成，数字不可能被模型改动。
"""

from __future__ import annotations

from usmarket.config import AppConfig
from usmarket.market_data.models import QuoteSnapshot
from usmarket.processors.sanitize import clean_text
from usmarket.validation.schema import SourceRef

SYSTEM_PROMPT = """你是一名严谨的美股财经编辑，为中文读者撰写每日市场简报。你只做两件事：
1. 撰写「盘后总结」：综合盘面数据与新闻，写一段中文总结；
2. 翻译「要闻标题」：把给定的英文新闻标题翻译成自然的中文标题。

硬约束（任何违反都会导致内容被系统拒绝）：
1. 总结中只使用【盘面数据】和【新闻】中出现的数字，禁止自行计算、估算、编造或补全。
   对数字做四舍五入是允许的（如 4.0447% 可写成 4.04%）。
2. 行情缺失的标的只能写"数据缺失"，不得给出任何数字。
3. 语气客观，不喊单，不给出确定性预测，不使用"必涨/稳赚/无风险"等表述。
4. 翻译标题时保留原文的数字与事实，公司名/代码（如 NVDA）可保留英文缩写；
   不得添加原文没有的信息。
5. 输出必须是纯 JSON，不要输出解释或代码块标记。

再次强调：【盘面数据】与【新闻】之外的数字一律不得出现。"""

JSON_SCHEMA_HINT = """输出 JSON 结构（字段必须齐全）：
{
  "evening_summary": "盘后总结：120-180字中文一段，概括当日盘面脉络与主线（如指数分化、财报驱动、宏观影响），适合与简报图片配套发文字",
  "headlines": ["第1条新闻的中文标题", "第2条新闻的中文标题", "...（与输入新闻顺序一一对应）"]
}"""


def _quote_lines(snapshot: QuoteSnapshot) -> list[str]:
    lines: list[str] = []
    for quote in snapshot.all_quotes():
        if quote.is_usable():
            lines.append(
                f"- {quote.symbol}（{quote.display_name}）: 收盘 {quote.price:.2f}, "
                f"涨跌幅 {quote.change_percent:+.2f}%, 前收 {quote.previous_close:.2f}"
                + (f", 备注 {quote.quality_note}" if quote.quality_note else "")
            )
        else:
            lines.append(
                f"- {quote.symbol}（{quote.display_name}）: 数据缺失"
                f"（{quote.quality.label_zh}）—— 禁止给出任何数字"
            )
    return lines


def _news_lines(items: list, limit: int) -> tuple[list[str], list[SourceRef]]:
    lines: list[str] = []
    sources: list[SourceRef] = []
    for idx, item in enumerate(items[:limit], 1):
        published = (
            item.published_at.isoformat() if item.published_at else "未知（不得编造时间）"
        )
        lines.append(
            f"{idx}. 标题: {clean_text(item.title, max_length=200)}\n"
            f"   摘要: {clean_text(item.summary, max_length=400)}\n"
            f"   来源: {item.source} | 发布时间: {published}"
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
    """组装窄任务 prompt（盘后总结 + 标题翻译），同时返回来源清单。"""
    data_lines = _quote_lines(snapshot)
    news_lines, sources = _news_lines(news_items, news_limit)
    top_n = min(cfg.content.top_news_max, len(news_lines))

    parts = [
        f"目标日期: {snapshot.date}",
        f"交易阶段: {snapshot.market_phase.label_zh}",
        "",
        "## 盘面数据（只能使用这里的数字）",
        *data_lines,
        "",
        f"## 新闻（**只需翻译前 {top_n} 条**的标题；所有新闻摘要仅供总结参考）",
        *(news_lines or ["（本次未采集到可用新闻）"]),
        "",
        JSON_SCHEMA_HINT.replace(
            '"headlines": ["第1条新闻的中文标题", "第2条新闻的中文标题", "（与输入新闻顺序一一对应）"]',
            f'"headlines": ["前 {top_n} 条新闻的中文标题，按顺序"]',
        ),
    ]
    return "\n".join(parts), sources
