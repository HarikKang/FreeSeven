"""信号生成：目标权重差异计算（选股统一入口在 strategy.core.MomentumStrategy）。"""
from __future__ import annotations


def diff_signal(
    prev: dict[str, float], new: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    """返回 (需卖出, 需买入) 的权重差。"""
    sells = {c: w for c, w in prev.items() if c not in new}
    buys = {c: w for c, w in new.items() if c not in prev}
    return sells, buys