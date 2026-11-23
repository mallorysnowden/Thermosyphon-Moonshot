"""Correlations and boundary conditions added from Zolfagharroshan 2024 and Gruber 2026."""
import numpy as np

from geowell_tea.correlations import cooper, helical_coil_h, imura, nusselt_condensation
from geowell_tea.fluids import saturation_table
from geowell_tea.geology import Geology
from geowell_tea.rock import RockField
from geowell_tea.thermosiphon import CoilCondenser, Thermosiphon, ThermosiphonDesign, coupled_capability
from geowell_tea.wellbore import Well

NH3 = saturation_table("ammonia")


def test_cooper_rises_with_heat_flux_and_pressure():
    h1 = cooper(NH3, 273.15 + 30, 2000.0, 1.0)
    h2 = cooper(NH3, 273.15 + 30, 8000.0, 1.0)
    h3 = cooper(NH3, 273.15 + 60, 2000.0, 1.0)
    assert h2 / h1 == np.clip(h2 / h1, 4 ** 0.67 * 0.99, 4 ** 0.67 * 1.01)
    assert h3 > h1 > 100.0


def test_nusselt_condensation_falls_with_length_and_flux():
    a = nusselt_condensation(NH3, 273.15 + 40, 2000.0, 2.0)
    b = nusselt_condensation(NH3, 273.15 + 40, 2000.0, 20.0)
    c = nusselt_condensation(NH3, 273.15 + 40, 8000.0, 2.0)
    assert a > b > 0 and a > c


def test_imura_positive():
    assert imura(NH3, 273.15 + 40, 3000.0) > 100.0


def test_helical_coil_matches_zolfagharroshan_table_within_10pct():
    """Zolfagharroshan 2024 report Nu ~ 276 / 491 / 687 at 7.5 / 15 / 22.5 L/min (published)."""
    for lpm, nu_pub in ((7.5, 276.0), (15.0, 491.0), (22.5, 687.0)):
        h, nu, re, dp = helical_coil_h(lpm / 60e3, 0.0060, 0.1175, 70.0)
        assert abs(nu / nu_pub - 1) < 0.10


def test_coupled_condenser_balances_pipe_and_coil():
    geo = Geology.linear(250, 15, 22.5)
    well = Well(casing_id=0.1222, casing_wall=0.001, cement_thickness=0.02, k_cement=1.5)
    rf = RockField(geo, well.r_b, n_z=40, far_field="dirichlet")
    ts = Thermosiphon(ThermosiphonDesign(fluid="water", T_top=20, check_mechanics=False,
                                         liquid_distribution="guided"), well, geo.depth, rf.z, rf.dz)
    cond = CoilCondenser(T_in=5.0)
    q, Q, T_top = coupled_capability(ts, rf.response(86400.0 * 30), cond)
    assert Q > 0
    assert abs(cond.heat_removed(ts.sat, T_top) - Q) / Q < 0.05


def test_dirichlet_far_field_energy_balance():
    geo = Geology.linear(1000, 10, 45)
    rf = RockField(geo, 0.12, n_z=20, n_r=24, r_far=20.0, far_field="dirichlet")
    extracted = 0.0
    for _ in range(60):
        q = np.full(rf.n_z, 40.0)
        rf.response(30 * 86400.0)
        rf.apply(q)
        extracted += q.sum() * rf.dz * 30 * 86400.0
    bal = rf.energy_deficit_J() + rf.far_field_inflow_J
    assert rf.far_field_inflow_J > 0
    assert abs(bal - extracted) / extracted < 0.02


def test_insulation_options_order_and_bore():
    """Factory aerogel in a N2-capped annulus insulates far better than water; N2 alone keeps full bore."""
    from geowell_tea.geology import Geology
    from geowell_tea.wellbore import Well
    geo = Geology.linear(1700, 12, 80)
    well = Well(casing_id=0.150)
    rf = RockField(geo, well.r_b, n_z=34)
    R = {}
    for ins in ("aerogel_n2", "n2_only", "pip", "vit_liner"):
        ts = Thermosiphon(ThermosiphonDesign(T_top=42, insulated_length=850, insulation=ins), well, geo.depth, rf.z, rf.dz)
        R[ins] = float(ts.R_static[0])
        if ins == "n2_only":
            assert ts.geom.d_i_ins == ts.geom.d_i
        if ins == "aerogel_n2":
            assert ts.ins_t == 0.005 and ts.geom.d_i_ins < ts.geom.d_i
    R_water = float(ts.R_static[-1])
    assert R["aerogel_n2"] > R["n2_only"] > R_water


def test_cost_levels_ordered():
    from geowell_tea.costs import capex_breakdown
    from geowell_tea.schema import load_case
    p = load_case("case_a_pa.yaml").params
    q = dict(depth_m=1700, steel_kg=30000, insulated_m=0, guided=True, inventory_kg=400, fluid="ammonia",
             peak_geo_W=1.2e5, peak_useful_W=1.5e5, peak_pump_W=1e3, distance_m=250, direct_coupled=True)
    tot = {lvl: sum(capex_breakdown("T_HP", q, dict(p, ts_cost_level=lvl)).values()) for lvl in ("foak", "base", "noak")}
    assert tot["foak"] > tot["base"] > tot["noak"]
    items = capex_breakdown("T_HP", q, p)
    assert items["secondary_loop"] == 0 and items["hp_direct_coupling"] > 0
