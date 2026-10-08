"""月末信号自动执行器（cron 每交易日晚间调用；非信号日秒退）。

职责:
  1. 补算漏跑: 上月末交易日无信号存档（如节前关机）-> 用 --asof 自动补算
  2. 当日信号: 今天是本月最后交易日（按 tushare 官方交易日历）-> 等数据就绪后自动 run_signal
  3. 告警: 数据迟迟未就绪或执行异常 -> 按配置渠道推送告警

用法:
    python scripts/auto_signal.py             # 日常（cron 调用）
    python scripts/auto_signal.py --dry-run   # 只打印判断，不执行不推送

cron 安装（每交易日 21:30 检查，数据未就绪自动重试至约 22:30）:
    30 21 * * 1-5 cd /Users/kangdingwu/Documents/code/FreeSeven && /Users/kangdingwu/.pyenv/versions/3.11.15/bin/python scripts/auto_signal.py >> out/auto_signal.log 2>&1
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd

from config import ROOT, load_config
from data import Storage, TushareFetcher
from data.sync import fetch_incremental
from signals.notifier import notify

SIGNAL_DIR = ROOT / "data" / "signals"
# 最近信号存档超过该天数视为系统停用，不自动补算，转人工确认
DORMANT_GAP_DAYS = 40


def trading_days_this_and_prev_month(fetcher: TushareFetcher, today: datetime) -> list[pd.Timestamp]:
    """上月1日至本月末之间的全部交易日（官方日历，含未来日期）。"""
    month_start = pd.Timestamp(today.year, today.month, 1)
    prev_start = (month_start - pd.offsets.BMonthEnd(1)).replace(day=1)
    month_end = month_start + pd.offsets.MonthEnd(0)
    cal = fetcher.trade_cal(prev_start.strftime("%Y%m%d"), month_end.strftime("%Y%m%d"))
    return sorted(pd.to_datetime(cal["cal_date"], format="%Y%m%d"))


def latest_signal_date(signal_dir=SIGNAL_DIR) -> pd.Timestamp | None:
    """信号存档中最新的信号日（忽略 latest.json 快捷方式）。"""
    dates = [pd.Timestamp(f.stem) for f in signal_dir.glob("2*.json")]
    return max(dates) if dates else None


def ensure_data_ready(
    storage: Storage, fetcher: TushareFetcher, cfg: dict,
    expected: str, retries: int, interval: int,
) -> bool:
    """增量拉取并等待数据水位达到 expected（YYYYMMDD）。"""
    for attempt in range(1, retries + 1):
        fetch_incremental(fetcher, storage, cfg["backtest"]["end"])
        got = storage.latest_date("fund_daily")
        if got >= expected:
            print(f"[数据] 水位 {got}，已达 {expected}")
            return True
        if attempt < retries:
            print(f"[等待] 数据最新到 {got}，未到 {expected}，"
                  f"{interval // 60} 分钟后重试（{attempt}/{retries - 1}）")
            time.sleep(interval)
    print(f"[失败] 数据水位始终未到 {expected}")
    return False


def run_signal_cli(extra_args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(ROOT / "scripts" / "run_signal.py"), "--force", *extra_args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, end="")
    return proc


def alert(cfg: dict, text: str, dry_run: bool):
    print(f"[告警] {text}")
    if not dry_run:
        notify(cfg["notify"]["channel"], "月末信号自动执行告警", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="月末信号自动执行器（cron 调用）")
    parser.add_argument("--dry-run", action="store_true", help="只打印判断，不执行不推送")
    parser.add_argument("--retries", type=int, default=3, help="数据未就绪重试次数")
    parser.add_argument("--interval", type=int, default=1800, help="重试间隔（秒）")
    args = parser.parse_args()

    cfg = load_config()
    today_ts = pd.Timestamp(datetime.now().date())

    try:
        days = trading_days_this_and_prev_month(TushareFetcher(), datetime.now())
    except Exception as exc:  # 交易日历不可用即无法安全判断，直接告警
        alert(cfg, f"交易日历获取失败（{exc}），今日跳过自动执行", args.dry_run)
        return 1

    month_start = pd.Timestamp(datetime.now().year, datetime.now().month, 1)
    prev_end = max((d for d in days if d < month_start), default=None)
    cur_end = max((d for d in days if d >= month_start), default=None)
    expected = max((d for d in days if d <= today_ts), default=None)
    print(f"[日历] 今天 {today_ts.date()} | 上月末交易日 {prev_end and prev_end.date()} | "
          f"本月末交易日 {cur_end and cur_end.date()} | 数据应达 {expected and expected.date()}")
    if expected is None:
        print("[跳过] 日历内无已过交易日。")
        return 0

    # ---- 组装待执行动作 ----
    actions: list[tuple[str, list[str]]] = []

    # 1) 上月末信号漏跑 -> 补算
    if prev_end is not None and not (SIGNAL_DIR / f"{prev_end:%Y%m%d}.json").exists():
        latest = latest_signal_date()
        if latest is None or (today_ts - latest).days > DORMANT_GAP_DAYS:
            alert(cfg, f"检测到上月末（{prev_end.date()}）信号缺失，但最近信号存档过旧"
                       f"（{latest and latest.date()}），系统疑似停用，请人工确认是否补算", args.dry_run)
        else:
            actions.append((f"补算 {prev_end.date()} 月末信号", ["--asof", prev_end.strftime("%Y%m%d")]))

    # 2) 今日即本月最后交易日 -> 正式信号（已生成过则跳过，避免重复推送）
    is_signal_day = cur_end is not None and today_ts == cur_end
    if is_signal_day:
        if (SIGNAL_DIR / f"{cur_end:%Y%m%d}.json").exists():
            print("[跳过] 今日信号已生成过。")
        else:
            actions.append(("本月最后交易日，生成正式信号", []))

    if not actions:
        print("[跳过] 今日无需生成信号。")
        return 0

    # ---- 执行 ----
    # 说明: auto_signal 已自行校验"官方日历月末 + 数据水位达标"，
    # 因此统一带 --force，绕过 run_signal 对中国节假日月末保守的 BMonthEnd 启发式。
    storage = Storage()
    fetcher = TushareFetcher()
    for label, extra in actions:
        print(f"\n===== {label} =====")
        if args.dry_run:
            print(f"[dry-run] 数据门槛 {expected.date()}，将执行: run_signal.py --force {' '.join(extra)}".rstrip())
            continue
        if not ensure_data_ready(storage, fetcher, cfg, expected.strftime("%Y%m%d"),
                                 args.retries, args.interval):
            alert(cfg, f"数据水位始终未到 {expected.date()}（重试 {args.retries} 次后放弃），"
                       f"请手动执行 run_signal.py 补算", args.dry_run)
            return 1
        proc = run_signal_cli(extra)
        if proc.returncode != 0 or "未写入信号档案" in proc.stdout:
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
            alert(cfg, f"信号执行异常（{label}），请检查 out/auto_signal.log 并手动处理", args.dry_run)
            return 1
        print(f"[完成] {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
