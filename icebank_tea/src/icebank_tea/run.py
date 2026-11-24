"""Run the ice-bank TEA for every case and write outputs/ and RESULTS.md.

    python -m icebank_tea.run            # full run (~2 min)
    python -m icebank_tea.run --quick    # coarse grid, for testing
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .cases import CASES, Case, day_of_year, month_of_doy
from .costs import AL_WORLD, CostInputs, crf, pit_usd_per_m3, unit_bom, with_foak
from .store import KWH_PER_M3_ICE, Design, Physics, simulate
from .weather import CLIMATES, chained_years, freezing_degree_days

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
BACKUPS = {"full": 1.0, "partial": 0.3, "none": 0.0}
BACKUP_LABEL = {"full": "Ice + full backup chiller", "partial": "Ice + 30% backup chiller", "none": "Ice only (no chiller)"}
RELIABILITY = 0.001  # worst-year unmet cooling must be <= 0.1% of a median year's cooling


def series(case: Case, years: int, seed0: int = 1000, t_air=None):
    cl = CLIMATES[case.climate]
    t = chained_years(cl, years, seed0) if t_air is None else t_air
    doy = day_of_year(len(t))
    return t, case.load_w(t, doy)


def monthly_peaks(x, month, warm=184 * 24):
    """(Y, 12) monthly maximum of an hourly series, calendar years after the warm-up."""
    Y = (len(x) - warm) // 8760
    out = np.zeros((Y, 12))
    for y in range(Y):
        sl = slice(warm + y * 8760, warm + (y + 1) * 8760)
        np.maximum.at(out[y], month[sl], x[sl])
    return out


def demand_cost(peaks_kw, case: Case):
    """Median-year demand charges for (Y, 12[, K]) monthly peak kW."""
    r = case.demand_rates()
    per_year = np.tensordot(peaks_kw, r, axes=([1], [0])) if peaks_kw.ndim == 2 else np.einsum("ymk,m->yk", peaks_kw, r)
    return np.median(per_year, axis=0)


def water_usd_per_mwh_rejected(case: Case, ci: CostInputs) -> float:
    """Tower / evaporative-condenser water cost per MWh of heat rejected (0 for air-cooled plants)."""
    if case.heat_rejection != "tower":
        return 0.0
    evap = ci.evap_m3_per_mwh_rej
    blow = evap / (ci.cycles_of_conc - 1)
    makeup = evap + blow
    sewer_m3 = makeup if case.sewer_on == "makeup" else blow
    return ci.water_price_mult * (makeup * (case.water_usd_m3 + ci.tower_chem_usd_m3) + sewer_m3 * case.sewer_usd_m3)


def water_m3_per_mwh_rejected(case: Case, ci: CostInputs) -> float:
    if case.heat_rejection != "tower":
        return 0.0
    return ci.evap_m3_per_mwh_rej * ci.cycles_of_conc / (ci.cycles_of_conc - 1)


def bau(case: Case, t, load, ci: CostInputs, warm=184 * 24):
    """Annual cost of BAU cooling (median year).

    Electricity covers the chiller (COP) plus auxiliaries (chilled-water pumps; condenser pumps and tower fans
    for tower plants). Tower plants also pay for makeup water, treatment and sewer.
    """
    peak_kw = case.peak_w / 1e3
    cop = case.cop(t)
    aux = case.aux_kw_per_kwth()
    kwe = load * (1.0 / cop + aux) / 1e3                               # hourly BAU electric draw, kW
    rej_mwh = load * (1.0 + 1.0 / cop) / 1e6                           # heat rejected each hour, MWh
    month = month_of_doy(day_of_year(len(t)))
    per_year_mwh, per_year_kwh_e, per_year_rej = [], [], []
    for y in range((len(t) - warm) // 8760):
        sl = slice(warm + y * 8760, warm + (y + 1) * 8760)
        per_year_mwh.append(load[sl].sum() / 1e6)
        per_year_kwh_e.append(kwe[sl].sum())
        per_year_rej.append(rej_mwh[sl].sum())
    cold = float(np.median(per_year_mwh)); kwh_e = float(np.median(per_year_kwh_e))
    rej = float(np.median(per_year_rej))
    chiller_pk = monthly_peaks(kwe, month, warm)                       # kWe, assumed to set the site's monthly peak
    pump_pk = monthly_peaks(load / ci.pump_cop / 1e3, month, warm)     # ice-bank discharge pumps
    mech = peak_kw * case.redundancy * case.mech_usd_kw + peak_kw * case.extra_bau_capex_usd_kw
    peak_kwe = peak_kw * (1.0 / case.peak_cop() + aux)
    svc = peak_kwe * ci.elec_service_usd_kwe
    a = crf(ci.rate, ci.life_mech)
    parts = dict(plant=mech * a, elec_service=svc * a, energy=kwh_e * case.elec_usd_kwh,
                 demand=float(demand_cost(chiller_pk, case)), water=rej * water_usd_per_mwh_rejected(case, ci),
                 om=mech * ci.mech_om_frac)
    total = sum(parts.values())
    return dict(pump_peak_kw=pump_pk, cold_mwh=cold, cold_p90_mwh=float(np.percentile(per_year_mwh, 90)), kwh_e=kwh_e,
                mean_cop=cold * 1e3 / max(kwh_e, 1e-9), rej_per_mwh=rej / max(cold, 1e-9),
                water_m3=rej * water_m3_per_mwh_rejected(case, ci), capex=mech + svc, parts=parts, total=total,
                lcoc=total / max(cold, 1e-9), peak_kwe=peak_kwe)


def evaluate(case: Case, designs, n_units, sim, ci: CostInputs, b: dict):
    """Annual cost of every design x unit count x backup level. Returns list of dict rows."""
    peak_kw = case.peak_w / 1e3
    M = len(n_units)
    a_ice = crf(ci.rate, ci.life_icebank) * (1 + ci.rate) ** ci.construction_lag_years
    a_mech = crf(ci.rate, ci.life_mech)
    cold = b["cold_mwh"]
    pump_pk = b["pump_peak_kw"][:, :, None]
    dem = {"full": demand_cost(sim.peak_kwe_full + pump_pk, case),
           "partial": demand_cost(sim.peak_kwe_partial + pump_pk, case),
           "none": demand_cost(np.broadcast_to(pump_pk, sim.peak_kwe_full.shape), case)}
    rows = []
    for i, d in enumerate(designs):
        bom = unit_bom(d, ci)
        for j, n in enumerate(n_units):
            k = i * M + j
            pit_m3 = n * d.pitch_m**2 * d.depth_m
            capex_units = n * bom["unit_usd"]
            capex_pit = pit_m3 * pit_usd_per_m3(pit_m3, ci)
            capex_dis = peak_kw * ci.discharge_usd_kw * 1.2
            ice_capex = capex_units + capex_pit + capex_dis
            unmet_y = sim.unmet_mwh[:, k]
            served = cold - float(np.median(unmet_y))
            for key, f in BACKUPS.items():
                if key == "full":
                    backup_mwh, left_y = float(np.median(unmet_y)), np.zeros_like(unmet_y)
                elif key == "partial":
                    backup_mwh, left_y = float(np.median(sim.backup_partial_mwh[:, k])), sim.unmet_partial_mwh[:, k]
                else:
                    backup_mwh, left_y = 0.0, unmet_y
                worst = float(left_y.max()) / max(cold, 1e-9)
                mech = f * peak_kw * case.mech_usd_kw
                # Electrical service: backup chiller + its auxiliaries, plus the ice bank's discharge pumps
                svc = (f * b["peak_kwe"] + peak_kw / ci.pump_cop) * ci.elec_service_usd_kwe
                energy = (backup_mwh * 1e3 / b["mean_cop"] + served * 1e3 / ci.pump_cop) * case.elec_usd_kwh
                water = backup_mwh * b["rej_per_mwh"] * water_usd_per_mwh_rejected(case, ci)
                parts = dict(thermosiphons=capex_units * a_ice, pit=capex_pit * a_ice, discharge=capex_dis * a_ice,
                             backup_plant=mech * a_mech, elec_service=svc * a_mech, energy=energy,
                             demand=float(dem[key][k]), water=water,
                             om=ice_capex * ci.icebank_om_frac + mech * ci.mech_om_frac)
                total = sum(parts.values())
                rows.append(dict(case=case.key, backup=key, design=asdict(d), n_units=int(round(n)),
                                 unit_usd=bom["unit_usd"], pit_m3=pit_m3, pit_ha=n * d.pitch_m**2 / 1e4,
                                 ice_capex=ice_capex, backup_capex=mech + svc, parts=parts, total=total,
                                 lcoc=total / max(cold, 1e-9), ratio=total / b["total"], worst_unmet_frac=worst,
                                 feasible=worst <= RELIABILITY, kwh_ice_per_unit=float(np.median(sim.frozen_mwh[:, k])) * 1e3 / n,
                                 losses_frac=float(np.median(sim.losses_mwh[:, k])) / max(cold, 1e-9), k=k))
    return rows


def best(rows, backup):
    cands = [r for r in rows if r["backup"] == backup and r["feasible"]]
    return min(cands, key=lambda r: r["total"]) if cands else None


def grid(quick: bool):
    pitches = [1.0, 1.5] if quick else [0.8, 1.0, 1.25, 1.5, 2.0]
    conds = [25.0] if quick else [12.0, 25.0, 40.0]
    depths = [10.0] if quick else [10.0, 15.0]
    return [Design(p, a, z) for p in pitches for a in conds for z in depths]


def n_grid(b: dict, quick: bool) -> np.ndarray:
    ref = (np.pi * (0.85 / np.pi) * 9) * KWH_PER_M3_ICE  # ~650 kWh: 1 m pitch, 9 m tube, full cell
    n0 = max(b["cold_p90_mwh"] * 1e3 * 1.1 / ref, 5)
    return np.unique(np.round(n0 * np.geomspace(0.25, 6.0, 10 if quick else 28)))


def fill_dates(case, d, n, t, load, phys, warm=184 * 24):
    """Median date each winter when the store reaches 50% and 90% of its peak ice."""
    sim = simulate([d], np.array([n]), t, load, case.t_use_max, CLIMATES[case.climate].ground_c, phys, trace=True)
    tr = sim.trace
    out = []
    for w in range(len(tr) // 365):
        seg = tr[w * 365:(w + 1) * 365]
        if seg.max() <= 0:
            continue
        imax = int(np.argmax(seg)); imin = int(np.argmin(seg[:imax + 1]))  # refill starts at the low point
        lo, hi = seg[imin], seg[imax]
        i50 = imin + int(np.argmax(seg[imin:] >= lo + 0.5 * (hi - lo)))
        i90 = imin + int(np.argmax(seg[imin:] >= lo + 0.9 * (hi - lo)))
        out.append((i50, i90, float(hi), float(lo)))
    if not out:
        return None
    md = lambda i: (dt.date(2025, 7, 1) + dt.timedelta(days=int(np.median([o[i] for o in out])))).strftime("%b %d")
    return dict(half=md(0), ninety=md(1), peak_ice_frac=float(np.median([o[2] for o in out])),
                low_ice_frac=float(np.median([o[3] for o in out])))


def sensitivities(case, backup, b_fn, rows_fn, ci, base_row, base_bau):
    """One-at-a-time changes for one backup configuration of a case.

    Each entry records the ice/BAU ratio and both annualized costs ($/MWh of the base case's cooling)
    at the low and high input, with the ice bank re-optimized each time.
    """
    out = []

    def cost_only(label, lo_ci, hi_ci, lo_case=None, hi_case=None):
        e = dict(input=label)
        for side, cc, cs in (("low", lo_ci, lo_case or case), ("high", hi_ci, hi_case or case)):
            b = b_fn(cs, cc)
            rr = [r for r in rows_fn(cs, cc, b) if r["backup"] == backup and r["feasible"]]
            ice = min(r["total"] for r in rr) if rr else float("nan")
            e[side] = ice / b["total"]
            e[f"bau_{side}"] = b["lcoc"]
            e[f"ice_{side}"] = ice / base_bau["cold_mwh"]
        out.append(e)

    cost_only("Finished/raw index (2.0 / 3.5)", replace(ci, index=2.0), replace(ci, index=3.5))
    cost_only("Aluminium price (world $2.85 / US $5.3 x1.2)", replace(ci, al_price=AL_WORLD), replace(ci, al_price=ci.al_price * 1.2))
    cost_only("Pit cost (x0.7 / x1.5)", replace(ci, pit_mult=0.7), replace(ci, pit_mult=1.5))
    cost_only("Discount rate (6% / 10%)", replace(ci, rate=0.06), replace(ci, rate=0.10))
    cost_only("Electricity price (x0.67 / x1.5)", ci, ci, replace(case, elec_usd_kwh=case.elec_usd_kwh * 0.67),
              replace(case, elec_usd_kwh=case.elec_usd_kwh * 1.5))
    cost_only("BAU plant $/kW (x0.6 / x1.5)", ci, ci, replace(case, mech_usd_kw=case.mech_usd_kw * 0.6),
              replace(case, mech_usd_kw=case.mech_usd_kw * 1.5))
    cost_only("Electrical service cost ($0 / $1,500 per kWe)", replace(ci, elec_service_usd_kwe=0),
              replace(ci, elec_service_usd_kwe=1500))
    cost_only("Demand charge (none / x2, e.g. 12-month ratchet)", ci, ci,
              replace(case, demand_summer=0.0, demand_winter=0.0),
              replace(case, demand_summer=2 * case.demand_summer, demand_winter=2 * case.demand_winter))
    if case.heat_rejection == "tower":
        cost_only("Water + sewer price (x0.5 / x2)", replace(ci, water_price_mult=0.5), replace(ci, water_price_mult=2.0))
    elif case.key == "A":
        # One-sided: switch the BAU trim chillers to water-cooled with towers (better COP, but uses water)
        cost_only("Trim chillers (air-cooled / water-cooled + towers)", ci, ci, case,
                  replace(case, heat_rejection="tower"))
    cost_only("FOAK costs (NOAK / FOAK)", ci, with_foak(ci))
    for r in out:
        r["base"] = base_row["ratio"]
        r["bau_base"] = base_bau["lcoc"]
        r["ice_base"] = base_row["lcoc"]
    return out


def physics_sensitivity(case, backup, designs, n_units, t, load, gc, phys, trk, ci, b, base_row):
    """Condenser conductance, re-simulated (only the ice bank changes)."""
    e = dict(input="Condenser conductance (3 / 8 W/m2K)", base=base_row["ratio"], bau_base=b["lcoc"],
             ice_base=base_row["lcoc"])
    for side, u in (("low", 3.0), ("high", 8.0)):
        sim_u = simulate(designs, n_units, t, load, case.t_use_max, gc, replace(phys, u_cond=u),
                         partial_backup_w=0.3 * case.peak_w, **trk)
        rr = [r for r in evaluate(case, designs, n_units, sim_u, ci, b) if r["backup"] == backup and r["feasible"]]
        ice = min(r["total"] for r in rr) if rr else float("nan")
        e[side] = ice / b["total"]; e[f"bau_{side}"] = b["lcoc"]; e[f"ice_{side}"] = ice / b["cold_mwh"]
    return e


def run_case(case: Case, years: int, quick: bool, ci: CostInputs, phys: Physics, log=print):
    t, load = series(case, years)
    b = bau(case, t, load, ci)
    designs = grid(quick)
    n_units = n_grid(b, quick)
    gc = CLIMATES[case.climate].ground_c
    trk = dict(month=month_of_doy(day_of_year(len(t))),
               kwe_per_w=(1.0 / case.cop(t) + case.aux_kw_per_kwth()) / 1e3)
    log(f"[{case.key}] simulating {len(designs)} designs x {len(n_units)} sizes over {years} years ...")
    sim = simulate(designs, n_units, t, load, case.t_use_max, gc, phys, partial_backup_w=0.3 * case.peak_w, **trk)
    cache = {"sim": sim}

    def rows_fn(cs, cc, bb):
        return evaluate(cs, designs, n_units, cache["sim"], cc, bb)

    def b_fn(cs, cc):
        return bau(cs, t, cs.load_w(t, day_of_year(len(t))) if cs is not case else load, cc)

    rows = rows_fn(case, ci, b)
    res = dict(case=case, bau=b, fdd=freezing_degree_days(t[184 * 24:]) / years, best={}, sens=None, fill=None,
               foak={})
    for key in BACKUPS:
        res["best"][key] = best(rows, key)
        fr = rows_fn(case, with_foak(ci), bau(case, t, load, with_foak(ci)))
        res["foak"][key] = best(fr, key)
    # The configuration to stress-test: cheapest feasible one
    feas = [r for r in res["best"].values() if r]
    top = min(feas, key=lambda r: r["total"])
    res["top"] = top
    res["sens"] = sensitivities(case, top["backup"], b_fn, rows_fn, ci, top, b)
    res["sens"].append(physics_sensitivity(case, top["backup"], designs, n_units, t, load, gc, phys, trk, ci, b, top))
    # Ice-only sensitivities as well (for the charts), unless that is already the top configuration
    ice = res["best"]["none"]
    if ice is not None:
        if top["backup"] == "none":
            res["sens_none"] = res["sens"]
        else:
            res["sens_none"] = sensitivities(case, "none", b_fn, rows_fn, ci, ice, b)
            res["sens_none"].append(physics_sensitivity(case, "none", designs, n_units, t, load, gc, phys, trk, ci, b, ice))
    if res["best"]["none"]:
        r = res["best"]["none"]
        res["fill"] = fill_dates(case, Design(**r["design"]), r["n_units"], t, load, phys)
    return res


def fmt_design(d):
    return f"{d['pitch_m']:.2g} m pitch, {d['cond_area_m2']:.0f} m2 fins, {d['depth_m']:.0f} m deep"


def write_outputs(results, ci, years, phys):
    OUT.mkdir(exist_ok=True)
    with open(OUT / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "config", "bau_lcoc_usd_mwh", "ice_lcoc_usd_mwh", "ratio_vs_bau", "foak_ratio",
                    "n_units", "unit_usd", "kwh_ice_per_unit", "pitch_m", "cond_area_m2", "depth_m", "pit_m3",
                    "pit_ha", "worst_year_unmet_pct", "losses_pct", "bau_demand_usd_mwh", "ice_demand_usd_mwh"])
        for res in results:
            for key, r in res["best"].items():
                if not r:
                    w.writerow([res["case"].key, BACKUP_LABEL[key]] + ["no feasible design"] + [""] * 15)
                    continue
                fo = res["foak"][key]
                d = r["design"]
                w.writerow([res["case"].key, BACKUP_LABEL[key], round(res["bau"]["lcoc"], 1), round(r["lcoc"], 1),
                            round(r["ratio"], 3), round(fo["ratio"], 3) if fo else "", r["n_units"],
                            round(r["unit_usd"]), round(r["kwh_ice_per_unit"]), d["pitch_m"], d["cond_area_m2"],
                            d["depth_m"], round(r["pit_m3"]), round(r["pit_ha"], 2), round(100 * r["worst_unmet_frac"], 3),
                            round(100 * r["losses_frac"], 1),
                            round(res["bau"]["parts"]["demand"] / res["bau"]["cold_mwh"], 1),
                            round(r["parts"]["demand"] / res["bau"]["cold_mwh"], 1)])
    with open(OUT / "sensitivity.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "config", "input", "base_ratio", "low_case_ratio", "high_case_ratio",
                    "bau_base_usd_mwh", "bau_low_usd_mwh", "bau_high_usd_mwh",
                    "ice_base_usd_mwh", "ice_low_usd_mwh", "ice_high_usd_mwh"])
        for res in results:
            sets = [(res["top"]["backup"], res["sens"])]
            if res.get("sens_none") is not None and res["sens_none"] is not res["sens"]:
                sets.append(("none", res["sens_none"]))
            for key, sens in sets:
                for s in sens:
                    w.writerow([res["case"].key, BACKUP_LABEL[key], s["input"]] +
                               [round(s[k], 3) for k in ("base", "low", "high")] +
                               [round(s[k], 1) for k in ("bau_base", "bau_low", "bau_high",
                                                         "ice_base", "ice_low", "ice_high")])
    bom_rows = []
    for res in results:
        r = res["top"]
        b = unit_bom(Design(**r["design"]), ci)
        bom_rows.append(dict(case=res["case"].key, **{k: round(v, 2) for k, v in b.items()}))
    with open(OUT / "unit_bom.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bom_rows[0].keys()))
        w.writeheader(); w.writerows(bom_rows)
    (OUT / "run_meta.json").write_text(json.dumps(dict(years=years, reliability=RELIABILITY, costs=asdict(ci),
                                                        physics=asdict(phys)), indent=1))
    write_results_md(results, ci, years)


def write_results_md(results, ci, years):
    L = []
    L.append("# Ice bank TEA: results\n")
    L.append("Generated by `python -m icebank_tea.run`. Ratio = ice-bank annual cost / BAU annual cost "
             "(below 1 means the ice bank is cheaper). NOAK costs unless marked FOAK.\n")
    L.append(f"Weather: {years} synthetic years per site. Store must leave no more than {RELIABILITY:.1%} of a "
             "median year's cooling unmet in its worst year (configs without a full backup chiller).\n")
    L.append("## Headline (demand charges included)\n")
    L.append("Cost of cooling in $ per MWh of cold delivered (median year), and the ratio to BAU in brackets.\n")
    L.append("| Case | Why this case | BAU $/MWh | of which demand charges | Ice + full backup | Ice + 30% backup | Ice only | Ice only at FOAK |")
    L.append("|---|---|---|---|---|---|---|---|")
    for res in results:
        c = res["case"]; b = res["best"]; fo = res["foak"]; bb = res["bau"]
        cell = lambda r: f"{r['lcoc']:.0f} ({r['ratio']:.2f})" if r else "not feasible"
        L.append(f"| {c.title} | {c.why} | {bb['lcoc']:.0f} | {bb['parts']['demand'] / bb['cold_mwh']:.0f} | "
                 f"{cell(b['full'])} | {cell(b['partial'])} | {cell(b['none'])} | {cell(fo['none'])} |")
    L.append("\nFOAK costs are quoted against the BAU cost above, so the FOAK ratio is FOAK $/MWh / BAU $/MWh.\n")
    L.append("\n## Best ice-only design per case\n")
    L.append("| Case | Thermosiphons | Cost per unit | Ice per unit per winter | Design | Pit | Worst-year unmet | Store 50% / 90% full |")
    L.append("|---|---|---|---|---|---|---|---|")
    for res in results:
        r = res["best"]["none"]
        if not r:
            L.append(f"| {res['case'].key} | no feasible design in the grid | | | | | | |")
            continue
        fd = res["fill"] or {}
        L.append(f"| {res['case'].key} | {r['n_units']:,} | ${r['unit_usd']:.0f} | {r['kwh_ice_per_unit']:.0f} kWh | "
                 f"{fmt_design(r['design'])} | {r['pit_m3']:,.0f} m3 ({r['pit_ha']:.2f} ha) | "
                 f"{100 * r['worst_unmet_frac']:.2f}% | {fd.get('half', '-')} / {fd.get('ninety', '-')} |")
    L.append("\n## Where the money goes ($ per MWh of cold)\n")
    L.append("Ice-bank options:\n")
    L.append("| Case | Config | Thermosiphons | Pit | Pumps + HX | Backup chiller | Electrical service | Energy | "
             "Demand charges | Water | O&M | Total |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for res in results:
        cold = res["bau"]["cold_mwh"]
        for key in BACKUPS:
            r = res["best"][key]
            if r is None:
                continue
            p = r["parts"]
            L.append(f"| {res['case'].key} | {BACKUP_LABEL[key]} | " + " | ".join(
                f"{p[k] / cold:.0f}" for k in ("thermosiphons", "pit", "discharge", "backup_plant", "elec_service",
                                               "energy", "demand", "water", "om")) + f" | {r['lcoc']:.0f} |")
    L.append("\nConventional (BAU):\n")
    L.append("| Case | Heat rejection | Chiller plant | Electrical service | Energy (chiller + pumps/fans) | "
             "Demand charges | Water + sewer | O&M | Total | Water use, m3/yr |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for res in results:
        bb = res["bau"]; p = bb["parts"]; cold = bb["cold_mwh"]; c = res["case"]
        L.append(f"| {c.key} | {'cooling towers' if c.heat_rejection == 'tower' else 'air-cooled'} | " + " | ".join(
            f"{p[k] / cold:.0f}" for k in ("plant", "elec_service", "energy", "demand", "water", "om"))
            + f" | {bb['lcoc']:.0f} | {bb['water_m3']:,.0f} |")
    L.append("\n## Sensitivities (best configuration per case; ratio at the low / high input)\n")
    L.append("| Case | Input | Base | Low | High |")
    L.append("|---|---|---|---|---|")
    for res in results:
        for s in sorted(res["sens"], key=lambda s: -abs(np.nan_to_num(s["high"]) - np.nan_to_num(s["low"]))):
            L.append(f"| {res['case'].key} | {s['input']} | {s['base']:.2f} | {s['low']:.2f} | {s['high']:.2f} |")
    L.append("\n## Case notes\n")
    for res in results:
        c = res["case"]
        L.append(f"- **{c.key}. {c.title}.** {c.notes} Demand charge: {c.demand_note} "
                 f"Median freezing degree-days {res['fdd']:.0f} degC-days; "
                 f"median-year cooling {res['bau']['cold_mwh']:,.0f} MWh.")
    L.append("\nWater: " + " ".join(f"{c.key}: {c.water_note}" for c in (r["case"] for r in results) if c.water_note)
             + " Tower makeup = evaporation (1.6 m3 per MWh of heat rejected, ~1.8 gal per ton-hour) + blowdown at "
             "4 cycles of concentration, plus $0.15/m3 treatment chemicals.")
    L.append("\nDemand charges bill the chiller's (and discharge pumps') highest draw in each month, assuming it adds "
             "fully to the site's monthly peak. Ratchets, interim surcharges and coincident-peak tariffs are not "
             "modelled; the x2 sensitivity brackets them.")
    (ROOT / "RESULTS.md").write_text("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--years", type=int, default=12)
    ap.add_argument("--cases", default="ABCD")
    a = ap.parse_args(argv)
    ci, phys = CostInputs(), Physics()
    years = 4 if a.quick else a.years
    results = [run_case(CASES[k], years, a.quick, ci, phys) for k in a.cases]
    write_outputs(results, ci, years, phys)
    try:
        from .charts import make_charts
        for f in make_charts(results, ci, years):
            print("wrote", f)
    except ImportError:
        print("matplotlib not installed: skipping charts (pip install -e .[charts])")
    for res in results:
        print(res["case"].key, {k: (round(v["ratio"], 2) if v else None) for k, v in res["best"].items()},
              "BAU", round(res["bau"]["lcoc"]), "$/MWh")


if __name__ == "__main__":
    main()
