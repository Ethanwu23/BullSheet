"""LLM Provider 配置与输出归一化测试（含阿里百炼预设）。

覆盖两个真实缺陷：
1. 模型把 market_phase 写成 "pre-market"，直接校验失败导致整篇回退规则式生成。
2. 百炼端点/模型/密钥来源需要预设，否则用户要手填三处易错的默认值。
"""

from __future__ import annotations

import pytest

from usmarket.ai.base import coerce_content, normalize_payload
from usmarket.config import (
    DASHSCOPE_BASE_URL,
    DASHSCOPE_DEFAULT_MODEL,
    load_config,
    validate_sensitive_config,
)


@pytest.fixture
def clean_env(monkeypatch):
    """清空所有会干扰断言的 LLM 相关环境变量。"""
    for name in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_EXTRA_BODY_JSON",
        "DASHSCOPE_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestDashScopePreset:
    def test_preset_fills_endpoint_and_model(self, clean_env):
        clean_env.setenv("LLM_PROVIDER", "dashscope")
        clean_env.setenv("DASHSCOPE_API_KEY", "sk-test")
        cfg = load_config()

        assert cfg.llm.provider == "dashscope"
        assert cfg.llm.base_url == DASHSCOPE_BASE_URL
        assert cfg.llm.model == DASHSCOPE_DEFAULT_MODEL
        assert cfg.llm.api_key == "sk-test"

    def test_llm_api_key_takes_precedence(self, clean_env):
        clean_env.setenv("LLM_PROVIDER", "dashscope")
        clean_env.setenv("DASHSCOPE_API_KEY", "sk-fallback")
        clean_env.setenv("LLM_API_KEY", "sk-explicit")
        assert load_config().llm.api_key == "sk-explicit"

    def test_explicit_overrides_win(self, clean_env):
        clean_env.setenv("LLM_PROVIDER", "dashscope")
        clean_env.setenv("LLM_MODEL", "qwen3.8-max")
        clean_env.setenv("LLM_BASE_URL", "https://example.invalid/v1")
        cfg = load_config()
        assert cfg.llm.model == "qwen3.8-max"
        assert cfg.llm.base_url == "https://example.invalid/v1"

    def test_missing_key_is_reported_without_value(self, clean_env, monkeypatch):
        # 隔离本机 .env（load_dotenv 会把真实 key 注入，干扰"缺 key"断言）
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)

        clean_env.setenv("LLM_PROVIDER", "dashscope")
        missing = validate_sensitive_config(load_config())
        assert any("DASHSCOPE" in m or "LLM_API_KEY" in m for m in missing)

    def test_extra_body_is_parsed(self, clean_env):
        clean_env.setenv("LLM_PROVIDER", "dashscope")
        clean_env.setenv(
            "LLM_EXTRA_BODY_JSON", '{"chat_template_kwargs": {"enable_thinking": false}}'
        )
        cfg = load_config()
        assert cfg.llm.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_invalid_extra_body_raises(self, clean_env):
        from usmarket.errors import ConfigError

        clean_env.setenv("LLM_EXTRA_BODY_JSON", "not-json")
        with pytest.raises(ConfigError):
            load_config()


class TestNormalizePayload:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("pre-market", "pre"),
            ("premarket", "pre"),
            ("盘前", "pre"),
            ("regular", "regular"),
            ("after-hours", "post"),
            ("closed", "closed"),
            ("market-open", "unknown"),
        ],
    )
    def test_market_phase_aliases(self, raw: str, expected: str):
        assert normalize_payload({"market_phase": raw})["market_phase"] == expected

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("fact", "fact"),
            ("FACT", "fact"),
            ("事实", "fact"),
            ("analysis", "analysis"),
            ("speculation", "speculation"),
            ("推测", "speculation"),
            ("guess", "analysis"),
        ],
    )
    def test_confidence_aliases(self, raw: str, expected: str):
        payload = {"top_news": [{"confidence": raw}]}
        assert normalize_payload(payload)["top_news"][0]["confidence"] == expected

    def test_unknown_confidence_defaults_to_analysis(self):
        payload = {"watchlist_moves": [{"confidence": "???"}]}
        assert normalize_payload(payload)["watchlist_moves"][0]["confidence"] == "analysis"

    def test_non_string_values_untouched(self):
        payload = {"market_phase": 123, "top_news": []}
        assert normalize_payload(payload)["market_phase"] == 123


class TestCoerceContent:
    def test_pre_market_alias_is_accepted(self):
        payload = {
            "date": "2026-10-26",
            "market_phase": "pre-market",
            "summary": "测试用概览，行情数据缺失。",
            "top_news": [],
            "sources": [],
            "xhs": {"title": "测试标题", "body": "测试正文", "tags": ["#美股"]},
        }
        content = coerce_content(payload)
        assert content.market_phase == "pre"

    def test_still_rejects_missing_summary(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            coerce_content({"date": "2026-10-26", "market_phase": "pre"})
