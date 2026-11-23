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


def _run_schedule(geo, well, design, steps_days, marks_days, n_z=80, r_far=150.0, far_field="dirichlet",
                  condenser=None):
    """Run a thermosiphon on an arbitrary step schedule; return {mark_day: (Q_kW, T_top_C, loss_kW)}."""
    from .thermosiphon import coupled_capability
    rf = RockField(geo, well.r_b, n_z=n_z, n_r=40, r_far=r_far, far_field=far_field)
    ts = Thermosiphon(design, well, geo.depth, rf.z, rf.dz)
    ts.mechanical_checks(geo.T_bottom)
    t, out, marks = 0.0, {}, sorted(marks_days)
    energy = 0.0
    for dd in steps_days:
        r = rf.response(dd * 86400)
        if condenser is None:
            q, Q, aux = ts.capability(r)
            T_top = aux.get("T_top", design.T_top) if aux else design.T_top
        else:
            q, Q, T_top = coupled_capability(ts, r, condenser)
        rf.apply(q)
        t += dd
        energy += Q * dd
        while marks and t >= marks[0] - 1e-6:
            out[marks.pop(0)] = (Q / 1e3, T_top, float(-np.sum(np.clip(q, None, 0)) * rf.dz / 1e3))
    out["mean_kW"] = energy / t / 1e3
    return out, ts


def _schedule(days_total, fine_hours=24):
    """1 h steps for the first day, then 1 d to day 30, weekly to day 365, then monthly."""
    s = [1 / 24] * fine_hours + [1.0] * 29
    t = sum(s)
    while t < min(365.0, days_total) - 1e-9:
        s.append(min(7.0, 365.0 - t))
        t += s[-1]
    while t < days_total - 1e-9:
        s.append(min(30.4375, days_total - t))
        t += s[-1]
    return s


ZOLF_PROFILE = ([0, 10, 20, 30, 40, 50, 60, 75, 100, 110, 125, 135, 150, 175, 200, 225, 250],
                [60, 70, 88, 110, 130, 148, 155, 158, 168, 175, 190, 196, 198, 197, 190, 180, 170])


def zolfagharroshan_2024() -> list[dict]:
    """Zolfagharroshan et al. (2024) Applied Thermal Engineering 248:123205, Section 4.2.

    Inputs from the paper: pentane TPCT, 150/200/250 m deep, top 50 m insulated (treated
    adiabatic), wall 6.25 mm, 2 m condenser with a fully wrapped helical coil (OD 10.156 mm,
    wall 2.078 mm), water 70 C / 15 lpm, 35 % fill of evaporator volume (pool), Imura boiling,
    Nusselt condensation, far field at 50 m held at the initial temperature, 20 years.
    Rock: k = 2 W/m/K, rho = 2490, cp = 1100 (their Table 2, same Beppu site).
    Initial temperature profile digitised from their Fig. 5a/7 (+/- ~5 C).
    Pipe OD 130.1 mm inferred from Table 4 (D_coil = OD + d/2 = 135.156 mm)."""
    from .thermosiphon import CoilCondenser
    published = {150: 10.69, 200: 14.04, 250: 15.54}
    zs, Ts = ZOLF_PROFILE
    out = []
    for L, Q_pub in published.items():
        prof_z = [z for z in zs if z < L] + [L]
        prof_T = [T for z, T in zip(zs, Ts) if z < L] + [float(np.interp(L, zs, Ts))]
        geo = Geology(depth=float(L), profile_z=prof_z, profile_T=prof_T, k=2.0, rho=2490, cp=1100)
        well = Well(casing_id=0.1301, casing_wall=1e-4, cement_thickness=1e-4, k_cement=2.0)
        d = ThermosiphonDesign(fluid="pentane", insulated_length=50.0, adiabatic_insulation=True, gap=1e-4,
                               wall_thickness=0.00625, check_mechanics=False, evap_correlation="imura",
                               liquid_distribution="guided", pool_depth=0.35 * (L - 50), T_top=80.0)
        cond = CoilCondenser(length=2.0, d_in=0.1301 - 2 * 0.00625, d_out=0.1301)
        res, ts = _run_schedule(geo, well, d, _schedule(20 * 365.25), [365.25, 20 * 365.25], n_z=int(L / 5),
                                r_far=50.0, condenser=cond)
        out.append(dict(benchmark="Zolfagharroshan 2024 (20-yr mean heat rate)", depth_m=L,
                        model_kW=res["mean_kW"], published_kW=Q_pub, error_pct=100 * (res["mean_kW"] / Q_pub - 1),
                        model_T_out_y20=cond.outlet_temperature(res[20 * 365.25][0] * 1e3),
                        status=ts.status))
    return out


