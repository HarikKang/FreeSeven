"""向量化回测引擎：ETF 动量轮动

信号：调仓日收盘动量 -> 目标权重（经 MomentumStrategy，与实盘信号同源）
执行：下一个交易日开盘价进出
持有：期间不做日内再平衡，权重自然漂移；停牌/缺数据的持仓当日按 0 收益近似
成本：佣金(含最低5元) + 滑点 + 印花税(ETF 为 0)
"""
from __future__ import annotations

import pandas as pd

from strategy.core import MomentumStrategy


def _valid(price) -> bool:
    """价格有效：非 NaN 且为正。停牌/缺数据返回 False。"""
    return pd.notna(price) and price > 0


def _cost_fraction(
    old_weights: dict[str, float],
    new_weights: dict[str, float],
    costs: dict,
    equity: float,
) -> float:
    """返回成本占当前权益的比例。old -> new 的调仓成本。"""
    codes = set(old_weights) | set(new_weights)
    commission = 0.0
    buy_amt = 0.0
    sell_amt = 0.0
    for c in codes:
        diff = new_weights.get(c, 0.0) - old_weights.get(c, 0.0)
        if abs(diff) < 1e-9:
            continue
        traded = abs(diff) * equity
        commission += max(traded * costs["commission_rate"], costs["min_commission"])
        if diff > 0:
            buy_amt += traded
        else:
            sell_amt += traded
    slippage = (buy_amt + sell_amt) * costs["slippage"]
    stamp = sell_amt * costs["stamp_duty"]
    return (commission + slippage + stamp) / equity if equity > 0 else 0.0


def backtest_momentum(
    closes: pd.DataFrame,
    opens: pd.DataFrame,
    strategy: MomentumStrategy,
    costs: dict,
    rebalance_weekday: int = 4,
    rebalance_dates: list | None = None,
    capital: float = 100000.0,
    regime_code: str | None = None,
) -> dict:
    """返回 equity、daily_returns、trades 等结果。

    - strategy：动量与选股参数的唯一来源（回测/实盘共用）
    - regime_code：大盘趋势过滤标的（需在 closes 中），其动量转负则整体空仓；None 关闭
    """
    closes = closes.sort_index()
    opens = opens.reindex(closes.index)

    mom = strategy.momentum(closes)
    dates = list(closes.index)

    # 调仓日：每周 rebalance_weekday 的交易日；执行日为其下一个交易日
    if rebalance_dates is None:
        rebalance_dates = [d for d in dates if d.weekday() == rebalance_weekday]
    idx_map = {pd.Timestamp(d): i for i, d in enumerate(dates)}
    signal_by_exec: dict = {}  # exec_date -> signal_date
    for r in rebalance_dates:
        idx = idx_map[pd.Timestamp(r)]
        if idx + 1 < len(dates):
            signal_by_exec[dates[idx + 1]] = pd.Timestamp(r)

    equity = capital
    active: dict[str, float] = {}
    daily_returns: dict[str, float] = {}
    trades: list[dict] = []
    prev_close: pd.Series | None = None

    for d in dates:
        if d in signal_by_exec:
            signal_date = signal_by_exec[d]
            # 卖出部分：从昨收到今开（停牌标的无有效开盘价，当日不计收益）
            ret_old = 0.0
            if prev_close is not None and active:
                ret_old = sum(
                    w * (opens.loc[d][c] / prev_close[c] - 1.0)
                    for c, w in active.items()
                    if c in prev_close and _valid(prev_close[c]) and _valid(opens.loc[d][c])
                )
            # 决定新目标权重（用调仓日收盘的动量）
            new_active = strategy.select(mom.loc[signal_date])
            # 大盘趋势过滤：regime 动量转负 -> 整体空仓
            if regime_code is not None:
                regime_mom = mom.loc[signal_date].get(regime_code)
                if regime_mom is not None and regime_mom < 0:
                    new_active = {}
            cost = _cost_fraction(active, new_active, costs, equity)
            # 买入部分：从今开到今收
            ret_new = sum(
                w * (closes.loc[d][c] / opens.loc[d][c] - 1.0)
                for c, w in new_active.items()
                if _valid(opens.loc[d][c]) and _valid(closes.loc[d][c])
            )
            daily_returns[d] = (1.0 + ret_old) * (1.0 - cost) * (1.0 + ret_new) - 1.0
            equity *= 1.0 + daily_returns[d]

            buys = {c: w for c, w in new_active.items() if new_active.get(c, 0) > active.get(c, 0) + 1e-9}
            sells = {c: w for c, w in active.items() if new_active.get(c, 0) < active.get(c, 0) - 1e-9}
            if buys or sells or cost > 0:
                trades.append(
                    {
                        "date": d,
                        "signal_date": signal_date,
                        "buys": buys,
                        "sells": sells,
                        "weights": dict(new_active),
                        "old_weights": dict(active),
                        "cost": cost,
                    }
                )
            active = new_active
        else:
            if active and prev_close is not None:
                r = sum(
                    w * (closes.loc[d][c] / prev_close[c] - 1.0)
                    for c, w in active.items()
                    if c in prev_close and _valid(prev_close[c]) and _valid(closes.loc[d][c])
                )
                daily_returns[d] = r
            else:
                daily_returns[d] = 0.0
            equity *= 1.0 + daily_returns[d]
        prev_close = closes.loc[d]

    return {
        "equity": (1.0 + pd.Series(daily_returns, name="ret")).cumprod().rename("equity"),
        "daily_returns": pd.Series(daily_returns, name="ret"),
        "trades": trades,
    }


def benchmark_equity(closes: pd.DataFrame, bench_code: str) -> pd.Series:
    s = closes[bench_code].dropna()
    return (s / s.iloc[0]).rename("benchmark")
