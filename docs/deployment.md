# 部署与运维手册

**版本**：v1 ｜ **日期**：2026-10-27

---

## 1. 部署形态

| 形态 | 适用 | 说明 |
| --- | --- | --- |
| 本地 CLI | 开发、单次补跑 | `usmarket generate --date ...` |
| GitHub Actions（推荐） | 每日自动运行 | `.github/workflows/daily.yml` |
| 自托管 cron + 容器 | 内网/合规要求 | 见 §5 |

**核心事实**：本项目的生产链路止于「内容生成 + 待审核」。
**发布不在自动链路内**（默认人工审核，发布适配器为模拟/导出）。

---

## 2. GitHub Actions 部署

### 2.1 前置

1. 仓库推送到 GitHub；
2. 仓库 Settings → Actions → General → Workflow permissions 保持 `Read repository contents`；
3. 创建必要的 Secrets / Variables（见 §2.2）。

### 2.2 Secrets 与 Variables

| 名称 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `LLM_API_KEY` | Secret | 否 | — | 不用 LLM 可留空 |
| `ANTHROPIC_API_KEY` | Secret | 否 | — | 仅 anthropic |
| `FINNHUB_API_KEY` | Secret | 否 | — | 仅 finnhub |
| `LLM_PROVIDER` | Variable | 否 | `rule_based` | |
| `LLM_BASE_URL` | Variable | 否 | `https://api.openai.com/v1` | |
| `LLM_MODEL` | Variable | 否 | `gpt-4o-mini` | |
| `MARKET_PROVIDER` | Variable | 否 | `yahoo` | |
| `XHS_PUBLISHER` | Variable | 否 | `mock` | |
| `SEC_USER_AGENT` | Variable | 建议 | `.../actions@users.noreply.github.com` | 格式 `App/ver (email)` |

```bash
gh secret set LLM_API_KEY --body "sk-..."
gh variable set LLM_PROVIDER --body "openai_compatible"
gh variable set SEC_USER_AGENT --body "USMarketDailyXHS/0.1 (you@example.com)"
```

> 不要把 `.env` 提交到仓库；`.gitignore` 已覆盖 `.env`、`cookies.json`、`credentials.json`、`*.pem`。

### 2.3 触发与调度

```yaml
on:
  schedule:
    - cron: "30 22 * * 1-5"   # UTC 22:30
  workflow_dispatch:
    inputs: { run_date, mode, offline, template }
```

**关于 cron 的必须知道的事实**：

- GitHub Actions 的 `schedule` **不保证精确**，高峰期可能延迟 15–60 分钟甚至跳过；
- 因此本项目的目标交易日**由程序按美东时间解析为"最近一个已收盘交易日"**，而不是取触发日期；
- 发布若启用，也必须在发布前**重新校验时间窗口**，不得把工作流触发时间当作平台发布时间。

### 2.4 并发保护

```yaml
concurrency:
  group: us-market-daily-${{ github.event.inputs.run_date || github.run_id }}
  cancel-in-progress: false
```

同一 `run_date` 的重复触发会被合并/排队，避免重复生成内容。

### 2.5 产物与日志

- `data/<date>/` 与 `generate.log` 作为 artifact 上传，保留 14 天；
- 成功/失败摘要写入 `GITHUB_STEP_SUMMARY`；
- 结构化日志（JSON）写入 `data/<date>/run.log`，已脱敏。

### 2.6 每日操作流程（人工审核）

```text
1. 工作流运行完成 → artifact 内含 REVIEW.md 与图片
2. 下载 artifact，查看 data/<date>/content/report.md
3. 本地（或 Runner）执行：
   usmarket approve --date <date>
   usmarket publish --date <date>          # 默认 mock：仅验证流程
   或 usmarket publish（XHS_PUBLISHER=manual_export）→ 导出人工发布包
4. 人工在小红书发布后：
   usmarket mark-published --date <date> --remote-id "<笔记链接>"
```

> 若希望审核在 CI 中完成，可加一个 `workflow_dispatch` 输入 `approve=true`，
> 但本项目默认**不在无人值守情况下发布**。

---

## 3. 本地/服务器部署

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env && $EDITOR .env
sudo apt-get install -y fonts-noto-cjk     # 或 python scripts/fetch_fonts.py
usmarket check-config
usmarket generate --date 2026-10-26
```

### 3.1 systemd 定时（替代方案）

```ini
# /etc/systemd/system/usmarket.service
[Unit]
Description=US Market Daily generate
After=network-online.target

