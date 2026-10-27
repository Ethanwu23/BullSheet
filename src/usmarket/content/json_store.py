"""内容 JSON 落盘与读取（与原始行情分开存储）。"""

from __future__ import annotations

import json
from pathlib import Path

from usmarket.validation.schema import DailyContent


def save_content(content: DailyContent, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(content.to_dict(), fh, ensure_ascii=False, indent=2)
    return path


def load_content(path: Path) -> DailyContent:
    with path.open("r", encoding="utf-8") as fh:
        return DailyContent.from_dict(json.load(fh))
