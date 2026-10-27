"""排版与渲染前文本清洗的回归测试。

这些用例覆盖三个真实出现过的缺陷：
1. str.isalnum() 对中文返回 True，导致所有中文断行点被判为不可断，
   每行都在最后一个字符处硬切（"标普5" / "00"）。
2. LLM 输出带 emoji 与 Markdown 标记，图片字体无字形 → 空白/豆腐块/星号外露。
3. 行情解读文字画到卡片外面（跨卡片重叠）。
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from usmarket.image_renderer.fonts import load
from usmarket.image_renderer.layout import can_break_before, wrap_text
from usmarket.image_renderer.sanitize import sanitize_content_for_image, strip_unsupported


class TestCanBreakBefore:
    def test_cjk_pair_is_breakable(self):
        """中文之间必须可断（曾因 isalnum() 对中文为 True 而全部判为不可断）。"""
        assert can_break_before("美股", 1) is True
        assert can_break_before("股市上涨", 2) is True

    @pytest.mark.parametrize(
        "text,index",
        [
            ("标普500", 2),   # 标|5 → 中文与数字之间不断
            ("标普500", 3),   # 5|0 → 数字内部不断
            ("标普500", 4),   # 0|0
            ("2027年初", 4),  # 7|年 → 数字与量词不断
            ("跌幅近1%", 4),  # 1|% → 百分号不另起行
        ],
    )
    def test_number_tokens_are_atomic(self, text: str, index: int):
        assert can_break_before(text, index) is False

    def test_latin_word_splits_only_at_space(self):
        assert can_break_before("hello world", 6) is True   # 空格后
        assert can_break_before("hello", 3) is False         # 词内

    def test_no_line_start_punctuation(self):
        assert can_break_before("上涨，下跌", 2) is False   # 逗号不能做行首


class TestWrapText:
    @pytest.fixture(scope="class")
    def font(self):
        from usmarket.image_renderer.fonts import FontMissingError

        try:
            return load("", size=36)
        except FontMissingError:  # pragma: no cover - 无字体环境
            pytest.skip("系统中没有可用中文字体")

    def test_cjk_text_wraps_into_multiple_lines(self, font):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 300)))
        text = "美股收盘呈现显著分化，道指逆势上涨而科技股承压。标普500微跌，纳斯达克跌近1%。"
        lines = wrap_text(draw, text, font, 600, max_lines=10)
        assert len(lines) >= 3, f"中文未正确换行: {lines}"
        # 除最后一行外，各行长度应接近（硬切会导致某行只剩 1-2 个字符）
        body_lengths = [len(line) for line in lines[:-1]]
        assert min(body_lengths) >= max(body_lengths) * 0.8, lines
        # 换行不应丢字符
        assert "".join(lines).replace(" ", "") == text.replace(" ", "")

    def test_index_name_is_never_split(self, font):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 300)))
        text = "美股收盘呈现显著分化，道指逆势上涨而科技股承压。标普500微跌。"
        lines = wrap_text(draw, text, font, 920, max_lines=10)
        joined = "".join(lines)
        assert "标普500" in joined
        for line in lines:
            assert not line.startswith("00"), f"标普500 被切断: {lines}"
            assert "标普5" not in line or "标普500" in line

    def test_latin_text_wraps_at_single_space(self, font):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 300)))
        lines = wrap_text(draw, "A " * 200, font, 400, max_lines=5)
        assert len(lines) == 5


class TestStripUnsupported:
    def test_emoji_are_removed(self):
        cleaned, removed = strip_unsupported("📉美股复盘：科技巨头大跌")
        assert cleaned == "美股复盘：科技巨头大跌"
        assert removed == 1

    def test_warning_emoji_becomes_text(self):
        cleaned, _ = strip_unsupported("⚠️ 风险提示")
        assert "注意：" in cleaned

    def test_markdown_emphasis_removed(self):
        cleaned, _ = strip_unsupported("🔴 **三大指数**：道指涨0.76%")
        assert "**" not in cleaned
        assert "三大指数" in cleaned
        assert "0.76%" in cleaned  # 数字必须保留

    def test_hashtag_is_preserved(self):
        """话题标签 #美股 不带空格，不能当作 Markdown 标题删除。"""
        cleaned, _ = strip_unsupported("#美股 #财经")
        assert "#美股" in cleaned and "#财经" in cleaned

    def test_keycap_and_zwj_removed(self):
        cleaned, _ = strip_unsupported("1️⃣ 要闻")
        assert "1" in cleaned and "要闻" in cleaned
        assert "\ufe0f" not in cleaned

    def test_numbers_untouched(self):
        original = "标普500跌0.18%，纳指跌0.99%"
        cleaned, _ = strip_unsupported(original)
        assert cleaned == original


class TestSanitizeContentForImage:
    def test_content_copy_is_cleaned_and_original_untouched(self, content):
        original_title = content.xhs.title
        cleaned = sanitize_content_for_image(content)

        assert content.xhs.title == original_title  # 原对象不变
        assert cleaned is not content
        assert "**" not in cleaned.xhs.body
        assert "\ufe0f" not in cleaned.xhs.title

    def test_numbers_survive_sanitize(self, content):
        cleaned = sanitize_content_for_image(content)
        for src, dst in zip(content.index_moves, cleaned.index_moves, strict=True):
            assert src.price == dst.price
            assert src.change_percent == dst.change_percent

    def test_sources_and_links_preserved(self, content):
        cleaned = sanitize_content_for_image(content)
        assert len(cleaned.sources) == len(content.sources)
        for src, dst in zip(content.sources, cleaned.sources, strict=True):
            assert src.url == dst.url
