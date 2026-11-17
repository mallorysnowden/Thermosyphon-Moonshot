# Thermosiphon Moonshot

Techno-economic analysis (TEA) of a thermosiphon business: passive heat pipes that keep frozen ground frozen, sold to Arctic data centers and remote sites, with glacier stabilization as the long-term moonshot.

The model is plain Python. Every input lives in one TOML file with its source, so changing an assumption means editing that file and re-running.

## Quick start

```bash
python scripts/run_thermosiphon.py            # base case -> results/thermosiphon_base/
python -m pytest                              # checks
```

To try another case, copy `inputs/thermosiphon_base.toml`, edit it, and run:

```bash
python scripts/run_thermosiphon.py --inputs inputs/my_case.toml --out results/my_case
```

Requires Python 3.11+. Matplotlib is optional (it draws the sensitivity chart).

## What's in the repo

| Path | What it is |
|---|---|
| `inputs/thermosiphon_base.toml` | Every input: base, low, high, unit, and source. "Assumption" marks a judgment, not a sourced figure. |
| `tea/thermosiphon.py` | The model: four revenue streams, a 10-year cash flow, and a one-at-a-time sensitivity sweep. |
| `tea/finance.py`, `tea/inputs.py` | Shared helpers (discounting, input loading) for this and future TEAs. |
| `scripts/run_thermosiphon.py` | Runs a case and writes the results. |
| `results/thermosiphon_base/` | `summary.md` (start here), `cashflow.csv`, `cooling.csv`, `sensitivity.csv`, `tornado.png`. |
| `inputs/cold_bank_cooling.toml`, `tea/cold_bank_cooling.py`, `scripts/run_cold_bank_cooling.py` | Cold bank vs BAU cooling cost for one data center (see below). |
| `tests/` | Checks the base case against the spreadsheet version and a few sanity cases. |

## The model

Four revenue streams, all at full ramp, scaled each year by the ramp in the inputs:

- **A. Data center foundations.** Thermosiphon foundations under data centers built on permafrost. Revenue = MW built × market share × building m² per MW × price per m². The entrant's cost is the incumbent's cost cut by an innovation target, and its price is the incumbent's minus a discount.
- **B. Cold bank.** Thermosiphons freeze a block of ground each winter; the data center draws that cold in summer instead of running trim chillers. Revenue = trim cooling needed (MWh of cold per year) × price per MWh/yr of capacity. Units needed = trim cooling ÷ cold stored per thermosiphon. The customer check compares the cold bank's annualized price with a chiller's cost (electricity ÷ COP, plus chiller and generator capex spread over the trim hours).
- **C. Remote sites.** Foundation packages for telecom towers, satellite antennas and weather stations, plus a monitoring subscription on every site in service.
- **D. Glacier research grants.** Counted as revenue but not profit, since grants pay for the research they fund.

Cash flow: gross profit minus a flat operating cost, discounted at the company rate over 10 years. Pre-tax, today's dollars, no working capital or terminal value.

## Base-case result

NPV about **$31M**, revenue leveling off near **$37M/yr**. Foundations are ~70% of revenue. See `results/thermosiphon_base/summary.md` for the full output.

## Cold bank vs business-as-usual cooling

`tea/cold_bank_cooling.py` compares the cost of trim cooling for one data center, per MW of IT, in three setups:

- **BAU:** trim chillers sized for peak with N+1 redundancy, the power capacity to run them, and their electricity.
- **Hybrid:** keep the whole BAU chiller plant as backup and add a cold bank that carries the trim energy (higher capex, lower opex).
- **Replace:** no chillers; the cold bank is sized for peak with redundancy.

The cold bank is sized by whichever is larger: the trim energy (stored cold × extraction efficiency per thermosiphon, from Tareen et al. 2024) or the peak rate (kW per thermosiphon, an assumption, since the paper does not model extraction).

```bash
python scripts/run_cold_bank_cooling.py       # -> results/cold_bank_cooling/
```

Base case: the cold bank cuts electricity and O&M by about $8,700/yr per MW of IT, but adds about $1M of capex, so its annual cost is roughly 3× BAU. It breaks even at about $6,600 per installed 100 m thermosiphon, against a $25,000 base estimate. See `results/cold_bank_cooling/summary.md`.

Note: the platform TEA (`inputs/thermosiphon_base.toml`) still uses an earlier, more optimistic cold-bank cost ($8,000 per unit, no extraction loss).

## Known limits

- The cold-bank price is an input, so changing chiller COP, electricity price or generation capex moves the customer's saving but not our NPV.
- The cold bank ignores the cost of pumping cold out of the ground at peak rate, which would raise its cost.
- Several key inputs are assumptions with no market data yet: building footprint per MW, cold-bank unit cost, market shares, operating cost and volumes. They are flagged in the inputs file.
- No terminal value: a business still growing in year 10 is undervalued.

## Sources

Sourced figures are cited next to each input. The main ones:

- Thermosiphon unit and mounting cost: [arXiv 2108.10138](https://arxiv.org/abs/2108.10138)
- Cold stored per thermosiphon, 50-75% extraction efficiency: Tareen et al., *Journal of Energy Storage* 84 (2024) 111486
- Borehole drilling cost: NLR 2025 US Geothermal Market Report, via [The Driller](https://www.thedriller.com/articles/93881-financing-thermal-energy-networks-capital-flow-determines-whether-rigs-move)
- Data center lease rates: [CBRE North America Data Center Trends](https://www.cbre.com/insights/books/north-america-data-center-trends)
- Data center build cost: [JLL 2026 Global Data Center Outlook](https://www.jll.com/en-au/insights/data-center-outlook)
- Alaska residential thermosyphon cost adder: [Alaska Estimation](https://alaskaestimation.com/why-construction-costs-in-alaska-are-higher-than-the-lower-48/)
- North Slope data center lease: [News From the States, Nov 11, 2026](https://www.newsfromthestates.com/node/437913)
- Air Force data centers on Alaska bases: [Migflug](https://migflug.com/jetflights/ai-data-centres-are-coming-to-alaska-air-force-bases/)
- ARIA climate-cooling grants: [SRM360](https://srm360.org/news-reaction/aria-45m-funding-21-climate-cooling-research-projects/)
