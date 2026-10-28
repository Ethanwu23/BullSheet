"""内容生成服务：Provider 选择、解析、校验与兜底。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from usmarket.ai.base import ProviderUnavailableError, coerce_content, extract_json
from usmarket.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from usmarket.ai.rule_based import generate_content as rule_based_generate
from usmarket.config import AppConfig
from usmarket.errors import ValidationError
from usmarket.market_data.models import QuoteSnapshot
from usmarket.validation.compliance import validate_compliance
from usmarket.validation.numbers import validate_numbers
from usmarket.validation.schema import DailyContent, SourceRef
from usmarket.validation.sources import validate_sources

LOGGER = logging.getLogger(__name__)


def build_provider(cfg: AppConfig) -> Any:
    """按配置构造 LLM provider。"""
    name = (cfg.llm.provider or "rule_based").lower()
    if name == "rule_based" or cfg.offline:
        return None
    if name in {"openai_compatible", "dashscope"}:
        # dashscope 只是 openai_compatible 的预设别名（端点/模型/密钥来源不同）
        from usmarket.ai.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(cfg.llm)
    if name == "anthropic":
        from usmarket.ai.anthropic import AnthropicProvider

        return AnthropicProvider(cfg.llm)
    LOGGER.warning("未知 LLM provider: %s，回退到规则式生成", name)
    return None


def _input_texts(news_items: list) -> list[str]:
    return [f"{item.title} {item.summary}" for item in news_items]


def validate_content(
    content: DailyContent,
    snapshot: QuoteSnapshot | None,
    *,
    news_items: list,
    cfg: AppConfig,
) -> list[str]:
    """完整校验：结构 + 数字 + 来源 + 合规。返回错误列表（空表示通过）。"""
    errors: list[str] = []

    issues_numbers = validate_numbers(
        content, snapshot, input_texts=_input_texts(news_items)
    )
    errors += [f"[数字] {issue}" for issue in issues_numbers]

    errors += [f"[来源] {issue}" for issue in validate_sources(content)]
    errors += [f"[合规] {issue}" for issue in validate_compliance(content)]

    # 数量约束
    if len(content.top_news) > cfg.content.top_news_max:
        errors.append(f"[结构] top_news 超过上限 {cfg.content.top_news_max}")
    if len(content.top_news) < cfg.content.top_news_min and not content.low_confidence:
        errors.append(
            f"[结构] top_news 少于下限 {cfg.content.top_news_min} 且未标记 low_confidence"
        )
    if len(content.xhs.title) > cfg.content.title_max_chars:
        errors.append(f"[结构] 标题超过 {cfg.content.title_max_chars} 字")

    return errors


def generate_daily_content(
    cfg: AppConfig,
    snapshot: QuoteSnapshot,
    news_items: list,
    *,
    now: datetime | None = None,
    provider: Any | None = None,
    fallback_on_invalid: bool = True,
) -> tuple[DailyContent, list[str]]:
    """生成并校验每日内容。

    返回 (内容, 警告列表)。校验失败时抛 ValidationError。
    """
    warnings: list[str] = []
    user_prompt, sources = build_user_prompt(cfg, snapshot, news_items)
    _input_texts(news_items)

    prov = provider if provider is not None else build_provider(cfg)

    if prov is not None:
        content = None
        last_error: Exception | None = None
        # LLM 输出偶发不合法（实测 qwen3.8-flash 约几%概率），重试一次再回退，
        # 避免单次抖动导致当天内容质量降级。
        for attempt in (1, 2):
            try:
                raw = prov.generate(SYSTEM_PROMPT, user_prompt)
                payload = extract_json(raw)
                if payload is None:
                    raise ProviderUnavailableError("模型输出不是合法 JSON")
                payload.setdefault("date", snapshot.date)
                payload.setdefault("market_phase", snapshot.market_phase.value)
                payload.setdefault("disclaimer", cfg.content.disclaimer)
                payload.setdefault(
                    "sources", [s.model_dump(mode="json") for s in sources]
                )
                payload.setdefault("evening_summary", "")
                payload.setdefault("generator", getattr(prov, "name", "llm"))
                content = coerce_content(payload)
                # 模型漏写盘后总结时，用规则式拼接补齐（数字同源，可过校验）
                if not content.evening_summary:
                    rule = _rule_based(cfg, snapshot, news_items, sources, now)
                    content = content.model_copy(
                        update={"evening_summary": rule.evening_summary}
                    )
                break
            except Exception as exc:  # noqa: BLE001 - 任何 LLM 异常都应回退而非中断
                last_error = exc
                LOGGER.warning(
                    "LLM 生成失败（第 %d 次）: %s", attempt, exc,
                    extra={"stage": "generate"},
                )
        if content is None:
            warnings.append(
                f"LLM 生成失败，已回退规则式生成: {type(last_error).__name__}"
            )
            LOGGER.warning(
                "LLM 生成失败，回退规则式生成: %s",
                last_error,
                extra={"stage": "generate"},
            )
            content = _rule_based(cfg, snapshot, news_items, sources, now)
        else:
            errors = validate_content(content, snapshot, news_items=news_items, cfg=cfg)
            if errors:
                warnings.append("LLM 输出未通过校验，已回退规则式生成")
                LOGGER.warning(
                    "LLM 输出校验失败: %s", "; ".join(errors), extra={"stage": "validation"}
                )
                if fallback_on_invalid:
                    content = _rule_based(cfg, snapshot, news_items, sources, now)
                else:
                    raise ValidationError("内容校验未通过", detail="; ".join(errors))
    else:
        content = _rule_based(cfg, snapshot, news_items, sources, now)

    errors = validate_content(content, snapshot, news_items=news_items, cfg=cfg)
    if errors:
        raise ValidationError(
            "内容校验未通过（已阻止发布）", detail="; ".join(errors)
        )

    if content.low_confidence:
        warnings.append(
            "可用新闻不足或行情缺失，内容标记为 low_confidence，必须人工复核后再发布"
        )
    if content.generator != "rule_based" and any("回退" in w for w in warnings):
        pass

    LOGGER.info(
        "内容生成完成 generator=%s 要闻=%d 低置信=%s",
        content.generator, len(content.top_news), content.low_confidence,
        extra={"stage": "generate"},
    )
    return content, warnings


def _rule_based(
    cfg: AppConfig,
    snapshot: QuoteSnapshot,
    news_items: list,
    sources: list[SourceRef],
    now: datetime | None,
) -> DailyContent:
    content = rule_based_generate(cfg, snapshot, news_items, sources=sources, now=now)
    return content.model_copy(update={"generator": "rule_based"})
