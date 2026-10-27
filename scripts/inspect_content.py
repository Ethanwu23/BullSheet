"""临时脚本：查看某天生成的 content.json 关键内容（中文输出）。

用法：python scripts/inspect_content.py <data_dir>/<date>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    day = Path(argv[0]) if argv else Path("data/2026-10-26")
    path = day / "content" / "content.json"
    if not path.exists():
        print(f"不存在: {path}")
        return 1
    d = json.loads(path.read_text(encoding="utf-8"))
    print("generator:", d.get("generator"), "| phase:", d.get("market_phase"),
          "| low_confidence:", d.get("low_confidence"))
    print()
    print("【概览】", d.get("summary"))
    print()
    for i, n in enumerate(d.get("top_news", []), 1):
        print(f"{i}. [{n.get('confidence')}] {n.get('headline')}")
        print("   ", (n.get("body") or "")[:200])
        print("    源:", n.get("source_title"), "|", (n.get("source_url") or "")[:80])
        print("    时间:", n.get("published_at"))
    print()
    print("【个股异动】")
    for m in d.get("watchlist_moves", []):
        print("  ", m.get("symbol"), m.get("change_percent"), "|", (m.get("note") or "")[:100])
    print()
    print("【XHS 标题】", d.get("xhs", {}).get("title"))
    print("【XHS 标签】", " ".join(d.get("xhs", {}).get("tags", [])))
    print()
    print("【正文】")
    print(d.get("xhs", {}).get("body"))
    print()
    print("【次日关注】", d.get("next_session"))
    print("【风险提示】", d.get("risk_notes"))
    print("【来源数】", len(d.get("sources", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
