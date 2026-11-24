# Thermosyphon Moonshot

Techno-economic analyses (TEAs) of moonshot candidates, built on one shared framework so they compare apples to apples. The first project is a thermosyphon platform ("Project Cryo"): passive heat pipes that keep frozen ground frozen under data centers, roads, remote sites and mine waste, with glacier stabilization as long-term research.

## Quick start

```bash
python scripts/run_tea.py thermosyphon_platform     # -> results/thermosyphon_platform/summary.md
python scripts/run_cold_bank_cooling.py             # -> results/cold_bank_cooling/summary.md
python -m pytest
```

Python 3.11+. Matplotlib is optional (charts).

## Layout

| Path | What it is |
|---|---|
| `docs/framework.md` | The standard framework: conventions, what each project provides, the standard outputs. |
| `inputs/conventions.toml` | Shared conventions: discount rates, horizon, fx, big-enough line, rubric weights. |
| `inputs/thermosyphon_platform.toml` | Platform inputs, each with base/low/high, unit and source. |
| `tea/thermosyphon_platform.py` | Platform model (v2). |
| `tea/framework/` | Learning curves, standard result, tornado, Monte Carlo, break-even, report. |
| `tea/cold_bank_cooling.py` | Cold bank vs BAU cooling for one data center (feeds the platform's cold-bank inputs). |
| `results/` | Committed outputs of the base cases. |

## geowell_tea: thermosiphons vs coaxial exchangers in spent oil & gas wells

A separate, self-contained application in [`geowell_tea/`](geowell_tea/) (own `pyproject.toml`, tests and
configs). It compares a deep gravity thermosiphon with a pumped coaxial borehole heat exchanger installed in the
*same* existing well, both independently optimised, for low-grade heating (greenhouse, aquaculture). A shared
transient rock model is coupled to depth-resolved two-phase thermosiphon physics and to a coaxial counterflow
model, followed by heat-pump/direct dispatch, lifetime economics, Monte Carlo, and a depth x temperature x casing
envelope sweep. Start with [`geowell_tea/RESULTS.md`](geowell_tea/RESULTS.md) and
[`geowell_tea/MODEL_LIMITATIONS.md`](geowell_tea/MODEL_LIMITATIONS.md).

```bash
cd geowell_tea && pip install -e .[test] && python -m pytest
python -m geowell_tea.cli run configs/case_a_pa.yaml
```

## icebank_tea: seasonal thermosiphon ice bank vs conventional cooling

A self-contained application in [`icebank_tea/`](icebank_tea/) (own `pyproject.toml` and tests). Passive ammonia
thermosiphons freeze an insulated water pit in winter, and the store cools a load later in the year. An hourly
store model and a joint design search are costed with raw-material NOAK costs (same philosophy as
`geowell_tea`) for four cases: a 100 MW AI data center (ND), a hospital (MN), a salmon processor (AK) and a
year-round process load (ND), each with a full, partial or no backup chiller. Start with
[`icebank_tea/RESULTS.md`](icebank_tea/RESULTS.md).

```bash
cd icebank_tea && pip install -e .[test] && python -m pytest
python -m icebank_tea.run
```

## Thermosyphon platform v2: base case

NPV about **-$34M** over 15 years, peak cash need about **$52M**, revenue about **$29M** in year 15, and a 39% chance of NPV > 0 across the input ranges. It fails all four kill metrics: NOAK cost is 24% below the incumbent (target 30%), well short of the 10x target, roads cost 12x more than repairing them as they settle, and revenue is ~3% of the big-enough line. Full output: `results/thermosyphon_platform/summary.md`.

### Changes from v1

- Only 40% of permafrost data center sites are assumed to need thermosyphons, and 500 m² per MW (from Stak's pad size).
- Cost reductions are set per component; install, logistics and engineering learn slower than hardware.
- Two years of R&D before revenue, then a ramp; costs follow a learning curve from FOAK to NOAK.
- New markets: roads and runways (Dry Creek costs), mining containment (Giant Mine freeze program). Cold bank set to zero (see the cooling model).
- Monitoring and maintenance revenue on the installed base; failure rates in customer life-cycle cost.
- Glacier grants cut to $0.2M/yr (Arête Frontier Grants scale).

v1 is in the git history (commit `b5bfb19`).

## Known limits

- Cash flow is EBIT: no taxes, working capital, capital equipment or terminal value.
- Prices are value-based (incumbent less a discount), so cost cuts show up as margin, not lower customer prices.
- Gravel pads, piles and ventilated foundations can't be priced per m² from public data, so foundations are compared only with incumbent thermosyphons.
- Many inputs are assumptions and are flagged in the inputs file; most ranges lean to the upside of a cautious base, which is why the Monte Carlo median sits above the base case.
