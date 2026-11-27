"""Run all cases, sensitivities and checks; write outputs/*.csv, outputs/results.json and RESULTS.md."""
from __future__ import annotations

import csv
import json
import math
from dataclasses import replace
from pathlib import Path

from .cases import (BEAVER_CREEK, BETHEL, CASES, DEADHORSE, ROSS_RIVER, case_a, case_b, case_c, case_d,
                    dry_creek_check)
from .model import Costs, Physics, Unit, USD_PER_CAD, crf, platform_unit_cost, incumbent_unit_cost, \
    winter_extraction_kwh

OUT = Path(__file__).resolve().parents[2] / "outputs"


def evaluate(key: str, c: Costs, p: Physics, **kw) -> list[dict]:
    title, fn, fu, scale = CASES[key]
    opts = fn(c, p, **kw)
    foak = fn(c, p, foak=True, **kw)
    opts.update({k: v for k, v in foak.items() if "FOAK" in k})
    bau_name = next(k for k in opts if "BAU" in k)
    bau = opts[bau_name].npv(c.rate, c.life)
    rows = []
    for name, b in opts.items():
        npv = b.npv(c.rate, c.life)
        rows.append(dict(case=key, option=name, units=b.units, capex=b.capex, capex_per_fu=b.capex / scale,
                         npv=npv, annual_per_fu=npv * crf(c.rate, c.life) / scale, ratio=npv / bau,
                         note=b.note, items={k: round(v) for k, v in b.items.items()},
                         annual={k: round(v) for k, v in b.annual.items()}))
    return rows


def platform_ratio(key: str, c: Costs, p: Physics, **kw) -> float:
    rows = evaluate(key, c, p, **kw)
    plat = next(r for r in rows if "Platform" in r["option"] and "NOAK" in r["option"])
    best_alt = min(r["npv"] for r in rows if "Platform" not in r["option"])
    return plat["npv"] / best_alt


SENS = [
    ("Drilling $/m (250 / 500)", lambda c, p, v: (replace(c, drill_vert_per_m=v, drill_incl_per_m=v), p, {}), 250, 500),
    ("Platform drilling cut (0% / 40%)", lambda c, p, v: (c, p, {"_drill_cut": v}), 0.0, 0.40),
    ("Mobilization ($75k / $400k)", lambda c, p, v: (replace(c, mobilization=v), p, {}), 75_000, 400_000),
    ("Finished/raw index (2.0 / 3.5)", lambda c, p, v: (replace(c, index=v), p, {}), 2.0, 3.5),
    ("Warming (0.3 / 0.8 C per decade)", lambda c, p, v: (c, p, {"_warm": v}), 0.3, 0.8),
    ("Condenser U (3 / 8 W/m2K)", lambda c, p, v: (c, replace(p, u_cond=v), {}), 3.0, 8.0),
    ("Discount rate (6% / 10%)", lambda c, p, v: (replace(c, rate=v), p, {}), 0.06, 0.10),
    ("Engineering fixed ($75k / $300k)", lambda c, p, v: (replace(c, eng_fixed=v), p, {}), 75_000, 300_000),
]

CASE_SENS = {
    "A": [("Thermopile depth (9 / 15 m)", "tp_depth", 9.0, 15.0),
          ("P(relevel) on plain piles (0.2 / 0.9)", "p_relevel_conv", 0.2, 0.9)],
    "B": [("Hall air temp (18 / 32 C)", "t_in", 18.0, 32.0)],
    "C": [("Relevel interval (3 / 10 yr)", "relevel_every", 3, 10),
          ("Thaw-bulb depth (2 / 8 m)", "thaw_depth", 2.0, 8.0)],
    "D": [("Repair CAD/km/yr (15k / 120k)", "repair_cad", 15_000.0, 120_000.0)],
}

CLIMS = {"A": BETHEL, "B": DEADHORSE, "C": ROSS_RIVER, "D": BEAVER_CREEK}


def _apply(key, c, p, fn, v):
    from . import model
    c2, p2, extra = fn(c, p, v)
    kw = {}
    if "_warm" in extra:
        kw["clim"] = replace(CLIMS[key], warming_c_per_decade=extra["_warm"])
    if "_drill_cut" in extra:
        cut = extra["_drill_cut"]
        orig = model.platform_costs

        def patched(cc, foak=False, _o=orig):
            r = _o(cc, foak)
            return r if foak else replace(r, drill_reduction=cut)
        import permafrost_tea.cases as cases_mod
        cases_mod.platform_costs = patched
        try:
            return platform_ratio(key, c2, p2, **kw)
        finally:
            cases_mod.platform_costs = orig
    return platform_ratio(key, c2, p2, **kw)


def sensitivities(c: Costs, p: Physics) -> list[dict]:
    rows = []
    for key in CASES:
        base = platform_ratio(key, c, p)
        for name, fn, lo, hi in SENS:
            rows.append(dict(case=key, input=name, base=base, low=_apply(key, c, p, fn, lo),
                             high=_apply(key, c, p, fn, hi)))
        for name, arg, lo, hi in CASE_SENS[key]:
            rows.append(dict(case=key, input=name, base=base, low=platform_ratio(key, c, p, **{arg: lo}),
                             high=platform_ratio(key, c, p, **{arg: hi})))
    return rows


