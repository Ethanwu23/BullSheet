"""统一异常类型。

区分失败阶段是为了让"采集失败 / 生成失败 / 图片失败 / 发布失败"可以分别定位（FR-066）。
"""

from __future__ import annotations


class USMarketError(Exception):
    """项目基础异常。"""

    stage: str = "unknown"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigError(USMarketError):
    stage = "config"


class CollectionError(USMarketError):
    stage = "collect"


class MarketDataError(USMarketError):
    stage = "market_data"


class ContentGenerationError(USMarketError):
    stage = "generate"


class ValidationError(USMarketError):
    stage = "validation"


class RenderError(USMarketError):
    stage = "render"


class PublishError(USMarketError):
    stage = "publish"


class StorageError(USMarketError):
    stage = "storage"


class StateTransitionError(USMarketError):
    stage = "storage"


class FontMissingError(RenderError):
    """找不到可用的中文字体。"""

    def __init__(self, searched: list[str]) -> None:
        super().__init__(
            "未找到可用的中文字体，无法渲染图片。"
            "请在系统安装中文字体，或运行 `python scripts/fetch_fonts.py` 下载 Noto Sans SC。",
            detail=f"已尝试路径: {searched}",
        )
        self.searched = searched
