# Model limitations

`geowell_tea` is a **screening model**. It is not a validated design tool, a well-completion design or a
basis for investment. Every limitation below is also visible in the exported results (status flags,
provenance tags, validation tables).

## 1. Benchmarks: what was compared, and what the gaps say

No model parameter was tuned to any benchmark (`outputs/validation/`). The comparisons are against other
models (Gruber, Zolfagharroshan, Huang, Brown) as well as field data (Xiong'an, Taiyuan), so agreement is
evidence of consistent physics, not proof of accuracy.

| Benchmark | Type | Result | What it says |
|---|---|---|---|
| 4 km HDR water heat pipe (Huang model, via Gruber 2026 Fig. 7b) | model | -0.4 to -4.5 % over 10 yr | Rock + water-pipe physics agree when the vapour column is light |
| Zolfagharroshan 2024, 150-250 m water thermosyphon with 2 m helical-coil condenser | model | +15 to +19 % (20-yr mean) | Coil condenser limits output; coil correlation reproduces their Nu within 8 % |
| Gruber 2026, 1,800 m ammonia, conventional and packer | model | 0.38-0.75x with vapour head; **0.78-0.82x without** | Decline 1-10 yr matches (19 % vs 19-23 %). Most of the gap is how strongly the ammonia vapour column's weight is penalised |
| Taiyuan #2, ~2.1 km ammonia (Chen 2024 field data via Gruber Fig. 7a) | field | 0.58-0.71x at 120 d | Even an ideal pipe (zero internal resistance) in conducting rock gives only 0.69-0.77x of the field values: the field site gets extra heat from the formation (groundwater crossflow, which Chen et al. cite, or higher effective k) |
| Xiong'an D34, 4,149 m ammonia (Huang 2024 field) | field | 0.15-0.55x of 40-day averages | Carbonate reservoir with a convective low-gradient section; diameters step; inputs inconsistent |
| Brown 2026 Fig. 4 (after Brown 2023b), 920 m coaxial DBHE sensitivities | model | base 54.5 kW vs 44-53 kW band; each sensitivity's span 13-30 % larger than published | Coaxial model is, if anything, **optimistic** (base geometry assumed, not published) |

**Implications.**

* *Thermosiphon is probably under-credited, coaxial possibly over-credited.* Against Gruber the thermosiphon
  model runs ~0.7x (vapour head on) to ~0.8x (off); against Brown the coaxial model runs ~1.0-1.25x. Both
  biases push the ranking towards coaxial. The `greenhouse_45_35_no_vapour_head` envelope is the
  TS-favourable bound for this.
* *Field sites outperform conduction for both technologies.* The Taiyuan conduction ceiling shows the extra
  heat comes from the formation, not from thermosiphon-specific physics, so it is **not** credited to the
  thermosiphon alone. Brown et al. (2026) note that groundwater flow only matters above a Darcy velocity of
  ~1e-6 m/s (up to +25 kW for a DBHE) and that aquifers are usually a small part of a deep well.
* Not reproduced: the Gruber integrated heating/cooling system (needs their flash-vessel heat-pump model and
  hourly loads), the Zolfagharroshan 32 m experimental start-up transient (outside a monthly model), and
  the UK DBHE candidate outputs in Brown 2026 (82-198 kW at 4 L/s over 25 yr; well geometry not given),
  which are only used as a plausibility range.

## 1b. NOAK update (22 Nov 2026): what is and is not covered

* **NOAK cost level** is an estimate built from raw-material content x 2.5 plus a bottom-up automated
  installation cost; it is not a quote and assumes the modular manufacturing plan works as described
  (single-station weld + PAUT cycle ~25 min per 12 m segment). FOAK = base x 1.5 is a judgement.
* **Leaks are excluded from cost** by choice (all-welded, PAUT-inspected string; annulus NH3 monitoring).
  A downhole leak would mean pulling and re-running the string: a real risk, not modelled.
* **Factory insulation in a N2-capped annulus** is modelled as conduction + gap radiation with bare weld
  bands in parallel. Not modelled: loss of the N2 cap (aerogel compaction under liquid head), moisture
  migration, liquid-level control, casing collapse with gas inside an old well (must be checked per well),
  and the smaller tube OD's transition piece. The tube wall is still sized for a liquid-filled annulus
  (conservative).
* **Stepped reflux built into each module** (Xiong'an-style ladder) is costed but its flooding benefit is the
  generic "guided return" model; its freedom to operate has not been checked.
* **Direct coupling** adds 15 % (range 0-40 %) to heat-pump capex; ammonia then enters the machinery room
  (IIAR scope, heat-pump charge counts toward the PSM/RMP threshold), which is flagged but not costed.
* **Netherlands cases** reuse the US wells, loads and non-energy costs; only energy prices change. No Dutch
  subsidy (SDE++), permitting, labour or abandonment costs were modelled.
* **Not rerun:** the depth-temperature-diameter envelopes, tornado drivers and fluid screening in
  `RESULTS.md` sections 1+ predate this update.

## 2. Physics simplifications

| Area | Simplification | Effect |
|---|---|---|
| Rock | 1+1D: radial conduction per depth slice, no vertical conduction; far field adiabatic at 200 m (TEA default) or fixed-temperature (Dirichlet, used for benchmarks to match the papers) | Adiabatic is conservative (omits background heat flux); verified against the line-source solution (<0.03 K after 1 yr) |
| Groundwater | Not modelled (flag only); layered "effective k" proxy available | Can under-predict strongly in aquifers |
| Time step | Monthly; duty-cycling within the month | Hourly peaks are not resolved; equipment is sized with a 1.3x peak factor |
| Thermosiphon | Quasi-steady, 1D vapour momentum (head + interfacial friction), film wetting; Cooper (nucleate boiling) evaporator and Nusselt film-condensation coefficients, as in Gruber 2026 / Zolfagharroshan 2024 (Imura selectable) | No start-up, geysering, entrainment details, pool dynamics or non-condensable gas build-up. Wall roughness for Cooper (1 um) is assumed |
| Transport limits | Tien-Kutateladze / Wallis flooding and vapour Mach number. Exceeding them **throttles** the pipe (condenser temperature rises until the limit is met) instead of failing the design. Guided return: Ku 3.2-6 runs but is UNVALIDATED (field-demonstrated, not covered by correlations); film return near flooding (> 0.7) is UNVALIDATED | Limits are screening criteria, not predictions; throttling assumes stable operation at the limit |
| Condenser | TEA: ideal condenser at the setpoint. Benchmarks: optional helical-coil condenser (Mori-Nakayama / Schmidt) coupled to the pipe | A real condenser of fixed size will reduce output, as Zolfagharroshan show |
| Packer architecture | Above the packer: vacuum-insulated vapour channel (assumed 50 % of bore) and separate liquid line, so no counter-current flooding there | Geometry inferred from the patent abstract and Gruber 2026; not a qualified design |
| Coaxial | Single-phase water, annulus-down flow only, VIT as an effective conductivity | Centre-down flow and glycol below 3 C are not modelled |
| Surface | Carnot-fraction COP (eta = 0.5), constant approach temperatures | Replace with manufacturer maps before design |
| Properties | Peng-Robinson + Rackett (IF97 for water), not CoolProp/REFPROP; within ~1-6 % of reference values in tests | Transport properties (sigma, mu) are rough and only affect screening limits |
| Pipe mechanics | Simplified collapse (0.8 x min of yield/elastic) and Barlow burst | Real designs need API 5C3 / ISO 10400 checks |

## 3. Economics

* **No cost input is a vendor quote.** Most are engineering-judgment placeholders with ranges (see
  `configs/assumptions.yaml` and each case's `provenance.csv`). The biggest single driver of the
  thermosiphon-vs-coaxial ranking is the **price of vacuum-insulated tubing** (no public price was found).
* Well reuse is not free: acquisition, permits, integrity testing, workover and end-of-life plugging are
  included as common costs, but **well-specific liabilities** (casing condition, cement, leaks, re-entry
  risk) can dominate a real project and are not modelled. Brown et al. (2026) list the open questions a
  regulator will ask of any repurposed well, whichever loop goes in: is it truly hydraulically isolated;
  density contrast with formation brine; galvanic corrosion in saline, reducing conditions; fugitive
  methane or H2S; thermal stress on casing and cement from circulating chilled fluid; monitoring plan; and
  who funds plugging and abandonment. They also flag an unresolved liability question: converting a
  hydrocarbon well to a geothermal well must not become a route around P&A obligations. Older, deviated and
  boom-era wells are more likely to have integrity problems.
* Brown et al. (2026) report the UK's Third Energy KM8 DBHE study (984 kW peak, 2.28 GWh/yr for 147
  homes) was **not economic without grants**, consistent with this model's finding that single-well
  retrofits cost several times the incumbent fuel.
* The coaxial VIT price assumption ($250/m, range $120-500) is unquoted. Brown et al. (2026), citing Gascuel
  et al. (2022), note VIT is expensive and may not pay back versus plain HDPE centre pipe (+22 kW in that
  study); the coaxial grid already includes a cheaper composite centre tube for that reason.
* Heat revenue is an explicit offtake assumption (90 % of the incumbent's useful-heat cost), not the
  avoided bill.
* Pre-tax, unlevered, real 2026 USD, no incentives (for example US federal geothermal credits), no carbon
  price.
* Ammonia inventory above 10,000 lb triggers OSHA PSM / EPA RMP costs; flammable fluids get a hazardous-area
  allowance. Permitting a toxic or flammable pressure system in a reused oil & gas well is not costed in
  detail.
* The patented packer architecture (SI23618A, Gruber et al. 2026) is **not** in the default design grid.
  It is available as an IP-flagged sensitivity (`greenhouse_45_35_packer`) with an assumed hardware cost
  ($60k, range 30-150k) and a licence fee of $0-100/kW (0 in the base case because no terms are public).
  Simulating it does not establish freedom to operate.

## 4. Inputs that are synthetic

* Case A: depth and bottom-hole temperature from the Penn State (2025) study; everything else assumed.
  The greenhouse load is a proxy, not metered.
* Neither case has a real casing tally. Brown et al. (2026) note that hydrocarbon wells narrow with depth
  (telescoping casing, liners), and that 5-inch production casing restricts a coaxial centre pipe and its
  insulation; the same limit is harsher for a thermosiphon (vapour area). The model uses one ID for the
  whole well.
* Case B: **all geology is synthetic**. The Mandaree open-loop doublet results are not transferable to a
  single closed-loop well.
