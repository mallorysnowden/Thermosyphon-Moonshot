# Standard TEA framework

Every moonshot in this repo is evaluated the same way, so the results can be compared directly.

## Conventions (`inputs/conventions.toml`)

- Real 2026 US dollars, pre-tax, one company discount rate (10%) and one customer discount rate (8%) for every project, 15-year horizon.
- **NOAK costs.** Unit costs are entered at NOAK. The path from FOAK to NOAK comes from Wright's-law learning rates, set per cost component (hardware, installation, logistics, engineering), because these learn at very different speeds. Learning stops at NOAK, so the model never assumes costs below NOAK.
- **Big-enough line:** $1B/yr revenue at full scale (a judgment proxy for the Gimbal's line).
- Every input carries a base, an optional low/high range, a unit, and a source or "Assumption".

## What each project provides

A module `tea/<project>.py` with:

- `run(v) -> StandardResult`: yearly cash flow (with R&D and commercial phases), customer cost vs BAU in one or more functional units, FOAK and NOAK cost multipliers, and kill metrics.
- `breakevens(v)` (optional): the project's break-even questions.

and an inputs file `inputs/<project>.toml` with a `[meta]` table (project name, boundary, functional units) and `score.*` judgment scores for the rubric.

## Standard outputs (`python scripts/run_tea.py <project>`)

Written to `results/<project>/`:

1. **Headline:** NPV, IRR, probability NPV > 0, peak cash need, cash breakeven year, final-year revenue, year NOAK is reached, the extra cost of learning, and NPV if costs started at NOAK.
2. **Customer cost vs BAU** per functional unit, including the project priced at its own NOAK cost (the floor).
3. **FOAK to NOAK** cost multipliers by component.
4. **Cash flow** by year and revenue by stream.
5. **Break-evens.**
6. **Tornado** chart and table (one input at a time).
7. **Monte Carlo** (triangular on every ranged input): P10/P50/P90 and P(NPV > 0).
8. **Kill metrics** with thresholds.
9. **Scorecard** on the rubric weights: economics is scored from P(NPV > 0), the rest are judgment scores from the inputs file.

Plus `cashflow.csv`, `sensitivity.csv` and `inputs_used.csv` for audit.

## Adding a project

1. Copy `inputs/thermosyphon_platform.toml` as a template and replace the markets and cost structure.
2. Write `tea/<project>.py` returning a `StandardResult` (see `tea/thermosyphon_platform.py`).
3. Add tests that check at least one number by hand.
4. Run `python scripts/run_tea.py <project>`.
