import numpy as np
import pytest

from geowell_tea.coaxial import Coaxial, CoaxialDesign
from geowell_tea.fluids import water_rho
from geowell_tea.geology import Geology
from geowell_tea.rock import RockField
from geowell_tea.wellbore import Well

GEO = Geology.linear(1737, 12, 80)
WELL = Well(casing_id=0.15)


def _solve(design, m=None, T_in=None):
    rf = RockField(GEO, WELL.r_b, n_z=40)
    cx = Coaxial(design, WELL, GEO.depth, rf.z, rf.dz)
    r = rf.response(30 * 86400.0)
    q, T_a, T_c, Q, c = cx.solve(r, m or design.m_dot, T_in if T_in is not None else design.T_in)
    return cx, q, T_a, T_c, Q, c


def test_fluid_energy_equals_rock_heat():
    cx, q, T_a, T_c, Q, c = _solve(CoaxialDesign(m_dot=3, T_in=10))
    assert Q == pytest.approx(3 * c["cp"] * (T_c[0] - 10), rel=1e-9)


def test_pump_power_units_and_no_static_head():
    cx, q, T_a, T_c, Q, c = _solve(CoaxialDesign(m_dot=3, T_in=10))
    W, dp = cx.pump_power(3.0, T_a, T_c, c)
    # static head rho*g*L ~ 170 bar would imply > 85 kW; friction-only must be far below
    assert dp < 10e5
    assert W == pytest.approx(dp * 3.0 / c["rho"] / cx.d.pump_eff, rel=1e-9)


def test_buoyancy_helps_circulation():
    cx, q, T_a, T_c, Q, c = _solve(CoaxialDesign(m_dot=1.0, T_in=10))
    assert np.sum(water_rho(T_a) - water_rho(T_c)) > 0  # cold annulus heavier than warm centre


def test_poor_insulation_short_circuits_direct_heat():
    _, _, _, T_vit, _, _ = _solve(CoaxialDesign(m_dot=1.0, T_in=40, k_ins=0.015))
    _, _, _, T_bad, _, _ = _solve(CoaxialDesign(m_dot=1.0, T_in=40, k_ins=0.2))
    assert T_vit[0] > T_bad[0] + 3


def test_tube_must_fit_clearance():
    rf = RockField(GEO, Well(casing_id=0.10).r_b, n_z=10)
    cx = Coaxial(CoaxialDesign(tube_od=0.0889), Well(casing_id=0.10), GEO.depth, rf.z, rf.dz)
    assert cx.status == "INFEASIBLE"
