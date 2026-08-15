"""绩效指标计算"""
from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    return float((equity / running_max - 1.0).min())


def total_return(equity: pd.Series) -> float:
    if equity.empty or equity.iloc[0] <= 0:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1.0)


def cagr(equity: pd.Series) -> float:
    if equity.empty or equity.iloc[0] <= 0:
        return 0.0
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0)


def sharpe(daily_returns: pd.Series, rf: float = 0.0) -> float:
    if daily_returns.empty:
        return 0.0
    excess = daily_returns - rf / 252
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(excess.mean() / std * np.sqrt(252))


def annual_vol(daily_returns: pd.Series) -> float:
    if daily_returns.empty:
        return 0.0
    return float(daily_returns.std(ddof=1) * np.sqrt(252))


def metrics(
    equity: pd.Series, daily_returns: pd.Series, rf: float = 0.0
) -> dict:
    return {
        "总收益": total_return(equity) * 100,
        "年化收益": cagr(equity) * 100,
        "年化波动": annual_vol(daily_returns) * 100,
        "夏普": sharpe(daily_returns, rf),
        "最大回撤": max_drawdown(equity) * 100,
        "交易日数": int(len(daily_returns)),
    }