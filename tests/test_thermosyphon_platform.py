from pathlib import Path

import pytest

from tea.finance import crf
from tea.framework.report import write_report
from tea.inputs import base_values, load_meta, load_params
from tea.thermosyphon_platform import COMPONENTS, blended, breakevens, market_values, run

ROOT = Path(__file__).resolve().parents[1]
FILES = (ROOT / "inputs" / "conventions.toml", ROOT / "inputs" / "thermosyphon_platform.toml")


@pytest.fixture
def params():
    out = {}
    for f in FILES:
        out.update(load_params(f))
    return out


@pytest.fixture
def v(params):
    return base_values(params)


def test_cost_shares_sum_to_one(v):
    assert sum(v[f"cost.share_{c}"] for c in COMPONENTS) == pytest.approx(1.0)


def test_noak_blended_cost_by_hand(v):
    noak = {"hardware": 0.6, "install": 0.85, "logistics": 0.9, "engineering": 0.7}
    # 0.8 x (0.3*0.6 + 0.4*0.85 + 0.15*0.9 + 0.15*0.7) = 0.8 x 0.76
    assert blended(v, noak) == pytest.approx(0.608)


def test_first_commercial_year_revenue_by_hand(v):
    res = run(v)
    year3 = res.years[2]
    full = sum(market_values(v).values())
    assert year3.phase == "commercial"
    # 10% ramp x 85% of incumbent price, no installed base yet, plus grants
    assert year3.revenue == pytest.approx(0.1 * full * 0.85 + v["glacier.grants"])


def test_road_incumbent_cost_by_hand(v):
    fu = run(v).functional_units[1].options
    expected = 4_200_000 * (crf(0.08, 30) + 0.01 + 0.01) + 0.25 * 22_000
    assert fu["Incumbent thermosyphons"] == pytest.approx(expected)


def test_no_markets_loses_only_operating_cost(v):
    zero = {**v, "foundations.dc_mw_per_year": 0, "foundations.other_m2_per_year": 0, "remote.sites_per_year": 0,
            "roads.km_per_year": 0, "mining.addressable_per_year": 0, "cold_bank.mw_per_year": 0}
    res = run(zero)
    rd = int(v["company.rd_years"])
    expected = -sum((v["company.rd_opex"] if t <= rd else v["company.commercial_opex"]) / 1.1 ** t
                    for t in range(1, int(v["finance.horizon"]) + 1))
    assert res.npv == pytest.approx(expected)


def test_report_writes_standard_outputs(tmp_path, params, v):
    meta = {}
    for f in FILES:
        meta.update(load_meta(f))
    text = write_report(run(v), params, v, run, tmp_path, meta, breakevens(v), draws=50)
    for section in ("## Headline", "## Customer cost vs BAU", "## FOAK to NOAK", "## Monte Carlo", "## Kill metrics", "## Scorecard"):
        assert section in text
    assert (tmp_path / "cashflow.csv").exists() and (tmp_path / "inputs_used.csv").exists()
