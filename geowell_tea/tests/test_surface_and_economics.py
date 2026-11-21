import numpy as np
import pytest

from geowell_tea.costs import economics
from geowell_tea.loads import monthly_fractions
from geowell_tea.schema import load_case, sample_params
from geowell_tea.surfaces import SurfaceParams, convert, cop

P = SurfaceParams()


def test_cop_uses_kelvin_and_is_bounded():
    c = cop(10.0, 50.0, P)
    assert c == pytest.approx(0.5 * 323.15 / 40.0)
    assert cop(49.0, 50.0, P) <= P.cop_max


def test_direct_only_when_source_hot_enough():
    hot = convert("DIRECT", "TS", 10e3, {"T_top": 55.0}, P)
    cold = convert("DIRECT", "TS", 10e3, {"T_top": 45.0}, P)
    assert hot.Q_useful == 10e3 and hot.W_comp == 0
    assert cold.Q_useful == 0


@pytest.mark.parametrize("mode", ["HP", "ADAPTIVE"])
@pytest.mark.parametrize("tech,src", [("TS", {"T_top": 30.0}), ("C", {"T_out": 35.0, "T_in": 15.0, "m": 1.0, "cp": 4180.0})])
def test_sink_equals_source_plus_work(mode, tech, src):
    Q_geo = 50e3
    r = convert(mode, tech, Q_geo, src, P)
    assert r.Q_useful == pytest.approx(Q_geo + r.W_comp)
    assert r.W_comp > 0 and r.Q_direct <= r.Q_useful


def test_adaptive_beats_pure_hp_on_compressor_work():
    src = {"T_out": 42.0, "T_in": 20.0, "m": 1.0, "cp": 4180.0}
    Q_geo = 1.0 * 4180 * 22
    hp = convert("HP", "C", Q_geo, src, P)
    ad = convert("ADAPTIVE", "C", Q_geo, src, P)
    assert ad.W_comp < hp.W_comp


def test_load_fraction_shape_hits_flh():
    f = monthly_fractions("western_pa", 5000)
    assert f.max() == pytest.approx(1.0)
    assert f.mean() * 8760 == pytest.approx(5000, rel=1e-9)


def test_lcoh_hand_check():
    """One-design LCOH checked by hand: capex + PV(opex) + PV(eol) over PV(MWh)."""
    case = load_case("case_a_pa.yaml")
    p = dict(case.params)
    q = dict(depth_m=1000.0, peak_geo_W=0.0, peak_useful_W=0.0, peak_pump_W=0.0, distance_m=0.0, vit_m=1000.0)
    years = 20
    annual = dict(useful=np.full(years, 100.0), elec=np.zeros(years), backup=np.zeros(years), load=np.full(years, 100.0))
    e = economics("C_DIRECT", q, annual, p)
    capex = sum(e["capex_items"].values())
    r = p["discount_rate"]
    v = 1 / (1 + r) ** np.arange(1, years + 1)
    opex = p["om_common_per_yr"] + p["coax_om_per_yr"]
    repl = e["capex_items"]["circulation_pump"] * 0.5 * v[9]
    expected = (capex + opex * v.sum() + repl + p["plugging_eol"] * v[-1]) / (100.0 * v.sum())
    assert e["lcoh"] == pytest.approx(expected, rel=1e-9)


def test_monte_carlo_draws_within_ranges():
    case = load_case("case_a_pa.yaml")
    d = sample_params(case.params, case.ranges, 300)
    for k, (lo, mid, hi) in case.ranges.items():
        assert np.all(d[k] >= lo - 1e-12) and np.all(d[k] <= hi + 1e-12)


def test_every_parameter_has_provenance_status():
    case = load_case("case_b_nd.yaml")
    assert all(p["status"] in {"published", "assumed", "derived", "measured"} for p in case.provenance)
    assert any(p["status"] == "published" for p in case.provenance)