GRUBER_PROFILE_Z = list(np.linspace(0, 1800, 91))
GRUBER_PROFILE_T = [81.13 / (1 + np.exp(-(0.00606 * z - 1.99))) for z in GRUBER_PROFILE_Z]
# Digitised from Gruber et al. (2026) Figs. 8-9 (about +/- 5 kW).
GRUBER_PUBLISHED = {
    ("conventional", 40): (246, 185, 148), ("conventional", 50): (150, 110, 88), ("conventional", 60): (52, 40, 31),
    ("packer", 40): (246, 185, 150), ("packer", 50): (185, 140, 111), ("packer", 60): (122, 98, 75),
    ("packer", 70): (60, 47, 36),
}


def gruber_2026(vapor_head_options=(True, False)) -> list[dict]:
    """Gruber et al. (2026) Energy 353:140961, Section 4.2 (Table 2 inputs).

    1,800 m ammonia SLGHP, pipe ID 177.8 mm / wall 6.1 mm, borehole radius 105 mm, logistic
    profile T = 81.13/(1+exp(-(0.00606 z - 1.99))), k_eff = 2.4, rho = 2400 / cp = 850 with 20 %
    water-filled porosity (effective rho*cp ~ 2.46e6 J/m3/K), far field 150 m at initial
    temperature, Cooper boiling (Rp = 1 um), no dry-out (guided).  Packer at 650 m with an
    adiabatic transport section.  The 250 m of rock below the pipe in their model is not
    represented (no axial conduction).  Pool: 5 m (their 20 % volumetric fill is not
    reproducible as a static pool and is tested separately).  Their 10-year runs neglect the
    ~2-3 C vapour-head stratification, so both head on/off are reported."""
    geo = Geology(depth=1800.0, profile_z=GRUBER_PROFILE_Z, profile_T=GRUBER_PROFILE_T, k=2.4, rho=2460, cp=1000)
    well = Well(casing_id=0.1900, casing_wall=1e-4, cement_thickness=0.0099, k_cement=2.4)
    sched = _schedule(3652.5)
    out = []
    for head in vapor_head_options:
        for (arch, Tc), (p30, p1y, p10y) in GRUBER_PUBLISHED.items():
            d = ThermosiphonDesign(fluid="ammonia", T_top=float(Tc), architecture=arch,
                                   insulated_length=650.0 if arch == "packer" else 0.0, adiabatic_insulation=True,
                                   gap=1e-4, wall_thickness=0.0061, check_mechanics=False,
                                   liquid_distribution="guided", vapor_head=head)
            res, ts = _run_schedule(geo, well, d, sched, [30, 365.25, 3652.5], n_z=90)
            out.append(dict(benchmark="Gruber 2026 1,800 m ammonia", architecture=arch, Tc=Tc, vapor_head=head,
                            model_30d=res[30][0], pub_30d=p30, model_1y=res[365.25][0], pub_1y=p1y,
                            model_10y=res[3652.5][0], pub_10y=p10y, ratio_30d=res[30][0] / p30,
                            ratio_10y=res[3652.5][0] / p10y, model_decline_1y_10y=1 - res[3652.5][0] / res[365.25][0],
                            pub_decline_1y_10y=1 - p10y / p1y, status=ts.status))
    return out


TAIYUAN_PUBLISHED = {0: (450, 360, 315), 5: (395, 320, 275), 10: (345, 280, 240), 15: (295, 240, 205),
                     20: (245, 200, 170)}  # Chen et al. field data as plotted in Gruber Fig. 7a (digitised)


