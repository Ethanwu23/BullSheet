# 技术决策记录（ADR）

格式：决策 → 备选方案 → 选择理由 → 影响/风险 → 状态

---

## ADR-001 不复用任何候选开源项目的源码，只借鉴设计

- **决策**：本项目从零实现，不 vendor 任何候选仓库代码。
- **备选**：
  1. 直接 fork/extend `CazSyd/stock-report`；
  2. 复用 `angelinavio/daily-market-brief`（MIT）；
  3. 从零实现。
- **理由（实测依据）**：
  - `stock-report`：根目录**无 LICENSE**（`已查看源码`）→ 法律上默认保留所有权利；且其默认源 `finance.yahoo.com/news/rssindex` **实测 404 已失效**。
  - `daily-digest`：README 声称 MIT 但**根目录无 LICENSE 文件**（`已查看源码`）→ 声明与文件不一致；且主脚本为单文件约 3300 行，难测试。
  - `daily-market-brief`：虽有 MIT，但配置写在 Python 源码 `config/settings.py`、模块为扁平单文件、投递目标是邮件；且其依赖的 Finnhub 免费档**不支持原始指数代码**（README 自述），与本项目必须展示三大指数的需求冲突。
  - `XHS_Auto_Publish`：**无 LICENSE**、停更 19 个月、Cookie 路径硬编码在源码 → 直接违反本项目安全原则。
- **影响**：开发量更大，但代码可控、可测试、无许可证风险。
- **借鉴的设计**：按 ticker 分桶独立 LLM 会话；单一来源条数上限防刷屏；`--dry-run` 无 key 可跑；CLI 语义化退出码；脚本注入真实行情数字而非 AI 生成。
- **状态**：已接受

---

## ADR-002 行情主 provider 选 Yahoo chart API，但做成可插拔

- **决策**：默认使用 `query1.finance.yahoo.com/v8/finance/chart/<sym>`（无需 API key），同时定义 `QuoteProvider` 协议，预留 Finnhub / Alpha Vantage / Mock。
- **备选**：
  1. `yfinance`（stock-report 用的）；
  2. Finnhub 免费档；
  3. Stooq CSV；
  4. Yahoo chart API。
- **理由（实测依据）**：
  - Yahoo chart API **实测 200**：`^GSPC 7676.77`、`^IXIC 26169.38`、`^DJI 52361.58`、`NVDA 216.00`，返回 `chartPreviousClose`、`regularMarketTime`、`exchangeTimezoneName=America/New_York`，**且支持原始指数代码 `^GSPC/^IXIC/^DJI`**（Finnhub 免费档不支持，见 daily-market-brief README）。
  - Stooq CSV **实测 404**，排除。
  - `yfinance` 依赖链重（pandas/numpy），且仍是对同一非公开接口的封装，收益不抵复杂度。
  - Finnhub / Alpha Vantage 需 key，作为可插拔备选保留，有 key 时优先度可配置。
- **风险与缓解**：Yahoo 该接口为**非公开**接口，无 SLA。缓解：(a) 抽象成 provider，可一行切换；(b) 失败时 `QuoteQuality.MISSING` + 显式标注，绝不编造；(c) README 明确告知风险并给出替换方式。
- **状态**：已接受

---

## ADR-003 新闻源以 RSS/官方源为主，不使用商业新闻 API

- **决策**：默认使用 6 个实测可用的免费源 + SEC EDGAR，全部通过环境变量可增删。
- **实测可用源**：Google News（话题 + 按 ticker 搜索）、CNBC、MarketWatch（`feeds.content.dowjones.io`）、Yahoo 个股 RSS（`feeds.finance.yahoo.com`）、美联储新闻稿 RSS、Investing.com。
- **实测不可用**：`finance.yahoo.com/news/rssindex`（404）、Reuters Agency RSS（404）。
- **SEC EDGAR**：默认 UA 返回 403，**必须**发送 `User-Agent: <App>/<ver> (<email>)` 才返回 200（`已实测`）。已内置合规 UA。
- **备选**：Tavily / Exa / NewsAPI 等（daily-digest 路线）。
- **理由**：商业 API 需 key、有配额、增加成本与配置负担；RSS 源已能满足"宏观 + 个股 + 财报 + 异动"四类需求，且全部可追溯到原始链接。
- **影响**：无语义搜索能力；靠关键词 + ticker 检索覆盖。可接受。
- **状态**：已接受

