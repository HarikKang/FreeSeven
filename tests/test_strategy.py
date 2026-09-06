import pandas as pd

from strategy.core import MomentumStrategy
from strategy.momentum import compute_momentum
from signals.generator import diff_signal


def test_compute_momentum_window():
    closes = pd.DataFrame({"A": [1, 2, 3, 4, 5]})
    mom = compute_momentum(closes, window=2)
    assert mom.iloc[-1]["A"] == 5 / 3 - 1


def test_compute_momentum_lag():
    closes = pd.DataFrame({"A": [1, 2, 3, 4, 5]})
    mom = compute_momentum(closes, window=2, lag=1)
    # end = close[-2]=4, start = close[-4]=2
    assert mom.iloc[-1]["A"] == 4 / 2 - 1


def test_select_topn():
    s = pd.Series({"A": 0.3, "B": 0.1, "C": -0.2, "D": 0.2})
    w = MomentumStrategy(top_n=2).select(s)
    assert set(w.keys()) == {"A", "D"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_select_all_negative():
    s = pd.Series({"A": -0.1, "B": -0.2})
    assert MomentumStrategy(top_n=2).select(s) == {}


def test_select_ignores_nan():
    s = pd.Series({"A": 0.3, "B": float("nan"), "C": 0.1})
    w = MomentumStrategy(top_n=3).select(s)
    assert set(w.keys()) == {"A", "C"}


def test_select_max_momentum():
    s = pd.Series({"A": 0.95, "B": 0.6, "C": 0.4, "D": -0.1})
    w = MomentumStrategy(top_n=2, max_momentum=0.8).select(s)
    assert set(w.keys()) == {"B", "C"}


def test_month_end_dates():
    import pandas as pd

    from strategy.schedule import month_end_dates

    idx = pd.DatetimeIndex(pd.date_range("2026-01-06", "2026-03-31", freq="B"))
    dates = month_end_dates(idx)
    assert dates == [pd.Timestamp("2026-01-30"), pd.Timestamp("2026-02-27"), pd.Timestamp("2026-03-31")]


def test_diff_signal_includes_weight_adjustments():
    sells, buys = diff_signal({"A": 0.5, "B": 0.5}, {"A": 0.6, "B": 0.2, "C": 0.2})
    assert set(sells) == {"B"} and abs(sells["B"] - 0.3) < 1e-9
    assert set(buys) == {"A", "C"}
    assert abs(buys["A"] - 0.1) < 1e-9
    assert abs(buys["C"] - 0.2) < 1e-9


def test_select_enforces_theme_region_and_activation():
    s = MomentumStrategy(
        top_n=4, require_positive=True, max_per_theme=1, max_per_region=1,
        theme_by_code={"T1": "tech", "T2": "tech"},
        region_by_code={"U1": "us", "U2": "us"},
        active_from={"NEW": "2026-08-01"},
    )
    mom = pd.Series({"T1": 0.9, "T2": 0.8, "U1": 0.7, "U2": 0.6, "NEW": 0.5, "A": 0.4})
    result = s.select(mom, asof=pd.Timestamp("2026-07-31"), excluded_codes={"U1"})
    assert set(result) == {"T1", "U2", "A"}
