"""中文字体解析。

CI（ubuntu-latest）默认没有中文字体；本机 Windows 有 msyh.ttc / simhei.ttf。
缺失时报 FontMissingError，绝不产出乱码图片（FR-033）。
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from usmarket.config import PROJECT_ROOT
from usmarket.errors import FontMissingError

LOGGER = logging.getLogger(__name__)

ASSET_FONT_DIR = PROJECT_ROOT / "assets" / "fonts"

# 候选字体路径（按优先级）
CANDIDATE_PATHS: tuple[str, ...] = (
    # 用户显式指定
    "",
    # 项目自带
    str(ASSET_FONT_DIR / "NotoSansSC-Regular.ttf"),
    str(ASSET_FONT_DIR / "NotoSansSC-Bold.ttf"),
    str(ASSET_FONT_DIR / "SourceHanSansSC-Regular.otf"),
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux / CI
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
)

CJK_TEST_CHAR = "中"
NOTDEF_TEST_CHAR = "\ue000"  # 私有区字符，任何字体都没有


def _supports_cjk(font: ImageFont.FreeTypeFont) -> bool:
    """判断字体是否支持中文。

    对比"中"与私有区字符（必然 notdef）的渲染结果：一致说明"中"也是 notdef。
    """
    def render(ch: str) -> bytes:
        img = Image.new("L", (48, 48), 0)
        draw = ImageDraw.Draw(img)
        draw.text((4, 4), ch, font=font, fill=255)
        return img.tobytes()

    try:
        return render(CJK_TEST_CHAR) != render(NOTDEF_TEST_CHAR)
    except Exception:  # noqa: BLE001
        return False


def iter_font_candidates(explicit: str = "") -> list[str]:
    paths: list[str] = []
    env_font = os.environ.get("USMARKET_FONT_REGULAR", "")
    for value in (explicit, env_font):
        if value and Path(value).exists():
            paths.append(value)
    paths.extend(p for p in CANDIDATE_PATHS if p)
    # 扫描项目自带字体目录
    if ASSET_FONT_DIR.exists():
        for path in sorted(ASSET_FONT_DIR.glob("*.*")):
            if path.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                paths.append(str(path))
    seen: set[str] = set()
    unique: list[str] = []
    for p in paths:
        key = str(Path(p).resolve()) if Path(p).exists() else p
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


@lru_cache(maxsize=64)
def resolve_font(explicit: str = "", *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """解析支持中文的字体；找不到则抛 FontMissingError。"""
    candidates = iter_font_candidates(explicit)
    searched: list[str] = []
    bold_candidates = [
        p for p in candidates if any(k in Path(p).name.lower() for k in ("bold", "bd", "msyhbd"))
    ]
    order = (bold_candidates + candidates) if bold else candidates

    fallback: ImageFont.FreeTypeFont | None = None
    for path in order:
        if not Path(path).exists():
            continue
        searched.append(path)
        try:
            font = ImageFont.truetype(path, 32)
        except OSError:
            continue
        if _supports_cjk(font):
            return font
        fallback = fallback or font

    if fallback is not None:
        # 存在字体但不支持中文：仍然报错，避免产出乱码
        raise FontMissingError(searched or ["<无候选路径>"])

    raise FontMissingError(searched or list(CANDIDATE_PATHS))


def load(explicit: str = "", *, size: int = 32, bold: bool = False) -> ImageFont.FreeTypeFont:
    """按字号加载字体。"""
    base = resolve_font(explicit, bold=bold)
    return ImageFont.truetype(base.path, size)
