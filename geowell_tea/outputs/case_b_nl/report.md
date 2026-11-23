# Case B-NL - Case B well geometry with Dutch economics: thermosiphon vs coaxial TEA

_Same geology, well and load as the US case; prices replaced by Dutch / EU non-household values (EUR converted at 1.10 USD/EUR). No subsidy in the base case._
Model version 0.1.0, config hash `48fc19766bf3`, 73 designs searched, runtime 465.1 s. All numbers are computed by the code from the inputs listed in `provenance.csv`; most inputs are **assumed** (see that file).

## Economic optimum per architecture (customer dispatch, FEASIBLE designs only)

| architecture | design | status | geo_capability_kW_y1 | geo_capability_kW_y20 | E_useful_MWh_total | SPF_system | unmet_share | lcoh | site_cost_per_MWh | incumbent_only_cost_per_MWh | npv |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C_ADAPTIVE | C_ADAPTIVE VIT114mm m=3.0kg/s T_in=22C | FEASIBLE | 308.8 | 227.1 | 40401.9 | 12.0 | 0.0 | 141.0 | 139.8 | 97.8 | -921911.5 |
| C_DIRECT | C_DIRECT VIT114mm m=8.0kg/s T_in=var | FEASIBLE | 273.3 | 184.5 | 34743.7 | 21.1 | 0.2 | 122.6 | 119.0 | 97.8 | -529731.1 |
| C_HP | C_HP VIT114mm m=3.0kg/s T_in=20C | FEASIBLE | 330.5 | 250.0 | 42018.3 | 5.7 | 0.0 | 155.6 | 155.6 | 97.8 | -1208846.4 |
| T_ADAPTIVE | T_ADAPTIVE ammonia T_top=32C ins=816m guided | FEASIBLE | 231.3 | 162.8 | 34019.5 | 8.9 | 0.2 | 159.4 | 149.3 | 97.8 | -1068981.7 |
| T_DIRECT | T_DIRECT ammonia T_top=40C ins=1049m guided | FEASIBLE | 170.9 | 121.3 | 23048.0 | 73.6 | 0.5 | 150.6 | 128.0 | 97.8 | -640849.4 |
| T_HP | T_HP ammonia T_top=25C ins=0m guided | FEASIBLE | 283.7 | 198.2 | 39413.6 | 7.2 | 0.1 | 145.0 | 142.7 | 97.8 | -971231.4 |

`lcoh` = geothermal-only levelised cost of useful heat [$/MWh]; `site_cost_per_MWh` blends in backup heat for unmet load; `incumbent_only_cost_per_MWh` is the customer's cost with no geothermal.

## Resource test: maximum year-20 capability per architecture (sink never limiting)

| architecture | design | status | geo_capability_kW_t0 | geo_capability_kW_y1 | geo_capability_kW_y10 | geo_capability_kW_y20 | E_geo_MWh_total | y20_over_y3_capability | sustainable_80pct |
|---|---|---|---|---|---|---|---|---|---|
| C_ADAPTIVE | C_ADAPTIVE VIT89mm m=3.0kg/s T_in=12C | FEASIBLE | 436.8 | 361.9 | 285.6 | 273.0 | 51142.0 | 0.9 | True |
| C_DIRECT | C_DIRECT VIT114mm m=8.0kg/s T_in=var | FEASIBLE | 340.6 | 263.4 | 194.7 | 184.3 | 35100.1 | 0.8 | True |
| C_HP | C_HP VIT114mm m=5.0kg/s T_in=5C | FEASIBLE | 562.1 | 455.6 | 351.9 | 335.3 | 63155.8 | 0.9 | True |
| T_ADAPTIVE | T_ADAPTIVE ammonia T_top=32C ins=816m guided | FEASIBLE | 285.5 | 226.7 | 171.4 | 162.7 | 30827.9 | 0.9 | True |
| T_DIRECT | T_DIRECT ammonia T_top=40C ins=1049m guided | FEASIBLE | 217.0 | 170.9 | 128.0 | 121.3 | 23048.0 | 0.9 | True |
| T_HP | T_HP ammonia T_top=25C ins=0m guided | FEASIBLE | 334.6 | 267.1 | 203.5 | 193.5 | 36574.0 | 0.9 | True |


