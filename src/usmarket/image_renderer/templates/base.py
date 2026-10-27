"""模板基类：竖屏卡片的通用绘制原语。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from usmarket.config import AppConfig
from usmarket.image_renderer.fonts import load
from usmarket.image_renderer.layout import truncate_to_width, wrap_text
from usmarket.image_renderer.theme import ResolvedTheme, hex_to_rgb
from usmarket.market_data.models import Quote, QuoteSnapshot
from usmarket.validation.schema import DailyContent


@dataclass
class Canvas:
    """一张卡片的绘制上下文。"""

    image: Image.Image
    draw: ImageDraw.ImageDraw
    theme: ResolvedTheme
    width: int
    height: int
    margin: int
    fonts: dict[str, ImageFont.FreeTypeFont] = field(default_factory=dict)
    cursor_y: int = 0

    @property
    def content_width(self) -> float:
        return float(self.width - self.margin * 2)


class BaseTemplate:
    """模板基类。子类实现 build_pages()。"""

    name = "base"

    def __init__(self, cfg: AppConfig, theme: ResolvedTheme) -> None:
        self.cfg = cfg
        self.theme = theme

    # ---------- 基础绘制 ----------
    def new_canvas(self) -> Canvas:
        width = self.cfg.image.width
        height = self.cfg.image.height
        image = Image.new("RGB", (width, height), hex_to_rgb(self.theme.background))
        draw = ImageDraw.Draw(image)
        canvas = Canvas(
            image=image,
            draw=draw,
            theme=self.theme,
            width=width,
            height=height,
            margin=self.cfg.image.margin,
        )
        canvas.fonts = {
            "title": load(self.theme.font_regular, size=72, bold=True),
            "h1": load(self.theme.font_regular, size=52, bold=True),
            "h2": load(self.theme.font_regular, size=40, bold=True),
            "body": load(self.theme.font_regular, size=34),
            "small": load(self.theme.font_regular, size=27),
            "tiny": load(self.theme.font_regular, size=23),
            "number": load(self.theme.font_regular, size=44, bold=True),
        }
        canvas.cursor_y = self.cfg.image.margin
        return canvas

    def text(
        self,
        canvas: Canvas,
        content: str,
        *,
        font_key: str = "body",
        color: str | None = None,
        max_width: float | None = None,
        line_gap: int = 12,
        max_lines: int | None = None,
        align: str = "left",
    ) -> int:
        """绘制多行文本，返回占用的高度。"""
        font = canvas.fonts[font_key]
        color = color or self.theme.text_primary
        width = max_width or canvas.content_width
        lines = wrap_text(canvas.draw, content, font, width, max_lines=max_lines)
        start_y = canvas.cursor_y
        y = start_y
        for line in lines:
            if not line:
                y += font.size // 2
                continue
            line_w = canvas.draw.textbbox((0, 0), line, font=font)[2]
            if align == "center":
                x = (canvas.width - line_w) / 2
            elif align == "right":
                x = canvas.width - canvas.margin - line_w
            else:
                x = canvas.margin
            canvas.draw.text((x, y), line, font=font, fill=hex_to_rgb(color))
            y += font.size + line_gap
        canvas.cursor_y = y
        return y - start_y

    def single_line(
        self,
        canvas: Canvas,
        content: str,
        *,
        font_key: str = "body",
        color: str | None = None,
        max_width: float | None = None,
        y: int | None = None,
        align: str = "left",
    ) -> int:
        font = canvas.fonts[font_key]
        color = color or self.theme.text_primary
        width = max_width or canvas.content_width
        line = truncate_to_width(canvas.draw, content, font, width)
        line_w = canvas.draw.textbbox((0, 0), line, font=font)[2]
        if align == "center":
            x = (canvas.width - line_w) / 2
        elif align == "right":
            x = canvas.width - canvas.margin - line_w
        else:
            x = canvas.margin
        draw_y = y if y is not None else canvas.cursor_y
        canvas.draw.text((x, draw_y), line, font=font, fill=hex_to_rgb(color))
        if y is None:
            canvas.cursor_y = draw_y + font.size + 12
        return draw_y + font.size

    def rect(
        self,
        canvas: Canvas,
        box: tuple[float, float, float, float],
        *,
        fill: str | None = None,
        outline: str | None = None,
        radius: int = 18,
        width: int = 2,
    ) -> None:
        canvas.draw.rounded_rectangle(
            box,
            radius=radius,
            fill=hex_to_rgb(fill) if fill else None,
            outline=hex_to_rgb(outline) if outline else None,
            width=width,
        )

    def divider(self, canvas: Canvas, *, y: int | None = None, color: str | None = None) -> int:
        draw_y = y if y is not None else canvas.cursor_y + 10
        canvas.draw.line(
            [(canvas.margin, draw_y), (canvas.width - canvas.margin, draw_y)],
            fill=hex_to_rgb(color or self.theme.muted),
            width=2,
        )
        if y is None:
            canvas.cursor_y = draw_y + 20
        return draw_y

    def footer(
        self,
        canvas: Canvas,
        text: str,
        *,
        snapshot: QuoteSnapshot | None = None,
    ) -> None:
        """底部：来源 + 风险提示。"""
        y = canvas.height - canvas.margin - 96
        self.single_line(
            canvas,
            f"数据来源：{snapshot.provider if snapshot else 'unknown'}"
            + ("（延迟行情）" if (snapshot and snapshot.is_delayed) else ""),
            font_key="tiny",
            color=self.theme.text_secondary,
            y=y,
        )
        self.single_line(
            canvas,
            truncate_to_width(canvas.draw, text, canvas.fonts["tiny"], canvas.content_width),
            font_key="tiny",
            color=self.theme.text_secondary,
            y=y + 34,
        )
        self.single_line(
            canvas,
            f"账号：{self.cfg.account.name}",
            font_key="tiny",
            color=self.theme.text_secondary,
            y=y + 68,
            align="right",
        )

    # ---------- 数据卡片 ----------
    def quote_row(
        self,
        canvas: Canvas,
        quote: Quote,
        *,
        y: int,
        height: int | None = None,
        note: str = "",
    ) -> int:
        """一行行情：名称 | 代码 | 价格 | 涨跌幅，可选一行解读（画在卡片内）。"""
        left = canvas.margin
        right = canvas.width - canvas.margin
        has_note = bool(note)
        if height is None:
            height = 152 if has_note else 110
        self.rect(
            canvas,
            (left, y, right, y + height),
            fill=self.theme.surface,
            radius=16,
        )
        name_font = canvas.fonts["h2"]
        symbol_font = canvas.fonts["tiny"]
        num_font = canvas.fonts["number"]
        note_font = canvas.fonts["tiny"]

        block_h = name_font.size + 10 + symbol_font.size
        if has_note:
            block_h += 6 + note_font.size
        top = y + (height - block_h) / 2
        canvas.draw.text(
            (left + 24, top),
            truncate_to_width(canvas.draw, quote.display_name, name_font, 300),
            font=name_font,
            fill=hex_to_rgb(self.theme.text_primary),
        )
        canvas.draw.text(
            (left + 24, top + name_font.size + 10),
            quote.symbol,
            font=symbol_font,
            fill=hex_to_rgb(self.theme.text_secondary),
        )
        if has_note:
            # 解读只占左半区，避免与右侧价格/涨跌幅相撞
            note_width = canvas.content_width * 0.56
            canvas.draw.text(
                (left + 24, top + name_font.size + 10 + symbol_font.size + 6),
                truncate_to_width(canvas.draw, note, note_font, note_width),
                font=note_font,
                fill=hex_to_rgb(self.theme.text_secondary),
            )

        if quote.is_usable():
            price_text = f"{quote.price:,.2f}"
            pct_text = f"{quote.change_percent:+.2f}%"
            pct_color = (
                self.theme.positive
                if (quote.change_percent or 0) >= 0
                else self.theme.negative
            )
        else:
            price_text = "数据缺失"
            pct_text = "—"
            pct_color = self.theme.text_secondary

        pct_w = canvas.draw.textbbox((0, 0), pct_text, font=num_font)[2]
        canvas.draw.text(
            (right - 24 - pct_w, y + (height - num_font.size) / 2),
            pct_text,
            font=num_font,
            fill=hex_to_rgb(pct_color),
        )

        price_font = canvas.fonts["body"]
        price_w = canvas.draw.textbbox((0, 0), price_text, font=price_font)[2]
        canvas.draw.text(
            (right - 24 - pct_w - 32 - price_w, y + (height - price_font.size) / 2),
            price_text,
            font=price_font,
            fill=hex_to_rgb(self.theme.text_secondary),
        )
        return y + height + 16

    # ---------- 接口 ----------
    def build_pages(
        self, content: DailyContent, snapshot: QuoteSnapshot, now: datetime
    ) -> list[Image.Image]:
        raise NotImplementedError
