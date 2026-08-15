"""信号生成"""
from __future__ import annotations

import pandas as pd

from strategy.core import MomentumStrategy


def generate_signal(
    closes: pd.DataFrame,
    window: int,
    top_n: int,
    require_positive: bool,
    max_momentum: float | None = None,
    asof: pd.Timestamp | None = None,
    lag: int = 0,
) -> dict[str, float]:
    """基于截至 asof 的数据生成目标权重（兼容入口，优先用 MomentumStrategy）。"""
    strategy = MomentumStrategy(
        window=window, lag=lag, top_n=top_n,
        require_positive=require_positive, max_momentum=max_momentum,
    )
    return strategy.signal(closes, asof=asof)


def diff_signal(
    prev: dict[str, float], new: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    """返回 (需卖出, 需买入) 的权重差。"""
    sells = {c: w for c, w in prev.items() if c not in new}
    buys = {c: w for c, w in new.items() if c not in prev}
    return sells, buys