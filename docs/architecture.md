# 系统架构设计

**项目**：US Market Daily（美股每日简报生成器——每日一张长图）
**版本**：v2（定位调整：只生成内容与图片，不含平台发布；发布适配器保留但默认不启用）
**日期**：2026-10-28

---

## 1. 架构总览

系统是一条**单向流水线**，每一步的产物都落盘，任何一步失败都能定位、能重跑、能人工干预。

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│ collectors  │   │ market_data  │   │  processors  │
│ 新闻采集     │   │  行情服务     │   │ 去重/过滤/分级 │
└──────┬──────┘   └──────┬───────┘   └──────┬───────┘
       │  NewsItem[]     │  QuoteSnapshot   │ 清洗后语料
       └────────────┬────┴──────────────────┘
                    ▼
             ┌─────────────┐
             │     ai      │  LLMProvider（可插拔）
             │  内容生成    │  输出结构化 JSON（DailyContent）
             └──────┬──────┘
                    ▼
             ┌─────────────┐
             │ validation  │  结构校验 / 数字校验 / 来源校验 / 合规校验
             └──────┬──────┘
                    ▼
             ┌─────────────┐
             │   content   │  Markdown + JSON + 来源清单
             └──────┬──────┘
                    ▼
             ┌─────────────┐
             │image_renderer│ 封面 + 5~7 页正文（Pillow）
             └──────┬──────┘
                    ▼
             ┌─────────────┐     ┌──────────┐
             │   storage   │◄───►│   cli    │  审核/发布/重跑
             │ 任务与状态   │     └──────────┘
             └──────┬──────┘
                    ▼
             ┌─────────────┐
             │  publishing │  适配器：mock（默认）/ manual_export / browser(未验收)
             └──────┬──────┘
                    ▼
             ┌─────────────┐
             │  scheduler  │  GitHub Actions cron + workflow_dispatch
             └─────────────┘
```

**关键架构约束**：

1. **行情数字与 AI 文本严格分离。** 行情由 `market_data` 产出 `QuoteSnapshot`；AI 只做"选择引用哪个数字 + 撰写解读文字"，且输出后由 `validation` 反查：内容中出现的每个数字都必须能在 `QuoteSnapshot` 或 `NewsItem` 中找到出处。数字不匹配 → 校验失败 → 不进入发布。
2. **发布是独立适配器。** `publishing` 不 import `collectors` / `ai`；只接收 `PublishPayload`（标题、正文、标签、图片路径列表、指纹）。
3. **每一步产物落盘。** 目录 `data/<date>/`，见 §5。
4. **默认人工审核。** 没有 `approved` 状态的任务不能进入 `publish()`。

---

## 2. 模块职责

| 模块 | 路径 | 职责 | 禁止事项 |
| --- | --- | --- | --- |
| `collectors` | `src/usmarket/collectors/` | RSS/Atom 抓取、EDGAR 抓取、字段归一化、按 ticker/主题检索 | 不做去重（交给 processors） |
| `market_data` | `src/usmarket/market_data/` | 行情获取、涨跌幅计算、交易阶段判定、缺失/异常标记 | **不允许补全或插值行情数字** |
| `processors` | `src/usmarket/processors/` | 去重（URL + 标题指纹）、时效过滤、来源分级、主题归类 | 不修改原文数字 |
| `ai` | `src/usmarket/ai/` | LLM Provider 抽象、prompt 组装、结构化输出解析与修复 | 不直接落盘、不做发布 |
| `validation` | `src/usmarket/validation/` | JSON Schema 校验、数字可追溯校验、来源校验、合规词校验 | 不放行未通过项 |
| `content` | `src/usmarket/content/` | Markdown 渲染、文案 JSON 落盘、来源清单渲染 | — |
| `image_renderer` | `src/usmarket/image_renderer/` | 封面 + 正文页渲染（Pillow）、模板切换、字体解析 | 不修改数据，只渲染已校验数据 |
| `publishing` | `src/usmarket/publishing/` | 适配器接口 + mock / manual_export / browser(未验收) | 不含新闻采集逻辑 |
| `scheduler` | `src/usmarket/scheduler/` | 交易日历、时区转换、运行时机判定、日期参数解析 | — |
| `storage` | `src/usmarket/storage/` | 任务存储、状态机、幂等、产物索引、迁移 | — |
| `cli` | `src/usmarket/cli/` | 命令行入口（Typer） | — |

---

## 3. 核心数据模型

### 3.1 `NewsItem`（采集产物）

```python
@dataclass(frozen=True)
class NewsItem:
    title: str              # 原文标题
    summary: str            # 摘要（截断后的纯文本）
    url: str                # 原始链接（必须保留）
    source: str             # 来源名称（如 "CNBC"、"SEC EDGAR"）
    published_at: datetime | None   # 原始发布时间（tz-aware；None 表示源未提供）
    fetched_at: datetime            # 抓取时间（系统生成，必填）
    tickers: tuple[str, ...]        # 识别出的股票代码
    category: str                   # macro / earnings / company / market_move / other
    trust_level: str                # official / established / aggregator
    language: str = "en"
