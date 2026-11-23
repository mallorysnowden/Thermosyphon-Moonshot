# Case B-NL - Case B well geometry with Dutch economics: guided-return validity Ku <= 4.4

## What would need to be true
Thermosiphon at FOAK / today's base / NOAK and with cumulative scale levers (thermosiphon only); coaxial and the incumbent stay at today's assumptions. Best FEASIBLE design re-picked at each step.

**Coverage: any** (coaxial today $123/MWh; incumbent $98/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 168.74 | 1.38 | 352.87 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 144.96 | 1.18 | 234.59 | 0.10 | T_HP ammonia T_top=25C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 118.56 | 0.97 | 103.35 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 96.53 | 0.79 | 0.00 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |
| 3. heat pump $500/kW | 96.53 | 0.79 | 0.00 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |
| 4. infrastructure financing 6% real | 78.76 | 0.64 | 0.00 | 0.49 | T_DIRECT ammonia T_top=40C ins=1049m guided |

**Coverage: full (<2% unmet every year)** (coaxial today $154/MWh; incumbent $98/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 168.74 | 1.10 | 352.87 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 145.73 | 0.95 | 238.44 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 127.83 | 0.83 | 149.44 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 113.39 | 0.74 | 77.61 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 3. heat pump $500/kW | 103.06 | 0.67 | 26.25 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 4. infrastructure financing 6% real | 89.55 | 0.58 | 0.00 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |

**Break-evens** (nan = no parity inside the search range)

* `noak_index_for_coax_parity_any` = 2.81
* `noak_index_for_incumbent_parity_any` = 0.93
* `vit_price_for_parity_ts_base_any` = 344.77
* `vit_price_for_parity_ts_noak_any` = 232.67
* `noak_index_for_coax_parity_full` = 5.92
* `noak_index_for_incumbent_parity_full` = n/a
* `vit_price_for_parity_ts_base_full` = 209.26
* `vit_price_for_parity_ts_noak_full` = 120.31
