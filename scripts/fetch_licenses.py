"""Fetch LICENSE and selected source files from the candidate repositories."""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(".cache/research")
TIMEOUT = 25

FILES = {
    "CazSyd/stock-report": [
        "LICENSE",
        "pyproject.toml",
        "config.yaml",
        "requirements.txt",
    ],
    "SamirPaulb/daily-digest": ["LICENSE", "scripts/requirements.txt", ".env.example"],
    "angelinavio/daily-market-brief": ["LICENSE", "requirements.txt"],
    "hasuoshenyun/XHS_Auto_Publish": ["LICENSE", "requirements.txt", "upload.py"],
    "github/spec-kit": ["LICENSE"],
}


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 research-script"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


def main() -> None:
    for repo, paths in FILES.items():
        dest = OUT / repo.replace("/", "__") / "files"
        dest.mkdir(parents=True, exist_ok=True)
        for p in paths:
            for branch in ("HEAD", "main", "master"):
                st, body = get(
                    f"https://raw.githubusercontent.com/{repo}/{branch}/{p}"
                )
                if st == 200:
                    out = dest / p.replace("/", "__")
                    out.write_text(body, encoding="utf-8")
                    print(f"[200] {repo}/{p} ({len(body)} bytes)")
                    break
            else:
                print(f"[MISS] {repo}/{p}")


if __name__ == "__main__":
    main()
