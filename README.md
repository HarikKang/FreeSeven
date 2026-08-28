# FreeSeven

A股 + 跨市场 ETF 动量轮动量化工具。小资金、信号 + 手动下单、月频调仓。

## 策略

- **信号**：过去 250 个交易日（12 个月）动量，取动量为正的前 8 只 ETF 等权持有；无正动量则空仓
- **过热剔除**：12 个月动量超过 80% 的票不买（防高位接盘）
- **跨市场限仓**：QDII（纳指/标普/恒生/日经等）最多入选 2 只，限溢价回落与单一市场集中风险
- **溢价监测**：出信号时对比收盘价与基金净值，溢价 >3% 提醒、>5% 建议回避并给出替补
- **候选池**：41 只（宽基 / 行业 / 红利 / 国债·货币·可转债·短债防御 / 黄金·豆粕·有色期货·能源 / 纳指·标普·恒生·日经等跨市场）
- **调仓**：每月最后一个交易日收盘后出信号，下月第一个交易日开盘手动执行
- **成本**：佣金万 2.5（最低 5 元）、ETF 免印花税、滑点 0.1%

### 回测结果（2018-01 ~ 2026-08，前复权）

| 指标 | 策略 | 沪深300 |
|---|---|---|
| 年化收益 | 13.0% | ~3.4% |
| 最大回撤 | -17.6% | -42% |
| 夏普 | 0.80 | - |
| 调仓 | 87 次/8.6 年，单边换手 25.6%/期 | - |

策略特点：熊市抗跌（2018 空仓躲过 -26%）、牛市靠跨市场趋势获得超额；急速反转年（2019、2024）会明显跑输基准，这是动量策略的结构性弱点。归因：黄金+美股贡献约 3 个点年化，`python scripts/attribution.py` 可复核；参数稳健性用 `scripts/sensitivity.py --oos-start 20230101` 检验；逐年滚动验证与池子改动贡献检验用 `scripts/walk_forward.py`。

**预期管理**：上表的 13%/回撤 -17.6% 是含 2021-2022 商品大年、且候选池在同一样本内扩充后的最好情形；常态预期应按 **年化 10~11%、回撤 -25% 左右**规划，若出现股商同跌或急速反转年，实际回撤可能更深。新候选池（能源/钢铁/可转债/短债/豆粕/有色期货）的贡献是否稳定，用 `scripts/walk_forward.py --exclude ...` 逐年复核。

## 目录结构

```
config.py      配置加载（config.yaml + .env）
config/        config.yaml、.env.example
data/          数据层（tushare 封装、SQLite、ETF 池、数据同步）
strategy/      动量计算、统一策略类 MomentumStrategy、调仓调度
backtest/      回测引擎与绩效指标
signals/       信号生成、溢价监测、推送与报告渲染
scripts/       拉数据、回测、敏感性、滚动验证、归因、出信号
tests/         单元测试
pyproject.toml 包声明（依赖唯一来源，pip install -e .[dev,plot]）
```

## 快速开始

```bash
pip install -r requirements.txt      # 以可编辑模式安装 freeseven 包（依赖声明在 pyproject.toml）
cp config/.env.example config/.env   # 填 TUSHARE_TOKEN
python scripts/fetch_data.py         # 全量拉取 ETF 日线到 SQLite
python scripts/run_backtest.py --chart out/equity.png   # 回测
python scripts/run_signal.py --capital 100000       # 出本月调仓信号
```

常用命令：

```bash
python scripts/fetch_data.py --incremental          # 增量更新（各标的按自己水位，含复权因子）
python scripts/run_signal.py --fetch --capital 100000  # 先更新数据再出信号
python scripts/run_signal.py --force                # 非调仓日强制出信号
python scripts/sensitivity.py                       # 参数敏感性（window × top_n 网格，检验过拟合）
python scripts/sensitivity.py --oos-start 20230101  # 网格同时输出 IS/OOS，防调参变样本内挖矿
python scripts/walk_forward.py                      # 逐年滚动验证
python scripts/walk_forward.py --exclude CODES      # 剔除指定标的逐年对比（验证池子改动贡献）
python scripts/attribution.py                       # 收益来源归因（剔除法 + 跨市场限仓对照）
```

推送配置：在 `config/.env` 配置 `DINGTALK_WEBHOOK_URL` 与 `DINGTALK_SECRET`（钉钉群→群设置→智能群助手→自定义机器人），`config/config.yaml` 的 `notify.channel` 设为 `dingtalk`。也支持 Server酱（`SERVERCHAN_KEY`）/ PushPlus（`PUSHPLUS_TOKEN`）。

信号存档：每次运行 `run_signal.py` 会在 `data/signals/` 写入带日期的记录（如 `20260828.json`），并纳入 git 版本管理——换电脑时 clone 即可带走全部历史信号，方便事后对照实际成交做复盘（`latest.json` 为快捷方式不入库）。

## 注意事项

- **价格为前复权**：基于 tushare `fund_adj` 复权因子，修正分红除息对动量/收益的污染；升级后请先跑一次 `python scripts/fetch_data.py` 拉取复权因子
- **QDII 溢价风险**：跨市场 ETF 常因额度限制暂停申购，二级价格可能大幅高于净值；信号自带溢价检测，但净值滞后 1~2 日，**下单前务必以交易软件实时 IOPV 为准，限价单不追高**
- 策略赚的是趋势/风格超额，震荡市会有连续小亏，**不构成投资建议**
- 本工具只出信号，下单由你手动执行，请严格执行纪律

## 免责声明

本工具仅提供量化信号与统计研究，不构成投资建议。