from pathlib import Path

import pytest

from tea.cold_bank_cooling import breakeven_unit_cost, compare
from tea.inputs import base_values, load_params

INPUTS = Path(__file__).resolve().parents[1] / "inputs" / "cold_bank_cooling.toml"


@pytest.fixture
def v():
    return base_values(load_params(INPUTS))


def test_bau_by_hand(v):
    c = compare(v)
    # 300 kW_th x 1.25 x $400 + 75 kW_e x $1,500
    assert c.bau.capex == pytest.approx(150_000 + 112_500)
    # 300 MWh_th / COP 4 x $90
    assert c.bau.electricity == pytest.approx(6_750)


def test_hybrid_has_higher_capex_and_lower_energy_cost(v):
    c = compare(v)
    assert c.hybrid.capex > c.bau.capex
    assert c.hybrid.electricity < c.bau.electricity


def test_size_is_the_larger_of_energy_and_peak(v):
    c = compare(v)
    assert c.replace.thermosiphons == pytest.approx(max(c.units_energy_limited, c.units_peak_limited), abs=1)


def test_breakeven_unit_cost_equalizes(v):
    be = breakeven_unit_cost(v)
    c = compare({**v, "cold_bank.unit_cost": be})
    assert c.replace.annual_cost == pytest.approx(c.bau.annual_cost, rel=1e-3)


def test_cheaper_thermosiphons_help(v):
    cheap = compare({**v, "cold_bank.unit_cost": 5000})
    dear = compare({**v, "cold_bank.unit_cost": 40000})
    assert cheap.replace.annual_cost < dear.replace.annual_cost
