"""命令行入口。

命令：generate / render / list / show / approve / reject / publish / rerun /
      mark-published / schedule / check-config / llm-models / llm-check
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import typer

from usmarket.__init__ import __version__
from usmarket.cli.pipeline import day_paths, load_generated, run_generate_command
from usmarket.config import AppConfig, load_config, validate_sensitive_config
from usmarket.errors import PublishError, USMarketError
from usmarket.logging_setup import setup_logging
from usmarket.publishing.base import PublishPayload
from usmarket.publishing.service import build_payload, publish_task
from usmarket.scheduler.resolve import parse_run_date, resolve_target_date
from usmarket.storage.file_store import FileTaskStore
from usmarket.storage.models import TaskStatus
from usmarket.storage.state_machine import can_transition

app = typer.Typer(
    help="美股每日简报：采集新闻与行情 → AI 生成中文内容 → 渲染一张长图",
    no_args_is_help=True,
)


def _cfg(
    offline: bool = False,
    tickers: str | None = None,
    provider: str | None = None,
    template: str | None = None,
    data_dir: str | None = None,
) -> AppConfig:
    cfg = load_config()
    ticker_tuple = tuple(t.strip() for t in tickers.split(",") if t.strip()) if tickers else None
    return cfg.with_overrides(
        tickers=ticker_tuple,
        provider=provider,
        template=template,
        offline=offline or None,
        data_dir=Path(data_dir) if data_dir else None,
    )


def _resolve_date(date: str | None) -> str:
    parsed = parse_run_date(date)
    if parsed:
        return parsed
    return resolve_target_date(datetime.now().astimezone(), mode="after_close").target_date


@app.command()
def version() -> None:
    """显示版本。"""
    typer.echo(f"usmarket {__version__}")


@app.command()
def check_config() -> None:
    """校验配置与敏感项是否齐备（不打印密钥值）。"""
    cfg = load_config()
    missing = validate_sensitive_config(cfg)
    typer.echo(f"LLM provider : {cfg.llm.provider}")
    typer.echo(f"行情 provider: {cfg.market.provider}")
    typer.echo(f"发布适配器   : {cfg.publish.publisher}")
    typer.echo(f"图片模板     : {cfg.image.template} ({cfg.image.width}x{cfg.image.height})")
    typer.echo(f"离线模式     : {cfg.offline}")
    if missing:
        typer.secho("缺失的敏感配置: " + ", ".join(missing), fg=typer.colors.RED)
        raise typer.Exit(code=2)
    typer.secho("配置校验通过", fg=typer.colors.GREEN)


@app.command()
def llm_models(
    limit: int = typer.Option(40, "--limit", help="最多显示多少个 model id"),
    contains: str = typer.Option("", "--contains", help="按关键字过滤，如 flash / qwen3.8"),
) -> None:
    """列出当前 LLM 端点可用模型（OpenAI 兼容的 /v1/models）。

    用于确认 model id 是否正确（例如百炼的 qwen3.8-flash）。不打印密钥。
    """
    import requests

    cfg = load_config()
    if cfg.llm.provider not in {"openai_compatible", "dashscope"}:
        typer.secho(
            f"当前 provider={cfg.llm.provider} 不支持 /v1/models；"
            f"请设置 LLM_PROVIDER=dashscope 或 openai_compatible",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)
    if not cfg.llm.api_key:
        typer.secho("未配置 LLM_API_KEY / DASHSCOPE_API_KEY", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    url = cfg.llm.base_url.rstrip("/") + "/models"
    typer.echo(f"端点: {cfg.llm.base_url}")
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {cfg.llm.api_key}"},
            timeout=cfg.llm.timeout_seconds,
        )
    except requests.RequestException as exc:
        typer.secho(f"请求失败: {type(exc).__name__}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    if resp.status_code >= 400:
        typer.secho(f"端点返回状态码: {resp.status_code}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        ids = sorted(str(m.get("id", "")) for m in resp.json().get("data", []))
    except (ValueError, AttributeError):
        typer.secho("响应结构异常（非 OpenAI 兼容格式）", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    ids = [m for m in ids if m]
    if contains:
        ids = [m for m in ids if contains.lower() in m.lower()]
    typer.echo(f"可用模型 {len(ids)} 个，当前配置 model={cfg.llm.model}")
    for m in ids[:limit]:
        typer.echo("  " + m)
    if len(ids) > limit:
        typer.echo(f"  …（还有 {len(ids) - limit} 个，用 --limit 调整）")


@app.command()
def llm_check(
    model: str | None = typer.Option(None, "--model", help="临时覆盖模型名"),
    provider: str | None = typer.Option(
        None, "--provider", help="临时覆盖 provider: dashscope|openai_compatible|anthropic"
    ),
) -> None:
    """真实调用一次 LLM 并校验其输出能否通过本项目的内容校验。

    发送一条极小的结构化 JSON 生成请求，报告：延迟、token 用量、JSON 是否可解析。
    不打印密钥，也不把响应体写入日志。
    """
    cfg = _cfg(provider=provider)
    if model:
        from dataclasses import replace as _replace

        cfg = _replace(cfg, llm=_replace(cfg.llm, model=model))
    missing = validate_sensitive_config(cfg)
    if missing:
        typer.secho("敏感配置缺失: " + ", ".join(missing), fg=typer.colors.RED)
        raise typer.Exit(code=2)

    from usmarket.ai.service import build_provider

    prov = build_provider(cfg)
    if prov is None:
        typer.secho(
            "当前配置未启用 LLM（provider=rule_based 或 offline=1），无法连通性测试",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    import time

    from usmarket.ai.base import extract_json

    typer.echo(f"provider  : {cfg.llm.provider}")
    typer.echo(f"端点      : {cfg.llm.base_url}")
    typer.echo(f"模型      : {cfg.llm.model}")
    system = "你是一个只输出 JSON 的助手。"
    user = '请输出：{"ok": true, "model": "你的模型名"}，不要包含任何额外文字。'
    started = time.perf_counter()
    try:
        raw = prov.generate(system, user)
    except Exception as exc:  # noqa: BLE001 - 诊断命令需展示原始异常类型
        typer.secho(f"调用失败: {type(exc).__name__}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None
    elapsed = time.perf_counter() - started
    typer.secho(f"调用成功：{elapsed:.2f}s，响应 {len(raw)} 字符", fg=typer.colors.GREEN)
    typer.echo("--- 原始响应（前 300 字符）---")
    typer.echo(raw[:300])
    try:
        parsed = extract_json(raw)
        typer.secho("JSON 解析: 通过", fg=typer.colors.GREEN)
        typer.echo(f"解析结果: {parsed}")
    except Exception as exc:  # noqa: BLE001
        typer.secho(f"JSON 解析失败: {type(exc).__name__}: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1) from None


@app.command()
def generate(
    date: str | None = typer.Option(None, "--date", help="目标日期 YYYY-MM-DD（默认自动解析）"),
    offline: bool = typer.Option(False, "--offline", help="使用 fixture，不访问网络"),
    no_render: bool = typer.Option(False, "--no-render", help="跳过图片渲染"),
    tickers: str | None = typer.Option(None, "--tickers", help="覆盖股票列表，逗号分隔"),
    provider: str | None = typer.Option(
        None,
        "--provider",
        help="LLM provider: rule_based|dashscope|openai_compatible|anthropic",
    ),
    template: str | None = typer.Option(
        None, "--template", help="图片模板: one_page(单图)|daily_review|flash_brief"
    ),
    data_dir: str | None = typer.Option(None, "--data-dir", help="产物根目录"),
) -> None:
    """采集 → 生成 → 校验 → 渲染 → 进入待审核。"""
    cfg = _cfg(offline, tickers, provider, template, data_dir)
    setup_logging(cfg.log_level)
    missing = validate_sensitive_config(cfg)
    if missing:
        typer.secho("敏感配置缺失（不会打印其值）: " + ", ".join(missing), fg=typer.colors.RED)
        raise typer.Exit(code=2)

    target = _resolve_date(date)
    typer.echo(f"目标日期: {target}")
    try:
        task = run_generate_command(cfg, target, render=not no_render)
    except USMarketError as exc:
        typer.secho(f"[{exc.stage}] {exc.message}", fg=typer.colors.RED)
        if exc.detail:
            typer.secho(exc.detail, fg=typer.colors.YELLOW)
        raise typer.Exit(code=1) from exc

    typer.secho(
        f"完成：状态={task.status.value} 指纹={task.content_fingerprint[:12]}", fg=typer.colors.GREEN
    )
    typer.echo(f"审核文件: {Path(cfg.data_dir) / target / 'REVIEW.md'}")


@app.command()
def render(
    date: str | None = typer.Option(None, "--date"),
    template: str | None = typer.Option(None, "--template"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """根据已生成内容重新渲染图片。"""
    from usmarket.image_renderer.renderer import render_images

    cfg = _cfg(False, None, None, template, data_dir)
    setup_logging(cfg.log_level)
    target = _resolve_date(date)
    content, snapshot, _ = load_generated(cfg, target)
    paths = day_paths(cfg, target)
    result = render_images(cfg, content, snapshot, paths["images"], now=datetime.now())
    typer.secho(f"已渲染 {1 + len(result.pages)} 张图片 -> {paths['images']}", fg=typer.colors.GREEN)


@app.command("list")
def list_tasks(
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """列出所有任务。"""
    cfg = _cfg(False, None, None, None, data_dir)
    store = FileTaskStore(Path(cfg.data_dir))
    tasks = store.list_all()
    if not tasks:
        typer.echo("（无任务）")
        return
    typer.echo(f"{'日期':<12} {'状态':<10} {'阶段':<12} {'生成器':<16} {'错误'}")
    for t in tasks:
        typer.echo(
            f"{t.date:<12} {t.status.value:<10} {t.stage.value:<12} "
            f"{t.generator:<16} {t.error[:40]}"
        )


@app.command()
def show(
    date: str = typer.Option(..., "--date"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """查看某天任务详情（含失败原因）。"""
    cfg = _cfg(False, None, None, None, data_dir)
    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date)
    if task is None:
        typer.secho(f"任务不存在: {date}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))


@app.command()
def approve(
    date: str = typer.Option(..., "--date"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """审核通过。"""
    cfg = _cfg(False, None, None, None, data_dir)
    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date)
    if task is None:
        typer.secho(f"任务不存在: {date}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if not can_transition(task.status, TaskStatus.APPROVED):
        typer.secho(
            f"当前状态 {task.status.value} 不能迁移到 approved", fg=typer.colors.RED
        )
        raise typer.Exit(code=1)
    updated = store.transition(date, TaskStatus.APPROVED, note="人工审核通过")
    typer.secho(f"{date} -> {updated.status.value}", fg=typer.colors.GREEN)


@app.command()
def reject(
    date: str = typer.Option(..., "--date"),
    reason: str = typer.Option("未填写", "--reason"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """审核驳回。"""
    cfg = _cfg(False, None, None, None, data_dir)
    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date)
    if task is None:
        typer.secho(f"任务不存在: {date}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if not can_transition(task.status, TaskStatus.REJECTED):
        typer.secho(f"当前状态 {task.status.value} 不能驳回", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    store.transition(date, TaskStatus.REJECTED, note=f"驳回原因: {reason}", error=reason)
    typer.secho(f"{date} -> rejected（{reason}）", fg=typer.colors.YELLOW)


@app.command()
def rerun(
    date: str = typer.Option(..., "--date"),
    offline: bool = typer.Option(False, "--offline"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """重新运行失败任务。"""
    cfg = _cfg(offline, None, None, None, data_dir)
    setup_logging(cfg.log_level)
    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date)
    if task is None:
        typer.secho(f"任务不存在: {date}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if task.status not in {TaskStatus.FAILED, TaskStatus.REJECTED, TaskStatus.PENDING}:
        typer.secho(
            f"状态 {task.status.value} 不需要重跑（仅 failed/rejected/pending 可重跑）",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1)
    store.transition(date, TaskStatus.PENDING, note="重跑")
    run_generate_command(cfg, date)
    typer.secho(f"{date} 重跑完成", fg=typer.colors.GREEN)


@app.command()
def publish(
    date: str = typer.Option(..., "--date"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """发布（需先 approve；默认使用模拟发布器）。"""
    cfg = _cfg(False, None, None, None, data_dir)
    setup_logging(cfg.log_level)
    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date)
    if task is None:
        typer.secho(f"任务不存在: {date}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if task.status == TaskStatus.PUBLISHED:
        # 幂等命中：已发布任务再次调用直接返回，不重复发布（FR-039）
        typer.secho(
            f"{date} 已发布（幂等命中，跳过重复发布）", fg=typer.colors.YELLOW
        )
        return

    content, snapshot, images = load_generated(cfg, date)
    payload: PublishPayload = build_payload(
        date,
        title=content.xhs.title,
        body=content.xhs.body,
        tags=content.xhs.tags,
        images=images,
        fingerprint=task.content_fingerprint,
    )
    try:
        outcome = publish_task(cfg, store, task, payload)
    except PublishError as exc:
        typer.secho(f"[publish] {exc.message}", fg=typer.colors.RED)
        if exc.detail:
            typer.echo(exc.detail)
        raise typer.Exit(code=1) from exc

    if outcome.success:
        typer.secho(
            f"发布成功 task_id={outcome.task_id} simulated={outcome.simulated} "
            f"verified={outcome.verified}",
            fg=typer.colors.GREEN,
        )
        if outcome.detail.get("skipped"):
            typer.secho("（幂等命中：已跳过重复发布）", fg=typer.colors.YELLOW)
        if outcome.simulated:
            typer.secho(
                "注意：本次为模拟流程记录（本项目仅生成内容，不含平台发布）。",
                fg=typer.colors.YELLOW,
            )
    else:
        typer.secho(f"发布失败: {outcome.error}", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@app.command("mark-published")
def mark_published(
    date: str = typer.Option(..., "--date"),
    remote_id: str = typer.Option("", "--remote-id", help="人工发布后的笔记链接或 ID"),
    data_dir: str | None = typer.Option(None, "--data-dir"),
) -> None:
    """人工发布后手动标记完成（配合 manual_export 使用）。"""
    cfg = _cfg(False, None, None, None, data_dir)
    store = FileTaskStore(Path(cfg.data_dir))
    task = store.get(date)
    if task is None:
        typer.secho(f"任务不存在: {date}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    from usmarket.storage.models import PublishRecord

    task.publish_records.append(
        PublishRecord(
            publisher="manual",
            task_id=f"manual-{date}",
            result="success",
            simulated=False,
            verified=False,  # 人工发布也未由系统验证
            at=datetime.now().astimezone().isoformat(),
            idempotency_key=f"{date}:{task.content_fingerprint}",
            remote_id=remote_id,
        )
    )
    store.save(task)
    if task.status != TaskStatus.PUBLISHED:
        store.transition(
            date, TaskStatus.PUBLISHED, note=f"人工发布完成 remote_id={remote_id}"
        )
    typer.secho(f"{date} 已标记为已发布（verified=False，系统未验证）", fg=typer.colors.GREEN)


@app.command()
def schedule(
    at: str | None = typer.Option(None, "--at", help="ISO8601 触发时间（默认当前时间）"),
    mode: str = typer.Option("after_close", "--mode"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """解析某次触发对应的目标交易日（不执行采集）。"""
    trigger = datetime.fromisoformat(at) if at else datetime.now().astimezone()
    try:
        plan = resolve_target_date(trigger, mode=mode)
    except NotImplementedError as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "mode": plan.mode,
                    "trigger_utc": plan.trigger_utc.isoformat(),
                    "market_time": plan.market_time.isoformat(),
                    "target_date": plan.target_date,
                    "market_phase": plan.market_phase,
                    "reason": plan.reason,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    typer.echo(f"触发时间(UTC): {plan.trigger_utc.isoformat()}")
    typer.echo(f"美东时间     : {plan.market_time.isoformat()}")
    typer.echo(f"交易阶段     : {plan.market_phase}")
    typer.echo(f"目标交易日   : {plan.target_date}")
    typer.echo(f"依据         : {plan.reason}")


def main() -> None:
    # Windows 控制台默认非 UTF-8，中文会乱码：尽力切换（失败不影响功能）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    try:
        app()
    except USMarketError as exc:
        typer.secho(f"[{exc.stage}] {exc.message}", fg=typer.colors.RED)
        sys.exit(1)


if __name__ == "__main__":
    main()
