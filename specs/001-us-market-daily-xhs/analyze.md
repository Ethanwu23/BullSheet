# Analyze：规格 ↔ 架构 ↔ 任务 一致性检查

**日期**：2026-10-27 ｜ **范围**：`spec.md`（66 FR / 8 SC）、`plan.md`、`tasks.md`、`docs/architecture.md`

方法：逐条 FR 找到实现位置与验证方式；标注 `✅ 已实现并测试` / `⚠️ 部分实现` / `❌ 未实现` / `➖ 不适用`。

---

## 一、Spec 覆盖矩阵

### 模块 A：新闻采集

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-001 多源采集 | `collectors/manager.py`、`config/default.yaml` | `test_live_rss_feeds_parse`（network）、`test_offline_pipeline` | ✅ |
| FR-002 SEC EDGAR + 合规 UA | `collectors/edgar.py` | `test_sec_edgar_requires_declared_user_agent`（network） | ✅ |
| FR-003 记录 7 个字段 | `collectors/models.py::NewsItem` | `test_content_json_is_valid_and_complete` | ✅ |
| FR-004 published/fetched 分离 | `NewsItem.published_at / fetched_at` | `test_published_at_and_fetched_at_are_distinct`、`test_missing_published_at_not_replaced_by_fetched_at` | ✅ |
| FR-005 自定义列表与主题 | `config.py`（YAML/env/CLI 三级） | `test_cli_generate_offline`（`--tickers`） | ✅ |
| FR-006 六类信息覆盖 | `processors/classify.py`、`config` 的 tickers/topics/feeds | `test_classify_category` | ⚠️ 分类与检索覆盖已实现；"并购""市场情绪"依赖源文本关键词，无专门数据源 |
| FR-007 去重 + 时效 | `processors/dedupe.py`、`filter.py` | `test_deduplicate_*`（5 项）、`test_old_news_filtered_out` | ✅ |
| FR-008 来源分级排序 | `TrustLevel.rank`、`filter.rank` | `test_rank_puts_official_first_and_unknown_time_last` | ✅ |
| FR-009 未核实信息标注 | `NewsItem.published_display`、`confidence` | `test_fact_without_published_at_blocked` | ✅ |
| FR-010 数据源限制记录 | `content/sources_doc.py::SOURCE_NOTES` | `test_sources_doc_lists_limits` | ✅ |

### 模块 B：行情

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-011 独立行情服务 | `market_data/service.py` | `test_snapshot_roundtrip` | ✅ |
| FR-012 价格/涨跌幅/时间/时区/阶段/前收/成交量 | `market_data/models.py::Quote` | `test_yahoo_chart_api_returns_index_quotes`（network） | ✅ |
| FR-013 不依赖 marketState | `market_data/phases.py` | `test_classify_phase`（9 参数化用例） | ✅ |
| FR-014 禁止编造/补全 | `compute_change_percent` 返回 None；`missing_quote()` | `test_compute_change_percent_missing_returns_none`、`test_missing_quote_has_no_numbers`、`test_snapshot_marks_unusable_symbols` | ✅ |
| FR-015 标记过期/异常 + 不伪装实时 | `QuoteQuality`、`is_stale`（按时段）、`is_delayed=True` | `test_is_stale_*`（4 项）、`test_pre_market_overnight_close_is_not_stale` | ✅ |
| FR-016 保存 provider 原始片段 | `Quote.raw` + `raw/quotes.json` | `test_snapshot_has_no_fabricated_numbers`、`test_quotes_are_traceable_in_report` | ✅ |
| FR-017 休市自动调整 | `calendar.previous_trading_day`、`scheduler/resolve.py` | `test_weekend_falls_back_to_friday`、`test_holiday_falls_back_to_previous_trading_day` | ✅ |

### 模块 C：AI 生成

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-018 可替换 Provider + env 配置 | `ai/base.py`、`openai_compatible.py`（含 dashscope 预设）、`anthropic.py`、`config.LLMConfig` | `test_llm_provider_config.py`（11 项）；真实调用百炼 qwen3.8-flash 通过 | ✅ 接口 + 配置 + 真实调用（Anthropic 未实测） |
| FR-019 六类内容 + 小红书文案 | `ai/prompts.py`、`ai/rule_based.py`、`validation/schema.py` | `test_content_json_is_valid_and_complete` | ✅ |
| FR-020 结构化 JSON | `DailyContent`（pydantic） | `test_schema_*` | ✅ |
| FR-021 fact/analysis/speculation | `Confidence` 枚举 | `test_speculation_allows_hedged_prediction` | ✅ |
| FR-022 禁夸大/紧迫/确定性预测 | `validation/compliance.py` | `test_compliance_blocks_banned_phrases`（6 参数化） | ✅ |
| FR-023 禁伪造引用 | 同上 + `validate_sources` | `test_source_url_must_appear_in_sources_list` | ✅ |
| FR-024 保留来源链接与时间 | `NewsEntry.source_url/published_at` | `test_sources_missing_url_blocked` | ✅ |
| FR-025 结构/数字/来源校验 | `ai/service.py::validate_content` | `test_fabricated_number_in_text_is_blocked`、`test_real_numbers_pass` | ✅ |
| FR-026 不可用时规则兜底 | `ai/rule_based.py`、`ai/service.py` 回退 | 离线全流程（`generator=rule_based`） | ✅ |

