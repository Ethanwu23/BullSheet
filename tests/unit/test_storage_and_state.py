"""存储与状态机测试：合法迁移、非法迁移、原子写入、索引。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from usmarket.errors import StateTransitionError, StorageError
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import PublishTask, TaskStage, TaskStatus
from usmarket.storage.state_machine import (
    ALLOWED_TRANSITIONS,
    assert_transition,
    can_publish,
    can_transition,
)


# ---------- 状态机 ----------
@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        (TaskStatus.PENDING, TaskStatus.GENERATED, True),
        (TaskStatus.GENERATED, TaskStatus.REVIEW, True),
        (TaskStatus.REVIEW, TaskStatus.APPROVED, True),
        (TaskStatus.REVIEW, TaskStatus.REJECTED, True),
        (TaskStatus.APPROVED, TaskStatus.PUBLISHED, True),
        (TaskStatus.SCHEDULED, TaskStatus.PUBLISHED, True),
        (TaskStatus.PUBLISHED, TaskStatus.PENDING, False),
        (TaskStatus.REVIEW, TaskStatus.PUBLISHED, False),
        (TaskStatus.GENERATED, TaskStatus.APPROVED, False),
        (TaskStatus.REJECTED, TaskStatus.PUBLISHED, False),
    ],
)
def test_can_transition(current, target, expected):
    assert can_transition(current, target) is expected


def test_assert_transition_raises_on_illegal():
    with pytest.raises(StateTransitionError):
        assert_transition(TaskStatus.GENERATED, TaskStatus.PUBLISHED)


def test_can_publish_requires_approval():
    for status in TaskStatus:
        expected = status in {TaskStatus.APPROVED, TaskStatus.SCHEDULED}
        assert can_publish(status) is expected


def test_published_is_terminal():
    assert ALLOWED_TRANSITIONS[TaskStatus.PUBLISHED] == set()


# ---------- 存储 ----------
@pytest.fixture
def store(tmp_path: Path) -> FileTaskStore:
    return FileTaskStore(tmp_path / "data")


def test_save_and_get(store):
    task = PublishTask(date="2026-10-26", status=TaskStatus.PENDING)
    store.save(task)
    loaded = store.get("2026-10-26")
    assert loaded is not None
    assert loaded.date == "2026-10-26"
    assert loaded.created_at  # 自动填充


def test_get_missing_returns_none(store):
    assert store.get("1999-01-01") is None


def test_transition_persists_and_records_history(store):
    store.save(PublishTask(date="2026-10-26"))
    store.transition("2026-10-26", TaskStatus.GENERATED, note="生成完成")
    task = store.get("2026-10-26")
    assert task is not None
    assert task.status == TaskStatus.GENERATED
    assert task.history[-1].status == "generated"
    assert task.history[-1].note == "生成完成"


def test_illegal_transition_rejected_by_store(store):
    store.save(PublishTask(date="2026-10-26", status=TaskStatus.GENERATED))
    with pytest.raises(StateTransitionError):
        store.transition("2026-10-26", TaskStatus.PUBLISHED)


def test_transition_missing_task_raises(store):
    with pytest.raises(StorageError):
        store.transition("1999-01-01", TaskStatus.GENERATED)


def test_list_all_sorted(store):
    for date in ("2026-10-24", "2026-10-22", "2026-10-23"):
        store.save(PublishTask(date=date))
    dates = [t.date for t in store.list_all()]
    assert dates == ["2026-10-22", "2026-10-23", "2026-10-24"]


def test_index_rebuilt(store):
    store.save(PublishTask(date="2026-10-26", status=TaskStatus.REVIEW))
    index = (Path(store.data_dir) / "tasks.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in index.strip().splitlines()]
    assert rows[0]["date"] == "2026-10-26"
    assert rows[0]["status"] == "review"


def test_corrupt_task_file_raises(store):
    path = store.task_path("2026-10-26")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError):
        store.get("2026-10-26")


def test_atomic_write_leaves_no_tmp_file(store):
    store.save(PublishTask(date="2026-10-26"))
    tmp_files = list(Path(store.data_dir).rglob("*.tmp"))
    assert tmp_files == []


def test_task_serialization_roundtrip():
    task = PublishTask(
        date="2026-10-26",
        status=TaskStatus.APPROVED,
        stage=TaskStage.RENDER,
        generator="rule_based",
        content_fingerprint="abc123",
        warnings=["w1"],
        artifacts={"cover": "x.png"},
    )
    restored = PublishTask.from_dict(task.to_dict())
    assert restored.status == TaskStatus.APPROVED
    assert restored.generator == "rule_based"
    assert restored.artifacts == {"cover": "x.png"}
