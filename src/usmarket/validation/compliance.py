"""合规校验：禁用表述、虚假紧迫感、无证据的确定性预测。

FR-022 / FR-023：不得夸大收益、不得制造虚假紧迫感、不得输出无证据支持的
确定性股价预测、不得伪造引用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from usmarket.validation.schema import DailyContent

# 保证收益 / 夸大类
BANNED_PHRASES = (
    "稳赚", "必赚", "包赚", "保证获利", " guaranteed profit", "保证收益",
    "无风险", "零风险", "100%赚钱", "躺赚", "稳赢", "必涨", "一定涨",
    "翻倍", "暴富", "财富自由", "跟着买就赚", "包你赚", "稳赚不赔",
)

# 虚假紧迫感
URGENCY_PATTERNS = (
    r"最后机会", r"错过就没了", r"马上上车", r"再不买就来不及", r"限时",
    r"只剩最后\d+", r"紧急通知", r"act now", r"last chance",
)

# 无证据的确定性预测
CERTAINTY_PATTERNS = (
    r"一定(会|能)?(涨|跌|上涨|下跌)",
    r"必然(上涨|下跌|大涨|暴跌)",
    r"肯定会(涨|跌)",
    r"目标价\s*\$?\d",
    r"will definitely (rise|fall|jump|surge)",
    r"guaranteed to (rise|fall)",
)

# 投资建议式指令
ADVICE_PATTERNS = (
    r"建议(全仓|满仓|重仓)",
    r"(全仓|满仓|梭哈)(买入|杀入|进场)",
    r"必须买入", r"赶紧买入", r"立即买入",
    r"buy now", r"must buy",
)


@dataclass(frozen=True)
class ComplianceIssue:
    field: str
    matched: str
    rule: str

    def __str__(self) -> str:
        return f"{self.field}: 命中「{self.matched}」（{self.rule}）"


def _scan(text: str, patterns: tuple[str, ...], rule: str, field: str) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            issues.append(ComplianceIssue(field, match.group(0), rule))
    return issues


def validate_compliance(content: DailyContent) -> list[ComplianceIssue]:
    """合规校验。返回空列表表示通过。"""
    issues: list[ComplianceIssue] = []

    for field_name, text in _iter_fields(content):
        for phrase in BANNED_PHRASES:
            if phrase.lower() in text.lower():
                issues.append(ComplianceIssue(field_name, phrase, "禁止的收益承诺/夸大表述"))
        issues += _scan(text, URGENCY_PATTERNS, "禁止制造虚假紧迫感", field_name)
        issues += _scan(text, ADVICE_PATTERNS, "禁止指令式买卖建议", field_name)
        # 确定性预测**无论 confidence 为何值**都禁止：
        # speculation 只允许"可能/若…则…"式的模糊表述，不允许"一定会"。
        issues += _scan(
            text, CERTAINTY_PATTERNS, "禁止无证据支持的确定性预测", field_name
        )

    return issues


def _iter_fields(content: DailyContent) -> list[tuple[str, str]]:
    fields = [
        ("summary", content.summary),
        ("xhs.title", content.xhs.title),
        ("xhs.body", content.xhs.body),
    ]
    for i, entry in enumerate(content.top_news):
        fields.append((f"top_news[{i}].headline", entry.headline))
        fields.append((f"top_news[{i}].body", entry.body))
    for i, entry in enumerate(content.watchlist_moves):
        fields.append((f"watchlist_moves[{i}].note", entry.note))
    for i, entry in enumerate(content.earnings_and_macro):
        fields.append((f"earnings_and_macro[{i}].title", entry.title))
        fields.append((f"earnings_and_macro[{i}].detail", entry.detail))
    for i, note in enumerate(content.risk_notes):
        fields.append((f"risk_notes[{i}]", note))
    for i, tag in enumerate(content.xhs.tags):
        fields.append((f"xhs.tags[{i}]", tag))
    return [(name, text) for name, text in fields if text]