def capacity_decline(p: Physics) -> list[dict]:
    units = {
        "A": Unit(evap_len_m=12, cond_area_m2=6, layout="thermopile", spacing_m=3.5),
        "B": Unit(evap_len_m=50, cond_area_m2=40, layout="pad", spacing_m=2.5),
        "C": Unit(evap_len_m=18.3, cond_area_m2=20, layout="inclined", spacing_m=2.0, riser_len_m=4),
        "D": Unit(evap_len_m=34, cond_area_m2=19.5, layout="inclined", spacing_m=7.0, riser_len_m=4),
    }
    rows = []
    for k, u in units.items():
        cl = CLIMS[k]
        q0, q30 = winter_extraction_kwh(u, p, cl, 0), winter_extraction_kwh(u, p, cl, 30)
        rows.append(dict(case=k, site=cl.name, freezing_index_now=round(cl.freezing_index(0)),
                         freezing_index_30yr=round(cl.freezing_index(30)), kwh_now=round(q0), kwh_30yr=round(q30),
                         decline=1 - q30 / q0))
    return rows


def road_breakeven(c: Costs, p: Physics) -> dict:
    """Installed $/km at which thermosyphons match repair-as-it-settles and ACE (30 yr, 8%)."""
    rows = {r["option"]: r for r in evaluate("D", c, p)}
    repair = rows["Repair as it settles (BAU)"]["npv"]
    plat = rows["Platform sloped thermosyphons (NOAK)"]
    resid_npv = plat["npv"] - plat["capex"]
    # repair cost per km-yr at which the platform matches repair-as-it-settles (residual repair = 25%)
    from .model import npv_factor
    f = npv_factor(c.rate, c.life)
    fixed = plat["npv"] - 0.25 * repair  # platform NPV without its residual-repair stream
    be_repair_yr = fixed / (f * (1 - 0.25))
    return dict(breakeven_repair_usd_km_yr=be_repair_yr, vs_repair=repair - resid_npv, vs_ace=rows["Air-convection embankment"]["npv"] - resid_npv,
                platform_capex=plat["capex"], incumbent_capex=rows["Incumbent sloped thermosyphons"]["capex"])


def main() -> None:
    c, p = Costs(), Physics()
    OUT.mkdir(exist_ok=True)
    results = {k: evaluate(k, c, p) for k in CASES}
    sens = sensitivities(c, p)
    decline = capacity_decline(p)
    dc = dry_creek_check(c)
    be = road_breakeven(c, p)
    u_plat = Unit(evap_len_m=12, cond_area_m2=6, layout="thermopile")
    unit_costs = dict(platform_thermopile_insert=platform_unit_cost(u_plat, c),
                      incumbent_thermopile_insert=incumbent_unit_cost(u_plat, c),
                      platform_dry_creek_unit=platform_unit_cost(Unit(34, 19.5, 4.0, layout="inclined"), c),
                      incumbent_dry_creek_unit=incumbent_unit_cost(Unit(34, 19.5, 4.0, layout="inclined"), c))
    with open(OUT / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "option", "units", "capex_usd", "capex_per_fu", "npv_30yr", "annual_per_fu", "ratio_vs_bau", "note"])
        for rows in results.values():
            for r in rows:
                w.writerow([r["case"], r["option"], r["units"], round(r["capex"]), round(r["capex_per_fu"], 1),
                            round(r["npv"]), round(r["annual_per_fu"], 2), round(r["ratio"], 3), r["note"]])
    with open(OUT / "sensitivity.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case", "input", "base", "low", "high"])
        w.writeheader()
        for r in sens:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    (OUT / "results.json").write_text(json.dumps(dict(results=results, sensitivity=sens, capacity_decline=decline,
                                                      dry_creek_usd=dc, road_breakeven=be, unit_costs=unit_costs),
                                                 indent=1, default=float))
    print(json.dumps(dict(dry_creek_usd=round(dc), road_breakeven={k: round(v) for k, v in be.items()},
                          unit_costs={k: round(v) for k, v in unit_costs.items()}), indent=1))
    for k, rows in results.items():
        print("\n==", k, CASES[k][0])
        for r in rows:
            print(f"  {r['option']:45s} capex ${r['capex']/1e6:7.2f}M  {r['capex_per_fu']:>11,.0f}/fu  "
                  f"NPV ${r['npv']/1e6:6.2f}M  ratio {r['ratio']:.2f}  | {r['note']}")
    print("\ncapacity decline:")
    for r in decline:
        print(" ", r)
    print("\nsensitivity (platform NOAK / best alternative):")
    for r in sens:
        print(f"  {r['case']} {r['input']:42s} {r['base']:.2f}  {r['low']:.2f} / {r['high']:.2f}")


if __name__ == "__main__":
    main()
