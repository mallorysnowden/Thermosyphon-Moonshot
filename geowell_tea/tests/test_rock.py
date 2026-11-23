import math

import numpy as np
from scipy.special import exp1

from geowell_tea.geology import Geology
from geowell_tea.rock import RockField


def test_line_source_agreement_after_one_year():
    k, q = 2.5, 50.0
    geo = Geology.linear(1000, 20, 20, k=k)
    rf = RockField(geo, 0.1, n_z=2, n_r=40, r_far=300)
    dt = 7 * 86400.0
    for _ in range(52 * 5):
        rf.response(dt)
        rf.apply(np.full(2, q))
    t = 52 * 5 * dt
    ana = 20 - q / (4 * math.pi * k) * exp1(0.1 ** 2 / (4 * geo.alpha * t))
    assert abs(rf.wall_temperature(np.full(2, q))[0] - ana) < 0.05


def test_energy_conservation_exact():
    geo = Geology.linear(2000, 10, 70)
    rf = RockField(geo, 0.1, n_z=20, n_r=30)
    rng = np.random.default_rng(0)
    for _ in range(50):
        rf.response(30 * 86400.0)
        rf.apply(rng.uniform(-20, 80, 20))
    assert abs(rf.cum_extracted_J - rf.energy_deficit_J()) / abs(rf.energy_deficit_J()) < 1e-9


def test_mesh_and_timestep_convergence():
    geo = Geology.linear(1000, 30, 30)
    vals = []
    for n_r, dt_days in ((24, 30.0), (48, 7.5)):
        rf = RockField(geo, 0.1, n_z=1, n_r=n_r)
        steps = int(365 * 5 / dt_days)
        for _ in range(steps):
            rf.response(dt_days * 86400)
            rf.apply(np.array([60.0]))
        vals.append(rf.wall_temperature(np.array([60.0]))[0])
    assert abs(vals[0] - vals[1]) < 0.1


def test_far_field_does_not_resupply_heat():
    """Adiabatic outer boundary: a small domain depletes faster than a large one."""
    geo = Geology.linear(1000, 30, 30)
    out = []
    for r_far in (20.0, 200.0):
        rf = RockField(geo, 0.1, n_z=1, n_r=36, r_far=r_far)
        for _ in range(240):
            rf.response(365.25 / 12 * 86400)
            rf.apply(np.array([60.0]))
        out.append(rf.wall_temperature(np.array([60.0]))[0])
    assert out[0] < out[1] - 0.5


def test_layered_conductivity_uses_layer_values():
    geo = Geology.linear(1000, 30, 30, k=2.0, k_layers=[(500.0, 4.0)])
    rf = RockField(geo, 0.1, n_z=10, n_r=30)
    r = rf.response(30 * 86400.0)
    assert r.R_rock[0] > r.R_rock[-1]
