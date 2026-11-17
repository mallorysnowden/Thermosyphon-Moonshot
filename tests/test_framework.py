import pytest

from tea.finance import irr, npv
from tea.framework.learning import cost_multiplier
from tea.framework.uncertainty import breakeven, percentile


def test_learning_at_and_before_noak():
    assert cost_multiplier(300, 300, 0.6, 0.2) == pytest.approx(0.6)
    assert cost_multiplier(1000, 300, 0.6, 0.2) == pytest.approx(0.6)  # no learning past NOAK
    # half the experience = one doubling short of NOAK -> 1/(1-0.2) higher
    assert cost_multiplier(150, 300, 0.6, 0.2) == pytest.approx(0.6 / 0.8)
    assert cost_multiplier(10, 300, 0.6, 0.0) == pytest.approx(0.6)


def test_irr_matches_npv_zero():
    cash = [-100, 30, 40, 50, 20]
    r = irr(cash)
    assert npv(r, cash) == pytest.approx(0, abs=1e-6)
    assert irr([1, 2, 3]) is None


def test_breakeven_and_percentile():
    assert breakeven({"x": 0}, "x", lambda v: 2 * v["x"] - 3, 0, 0, 10) == pytest.approx(1.5)
    assert breakeven({"x": 0}, "x", lambda v: v["x"] + 1, 0, 0, 10) is None
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
