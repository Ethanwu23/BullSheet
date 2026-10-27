# 开源项目与数据源研究

- 研究日期：2026-10-27
- 研究环境：Windows 11 / PowerShell / Python 3.13.12 / uv 0.x / Spec Kit CLI 1.2.3
- 研究方法：直接抓取 GitHub 仓库页面、`README.md`、`LICENSE`、依赖清单与提交 Atom feed；并**实机发起 HTTP 请求**验证数据源可用性。
- 可信度标注：`已实测` = 本机发起真实 HTTP 请求并得到响应；`已查看源码` = 读到真实文件内容；`未验证` = 仅依据 README 或二手资料。

> 本文中所有"可用/不可用"结论均来自上述实测，未实测的部分已显式标注为"未验证"。

---

## 1. 候选开源项目

### 1.1 CazSyd/stock-report — 美股日报生成

| 项目 | 值 |
| --- | --- |
| 描述 | 定时抓取市场与自选股新闻，用 OpenRouter 免费模型生成 Markdown 日报 |
| **许可证** | **仓库根目录无 LICENSE 文件**（`已查看源码`：根目录仅 `.github/workflows`、`stockreport`、`tests`、`.env.example`、`.gitignore`、`README.md`、`config.example.yaml`、`config.yaml`、`pyproject.toml`、`uv.lock`）。法律上默认"保留所有权利" |
| 最近提交 | 2026-09-30（`已查看源码`：commits.atom） |
| Star | 0 |
| 依赖（`已查看源码` pyproject.toml） | `yfinance>=0.2.50`、`feedparser>=6.0.11`、`requests>=2.32.0`、`pyyaml>=6.0.2`、`python-dotenv>=1.0.1`，dev: `pytest>=8.3` |
| 测试 | README 声称 70 个测试（`未验证`，未实际运行） |
| 结构 | `stockreport/` 包 + `tests/`，扁平布局，配置用 `config.yaml` |

**实测结论（重要）**：其 `config.yaml` 中配置的 `https://finance.yahoo.com/news/rssindex` **返回 404，已失效**（`已实测`）。也就是说该项目当前至少有一个默认新闻源不可用。

**可借鉴点**（概念层面，非复制代码）：
- 按 ticker 分桶、每桶独立 LLM 会话，避免单上下文过长；
- 去重 + 时间窗过滤 + 每主题条数上限；
- 单一来源在聚合池中的条数上限（`market_source_cap`），防止通讯社批量转载刷屏；
- CLI 退出码语义化（0 成功 / 1 配置错 / 2 key 无效 / 3 部分失败 / 4 投递失败）；
- `--dry-run` 不需要 API key 也能跑通。

**结论：不复用其代码。** 原因：(a) 无 LICENSE，复用存在法律风险；(b) 依赖 `yfinance`（重量级、易受 Yahoo 接口变更影响、且 Yahoo 接口无 SLA）；(c) 默认源已失效。仅借鉴设计思路。

---

### 1.2 SamirPaulb/daily-digest — 多来源新闻 + AI 日报

| 项目 | 值 |
| --- | --- |
| 描述 | 每日 4:30 IST 由 GitHub Actions 生成市场/新闻/AI 简报并发布到 GitHub Pages |
| **许可证** | README 声称 MIT，但**仓库根目录无 LICENSE 文件**（`已查看源码`：根目录仅 `.github/workflows`、`digests`、`scripts`、`.env.example`、`.gitignore`、`README.md`、`index.html`、`manifest.json`）。声明与文件不一致，法律上仍存疑 |
| 最近提交 | 2026-10-27（今天，非常活跃） |
| Star | 5 |
| 依赖（`已查看源码` scripts/requirements.txt） | `feedparser`、`anthropic~=0.100`、`openai~=2.36`、`google-genai~=2.0`、`markdown`、`exa-py`、`tavily-python`、`ddgs>=9.0` |
| 结构 | README 自述 `scripts/generate_digest.py` **单文件约 3300 行**（`未验证`行数，来自 README） |

**评估**：
- 优点：多 provider 降级链设计（6 层，含"无 AI 直接拼装"兜底）、"脚本注入真实行情数字而非 AI 生成"这一条与我们需求高度一致。
- 风险：单文件 3300 行，难以测试与维护；依赖大量需要 API key 的商业新闻 API（Tavily / Exa / NewsAPI / GNews …），默认配置下本地不可运行；许可证文件缺失。

