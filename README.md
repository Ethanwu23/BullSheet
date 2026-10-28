# US Market Daily · 美股每日简报

> 每个交易日采集美股行情与新闻 → 确定性生成数据内容 → LLM 只做两件事（**盘后总结** + **要闻标题中译**）→ 渲染**一张长图**。
>
> 行情数字全程不经过模型，从数据源到图片逐位可追溯。

**产出物**（每天一份，本地或 GitHub Actions 手动触发）：

| 文件 | 内容 |
| --- | --- |
| `images/cover.png` | 简报长图（1080 宽，高度自适应）：标题、三大指数、概览、要闻速递、个股异动（七姐妹+SpaceX，收盘价）、风险提示与数据来源 |
| `content/evening_summary.txt` | 盘后总结（120–180 字中文，AI 撰写，可直接复制配图分享） |
| `content/report.md` | 完整 Markdown 文字稿 |
| `content/sources.md` | 数据来源与限制清单 |

示例：`docs/examples/one_page_llm.png`（真实产出）、`evening_summary_example.txt`、`llm_report_example.md`。

---

## 目录

- [快速开始](#快速开始)
- [核心设计](#核心设计)
- [配置](#配置)
- [GitHub Actions](#github-actions)
- [已验证清单](#已验证清单)
- [故障排查](#故障排查)
- [项目结构](#项目结构)
- [测试](#测试)
- [许可](#许可)

---

## 快速开始

```bash
# 安装（Python 3.11+）
pip install -e ".[dev]"            # 或 uv sync --extra dev
cp .env.example .env               # 填入 DASHSCOPE_API_KEY（可选，见下）

# 生成今天的简报（约 1-2 分钟：真实行情+新闻 → 百炼 → 单图）
usmarket generate

# 查看产物
explorer data\<日期>\images        # 长图
notepad data\<日期>\content\evening_summary.txt   # 盘后总结文字
python scripts/inspect_content.py data\<日期>     # 命令行看全部内容
```

**不想配 LLM 也能跑**：`LLM_PROVIDER=rule_based`（默认）时全部内容由规则式生成，要闻标题为英文原文，数字同样准确。

常用命令：

| 命令 | 用途 |
| --- | --- |
| `usmarket generate` | 生成最近已收盘交易日的简报 |
| `usmarket generate --date 2026-10-27` | 指定日期 |
| `usmarket generate --offline --date 2026-10-26` | 离线测试（**假数据**，只看排版） |
| `usmarket llm-check` | LLM 连通性自检 |
| `usmarket list` / `show --date <日期>` | 任务状态与失败原因 |

---

## 核心设计

### 1. 行情数字不经过模型（ADR-016）

```
行情快照 ──► 规则式确定性生成 ──► 基础内容（指数表/个股表/来源/文案）
                                    │
新闻 ──────► LLM 窄任务（仅两样）：  ▼
              ① 盘后总结一段      合并（只替换这两处）→ 校验 → 产出
              ② 要闻标题英→中
```

- 指数、个股、涨跌幅、来源链接、时间等字段**由代码确定性生成**，模型在机制上无法改动；
- LLM 输出合并前仍过完整校验（数字可追溯/来源/合规），失败重试一次后沿用规则式内容；
- 合并后 `generator=hybrid`；纯规则式为 `rule_based`。

### 2. 收盘数据口径（ADR-017）

涨跌幅一律使用**日线收盘序列**：最近已收盘交易日的收盘价 vs 前一日收盘价。盘中运行自动跳过未收盘 bar；日线滞后时如实标记 STALE，绝不冒充。

> 历史教训：曾误用 Yahoo `chartPreviousClose`（5 日窗口基数），导致显示的是约 5 日累计涨幅（TSLA 显示 +9.03% 而真实昨涨 +4.04%）。已修复并有回归测试。

### 3. 数据缺失如实呈现

SpaceX 之外任何标的取不到行情时显示"数据缺失"卡片，禁止编造或用占位数字补全；发布前的数字校验 fail-closed。

---

## 配置

`.env`（或 GitHub Variables/Secrets）：

```env
LLM_PROVIDER=dashscope            # dashscope | openai_compatible | anthropic | rule_based
DASHSCOPE_API_KEY=sk-xxx          # dashscope 时仅需此项
LLM_EXTRA_BODY_JSON={"chat_template_kwargs": {"enable_thinking": false}}  # 关思考链，30-40s
LLM_MAX_TOKENS=8000
MARKET_PROVIDER=yahoo             # 默认，无需 key
SEC_USER_AGENT="USMarketDaily/0.1 (you@example.com)"   # SEC 要求，否则 403
```

**自选股**（`config/default.yaml`）：默认七姐妹 + SPCX（SpaceX，NASDAQ 已上市）：

```yaml
watchlist:
  indices: ["^GSPC", "^IXIC", "^DJI"]
  tickers: ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "SPCX"]
```

**图片主题**（`config/default.yaml` → `image.theme`）：背景/强调色/涨跌色/字体均可配置，留空自动探测系统中文字体。

模板：`one_page`（默认，单张长图）；`daily_review` / `flash_brief`（多页，备用）。

---

## GitHub Actions

**仅手动触发**（不设定时，按需运行节省 token）：

1. 打开 https://github.com/Ethanwu23/BullSheet/actions
2. US Market Daily → Run workflow（可指定 `run_date` / `template`）
3. 等 3–5 分钟 → 下载 artifact（zip 解压即得长图 + 总结 + 文字稿）

所需配置（已在仓库设置）：Secret `DASHSCOPE_API_KEY`；Variable `LLM_PROVIDER=dashscope`。

> **Fork 说明**：GitHub Secrets 不会随 fork 传播。fork 本项目后 workflow 可以运行，
> 但 LLM 会回退规则式（英文标题、数字仍准确）；如需 AI 总结/翻译，请在自己的
> 仓库 Settings → Secrets 配置 `DASHSCOPE_API_KEY`（或改用任意 OpenAI 兼容端点）。

---

## 已验证清单

以实际执行为准（详见 `specs/001-us-market-daily-xhs/checklists/implementation.md`）：

| 项 | 状态 |
| --- | --- |
| 全量测试 | **242 passed / 4 skipped** |
| 行情收盘口径 | ✅ 实测 TSLA +4.04%（修复前误显示 +9.03%），昨收→今收逐位正确 |
| LLM 窄任务（百炼 qwen3.8-flash） | ✅ generator=hybrid，中文标题+总结，数字与行情层逐位一致 |
| 行情不经过模型 | ✅ 专项测试锁定（`test_market_data_never_passes_through_llm`） |
| 个股=七姐妹+SPCX | ✅ 强制过滤杂股+补齐漏写，恰好 8 只 |
| 单图渲染 | ✅ 一张长图，非空白/断行/数字一致均有测试 |
| GitHub Actions | ✅ 真实运行成功（手动触发，含字体/测试/生成/上传） |
| 日志脱敏 | ✅ 无 token/cookie/password 泄漏（测试断言） |

**已知限制**：Anthropic provider 未实测（无 key）；Yahoo 为非公开接口无 SLA；LLM 失败时兜底为英文标题（数字不受影响）。详见 `docs/limitations.md`。

---

## 故障排查

| 现象 | 处理 |
| --- | --- |
| 数据不对 | 检查是否用了 `--offline`（假数据）；看 `raw/quotes.json` 的 `provider` 是否 `yahoo` |
| `FontMissingError` | 安装 `fonts-noto-cjk` 或 `python scripts/fetch_fonts.py` |
| LLM 超时 | `LLM_TIMEOUT_SECONDS=180` + 关思考链（见配置） |
| LLM 截断 | 调大 `LLM_MAX_TOKENS`（默认 8000） |
| 要闻是英文 | LLM 窄任务失败兜底所致；查 `run.log` 中「LLM 窄任务失败」原因，多为临时网络问题，重跑即可 |
| 任务失败 | `usmarket show --date <日期>` 看阶段与错误，修复后 `usmarket rerun` |

---

## 项目结构

```
src/usmarket/
├── collectors/        # RSS/Atom 多源 + SEC EDGAR
├── market_data/       # Yahoo provider（日线收盘口径）、交易日历、阶段判定
├── processors/        # 清洗、去重、分类、时效过滤
├── ai/                # LLM 窄任务（总结+翻译）、规则式基础生成
├── validation/        # 数字可追溯/来源/合规校验
├── content/           # Markdown/JSON/来源清单落盘
├── image_renderer/    # 字体、中文排版、one_page 模板（默认）
├── storage/           # 任务状态机（文件后端，可选 SQLite）
└── cli/               # usmarket 命令
```

SDD 产物：`specs/001-us-market-daily-xhs/`（spec / plan / tasks / analyze / checklists）；
决策记录：`docs/decisions.md`（ADR-001 ~ 017）。

---

## 测试

```bash
python -m pytest tests -q                          # 全量离线（无需网络/key）
$env:NETWORK_TESTS=1; python -m pytest tests/integration/test_network_sources.py -m network -q
python -m ruff check src tests
```

---

## 许可

MIT。数据来源条款：RSS 内容版权归原媒体（仅引用标题摘要并保留链接）；Yahoo 非公开接口无 SLA；SEC EDGAR 公共数据需声明 User-Agent。

> 本项目输出不构成投资建议。行情可能存在延迟，请以交易所与官方渠道为准。
