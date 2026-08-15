"""QDII 溢价率计算：收盘价相对单位净值的偏离。

QDII ETF 受外汇额度限制常暂停一级申购，二级价格可能显著高于净值（IOPV），
高溢价买入后溢价回落会造成独立于标的本身的亏损。净值通常滞后 1~2 个交易日，
溢价率为近似值，实盘下单前仍应以交易软件的实时 IOPV 为准。
"""
from __future__ import annotations

import pandas as pd

WARN_THRESHOLD = 0.03   # >3% 提醒留意
HIGH_THRESHOLD = 0.05   # >5% 建议回避


def compute_premiums(
    closes_row: pd.Series, latest_nav: pd.DataFrame
) -> dict[str, dict]:
    """返回 {ts_code: {"premium": float, "nav_date": str}}。

    - closes_row：某一天的收盘价截面（ts_code -> close）
    - latest_nav：每只标的最新净值（columns: ts_code, nav_date, unit_nav）
    无净值数据或净值非正的标的不返回。
    """
    if latest_nav.empty:
        return {}
    nav_map = {
        r.ts_code: (r.unit_nav, r.nav_date)
        for r in latest_nav.itertuples(index=False)
        if pd.notna(r.unit_nav) and r.unit_nav > 0
    }
    out = {}
    for code, close in closes_row.items():
        if code not in nav_map or not (pd.notna(close) and close > 0):
            continue
        nav, nav_date = nav_map[code]
        out[code] = {"premium": float(close / nav - 1.0), "nav_date": str(nav_date)}
    return out


def premium_level(premium: float) -> str:
    """分级：""=正常 / warn=留意 / high=建议回避。"""
    if premium > HIGH_THRESHOLD:
        return "high"
    if premium > WARN_THRESHOLD:
        return "warn"
    return ""
