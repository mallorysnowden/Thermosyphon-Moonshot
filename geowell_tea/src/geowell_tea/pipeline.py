"""Case pipeline: design search -> resource test -> customer dispatch -> TEA ->
sensitivities -> outputs (CSV, figures, Markdown report)."""
from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
import time

import numpy as np
import pandas as pd

from . import __version__
from . import plots
from .costs import economics
from .loads import load_series
from .optimize import (ARCHS, annual_block, best_by_arch, coax_grid, evaluate, run_designs, ts_grid)
from .schema import Case, load_case, sample_params
from .simulate import SimSettings

OUT_ROOT = Path(__file__).resolve().parents[2] / "outputs"
SCREEN_FLUIDS = ("ammonia", "water", "propane", "isobutane", "pentane", "co2")


def _sim_settings(case: Case, **kw) -> SimSettings:
    s = case.sim
    return SimSettings(years=int(s.get("years", 20)), n_z=int(s.get("n_z", 50)), n_r=int(s.get("n_r", 36)),
                       distance_m=float(case.load["distance_m"]), **kw)


def best_pair(rows, key="lcoh", allow_unvalidated=False):
    b = best_by_arch(rows, key=key, allow_unvalidated=allow_unvalidated)
    ts = [b[a] for a in b if a.startswith("T_")]
    cx = [b[a] for a in b if a.startswith("C_")]
    bt = min(ts, key=lambda x: x[1][key]) if ts else None
    bc = min(cx, key=lambda x: x[1][key]) if cx else None
    return bt, bc


def lcoh_matrix(rows, params, distance_m):
    """LCOH for every design under (possibly vectorised) params -> (archs, statuses, matrix)."""
    out = []
    for res, s in rows:
        q = dict(res.quantities, distance_m=distance_m,
                 composite=bool(res.arch.coax and res.arch.coax.k_ins > 0.05))
        eco = economics(res.arch.arch_id, q, annual_block(res), params)
        out.append(np.atleast_1d(eco["lcoh"]))
    return np.vstack(out)


def ts_vs_c(rows, params, distance_m, allow_unvalidated=False, mask_rows=None):
    ok = {"FEASIBLE", "UNVALIDATED"} if allow_unvalidated else {"FEASIBLE"}
    keep = [(r, s) for r, s in rows if s["status"] in ok and s["E_useful_MWh_total"] > 0]
    if not keep:
        return None
    M = lcoh_matrix(keep, params, distance_m)
    is_ts = np.array([s["architecture"].startswith("T_") for _, s in keep])
    ts_min = M[is_ts].min(axis=0) if is_ts.any() else np.full(M.shape[1], np.inf)
    c_min = M[~is_ts].min(axis=0) if (~is_ts).any() else np.full(M.shape[1], np.inf)
    return ts_min, c_min


