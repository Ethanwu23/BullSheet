"""图片渲染前的文本清洗。

LLM 生成的小红书文案常常包含 emoji 与 Markdown 标记（实测 qwen3.8-flash 会输出
"📉 **科技股惨案**" 这类内容）。这些字符在中文正文字体（微软雅黑 / Noto Sans SC）
中通常没有字形，直接绘制会得到空白或"豆腐块"，而 Markdown 的 `**` 会原样显示。

因此：
1. emoji 按映射替换为等价中文，无法映射的直接移除；
2. Markdown 强调与列表标记移除（**话题标签** #美股 不带空格，不会被误删）；
3. 只影响图片文本，content.json 与人工复制发布的正文保持原样。
"""

from __future__ import annotations

import logging
import re

LOGGER = logging.getLogger(__name__)

# emoji 处理：涨跌类 emoji 直接丢弃（数字本身带正负号，替换成文字会破坏中文语序，
# 例如 "📉美股复盘" 会变成 "跌美股复盘"）；带语义的警示类保留为中文。
EMOJI_MAP: dict[str, str] = {
    "\U0001f4c9": "",        # 📉
    "\U0001f4c8": "",        # 📈
    "\U0001f680": "",        # 🚀
    "\U0001f525": "",        # 🔥
    "⚠️": "注意：",           # ⚠️（带变体选择符）
    "⚠": "注意：",            # ⚠
    "\U0001f534": "",       # 🔴
    "\U0001f7e2": "",       # 🟢
    "\U0001f4b0": "",       # 💰
    "\U0001f4ca": "",       # 📊
    "\U0001f4f0": "",       # 📰
    "\U0001f4bb": "",       # 💻
    "\U0001f697": "",       # 🚗
    "\U0001f4b5": "",       # 💵
    "\U0001f4c5": "",       # 📅
    "✅": "",
    "❌": "",
    "❗": "！",
    "‼️": "！",
}

# Markdown：加粗/斜体/行内代码/标题/列表符号
_MARKDOWN_RE = re.compile(r"\*\*|__|`|^#{1,6}\s+|^\s*[-*+]\s+", re.MULTILINE)

# 无法映射的符号与 emoji 范围（含变体选择符、ZWJ、键帽、旗帜、箭头、杂项符号）
_SYMBOL_RANGES = (
    "\U0001f000-\U0001faff",  # emoji 主体
    "\U0001f1e6-\U0001f1ff",  # 区域指示符（国旗）
    "☀-➿",            # 杂项符号与装饰符号 U+2600–U+27BF
    "⬀-⬿",            # U+2B00–U+2BFF
    "←-⇿",            # 箭头 U+2190–U+21FF
    "︀-️",            # 变体选择符 U+FE00–U+FE0F
    "⃐-⃿",            # 组合符号 U+20D0–U+20FF
    "️⃣",             # 键帽 U+20E3
    "\u200d",                # ZWJ
)
_SYMBOL_RE = re.compile(f"[{''.join(_SYMBOL_RANGES)}]")

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")


def strip_unsupported(text: str) -> tuple[str, int]:
    """移除 emoji / Markdown 标记 / 零宽字符。返回 (清洗后文本, 移除的符号数)。"""
    if not text:
        return text, 0

    removed = 0
    result = text
    for src, dst in EMOJI_MAP.items():
        if src in result:
            removed += result.count(src)
            result = result.replace(src, dst)

    before = len(result)
    result = _SYMBOL_RE.sub("", result)
    removed += before - len(result)

    result = _ZERO_WIDTH_RE.sub("", result)
    result = _MARKDOWN_RE.sub("", result)
    # 清理因移除符号产生的多余空格（保留换行）
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r"[ \t]+\n", "\n", result)
    return result, removed


def sanitize_content_for_image(content):  # noqa: ANN001 - DailyContent，避免循环导入
    """返回一份"图片安全"的内容副本（不修改原对象）。

    原对象保留 emoji 与 Markdown，用于 content.json 和人工复制发布。
    """
    cleaned = content.model_copy(deep=True)
    removed_total = 0

    def fix(obj: object, attr: str) -> None:
        nonlocal removed_total
        value = getattr(obj, attr, None)
        if isinstance(value, str):
            new_value, removed = strip_unsupported(value)
            removed_total += removed
            setattr(obj, attr, new_value)

    for attr in ("summary", "disclaimer"):
        fix(cleaned, attr)

    for entry in list(cleaned.top_news):
        for attr in ("headline", "body"):
            fix(entry, attr)
    for entry in list(cleaned.watchlist_moves):
        for attr in ("note",):
            fix(entry, attr)
    for entry in list(cleaned.earnings_and_macro):
        for attr in ("title", "detail"):
            fix(entry, attr)
    for entry in list(cleaned.sources):
        for attr in ("title",):
            fix(entry, attr)

    cleaned.next_session = [strip_unsupported(x)[0] for x in cleaned.next_session]
    cleaned.risk_notes = [strip_unsupported(x)[0] for x in cleaned.risk_notes]
    cleaned.data_notes = [strip_unsupported(x)[0] for x in cleaned.data_notes]

    xhs = cleaned.xhs
    xhs.title, r1 = strip_unsupported(xhs.title)
    xhs.body, r2 = strip_unsupported(xhs.body)
    removed_total += r1 + r2

    if removed_total:
        LOGGER.info(
            "已从图片文本中移除 %d 个 emoji/符号或 Markdown 标记（正文原样保留）",
            removed_total,
            extra={"stage": "render"},
        )
    return cleaned
