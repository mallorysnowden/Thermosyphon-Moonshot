# Results (model v0.1.0, 20 Nov 2026)

All numbers below were computed by the code in this folder from the configs as committed. Most cost inputs
are **assumed** (see `configs/assumptions.yaml`). Read `MODEL_LIMITATIONS.md` before quoting anything.

## 1. Headline answer

**Under the base cost assumptions there is no depth-temperature-diameter region where a thermosiphon
*consistently* (P >= 0.9 across the cost Monte Carlo) beats a coaxial exchanger on lifetime cost per MWh of
useful heat.** A conditional envelope does exist, and it is set mostly by the price of the coaxial loop's
vacuum-insulated centre tubing (VIT) and by whether the customer can absorb the coaxial loop's extra
output.

| Scenario (k = 2.5 W/m/K) | Cells | Max P(TS cheaper), FEASIBLE designs | Incl. UNVALIDATED guided designs | TS-consistent cells if VIT = $350 / $500 / $700 per m |
|---|---|---|---|---|
| Greenhouse 45/35 C, customer sized to each design's output | 128 | 0.25 | 0.74 | 0 / 16 / 50 |
| Aquaculture 35/25 C (ND prices), sized customer | 124 | 0.36 | 0.67 | 0 / 13 / 46 |
| Greenhouse, **fixed 120 kW customer** (load-limited) | 128 | 0.75 | 0.82 | 39 / 82 / 86 |
| Greenhouse sized, k = 1.5 / 4.0 (127 and 150 mm casings) | 64 each | 0.41 / 0.19 | 0.67 / 0.80 | n/a |

Base VIT assumption: $250/m (range $120-500). No public VIT price was found, so this is the single most
important number to replace with a quote.

**Conditional envelope (where the thermosiphon *does* win consistently):**

* **Customer smaller than the well (load-limited, like the 120 kW greenhouse) and VIT >= ~$350/m:**
  depth **2-4 km**, casing ID **127-180 mm**, bottom-hole temperature **50-125 C** (patchy at 95-110 C,
  where a direct coaxial loop becomes viable).
* **Customer able to take everything the well gives, and VIT >= ~$500/m:** casing **>= 150 mm**, depth
  **2-4 km**, bottom-hole temperature **~80-110 C** (gradient ~20-45 K/km). Cells that win in *both* the
  greenhouse and aquaculture sweeps: 150 mm at 2.0 km/95 C, 2.5 km/80 C, 3.0 km/80 C; 180 mm at
  2.5 km/95-110 C, 3.0 km/80-95 C, 3.5 km/80 C, 4.0 km/80 C.
* **Never** (at any VIT price tested): **100 mm casings** (vapour flooding), **bottom-hole >= ~140 C**
  (ammonia, critical point 132 C, stagnates supercritical at shut-in, so all designs are UNVALIDATED), and
  **~1 km wells** (too little VIT for its cost to matter).

## 2. Why: physics findings

1. **Thermosiphons extract less heat from the same well.** Median year-20 extraction of the best
   thermosiphon is **66-68 %** of the best coaxial loop (FEASIBLE designs; 79-81 % including UNVALIDATED
   guided designs). At k = 4 W/m/K the ratio drops to 51 %, because the extra heat runs into vapour-flow
   limits.
2. **The vapour column's own weight matters.** In a 1.7 km ammonia pipe the saturation temperature at the
   bottom is ~5 K above the condenser. Heavy vapours are far worse: propane, isobutane and pentane give
   zero direct-heat output in Case A for this reason. CO2 cannot condense above 31 C. Water works only at
   low duty (sub-atmospheric vapour, friction and flooding). **Ammonia is the only fluid that survives
   screening**, matching the field systems.
3. **Direct heat is a poor use of a deep thermosiphon.** With a 45 C supply, the uninsulated upper section
   condenses vapour into cold shallow rock and the net output goes to zero. Insulating it with VIT takes
   vapour area and costs as much as the coaxial loop's VIT. Case A: thermosiphon direct 12 kW at year 20
   vs coaxial direct 27 kW. The winning thermosiphon is almost always a **heat-pump design with a 12-20 C
   condenser, uninsulated, with guided condensate return**.
4. **Transport limits set the diameter floor.** In 100 mm (and often 127 mm) casings, high-duty designs
   exceed the counter-current flooding limit. Guided-return designs beyond Ku = 3.2 are flagged
   UNVALIDATED: the Xiong'an field pipe operated there, but correlations don't cover it. Allowing them
   lifts P(TS cheaper) to ~0.7 in 127 mm, 3-4 km, 80-95 C wells.
5. **Idle thermosiphons short-circuit the well.** With a seasonal load, the closed condenser lets the pipe
   move heat from deep to shallow rock all summer (modelled as stagnation). The coaxial loop simply stops.