def taiyuan_2_via_gruber() -> list[dict]:
    """Taiyuan #2 SLGHP (Chen et al. 2024) using the set-up Gruber et al. (2026) state for their
    validation: 2,020 m, ammonia, 23 C/km from 15 C, k = 1.95, rho = 2650, cp = 1000, 120 days,
    condensation 0-20 C.  Pipe diameter is not stated there: 177.8 mm assumed.  An 'ideal pipe'
    (no internal resistance, no vapour head, no losses above the T_c isotherm) gives the
    radial-conduction ceiling for those inputs."""
    geo = Geology.linear(2020.0, 15.0, 15.0 + 23.0 * 2.020, k=1.95, rho=2650, cp=1000)
    well = Well(casing_id=0.1900, casing_wall=1e-4, cement_thickness=0.0099, k_cement=1.95)
    sched = _schedule(120.0)
    out = []
    for Tc, (p10, p40, p120) in TAIYUAN_PUBLISHED.items():
        d = ThermosiphonDesign(fluid="ammonia", T_top=float(Tc), gap=1e-4, wall_thickness=0.0061,
                               check_mechanics=False, liquid_distribution="guided")
        res, ts = _run_schedule(geo, well, d, sched, [10, 40, 120])
        ideal = ThermosiphonDesign(fluid="ammonia", T_top=float(Tc), gap=1e-4, wall_thickness=0.0061,
                                   check_mechanics=False, liquid_distribution="guided", vapor_head=False,
                                   evap_correlation="constant", h_evap=1e6,
                                   insulated_length=geo.depth_at_temperature(Tc), adiabatic_insulation=True)
        res_i, _ = _run_schedule(geo, well, ideal, sched, [120])
        out.append(dict(benchmark="Taiyuan #2 field (Chen 2024) via Gruber Fig. 7a", Tc=Tc,
                        model_10d=res[10][0], model_40d=res[40][0], model_120d=res[120][0],
                        pub_10d=p10, pub_40d=p40, pub_120d=p120, ratio_120d=res[120][0] / p120,
                        conduction_ceiling_120d=res_i[120][0], pub_over_ceiling=p120 / res_i[120][0],
                        status=ts.status))
    return out


HDR_PUBLISHED = {91.3: 620, 365.25: 560, 730.5: 520, 1826.25: 480, 3652.5: 450}  # Gruber Fig. 7b (digitised)


def hdr_4000m_water() -> list[dict]:
    """4,000 m hot-dry-rock water heat pipe (Huang et al. model, as reproduced in Gruber Fig. 7b):
    D = 300 mm, T_c = 50 C, 45 C/km from 15 C, k = 2.1, rho = 2650, cp = 1000, 10 years.
    Model-to-model comparison (not field data)."""
    geo = Geology.linear(4000.0, 15.0, 15.0 + 45.0 * 4.0, k=2.1, rho=2650, cp=1000)
    well = Well(casing_id=0.3122, casing_wall=1e-4, cement_thickness=0.01, k_cement=2.1)
    d = ThermosiphonDesign(fluid="water", T_top=50.0, gap=1e-4, wall_thickness=0.0061, check_mechanics=False,
                           liquid_distribution="guided")
    res, ts = _run_schedule(geo, well, d, _schedule(3652.5), list(HDR_PUBLISHED))
    return [dict(benchmark="4 km HDR water heat pipe (Huang model via Gruber Fig. 7b)", day=k,
                 model_kW=res[k][0], published_kW=v, error_pct=100 * (res[k][0] / v - 1), status=ts.status,
                 flags="; ".join(ts.flags)) for k, v in HDR_PUBLISHED.items()]


# Brown et al. 2026 (GSL Spec. Pub. 566) Fig. 4, after Brown et al. 2023b: average heat load over a
# 6-month extraction from a 920 m coaxial DBHE at 8.33 L/s and 10 C inlet.  Values digitised from the
# figure; the base-case geometry and rock properties are not given in the review, so this is a TREND
# check (ratios between the ends of each sensitivity panel), not an absolute-value benchmark.
BROWN_FIG4 = {
    "k_rock 1.5 -> 4.5 W/mK": (29.5, 60.0),
    "gradient 10 -> 40 C/km": (12.0, 56.0),
    "inlet 25 -> 5 C": (0.0, 62.0),
    "flow 1 -> 8 L/s": (19.0, 44.5),
    "depth 1000 -> 2500 m": (55.0, 285.0),
}
BROWN_BASE_BAND_kW = (44.0, 53.0)  # spread of the base points across panels (b, d, g, h)


