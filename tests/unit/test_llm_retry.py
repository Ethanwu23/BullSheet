"""LLM 窄任务（总结+翻译）生成链路测试。

架构（ADR-016）：行情数据不交给模型。LLM 只返回
{evening_summary, headlines}，由 _merge_llm_parts 合并进规则式基础内容。
"""

from __future__ import annotations

import json

import pytest

from usmarket.ai import service as ai_service


def _narrow_payload(news_count: int) -> str:
    return json.dumps(
        {
            "evening_summary": "今日美股收盘分化，特斯拉领涨，详细见图。",
            "headlines": [f"第{i}条新闻的中文标题" for i in range(1, news_count + 1)],
        },
        ensure_ascii=False,
    )


class FlakyProvider:
    """前 N 次返回非法输出，之后返回合法窄任务 JSON。"""

    name = "flaky"

    def __init__(self, fail_times: int, payload: str) -> None:
        self.fail_times = fail_times
        self.payload = payload
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            return "这不是 JSON"
        return self.payload


@pytest.fixture
def news_count(processed_news, offline_cfg) -> int:
    return min(len(processed_news), offline_cfg.content.top_news_max)


def test_llm_summary_and_translation_merged(
    offline_cfg, snapshot, processed_news, news_count
):
    """窄任务成功：generator=hybrid，标题被替换为中文，总结被替换。"""
    prov = FlakyProvider(0, _narrow_payload(news_count))
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert result.generator == "hybrid"
    assert result.evening_summary == "今日美股收盘分化，特斯拉领涨，详细见图。"
    assert all("中文标题" in n.headline for n in result.top_news)
    assert not any("失败" in w for w in warnings)


def test_retry_recovers_from_single_failure(
    offline_cfg, snapshot, processed_news, news_count
):
    """第 1 次输出非法、第 2 次合法 → 仍用 LLM 结果。"""
    prov = FlakyProvider(1, _narrow_payload(news_count))
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert prov.calls == 2
    assert result.generator == "hybrid"
    assert not any("失败" in w for w in warnings)


def test_fallback_after_all_retries_exhausted(
    offline_cfg, snapshot, processed_news
):
    """两次都失败 → 沿用规则式内容（英文标题 + 规则式总结），记录警告。"""
    prov = FlakyProvider(99, "")
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert prov.calls == 2
    assert result.generator == "rule_based"
    assert any("沿用规则式" in w for w in warnings)


def test_no_llm_when_provider_is_none(offline_cfg, snapshot, processed_news):
    """rule_based（provider=None）：纯规则式。"""
    result, _ = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=None, now=None
    )
    assert result.generator == "rule_based"


def test_headline_count_too_few_rejected(
    offline_cfg, snapshot, processed_news, news_count
):
    """headlines 少于要闻数 → 拒绝合并，沿用规则式。"""
    bad = json.dumps(
        {"evening_summary": "x", "headlines": ["只有一条"]}, ensure_ascii=False
    )
    prov = FlakyProvider(0, bad)
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert result.generator == "rule_based"
    assert any("沿用规则式" in w for w in warnings)


def test_extra_headlines_tolerated(
    offline_cfg, snapshot, processed_news, news_count
):
    """模型翻译了全部输入新闻（多于要闻数）→ 取前 N 条，不视为失败。"""
    extra = json.dumps(
        {
            "evening_summary": "总结。",
            "headlines": [f"标题{i}" for i in range(1, news_count + 10)],
        },
        ensure_ascii=False,
    )
    prov = FlakyProvider(0, extra)
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert result.generator == "hybrid"
    assert len(result.top_news) == news_count
    assert not any("沿用规则式" in w for w in warnings)


def test_market_data_never_passes_through_llm(
    offline_cfg, snapshot, processed_news, news_count
):
    """关键规则：指数/个股数字必须与规则式基础完全一致（LLM 无法改动行情）。"""
    base, _ = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=None, now=None
    )
    prov = FlakyProvider(0, _narrow_payload(news_count))
    merged, _ = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert [m.model_dump() for m in merged.index_moves] == [
        m.model_dump() for m in base.index_moves
    ]
    assert [m.model_dump() for m in merged.watchlist_moves] == [
        m.model_dump() for m in base.watchlist_moves
    ]
    # 来源链接与时间同样不可被模型改动
    assert [s.model_dump() for s in merged.sources] == [
        s.model_dump() for s in base.sources
    ]
