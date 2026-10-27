"""Anthropic Messages API provider。"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from usmarket.config import LLMConfig

LOGGER = logging.getLogger(__name__)

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, cfg: LLMConfig, *, session: requests.Session | None = None) -> None:
        self.cfg = cfg
        self._session = session

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        api_key = self.cfg.anthropic_api_key
        if not api_key:
            raise RuntimeError("未配置 ANTHROPIC_API_KEY")

        url = "https://api.anthropic.com/v1/messages"
        payload: dict[str, Any] = {
            "model": self.cfg.anthropic_model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        sess = self._session or requests.Session()
        try:
            resp = sess.post(url, json=payload, headers=headers, timeout=self.cfg.timeout_seconds)
        except requests.RequestException as exc:
            raise RuntimeError(f"Anthropic 请求失败: {type(exc).__name__}") from exc
        finally:
            if self._session is None:
                sess.close()

        if resp.status_code >= 400:
            raise RuntimeError(f"Anthropic 返回错误状态码: {resp.status_code}")

        try:
            data = resp.json()
            return data["content"][0]["text"]
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise RuntimeError(f"Anthropic 响应结构异常: {type(exc).__name__}") from exc
