# US Market Daily Xiaohongshu · 美股每日情报与小红书图文自动化

> 每天自动采集美股新闻与行情 → 用 AI（或规则兜底）生成中文结构化内容 → 渲染竖屏图文 → **人工审核** → 发布（默认模拟）。
>
> **发布状态说明（务必先读）**：本项目**未实现经真实验收的小红书自动发布**。
> 默认使用模拟发布器（`mock`）或人工发布包导出（`manual_export`），产物中
> `simulated=true` / `verified=false`。详见 [发布能力](#发布能力与真实验收状态)。

---

## 目录

- [项目能力概览](#项目能力概览)
- [环境要求](#环境要求)
- [安装步骤](#安装步骤)
- [配置 AI API](#配置-ai-api)
- [配置新闻与行情数据源](#配置新闻与行情数据源)
- [本地运行](#本地运行)
- [生成指定日期的日报](#生成指定日期的日报)
- [生成图文图片](#生成图文图片)
- [配置 GitHub Actions](#配置-github-actions)
- [审核与发布](#审核与发布)
- [已验证 / 模拟实现清单](#已验证--模拟实现清单)
- [项目结构](#项目结构)
- [测试](#测试)
- [故障排查](#故障排查)
- [合规与许可](#合规与许可)

---

## 项目能力概览

| 模块 | 能力 | 实现状态 |
| --- | --- | --- |
| A 新闻采集 | RSS/Atom 多源 + SEC EDGAR；去重、时效过滤、来源分级、可信度标注 | ✅ 已验证（真实网络） |
| B 行情数据 | 三大指数 + 自选股；涨跌幅、前收、成交量、交易阶段；缺失/过期/异常标记 | ✅ 已验证（Yahoo chart 实测） |
| C AI 内容生成 | 可插拔 LLM（OpenAI 兼容 / Anthropic / 规则兜底）；结构化 JSON 输出 | ✅ 已验证（规则兜底 + 校验链路）；LLM 需自备 key |
| D 图文生成 | 封面 + 5–7 张正文图；两种模板；中文排版；数据与文案一致 | ✅ 已验证 |
| E 发布管理 | 适配器接口；mock / manual_export / browser(未验收)；幂等 + 重试 | ⚠️ **模拟实现**（真实发布未验收） |
| F 定时调度 | GitHub Actions cron + 手动触发 + concurrency + artifact + 失败摘要 | ✅ 配置已就绪（未在真实仓库跑过） |
| G 审核与任务 | 8 状态机、CLI、REVIEW.md、失败定位、重跑、幂等 | ✅ 已验证 |

**设计原则**（完整版见 `.specify/memory/constitution.md`）：

1. 行情数字只能来自真实数据源，缺失即标记 `数据缺失`，**禁止 AI 编造或补全**；
2. `published_at`（源提供）与 `fetched_at`（系统生成）严格分离；
3. 原始行情（`raw/quotes.json`）与 AI 文本（`content/content.json`）分开存储；
4. 外部新闻只作为数据，不改变系统指令、不触发代码执行；
5. 默认人工审核，未 `approved` 不允许发布；
6. 发布幂等（内容指纹 + idempotency key），重试不产生重复发布。

---

## 环境要求

- **Python 3.11+**（开发与验证环境为 3.13.12）
- 依赖：`requests`、`feedparser`、`Pillow`、`pydantic>=2`、`python-dateutil`、`pyyaml`、`typer`、`python-dotenv`
- **中文字体**（图片渲染必需）：
  - Windows：系统自带 `msyh.ttc` 即可
  - macOS：`PingFang.ttc`
  - Linux / CI：需安装 `fonts-noto-cjk` 或运行 `python scripts/fetch_fonts.py`
- 可选：`uv`（更快的安装器）、`specify-cli`（SDD 工具链，仅开发规格时需要）

---

## 安装步骤

```bash
# 1. 获取代码
cd BullSheet

# 2. 创建虚拟环境（任选其一）
python -m venv .venv && source .venv/bin/activate     # Linux/macOS
python -m venv .venv && .venv\Scripts\activate        # Windows PowerShell

# 3. 安装（可编辑模式，含开发依赖）
pip install -e ".[dev]"

# 或使用 uv（可复现安装，依赖已锁定在 uv.lock）：
uv sync --extra dev
# 不建虚拟环境时：uv pip install --system -e ".[dev]"

# 4. 复制环境变量模板
cp .env.example .env        # Windows: copy .env.example .env

# 5. 自检（不会打印任何密钥值）
usmarket check-config
```

`usmarket` 命令安装后即可使用；不用 `pip install -e` 也可 `python -m usmarket.cli.main`。

**中文字体准备**（Linux/CI 必做）：

```bash
sudo apt-get install -y fonts-noto-cjk     # 系统级
# 或者把字体放到项目内（不入库）：
python scripts/fetch_fonts.py              # 下载 Noto Sans SC 到 assets/fonts/
```

若找不到中文字体，渲染会抛出明确的 `FontMissingError`，**不会产出乱码图片**。

---

## 配置 AI API

LLM 通过环境变量配置，**不写死在配置文件中**。四种 provider：

### 方式一：阿里百炼 / DashScope（已实测）

```env
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxxxxxxx
```

只有两行。端点（`https://dashscope.aliyuncs.com/compatible-mode/v1`）与模型
（`qwen3.8-flash`）自动填充；也可显式覆盖：

```env
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxxxxxxx
LLM_MODEL=qwen3.8-max              # 可选：qwen3.8-flash / qwen3.8-max / qwen3.8-27b …
LLM_EXTRA_BODY_JSON={"chat_template_kwargs": {"enable_thinking": false}}
LLM_TIMEOUT_SECONDS=180
```

- `LLM_EXTRA_BODY_JSON` 用于关闭思考链（**百炼专有参数**，其他 provider 请勿设置）。
  实测：开启思考链时一次完整复盘生成约 100–120s，容易触到默认超时；
  关闭后约 30–40s。本项目对超时有兜底（回退规则式），但会额外消耗时间。
- 查看当前 key 可用的 model id：

```bash
usmarket llm-models --contains qwen3.8
```

### 方式二：OpenAI 兼容端点（覆盖面最广）

```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-xxxxxxxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4000
```

`LLM_BASE_URL` 换成任意 OpenAI 兼容端点即可：

| 服务 | LLM_BASE_URL | LLM_MODEL 示例 |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| GitHub Models | `https://models.inference.ai.azure.com` | `gpt-4o-mini` |

（百炼也可用这种方式，但推荐上面的 `dashscope` 预设。）

### 方式三：Anthropic

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

（代码已完成，**未实测**——本机无该 key。）

### 方式四：不配置（规则兜底）

```env
LLM_PROVIDER=rule_based
```

**不需要任何 key 即可完整跑通**。规则生成器只复用已核实的行情与新闻数字，
不做翻译、不推测、不给预测；产物 `generator=rule_based`，需人工复核。

### 连通性自检

```bash
usmarket llm-check          # 真实调用一次，报告延迟、原始响应与 JSON 可解析性
usmarket llm-check --model qwen3.8-max
```

```
provider  : dashscope
端点      : https://dashscope.aliyuncs.com/compatible-mode/v1
模型      : qwen3.8-flash
调用成功：2.58s，响应 32 字符
JSON 解析: 通过
```

> **失败兜底**：LLM 超时、报错，或输出未通过校验（数字对不上 / 来源缺失 / 违规表述 / 枚举值不规范），
> 系统会**回退到规则式生成**并记录告警，绝不会把未经校验的 LLM 内容用于发布。
> 模型常把 `market_phase` 写成 `pre-market`、`confidence` 写成 `事实`，这些同义写法会被归一化后放行。

---

## 配置新闻与行情数据源

### 新闻源

编辑 `config/default.yaml` 的 `news.feeds`（也可用环境变量覆盖超时与回看窗口）。

默认启用 **6 个已实测可用**的源：

| 来源 | 类型 | 可信度 |
| --- | --- | --- |
| CNBC RSS | 市场新闻 | established |
| MarketWatch RSS（`feeds.content.dowjones.io`） | 市场新闻 | established |
| Google News Business RSS | 聚合 | aggregator |
| Google News 按 ticker 搜索 RSS | 聚合 | aggregator |
| 美联储新闻稿 RSS | 官方宏观 | official |
| Investing.com RSS | 市场新闻 | established |
| SEC EDGAR（8-K，按 ticker） | 官方公告 | official |

**已实测失效、默认禁用**：`https://finance.yahoo.com/news/rssindex`（HTTP 404）。
配置中保留为 `enabled: false` 以记录调查结论。

**SEC EDGAR 必须声明身份**，否则返回 403：

```env
SEC_USER_AGENT="USMarketDailyXHS/0.1 (your-email@example.com)"
```

自定义股票与主题：

```yaml
watchlist:
  indices: ["^GSPC", "^IXIC", "^DJI"]
  tickers: ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"]
  topics: ["earnings", "fed", "inflation", "ai", "semiconductor"]
```

或用 CLI（优先级最高）：`usmarket generate --tickers NVDA,TSLA --date 2026-10-26`
或环境变量 `USMARKET_TICKERS=NVDA,TSLA`。

### 行情源

```env
MARKET_PROVIDER=yahoo          # yahoo（默认，无需 key）| finnhub | mock
MARKET_STALE_MINUTES=60
FINNHUB_API_KEY=
```

- **`yahoo`（默认）**：`query1.finance.yahoo.com/v8/finance/chart/<symbol>`。
  实测（2026-10-27）返回 `^GSPC 7676.77`、`^IXIC 26169.38`、`^DJI 52361.58`，
  支持原始指数代码，提供 `chartPreviousClose` / `regularMarketTime`。
  ⚠️ 这是 Yahoo 面向自家前端的**非公开接口**，无 SLA、可能限流或变更。本项目把它做成可插拔，
  失败时该标的标记 `数据缺失`，绝不编造。
- **`finnhub`**：需 key。注意免费档**不支持原始指数代码**（`^GSPC`/`^IXIC`/`^DJI`），
  本 provider 会明确返回 `数据缺失` 而非偷偷用 ETF 顶替。
- **`mock`**：读取 `tests/fixtures/quotes.json`，完全离线。

**交易阶段**由程序自行判定（盘前 04:00–09:30 / 盘中 09:30–收盘 / 盘后 收盘–20:00 / 其余休市，
美东时区，`zoneinfo` 自动处理夏令时；内置 2025–2027 NYSE 休市与提前收盘表）。
**不依赖** provider 返回的 `marketState` —— 实测 Yahoo 该字段为 `None`。

---

## 本地运行

```bash
# 状态自检
usmarket check-config

# LLM 连通性自检（不配置 LLM 时可跳过）
usmarket llm-check

# 完整流程（自动解析最近一个已收盘交易日）
usmarket generate

# 完全离线（用 tests/fixtures，不访问网络，无需任何 key）
usmarket generate --date 2026-10-26 --offline

# 查看任务
usmarket list
usmarket show --date 2026-10-26
```

`generate` 会依次完成：采集 → 清洗/去重/时效过滤 → 行情 → 生成 → 校验 → 渲染 → 落盘 → 置为 `review`。

不使用 `usmarket` 入口时：

```bash
python -m usmarket.cli.main generate --date 2026-10-26 --offline
```

---

## 生成指定日期的日报

```bash
usmarket generate --date 2026-10-26
```

产物目录：

```
data/2026-10-26/
├── raw/
│   ├── news.jsonl            # 原始采集（含 published_at 与 fetched_at）
│   ├── quotes.json           # 原始行情（含 provider 原始片段，可追溯）
│   └── source_results.json   # 每个新闻源的成败与耗时
├── processed/
│   └── news_deduped.jsonl    # 去重 + 时效过滤后
├── content/
│   ├── content.json          # 结构化内容（下游唯一依赖）
│   ├── report.md             # Markdown 日报
│   └── sources.md            # 来源、数据质量、条款与限制清单
├── images/
│   ├── cover.png
│   ├── page_01.png … page_06.png
│   └── manifest.json
├── task.json                 # 状态、指纹、历史、发布记录
├── REVIEW.md                 # 人工审核文件（含审核命令）
└── run.log                   # 结构化日志（已脱敏）
```

`content.json` 关键字段：`summary`、`index_moves`、`top_news`（3–5 条）、
`watchlist_moves`、`earnings_and_macro`、`next_session`、`risk_notes`、
`xhs{title,body,tags}`、`sources`、`disclaimer`、`low_confidence`。

**休市处理**：若目标日是周末/节假日，或美东时间尚未收盘，程序自动使用
"最近一个已收盘交易日"，并在 `market_phase` 与文案中明确标注，不假装是当天。

---

## 生成图文图片

```bash
# 渲染（使用已生成的内容，不会重新采集）
usmarket render --date 2026-10-26

# 单图速览（一张长图装下全部内容，CI 默认）
usmarket render --date 2026-10-26 --template one_page

# 切换到「重大新闻专题」模板
usmarket render --date 2026-10-26 --template flash_brief
# 或在生成时指定
usmarket generate --date 2026-10-26 --template one_page
```

**默认规格**：`daily_review` / `flash_brief` 为 1080×1440 竖屏 PNG，封面 1 张 + 正文 5–7 张；
**`one_page` 为单张长图**（宽 1080，高度按内容自适应约 2500–3000，比例在小红书长图限制内）。

| 模板 | 用途 | 结构 |
| --- | --- | --- |
| `one_page` | **单图速览（CI 默认）** | 一张长图装下全部：标题 → 三大指数 → 概览 → 要闻 → 个股异动 → 明日关注 → 风险+免责 |
| `daily_review` | 多页每日复盘 | 封面（三大指数）→ 概览 → 要闻 1–2 页 → 个股异动 → 财报/宏观 → 次日关注+风险+来源 |
| `flash_brief` | 重大新闻专题 | 封面（大标题+要点条）→ 每条新闻一页（大号序号+引言块）→ 风险与来源 |

示例（均由本项目实际渲染）：

| 文件 | 说明 |
| --- | --- |
| `docs/examples/daily_review_cover.png` | 复盘模板封面（三大指数） |
| `docs/examples/daily_review_page01.png` | 今日市场概览 |
| `docs/examples/daily_review_page02.png` | 要闻页（3 条） |
| `docs/examples/daily_review_page03.png` | 要闻页（2 条） |
| `docs/examples/daily_review_page04.png` | 重点个股异动 |
| `docs/examples/daily_review_page05.png` | 财报与宏观 |
| `docs/examples/daily_review_page06.png` | 次日关注 + 风险 + 来源 |
| `docs/examples/flash_brief_cover.png` | 专题模板封面 |
| `docs/examples/flash_brief_page1.png` | 专题正文页 |
| `docs/examples/flash_brief_page2.png` | 专题正文页 |
| `docs/examples/one_page.png` | **单图速览**（一张长图装下全部内容） |
| `docs/examples/report_example.md` | Markdown 日报示例（规则式，离线可复现） |
| `docs/examples/sources_example.md` | 来源与数据清单示例 |
| `docs/examples/REVIEW_example.md` | 人工审核文件示例 |
| `docs/examples/llm_cover.png` | **真实 LLM（百炼 qwen3.8-flash）** 生成内容的封面 |
| `docs/examples/llm_overview.png` | LLM 生成的今日市场概览 |
| `docs/examples/llm_watchlist.png` | LLM 生成的个股异动页（含中文解读） |
| `docs/examples/llm_report_example.md` | LLM 生成的 Markdown 日报（含要闻与来源） |

**可配置项**（`config/default.yaml` → `image`）：

```yaml
image:
  width: 1080
  height: 1440
  min_pages: 5
  max_pages: 7
  template: daily_review
  margin: 80
  theme:
    background: "#0F172A"   # 背景
    surface: "#16213E"      # 卡片
    accent: "#F97316"       # 强调色
    positive: "#22C55E"     # 上涨
    negative: "#EF4444"     # 下跌
    text_primary: "#F8FAFC"
    text_secondary: "#94A3B8"
    font_regular: ""        # 留空自动探测系统中文字体
    font_bold: ""

account:
  name: 美股日报             # 图片底部账号名
```

**渲染保证**：
- 中英混排换行，不在"标普500"这类词中间断行；
- 超长文本按行数截断并加省略号，不溢出画布；
- 每张图渲染后做"非空白"检查（单一颜色占比 ≥ 99.5% 视为空白并报错）；
- 图片中的数字与 `content.json` 同源（测试中比对）。

---

## 配置 GitHub Actions

工作流：`.github/workflows/daily.yml`。

| 触发方式 | 说明 |
| --- | --- |
| `schedule: 30 22 * * 1-5` | UTC 22:30 ≈ 美东夏令时 18:30 / 冬令时 17:30（盘后） |
| `workflow_dispatch` | 手动触发，可指定 `run_date` / `template` / `offline` |

**关键设计**：
- ⚠️ GitHub cron **不保证精确到分钟**（常见延迟 15–60 分钟）。因此程序**不把触发时间当作"当天"**，
  而是按美东时间解析"最近一个已收盘交易日"；发布时也重新校验，不把工作流触发时间当成平台发布时间。
- `concurrency` 组避免同 `run_date` 并发重复生成。
- 失败时自动上传 `data/<date>/` 与 `generate.log` 为 artifact，并写入 `GITHUB_STEP_SUMMARY` 失败摘要。
- 凭据全部通过 **GitHub Secrets** 注入（见下表）。

### 需要配置的 Secrets / Variables

| 名称 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `LLM_API_KEY` | Secret | 否 | 不用 LLM 时留空（走规则兜底） |
| `ANTHROPIC_API_KEY` | Secret | 否 | 仅 `LLM_PROVIDER=anthropic` 时需要 |
| `FINNHUB_API_KEY` | Secret | 否 | 仅 `MARKET_PROVIDER=finnhub` 时需要 |
| `LLM_PROVIDER` | Variable | 否 | `openai_compatible` / `anthropic` / `rule_based` |
| `LLM_BASE_URL` / `LLM_MODEL` | Variable | 否 | OpenAI 兼容端点与模型 |
| `MARKET_PROVIDER` | Variable | 否 | 默认 `yahoo` |
| `XHS_PUBLISHER` | Variable | 否 | 默认 `mock` |
| `SEC_USER_AGENT` | Variable | 建议 | 形如 `App/0.1 (you@example.com)`，否则 SEC 返回 403 |

```bash
gh secret set LLM_API_KEY
gh variable set LLM_PROVIDER --body "openai_compatible"
gh variable set SEC_USER_AGENT --body "USMarketDailyXHS/0.1 (you@example.com)"
gh variable set XHS_PUBLISHER --body "mock"
```

### 手动重跑某天

```bash
gh workflow run daily.yml -f run_date=2026-10-26 -f template=daily_review
# 或本地
usmarket generate --date 2026-10-26
```

---

## 审核与发布

### 状态机

```
pending → generated → review → approved → scheduled → published
   ↑           │         │         │          │
   └───────────┴─────────┴─────────┴──────────┴──→ failed
                 review → rejected → generated（重新生成）
```

非法迁移会被 `state_machine` 拒绝（如 `review → published`）。

### 审核命令

```bash
usmarket list                              # 所有任务及状态
usmarket show --date 2026-10-26            # 详情（含失败阶段与错误）
cat data/2026-10-26/REVIEW.md              # 人工审核文件

usmarket approve --date 2026-10-26                     # 通过
usmarket reject  --date 2026-10-26 --reason "标题不够吸引"  # 驳回
usmarket rerun   --date 2026-10-26                     # 失败/驳回后重跑
```

### 发布

```bash
usmarket publish --date 2026-10-26
```

- **未 `approved` 直接 publish 会被拒绝**，不调用任何适配器。
- 重复 publish 命中幂等，不会产生第二条发布记录。
- 失败按 `PUBLISH_MAX_RETRIES`（默认 3）与指数退避重试。
- 结果写入 `data/<date>/publish/result.json`（含 `simulated` / `verified`）。

### 三种发布适配器

| 适配器 | 行为 | 真实调用平台 | `verified` |
| --- | --- | --- | --- |
| `mock`（默认） | 模拟上传/建草稿/发布，可注入失败 | ❌ | `false` |
| `manual_export` | 导出 `publish_bundle.json` + `HOW_TO_PUBLISH.md`，人工复制发布 | ❌ | `false` |
| `browser` | **未实现、默认禁用**，只抛"未实现"错误 | ❌ | `false` |

切换：`XHS_PUBLISHER=manual_export`

人工发布后记录结果：

```bash
usmarket mark-published --date 2026-10-26 --remote-id "https://www.xiaohongshu.com/explore/xxxx"
```

### 发布能力与真实验收状态

**明确声明：本项目没有实现、也没有验收真实的小红书自动发布。** 原因：

1. 小红书**未向个人账号开放笔记发布 API**。企业/个体工商户主体可在
   `open.xiaohongshu.com` 申请开发者权限（笔记发布需单独审核），个人号无公开接口。
2. 社区常见的"自动发布"依赖 Selenium/Playwright + Cookie 注入，属浏览器自动化，
   不受平台支持，受前端改版与风控影响，不可持续。
3. 本项目**不实现**验证码绕过、指纹伪造、反检测规避等违反平台规则的功能。

**标记为"真实发布已实现"的门槛**（三条同时满足，缺一不可）：

1. 具备合法授权（官方开放平台权限，或账号所有者明确授权）；
2. 目标接口/页面结构在当前版本可用且已实测；
3. 至少一次完整的真实发布（含图片上传）成功，并留下可核对的 `result.json`（`verified=true`）。

在此之前，所有发布产物一律 `simulated=true` / `verified=false`。

---

## 已验证 / 模拟实现清单

以**实际执行**为准，不以文档声称。

### ✅ 已通过真实测试

| 项目 | 验证方式 |
| --- | --- |
| `pytest` 全量离线测试 | 224 passed / 4 skipped（网络测试默认跳过） |
| **LLM 真实生成（阿里百炼 qwen3.8-flash）** | 真实调用：`generator=openai_compatible`，产出 4 条要闻 + 个股解读 + 小红书文案，通过全部数字/来源/合规校验 |
| LLM 连通性自检 | `usmarket llm-check` 2.58s 返回并通过 JSON 解析；`llm-models` 实测返回 182 个 model id |
| Yahoo chart 行情（三大指数） | 真实请求，`^GSPC 7676.77`、`^IXIC 26169.38`、`^DJI 52361.58`，`usable=10/10` |
| 20 个新闻源并发采集 | 真实请求，`sources ok: 20/20` |
| 完整 `generate`（真实网络） | 产出 content/report/sources/7 张图片，状态 `review` |
| 离线 `generate --offline` | 无网络、无 key 可跑通 |
| 图片渲染（两种模板） | Pillow 可打开、尺寸 1080×1440、非空白 |
| 状态机 / 审核 / 驳回 / 重跑 | 集成测试通过 |
| 发布幂等与重试 | 集成 + 单元测试通过 |
| 日志脱敏 | 测试断言日志中无 cookie/token/password |
| 数字可追溯校验 | 编造数字 100% 被拦截（测试） |
| 交易阶段/DST/节假日 | 单元测试覆盖 DST 边界、周末、NYSE 假日 |

### ⚠️ 模拟实现（不可声称已完成）

| 项目 | 状态 |
| --- | --- |
| 小红书真实自动发布 | **未实现、未验收**（`browser` 适配器仅骨架） |
| 发布结果真实性 | `result.json` 中 `simulated=true`、`verified=false` |
| Anthropic provider | 代码已完成，本机无该 key，**未实测**（OpenAI 兼容 / 百炼路径已实测） |
| 真实小红书登录态 | 无账号授权，**从未验证过**任何真实接口 |
| Finnhub / Alpha Vantage | **未实测**（无 key）；Alpha Vantage 未实现 |
| GitHub Actions 实际运行 | 工作流已写好，**未在真实仓库触发过** |

### ❌ 明确不做

- 反检测、验证码绕过、账号池等违反平台规则的功能；
- 盘前模式（枚举预留，第一版不启用）；
- Web 审核后台（用 CLI + REVIEW.md 代替）。

---

## 项目结构

```
BullSheet/
├── src/usmarket/
│   ├── config.py              # YAML + env + CLI 三级配置，敏感项校验
│   ├── logging_setup.py       # 结构化日志 + 凭据脱敏
│   ├── errors.py              # 按阶段区分的异常（便于定位失败）
│   ├── http_client.py         # 超时 + 有限重试 + 退避
│   ├── collectors/            # A：RSS/Atom、SEC EDGAR、采集编排
│   ├── market_data/            # B：provider、交易日历、阶段判定、质量标记
│   ├── processors/            # 清洗、去重、分类、时效过滤
│   ├── ai/                    # C：Provider 抽象、prompt、规则兜底、生成服务
│   ├── validation/            # 结构 / 数字 / 来源 / 合规校验
│   ├── content/               # Markdown、JSON、来源清单
│   ├── image_renderer/        # D：字体、排版、主题、两种模板、渲染器
│   ├── publishing/            # E：适配器、幂等、重试、编排
│   ├── scheduler/             # F：触发时间 → 目标交易日
│   ├── storage/               # G：任务模型、状态机、文件存储、SQLite
│   └── cli/                   # Typer 命令与端到端 pipeline
├── config/default.yaml
├── tests/{unit,integration,fixtures}
├── docs/{research,architecture,decisions,deployment,limitations,examples}
├── specs/001-us-market-daily-xhs/
├── .specify/memory/constitution.md
├── .github/workflows/daily.yml
└── scripts/{fetch_fonts.py,fetch_repos.py,...}
```

---

## 测试

```bash
# 全量离线测试（推荐；无需网络与 key）
python -m pytest tests -q

# 覆盖率
python -m pytest tests --cov=usmarket --cov-report=term-missing

# 只跑单元测试
python -m pytest tests/unit -q

# 真实数据源验证（需联网；会真实请求 Yahoo / RSS / SEC）
# Linux/macOS:
NETWORK_TESTS=1 python -m pytest tests/integration/test_network_sources.py -m network -q
# Windows PowerShell:
$env:NETWORK_TESTS=1; python -m pytest tests/integration/test_network_sources.py -m network -q

# 静态检查
python -m ruff check src tests
python -m mypy src
```

**测试组织**：

| 目录 | 内容 |
| --- | --- |
| `tests/unit/test_market_data.py` | 涨跌幅、缺失不补全、交易阶段、DST、节假日、新鲜度 |
| `tests/unit/test_collectors.py` | URL 归一、去重、时间字段分离、时效、HTML/注入清洗 |
| `tests/unit/test_validation.py` | 结构、数字可追溯、来源完整性、合规表述 |
| `tests/unit/test_storage_and_state.py` | 状态机合法/非法迁移、原子写入、索引重建 |
| `tests/unit/test_publishing.py` | 模拟成功/失败、幂等、重试退避、未审核拦截、凭据不泄露 |
| `tests/unit/test_scheduler.py` | 时区、DST、周末、节假日回退、盘前未启用 |
| `tests/unit/test_renderer.py` | 尺寸、可打开、非空白、换行不溢出、数字一致 |
| `tests/unit/test_logging_security.py` | 脱敏规则、日志文件不含凭据 |
| `tests/integration/test_offline_pipeline.py` | 离线端到端（含低置信度、无行情场景） |
| `tests/integration/test_review_flow.py` | CLI 审核-发布全流程、幂等、失败定位 |
| `tests/integration/test_network_sources.py` | 真实数据源（`-m network`，默认跳过） |

---

## 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `FontMissingError` | 系统无中文字体 | `sudo apt install fonts-noto-cjk` 或 `python scripts/fetch_fonts.py` |
| `[config] 环境变量 X 必须为整数` | 环境变量格式错 | 检查 `.env` |
| `敏感配置缺失: LLM_API_KEY` | 选了 LLM provider 但没给 key | 填 key，或 `LLM_PROVIDER=rule_based` |
| `[collect] 过滤后无任何可用新闻` | 所有源失败或时间窗太窄 | 看 `data/<date>/raw/source_results.json`；调大 `NEWS_LOOKBACK_HOURS` / `news.lookback_hours` |
| SEC 返回 403 | 未声明 User-Agent | 设置 `SEC_USER_AGENT="App/0.1 (you@example.com)"` |
| 行情显示"数据缺失" | provider 失败或超时；**这是正确行为** | 看 `raw/quotes.json` 的 `quality_note`；换 `MARKET_PROVIDER` |
| 行情显示"数据过期" | 超过新鲜度阈值 | 调 `MARKET_STALE_MINUTES`；休市时该判断已按"最近收盘"计算 |
| 图片有大片空白 / 文字被截断 | 文本过长 | 降低 `content.body_max_chars`，或调 `image` 字号/边距 |
| `[validation] 正文中出现的数字在输入数据中找不到出处` | LLM 编造数字 | **这是正确行为**，系统已阻止发布；换模型或降 temperature |
| `LLM 生成失败，回退规则式生成: ReadTimeout` | 生成超时（百炼默认开启思考链时常见） | 设 `LLM_TIMEOUT_SECONDS=180`，并加 `LLM_EXTRA_BODY_JSON={"chat_template_kwargs": {"enable_thinking": false}}` |
| `LLM 生成失败: LLM 返回错误状态码: 401/404` | key 无效或 model id 不存在 | `usmarket llm-check` 定位；`usmarket llm-models --contains qwen` 确认 model id |
| `1 validation error for DailyContent ... market_phase` | 模型用了不在枚举内的写法 | 已内置归一化（`pre-market`/`盘前` 等）；若仍有新写法，补 `ai/base.py::_MARKET_PHASE_ALIASES` |
| 图片里出现空白方块 / 字间多余空格 | 文案含 emoji | 渲染前已自动剥离 emoji 与 Markdown 标记；`content.json` 与复制发布用的正文仍保留原样 |
| 想直接看待审核内容 | — | `python scripts/inspect_content.py data/<date>` 打印中文摘要、要闻与小红书文案 |
| `[publish] 未通过审核，禁止发布` | 未 `approve` | 先 `usmarket approve --date <date>` |
| 任务卡在 `failed` | 某阶段失败 | `usmarket show --date <date>` 看 `stage` 与 `error`，修好后 `usmarket rerun` |
| `非法状态迁移` | 跳步操作 | 用 `rerun` 重置到 `pending` 再走流程 |
| PowerShell 中文乱码 | 控制台编码 | 已在 CLI 尝试切换 UTF-8；仍乱码可先 `chcp 65001` |
| Actions 定时不准 | GitHub cron 延迟 | 设计已规避：目标日按"最近已收盘交易日"解析 |

详细部署说明见 [`docs/deployment.md`](docs/deployment.md)；
已知限制与后续任务见 [`docs/limitations.md`](docs/limitations.md)。

---

## 合规与许可

- 本项目代码：**MIT**。
- 第三方内容与条款：
  - RSS 内容版权归原媒体所有；本项目**仅引用标题与摘要并保留原始链接**，不做全文转载。
  - Yahoo `query1.finance.yahoo.com` 为**非公开接口**，无 SLA；商用前请自行评估 Yahoo 服务条款。
  - SEC EDGAR 为公共数据，但要求声明式 User-Agent（已实现）。
  - Finnhub 免费档 60 次/分钟，且不支持原始指数代码。
  - 小红书：无面向个人账号的公开笔记发布 API；任何自动化发布需自行评估平台规则。
- **未复用**任何无 LICENSE 的开源项目代码，详见 [`docs/research.md`](docs/research.md) 与
  [`docs/decisions.md`](docs/decisions.md)。

> 本项目输出**不构成投资建议**。使用者需自行承担数据准确性、平台合规与投资决策责任。
