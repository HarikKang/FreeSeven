"""信号生成"""
from __future__ import annotations

import pandas as pd

from strategy.allocator import target_weights
from strategy.momentum import compute_momentum


def generate_signal(
    closes: pd.DataFrame,
    window: int,
    top_n: int,
    require_positive: bool,
    max_momentum: float | None = None,
    asof: pd.Timestamp | None = None,
) -> dict[str, float]:
    """基于截至 asof 的数据生成目标权重。"""
    closes = closes.sort_index().loc[:asof]
    mom = compute_momentum(closes, window).iloc[-1]
    return target_weights(mom, top_n, require_positive, max_momentum=max_momentum)


def diff_signal(
    prev: dict[str, float], new: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    """返回 (需卖出, 需买入) 的权重差。"""
    sells = {c: w for c, w in prev.items() if c not in new}
    buys = {c: w for c, w in new.items() if c not in prev}
    return sells, buys