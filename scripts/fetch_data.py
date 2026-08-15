"""拉取 ETF 日线数据到本地 SQLite。

用法:
    python scripts/fetch_data.py                  # 全量（从 config 回测起点）
    python scripts/fetch_data.py --incremental    # 增量（从上一次写入日期开始）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config
from data import Storage, TushareFetcher, ts_codes


def fetch_all(fetcher: TushareFetcher, storage: Storage, start: str, end: str):
    codes = ts_codes()
    total = 0
    for code in codes:
        df = fetcher.fund_daily(code, start_date=start, end_date=end)
        n = storage.save_fund_daily(df)
        total += n
        print(f"  {code}: {n} 行")
    return total


def fetch_incremental(fetcher: TushareFetcher, storage: Storage, end: str):
    last = storage.latest_date("fund_daily")
    start = last or "20150101"
    print(f"增量更新，从 {start} 到 {end}")
    return fetch_all(fetcher, storage, start, end)


def main():
    parser = argparse.ArgumentParser(description="拉取 ETF 日线到 SQLite")
    parser.add_argument("--incremental", action="store_true", help="增量更新")
    parser.add_argument("--end", default="", help="结束日期 YYYYMMDD，默认当天")
    args = parser.parse_args()

    cfg = load_config()
    end = args.end or cfg["backtest"]["end"]
    start = cfg["backtest"]["start"]

    fetcher = TushareFetcher()
    storage = Storage()

    if args.incremental:
        total = fetch_incremental(fetcher, storage, end)
    else:
        print(f"全量拉取 {len(ts_codes())} 只 ETF，{start} ~ {end}")
        total = fetch_all(fetcher, storage, start, end)

    print(f"完成，共写入 {total} 行到 {storage.db_path}")


if __name__ == "__main__":
    main()