## Thermosiphon working-fluid screening (resource mode)

| fluid | architecture | best_geo_kW_y20 | statuses |
|---|---|---|---|
| ammonia | T_ADAPTIVE | 162.7 | FEASIBLE,UNVALIDATED |
| ammonia | T_DIRECT | 121.3 | FEASIBLE,UNVALIDATED |
| ammonia | T_HP | 278.3 | FEASIBLE,UNVALIDATED |
| co2 | T_ADAPTIVE | 0.0 | INFEASIBLE |
| co2 | T_DIRECT | 0.0 | INFEASIBLE |
| co2 | T_HP | 0.0 | INFEASIBLE,UNVALIDATED |
| isobutane | T_ADAPTIVE | 90.7 | UNVALIDATED |
| isobutane | T_DIRECT | 51.1 | FEASIBLE,UNVALIDATED |
| isobutane | T_HP | 160.6 | UNVALIDATED |
| pentane | T_ADAPTIVE | 69.9 | FEASIBLE,UNVALIDATED |
| pentane | T_DIRECT | 48.0 | FEASIBLE,UNVALIDATED |
| pentane | T_HP | 96.7 | FEASIBLE,UNVALIDATED |
| propane | T_ADAPTIVE | 97.5 | UNVALIDATED |
| propane | T_DIRECT | 52.8 | UNVALIDATED |
| propane | T_HP | 217.4 | UNVALIDATED |
| water | T_ADAPTIVE | 69.3 | UNVALIDATED |
| water | T_DIRECT | 61.1 | UNVALIDATED |
| water | T_HP | 67.7 | UNVALIDATED |


## Thermosiphon vs coaxial

* Base-case LCOH ratio (best thermosiphon / best coaxial, FEASIBLE designs): **1.18**
* Monte Carlo over cost/finance inputs (46 ranged parameters): P(thermosiphon cheaper) = **0.20** (incl. UNVALIDATED designs: 0.35); ratio P10/P50/P90 = 0.93 / 1.16 / 1.40


### Largest drivers of the TS/C cost ratio (tornado)

| parameter | low | base | high | ratio_low | ratio_high |
|---|---|---|---|---|---|
| vit_per_m | 120 | 250 | 500 | 1.57 | 0.799 |
| coax_capex_mult | 0.85 | 1 | 1.25 | 1.29 | 1.04 |
| ts_capex_mult | 0.85 | 1 | 1.25 | 1.12 | 1.28 |
| hp_per_kw | 500 | 800 | 1.3e+03 | 1.09 | 1.23 |
| ts_internals_per_m | 0 | 15 | 60 | 1.16 | 1.26 |
| guide_line_per_m | 15 | 35 | 70 | 1.15 | 1.24 |
| ts_string_per_m_base | 25 | 40 | 80 | 1.16 | 1.25 |
| discount_rate | 0.06 | 0.1 | 0.15 | 1.22 | 1.14 |
| ts_direct_hp_premium | 0 | 0.15 | 0.4 | 1.16 | 1.23 |
| equipment_size_factor | 1.15 | 1.3 | 1.5 | 1.15 | 1.22 |


### Electricity-price sweep (LCOH, $/MWh)

| electricity_price | C_ADAPTIVE | C_DIRECT | C_HP | T_ADAPTIVE | T_DIRECT | T_HP |
|---|---|---|---|---|---|---|
| $0.08/kWh | 132 | 117 | 135 | 146 | 149 | 128 |
| $0.10/kWh | 133 | 118 | 138 | 148 | 149 | 131 |
| $0.13/kWh | 136 | 119 | 144 | 152 | 150 | 135 |
| $0.15/kWh | 137 | 120 | 147 | 154 | 150 | 138 |
| $0.20/kWh | 141 | 123 | 156 | 160 | 151 | 145 |
| $0.25/kWh | 145 | 125 | 165 | 165 | 151 | 152 |
| $0.30/kWh | 148 | 128 | 173 | 171 | 152 | 159 |
| $0.40/kWh | 154 | 133 | 191 | 182 | 153 | 173 |
| $0.45/kWh | 157 | 135 | 200 | 187 | 154 | 180 |


