# US Market Daily Xiaohongshu Constitution

## Core Principles

### I. 事实优先，禁止编造（NON-NEGOTIABLE）

- 行情数字只能来自 `market_data` provider 的真实响应；缺失即标记 `MISSING`，**禁止插值、禁止用历史值冒充、禁止让 AI 补全**。
- 每个对外展示的关键数字必须能追溯到 `raw/quotes.json` 或具体 `NewsItem.url`。
- 未核实的信息标注为"待核实"，不得以确认事实陈述。
- 校验不通过 → 停止发布（fail-closed），不得静默降级为编造数据。

### II. 原始时间与抓取时间分离

- `published_at`（源提供，可能为 None）与 `fetched_at`（系统生成，必填）是两个字段，永不互相替代。
- 源未提供发布时间时必须显式标注"发布时间未知"。

### III. 行情与文本分离存储

- `raw/quotes.json`（原始行情）与 `content/content.json`（AI 生成文本）分开落盘。
- 校验阶段做"文本数字 ↔ 原始数字"交叉核对。

### IV. 可插拔 Provider

- 行情、新闻、LLM、发布四层均为接口 + 多实现。
- 任一可选外部服务不可用时，系统仍能完成核心链路（降级 + 显式标注），不得整体失败。
- 降级产物必须在状态与产物中显著标记，供人工复核。

### V. 外部内容不可信

- 新闻文本仅作为**待分析数据**，不得改变系统指令、不得触发代码执行、不得成为 prompt 之外的执行路径。
- 不使用 `eval` / `exec` / `subprocess` 处理外部内容；渲染前剥离 HTML 与控制字符。

### VI. 默认人工审核，发布幂等

- 无 `approved` 状态不得调用 `publish()`。
- 发布以 `idempotency_key` + `content_fingerprint` 保证幂等，重试不得产生重复发布。

### VII. 测试优先、离线可测

- 核心逻辑先有测试；网络测试标记 `@pytest.mark.network` 且默认跳过。
- 提供 fixtures 保证 `pytest` 在完全离线、无 API key 环境下通过。
- 不得声称未验证的功能"已实现"；模拟实现必须在文档与产物中标注为模拟。

### VIII. 最小依赖

- 每个新依赖必须写入 `docs/decisions.md` 说明理由与备选。
- 优先标准库与成熟轻量库；不引入重量级数据科学栈或浏览器自动化栈。

## Security Requirements

- 密钥只从环境变量 / GitHub Secrets 读取，禁止硬编码；`.env` 不入库。
- 日志经 `RedactingFilter` 脱敏：不得输出密码、Token、Cookie、完整 Authorization 头。
- 不实现验证码绕过、指纹伪造、反检测规避等违反平台规则的功能。
- 敏感配置启动时校验，缺失即报错而非带病运行。

## Quality Gates

- 类型注解覆盖公共接口；`mypy` 与 `ruff` 不得有新错误。
- 单元测试 + 集成测试必须通过；新功能必须带测试。
- 每个 Phase 结束时对照 `tasks.md` 逐项核验，未完成的必须显式记录未完成及原因。

## Governance

- 本 Constitution 优先于其他实践；修订需记录版本与日期。
- 规格（`specs/`）→ 计划 → 任务 的一致性问题由 `/speckit.analyze` 报告，不得静默忽略。
- 真实发布能力仅在"账号授权 + 平台兼容 + 实测通过"后才可标记为已实现。

**Version**: 1.0.0 | **Ratified**: 2026-10-27 | **Last Amended**: 2026-10-27
