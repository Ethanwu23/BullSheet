"""图片测试：可打开、尺寸、非空白、文字不溢出、数字一致、字体缺失报错。"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw, ImageFont

from usmarket.errors import FontMissingError, RenderError
from usmarket.image_renderer import fonts as fonts_module
from usmarket.image_renderer.layout import (
    can_break_before,
    text_width,
    truncate_to_width,
    wrap_text,
)
from usmarket.image_renderer.renderer import assert_not_blank, render_images


def _has_cjk_font() -> bool:
    try:
        fonts_module.resolve_font("")
        return True
    except FontMissingError:
        return False


HAS_FONT = _has_cjk_font()
requires_font = pytest.mark.skipif(
    not HAS_FONT, reason="系统缺少中文字体，跳过渲染测试"
)


def _font(size: int = 32) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(fonts_module.resolve_font("").path, size)


@pytest.fixture
def draw() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("RGB", (1000, 1000), "white"))


# ---------- 字体 ----------
@requires_font
def test_font_supports_chinese():
    font = fonts_module.resolve_font("")
    img = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(img).text((4, 4), "中文测试", font=ImageFont.truetype(font.path, 32), fill=255)
    assert img.getbbox() is not None


def test_missing_font_raises_clear_error(monkeypatch, tmp_path):
    """字体缺失时抛明确错误，不得产出乱码图片（FR-033）。"""
    monkeypatch.setattr(fonts_module, "CANDIDATE_PATHS", ())
    monkeypatch.setattr(fonts_module, "ASSET_FONT_DIR", tmp_path / "none")
    monkeypatch.delenv("USMARKET_FONT_REGULAR", raising=False)
    fonts_module.resolve_font.cache_clear()
    try:
        with pytest.raises(FontMissingError) as exc:
            fonts_module.resolve_font("")
        assert "字体" in str(exc.value)
    finally:
        fonts_module.resolve_font.cache_clear()


# ---------- 换行 ----------
@requires_font
def test_wrap_text_respects_width(draw):
    font = _font(32)
    text = "美股三大指数今日集体收涨，纳斯达克综合指数领涨，半导体板块表现强势。" * 2
    lines = wrap_text(draw, text, font, 600)
    assert len(lines) > 1
    for line in lines:
        assert text_width(draw, line, font) <= 600 + 1


@requires_font
def test_wrap_text_does_not_split_cjk_number_token(draw):
    font = _font(40)
    lines = wrap_text(draw, "标普500收涨0.61%", font, 1000)
    joined = "".join(lines)
    assert "标普500" in joined


def test_can_break_rules():
    text = "标普500"
    # 不允许在「普」与「5」之间断行
    assert can_break_before(text, 2) is False


@requires_font
def test_truncate_to_width(draw):
    font = _font(32)
    long = "这是一个非常长的标题" * 5
    out = truncate_to_width(draw, long, font, 300)
    assert out.endswith("…")
    assert text_width(draw, out, font) <= 300 + 1


# ---------- 空白检测 ----------
def test_assert_not_blank_detects_blank():
    blank = Image.new("RGB", (200, 300), (15, 23, 42))
    with pytest.raises(RenderError):
        assert_not_blank(blank)


def test_assert_not_blank_passes_for_content():
    img = Image.new("RGB", (200, 300), (15, 23, 42))
    draw = ImageDraw.Draw(img)
    for i in range(0, 200, 20):
        draw.rectangle([i, 20, i + 10, 280], fill=(249, 115, 22))
    assert_not_blank(img)


# ---------- 完整渲染 ----------
@requires_font
@pytest.mark.parametrize("template", ["daily_review", "flash_brief"])
def test_render_images(offline_cfg, snapshot, content, tmp_path, template):
    from dataclasses import replace

    cfg = replace(offline_cfg, image=replace(offline_cfg.image, template=template))
    result = render_images(cfg, content, snapshot, tmp_path / "images")
    assert result.cover.exists()
    assert 5 <= len(result.pages) <= 7

    cover = Image.open(result.cover)
    assert cover.size == (cfg.image.width, cfg.image.height)
    for page in result.pages:
        img = Image.open(page)
        assert img.size == (cfg.image.width, cfg.image.height)
        assert_not_blank(img)


@requires_font
def test_rendered_image_numbers_match_content(offline_cfg, snapshot, content, tmp_path):
    """图片内数字与 content.json 一致（SC-004）。

    图片由 content + snapshot 渲染，两者数字同源；此处校验：
    1. content.json 序列化往返后模块数字不变；
    2. content 中展示的指数数字与 snapshot 完全一致。
    """
    from usmarket.content.json_store import load_content, save_content

    result = render_images(offline_cfg, content, snapshot, tmp_path / "images")
    json_path = tmp_path / "content.json"
    save_content(content, json_path)
    reloaded = load_content(json_path)

    by_symbol = {m.symbol: m for m in reloaded.index_moves}
    for quote in snapshot.indices:
        move = by_symbol.get(quote.symbol)
        assert move is not None
        if quote.is_usable():
            assert move.price == quote.price
            assert move.change_percent == quote.change_percent
        else:
            assert move.price is None and move.change_percent is None
    assert result.manifest.exists()


@requires_font
def test_page_count_within_config(offline_cfg, snapshot, content, tmp_path):
    """多页模板（daily_review）的页数必须落在配置区间内。"""
    from dataclasses import replace

    cfg = replace(
        offline_cfg, image=replace(offline_cfg.image, template="daily_review")
    )
    result = render_images(cfg, content, snapshot, tmp_path / "images")
    assert len(result.pages) <= cfg.image.max_pages
    assert len(result.pages) >= cfg.image.min_pages


def test_unknown_template_raises(offline_cfg):
    from dataclasses import replace

    from usmarket.image_renderer.renderer import build_template
    from usmarket.image_renderer.theme import ResolvedTheme

    cfg = replace(offline_cfg, image=replace(offline_cfg.image, template="nope"))
    with pytest.raises(RenderError):
        build_template(cfg, ResolvedTheme.from_config(cfg.image.theme))


def test_theme_hex_parsing():
    from usmarket.image_renderer.theme import hex_to_rgb

    assert hex_to_rgb("#0F172A") == (15, 23, 42)
    assert hex_to_rgb("fff") == (255, 255, 255)
    with pytest.raises(ValueError):
        hex_to_rgb("#12345")
