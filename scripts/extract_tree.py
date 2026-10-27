"""Extract root-level file/dir listings from cached GitHub repo HTML pages."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPOS = [
    "CazSyd__stock-report",
    "SamirPaulb__daily-digest",
    "angelinavio__daily-market-brief",
    "hasuoshenyun__XHS_Auto_Publish",
]

for slug in REPOS:
    p = Path(".cache/research") / slug / "page.html"
    if not p.exists():
        print(slug, "-> no page")
        continue
    h = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'"tree":\{"items":\[(.*?)\],"totalCount"', h, re.S)
    if not m:
        print(slug, "-> no tree")
        continue
    names = re.findall(r'"name":"([^"]+)"', m.group(1))
    has_license = any(n.lower().startswith(("license", "licence", "copying")) for n in names)
    print(f"{slug}: license_present={has_license} entries={names}")
