# Feature Specification: 美股每日简报生成系统

**Feature Branch**: `001-us-market-daily-xhs`

**Created**: 2026-10-27 ｜ **最后更新**: 2026-10-28

**Status**: Implemented & Verified（项目定位已收敛，见下方「定位变更记录」）

**Input**: 用户描述（原始）："每天自动收集美股市场新闻和行情，利用 AI 生成中文小红书图文内容……"
**定位变更（2026-10-28，经用户确认）**：本项目为**美股每日简报生成器**——每日产出一张长图与配套文字。**不包含**任何平台的自动发布功能（历史规格中的发布模块 E 仅保留代码，默认不启用）。

**定位变更（2026-10-28，ADR-016）**：LLM 职责收敛为两个窄任务——①盘后总结一段文字；②要闻标题中译。行情数据不交给模型加工，全部结构化内容由规则式确定性生成。

**定位变更（2026-10-28，ADR-017）**：涨跌幅一律使用日线收盘序列（昨收→今收）。

**相关文档**：`docs/research.md`（开源与数据源研究）、`docs/architecture.md`、`docs/decisions.md`（ADR-001~017）

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 每日自动生成一份可审核的中文日报素材 (Priority: P1)

运营者在每个美股交易日盘后，无需手工查数据，即可获得一份包含市场概览、3–5 条要闻、异动解读、财报/宏观、次日关注、风险提示的中文素材包（Markdown + 结构化 JSON + 来源清单），可直接阅读与修改。

**Why this priority**: 这是整条链路的价值核心；没有素材，后续图片、审核、发布都无意义。

**Independent Test**: 在无 API key、无网络的环境中执行 `usmarket generate --date 2026-10-24 --offline`，产出 `data/2026-10-24/content/report.md` 与 `content.json`，且其中所有数字均来自 fixture。

**Acceptance Scenarios**:

1. **Given** 离线环境且配置了 fixture 数据，**When** 执行 `generate --date <date> --offline`，**Then** 生成 `report.md`、`content.json`、`sources.md` 三个文件，且退出码为 0。
2. **Given** 无任何 LLM API key，**When** 执行 `generate`，**Then** 使用 `RuleBasedProvider` 生成内容，任务标记 `generator=fallback`，且内容中不含任何未经核实的数字。
3. **Given** 内容中某数字在 `raw/quotes.json` 中不存在，**When** 执行校验，**Then** 校验失败，任务状态置 `failed` 且不生成可供发布的产物。

---

### User Story 2 - 行情数字真实、可追溯、不编造 (Priority: P1)

运营者看到的每一个涨跌幅都能点回数据源；行情缺失时看到"数据缺失"而不是被编造的数字；盘前/盘中/盘后/休市状态被明确标注。

**Why this priority**: 本系统的可信度完全建立在数据真实性上（Constitution 原则 I）。

**Independent Test**: 单元测试覆盖涨跌幅计算、交易阶段判定、缺失标记；集成测试用固定 fixture 校验"缺失行情不产生数字"。

**Acceptance Scenarios**:

1. **Given** 某标的行情获取失败，**When** 生成日报，**Then** 该标的显示 `数据缺失`，`quality=MISSING`，且 `change_percent=None`，不得出现 0.0 或上一交易日数值。
2. **Given** 当前为交易日 08:00 ET，**When** 判定交易阶段，**Then** 结果为 `PRE`；20:30 ET 判为 `POST`；周六判为 `CLOSED`。
3. **Given** 展示的关键数字，**When** 追溯检查，**Then** 可在 `data/<date>/raw/quotes.json` 中找到同一数值与 provider 记录。

---

### User Story 3 - 生成竖屏图文素材 (Priority: P2)

运营者一键生成 1 张封面 + 5–7 张正文图片，中文排版清晰、竖屏适配、数据与文案一致，可直接预览审核。

**Why this priority**: 小红书是图文平台，图片是发布本体；但它依赖 US1/US2 的产物。

**Independent Test**: `usmarket render --date <date>` 后逐张用 Pillow 打开验证尺寸、非空白、无溢出，并比对图片文本中的数字与 `content.json`。

**Acceptance Scenarios**:

