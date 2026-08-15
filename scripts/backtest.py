"""跑动量轮动回测并输出报告。

用法:
    python scripts/backtest.py
    python scripts/backtest.py --start 20200101
    python scripts/backtest.py --chart out/equity.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import backtest_momentum, benchmark_equity
from backtest.metrics import metrics, max_drawdown
from config import load_config
from data import Storage, ts_codes
from strategy.core import MomentumStrategy
from strategy.schedule import month_end_dates


def win_rate(daily_returns: pd.Series) -> float:
    weekly = daily_returns.resample("W-FRI").sum().dropna()
    return float((weekly > 0).mean())


def turnover_avg(trades: list[dict]) -> float:
    """平均每期单边换手率（按权重变动一半计算）。"""
    vals = []
    for t in trades:
        old_w = {c: 0.0 for c in t.get("sells", {})}
        new_w = {c: 0.0 for c in t.get("buys", {})}
        codes = set(old_w) | set(new_w) | set(t["weights"])
        one_way = sum(abs(t["weights"].get(c, 0) - (t.get("old_weights", {}).get(c, 0))) for c in codes) / 2
        vals.append(one_way)
    return float(sum(vals) / len(vals)) if vals else 0.0


def fridays_of(index: pd.DatetimeIndex, weekday: int) -> list:
    return [d for d in index if d.weekday() == weekday]


def main():
    parser = argparse.ArgumentParser(description="ETF 动量轮动回测")
    parser.add_argument("--start", default="", help="回测起点 YYYYMMDD")
    parser.add_argument("--chart", default="", help="保存净值图路径（需 matplotlib）")
    args = parser.parse_args()

    cfg = load_config()
    strat = cfg["strategy"]
    costs = cfg["costs"]
    bench = cfg["universe"][0]["ts_code"]  # 沪深300 作基准

    storage = Storage()
    closes, opens = storage.load_matrices()  # 前复权价格
    if args.start:
        closes = closes.loc[closes.index >= pd.to_datetime(args.start, format="%Y%m%d")]
        opens = opens.reindex(closes.index)

    interval = strat.get("rebalance_interval_weeks", 1)
    rb = fridays_of(closes.index, strat["rebalance_weekday"])[::interval]
    if strat.get("rebalance_schedule") == "month_end":
        rb = month_end_dates(closes.index)

    strategy = MomentumStrategy.from_config(strat, cross_codes=cfg.get("cross_market", []))
    result = backtest_momentum(
        closes=closes,
        opens=opens,
        strategy=strategy,
        costs=costs,
        rebalance_dates=rb,
        regime_code=strat.get("regime_code") or None,
    )
    equity, daily, trades = result["equity"], result["daily_returns"], result["trades"]

    print("=" * 60)
    print("ETF 动量轮动回测报告")
    print(f"  参数: 动量{strat['momentum_window']}日 | Top{strat['top_n']} | 需为正动量"
          f"{'是' if strat['require_positive'] else '否'} | 每{interval}周调仓")
    print(f"  区间: {equity.index[0].date()} ~ {equity.index[-1].date()}")
    print("-" * 60)

    m = metrics(equity, daily)
    for k, v in m.items():
        unit = "%" if "收益" in k or "波动" in k or "回撤" in k else ""
        print(f"  {k}: {v:.2f}{unit}" if isinstance(v, float) else f"  {k}: {v}")
    print(f"  周度胜率: {win_rate(daily) * 100:.1f}%")
    print(f"  平均单边换手: {turnover_avg(trades) * 100:.1f}%/期")
    print(f"  调仓次数: {len(trades)}")

    # 基准对比
    bench_eq = benchmark_equity(closes, bench).reindex(equity.index).ffill()
    bench_ret = (bench_eq.iloc[-1] / bench_eq.iloc[0] - 1) * 100
    bench_dd = max_drawdown(bench_eq) * 100
    strat_ret = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
    print("-" * 60)
    print(f"  基准 {bench}: 区间收益 {bench_ret:.1f}% | 最大回撤 {bench_dd:.1f}%")
    print(f"  策略 vs 基准超额: {strat_ret - bench_ret:.1f}%")

    if args.chart:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 5))
            eq_n = equity / equity.iloc[0]
            ax.plot(eq_n.index, eq_n.values, label="策略", lw=1.5)
            ax.plot(bench_eq.index, bench_eq.values, label=f"基准 {bench}", lw=1.2, alpha=0.8)
            ax.set_ylabel("净值")
            ax.legend()
            ax.grid(alpha=0.3)
            out = Path(args.chart)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.tight_layout()
            fig.savefig(out, dpi=120)
            print(f"  净值图已保存: {out}")
        except ImportError:
            print("  (未安装 matplotlib，跳过图表)")

    print("=" * 60)


if __name__ == "__main__":
    main()