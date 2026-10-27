"""结构化日志 + 凭据脱敏。

FR-062：日志不得输出密码、Token 或完整 Cookie。
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|cookie|authorization|credential)",
    re.IGNORECASE,
)

# 疑似凭据值：长 hex / JWT / Bearer 前缀
_VALUE_PATTERNS = (
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}"),  # JWT
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]{8,}"),
    re.compile(r"(?i)\b(sk|ghp|gho|github_pat)[-_][A-Za-z0-9]{12,}"),
    re.compile(r"(?i)\b[A-F0-9]{32,}\b"),
)

REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """对文本中的敏感键值与疑似凭据做脱敏。"""
    result = text
    # 支持 key=value / "key": "value" / 'key': 'value' 三种形式
    result = re.sub(
        rf"([\"']?{SENSITIVE_KEY_PATTERN.pattern}[\"']?)\s*[:=]\s*[\"']?([^\s,;\"'}}]+)",
        lambda m: f"{m.group(1)}={REDACTED}",
        result,
        flags=re.IGNORECASE,
    )
    for pattern in _VALUE_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


class RedactingFilter(logging.Filter):
    """日志脱敏过滤器。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # 先完整格式化，再做脱敏，避免"部分替换 + 残留 args"导致格式化参数不匹配
            message = redact(record.getMessage())
            record.msg = message
            record.args = ()
        except Exception:  # noqa: BLE001 - 日志不能因为脱敏失败而崩溃
            record.msg = "<log redaction error>"
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """JSON 结构化日志（FR-056）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        for key in ("stage", "date", "source", "symbol", "task_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{datetime.fromtimestamp(record.created, tz=UTC):%Y-%m-%d %H:%M:%S}"
            f" | {record.levelname:<7} | {record.name} | {redact(record.getMessage())}"
        )
        if record.exc_info:
            base += "\n" + redact(self.formatException(record.exc_info))
        return base


def setup_logging(level: str = "INFO", *, log_file: Path | None = None) -> None:
    """配置根 logger。"""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    text_handler = logging.StreamHandler(sys.stderr)
    text_handler.setFormatter(TextFormatter())
    root.addHandler(text_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    redacting = RedactingFilter()
    for handler in root.handlers:
        handler.addFilter(redacting)
    root.addFilter(redacting)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
