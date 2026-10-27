"""发布适配器接口。

发布能力与采集/生成完全解耦：适配器只接收 PublishPayload，
不 import collectors / ai（FR-034）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class PublishPayload:
    date: str
    title: str
    body: str
    tags: tuple[str, ...]
    images: tuple[Path, ...]
    content_fingerprint: str
    idempotency_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            object.__setattr__(
                self, "idempotency_key", f"{self.date}:{self.content_fingerprint}"
            )


@dataclass(frozen=True)
class PublishOutcome:
    success: bool
    task_id: str
    simulated: bool
    verified: bool          # 是否经过真实平台验证
    remote_id: str = ""
    error: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Publisher(Protocol):
    name: str
    simulated: bool
    verified: bool

    def validate_content(self, payload: PublishPayload) -> list[str]:
        """校验待发布内容，返回错误列表（空表示通过）。"""
        ...

    def upload_images(self, payload: PublishPayload) -> tuple[str, ...]:
        """上传图片，返回远端标识列表。"""
        ...

    def create_draft(self, payload: PublishPayload, image_ids: tuple[str, ...]) -> str:
        """创建草稿，返回草稿 ID。"""
        ...

    def publish(self, payload: PublishPayload) -> PublishOutcome:
        """发布。"""
        ...

    def get_publish_status(self, task_id: str) -> str:
        """查询发布状态。"""
        ...


def compute_fingerprint(
    date: str, news_urls: list[str], quote_values: list[str]
) -> str:
    """内容指纹：日期 + 排序后的新闻 URL + 行情关键数字。"""
    canonical = json.dumps(
        {
            "date": date,
            "news": sorted(set(news_urls)),
            "quotes": sorted(set(quote_values)),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()
