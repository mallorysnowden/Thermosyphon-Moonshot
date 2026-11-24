# icebank_tea: seasonal thermosiphon ice bank vs conventional cooling

Passive ammonia thermosiphons freeze an insulated water pit in winter; the ice (and the cold water around it)
carries cooling later in the year. This app compares the ice bank's annualized cost of cooling with the
business-as-usual (BAU) plant it would replace, for four cases. It supersedes the ground "cold bank"
(`tea/cold_bank_cooling.py`), which froze soil and came out at about 3x BAU.

```bash
cd icebank_tea && pip install -e .[test,charts] && python -m pytest
python -m icebank_tea.run            # ~3 min, writes outputs/, outputs/figures/ and RESULTS.md
python -m icebank_tea.run --quick    # coarse grid
```

Start with [`RESULTS.md`](RESULTS.md), the charts in [`outputs/figures/`](outputs/figures/), and [`MODEL_LIMITATIONS.md`](MODEL_LIMITATIONS.md).

## What changed from the first ice-bank model (Nov 23 doc)

1. **Hour-by-hour store.** Each hour the thermosiphons freeze (only when the air is colder than the store),
   the load melts ice or warms the water, and the cover and ground leak heat in. The store is sized by its worst
   stretch without recharge, not by "fill in winter, drain in summer", so freeze-thaw recharging and winter
   direct cooling are captured.
2. **Whole-winter design search.** Tube spacing (0.8-2 m), condenser area (12-40 m2) and pit depth (10 or 15 m)
   are searched together with the unit count, so units no longer sit full and idle from late January.
3. **Backup chiller options for every case:** ice + full backup chiller, ice + 30% backup, and ice only.
   Without a full backup the store must leave no more than 0.1% of a median year's cooling unmet in its worst
   synthetic year.
4. **Winter cooling credited only against a chiller.** BAU in the year-round case (D) cools for free with a dry
   cooler below -3 degC, so the ice bank gets no credit for those hours.
5. **NOAK costs like geowell_tea:** raw materials x 2.5 (range 2-3.5) for an all-aluminium ammonia unit with a
   code-sized wall, plus installation priced bottom-up; FOAK = index 3.5, manual install, pricier civil works.
   Units longer than 12 m pay for a field joint. Condenser conductance calibrated to Li et al. (2020).
6. **Repo conventions:** 8% customer discount rate; one-year lag before first cooling (the pit needs a winter).
7. **Monthly demand charges** from each site's published tariff, billed on the chiller's (and discharge pumps')
   highest draw each month: Xcel ND for the data center and process cases, Xcel MN for the hospital, and a
   Bristol Bay co-op seasonal rate for the salmon plant. Removing the chiller removes most of this charge.

## Files

| Path | What it is |
|---|---|
| `src/icebank_tea/weather.py` | Synthetic hourly weather from monthly normals; `load_csv` swaps in real hourly data |
| `src/icebank_tea/store.py` | Vectorized hourly ice-store model (every design x unit count at once) |
| `src/icebank_tea/costs.py` | Unit bill of materials, raw-material NOAK costing, pit cost curve, finance |
| `src/icebank_tea/cases.py` | Cases A-D: loads, usable water temperature, BAU plant |
| `src/icebank_tea/run.py` | Design search, backup options, sensitivities, outputs |
| `src/icebank_tea/charts.py` | Data-center cost-breakdown donuts and sensitivity tornados (needs matplotlib) |
| `outputs/` | `summary.csv`, `sensitivity.csv` (ratios and $/MWh), `unit_bom.csv`, `run_meta.json`, `figures/` |
