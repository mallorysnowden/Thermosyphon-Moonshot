"""Depth x bottom-hole temperature x casing-diameter envelope.

For every cell both technologies are independently optimised over their design
grids in the *same* well (same geology, clearance and customer temperatures).
In the default scenarios each design serves a customer sized to its own year-1
capability with the scenario's seasonal shape ("sized-to-resource"), so
neither technology is forced to an equal output.  The ``*_fixed_*`` scenario
instead serves one fixed customer (load-limited regime, like Case A).

Economics are then evaluated under a Monte Carlo
of the cost/finance inputs (shared draws for both technologies), and the cell
is classed as:

    TS_CONSISTENT  P(best TS LCOH < best coax LCOH) >= threshold (default 0.9)
    C_CONSISTENT   P(...) <= 1 - threshold
    CONTESTED      otherwise
    NO_FEASIBLE_TS / NO_FEASIBLE_C  when one side has no FEASIBLE design
"""
from __future__ import annotations

from dataclasses import dataclass
import multiprocessing as mp
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from .costs import economics
from .geology import Geology
from .optimize import annual_block, coax_grid, ts_grid, _make_load
from .schema import load_case, sample_params
from .simulate import SimSettings, simulate
from .surfaces import SurfaceParams
from .wellbore import Well


@dataclass
class LiteResult:
    """Just what the economics need (keeps pickles small)."""
    arch_id: str
    design: str
    status: str
    flags: str
    quantities: dict
    annual: dict
    composite: bool
    geo_kW_y1: float
    geo_kW_y20: float
    useful_MWh: float


def _cell_worker(args):
    depth, bht, casing_id, k, scen, sim = args
    geo = Geology.linear(depth, scen["T_surface"], bht, k=k)
    well = Well(casing_id=casing_id)
    surf = SurfaceParams(T_supply=scen["T_supply"], T_return=scen["T_return"])
    archs = ts_grid(geo, surf, compact=True) + coax_grid(geo, well, surf, compact=True)
    out = []
    if scen.get("fixed_peak_kW"):
        from .loads import load_series
        spec = ("fixed", load_series(scen["fixed_peak_kW"] * 1e3, scen["shape"], scen["flh"], sim.years))
    else:
        spec = ("sized", scen["shape"], scen["flh"])
    for a in archs:
        load = _make_load(a, geo, well, surf, spec, sim)
        r = simulate(a, geo, well, surf, load, sim)
        s = r.summary()
        out.append(LiteResult(a.arch_id, s["design"], r.status, "; ".join(r.flags), dict(r.quantities),
                              annual_block(r), bool(a.coax and a.coax.k_ins > 0.05),
                              s["geo_capability_kW_y1"], s["geo_capability_kW_y20"], s["E_useful_MWh_total"]))
    return (depth, bht, casing_id, k), out


def default_cells(T_surface=10.0):
    depths = [1000, 1500, 2000, 2500, 3000, 3500, 4000]
    bhts = [50, 65, 80, 95, 110, 125, 140]
    dias = [0.10, 0.127, 0.15, 0.18]
    cells = []
    for d in depths:
        for b in bhts:
            grad = (b - T_surface) / d * 1000
            if 15 <= grad <= 50:
                for D in dias:
                    cells.append((d, b, D))
    return cells


def run_physics(scen: dict, cells, k_values=(2.5,), n_z=30, processes=None, cache: Path | None = None):
    sim = SimSettings(years=20, n_z=n_z, n_r=32, distance_m=scen["distance_m"])
    jobs = [(d, b, D, k, scen, sim) for (d, b, D) in cells for k in k_values]
    processes = processes or (os.cpu_count() or 1)
    ctx = mp.get_context("fork")
    with ctx.Pool(processes) as pool:
        results = dict(pool.imap_unordered(_cell_worker, jobs, chunksize=1))
    if cache:
        with open(cache, "wb") as fh:
            pickle.dump(results, fh)
    return results


