# Case A-NL - Case A well geometry with Dutch greenhouse economics: guided-return validity Ku <= 4.4

## What would need to be true
Thermosiphon at FOAK / today's base / NOAK and with cumulative scale levers (thermosiphon only); coaxial and the incumbent stay at today's assumptions. Best FEASIBLE design re-picked at each step.

**Coverage: any** (coaxial today $328/MWh; incumbent $98/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 362.67 | 1.10 | 1317.15 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| today's base costs | 313.10 | 0.95 | 1070.69 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 270.01 | 0.82 | 856.41 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 227.65 | 0.69 | 645.79 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 3. heat pump $500/kW | 212.97 | 0.65 | 572.76 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |
| 4. infrastructure financing 6% real | 181.21 | 0.55 | 414.86 | 0.04 | T_HP ammonia T_top=25C ins=0m guided |

**Coverage: full (<2% unmet every year)** (coaxial today $328/MWh; incumbent $98/MWh)
| thermosiphon case | ts_lcoh | ts_over_coax | carbon_price_for_parity | ts_unmet_max | ts_design |
|---|---|---|---|---|---|
| FOAK (1.5x base) | 363.56 | 1.11 | 1321.57 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| today's base costs | 314.81 | 0.96 | 1079.19 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 1. NOAK manufacturing + automated install (raw x 2.5) | 272.43 | 0.83 | 868.46 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 2. standardised well-reuse programme (common -40%, contingency 10%) | 230.75 | 0.70 | 661.19 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 3. heat pump $500/kW | 216.30 | 0.66 | 589.31 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |
| 4. infrastructure financing 6% real | 184.68 | 0.56 | 432.13 | 0.00 | T_HP ammonia T_top=20C ins=0m guided |

**Break-evens** (nan = no parity inside the search range)

* `noak_index_for_coax_parity_any` = 6.33
* `noak_index_for_incumbent_parity_any` = n/a
* `vit_price_for_parity_ts_base_any` = 212.67
* `vit_price_for_parity_ts_noak_any` = 107.00
* `noak_index_for_coax_parity_full` = 6.24
* `noak_index_for_incumbent_parity_full` = n/a
* `vit_price_for_parity_ts_base_full` = 216.87
* `vit_price_for_parity_ts_noak_full` = 112.94
