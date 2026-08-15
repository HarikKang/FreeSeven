# FreeSeven

A股 + 跨市场 ETF 动量轮动量化工具。小资金、信号 + 手动下单、月频调仓。

## 策略（v1 定型）

- **信号**：过去 250 个交易日（12 个月）动量，取动量为正的前 8 只 ETF 等权持有；无正动量则空仓
- **过热剔除**：12 个月动量超过 80% 的票不买（历史数据显示 >80% 后 6 个月平均 -4%）
- **候选池**：35 只（宽基 / 行业 / 红利 / 国债·货币防御 / 黄金 / 纳指·标普·恒生·日经等跨市场）
- **调仓**：每月最后一个交易日收盘后出信号，下月第一个交易日开盘手动执行
- **成本**：佣金万 2.5（最低 5 元）、ETF 免印花税、滑点 0.1%

### 回测结果（2018-01 ~ 2026-08）

| 指标 | 策略 | 沪深300 |
|---|---|---|
| 年化收益 | 9.6% | ~1.5% |
| 最大回撤 | -26% | -45% |
| 夏普 | 0.62 | - |
| 调仓 | 约 10 次/年，单边换手 26%/期 | - |

样本外验证（2023-2026）：年化 10.2%、夏普 0.65、回撤 -18%，与样本内一致。策略特点：熊市抗跌（2018 空仓、2022 仅 -4.6%），牛市靠跨市场趋势（纳指/标普/日经）获得超额。

## 目录结构

```
config.py      配置加载（config.yaml + .env）
config/        config.yaml、.env.example
data/          数据层（tushare 封装、SQLite、ETF 池）
strategy/      动量、持仓分配、调仓调度
backtest/      回测引擎与绩效指标
signals/       信号生成与推送
scripts/       拉数据、回测、出信号
tests/         单元测试
```

## 快速开始

```bash
pip install -r requirements.txt
cp config/.env.example config/.env   # 填 TUSHARE_TOKEN
python scripts/fetch_data.py         # 全量拉取 ETF 日线到 SQLite
python scripts/backtest.py --chart out/equity.png   # 回测
python scripts/run_signal.py --capital 100000       # 出本月调仓信号
```

常用命令：

```bash
python scripts/fetch_data.py --incremental          # 增量更新
python scripts/run_signal.py --fetch --capital 100000  # 先更新数据再出信号
python scripts/run_signal.py --force                # 非调仓日强制出信号
```

微信推送：在 `config/.env` 配置 `DINGTALK_WEBHOOK_URL` 与 `DINGTALK_SECRET`（钉钉群→群设置→智能群助手→自定义机器人），`config/config.yaml` 的 `notify.channel` 设为 `dingtalk`。也支持 Server酱（`SERVERCHAN_KEY`）/ PushPlus（`PUSHPLUS_TOKEN`）。

## 注意事项

- **跨市场 QDII ETF 存在溢价/折价**：价格含溢价，极端时溢价可能回落导致回撤，实盘需留意
- 策略赚的是趋势/风格超额，震荡市会有连续小亏，**不构成投资建议**
- 本工具只出信号，下单由你手动执行，请严格执行纪律

## 免责声明

本工具仅提供量化信号与统计研究，不构成投资建议。