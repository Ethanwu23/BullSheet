"""Scrape GitHub HTML pages (no API rate limit) for license, last commit, file tree.

Outputs to .cache/research/<owner>__<repo>/{meta.json,commits.atom,tree_html.txt}
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path

REPOS = [
    "CazSyd/stock-report",
    "SamirPaulb/daily-digest",
    "angelinavio/daily-market-brief",
    "hasuoshenyun/XHS_Auto_Publish",
    "github/spec-kit",
]

OUT = Path(".cache/research")
TIMEOUT = 25


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research-script"
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"


LICENSE_RE = re.compile(r"(?i)\b(MIT|Apache-2\.0|GPL-3\.0|GPL-2\.0|AGPL-3\.0|BSD-3-Clause|BSD-2-Clause|MPL-2\.0|Unlicense|NOASSERTION|Other)\b")


def main() -> None:
    summary: dict[str, dict] = {}
    for repo in REPOS:
        slug = repo.replace("/", "__")
        dest = OUT / slug
        dest.mkdir(parents=True, exist_ok=True)
        info: dict = {}

        st, html = get(f"https://github.com/{repo}")
        (dest / "page.html").write_text(html, encoding="utf-8")
        if st == 200:
            m = re.search(
                r'<a[^>]+href="/{}/blob/[^"]+/(?:LICENSE|LICENCE|COPYING)[^"]*"[^>]*>\s*([^<]+)</a>'.format(
                    re.escape(repo)
                ),
                html,
            )
            if m:
                info["license_link_text"] = unescape(m.group(1)).strip()
            # license from sidebar
            m2 = re.search(r'href="/{}/blob/[^"]*(?:LICENSE|LICENCE|COPYING)[^"]*"[^>]*>(.*?)</a>'.format(re.escape(repo)), html, re.S)
            if m2:
                txt = re.sub(r"<[^>]+>", "", m2.group(1)).strip()
                info["license_file"] = unescape(txt)
            m3 = re.search(r'"license"\s*:\s*\{[^}]*?"spdxId"\s*:\s*"([^"]+)"', html)
            if m3:
                info["license_spdx"] = m3.group(1)
            m4 = re.search(r'"licenseInfo"\s*:\s*\{[^}]*?"spdxId"\s*:\s*"([^"]+)"', html)
            if m4:
                info["license_spdx"] = m4.group(1)
            # stars / forks
            m5 = re.search(r'"stargazerCount"\s*:\s*(\d+)', html)
            if m5:
                info["stars"] = int(m5.group(1))
            # relative last commit
            m6 = re.findall(r'<relative-time[^>]*datetime="([^"]+)"', html)
            if m6:
                info["recent_timestamps"] = m6[:5]

        # commits atom (no rate limit)
        st2, atom = get(f"https://github.com/{repo}/commits.atom")
        (dest / "commits.atom").write_text(atom, encoding="utf-8")
        if st2 == 200:
            entries = re.findall(r"<updated>([^<]+)</updated>", atom)
            titles = re.findall(r"<title>\s*(.*?)\s*</title>", atom, re.S)
            info["latest_commit_updated"] = entries[1] if len(entries) > 1 else entries[:1]
            info["commit_count_in_feed"] = max(0, len(titles) - 1)

        summary[repo] = info
        print(f"[{st}/{st2}] {repo} -> {json.dumps(info, ensure_ascii=False)}")

    (OUT / "meta_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