---

## ADR-004 交易阶段自行计算，不信任 provider 的 marketState

- **决策**：`market_data/phases.py` 基于 `zoneinfo("America/New_York")` + 内置 NYSE 日历自行判定 PRE/REGULAR/POST/CLOSED。
- **依据**：**实测** Yahoo chart 返回的 `meta.marketState` 为 `None`，不可依赖。
- **理由**：模块 B 要求"明确区分盘前/盘中/盘后/最近完整交易日"，这是硬需求，不能依赖外部不可靠字段。
- **影响**：需维护 NYSE 节假日表（已内置 2025–2027，含 Good Friday 计算）；表外年份降级为"仅周末判断"并标记 `calendar_confidence=low`。
- **状态**：已接受

---

## ADR-005 图片渲染只用 Pillow，不引入 matplotlib / Playwright / HTML 转图

- **决策**：单一渲染技术 Pillow。
- **备选**：
  1. matplotlib（daily-market-brief 路线）→ 中文字体与排版控制弱，且引入 numpy；
  2. HTML/CSS → Playwright 截图 → 需下载浏览器（~150MB），CI 慢，复杂度高；
  3. SVG → cairosvg → 中文字体与换行控制差。
- **理由**：需求是"竖屏卡片式图文"，本质是固定布局 + 文本换行 + 色块，Pillow 足够；依赖最少、启动最快、CI 友好；Pillow 对 TTF/TTC 中文字体支持成熟（本机实测 `msyh.ttc` 等可用）。
- **影响**：图表需手绘（条形涨跌图用矩形即可，无需图表库）。
- **状态**：已接受

---

## ADR-006 发布层默认 Mock，真实发布标记为未验收

- **决策**：`publishing` 提供三个适配器：`mock`（默认，完全可测）、`manual_export`（导出可直接复制的发布包）、`browser`（默认禁用，标记 UNVERIFIED）。
- **依据**：
  - 小红书**无面向个人账号的公开笔记发布 API**（网络调研，二手资料，`未验证`官方后台现状）。企业主体需在 `open.xiaohongshu.com` 申请笔记发布权限并通过审核。
  - 候选项目 `XHS_Auto_Publish` 无 LICENSE、停更 19 个月、Cookie 硬编码 → 不可复用。
- **理由**：需求明确要求"不得假定某个开源项目能永久绕过平台限制""不实现验证码绕过、反检测规避""无法验证真实发布时实现可测试的模拟适配器并明确标注"。
- **影响**：Phase 5 的真实发布在未取得授权与实测前**不得声称已实现**。
- **状态**：已接受

---

## ADR-007 存储用文件 + JSONL，SQLite 作为可选后端

- **决策**：默认 `storage/FileTaskStore`（JSONL + 每日目录），提供 `SqliteTaskStore` 可选实现与迁移脚本。
- **备选**：仅 SQLite / 仅 JSON。
- **理由**：第一版需求是"轻量审核方案"；JSONL 可直接 git 归档、易读易 diff、无迁移负担。SQLite 在任务量大时能更好支持查询，预留接口。
- **影响**：并发写入用文件锁（`.lock`）+ 原子替换（写临时文件后 `os.replace`）保证一致性。
- **状态**：已接受

---

## ADR-008 LLM Provider 可插拔，含无需 key 的规则式兜底

- **决策**：定义 `LLMProvider` 协议；实现 `OpenAICompatibleProvider`（覆盖 OpenAI / DeepSeek / OpenRouter / 通义 / Moonshot 等 OpenAI 兼容端点）、`AnthropicProvider`、`RuleBasedProvider`（无 key 兜底）。
- **理由**：需求要求"可替换的 LLM Provider 接口，支持通过环境变量配置模型和 API"；且要求"不得因为一个可选外部服务不可用而放弃整个项目"—— 无 key 时系统仍能产出（但明确标注为 fallback 生成，需人工复核）。
- **约束**：`RuleBasedProvider` **只复用已核实的数字**（来自 `QuoteSnapshot` 与 `NewsItem`），不推测、不补全。
- **状态**：已接受

---