def _coax_6mo(depth=920.0, k=2.8, grad=34.0, T_in=10.0, flow_ls=8.33, T_surf=9.0):
    """Assumed DBHE: 8-1/2" hole, 7" casing (ID 159 mm), 4-1/2" HDPE-like centre pipe (k_ins 0.4)."""
    from .coaxial import Coaxial
    geo = Geology.linear(depth, T_surf, T_surf + grad * depth / 1e3, k=k)
    well = Well(casing_id=0.159, casing_wall=0.0092, cement_thickness=0.0283, k_cement=1.5)
    d = CoaxialDesign(tube_od=0.1143, tube_id=0.0935, k_ins=0.4, m_dot=flow_ls * 0.999, T_in=T_in,
                      max_pump_dp=1e9, max_velocity=10.0)
    rf = RockField(geo, well.r_b, n_z=60, n_r=40, r_far=100.0)
    cx = Coaxial(d, well, depth, rf.z, rf.dz)
    t, e = 0.0, 0.0
    for dd in [1 / 24] * 24 + [1.0] * 29 + [7.0] * 21:  # ~ 6 months
        q, Q, _ = cx.capability(rf.response(dd * 86400))
        rf.apply(q)
        t += dd
        e += Q * dd
    return e / t / 1e3


def brown_2026_dbhe_trends() -> list[dict]:
    """Coaxial-model trend check against Brown et al. 2026 Fig. 4 (see BROWN_FIG4)."""
    runs = {
        "k_rock 1.5 -> 4.5 W/mK": (dict(k=1.5), dict(k=4.5)),
        "gradient 10 -> 40 C/km": (dict(grad=10.0), dict(grad=40.0)),
        "inlet 25 -> 5 C": (dict(T_in=25.0), dict(T_in=5.0)),
        "flow 1 -> 8 L/s": (dict(flow_ls=1.0), dict(flow_ls=8.0)),
        "depth 1000 -> 2500 m": (dict(depth=1000.0), dict(depth=2500.0)),
    }
    base = _coax_6mo()
    out = [dict(benchmark="Brown 2026 Fig.4 base (920 m, 8.33 L/s, 10 C in, 6 mo) - assumed geometry",
                sweep="base", model_lo_kW=base, model_hi_kW=base,
                published_lo_kW=BROWN_BASE_BAND_kW[0], published_hi_kW=BROWN_BASE_BAND_kW[1],
                model_change_kW=float("nan"), published_change_kW=float("nan"))]
    for name, (a, b) in runs.items():
        lo, hi = _coax_6mo(**a), _coax_6mo(**b)
        p_lo, p_hi = BROWN_FIG4[name]
        out.append(dict(benchmark="Brown 2026 Fig.4 sensitivity", sweep=name, model_lo_kW=lo, model_hi_kW=hi,
                        published_lo_kW=p_lo, published_hi_kW=p_hi, model_change_kW=hi - lo,
                        published_change_kW=p_hi - p_lo))
    return out


NOT_REPRODUCED = [
    dict(benchmark="Zolfagharroshan 32 m flexible thermosyphon (Liu et al.) and cold-storage experiment",
         status="NOT ATTEMPTED",
         reason="Time-series data are only in figures; the 24-h start-up transient is outside this model's "
                "monthly/quasi-steady scope."),
    dict(benchmark="Gruber 2026 integrated heating/cooling system (COP 4.22, SPF 6.19, 485 MWh)",
         status="NOT ATTEMPTED",
         reason="Requires the flash-vessel ammonia heat pump, buffer tank, cooling load and hourly demand model; "
                "the TEA uses a separate-circuit heat pump on monthly steps."),
    dict(benchmark="Ma et al. 2024 / Huang et al. 2021 (power-generation SLGHP vs DHE)",
         status="CONTEXT ONLY", reason="Electricity-generation economics; not transferable to heat LCOH."),
]
