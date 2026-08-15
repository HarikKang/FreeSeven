"""调仓日调度"""
from __future__ import annotations

import pandas as pd


def month_end_dates(dates: pd.Index) -> list[pd.Timestamp]:
    """每月最后一个交易日。"""
    s = pd.Series(dates)
    s.index = s
    grouped = s.groupby(s.dt.to_period("M")).max()
    return [pd.Timestamp(x) for x in grouped.values]


def next_execution_dates(
    dates: pd.Index, rebalance_dates: list[pd.Timestamp]
) -> dict[pd.Timestamp, pd.Timestamp]:
    """每个调仓日 -> 下一个交易日（执行日）。"""
    out = {}
    idx = {d: i for i, d in enumerate(dates)}
    for r in rebalance_dates:
        i = idx[r]
        if i + 1 < len(dates):
            out[r] = dates[i + 1]
    return out


def is_signal_day(
    asof: pd.Timestamp, dates: pd.Index
) -> bool:
    """asof 是否为月度调仓日（当月最后一个交易日）。"""
    return asof in month_end_dates(dates)