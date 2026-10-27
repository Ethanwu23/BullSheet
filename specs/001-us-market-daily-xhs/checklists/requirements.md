# 需求完整性检查清单（Requirements Checklist）

**对象**：`spec.md` ｜ **日期**：2026-10-27
**用法**：发布或迭代前逐项核对；`[x]` 通过，`[ ]` 未通过需说明。

---

## A. 需求本身的质量

- [x] 每条 FR 可测试（66 条 FR 均能对应测试或明确的验证方式，见 `analyze.md`）
- [x] 明确写出"不做什么"（反检测、验证码、盘前模式、Web 后台）
- [x] 关键歧义已识别并给出默认值（`clarify.md` 10 项）
- [x] 成功标准可量化（SC-001 ~ SC-008）
- [x] 边界场景已列出（源全失败、部分失败、无发布时间、重复、休市、DST、非法 JSON、编造数字、字体缺失、文本溢出、凭据缺失）
- [x] 术语一致（`published_at` / `fetched_at` / `quality` / `stage` 在 spec、架构、代码中同名）
- [x] 未把模拟实现描述为真实集成（发布能力单独小节声明）

## B. 功能覆盖

- [x] 三大指数（S&P 500 / Nasdaq / Dow）
- [x] 科技与 AI 龙头自选股（NVDA/AAPL/MSFT/GOOGL/AMZN/META/TSLA）
- [x] 财报与公司公告（SEC EDGAR 8-K + 新闻分类）
- [x] 宏观（美联储 RSS + 关键词分类）
- [x] 市场异动与行业热点（分类 + 涨跌幅排序）
- [x] 用户自定义股票与主题
- [x] 去重与时效过滤
- [x] 来源链接与发布时间保留
- [x] 行情缺失/过期/异常标记
- [x] 交易阶段区分（盘前/盘中/盘后/休市）
- [x] 休市自动切换最近完整交易日
- [x] 可替换 LLM Provider（4 实现：dashscope 百炼预设**已实测** / openai_compatible / anthropic / rule_based）
- [x] 结构化 JSON 输出
- [x] 事实/分析/推测区分
- [x] 封面 + 5–7 页正文 + MD + JSON + 来源清单
- [x] 两种图片模板
- [x] 发布适配器接口（5 方法）
- [x] 人工审核（通过/驳回/修改/重生成）
- [x] 幂等 + 有限重试
- [x] 8 状态任务管理
- [x] GitHub Actions（cron + 手动 + 并发保护 + artifact）

## C. 真实性要求（最关键）

- [x] 行情数字不允许 AI 编造 → 结构性比对 + 文本数字扫描，fail-closed
- [x] 每个展示数字可追溯到 provider 原始值（`raw.raw` 片段）
- [x] 缺失行情不填补（`price=None`，显示"数据缺失"）
- [x] 延迟行情不标为实时（`is_delayed=True` + 报告注明）
- [x] 未经核实信息标注"发布时间未知"
- [x] 真实发布未验收则明确标注（`verified=false`）
- [x] 未实现功能未声称已实现（README 列"已验证/模拟/不做"三张表）

## D. 安全要求

- [x] 密钥仅从环境变量 / Secrets 读取
- [x] 日志脱敏（专用测试）
- [x] 外部内容不进入执行路径（无 eval/exec/subprocess）
- [x] HTML / 控制字符 / 零宽字符清洗
- [x] 原始行情与 AI 文本分开存储
- [x] 未审核不得发布
- [x] `.gitignore` 覆盖 `.env`、`cookies.json`、`credentials.json`、`*.pem`、`data/`
- [x] 不实现验证码绕过 / 反检测

## E. 可运维性

- [x] `usmarket check-config` 自检
- [x] 失败按阶段定位（collect/generate/validation/render/publish）
- [x] 失败可重跑，已成功阶段产物可复用
- [x] 运行日志结构化且落盘
- [x] 部署与故障排查文档（`docs/deployment.md`、README 故障排查表）
- [x] 已知限制文档（`docs/limitations.md`）

## F. 待确认事项（不阻塞）

- [ ] 是否需要在 CI 中直接完成 approve（当前设计为人工）
- [ ] 是否增加通知渠道（邮件/IM）
- [ ] 是否需要 Web 审核界面
- [ ] 是否需要盘前模式（当前仅盘后）
