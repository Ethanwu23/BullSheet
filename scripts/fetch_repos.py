"""Fetch GitHub repository metadata, README and file tree for research purposes.

Usage: python scripts/fetch_repos.py
Outputs raw JSON/markdown into .cache/research/<owner>__<repo>/ for later analysis.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

REPOS = [
    "CazSyd/stock-report",
    "SamirPaulb/daily-digest",
    "angelinavio/daily-market-brief",
    "hasuoshenyun/XHS_Auto_Publish",
    "github/spec-kit",
]

OUT = Path(".cache/research")
TIMEOUT = 20


def get(url: str) -> tuple[int, str, dict]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "research-script",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:  # noqa: PERF203
        return e.code, e.read().decode("utf-8", errors="replace"), dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}", {}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for repo in REPOS:
        slug = repo.replace("/", "__")
        dest = OUT / slug
        dest.mkdir(parents=True, exist_ok=True)
        status, body, _ = get(f"https://api.github.com/repos/{repo}")
        (dest / "repo.json").write_text(body, encoding="utf-8")
        meta = {}
        if status == 200:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {}
            meta = {
                "full_name": data.get("full_name"),
                "description": data.get("description"),
                "license": (data.get("license") or {}).get("spdx_id"),
                "stars": data.get("stargazers_count"),
                "open_issues": data.get("open_issues_count"),
                "archived": data.get("archived"),
                "pushed_at": data.get("pushed_at"),
                "created_at": data.get("created_at"),
                "default_branch": data.get("default_branch"),
                "language": data.get("language"),
                "topics": data.get("topics"),
                "size_kb": data.get("size"),
            }
        # README
        for branch_hint in ("HEAD", "main", "master"):
            st, txt, _ = get(
                f"https://raw.githubusercontent.com/{repo}/{branch_hint}/README.md"
            )
            if st == 200:
                (dest / "README.md").write_text(txt, encoding="utf-8")
                meta["readme_bytes"] = len(txt)
                break
        # tree
        st, tree_body, _ = get(
            f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"
        )
        if st == 200:
            (dest / "tree.json").write_text(tree_body, encoding="utf-8")
            try:
                paths = [i["path"] for i in json.loads(tree_body).get("tree", [])]
            except json.JSONDecodeError:
                paths = []
            (dest / "tree.txt").write_text("\n".join(paths), encoding="utf-8")
            meta["file_count"] = len(paths)
        summary[repo] = meta
        print(f"[{status}] {repo} -> {meta}")
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