```

`published_at` 与 `fetched_at` **必须分别记录**，不得互相替代。源未提供发布时间时 `published_at=None` 并在报告中标注"发布时间未知"，不得用抓取时间冒充。

### 3.2 `QuoteSnapshot`（行情产物）

```python
@dataclass(frozen=True)
class Quote:
    symbol: str
    display_name: str
    price: float | None
    change: float | None
    change_percent: float | None
    previous_close: float | None
    volume: int | None
    as_of: datetime | None          # 行情时间戳（tz-aware）
    market_phase: MarketPhase       # PRE / REGULAR / POST / CLOSED / UNKNOWN
    provider: str                   # 数据来自哪个 provider
    is_delayed: bool                # 是否为延迟行情
    quality: QuoteQuality           # OK / STALE / MISSING / ANOMALOUS
    raw: dict                       # provider 原始响应片段，用于追溯
```

`quality != OK` 的条目在文案与图片中显示为"数据缺失/待核实"，**绝不用上一交易日数据冒充当日数据**。

### 3.3 `DailyContent`（AI 结构化输出）

```json
{
  "date": "2026-10-27",
  "market_phase": "closed",
  "summary": "…今日概览…",
  "index_moves": [{"symbol": "^GSPC", "name": "标普500", "price": 7676.77, "change_percent": -0.86, "source_ref": "quote:^GSPC"}],
  "top_news": [
    {"headline": "…", "body": "…", "tickers": ["NVDA"],
     "source_title": "…", "source_url": "https://…", "published_at": "2026-10-27T…",
     "confidence": "fact"}
  ],
  "watchlist_moves": [...],
  "earnings_and_macro": [...],
  "next_session": [...],
  "risk_notes": ["…"],
  "xhs": {"title": "…", "body": "…", "tags": ["#美股", …]},
  "sources": [{"title": "…", "url": "…", "source": "…", "published_at": "…"}],
  "disclaimer": "…"
}
```

`confidence` 取值：`fact`（有来源）/ `analysis`（明确标注为分析）/ `speculation`（明确标注为推测）。合规性校验禁止把 `speculation` 写成确定结论。

### 3.4 `PublishTask`（任务与状态）

```python
class TaskStatus(str, Enum):
    PENDING = "pending"        # 待生成
    GENERATED = "generated"    # 内容已生成
    REVIEW = "review"          # 等待人工审核
    APPROVED = "approved"      # 审核通过
    SCHEDULED = "scheduled"    # 等待发布
    PUBLISHED = "published"    # 发布成功
    FAILED = "failed"          # 任务失败
    REJECTED = "rejected"      # 审核驳回
```

合法状态迁移（`storage/state_machine.py` 强制校验，非法迁移抛错）：

```
pending → generated → review → approved → scheduled → published
              │          │         │           │
              └──────────┴─────────┴───────────┴──→ failed
