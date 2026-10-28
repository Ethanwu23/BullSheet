"""内容生成服务。

**架构（ADR-016）**：行情数据不交给模型加工。流程为：
1. 规则式确定性生成全部结构化内容（指数、个股、来源、文案骨架）；
2. LLM 只承担两个窄任务：盘后总结（evening_summary）+ 要闻标题中译（headlines）；
3. 合并后过完整校验（数字可追溯 / 来源 / 合规），失败重试一次，仍失败沿用规则式内容。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from usmarket.ai.base import ProviderUnavailableError, extract_json
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
    """完整校验：数字 + 来源 + 合规 + 结构。返回错误列表（空表示通过）。"""
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


def _merge_llm_parts(
    base: DailyContent, payload: dict[str, Any]
) -> DailyContent:
    """把 LLM 的两个窄产物（总结 + 标题翻译）合并进规则式基础内容。

    只触碰 evening_summary 与 top_news[].headline 两处，其余字段一律保留
    规则式结果——行情数字不可能被模型改动（ADR-016）。
    """
    summary = payload.get("evening_summary")
    headlines = payload.get("headlines")

    if not isinstance(summary, str) or not summary.strip():
        raise ProviderUnavailableError("模型未输出 evening_summary")
    if not isinstance(headlines, list) or not headlines:
        raise ProviderUnavailableError("模型未输出 headlines")
    # 模型可能把输入的全部新闻都翻译（实测 qwen）：多于要闻数时取前 N 条即可
    if len(headlines) < len(base.top_news):
        raise ProviderUnavailableError(
            f"headlines 数量（{len(headlines)}）少于要闻数（{len(base.top_news)}）"
        )
    headlines = headlines[: len(base.top_news)]

    top_news = []
    for entry, zh in zip(base.top_news, headlines, strict=True):
        if not isinstance(zh, str) or not zh.strip():
            raise ProviderUnavailableError("存在空的翻译标题")
        # 保留规则式的【分类】前缀，替换英文标题为中文
        prefix = entry.headline.split("】", 1)[0] + "】" if "】" in entry.headline else ""
        top_news.append(entry.model_copy(update={"headline": prefix + zh.strip()}))

    return base.model_copy(
        update={
            "evening_summary": summary.strip(),
            "top_news": top_news,
            "generator": "hybrid",
        }
    )


def generate_daily_content(
    cfg: AppConfig,
    snapshot: QuoteSnapshot,
    news_items: list,
    *,
    now: datetime | None = None,
    provider: Any | None = None,
    fallback_on_invalid: bool = True,
) -> tuple[DailyContent, list[str]]:
    """生成每日内容：规则式基础 + LLM 窄任务（总结/翻译）合并。"""
    warnings: list[str] = []
    user_prompt, sources = build_user_prompt(cfg, snapshot, news_items)

    # 1) 规则式基础内容（数字全部来自行情快照与新闻原文，确定性生成）
    content = _rule_based(cfg, snapshot, news_items, sources, now)

    # 2) LLM 窄任务：总结 + 翻译
    prov = provider if provider is not None else build_provider(cfg)
    if prov is not None:
        merged: DailyContent | None = None
        last_error: Exception | None = None
        # LLM 输出偶发不合法（实测 qwen3.8-flash），重试一次再沿用规则式内容
        for attempt in (1, 2):
            try:
                raw = prov.generate(SYSTEM_PROMPT, user_prompt)
                payload = extract_json(raw)
                if not isinstance(payload, dict):
                    raise ProviderUnavailableError("模型输出不是合法 JSON")
                candidate = _merge_llm_parts(content, payload)
                errors = validate_content(
                    candidate, snapshot, news_items=news_items, cfg=cfg
                )
                if errors:
                    raise ProviderUnavailableError(
                        "LLM 内容校验失败: " + "; ".join(errors[:3])
                    )
                merged = candidate
                break
            except Exception as exc:  # noqa: BLE001 - 任何 LLM 异常都应降级而非中断
                last_error = exc
                LOGGER.warning(
                    "LLM 窄任务失败（第 %d 次）: %s", attempt, exc,
                    extra={"stage": "generate"},
                )
        if merged is not None:
            content = merged
        else:
            warnings.append(
                f"LLM 总结/翻译失败，沿用规则式内容: {type(last_error).__name__}"
            )
            LOGGER.warning(
                "LLM 窄任务失败，沿用规则式内容: %s", last_error,
                extra={"stage": "generate"},
            )

    # 3) 最终校验（规则式基础必然通过；防回归）
    errors = validate_content(content, snapshot, news_items=news_items, cfg=cfg)
    if errors:
        raise ValidationError(
            "内容校验未通过（已阻止产出）", detail="; ".join(errors)
        )

    if content.low_confidence:
        warnings.append(
            "可用新闻不足或行情缺失，内容标记为 low_confidence，必须人工复核后再发布"
        )

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
