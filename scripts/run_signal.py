"""生成本月调仓信号（信号+手动下单模式）。

用法:
    python scripts/run_signal.py                  # 基于最新数据出信号
    python scripts/run_signal.py --capital 100000 # 按资金算买卖金额
    python scripts/run_signal.py --fetch          # 先增量拉数据再出信号
    python scripts/run_signal.py --force          # 非月末也出（如复盘）
    python scripts/run_signal.py --asof 20260930  # 补算指定信号日（如节前漏跑月末信号）
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import ROOT, load_config
from data import Storage, TushareFetcher, active_codes, load_universe
from data.sync import fetch_incremental
from signals.generator import diff_signal
from signals.notifier import notify
from signals.premium import compute_premiums
from signals.report import render_signal_report
from strategy.core import MomentumStrategy
from strategy.schedule import is_signal_day, next_execution_dates

SIGNAL_DIR = ROOT / "data" / "signals"
STATE_PATH = ROOT / "data" / "portfolio_state.json"


def load_previous() -> dict | None:
    f = SIGNAL_DIR / "latest.json"
    if f.exists():
        return json.loads(f.read_text())
    return None


def load_actual_weights(path, closes: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float] | None:
    """按真实份额和最新收盘价计算当前权重；不存在状态文件时返回 None。"""
    if not path.exists():
        return None
    state = json.loads(path.read_text())
    values = {
        p["ts_code"]: float(p["shares"]) * float(closes.loc[asof, p["ts_code"]])
        for p in state.get("positions", [])
        if p.get("ts_code") in closes.columns and p.get("shares", 0) > 0
    }
    total = float(state.get("cash", 0)) + sum(values.values())
    return {code: value / total for code, value in values.items()} if total > 0 else {}


def save_signal(asof: str, weights: dict, plan: dict):
    SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
    data = {"asof": asof, "weights": weights, "plan": plan}
    (SIGNAL_DIR / f"{asof}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    (SIGNAL_DIR / "latest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="生成 ETF 动量轮动调仓信号")
    parser.add_argument("--capital", type=float, default=0.0, help="可用资金（元），用于换算买卖金额")
    parser.add_argument("--fetch", action="store_true", help="先增量拉取数据")
    parser.add_argument("--force", action="store_true", help="非调仓日也强制出信号")
    parser.add_argument("--asof", default=None, help="补算历史信号日（YYYYMMDD），如节前漏跑月末信号")
    parser.add_argument("--state", default=str(STATE_PATH), help="实际持仓 JSON（份额为准）")
    args = parser.parse_args()

    cfg = load_config()
    strat = cfg["strategy"]
    names = {u["ts_code"]: u["name"] for u in load_universe()}

    storage = Storage()
    if args.fetch:
        fetch_incremental(TushareFetcher(), storage, cfg["backtest"]["end"])

    closes_all, _ = storage.load_matrices()  # 前复权价格，与回测同源
    latest = closes_all.index[-1]
    today = datetime.now().date()

    # 信号截面日：默认最新交易日；--asof 用于补算错过的历史信号日（如节前漏跑）。
    if args.asof:
        asof = pd.Timestamp(args.asof)
        if asof not in closes_all.index:
            print(f"[错误] {asof.date()} 不是交易日或库中无该日数据，退出。")
            return
    else:
        asof = latest

    # 数据新鲜度检查：不能把“缓存里的最后一天”误认为月末（按最新数据日判断，
    # --asof 补算时数据本身仍应是新的）。
    gap_days = (today - latest.date()).days
    business_gap = max(len(pd.bdate_range(latest.date(), today)) - 1, 0)
    data_is_fresh = business_gap <= 1
    if not data_is_fresh:
        print(f"[警告] 数据最新到 {latest.date()}，落后今天 {gap_days} 天，"
              f"建议先运行 --fetch 更新后再出信号。")

    # 中国节假日导致月末早于自然工作日时，保守地要求使用 --force；
    # 这优于在数据不完整时自动写档和推送错误信号。
    calendar_month_end = asof == asof + pd.offsets.BMonthEnd(0)
    should_execute = args.force or (calendar_month_end and data_is_fresh)
    if not should_execute:
        print(f"[提示] {asof.date()} 尚未确认是可执行的月末信号日，"
              f"本次仅作预览。可在更新数据后重试，或用 --force 强制。")

    closes = closes_all.loc[:asof]  # 信号截面截至 asof，补算时杜绝 asof 之后的数据泄漏

    strategy = MomentumStrategy.from_config(
        strat, cross_codes=cfg.get("cross_market", []), risk=cfg.get("risk"),
        active_from=cfg.get("candidate_activation"), eligible_codes=active_codes(),
    )
    # 展示用动量（与选股同一口径，含 lag/max_momentum 参数）
    mom_series = strategy.momentum(closes).iloc[-1]

    # QDII 溢价：收盘价 vs 最新单位净值（净值滞后 1~2 日，仅近似）
    latest_nav = storage.read_latest_fund_nav()
    premiums = compute_premiums(closes.loc[asof], latest_nav)
    risk = cfg.get("risk", {})
    qdii = set(cfg.get("cross_market", []))
    blocked_qdii = {
        code for code in qdii
        if code not in premiums and risk.get("block_qdii_without_nav", True)
        or code in premiums and premiums[code]["premium"] > risk.get("premium_block", 0.05)
    }
    weights = strategy.select(
        strategy.momentum(closes).iloc[-1], asof=asof, excluded_codes=blocked_qdii, closes=closes
    )
    if blocked_qdii:
        labels = ", ".join(sorted(blocked_qdii))
        print(f"[风控] 已阻止高溢价/无净值 QDII 新开仓: {labels}")

    actual_weights = load_actual_weights(Path(args.state), closes, asof)
    prev = load_previous()
    prev_weights = actual_weights if actual_weights is not None else (prev.get("weights", {}) if prev else {})
    if actual_weights is None:
        print("[提示] 未找到实际持仓文件，交易差额暂以最近信号为准；可复制 config/portfolio_state.example.json。")
    sells, buys = diff_signal(prev_weights, weights)
    holds = {
        code for code in set(prev_weights) & set(weights)
        if abs(prev_weights[code] - weights[code]) < 1e-9
    }

    capital = args.capital or cfg.get("portfolio", {}).get("capital", 0.0)
    exec_day = next_execution_dates(closes_all.index, [asof]).get(asof)  # 信号日下一个交易日（按完整日历）

    plan_text = render_signal_report(
        asof=asof,
        exec_day=exec_day,
        weights=weights,
        sells=sells,
        buys=buys,
        holds=holds,
        mom_series=mom_series,
        premiums=premiums,
        names=names,
        capital=capital,
        max_momentum=strat.get("max_momentum"),
        has_nav=not latest_nav.empty,
    )
    print(plan_text)

    if should_execute:
        save_signal(asof.strftime("%Y%m%d"), weights, {"sells": sells, "buys": buys, "holds": list(holds)})
        ok = notify(cfg["notify"]["channel"], f"ETF调仓信号 {asof.date()}", plan_text)
        print(f"\n[推送] {'成功' if ok else '未推送'}")
    else:
        print("\n[预览] 未写入信号档案，也未推送。")


if __name__ == "__main__":
    main()