1. **Given** 已生成内容，**When** 执行 `render`，**Then** 产出 `cover.png` 与 5–7 张 `page_XX.png`，尺寸为配置值（默认 1080×1440），Pillow 可正常打开。
2. **Given** 一张图片的文本内容，**When** 布局计算，**Then** 文本在安全边距内换行，不超出画布；超长文本按配置截断并加省略号。
3. **Given** 图片中的行情数字，**When** 与 `content.json` 比对，**Then** 完全一致。
4. **Given** 指定 `--template flash_brief`，**When** 渲染，**Then** 使用"重大新闻专题"模板，与默认 `daily_review` 视觉不同。

---

### User Story 4 - 人工审核与状态跟踪 (Priority: P2)

运营者可查看每日任务状态、查看失败原因、审核通过/驳回、重新生成，且未审核内容不会进入发布。

**Why this priority**: 需求明确"默认人工审核模式"；也是安全边界的一部分。

**Independent Test**: CLI 全流程：`list` → `review` → `approve` → `publish`；并测试未 approve 时 publish 被拒绝。

**Acceptance Scenarios**:

1. **Given** 任务处于 `review`，**When** 执行 `approve`，**Then** 状态变为 `approved`；**When** 执行 `reject --reason`，**Then** 变为 `rejected` 且原因被记录。
2. **Given** 任务处于 `generated`（未 approve），**When** 执行 `publish`，**Then** 被拒绝并报错，不调用任何发布适配器。
3. **Given** 任务失败，**When** 执行 `show --date <date>`，**Then** 显示失败阶段（`collect`/`generate`/`render`/`publish`）与错误信息。
4. **Given** 任务处于 `failed`，**When** 执行 `rerun`，**Then** 从失败阶段重跑，且复用已成功阶段的产物。

---

### User Story 5 - 模拟发布与幂等 (Priority: P2)

运营者在未取得真实发布授权前，可用模拟适配器完整跑通"发布"流程，验证幂等与重试行为，且系统明确标注这是模拟。

**Why this priority**: 需求要求"如果当前环境无法验证真实发布，则实现可测试的模拟发布适配器，并明确标注真实发布尚未验收"。

**Independent Test**: 单元测试模拟成功/失败/重复调用三种路径。

**Acceptance Scenarios**:

1. **Given** `XHS_PUBLISHER=mock`，**When** 对已审核任务执行 `publish`，**Then** 返回 `published`，`result.json` 中 `simulated=true`。
2. **Given** 同一任务重复执行 `publish` 两次，**When** 第二次执行，**Then** 跳过并返回既有结果，不产生第二条发布记录。
3. **Given** mock 适配器被配置为首次失败，**When** 执行发布，**Then** 按退避策略重试有限次数（默认 3），失败后状态为 `failed` 且错误信息完整。
4. **Given** 发布日志，**When** 检查，**Then** 不含任何凭据字段（`cookie`/`token`/`password`/`authorization`）的明文值。

---

### User Story 6 - 定时自动运行 (Priority: P3)

运营者配置一次后，系统每个交易日盘后自动运行；支持手动触发与指定日期重跑；失败保留日志与产物。

**Why this priority**: 自动化是最终目标，但依赖前 5 个故事稳定。

**Independent Test**: 本地执行 `usmarket schedule resolve --at <utc-timestamp>` 验证时区与目标交易日解析；工作流 YAML 静态校验。

**Acceptance Scenarios**:

1. **Given** 工作流配置，**When** 检查，**Then** 同时包含 `schedule`（cron UTC）与 `workflow_dispatch`（支持 `run_date`、`mode`、`offline` 输入）。
2. **Given** 触发时间为 UTC 23:30（含 GitHub 延迟），**When** 解析目标交易日，**Then** 返回最近一个已收盘的美股交易日，而非简单取当天。
3. **Given** 同一 `run_date` 的工作流并发触发，**When** 第二次启动，**Then** 被 concurrency 组阻止或排队，不产生重复内容。
4. **Given** 任务失败，**When** 工作流结束，**Then** 上传 `data/<date>/` 与 `run.log` 作为 artifact，并输出失败摘要。

---

### Edge Cases

