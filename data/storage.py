"""SQLite 本地缓存：基金日线、指数日线、交易日历"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "freeseven.db"

# 各表主键（用于去重与唯一索引）
_PK = {
    "fund_daily": "ts_code, trade_date",
    "fund_adj": "ts_code, trade_date",
    "fund_nav": "ts_code, nav_date",
    "index_daily": "ts_code, trade_date",
    "trade_cal": "cal_date",
}


class Storage:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        return conn

    def save_fund_daily(self, df: pd.DataFrame) -> int:
        """写入基金日线（upsert：同 code+date 覆盖）。返回写入行数。"""
        return self._upsert(df, "fund_daily")

    def save_fund_adj(self, df: pd.DataFrame) -> int:
        """写入基金复权因子（tushare fund_adj）。"""
        return self._upsert(df, "fund_adj")

    def save_fund_nav(self, df: pd.DataFrame) -> int:
        """写入基金净值（tushare fund_nav，用于溢价率监测）。"""
        if df.empty:
            return 0
        df = df[["ts_code", "nav_date", "unit_nav", "accum_nav"]].copy()
        return self._upsert(df, "fund_nav")

    def save_index_daily(self, df: pd.DataFrame) -> int:
        return self._upsert(df, "index_daily")

    def save_trade_cal(self, df: pd.DataFrame) -> int:
        return self._upsert(df, "trade_cal")

    def _upsert(self, df: pd.DataFrame, table: str) -> int:
        """INSERT OR REPLACE 写入，依赖主键唯一索引。

        旧版 append+DELETE 去重表会自动迁移（先清理重复再建索引）。
        """
        if df.empty:
            return 0
        pk = _PK[table]
        idx_name = f"ux_{table}"
        conn = self._connect()
        try:
            cols = list(df.columns)
            col_sql = ", ".join(cols)
            conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_sql})")
            has_idx = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND name=?",
                (table, idx_name),
            ).fetchone()
            if not has_idx:
                # 兼容旧表：先清理历史重复行，再建唯一索引
                conn.execute(
                    f"DELETE FROM {table} WHERE rowid NOT IN "
                    f"(SELECT MAX(rowid) FROM {table} GROUP BY {pk})"
                )
                conn.execute(f"CREATE UNIQUE INDEX {idx_name} ON {table} ({pk})")
            placeholders = ", ".join("?" * len(cols))
            rows = df.itertuples(index=False, name=None)
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({col_sql}) VALUES ({placeholders})", rows
            )
            conn.commit()
        finally:
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

    def latest_dates_by_code(self, table: str, date_col: str = "trade_date") -> dict[str, str]:
        """每只标的各自的数据水位（ts_code -> 最新日期）。

        增量拉取应按 code 取水位，避免某只标的历史拉取失败后缺口永远无法回补。
        """
        conn = self._connect()
        try:
            cur = conn.execute(
                f"SELECT ts_code, MAX({date_col}) FROM {table} GROUP BY ts_code"
            )
            return {code: d for code, d in cur.fetchall() if d}
        except Exception:
            return {}
        finally:
            conn.close()

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

    def read_all_fund_adj(self) -> pd.DataFrame:
        if not self.has_table("fund_adj"):
            return pd.DataFrame()
        conn = self._connect()
        df = pd.read_sql("SELECT * FROM fund_adj", conn)
        conn.close()
        return df

    def read_latest_fund_nav(self) -> pd.DataFrame:
        """每只标的最新一条净值（ts_code, nav_date, unit_nav）。"""
        if not self.has_table("fund_nav"):
            return pd.DataFrame()
        conn = self._connect()
        df = pd.read_sql(
            "SELECT ts_code, nav_date, unit_nav FROM fund_nav f "
            "WHERE nav_date = (SELECT MAX(nav_date) FROM fund_nav "
            "WHERE ts_code = f.ts_code)",
            conn,
        )
        conn.close()
        return df

    def load_matrices(
        self, adjust: bool = True
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """加载收盘价/开盘价矩阵（index=交易日, columns=ts_code）。

        adjust=True 且存在复权因子时做前复权：price * adj_factor / 最新 adj_factor，
        最新价格不变、历史价格向下调整，分红除息不再污染动量与收益。
        """
        df = self.read_all_fund_daily()
        if df.empty:
            empty = pd.DataFrame()
            return empty, empty.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        closes = df.pivot(index="trade_date", columns="ts_code", values="close").sort_index()
        opens = df.pivot(index="trade_date", columns="ts_code", values="open").sort_index()
        if adjust:
            adj = self.read_all_fund_adj()
            if not adj.empty:
                adj["trade_date"] = pd.to_datetime(adj["trade_date"], format="%Y%m%d")
                factor = adj.pivot(
                    index="trade_date", columns="ts_code", values="adj_factor"
                ).sort_index()
                factor = factor.reindex(closes.index).ffill().bfill()
                # 前复权比例：最新一日为 1；无复权因子的列保持原价（比例取 1）
                ratio = (factor / factor.iloc[-1]).fillna(1.0)
                closes = closes * ratio
                opens = opens * ratio
        return closes, opens

    def has_table(self, table: str) -> bool:
        conn = self._connect()
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        row = cur.fetchone()
        conn.close()
        return row is not None