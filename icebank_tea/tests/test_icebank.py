"""Hand-checkable tests for the ice-bank TEA."""
import math

import numpy as np
import pytest

from icebank_tea.costs import CostInputs, crf, unit_bom, wall_m
from icebank_tea.store import KWH_PER_M3_ICE, K_ICE, L_F, RHO_ICE, Design, Physics, simulate


def test_crf_by_hand():
    # 8%, 20 years: 0.08 * 1.08**20 / (1.08**20 - 1) = 0.10185
    assert crf(0.08, 20) == pytest.approx(0.10185, abs=1e-5)


def test_latent_heat_of_ice_per_m3():
    assert KWH_PER_M3_ICE == pytest.approx(917 * 334e3 / 3.6e6)
    assert KWH_PER_M3_ICE == pytest.approx(85.1, abs=0.1)


def test_wall_and_unit_cost_by_hand():
    d = Design(1.0, 25.0, 10.0)
    c = CostInputs()
    assert wall_m(d, c) * 1e3 == pytest.approx(2.6 * 80 / (2 * 43), rel=1e-6)  # 2.42 mm
    b = unit_bom(d, c)
    tube = math.pi * 0.08 * wall_m(d, c) * 12.0 * 2700
    al = tube + 25 * 0.474 + 1.0
    hand = (al * 5.3 + 0.033 * 9 * 0.6) * 2.5 + 4.0 * (1375 / 907.2) * 2.5 + (8000 / 16 / 36 + 200 / 36)
    assert b["unit_usd"] == pytest.approx(hand, rel=1e-9)
    assert b["field_joint_usd"] == 0.0  # 12 m unit ships sealed
    assert unit_bom(Design(1.0, 25.0, 15.0), c)["field_joint_usd"] == c.field_joint_usd


def test_ice_growth_matches_closed_form():
    """Constant -10 degC, ice conduction in series with fixed condenser + boiling resistance R_ext.
    Quasi-steady: t(R) = rho L / dT * [ (R^2 ln(R/r0)/2 - (R^2 - r0^2)/4) / k + pi L_e R_ext (R^2 - r0^2) ]."""
    d = Design(pitch_m=3.0, cond_area_m2=25.0, depth_m=10.0)
    phys = Physics(head_k_per_m=0.0, u_cover=0.0, u_ground=0.0, t_water_start=0.0)
    hours = 8760
    sim = simulate([d], np.array([1.0]), np.full(hours, -10.0), np.zeros(hours), 1.0, 0.0, phys, warmup_hours=0)
    L, r0 = d.evap_len_m, d.r_out_m
    R = math.sqrt(sim.end_ice_frac[0] * d.pitch_m**2 * L / (math.pi * L) + r0**2)
    r_ext = 1 / (phys.u_cond * d.cond_area_m2) + 1 / (phys.h_evap * 2 * math.pi * d.r_in_m * L)
    t_closed = RHO_ICE * L_F / 10.0 * ((R**2 * math.log(R / r0) / 2 - (R**2 - r0**2) / 4) / K_ICE
                                       + math.pi * L * r_ext * (R**2 - r0**2))
    assert t_closed / 3600 == pytest.approx(hours, rel=0.02)


def test_energy_balance_no_load():
    """Cold charged = sensible cooling of the water to 0 degC + latent heat of the ice made."""
    d = Design(pitch_m=1.0, cond_area_m2=25.0, depth_m=10.0)
    phys = Physics(u_cover=0.0, u_ground=0.0, t_water_start=4.0)
    hours = 8760
    t = np.full(hours, -8.0)
    t[: 24 * 30] = 5.0  # a warm first month: nothing freezes
    sim = simulate([d], np.array([1.0]), t, np.zeros(hours), 1.0, 0.0, phys, warmup_hours=0)
    v_water = d.pitch_m**2 * d.depth_m
    sensible_mwh = 1000 * 4190 * v_water * 4.0 / 3.6e9
    latent_mwh = sim.end_ice_frac[0] * d.pitch_m**2 * d.evap_len_m * KWH_PER_M3_ICE / 1e3
    assert sim.frozen_mwh[0, 0] == pytest.approx(sensible_mwh + latent_mwh, rel=1e-3)


def test_load_is_unmet_when_store_is_empty_and_warm():
    d = Design(pitch_m=1.0, cond_area_m2=25.0, depth_m=10.0)
    phys = Physics(t_water_start=20.0, u_cover=0.0, u_ground=0.0)
    hours = 8760
    sim = simulate([d], np.array([1.0]), np.full(hours, 20.0), np.full(hours, 1000.0), 5.0, 10.0, phys,
                   warmup_hours=0)
    assert sim.unmet_mwh[0, 0] == pytest.approx(8.76, rel=1e-6)  # 1 kW all year, nothing served