### 模块 D：图文

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-027 封面+5-7 页+MD+JSON+来源 | `image_renderer/renderer.py`、`content/*` | `test_offline_pipeline_end_to_end` | ✅ |
| FR-028 图片要素齐备 | `templates/daily_review.py`、`flash_brief.py` | 目视 + `docs/examples/*.png` | ✅ |
| FR-029 统一字体配色/竖屏 | `theme.py`、`layout.py` | `test_wrap_text_respects_width`、`test_wrap_text_does_not_split_cjk_number_token` | ✅ |
| FR-030 图片数据与 JSON 一致 | 同源渲染 | `test_rendered_image_numbers_match_content` | ✅ |
| FR-031 两种模板 | `templates/` | `test_both_templates_produce_pages`（参数化） | ✅ |
| FR-032 颜色/字体/账号可配置 | `config.ImageConfig`、`ThemeConfig`、`account.name` | `test_theme_hex_parsing` | ✅ |
| FR-033 字体缺失明确报错 | `errors.FontMissingError`、`fonts.py` | `test_missing_font_raises_clear_error` | ✅ |

### 模块 E：发布

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-034 独立适配器、不耦合 | `publishing/*` 不 import collectors/ai | 代码审查 | ✅ |
| FR-035 五个接口 | `publishing/base.py::Publisher` | `test_mock_publish_success` | ✅ |
| FR-036 完整流程 | `cli/pipeline.py` + `publishing/service.py` | `test_review_approve_publish_flow` | ✅ |
| FR-037 默认人工审核 + 四操作 | `storage/state_machine.py`、CLI | `test_publish_requires_approval`、`test_reject_records_reason` | ✅ |
| FR-038 记录 ID/时间/结果/错误 | `PublishRecord`、`publish/result.json` | `test_review_approve_publish_flow` | ✅ |
| FR-039 指纹/状态防重复 | `publishing/retry.py::has_succeeded` | `test_publish_idempotent`、`test_publish_twice_is_idempotent` | ✅ |
| FR-040 有限重试 + 退避 | `retry_with_backoff` | `test_retry_with_backoff_success_on_third_try` | ✅ |
| FR-041 发布成功后保存素材版本 | `result.json` 含 `images` / `content_fingerprint` | 同上 | ⚠️ 保存的是路径与指纹，未做图片副本归档 |
| FR-042 不做验证码/反检测 | `publishing/browser.py` 拒绝实现 | 代码审查 | ✅ |
| FR-043 真实发布标记未验收 | `verified=False` 全链路 | `test_browser_publisher_is_not_verified`、`test_manual_export_adapter` | ✅ |

### 模块 F：调度

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-044 schedule + workflow_dispatch | `.github/workflows/daily.yml` | YAML 审查（未真实触发） | ⚠️ 未在真实仓库运行 |
| FR-045 时区 + DST + 日历 | `scheduler/resolve.py`、`market_data/calendar.py` | `test_dst_switching_is_handled`、`test_dst_transition_day_parsing` | ✅ |
| FR-046 失败留日志与产物 | workflow `upload-artifact` + `if: failure()` | YAML 审查 | ⚠️ 未真实触发 |
| FR-047 重跑指定日期 | `usmarket rerun --date` / `workflow_dispatch.run_date` | `test_rejected_task_can_be_rerun` | ✅ |
| FR-048 concurrency 防重复 | workflow `concurrency.group` | YAML 审查 | ⚠️ 未真实触发 |
| FR-049 不把触发时间当发布时间 | `resolve_target_date` + `publish` 前校验 | `test_before_close_falls_back_to_previous_session` | ✅（逻辑层） |
| FR-050 Secrets 管理 | workflow `secrets.*` / `vars.*` | YAML 审查 + `.gitignore` | ✅ |

### 模块 G：审核与任务

| FR | 实现位置 | 验证 | 状态 |
| --- | --- | --- | --- |
| FR-051 8 状态 | `storage/models.py::TaskStatus` | `test_can_transition`（10 参数化） | ✅ |
| FR-052 查询/失败原因/重跑/恢复 | `cli/main.py` list/show/rerun/render | `test_list_and_show`、`test_failed_task_is_reported_with_stage` | ✅ |
| FR-053 发布幂等 | `retry.has_succeeded` + CLI 短路 | `test_publish_twice_is_idempotent` | ✅ |

