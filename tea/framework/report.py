"""Write the standard TEA report: the same sections and charts for every project."""
from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from .result import StandardResult
from .uncertainty import monte_carlo, percentile, tornado

RUBRIC = ("impact", "breakthrough", "feasibility", "economics", "scalability", "demand", "white_space", "validation")


def money(x: float | None) -> str:
    if x is None:
        return "n/a"
    a = abs(x)
    s = f"${a / 1e9:,.2f}B" if a >= 1e9 else f"${a / 1e6:,.1f}M" if a >= 1e6 else f"${a:,.0f}"
    return "-" + s if x < 0 else s


def _num(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}"


def _plots():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError:
        return None


def _tornado_png(rows, base_value, path) -> bool:
    plt = _plots()
    rows = [r for r in rows if r["swing"] > 0][:15][::-1]
    if plt is None or not rows:
        return False
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(rows) + 1.3))
    for i, r in enumerate(rows):
        ax.barh(i, (r["at_low"] - base_value) / 1e6, left=base_value / 1e6, color="#9aa5b1")
        ax.barh(i, (r["at_high"] - base_value) / 1e6, left=base_value / 1e6, color="#2f6db5")
    ax.set_yticks(range(len(rows)), [r["input"] for r in rows], fontsize=8)
    ax.axvline(base_value / 1e6, color="black", linewidth=0.8)
    ax.set_xlabel("NPV ($M)   grey = low value, blue = high value")
    ax.set_title(f"NPV sensitivity (base {money(base_value)})", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def _mc_png(values, path) -> bool:
    plt = _plots()
    if plt is None:
        return False
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.hist([x / 1e6 for x in values], bins=40, color="#2f6db5")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("NPV ($M)")
    ax.set_ylabel("draws")
    ax.set_title("Monte Carlo NPV", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        fields = list(dict.fromkeys(k for r in rows for k in r))  # union of keys, first-seen order
        w = csv.DictWriter(f, fieldnames=fields, restval=0)
        w.writeheader()
        w.writerows(rows)


def write_report(result: StandardResult, params, v: dict, run, out: Path, meta: dict,
                 breakevens: list[dict] | None = None, draws: int | None = None,
                 scenarios: list[tuple[str, dict]] | None = None) -> str:
    out.mkdir(parents=True, exist_ok=True)
    npv_of = lambda x: run(x).npv  # noqa: E731

    tor = tornado(params, v, npv_of)
    noak_start = None
    if "learning.noak_experience" in v and "learning.first_year_experience" in v:
        noak_start = run({**v, "learning.first_year_experience": v["learning.noak_experience"]})
    mc = monte_carlo(params, v, npv_of, draws=int(draws or v.get("uncertainty.monte_carlo_draws", 2000)))
    p_pos = sum(x > 0 for x in mc) / len(mc)
    has_tor = _tornado_png(tor, result.npv, out / "tornado.png")
    has_mc = _mc_png(mc, out / "monte_carlo.png")

    years = []
    for r in result.years:
        d = asdict(r)
        streams = d.pop("revenue_by_stream")
        d.update({f"rev_{k}": v_ for k, v_ in streams.items()})
        years.append(d)
    _write_csv(out / "cashflow.csv", years)
    _write_csv(out / "sensitivity.csv", tor)
    _write_csv(out / "inputs_used.csv", [
        {"input": k, "base": p.base, "low": p.low, "high": p.high, "unit": p.unit, "source": p.source}
        for k, p in params.items()])

    L = [f"# {result.project}: TEA results", ""]
    L += ["## Conventions", ""]
    for key in ("currency", "noak"):
        if key in meta:
            L.append(f"- {meta[key]}")
    for key in ("boundary", "functional_units"):
        if key in meta:
            L.append(f"- **{key.replace('_', ' ').capitalize()}:** {meta[key]}")
    L.append(f"- Company discount rate {v['finance.company_discount_rate']:.0%}, customer discount rate "
             f"{v['finance.customer_discount_rate']:.0%}, horizon {int(v['finance.horizon'])} years.")
    L += [""]

    last = result.years[-1]
    L += ["## Headline", "", "| Metric | Value |", "|---|---|",
          f"| NPV | {money(result.npv)} |",
          f"| IRR | {'n/a' if result.irr is None else f'{result.irr:.0%}'} |",
          f"| Probability NPV > 0 (Monte Carlo) | {p_pos:.0%} |",
          f"| Peak cash need | {money(result.peak_cash_need)} |",
          f"| Cash breakeven year | {result.breakeven_year or 'not within horizon'} |",
          f"| Revenue in final year | {money(result.full_scale_revenue)} |",
          f"| NOAK reached in year | {result.noak_year or 'not within horizon'} |",
          f"| Extra cost paid while learning (FOAK to NOAK) | {money(result.learning_investment)} |"]
    if noak_start is not None:
        L += [f"| NPV if costs started at NOAK (no learning period) | {money(noak_start.npv)} |"]
    L += [""]

    L += ["## Customer cost vs BAU", ""]
    for fu in result.functional_units:
        name, proj = fu.project
        fmt = money if "$" in fu.unit else (lambda x: f"{x:,.1f}")
        L += [f"**{fu.label}** ({fu.unit})", "", "| Option | Value | vs ours |", "|---|---|---|"]
        for k, val in fu.options.items():
            L.append(f"| {k} | {fmt(val)} | {val / proj:.2f}x |")
        if fu.note:
            L += ["", fu.note]
        L.append("")

    for title, headers, rows in result.tables:
        L += [f"**{title}**", "", "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        L += ["| " + " | ".join(r) + " |" for r in rows]
        L += [""]
    L += ["## FOAK to NOAK", "", "Cost multiplier vs the incumbent's cost for each component (1.00 = incumbent).", "",
          "| Component | FOAK | NOAK |", "|---|---|---|"]
    for c, (f, n) in result.learning.items():
        L.append(f"| {c} | {f:.2f} | {n:.2f} |")
    L.append("")

    has_capex = any(r.capex for r in result.years)
    cap_h, cap_s = (" Capex |", "---|") if has_capex else ("", "")
    L += ["## Cash flow", "", f"| Year | Phase | Revenue | Gross profit | Operating cost | EBIT |{cap_h} Cumulative cash | Cost vs incumbent |",
          f"|---|---|---|---|---|---|{cap_s}---|---|"]
    for r in result.years:
        cap = f" {money(r.capex)} |" if has_capex else ""
        L.append(f"| {r.year} | {r.phase} | {money(r.revenue)} | {money(r.gross_profit)} | {money(r.operating_cost)} | "
                 f"{money(r.ebit)} |{cap} {money(r.cumulative_cash)} | {r.cost_multiplier:.2f} |")
    L += ["", "Revenue in the final year by stream:", ""]
    for k, val in last.revenue_by_stream.items():
        if val:
            L.append(f"- {k}: {money(val)} ({val / last.revenue:.0%})")
    L.append("")

    if breakevens:
        L += ["## Break-evens", "", "| Question | Answer | Base input |", "|---|---|---|"]
        for b in breakevens:
            ans = "no crossing in range" if b["answer"] is None else _num(b["answer"])
            L.append(f"| {b['question']} | {ans} | {_num(b['base'])} |")
        L.append("")

    if scenarios:
        L += ["## Scenarios", "", "| Scenario | NPV | Final-year revenue | Peak cash need |", "|---|---|---|---|"]
        for name, overrides in scenarios:
            r_ = run({**v, **overrides})
            L.append(f"| {name} | {money(r_.npv)} | {money(r_.full_scale_revenue)} | {money(r_.peak_cash_need)} |")
        L.append("")

    L += ["## Sensitivity (one input at a time)", ""]
    if has_tor:
        L += ["![Tornado](tornado.png)", ""]
    L += ["| Input | Low | NPV at low | High | NPV at high |", "|---|---|---|---|---|"]
    for r in tor[:15]:
        L.append(f"| `{r['input']}` | {r['low_value']:,} | {money(r['at_low'])} | {r['high_value']:,} | {money(r['at_high'])} |")
    L.append("")

    L += ["## Monte Carlo", "",
          f"{len(mc):,} draws, triangular distribution on every input with a range.", "",
          "| P10 | P50 | P90 | P(NPV > 0) |", "|---|---|---|---|",
          f"| {money(percentile(mc, 0.1))} | {money(percentile(mc, 0.5))} | {money(percentile(mc, 0.9))} | {p_pos:.0%} |", ""]
    if has_mc:
        L += ["![Monte Carlo](monte_carlo.png)", ""]

    L += ["## Kill metrics", "", "| Metric | Value | Threshold | Passes |", "|---|---|---|---|"]
    for k in result.kill_metrics:
        L.append(f"| {k.name} | {k.value:,.2f} {k.unit} | {k.threshold:,.2f} | {'yes' if k.passes else 'no'} |")
    L.append(f"| Probability NPV > 0 | {p_pos:.0%} | 50% | {'yes' if p_pos >= 0.5 else 'no'} |")
    L.append("")

    scores = {k: v.get(f"score.{k}") for k in RUBRIC}
    econ = 5 if p_pos >= 0.8 else 4 if p_pos >= 0.6 else 3 if p_pos >= 0.4 else 2 if p_pos >= 0.2 else 1
    scores["economics"] = econ
    if all(s is not None for s in scores.values()):
        total = sum(v[f"rubric.{k}"] * scores[k] for k in RUBRIC)
        L += ["## Scorecard", "", "Economics is scored from P(NPV > 0); the rest are judgment scores set in the inputs file.", "",
              "| Category | Weight | Score |", "|---|---|---|"]
        for k in RUBRIC:
            L.append(f"| {k.replace('_', ' ')} | {v[f'rubric.{k}']:.0%} | {scores[k]} |")
        L += [f"| **Weighted total** | | **{total:.2f}** |", ""]

    if result.notes:
        L += ["## Notes", ""] + [f"- {n}" for n in result.notes] + [""]
    text = "\n".join(L) + "\n"
    (out / "summary.md").write_text(text)
    return text
