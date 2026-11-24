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


def test_month_and_demand_charge_by_hand():
    from icebank_tea.cases import CASES, month_of_doy
    from icebank_tea.run import demand_cost
    assert list(month_of_doy(np.array([0, 30, 31, 151, 364]))) == [0, 0, 1, 5, 11]
    c = CASES["D"]  # $15.38 Jun-Sep, $11.03 otherwise
    peaks = np.full((3, 12), 200.0)  # 200 kWe every month, three years
    assert demand_cost(peaks, c) == pytest.approx(200 * (4 * 15.38 + 8 * 11.03))


def test_backup_peak_tracks_unmet_draw():
    # Warm store, no freezing: every hour is unmet, so the monthly peak backup draw is load / COP
    from icebank_tea.store import Design, ElecInputs, Physics, simulate
    n = 184 * 24 + 8760
    t = np.full(n, 25.0)
    load = np.full(n, 1e5)
    month = np.zeros(n, dtype=int)
    sim = simulate([Design(1.0, 12.0, 10.0)], np.array([10.0]), t, load, t_use_max=0.0, ground_c=8.0,
                   phys=Physics(t_water_start=20.0),
                   el=ElecInputs(month=month, onpk=np.zeros(n, bool), kwe_per_w=np.full(n, 1 / 5e3), peak_w=0.0))
    e = sim.elec["full"]  # pumps serve nothing (store unusable), so the draw is the backup chiller
    assert max(e["pk_on"][0, 0, 0], e["pk_off"][0, 0, 0]) == pytest.approx(1e5 / 5e3)


def test_tower_water_cost_by_hand():
    from icebank_tea.cases import CASES
    from icebank_tea.costs import CostInputs
    from icebank_tea.run import water_usd_per_mwh_rejected
    ci = CostInputs()
    b = CASES["B"]  # Minneapolis: sewer billed on all water used
    makeup = 1.6 * 4 / 3  # evaporation + blowdown at 4 cycles, m3 per MWh rejected
    assert water_usd_per_mwh_rejected(b, ci) == pytest.approx(makeup * (b.water_usd_m3 + 0.15 + b.sewer_usd_m3))
    assert water_usd_per_mwh_rejected(CASES["A"], ci) == 0.0  # air-cooled: no water


def test_dry_cooler_cools_warm_water_toward_air():
    # Warm pit, cool air, no load: a dry cooler adds sensible recharge on top of the thermosiphons
    from icebank_tea.store import Design, ElecInputs, Physics, simulate
    n = 8760
    t = np.where(np.arange(n) < 24 * 30, 10.0, 30.0)  # 30 cool days, then warm (no further cooling possible)
    el = ElecInputs(month=np.zeros(n, int), onpk=np.zeros(n, bool), kwe_per_w=np.full(n, 2e-4), peak_w=1e6)
    phys = Physics(t_water_start=25.0, u_cover=0.0, u_ground=0.0)
    kw = dict(t_use_max=27.0, ground_c=10.0, phys=phys, warmup_hours=0, el=el)
    with_dc = simulate([Design(1.0, 12.0, 10.0, dc_frac=0.3)], np.array([100.0]), t, np.zeros(n), **kw)
    no_dc = simulate([Design(1.0, 12.0, 10.0, dc_frac=0.0)], np.array([100.0]), t, np.zeros(n), **kw)
    assert with_dc.dc_mwh.sum() > 0 and no_dc.dc_mwh.sum() == 0
    removed = lambda s: s.frozen_mwh.sum() + s.dc_mwh.sum()
    # either way the water can't be cooled below the air, so total heat removed is capped at (25 - 10) K
    cap_mwh = 100 * 1000 * 4186 * 10.0 * 15.0 / 3.6e9
    assert removed(no_dc) < removed(with_dc) <= cap_mwh * 1.001