def run_case(config: str, out_dir: Path | None = None, mc_draws: int = 500, quick: bool = False) -> dict:
    t0 = time.time()
    case = load_case(config)
    tag = Path(config).stem
    out = Path(out_dir) if out_dir else OUT_ROOT / tag
    out.mkdir(parents=True, exist_ok=True)
    sim = _sim_settings(case)
    if quick:
        sim.n_z = 30
    geo, well, surf = case.geology, case.well, case.surface
    L = load_series(case.load["peak_month_kW"] * 1e3, case.load["shape"], case.load["flh"], sim.years)

    archs = ts_grid(geo, surf, compact=quick) + coax_grid(geo, well, surf, compact=quick)
    # ---- (1) customer dispatch for every design ----
    res_cust = run_designs(archs, geo, well, surf, ("fixed", L), sim)
    rows = evaluate(res_cust, case.params, sim.distance_m)
    # ---- (2) resource-only test (sink never limiting) for every design ----
    res_res = run_designs(archs, geo, well, surf, None, sim)
    rrows = evaluate(res_res, case.params, sim.distance_m)

    design_df = pd.DataFrame([{k: v for k, v in s.items() if k != "capex_items"} for _, s in rows])
    design_df.to_csv(out / "designs_customer_dispatch.csv", index=False)
    resource_df = pd.DataFrame([{k: v for k, v in s.items() if k != "capex_items"} for _, s in rrows])
    resource_df.to_csv(out / "designs_resource_test.csv", index=False)

    best = best_by_arch(rows)
    best_u = best_by_arch(rows, allow_unvalidated=True)
    best_res = best_by_arch(rrows, key="geo_capability_kW_y20", allow_unvalidated=False)
    best_df = pd.DataFrame([{k: v for k, v in s.items() if k != "capex_items"} for a, (r, s) in sorted(best.items())])
    best_df.to_csv(out / "best_by_architecture.csv", index=False)
    resmax_df = pd.DataFrame([{**{k: s[k] for k in ("architecture", "design", "status", "geo_capability_kW_t0",
                                                    "geo_capability_kW_y1", "geo_capability_kW_y10",
                                                    "geo_capability_kW_y20", "E_geo_MWh_total",
                                                    "y20_over_y3_capability", "sustainable_80pct")}}
                              for a, (r, s) in sorted(best_res.items())])
    resmax_df.to_csv(out / "resource_maximum_by_architecture.csv", index=False)
    capex_rows = []
    for a, (r, s) in sorted(best.items()):
        for item, val in s["capex_items"].items():
            capex_rows.append(dict(architecture=a, item=item, usd=val))
    pd.DataFrame(capex_rows).to_csv(out / "capex_breakdown.csv", index=False)
    ts_rows = []
    for a, (r, s) in sorted(best.items()):
        for m in range(r.months):
            ts_rows.append(dict(architecture=a, month=m, Q_geo_cap_kW=r.Q_geo_cap[m] / 1e3,
                                Q_geo_kW=r.Q_geo[m] / 1e3, Q_useful_kW=r.Q_useful[m] / 1e3,
                                load_kW=r.load[m] / 1e3, W_comp_kW=r.W_comp[m] / 1e3,
                                W_pump_source_kW=r.W_pump_source[m] / 1e3, W_delivery_kW=r.W_delivery[m] / 1e3,
                                T_source_C=r.T_source[m], COP=r.cop[m]))
    pd.DataFrame(ts_rows).to_csv(out / "timeseries_best.csv", index=False)

    # ---- (3) fluid screening (thermosiphon, resource mode, compact grid) ----
    screen = ts_grid(geo, surf, fluids=SCREEN_FLUIDS, compact=True)
    scr = run_designs(screen, geo, well, surf, None, sim)
    scr_df = pd.DataFrame([dict(fluid=r.arch.ts.fluid, architecture=r.arch.arch_id, T_top=r.arch.ts.T_top,
                                insulated_m=r.arch.ts.insulated_length, liquid=r.arch.ts.liquid_distribution,
                                status=r.status, flags="; ".join(r.flags),
                                geo_kW_y1=r.summary()["geo_capability_kW_y1"],
                                geo_kW_y20=r.summary()["geo_capability_kW_y20"],
                                Tsat_bottom=r.diagnostics.get("Tsat_bottom"),
                                inventory_kg=r.quantities.get("inventory_kg"),
                                p_stag_bar=r.quantities.get("p_stag_bar")) for r in scr])
    scr_df.to_csv(out / "fluid_screening.csv", index=False)

    # ---- (4) electricity-price sweep (physics fixed; best design re-picked per price) ----
    sweep = []
    for price in (0.08, 0.10, 0.13, 0.15, 0.20, 0.25, 0.30, 0.40, 0.45):
        p = dict(case.params, electricity_price=price)
        b = best_by_arch(evaluate(res_cust, p, sim.distance_m))
        for a, (r, s) in b.items():
            sweep.append(dict(electricity_price=price, architecture=a, lcoh=s["lcoh"], design=s["design"]))
    sweep_df = pd.DataFrame(sweep)
    sweep_df.to_csv(out / "electricity_sweep.csv", index=False)

    # ---- (5) tornado on LCOH ratio best-TS / best-C ----
    def ratio(params):
        r = ts_vs_c(rows, params, sim.distance_m)
        return float(r[0][0] / r[1][0]) if r else float("nan")
    base_ratio = ratio(case.params)
    torn = []
    for name, (lo, mid, hi) in case.ranges.items():
        if name in ("years",):
            continue
        rl = ratio(dict(case.params, **{name: lo}))
        rh = ratio(dict(case.params, **{name: hi}))
        torn.append(dict(parameter=name, low=lo, base=mid, high=hi, ratio_low=rl, ratio_base=base_ratio,
                         ratio_high=rh, swing=abs(rh - rl)))
    torn_df = pd.DataFrame(torn).sort_values("swing", ascending=False)
    torn_df.to_csv(out / "tornado_lcoh_ratio.csv", index=False)

    # ---- (6) Monte Carlo on cost / finance parameters ----
    mc_ranges = dict(case.ranges)
    e = case.params["electricity_price"]
    mc_ranges["electricity_price"] = (0.7 * e, e, 1.4 * e)  # MC uses +/-30-40 %; the full range is the sweep
    draws = sample_params(case.params, mc_ranges, mc_draws)
    mc = ts_vs_c(rows, draws, sim.distance_m)
    mc_u = ts_vs_c(rows, draws, sim.distance_m, allow_unvalidated=True)
    mc_summary = {}
    if mc:
        ts_min, c_min = mc
        mc_summary = dict(p_ts_cheaper=float(np.mean(ts_min < c_min)),
                          ratio_p10=float(np.percentile(ts_min / c_min, 10)),
                          ratio_p50=float(np.percentile(ts_min / c_min, 50)),
                          ratio_p90=float(np.percentile(ts_min / c_min, 90)),
                          ts_lcoh_p50=float(np.median(ts_min)), c_lcoh_p50=float(np.median(c_min)))
    if mc_u:
        mc_summary["p_ts_cheaper_incl_unvalidated"] = float(np.mean(mc_u[0] < mc_u[1]))
    pd.DataFrame([mc_summary]).to_csv(out / "monte_carlo.csv", index=False)

    # ---- (7) case-B style prospective customer (ramped demand) ----
    b2 = None
    if "b2_ramp" in case.load:
        L2 = load_series(case.load["peak_month_kW"] * 1e3, case.load["shape"], case.load["flh"], sim.years,
                         ramp=list(case.load["b2_ramp"]))
        b2_archs = [r.arch for a, (r, s) in sorted(best.items())]
        b2_res = run_designs(b2_archs, geo, well, surf, ("fixed", L2), sim)
        b2_rows = evaluate(b2_res, case.params, sim.distance_m)
        b2 = pd.DataFrame([{k: s[k] for k in ("architecture", "design", "status", "E_useful_MWh_total", "lcoh",
                                              "npv", "site_cost_per_MWh")} for _, s in b2_rows])
        b2["customer_facility_capex_reported_separately"] = case.load.get("b2_customer_facility_capex")
        b2.to_csv(out / "b2_prospective_customer.csv", index=False)

    # ---- provenance + figures + report ----
    prov = pd.DataFrame(case.provenance)
    prov.to_csv(out / "provenance.csv", index=False)
    plots.heat_vs_time(best, out / "fig_heat_vs_time.png")
    plots.depth_profiles(best, out / "fig_depth_profiles.png")
    plots.summary_bars(best, out / "fig_summary_bars.png")
    plots.electricity_crossover(sweep_df, out / "fig_electricity_crossover.png")
    plots.tornado(torn_df, out / "fig_tornado.png", f"{case.name}: LCOH ratio TS/C")

    summary = dict(case=case.name, model_version=__version__, config_hash=_hash_file(config),
                   runtime_s=round(time.time() - t0, 1), n_designs=len(archs),
                   base_lcoh_ratio_ts_over_c=base_ratio, monte_carlo=mc_summary,
                   best=[{k: s[k] for k in ("architecture", "design", "status", "lcoh", "npv",
                                            "geo_capability_kW_y1", "geo_capability_kW_y20",
                                            "E_useful_MWh_total", "SPF_system", "unmet_share",
                                            "site_cost_per_MWh", "incumbent_only_cost_per_MWh", "capex")}
                         for a, (r, s) in sorted(best.items())],
                   best_incl_unvalidated={a: dict(design=s["design"], status=s["status"], lcoh=s["lcoh"])
                                          for a, (r, s) in sorted(best_u.items())},
                   energy_residual_max=float(max(abs(r.energy_residual) for r in res_cust)))
    with open(out / "summary.json", "w") as fh:
        json.dump(summary, fh, indent=2, default=float)
    _write_report(case, out, summary, best_df, resmax_df, scr_df, torn_df, mc_summary, sweep_df, b2)
    return summary


