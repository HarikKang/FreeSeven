"""跨市场限仓与 QDII 溢价计算单测。"""
import pandas as pd

from signals.premium import compute_premiums, premium_level
from strategy.core import MomentumStrategy


def test_max_cross_caps_cross_market_selection():
    """跨市场最多入选 max_cross 只，其余名额由动量次优补足。"""
    s = MomentumStrategy(
        window=5, top_n=3, require_positive=True,
        max_cross=2, cross_codes=["X1", "X2", "X3"],
    )
    # X1/X2/X3 动量最高，但限 2 只 -> A 补位
    mom = pd.Series({"X1": 0.5, "X2": 0.4, "X3": 0.3, "A": 0.2, "B": 0.1})
    w = s.select(mom)
    assert set(w.keys()) == {"X1", "X2", "A"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_max_cross_none_means_unlimited():
    s = MomentumStrategy(
        window=5, top_n=3, require_positive=True,
        max_cross=None, cross_codes=["X1", "X2", "X3"],
    )
    mom = pd.Series({"X1": 0.5, "X2": 0.4, "X3": 0.3, "A": 0.2})
    assert set(s.select(mom).keys()) == {"X1", "X2", "X3"}


def test_max_cross_respects_positive_and_overheat_filters():
    """限仓逻辑与正动量/过热过滤叠加。"""
    s = MomentumStrategy(
        window=5, top_n=3, require_positive=True, max_momentum=0.6,
        max_cross=1, cross_codes=["X1", "X2"],
    )
    mom = pd.Series({"X1": 0.9, "X2": 0.5, "A": 0.4, "B": -0.1})
    # X1 过热剔除；X2 占 1 个跨市场名额；A 补位
    assert set(s.select(mom).keys()) == {"X2", "A"}


def test_compute_premiums():
    closes_row = pd.Series({"Q": 2.10, "A": 1.00, "N": float("nan")})
    nav = pd.DataFrame({
        "ts_code": ["Q", "A"],
        "nav_date": ["20260813", "20260813"],
        "unit_nav": [2.00, 1.00],
    })
    prem = compute_premiums(closes_row, nav)
    assert set(prem.keys()) == {"Q", "A"}
    assert abs(prem["Q"]["premium"] - 0.05) < 1e-9
    assert prem["Q"]["nav_date"] == "20260813"


def test_compute_premiums_empty_nav():
    assert compute_premiums(pd.Series({"A": 1.0}), pd.DataFrame()) == {}


def test_premium_level():
    assert premium_level(0.01) == ""
    assert premium_level(0.04) == "warn"
    assert premium_level(0.06) == "high"
