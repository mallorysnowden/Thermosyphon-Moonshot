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
python -m pytest                 # 76 tests, ~30 s
python -m geowell_tea.cli validate                       # rock check + published benchmarks (~1 min)
python -m geowell_tea.cli run configs/case_a_pa.yaml     # Case A, ~2 min
python -m geowell_tea.cli run configs/case_b_nd.yaml     # Case B, ~1 min
python -m geowell_tea.cli envelope greenhouse_45_35      # depth x BHT x casing sweep, ~45 min on 2 cores
python -m geowell_tea.cli envelope aquaculture_35_25
python -m geowell_tea.cli envelope greenhouse_45_35 --k 1.5 4.0                    # rock-conductivity sensitivity
python -m geowell_tea.cli envelope greenhouse_45_35_packer --dias 0.127 0.15 0.18    # IP-flagged packer design allowed
python -m geowell_tea.cli envelope greenhouse_45_35_no_vapour_head --dias 0.127 0.15 0.18  # TS-favourable bound
```

Without installing: `PYTHONPATH=src python -m geowell_tea.cli ...`.

## What is modelled

| Module | Content |
|---|---|
| `rock.py` | Shared transient 1+1D formation model: implicit radial finite volumes per depth slice, adiabatic far field (no free heat from infinity; TEA default) or fixed-temperature far field (benchmarks), optional layered conductivity, exact implicit coupling to the well fluid. Verified against the line-source solution; energy conserved to ~1e-10. |
| `thermosiphon.py` | Depth-resolved saturation temperature (vapour weight + interfacial friction), Cooper boiling / Nusselt condensation coefficients, parasitic condensation into cold upper rock, optional vacuum-insulated upper section, falling-film wetting/dry-out or guided condensate return, bottom pool, **stagnation** when the condenser is idle (deep rock heats shallow rock through the pipe). Flooding (Tien-Kutateladze/Wallis) and Mach limits **throttle** the condenser rather than failing the design. Optional IP-flagged packer architecture (SI23618A, Gruber 2026) and a coupled helical-coil condenser. Screens Mach number, vapour pressure drop, critical point, freezing, shut-in pressure vs burst rating, collapse under the water-filled annulus, ammonia inventory vs the 10,000 lb PSM/RMP threshold. Returns FEASIBLE / UNVALIDATED / INFEASIBLE with reasons. |
| `coaxial.py` | Annulus-down / insulated-centre-up counterflow solved as one linear system on the same rock slices, with the thermal short circuit through the centre tube; Darcy friction, minor losses, HX drop, buoyancy credit (no static head counted as pump work); variable-flow control capped at the pump/velocity envelope. |
| `correlations.py` | Cooper and Imura pool-boiling, Nusselt film condensation, Mori-Nakayama/Schmidt helical-coil heat transfer and pressure drop (as used by Gruber 2026 and Zolfagharroshan 2024). |
| `fluids.py` | CoolProp was unavailable offline, so: Peng-Robinson saturation + Rackett liquid density (IF97 for water). Within ~1-6 % of reference values (tests). |
| `surfaces.py` | Direct HX, separate-circuit heat pump (Carnot-fraction COP), and adaptive series preheat + HP. `Q_sink = Q_source + W` exactly. |
| `simulate.py` | Monthly dispatch for 20 years against a load profile (duty cycling, backup for unmet load) or a resource-only test. |
| `costs.py` | CAPEX by item (common well-reuse costs vs architecture-specific), OPEX, replacements, plugging at end of life; LCOH, NPV, site-blended cost; vectorised for Monte Carlo. |
| `optimize.py` | Independent design grids: thermosiphon fluid, condenser setpoint, insulated length, film vs guided return; coaxial VIT size, flow, inlet temperature. |
| `envelope.py` | Depth x bottom-hole temperature x casing-ID sweep with Monte Carlo classification. |
| `validate.py` | Published benchmarks: Gruber 2026 (1.8 km ammonia, conventional + packer), Taiyuan field data via Gruber, 4 km HDR water pipe, Zolfagharroshan 2024 (shallow water thermosyphon with coil condenser), Xiong'an D34, Brown 2026 coaxial DBHE sensitivities. Nothing is tuned to them. |

Architectures: `T_DIRECT`, `T_HP`, `T_ADAPTIVE` (thermosiphon) and `C_DIRECT`, `C_HP`, `C_ADAPTIVE`
(coaxial), plus the customer's backup boiler.

### What would need to be true (NOAK update)

Every `run` now writes `what_must_be_true.csv` and `breakevens.csv`: the thermosiphon at FOAK / base / NOAK
cost levels and with cumulative scale levers (thermosiphon only) against coaxial and the incumbent at
today's costs, for any coverage and for full coverage (< 2 % unmet every year). Validity regimes:

```bash
python -m geowell_tea.cli run configs/case_b_nd.yaml --ku 4.4   # guided return validated to Ku 4.4
python -m geowell_tea.cli run configs/case_b_nl.yaml             # Dutch-price variant (also case_a_nl)
```

## Web calculator (Streamlit)

`app.py` is a fast, thermosiphon-only calculator built on `geowell_tea.fast`. The user picks the
configuration (**hybrid**: condenser = heat-pump evaporator, or **direct** heat), the condensate-return method
(guided stepped reflux or falling film), the well, the heat demand and prices; the tool searches only the
condenser setpoint and insulated length (3-10 simulations, a few seconds) and compares the best design with
the incumbent boiler, including the "what would need to be true" waterfall. Invalid inputs return an error
with a one-line reason (well too cold for direct heat, no operable point because of vapour-flow limits,
ammonia past its critical point, string fails collapse/burst, no design covers the full load); questionable
results are shown with warnings (unvalidated Ku, near-flooding film, unmet load, PSM threshold, ammonia in
the machinery room). On the four presets it reproduces the full model's best design and cost within 0.1 %.

```bash
pip install streamlit && streamlit run app.py          # local
bash scripts/build_hf_space.sh                          # Hugging Face Space bundle in dist/hf_space/
huggingface-cli upload <hf-user>/<space-name> dist/hf_space . --repo-type=space
```

To deploy on **Streamlit Community Cloud** (free): at share.streamlit.io choose this repo, branch `main`,
main file `geowell_tea/app.py`, and Python 3.12 under Advanced settings. Dependencies come from
`geowell_tea/requirements.txt` (Streamlit itself is preinstalled). Hugging Face no longer offers a Streamlit
Space type, so the `build_hf_space.sh` bundle is only useful with a paid Docker Space.

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
* `validation/`: one CSV per benchmark (model vs published, ratio/error, status), rock line-source check,
  and the list of benchmarks not reproduced and why.

## Results

See [`RESULTS.md`](RESULTS.md).