def analyse(results: dict, params: dict, ranges: dict, distance_m: float, draws=400, threshold=0.9,
            allow_unvalidated=False, seed=11) -> pd.DataFrame:
    mc_ranges = dict(ranges)
    e = params["electricity_price"]
    mc_ranges["electricity_price"] = (0.7 * e, e, 1.4 * e)
    P = sample_params(params, mc_ranges, draws, seed=seed)
    ok = {"FEASIBLE", "UNVALIDATED"} if allow_unvalidated else {"FEASIBLE"}
    rows = []
    for (depth, bht, D, k), lites in sorted(results.items()):
        lcoh_base, lcoh_mc, info = {"TS": [], "C": []}, {"TS": [], "C": []}, {"TS": [], "C": []}
        for lr in lites:
            if lr.status not in ok or lr.useful_MWh <= 0:
                continue
            tech = "TS" if lr.arch_id.startswith("T_") else "C"
            q = dict(lr.quantities, distance_m=distance_m, composite=lr.composite)
            eb = economics(lr.arch_id, q, lr.annual, params)
            em = economics(lr.arch_id, q, lr.annual, P)
            lcoh_base[tech].append(eb["lcoh"])
            lcoh_mc[tech].append(em["lcoh"])
            info[tech].append(lr)
        row = dict(depth=depth, bht=bht, casing_id=D, k=k,
                   gradient_K_per_km=(bht - (bht - (bht - 0))) if False else None)
        if not lcoh_base["TS"] or not lcoh_base["C"]:
            row.update(cls="NO_FEASIBLE_TS" if not lcoh_base["TS"] else "NO_FEASIBLE_C",
                       p_ts_wins=1.0 if not lcoh_base["C"] and lcoh_base["TS"] else 0.0)
            for tech in ("TS", "C"):
                if lcoh_base[tech]:
                    i = int(np.argmin(lcoh_base[tech]))
                    row[f"{tech}_best"] = info[tech][i].design
                    row[f"{tech}_lcoh"] = lcoh_base[tech][i]
                    row[f"{tech}_geo_kW_y20"] = info[tech][i].geo_kW_y20
            rows.append(row)
            continue
        ts_min = np.min(np.vstack(lcoh_mc["TS"]), axis=0)
        c_min = np.min(np.vstack(lcoh_mc["C"]), axis=0)
        p = float(np.mean(ts_min < c_min))
        it = int(np.argmin(lcoh_base["TS"]))
        ic = int(np.argmin(lcoh_base["C"]))
        cls = "TS_CONSISTENT" if p >= threshold else ("C_CONSISTENT" if p <= 1 - threshold else "CONTESTED")
        row.update(cls=cls, p_ts_wins=p,
                   ratio_base=lcoh_base["TS"][it] / lcoh_base["C"][ic],
                   ratio_p10=float(np.percentile(ts_min / c_min, 10)),
                   ratio_p50=float(np.percentile(ts_min / c_min, 50)),
                   ratio_p90=float(np.percentile(ts_min / c_min, 90)),
                   TS_best=info["TS"][it].design, TS_lcoh=lcoh_base["TS"][it],
                   TS_geo_kW_y20=info["TS"][it].geo_kW_y20, TS_useful_MWh=info["TS"][it].useful_MWh,
                   C_best=info["C"][ic].design, C_lcoh=lcoh_base["C"][ic],
                   C_geo_kW_y20=info["C"][ic].geo_kW_y20, C_useful_MWh=info["C"][ic].useful_MWh)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["gradient_K_per_km"] = None
    return df


SCENARIOS = {
    "greenhouse_45_35": dict(T_surface=10.0, T_supply=45.0, T_return=35.0, shape="western_pa", flh=5000,
                             distance_m=250.0, case_config="case_a_pa.yaml"),
    "greenhouse_fixed_120kW": dict(T_surface=10.0, T_supply=45.0, T_return=35.0, shape="western_pa", flh=5000,
                                   distance_m=250.0, case_config="case_a_pa.yaml", fixed_peak_kW=120.0),
    "aquaculture_35_25": dict(T_surface=7.0, T_supply=35.0, T_return=25.0, shape="western_nd", flh=7000,
                              distance_m=250.0, case_config="case_b_nd.yaml"),
}
