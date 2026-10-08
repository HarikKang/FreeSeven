"""持仓对账月报：实际持仓 vs 信号目标，逐月跟踪误差。

用途: 验证"实盘 vs 回测/信号"的偏差（执行延迟、滑点、手动干预），
这是检验策略真实成色的唯一闭环。建议每次执行完调仓后运行一次。

用法:
    # 首次启用：按最近信号目标初始化实际持仓文件（成交后请按券商记录修正份额）
    python scripts/reconcile.py --init-from-signal --capital 100000

    # 月度对账（自动快照历史，两期起输出跟踪误差）
    python scripts/reconcile.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from config import ROOT, load_config
from data import Storage, load_universe
from data.portfolio import actual_weights, init_state_from_signal, load_state, portfolio_value

STATE_PATH = ROOT / "data" / "portfolio_state.json"
HISTORY_PATH = ROOT / "data" / "reconcile_history.json"
SIGNAL_PATH = ROOT / "data" / "signals" / "latest.json"


def render_position_report(
    held: dict[str, float], target: dict[str, float], names: dict[str, str], cash: float
) -> tuple[float, list[str], list[str]]:
    """打印实际 vs 目标权重表；返回 (最大单只偏离pp, 持有但不在目标, 目标但未持有)。"""
    lines = ["", "【持仓对账】实际 vs 信号目标", f"{'标的':<14}{'实际':>8}{'目标':>8}{'偏离':>9}"]
    max_dev = 0.0
    for code in sorted(set(held) | set(target), key=lambda c: -(held.get(c, 0) + target.get(c, 0))):
        h, t = held.get(code, 0.0), target.get(code, 0.0)
        dev = h - t
        max_dev = max(max_dev, abs(dev))
        lines.append(f"{names.get(code, code):<14}{h:>8.1%}{t:>8.1%}{dev:>+9.1%}")
    lines.append(f"{'现金':<14}{cash:>8.1%}{'—':>8}{'':>9}")
    extra_held = sorted(set(held) - set(target))
    extra_target = sorted(set(target) - set(held))
    lines.append(f"最大单只偏离: {max_dev:.1%}")
    if extra_held:
        lines.append(f"[注意] 持有但不在目标: {', '.join(names.get(c, c) for c in extra_held)}")
    if extra_target:
        lines.append(f"[注意] 目标但未持有: {', '.join(names.get(c, c) for c in extra_target)}")
    print("\n".join(lines))
    return max_dev, extra_held, extra_target


def render_tracking_report(history: list[dict], closes: pd.DataFrame, names: dict[str, str]):
    """逐期对比实际收益 vs 信号组合收益（信号收益=按期初信号权重买入持有至期末）。"""
    if len(history) < 2:
        print("\n【跟踪误差】首期基线已记录，下期起输出实际 vs 信号的逐期对比。")
        return
    rows = []
    cum_a = cum_s = 1.0
    for prev, cur in zip(history, history[1:]):
        d1, d2 = pd.Timestamp(prev["date"]), pd.Timestamp(cur["date"])
        actual_ret = cur["value"] / prev["value"] - 1 if prev["value"] > 0 else float("nan")
        sig_ret = sum(
            w * (float(closes.loc[d2, c]) / float(closes.loc[d1, c]))
            for c, w in prev.get("signal_weights", {}).items()
        ) - 1
        cum_a *= 1 + actual_ret
        cum_s *= 1 + sig_ret
        rows.append((d1, d2, actual_ret, sig_ret, actual_ret - sig_ret))
    print("\n【跟踪误差】实际 vs 信号（假设期间无出入金）")
    print(f"{'期间':<28}{'实际':>9}{'信号':>9}{'差':>9}")
    for d1, d2, a, s, diff in rows:
        print(f"{d1.date()} → {d2.date()}{a:>9.2%}{s:>9.2%}{diff:>+9.2%}")
    print(f"{'累计':<20}{cum_a - 1:>17.2%}{cum_s - 1:>9.2%}{cum_a - cum_s:>+9.2%}")
    worst = min(rows, key=lambda r: r[4])
    print(f"最差一期: {worst[1].date()} 差 {worst[4]:+.2%}（持续偏大说明执行有系统性拖累）")


def save_snapshot(history_path: Path, snapshot: dict):
    """追加快照（同日覆盖），按日期升序保存。"""
    history = []
    if history_path.exists():
        history = json.loads(history_path.read_text())
    history = [h for h in history if h["date"] != snapshot["date"]]
    history.append(snapshot)
    history.sort(key=lambda h: h["date"])
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="持仓对账与跟踪误差月报")
    parser.add_argument("--init-from-signal", action="store_true",
                        help="按最近信号目标初始化持仓文件（首次启用用）")
    parser.add_argument("--capital", type=float, default=0.0, help="组合总资金（init 时必填）")
    parser.add_argument("--state", default=str(STATE_PATH), help="持仓 JSON 路径")
    parser.add_argument("--history", default=str(HISTORY_PATH), help="对账历史 JSON 路径")
    args = parser.parse_args()

    cfg = load_config()  # 确保 .env 已加载
    state_path, history_path = Path(args.state), Path(args.history)
    names = {u["ts_code"]: u["name"] for u in load_universe()}
    storage = Storage()
    closes, _ = storage.load_matrices()
    asof = closes.index[-1]

    signal = json.loads(SIGNAL_PATH.read_text()) if SIGNAL_PATH.exists() else None
    if signal is None:
        print(f"[错误] 未找到信号档案 {SIGNAL_PATH}，请先运行 run_signal.py。")
        return

    if args.init_from_signal:
        if args.capital <= 0:
            print("[错误] --init-from-signal 需要同时指定 --capital（组合总资金）。")
            return
        state = init_state_from_signal(signal, closes, asof, args.capital, state_path)
        print(f"[初始化] 已按信号 {signal['asof']} 目标权重生成 {state_path}（估值日 {asof.date()}）：")
        for p in state["positions"]:
            print(f"    {names.get(p['ts_code'], p['ts_code'])}: {p['shares']:,.0f} 份")
        print("[提醒] 以上为理论份额，请按券商实际成交修正 shares/cash 后再用于对账。")
        return

    state = load_state(state_path)
    if state is None:
        print(f"[错误] 未找到持仓文件 {state_path}。首次启用请运行：\n"
              f"    python scripts/reconcile.py --init-from-signal --capital <总资金>")
        return

    held = actual_weights(state, closes, asof)
    target = signal.get("weights", {})
    cash = float(state.get("cash", 0))
    total_value = portfolio_value(state, closes, asof)
    cash_w = cash / total_value if total_value > 0 else 0.0

    print(f"【持仓对账】估值日 {asof.date()} | 信号 {signal['asof']} | 总市值 {total_value:,.0f} 元")
    render_position_report(held, target, names, cash_w)

    save_snapshot(history_path, {
        "date": asof.strftime("%Y%m%d"),
        "value": total_value,
        "cash": cash,
        "weights": held,
        "signal_asof": signal["asof"],
        "signal_weights": target,
    })
    history = json.loads(history_path.read_text())
    render_tracking_report(history, closes, names)
    print(f"\n[快照] 已写入 {history_path}（{len(history)} 期）")


if __name__ == "__main__":
    main()
