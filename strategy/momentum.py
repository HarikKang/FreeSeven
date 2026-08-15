"""动量信号计算"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_momentum(
    closes: pd.DataFrame, window: int = 20, lag: int = 0
) -> pd.DataFrame:
    """滚动动量：close[t-lag] / close[t-window-lag] - 1。

    - window：动量回看窗口（交易日）
    - lag：回看起点跳过最近 lag 天（双动量 12-1 用 lag≈21 规避短期反转）
    NaN 表示数据不足或未上市。
    """
    end = closes.shift(lag)
    start = closes.shift(window + lag)
    return end / start - 1.0