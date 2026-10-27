"""文本排版：中英混排换行、截断、溢出检测。

目标：竖屏卡片中不出现文字溢出画布或明显截断错误（FR-029 / FR-030）。
"""

from __future__ import annotations

from PIL import ImageDraw, ImageFont

# CJK 及全角标点可任意断行
_CJK_RANGES = (
    (0x1100, 0x11FF),   # 韩文
    (0x2E80, 0x303F),   # CJK 符号与标点
    (0x3040, 0x30FF),   # 日文假名
    (0x3400, 0x4DBF),   # CJK 扩展 A
    (0x4E00, 0x9FFF),   # CJK 基本区
    (0xA000, 0xA4CF),   # 彝文
    (0xAC00, 0xD7A3),   # 韩文音节
    (0xF900, 0xFAFF),   # 兼容表意文字
    (0xFE30, 0xFE4F),   # CJK 兼容形式
    (0xFF00, 0xFF60),   # 全角形式
    (0xFFE0, 0xFFE6),
    (0x20000, 0x2A6DF),  # CJK 扩展 B
)

# 行首禁止出现的标点
_NO_LINE_START = "。，、；：）】》」』！？%‰℃…·”’"
# 行尾禁止出现的标点
_NO_LINE_END = "（【《「『“‘"


def is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def _is_ascii_alnum(ch: str) -> bool:
    """仅把 ASCII 数字/字母视为"词内字符"。

    注意：str.isalnum() 对中文字符也返回 True，直接使用会把所有中文断行点判为
    不可断，导致每行都在最后一个字符处硬切（历史上出现过 "标普5" / "00" 的断字）。
    """
    return ch.isascii() and ch.isalnum()


def can_break_before(text: str, index: int) -> bool:
    """是否可在 index 处断行（index 为下一行首字符下标）。"""
    if index <= 0 or index >= len(text):
        return False
    ch = text[index]
    if ch in _NO_LINE_START:
        return False
    prev = text[index - 1]
    if prev in _NO_LINE_END:
        return False
    if ch.isspace() or prev == " ":
        return True

    # 数字/英文词内部不断行（如 500、3nm 中的字符之间）
    if _is_ascii_alnum(ch) and _is_ascii_alnum(prev):
        return False
    # 「中文 + 数字/字母」不断行（如 标普500、英伟达3nm）
    if is_cjk(prev) and _is_ascii_alnum(ch):
        return False
    # 「数字/字母 + 中文量词」不断行（如 2027年、500点、1%）
    if is_cjk(ch) and _is_ascii_alnum(prev):
        return False

    if is_cjk(ch) and is_cjk(prev):
        return True
    # 中文紧跟在拉丁词/标点后 → 可断
    if is_cjk(ch):
        return True
    # 拉丁文本：仅在已有空格处断行
    return False


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    if not text:
        return 0.0
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return float(right - left)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    *,
    max_lines: int | None = None,
) -> list[str]:
    """按像素宽度换行，支持中英混排。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []

    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        i = 0
        while i < len(paragraph):
            ch = paragraph[i]
            candidate = current + ch
            if current and text_width(draw, candidate, font) > max_width:
                # 回溯寻找合适的断点：从倒数第二个字符开始（current 本身必然放得下）
                break_at = len(candidate) - 1
                for j in range(len(candidate) - 1, 0, -1):
                    if can_break_before(candidate, j):
                        break_at = j
                        break
                lines.append(candidate[:break_at].rstrip())
                current = candidate[break_at:].lstrip()
                if max_lines and len(lines) >= max_lines:
                    break
            else:
                current = candidate
            i += 1
        if current:
            lines.append(current.rstrip())
        if max_lines and len(lines) >= max_lines:
            break

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate_to_width(draw, lines[-1], font, max_width)
    return lines


def truncate_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    *,
    ellipsis: str = "…",
) -> str:
    """单行截断并加省略号。"""
    if text_width(draw, text, font) <= max_width:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if text_width(draw, text[:mid] + ellipsis, font) <= max_width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + ellipsis


def fit_font_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    max_width: float,
    *,
    start_size: int,
    min_size: int = 12,
) -> ImageFont.FreeTypeFont:
    """逐步缩小字号直到文本宽度合适（用于标题自适应）。"""
    from PIL import ImageFont as _ImageFont

    size = start_size
    while size > min_size:
        font = _ImageFont.truetype(font_path, size)
        if text_width(draw, text, font) <= max_width:
            return font
        size -= 2
    return _ImageFont.truetype(font_path, min_size)


class OverflowError(Exception):
    """文本在给定区域内放不下。"""