## ADR-009 调度用 GitHub Actions，且不把触发时间当成发布时间

- **决策**：`.github/workflows/daily.yml`，`schedule`（cron，UTC）+ `workflow_dispatch`（支持指定 `run_date`、模式）。
- **理由**：需求指定 GitHub Actions；免费、与仓库一体、Secrets 管理成熟。
- **已知限制（README 明确写出）**：GitHub cron **不保证精确到分钟**，可能延迟 15–60 分钟甚至更长。因此发布模块**重新校验**预定发布时间与当前时间，不把工作流触发时间当作实际发布时间；盘后任务取"最近完整交易日"而非"触发当天"。
- **并发**：工作流设置 `concurrency: group: daily-${{ inputs.run_date }}` + `cancel-in-progress: false`，避免同日重复生成。
- **状态**：已接受

---

## ADR-010 第一版只做盘后复盘，盘前模式预留

- **决策**：Phase 1–4 只实现 `mode=after_close`；`pre_open` 的枚举与配置位预留但不开通。
- **理由**：需求明确"第一版可以只实现盘后复盘，确保核心链路稳定后再扩展"。
- **状态**：已接受

---

## ADR-011 依赖最小化

- **运行时依赖**：`requests`、`feedparser`、`Pillow`、`pydantic`（v2）、`python-dateutil`、`typer`、`python-dotenv`。
- **开发依赖**：`pytest`、`pytest-cov`、`ruff`、`mypy`。
- **明确不引入**：`yfinance`（ADR-002）、`matplotlib`/`numpy`（ADR-005）、`selenium`/`playwright`（ADR-006）、`pandas`。
- **状态**：已接受

---

## ADR-012 许可证：本项目 MIT；第三方条款记录

- **决策**：本项目 MIT。
- **第三方注意（写入 README）**：
  - RSS 内容版权归原媒体所有，本项目仅做标题/摘要引用并保留原始链接，不做全文转载。
  - Yahoo 非公开接口：无 SLA，商用前需自行评估 Yahoo 服务条款。
  - SEC EDGAR：公共数据，但要求声明式 User-Agent（已实现）。
  - 小红书：无官方个人发布 API；自动化发布需自行评估平台规则。
- **状态**：已接受

---

## ADR-013 新增 `dashscope` provider 预设（阿里百炼）

- **决策**：在 `openai_compatible` 之上加一个语义别名 `LLM_PROVIDER=dashscope`：端点自动取 `https://dashscope.aliyuncs.com/compatible-mode/v1`，模型默认 `qwen3.8-flash`，密钥回退 `DASHSCOPE_API_KEY`。同时新增 `LLM_EXTRA_BODY_JSON` 环境变量，用于注入厂商专有请求体参数。
- **实测依据**（2026-10-27，真实调用）：
  - `/v1/models` 返回 182 个 model id（`qwen3.8-flash` / `qwen3.8-max` / `qwen3.8-27b` 等）；
  - 完整复盘生成：默认思考链开启时约 100–120s（会触发默认超时），关闭（`{"chat_template_kwargs": {"enable_thinking": false}}`）后约 30–40s；
  - 端点为 OpenAI 兼容，但思考链开关是 DashScope 专有参数，标准 payload 不含 —— 这就是引入 `LLM_EXTRA_BODY_JSON` 的原因。
- **备选**：让用户手写 `LLM_BASE_URL` + `LLM_MODEL` 三处配置。否决：预设别名把配置从 3 行减到 2 行，且避免手抄端点 URL 出错；显式 `LLM_MODEL`/`LLM_BASE_URL` 仍可覆盖预设，不损失灵活性。
- **影响**：`extra_body` 仅在 `openai_compatible.py` 请求体中 merge；设置到非百炼 provider 时参数会被对方端点忽略或报错，`.env.example` 已注明"仅百炼支持"。
- **状态**：已接受（实测通过）

---

## ADR-014 LLM 输出在图片渲染前剥离 emoji 与 Markdown，content.json 保持原样

