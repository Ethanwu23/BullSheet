"""LLM Provider 抽象与 JSON 输出修复。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol, runtime_checkable

from usmarket.validation.schema import DailyContent

LOGGER = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """返回原始文本（由 service 负责解析为 DailyContent）。"""
        ...


def extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出中提取 JSON 对象。

    依次尝试：直接解析 → ```json 代码块 → 首个 { 到最后一个 }。
    """
    text = (text or "").strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


class ProviderUnavailableError(Exception):
    """Provider 不可用（缺 key / 网络失败 / 返回非法内容）。"""


# 模型常输出枚举的"同义写法"（实测 qwen 会输出 pre-market），
# 直接校验失败会无谓地回退到规则式生成，因此先做归一化。
_MARKET_PHASE_ALIASES = {
    "pre": "pre",
    "pre-market": "pre",
    "premarket": "pre",
    "pre_market": "pre",
    "before_open": "pre",
    "盘前": "pre",
    "regular": "regular",
    "regular-market": "regular",
    "regular_market": "regular",
    "open": "regular",
    "intraday": "regular",
    "盘中": "regular",
    "post": "post",
    "post-market": "post",
    "postmarket": "post",
    "after_hours": "post",
    "after-hours": "post",
    "盘后": "post",
    "closed": "closed",
    "close": "closed",
    "收盘": "closed",
    "unknown": "unknown",
}

_CONFIDENCE_ALIASES = {
    "fact": "fact",
    "facts": "fact",
    "factual": "fact",
    "事实": "fact",
    "analysis": "analysis",
    "analyze": "analysis",
    "分析": "analysis",
    "speculation": "speculation",
    "speculative": "speculation",
    "推测": "speculation",
    "猜测": "speculation",
}


def _normalize_enum(value: Any, table: dict[str, str], default: str) -> Any:
    if not isinstance(value, str):
        return value
    key = value.strip().lower().replace(" ", "")
    return table.get(key, table.get(value.strip().lower(), default))


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把模型输出中的枚举同义写法归一化为 schema 允许值。"""
    data = dict(payload)
    if "market_phase" in data:
        data["market_phase"] = _normalize_enum(
            data["market_phase"], _MARKET_PHASE_ALIASES, "unknown"
        )
    for key in ("top_news", "watchlist_moves", "earnings_and_macro"):
        entries = data.get(key)
        if not isinstance(entries, list):
            continue
        normalized: list[Any] = []
        for entry in entries:
            if isinstance(entry, dict) and "confidence" in entry:
                entry = dict(entry)
                entry["confidence"] = _normalize_enum(
                    entry["confidence"], _CONFIDENCE_ALIASES, "analysis"
                )
            normalized.append(entry)
        data[key] = normalized
    return data


def coerce_content(payload: dict[str, Any]) -> DailyContent:
    """把模型输出强制转换为 DailyContent；失败时抛出 ValueError。

    先归一化枚举同义写法，再做严格校验：既容忍模型措辞差异，
    又不放松对数字、来源与合规的要求。
    """
    return DailyContent.model_validate(normalize_payload(payload))