**结论：不复用其代码。** 借鉴"行情数字由脚本注入、AI 只写文字"的原则（该原则直接写入本项目 Constitution）。

---

### 1.3 angelinavio/daily-market-brief — 市场简报 + 图表

| 项目 | 值 |
| --- | --- |
| 描述 | 每工作日早间 RSS 抓新闻 + Claude 撰写 + Finnhub 行情 + matplotlib 图表，邮件投递 |
| **许可证** | **MIT，LICENSE 文件存在且已读取**（`已查看源码`，1068 字节） |
| 最近提交 | 2026-07-16（约 3.4 个月前，维护放缓） |
| Star | 0 |
| 依赖（`已查看源码` requirements.txt） | `anthropic==0.116.0`、`feedparser==6.0.12`、`matplotlib==3.11.0`、`pillow==12.3.0`、`pydantic==2.13.4`、`requests==2.34.2`、`python-dotenv`、`numpy` 等 |
| 结构 | 扁平单文件模块：`build_brief.py`、`fetch_news.py`、`fetch_market_data.py`、`chart.py`、`render.py`、`send_email.py`、`config/settings.py` |

**已知限制（README 明确写出）**：Finnhub 免费档**不支持原始指数代码**（如 `^GSPC`），需改用 ETF（如 `SPY`）。这与本项目"必须展示 S&P 500 / Nasdaq / Dow 三大指数"的需求冲突，是一个重要的技术选型参考。

**结论：许可证兼容（MIT），但代码不直接复用。** 理由：配置写在 Python 源码里（`config/settings.py`）不利于环境化；单文件模块边界不清；投递目标是邮件而非小红书。借鉴点：README 里诚实记录成本与故障排查表，本项目 README 采用同样写法。

---

### 1.4 hasuoshenyun/XHS_Auto_Publish — 小红书自动发布（候选）

| 项目 | 值 |
| --- | --- |
| 描述 | 基于 Selenium 的小红书图文/视频定时发布工具 |
| **许可证** | **无 LICENSE 文件**（`已查看源码`：根目录仅 `docs`、`README.md`、`requirements.txt`、`upload.py`）。默认保留所有权利 |
| 最近提交 | 2025-03-30（**约 19 个月前，已停更**） |
| Star | 12 |
| 依赖（`已查看源码` requirements.txt） | `loguru==0.7.2`、`selenium==4.21.0`、`webdriver-manager==4.0.0`、`types-python-dateutil` |
| 代码形态（`已查看源码` upload.py 前 90 行） | `XIAOHONGSHU_COOKIE_PATH = "/your_path/cookies.json"` **硬编码在源码里**；`webdriver.Edge`；读 cookies.json 注入 → 跳转 `creator.xiaohongshu.com/publish/publish` → 用 `//*[contains(text(),"发布笔记")]` 一类脆弱 XPath 定位元素 |

**风险清单**：
1. **无 LICENSE** → 不得复制其代码。
2. **停更 19 个月** → 小红书创作者后台前端选择器几乎必然已变化，XPath 定位早已失效（`未验证`，但属高概率；本项目不做未经验证的假设）。
3. **凭据处理不安全** → Cookie 文件路径硬编码在源码中，与本项目"凭据不得写死在源码"原则直接冲突。
4. **依赖特定浏览器** → 绑定 Edge，CI（Ubuntu runner）不可用。
5. **平台规则风险** → 浏览器自动化发布个人号违反小红书服务协议，且不可持续。

**结论：不复用。** 仅作为"为什么自建适配层"的反面案例记录在案。

---

### 1.5 github/spec-kit — SDD 工具链

| 项目 | 值 |
| --- | --- |
| **许可证** | **MIT，LICENSE 已读取** |
| Star | 143,110 |
| 最近提交 | 2026-10-26（活跃） |
| 本地安装 | `uv tool install specify-cli` → **specify-cli 1.2.3 已安装**（`已实测`） |
| 初始化 | `specify init . --integration codebuddy --here --force --non-interactive --ignore-agent-tools`（`已实测`） |

