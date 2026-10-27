"""文件 + JSONL 任务存储（默认后端）。

并发安全：写入临时文件后原子替换；进程内用简单文件锁避免并发写。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from usmarket.errors import StorageError
from usmarket.storage.models import PublishTask, TaskStatus
from usmarket.storage.state_machine import assert_transition

try:  # pragma: no cover - Windows 无 fcntl
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

INDEX_FILENAME = "tasks.jsonl"
TASK_FILENAME = "task.json"
LOCK_FILENAME = ".tasks.lock"


class _FileLock:
    """跨平台尽力而为的文件锁。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def __enter__(self) -> _FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")  # noqa: SIM115
        if fcntl is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
            except OSError:
                # 平台不支持 flock：退化为尽力而为（配合原子替换保证一致性）
                pass
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is None:
            return
        if fcntl is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        self._fh.close()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink(missing_ok=True)


class FileTaskStore:
    """按日期目录存储任务。"""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / INDEX_FILENAME
        self.lock_path = self.data_dir / LOCK_FILENAME

    # ---------- 路径 ----------
    def day_dir(self, date: str) -> Path:
        return self.data_dir / date

    def task_path(self, date: str) -> Path:
        return self.day_dir(date) / TASK_FILENAME

    # ---------- 读写 ----------
    def get(self, date: str) -> PublishTask | None:
        path = self.task_path(date)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                return PublishTask.from_dict(json.load(fh))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise StorageError(f"任务文件损坏: {path}") from exc

    def save(self, task: PublishTask) -> PublishTask:
        task.updated_at = datetime.now().astimezone().isoformat()
        if not task.created_at:
            task.created_at = task.updated_at
        with _FileLock(self.lock_path):
            _atomic_write_json(self.task_path(task.date), task.to_dict())
            self._rebuild_index()
        return task

    def transition(
        self, date: str, target: TaskStatus, *, note: str = "", **fields: Any
    ) -> PublishTask:
        """状态迁移（校验合法性）。"""
        with _FileLock(self.lock_path):
            task = self.get(date)
            if task is None:
                raise StorageError(f"任务不存在: {date}")
            assert_transition(task.status, target)
            task.status = target
            for key, value in fields.items():
                setattr(task, key, value)
            task.add_history(target, note)
            _atomic_write_json(self.task_path(date), task.to_dict())
            self._rebuild_index()
        return task

    def list_all(self) -> list[PublishTask]:
        tasks: list[PublishTask] = []
        if not self.data_dir.exists():
            return tasks
        for path in sorted(self.data_dir.glob(f"*/{TASK_FILENAME}")):
            try:
                with path.open("r", encoding="utf-8") as fh:
                    tasks.append(PublishTask.from_dict(json.load(fh)))
            except (json.JSONDecodeError, KeyError, ValueError):
                LOGGER.warning("跳过损坏的任务文件: %s", path)
        return sorted(tasks, key=lambda t: t.date)

    def _rebuild_index(self) -> None:
        """重建 JSONL 索引（供 CLI 快速查询）。"""
        rows: list[dict[str, Any]] = []
        for task in self.list_all():
            rows.append(
                {
                    "date": task.date,
                    "status": task.status.value,
                    "stage": task.stage.value,
                    "generator": task.generator,
                    "fingerprint": task.content_fingerprint,
                    "error": task.error,
                    "updated_at": task.updated_at,
                }
            )
        tmp = self.index_path.with_suffix(".jsonl.tmp")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, self.index_path)
