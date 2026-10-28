"""数字可追溯校验。

目标：AI 不得编造行情数字（FR-014 / FR-025）。
两类检查：
1. 结构性数字：index_moves / watchlist_moves 的值必须与 QuoteSnapshot 完全一致；
2. 文本型数字：正文中出现的"疑似行情数字"（小数或百分比）必须能在输入数据
   （行情快照或采集到的新闻原文）中找到出处。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from usmarket.market_data.models import QuoteSnapshot
from usmarket.validation.schema import DailyContent

# 疑似行情数字：带小数点的数字，或带 % 的数字
_DECIMAL_RE = re.compile(r"\d[\d,]*\.\d+")
_PERCENT_RE = re.compile(r"\d[\d,]*\.?\d*\s*%")
_INTEGER_RE = re.compile(r"\b\d+\b")

# 豁免：年份与小整数（日期、条数、序号等不是行情数字）
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_SMALL_INT_MAX = 12

TOLERANCE = 0.005


@dataclass(frozen=True)
class NumberIssue:
    field: str
    value: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.value} — {self.reason}"


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def build_allowed_numbers(
    snapshot: QuoteSnapshot | None, input_texts: list[str]
) -> set[str]:
    """构建允许出现的数字集合（来自真实行情与采集到的新闻原文）。"""
    allowed: set[str] = set()

    if snapshot is not None:
        for quote in snapshot.all_quotes():
            for value in (
                quote.price,
                quote.previous_close,
                quote.change,
                quote.change_percent,
            ):
                if value is None:
                    continue
                allowed.add(_fmt(abs(value)))
                allowed.add(f"{abs(value):.4f}".rstrip("0").rstrip("."))
                allowed.add(str(round(abs(value))))
                allowed.add(f"{abs(value):,.2f}")
            if quote.volume:
                allowed.add(str(quote.volume))
                allowed.add(f"{quote.volume:,}")

    for text in input_texts:
        for match in _DECIMAL_RE.finditer(text):
            allowed.add(match.group(0).replace(",", ""))
        for match in _PERCENT_RE.finditer(text):
            allowed.add(match.group(0).replace(",", "").replace(" ", "").rstrip("%"))
        for match in _INTEGER_RE.finditer(text):
            allowed.add(match.group(0))

    return allowed


def verify_structural_numbers(
    content: DailyContent, snapshot: QuoteSnapshot
) -> list[NumberIssue]:
    """结构性数字必须与行情快照一致。"""
    issues: list[NumberIssue] = []

    for move in content.index_moves:
        quote = snapshot.by_symbol(move.symbol)
        if quote is None:
            issues.append(
                NumberIssue(f"index_moves[{move.symbol}]", move.symbol, "行情快照中不存在该标的")
            )
            continue
        if not quote.is_usable():
            if move.change_percent is not None or move.price is not None:
                issues.append(
                    NumberIssue(
                        f"index_moves[{move.symbol}]",
                        f"price={move.price} pct={move.change_percent}",
                        f"行情不可用时不得给出数字（quality={quote.quality.value}）",
                    )
                )
            continue
        if move.price is not None and quote.price is not None:
            if abs(move.price - quote.price) > TOLERANCE:
                issues.append(
                    NumberIssue(
                        f"index_moves[{move.symbol}].price",
                        str(move.price),
                        f"与行情快照不一致（快照={quote.price}）",
                    )
                )
        if move.change_percent is not None and quote.change_percent is not None:
            if abs(move.change_percent - quote.change_percent) > TOLERANCE:
                issues.append(
                    NumberIssue(
                        f"index_moves[{move.symbol}].change_percent",
                        str(move.change_percent),
                        f"与行情快照不一致（快照={quote.change_percent}）",
                    )
                )

    for move in content.watchlist_moves:
        quote = snapshot.by_symbol(move.symbol)
        if quote is None:
            issues.append(
                NumberIssue(f"watchlist_moves[{move.symbol}]", move.symbol, "行情快照中不存在该标的")
            )
            continue
        if move.change_percent is None:
            continue
        if not quote.is_usable() or quote.change_percent is None:
            issues.append(
                NumberIssue(
                    f"watchlist_moves[{move.symbol}].change_percent",
                    str(move.change_percent),
                    f"行情不可用/缺失时不得给出涨跌幅（quality={quote.quality.value}）",
                )
            )
        elif abs(move.change_percent - quote.change_percent) > TOLERANCE:
            issues.append(
                NumberIssue(
                    f"watchlist_moves[{move.symbol}].change_percent",
                    str(move.change_percent),
                    f"与行情快照不一致（快照={quote.change_percent}）",
                )
            )

    return issues


def _is_exempt(token: str) -> bool:
    if _YEAR_RE.fullmatch(token):
        return True
    try:
        value = int(token.replace(",", ""))
    except ValueError:
        return False
    return value <= _SMALL_INT_MAX


def scan_text_numbers(
    content: DailyContent, allowed: set[str]
) -> list[NumberIssue]:
    """扫描正文中的疑似行情数字，未在输入数据中出现的视为可疑。"""
    issues: list[NumberIssue] = []

    for field_name, text in _iter_text_fields(content):
        for match in _DECIMAL_RE.finditer(text):
            token = match.group(0).replace(",", "")
            if token in allowed or _fmt(float(token)) in allowed:
                continue
            issues.append(
                NumberIssue(field_name, token, "正文中出现的数字在输入数据中找不到出处")
            )
        for match in _PERCENT_RE.finditer(text):
            raw = match.group(0).replace(",", "").replace(" ", "").rstrip("%")
            if raw in allowed or _fmt(float(raw)) in allowed or _is_exempt(raw):
                continue
            issues.append(
                NumberIssue(field_name, f"{raw}%", "正文中出现的百分比在输入数据中找不到出处")
            )
    return issues


def _iter_text_fields(content: DailyContent) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = [
        ("summary", content.summary),
        ("xhs.title", content.xhs.title),
        ("xhs.body", content.xhs.body),
        ("evening_summary", content.evening_summary),
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
    for i, note in enumerate(content.next_session):
        fields.append((f"next_session[{i}]", note))
    return [(name, text) for name, text in fields if text]


def validate_numbers(
    content: DailyContent, snapshot: QuoteSnapshot | None, *, input_texts: list[str]
) -> list[NumberIssue]:
    """完整数字校验。返回空列表表示通过。"""
    issues: list[NumberIssue] = []
    if snapshot is not None:
        issues += verify_structural_numbers(content, snapshot)
    issues += scan_text_numbers(content, build_allowed_numbers(snapshot, input_texts))
    return issues
