"""End-to-end conservation and invariant tests."""
import numpy as np
import pytest

from geowell_tea.coaxial import CoaxialDesign
from geowell_tea.geology import Geology
from geowell_tea.loads import load_series
from geowell_tea.simulate import Architecture, SimSettings, simulate
from geowell_tea.surfaces import SurfaceParams
from geowell_tea.thermosiphon import ThermosiphonDesign
from geowell_tea.wellbore import Well

GEO = Geology.linear(1737, 12, 80)
WELL = Well(casing_id=0.15)
SURF = SurfaceParams()
SIM = SimSettings(years=3, n_z=30)

ARCHS = [
    Architecture("T_HP", ts=ThermosiphonDesign(T_top=20, liquid_distribution="guided")),
    Architecture("T_DIRECT", ts=ThermosiphonDesign(T_top=50, insulated_length=960)),
    Architecture("T_ADAPTIVE", ts=ThermosiphonDesign(T_top=40, insulated_length=700)),
    Architecture("C_HP", coax=CoaxialDesign(m_dot=3, T_in=10)),
    Architecture("C_DIRECT", coax=CoaxialDesign(m_dot=6, T_in=40, variable_flow_target=50)),
    Architecture("C_ADAPTIVE", coax=CoaxialDesign(m_dot=3, T_in=20)),
]


@pytest.mark.parametrize("arch", ARCHS, ids=lambda a: a.arch_id)
@pytest.mark.parametrize("with_load", [False, True])
def test_rock_energy_matches_delivered_heat(arch, with_load):
    load = load_series(100e3, "western_pa", 5000, SIM.years) if with_load else None
    r = simulate(arch, GEO, WELL, SURF, load, SIM)
    assert abs(r.energy_residual) < 1e-6


@pytest.mark.parametrize("arch", ARCHS, ids=lambda a: a.arch_id)
def test_heat_pump_balance_and_no_free_lift(arch):
    load = load_series(100e3, "western_pa", 5000, SIM.years)
    r = simulate(arch, GEO, WELL, SURF, load, SIM)
    # Q_useful = Q_geo + W_comp exactly (compressor heat ends up in the sink)
    np.testing.assert_allclose(r.Q_useful, r.Q_geo + r.W_comp, rtol=1e-9, atol=1e-6)
    assert np.all(r.W_comp >= -1e-9)
    assert np.all(r.Q_useful <= r.load + 1e-6)  # sales capped at load
    if arch.mode == "DIRECT":
        assert np.all(r.W_comp == 0)
        # no direct heat from a source colder than supply + approach
        too_cold = r.T_source < SURF.T_supply - 1e-9
        assert np.all(r.Q_useful[too_cold] == 0)


def test_no_demand_means_no_electricity_except_controls():
    load = np.zeros(12 * SIM.years)
    for arch in ARCHS:
        r = simulate(arch, GEO, WELL, SURF, load, SIM)
        assert np.all(r.W_comp == 0) and np.all(r.W_pump_source == 0) and np.all(r.W_delivery == 0)
        assert np.all(r.Q_useful == 0)


def test_extraction_cools_rock_and_capability_declines():
    r = simulate(ARCHS[3], GEO, WELL, SURF, None, SimSettings(years=5, n_z=30))
    assert np.all(r.T_rock_wall_final <= r.T_rock_init + 1e-9)
    cap = r.Q_geo_cap.reshape(-1, 12).mean(axis=1)
    assert np.all(np.diff(cap) < 0)


def test_identical_geology_for_both_technologies():
    a, b = ARCHS[0], ARCHS[3]
    ra = simulate(a, GEO, WELL, SURF, None, SIM)
    rb = simulate(b, GEO, WELL, SURF, None, SIM)
    np.testing.assert_array_equal(ra.T_rock_init, rb.T_rock_init)
    assert ra.quantities["depth_m"] == rb.quantities["depth_m"]
