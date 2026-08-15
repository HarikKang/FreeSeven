"""持仓分配：基于动量排名生成目标权重"""
from __future__ import annotations

import numpy as np
import pandas as pd


def target_weights(
    momentum: pd.Series,
    top_n: int,
    require_positive: bool = True,
) -> dict[str, float]:
    """给定某一天的动量（Series: ts_code -> 动量值），返回目标权重 dict。

    - require_positive=True：只保留动量 > 0 的，否则空仓（全现金）
    - 取动量最高的 top_n 只，等权
    """
    m = momentum.dropna()
    if require_positive:
        m = m[m > 0]
    if m.empty:
        return {}
    m = m.sort_values(ascending=False).head(top_n)
    weight = 1.0 / len(m)
    return {code: weight for code in m.index}


def weights_to_series(weights: dict[str, float], codes: list[str]) -> pd.Series:
    s = pd.Series(0.0, index=codes)
    for code, w in weights.items():
        s[code] = w
    return s