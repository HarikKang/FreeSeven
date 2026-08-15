"""生成本月调仓信号（信号+手动下单模式）。

用法:
    python scripts/run_signal.py                  # 基于最新数据出信号
    python scripts/run_signal.py --capital 100000 # 按资金算买卖金额
    python scripts/run_signal.py --fetch          # 先增量拉数据再出信号
    python scripts/run_signal.py --force          # 非月末也出（如复盘）
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from config import ROOT, load_config
from data import Storage, TushareFetcher, load_universe
from data.sync import fetch_incremental
from signals.generator import diff_signal
from signals.notifier import notify
from signals.premium import compute_premiums
from signals.report import render_signal_report
from strategy.core import MomentumStrategy
from strategy.schedule import is_signal_day, next_execution_dates

SIGNAL_DIR = ROOT / "data" / "signals"


def load_previous() -> dict | None:
    f = SIGNAL_DIR / "latest.json"
    if f.exists():
        return json.loads(f.read_text())
    return None


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
    args = parser.parse_args()

    cfg = load_config()
    strat = cfg["strategy"]
    names = {u["ts_code"]: u["name"] for u in load_universe()}

    storage = Storage()
    if args.fetch:
        fetch_incremental(TushareFetcher(), storage, cfg["backtest"]["end"])

    closes, _ = storage.load_matrices()  # 前复权价格，与回测同源
    asof = closes.index[-1]
    today = datetime.now().date()

    # 数据新鲜度检查：落后太多时信号日判断会错位，提醒先更新
    gap_days = (today - asof.date()).days
    if gap_days > 4:
        print(f"[警告] 数据最新到 {asof.date()}，落后今天 {gap_days} 天，"
              f"建议先运行 --fetch 更新后再出信号。")

    if not args.force and not is_signal_day(asof, closes.index):
        print(f"[提示] {asof.date()} 不是月度调仓日（当月最后一个交易日），"
              f"本次仅作预览。可用 --force 强制。")

    strategy = MomentumStrategy.from_config(strat, cross_codes=cfg.get("cross_market", []))
    weights = strategy.signal(closes, asof=asof)
    prev = load_previous()
    prev_weights = prev.get("weights", {}) if prev else {}
    sells, buys = diff_signal(prev_weights, weights)
    holds = set(prev_weights) & set(weights)

    # 展示用动量（与选股同一口径，含 lag/max_momentum 参数）
    mom_series = strategy.momentum(closes).iloc[-1]

    # QDII 溢价：收盘价 vs 最新单位净值（净值滞后 1~2 日，仅近似）
    latest_nav = storage.read_latest_fund_nav()
    premiums = compute_premiums(closes.loc[asof], latest_nav)

    capital = args.capital or cfg.get("portfolio", {}).get("capital", 0.0)
    exec_day = next_execution_dates(closes.index, [asof]).get(asof)  # 信号日下一个交易日

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

    save_signal(asof.strftime("%Y%m%d"), weights, {"sells": sells, "buys": buys, "holds": list(holds)})

    if args.force or is_signal_day(asof, closes.index):
        ok = notify(cfg["notify"]["channel"], f"ETF调仓信号 {asof.date()}", plan_text)
        print(f"\n[推送] {'成功' if ok else '未推送'}")


if __name__ == "__main__":
    main()
