"""临时脚本：查询最新 dispatch 运行结果并验证单图+LLM。执行后删除。"""

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


def get_json(url: str, h: dict, *, retries: int = 4) -> dict:
    for i in range(retries):
        try:
            return requests.get(url, headers=h, timeout=30).json()
        except requests.RequestException as exc:
            print(f"  网络重试 {i + 1}: {type(exc).__name__}")
            time.sleep(10)
    raise RuntimeError("网络连续失败")


def main() -> None:
    token = get_token()
    h = {"Authorization": f"Bearer {token}", "User-Agent": "x"}
    head = subprocess.run(
        [GIT, "rev-parse", "HEAD"], capture_output=True, text=True, cwd=os.getcwd()
    ).stdout.strip()

    run = None
    for _ in range(60):
        runs = get_json(f"{BASE}/actions/runs?per_page=3", h)
        match = [r for r in runs["workflow_runs"] if r["head_sha"] == head]
        if match:
            run = match[0]
            print(f"[{run['status']}/{run['conclusion']}]")
            if run["status"] == "completed":
                break
        else:
            print("等待运行出现...")
        time.sleep(15)
    if not run or run["status"] != "completed":
        print("未完成或未找到")
        return
    print("结论:", run["conclusion"])
    if run["conclusion"] != "success":
        return

    arts = get_json(f"{BASE}/actions/runs/{run['id']}/artifacts", h)
    for a in arts["artifacts"]:
        print(f"artifact: {a['name']} {a['size_in_bytes'] // 1024}KB")
        r = requests.get(a["archive_download_url"], headers=h, timeout=180)
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        pngs = [n for n in zf.namelist() if n.endswith(".png")]
        print("  图片文件数:", len(pngs), [Path(p).name for p in pngs])
        for name in zf.namelist():
            if name.endswith("content/content.json"):
                import json

                data = json.loads(zf.read(name).decode("utf-8"))
                gen = data.get("generator", "")
                print("  generator =", gen)
                print("  要闻数 =", len(data.get("top_news", [])))
                single = len(pngs) == 1
                if single and gen == "openai_compatible":
                    print("  ✅ 单图 + 真实百炼 LLM：全部生效")
                else:
                    print(f"  ⚠️ 单图={single} LLM={gen}")


if __name__ == "__main__":
    main()
