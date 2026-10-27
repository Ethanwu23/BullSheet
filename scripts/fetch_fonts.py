"""下载中文字体到 assets/fonts/。

用途：GitHub Actions（ubuntu-latest）默认没有中文字体，
图片渲染会因找不到中文字体而报 FontMissingError（FR-033）。

用法：
    python scripts/fetch_fonts.py
    python scripts/fetch_fonts.py --url <自定义字体 zip/ttf 直链>

默认从 Google Fonts 的 Noto Sans SC 静态字体直链下载（SIL Open Font License 1.1）。
若下载失败，请自行放置任意支持中文的 .ttf/.otf/.ttc 到 assets/fonts/。
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"

DEFAULT_URL = (
    "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/"
    "NotoSansSC-Regular.otf"
)
DEFAULT_BOLD_URL = (
    "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/"
    "NotoSansSC-Bold.otf"
)

TIMEOUT = 60
USER_AGENT = "USMarketDailyXHS/0.1 (font-fetcher)"


def _download(url: str, timeout: int = TIMEOUT) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _looks_like_zip(data: bytes) -> bool:
    return data[:2] == b"PK"


def save_font(data: bytes, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if _looks_like_zip(data):
        extracted: list[Path] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".ttf", ".otf")):
                    out = target.parent / Path(name).name
                    out.write_bytes(zf.read(name))
                    extracted.append(out)
        if not extracted:
            raise RuntimeError("压缩包中没有找到字体文件")
        return extracted[0]
    target.write_bytes(data)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="字体直链或 zip")
    parser.add_argument("--bold-url", default=DEFAULT_BOLD_URL, help="粗体字体直链")
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    args = parser.parse_args(argv)

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    ok = False
    for label, url, name in (
        ("regular", args.url, "NotoSansSC-Regular.otf"),
        ("bold", args.bold_url, "NotoSansSC-Bold.otf"),
    ):
        try:
            data = _download(url, args.timeout)
            path = save_font(data, FONT_DIR / name)
            print(f"[ok] {label} -> {path} ({path.stat().st_size} bytes)")
            ok = True
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {label} 下载失败: {type(exc).__name__}: {exc}", file=sys.stderr)

    if not ok:
        print(
            "未下载到任何字体。请手动放置一个支持中文的字体到 "
            f"{FONT_DIR}（例如 msyh.ttc / NotoSansSC-Regular.otf）。",
            file=sys.stderr,
        )
        return 1

    # 校验：确认字体可被 Pillow 加载且支持中文
    try:
        from usmarket.image_renderer.fonts import resolve_font

        resolve_font.cache_clear()
        font = resolve_font()
        print(f"[ok] 已验证可用中文字体: {font.path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 字体校验失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
