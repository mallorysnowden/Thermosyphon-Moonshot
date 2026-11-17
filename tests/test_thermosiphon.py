import math
from pathlib import Path

import pytest

from tea.finance import crf, npv
from tea.inputs import base_values, load_params
from tea.thermosiphon import run

INPUTS = Path(__file__).resolve().parents[1] / "inputs" / "thermosiphon_base.toml"


@pytest.fixture
def v():
    return base_values(load_params(INPUTS))


def test_crf_known_value():
    # 8%, 20 years -> 0.10185
    assert crf(0.08, 20) == pytest.approx(0.101852, rel=1e-5)


def test_npv_simple():
    assert npv(0.10, [110.0]) == pytest.approx(100.0)


def test_base_case_matches_spreadsheet(v):
    # Values from the Claude Sheets version of this model (Nov 17, 2026).
    res = run(v)
    assert res.npv == pytest.approx(31_127_477.69, abs=1)
    assert res.years[4].revenue == pytest.approx(36_676_000)
    assert res.foundations.revenue == pytest.approx(25_500_000)
    assert res.cold_bank.revenue == pytest.approx(9_000_000)
    assert res.cold_bank.customer_cost_chiller == pytest.approx(101.435, rel=1e-4)
    assert res.cold_bank.customer_cost_cold_bank == pytest.approx(88.827, rel=1e-4)


def test_no_sales_loses_only_operating_cost(v):
    v = {**v, "foundations.dc_mw_per_year": 0, "cold_bank.dc_mw_per_year": 0,
         "remote_sites.sites_per_year": 0, "glacier.grants": 0}
    res = run(v)
    expected = -sum(v["general.operating_cost"] / 1.1 ** y for y in range(1, 11))
    assert res.npv == pytest.approx(expected)


def test_more_cold_per_unit_raises_margin(v):
    low = run({**v, "cold_bank.mwh_per_unit": 5}).cold_bank.gross_margin
    high = run({**v, "cold_bank.mwh_per_unit": 20}).cold_bank.gross_margin
    assert high > low


def test_every_input_has_a_source():
    for p in load_params(INPUTS).values():
        assert p.source, f"{p.key} has no source"
        if p.low is not None and p.high is not None and not isinstance(p.base, list):
            assert p.low <= p.base <= p.high, p.key
