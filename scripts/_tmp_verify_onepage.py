"""临时脚本：触发 CI 并验证产物为单图。执行后删除。"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import requests

GIT = (
    r"C:\Users\wudin\AppData\Local\GitHubDesktop"
    r"\app-3.5.5\resources\app\git\cmd\git.exe"
)
BASE = "https://api.github.com/repos/Ethanwu23/BullSheet"


def get_token() -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("protocol=https\nhost=github.com\n\n")
        inp = f.name
    out = inp + ".out"
    subprocess.run(
        [GIT, "credential", "fill"],
        stdin=open(inp, "rb"),
        stdout=open(out, "wb"),
        check=True,
        env={**os.environ, "GCM_INTERACTIVE": "never"},
    )
    token = [
        line.split("=", 1)[1]
        for line in Path(out).read_text().splitlines()
        if line.startswith("password=")
    ][0]
    Path(inp).unlink()
    Path(out).unlink()
    return token


def main() -> None:
    token = get_token()
    h = {"Authorization": f"Bearer {token}", "User-Agent": "x"}

    d = requests.post(
        f"{BASE}/actions/workflows/daily.yml/dispatches",
        headers=h,
        json={"ref": "master"},
        timeout=30,
    )
    print("dispatch:", d.status_code)
    if d.status_code != 204:
        return

    # 等待运行完成（最多 12 分钟）
    run_id = None
    for _ in range(48):
        time.sleep(15)
        runs = requests.get(
            f"{BASE}/actions/runs?per_page=1", headers=h, timeout=30
        ).json()
        run = runs["workflow_runs"][0]
        if run["event"] == "workflow_dispatch" and run["head_sha"].startswith(
            # 本地最新提交
            subprocess.run(
                [GIT, "rev-parse", "--short=7", "HEAD"],
                capture_output=True, text=True, cwd=os.getcwd()
            ).stdout.strip()
        ):
            run_id = run["id"]
            print(f"[{run['status']}/{run['conclusion']}]")
            if run["status"] == "completed":
                break

    if not run_id:
        print("未找到对应运行")
        return

    print(f"结论: {run['conclusion']}")
    if run["conclusion"] != "success":
        return

    arts = requests.get(
        f"{BASE}/actions/runs/{run_id}/artifacts", headers=h, timeout=30
    ).json()
    for a in arts["artifacts"]:
        print(f"artifact: {a['name']} {a['size_in_bytes'] // 1024}KB")
        r = requests.get(a["archive_download_url"], headers=h, timeout=120)
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        pngs = [n for n in zf.namelist() if n.endswith(".png")]
        print("  图片文件:", pngs)
        for name in zf.namelist():
            if name.endswith("content/content.json"):
                import json

                data = json.loads(zf.read(name).decode("utf-8"))
                print("  generator =", data.get("generator"))
                print("  要闻数 =", len(data.get("top_news", [])))


if __name__ == "__main__":
    main()
