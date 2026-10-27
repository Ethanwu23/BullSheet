"""模板一：每日市场复盘。

页面构成（含封面共 5–7 张）：
1. 封面：标题 + 日期 + 三大指数概览
2. 市场概览
3-4. 重要新闻
5. 重点个股异动
6. 财报与宏观
7. 次日关注 / 风险提示 / 来源
"""

from __future__ import annotations

from datetime import datetime

from PIL import Image

from usmarket.image_renderer.layout import truncate_to_width
from usmarket.image_renderer.templates.base import BaseTemplate, Canvas
from usmarket.market_data.models import QuoteSnapshot
from usmarket.validation.schema import DailyContent

PHASE_ZH = {
    "pre": "盘前", "regular": "盘中", "post": "盘后",
    "closed": "收盘", "unknown": "",
}


class DailyReviewTemplate(BaseTemplate):
    name = "daily_review"

    # ---------- 封面 ----------
    def build_cover(
        self, content: DailyContent, snapshot: QuoteSnapshot
    ) -> Image.Image:
        canvas = self.new_canvas()
        phase = PHASE_ZH.get(content.market_phase, "")
        date_text = content.date

        canvas.cursor_y = 150
        self.single_line(
            canvas,
            f"{date_text} 美股{phase}复盘",
            font_key="h1",
            color=self.theme.accent,
        )
        canvas.cursor_y += 24
        self.text(
            canvas,
            content.xhs.title,
            font_key="title",
            color=self.theme.text_primary,
            max_lines=3,
            line_gap=18,
        )

        canvas.cursor_y += 40
        self.divider(canvas)

        y = canvas.cursor_y + 20
        for quote in snapshot.indices[:3]:
            y = self.quote_row(canvas, quote, y=y, height=120)

        canvas.cursor_y = y + 20
        if content.low_confidence:
            self.single_line(
                canvas,
                "⚠ 低置信度：新闻或行情不足，发布前需人工复核",
                font_key="small",
                color=self.theme.negative,
            )
        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    # ---------- 概览页 ----------
    def build_overview_page(
        self, content: DailyContent, snapshot: QuoteSnapshot
    ) -> Image.Image:
        canvas = self.new_canvas()
        self._header(canvas, "今日市场概览", content)
        self.text(
            canvas,
            content.summary,
            font_key="body",
            color=self.theme.text_primary,
            max_lines=14,
            line_gap=16,
        )
        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    # ---------- 新闻页 ----------
    def build_news_page(
        self,
        content: DailyContent,
        snapshot: QuoteSnapshot,
        entries: list,
        *,
        page_no: int,
        total_pages: int,
    ) -> Image.Image:
        canvas = self.new_canvas()
        self._header(canvas, f"今日要闻 {page_no}/{total_pages}", content)

        for entry in entries:
            canvas.cursor_y += 8
            self.text(
                canvas,
                entry.headline,
                font_key="h2",
                color=self.theme.accent,
                max_lines=2,
                line_gap=8,
            )
            self.text(
                canvas,
                entry.body,
                font_key="small",
                color=self.theme.text_primary,
                max_lines=5,
                line_gap=10,
            )
            published = (
                entry.published_at.strftime("%m-%d %H:%M")
                if entry.published_at
                else "时间未知"
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
            canvas.cursor_y += 10
            self.divider(canvas)

        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    # ---------- 异动页 ----------
    def build_moves_page(
        self, content: DailyContent, snapshot: QuoteSnapshot
    ) -> Image.Image:
        canvas = self.new_canvas()
        self._header(canvas, "重点个股异动", content)

        y = canvas.cursor_y + 10
        for entry in content.watchlist_moves[:6]:
            quote = snapshot.by_symbol(entry.symbol)
            y = self.quote_row(
                canvas,
                quote or self._missing_quote(entry.symbol, entry.name),
                y=y,
                note=entry.note or "",
            )
        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    # ---------- 财报/宏观页 ----------
    def build_events_page(
        self, content: DailyContent, snapshot: QuoteSnapshot
    ) -> Image.Image:
        canvas = self.new_canvas()
        self._header(canvas, "财报与宏观", content)
        if content.earnings_and_macro:
            for entry in content.earnings_and_macro[:5]:
                self.text(
                    canvas,
                    entry.title,
                    font_key="h2",
                    color=self.theme.text_primary,
                    max_lines=2,
                    line_gap=8,
                )
                if entry.detail:
                    self.text(
                        canvas,
                        entry.detail,
                        font_key="small",
                        color=self.theme.text_secondary,
                        max_lines=3,
                    )
                if entry.source_url:
                    self.single_line(
                        canvas,
                        truncate_to_width(
                            canvas.draw,
                            entry.source_url,
                            canvas.fonts["tiny"],
                            canvas.content_width,
                        ),
                        font_key="tiny",
                        color=self.theme.muted,
                    )
                canvas.cursor_y += 22
                self.divider(canvas)
        else:
            self.text(
                canvas,
                "本次未采集到明确的财报或宏观事件。",
                font_key="body",
                color=self.theme.text_secondary,
            )
        self.footer(canvas, content.disclaimer or self.cfg.content.disclaimer, snapshot=snapshot)
        return canvas.image

    # ---------- 收尾页 ----------
    def build_closing_page(
        self, content: DailyContent, snapshot: QuoteSnapshot
    ) -> Image.Image:
        canvas = self.new_canvas()
        self._header(canvas, "明日关注与风险提示", content)

        self.text(canvas, "下一交易日关注", font_key="h2", color=self.theme.accent, max_lines=1)
        for item in content.next_session[:4]:
            self.text(
                canvas,
                "· " + item,
                font_key="small",
                color=self.theme.text_primary,
                max_lines=3,
            )
        canvas.cursor_y += 16
        self.divider(canvas)

        self.text(canvas, "风险提示", font_key="h2", color=self.theme.negative, max_lines=1)
        for note in content.risk_notes[:3]:
            self.text(
                canvas,
                "· " + note,
                font_key="small",
                color=self.theme.text_secondary,
                max_lines=4,
            )
        canvas.cursor_y += 16
        self.divider(canvas)

        self.text(
            canvas,
            f"主要来源（{len(content.sources)} 条）",
            font_key="h2",
            color=self.theme.accent,
            max_lines=1,
        )
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

    # ---------- 组装 ----------
    def build_pages(
        self, content: DailyContent, snapshot: QuoteSnapshot, now: datetime
    ) -> list[Image.Image]:
        pages: list[Image.Image] = [self.build_cover(content, snapshot)]
        pages.append(self.build_overview_page(content, snapshot))

        news = list(content.top_news)
        if news:
            # 新闻最多占 2 页：3 条以内单页，4-5 条分 2 页（避免出现只放 1 条的空页）
            import math

            page_count = 1 if len(news) <= 3 else 2
            chunk_size = math.ceil(len(news) / page_count)
            chunks = [news[i : i + chunk_size] for i in range(0, len(news), chunk_size)]
            for idx, chunk in enumerate(chunks, 1):
                pages.append(
                    self.build_news_page(
                        content, snapshot, chunk, page_no=idx, total_pages=len(chunks)
                    )
                )

        if content.watchlist_moves:
            pages.append(self.build_moves_page(content, snapshot))
        if content.earnings_and_macro:
            pages.append(self.build_events_page(content, snapshot))
        pages.append(self.build_closing_page(content, snapshot))

        return self._trim(pages)

    def _trim(self, pages: list[Image.Image]) -> list[Image.Image]:
        """裁剪到配置的页数区间（封面 + 5~7 页正文）。"""
        min_total = self.cfg.image.min_pages + 1
        max_total = self.cfg.image.max_pages + 1
        if len(pages) > max_total:
            # 保留封面、概览、收尾，中间按需裁剪
            keep_head = 2
            keep_tail = 1
            middle = pages[keep_head:-keep_tail]
            allowed_middle = max(0, max_total - keep_head - keep_tail)
            pages = pages[:keep_head] + middle[:allowed_middle] + pages[-keep_tail:]
        while len(pages) < min_total:
            pages.insert(len(pages) - 1, pages[-2] if len(pages) >= 2 else pages[-1])
        return pages

    # ---------- 工具 ----------
    def _header(self, canvas: Canvas, title: str, content: DailyContent) -> None:
        canvas.cursor_y = self.cfg.image.margin
        self.single_line(
            canvas,
            truncate_to_width(canvas.draw, title, canvas.fonts["h1"], canvas.content_width),
            font_key="h1",
            color=self.theme.accent,
        )
        self.single_line(
            canvas,
            f"{content.date} · 美股复盘",
            font_key="small",
            color=self.theme.text_secondary,
        )
        canvas.cursor_y += 8
        self.divider(canvas)
        canvas.cursor_y += 8

    def _missing_quote(self, symbol: str, name: str):
        from usmarket.market_data.models import Quote, QuoteQuality

        return Quote(
            symbol=symbol,
            display_name=name,
            quality=QuoteQuality.MISSING,
            quality_note="数据缺失",
        )
