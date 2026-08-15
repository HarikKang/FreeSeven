"""ETF 候选池定义"""
from __future__ import annotations

from config import load_config


def load_universe() -> list[dict]:
    """从 config.yaml 读取候选池。返回 [{"ts_code": ..., "name": ...}, ...]"""
    cfg = load_config()
    return cfg["universe"]


def ts_codes() -> list[str]:
    return [u["ts_code"] for u in load_universe()]