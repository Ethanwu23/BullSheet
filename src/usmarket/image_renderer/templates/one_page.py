"""模板三：单图速览（one_page）。

把全天内容浓缩到**一张长图**：宽 1080 不变，高度按实际内容自适应
（先画在足够高的画布上，再按光标位置裁掉尾部空白）。

内容结构（自上而下）：
1. 日期 + 标题
2. 三大指数（紧凑行）
3. 今日概览（限行）
4. 要闻（每条限 3 行内）
5. 个股异动（紧凑列表）
6. 明日关注 / 风险提示
7. 免责声明 footer（画在内容末尾，而非画布底部）
"""

from __future__ import annotations

from datetime import datetime

from PIL import Image, ImageDraw

from usmarket.image_renderer.fonts import load
from usmarket.image_renderer.layout import text_width, truncate_to_width
from usmarket.image_renderer.templates.base import BaseTemplate, Canvas
from usmarket.image_renderer.theme import hex_to_rgb
from usmarket.market_data.models import Quote, QuoteSnapshot
from usmarket.validation.schema import DailyContent

PHASE_ZH = {
    "pre": "盘前", "regular": "盘中", "post": "盘后",
    "closed": "收盘", "unknown": "",
}


class _OutOfCanvas(Exception):
    """内容超出预留画布高度（触发用更高画布重画）。"""


