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
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config
from data import Storage, load_universe, ts_codes
from signals.generator import diff_signal
from signals.notifier import notify
from signals.premium import compute_premiums, premium_level
from strategy.core import MomentumStrategy
from strategy.schedule import is_signal_day, month_end_dates, next_execution_dates

SIGNAL_DIR = Path(__file__).resolve().parent.parent / "data" / "signals"


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

    if args.fetch:
        from scripts.fetch_data import fetch_incremental  # noqa: PLC0415

        from data import TushareFetcher  # noqa: PLC0415

        end = cfg["backtest"]["end"]
        fetch_incremental(TushareFetcher(), Storage(), end)

    storage = Storage()
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

    # 执行日 = 信号日下一个交易日
    exec_day = next_execution_dates(closes.index, [asof]).get(asof)

    lines = []
    lines.append("【ETF动量轮动 · 调仓信号】")
    lines.append(f"信号日: {asof.date()}（{'周五' if asof.weekday()==4 else ''}收盘）")
    if exec_day:
        lines.append(f"执行日: {exec_day.date()}（{['一','二','三','四','五'][exec_day.weekday()]}）开盘")
    else:
        lines.append("执行日: 下一个交易日开盘")
    if capital:
        lines.append(f"资金: {capital:,.0f} 元 | 目标 {len(weights)} 只等权 | 每只约 {capital/max(len(weights),1):,.0f} 元")
    else:
        lines.append(f"资金: 未指定（可用 --capital 换算金额）| 目标 {len(weights)} 只等权")
    lines.append("")

    if not weights:
        lines.append("🟡 本月操作：全空仓")
        lines.append("    无正动量标的，持币等待，本月不交易。")
    else:
        lines.append(f"🟢 新建买入（{len(buys)}只）:" + (" 无" if not buys else ""))
        for code in sorted(buys, key=lambda c: -mom_series.get(c, 0)):
            amt = capital * weights[code] if capital else 0
            lines.append(f"    {names.get(code, code)}[{code}] {weights[code]*100:.0f}%"
                         + (f" 约{amt:,.0f}元" if amt else ""))
        lines.append(f"⚪ 继续持有（{len(holds)}只）:" + (" 无" if not holds else ""))
        for code in sorted(holds, key=lambda c: -mom_series.get(c, 0)):
            amt = capital * weights[code] if capital else 0
            lines.append(f"    {names.get(code, code)}[{code}] {weights[code]*100:.0f}%"
                         + (f" 约{amt:,.0f}元" if amt else ""))
        lines.append(f"🔴 清仓卖出（{len(sells)}只）:" + (" 无" if not sells else ""))
        for code in sorted(sells, key=lambda c: -mom_series.get(c, 0)):
            lines.append(f"    {names.get(code, code)}[{code}]")
    lines.append("")

    max_mom = strat.get("max_momentum")
    if max_mom:
        over = mom_series[mom_series > max_mom].sort_values(ascending=False)
        if not over.empty:
            lines.append(f"⚠️ 过热剔除（12月动量>+{max_mom*100:.0f}%，防高位接盘）:")
            for code, v in over.items():
                lines.append(f"    {names.get(code, code)}[{code}] 近12月+{v*100:.1f}%")
            lines.append("")

    lines.append("【目标持仓明细】（按近12月动量排序）")
    if weights:
        for i, code in enumerate(sorted(weights, key=lambda c: -mom_series.get(c, 0)), 1):
            mom = mom_series.get(code)
            mom_s = f"近12月{mom*100:+.1f}%" if mom == mom else "数据不足"
            amt = capital * weights[code] if capital else 0
            prem_s = ""
            if code in premiums:
                p = premiums[code]["premium"]
                icon = {"high": "🔴", "warn": "⚠️"}.get(premium_level(p), "")
                prem_s = f"  溢价{p*100:+.1f}%{icon}"
            lines.append(f"  {i}. {names.get(code, code)}[{code}] {weights[code]*100:.0f}%"
                         + (f" {amt:,.0f}元" if amt else "") + f"  {mom_s}{prem_s}")
    else:
        lines.append("  （空仓）")
    lines.append("")

    # 溢价预警：持仓中溢价超阈值的标的，高风险时给出候选替补
    flagged = [(c, premiums[c]["premium"]) for c in weights
               if c in premiums and premium_level(premiums[c]["premium"])]
    if flagged:
        ranked = mom_series.dropna()
        if strat.get("max_momentum") is not None:
            ranked = ranked[ranked <= strat["max_momentum"]]
        ranked = ranked[ranked > 0].sort_values(ascending=False)
        alts = [c for c in ranked.index if c not in weights]
        lines.append("【QDII 溢价预警】（收盘价 vs 单位净值，净值滞后 1~2 日，下单前看实时 IOPV）")
        for c, p in sorted(flagged, key=lambda x: -x[1]):
            if premium_level(p) == "high":
                alt = f"{names.get(alts[0], alts[0])}[{alts[0]}]" if alts else "无"
                tip = f"溢价过高建议回避，候选替补: {alt}"
            else:
                tip = "留意溢价回落风险，限价单不追高"
            lines.append(f"    {'🔴' if premium_level(p) == 'high' else '⚠️'} "
                         f"{names.get(c, c)}[{c}] 溢价 {p*100:+.1f}% — {tip}")
        lines.append("")
    elif weights and latest_nav.empty:
        lines.append("【QDII 溢价】无净值数据，溢价检测不可用；请运行 python scripts/fetch_data.py 拉取")
        lines.append("")

    lines.append("【提醒】")
    lines.append("- 下个交易日开盘照清单下单，每只等权即可")
    lines.append("- QDII（纳指/标普/日经/恒生等）注意溢价，现价明显高于净值(IOPV)时观望")
    lines.append("- 本信号仅作研究参考，不构成投资建议")
    plan_text = "\n".join(lines)
    print(plan_text)

    save_signal(asof.strftime("%Y%m%d"), weights, {"sells": sells, "buys": buys, "holds": list(holds)})

    if args.force or is_signal_day(asof, closes.index):
        ok = notify(cfg["notify"]["channel"], f"ETF调仓信号 {asof.date()}", plan_text)
        print(f"\n[推送] {'成功' if ok else '未推送'}")


if __name__ == "__main__":
    main()