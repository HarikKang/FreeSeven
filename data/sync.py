"""数据同步编排：fetcher 与 storage 的协作（水位判断、容错降级）。

从 scripts/fetch_data.py 下沉而来，供 CLI 与 run_signal --fetch 复用，
避免脚本互相 import。
"""
from __future__ import annotations

from data.fetcher import TushareFetcher
from data.storage import Storage
from data.universe import ts_codes

DEFAULT_START = "20150101"


def _fetch_adj(fetcher: TushareFetcher, storage: Storage, code: str, start: str, end: str) -> int:
    """拉复权因子；接口不可用时降级为不复权并告警，不中断整体流程。"""
    try:
        df = fetcher.fund_adj(code, start_date=start, end_date=end)
    except Exception as e:
        print(f"  [警告] {code} 复权因子拉取失败（{e}），将使用不复权价格")
        return 0
    return storage.save_fund_adj(df)


def _fetch_nav(fetcher: TushareFetcher, storage: Storage, code: str, start: str, end: str) -> int:
    """拉基金净值（溢价监测用）；失败仅告警，不影响主流程。"""
    try:
        df = fetcher.fund_nav(code, start_date=start, end_date=end)
    except Exception as e:
        print(f"  [警告] {code} 净值拉取失败（{e}），溢价监测不可用")
        return 0
    return storage.save_fund_nav(df)


def fetch_all(fetcher: TushareFetcher, storage: Storage, start: str, end: str) -> int:
    total = 0
    for code in ts_codes():
        df = fetcher.fund_daily(code, start_date=start, end_date=end)
        n = storage.save_fund_daily(df)
        n_adj = _fetch_adj(fetcher, storage, code, start, end)
        n_nav = _fetch_nav(fetcher, storage, code, start, end)
        total += n
        print(f"  {code}: 行情 {n} 行, 复权因子 {n_adj} 行, 净值 {n_nav} 行")
    return total


def fetch_incremental(fetcher: TushareFetcher, storage: Storage, end: str) -> int:
    """增量更新：每只标的按自己的水位拉取。

    用全表 MAX(trade_date) 做水位会让历史拉取失败的标的缺口永远无法回补，
    因此价格与复权因子都按 ts_code 各自取水位。
    """
    wm_price = storage.latest_dates_by_code("fund_daily")
    wm_adj = storage.latest_dates_by_code("fund_adj")
    wm_nav = storage.latest_dates_by_code("fund_nav", date_col="nav_date")
    total = 0
    for code in ts_codes():
        start = wm_price.get(code) or DEFAULT_START
        df = fetcher.fund_daily(code, start_date=start, end_date=end)
        n = storage.save_fund_daily(df)
        start_adj = wm_adj.get(code) or start
        n_adj = _fetch_adj(fetcher, storage, code, start_adj, end)
        start_nav = wm_nav.get(code) or DEFAULT_START  # 净值无水位时拉全量（溢价监测需要）
        n_nav = _fetch_nav(fetcher, storage, code, start_nav, end)
        total += n
        print(f"  {code}: 行情 {n} 行（从 {start}）, 复权因子 {n_adj} 行, 净值 {n_nav} 行")
    return total
