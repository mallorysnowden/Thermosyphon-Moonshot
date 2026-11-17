"""Compare cold-bank cooling with business-as-usual (BAU) chillers, per MW of IT.

Usage:
    python scripts/run_cold_bank_cooling.py
    python scripts/run_cold_bank_cooling.py --inputs inputs/my_case.toml --out results/my_case
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tea.cold_bank_cooling import breakeven_unit_cost, compare  # noqa: E402
from tea.inputs import base_values, load_params  # noqa: E402


def money(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", default=ROOT / "inputs" / "cold_bank_cooling.toml")
    parser.add_argument("--out", default=ROOT / "results" / "cold_bank_cooling")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    params = load_params(args.inputs)
    v = base_values(params)
    c = compare(v)
    configs = (c.bau, c.hybrid, c.replace)

    with open(out / "comparison.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config", "capex", "annualized_capex", "om", "electricity", "opex", "annual_cost",
                    "cost_per_mwh_th", "saving_vs_bau", "thermosiphons"])
        for cfg in configs:
            w.writerow([cfg.name, round(cfg.capex), round(cfg.annualized_capex), round(cfg.om),
                        round(cfg.electricity), round(cfg.opex), round(cfg.annual_cost),
                        round(cfg.annual_cost / c.trim_mwh_th, 1), round(c.saving(cfg), 4), cfg.thermosiphons])

    sens = []
    for key, p in params.items():
        if p.low is None or p.high is None:
            continue
        lo, hi = compare({**v, key: p.low}), compare({**v, key: p.high})
        sens.append((key, p.low, lo.saving(lo.replace), p.high, hi.saving(hi.replace)))
    sens.sort(key=lambda r: abs(r[4] - r[2]), reverse=True)
    with open(out / "sensitivity.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["input", "low", "replace_saving_at_low", "high", "replace_saving_at_high"])
        w.writerows(sens)

    breakeven = breakeven_unit_cost(v)
    lines = [
        "# Cold bank vs BAU trim cooling (per MW of IT)",
        "",
        f"Trim load: {c.peak_kw_th:,.0f} kW_th at peak, {c.trim_mwh_th:,.0f} MWh_th/yr. "
        "Dry coolers are the same in every case and left out.",
        "",
        "| | Capex | Annualized capex | O&M | Electricity | Annual cost | $/MWh of cold | vs BAU | Thermosiphons |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cfg in configs:
        lines.append(
            f"| {cfg.name} | {money(cfg.capex)} | {money(cfg.annualized_capex)} | {money(cfg.om)} | "
            f"{money(cfg.electricity)} | {money(cfg.annual_cost)} | {money(cfg.annual_cost / c.trim_mwh_th)} | "
            f"{('baseline' if cfg is c.bau else f'{-c.saving(cfg):+.0%} cost')} | {cfg.thermosiphons:.0f} |"
        )
    lines += [
        "",
        f"- Thermosiphons needed for the trim energy: {c.units_energy_limited:.0f}; for the peak rate (with redundancy): "
        f"{c.units_peak_limited:.0f}. The larger number sets the size.",
        f"- Installed cost per thermosiphon at which *Replace* breaks even with BAU: **{money(breakeven)}** "
        f"(base input {money(v['cold_bank.unit_cost'])}).",
        f"- Peak power freed by dropping chillers: {c.freed_peak_kw_e:,.0f} kW_e per MW of IT. On a power-capped site that "
        f"could host more IT, worth {money(c.capacity_upside)}/yr in lease revenue at {money(v['upside.lease_rate'])}/kW-month "
        "(revenue, before the cost of the extra building and servers).",
        "",
        "## Sensitivity: change in annual cost of *Replace* vs BAU",
        "",
        "| Input | Low | At low | High | At high |",
        "|---|---|---|---|---|",
    ]
    for key, lo_v, lo_s, hi_v, hi_s in sens:
        lines.append(f"| `{key}` | {lo_v:,} | {-lo_s:+.0%} | {hi_v:,} | {-hi_s:+.0%} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
