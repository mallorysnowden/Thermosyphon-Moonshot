"""Published-benchmark cross-checks.

Only comparisons whose inputs are actually available in this session are run.
Each benchmark reports what was compared, the model result, the published
value, and why they may differ.  Nothing here is a calibration: no model
parameter is tuned to match these numbers.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.special import exp1

from .coaxial import CoaxialDesign
from .geology import Geology
from .rock import RockField
from .simulate import Architecture, SimSettings, simulate
from .surfaces import SurfaceParams
from .thermosiphon import Thermosiphon, ThermosiphonDesign
from .wellbore import Well


def rock_line_source_check(k=2.5, q=50.0, years=20) -> dict:
    """Constant-flux extraction vs the infinite line-source solution."""
    geo = Geology.linear(1000, 20, 20, k=k)
    rf = RockField(geo, 0.1, n_z=2, n_r=40, r_far=300)
    dt = 7 * 86400.0
    errs = {}
    t = 0.0
    for i in range(52 * years):
        rf.response(dt)
        rf.apply(np.full(2, q))
        t += dt
        if (i + 1) in (52, 520, 1040):
            Tw = rf.wall_temperature(np.full(2, q))[0]
            ana = 20 - q / (4 * math.pi * k) * exp1(0.1 ** 2 / (4 * geo.alpha * t))
            errs[f"year_{(i + 1) // 52}"] = dict(model=Tw, analytic=ana, error_K=Tw - ana)
    errs["energy_residual"] = (rf.cum_extracted_J - rf.energy_deficit_J()) / rf.energy_deficit_J()
    return errs


def _run_ts_days(geo, well, design, days, dt_days=1.0, n_z=60):
    rf = RockField(geo, well.r_b, n_z=n_z, n_r=40)
    ts = Thermosiphon(design, well, geo.depth, rf.z, rf.dz)
    ts.mechanical_checks(geo.T_bottom)
    Qs = []
    for _ in range(int(days / dt_days)):
        r = rf.response(dt_days * 86400)
        q, Q, aux = ts.capability(r)
        rf.apply(q)
        Qs.append(Q)
    return np.array(Qs), ts


def xiongan_d34(k_values=(2.5, 3.5)) -> list[dict]:
    """Huang et al. (2024) EES: 4,149 m ammonia SLGHP in well D34, Xiong'an.

    Published 40-day averages: 1049 kW @ 36.8 C, 596 kW @ 52.8 C, 442 kW @ 59.3 C
    (production temperature).  Our approximation: single 177.8 mm string (the
    real pipe steps 244.5/177.8/127.0 mm), casing 244.5 mm (ID ~0.224 m),
    water-filled annulus, guided condensate (ladder design), uninsulated, rock
    conductivity unknown (two values).  Two temperature profiles bracket the
    paper's internally inconsistent gradient vs bottom-hole numbers."""
    published = [(36.8, 1049.0), (52.8, 596.0), (59.3, 442.0)]
    profiles = {
        "stated gradients (2.73 then 1.23 C/100m)": ([0, 25, 3455, 4149], [14.5, 15.0, 15.0 + 0.0273 * 3430,
                                                                          15.0 + 0.0273 * 3430 + 0.0123 * 694]),
        "anchored to 131.8 C BHT at 4507 m": ([0, 25, 3455, 4507], [14.5, 15.0, 15.0 + 0.0273 * 3430, 131.8]),
    }
    well = Well(casing_id=0.224, casing_wall=0.0105, cement_thickness=0.03)
    out = []
    variants = [(f"conduction k={k}", k, None, False) for k in k_values]
    variants += [("conduction k=2.5, upper section insulated", 2.5, None, True),
                 ("convective-reservoir proxy: k_eff=10 below 3455 m", 2.5, [(3455.0, 10.0)], False)]
    for pname, (zs, Ts) in profiles.items():
        for vname, k, layers, insulate in variants:
            T4149 = float(np.interp(4149, zs, Ts))
            geo = Geology(depth=4149.0, profile_z=list(zs[:-1]) + [4149.0], profile_T=list(Ts[:-1]) + [T4149], k=k,
                          k_layers=layers)
            for T_top, Q_pub in published:
                L_ins = geo.depth_at_temperature(T_top) if insulate else 0.0
                d = ThermosiphonDesign(fluid="ammonia", T_top=T_top, liquid_distribution="guided",
                                       gap=(0.224 - 0.1778) / 2, insulated_length=L_ins)
                Qs, ts = _run_ts_days(geo, well, d, 40)
                out.append(dict(benchmark="Xiong'an D34 (Huang et al. 2024)", profile=pname, variant=vname,
                                T_top=T_top, model_kW_40d=float(Qs.mean() / 1e3), published_kW_40d=Q_pub,
                                ratio=float(Qs.mean() / 1e3 / Q_pub), status=ts.status,
                                flags="; ".join(ts.flags)))
    return out


