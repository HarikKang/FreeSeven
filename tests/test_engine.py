"""回测引擎单测：合成数据验证收益、成本、停牌 NaN 防护与信号一致性。"""
import numpy as np
import pandas as pd

from backtest.engine import backtest_momentum
from strategy.core import MomentumStrategy

ZERO_COSTS = {"commission_rate": 0.0, "min_commission": 0.0, "slippage": 0.0, "stamp_duty": 0.0}


def make_market(periods: int = 20) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """A 单边上涨、B 单边下跌的合成市场；open=close（无隔夜跳空）。"""
    dates = pd.bdate_range("2024-01-01", periods=periods)
    closes = pd.DataFrame(
        {"A": 100.0 + np.arange(periods), "B": 100.0 - np.arange(periods) * 0.5},
        index=dates,
    )
    opens = closes.copy()
    return closes, opens, list(dates)


def test_engine_buys_positive_momentum():
    closes, opens, dates = make_market()
    strategy = MomentumStrategy(window=5, top_n=1, require_positive=True)
    result = backtest_momentum(
        closes, opens, strategy, ZERO_COSTS, rebalance_dates=[dates[6]]
    )
    # 调仓日信号：A 正动量入选、B 负动量剔除
    assert result["trades"][0]["weights"] == {"A": 1.0}
    assert result["trades"][0]["signal_date"] == dates[6]
    # 持有上涨的 A，净值应增长且无 NaN
    assert result["equity"].notna().all()
    assert result["equity"].iloc[-1] > 1.0


def test_engine_all_negative_momentum_stays_cash():
    dates = pd.bdate_range("2024-01-01", periods=20)
    closes = pd.DataFrame(
        {"A": 100.0 - np.arange(20), "B": 90.0 - np.arange(20) * 0.5}, index=dates
    )
    strategy = MomentumStrategy(window=5, top_n=1, require_positive=True)
    result = backtest_momentum(
        closes, closes.copy(), strategy, ZERO_COSTS, rebalance_dates=[dates[6]]
    )
    # 全负动量 -> 空仓，无交易，净值恒为 1
    assert result["equity"].iloc[-1] == 1.0
    assert result["trades"] == []


def test_engine_suspension_nan_does_not_pollute():
    """持仓标的停牌（价格 NaN）时，当日按 0 收益近似，不得污染整条净值。"""
    closes, opens, dates = make_market()
    closes.iloc[10, closes.columns.get_loc("A")] = np.nan  # 持有期内 A 停牌一天
    strategy = MomentumStrategy(window=5, top_n=1, require_positive=True)
    result = backtest_momentum(
        closes, opens, strategy, ZERO_COSTS, rebalance_dates=[dates[6]]
    )
    assert result["daily_returns"].notna().all()
    assert result["equity"].notna().all()
    # 停牌当日无有效价格，收益为 0
    assert result["daily_returns"][dates[10]] == 0.0


def test_engine_cost_applied():
    closes, opens, dates = make_market()
    costs = {"commission_rate": 0.0, "min_commission": 100.0, "slippage": 0.001, "stamp_duty": 0.0}
    strategy = MomentumStrategy(window=5, top_n=1, require_positive=True)
    result = backtest_momentum(closes, opens, strategy, costs, rebalance_dates=[dates[6]])
    # 建仓 100% 仓位：成本 = 最低佣金 100 元 + 0.1% 滑点（占 10 万权益）
    expected = (100.0 + 100000.0 * 0.001) / 100000.0
    assert abs(result["trades"][0]["cost"] - expected) < 1e-9


def test_signal_matches_backtest_selection():
    """实盘信号与回测选股同源：strategy.signal 与 strategy.select 结果一致。"""
    closes, _, dates = make_market(periods=30)
    strategy = MomentumStrategy(window=5, lag=1, top_n=2, require_positive=True, max_momentum=0.5)
    mom = strategy.momentum(closes)
    via_select = strategy.select(mom.loc[dates[-1]])
    via_signal = strategy.signal(closes, asof=dates[-1])
    assert via_signal == via_select


def test_from_config_reads_lag_and_max_momentum():
    strat = {
        "momentum_window": 5, "momentum_lag": 1, "top_n": 2,
        "require_positive": True, "max_momentum": 0.5,
    }
    s = MomentumStrategy.from_config(strat)
    assert (s.window, s.lag, s.top_n, s.max_momentum) == (5, 1, 2, 0.5)
