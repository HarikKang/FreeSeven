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
from signals.generator import diff_signal, generate_signal
from signals.notifier import notify
from strategy.schedule import is_signal_day, month_end_dates

SIGNAL_DIR = Path(__file__).resolve().parent.parent / "data" / "signals"


def load_closes(storage: Storage) -> pd.DataFrame:
    df = storage.read_all_fund_daily()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    return df.pivot(index="trade_date", columns="ts_code", values="close").sort_index()


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
    closes = load_closes(storage)
    asof = closes.index[-1]
    today = datetime.now().date()

    if not args.force and not is_signal_day(asof, closes.index):
        print(f"[提示] {asof.date()} 不是月度调仓日（当月最后一个交易日），"
              f"本次仅作预览。可用 --force 强制。")

    weights = generate_signal(
        closes,
        window=strat["momentum_window"],
        top_n=strat["top_n"],
        require_positive=strat["require_positive"],
        asof=asof,
    )
    prev = load_previous()
    sells, buys = diff_signal(prev.get("weights", {}) if prev else {}, weights)

    capital = args.capital or cfg.get("portfolio", {}).get("capital", 0.0)

    lines = []
    lines.append(f"ETF 动量轮动调仓信号（{asof.date()}）")
    if weights:
        w = 1.0 / max(len(weights), 1)
        for code in sorted(weights, key=lambda c: -weights[c]):
            amt = capital * weights[code] if capital else 0
            lines.append(f"  买入 {names.get(code, code)} [{code}] 权重{weights[code]*100:.1f}%"
                         + (f" 约{amt:,.0f}元" if amt else ""))
    else:
        lines.append("  全空仓（无正动量标的，持币等待）")

    if capital and (sells or buys):
        lines.append("")
        lines.append("  操作清单：")
        for code, w in sells.items():
            lines.append(f"    卖出 {names.get(code, code)} [{code}] 约{capital*w:,.0f}元")
        for code, w in buys.items():
            lines.append(f"    买入 {names.get(code, code)} [{code}] 约{capital*w:,.0f}元")

    lines.append("")
    lines.append("免责声明：本信号仅作研究参考，不构成投资建议。")
    plan_text = "\n".join(lines)
    print(plan_text)

    save_signal(asof.strftime("%Y%m%d"), weights, {"sells": sells, "buys": buys})

    if args.force or is_signal_day(asof, closes.index):
        ok = notify(cfg["notify"]["channel"], f"ETF调仓信号 {asof.date()}", plan_text)
        print(f"\n[推送] {'成功' if ok else '未推送'}")


if __name__ == "__main__":
    main()