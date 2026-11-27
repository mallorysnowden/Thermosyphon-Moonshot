# permafrost_tea: thermosyphon permafrost stabilization

Installed and 30-year cost of keeping ground frozen with the platform's aluminium/ammonia thermosyphon,
against today's incumbent (steel/CO2, Arctic Foundations-style) and the non-thermosyphon alternatives.

```bash
cd permafrost_tea && pip install -e .[test] && python -m pytest
python -m permafrost_tea.run      # writes outputs/summary.csv, outputs/sensitivity.csv, outputs/results.json
```

## Cases

| Case | Configuration | Compared with |
|---|---|---|
| A. New 1,500 m2 school/clinic on piles, Y-K Delta (warm permafrost) | Integrated: thermosyphon insert in steel pipe pile, 12 m | 18 m adfreeze piles; incumbent thermopiles |
| B. New 10,000 m2 heated slab (data hall / hangar), North Slope | Integrated: evaporators laid in the gravel pad | Elevated on piles; incumbent flat loop |
| C. Retrofit 1,500 m2 school, Ross River-type | Standalone: inclined units drilled from both long sides | Relevel every 5 yr; replace; active crawlspace refrigeration; incumbent |
| D. Retrofit 1 km of highway, Alaska Highway | Standalone: Dry Creek design (7 m, 34 m inclined, 19.5 m2) | Repair as it settles; air-convection embankment; incumbent |

## Results (30-yr NPV ratio, platform at NOAK)

| Case | vs BAU | vs best alternative | Sensitivity range |
|---|---|---|---|
| A | 0.81 | 0.81 | 0.68-0.95 (thermopile depth) |
| B | 0.39 | 0.70 (incumbent flat loop) | 0.66-0.73 |
| C | 0.79 | 0.79 | 0.74-1.57 (relevel interval) |
| D | 10.2 | 10.2 | 2.8-20 (repair cost per km) |

## Method and calibration

- Unit heat extraction = (finned condenser at 5 W/m2K x 0.85 exposure, in series with frozen-ground conduction)
  x degree-days of air colder than -2 C ground. Daily sinusoidal climate, +0.5 C/decade, 75% in winter;
  units sized to the end-of-life climate.
- Platform hardware: 6063 Al at $5.3/kg x 2.5 finished/raw, 3 mm wall, coated buried section, $150 field joint
  beyond 12 m, 25% margin. NOAK field targets: -20% drilling, -40% install and engineering, -20% mobilization.
  FOAK: index 3.5, incumbent field rates.
- Incumbent: $1,000 + $100/m + $150/m2 radiator (UNAVCO thermopile monument $1,700); drilling $350/m.
  Dry Creek (58 units) prices at $1.69M vs a CAD 1.3-2.3M budget; incumbent flat loop at $205/m2.

## Limitations

- Steady-resistance physics; no transient freeze-front or peak-temperature check between pipes.
- Case B's BAU (elevated structural floor at $400/m2) and case A's relevel probabilities are assumptions.
- Drilling, mobilization and engineering costs are the largest inputs and have the thinnest public data.
- Russia (the largest market) is excluded from pricing except as a benchmark.
