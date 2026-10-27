"""存储迁移 CLI 辅助。

用法（模块方式）：
    python -m usmarket.storage.migrate --data-dir data --db state/tasks.db
"""

from __future__ import annotations

import argparse
from pathlib import Path

from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.sqlite_store import SqliteTaskStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把文件任务存储迁移到 SQLite（幂等）")
    parser.add_argument("--data-dir", default="data", help="文件存储根目录")
    parser.add_argument("--db", default="state/tasks.db", help="SQLite 目标路径")
    args = parser.parse_args(argv)

    source = FileTaskStore(Path(args.data_dir))
    tasks = source.list_all()
    print(f"发现 {len(tasks)} 条文件任务")

    with SqliteTaskStore(Path(args.db)) as store:
        migrated = store.migrate_from_files(Path(args.data_dir))
        print(f"已迁移 {migrated} 条到 {args.db}（schema v{store.schema_version()}）")
        print(f"校验：SQLite 中共 {len(store.list_all())} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
