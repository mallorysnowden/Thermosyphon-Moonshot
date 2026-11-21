# Model limitations

`geowell_tea` is a **screening model**. It is not a validated design tool, a well-completion design or a
basis for investment. Every limitation below is also visible in the exported results (status flags,
provenance tags, validation tables).

## 1. No deep field calibration, and the one field comparison shows a large gap

* The only kilometre-scale thermosiphon with published heat output that we could compare against is the
  4,149 m ammonia SLGHP in well D34, Xiong'an (Huang et al. 2024, *Energy Environ. Sci.*). Our
  conduction-only model predicts **15-55 % of the published 40-day averages** (1,049 / 596 / 442 kW at
  36.8 / 52.8 / 59.3 C production temperature), depending on rock conductivity, insulation and a crude
  convective-reservoir proxy (`outputs/validation/xiongan_d34.csv`).
* Likely reasons: the D34 bottom section is in carbonate strata with a low gradient (1.23 C/100 m) that
  suggests convective groundwater flow (not modelled); the published gradients and bottom-hole temperature
  are not mutually consistent; the pipe's diameters step (244.5/177.8/127 mm) while we model one; the
  upper-section design, test sequence and rock properties are not published.
* Chen et al. (2024, Taiyuan) also attribute much of the longer pipe's yield to **groundwater crossflow**.
  Our two-pipe conduction-only estimate (~340 kW geothermal) is consistent with a ~1 MW system output only
  if the heat pump and groundwater contribute substantially.
* **Implication:** absolute kW and $/MWh for *both* technologies are probably conservative in convective
  formations. Because both share the same rock model, rankings are less affected than absolute values, but
  if long thermosiphons gain more from real-world effects than coaxial loops (for example better wall
  wetting or annulus convection), the thermosiphon is **under-credited**. Field data from a matched
  same-well test would be the most valuable measurement.
* Not reproduced: Zolfagharroshan et al. (2024) and Gruber et al. (2026). The brief says their PDFs were
  supplied, but they were not present in this session, and their site inputs cannot be guessed without
  turning reproduction into calibration (`outputs/validation/not_reproduced.csv`).

## 2. Physics simplifications

| Area | Simplification | Effect |
|---|---|---|
| Rock | 1+1D: radial conduction per depth slice, no vertical conduction, adiabatic far field at 200 m | Conservative (omits background heat flux); verified against the line-source solution (<0.03 K after 1 yr) |
| Groundwater | Not modelled (flag only); layered "effective k" proxy available | Can under-predict strongly in aquifers |
| Time step | Monthly; duty-cycling within the month | Hourly peaks are not resolved; equipment is sized with a 1.3x peak factor |
| Thermosiphon | Quasi-steady, 1D vapour momentum (head + interfacial friction), Nusselt-type film wetting, constant evaporation/condensation coefficients | No start-up, geysering, entrainment details, pool dynamics or non-condensable gas build-up |
| Flooding | Tien-Kutateladze / Wallis screening; for guided-return designs Ku > 3.2 is UNVALIDATED up to the field-demonstrated ~6 | Limits are screening criteria, not predictions |
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
  risk) can dominate a real project and are not modelled.
* Heat revenue is an explicit offtake assumption (90 % of the incumbent's useful-heat cost), not the
  avoided bill.
* Pre-tax, unlevered, real 2026 USD, no incentives (for example US federal geothermal credits), no carbon
  price.
* Ammonia inventory above 10,000 lb triggers OSHA PSM / EPA RMP costs; flammable fluids get a hazardous-area
  allowance. Permitting a toxic or flammable pressure system in a reused oil & gas well is not costed in
  detail.
* The patented packer architecture (SI23618A, Gruber et al. 2026) is **not** the default design, and
  simulating it would not establish freedom to operate.

## 4. Inputs that are synthetic

* Case A: depth and bottom-hole temperature from the Penn State (2025) study; everything else assumed.
  The greenhouse load is a proxy, not metered.
* Case B: **all geology is synthetic**. The Mandaree open-loop doublet results are not transferable to a
  single closed-loop well.
