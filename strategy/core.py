"""统一策略定义：回测与实盘信号共用同一入口，保证参数一致。"""
from __future__ import annotations

import pandas as pd

from strategy.momentum import compute_momentum


class MomentumStrategy:
    """动量轮动策略：参数集中于此，回测引擎与信号生成均通过它计算。"""

    def __init__(
        self,
        window: int = 250,
        lag: int = 0,
        top_n: int = 8,
        require_positive: bool = True,
        max_momentum: float | None = None,
        max_cross: int | None = None,
        cross_codes: list[str] | None = None,
    ):
        self.window = window
        self.lag = lag
        self.top_n = top_n
        self.require_positive = require_positive
        self.max_momentum = max_momentum
        self.max_cross = max_cross
        self.cross_codes = set(cross_codes or [])

    @classmethod
    def from_config(
        cls, strat: dict, cross_codes: list[str] | None = None
    ) -> "MomentumStrategy":
        return cls(
            window=strat["momentum_window"],
            lag=strat.get("momentum_lag", 0),
            top_n=strat["top_n"],
            require_positive=strat.get("require_positive", True),
            max_momentum=strat.get("max_momentum"),
            max_cross=strat.get("max_cross"),
            cross_codes=cross_codes,
        )

    def momentum(self, closes: pd.DataFrame) -> pd.DataFrame:
        """滚动动量矩阵（index=交易日, columns=ts_code）。"""
        return compute_momentum(closes, self.window, lag=self.lag)

    def select(self, mom_row: pd.Series) -> dict[str, float]:
        """给定某一天的动量截面，返回目标权重 dict。

        设置了 max_cross 时，跨市场资产（cross_codes）最多入选 max_cross 只，
        其余名额由动量次优标的补足（限 QDII 溢价/单一市场集中风险）。
        """
        m = mom_row.dropna()
        if self.require_positive:
            m = m[m > 0]
        if self.max_momentum is not None:
            m = m[m <= self.max_momentum]
        if m.empty:
            return {}
        cap = self.max_cross if self.max_cross is not None else len(m)
        chosen: list[str] = []
        for code in m.sort_values(ascending=False).index:
            if len(chosen) >= self.top_n:
                break
            if (
                code in self.cross_codes
                and sum(c in self.cross_codes for c in chosen) >= cap
            ):
                continue
            chosen.append(code)
        if not chosen:
            return {}
        weight = 1.0 / len(chosen)
        return {c: weight for c in chosen}

    def signal(
        self, closes: pd.DataFrame, asof: pd.Timestamp | None = None
    ) -> dict[str, float]:
        """基于截至 asof 的数据生成目标权重（实盘信号入口）。"""
        closes = closes.sort_index()
        if asof is not None:
            closes = closes.loc[:asof]
        return self.select(self.momentum(closes).iloc[-1])
