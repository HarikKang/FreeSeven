"""参数敏感性分析：window × top_n 网格回测，检验当前参数是"平台"还是"孤峰"。

若最优参数附近（±1 档）结果差异巨大，说明过拟合风险高；若成片稳定，则参数稳健。

用法:
    python scripts/sensitivity.py
    python scripts/sensitivity.py --windows 180,200,250,300 --top-ns 5,6,8,10
    python scripts/sensitivity.py --sweep-max-momentum   # 过热阈值敏感性
    python scripts/sensitivity.py --oos-start 20230101   # 网格同时输出 IS/OOS，防调参变样本内挖矿
    python scripts/sensitivity.py --start 20200101
"""
import argparse

from backtest.engine import backtest_momentum
from backtest.metrics import cagr, max_drawdown, sharpe
from config import load_config
from data import Storage
from strategy.core import MomentumStrategy
from strategy.schedule import month_end_dates


def run_one(closes, opens, rb, costs, strategy: MomentumStrategy, regime_code):
    result = backtest_momentum(
        closes=closes, opens=opens, strategy=strategy, costs=costs,
        rebalance_dates=rb, regime_code=regime_code,
    )
    equity, daily = result["equity"], result["daily_returns"]
    return {
        "年化%": cagr(equity) * 100,
        "回撤%": max_drawdown(equity) * 100,
        "夏普": sharpe(daily),
        "调仓": len(result["trades"]),
        "equity": equity,
    }


def main():
    parser = argparse.ArgumentParser(description="动量参数敏感性分析")
    parser.add_argument("--windows", default="200,250,300", help="动量窗口列表，逗号分隔")
    parser.add_argument("--top-ns", default="5,8,10", help="持有数量列表，逗号分隔")
    parser.add_argument("--sweep-max-momentum", action="store_true",
                        help="改为扫过热阈值（0.6/0.8/1.0/关闭），固定 config 的 window/top_n")
    parser.add_argument("--start", default="", help="回测起点 YYYYMMDD")
    parser.add_argument("--oos-start", default="", dest="oos_start",
                        help="样本外起点 YYYYMMDD，网格同时输出 IS/OOS 指标")
    args = parser.parse_args()

    cfg = load_config()
    strat, costs = cfg["strategy"], cfg["costs"]
    regime_code = strat.get("regime_code") or None
    cross_codes = cfg.get("cross_market", [])

    storage = Storage()
    closes, opens = storage.load_matrices()
    if args.start:
        import pandas as pd

        closes = closes.loc[closes.index >= pd.to_datetime(args.start, format="%Y%m%d")]
        opens = opens.reindex(closes.index)
    rb = month_end_dates(closes.index)

    rows = []
    if args.sweep_max_momentum:
        print(f"过热阈值敏感性（window={strat['momentum_window']}, top_n={strat['top_n']}）")
        for mm in [0.6, 0.8, 1.0, None]:
            s = MomentumStrategy(
                window=strat["momentum_window"], lag=strat.get("momentum_lag", 0),
                top_n=strat["top_n"], require_positive=strat["require_positive"],
                max_momentum=mm,
                max_cross=strat.get("max_cross"), cross_codes=cross_codes,
            )
            m = run_one(closes, opens, rb, costs, s, regime_code)
            rows.append((f"max_momentum={mm if mm is not None else '关闭'}", m))
    else:
        windows = [int(x) for x in args.windows.split(",")]
        top_ns = [int(x) for x in args.top_ns.split(",")]
        print(f"window × top_n 网格（require_positive={strat['require_positive']}, "
              f"max_momentum={strat.get('max_momentum')}）")
        for w in windows:
            for n in top_ns:
                s = MomentumStrategy(
                    window=w, lag=strat.get("momentum_lag", 0), top_n=n,
                    require_positive=strat["require_positive"],
                    max_momentum=strat.get("max_momentum"),
                    max_cross=strat.get("max_cross"), cross_codes=cross_codes,
                )
                m = run_one(closes, opens, rb, costs, s, regime_code)
                rows.append((f"window={w}, top_n={n}", m))

    if args.oos_start:
        import pandas as pd

        oos_dt = pd.to_datetime(args.oos_start, format="%Y%m%d")
        print("-" * 78)
        print(f"{'参数':<26} {'IS年化%':>8} {'OOS年化%':>9} {'OOS夏普':>8} {'OOS回撤%':>9}")
        print("-" * 78)
        for label, m in rows:
            eq = m["equity"]
            is_eq, oos_eq = eq.loc[eq.index < oos_dt], eq.loc[eq.index >= oos_dt]
            if len(is_eq) < 21 or len(oos_eq) < 21:
                print(f"{label:<26} {'样本不足':>8}")
                continue
            is_ann = cagr(is_eq) * 100
            oos_ann = cagr(oos_eq) * 100
            oos_sh = sharpe(oos_eq.pct_change().dropna())
            oos_dd = max_drawdown(oos_eq) * 100
            print(f"{label:<26} {is_ann:>8.1f} {oos_ann:>9.1f} {oos_sh:>8.2f} {oos_dd:>9.1f}")
        print("-" * 78)
        print("解读：OOS 相对 IS 普遍不崩才可信；若只有个别参数 OOS 好看，那是又一次挖矿。")
        return

    print("-" * 58)
    print(f"{'参数':<26} {'年化%':>8} {'回撤%':>8} {'夏普':>6} {'调仓':>5}")
    print("-" * 58)
    for label, m in rows:
        print(f"{label:<26} {m['年化%']:>8.1f} {m['回撤%']:>8.1f} {m['夏普']:>6.2f} {m['调仓']:>5}")
    print("-" * 58)
    print("解读：若当前 config 参数附近网格结果差异 >5% 年化，警惕过拟合（孤峰）。")


if __name__ == "__main__":
    main()
