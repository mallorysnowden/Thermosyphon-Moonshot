# Cold bank vs BAU trim cooling (per MW of IT)

Trim load: 300 kW_th at peak, 300 MWh_th/yr. Dry coolers are the same in every case and left out.

| | Capex | Annualized capex | O&M | Electricity | Annual cost | $/MWh of cold | vs BAU | Thermosiphons |
|---|---|---|---|---|---|---|---|---|
| BAU chillers | $262,500 | $26,736 | $4,500 | $6,750 | $37,986 | $127 | baseline | 0 |
| Hybrid (chillers kept as backup) | $1,307,500 | $119,561 | $5,850 | $810 | $126,221 | $421 | +232% cost | 40 |
| Replace (no chillers) | $1,319,750 | $117,406 | $1,688 | $810 | $119,903 | $400 | +216% cost | 50 |

- Thermosiphons needed for the trim energy: 40; for the peak rate (with redundancy): 50. The larger number sets the size.
- Installed cost per thermosiphon at which *Replace* breaks even with BAU: **$6,556** (base input $25,000).
- Peak power freed by dropping chillers: 66 kW_e per MW of IT. On a power-capped site that could host more IT, worth $154,440/yr in lease revenue at $195/kW-month (revenue, before the cost of the extra building and servers).

## Sensitivity: change in annual cost of *Replace* vs BAU

| Input | Low | At low | High | At high |
|---|---|---|---|---|
| `cold_bank.peak_kw_per_unit` | 3 | +654% | 15 | +157% |
| `cold_bank.unit_cost` | 12,000 | +64% | 50,000 | +508% |
| `cold_bank.mwh_stored_per_unit` | 3.31 | +631% | 23.19 | +216% |
| `chiller.capex` | 250 | +292% | 800 | +108% |
| `load.trim_hours` | 300 | +259% | 3,000 | +438% |
| `power.capacity_capex` | 500 | +292% | 2,500 | +165% |
| `chiller.cop` | 3.0 | +172% | 6.0 | +276% |
| `finance.thermosiphon_life` | 20 | +260% | 40 | +199% |
| `load.redundancy` | 1.0 | +183% | 1.5 | +242% |
| `cold_bank.extraction_efficiency` | 0.5 | +274% | 0.75 | +216% |
| `power.electricity_price` | 60 | +235% | 150 | +183% |
| `finance.discount_rate` | 0.06 | +189% | 0.1 | +239% |
| `cold_bank.loop_capex` | 75 | +207% | 300 | +233% |
| `cold_bank.pump_energy` | 0.01 | +212% | 0.06 | +221% |
| `load.trim_share` | 0.1 | +221% | 0.5 | +218% |
| `upside.lease_rate` | 150 | +216% | 235 | +216% |
