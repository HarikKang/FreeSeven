"""ETF 候选池定义"""
from __future__ import annotations

from config import load_config


def load_universe() -> list[dict]:
    """从 config.yaml 读取候选池。返回 [{"ts_code": ..., "name": ...}, ...]"""
    cfg = load_config()
    return cfg["universe"]


def ts_codes() -> list[str]:
    """全部研究池（含观察池；不含淘汰池），用于持续采集数据。"""
    return [u["ts_code"] for u in load_universe() if u.get("status") != "retired"]


def active_codes() -> list[str]:
    """正式主池，回测与出信号只能从这里选标的。"""
    return [u["ts_code"] for u in load_universe() if u.get("status", "active") == "active"]


def watch_codes() -> list[str]:
    """观察池：同步数据与研究，但不参与选股。"""
    return [u["ts_code"] for u in load_universe() if u.get("status") == "watch"]
