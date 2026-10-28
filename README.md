# US Market Daily · 美股每日简报

> 每个交易日自动采集美股新闻与行情 → AI 生成中文简报内容 → 渲染**一张长图**，每天早上从 GitHub 下载即可阅读。

**产出物**：每日一张 1080 宽的信息长图（标题、三大指数、概览、要闻、个股异动、明日关注、风险提示全部在一图内），附 Markdown 版文字稿与数据来源清单。

---

## 目录

- [项目能力概览](#项目能力概览)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [配置 AI API](#配置-ai-api)
- [配置新闻与行情数据源](#配置新闻与行情数据源)
- [本地运行](#本地运行)
- [生成指定日期的简报](#生成指定日期的简报)
- [简报图片说明](#简报图片说明)
- [配置 GitHub Actions](#配置-github-actions)
- [已验证 / 模拟实现清单](#已验证--模拟实现清单)
- [项目结构](#项目结构)
- [测试](#测试)
- [故障排查](#故障排查)
- [合规与许可](#合规与许可)

---

## 项目能力概览

| 模块 | 能力 | 实现状态 |
| --- | --- | --- |
| A 新闻采集 | RSS/Atom 多源 + SEC EDGAR；去重、时效过滤、来源分级、可信度标注 | ✅ 已验证（真实网络，20 源并发） |
| B 行情数据 | 三大指数 + 自选股；涨跌幅、前收、交易阶段；缺失/过期/异常标记 | ✅ 已验证（Yahoo chart 实测） |
| C AI 内容生成 | 可插拔 LLM（百炼 **已实测** / OpenAI 兼容 / Anthropic / 规则兜底）；结构化 JSON | ✅ 已验证（CI 真实产出） |
| D 简报图片 | **一张自适应高度长图**；中文排版；数据与文案一致 | ✅ 已验证 |
| E 定时调度 | GitHub Actions **手动触发** + concurrency + artifact | ✅ 已验证（真实运行成功） |
| F 任务管理 | 状态机、CLI、失败定位、重跑、幂等 | ✅ 已验证 |

**设计原则**（完整版见 `.specify/memory/constitution.md`）：

1. 行情数字只能来自真实数据源，缺失即标记 `数据缺失`，**禁止 AI 编造或补全**；
2. `published_at`（源提供）与 `fetched_at`（系统生成）严格分离；
3. 原始行情（`raw/quotes.json`）与 AI 文本（`content/content.json`）分开存储，每个数字可追溯；
4. 外部新闻只作为数据，不改变系统指令、不触发代码执行。

---

## 环境要求

- **Python 3.11+**（开发与验证环境为 3.13.12）
- 依赖：`requests`、`feedparser`、`Pillow`、`pydantic>=2`、`python-dateutil`、`pyyaml`、`typer`、`python-dotenv`
- **中文字体**（图片渲染必需）：
  - Windows：系统自带 `msyh.ttc` 即可
  - macOS：`PingFang.ttc`
  - Linux / CI：需安装 `fonts-noto-cjk` 或运行 `python scripts/fetch_fonts.py`
- 可选：`uv`（更快的安装器）

---

## 安装步骤

```bash
cd BullSheet

# 创建虚拟环境（任选其一）
python -m venv .venv && source .venv/bin/activate     # Linux/macOS
python -m venv .venv && .venv\Scripts\activate        # Windows PowerShell

# 安装
pip install -e ".[dev]"
# 或使用 uv（依赖已锁定在 uv.lock）：
uv sync --extra dev

# 复制环境变量模板
cp .env.example .env        # Windows: copy .env.example .env

# 自检（不会打印任何密钥值）
usmarket check-config
```

---

## 配置 AI API

LLM 通过环境变量配置。**不配置 key 也能完整运行**（规则兜底生成）。

### 方式一：阿里百炼 / DashScope（已实测，推荐）

```env
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxxxxxxx
```

只有两行：端点与模型（`qwen3.8-flash`）自动填充。可选覆盖：

```env
LLM_MODEL=qwen3.8-max              # 可选：flash/max/27b
LLM_EXTRA_BODY_JSON={"chat_template_kwargs": {"enable_thinking": false}}
LLM_TIMEOUT_SECONDS=180
```

- `LLM_EXTRA_BODY_JSON` 关闭思考链（**百炼专有**）：开启时单次生成约 100–120s，关闭后约 30–40s
- 查看当前 key 可用的模型：`usmarket llm-models --contains qwen`

### 方式二：OpenAI 兼容端点

```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

兼容 OpenAI / DeepSeek / OpenRouter / Moonshot / GitHub Models 等所有 `/v1/chat/completions` 端点。

### 方式三：Anthropic（代码完成，未实测）

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

### 方式四：规则兜底（默认，无需 key）

```env
LLM_PROVIDER=rule_based
```

只复用已核实的行情与新闻数字，不做翻译、不推测。产物 `generator=rule_based`。

### 连通性自检

```bash
usmarket llm-check          # 真实调用一次，报告延迟与 JSON 可解析性
```

> **失败兜底**：LLM 超时、报错或输出未通过校验（自动重试 1 次）后，系统回退规则式生成并记录告警，绝不把未经校验的内容用于产出。

---

## 配置新闻与行情数据源

### 新闻源

默认启用 6 个实测可用的源 + SEC EDGAR：

| 来源 | 类型 | 可信度 |
| --- | --- | --- |
| CNBC RSS | 市场新闻 | established |
| MarketWatch RSS | 市场新闻 | established |
| Google News Business / 按 ticker 搜索 | 聚合 | aggregator |
| 美联储新闻稿 RSS | 官方宏观 | official |
| Investing.com RSS | 市场新闻 | established |
| SEC EDGAR（8-K 公告） | 官方公告 | official |

自定义股票与主题（`config/default.yaml`）：

```yaml
watchlist:
  indices: ["^GSPC", "^IXIC", "^DJI"]
  tickers: ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"]
  topics: ["earnings", "fed", "inflation", "ai", "semiconductor"]
```

或 CLI 覆盖：`usmarket generate --tickers NVDA,TSLA`。

**SEC EDGAR 必须声明身份**（否则 403）：

```env
SEC_USER_AGENT="USMarketDaily/0.1 (your-email@example.com)"
```

### 行情源

```env
MARKET_PROVIDER=yahoo          # yahoo（默认，无需 key）| finnhub | mock
MARKET_STALE_MINUTES=60
```

- **`yahoo`**：`query1.finance.yahoo.com/v8/finance/chart/<symbol>`，支持原始指数代码。⚠️ 非公开接口，无 SLA，失败时该标的标记 `数据缺失`
- **`finnhub`**：需 key；免费档不支持 `^GSPC/^IXIC/^DJI`
- **`mock`**：读取 `tests/fixtures/quotes.json`，完全离线（测试用，**数据是假的**）

**交易阶段**由程序按美东时区自行判定（盘前/盘中/盘后/休市，含 NYSE 节假日与夏令时）。

---

## 本地运行

```bash
# 状态自检
usmarket check-config

# LLM 连通性自检（不配置 LLM 时可跳过）
usmarket llm-check

# 生成今天的简报（自动解析最近已收盘交易日；联网+百炼约 2 分钟）
usmarket generate

# 完全离线（测试数据，数据是假的，仅看排版）
usmarket generate --date 2026-10-26 --offline

# 查看任务
usmarket list
usmarket show --date 2026-10-26
```

产物目录：

```
data/2026-10-28/
├── images/
│   ├── cover.png           ← 简报长图（唯一产出图片）
│   └── manifest.json
├── content/
│   ├── content.json        # 结构化内容
│   ├── report.md           # Markdown 文字稿
│   └── sources.md          # 来源与数据清单
├── raw/
│   ├── news.jsonl          # 原始新闻
│   └── quotes.json         # 原始行情（provider 原始片段，可追溯）
├── task.json               # 任务状态
└── run.log                 # 结构化日志（已脱敏）
```

---

## 生成指定日期的简报

```bash
usmarket generate --date 2026-10-26
```

**休市处理**：目标日是周末/节假日或尚未收盘时，自动使用"最近一个已收盘交易日"并在图中明确标注。

---

## 简报图片说明

**默认产出**：`one_page` 单图模板——一张 1080 宽、高度自适应（约 2500–3000）的长图：

```
2026-10-27 美股收盘速览
AI 撰写的中文标题
────────────────────────
标普500 / 纳指 / 道指（真实行情卡片）
今日概览（AI 撰写）
要闻速递 3–5 条（中文标题+解读+来源时间）
个股异动 6 只
明日关注
风险提示
数据来源 + 免责声明
```

示例：
- `docs/examples/one_page_llm.png` —— **百炼真实生成的单图**（推荐先看）
- `docs/examples/one_page.png` —— 离线测试数据版
- `docs/examples/llm_report_example.md` —— Markdown 文字稿

另有两种多页模板可选（非默认）：

| 模板 | 说明 |
| --- | --- |
| `daily_review` | 多页复盘：封面 + 5–7 页正文 |
| `flash_brief` | 重大新闻专题：每条新闻一页 |

```bash
usmarket render --date 2026-10-26 --template one_page     # 单图（默认）
usmarket render --date 2026-10-26 --template daily_review # 多页
```

**可配置项**（`config/default.yaml` → `image`）：

```yaml
image:
  width: 1080
  template: one_page      # 默认单图
  margin: 80
  theme:
    background: "#0F172A"   # 背景
    surface: "#16213E"      # 卡片
    accent: "#F97316"       # 强调色
    positive: "#22C55E"     # 上涨
    negative: "#EF4444"     # 下跌
    font_regular: ""        # 留空自动探测系统中文字体

account:
  name: 美股日报             # 图片底部署名
```

**渲染保证**：
- 中英混排换行，不在"标普500"这类词中间断行；
- 超长文本截断加省略号，不溢出画布；
- 每张图渲染后做"非空白"检查；
- 图片中的数字与 `content.json` 同源（测试中比对），AI 文案中的 emoji/Markdown 在渲染前剥离（文字稿保留原样）。

---

## 配置 GitHub Actions

工作流：`.github/workflows/daily.yml`。

| 触发方式 | 说明 |
| --- | --- |
| `workflow_dispatch` | **仅手动触发**（不设定时，按需运行节省 token）：Actions 页面 → Run workflow，可指定 `run_date` / `template` / `offline` |

**使用方式**：想看简报时，打开
https://github.com/Ethanwu23/BullSheet/actions → 选择 US Market Daily → Run workflow → 等几分钟 → 下载 artifact（zip 解压即得长图 + 文字稿）。

**关键设计**：
- 目标交易日按美东时间解析"最近一个已收盘交易日"，不依赖触发时间——**任何时候手动触发都能得到正确的最新简报**
- `concurrency` 避免同日重复生成
- 失败时自动上传日志为 artifact 并写入失败摘要
- 凭据通过 **GitHub Secrets** 注入

### 需要配置的 Secrets / Variables

| 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `DASHSCOPE_API_KEY` | Secret | 用百炼时必填 | 百炼密钥 |
| `LLM_PROVIDER` | Variable | 否 | `dashscope`（已配置） |
| `LLM_MAX_TOKENS` | Variable | 否 | 默认 8000（低于 4000 会截断） |
| `SEC_USER_AGENT` | Variable | 建议 | 形如 `App/0.1 (you@example.com)` |
| `IMAGE_TEMPLATE` | Variable | 否 | 默认 `one_page` |

### 手动重跑某天

```bash
gh workflow run daily.yml -f run_date=2026-10-26
# 或本地
usmarket generate --date 2026-10-26
```

---

## 已验证 / 模拟实现清单

以**实际执行**为准，不以文档声称。

### ✅ 已通过真实测试

| 项目 | 验证方式 |
| --- | --- |
| `pytest` 全量测试 | 232 passed / 4 skipped |
| **LLM 真实生成（百炼 qwen3.8-flash）** | CI 真实运行：`generator=openai_compatible`，单图产出通过全部校验 |
| GitHub Actions 定时任务 | 真实自动触发并成功（含中文字体安装、测试、生成、上传 artifact） |
| 单图模板（CI 真实产出） | 1 张长图 + Markdown 文字稿，604KB |
| Yahoo chart 行情（三大指数） | 真实请求，`usable=10/10` |
| 20 个新闻源并发采集 | 真实请求，全部成功 |
| LLM 失败重试 | 单次抖动不降级（测试） |
| 日志脱敏 | 测试断言日志中无 cookie/token/password |
| 数字可追溯校验 | 编造数字 100% 被拦截（测试） |
| 交易阶段/DST/节假日 | 单元测试覆盖 |

### ⚠️ 未实测 / 已知限制

| 项目 | 状态 |
| --- | --- |
| Anthropic provider | 代码完成，本机无 key，未实测 |
| Finnhub / Alpha Vantage | 未实测（无 key）；Alpha Vantage 未实现 |
| Yahoo 非公开接口 | 无 SLA，可能限流或变更；失败时标记缺失，不编造 |

详见 [`docs/limitations.md`](docs/limitations.md)。

---

## 项目结构

```
BullSheet/
├── src/usmarket/
│   ├── config.py              # YAML + env + CLI 三级配置，敏感项校验
│   ├── logging_setup.py       # 结构化日志 + 凭据脱敏
│   ├── collectors/            # RSS/Atom、SEC EDGAR、采集编排
│   ├── market_data/           # provider、交易日历、阶段判定、质量标记
│   ├── processors/            # 清洗、去重、分类、时效过滤
│   ├── ai/                    # LLM Provider 抽象、prompt、规则兜底
│   ├── validation/            # 结构 / 数字 / 来源 / 合规校验
│   ├── content/               # Markdown、JSON、来源清单
│   ├── image_renderer/        # 字体、排版、主题、三种模板（one_page 默认）
│   ├── scheduler/             # 触发时间 → 目标交易日
│   ├── storage/               # 任务模型、状态机、文件存储
│   └── cli/                   # Typer 命令与端到端 pipeline
├── config/default.yaml
├── tests/{unit,integration,fixtures}
├── docs/
├── .github/workflows/daily.yml
└── specs/
```

---

## 测试

```bash
python -m pytest tests -q                        # 全量离线测试
$env:NETWORK_TESTS=1; python -m pytest tests/integration/test_network_sources.py -m network -q   # 真实数据源
python -m ruff check src tests                   # 静态检查
```

---

## 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `FontMissingError` | 系统无中文字体 | 安装 `fonts-noto-cjk` 或 `python scripts/fetch_fonts.py` |
| `敏感配置缺失: LLM_API_KEY` | 选了 LLM 但没 key | 填 key 或 `LLM_PROVIDER=rule_based` |
| **数据不对** | 跑了 `--offline`（测试样本，provider=mock） | 去掉 `--offline`；查 `raw/quotes.json` 的 `provider` 是否为 `yahoo` |
| 行情显示"数据缺失" | provider 失败；**这是正确行为** | 看 `raw/quotes.json` 的 `quality_note` |
| SEC 返回 403 | 未声明 User-Agent | 设置 `SEC_USER_AGENT` |
| `LLM 生成失败: ReadTimeout` | 生成超时 | `LLM_TIMEOUT_SECONDS=180` + 关思考链（见上文） |
| `LLM 输出被 max_tokens 截断` | 输出 token 不够 | 调大 `LLM_MAX_TOKENS`（默认 8000） |
| `[validation] 数字找不到出处` | LLM 编造数字 | **正确行为**，已拦截；换模型或降 temperature |
| 图片空白方块 | 文案含 emoji | 渲染前已自动剥离；文字稿保留原样 |
| 想直接看生成内容 | — | `python scripts/inspect_content.py data/<date>` |
| 任务卡在 `failed` | 某阶段失败 | `usmarket show --date <date>` 看 `stage` 与 `error` |
| Actions 定时不准 | GitHub cron 延迟 | 设计已规避：按"最近已收盘交易日"解析 |

---

## 合规与许可

- 本项目代码：**MIT**。
- 第三方内容与条款：
  - RSS 内容版权归原媒体所有；本项目仅引用标题与摘要并保留原始链接，不做全文转载。
  - Yahoo 为非公开接口，无 SLA；商用前请自行评估其服务条款。
  - SEC EDGAR 为公共数据，要求声明式 User-Agent（已实现）。
- **未复用**任何无 LICENSE 的开源项目代码，详见 [`docs/decisions.md`](docs/decisions.md)。

> 本项目输出**不构成投资建议**。行情数据可能存在延迟，请以交易所与官方渠道为准。