**本机真实产物**（`已查看源码`）：
- `.specify/memory/constitution.md`、`constitution-template.json`
- `.specify/templates/`：`spec-template.md`、`plan-template.md`、`tasks-template.md`、`checklist-template.md`、`constitution-template.md`
- `.specify/scripts/powershell/`：`create-new-feature.ps1`、`setup-plan.ps1`、`setup-tasks.ps1`、`check-prerequisites.ps1`、`resolve-template.ps1`
- `.specify/workflows/speckit/workflow.yml`
- `.codebuddy/commands/`：`speckit.constitution.md`、`speckit.specify.md`、`speckit.clarify.md`、`speckit.plan.md`、`speckit.tasks.md`、`speckit.analyze.md`、`speckit.checklist.md`、`speckit.implement.md`、`speckit.converge.md`、`speckit.taskstoissues.md`

**注意（版本差异，不假设命令一致）**：Spec Kit 1.2.3 的 CLI 只提供 `init / check / version / mcp / self / extension / integration / event / preset / artifact / bundle / workflow`。SDD 的 constitution/specify/plan/tasks/implement/converge **都是编码智能体的 slash 命令**（本项目为 `.codebuddy/commands/*.md`），不是终端命令。本文按 1.2.3 的真实形态执行。

---

## 2. 数据源实测结果（2026-10-27，本机发起真实请求）

### 2.1 新闻源

| 源 | URL | 结果 | 说明 |
| --- | --- | --- | --- |
| Google News 商业话题 RSS | `news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en` | ✅ 200 / 227 KB | 主力宏观新闻源 |
| Google News 搜索 RSS | `news.google.com/rss/search?q=NVDA+stock&hl=en-US&gl=US&ceid=US:en` | ✅ 200 / 128 KB | 按 ticker 检索 |
| CNBC RSS | `cnbc.com/id/100003114/device/rss/rss.html` | ✅ 200 / 20 KB | 市场新闻 |
| MarketWatch RSS | `feeds.content.dowjones.io/public/rss/mw_topstories` | ✅ 200 / 8 KB | 市场新闻 |
| Yahoo 个股 RSS | `feeds.finance.yahoo.com/rss/2.0/headline?s=NVDA&region=US&lang=en-US` | ✅ 200 / 7 KB | 按 ticker |
| 美联储新闻稿 RSS | `federalreserve.gov/feeds/press_all.xml` | ✅ 200 / 15 KB | 官方宏观源，权威可追溯 |
| Investing.com RSS | `investing.com/rss/news.rss` | ✅ 200 / 5 KB | 备选 |
| **Yahoo Finance 总榜 RSS** | `finance.yahoo.com/news/rssindex` | ❌ **404 已失效** | stock-report 默认配置中使用，不可用 |
| Reuters Agency RSS | `reutersagency.com/feed/?...` | ❌ 404 | 不可用，不纳入 |
| SEC EDGAR Atom | `sec.gov/cgi-bin/browse-edgar?...&output=atom` | ⚠️ 默认 UA 403；**声明式 UA 200** | 必须带 `User-Agent: App/1.0 (email)`，否则被拒 |

**SEC EDGAR 合规要求**：必须发送包含应用名与联系邮箱的 `User-Agent`，否则返回 403。本项目在 HTTP 客户端中固定设置该 UA。

### 2.2 行情源

| 源 | 结果 | 说明 |
| --- | --- | --- |
| Yahoo chart API `query1.finance.yahoo.com/v8/finance/chart/<sym>?range&interval` | ✅ 200，无需 key | 实测返回值：`^GSPC 7676.77`、`^IXIC 26169.38`、`^DJI 52361.58`、`NVDA 216.00`；`exchangeTimezoneName=America/New_York`；提供 `chartPreviousClose`、`regularMarketTime` |
| Stooq CSV | ❌ 404 | 本次实测不可用，**不作为依赖** |
| Finnhub | `未验证`（需 key） | 作为可插拔备选 provider 预留；README 已注明免费档不支持原始指数代码 |

**实测暴露的关键问题**：Yahoo chart API 的 `meta.marketState` 在本机返回 `None`，**不能依赖它判断交易阶段**。因此本项目自行基于 `America/New_York` 时区 + 交易所日历计算 `pre / regular / post / closed`，这是模块 B 的硬要求。

