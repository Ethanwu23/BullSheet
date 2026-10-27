"""SQLite 后端与迁移测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from usmarket.errors import StateTransitionError
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import PublishTask, TaskStage, TaskStatus
from usmarket.storage.sqlite_store import SqliteTaskStore


@pytest.fixture
def sqlite_store(tmp_path: Path) -> SqliteTaskStore:
    store = SqliteTaskStore(tmp_path / "state" / "tasks.db")
    yield store
    store.close()


def test_schema_version(sqlite_store: SqliteTaskStore):
    assert sqlite_store.schema_version() >= 1


def test_save_and_get(sqlite_store: SqliteTaskStore):
    sqlite_store.save(PublishTask(date="2026-10-26", status=TaskStatus.PENDING))
    task = sqlite_store.get("2026-10-26")
    assert task is not None
    assert task.status == TaskStatus.PENDING


def test_upsert_does_not_duplicate(sqlite_store: SqliteTaskStore):
    sqlite_store.save(PublishTask(date="2026-10-26"))
    sqlite_store.save(PublishTask(date="2026-10-26", status=TaskStatus.REVIEW))
    assert len(sqlite_store.list_all()) == 1
    assert sqlite_store.get("2026-10-26").status == TaskStatus.REVIEW


def test_transition_validates(sqlite_store: SqliteTaskStore):
    sqlite_store.save(PublishTask(date="2026-10-26", status=TaskStatus.GENERATED))
    with pytest.raises(StateTransitionError):
        sqlite_store.transition("2026-10-26", TaskStatus.PUBLISHED)

    updated = sqlite_store.transition("2026-10-26", TaskStatus.REVIEW, note="ok")
    assert updated.status == TaskStatus.REVIEW
    assert updated.history[-1].status == "review"


def test_migrate_from_files_is_idempotent(sqlite_store: SqliteTaskStore, tmp_path: Path):
    files = FileTaskStore(tmp_path / "data")
    for date in ("2026-10-22", "2026-10-23"):
        files.save(
            PublishTask(
                date=date,
                status=TaskStatus.REVIEW,
                stage=TaskStage.RENDER,
                generator="rule_based",
                content_fingerprint=f"fp-{date}",
            )
        )

    first = sqlite_store.migrate_from_files(tmp_path / "data")
    second = sqlite_store.migrate_from_files(tmp_path / "data")
    assert first == 2
    assert second == 2
    assert len(sqlite_store.list_all()) == 2

    migrated = sqlite_store.get("2026-10-23")
    assert migrated is not None
    assert migrated.status == TaskStatus.REVIEW
    assert migrated.content_fingerprint == "fp-2026-10-23"


def test_migrate_script_entrypoint(tmp_path: Path, capsys):
    from usmarket.storage.migrate import main

    files = FileTaskStore(tmp_path / "data")
    files.save(PublishTask(date="2026-10-26"))

    code = main(
        ["--data-dir", str(tmp_path / "data"), "--db", str(tmp_path / "state" / "t.db")]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "已迁移 1 条" in out
