"""Independent design-space search for each architecture in the same well.

Both technologies get the same geology, casing clearance and customer
temperatures; each picks its own setpoints and hardware to minimise its own
LCOH (economic optimum) or to maximise its own year-20 heat (resource maximum).
Nothing forces equal output.
"""
from __future__ import annotations

from dataclasses import replace
import multiprocessing as mp
import os

import numpy as np

from .coaxial import CoaxialDesign
from .costs import economics
from .geology import Geology
from .loads import load_series, monthly_fractions
from .simulate import Architecture, SimSettings, simulate
from .surfaces import SurfaceParams
from .wellbore import Well

# (OD, ID, k_ins, label).  VIT sizes per the 3.5" x 2-3/8" lower end of the VIT
# range; composite option is a pre-insulated polymer tube (much worse insulation).
CENTRE_TUBES = [
    (0.0889, 0.0507, 0.015, "VIT 3.5x2.375"),
    (0.1143, 0.0760, 0.015, "VIT 4.5x3.5"),
    (0.1397, 0.1003, 0.015, "VIT 5.5x4.5"),
    (0.0603, 0.0443, 0.06, "composite 60mm"),
]

ARCHS = ("T_DIRECT", "T_HP", "T_ADAPTIVE", "C_DIRECT", "C_HP", "C_ADAPTIVE")


def ts_grid(geo: Geology, surf: SurfaceParams, fluids=("ammonia",), compact=False, allow_packer=False):
    """Thermosiphon design grid.  ``allow_packer`` adds the patented packer architecture
    (SI23618A, Gruber 2026) with the packer at the depth where the rock reaches T_top + 3 C;
    it is IP-flagged and excluded unless explicitly requested."""
    T_dir = surf.T_supply + surf.approach
    out = []
    setpoints = {
        "T_DIRECT": [T_dir, T_dir + 5, T_dir + 10] if not compact else [T_dir, T_dir + 6],
        "T_HP": [10, 15, 20, 25, 30] if not compact else [12, 20, 28],
        "T_ADAPTIVE": [surf.T_return + surf.approach + 2, 0.5 * (surf.T_return + surf.T_supply) + surf.approach,
                       T_dir - 2] if not compact else [surf.T_return + surf.approach + 2, T_dir - 2],
    }
    for arch, Ts in setpoints.items():
        for fluid in fluids:
            for T_top in Ts:
                if T_top > geo.T_bottom - 8:
                    continue
                if arch == "T_HP" and T_top >= T_dir:
                    continue
                for ins in ("none", "auto"):
                    L_ins = 0.0 if ins == "none" else max(0.0, geo.depth_at_temperature(T_top + 3.0))
                    if ins == "auto" and L_ins < 0.05 * geo.depth:
                        continue
                    from .thermosiphon import ThermosiphonDesign
                    for liq in ("film", "guided"):
                        out.append(Architecture(arch, ts=ThermosiphonDesign(
                            fluid=fluid, T_top=float(T_top), insulated_length=float(L_ins),
                            liquid_distribution=liq)))
                    if allow_packer and ins == "auto":
                        out.append(Architecture(arch, ts=ThermosiphonDesign(
                            fluid=fluid, T_top=float(T_top), insulated_length=float(L_ins),
                            liquid_distribution="guided", architecture="packer")))
    return out


def coax_grid(geo: Geology, well: Well, surf: SurfaceParams, compact=False):
    tubes = [t for t in CENTRE_TUBES if t[0] <= well.casing_id - 0.03]
    vit = [t for t in tubes if t[2] < 0.05]
    tubes = vit[-2:] if vit else tubes[:1]  # two largest VITs that fit, else composite
    out = []
    T_in_direct = surf.T_return + surf.approach
    for od, idd, kins, lab in tubes:
        area = np.pi / 4 * idd ** 2
        m_cap = float(min(8.0, 2.5 * 990 * area))
        base = dict(tube_od=od, tube_id=idd, k_ins=kins, label=lab)
        out.append(Architecture("C_DIRECT", coax=CoaxialDesign(
            m_dot=m_cap, T_in=T_in_direct, variable_flow_target=surf.T_supply + surf.approach, **base)))
        hp_T = [5, 12, 20] if not compact else [6, 15]
        hp_m = [1.5, 3.0, 5.0] if not compact else [2.0, 4.0]
        for T_in in hp_T:
            for m in hp_m:
                if m <= m_cap:
                    out.append(Architecture("C_HP", coax=CoaxialDesign(m_dot=m, T_in=float(T_in), **base)))
        ad_T = [12, 22, surf.T_return] if not compact else [15, surf.T_return]
        for T_in in ad_T:
            for m in ([1.5, 3.0] if not compact else [2.0]):
                if m <= m_cap:
                    out.append(Architecture("C_ADAPTIVE", coax=CoaxialDesign(m_dot=m, T_in=float(T_in), **base)))
    return out


def _sim_worker(args):
    arch, geo, well, surf, load_spec, sim = args
    load = _make_load(arch, geo, well, surf, load_spec, sim)
    res = simulate(arch, geo, well, surf, load, sim)
    return res


def _make_load(arch, geo, well, surf, load_spec, sim):
    """load_spec: None (resource test), ("fixed", array) or ("sized", shape, flh)."""
    if load_spec is None:
        return None
    if load_spec[0] == "fixed":
        return load_spec[1]
    _, shape, flh = load_spec
    pre = simulate(arch, geo, well, surf, None, SimSettings(**{**sim.__dict__, "years": 1}))
    peak = float(np.mean(pre.Q_useful_cap))
    return load_series(peak, shape, flh, sim.years)


def run_designs(archs, geo, well, surf, load_spec, sim: SimSettings, processes=None):
    jobs = [(a, geo, well, surf, load_spec, sim) for a in archs]
    processes = processes or min(len(jobs), os.cpu_count() or 1)
    if processes > 1 and len(jobs) > 1:
        ctx = mp.get_context("fork")
        with ctx.Pool(processes) as pool:
            return pool.map(_sim_worker, jobs, chunksize=max(1, len(jobs) // (4 * processes)))
    return [_sim_worker(j) for j in jobs]


def annual_block(res) -> dict:
    return dict(useful=res.E_useful, elec=res.E_elec, backup=res.E_backup, load=res.annual(res.load)
                if np.all(np.isfinite(res.load)) else res.E_useful)


def evaluate(results, params: dict, distance_m: float):
    rows = []
    for res in results:
        q = dict(res.quantities, distance_m=distance_m, composite=bool(res.arch.coax and res.arch.coax.k_ins > 0.05))
        eco = economics(res.arch.arch_id, q, annual_block(res), params)
        s = res.summary()
        s.update({k: v for k, v in eco.items() if k != "capex_items"})
        s["capex_items"] = eco.get("capex_items", {})
        rows.append((res, s))
    return rows


def best_by_arch(rows, key="lcoh", allow_unvalidated=False):
    ok = {"FEASIBLE", "UNVALIDATED"} if allow_unvalidated else {"FEASIBLE"}
    best = {}
    for res, s in rows:
        if s["status"] not in ok or not np.isfinite(s[key]) or s["E_useful_MWh_total"] <= 0:
            continue
        a = s["architecture"]
        if a not in best:
            best[a] = (res, s)
            continue
        lower_is_better = key in ("lcoh", "site_cost_per_MWh", "elec_per_useful")
        if (s[key] < best[a][1][key]) if lower_is_better else (s[key] > best[a][1][key]):
            best[a] = (res, s)
    return best
