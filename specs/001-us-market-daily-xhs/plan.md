# Implementation Plan：美股每日情报与小红书自动化发布系统

**Branch**: `001-us-market-daily-xhs` | **Date**: 2026-10-27 | **Spec**: `spec.md`
**研究输入**：`docs/research.md` | **架构**：`docs/architecture.md` | **决策**：`docs/decisions.md`

---

## Summary

从零构建一个 Python 后端 + GitHub Actions 的系统：采集美股新闻与行情 → AI（或规则兜底）生成中文结构化内容 → 校验 → 渲染小红书竖屏图文 → CLI 人工审核 → 可插拔发布适配器（默认 mock）→ 定时运行。

**关键技术选择（均有实测或源码证据，见 decisions.md）**：
- 语言/运行时：Python 3.11+（本机 3.13.12），`pyproject.toml` + `uv` 锁定。
- 新闻：RSS/Atom（`feedparser`）+ SEC EDGAR（声明式 UA），6 个已实测可用源。
- 行情：Yahoo chart API（实测可用、支持 `^GSPC/^IXIC/^DJI`）+ 可插拔 provider。
- LLM：OpenAI 兼容（含 `dashscope` 百炼预设，**已实测 qwen3.8-flash**）/ Anthropic（未实测）/ 规则兜底。
- 图片：Pillow（唯一渲染技术）。
- 存储：文件 + JSONL（SQLite 可选）。
- 调度：GitHub Actions（cron + workflow_dispatch + concurrency）。
- 发布：适配器 + mock 默认，真实发布标记未验收。

---

## Technical Context

| 项 | 值 |
| --- | --- |
| 语言/版本 | Python 3.11+（实测 3.13.12） |
| 主依赖 | `requests`、`feedparser`、`Pillow`、`pydantic>=2`、`python-dateutil`、`typer`、`python-dotenv` |
| 开发依赖 | `pytest`、`pytest-cov`、`ruff`、`mypy` |
| 存储 | 文件 + JSONL（默认）；SQLite（可选后端） |
| 测试 | `pytest`；网络测试 `@pytest.mark.network` 默认跳过 |
| 目标平台 | 本地 Windows/macOS/Linux + GitHub Actions `ubuntu-latest` |
| 项目类型 | 单一 Python 项目（多模块包） |
| 性能目标 | 单次全流程 < 60s（离线 < 5s） |
| 约束 | 离线可跑、无 key 可跑、不可编造数据、默认人工审核 |
| 规模/复杂度 | 中小：约 12 个模块、6 个 CLI 命令 |

---

## Constitution Check

| 原则 | 是否满足 | 落实位置 |
| --- | --- | --- |
| I 事实优先、禁止编造 | ✅ | `market_data/quality.py`、`validation/numbers.py`、fail-closed |
| II 原始/抓取时间分离 | ✅ | `NewsItem.published_at` vs `fetched_at` |
| III 行情与文本分离 | ✅ | `raw/quotes.json` vs `content/content.json` |
| IV 可插拔 Provider | ✅ | 行情/新闻/LLM/发布四层接口 + 降级标注 |
| V 外部内容不可信 | ✅ | `processors/sanitize.py`，无 eval/exec/subprocess |
| VI 默认人工审核 + 幂等 | ✅ | `storage/state_machine.py`、`publishing/idempotency.py` |
| VII 测试优先、离线可测 | ✅ | fixtures + `NETWORK_TESTS` 开关 |
| VIII 最小依赖 | ✅ | 见 ADR-011 |

无违反项。

---

## Project Structure

