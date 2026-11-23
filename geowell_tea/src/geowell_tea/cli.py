"""Command-line interface.

    python -m geowell_tea.cli validate
    python -m geowell_tea.cli run configs/case_a_pa.yaml [--quick]
    python -m geowell_tea.cli envelope greenhouse_45_35 [--k 1.5 2.5 4.0] [--threshold 0.9]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import time

import pandas as pd

from .pipeline import OUT_ROOT, run_case


def cmd_validate(args):
    from .schema import load_case
    from . import validate as v
    out = OUT_ROOT / "validation"
    out.mkdir(parents=True, exist_ok=True)
    rock = v.rock_line_source_check()
    with open(out / "rock_line_source.json", "w") as fh:
        json.dump(rock, fh, indent=2, default=float)
    print(json.dumps(rock, indent=1, default=float))
    tables = {
        "xiongan_d34": v.xiongan_d34,
        "zolfagharroshan_2024": v.zolfagharroshan_2024,
        "gruber_2026": v.gruber_2026,
        "taiyuan_2_via_gruber": v.taiyuan_2_via_gruber,
        "hdr_4000m_water": v.hdr_4000m_water,
        "brown_2026_dbhe_trends": v.brown_2026_dbhe_trends,
        "penn_state_sanity": lambda: v.penn_state_sanity(load_case("case_a_pa.yaml")),
    }
    only = set(getattr(args, "only", None) or tables)
    for name, fn in tables.items():
        if name not in only:
            continue
        t0 = time.time()
        df = pd.DataFrame(fn())
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"\n== {name} ({time.time() - t0:.0f} s)")
        print(df.drop(columns=[c for c in ("flags",) if c in df]).round(2).to_string())
    pd.DataFrame(v.NOT_REPRODUCED).to_csv(out / "not_reproduced.csv", index=False)

def cmd_run(args):
    if args.ku is not None and abs(args.ku - 3.2) > 1e-9:
        from .pipeline import run_variant
        w = run_variant(args.config, args.ku)
        print(w["table"].round(2).to_string())
        print(json.dumps(w["breakevens"], indent=1, default=float))
        return
    s = run_case(args.config, mc_draws=args.draws, quick=args.quick)
    print(json.dumps({k: v for k, v in s.items() if k != "what_must_be_true"}, indent=1, default=float))


def cmd_envelope(args):
    from .envelope import SCENARIOS, analyse, default_cells, run_physics
    from .schema import load_case
    from . import plots
    scen = SCENARIOS[args.scenario]
    suffix = "" if args.k == [2.5] and not args.dias else "_k" + "-".join(str(k) for k in args.k)
    out = OUT_ROOT / "envelope" / (args.scenario + suffix)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "physics.pkl"
    t = time.time()
    if cache.exists() and not args.rerun:
        results = pickle.load(open(cache, "rb"))
    else:
        cells = default_cells(scen["T_surface"])
        if args.dias:
            cells = [c for c in cells if any(abs(c[2] - D) < 1e-6 for D in args.dias)]
        results = run_physics(scen, cells, k_values=tuple(args.k), n_z=args.n_z, cache=cache)
    print(f"physics: {len(results)} cells in {time.time()-t:.0f} s")
    case = load_case(scen["case_config"])
    frames = []
    for allow in (False, True):
        df = analyse(results, case.params, case.ranges, scen["distance_m"], draws=args.draws,
                     threshold=args.threshold, allow_unvalidated=allow)
        df["includes_unvalidated"] = allow
        frames.append(df)
    df = pd.concat(frames)
    df.to_csv(out / "envelope.csv", index=False)
    # conditional envelope: what VIT price would make the thermosiphon consistently cheaper?
    cond = []
    for vit in (250, 350, 500, 700):
        p = dict(case.params, vit_per_m=vit)
        rg = {k: v for k, v in case.ranges.items() if k != "vit_per_m"}
        d = analyse(results, p, rg, scen["distance_m"], draws=args.draws, threshold=args.threshold)
        d["vit_per_m_fixed"] = vit
        cond.append(d)
    cond = pd.concat(cond)
    cond.to_csv(out / "envelope_conditional_vit_price.csv", index=False)
    print(cond.groupby(["vit_per_m_fixed", "cls"]).size())
    for allow in (False, True):
        for k in sorted(df["k"].unique()):
            d = df[(df["includes_unvalidated"] == allow) & (df["k"] == k)]
            tag = f"k{k}_{'incl_unvalidated' if allow else 'feasible_only'}"
            plots.envelope_map(d, out / f"envelope_p_ts_wins_{tag}.png",
                               title=f"{args.scenario}: P(thermosiphon LCOH < coaxial LCOH), k={k}, "
                                     f"{'incl. UNVALIDATED' if allow else 'FEASIBLE only'}")
    print(df.groupby(["includes_unvalidated", "k", "cls"]).size())


def main(argv=None):
    ap = argparse.ArgumentParser(prog="geowell_tea")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("validate")
    p.add_argument("--only", nargs="*", default=None)
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("run")
    p.add_argument("config")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--draws", type=int, default=500)
    p.add_argument("--ku", type=float, default=None, help="guided-return validated Ku limit (3.2 strict, 4.4 field, 6 optimistic)")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("envelope")
    from .envelope import SCENARIOS
    p.add_argument("scenario", choices=list(SCENARIOS))
    p.add_argument("--k", type=float, nargs="+", default=[2.5])
    p.add_argument("--n-z", dest="n_z", type=int, default=30)
    p.add_argument("--draws", type=int, default=400)
    p.add_argument("--threshold", type=float, default=0.9)
    p.add_argument("--rerun", action="store_true")
    p.add_argument("--dias", type=float, nargs="*", default=None)
    p.set_defaults(func=cmd_envelope)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
