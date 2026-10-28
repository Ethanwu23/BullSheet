"""LLM 失败重试逻辑测试：单次抖动不降级为规则式。"""

from __future__ import annotations

import json

import pytest

from usmarket.ai import service as ai_service


class FlakyProvider:
    """前 N 次返回非法输出，之后返回合法 JSON。"""

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
def valid_payload(content) -> str:
    """用规则式内容（可通过全部校验）作为 LLM 的合法输出。"""
    data = content.model_dump(mode="json")
    data.pop("generator", None)
    return json.dumps(data, ensure_ascii=False)


def test_retry_recovers_from_single_failure(
    offline_cfg, snapshot, processed_news, content, valid_payload
):
    """第 1 次输出非法、第 2 次合法 → 最终仍用 LLM 结果而非规则式。"""
    prov = FlakyProvider(fail_times=1, payload=valid_payload)
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert prov.calls == 2
    assert result.generator == "flaky"
    assert not any("回退规则式" in w for w in warnings)


def test_fallback_after_all_retries_exhausted(offline_cfg, snapshot, processed_news):
    """两次都失败 → 回退规则式并记录警告，且不无限重试。"""
    prov = FlakyProvider(fail_times=99, payload="")
    result, warnings = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=prov, now=None
    )
    assert prov.calls == 2
    assert result.generator == "rule_based"
    assert any("回退规则式" in w for w in warnings)


def test_no_retry_when_provider_is_none(offline_cfg, snapshot, processed_news):
    """rule_based（provider=None）时不进入重试路径。"""
    result, _ = ai_service.generate_daily_content(
        offline_cfg, snapshot, processed_news, provider=None, now=None
    )
    assert result.generator == "rule_based"
