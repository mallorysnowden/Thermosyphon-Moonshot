import numpy as np

from geowell_tea.geology import Geology
from geowell_tea.rock import RockField
from geowell_tea.thermosiphon import FEASIBLE, INFEASIBLE, Thermosiphon, ThermosiphonDesign
from geowell_tea.wellbore import Well, collapse_pressure, required_wall

GEO = Geology.linear(1737, 12, 80)
WELL = Well(casing_id=0.15)


def _first_step(design, geo=GEO, well=WELL):
    rf = RockField(geo, well.r_b, n_z=40)
    ts = Thermosiphon(design, well, geo.depth, rf.z, rf.dz)
    ts.mechanical_checks(geo.T_bottom)
    r = rf.response(30 * 86400.0)
    q, Q, aux = ts.capability(r)
    return ts, q, Q, aux, r


def test_vapour_head_raises_bottom_saturation_temperature():
    ts, q, Q, aux, _ = _first_step(ThermosiphonDesign(T_top=50, insulated_length=960))
    assert aux["Tsat"][-1] > 50 + 3.0  # ~5 K for ammonia over 1.7 km


def test_uninsulated_direct_mode_loses_heat_to_shallow_rock():
    ts, q, Q, aux, r = _first_step(ThermosiphonDesign(T_top=50, insulated_length=0))
    q_raw, _, _ = ts._profile(r, 50.0)
    assert np.any(q_raw < 0)  # parasitic condensation in the cold upper section
    assert Q == 0.0  # net heat to the condenser is not positive: delivers nothing
    ts_i, q_i, Q_i, _, _ = _first_step(ThermosiphonDesign(T_top=50, insulated_length=960))
    assert Q_i > 0


def test_heavy_vapour_fluid_has_larger_head_penalty():
    _, _, _, a_nh3, _ = _first_step(ThermosiphonDesign(fluid="ammonia", T_top=50, insulated_length=960))
    _, _, _, a_c4, _ = _first_step(ThermosiphonDesign(fluid="isobutane", T_top=50, insulated_length=960))
    assert (a_c4["Tsat"][-1] - 50) > (a_nh3["Tsat"][-1] - 50)


def test_co2_cannot_condense_above_critical():
    ts, *_ = _first_step(ThermosiphonDesign(fluid="co2", T_top=40))
    assert ts.status == INFEASIBLE


def test_small_bore_high_duty_is_throttled_not_failed():
    """A transport limit is an operating limit: the condenser is throttled (T_top raised) until the
    flooding / Mach limit is met, rather than the design being declared infeasible."""
    geo = Geology.linear(3000, 7, 110)
    d = ThermosiphonDesign(fluid="ammonia", T_top=10, liquid_distribution="film", insulated_length=1500)
    ts, q, Q, aux, r = _first_step(d, geo=geo, well=Well(casing_id=0.127))
    assert ts.throttled_steps > 0
    assert aux["T_top"] > d.T_top
    fmax, mach, _ = ts._limits(aux)
    assert fmax <= 1.0 + 1e-3 and mach <= 0.7 + 1e-3
    q_free, _, _ = ts._profile(r, d.T_top)
    assert Q < np.sum(q_free) * ts.dz  # throttling reduces the delivered heat


def test_packer_architecture_is_guided_and_ip_flagged():
    d = ThermosiphonDesign(T_top=40, insulated_length=900, architecture="packer", liquid_distribution="film")
    ts, q, Q, aux, _ = _first_step(d)
    assert ts.d.liquid_distribution == "guided"
    assert any(f.startswith("IP:") for f in ts.flags)
    assert Q > 0


def test_ammonia_vapour_head_costs_output():
    on = _first_step(ThermosiphonDesign(T_top=40, insulated_length=900, vapor_head=True))[2]
    off = _first_step(ThermosiphonDesign(T_top=40, insulated_length=900, vapor_head=False))[2]
    assert off > on > 0


def test_stagnation_transfer_is_zero_sum():
    ts, q, Q, aux, r = _first_step(ThermosiphonDesign(T_top=25))
    q_s, T_s = ts.stagnation(r)
    assert abs(np.sum(q_s)) < 1e-6
    assert T_s > 25
    assert q_s[0] < 0 < q_s[-1]  # heat flows from deep to shallow rock


def test_collapse_wall_grows_with_depth():
    t1 = required_wall(0.134, 1000 * 9.81 * 1500)
    t2 = required_wall(0.134, 1000 * 9.81 * 4000)
    assert t2 >= t1
    assert collapse_pressure(0.134, t2) >= 1.125 * 1000 * 9.81 * 4000


def test_guided_return_reaches_bottom_wetted():
    ts, q, Q, aux, _ = _first_step(ThermosiphonDesign(T_top=20, liquid_distribution="guided"))
    assert np.all(aux["wet"] == 1.0)
    ts_f, *_ = _first_step(ThermosiphonDesign(T_top=20, liquid_distribution="film"))
    assert ts_f.min_wet < 1.0
