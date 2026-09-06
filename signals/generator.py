"""信号生成：目标权重差异计算（选股统一入口在 strategy.core.MomentumStrategy）。"""
from __future__ import annotations


def diff_signal(
    prev: dict[str, float], new: dict[str, float]
) -> tuple[dict[str, float], dict[str, float]]:
    """返回 (需卖出, 需买入) 的权重变动。

    value 是需交易的目标组合权重，而非旧/新持仓的完整权重；同一标的
    发生加仓或减仓时也必须出现在清单中。
    """
    codes = set(prev) | set(new)
    sells = {
        c: prev.get(c, 0.0) - new.get(c, 0.0)
        for c in codes
        if prev.get(c, 0.0) > new.get(c, 0.0) + 1e-9
    }
    buys = {
        c: new.get(c, 0.0) - prev.get(c, 0.0)
        for c in codes
        if new.get(c, 0.0) > prev.get(c, 0.0) + 1e-9
    }
    return sells, buys