## 3. Case results (economic optimum per architecture, FEASIBLE designs)

**Case A: western PA greenhouse** (1,737 m, 80 C, 150 mm, 120 kW peak-month load, gas incumbent):

| | Year-20 heat (kW) | LCOH ($/MWh) | CAPEX ($k) | Note |
|---|---|---|---|---|
| T_HP (ammonia, 25 C, guided) | 87 | **303** | 1,133 | cheapest overall; meets load |
| C_HP (VIT 114 mm, 1.5 kg/s, 20 C in) | 107 | 314 | 1,246 | VIT = $434k |
| C_DIRECT | 27 | 547 | 1,099 | covers 43 % of load |
| T_DIRECT | 12 | 1,276 | 1,103 | covers 19 % of load |
| Incumbent gas boiler | | **48** | | $12.38/Mcf (EIA), 85 % efficiency |

TS/C LCOH ratio 0.97; Monte Carlo P(TS cheaper) = **0.42** (contested). The tornado's dominant input is VIT
price (ratio 0.73-1.16 over $120-500/m).

**Case B: ND aquaculture, synthetic well** (3,000 m, 110 C, 127 mm, 300 kW, propane incumbent):

| | Year-20 heat (kW) | LCOH ($/MWh) | CAPEX ($k) |
|---|---|---|---|
| C_DIRECT (VIT 89 mm, variable flow) | 176 | **125** | 1,547 |
| C_ADAPTIVE | 233 | 133 | 1,912 |
| T_ADAPTIVE (ammonia 35 C, guided) | 123 | 171 | 1,510 |
| T_DIRECT | 91 | 190 | 1,213 |
| T_HP | none FEASIBLE: flooding in the 127 mm bore (UNVALIDATED guided design: $123/MWh) | | |
| Incumbent propane | | **76** | |

TS/C ratio 1.37; P(TS cheaper) = **0.006** (0.46 if the UNVALIDATED guided T_HP designs are allowed).

**Commercial viability, either technology:** single-well retrofits at 100-300 kW cost **$125-315/MWh**,
**1.6x** (Case B, propane) to **6.3x** (Case A, cheap pipeline gas) the incumbent fuel's useful-heat cost. All NPVs are negative at a 90 %-of-incumbent heat
price. Fixed well-reuse costs (acquisition, permits, MIT, workover, 250 m distribution, controls,
contingency) are ~$0.5M per well, plus end-of-life plugging, whichever technology is chosen. That, more
than the downhole choice, is what kills the economics at this scale.

## 4. Validation status

| Check | Result |
|---|---|
| Rock model vs line-source solution | error 0.024 K (yr 1), 0.013 K (yr 20); energy residual 2e-11 |
| End-to-end energy balance (all designs) | rock heat loss = delivered heat to < 1e-9 |
| Properties vs reference values | ammonia/propane/isobutane/CO2/pentane within 3-6 %; water (IF97) within 1 % |
| **Xiong'an D34**, 4,149 m ammonia SLGHP (Huang et al. 2024), 40-day averages | model = **15-55 %** of published 1,049/596/442 kW. Gap is largest at high condenser temperature; best with insulated top or convective-reservoir proxy (~0.45-0.55). Not calibrated. |
| Taiyuan, 2 x ~2.1 km (Chen et al. 2024) | ~340 kW geothermal (conduction only) vs a reported ~1 MW system output (incl. heat pump; paper cites groundwater crossflow) |
| Penn State 120 kW (different closed loop) | our coaxial: 131 kW yr 1 / 96 kW yr 20 at a 20 C inlet; plausible |
| Zolfagharroshan 2024; Gruber 2026 | **not attempted**: PDFs were not in the session, and their site inputs can't be guessed without calibrating |

The Xiong'an gap means absolute outputs are conservative. If real long thermosiphons beat conduction
models by more than coaxial loops do, the thermosiphon is under-credited here.

## 5. Most valuable next measurements

1. **A VIT quote** ($/m installed, 3.5-5.5 in) and a quote for gas-tight premium-connection tubing. These two
   prices decide which technology wins.
2. **A real candidate well:** caliper log (usable ID), temperature log, cement bond log. Casing ID below
   ~127 mm rules the thermosiphon out.
3. **A long guided-return thermosiphon test above Ku = 3.2 in a conduction-dominated formation.** It would
   settle whether the UNVALIDATED designs (which roughly double the thermosiphon's win probability) are
   real, and explain the Xiong'an gap.
4. **Customer sizing.** The thermosiphon's case is much stronger when the load is smaller than the well can
   deliver, so match the well to a customer of ~100-150 kW, not the reverse.
