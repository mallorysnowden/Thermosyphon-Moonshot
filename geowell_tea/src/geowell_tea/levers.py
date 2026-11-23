"""'What would need to be true' outputs.

The thermosiphon is shown at three cost levels (FOAK, today's base, NOAK) and with cumulative
scale levers applied to it alone; coaxial and the incumbent stay at today's assumptions.
Break-even values are found by bisection on one parameter at a time, re-picking the best design.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .costs import economics
from .optimize import annual_block

COMMON_PROGRAM_KEYS = ("well_acquisition_legal", "permits_engineering", "mit_logging", "surface_plant_base",
                       "instrumentation_controls", "cleanout_days_base", "cleanout_days_per_km")


def max_unmet_share(r) -> float:
    load = r.annual(r.load) if np.all(np.isfinite(r.load)) else None
    if load is None:
        return 0.0
    return float(np.max(np.asarray(r.E_backup) / np.maximum(load, 1e-9)))


def _lcoh(r, p, dist):
    q = dict(r.quantities, distance_m=dist, composite=bool(r.arch.coax and r.arch.coax.k_ins > 0.05))
    return float(economics(r.arch.arch_id, q, annual_block(r), p)["lcoh"])


def best(results, p, dist, tech="T_", full_cover=False, max_unmet=0.02):
    """(lcoh, result) of the cheapest FEASIBLE design of a technology, optionally full-coverage only."""
    cands = [r for r in results if r.arch.arch_id.startswith(tech) and r.status == "FEASIBLE"
             and float(np.sum(r.E_useful)) > 0 and (not full_cover or max_unmet_share(r) <= max_unmet)]
    if not cands:
        return float("nan"), None
    vals = [(_lcoh(r, p, dist), r) for r in cands]
    return min(vals, key=lambda v: v[0])


def lever_steps(p: dict) -> list[tuple[str, dict]]:
    """Cumulative levers applied to the thermosiphon only."""
    steps = [("today's base costs", dict(p, ts_cost_level="base"))]
    q = dict(p, ts_cost_level="noak")
    steps.append(("1. NOAK manufacturing + automated install (raw x %.1f)" % p["ts_noak_index"], dict(q)))
    for k in COMMON_PROGRAM_KEYS:
        if k in q:
            q[k] = p[k] * 0.6
    q["contingency"] = 0.10
    steps.append(("2. standardised well-reuse programme (common -40%, contingency 10%)", dict(q)))
    q["hp_per_kw"] = 500.0
    steps.append(("3. heat pump $500/kW", dict(q)))
    q["discount_rate"] = 0.06
    steps.append(("4. infrastructure financing 6% real", dict(q)))
    return steps


def _bisect(f, lo, hi, n=30):
    """Root of a monotone f on [lo, hi]; nan if f does not change sign there."""
    flo, fhi = f(lo), f(hi)
    if not (np.isfinite(flo) and np.isfinite(fhi)) or flo * fhi > 0:
        return float("nan")
    for _ in range(n):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if fm * flo > 0:
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def what_must_be_true(results, case, dist) -> dict:
    p0 = dict(case.params)
    inc = p0["incumbent_useful_cost"]
    ef = case.prices.get("incumbent_emission_factor_t_per_MWh")
    ef_useful = ef / case.prices["incumbent_efficiency"] if ef else float("nan")
    c_best, c_r = best(results, p0, dist, "C_")
    c_full, c_fr = best(results, p0, dist, "C_", full_cover=True)
    rows = []
    for full in (False, True):
        for label, p in [("FOAK (1.5x base)", dict(p0, ts_cost_level="foak"))] + lever_steps(p0):
            t, tr = best(results, p, dist, "T_", full_cover=full)
            ref = c_full if full else c_best
            rows.append(dict(coverage="full (<2% unmet every year)" if full else "any",
                             ts_case=label, ts_lcoh=t, ts_design=tr.arch.describe() if tr else None,
                             ts_unmet_max=max_unmet_share(tr) if tr else float("nan"),
                             coax_lcoh_today=ref, coax_design=(c_fr if full else c_r).arch.describe() if (c_fr if full else c_r) else None,
                             incumbent=inc, ts_over_coax=t / ref if np.isfinite(ref) else float("nan"),
                             carbon_price_for_parity=max(0.0, (t - inc) / ef_useful) if np.isfinite(ef_useful) else float("nan")))
    table = pd.DataFrame(rows)

    def ts_at(p, full=False):
        return best(results, p, dist, "T_", full_cover=full)[0]

    be = {}
    for full in (False, True):
        tag = "full" if full else "any"
        ref = c_full if full else c_best
        pn = dict(p0, ts_cost_level="noak")
        # NOAK index giving parity with coaxial / with the incumbent
        be[f"noak_index_for_coax_parity_{tag}"] = _bisect(lambda x: ts_at(dict(pn, ts_noak_index=x), full) - ref, 0.3, 12)
        be[f"noak_index_for_incumbent_parity_{tag}"] = _bisect(lambda x: ts_at(dict(pn, ts_noak_index=x), full) - inc, 0.3, 12)
        # VIT price at which the best coaxial design matches the thermosiphon (base and NOAK)
        for lvl in ("base", "noak"):
            t = ts_at(dict(p0, ts_cost_level=lvl), full)
            be[f"vit_price_for_parity_ts_{lvl}_{tag}"] = _bisect(
                lambda v: best(results, dict(p0, vit_per_m=v), dist, "C_", full_cover=full)[0] - t, 0.0, 3000.0)
    return dict(table=table, breakevens=be, ef_useful=ef_useful)
