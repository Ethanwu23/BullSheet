"""单图速览模板（one_page）测试：一张图、动态高度、溢出重画、渲染器兼容。"""

from __future__ import annotations

from datetime import datetime

import pytest
from PIL import Image

from usmarket.errors import FontMissingError
from usmarket.image_renderer import fonts as fonts_module
from usmarket.image_renderer.renderer import assert_not_blank, render_images
from usmarket.image_renderer.templates.one_page import OnePageTemplate


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

NOW = datetime(2026, 10, 26, 20, 5)


@pytest.fixture
def one_page_cfg(offline_cfg):
    from dataclasses import replace

    return replace(offline_cfg, image=replace(offline_cfg.image, template="one_page"))


@pytest.fixture
def pages(one_page_cfg, content, snapshot):
    from usmarket.image_renderer.theme import ResolvedTheme

    theme = ResolvedTheme.from_config(one_page_cfg.image.theme)
    return OnePageTemplate(one_page_cfg, theme).build_pages(content, snapshot, NOW)


@requires_font
class TestOnePageTemplate:
    def test_produces_exactly_one_image(self, pages):
        assert len(pages) == 1

    def test_width_matches_config_height_is_dynamic(self, offline_cfg, pages):
        image = pages[0]
        assert image.size[0] == offline_cfg.image.width
        # 高度自适应：不等于固定配置高度，但不小于一屏
        assert image.size[1] >= offline_cfg.image.width

    def test_image_openable_and_not_blank(self, pages):
        image = pages[0]
        assert image.mode == "RGB"
        assert_not_blank(image)

    def test_small_headroom_triggers_repage(self, one_page_cfg, content, snapshot):
        """内容超出预留高度时自动用更高画布重画，不崩溃也不丢内容。"""
        from usmarket.image_renderer.theme import ResolvedTheme

        theme = ResolvedTheme.from_config(one_page_cfg.image.theme)
        template = OnePageTemplate(one_page_cfg, theme)
        template._headroom = 400  # 极小画布，强制触发重画
        result = template.build_pages(content, snapshot, NOW)
        assert len(result) == 1
        assert result[0].size[1] > 400

    def test_render_images_accepts_dynamic_height(
        self, one_page_cfg, content, snapshot, tmp_path
    ):
        """render_images 对 one_page 只校验宽度，不因高度不同报错。"""
        result = render_images(one_page_cfg, content, snapshot, tmp_path / "images")
        assert result.cover.exists()
        assert result.pages == ()  # 单图模板没有正文页
        with Image.open(result.cover) as im:
            assert im.size[0] == one_page_cfg.image.width
