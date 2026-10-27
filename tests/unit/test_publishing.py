"""发布测试：模拟成功/失败、幂等、重试、未审核拦截、凭据不泄露。"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from usmarket.errors import PublishError
from usmarket.publishing.base import PublishPayload, compute_fingerprint
from usmarket.publishing.mock import MockPublisher
from usmarket.publishing.retry import retry_with_backoff
from usmarket.publishing.service import publish_task
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import PublishTask, TaskStatus


@pytest.fixture
def images(tmp_path: Path) -> list[Path]:
    paths = []
    for name in ("cover.png", "page_01.png", "page_02.png"):
        p = tmp_path / name
        p.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        paths.append(p)
    return paths


@pytest.fixture
def payload(images) -> PublishPayload:
    fp = compute_fingerprint("2026-10-26", ["https://a.com/1"], ["NVDA:186.42:2.37"])
    return PublishPayload(
        date="2026-10-26",
        title="美股收盘｜标普500 +0.61%",
        body="正文",
        tags=("#美股",),
        images=tuple(images),
        content_fingerprint=fp,
    )


@pytest.fixture
def store(tmp_path: Path) -> FileTaskStore:
    return FileTaskStore(tmp_path / "data")


def _approved(store: FileTaskStore, payload: PublishPayload) -> PublishTask:
    task = PublishTask(date="2026-10-26", status=TaskStatus.REVIEW)
    store.save(task)
    store.transition("2026-10-26", TaskStatus.APPROVED, note="ok")
    task = store.get("2026-10-26")
    assert task is not None
    task.content_fingerprint = payload.content_fingerprint
    store.save(task)
    return store.get("2026-10-26")  # type: ignore[return-value]


# ---------- 模拟发布 ----------
def test_mock_publish_success(offline_cfg, store, payload):
    task = _approved(store, payload)
    outcome = publish_task(offline_cfg, store, task, payload, publisher=MockPublisher())
    assert outcome.success is True
    assert outcome.simulated is True
    assert outcome.verified is False  # 从未真实验证过
    updated = store.get("2026-10-26")
    assert updated.status == TaskStatus.PUBLISHED


def test_mock_publish_failure_recorded(offline_cfg, store, payload):
    task = _approved(store, payload)
    publisher = MockPublisher(fail_first=10)
    outcome = publish_task(
        offline_cfg, store, task, payload, publisher=publisher, sleep=lambda _: None
    )
    assert outcome.success is False
    updated = store.get("2026-10-26")
    assert updated.status == TaskStatus.FAILED
    assert updated.error


def test_publish_requires_approval(offline_cfg, store, payload):
    store.save(PublishTask(date="2026-10-26", status=TaskStatus.GENERATED))
    task = store.get("2026-10-26")
    with pytest.raises(PublishError) as exc:
        publish_task(offline_cfg, store, task, payload, publisher=MockPublisher())
    assert "未通过审核" in str(exc.value)
    # 状态未被改变
    assert store.get("2026-10-26").status == TaskStatus.GENERATED


def test_publish_idempotent(offline_cfg, store, payload):
    """重复发布会命中幂等，不产生第二条记录（SC-005）。"""
    task = _approved(store, payload)
    publisher = MockPublisher()
    publish_task(offline_cfg, store, task, payload, publisher=publisher)
    task = store.get("2026-10-26")
    first_count = len(task.publish_records)

    # 即便状态被强行改回 approved，相同指纹也不应重复发布
    task.status = TaskStatus.APPROVED
    store.save(task)
    outcome = publish_task(offline_cfg, store, task, payload, publisher=publisher)
    assert outcome.success is True
    assert outcome.detail.get("skipped") is True
    assert publisher.published == [f"mock-{payload.content_fingerprint[:12]}"]
    assert len(store.get("2026-10-26").publish_records) == first_count


def test_retry_does_not_duplicate_on_eventual_success(offline_cfg, store, payload):
    """失败后重试成功，只产生一条成功记录。"""
    task = _approved(store, payload)
    outcome = publish_task(
        offline_cfg, store, task, payload,
        publisher=MockPublisher(fail_first=2), sleep=lambda _: None,
    )
    assert outcome.success is True
    assert outcome.detail["calls"] == 3
    records = store.get("2026-10-26").publish_records
    assert len(records) == 1


# ---------- 重试退避 ----------
def test_retry_with_backoff_success_on_third_try():
    calls = {"n": 0}
    delays: list[float] = []

    def flaky():
        calls["n"] += 1
        from usmarket.publishing.base import PublishOutcome

        return PublishOutcome(
            success=calls["n"] >= 3, task_id="t", simulated=True, verified=False
        )

    result = retry_with_backoff(flaky, max_retries=3, backoff_seconds=1.0, sleep=delays.append)
    assert result.success is True
    assert calls["n"] == 3
    assert delays == [1.0, 2.0]  # 指数退避


def test_retry_stops_at_max_retries():
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        from usmarket.publishing.base import PublishOutcome

        return PublishOutcome(success=False, task_id="t", simulated=True, verified=False)

    result = retry_with_backoff(
        always_fail, max_retries=3, backoff_seconds=0.01, sleep=lambda _: None
    )
    assert result.success is False
    assert calls["n"] == 3


# ---------- 内容校验 ----------
def test_validate_content_rejects_empty_title():
    publisher = MockPublisher()
    payload = PublishPayload(
        date="2026-10-26", title="", body="b", tags=(), images=(), content_fingerprint="x"
    )
    errors = publisher.validate_content(payload)
    assert any("标题" in e for e in errors)


def test_validate_content_rejects_missing_images(tmp_path):
    publisher = MockPublisher()
    payload = PublishPayload(
        date="2026-10-26", title="t", body="b", tags=(),
        images=(tmp_path / "nope.png",), content_fingerprint="x",
    )
    assert any("图片不存在" in e for e in publisher.validate_content(payload))


# ---------- 凭据不泄露 ----------
def test_credentials_not_logged(offline_cfg, store, payload, caplog):
    task = _approved(store, payload)
    with caplog.at_level(logging.DEBUG):
        publish_task(offline_cfg, store, task, payload, publisher=MockPublisher())
    joined = "\n".join(record.getMessage() for record in caplog.records)
    for secret in ("cookie", "token", "password", "authorization", "Bearer"):
        assert secret.lower() not in joined.lower()


# ---------- 指纹 ----------
def test_fingerprint_is_order_insensitive():
    a = compute_fingerprint("2026-10-26", ["u2", "u1"], ["q1", "q2"])
    b = compute_fingerprint("2026-10-26", ["u1", "u2"], ["q2", "q1"])
    assert a == b


def test_fingerprint_changes_with_content():
    a = compute_fingerprint("2026-10-26", ["u1"], ["q1"])
    b = compute_fingerprint("2026-10-26", ["u1"], ["q1", "q2"])
    assert a != b


# ---------- browser 适配器明确不可用 ----------
def test_browser_publisher_is_not_verified():
    from usmarket.publishing.browser import BrowserPublisher

    publisher = BrowserPublisher(enabled=False)
    assert publisher.verified is False
    assert publisher.simulated is True

    payload = PublishPayload(
        date="2026-10-26", title="t", body="b", tags=(), images=(), content_fingerprint="x"
    )
    outcome = publisher.publish(payload)
    assert outcome.success is False
    assert outcome.verified is False
    assert "未实现" in outcome.error


def test_manual_export_writes_bundle(tmp_path, payload):
    from usmarket.publishing.manual_export import ManualExportPublisher

    publisher = ManualExportPublisher(tmp_path / "export")
    outcome = publisher.publish(payload)
    assert outcome.success is True
    assert outcome.verified is False
    assert (tmp_path / "export" / "publish_bundle.json").exists()
    assert (tmp_path / "export" / "HOW_TO_PUBLISH.md").exists()