- **新闻源全部不可用**：记录每个源的 `source_error`，任务状态 `failed`（stage=collect），不产出内容；已存在的历史产物不被覆盖。
- **新闻源部分不可用**：继续用可用源，`sources.md` 中列出失败源；当可用新闻少于配置下限（默认 3 条）时，标记 `low_confidence` 并要求人工复核。
- **源未提供发布时间**：`published_at=None`，文案中显示"发布时间未知"，不得用 `fetched_at` 填充。
- **重复新闻**：同一事件被多个源转载 → 按 URL 归一 + 标题指纹去重，保留发布时间最早者，并在来源清单中列出转载来源。
- **市场休市（周末/节假日）**：自动切换为"最近完整交易日复盘"，标题与正文明确写出该日期，不假装是当天。
- **夏令时切换**：由 `zoneinfo` 自动处理，不手工维护偏移；测试覆盖 DST 边界日。
- **AI 输出非法 JSON**：尝试一次修复（提取 ```json 代码块 / 去除首尾噪声），仍失败则回退 `RuleBasedProvider` 并标记 `generator=fallback`。
- **AI 输出含未核实数字**：数字校验拦截，任务 `failed`（stage=validation）。
- **中文字体缺失**：渲染器报明确错误（提示安装字体或运行 `scripts/fetch_fonts.py`），不产出乱码图片。
- **图片文本溢出**：按配置截断 + 省略号；若仍溢出则渲染失败并报错，不产出异常图片。
- **凭据缺失**：启动时校验，缺失即退出并提示缺失项名称（不打印值）。

---

## Requirements *(mandatory)*

### Functional Requirements

**模块 A：新闻采集**

- **FR-001**: System MUST 从可配置的新闻源采集新闻，默认包含 Google News（商业话题 + 按 ticker 搜索）、CNBC、MarketWatch、Yahoo 个股 RSS、美联储新闻稿 RSS、Investing.com。
- **FR-002**: System MUST 采集 SEC EDGAR 的 8-K 等公司公告，且 MUST 发送包含应用名与联系邮箱的 `User-Agent` 请求头。
- **FR-003**: System MUST 记录每条新闻的：标题、摘要、原始链接、来源名称、发布时间、抓取时间、涉及股票代码。
- **FR-004**: System MUST 区分 `published_at`（源提供，可为空）与 `fetched_at`（系统生成，必填）。
- **FR-005**: System MUST 支持用户自定义股票列表与新闻主题（配置文件或 CLI 参数）。
- **FR-006**: System MUST 覆盖以下类别：三大指数（S&P 500 / Nasdaq Composite / Dow Jones）、科技与 AI 龙头（NVDA/AAPL/MSFT/GOOGL/AMZN/META/TSLA 等）、财报与公司公告、并购与重大事件、美联储/通胀/就业/利率等宏观、市场异动与情绪。
- **FR-007**: System MUST 对新闻去重（URL 归一化 + 标题指纹）并进行时效性过滤（可配置 lookback 小时数）。
- **FR-008**: System MUST 对来源分级（`official` / `established` / `aggregator`），排序时优先官方与权威媒体。
- **FR-009**: System MUST 对无法核实发布时间或来源的信息做显式标记，不得表述为已确认事实。
- **FR-010**: System MUST 记录每个数据源的使用限制、配额与许可说明（写入 `sources.md` 与 README）。

**模块 B：行情数据**

- **FR-011**: System MUST 提供独立的行情数据服务，与新闻采集解耦。
- **FR-012**: System MUST 至少提供指数与重点股票的价格与涨跌幅、数据日期时间与时区（America/New_York）、交易阶段、前一交易日收盘、可选成交量。
- **FR-013**: System MUST 明确区分盘前/盘中/盘后/最近完整交易日，且 MUST NOT 依赖 provider 返回的 `marketState`（实测为 None）。
- **FR-014**: System MUST NOT 由 AI 编造或补全行情数字；缺失时标记 `quality=MISSING`。
- **FR-015**: System MUST 标记过期（`STALE`）与异常（`ANOMALOUS`）数据，且不将延迟行情标注为实时行情。
- **FR-016**: System MUST 保存 provider 原始响应片段，保证每个展示数字可追溯。
- **FR-017**: System MUST 在市场休市时自动切换为最近完整交易日复盘并明确标注。

**模块 C：AI 内容生成**

- **FR-018**: System MUST 定义可替换的 `LLMProvider` 接口，模型与 API 通过环境变量配置。Provider 包括：`rule_based`（默认，无 key 兜底）、`dashscope`（阿里百炼，端点/模型/密钥自动预设）、`openai_compatible`（任意 OpenAI 兼容端点）、`anthropic`。System MUST 提供 LLM 连通性自检与可用模型列表查询命令（`llm-check` / `llm-models`）。
- **FR-019**: System MUST 生成：今日概览、3–5 条要闻、热门股票/行业异动解读、重要财报与宏观事件、下一交易日关注、风险提示与信息来源、小红书标题/正文/话题标签。
- **FR-020**: System MUST 以结构化 JSON 输出，禁止下游依赖自由文本解析。
- **FR-021**: System MUST 区分事实、分析、推测三类表述（`confidence: fact|analysis|speculation`）。
- **FR-022**: System MUST NOT 输出保证获利/稳赚类表述，MUST NOT 制造虚假紧迫感，MUST NOT 输出无证据支持的确定性股价预测。
- **FR-023**: System MUST NOT 伪造引用、新闻来源、财报数字或专家观点。
- **FR-024**: System MUST 为重要新闻保留来源链接与时间。
- **FR-025**: System MUST 在输出前执行结构校验、数字校验、来源检查，任一不通过则失败。
- **FR-026**: System MUST 在 LLM 不可用时使用 `RuleBasedProvider` 兜底，并标记 `generator=fallback`。

**模块 D：图文生成**

- **FR-027**: System MUST 生成 1 张封面 + 5–7 张正文图片 + 一份 Markdown 文案 + 一份结构化 JSON 文案 + 一份来源与数据清单。
- **FR-028**: 图片 MUST 包含标题与日期、核心市场数据、新闻重点与简洁解读、重要股票代码、数据来源与风险提示。
- **FR-029**: 图片 MUST 使用统一字体与配色，竖屏（默认 1080×1440），中文排版清晰。
- **FR-030**: 图片内数据 MUST 与 `content.json` 完全一致（测试比对）。
- **FR-031**: System MUST 提供至少两种模板：`daily_review`（每日市场复盘）与 `flash_brief`（重大新闻专题）。
- **FR-032**: 颜色、字体、封面样式、账号名称 MUST 可通过配置文件调整。
- **FR-033**: System MUST 在字体缺失时报明确错误，不产出乱码图片。

**模块 E：发布管理**

- **FR-034**: System MUST 将发布能力设计为独立适配器，不依赖采集与生成模块。
- **FR-035**: 适配器 MUST 实现接口：`validate_content()` / `upload_images()` / `create_draft()` / `publish()` / `get_publish_status()`。
- **FR-036**: System MUST 支持流程：采集 → 生成 → 校验 → 生成图片 → 保存待审核 → 人工确认 → 发布 → 记录结果。
- **FR-037**: System MUST 默认人工审核；支持通过/驳回/修改/重新生成。
- **FR-038**: System MUST 记录发布任务 ID、执行时间、结果、错误信息。
- **FR-039**: System MUST 通过内容指纹与任务状态防止重复发布。
- **FR-040**: System MUST 采用有限次数重试 + 退避策略。
- **FR-041**: System MUST 在发布成功后保存对应内容与素材版本。
- **FR-042**: System MUST NOT 实现验证码绕过、反检测规避或违反平台规则的功能。
- **FR-043**: System MUST 将真实发布适配器标记为未验收，直到账号授权、平台兼容性与实测均通过。

**模块 F：定时调度**

- **FR-044**: System MUST 提供 GitHub Actions 工作流，支持 `schedule` 与 `workflow_dispatch`。
- **FR-045**: System MUST 支持配置时区与运行时间，并考虑美国夏令时与交易日历。
- **FR-046**: System MUST 在失败时保留日志与产物并输出失败摘要。
- **FR-047**: System MUST 支持重新运行指定日期的任务。
- **FR-048**: System MUST 通过 concurrency 组避免并发重复生成。
- **FR-049**: System MUST NOT 把工作流触发时间等同于平台实际发布时间，发布时 MUST 重新校验时间。
- **FR-050**: 凭据 MUST 通过 GitHub Secrets 管理。

**模块 G：审核与任务管理**

- **FR-051**: System MUST 支持状态：`pending` / `generated` / `review` / `approved` / `scheduled` / `published` / `failed` / `rejected`。
- **FR-052**: System MUST 保存每日运行状态，支持按日期查询、查看失败原因、重跑失败任务、从已生成素材恢复审核流程。
- **FR-053**: System MUST 对发布操作提供幂等性保护。

**工程质量**

- **FR-054**: 代码 MUST 使用类型注解，公共接口 MUST 有类型标注。
- **FR-055**: 外部 API 调用 MUST 设置超时、错误处理与必要限流。
- **FR-056**: System MUST 输出结构化日志。
- **FR-057**: System MUST 提供可复现的依赖管理（`pyproject.toml` + 锁文件策略）。
- **FR-058**: System MUST 提供单元测试与集成测试，并支持离线运行。
- **FR-059**: System MUST 对敏感配置做启动校验。
- **FR-060**: System MUST 提供存储迁移策略。

**安全**

- **FR-061**: System MUST NOT 将密钥/凭据写死在源码中。
- **FR-062**: 日志 MUST NOT 输出密码、Token、完整 Cookie。
- **FR-063**: System MUST NOT 让外部新闻内容改变系统指令或触发代码执行。
- **FR-064**: System MUST 分开存储原始行情数据与 AI 生成文本。
- **FR-065**: 数据错误时 MUST 停止发布，不得静默使用编造数据。
- **FR-066**: 生成失败、图片失败、发布失败 MUST 能分别定位（`stage` 字段）。

### Key Entities

- **NewsItem**：标题、摘要、原始链接、来源名称、`published_at`、`fetched_at`、`tickers`、`category`、`trust_level`。
- **Quote**：`symbol`、`price`、`change`、`change_percent`、`previous_close`、`volume`、`as_of`、`market_phase`、`provider`、`is_delayed`、`quality`、`raw`。
- **QuoteSnapshot**：日期、`market_phase`、指数列表、个股列表、`calendar_confidence`、provider 列表。
- **DailyContent**：`summary`、`index_moves`、`top_news`、`watchlist_moves`、`earnings_and_macro`、`next_session`、`risk_notes`、`xhs{title,body,tags}`、`sources`、`disclaimer`。
- **PublishPayload**：`title`、`body`、`tags`、图片路径列表、`content_fingerprint`、`idempotency_key`。
- **PublishTask**：`date`、`status`、`stage`、`generator`、`fingerprint`、`history[]`、`error`。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 在完全离线、无 API key 环境下，`pytest` 全部通过，且 `generate --offline` 能产出完整素材包。
- **SC-002**: 联网执行 `generate` 能从 ≥4 个实测可用新闻源取到数据，三大指数行情获取成功率 100%（Yahoo chart 实测可用）。
- **SC-003**: 所有对外展示的行情数字 100% 可在 `raw/quotes.json` 中追溯到 provider 原始值；数字校验器对注入的编造数字 100% 拦截。
- **SC-004**: 生成的图片 100% 可被 Pillow 打开，尺寸符合配置，且通过"非空白 + 数字与 content.json 一致"检查。
- **SC-005**: 未 `approved` 的任务调用 `publish` 100% 被拒绝；同一任务重复 `publish` 不产生第二条发布记录。
- **SC-006**: 交易阶段判定在 DST 边界、周末、NYSE 节假日三类日期上 100% 正确。
- **SC-007**: 日志中 100% 不含凭据明文（由专门的测试断言）。
- **SC-008**: 每个 Phase 的已实现/未实现清单与代码实际行为一致，可复现验证。

---

## Assumptions

1. 运行环境为 Python 3.11+（本机 3.13.12），Windows/macOS/Linux 均可；CI 用 `ubuntu-latest`。
2. 第一版只实现盘后复盘（`mode=after_close`）；盘前模式预留枚举与配置。
3. 无 LLM API key 时使用规则式兜底生成器，产物需人工复核后才可发布。
4. 默认行情 provider 为 Yahoo 非公开接口（无 SLA），用户可替换为 Finnhub / Alpha Vantage。
5. 小红书真实发布 API 对个人账号不可用；Phase 5 之前发布为模拟/导出模式，明确标注未验收。
6. 存储默认文件 + JSONL；SQLite 作为可选后端。
7. 审核界面第一版为 CLI + Markdown 审核文件，不做 Web 后台。
8. GitHub Actions cron 存在延迟，发布时重新校验时间而非依赖触发时间。
9. 所有 RSS 内容仅引用标题与摘要并保留原链接，不做全文转载。
10. 用户自行负责遵守数据源条款与小红书平台规则。