[Service]
Type=oneshot
User=usmarket
WorkingDirectory=/opt/BullSheet
EnvironmentFile=/opt/BullSheet/.env
ExecStart=/opt/BullSheet/.venv/bin/usmarket generate
```

```ini
# /etc/systemd/system/usmarket.timer
[Unit]
Description=Run US Market Daily after US close

[Timer]
# 22:30 UTC 周一至周五；系统时区需为 UTC 或自行换算
OnCalendar=Mon..Fri 22:30
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now usmarket.timer
journalctl -u usmarket.service -n 100
```

> 注意：`OnCalendar` 使用**系统本地时区**。美国夏令时切换时，若系统为 UTC 则无需调整；
> 若系统为美东时区，`OnCalendar=Mon..Fri 18:30` 会在冬令时提前一小时，请显式使用 UTC。

---

## 4. 存储与迁移

默认后端：`FileTaskStore`（`data/<date>/task.json` + `data/tasks.jsonl` 索引）。

- **原子写入**：写临时文件后 `os.replace`；
- **并发保护**：`.tasks.lock` + `fcntl.flock`（Windows 无 `fcntl` 时退化为原子替换）；
- **索引重建**：每次保存后重建 `tasks.jsonl`，可直接 `grep`/`jq` 查询。

### 4.1 迁移到 SQLite（可选）

`src/usmarket/storage/sqlite_store.py` 提供同接口的 SQLite 后端与 `migrate_from_files()`：

```python
from pathlib import Path
from usmarket.storage.sqlite_store import SqliteTaskStore

store = SqliteTaskStore(Path("state/tasks.db"))
store.migrate_from_files(Path("data"))
```

迁移是**幂等**的（按 `date` upsert），可重复执行。

### 4.2 备份

```bash
tar czf backup-$(date +%F).tgz data/ state/
```

> `data/` 已加入 `.gitignore`：既有体积原因，也因为 `run.log` 可能含运行痕迹。

---

## 5. 可观测性

| 关注点 | 位置 |
| --- | --- |
| 各源成败 | `data/<date>/raw/source_results.json` |
| 行情质量 | `data/<date>/raw/quotes.json` → `quality` / `quality_note` |
| 校验失败原因 | 日志 `[validation] ...`；`task.error` |
| 失败阶段 | `task.json` → `stage` ∈ `collect/generate/validation/render/publish` |
| 发布结果 | `data/<date>/publish/result.json` |

日志为 JSON（文件）/ 文本（stderr），字段：`ts`、`level`、`logger`、`msg`、`stage`、`date`、`source`、`symbol`、`task_id`。

**脱敏**：`RedactingFilter` 会处理 `api_key|token|secret|password|cookie|authorization|credential`
键值、JWT、Bearer、`sk-*`/`ghp_*` 前缀以及长 hex 串。

---

## 6. 回滚

```bash
# 内容问题：删除当日产物并重跑（发布前）
rm -rf data/2026-10-26 && usmarket generate --date 2026-10-26

# 代码回滚
git revert <commit>
```

已 `published` 的任务不允许被静默覆盖（`pipeline` 会报错），保证已发布内容可追溯。

---

## 7. 容量与成本估算

| 项 | 量级 |
| --- | --- |
| 单次运行产物 | 约 2–5 MB（7 张 1080×1440 PNG 占主要体积） |
| 单次运行时长 | 离线 < 5s；真实网络约 20–60s（20 个源并发 + 行情） |
| 新闻请求数 | 6 固定源 + N 个 ticker/主题检索 + N 个 EDGAR 请求 |
| LLM token | 单次约 6k–12k（输入含行情与 25 条新闻） |
| GitHub Actions | 约 2–4 分钟/次，免费额度内充裕 |

---

## 8. 上线检查清单

- [ ] `usmarket check-config` 通过
- [ ] `pytest tests -q` 全绿
- [ ] 中文字体可用（`FontMissingError` 不出现）
- [ ] `SEC_USER_AGENT` 已设置为真实联系邮箱
- [ ] Secrets 未出现在任何提交中（`git log -p | grep -i "api_key"`）
- [ ] 首次 `workflow_dispatch` 手动跑通
- [ ] 确认 `XHS_PUBLISHER=mock`（除非已完成真实发布验收）
- [ ] 人工审核流程责任人与 REVIEW.md 位置已对齐
