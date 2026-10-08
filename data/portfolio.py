"""实际持仓状态：读写 portfolio_state.json，按收盘价估值算权重。

供 run_signal（交易差额基准）与 reconcile（对账月报）共用，
避免两份脚本各自解析持仓文件导致口径漂移。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def load_state(path: Path) -> dict | None:
    """读取持仓文件；不存在返回 None。"""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def actual_weights(state: dict, closes: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
    """按真实份额和 asof 收盘价计算当前权重（含现金，现金无权重）。"""
    values = {
        p["ts_code"]: float(p["shares"]) * float(closes.loc[asof, p["ts_code"]])
        for p in state.get("positions", [])
        if p.get("ts_code") in closes.columns and p.get("shares", 0) > 0
    }
    total = float(state.get("cash", 0)) + sum(values.values())
    return {code: value / total for code, value in values.items()} if total > 0 else {}


def portfolio_value(state: dict, closes: pd.DataFrame, asof: pd.Timestamp) -> float:
    """总市值 = 持仓市值 + 现金。"""
    pos = sum(
        float(p.get("shares", 0)) * float(closes.loc[asof, p["ts_code"]])
        for p in state.get("positions", [])
        if p.get("ts_code") in closes.columns
    )
    return pos + float(state.get("cash", 0))


def init_state_from_signal(
    signal: dict, closes: pd.DataFrame, asof: pd.Timestamp, capital: float, path: Path
) -> dict:
    """按信号目标权重生成持仓文件（份额 = 目标金额 / asof 收盘价）。

    仅作初始化基线，实际成交后应按券商记录修正 shares 与 cash。
    """
    positions = [
        {"ts_code": code, "shares": round(capital * w / float(closes.loc[asof, code]))}
        for code, w in signal.get("weights", {}).items()
        if w > 0 and code in closes.columns
    ]
    state = {
        "asof": asof.strftime("%Y%m%d"),
        "cash": 0,
        "positions": positions,
        "note": "由信号目标初始化，请按券商成交记录修正 shares/cash",
    }
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    return state