class OnePageTemplate(BaseTemplate):
    name = "one_page"

    def __init__(self, cfg, theme) -> None:  # noqa: ANN001 - 同基类
        super().__init__(cfg, theme)
        self._headroom = 3200  # 预留画布高度，不够时翻倍重画

    # ---------- 组装 ----------
    def build_pages(
        self, content: DailyContent, snapshot: QuoteSnapshot, now: datetime
    ) -> list[Image.Image]:
        while True:
            canvas = self._new_tall_canvas(self._headroom)
            try:
                self._draw_all(canvas, content, snapshot)
                end_y = self._draw_footer(canvas, content, snapshot)
            except _OutOfCanvas:
                self._headroom *= 2
                continue
            break

        # 裁剪到实际内容高度（含底部留白），保底不小于一屏
        crop_h = max(min(end_y, canvas.height), self.cfg.image.width)
        return [canvas.image.crop((0, 0, canvas.width, crop_h))]

    # ---------- 画布 ----------
    def _new_tall_canvas(self, height: int) -> Canvas:
        width = self.cfg.image.width
        image = Image.new("RGB", (width, height), hex_to_rgb(self.theme.background))
        canvas = Canvas(
            image=image,
            draw=ImageDraw.Draw(image),
            theme=self.theme,
            width=width,
            height=height,
            margin=self.cfg.image.margin,
        )
        canvas.fonts = {
            "title": load(self.theme.font_regular, size=60, bold=True),
            "h1": load(self.theme.font_regular, size=46, bold=True),
            "h2": load(self.theme.font_regular, size=36, bold=True),
            "body": load(self.theme.font_regular, size=32),
            "small": load(self.theme.font_regular, size=27),
            "tiny": load(self.theme.font_regular, size=23),
            "number": load(self.theme.font_regular, size=38, bold=True),
        }
        canvas.cursor_y = self.cfg.image.margin + 16
        return canvas

    # ---------- 内容绘制 ----------
    def _draw_all(
        self, canvas: Canvas, content: DailyContent, snapshot: QuoteSnapshot
    ) -> None:
        phase = PHASE_ZH.get(content.market_phase, "")

        # 标题区
        self._line(canvas, f"{content.date} 美股{phase}速览", "h1", self.theme.accent)
        self._line(
            canvas, content.xhs.title, "title", self.theme.text_primary,
            max_lines=2, gap=10,
        )
        canvas.cursor_y += 18
        self.divider(canvas)
        canvas.cursor_y += 14

        # 三大指数（紧凑行）
        for quote in snapshot.indices[:3]:
            self._compact_quote(canvas, quote)
        canvas.cursor_y += 14
        self.divider(canvas)
        canvas.cursor_y += 14

        # 概览
        self._line(canvas, "今日概览", "h2", self.theme.text_primary)
        self._line(
            canvas, content.summary, "small", self.theme.text_primary,
            max_lines=6, gap=8,
        )
        canvas.cursor_y += 12

        # 要闻
        if content.top_news:
            self._guard(canvas)
            self._line(
                canvas, f"要闻速递（{len(content.top_news)} 条）",
                "h2", self.theme.text_primary,
            )
            for entry in content.top_news:
                self._guard(canvas)
                self._line(
                    canvas, entry.headline, "small", self.theme.accent,
                    max_lines=2, gap=6,
                )
                self._line(
                    canvas, entry.body, "tiny", self.theme.text_secondary,
                    max_lines=2, gap=5,
                )
                published = (
                    entry.published_at.strftime("%m-%d %H:%M")
                    if entry.published_at
                    else "时间未知"
                )
                self._line(
                    canvas, f"{entry.source_title} · {published}", "tiny",
                    self.theme.muted, max_lines=1, gap=0,
                )
                canvas.cursor_y += 10
            canvas.cursor_y += 4

        # 个股异动（紧凑列表）
        if content.watchlist_moves:
            self._guard(canvas)
            self.divider(canvas)
            canvas.cursor_y += 10
            self._line(canvas, "个股异动", "h2", self.theme.text_primary)
            for entry in content.watchlist_moves[:6]:
                quote = snapshot.by_symbol(entry.symbol) or Quote(
                    symbol=entry.symbol,
                    display_name=entry.name,
                )
                self._compact_quote(canvas, quote)

        # 明日关注
        if content.next_session:
            self._guard(canvas)
            canvas.cursor_y += 12
            self.divider(canvas)
            canvas.cursor_y += 10
            self._line(canvas, "明日关注", "h2", self.theme.text_primary)
            for item in content.next_session[:3]:
                self._line(
                    canvas, "· " + item, "tiny", self.theme.text_secondary,
                    max_lines=2, gap=5,
                )

        # 风险提示
        if content.risk_notes:
            self._guard(canvas)
            canvas.cursor_y += 10
            self._line(canvas, "风险提示", "h2", self.theme.negative)
            for note in content.risk_notes[:2]:
                self._line(
                    canvas, "· " + note, "tiny", self.theme.text_secondary,
                    max_lines=2, gap=5,
                )

        if content.low_confidence:
            self._line(
                canvas, "低置信度：数据或新闻不足，发布前需人工复核", "tiny",
                self.theme.negative, max_lines=1,
            )
            canvas.cursor_y += 6

    def _draw_footer(
        self, canvas: Canvas, content: DailyContent, snapshot: QuoteSnapshot
    ) -> int:
        """footer 画在内容末尾（而非画布底部），返回结束 y。"""
        self._guard(canvas)
        canvas.cursor_y += 18
        self.divider(canvas)
        canvas.cursor_y += 12
        self._line(
            canvas,
            f"数据来源：{snapshot.provider}"
            + ("（延迟行情，非实时）" if snapshot.is_delayed else "")
            + f" · 来源 {len(content.sources)} 条",
            "tiny", self.theme.text_secondary,
        )
        self._line(
            canvas,
            content.disclaimer or self.cfg.content.disclaimer,
            "tiny", self.theme.text_secondary,
        )
        self._line(canvas, f"@{self.cfg.account.name}", "tiny", self.theme.muted)
        return canvas.cursor_y + 8

    # ---------- 原语 ----------
    def _guard(self, canvas: Canvas) -> None:
        """预留 300px 给 footer 与缓冲，超限则要求更高的画布。"""
        if canvas.cursor_y > canvas.height - 300:
            raise _OutOfCanvas

    def _line(
        self,
        canvas: Canvas,
        text: str,
        font_key: str,
        color: str,
        *,
        max_lines: int = 1,
        gap: int = 6,
    ) -> None:
        if not text:
            return
        self._guard(canvas)
        self.text(
            canvas,
            text,
            font_key=font_key,
            color=color,
            max_lines=max_lines,
            line_gap=gap,
        )
        canvas.cursor_y += gap

    def _compact_quote(self, canvas: Canvas, quote: Quote) -> None:
        """单行行情：名称+代码 | 价格 | 涨跌幅（高度 84，比常规行紧凑）。"""
        self._guard(canvas)
        left = canvas.margin
        right = canvas.width - canvas.margin
        height = 84
        top = canvas.cursor_y + 6
        self.rect(
            canvas,
            (left, top, right, top + height),
            fill=self.theme.surface,
            radius=12,
        )
        name_font = canvas.fonts["small"]
        tiny_font = canvas.fonts["tiny"]
        num_font = canvas.fonts["number"]

        name = truncate_to_width(canvas.draw, quote.display_name, name_font, 260)
        canvas.draw.text(
            (left + 20, top + (height - name_font.size) / 2),
            name,
            font=name_font,
            fill=hex_to_rgb(self.theme.text_primary),
        )
        name_w = text_width(canvas.draw, name, name_font)
        canvas.draw.text(
            (left + 20 + name_w + 12, top + (height - tiny_font.size) / 2 + 8),
            quote.symbol,
            font=tiny_font,
            fill=hex_to_rgb(self.theme.text_secondary),
        )

        if quote.is_usable() and quote.price is not None:
            price_text = f"{quote.price:,.2f}"
            pct = quote.change_percent
            pct_text = f"{pct:+.2f}%" if pct is not None else "—"
            pct_color = self.theme.positive if (pct or 0) >= 0 else self.theme.negative
        else:
            price_text = "数据缺失"
            pct_text = "—"
            pct_color = self.theme.text_secondary

        pct_w = text_width(canvas.draw, pct_text, num_font)
        canvas.draw.text(
            (right - 20 - pct_w, top + (height - num_font.size) / 2),
            pct_text,
            font=num_font,
            fill=hex_to_rgb(pct_color),
        )
        price_font = canvas.fonts["body"]
        price_w = text_width(canvas.draw, price_text, price_font)
        canvas.draw.text(
            (right - 20 - pct_w - 24 - price_w, top + (height - price_font.size) / 2),
            price_text,
            font=price_font,
            fill=hex_to_rgb(self.theme.text_secondary),
        )
        canvas.cursor_y = top + height + 10
