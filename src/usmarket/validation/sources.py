"""来源校验：每条重要新闻必须有可追溯的原始链接与时间。"""

from __future__ import annotations

from dataclasses import dataclass

from usmarket.validation.schema import DailyContent


@dataclass(frozen=True)
class SourceIssue:
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


def validate_sources(content: DailyContent) -> list[SourceIssue]:
    """校验来源完整性。"""
    issues: list[SourceIssue] = []

    if not content.top_news:
        issues.append(SourceIssue("top_news", "缺少重要新闻条目"))

    for i, entry in enumerate(content.top_news):
        if not entry.source_url:
            issues.append(SourceIssue(f"top_news[{i}]", "缺少来源链接"))
        if not entry.source_title:
            issues.append(SourceIssue(f"top_news[{i}]", "缺少来源名称"))
        if entry.confidence.value == "fact" and entry.published_at is None:
            issues.append(
                SourceIssue(
                    f"top_news[{i}]",
                    "以事实陈述的条目缺少发布时间（应提供时间或改为 analysis/speculation）",
                )
            )

    # 正文引用的来源必须能在 sources 清单中找到
    listed = {s.url for s in content.sources}
    for i, entry in enumerate(content.top_news):
        if listed and entry.source_url not in listed:
            issues.append(
                SourceIssue(f"top_news[{i}]", f"来源链接未出现在 sources 清单中: {entry.source_url}")
            )

    if not content.sources:
        issues.append(SourceIssue("sources", "缺少来源清单"))

    return issues
