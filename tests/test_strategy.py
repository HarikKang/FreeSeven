import pandas as pd

from strategy.allocator import target_weights
from strategy.momentum import compute_momentum


def test_compute_momentum_window():
    closes = pd.DataFrame({"A": [1, 2, 3, 4, 5]})
    mom = compute_momentum(closes, window=2)
    assert mom.iloc[-1]["A"] == 5 / 3 - 1


def test_compute_momentum_lag():
    closes = pd.DataFrame({"A": [1, 2, 3, 4, 5]})
    mom = compute_momentum(closes, window=2, lag=1)
    # end = close[-2]=4, start = close[-4]=2
    assert mom.iloc[-1]["A"] == 4 / 2 - 1


def test_target_weights_topn():
    s = pd.Series({"A": 0.3, "B": 0.1, "C": -0.2, "D": 0.2})
    w = target_weights(s, top_n=2, require_positive=True)
    assert set(w.keys()) == {"A", "D"}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_target_weights_all_negative():
    s = pd.Series({"A": -0.1, "B": -0.2})
    assert target_weights(s, top_n=2, require_positive=True) == {}


def test_target_weights_ignores_nan():
    s = pd.Series({"A": 0.3, "B": float("nan"), "C": 0.1})
    w = target_weights(s, top_n=3, require_positive=True)
    assert set(w.keys()) == {"A", "C"}