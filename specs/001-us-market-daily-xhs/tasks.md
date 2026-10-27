# Tasks：美股每日情报与小红书自动化发布系统

**Branch**: `001-us-market-daily-xhs` | **Date**: 2026-10-27
**输入**：`plan.md` / `spec.md` / `docs/decisions.md`

标记含义：`[x]` 已完成并测试通过；`[~]` 部分完成；`[ ]` 未完成。
每条任务必须可被测试验证，不接受"声称完成"。

---

## Phase 0 — 研究与规格

- [x] T001 检查工作区与运行环境（Python 3.13.12 / uv / 无 git），记录限制
- [x] T002 实测 5 个候选仓库：README、依赖、LICENSE、最近提交（`scripts/fetch_repos.py`）
- [x] T003 实测 10+ 新闻源可用性，记录 404/403 项（`docs/research.md` §2.1）
- [x] T004 实测行情源：Yahoo chart 可用、Stooq 404（`docs/research.md` §2.2）
- [x] T005 调研小红书发布 API 现状，确认个人号无公开 API
- [x] T006 安装并使用 Spec Kit CLI 1.2.3（codebuddy 集成）初始化项目
- [x] T007 编写 `docs/research.md`
- [x] T008 编写 `docs/architecture.md`
- [x] T009 编写 `docs/decisions.md`（12 条 ADR）
- [x] T010 编写 Constitution（`.specify/memory/constitution.md`）
- [x] T011 编写 `spec.md`（66 条 FR + 8 条 SC）
- [x] T012 编写 `clarify.md`（10 项歧义处置）
- [x] T013 编写 `plan.md`
- [x] T014 编写 `checklists/requirements.md`

---

## Phase 1 — 采集 / 行情 / 去重 / 生成 / Markdown（MVP）

- [x] T015 `pyproject.toml`（依赖、pytest/ruff/mypy 配置）+ `.env.example`
- [x] T016 `src/usmarket/config.py`：yaml + env + CLI 三级覆盖；敏感配置校验
- [x] T017 `src/usmarket/logging_setup.py`：结构化日志 + `RedactingFilter` 脱敏
- [x] T018 `market_data/calendar.py`：NYSE 节假日 2025–2027 + Good Friday 计算
- [x] T019 `market_data/phases.py`：PRE/REGULAR/POST/CLOSED 判定（zoneinfo，不依赖 marketState）
- [x] T020 `market_data/base.py` + `yahoo.py`：Yahoo chart provider（超时/重试/原始片段保存）
- [x] T021 `market_data/mock.py`：fixture provider（离线）
- [x] T022 `market_data/service.py`：聚合、涨跌幅计算、`quality` 标记（MISSING/STALE/ANOMALOUS）
- [x] T023 `collectors/base.py` + `rss.py`：RSS/Atom 抓取（feedparser + 超时重试）
- [x] T024 `collectors/edgar.py`：SEC EDGAR（声明式 UA）
- [x] T025 `collectors/manager.py`：并发抓取 + 单源失败容忍
- [x] T026 `processors/sanitize.py`：HTML 剥离 + 控制字符清理（防外部内容注入）
- [x] T027 `processors/dedupe.py`：URL 归一 + 标题指纹去重
- [x] T028 `processors/classify.py` + `filter.py`：类别/主题/ticker 识别、时效过滤、来源分级排序
- [x] T029 `ai/base.py`：`LLMProvider` 协议 + JSON 提取修复
- [x] T030 `ai/openai_compatible.py`、`ai/anthropic.py`
- [x] T031 `ai/rule_based.py`：无 key 兜底（只复用已核实数字）
- [x] T032 `ai/prompts.py` + `ai/service.py`：生成 `DailyContent`
- [x] T033 `validation/schema.py`：pydantic 模型（结构校验）
- [x] T034 `validation/numbers.py`：数字可追溯校验（fail-closed）
- [x] T035 `validation/sources.py` + `compliance.py`：来源校验 + 禁用表述校验
- [x] T036 `content/markdown.py`、`json_store.py`、`sources_doc.py`
- [x] T037 `cli/main.py`：`generate` 命令（含 `--date` `--offline` `--tickers`）
- [x] T038 `tests/unit` Phase 1：涨跌幅、交易阶段、去重、脱敏、数字校验
- [x] T039 `tests/integration/test_offline_pipeline.py`：离线端到端

---

## Phase 2 — 结构化内容 / 来源校验 / 图片生成

- [x] T040 `image_renderer/fonts.py`：字体候选解析 + 缺失明确报错
- [x] T041 `image_renderer/layout.py`：中文换行、截断、溢出检测
- [x] T042 `image_renderer/theme.py`：颜色/字体/封面样式/账号名可配置
- [x] T043 `image_renderer/templates/base.py` + `daily_review.py` + `flash_brief.py`
- [x] T044 `image_renderer/renderer.py`：封面 1 张 + 正文 5–7 张
- [x] T045 `cli`：`render` 命令
- [x] T046 `tests/unit/test_renderer.py`：可打开、尺寸、非空白、数字一致
- [x] T047 生成示例图片到 `docs/examples/`

---

## Phase 3 — 存储 / 审核 / 状态机 / 幂等 / 模拟发布

