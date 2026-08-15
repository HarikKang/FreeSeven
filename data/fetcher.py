"""tushare 封装"""
from __future__ import annotations

import time

import pandas as pd
import tushare as ts

from config import get_token


class TushareFetcher:
    """tushare 接口封装，带简单重试。"""

    def __init__(self, token: str | None = None, retries: int = 3, pause: float = 1.0):
        ts.set_token(token or get_token())
        self.pro = ts.pro_api()
        self.retries = retries
        self.pause = pause

    def _call(self, api: str, **params) -> pd.DataFrame:
        for attempt in range(self.retries):
            try:
                df = getattr(self.pro, api)(**params)
                return df
            except Exception as e:
                if attempt == self.retries - 1:
                    raise
                time.sleep(self.pause * (attempt + 1))
        raise RuntimeError(f"{api} 调用失败")  # 不可达，仅类型收口

    def fund_basic(self, market: str = "E") -> pd.DataFrame:
        """场内基金（ETF/LOF）列表，market=E 为交易所上市基金。"""
        return self._call("fund_basic", market=market)

    def fund_daily(
        self,
        ts_code: str,
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame:
        """单只基金日线。start_date/end_date 格式 YYYYMMDD。"""
        params = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._call("fund_daily", **params)

    def index_daily(
        self,
        ts_code: str,
        start_date: str = "",
        end_date: str = "",
    ) -> pd.DataFrame:
        params = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._call("index_daily", **params)

    def trade_cal(self, start_date: str, end_date: str) -> pd.DataFrame:
        return self._call(
            "trade_cal",
            exchange="SSE",
            start_date=start_date,
            end_date=end_date,
            is_open="1",
        )