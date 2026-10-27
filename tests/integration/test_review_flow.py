"""审核与发布流程集成测试：CLI 全链路、幂等、未审核拦截、驳回、重跑。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from usmarket.cli.main import app
from usmarket.cli.pipeline import day_paths, run_generate_command
from usmarket.config import AppConfig
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import TaskStatus

runner = CliRunner()
DATE = "2026-10-26"


def _run(*args: str):
    result = runner.invoke(app, list(args))
    if result.exit_code != 0 and result.exception:  # 便于定位
        raise AssertionError(
            f"命令失败: {args}\nexit={result.exit_code}\nexc={result.exception!r}\n"
            f"out={result.output}"
        )
    return result


def _generate(cfg: AppConfig) -> None:
    run_generate_command(cfg, DATE, render=True)


# ---------- CLI 生成 ----------
def test_cli_generate_offline(offline_cfg: AppConfig):
    result = _run(
        "generate", "--date", DATE, "--offline", "--data-dir", str(offline_cfg.data_dir)
    )
    assert result.exit_code == 0
    store = FileTaskStore(Path(offline_cfg.data_dir))
    assert store.get(DATE).status == TaskStatus.REVIEW


def test_cli_check_config(offline_cfg: AppConfig):
    result = _run("check-config")
    assert result.exit_code == 0
    assert "发布适配器" in result.output


# ---------- 审核流程 ----------
def test_review_approve_publish_flow(offline_cfg: AppConfig):
    _generate(offline_cfg)
    data_dir = str(offline_cfg.data_dir)

    # 未审核直接发布 → 失败
    denied = runner.invoke(app, ["publish", "--date", DATE, "--data-dir", data_dir])
    assert denied.exit_code != 0
    store = FileTaskStore(Path(offline_cfg.data_dir))
    assert store.get(DATE).status == TaskStatus.REVIEW

    # 审核通过
    _run("approve", "--date", DATE, "--data-dir", data_dir)
    assert store.get(DATE).status == TaskStatus.APPROVED

    # 发布
    result = _run("publish", "--date", DATE, "--data-dir", data_dir)
    assert "发布成功" in result.output
    task = store.get(DATE)
    assert task.status == TaskStatus.PUBLISHED
    assert len(task.publish_records) == 1

    # 结果文件
    result_path = Path(offline_cfg.data_dir) / DATE / "publish" / "result.json"
    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["simulated"] is True
    assert payload["verified"] is False  # 真实发布未验收


def test_publish_twice_is_idempotent(offline_cfg: AppConfig):
    _generate(offline_cfg)
    data_dir = str(offline_cfg.data_dir)
    _run("approve", "--date", DATE, "--data-dir", data_dir)
    _run("publish", "--date", DATE, "--data-dir", data_dir)

    second = _run("publish", "--date", DATE, "--data-dir", data_dir)
    store = FileTaskStore(Path(offline_cfg.data_dir))
    task = store.get(DATE)
    assert len(task.publish_records) == 1
    assert "幂等" in second.output or task.status == TaskStatus.PUBLISHED


def test_reject_records_reason(offline_cfg: AppConfig):
    _generate(offline_cfg)
    store = FileTaskStore(Path(offline_cfg.data_dir))
    _run("reject", "--date", DATE, "--reason", "标题不够吸引人",
         "--data-dir", str(offline_cfg.data_dir))
    task = store.get(DATE)
    assert task.status == TaskStatus.REJECTED
    assert "标题不够吸引人" in task.error


def test_rejected_task_can_be_rerun(offline_cfg: AppConfig):
    _generate(offline_cfg)
    store = FileTaskStore(Path(offline_cfg.data_dir))
    _run("reject", "--date", DATE, "--reason", "重写", "--data-dir", str(offline_cfg.data_dir))
    _run("rerun", "--date", DATE, "--offline", "--data-dir", str(offline_cfg.data_dir))
    assert store.get(DATE).status == TaskStatus.REVIEW


def test_list_and_show(offline_cfg: AppConfig):
    _generate(offline_cfg)
    listed = _run("list", "--data-dir", str(offline_cfg.data_dir))
    assert DATE in listed.output
    shown = _run("show", "--date", DATE, "--data-dir", str(offline_cfg.data_dir))
    assert "content_fingerprint" in shown.output


def test_show_unknown_date_fails(offline_cfg: AppConfig):
    result = runner.invoke(
        app, ["show", "--date", "1999-01-01", "--data-dir", str(offline_cfg.data_dir)]
    )
    assert result.exit_code != 0


def test_publish_without_generation_fails(offline_cfg: AppConfig):
    result = runner.invoke(
        app, ["publish", "--date", "1999-01-01", "--data-dir", str(offline_cfg.data_dir)]
    )
    assert result.exit_code != 0


def test_render_command_regenerates_images(offline_cfg: AppConfig):
    _generate(offline_cfg)
    paths = day_paths(offline_cfg, DATE)
    for image in paths["images"].glob("*.png"):
        image.unlink()
    assert not list(paths["images"].glob("*.png"))

    _run("render", "--date", DATE, "--data-dir", str(offline_cfg.data_dir))
    assert (paths["images"] / "cover.png").exists()
    assert len(list(paths["images"].glob("page_*.png"))) >= 5


def test_manual_export_adapter(monkeypatch, tmp_path: Path, offline_cfg: AppConfig):
    """manual_export 适配器导出发布包，不调用任何平台接口。

    CLI 从环境变量读取发布适配器，因此这里通过设置 XHS_PUBLISHER 切换。
    """
    from dataclasses import replace

    monkeypatch.setenv("XHS_PUBLISHER", "manual_export")
    monkeypatch.setenv("USMARKET_DATA_DIR", str(tmp_path / "data"))
    cfg = replace(offline_cfg, data_dir=tmp_path / "data")
    _generate(cfg)
    store = FileTaskStore(Path(cfg.data_dir))
    _run("approve", "--date", DATE, "--data-dir", str(cfg.data_dir))
    result = _run("publish", "--date", DATE, "--data-dir", str(cfg.data_dir))
    assert "发布成功" in result.output

    export = Path(cfg.data_dir) / DATE / "publish"
    assert (export / "publish_bundle.json").exists()
    assert (export / "HOW_TO_PUBLISH.md").exists()
    payload = json.loads((export / "result.json").read_text(encoding="utf-8"))
    assert payload["verified"] is False
    assert store.get(DATE).status == TaskStatus.PUBLISHED


def test_mark_published_command(offline_cfg: AppConfig):
    _generate(offline_cfg)
    store = FileTaskStore(Path(offline_cfg.data_dir))
    _run("approve", "--date", DATE, "--data-dir", str(offline_cfg.data_dir))
    _run(
        "mark-published", "--date", DATE, "--remote-id", "https://xhs.example/note/1",
        "--data-dir", str(offline_cfg.data_dir),
    )
    task = store.get(DATE)
    assert task.status == TaskStatus.PUBLISHED
    assert task.publish_records[-1].remote_id == "https://xhs.example/note/1"
    assert task.publish_records[-1].verified is False


def test_schedule_command(offline_cfg: AppConfig):
    result = _run(
        "schedule", "--at", "2026-10-27T13:00:00+00:00", "--json"
    )
    payload = json.loads(result.output)
    assert payload["target_date"] == "2026-10-26"


def test_failed_task_is_reported_with_stage(offline_cfg: AppConfig):
    """注入一个失败的 provider，验证失败可被定位到具体阶段。"""
    from unittest.mock import patch

    from usmarket.errors import CollectionError

    with patch(
        "usmarket.cli.pipeline.run_collect",
        side_effect=CollectionError("采集失败（模拟）"),
    ):
        try:
            run_generate_command(offline_cfg, "2026-10-23", render=False)
        except CollectionError:
            pass

    store = FileTaskStore(Path(offline_cfg.data_dir))
    task = store.get("2026-10-23")
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert task.stage.value == "collect"
    assert "采集失败" in task.error
