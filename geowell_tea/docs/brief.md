# Coding-Agent Brief: Deep-Well Thermosiphon vs. Coaxial Geothermal Heat Exchanger TEA

**Prepared:** November 20, 2026  
**Status:** Implementation specification, not validated engineering design  
**Goal:** Produce a transparent, reproducible Python model comparing independently optimized **gravity thermosiphon** and **pumped coaxial deep-borehole heat-exchanger** systems in the **same existing oil/gas well**, for two low-grade-heat markets.

> **Instruction to coding agent:** Implement and test the model, rather than merely proposing code. Begin with a well-documented, runnable reduced-order model and gradually add constrained deep two-phase-flow physics. Explicitly label approximations, tests, unavailable inputs, and unvalidated extrapolations. **Do not fabricate field data, validation results, actual quotes, or a commercially qualified thermosiphon design.** Numerical results must be calculated by the code; do not copy earlier illustrative figures as model outputs. Prioritize auditability over impressive-looking results.

## 1. Decision to be supported

For two hypothetical **existing, eligible, accessible, open-hole/appropriately cased wellbores**, determine:

1. The **maximum technically feasible and sustainable geothermal heat extraction** each independently optimized downhole architecture can obtain from the *same undisturbed well and geology* over an evaluation period, subject to **explicit temperature, pressure, hydraulic, freeze, thermosiphon-flow, and depletion limits**.
2. The annual **useful heat actually delivered** to the customer, both directly (when temperatures permit) and with an optional surface electric heat pump (HP).
3. Total electricity demand and annualized cost for each, including **surface compressor, circulation pump, auxiliary controls, and thermal delivery**.
4. The **technology/economic crossover**: under what depths, well diameters, rock temperatures, thermal conductivities, working fluids, liquid-flow rates, heat-demand profiles, electric tariffs, and installation-cost differences does the thermosiphon win?
5. Whether the advantage is due to downhole thermal effectiveness, source temperatures / compressor COP, pump electricity, maintenance, or CAPEX, **not** an inconsistent comparison of dissimilar outputs.

### Crucial comparison rule

**Equal starting geothermal resource, NOT equal heat output.** Both technologies get the same initial temperature-depth profile, formation properties, well depth, allowable internal envelope, no groundwater production, and customer boundary conditions. Each technology may choose its own flow, geometry, operating temperature, and equipment capacity to **maximize its own** sustainable heat recovery. Report different outputs honestly.

The phrase **“heat available”** here means the *common, undisturbed geothermal resource and well geometry*, **not** an arbitrary fixed number of kW. Recoverable heat is an outcome of the interaction between technology and ground. Do **not** set an identical 120 kW resource cap for both. The reported 120 kW Pennsylvania number is a **different study's modeled case outcome**, not an immutable reservoir limit or measured thermosiphon capability.

**Maximum extraction is ill-posed without constraints.** A solver that assumes unlimited pumping, unlimited cooling power, arbitrarily low fluid temperature, or no rock depletion will produce physically unhelpful maxima. Provide explicit configurable engineering limits, annual load duration, and a 20-year sustainability definition. Separately report (a) constrained physical maximum, (b) maximum year-20 firm heat, (c) economically optimal operating point, and (d) actual heat sold to the customer.

---

## 2. Architectures to model

Apply each architecture to **both** cases independently:

| ID | Downhole architecture | Surface mode | Purpose |
|---|---|---|---|
| `T_DIRECT` | Sealed gravity thermosiphon: two-phase vapor up / condensate back down | Surface condenser -> heat exchanger -> hydronic load; small delivery-loop pump | Best case for essentially compressor-free useful heat |
| `T_HP` | Same downhole thermosiphon | Surface condenser -> *separate* water/source loop -> electric vapor-compression HP -> hydronic load | Controls source temperature without downhole pumped circulation |
| `T_ADAPTIVE` | Same thermosiphon | Use direct preheating and direct supply when available; add HP lift when needed; controlled bypass | Quantify value of intelligent dispatch |
| `C_DIRECT` | Pumped, closed-loop *coaxial* borehole exchanger: annular descent and insulated central return, or other flow direction if optimized | Surface heat exchanger -> hydronic load | Proper direct-heat comparator |
| `C_HP` | Same coaxial loop | Source loop -> electric vapor-compression HP -> hydronic load | Conventional deep geothermal-HP comparator |
| `C_ADAPTIVE` | Same coaxial loop | Direct preheat when feasible, HP as necessary | **Essential fair comparison to `T_ADAPTIVE`** |
| `BACKUP` | No geothermal system | Existing fuel-fired boiler or commercial HP | Customer's economic outside option; fills unmet load |

Important clarifications:

- **Both downhole concepts are closed-loop** in their baseline designs. Thermosiphon working fluid does **not** enter the greenhouse or aquaculture tanks. The surface hydronic circuit is normally separate and has its own circulation energy.
- **Conventional coaxial systems commonly have accessible surface circulation pumps, not pumps at the bottom of the well.** Avoid claiming nonexistent downhole pump-replacement savings.
- A thermosiphon coupled to a heat pump still has an electric **compressor**; only the *downhole source-fluid circulation* is passive. It may require a source-side circulation pump depending on HX layout.
- Model a **separate-circuit heat pump** first for apples-to-apples comparison. Gruber (2026) additionally explores an integrated ammonia/flash-vessel/compressor cycle; add this as an **optional advanced architecture**, not as though it were identical to a generic secondary-loop HP.
- A thermosiphon can be an effectively directional heat-transfer device; unlike a pumped coaxial loop, do not grant it bidirectional seasonal charge/discharge without engineering a distinct reversible design.
- Design everything to fit the **same available well clearance**, preserving well-barrier obligations. Deep fluid columns, hydrostatic saturation-pressure changes, vapor pressure drops and liquid pooling can make attractive idealized direct-heat predictions infeasible.

