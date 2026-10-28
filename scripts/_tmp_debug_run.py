"""临时脚本：下载运行日志排查为什么没用 one_page/百炼。执行后删除。"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
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

    runs = requests.get(f"{BASE}/actions/runs?per_page=3", headers=h, timeout=30).json()
    for r in runs["workflow_runs"]:
        print(
            f"run {r['id']} sha={r['head_sha'][:7]} event={r['event']} "
            f"{r['status']}/{r['conclusion']} created={r['created_at']}"
        )

    # 取最新 dispatch 运行的日志
    run_id = runs["workflow_runs"][0]["id"]
    logs = requests.get(
        f"{BASE}/actions/runs/{run_id}/logs", headers=h, timeout=120, allow_redirects=True
    )
    print("logs HTTP", logs.status_code, "size", len(logs.content))
    if logs.status_code != 200:
        return
    zf = zipfile.ZipFile(io.BytesIO(logs.content))
    for name in zf.namelist():
        if "generate" in name.lower() and name.endswith(".txt"):
            text = zf.read(name).decode("utf-8", errors="replace")
            lines = text.splitlines()
            print(f"--- {name}（关键行） ---")
            for line in lines:
                low = line.lower()
                if any(
                    k in low
                    for k in (
                        "llm", "provider", "generator", "模板", "template",
                        "rule_based", "openai", "dashscope", "百炼", "兜底",
                        "args", "目标日期",
                    )
                ):
                    print(line[:200])


if __name__ == "__main__":
    main()