- [x] T048 `storage/models.py`：`PublishTask` + 状态枚举
- [x] T049 `storage/state_machine.py`：合法迁移校验
- [x] T050 `storage/file_store.py`：原子写入 + 文件锁 + 每日目录
- [x] T051 `storage/sqlite_store.py` + `migrate.py`：可选后端与迁移
- [x] T052 `publishing/base.py`：`Publisher` 协议（validate/upload_images/create_draft/publish/get_publish_status）
- [x] T053 `publishing/mock.py`：可注入成功/失败
- [x] T054 `publishing/manual_export.py`：导出人工复制用发布包
- [x] T055 `publishing/browser.py`：默认禁用、标记 UNVERIFIED、不实现反检测
- [x] T056 `publishing/idempotency.py` + `retry.py`：指纹幂等 + 有限退避重试
- [x] T057 `publishing/service.py`：发布流程编排
- [x] T058 `cli`：`list` / `show` / `review` / `approve` / `reject` / `publish` / `rerun`
- [x] T059 `tests/unit/test_state_machine.py`、`test_publishing.py`
- [x] T060 `tests/integration/test_review_flow.py`

---

## Phase 4 — GitHub Actions 调度

- [x] T061 `scheduler/resolve.py`：触发时间 → 目标交易日（最近已收盘）+ 时区转换
- [x] T062 `scheduler/tasks.py`：盘后模式（盘前预留）
- [~] T063 `.github/workflows/daily.yml`：cron + `workflow_dispatch(run_date/mode/offline)` + concurrency + artifact + 失败摘要
      —— 文件已按 GitHub Actions 规范编写，但**未在真实仓库触发过**（无远端仓库权限），
      因此"定时任务真实运行"未验收；目标交易日解析、幂等等逻辑已有离线测试覆盖。
- [x] T064 `scripts/fetch_fonts.py` + CI 字体安装步骤
- [x] T065 `tests/unit/test_scheduler.py`：时区/DST/周末/节假日

---

## Phase 5 — 真实发布适配器评估

- [x] T066 评估小红书官方开放平台发布能力（调研结论：个人号无公开 API；企业号需主体认证 + 权限审核）
- [x] T067 实现 `browser` 适配器骨架（默认禁用，明确 UNVERIFIED，不含反检测）
- [x] T068 在 README 与 `result.json` 中标注真实发布未验收

---

## Phase 6 — 测试 / 文档 / 交付

- [x] T069 `tests/` 补齐：采集、行情、内容、图片、发布、调度六类
- [x] T070 `README.md`：环境/安装/AI 配置/数据源/本地运行/指定日期/生成图片/Actions/审核发布/已验证与模拟清单
- [x] T071 `docs/deployment.md` 部署与故障排查
- [x] T072 `docs/limitations.md` 已知限制与后续任务
- [x] T073 运行全量测试并修复失败
- [x] T074 `analyze.md` 一致性检查
- [x] T075 `specs/001-us-market-daily-xhs/checklists/implementation.md` 验收清单

---

## Phase 6.5 — 增量：接入阿里百炼（真实 LLM 验收）

> 背景：本机已有 `DASHSCOPE_API_KEY`，用真实模型（qwen3.8-flash）验收 LLM 生成链路。
> 本阶段暴露并修复了 4 个真实缺陷，均有回归测试。

- [x] T076 `config.py`：`LLM_PROVIDER=dashscope` 预设（端点/模型/密钥来源自动推导）+ `LLM_EXTRA_BODY_JSON` 厂商参数注入
- [x] T077 `cli`：`llm-check`（真实调用自检）与 `llm-models`（列出当前 key 可用模型）命令
- [x] T078 `ai/base.py::normalize_payload`：枚举同义写法归一化（实测模型输出 `pre-market` 导致校验失败）
- [x] T079 `image_renderer/sanitize.py`：渲染前剥离 emoji/Markdown（实测 LLM 文案含 `📉`/`**`，中文字体无字形）
- [x] T080 `image_renderer/layout.py`：修复中文断字 bug——`str.isalnum()` 对中文为 True 导致所有中文断行点失效，每行硬切（`标普5`/`00`）
- [x] T081 `image_renderer/templates/base.py`：个股解读文字画到卡片外的溢出修复（卡片内绘制、行高自适应）
- [x] T082 `ai/rule_based.py`：解读改为相对强弱定性描述（避免与卡片右侧数字重复）
- [x] T083 `tests/unit/test_llm_provider_config.py`（11 项）+ `test_layout_and_sanitize.py`（16 项）
- [x] T084 真实验收：`usmarket llm-check` 0.70s 通过；完整 `generate`（百炼真实调用）产出通过全部校验；示例存 `docs/examples/llm_*`
- [x] T085 文档同步：README（AI 配置/已验证清单/故障排查）、`.env.example`、`limitations.md`、`decisions.md`（ADR-013~015）、`spec.md` FR-018

---

## 未完成 / 已明确排除

- 真实小红书自动发布：**未验收**，仅在"授权 + 兼容 + 实测通过"后启用（见 README Phase 5 章节）。
- 反检测、验证码绕过：**不实现**（Constitution 明令禁止）。
- 盘前模式：枚举预留，第一版不启用（需求允许）。
- Web 审核后台：第一版不做（需求明确）。
