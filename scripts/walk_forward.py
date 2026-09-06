"""滚动验证（walk-forward）：按年度切片报告策略的样本外表现。

策略参数固定（不随窗口重拟合），因此本脚本的价值是：
1. 逐年展示策略在"未来年份"的真实表现，暴露对特定市场风格的依赖；
2. 通过 --exclude 对比剔除某些标的后的逐年差异，专门用于验证
   "新增候选池"这类改动的贡献是否稳定，而非只在某一年偷分。

用法:
    python scripts/walk_forward.py
    python scripts/walk_forward.py --exclude 159985.SZ,159980.SZ,515210.SH,511360.SH,159930.SZ,511380.SH
"""
import argparse

import pandas as pd

from backtest.engine import backtest_momentum
from backtest.metrics import cagr, max_drawdown, sharpe
from config import load_config
from data import Storage, active_codes
from strategy.core import MomentumStrategy
from strategy.schedule import month_end_dates

BENCH = "510300.SH"


def run_backtest(closes, opens, cfg):
    strat, costs = cfg["strategy"], cfg["costs"]
    s = MomentumStrategy.from_config(strat, cross_codes=cfg.get("cross_market", []),
                                     risk=cfg.get("risk"), active_from=cfg.get("candidate_activation"),
                                     eligible_codes=active_codes())
    rb = month_end_dates(closes.index)
    return backtest_momentum(
        closes=closes, opens=opens, strategy=s, costs=costs,
        rebalance_dates=rb, regime_code=strat.get("regime_code") or None,
    )


def yearly(equity: pd.Series) -> pd.Series:
    return equity.groupby(equity.index.year).agg(lambda s: s.iloc[-1] / s.iloc[0] - 1)


def main():
    parser = argparse.ArgumentParser(description="逐年滚动验证")
    parser.add_argument("--exclude", default="",
                        help="逗号分隔的 ts_code 列表，剔除后对比（验证池子改动的贡献）")
    args = parser.parse_args()

    cfg = load_config()
    storage = Storage()
    closes, opens = storage.load_matrices()

    res = run_backtest(closes, opens, cfg)
    strat_ret = yearly(res["equity"])
    bench_ret = yearly(closes[BENCH].dropna())

    rows_ex = None
    if args.exclude:
        drop = [c.strip() for c in args.exclude.split(",") if c.strip()]
        missing = [c for c in drop if c not in closes.columns]
        if missing:
            print(f"[警告] 以下代码不在池内，忽略: {missing}")
            drop = [c for c in drop if c in closes.columns]
        res_ex = run_backtest(closes.drop(columns=drop),
                              opens.drop(columns=drop), cfg)
        rows_ex = yearly(res_ex["equity"])
        print(f"对照：剔除 {len(drop)} 只（{', '.join(drop)}）\n")

    print(f"{'年份':<6} {'策略':>8} {'基准':>8} {'超额':>8}", end="")
    if rows_ex is not None:
        print(f" {'剔除后':>8} {'新增贡献':>9}")
    else:
        print()
    print("-" * 70)
    for y in strat_ret.index:
        line = f"{y:<6} {strat_ret[y]*100:>+7.1f}% {bench_ret.get(y, float('nan'))*100:>+7.1f}% " \
               f"{(strat_ret[y]-bench_ret.get(y, 0))*100:>+7.1f}%"
        if rows_ex is not None and y in rows_ex.index:
            line += f" {rows_ex[y]*100:>+7.1f}% {(strat_ret[y]-rows_ex[y])*100:>+8.1f}%"
        print(line)

    eq, daily = res["equity"], res["daily_returns"]
    print("-" * 70)
    print(f"全区间: 年化 {cagr(eq)*100:.1f}% | 回撤 {max_drawdown(eq)*100:.1f}% | "
          f"夏普 {sharpe(daily):.2f} | 跑输基准的年份: "
          f"{sum(strat_ret[y] < bench_ret.get(y, 0) for y in strat_ret.index)}/{len(strat_ret)}")
    if rows_ex is not None:
        worst = (strat_ret - rows_ex).min() * 100
        best = (strat_ret - rows_ex).max() * 100
        print(f"新增标的逐年贡献区间: {worst:+.1f}% ~ {best:+.1f}%"
              f"（若贡献集中在单一年份，说明是运气不是分散）")


if __name__ == "__main__":
    main()
