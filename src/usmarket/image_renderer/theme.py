"""主题配置：颜色、字体、账号名称（可通过配置文件调整，FR-032）。"""

from __future__ import annotations

from dataclasses import dataclass

from usmarket.config import ThemeConfig


@dataclass(frozen=True)
class ResolvedTheme:
    background: str
    surface: str
    accent: str
    positive: str
    negative: str
    text_primary: str
    text_secondary: str
    muted: str
    font_regular: str
    font_bold: str

    @classmethod
    def from_config(cls, cfg: ThemeConfig) -> ResolvedTheme:
        return cls(
            background=cfg.background,
            surface=cfg.surface,
            accent=cfg.accent,
            positive=cfg.positive,
            negative=cfg.negative,
            text_primary=cfg.text_primary,
            text_secondary=cfg.text_secondary,
            muted=cfg.muted,
            font_regular=cfg.font_regular,
            font_bold=cfg.font_bold,
        )


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError(f"非法颜色值: {value!r}")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
