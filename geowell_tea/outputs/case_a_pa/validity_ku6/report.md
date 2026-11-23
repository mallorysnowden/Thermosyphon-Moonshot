# Case A - Western PA greenhouse: guided-return validity Ku <= 6

## What would need to be true
Thermosiphon at FOAK / today's base / NOAK and with cumulative scale levers (thermosiphon only); coaxial and the incumbent stay at today's assumptions. Best FEASIBLE design re-picked at each step.

**Coverage: any** (coaxial today $313/MWh; incumbent $48/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 347.67 | 1.11 | 1407.84 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 298.92 | 0.95 | 1178.92 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 256.22 | 0.82 | 978.36 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 213.86 | 0.68 | 779.45 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 3. heat pump $500/kW | 199.17 | 0.64 | 710.47 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 4. infrastructure financing 6% real | 167.41 | 0.53 | 561.33 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |

**Coverage: full (<2% unmet every year)** (coaxial today $313/MWh; incumbent $48/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 347.67 | 1.11 | 1407.84 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 298.92 | 0.95 | 1178.92 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 256.54 | 0.82 | 979.90 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 214.86 | 0.69 | 784.14 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 3. heat pump $500/kW | 200.40 | 0.64 | 716.26 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 4. infrastructure financing 6% real | 168.79 | 0.54 | 567.81 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |

**Break-evens** (nan = no parity inside the search range)

* `noak_index_for_coax_parity_any` = 6.29
* `noak_index_for_incumbent_parity_any` = n/a
* `vit_price_for_parity_ts_base_any` = 214.81
* `vit_price_for_parity_ts_noak_any` = 110.08
* `noak_index_for_coax_parity_full` = 6.29
* `noak_index_for_incumbent_parity_full` = n/a
* `vit_price_for_parity_ts_base_full` = 214.81
* `vit_price_for_parity_ts_noak_full` = 110.88
