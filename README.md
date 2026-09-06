# FreeSeven

A股 + 跨市场 ETF 动量轮动量化工具。小资金、信号 + 手动下单、月频调仓。

## 策略

- **信号**：过去 250 个交易日（12 个月）动量，取动量为正的前 8 只 ETF 等权持有；无正动量则空仓
- **过热剔除**：12 个月动量超过 80% 的票不买（防高位接盘）
- **分散约束**：科技主题（半导体/科创50/AI/创业板/纳指/标普/恒生科技等）最多 2 只；单一海外市场（美股/港股/日股）最多 1 只；QDII 总数最多 2 只
- **溢价风控**：出信号时对比收盘价与基金净值，溢价 >3% 预警；**溢价 >5% 或无法取得净值的高溢价 QDII 直接禁止开新仓**（规则自动执行，非人工提醒）
- **候选池（三池分离）**：正式池 32 只（宽基 / 行业 / 红利 / 国债·货币·可转债防御 / 黄金 / 纳指·标普·恒生·日经跨市场）；观察池 6 只（能源/钢铁/可转债/短债/豆粕/有色期货，只采集数据不选股，攒满真实样本外数据后凭表现转正）；淘汰池 3 只（H股/中概互联/恒生互联网，与现有标的高度重叠，不再采集）
- **调仓**：每月最后一个交易日收盘后出信号，下月第一个交易日开盘手动执行
- **成本**：佣金万 2.5（最低 5 元）、ETF 免印花税、滑点 0.1%；回测中持仓权重随价格在调仓间漂移，成本按漂移后权重计算

### 回测结果（2018-01 ~ 2026-09，前复权，无后见偏差口径）

| 指标 | 策略 | 沪深300 |
|---|---|---|
| 年化收益 | 8.0% | ~3.4% |
| 最大回撤 | -25.6% | -42% |
| 夏普 | 0.55 | - |
| 调仓 | 92 次/8.6 年，单边换手约 27%/期 | - |
| 全区间超额 | +64% | - |

逐年滚动验证（`scripts/walk_forward.py`，9 年中 7 年跑赢基准）：

| 年份 | 策略 | 基准 | 说明 |
|---|---|---|---|
| 2018 | 0.0% | -25.3% | 全负动量→空仓，躲过大熊 |
| 2019 | +6.2% | +40.5% | ❌ 反转年，普涨急拉追不上 |
| 2020 | +43.7% | +27.4% | 大年（科技+黄金+美股趋势） |
| 2021 | +8.6% | -4.9% | 基准跌它赚 |
| 2022 | -16.1% | -19.8% | 最痛：美联储加息、股商双杀无处躲 |
| 2023 | -4.3% | -10.0% | 阴跌年少亏 |
| 2024 | +10.4% | +19.0% | ❌ 反转年，9月暴力拉升踏空 |
| 2025 | +29.9% | +24.3% | 大年 |
| 2026 | -1.1% | -2.2% | 截至 9/4 |

策略特点：熊市抗跌（2018 空仓躲过 -25%）、利润集中在趋势大年（2020/2025），其余年份靠少亏积累；急速反转年（2019、2024）会明显跑输基准，股商双杀年（2022）会真实亏损——这是动量策略的结构性弱点，实测趋势过滤/牛市跟随/双动量等补丁均无增益。参数稳健性用 `scripts/sensitivity.py --oos-start 20230101` 检验；收益来源归因用 `scripts/attribution.py`。

**预期管理**：上表是当前最诚实的口径（无后见偏差：新资产只在观察池积累真实样本外数据，不参与回测；真分散：科技限 2、区域限 1）。历史版本曾出现过 13%/-17.6%/0.80 等更高数字，均已查实含水分（池内后见偏差、科技抱团、未计权重漂移），**规划请一律以年化 8%、回撤 -25% 为基准**；观察池标的未来转正后数字可能小幅变化，以 walk_forward 复核为准。

## 目录结构