## B2: prospective (ramped) customer

| architecture | design | status | E_useful_MWh_total | lcoh | npv | site_cost_per_MWh | customer_facility_capex_reported_separately |
|---|---|---|---|---|---|---|---|
| C_ADAPTIVE | C_ADAPTIVE VIT114mm m=3.0kg/s T_in=22C | FEASIBLE | 38936.7 | 151.3 | -1016450.3 | 149.9 | 3000000 |
| C_DIRECT | C_DIRECT VIT114mm m=8.0kg/s T_in=var | FEASIBLE | 33632.7 | 130.8 | -608290.7 | 126.2 | 3000000 |
| C_HP | C_HP VIT114mm m=3.0kg/s T_in=20C | FEASIBLE | 40445.4 | 165.8 | -1283168.2 | 165.8 | 3000000 |
| T_ADAPTIVE | T_ADAPTIVE ammonia T_top=32C ins=816m guided | FEASIBLE | 32933.8 | 160.8 | -1014206.1 | 151.0 | 3000000 |
| T_DIRECT | T_DIRECT ammonia T_top=40C ins=1049m guided | FEASIBLE | 22701.0 | 155.3 | -665654.2 | 132.3 | 3000000 |
| T_HP | T_HP ammonia T_top=25C ins=0m guided | FEASIBLE | 38014.5 | 154.6 | -1049918.7 | 152.1 | 3000000 |

The customer facility capex is **not** in the geothermal LCOH.


## Figures

![heat](fig_heat_vs_time.png)
![depth](fig_depth_profiles.png)
![bars](fig_summary_bars.png)
![elec](fig_electricity_crossover.png)
![tornado](fig_tornado.png)

See `../../MODEL_LIMITATIONS.md` before using any number here.

## What would need to be true (guided-return validity Ku <= 3.2)
Thermosiphon at FOAK / today's base / NOAK and with cumulative scale levers (thermosiphon only); coaxial and the incumbent stay at today's assumptions. Best FEASIBLE design re-picked at each step.

**Coverage: any** (coaxial today $123/MWh; incumbent $98/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 169.12 | 1.38 | 354.75 | 0.10 | T_HP ammonia T_top=25C ins=0m guided |
| today's base costs | 144.96 | 1.18 | 234.59 | 0.10 | T_HP ammonia T_top=25C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 118.56 | 0.97 | 103.35 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 96.53 | 0.79 | 0.00 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |
| 3. heat pump $500/kW | 96.53 | 0.79 | 0.00 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |
| 4. infrastructure financing 6% real | 78.76 | 0.64 | 0.00 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |

**Coverage: full (<2% unmet every year)** (coaxial today $154/MWh; incumbent $98/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | n/a | n/a | 0.00 | n/a | nan |
| today's base costs | n/a | n/a | 0.00 | n/a | nan |
| 1. NOAK manufacturing + automated install (raw x 2.5) | n/a | n/a | 0.00 | n/a | nan |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | n/a | n/a | 0.00 | n/a | nan |
| 3. heat pump $500/kW | n/a | n/a | 0.00 | n/a | nan |
| 4. infrastructure financing 6% real | n/a | n/a | 0.00 | n/a | nan |

**Break-evens** (nan = no parity inside the search range)

* `noak_index_for_coax_parity_any` = 2.81
* `noak_index_for_incumbent_parity_any` = 0.93
* `vit_price_for_parity_ts_base_any` = 344.77
* `vit_price_for_parity_ts_noak_any` = 232.67
* `noak_index_for_coax_parity_full` = n/a
* `noak_index_for_incumbent_parity_full` = n/a
* `vit_price_for_parity_ts_base_full` = n/a
* `vit_price_for_parity_ts_noak_full` = n/a
