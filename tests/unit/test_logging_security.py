"""日志安全测试：凭据绝不落日志（SC-007）。"""

from __future__ import annotations

import logging

from usmarket.logging_setup import REDACTED, RedactingFilter, redact, setup_logging


def test_redact_key_value_pairs():
    text = "api_key=sk-abc123456789 secret=topsecret password=hunter2"
    cleaned = redact(text)
    assert "sk-abc123456789" not in cleaned
    assert "topsecret" not in cleaned
    assert "hunter2" not in cleaned
    assert REDACTED in cleaned


def test_redact_json_style():
    text = '{"token": "abcdef123456", "api_key": "xyz"}'
    cleaned = redact(text)
    assert "abcdef123456" not in cleaned
    assert "xyz" not in cleaned


def test_redact_bearer_and_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    cleaned = redact(f"Authorization: Bearer {jwt}")
    assert jwt not in cleaned


def test_redact_github_and_openai_tokens():
    for token in ("ghp_abcdefghijklmnopqrstuvwxyz", "sk-abcdefghijklmnopqrst"):
        assert token not in redact(f"using {token} now")


def test_filter_redacts_log_record():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="connecting with password=%s", args=("s3cret",), exc_info=None,
    )
    RedactingFilter().filter(record)
    assert "s3cret" not in record.getMessage()


def test_setup_logging_writes_json_file(tmp_path):
    log_file = tmp_path / "run.log"
    setup_logging("INFO", log_file=log_file)
    logging.getLogger("usmarket.test").info("token=abcd1234 done")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "abcd1234" not in content
    assert "REDACTED" in content


def test_sensitive_values_not_in_task_error_message():
    """配置校验只返回键名，不返回值（FR-059）。"""
    import os

    from usmarket.config import load_config, validate_sensitive_config

    cfg = load_config(apply_env=False)
    from dataclasses import replace

    cfg = replace(cfg, llm=replace(cfg.llm, provider="openai_compatible", api_key=""))
    missing = validate_sensitive_config(cfg)
    assert "LLM_API_KEY" in missing
    assert all("=" not in m for m in missing)
    assert os.environ.get("LLM_API_KEY") not in missing