```
BullSheet/
├── src/usmarket/
│   ├── __init__.py
│   ├── config.py                 # 配置加载（yaml + env + CLI 覆盖）
│   ├── logging_setup.py          # 结构化日志 + RedactingFilter
│   ├── errors.py
│   ├── collectors/
│   │   ├── base.py               # NewsSource 协议
│   │   ├── rss.py                # RSS/Atom 抓取
│   │   ├── edgar.py              # SEC EDGAR（合规 UA）
│   │   └── manager.py            # 并发抓取 + 部分失败容忍
│   ├── market_data/
│   │   ├── base.py               # QuoteProvider 协议
│   │   ├── yahoo.py              # 默认 provider
│   │   ├── finnhub.py            # 可选（需 key）
│   │   ├── mock.py               # fixture provider
│   │   ├── phases.py             # 交易阶段判定（zoneinfo + NYSE 日历）
│   │   ├── calendar.py           # NYSE 节假日
│   │   └── service.py            # 聚合 + 质量标记
│   ├── processors/
│   │   ├── sanitize.py           # HTML 剥离、控制字符清理
│   │   ├── dedupe.py             # URL 归一 + 标题指纹去重
│   │   ├── classify.py           # 类别/主题/ticker 识别
│   │   └── filter.py             # 时效过滤 + 排序
│   ├── ai/
│   │   ├── base.py               # LLMProvider 协议 + JSON 修复 + 枚举同义写法归一化
│   │   ├── openai_compatible.py  # OpenAI 兼容（含 dashscope 预设 + extra_body）
│   │   ├── anthropic.py          # 未实测（无 key）
│   │   ├── rule_based.py         # 无 key 兜底
│   │   ├── prompts.py
│   │   └── service.py            # 生成 + 解析 + 落盘
│   ├── validation/
│   │   ├── schema.py             # pydantic 模型 + JSON Schema
│   │   ├── numbers.py            # 数字可追溯校验
│   │   ├── sources.py            # 来源校验
│   │   └── compliance.py         # 禁用表述/确定性预测校验
│   ├── content/
│   │   ├── markdown.py
│   │   ├── json_store.py
│   │   └── sources_doc.py
│   ├── image_renderer/
│   │   ├── fonts.py              # 字体解析（含缺失报错）
│   │   ├── layout.py             # 换行/截断/溢出检测
│   │   ├── theme.py              # 主题配置
│   │   ├── templates/
│   │   │   ├── base.py
│   │   │   ├── daily_review.py
│   │   │   └── flash_brief.py
│   │   └── renderer.py
│   ├── publishing/
│   │   ├── base.py               # Publisher 协议
│   │   ├── mock.py
│   │   ├── manual_export.py
│   │   ├── browser.py            # 默认禁用，UNVERIFIED
│   │   ├── idempotency.py
│   │   ├── retry.py
│   │   └── service.py
│   ├── scheduler/
│   │   ├── resolve.py            # 触发时间 → 目标交易日
│   │   └── tasks.py              # 盘后/盘前模式（第一版仅盘后）
│   ├── storage/
│   │   ├── models.py
│   │   ├── file_store.py         # 默认
│   │   ├── sqlite_store.py        # 可选
│   │   ├── state_machine.py
│   │   └── migrate.py
│   └── cli/
│       └── main.py               # Typer
├── config/default.yaml
├── tests/{unit,integration,fixtures}
├── docs/{research.md,architecture.md,decisions.md}
├── specs/001-us-market-daily-xhs/{spec.md,clarify.md,plan.md,tasks.md,checklists/}
├── scripts/{fetch_fonts.py,run_offline_demo.py}
├── .github/workflows/daily.yml
├── .env.example / pyproject.toml / README.md
└── data/ (运行产物，gitignore)
```

---

## Complexity Tracking

无 Constitution 违规，无需额外说明。

---

## Phasing

- **Phase 1（MVP）**：采集 + 行情 + 去重 + 生成 + Markdown 日报（离线用 fixture 也能跑通）。
- **Phase 2**：结构化中文内容 + 来源/数字校验 + 封面与多页图片。
- **Phase 3**：任务存储、状态机、审核 CLI、幂等、mock 发布。
- **Phase 4**：GitHub Actions 工作流、cron、concurrency、artifact、失败摘要。
- **Phase 5**：发布适配器评估（mock 默认；真实发布未验收）。
- **Phase 6**：完整测试、README、部署与故障排查。

---

## Risks

| 风险 | 缓解 |
| --- | --- |
| Yahoo 非公开接口变更/限流 | provider 可插拔；失败即 `MISSING` 并标注；README 提示替换 |
| RSS 源失效（已实测 Yahoo 总榜 404） | 多源冗余；单源失败不影响整体；`sources.md` 记录失败源 |
| CI 无中文字体 | `scripts/fetch_fonts.py` + 工作流安装 `fonts-noto-cjk`；字体缺失时明确报错 |
| AI 输出非法 JSON 或编造数字 | 一次修复 + 枚举同义写法归一化 + 规则兜底 + 数字校验 fail-closed |
| AI 输出 emoji / Markdown（图片字体无字形） | 渲染前剥离（`image_renderer/sanitize.py`），content.json 原样保留 |
| 百炼思考链导致生成超时（实测 100–120s） | `LLM_EXTRA_BODY_JSON` 关闭思考链（降至 ~40s）+ `LLM_TIMEOUT_SECONDS=180` + 超时回退规则式 |
| GitHub cron 延迟 | 目标交易日按"最近已收盘"解析，不取触发日；发布时重新校验时间 |
| 小红书无公开发布 API | mock 默认 + 明确标注未验收；不实现反检测 |
