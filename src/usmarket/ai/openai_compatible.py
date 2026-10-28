"""OpenAI 兼容 Chat Completions provider。

覆盖 OpenAI / DeepSeek / OpenRouter / 通义 / Moonshot / Groq / GitHub Models 等
所有实现 /v1/chat/completions 的端点。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from usmarket.config import LLMConfig

LOGGER = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, cfg: LLMConfig, *, session: requests.Session | None = None) -> None:
        self.cfg = cfg
        self._session = session

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.cfg.api_key:
            raise RuntimeError("未配置 LLM_API_KEY")

        base = self.cfg.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        # 厂商特有参数（如百炼 enable_thinking），由 LLM_EXTRA_BODY_JSON 注入
        if getattr(self.cfg, "extra_body", None):
            payload.update(self.cfg.extra_body)
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }

        sess = self._session or requests.Session()
        try:
            resp = sess.post(url, json=payload, headers=headers, timeout=self.cfg.timeout_seconds)
        except requests.RequestException as exc:
            raise RuntimeError(f"LLM 请求失败: {type(exc).__name__}") from exc
        finally:
            if self._session is None:
                sess.close()

        if resp.status_code >= 400:
            # 不打印响应体（可能含敏感信息），只记录状态码
            raise RuntimeError(f"LLM 返回错误状态码: {resp.status_code}")

        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish = choice.get("finish_reason")
            usage = data.get("usage", {})
            # 诊断信息：截断（finish_reason=length）是"输出不是合法 JSON"的常见根因
            LOGGER.info(
                "LLM 响应: finish_reason=%s content_len=%s completion_tokens=%s",
                finish,
                len(content or ""),
                usage.get("completion_tokens"),
                extra={"stage": "generate"},
            )
            if finish == "length":
                raise RuntimeError(
                    "LLM 输出被 max_tokens 截断（finish_reason=length），"
                    "请调大 LLM_MAX_TOKENS"
                )
            return content
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise RuntimeError(f"LLM 响应结构异常: {type(exc).__name__}") from exc