review → rejected → generated（修改后重新生成）
failed → pending（重跑）
```

---

## 4. 交易阶段判定

`market_data/phases.py` 基于 `America/New_York` 时区与 NYSE 常规时段计算，**不依赖 provider 返回的 `marketState`**（实测 Yahoo 该字段为 `None`）：

| 阶段 | 判定 |
| --- | --- |
| `PRE` | 交易日 04:00–09:30 ET |
| `REGULAR` | 交易日 09:30–16:00 ET |
| `POST` | 交易日 16:00–20:00 ET |
| `CLOSED` | 非上述时段，或遇周末/休市日 |
| `UNKNOWN` | 无法确定日历或时间 |

夏令时由 `zoneinfo` 的 `America/New_York` 自动处理，不手工维护偏移。
休市日判断采用"周末 + 内置 NYSE 节假日表（含 Good Friday 规则计算）"，表内年份不足时退化为"仅周末判断"并标记 `calendar_confidence=low`。

---

## 5. 目录与产物布局

```
data/
  <YYYY-MM-DD>/
    raw/
      news.jsonl            # 原始采集（含 fetched_at）
      quotes.json           # 原始行情（含 provider raw 片段）
    processed/
      news_deduped.jsonl    # 去重过滤后
    content/
      content.json          # DailyContent 结构化
      report.md             # Markdown 日报
      sources.md            # 来源与数据清单
    images/
      cover.png
      page_01.png … page_07.png
    publish/
      payload.json          # 发布载荷（含指纹）
      result.json           # 发布结果
    task.json               # 任务状态与历史
    run.log                 # 结构化日志
state/
  tasks.db (SQLite) 或 tasks.jsonl   # 全局任务索引（默认 JSONL，可选 SQLite）
```

**原始行情与 AI 文本分开存储**：`raw/quotes.json` 与 `content/content.json` 是两个文件，追溯时先读 raw 再核对 content。

---

## 6. 幂等与去重

- **新闻去重**：`url` 规范化（去 utm 参数、去尾斜杠）+ 标题指纹（`sha1(归一化标题)`，归一化=小写、去标点、去停用词）。两者任一命中即判重，保留 `published_at` 更早的一条。
- **内容指纹**：`sha1(date + 排序后的新闻 URL 列表 + 行情关键数字)`，写入 `content_fingerprint`。
- **发布幂等**：`publishing` 执行前检查 `task.json` 中是否已存在 `status=published` 且 `fingerprint` 相同的记录；命中则跳过并返回既有结果。重试使用同一 `idempotency_key`，不产生新记录。

---

## 7. 失败处理

- 外部 HTTP 请求统一超时（默认 15s）+ 有限重试（默认 3 次，指数退避 1s/2s/4s，带抖动）。
- 单个新闻源失败 → 记录 `source_error`，继续其他源；**全部源失败才算采集失败**。
- 行情获取失败 → `QuoteQuality.MISSING`，**不允许 AI 编造**，报告中标注"行情缺失"。
- AI 生成失败 → 回退到 `RuleBasedProvider`（纯规则拼装，不含任何未经核实的数字），任务状态置 `generated` 但 `generator=fallback`，并在审核界面显著提示。
- 图片渲染失败 / 发布失败 → 分别写入 `stage` 字段，可独立定位。

---

## 8. 安全边界

- 外部新闻文本**只作为数据**，不进入任何 prompt 之外的执行路径；渲染前做 HTML 标签剥离与控制字符清理；不使用 `eval` / `exec` / `subprocess` 处理外部内容。
- 所有日志经 `RedactingFilter`，对 `cookie`、`token`、`password`、`authorization`、`api_key`、`secret` 等键名及疑似凭据值做脱敏。
- 凭据只从环境变量 / GitHub Secrets 读取，`.env` 不入库（`.gitignore` 已包含）。
- `publishing` 的 `browser` 适配器默认禁用，且**不实现**验证码绕过与反检测。

---

## 9. 测试策略

```
tests/
  unit/          # 纯函数、去重、涨跌幅、状态机、校验器、渲染布局计算
  integration/   # CLI 端到端（离线 fixture）、真实 RSS 解析（可跳过）、mock 发布全流程
  fixtures/      # 固定 RSS/行情样本，保证离线可测
```

- 网络测试默认跳过：标记 `@pytest.mark.network`，由 `NETWORK_TESTS=1` 显式开启。
- CI 中仅跑离线测试，保证可复现。
