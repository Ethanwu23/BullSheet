"""模板二：重大新闻专题。

视觉与 daily_review 明显不同：强调单条重大新闻，封面使用大号标题 + 橙色强调条，
正文页每页一条新闻，配大号序号与引言块。
"""

from __future__ import annotations

from datetime import datetime

from PIL import Image

from usmarket.image_renderer.layout import truncate_to_width, wrap_text
from usmarket.image_renderer.templates.base import BaseTemplate, Canvas
from usmarket.image_renderer.theme import hex_to_rgb
from usmarket.market_data.models import QuoteSnapshot
from usmarket.validation.schema import DailyContent


class FlashBriefTemplate(BaseTemplate):
    name = "flash_brief"

    def _accent_bar(self, canvas: Canvas, y: int, width: int = 120, height: int = 10) -> None:
        canvas.draw.rectangle(
            [canvas.margin, y, canvas.margin + width, y + height],
            fill=hex_to_rgb(self.theme.accent),
        )

    def build_cover(self, content: DailyContent, snapshot: QuoteSnapshot) -> Image.Image:
        canvas = self.new_canvas()
        canvas.cursor_y = 170

        self.single_line(canvas, "重大新闻专题", font_key="h1", color=self.theme.accent)
        canvas.cursor_y += 20
        self._accent_bar(canvas, canvas.cursor_y)
        canvas.cursor_y += 60

        headline = content.top_news[0].headline if content.top_news else content.summary
        self.text(
            canvas,
            headline,
            font_key="title",
            color=self.theme.text_primary,
            max_lines=4,
            line_gap=20,
        )
        canvas.cursor_y += 30

        self.single_line(
            canvas,
            f"{content.date} · {len(content.top_news)} 条要点",
            font_key="body",
            color=self.theme.text_secondary,
        )
        canvas.cursor_y += 30

        y = canvas.cursor_y
        for quote in snapshot.indices[:3]:
            y = self.quote_row(canvas, quote, y=y, height=110)

        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    def build_news_page(
        self, canvas: Canvas, entry, index: int, total: int
    ) -> Image.Image:
        self._header(canvas, f"要点 {index}/{total}")

        # 大号序号
        canvas.draw.text(
            (canvas.margin, canvas.cursor_y),
            f"{index:02d}",
            font=canvas.fonts["title"],
            fill=hex_to_rgb(self.theme.accent),
        )
        canvas.cursor_y += 100

        self.text(
            canvas,
            entry.headline,
            font_key="h2",
            color=self.theme.text_primary,
            max_lines=3,
            line_gap=10,
        )
        canvas.cursor_y += 12

        # 引言块（高度按实际文本行数计算，避免大片空白）
        body_font = canvas.fonts["small"]
        inner_width = canvas.content_width - 48
        lines = wrap_text(canvas.draw, entry.body, body_font, inner_width, max_lines=8)
        line_step = body_font.size + 12
        block_top = canvas.cursor_y
        block_height = 48 + max(1, len(lines)) * line_step
        self.rect(
            canvas,
            (canvas.margin, block_top, canvas.width - canvas.margin, block_top + block_height),
            fill=self.theme.surface,
            radius=20,
        )
        y = block_top + 24
        for line in lines:
            if line:
                canvas.draw.text(
                    (canvas.margin + 24, y),
                    line,
                    font=body_font,
                    fill=hex_to_rgb(self.theme.text_primary),
                )
            y += line_step
        canvas.cursor_y = block_top + block_height + 20

        tickers = " ".join(f"${t}" for t in entry.tickers) if entry.tickers else "—"
        self.single_line(
            canvas, f"相关标的：{tickers}", font_key="small", color=self.theme.accent
        )
        published = (
            entry.published_at.strftime("%Y-%m-%d %H:%M")
            if entry.published_at
            else "发布时间未知"
        )
        self.single_line(
            canvas,
            truncate_to_width(
                canvas.draw,
                f"来源：{entry.source_title} · {published}",
                canvas.fonts["tiny"],
                canvas.content_width,
            ),
            font_key="tiny",
            color=self.theme.text_secondary,
        )
        self.single_line(
            canvas,
            truncate_to_width(canvas.draw, entry.source_url, canvas.fonts["tiny"],
                              canvas.content_width),
            font_key="tiny",
            color=self.theme.muted,
        )
        return canvas.image

    def build_closing_page(
        self, content: DailyContent, snapshot: QuoteSnapshot
    ) -> Image.Image:
        canvas = self.new_canvas()
        self._header(canvas, "风险提示与来源")
        for note in content.risk_notes[:3]:
            self.text(
                canvas, "· " + note, font_key="small",
                color=self.theme.text_secondary, max_lines=4,
            )
        canvas.cursor_y += 16
        self.divider(canvas)
        for src in content.sources[:6]:
            self.single_line(
                canvas,
                truncate_to_width(
                    canvas.draw, f"{src.source} · {src.title}",
                    canvas.fonts["tiny"], canvas.content_width,
                ),
                font_key="tiny",
                color=self.theme.text_secondary,
            )
        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    def build_pages(
        self, content: DailyContent, snapshot: QuoteSnapshot, now: datetime
    ) -> list[Image.Image]:
        pages: list[Image.Image] = [self.build_cover(content, snapshot)]
        news = list(content.top_news)[: self.cfg.image.max_pages - 1]
        for idx, entry in enumerate(news, 1):
            canvas = self.new_canvas()
            pages.append(self.build_news_page(canvas, entry, idx, len(news)))
        pages.append(self.build_closing_page(content, snapshot))

        min_total = self.cfg.image.min_pages + 1
        max_total = self.cfg.image.max_pages + 1
        if len(pages) > max_total:
            pages = pages[: max_total - 1] + [pages[-1]]
        while len(pages) < min_total:
            pages.insert(len(pages) - 1, pages[-2] if len(pages) >= 2 else pages[-1])
        return pages

    def _header(self, canvas: Canvas, title: str) -> None:
        canvas.cursor_y = self.cfg.image.margin
        self.single_line(
            canvas,
            truncate_to_width(canvas.draw, title, canvas.fonts["h1"], canvas.content_width),
            font_key="h1",
            color=self.theme.accent,
        )
        canvas.cursor_y += 14
        self._accent_bar(canvas, canvas.cursor_y, width=80, height=6)
        canvas.cursor_y += 30