def penn_state_sanity(case) -> list[dict]:
    """Penn State (2025) reports a modelled 120 kW closed-loop capacity for the
    5,700 ft / 80 C well.  Their inlet temperature, flow, tube and duration are
    not available here, so we report our coaxial resource-mode output at a few
    operating points instead of matching a single number."""
    out = []
    sim = SimSettings(years=20, n_z=50)
    for T_in, m in ((10, 3.0), (20, 3.0), (30, 3.0)):
        a = Architecture("C_HP", coax=CoaxialDesign(tube_od=0.1143, tube_id=0.076, m_dot=m, T_in=T_in))
        r = simulate(a, case.geology, case.well, case.surface, None, sim)
        s = r.summary()
        out.append(dict(benchmark="Penn State 2025 120 kW (different closed-loop design)", T_in=T_in, m_dot=m,
                        model_kW_y1=s["geo_capability_kW_y1"], model_kW_y20=s["geo_capability_kW_y20"],
                        published_kW=120.0))
    return out


def taiyuan_order_of_magnitude() -> list[dict]:
    """Chen et al. (2024): two SLGHPs (2,020 and 2,180 m) ~30 m apart, ~63 C at
    2,000 m, system 'can output 1 MW of heat' (with a heat pump).  Diameters and
    condenser temperatures are not in the abstract; groundwater crossflow boosted
    the longer well.  We report a conduction-only two-pipe estimate over 120 days
    for an assumed 0.20 m casing and 15 C condenser."""
    out = []
    for L in (2020.0, 2180.0):
        T_b = 12.0 + (63.0 - 12.0) * L / 2000.0
        geo = Geology.linear(L, 12.0, T_b, k=2.5)
        well = Well(casing_id=0.20)
        d = ThermosiphonDesign(fluid="ammonia", T_top=15.0, liquid_distribution="guided")
        Qs, ts = _run_ts_days(geo, well, d, 120, dt_days=5)
        out.append(dict(benchmark="Taiyuan SLGHP (Chen et al. 2024)", length_m=L,
                        model_geo_kW_120d=float(Qs.mean() / 1e3), status=ts.status))
    total = sum(r["model_geo_kW_120d"] for r in out)
    cop = 4.0
    out.append(dict(benchmark="Taiyuan system total", model_geo_kW_120d=total,
                    model_system_heat_kW_at_COP4=total * cop / (cop - 1), published_system_heat_kW=1000.0))
    return out


NOT_REPRODUCED = [
    dict(benchmark="Zolfagharroshan et al. 2024 (10.69/14.04/15.54 kW, 150/200/250 m, pentane)",
         status="NOT ATTEMPTED",
         reason="The brief says the full PDF was supplied, but only the brief and an unrelated lunar paper were "
                "present in this session. The site temperature profile, rock properties and coil boundary "
                "conditions needed to reproduce the 20-year means are not available; guessing them would be "
                "calibration to a target, which the brief forbids."),
    dict(benchmark="Gruber et al. 2026 (150 vs 185 kW, 1,800 m ammonia, packer)",
         status="NOT ATTEMPTED",
         reason="Full paper not present in this session; its logistic temperature profile and packer geometry are "
                "required. The patented packer (SI23618A) is not implemented as a default product."),
    dict(benchmark="Ma et al. 2024 / Huang et al. 2021 (power-generation SLGHP vs DHE)",
         status="CONTEXT ONLY", reason="Electricity-generation economics; not transferable to heat LCOH."),
]
