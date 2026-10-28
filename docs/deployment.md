# 部署与运维手册

**版本**：v2 ｜ **日期**：2026-10-28

---

## 1. 部署形态

| 形态 | 适用 | 说明 |
| --- | --- | --- |
| GitHub Actions（推荐） | 每日自动简报 | `.github/workflows/daily.yml`，已真实运行验证 |
| 本地 CLI | 补跑某天、开发调试 | `usmarket generate --date ...` |
| 自托管 cron + 容器 | 内网/合规要求 | 见 §5 |

**核心事实**：本项目的产出是**每日一张简报长图 + Markdown 文字稿**，从 GitHub artifact 获取，不涉及任何平台发布。

---

## 2. GitHub Actions 部署

### 2.1 前置

1. 仓库推送到 GitHub；
2. 创建必要的 Secrets / Variables（见 §2.2）。

### 2.2 Secrets 与 Variables

| 名称 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `DASHSCOPE_API_KEY` | Secret | 用百炼时必填 | — | 百炼密钥 |
| `LLM_PROVIDER` | Variable | 否 | `rule_based` | 已配置 `dashscope` |
| `LLM_MAX_TOKENS` | Variable | 否 | `8000` | 低于 4000 会截断输出 |
| `LLM_EXTRA_BODY_JSON` | Variable | 否 | 关思考链 JSON | 百炼专有 |
| `IMAGE_TEMPLATE` | Variable | 否 | `one_page` | 简报模板 |
| `SEC_USER_AGENT` | Variable | 建议 | — | 形式 `App/ver (email)`，否则 SEC 403 |

> 不要把 `.env` 提交到仓库；`.gitignore` 已覆盖 `.env`、`cookies.json`、`credentials.json`、`*.pem`。

### 2.3 触发与调度

```yaml
on:
  schedule:
    - cron: "30 22 * * 1-5"   # UTC 22:30，美东收盘后
  workflow_dispatch:
    inputs: { run_date, mode, offline, template }
```

**关于 cron 的必须知道的事实**：

- GitHub Actions 的 `schedule` **不保证精确**，高峰期可能延迟 15–60 分钟；
- 因此目标交易日**由程序按美东时间解析为"最近一个已收盘交易日"**，而不是取触发日期。

### 2.4 并发保护

```yaml
concurrency:
  group: us-market-daily-${{ github.event.inputs.run_date || github.run_id }}
  cancel-in-progress: false
```

同一 `run_date` 的重复触发会被合并/排队。

### 2.5 产物与日志

- `data/<date>/` 与 `generate.log` 作为 artifact 上传，保留 14 天；
- 失败时写入 `GITHUB_STEP_SUMMARY` 失败摘要；
- 结构化日志（JSON）写入 `data/<date>/run.log`，已脱敏。

### 2.6 每日使用

```text
1. 工作流自动运行 → artifact 内含简报长图与文字稿
2. 打开 Actions 页面下载最新 artifact（zip 解压即得）
3. 阅读图片或 Markdown 文字稿
```

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
OnCalendar=Mon..Fri 22:30
Persistent=true

[Install]
WantedBy=timers.target
```

> `OnCalendar` 使用系统本地时区；建议系统为 UTC，避免夏令时切换时需要调整。

---

## 4. 存储与迁移

默认后端：`FileTaskStore`（`data/<date>/task.json` + `data/tasks.jsonl` 索引）。

- **原子写入**：写临时文件后 `os.replace`
- **索引重建**：每次保存后重建 `tasks.jsonl`

可选 SQLite 后端与迁移（幂等，可重复执行）：

```bash
python -m usmarket.storage.migrate --data-dir data --db state/tasks.db
```

### 4.1 备份

```bash
tar czf backup-$(date +%F).tgz data/ state/
```

---

## 5. 可观测性

| 关注点 | 位置 |
| --- | --- |
| 各源成败 | `data/<date>/raw/source_results.json` |
| 行情质量 | `data/<date>/raw/quotes.json` → `quality` / `quality_note` |
| 校验失败原因 | 日志 `[validation] ...`；`task.error` |
| 失败阶段 | `task.json` → `stage` |
| LLM 诊断 | `finish_reason` / `content_len` / `completion_tokens`（generate 日志） |

**脱敏**：`RedactingFilter` 处理 `api_key|token|secret|password|cookie|authorization` 等键值与常见 token 前缀。

---

## 6. 回滚

```bash
# 内容问题：删除当日产物并重跑
rm -rf data/2026-10-26 && usmarket generate --date 2026-10-26

# 代码回滚
git revert <commit>
```

---

## 7. 容量与成本估算

| 项 | 量级 |
| --- | --- |
| 单次运行产物 | 单图约 500–650KB + 文字稿 |
| 单次运行时长 | 离线 < 5s；CI 全流程约 3–5 分钟 |
| 新闻请求数 | 6 固定源 + N 个 ticker 检索 + N 个 EDGAR 请求 |
| LLM token | 单次约 3k–8k（qwen3.8-flash，月成本约几毛到几块钱人民币） |
| GitHub Actions | 约 3–5 分钟/次，免费额度内充裕 |

---

## 8. 上线检查清单

- [ ] `usmarket check-config` 通过
- [ ] `pytest tests -q` 全绿
- [ ] 中文字体可用（`FontMissingError` 不出现）
- [ ] `SEC_USER_AGENT` 已设置为真实联系邮箱
- [ ] Secrets 未出现在任何提交中
- [ ] 首次 `workflow_dispatch` 手动跑通
- [ ] 下载 artifact 确认单图质量
