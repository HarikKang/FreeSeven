"""SQLite 本地缓存：基金日线、指数日线、交易日历"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "freeseven.db"


class Storage:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        return conn

    def save_fund_daily(self, df: pd.DataFrame) -> int:
        """写入基金日线（覆盖式 upsert：同 code+date 替换）。返回写入行数。"""
        return self._upsert(df, "fund_daily")

    def save_index_daily(self, df: pd.DataFrame) -> int:
        return self._upsert(df, "index_daily")

    def save_trade_cal(self, df: pd.DataFrame) -> int:
        return self._upsert(df, "trade_cal")

    def _upsert(self, df: pd.DataFrame, table: str) -> int:
        if df.empty:
            return 0
        conn = self._connect()
        df.to_sql(table, conn, if_exists="append", index=False)
        # 去重：保留最后写入的一行
        pk = {"fund_daily": "ts_code, trade_date", "index_daily": "ts_code, trade_date", "trade_cal": "cal_date"}[table]
        dedup_sql = (
            f"DELETE FROM {table} WHERE rowid NOT IN "
            f"(SELECT MAX(rowid) FROM {table} GROUP BY {pk})"
        )
        conn.execute(dedup_sql)
        conn.commit()
        conn.close()
        return len(df)

    def latest_date(self, table: str) -> str:
        conn = self._connect()
        try:
            cur = conn.execute(f"SELECT MAX(trade_date) FROM {table}")
            row = cur.fetchone()
        except Exception:
            return ""
        finally:
            conn.close()
        return row[0] or ""

    def read_fund_daily(self, ts_code: str, start_date: str = "", end_date: str = "") -> pd.DataFrame:
        conn = self._connect()
        sql = "SELECT * FROM fund_daily WHERE ts_code = ?"
        args: list = [ts_code]
        if start_date:
            sql += " AND trade_date >= ?"
            args.append(start_date)
        if end_date:
            sql += " AND trade_date <= ?"
            args.append(end_date)
        df = pd.read_sql(sql, conn, params=args)
        conn.close()
        if not df.empty:
            df = df.sort_values("trade_date").reset_index(drop=True)
        return df

    def read_all_fund_daily(self, start_date: str = "", end_date: str = "") -> pd.DataFrame:
        conn = self._connect()
        sql = "SELECT * FROM fund_daily"
        args: list = []
        if start_date:
            sql += " WHERE trade_date >= ?"
            args.append(start_date)
        if end_date:
            sql += " AND trade_date <= ?"
            args.append(end_date)
        df = pd.read_sql(sql, conn, params=args)
        conn.close()
        return df

    def has_table(self, table: str) -> bool:
        conn = self._connect()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        row = cur.fetchone()
        conn.close()
        return row is not None