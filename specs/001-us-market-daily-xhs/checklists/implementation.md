# 实现验收清单（Implementation Checklist）

**日期**：2026-10-27 ｜ **原则**：以实际执行结果为准，不以文档声称。

---

## 1. 可运行性

- [x] `pip install -e ".[dev]"` 成功
- [x] `usmarket check-config` 通过（无 key 环境）
- [x] `usmarket generate --date 2026-10-26 --offline` 成功（无网络、无 key）
- [x] `usmarket generate --date 2026-10-26` 成功（真实网络）
- [x] `usmarket render --date 2026-10-26` 成功
- [x] `usmarket list` / `show` / `approve` / `reject` / `publish` / `rerun` 均可用
- [x] `usmarket schedule --at <iso> --json` 输出目标交易日
- [x] `python -m usmarket.storage.migrate` 可迁移到 SQLite

## 2. 真实数据验证

- [x] Yahoo chart 取到 `^GSPC` / `^IXIC` / `^DJI` 真实价格（`usable=10/10`）
- [x] 20 个新闻源并发抓取成功（`sources ok: 20/20`）
- [x] SEC EDGAR 未声明 UA 返回 403、声明后返回 200（双向验证）
- [x] 已知失效源 `finance.yahoo.com/news/rssindex` 仍为 404
- [x] 真实运行产出 7 张图片（1080×1440）与完整 Markdown 报告

## 3. 测试结果

- [x] `python -m pytest tests -q` → **224 passed, 4 skipped**
- [x] `python -m pytest tests/integration/test_network_sources.py -m network` → **4 passed**
- [x] `python -m ruff check src tests` → **All checks passed**
- [x] 无网络测试被误纳入默认套件（`-m network` 默认跳过）

覆盖的必测项（对应第六阶段验收标准）：

| 要求 | 对应测试 | 通过 |
| --- | --- | --- |
| RSS 不可用能正确处理 | `test_rss_source_handles_unavailable_source` | ✅ |
| 重复新闻不重复计入 | `test_duplicate_news_counted_once`、`test_news_dedup_applied_in_pipeline` | ✅ |
| 发布时间与抓取时间正确区分 | `test_published_at_and_fetched_at_are_distinct`、`test_missing_published_at_not_replaced_by_fetched_at` | ✅ |
| 不可信文本不改变系统行为 | `test_injection_detected_but_not_executed`、`test_html_injection_is_stripped` | ✅ |
| 涨跌幅计算正确 | `test_compute_change_percent`（5 参数化） | ✅ |
| 缺失行情不被虚构填补 | `test_missing_quote_has_no_numbers`、`test_snapshot_marks_unusable_symbols` | ✅ |
| 交易阶段正确标注 | `test_classify_phase`（9 参数化）+ 早收盘 | ✅ |
| AI 数字与输入一致 | `test_real_numbers_pass`、`test_structural_numbers_match_snapshot` | ✅ |
| 标题/正文/标签/来源结构完整 | `test_content_json_is_valid_and_complete` | ✅ |
| 来源缺失能拦截 | `test_sources_missing_url_blocked` | ✅ |
| 未证实预测不写成事实 | `test_compliance_blocks_banned_phrases`、`test_confirmed_forecast_wording_is_blocked_even_in_speculation` | ✅ |
| 内容长度可配置 | `test_content_limits_are_configurable` | ✅ |
| 图片可正常打开 | `test_render_images` | ✅ |
| 图片尺寸符合配置 | 同上 | ✅ |
| 无空白图 / 文字溢出 | `test_assert_not_blank_detects_blank`、`test_wrap_text_respects_width` | ✅ |
| 图文数字一致 | `test_rendered_image_numbers_match_content` | ✅ |
| 模拟发布成功/失败 | `test_mock_publish_success`、`test_mock_publish_failure_recorded` | ✅ |
| 重试不重复发布 | `test_retry_does_not_duplicate_on_eventual_success`、`test_publish_idempotent` | ✅ |
| 未审核不能发布 | `test_publish_requires_approval`、`test_review_approve_publish_flow` | ✅ |
| 凭据不出现在日志 | `test_credentials_not_logged`、`test_setup_logging_writes_json_file` | ✅ |
| 手动运行指定日期 | `test_cli_generate_offline`、`test_schedule_command` | ✅ |
| 重复运行幂等 | `test_pipeline_is_idempotent_on_rerun`、`test_publish_twice_is_idempotent` | ✅ |
| 失败后可恢复 | `test_rejected_task_can_be_rerun`、`test_failed_task_is_reported_with_stage` | ✅ |
| 时区转换正确 | `test_dst_switching_is_handled`、`test_naive_trigger_treated_as_utc` | ✅ |

## 4. 交付物

- [x] `docs/research.md`（含实测数据与"未验证事项清单"）
- [x] `docs/architecture.md`
- [x] `docs/decisions.md`（12 条 ADR）
- [x] `docs/deployment.md`
- [x] `docs/limitations.md`
- [x] `docs/examples/`（5 张实际渲染图片 + 报告 + 来源清单）
- [x] `specs/001-us-market-daily-xhs/{spec,clarify,plan,tasks,analyze}.md` + 2 份 checklist
- [x] `.specify/memory/constitution.md`
- [x] `.github/workflows/daily.yml`
- [x] `.env.example`
- [x] `pyproject.toml`
- [x] `README.md`（含环境/安装/AI/数据源/运行/图片/Actions/审核发布/已验证清单/故障排查）
- [x] `config/default.yaml`
- [x] `src/usmarket/`（12 个模块）
- [x] `tests/`（unit + integration + fixtures）
- [x] `scripts/fetch_fonts.py`、`scripts/fetch_repos.py`

## 5. 未完成项（显式记录）

- [ ] 真实小红书发布适配器（未实现、未验收；`browser` 仅骨架）
- [x] LLM 真实模型调用实测（阿里百炼 qwen3.8-flash，走通完整生成 + 全部校验）
- [ ] Anthropic provider 实测（本机无 key）
- [ ] GitHub Actions 真实触发验证
- [ ] 盘前模式
- [ ] Web 审核界面
- [x] 精确依赖锁文件 `uv.lock`（39 个包）
- [ ] 覆盖率 90% 目标（当前核心链路覆盖，未统计全量）
