"""Run the thermosiphon platform TEA and write results.

Usage:
    python scripts/run_thermosiphon.py
    python scripts/run_thermosiphon.py --inputs inputs/my_case.toml --out results/my_case
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tea.inputs import base_values, load_params  # noqa: E402
from tea.thermosiphon import (  # noqa: E402
    chiller_cost_per_mwh,
    cold_bank_cost_per_mwh,
    run,
    sensitivity,
)

COOLING_HOURS = [300, 500, 1000, 2000, 4000]


def money(x: float) -> str:
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def write_csv(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def tornado(rows: list[dict], base_npv: float, path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    rows = [r for r in rows if r["swing"] > 0][::-1]
    fig, ax = plt.subplots(figsize=(8, 0.45 * len(rows) + 1.2))
    for i, r in enumerate(rows):
        lo, hi = r["npv_at_low"] / 1e6, r["npv_at_high"] / 1e6
        ax.barh(i, lo - base_npv / 1e6, left=base_npv / 1e6, color="#9aa5b1")
        ax.barh(i, hi - base_npv / 1e6, left=base_npv / 1e6, color="#2f6db5")
    ax.set_yticks(range(len(rows)), [r["input"] for r in rows], fontsize=8)
    ax.axvline(base_npv / 1e6, color="black", linewidth=0.8)
    ax.set_xlabel("10-year NPV ($M)   grey = low value, blue = high value")
    ax.set_title(f"NPV sensitivity (base {money(base_npv)})", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", default=ROOT / "inputs" / "thermosiphon_base.toml")
    parser.add_argument("--out", default=ROOT / "results" / "thermosiphon_base")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    params = load_params(args.inputs)
    v = base_values(params)
    res = run(v)

    write_csv(out / "cashflow.csv", [asdict(r) for r in res.years])
    sens = sensitivity(params)
    write_csv(out / "sensitivity.csv", sens)
    cooling = [
        {
            "trim_hours": h,
            "chiller_cost_per_mwh": chiller_cost_per_mwh(v, h),
            "cold_bank_price_per_mwh": cold_bank_cost_per_mwh(v),
            "cold_bank_cost_per_mwh": cold_bank_cost_per_mwh(v, at_cost=True),
            "cheaper_for_customer": "cold bank" if cold_bank_cost_per_mwh(v) < chiller_cost_per_mwh(v, h) else "chiller",
        }
        for h in COOLING_HOURS
    ]
    write_csv(out / "cooling.csv", cooling)
    has_plot = tornado(sens, res.npv, out / "tornado.png")

    y5 = res.years[4]
    a, b, c = res.foundations, res.cold_bank, res.remote_sites
    lines = [
        "# Thermosiphon platform TEA: results",
        "",
        f"Inputs: `{Path(args.inputs).relative_to(ROOT) if Path(args.inputs).is_relative_to(ROOT) else args.inputs}`",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| NPV over 10 years | {money(res.npv)} |",
        f"| Revenue at full ramp (year 5) | {money(y5.revenue)} |",
        f"| EBIT at full ramp (year 5) | {money(y5.ebit)} |",
        f"| Share of year-5 revenue: data center foundations | {a.revenue / y5.revenue:.1%} |",
        f"| Share of year-5 revenue: cold bank | {b.revenue / y5.revenue:.1%} |",
        f"| Share of year-5 revenue: remote sites | {(c.foundation_revenue + y5.sites_in_service * c.subscription_per_site) / y5.revenue:.1%} |",
        f"| Share of year-5 revenue: glacier grants | {res.grants / y5.revenue:.1%} |",
        f"| Entrant foundation gross margin | {a.gross_margin:.1%} |",
        f"| Foundation cost as share of data center build cost | {a.share_of_dc_build_cost:.1%} |",
        f"| Customer saving, cold bank vs chiller | {b.customer_saving:.1%} |",
        f"| Arctic data center MW/yr needed for $1B/yr revenue (buying both A and B) | {1e9 / res.revenue_per_mw_both:,.0f} |",
        "",
        "## Cash flow",
        "",
        "| Year | Ramp | Revenue | Gross profit | Operating cost | EBIT | Present value |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in res.years:
        lines.append(
            f"| {r.year} | {r.ramp:.0%} | {money(r.revenue)} | {money(r.gross_profit)} | "
            f"{money(r.operating_cost)} | {money(r.ebit)} | {money(r.present_value)} |"
        )
    lines += [
        "",
        "## Cooling cost to the customer ($/MWh of cold)",
        "",
        "| Trim hours/yr | Chiller | Cold bank (our price) | Cold bank (our cost) | Cheaper |",
        "|---|---|---|---|---|",
    ]
    for r in cooling:
        lines.append(
            f"| {r['trim_hours']:,} | {money(r['chiller_cost_per_mwh'])} | {money(r['cold_bank_price_per_mwh'])} | "
            f"{money(r['cold_bank_cost_per_mwh'])} | {r['cheaper_for_customer']} |"
        )
    lines += [
        "",
        "## Sensitivity (one input at a time, others at base)",
        "",
        "| Input | Low | NPV at low | High | NPV at high |",
        "|---|---|---|---|---|",
    ]
    for r in sens:
        lines.append(
            f"| `{r['input']}` | {r['low_value']:,} | {money(r['npv_at_low'])} | {r['high_value']:,} | {money(r['npv_at_high'])} |"
        )
    if has_plot:
        lines += ["", "![NPV sensitivity](tornado.png)"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
