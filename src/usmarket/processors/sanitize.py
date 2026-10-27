"""外部内容清洗。

Constitution 原则 V：外部新闻只作为待分析数据，不得改变系统指令或触发代码执行。
因此：剥离 HTML、移除控制字符与零宽字符、限制长度；绝不 eval / exec / 反序列化代码。
"""

from __future__ import annotations

import html
import re

# 控制字符（保留 \n \t）与零宽字符
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028\u2029\ufeff]")
_HTML_TAG_RE = re.compile(r"<[^>]{0,2000}>", re.DOTALL)
_WS_RE = re.compile(r"[ \t ]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")

# 看起来像指令注入的片段：记录但不执行（只做标注，交由上层决定是否丢弃）
_INJECTION_HINTS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "system prompt",
    "you are now",
    "忽略以上",
    "忽略之前的",
    "现在你是",
)


def strip_html(text: str) -> str:
    """剥离 HTML 标签并反转义实体。"""
    if not text:
        return ""
    without_tags = _HTML_TAG_RE.sub(" ", text)
    return html.unescape(without_tags)


def clean_text(text: str, *, max_length: int | None = None) -> str:
    """清洗外部文本：去 HTML、去控制字符、压缩空白。"""
    if not text:
        return ""
    cleaned = strip_html(text)
    cleaned = _CONTROL_RE.sub("", cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    cleaned = _MULTI_NL_RE.sub("\n\n", cleaned)
    cleaned = cleaned.strip()
    if max_length is not None and len(cleaned) > max_length:
        cleaned = cleaned[: max_length - 1].rstrip() + "…"
    return cleaned


def looks_like_injection(text: str) -> bool:
    """检测疑似提示词注入。仅用于标注，不改变系统指令。"""
    lowered = (text or "").lower()
    return any(hint in lowered for hint in _INJECTION_HINTS)


def safe_excerpt(text: str, limit: int = 600) -> str:
    """生成安全摘要：清洗 + 截断。"""
    return clean_text(text, max_length=limit)
