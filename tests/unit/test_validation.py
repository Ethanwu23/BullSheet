"""校验测试：数字可追溯、来源完整性、合规表述、结构。"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from usmarket.validation.compliance import validate_compliance
from usmarket.validation.numbers import (
    build_allowed_numbers,
    scan_text_numbers,
    validate_numbers,
    verify_structural_numbers,
)
from usmarket.validation.schema import (
    Confidence,
    DailyContent,
    IndexMove,
    MoveEntry,
    NewsEntry,
    SourceRef,
    XhsContent,
)
from usmarket.validation.sources import validate_sources

NOW = datetime(2026, 10, 26, 20, 5, tzinfo=UTC)


def _content(**overrides) -> DailyContent:
    base = dict(
        date="2026-10-26",
        market_phase="closed",
        generator="test",
        summary="标普500 收于 6,791.50 点，上涨 0.61%。",
        index_moves=[
            IndexMove(
                symbol="^GSPC", name="标普500", price=6791.5, change_percent=0.6133,
                source_ref="quote:^GSPC",
            )
        ],
        top_news=[
            NewsEntry(
                headline="英伟达财报超预期",
                body="数据中心收入增长。",
                tickers=["NVDA"],
                source_title="CNBC",
                source_url="https://www.cnbc.com/a",
                published_at=NOW,
                confidence=Confidence.FACT,
            )
        ],
        watchlist_moves=[
            MoveEntry(
                symbol="NVDA", name="英伟达", change_percent=2.3723,
                note="英伟达上涨 2.37%", confidence=Confidence.ANALYSIS,
            )
        ],
        xhs=XhsContent(title="美股收盘｜标普500 +0.61%", body="正文内容", tags=["#美股"]),
        sources=[
            SourceRef(title="英伟达财报超预期", url="https://www.cnbc.com/a",
                      source="CNBC", published_at=NOW)
        ],
        disclaimer="不构成投资建议",
        low_confidence=True,
    )
    base.update(overrides)
    return DailyContent(**base)


# ---------- 结构 ----------
def test_schema_requires_source_url():
    with pytest.raises(PydanticValidationError):
        NewsEntry(
            headline="x", body="y", source_title="CNBC", source_url="not-a-url"
        )


def test_schema_rejects_empty_title():
    with pytest.raises(PydanticValidationError):
        XhsContent(title="", body="x")


# ---------- 数字校验 ----------
def test_structural_numbers_match_snapshot(snapshot):
    content = _content()
    assert verify_structural_numbers(content, snapshot) == []


def test_structural_numbers_detect_mismatch(snapshot):
    content = _content(
        index_moves=[
            IndexMove(symbol="^GSPC", name="标普500", price=7000.0, change_percent=3.0)
        ]
    )
    issues = verify_structural_numbers(content, snapshot)
    assert len(issues) == 2  # price 和 change_percent 都不一致
    assert all("不一致" in i.reason for i in issues)


def test_structural_numbers_reject_number_for_missing_quote(snapshot):
    content = _content(
        watchlist_moves=[
            MoveEntry(symbol="NOT_IN_FIXTURE", name="未知", change_percent=1.23)
        ]
    )
    issues = verify_structural_numbers(content, snapshot)
    assert any("不存在" in i.reason for i in issues)


def test_fabricated_number_in_text_is_blocked(snapshot, news_items):
    """AI 编造的数字必须被拦截（SC-003）。"""
    content = _content(summary="标普500 收于 8,999.99 点，上涨 12.34%。")
    issues = scan_text_numbers(
        content, build_allowed_numbers(snapshot, [f"{n.title} {n.summary}" for n in news_items])
    )
    values = " ".join(i.value for i in issues)
    assert "8999.99" in values or "8,999.99" in values
    assert "12.34" in values


def test_real_numbers_pass(snapshot, news_items):
    content = _content()
    issues = validate_numbers(
        content, snapshot, input_texts=[f"{n.title} {n.summary}" for n in news_items]
    )
    assert issues == [], [str(i) for i in issues]


def test_years_and_small_integers_are_exempt(snapshot):
    content = _content(summary="2026 年以来，三大指数中有 2 个创下新高。")
    issues = scan_text_numbers(content, build_allowed_numbers(snapshot, []))
    assert issues == []


# ---------- 来源校验 ----------
def test_sources_missing_url_blocked():
    content = _content(top_news=[])
    issues = validate_sources(content)
    assert any("缺少重要新闻条目" in i.reason for i in issues)


def test_source_url_must_appear_in_sources_list():
    content = _content(
        top_news=[
            NewsEntry(
                headline="h", body="b", source_title="CNBC",
                source_url="https://www.cnbc.com/other", published_at=NOW,
            )
        ]
    )
    issues = validate_sources(content)
    assert any("sources 清单" in i.reason for i in issues)


def test_fact_without_published_at_blocked():
    content = _content(
        top_news=[
            NewsEntry(
                headline="h", body="b", source_title="CNBC",
                source_url="https://www.cnbc.com/a", published_at=None,
                confidence=Confidence.FACT,
            )
        ]
    )
    issues = validate_sources(content)
    assert any("缺少发布时间" in i.reason for i in issues)


# ---------- 合规 ----------
@pytest.mark.parametrize(
    "text",
    [
        "这只股票稳赚不赔",
        " guaranteed profit 机会",
        "无风险套利",
        "最后机会，错过就没了",
        "建议全仓买入",
        "该股一定会涨",
    ],
)
def test_compliance_blocks_banned_phrases(text):
    content = _content(summary=text)
    issues = validate_compliance(content)
    assert issues, f"未拦截: {text}"


def test_compliance_allows_normal_analysis():
    content = _content(summary="标普500 收涨，市场情绪偏暖，但成交额一般。")
    assert validate_compliance(content) == []


def test_speculation_allows_hedged_prediction():
    """推测性表述允许出现，但必须标为 speculation 且不构成保证。"""
    content = _content(
        top_news=[
            NewsEntry(
                headline="分析师认为若降息落地，成长股可能受益",
                body="这是分析而非事实。",
                source_title="CNBC",
                source_url="https://www.cnbc.com/a",
                published_at=NOW,
                confidence=Confidence.SPECULATION,
            )
        ]
    )
    assert validate_compliance(content) == []


def test_confirmed_forecast_wording_is_blocked_even_in_speculation():
    """即使是 speculation 条目，"一定会涨"也属于无证据的确定性预测。"""
    content = _content(
        top_news=[
            NewsEntry(
                headline="该股下周一定会涨",
                body="b",
                source_title="X",
                source_url="https://x.com/1",
                published_at=NOW,
                confidence=Confidence.SPECULATION,
            )
        ]
    )
    issues = validate_compliance(content)
    assert any("确定性预测" in i.rule or "夸大" in i.rule for i in issues) or issues


# ---------- 长度可配置 ----------
def test_content_limits_are_configurable(offline_cfg):
    assert offline_cfg.content.title_max_chars == 30
    assert offline_cfg.content.top_news_min == 3
    assert offline_cfg.content.top_news_max == 5