---

## 3. Case A — Western Pennsylvania greenhouse (literature-anchored resource)

**Use case:** Reuse an existing vertical/deviated-but-usable gas well near a greenhouse in western Pennsylvania. Purpose: greenhouse hydronic heating. **Hypothetical well candidate**; we do not possess a well log, completion diagram, confirmed owner or retrofit quote.

**Published anchor:** *Sustainable Well Upcycling for Greenhouse Heating: A Pennsylvania Case Study* (2025), Penn State publication record. It analyzes a **5,700 ft gas well** with **~80 °C bottom-hole temperature**, and reports a modeled **120 kW thermal capacity** supporting a **10,000 ft² greenhouse**. It describes a **closed-loop heat exchanger**. This **does not validate a thermosiphon** and must **not** be used as a universal heat cap or direct technology comparison. See [Penn State record](https://pure.psu.edu/en/publications/sustainable-well-upcycling-for-greenhouse-heating-a-pennsylvania-/).

### Case A baseline input config — labeled assumptions

| Variable | Baseline | Provenance / status |
|---|---:|---|
| Total vertical usable depth | **1,737 m** (~5,700 ft) | Published study anchor (rounded) |
| Initial undisturbed bottom-hole temperature | **80 °C** | Published study anchor |
| Initial effective temperature near ground surface | **12 °C** | **Scenario assumption**; NOT measured at the well |
| Initial temperature profile | Linear between 12 °C and 80 °C; implied gradient ~39.15 K/km | **Simplification**, not an actual temperature log |
| Formation thermal conductivity | **2.5 W/(m·K)** | **Scenario assumption** |
| Formation density / heat capacity | **2,400 kg/m³; 900 J/(kg·K)** | **Scenario assumptions** |
| Saturated formation groundwater convection | **Off in baseline**; evaluate enhancement as sensitivity | Unknown; do not presume presence |
| Usable well clear inner diameter | **0.150 m** | **Scenario assumption**; enforce a clearance-budget constraint; sensitivity **0.10–0.20 m** |
| Well length in productive rock | Optimize evaporator/insulation placement | Not automatically whole well |
| Customer load | **10,000 ft² greenhouse** | Published study context; load curve **not provided** |
| Hydronic supply / return | **45 / 35 °C** | **Scenario assumption** matching our previous Case A discussion; sensitivity 30/25, 40/30, 55/40 °C |
| Full-load-equivalent utilization | **5,000 h/y** for initial illustrative constant-load screening | **Scenario assumption**; build a separate plausible seasonal time series or accept user-supplied measured load |
| Well-to-customer pipe distance | **250 m one way** | **Scenario assumption**, sensitivity 0–1,000 m |
| Evaluation period | **20 years** | Investment horizon assumption |
| Backup | Existing gas/propane heat (configurable) | Required whenever geothermal useful heat does not meet the load |

**Do not calibrate the model until it produces 120 kW.** Instead, compare your modeled closed-loop output against the Penn State result as a *sanity check with incomplete matching inputs*, and explain differences.

### Case A demand test

1. **Resource-only test:** Max physically feasible sustained geothermal extraction in the given well, with a sufficiently large controlled heat sink (customer demand not limiting). Report at `t=0`, year 1, year 10, year 20 and time-integrated heat.
2. **Customer dispatch:** Greenhouse receives 45/35 °C water (and lower-temperature variants), has a 10,000 ft² footprint, and specified seasonal load. Model direct/HP/backup priority; cap *sales* at the load, not gross extraction.
3. **Economics:** Report `LCOH` and NPV for greenhouse heat, including backup heating costs and value of avoided gas/propane consumption. Electricity-price sweep **$0.08–$0.45/kWh**. These prices are sensitivity parameters, not actual contracted tariffs.

---

## 4. Case B — North Dakota year-round rural heat load (synthetic well)

**Use case:** A usable existing deep oil/gas well in North Dakota's Williston Basin, located near an **industrial recirculating-aquaculture facility (RAS)** or another continuous, low-temperature heat customer. A co-located purpose-built facility may be considered, but customer construction cost **must not** be buried inside geothermal-project cost or treated as pre-existing demand.

**Context, not calibration:** The *Mandaree, North Dakota* geothermal district-heating study considers repurposed wells and a large **open-loop production/injection doublet**, with roughly **4.1 MW of local demand**. It is **not** evidence that a single closed-loop thermosiphon can deliver 4.1 MW. See [Mandaree chapter](https://www.sciencedirect.com/science/article/pii/B9780323906166000178).

### Case B baseline input config — all synthetic engineering assumptions

| Variable | Baseline | Provenance / status |
|---|---:|---|
| Available usable true vertical depth | **3,000 m** | **Synthetic case**, NOT a located well |
| Initial bottom-hole temperature | **110 °C** | **Synthetic case**, NOT a measured well log |
| Initial near-surface ground temperature | **7 °C** | **Synthetic case** |
| Initial geothermal temperature profile | Linear from 7 to 110 °C (~34.3 K/km) | **Synthetic case**, replace with depth-resolved ND data when available |
| Formation conductivity | **2.5 W/(m·K)** | **Scenario assumption**, sensitivity 1.5–4.0 |
| Formation density / heat capacity | **2,400 kg/m³; 900 J/(kg·K)** | **Scenario assumptions** |
| Usable well clear diameter | **0.127 m** | **Scenario assumption**, sensitivity 0.10–0.18 m; well geometry is potentially binding |
| Groundwater recharge | Off baseline; optional sensitivity | Unknown |
| RAS tank target water temperature | **26 °C** | **Scenario assumption** |
| Heating distribution supply / return | **35 / 25 °C** | **Scenario assumption**; implies a tank HX and appropriate approach temperatures |
| Heat-load availability | High, approximately **7,000 equivalent h/y** for screening | **Scenario assumption**, model 5,000–8,000 h/y sweep |
| Customer distance | **250 m one way** | **Scenario assumption**, sensitivity 0–1,000 m |
| Heat capacity goal | **Do not force 150–500 kW.** Treat this range as an aspirational commercial scale to check. | Previous scoping hypothesis, NOT proven well output |
| Evaluation period | **20 years** | Investment horizon assumption |
| Incumbent fuel | Propane or gas, both parameterized; include HP fallback | **Unverified** at site, not a live customer tariff |

Run two customer arrangements: **(B1)** already-operating year-round heat consumer with realistic demand and **(B2)** prospective site-built aquaculture operation. For B2, quantify *incremental* customer-facility investment and offtake/offsite demand risk separately. A project cannot create arbitrarily valuable demand by assuming a free greenhouse or fish farm.

### Sensitivities critical to B

- Depth **2–4 km**; initial BHT **80–140 °C**; temperature gradients not necessarily linear.
- Real accessible casing ID, vertical/deviated/horizontal geometry, well condition, re-entry/workover requirements.
- Two-phase fluid choices and vapor pressure limits, especially at 110 °C.
- Year-round load factor, extra radiator/HX approach temperatures, and expensive delivered propane vs low-price pipeline gas.
- Field/regulatory/well abandonment liabilities and distances to customers.

**Caution:** Even if the Mandaree open-loop doublet produces megawatt-scale heat, a sealed single-well closed-loop completion has different physics and much lower or higher output depending on geology and design. Never transfer Mandaree power or economics to B without an appropriate reservoir model.

---

## 5. Essential papers and what to implement from them

**Source-provenance rule:** Distinguish **(i) user-provided full PDF**, **(ii) publicly accessible full paper**, and **(iii) abstract-only / not fully verified**. Do not conflate independently measured field performance with model-to-model reproduction or modeled commercialization economics.

### P1 — Zolfagharroshan et al. (2024) — PRIMARY fast rock/thermal-network backbone

- **Title:** *Two-phase closed thermosyphons (TPCT) for geothermal energy extraction: A computationally efficient framework*.
- **Citation:** *Applied Thermal Engineering* **248**, 123205 (2024). DOI: [10.1016/j.applthermaleng.2024.123205](https://doi.org/10.1016/j.applthermaleng.2024.123205).
- **Full PDF supplied:** `1-s2.0-S1359431124008731-main.pdf` (13 pp).
- **Relevant method:** transient **1+1D reduced-order ground conduction** (radial conduction with axial marching) coupled to a **nonlinear thermal resistance network** using Newton–Raphson. The serial thermal resistances include evaporator wall, pool/film boiling, condenser, condenser wall, and the external **helical water coil**. Includes hydrostatic pressure within the *bottom liquid pool* in its boiling treatment, but is **not** a comprehensive kilometer-long vapor/liquid momentum solver.
- **Baseline application:** **150/200/250 m** total depth, first **50 m insulated**, **pentane** working fluid, 35% modeled filling ratio, helical water coil; condenser water inlet **70 °C** and **15 L/min** for base configurations. This is a *hot Japanese geothermal site*, not our 80 °C bottom-hole Case A.
- **Published 20-year mean heat rates:** **10.69, 14.04, 15.54 kW** for 150, 200, 250 m cases, respectively. The abstract's **109.55 W/m** is a distinct reported maximum/condition and must **not** be mistaken for their 20-year average.
- **Validation:** compares ground-temperature predictions to a **500 m coaxial** field test (average temperature discrepancy reportedly **0.9%** in selected cases); heat-rate predictions for a separate **32 m flexible thermosiphon** experiment (~**2.65%** after 4 h); and a small-scale cold-storage experiment. **It did not validate a 1.7 km thermosiphon.**
- **Computational claim:** **4–14 hours** for a 20-year simulation; developed Python code mentioned, but paper's data statement is **"available on request"**, not an open code license or linked repository.
- **Warning:** Their helical-condenser water-side pumping loss can be material. **Do not** apply that coil pressure drop to a different surface plate HX, and **do not** treat it as a coaxial well-pump load. Their thermal-network abstraction is weak during startup and does not guarantee stability against flooding, dryout or long-pipe momentum effects.
- **Use for:** reusable depth-resolved rock solver, heat-flux coupling, transient depletion model, benchmark reproduction, quick parametric screening.

### P2 — Gruber et al. (2026) — DEEP thermosiphon physics and advanced architecture

- **Title:** *Super-long gravity heat pipe system for simultaneous heating and cooling in geothermal sites with non-linear temperature gradients*.
- **Citation:** *Energy* **353**, 140961 (2026). DOI: [10.1016/j.energy.2026.140961](https://doi.org/10.1016/j.energy.2026.140961).
- **Full published PDF supplied:** `1-s2.0-S0360544226010662-main.pdf` (19 pp). Also supplied: `ssrn-6021285.pdf` (earlier **preprint of the same study, NOT independent evidence**).
- **Configuration:** **1,800 m** modeled ammonia (R717) gravity heat pipe; casing inner diameter **177.8 mm**, **650 m packer**, 20% fill; site temperature profile **nonlinear/logistic and plateauing near 81 °C**. The patented **SI23618A** architecture isolates the upper well and **extracts vapor at mid-depth** using separated channels/packer, specifically to avoid parasitic heat exchange with cooler upper layers and countercurrent interference. Do **not** assume it applies automatically to a linear-gradient Pennsylvania well or is free of IP constraints.
- **Published modeled comparison:** **150 kW** conventional SLGHP vs **185 kW** packer design at **50 °C condenser condition**, i.e. +23% **against another thermosiphon**, NOT against coaxial.
- **Integrated HP:** modeled **55/30 °C** low-temperature district water and **50 kW simultaneous cooling**, **5 m³** thermal buffer, **72% assumed compressor isentropic efficiency**, 5 K HX pinch. It can route high-temperature ammonia for direct preheat or via a **flash vessel/compressor**; not equivalent to a generic separate-circuit HP.
- **Published system outcomes:** **4.22 heating COP** at peak; **6.19 120-day heating SPF** with direct preheating and recovered cooling waste heat; **485 MWh** modeled delivered heating over the evaluated 120-day season. **Do not interpret 6.19 as a standalone thermosiphon or compressor-only COP.**
- **Model validation:** authors report **1.60%** and **1.30%** mean absolute percentage errors against *prior reference field and numerical cases*, respectively; **patented packer configuration itself is numerical, not field-validated**.
- **Assumptions requiring engineering checks:** no vapor-liquid entrainment, no dryout, no operation beyond sonic/flooding limits, negligible interphase momentum exchange, upper insulated section adiabatic, steady-state HP, idealized surface HX losses, and 100% compressor mechanical efficiency. Published study's principal application simulation is **120 days**, not 20-year field validation. Property calculations use **REFPROP**.
- **Use for:** 1D two-phase **mass/momentum/energy** conservation, saturation-pressure variation, working-fluid choice, deep-well transport limit checks, insulated active length, optional packer and integrated flash-cycle modes. Implement **CoolProp** for properties as the reproducible initial substitute; verify against published saturation tables/reference values. **Do not** reproduce the proprietary patented geometry as our default commercial product.

### P3 — Chen et al. (2024) — FIELD anchors for >2 km thermosiphons

- **Title:** *Super-long gravity heat pipe geothermal space heating system: A practical case in Taiyuan, China*.
- **Citation:** *Energy* **299**, 131521 (2024). DOI: [10.1016/j.energy.2024.131521](https://doi.org/10.1016/j.energy.2024.131521).
- **Access:** public abstract; full manuscript **not supplied**.
- **Evidence:** reported **operating installation** of **2,020 m and 2,180 m** gravity heat pipes, approximately **30 m** apart, coupled to a heat pump; formation about **63 °C at 2,000 m**. Study models 120 days and projects 20 years; reported thermal-output decline **20.4%** and **6.8%** for the respective well simulations. Strong site-specific influence from **groundwater crossflow** on longer-well performance.
- **Use for:** order-of-magnitude and temperature/long-term-drift cross-checks, and a prompt to model/flag aquifer advection. **Not** a matched same-well thermosiphon/coaxial test. Do not borrow their output for a homogeneous conduction-only Case A/B.

### P4 — Ma et al. (2024) — TECHNICAL/ECONOMIC comparison benchmark, not direct greenhouse result

- **Title:** *Thermodynamic and economic performance of super-long gravity heat pipe geothermal power plant*.
- **Citation:** *Applied Thermal Engineering*, article **123115** (2024). DOI: [10.1016/j.applthermaleng.2024.123115](https://doi.org/10.1016/j.applthermaleng.2024.123115).
- **Access:** abstract/web records available; full manuscript **not supplied**.
- **Evidence:** compares SLGHP versus a single-well DHE under **common geological/reservoir conditions** for **electricity generation**; reports energy efficiency **10.92%** for SLGHP, about **1.37 times** DHE, and modeled LCOE **$0.30 vs $0.74/kWh** (one well) and **$0.18 vs $0.43/kWh** (ten wells).
- **Use for:** define economic-comparison logic and stress-test dependence on well count and thermal output. **Do not** use power-generation efficiencies or LCOE to calibrate greenhouse thermal efficiency or retrofit costs. Full DHE configuration and CAPEX assumptions remain unverified until the paper is obtained.

### P5 — Huang et al. (2021) — PUBLIC head-to-head research, much hotter/deeper resource

- **Title:** *Numerical study and economic analysis of gravity heat pipe hot dry rock geothermal system*.
- **Citation:** *CIESC Journal* **72(3)**, 1302–1313 (2021). DOI: [10.11949/0438-1157.20200639](https://doi.org/10.11949/0438-1157.20200639).
- **Access:** public English abstract and tables: [journal page](https://hgxb.cip.com.cn/EN/10.11949/0438-1157.20200639).
- **Evidence:** modeled **4,500 m hot-dry-rock** heat pipe vs single-well DHE with economic analysis. This **is** a direct numerical comparison, but the geology, power-generation objective, new drilling, and horizon differ substantially from our spent-well heating problem.
- **Use for:** high-level sanity check that head-to-head studies exist and economic results can change when drilling cost is removed. **Never** equate its turbine electricity output to kW of geothermal heat delivered to a greenhouse.

### P6 — Open coaxial reference (2025) — fast conventional comparator

- **Title:** *Rapid Open-Source-Based Simulation Approach for Coaxial Medium-Deep and Deep Borehole Heat Exchanger Systems*.
- **Citation:** *Energies* **18(18)**, 4921 (2025). DOI: [10.3390/en18184921](https://doi.org/10.3390/en18184921). [Open full text](https://www.mdpi.com/1996-1073/18/18/4921).
- **Method:** modified **pygfunction v2.3.0**, accepting circulating-fluid inlet temperature, using effective ground properties. Benchmarked against **12** numerical/field references at **700–3,000 m**.
- **Limitations:** usually **2–3 °C low** on predicted outlet temperature, corresponding to up to ~4% COP underestimation in the reported cases; larger errors with strong groundwater flow or extreme gradients. Authors caution that this fast approach **does not accurately recover the full fluid temperature profile along a deep borehole**.
- **Use for:** independent **quick coaxial benchmark** and screening sanity check. For the physics-level fair comparison, implement **depth-resolved coaxial down/up flow, pipe losses and countercurrent thermal short circuit** coupled to the **same ground solver** used by the thermosiphon. Do **not** apply a single depth-averaged formation temperature if the goal is to optimize the active section in strongly stratified rock.

### P7 — RSC (2024) — long heat-pipe field measurements (optional advanced validation)

- **Title:** *Developing kilometers-long gravity heat pipe for geothermal energy exploitation*.
- **Citation:** *Energy & Environmental Science* (2024). DOI: [10.1039/D4EE01235F](https://doi.org/10.1039/D4EE01235F). [Open paper](https://pubs.rsc.org/en/content/articlehtml/2024/ee/d4ee01235f).
- **Evidence:** describes development and field testing of kilometer-scale gravity heat pipes, with thermal extraction and temperature monitoring; reports >1 MW of heat in a suitable deep system. **Does not show that an arbitrary 80°C, 1.7 km abandoned gas well can deliver 1 MW.**
- **Use for:** assess credible operating constraints, validation targets, and realistic upper-envelope long-pipe demonstrations.

### Background papers NOT needed for MVP implementation

- Rieberer et al. 2005 CO₂ thermosiphon GSHP: establishes shallow commercial precedent; not a kilometer-scale solver.
- Lim et al. 2017 (previously misstated as 2018) heat-pipe-assisted GSHP electricity savings: useful contextual comparison, but different configurations and depths; not our principal benchmark.
- Mahfouz et al. 2026 500 m heat-pipe/heat-pump working-fluid study: relevant if later implementing integrated direct-expansion refrigerant cycles; not required for initial separate-circuit TEA.

---

## 6. Recommended computational architecture

**Decision:** Use **Zolfagharroshan-inspired reduced-order transient rock conduction** as common geothermal backbone, plus **two independently optimized downhole exchangers**. Implement **Gruber-inspired deep two-phase transport constraints** (do not assume 1,737–3,000 m behave like 200 m). Use **CoolProp instead of REFPROP** for a transparent first implementation. Reuse `pygfunction` only as a coaxial cross-check or provisional rapid surrogate, given its known deep-well depth-profile limitations.

### Modules

```text
geowell_tea/
  pyproject.toml                 # deterministic dependencies, Python >=3.11
  README.md
  configs/
    case_a_pa.yaml
    case_b_nd.yaml
    assumptions.yaml            # clearly tagged 'study' vs 'scenario'
  src/geowell_tea/
    schema.py                   # pydantic/dataclass input validation, units
    rock.py                     # shared transient r-z / 1+1D ground energy
    geology.py                  # T_undisturbed(z), layers, boundary conditions
    fluids.py                   # CoolProp wrappers; saturation, latent heat
    thermosiphon.py             # thermal network + deep two-phase checks
    coaxial.py                  # depth-dependent downflow/upflow, pressure loss
    surfaces.py                 # HX, direct bypass, load, compressor COP, pumps
    dispatch.py                 # operate at physical max vs actual load
    optimize.py                 # constrained independent T and C optimization
    finance.py                  # annual cash flows / LCOH / NPV
    validate.py                 # published benchmark reproduction
    plots.py                    # output temperature profiles, heat & economics
    cli.py                      # commands run, validate, sweep
  tests/
    test_energy_balance.py
    test_rock.py
    test_properties.py
    test_thermosiphon_limits.py
    test_coaxial_hydraulics.py
    test_surface_balance.py
    test_economics.py
    test_regressions.py
  outputs/                      # CSV + charts + scenario provenance
```

### Recommended physics

**A. Shared geology**

- Spatial coordinate `z`: **true vertical depth**, positive downward; radius `r` outward from casing. Confirm conventions in every sign-dependent equation.
- Initial undisturbed profile `T0(z)`: user-provided measured log if available; otherwise named linear/logistic **scenario** profile.
- Solve transient formation energy balance: `rho*cp*dT/dt = div(k grad T)` with temperature-dependent/layer-dependent `k, rho, cp` if data exist; optional groundwater advection extension with separate hydrogeological calibration.
- Well wall coupling: `q'(z,t) = (T_rock_wall - T_fluid_effective)/R'_interface(z,t)`; no single guessed constant temperature across deep well.
- Shared formation domain, radial/axial resolution, far-field boundaries and deployment schedule for both technologies. Do mesh/time convergence tests and avoid a far-field heat supply that silently replenishes infinite heat.
- Record `T_formation(z,t)` and integrated heat removed. Check long-run energy balance within a numerical tolerance.

**B. Thermosiphon**

- Start with Zolfagharroshan's **R1...R5 series thermal resistance** network and hydrostatic bottom liquid-pool treatment; solve root of `Q = (T_evap - T_cond)/R_eq(Q, properties, geometry)`.
- Add a **separate deep-fluid hydraulic/momentum feasibility layer** before trusting maximum extraction: `m_dot_vapor ~ Q_latent/h_fg`, vapor pressure drop, liquid return head, saturation-temperature shifts with depth, fill/hold-up, liquid pooling, countercurrent flooding, sonic limit, entrainment/dryout and allowable design pressure.
- For the deep option, adapt Gruber's 1D conservation-law treatment as needed. Solver should return `FEASIBLE`, `INFEASIBLE` (reason), or `UNVALIDATED` for unmodeled transport regimes. **Do not** take a thermosiphon's entire 1.7–3.0 km vapor column as perfectly isothermal or frictionless.
- Optimize active evaporator length, insulated sections, internal diameters, fill inventory, condenser pressure/temperature and fluid choice. Compare standard gravity pipe and separated liquid/vapor flow variants. Patented packer is optional and explicitly IP-flagged.
- Candidate fluids for **screening only**: ammonia, water, CO₂, and compatible hydrocarbons; check critical-point, freezing, pressure, volatility, corrosion, leakage, site safety and permitting. The model's best thermodynamic fluid is not automatically a viable commercial choice.

**C. Coaxial**

- Model annulus descent and insulated center-pipe ascent, with depth-resolved heat flux to rock and unwanted up/down thermal short circuit.
- Include fluid viscosity/density/Cp changes with temperature and pressure, Reynolds/friction factor, annulus hydraulic diameter, connections and surface pressure losses.
- Pump electric power `W_pump = (DeltaP * V_dot)/eta_pump` including any differential hydraulic/gravity effect of unequal-density columns. **Do not** count `rho*g*well_depth` as an unrecovered static lift in a closed loop.
- Optimize actual clearances, inner tube diameter/insulation, mass flow rate, inlet temperature and flow direction; impose surface pump capacity and maximum differential pressure.

**D. Direct heating, heat pump and dispatch**

- Common hydronic load and HX approach constraints. Only deliver useful direct heat when source-side temperature is **above** the required load temperature by an achievable HX approach. Otherwise use compressor or backup.
- With HP: `Q_sink = Q_source + W_compressor`; define whether compressor power includes motor losses; `COP_heat = Q_sink/W_comp`, and `SPF_system = delivered useful heat / (compressor + downhole pump + condenser/primary pump + delivery pump + controls)`.
- Model `COP(T_source,T_sink,part_load)` via transparent Carnot-efficiency approximation for MVP, then optionally replace with manufacturer performance maps. Report compressor lift and operating envelope.
- Track each load segment: direct geothermal, geothermal to HP evaporator, compressor electricity added, backup heat, curtailed heat, hydronic losses, and net heat delivered to customer. Avoid double-counting direct preheat plus heat-pump output.
- `T_ADAPTIVE` must be compared against `C_ADAPTIVE` with equivalent controls and customer demand.

**E. Sustainability, operational optimization, and TEA**

- Report **instantaneous initial** maximum, **year-1**, **year-10**, **year-20** design-day maximum, **20-year cumulative extraction**, annual output, decline, and peak vs average.
- Define provisional sustainability criterion (modifiable planning rule): **year-20 sustainable annual geothermal extraction >= 80% of year-3 extraction** at the selected operating schedule, with no in-well safety violations. This **80% is our own screening criterion, NOT a published standard**. Also report results without this constraint.
- Two optimizer modes: **resource maximum** (large capable heat sink, within equipment/ground constraints) and **economic optimum** (actual contracted demand, tariffs, installed cost, equipment sizes).
- For fair same-well comparison, never normalize to a fixed requested kW and then call the higher-output system inefficient. For accounting, also report **electric MWh per delivered thermal MWh**, **recovered geothermal MWh per well**, **unmet demand** and **20-year customer heating costs**.

---

## 7. Financial model and TEA math

Use **real 2026 USD** by default. Base model lifetime **20 years**, real discount rate **10%** as a planning assumption; sweep **6–15%**. Include investment time, commissioning, equipment replacement, depreciation/tax **only if explicitly modeled** (else report pre-tax unlevered NPV), and project end-of-life well handling.

**CAPEX categories:** well and logging acquisition; ownership and permits; mechanical integrity test; workover/cleanout; existing casing rehabilitation; central pipe/downhole steel; proprietary TPCT internals; insulation/packers; thermosiphon pressure equipment and charging; coaxial circulation pump; surface condenser/HXs; optional heat pump; electrical; interconnection and distribution to customer; instrumentation; commissioning; contingency. Separate **common** vs **architecture-dependent** costs, and avoid treating sunk *original drilling* costs as new CAPEX if existing borehole is suitable; nonetheless include remaining well liabilities/abandonment reserves.

**OPEX:** compressor electricity, downhole source-loop circulation (coax only), surface/greenhouse delivery pumps (both), auxiliary controls, repairs and replacements, routine monitoring, insurance, maintenance, working-fluid leakage/remediation allowance, well integrity inspection, backup-fuel spend, optional carbon price, taxes (if in scope).

For each design `d`, compute at least:

```text
Q_geo_d(t)           = actual geothermal heat removed from rock [kW]
Q_useful_d(t)        = heat supplied at customer-required temperature [kW]
E_electric_d(y)      = sum of ALL operating electricity [kWh/y]
E_backup_d(y)        = backup useful thermal energy [MWh/y]
E_geo_d(y)           = integrated Q_geo_d [MWh/y]
E_delivered_d(y)     = integrated useful customer heat [MWh/y]

LCOH_d = PV(all relevant project costs incl replacements and residuals)
         / PV(useful customer MWh from the specific geothermal system)

NPV_d = -initial_CAPEX + PV(heat sales and any contracted benefits
                         - OPEX - replacements - liabilities)

Break-even offered heat price: price such that NPV_d = 0.
```

**Denominator caution:** If boiler backup supplies unmet customer demand, do not claim its heat in the geothermal system's LCOH without also including its costs and labeling the metric as **blended whole-site heat LCOH**. Report both *geothermal-only* and *complete-site* costs. **Do not equate `$ avoided gas bill` with `$ contract revenue`** without an explicit pricing/offtake assumption.

**Core sensitivity matrix** (run for A and B as feasible): power price $0.08/0.15/0.25/0.40 per kWh; competing useful heat price $25/50/80/120 per MWh; well workover/installation CAPEX with ±50%; rock `k=1.5/2.5/4 W/mK`; bottom-hole temperature ±15°C; casing ID 0.10/0.127/0.15/0.18 m; customer distance 0/250/1000 m; 20-year geothermal decline; surface exchanger approach 3/5/10K; source circulation pump curves; ground recharge; annual utilization 3,000/5,000/7,000/8,000 hours. Clearly mark infeasible combinations.

Required charts:

1. Heat extraction and source temperature vs time for each design, with year-20 decline.
2. Depth-resolved initial/final rock and fluid temperatures; active evaporator heat flux.
3. Max sustainable geothermal kW, delivered useful kW, electric kW, COP/SPF by configuration.
4. NPV/LCOH tornado and electricity-price crossover graphs.
5. Thermosiphon-vs-coaxial **win region** (well depth × bottom-hole temperature, color by cost/thermal advantage), each under the **same** common resource constraints.
6. Assumption/data-quality report highlighting unmeasured or synthetic parameters and results dependent on them.

---

## 8. Validation and acceptance criteria

**Do not proceed directly to Case A/B conclusions before regression tests pass.**

### Published reproduction benchmarks

- [ ] **Zolfagharroshan**: reproduce 150/200/250 m *20-year mean* outputs approximately **10.69 / 14.04 / 15.54 kW** using *their* geology/geometry/flow/surface temperatures, **not** Case A's geology. Initial target ±10% with documented causes; improve toward ±5%. Also verify parameter trends and 20-year shape.
- [ ] Reproduce the paper's **32 m thermosiphon** published test trend/heat rate where sufficient underlying data can be extracted; mark as not fully reproducible if field series are unavailable. Distinguish authors' own ~2.65% fit from our achieved error.
- [ ] **Gruber**: optional deeper model benchmark of **150 vs 185 kW at a 50°C condenser condition**, only after implementing their **nonlinear** site gradient and defined packer/insulation; expected different outcome in Case A's **linear** geology. Report limitations of predicting their patented configuration.
- [ ] **Coaxial**: compare to accessible 2025 `pygfunction` reference and at least one reported 500–3000m coaxial case; don't treat 0.9% paper-reported ground-profile error as our own.
- [ ] **Deep thermosiphon**: cross-check order of magnitude, temperature ranges and any obtainable timeseries against **Chen 2024** and **RSC 2024** field measurements; both are different wells, not gold-standard same-well calibration.

### Engineering invariants (automatic tests)

- [ ] All energies conserved within a stated finite-difference / HX tolerance: formation heat loss = heat extracted ± numerical/residual/storage terms, and `Q_heatpump_delivered = Q_source + W_comp` (accounting for losses if included).
- [ ] Pump pressure work uses flow in m³/s and pressure in Pa; closed-loop static head not double-counted.
- [ ] All temperature differences and COP Carnot calculations use kelvin correctly.
- [ ] Zero pump/HP demand in off mode except explicitly modeled standby; source cannot deliver heat to hotter load without lift.
- [ ] Increasing extraction lowers adjacent ground temperature over time absent replenishment; rock response converges under mesh/time refinement.
- [ ] Working-fluid states remain inside thermodynamic property validity and equipment pressure ranges. Solver **fails loudly**, instead of returning extraordinary unrealistic outputs, when an unmodeled two-phase regime is encountered.
- [ ] Identical geological initial conditions and physical casing diameter for T and C in each test.
- [ ] No direct heating when source is too cold. No infinite COP or negative compressor power.
- [ ] Stage-specific model limitations and missing data appear in the exported result, not only the source comments.

### Deliverables from coding agent

1. A runnable, dependency-pinned Python repository with CLI commands, e.g. `python -m geowell_tea.cli validate`, `... run configs/case_a_pa.yaml`, `... sweep configs/case_b_nd.yaml` (actual command names documented and tested).
2. Clearly tagged `YAML` configuration files for both cases; **every parameter labeled `published`, `assumed`, `derived`, or `measured`**, with sources where applicable.
3. Independent `thermosiphon` and `coaxial` modules using the **same rock module**; optional advanced packer module.
4. Reproduction report showing actual validation errors and what could not be reproduced.
5. Two TEA reports with independently optimized geothermal recovery, electric use, useful heat and economics, along with figures and CSV/Parquet outputs.
6. Machine-readable summary with units, convergence/feasibility flags, and model version/hash.
7. `MODEL_LIMITATIONS.md` listing lack of deep field calibration, assumed well integrity, possible hydrothermal/advection effects, fluid-safety concerns, and speculative costs.

**MVP success is not a claim that thermosiphons win.** MVP success is a defensible answer as to **where they win, lose, or cannot yet be evaluated**, with documented physical and economic sensitivities.

---

## 9. Implementation sequence (recommended)

**Milestone 0 — Provenance and benchmark extraction.** Check uploaded PDFs and source web pages. Build unit/parameter registry, preserve all paper figures and input details, identify missing boundary conditions. Request original Zolfagharroshan Python code/data if useful, but do not depend on it or assume permission to redistribute it.

**Milestone 1 — Shared transient formation + simplified exchange.** Implement rock domain and a baseline fixed-temperature wall/HX boundary. Demonstrate convergence and annual energy balance.

**Milestone 2 — Coaxial and initial thermosiphon modules.** Implement coaxial fluid/hydraulics and Zolfagharroshan-style TPCT thermal network. Reproduce available model benchmarks.

**Milestone 3 — Deep thermosiphon hydraulic restrictions.** Add pressure saturation head, vapor momentum/friction, return-channel head, flooding/dryout/sonic screening, and depth-dependent active region. Use Gruber as a methodological reference; note model extrapolation explicitly.

**Milestone 4 — Surface HP, demand and dispatch.** Calculate output at independently optimized temperature/flow conditions. Surface electricity and controls are comparable, and all configurations have the same customer delivery temperature requirement.

**Milestone 5 — Economic optimization / uncertainty.** Add project cash flow, sweep case A/B, generate crossover charts and uncertainty bounds; flag when a model conclusion is controlled by unknown oilwell or customer data.

**Milestone 6 — Recommendation.** Produce concise answer: estimated economically favorable domain for each technology, most important measurement to improve confidence, and next experiment or field test.

---

## 10. Interpretation cautions for the coding agent

1. **No equal delivered heat constraint.** Equal resource and safety envelope; output is a result.
2. **Do not label thermal transport as HP efficiency.** Report `Q_geo`, `Q_useful`, `W_elec`, COP, SPF and exergy separately.
3. **Prior illustrative 17 kW thermosiphon and 134 kW coaxial figures were not validated results.** Do **not** treat them as reproduction targets; the uniform-depth-temperature idealization was not adequate for a deep thermosiphon.
4. **120 kW Penn State number is for a different closed-loop design**, not a thermosiphon maximum.
5. **Gruber +23% is thermosiphon vs thermosiphon**, not thermosiphon vs coaxial.
6. **Gruber 6.19 SPF includes favorable system integration**, not just downhole pipe and compressor performance.
7. **Zolfagharroshan's 500 m coaxial field comparison validates part of its temperature-response framework**, not a 500 m two-phase thermosiphon.
8. **Mandaree megawatt-scale feasibility relies on a production/injection doublet**, not a passive single-well thermosiphon.
9. **Electricity-price savings are only decisive for auxiliary power actually avoided.** Surface HP compressors are still required when source temperature is too low; compare both technologies at their actual optimized source temperatures.
10. **Existing oil/gas well reuse is not free.** Casing integrity, re-entry, isolation barriers, workover, permitting, leakage liability and plugging obligations can dominate TEA results.
11. This is a **commercial feasibility codebase**, not an as-built well completion design; run all pressure-system/working-fluid choices through qualified engineering and regulations before field deployment.

## 11. Source index, access and ownership

| Reference | URL | Availability / use |
|---|---|---|
| Zolfagharroshan et al. (2024) | https://doi.org/10.1016/j.applthermaleng.2024.123205 | **Uploaded complete PDF**: `1-s2.0-S1359431124008731-main.pdf`; primary rapid model |
| Gruber et al. (2026) | https://doi.org/10.1016/j.energy.2026.140961 | **Uploaded complete published PDF**: `1-s2.0-S0360544226010662-main.pdf`; deep 2-phase physics |
| Gruber preprint | https://ssrn.com/abstract=6021285 | **Uploaded**: `ssrn-6021285.pdf`; duplicate earlier version, not independent validation |
| Chen et al. (2024) | https://doi.org/10.1016/j.energy.2024.131521 | Public abstract; deep field evidence |
| Ma et al. (2024) | https://doi.org/10.1016/j.applthermaleng.2024.123115 | Public abstract; head-to-head but power-generation economics |
| Huang et al. (2021) | https://hgxb.cip.com.cn/EN/10.11949/0438-1157.20200639 | Public comparison and economic table |
| Coaxial `pygfunction` (2025) | https://doi.org/10.3390/en18184921 | Open full text; coaxial screening comparison |
| RSC long heat pipe (2024) | https://doi.org/10.1039/D4EE01235F | Open full text; deep field evidence |
| Penn State Case A (2025) | https://pure.psu.edu/en/publications/sustainable-well-upcycling-for-greenhouse-heating-a-pennsylvania-/ | Public abstract; Case A case anchor |
| Mandaree ND study | https://www.sciencedirect.com/science/article/pii/B9780323906166000178 | Public abstract; **open-loop doublet**, B market context only |
| CoolProp | https://coolprop.org/ | Public fluid-property library; use with range checks |
| pygfunction | https://github.com/MassimoCimmino/pygfunction | Open-source geothermal ground/BHE modeling |
| OpenGeoSys | https://www.opengeosys.org/ | Higher-fidelity groundwater/rock modeling, optional |
| TESPy | https://github.com/oemof/tespy | Surface-cycle modeling, optional |
| GEOPHIRES-X | https://github.com/NatLabRockies/GEOPHIRES-X | TEA framework, optional integration |

**Developer note on attribution and IP:** Published equations and scientific descriptions can inform an independently implemented simulator; do not copy repository code without reviewing its license. The Gruber paper describes **patent SI23618A**. Simulating that configuration does not establish freedom to operate commercially. No uploaded paper establishes a validated, general-purpose open-source kilometer-scale thermosiphon code release.
