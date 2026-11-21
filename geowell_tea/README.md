# geowell_tea: thermosiphons vs coaxial exchangers in spent oil & gas wells

A transparent, reproducible screening model that answers one question: **in the same existing well,
does a deep gravity thermosiphon (two-phase closed thermosyphon / super-long gravity heat pipe) deliver
low-grade heat more cheaply over its life than a pumped coaxial borehole heat exchanger?** It implements
the brief in `docs/brief.md`. Both technologies get the same rock, the same casing clearance and the same
customer temperatures, and each is optimised independently. Nothing forces them to deliver the same kW.

> Screening model, not a validated design. Read [`MODEL_LIMITATIONS.md`](MODEL_LIMITATIONS.md) first.
> Most cost inputs are **assumed** placeholders (tagged in every output).

## Quick start

```bash
cd geowell_tea
pip install -e .[test]          # numpy, scipy, pandas, pyyaml, matplotlib (pinned)
python -m pytest                 # 62 tests, ~3 s
python -m geowell_tea.cli validate                       # rock check + published field cross-checks
python -m geowell_tea.cli run configs/case_a_pa.yaml     # Case A, ~2 min
python -m geowell_tea.cli run configs/case_b_nd.yaml     # Case B, ~1 min
python -m geowell_tea.cli envelope greenhouse_45_35      # depth x BHT x casing sweep, ~10 min on 2 cores
python -m geowell_tea.cli envelope aquaculture_35_25
python -m geowell_tea.cli envelope greenhouse_45_35 --k 1.5 4.0 --dias 0.127 0.15   # rock-conductivity sensitivity
```

Without installing: `PYTHONPATH=src python -m geowell_tea.cli ...`.

## What is modelled

| Module | Content |
|---|---|
| `rock.py` | Shared transient 1+1D formation model: implicit radial finite volumes per depth slice, adiabatic far field (no free heat from infinity), optional layered conductivity, exact implicit coupling to the well fluid. Verified against the line-source solution; energy conserved to ~1e-10. |
| `thermosiphon.py` | Depth-resolved saturation temperature (vapour weight + interfacial friction), parasitic condensation into cold upper rock, optional vacuum-insulated upper section, falling-film wetting/dry-out or guided condensate return, bottom pool, **stagnation** when the condenser is idle (deep rock heats shallow rock through the pipe). Screens flooding (Tien-Kutateladze/Wallis), Mach number, vapour pressure drop, critical point, freezing, shut-in pressure vs burst rating, collapse under the water-filled annulus, ammonia inventory vs the 10,000 lb PSM/RMP threshold. Returns FEASIBLE / UNVALIDATED / INFEASIBLE with reasons. |
| `coaxial.py` | Annulus-down / insulated-centre-up counterflow solved as one linear system on the same rock slices, with the thermal short circuit through the centre tube; Darcy friction, minor losses, HX drop, buoyancy credit (no static head counted as pump work); variable-flow control capped at the pump/velocity envelope. |
| `fluids.py` | CoolProp was unavailable offline, so: Peng-Robinson saturation + Rackett liquid density (IF97 for water). Within ~1-6 % of reference values (tests). |
| `surfaces.py` | Direct HX, separate-circuit heat pump (Carnot-fraction COP), and adaptive series preheat + HP. `Q_sink = Q_source + W` exactly. |
| `simulate.py` | Monthly dispatch for 20 years against a load profile (duty cycling, backup for unmet load) or a resource-only test. |
| `costs.py` | CAPEX by item (common well-reuse costs vs architecture-specific), OPEX, replacements, plugging at end of life; LCOH, NPV, site-blended cost; vectorised for Monte Carlo. |
| `optimize.py` | Independent design grids: thermosiphon fluid, condenser setpoint, insulated length, film vs guided return; coaxial VIT size, flow, inlet temperature. |
| `envelope.py` | Depth x bottom-hole temperature x casing-ID sweep with Monte Carlo classification. |
| `validate.py` | Published cross-checks actually runnable in this session (see below). |

Architectures: `T_DIRECT`, `T_HP`, `T_ADAPTIVE` (thermosiphon) and `C_DIRECT`, `C_HP`, `C_ADAPTIVE`
(coaxial), plus the customer's backup boiler.

## Configuration and provenance

`configs/case_a_pa.yaml`, `configs/case_b_nd.yaml` and `configs/assumptions.yaml`: every value has
`status: published | assumed | derived | measured` and a source. Each run writes `provenance.csv` next
to its results.

## Outputs (`outputs/`)

* `case_*/report.md`: economic optimum per architecture, resource maximum, fluid screening, TS/C ratio,
  Monte Carlo, tornado, electricity sweep, figures; plus all designs as CSV, monthly time series, CAPEX
  breakdown, `summary.json` (model version, config hash, energy residual).
* `envelope/<scenario>/envelope.csv` + maps: P(thermosiphon cheaper) per cell, with FEASIBLE-only and
  incl.-UNVALIDATED variants; `envelope_conditional_vit_price.csv` repeats the classification at fixed
  VIT prices.
* `validation/`: rock line-source check, Xiong'an D34 and Taiyuan cross-checks, Penn State sanity check,
  list of benchmarks not reproduced and why.

## Results

See [`RESULTS.md`](RESULTS.md).
