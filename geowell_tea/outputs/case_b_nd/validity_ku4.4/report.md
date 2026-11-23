# Case B - North Dakota aquaculture (synthetic well): guided-return validity Ku <= 4.4

## What would need to be true
Thermosiphon at FOAK / today's base / NOAK and with cumulative scale levers (thermosiphon only); coaxial and the incumbent stay at today's assumptions. Best FEASIBLE design re-picked at each step.

**Coverage: any** (coaxial today $117/MWh; incumbent $76/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 147.98 | 1.27 | 301.07 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 124.96 | 1.07 | 204.51 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 107.07 | 0.92 | 129.41 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 92.62 | 0.79 | 68.79 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 3. heat pump $500/kW | 82.29 | 0.70 | 25.46 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 4. infrastructure financing 6% real | 68.97 | 0.59 | 0.00 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |

**Coverage: full (<2% unmet every year)** (coaxial today $134/MWh; incumbent $76/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 147.98 | 1.10 | 301.07 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 124.96 | 0.93 | 204.51 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 107.07 | 0.80 | 129.41 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 92.62 | 0.69 | 68.79 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 3. heat pump $500/kW | 82.29 | 0.61 | 25.46 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 4. infrastructure financing 6% real | 68.97 | 0.51 | 0.00 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |

**Break-evens** (nan = no parity inside the search range)

* `noak_index_for_coax_parity_any` = 3.77
* `noak_index_for_incumbent_parity_any` = n/a
* `vit_price_for_parity_ts_base_any` = 284.85
* `vit_price_for_parity_ts_noak_any` = 208.83
* `noak_index_for_coax_parity_full` = 6.04
* `noak_index_for_incumbent_parity_full` = n/a
* `vit_price_for_parity_ts_base_full` = 204.56
* `vit_price_for_parity_ts_noak_full` = 115.61
