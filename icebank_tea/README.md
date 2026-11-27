# icebank_tea: seasonal thermosiphon ice bank vs conventional cooling

Passive ammonia thermosiphons freeze an insulated water pit in winter; the ice (and the cold water around it)
carries cooling later in the year. This app compares the ice bank's annualized cost of cooling with the
business-as-usual (BAU) plant it would replace, for six cases: a liquid-cooled data center (A), a
hospital with heating and cooling against a gas-heated (B) and an all-electric (F) plant, a salmon processor (C),
year-round process cooling (D) and an air-cooled data center (E). It supersedes the ground "cold bank"
(`tea/cold_bank_cooling.py`), which froze soil and came out at about 3x BAU.

```bash
cd icebank_tea && pip install -e .[test,charts] && python -m pytest
python -m icebank_tea.run            # ~1.5 h (12 years, six cases); writes outputs/, outputs/figures/ and RESULTS.md
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
8. **Auxiliaries, electrical service and water on both sides.** Conventional plants pay for chilled-water pumps
   (and, with cooling towers, condenser-water pumps and tower fans) in energy, demand charges and electrical
   service; the ice bank's discharge pumps now pay electrical service too. Tower plants (hospital, salmon
   evaporative condensers) pay for makeup water, treatment and sewer at local rates.
9. **Hourly time-of-use billing and year-round night recharge.** The data-center and hospital tariffs are billed
   on-peak (9 a.m.-9 p.m. weekdays) vs off-peak, with on-peak demand charges. The thermosiphons already recharge
   the pit whenever the air is colder than the water, in any season; the design search can also add a dry cooler
   (0, 10% or 30% of peak load) that cools liquid pit water on cool nights and shoulder seasons.
10. **Smart charging for the 30% backup.** The 30% backup chiller may also charge the pit in off-peak hours
   (ice-making at 70% of its chilled-water COP and capacity, plus $30/kW of in-pit coils); each case reports
   whichever of "charge" or "don't charge" is cheaper. It lowers the 30% option's cost in the data-center,
   hospital and process cases but does not make it the best configuration in any case. Off-peak charging by a
   full backup chiller is not modelled.
11. **Hospital heating and cooling (cases B and F).** The hospital now needs heat as well as cold: 7,000 MWh a
   year of space heat, reheat and hot water, peaking at 1.9 MW at -26 degC, with a 25% year-round floor. A
   water-to-water heat pump can draw its heat from the pit (55 degC hot water, half of Carnot, COP about 2.6 from
   a frozen pit), which freezes the pit and so makes ice for the summer. Case B compares against gas boilers;
   case F against air-source heat pumps (boilers kept as backup only, so in F the heat pumps must carry the
   heating to the same 0.1% standard as the cooling). The design search adds the heat-pump size (0-100% of peak
   heat) and wider tube spacing (up to 4 m, i.e. fewer thermosiphons per m3 of pit, since the heat pump can make
   much of the ice). From October to April a valve on the thermosiphons closes once the pit's spare ice room is
   down to what the heat pump will need until May, so free freezing doesn't shut the heat pump out. Costs per
   MWh in these cases are per MWh of heat plus cold.
   *Result:* against gas (B) the best "ice bank" is the smallest pit in the grid with a full chiller (1.01x BAU),
   i.e. don't build one: at 12.5 c/kWh and $7/Mcf, heat from a COP-2.6 heat pump costs more than heat from gas
   ($46 vs $28 per MWh), so the free ice doesn't pay for the pit. The heat-pump options need gas at roughly
   $19/Mcf to break even. Against the electrified plant (F) the best option breaks even (0.99x): a pit heat pump
   sized for the whole 1.9 MW heating peak, a 61,000 m3 pit (0.4 ha, 15 m deep) with 1,018 thermosiphons at 2 m
   spacing, and a 30% backup chiller. It replaces the air-source heat pumps and most of the chiller; the pit
   cost (x0.7 gives 0.88x) and demand charges (x2 gives 0.93x) decide whether it wins.

## Files

| Path | What it is |
|---|---|
| `src/icebank_tea/weather.py` | Synthetic hourly weather from monthly normals; `load_csv` swaps in real hourly data |
| `src/icebank_tea/store.py` | Vectorized hourly ice-store model (every design x unit count at once) |
| `src/icebank_tea/costs.py` | Unit bill of materials, raw-material NOAK costing, pit cost curve, finance |
| `src/icebank_tea/cases.py` | Cases A-F: loads, heating demand, usable water temperature, BAU plant |
| `src/icebank_tea/run.py` | Design search, backup options, sensitivities, outputs |
| `src/icebank_tea/charts.py` | Data-center cost-breakdown donuts and sensitivity tornados (needs matplotlib) |
| `outputs/` | `summary.csv`, `sensitivity.csv` (ratios and $/MWh), `unit_bom.csv`, `run_meta.json`, `figures/` |
