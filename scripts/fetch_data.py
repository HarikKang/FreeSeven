"""拉取 ETF 日线数据到本地 SQLite。

用法:
    python scripts/fetch_data.py                  # 全量（从 config 回测起点）
    python scripts/fetch_data.py --incremental    # 增量（各标的从自己的水位开始）
"""
import argparse

from config import load_config
from data import Storage, TushareFetcher, ts_codes
from data.sync import fetch_all, fetch_incremental


def main():
    parser = argparse.ArgumentParser(description="拉取 ETF 日线到 SQLite")
    parser.add_argument("--incremental", action="store_true", help="增量更新")
    parser.add_argument("--end", default="", help="结束日期 YYYYMMDD，默认 config.backtest.end")
    args = parser.parse_args()

    cfg = load_config()
    end = args.end or cfg["backtest"]["end"]
    start = cfg["backtest"]["start"]

    fetcher = TushareFetcher()
    storage = Storage()

    if args.incremental:
        print(f"增量更新到 {end}（各标的按自己的水位）")
        total = fetch_incremental(fetcher, storage, end)
    else:
        print(f"全量拉取 {len(ts_codes())} 只 ETF，{start} ~ {end}")
        total = fetch_all(fetcher, storage, start, end)

    print(f"完成，共写入 {total} 行行情到 {storage.db_path}")


if __name__ == "__main__":
    main()