### 工程质量与安全

| FR | 实现 | 状态 |
| --- | --- | --- |
| FR-054 类型注解 | 全模块 `from __future__ import annotations` + 公共接口标注 | ✅（`mypy` 非 strict） |
| FR-055 超时/错误/限流 | `http_client.py`（Retry + backoff + pool） | ✅ |
| FR-056 结构化日志 | `logging_setup.py::JsonFormatter` | ✅ |
| FR-057 可复现依赖 | `pyproject.toml` + `uv.lock`（39 个包已锁定） | ✅ |
| FR-058 单元+集成+离线 | `tests/`（224 passed） | ✅ |
| FR-059 敏感配置校验 | `config.validate_sensitive_config` | ✅ |
| FR-060 存储迁移 | `storage/migrate.py`、`SqliteTaskStore.migrate_from_files` | ✅ |
| FR-061 密钥不硬编码 | `.env` + secrets；`.gitignore` | ✅ |
| FR-062 日志不出凭据 | `RedactingFilter` | ✅（有专门测试） |
| FR-063 外部内容不改变行为 | `processors/sanitize.py`，无 eval/exec/subprocess | ✅ |
| FR-064 行情与文本分开存储 | `raw/quotes.json` vs `content/content.json` | ✅ |
| FR-065 数据错误即停 | 校验 fail-closed | ✅ |
| FR-066 失败可分别定位 | `TaskStage` + `errors.stage` | ✅ |

---

## 二、发现的缺口与处置

| # | 缺口 | 严重度 | 处置 |
| --- | --- | --- | --- |
| 1 | FR-006 中"并购/市场情绪"无专门数据源，靠关键词识别 | 低 | 已记录在 `docs/limitations.md`；分类枚举覆盖，召回率取决于源文本 |
| 2 | FR-041 发布成功后仅记录图片路径，未复制副本 | 低 | 已记录；图片本身在 `data/<date>/images/` 不会被覆盖（已发布任务禁止重生成） |
| 3 | FR-044/046/048 GitHub Actions 未真实运行 | **中** | 已在 README/limitations 明确标注"未在真实仓库触发过"；逻辑层（目标日解析、幂等）已有测试 |
| 4 | ~~FR-057 未提供精确锁文件~~ | 已关闭 | 已生成 `uv.lock`（39 个包） |
| 5 | ~~FR-018 LLM 真实调用未实测~~ | 已关闭 | 百炼 qwen3.8-flash 实测通过；Anthropic 仍未实测（已在 README 标注） |
| 7 | LLM 输出 emoji / Markdown / 枚举同义写法导致渲染与校验问题 | 已关闭 | 新增 `image_renderer/sanitize.py` 与 `ai/base.normalize_payload`；有回归测试 |
| 6 | 交易日历仅到 2027 | 低 | 超范围抛错而非静默猜错；已列入后续任务 |

**结论**：无 `❌ 未实现` 的关键需求；6 项缺口均已在文档中显式披露，且不影响"离线可跑、无 key 可跑、默认不自动发布"的核心闭环。

---

## 三、Constitution 合规复核

| 原则 | 复核结果 |
| --- | --- |
| I 事实优先、禁止编造 | ✅ 数字校验 fail-closed；缺失行情 `price=None` 并显示"数据缺失"；有针对性测试 |
| II 时间字段分离 | ✅ 两个字段、两个显示函数、专门测试 |
| III 行情与文本分离 | ✅ 两个物理文件；校验阶段交叉核对 |
| IV 可插拔 Provider | ✅ 行情/新闻/LLM/发布四层均为协议 + 多实现 |
| V 外部内容不可信 | ✅ HTML/控制符清洗；无 eval/exec/subprocess；注入检测仅标注不执行 |
| VI 人工审核 + 幂等 | ✅ 状态机强制；指纹 + idempotency_key 双保险 |
| VII 测试优先、离线可测 | ✅ 178 离线测试通过；网络测试默认跳过 |
| VIII 最小依赖 | ✅ 8 个运行时依赖，无 pandas/numpy/selenium/matplotlib |

---

## 四、任务清单一致性

`tasks.md` 中 T001–T075 与代码/文档一一对应，无"声称完成但无对应实现"的条目。
唯一需要下修预期的是 T063（Actions 工作流）：文件已写、未真实运行，已在 `tasks.md` 与 README 中标注。

---

## 五、建议的下一步（收敛阶段）

1. 用真实 LLM key 跑一次生成，检查中文质量与 `warnings`（最高价值）；
2. 在真实仓库 `workflow_dispatch` 跑一次，确认 artifact/摘要；
3. 补齐 `uv.lock`；
4. 实现盘前模式（规格已预留）。