**Yahoo 接口合规性说明**：`query1.finance.yahoo.com` 是 Yahoo 面向自家前端的**非公开**接口，无 SLA、随时可能变更或限流。本项目将其作为"无 key 时的默认 provider"，同时在架构上做成可插拔，允许替换为 Finnhub / Alpha Vantage / 自建代理。README 明确告知该风险。

### 2.3 中文字体（图片渲染前置条件）

本机 `已实测`存在：`C:\Windows\Fonts\msyh.ttc`、`msyhbd.ttc`、`simhei.ttf`、`Noto Sans SC (TrueType).otf`、`NotoSansSC-VF.ttf`。

**CI（GitHub Actions ubuntu-latest）默认没有中文字体**，必须在工作流中安装（如 `fonts-noto-cjk`）或下载字体文件。本项目图片渲染器实现"字体候选列表 + 显式缺失报错"，并提供 `scripts/fetch_fonts.py`。

---

## 3. 小红书发布能力调研

- **官方渠道（`已查看` 网络搜索结果，二手资料，未在官方后台验证）**：小红书开放平台 `open.xiaohongshu.com` 面向**企业/个体工商户主体**提供开发者账号，笔记发布权限需单独申请并通过审核；个人账号无公开笔记发布 API。
- **第三方方案现状**：市面上所有"自动发布"方案本质上分两类 —— (a) Selenium/Playwright 浏览器自动化 + Cookie 持久化；(b) 逆向 App 私有协议。二者均**不受平台支持**，受前端改版、风控策略影响，不可持续。
- **本项目立场**：
  1. 发布能力抽象为独立适配器接口，与采集/生成完全解耦；
  2. **默认实现为可测试的模拟发布器（MockPublisher）**，并明确标注"真实发布尚未验收"；
  3. 不实现验证码绕过、指纹伪造、反检测规避等违反平台规则的功能；
  4. 真实发布仅在"账号授权 + 平台兼容性 + 实际测试通过"后启用，属 Phase 5，且本项目不声称已实现无人值守发布。

---

## 4. 技术选型对比矩阵

| 能力 | stock-report | daily-digest | daily-market-brief | XHS_Auto_Publish | **本项目选择** |
| --- | --- | --- | --- | --- | --- |
| 新闻采集 | RSS + yfinance（部分源已 404） | 20+ 源，多数需 key | RSS（feedparser） | — | **RSS 优先 + 可插拔 provider**（已实测的 6 个可用源 + SEC EDGAR） |
| 行情获取 | yfinance | Finnhub→AV→Yahoo→…6 层 | Finnhub（不支持指数） | — | **Yahoo chart（无 key，实测可用）为主 + Finnhub/AV 可插拔备选** |
| AI 总结 | OpenRouter 免费模型 | 7+ provider 降级链 | Claude | — | **可插拔 LLM Provider**（OpenAI 兼容 / Anthropic / 规则式 fallback） |
| 图片生成 | 无 | 无 | matplotlib + Pillow | 无 | **Pillow 单一渲染技术**（不引入 matplotlib / 浏览器渲染） |
| 定时调度 | GitHub Actions | GitHub Actions | GitHub Actions | 本地 cron | **GitHub Actions**（cron + workflow_dispatch） |
| 发布 | Telegram | GitHub Pages | 邮件 | Selenium 小红书 | **适配层 + Mock 默认** |
| 审核 | 无 | 无 | 无 | 无 | **CLI + Markdown 审核文件 + 状态机**（本项目新增） |
| 许可证 | ❌ 无 | ⚠️ 声明 MIT 但无文件 | ✅ MIT | ❌ 无 | **本项目 MIT；不复制任何无 LICENSE 仓库的代码** |

---

## 5. 未验证事项清单（诚实记录）

以下事项本次**未**验证，不得声称已完成：

1. 三个候选项目的**测试是否真的通过**（仅读到 README 声明，未 clone 运行）。
2. `daily-digest` 的 3300 行单文件行数（来自 README 自述）。
3. `XHS_Auto_Publish` 的 XPath 选择器当前是否失效（未运行浏览器验证）。
4. Finnhub / Alpha Vantage 的实际返回（本机无 key，未实测）。
5. 小红书开放平台笔记发布 API 的**当前真实可用性与审核门槛**（未登录企业后台验证，依赖二手资料）。
6. GitHub Actions 定时任务的实际执行延迟（未实机运行工作流）。
7. `yfinance` 包是否仍可正常取数（本项目不使用，故未测）。