def _hash_file(path) -> str:
    p = Path(path)
    if not p.exists():
        from .schema import CONFIG_DIR
        p = CONFIG_DIR / path
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _fmt(df: pd.DataFrame, cols, floatfmt="{:.1f}") -> str:
    d = df[cols].copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].map(lambda v: floatfmt.format(v) if np.isfinite(v) else "n/a")
    header = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return header + "\n".join("| " + " | ".join(str(v) for v in row) + " |" for row in d.values) + "\n"


def _write_report(case, out, summary, best_df, resmax_df, scr_df, torn_df, mc, sweep_df, b2):
    lines = [f"# {case.name}: thermosiphon vs coaxial TEA\n\n",
             f"_{case.description}_\n",
             f"Model version {summary['model_version']}, config hash `{summary['config_hash']}`, "
             f"{summary['n_designs']} designs searched, runtime {summary['runtime_s']} s. "
             "All numbers are computed by the code from the inputs listed in `provenance.csv`; "
             "most inputs are **assumed** (see that file).\n",
             "## Economic optimum per architecture (customer dispatch, FEASIBLE designs only)\n",
             _fmt(best_df, ["architecture", "design", "status", "geo_capability_kW_y1", "geo_capability_kW_y20",
                            "E_useful_MWh_total", "SPF_system", "unmet_share", "lcoh", "site_cost_per_MWh",
                            "incumbent_only_cost_per_MWh", "npv"]),
             "\n`lcoh` = geothermal-only levelised cost of useful heat [$/MWh]; `site_cost_per_MWh` blends in "
             "backup heat for unmet load; `incumbent_only_cost_per_MWh` is the customer's cost with no geothermal.\n",
             "## Resource test: maximum year-20 capability per architecture (sink never limiting)\n",
             _fmt(resmax_df, list(resmax_df.columns)),
             "\n## Thermosiphon working-fluid screening (resource mode)\n",
             _fmt(scr_df.groupby(["fluid", "architecture"]).agg(
                 best_geo_kW_y20=("geo_kW_y20", "max"),
                 statuses=("status", lambda s: ",".join(sorted(set(s))))).reset_index(),
                 ["fluid", "architecture", "best_geo_kW_y20", "statuses"]),
             "\n## Thermosiphon vs coaxial\n",
             f"* Base-case LCOH ratio (best thermosiphon / best coaxial, FEASIBLE designs): "
             f"**{summary['base_lcoh_ratio_ts_over_c']:.2f}**\n"]
    if mc:
        lines.append(f"* Monte Carlo over cost/finance inputs ({len(case.ranges)} ranged parameters): "
                     f"P(thermosiphon cheaper) = **{mc.get('p_ts_cheaper', float('nan')):.2f}** "
                     f"(incl. UNVALIDATED designs: {mc.get('p_ts_cheaper_incl_unvalidated', float('nan')):.2f}); "
                     f"ratio P10/P50/P90 = {mc.get('ratio_p10', 0):.2f} / {mc.get('ratio_p50', 0):.2f} / "
                     f"{mc.get('ratio_p90', 0):.2f}\n")
    lines.append("\n### Largest drivers of the TS/C cost ratio (tornado)\n")
    lines.append(_fmt(torn_df.head(10), ["parameter", "low", "base", "high", "ratio_low", "ratio_high"],
                      "{:.3g}"))
    lines.append("\n### Electricity-price sweep (LCOH, $/MWh)\n")
    piv = sweep_df.pivot_table(index="electricity_price", columns="architecture", values="lcoh").reset_index()
    piv["electricity_price"] = piv["electricity_price"].map(lambda v: f"${v:.2f}/kWh")
    lines.append(_fmt(piv, list(piv.columns), "{:.0f}"))
    if b2 is not None:
        lines.append("\n## B2: prospective (ramped) customer\n")
        lines.append(_fmt(b2, list(b2.columns)))
        lines.append("\nThe customer facility capex is **not** in the geothermal LCOH.\n")
    lines.append("\n## Figures\n\n![heat](fig_heat_vs_time.png)\n![depth](fig_depth_profiles.png)\n"
                 "![bars](fig_summary_bars.png)\n![elec](fig_electricity_crossover.png)\n![tornado](fig_tornado.png)\n")
    lines.append("\nSee `../../MODEL_LIMITATIONS.md` before using any number here.\n")
    text = "".join(lines)
    text = re.sub(r"\n(#+ )", r"\n\n\1", text)
    text = re.sub(r"(#+ [^\n]*\n)(?=[|*_!S`])", r"\1\n", text)
    (out / "report.md").write_text(text)