- **决策**：新增 `image_renderer/sanitize.py`，渲染前对文本做"图片安全"清洗（emoji 移除/映射、Markdown 强调与列表标记移除、零宽字符清理）；**不修改** `content.json` 与 `xhs.body`（人工复制发布仍保留 emoji）。
- **实测依据**：百炼 qwen3.8-flash 生成的小红书文案包含 `📉` `🚀` `1️⃣` `⚠️` 与 `**加粗**`；中文正文字体（微软雅黑 / Noto Sans SC）无 emoji 字形，直接绘制产生空白豆腐块，Markdown 星号原样外露。
- **备选**：
  1. 要求 prompt 禁止 emoji —— 否决：对模型约束不可靠，且小红书正文本身**需要** emoji（人工发布时更符合平台风格）；
  2. 换用含 emoji 字形的字体 —— 否决：emoji 字体与中文字体混排复杂度远超收益。
- **影响**：涨跌类 emoji（📉📈）直接移除而非替换成文字——实测替换成"跌"会破坏中文语序（"📉美股复盘" → "跌美股复盘"）；警示类（⚠️）映射为"注意："。数字与链接不受清洗影响（有回归测试保证）。
- **状态**：已接受（实测通过）

---

## ADR-015 LLM 枚举同义写法先归一化再校验

- **决策**：`ai/base.py::normalize_payload()` 在 pydantic 严格校验前，把 `market_phase` 与 `confidence` 的常见同义写法归一化（`pre-market`/`盘前`→`pre`，`事实`→`fact` 等）；无法识别的写法仍走严格校验并失败回退。
- **实测依据**：百炼首次真实生成即输出 `market_phase: "pre-market"`，pydantic 校验失败，整篇无谓回退到规则式生成——内容其实完全可用。
- **备选**：放宽 schema（`Literal` 改 `str`）。否决：会掩盖真正的结构错误；归一化白名单既容忍模型措辞差异，又不放松对数字、来源与合规的校验。
- **影响**：未知同义写法出现时仍会回退（fail-closed 语义不变）；新增写法只需补 `_MARKET_PHASE_ALIASES` / `_CONFIDENCE_ALIASES` 两张表。
- **状态**：已接受（实测通过）

---

## ADR-016 LLM 只做「总结 + 翻译」两个窄任务，行情数据不交给模型加工

- **决策**：重构生成链路。规则式确定性生成**全部**结构化内容（指数表、个股表、来源清单、文案骨架）；LLM 只返回 `{evening_summary, headlines}` 两样——盘后总结一段 + 要闻标题中译——由 `_merge_llm_parts` 合并进基础内容，且只触碰这两处字段。
- **动机**（用户规则，2026-10-28）：此前把全部内容交给模型生成再校验，数字正确性依赖"校验拦截"，且模型行为不可控（混股票、漏标的、舍入触发回退、编造结构等问题接连出现）。改为"模型根本碰不到行情数字"后，这些问题从根上消失。
- **合并规则**：保留规则式的【分类】前缀替换英文标题；headlines 多于要闻数时取前 N（实测 qwen 会翻译全部输入新闻），少于则拒绝；合并结果仍过完整校验（数字/来源/合规），失败重试一次后沿用规则式内容（英文标题兜底）。
- **代价**：标题风格是"翻译体"而非"AI 改写标题"，xhs 文案为规则式拼接。可接受——本项目的核心价值是**数字可靠**。
- **状态**：已接受（实测 generator=hybrid，数字与行情层逐位一致）

---

## ADR-017 涨跌幅一律使用日线收盘序列，弃用 meta.chartPreviousClose

- **决策**：`yahoo.py` 改用 `indicators.quote[0].close` 日线序列——取「最近已收盘交易日」bar 的收盘价为 `price`，其前一根 close 为 `previous_close`；盘中运行跳过当日未收盘 bar；日线滞后于最近收盘日时标记 STALE。
- **动机**（2026-10-28 用户实测反馈触发）：`meta.chartPreviousClose` 在 `range=5d` 查询下是**5 日窗口起点前一日**的收盘价，与 `regularMarketPrice` 相减得到的是约 5 日累计涨幅——TSLA 显示 +9.03%（真实昨涨 +4.04%），META 显示 -10.67%（真实 -1.64%），三大指数同样受影响。
- **回归测试**：用反馈当日的真实 TSLA 日线数据构造 4 项测试（收盘口径 / 盘中跳过未收盘 bar / 滞后标记 STALE / 收盘后取当日 bar）。
- **状态**：已接受（实测全部标的口径正确）
