"""调仓信号文案渲染：纯函数，输入计算结果、输出可读报告文本。"""
from __future__ import annotations

import pandas as pd

from signals.premium import premium_level


def render_signal_report(
    asof: pd.Timestamp,
    exec_day: pd.Timestamp | None,
    weights: dict[str, float],
    sells: dict[str, float],
    buys: dict[str, float],
    holds: set[str],
    mom_series: pd.Series,
    premiums: dict[str, dict],
    names: dict[str, str],
    capital: float,
    max_momentum: float | None,
    has_nav: bool,
) -> str:
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
        lines.append(f"🟢 需买入/加仓（{len(buys)}只）:" + (" 无" if not buys else ""))
        for code in sorted(buys, key=lambda c: -mom_series.get(c, 0)):
            target_amt = capital * weights[code] if capital else 0
            trade_amt = capital * buys[code] if capital else 0
            lines.append(f"    {names.get(code, code)}[{code}] 目标{weights[code]*100:.1f}%"
                         + (f" | 买入约{trade_amt:,.0f}元（目标约{target_amt:,.0f}元）" if capital else ""))
        lines.append(f"⚪ 继续持有（{len(holds)}只）:" + (" 无" if not holds else ""))
        for code in sorted(holds, key=lambda c: -mom_series.get(c, 0)):
            amt = capital * weights[code] if capital else 0
            lines.append(f"    {names.get(code, code)}[{code}] {weights[code]*100:.0f}%"
                         + (f" 约{amt:,.0f}元" if amt else ""))
        lines.append(f"🔴 需卖出/减仓（{len(sells)}只）:" + (" 无" if not sells else ""))
        for code in sorted(sells, key=lambda c: -mom_series.get(c, 0)):
            amt = capital * sells[code] if capital else 0
            lines.append(f"    {names.get(code, code)}[{code}]"
                         + (f" 卖出约{amt:,.0f}元" if amt else ""))
    lines.append("")

    if max_momentum:
        over = mom_series[mom_series > max_momentum].sort_values(ascending=False)
        if not over.empty:
            lines.append(f"⚠️ 过热剔除（12月动量>+{max_momentum*100:.0f}%，防高位接盘）:")
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
        if max_momentum is not None:
            ranked = ranked[ranked <= max_momentum]
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
    elif weights and not has_nav:
        lines.append("【QDII 溢价】无净值数据，溢价检测不可用；请运行 python scripts/fetch_data.py 拉取")
        lines.append("")

    lines.append("【提醒】")
    lines.append("- 下个交易日开盘照清单下单，每只等权即可")
    lines.append("- QDII（纳指/标普/日经/恒生等）注意溢价，现价明显高于净值(IOPV)时观望")
    lines.append("- 本信号仅作研究参考，不构成投资建议")
    return "\n".join(lines)
