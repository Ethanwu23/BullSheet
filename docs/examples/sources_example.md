# 来源与数据清单 — 2026-10-27

## 一、行情数据源

| 标的 | 代码 | 最新 | 涨跌幅 | 时间(UTC) | 阶段 | 质量 | provider |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 标普500 | ^GSPC | 7,722.60 | +0.60% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 纳斯达克综合 | ^IXIC | 26,477.81 | +1.18% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 道琼斯工业 | ^DJI | 52,377.57 | +0.03% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 英伟达 | NVDA | 217.94 | +0.90% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 苹果 | AAPL | 347.10 | +0.93% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 微软 | MSFT | 531.33 | -0.24% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 谷歌 | GOOGL | 320.58 | +1.19% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 亚马逊 | AMZN | 253.10 | +1.61% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| Meta | META | 620.19 | -1.64% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| 特斯拉 | TSLA | 407.46 | +4.04% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |
| SpaceX | SPCX | 148.58 | +1.14% | 2026-10-27 20:00 | 盘中 | 正常 | yahoo |

- 快照时间：2026-10-28T21:56:12.694620+08:00
- 是否延迟行情：是（不得标注为实时）
- 交易日历可信度：high

## 二、新闻来源

| 来源 | 状态 | 条数 | 耗时(s) | 说明 |
| --- | --- | --- | --- | --- |
| Federal Reserve | 成功 | 20 | 0.97 |  |
| Investing.com | 成功 | 10 | 0.98 |  |
| Google News: AAPL | 成功 | 20 | 1.03 |  |
| MarketWatch | 成功 | 10 | 1.04 |  |
| Google News: MSFT | 成功 | 20 | 1.08 |  |
| Google News: NVDA | 成功 | 20 | 1.64 |  |
| Google News Business | 成功 | 20 | 1.70 |  |
| Google News: META | 成功 | 20 | 0.88 |  |
| Google News: SPCX | 成功 | 20 | 0.87 |  |
| Google News: GOOGL | 成功 | 20 | 1.03 |  |
| Google News: TSLA | 成功 | 20 | 1.24 |  |
| Google News: earnings | 成功 | 20 | 0.90 |  |
| Google News: employment | 成功 | 20 | 0.68 |  |
| CNBC | 成功 | 20 | 2.70 |  |
| Google News: AMZN | 成功 | 20 | 1.78 |  |
| Google News: fed | 成功 | 20 | 1.24 |  |
| Google News: semiconductor | 成功 | 20 | 1.02 |  |
| Google News: inflation | 成功 | 20 | 1.45 |  |
| Google News: ai | 成功 | 20 | 1.40 |  |
| Google News: merger | 成功 | 20 | 0.93 |  |
| SEC EDGAR | 失败 | 70 | 6.45 | SPCX/8-K: XML 解析失败 syntax error: line 2, column 61 |

## 三、数据源条款与使用限制

- **Yahoo Finance (chart API)**：非公开接口（query1.finance.yahoo.com/v8/finance/chart），无 SLA、可能限流或变更；返回值为延迟行情，不得标注为实时。商用前请自行评估 Yahoo 服务条款。
- **Finnhub**：免费档 60 次/分钟；不支持原始指数代码（^GSPC/^IXIC/^DJI），需改用 ETF。
- **Google News RSS**：公开 RSS；内容为第三方媒体版权所有，仅引用标题与摘要并保留原链接。
- **CNBC RSS**：公开 RSS；同上，仅做标题/摘要引用。
- **MarketWatch RSS**：Dow Jones 公开 RSS；仅做标题/摘要引用。
- **Federal Reserve RSS**：官方公开新闻稿，可自由引用，须注明来源。
- **Investing.com RSS**：公开 RSS；仅做标题/摘要引用。
- **SEC EDGAR**：公共数据；SEC 要求声明式 User-Agent（应用名/版本 + 联系邮箱），否则返回 403。请求频率限制 10 次/秒。
- **fixture**：离线样本数据，仅用于测试，不代表真实市场。

- **通用**：所有新闻内容版权归原媒体所有，本项目仅引用标题与摘要并保留原始链接，不做全文转载。