```
config.py      配置加载（config.yaml + .env）
config/        config.yaml（含候选池三池定义与风控分组）、.env.example、portfolio_state.example.json
data/          数据层（tushare 封装、SQLite、ETF 池、数据同步、净值/份额溢价监测）
strategy/      动量计算、统一策略类 MomentumStrategy（含风控约束）、调仓调度
backtest/      回测引擎（权重漂移、开盘执行、成本模型）与绩效指标
signals/       信号生成、溢价监测、推送与报告渲染
scripts/       拉数据、回测、敏感性、滚动验证、归因、出信号
tests/         单元测试（23 个）
pyproject.toml 包声明（依赖唯一来源，pip install -e .[dev,plot]）
```

## 快速开始

```bash
pip install -r requirements.txt      # 以可编辑模式安装 freeseven 包（依赖声明在 pyproject.toml）
cp config/.env.example config/.env   # 填 TUSHARE_TOKEN
python scripts/fetch_data.py         # 全量拉取 ETF 日线到 SQLite
cp config/portfolio_state.example.json data/portfolio_state.json  # 填入真实持仓份额（可选，信号据此算精确买卖金额）
python scripts/run_backtest.py --chart out/equity.png   # 回测
python scripts/run_signal.py --capital 100000       # 出本月调仓信号
```

常用命令：

```bash
python scripts/fetch_data.py --incremental          # 增量更新（各标的按自己水位，含复权因子/净值/份额）
python scripts/run_signal.py --fetch --capital 100000  # 先更新数据再出信号（仅月末信号日会写档并推送）
python scripts/run_signal.py --force                # 非调仓日强制写档推送（慎用）
python scripts/sensitivity.py                       # 参数敏感性（window × top_n 网格，检验过拟合）
python scripts/sensitivity.py --oos-start 20230101  # 网格同时输出 IS/OOS，防调参变样本内挖矿
python scripts/walk_forward.py                      # 逐年滚动验证
python scripts/walk_forward.py --exclude CODES      # 剔除指定标的逐年对比（验证池子改动贡献）
python scripts/attribution.py                       # 收益来源归因（剔除法 + 限仓对照）
```

推送配置：在 `config/.env` 配置 `DINGTALK_WEBHOOK_URL` 与 `DINGTALK_SECRET`（钉钉群→群设置→智能群助手→自定义机器人），`config/config.yaml` 的 `notify.channel` 设为 `dingtalk`。也支持 Server酱（`SERVERCHAN_KEY`）/ PushPlus（`PUSHPLUS_TOKEN`）。

信号存档：每次**正式信号**（月末信号日且数据新鲜）会在 `data/signals/` 写入带日期的记录（如 `20260828.json`）并推送；**非调仓日运行只作预览，不写档、不推送**，避免误触发。正式记录纳入 git 版本管理——换电脑时 clone 即可带走全部历史信号，方便事后对照实际成交做复盘（`latest.json` 为快捷方式不入库）。

实际持仓对照：把券商 App 里的真实份额填入 `data/portfolio_state.json`（格式见 `config/portfolio_state.example.json`），信号会按实际仓位计算每只精确的买入/卖出金额，而不是拿上一份信号档案估算；该文件属个人数据，不入库。

## 注意事项

- **价格为前复权**：基于 tushare `fund_adj` 复权因子，修正分红除息对动量/收益的污染；升级后请先跑一次 `python scripts/fetch_data.py` 拉取复权因子
- **QDII 溢价风险**：跨市场 ETF 常因额度限制暂停申购，二级价格可能大幅高于净值；溢价 >5% 或拿不到净值的 QDII 会被风控规则自动禁止开新仓，但净值滞后 1~2 日，**下单前务必以交易软件实时 IOPV 为准，限价单不追高**
- **观察池转正纪律**：观察池标的（能源/钢铁/可转债/短债/豆粕/有色期货）只积累真实样本外数据，不参与回测与选股；至少观察 12 个月、用 `walk_forward.py --exclude` 验证增量贡献非负后方可转正，防止“事后知道它涨得好”的后见偏差
- 策略赚的是趋势/风格超额，震荡市会有连续小亏，利润集中在少数趋势大年，**不构成投资建议**
- 本工具只出信号，下单由你手动执行，请严格执行月度调仓纪律，月中不因新闻/波动临时动手

## 免责声明

本工具仅提供量化信号与统计研究，不构成投资建议。