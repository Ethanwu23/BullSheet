"""SQLite 任务存储（可选后端）。

与 FileTaskStore 接口一致，便于在任务量大或需要并发查询时切换。
提供 migrate_from_files()，可从文件后端幂等迁移（FR-060）。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from usmarket.errors import StorageError
from usmarket.storage.models import PublishTask, TaskStatus
from usmarket.storage.state_machine import assert_transition

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    date        TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    stage       TEXT NOT NULL,
    generator   TEXT,
    fingerprint TEXT,
    error       TEXT,
    payload     TEXT NOT NULL,
    created_at  TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks(updated_at);
"""


class SqliteTaskStore:
    """SQLite 后端任务存储。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self._conn.commit()

    # ---------- 基础 ----------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteTaskStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    # ---------- 读写 ----------
    def get(self, date: str) -> PublishTask | None:
        row = self._conn.execute("SELECT payload FROM tasks WHERE date=?", (date,)).fetchone()
        if row is None:
            return None
        try:
            return PublishTask.from_dict(json.loads(row["payload"]))
        except (json.JSONDecodeError, ValueError) as exc:
            raise StorageError(f"任务数据损坏: {date}") from exc

    def save(self, task: PublishTask) -> PublishTask:
        now = datetime.now().astimezone().isoformat()
        task.updated_at = now
        if not task.created_at:
            task.created_at = now
        payload = json.dumps(task.to_dict(), ensure_ascii=False)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks(date, status, stage, generator, fingerprint, error,
                                  payload, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(date) DO UPDATE SET
                    status=excluded.status,
                    stage=excluded.stage,
                    generator=excluded.generator,
                    fingerprint=excluded.fingerprint,
                    error=excluded.error,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    task.date,
                    task.status.value,
                    task.stage.value,
                    task.generator,
                    task.content_fingerprint,
                    task.error,
                    payload,
                    task.created_at,
                    task.updated_at,
                ),
            )
        return task

    def transition(
        self, date: str, target: TaskStatus, *, note: str = "", **fields: Any
    ) -> PublishTask:
        task = self.get(date)
        if task is None:
            raise StorageError(f"任务不存在: {date}")
        assert_transition(task.status, target)
        task.status = target
        for key, value in fields.items():
            setattr(task, key, value)
        task.add_history(target, note)
        return self.save(task)

    def list_all(self) -> list[PublishTask]:
        rows = self._conn.execute("SELECT payload FROM tasks ORDER BY date").fetchall()
        tasks: list[PublishTask] = []
        for row in rows:
            try:
                tasks.append(PublishTask.from_dict(json.loads(row["payload"])))
            except (json.JSONDecodeError, ValueError):
                LOGGER.warning("跳过损坏的任务记录")
        return tasks

    # ---------- 迁移 ----------
    def migrate_from_files(self, data_dir: Path) -> int:
        """从文件后端迁移（按 date upsert，可重复执行）。"""
        from usmarket.storage.file_store import FileTaskStore

        source = FileTaskStore(Path(data_dir))
        count = 0
        for task in source.list_all():
            self.save(task)
            count += 1
        LOGGER.info("已从文件存储迁移 %d 条任务到 %s", count, self.db_path)
        return count
