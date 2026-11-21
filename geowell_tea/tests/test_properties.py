"""Property substitute (Peng-Robinson + Rackett / IF97) vs reference values.

Reference values are standard saturated-property figures (rounded) from
common tables; tolerances reflect the screening use of these properties."""
import pytest

from geowell_tea.fluids import FLUIDS, liquid_density, pr_saturation, saturation_table, water_saturation

REF = [
    # fluid, T [K], Psat [bar], rho_v [kg/m3], h_fg [kJ/kg]
    ("ammonia", 273.15, 4.294, 3.457, 1262),
    ("ammonia", 323.15, 20.33, 15.6, 1050),
    ("propane", 293.15, 8.36, 18.0, 342),
    ("isobutane", 293.15, 3.02, 7.9, 334),
    ("co2", 273.15, 34.85, 97.6, 231),
    ("pentane", 298.15, 0.684, 2.0, 366),
]


@pytest.mark.parametrize("fluid,T,P,rv,h", REF)
def test_peng_robinson_saturation(fluid, T, P, rv, h):
    P_m, rv_m, h_m = pr_saturation(FLUIDS[fluid], T)
    assert P_m / 1e5 == pytest.approx(P, rel=0.03)
    assert rv_m == pytest.approx(rv, rel=0.05)
    assert h_m / 1e3 == pytest.approx(h, rel=0.06)


@pytest.mark.parametrize("T,P,h", [(373.15, 1.01325, 2257), (323.15, 0.1235, 2383), (293.15, 0.02339, 2454)])
def test_water_if97(T, P, h):
    P_m, rv, h_m = water_saturation(T)
    assert P_m / 1e5 == pytest.approx(P, rel=0.003)
    assert h_m / 1e3 == pytest.approx(h, rel=0.01)


def test_rackett_liquid_density():
    assert float(liquid_density(FLUIDS["ammonia"], 298.15)) == pytest.approx(602.8, rel=0.02)
    assert float(liquid_density(FLUIDS["propane"], 298.15)) == pytest.approx(493, rel=0.02)
    assert float(liquid_density(FLUIDS["water"], 298.15)) == pytest.approx(997, rel=0.01)


def test_table_inverse_consistency():
    t = saturation_table("ammonia")
    for T in (260.0, 300.0, 350.0):
        assert float(t.tsat(t.psat(T))) == pytest.approx(T, abs=0.05)


def test_critical_point_rejected():
    with pytest.raises(ValueError):
        pr_saturation(FLUIDS["co2"], 310.0)
