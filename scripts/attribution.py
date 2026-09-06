"""收益来源归因回测：检验策略对黄金/美股/跨市场资产的依赖程度。

方法：
1. 剔除法 —— 从候选池移除目标资产后重跑回测，年化差值即其贡献
2. 仓位上限 —— 保留候选池但限制跨市场资产最多入选 K 只，检验"限仓是否值得"

用法:
    python scripts/attribution.py
    python scripts/attribution.py --start 20200101
"""
import argparse

import pandas as pd

from backtest.engine import backtest_momentum
from backtest.metrics import cagr, max_drawdown, sharpe
from config import load_config
from data import Storage
from strategy.core import MomentumStrategy
from strategy.schedule import month_end_dates

# 资产分类：跨市场列表优先读 config，缺省回退内置
GOLD = ["518880.SH"]
US = ["513100.SH", "513500.SH"]  # 纳指100、标普500
_DEFAULT_CROSS = [
    "513100.SH", "513500.SH",     # 纳指、标普
    "159920.SZ", "513180.SH", "510900.SH",  # 恒生、恒生科技、H股
    "513050.SH", "513330.SH",     # 中概互联、恒生互联网
    "513000.SH",                   # 日经225
]


def run(closes, opens, rb, costs, strategy, regime_code):
    res = backtest_momentum(
        closes=closes, opens=opens, strategy=strategy, costs=costs,
        rebalance_dates=rb, regime_code=regime_code,
    )
    eq, daily = res["equity"], res["daily_returns"]
    return cagr(eq) * 100, max_drawdown(eq) * 100, sharpe(daily)


def main():
    parser = argparse.ArgumentParser(description="收益来源归因回测")
    parser.add_argument("--start", default="", help="回测起点 YYYYMMDD")
    args = parser.parse_args()

    cfg = load_config()
    strat, costs = cfg["strategy"], cfg["costs"]
    regime_code = strat.get("regime_code") or None
    cross_all = cfg.get("cross_market") or _DEFAULT_CROSS

    storage = Storage()
    closes, opens = storage.load_matrices()
    if args.start:
        closes = closes.loc[closes.index >= pd.to_datetime(args.start, format="%Y%m%d")]
        opens = opens.reindex(closes.index)
    rb = month_end_dates(closes.index)

    base = MomentumStrategy.from_config(strat, cross_codes=cross_all, risk=cfg.get("risk"),
                                        active_from=cfg.get("candidate_activation"))

    # —— 第一组：剔除法 ——
    drop_variants = [
        ("基准（当前 config）", base, []),
        ("剔除黄金", base, GOLD),
        ("剔除美股（纳指+标普）", base, US),
        ("剔除黄金+美股", base, GOLD + US),
        ("剔除全部跨市场", base, cross_all),
    ]
    print("=" * 62)
    print("第一组：剔除法（移除资产后重跑，年化差 = 该资产贡献）")
    print("=" * 62)
    rows = []
    for label, s, drop in drop_variants:
        c = closes.drop(columns=[x for x in drop if x in closes.columns])
        o = opens.reindex(columns=c.columns)
        a, d, sh = run(c, o, rb, costs, s, regime_code)
        rows.append((label, a, d, sh))
    base_ann = rows[0][1]
    for label, a, d, sh in rows:
        delta = a - base_ann
        print(f"{label:<22} 年化 {a:>6.1f}% (Δ{delta:+5.1f})  回撤 {d:>6.1f}%  夏普 {sh:.2f}")

    # —— 第二组：跨市场仓位上限 ——
    print()
    print("=" * 62)
    print("第二组：跨市场仓位上限（保留全池，限制跨市场入选数量）")
    print("=" * 62)
    cap_rows = [("不限", MomentumStrategy.from_config({**strat, "max_cross": None}, cross_codes=cross_all))] + [
        (f"跨市场最多 {k} 只",
         MomentumStrategy.from_config({**strat, "max_cross": k}, cross_codes=cross_all))
        for k in (2, 3, 4)
    ]
    for label, s in cap_rows:
        a, d, sh = run(closes, opens, rb, costs, s, regime_code)
        delta = a - base_ann
        print(f"{label:<22} 年化 {a:>6.1f}% (Δ{delta:+5.1f})  回撤 {d:>6.1f}%  夏普 {sh:.2f}")

    print()
    print("解读：")
    print("- 剔除后年化掉得越多，说明策略对该资产依赖越重（收益来源集中）")
    print("- 若限仓后回撤显著下降而年化损失有限，则值得在实盘中采用上限约束")


if __name__ == "__main__":
    main()
