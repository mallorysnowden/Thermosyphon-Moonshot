"""Permafrost stabilization TEA: climate, thermosyphon heat extraction, sizing and installed cost.

Conventions follow the rest of the repo (inputs/conventions.toml):
- Real 2026 USD; CAD converted at 0.73 USD/CAD; RUB at ~80 RUB/USD (assumption).
- Customer discount rate 8% real.
- Platform hardware at NOAK = raw material x finished/raw index 2.5 (range 2-3.5), as in geowell_tea and
  icebank_tea; FOAK = index 3.5 with incumbent field productivity.

Every number is an input with a source note in cases.py. Physics is deliberately simple (steady resistances,
daily sinusoidal air temperature) because the question is cost, not ground-thermal detail.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

USD_PER_CAD = 0.73
RUB_PER_USD = 80.0

# Raw material prices, 2026 USD/kg (same basis as icebank_tea/geowell_tea)
AL_US = 5.3                # LME + US Midwest premium
HRC_US = 1375 / 907.2      # US hot-rolled coil
NH3 = 0.6
RHO_AL = 2700.0
RHO_STEEL = 7850.0


# ---------------------------------------------------------------------------------------------- climate
@dataclass(frozen=True)
class Climate:
    name: str
    maat_c: float              # mean annual air temperature today
    amp_c: float               # half the Jan-Jul range
    warming_c_per_decade: float = 0.5
    winter_share: float = 0.75  # share of warming that falls in winter (Arctic warming is winter-heavy)

    def daily_temps(self, years_ahead: float = 0.0) -> np.ndarray:
        d_maat = self.warming_c_per_decade * years_ahead / 10
        # winter warms faster than summer -> amplitude shrinks
        d_winter = 2 * self.winter_share * d_maat
        d_summer = 2 * (1 - self.winter_share) * d_maat
        maat = self.maat_c + d_maat
        amp = self.amp_c - (d_winter - d_summer) / 2
        day = np.arange(365)
        return maat + amp * np.cos(2 * np.pi * (day - 200) / 365)   # warmest ~ Jul 19

    def freezing_index(self, years_ahead: float = 0.0) -> float:
        t = self.daily_temps(years_ahead)
        return float(np.clip(-t, 0, None).sum())

    def drive_degree_days(self, t_ground_c: float, years_ahead: float = 0.0) -> float:
        """K*days that the air is colder than the ground the evaporator sits in."""
        t = self.daily_temps(years_ahead)
        return float(np.clip(t_ground_c - t, 0, None).sum())


# ------------------------------------------------------------------------------------------ thermosyphon
@dataclass(frozen=True)
class Unit:
    """One thermosyphon. Geometry drives both heat extraction and bill of materials."""
    evap_len_m: float
    cond_area_m2: float
    riser_len_m: float = 3.0
    d_out_m: float = 0.080
    layout: str = "vertical"    # vertical | inclined | thermopile | pad
    spacing_m: float = 3.0      # centre-to-centre spacing between evaporators
    pile_d_m: float = 0.273     # thermopile host pile OD (10-inch pipe)


@dataclass(frozen=True)
class Physics:
    u_cond: float = 5.0          # W/m2K on dense-fin area (icebank_tea calibration, Li et al. 2020)
    exposure: float = 0.85       # snow, wind shelter and buildings (CRREL radiation factor 0.2-1.0)
    k_frozen: float = 2.0        # W/mK frozen silt/sand
    t_ground_c: float = -2.0     # ground temperature the design holds (Dry Creek: <= -2 C at top of ice)
    pad_depth_m: float = 1.0     # distance from pad evaporators to the 0 C plane below


def ground_resistance(u: Unit, p: Physics) -> float:
    k, L = p.k_frozen, u.evap_len_m
    if u.layout == "pad":
        # row of pipes in a plane, heat drawn from a frozen half-space below
        return (math.log(u.spacing_m / (math.pi * u.d_out_m)) / (2 * math.pi * k * L)
                + p.pad_depth_m / (k * u.spacing_m * L))
    r_in = u.pile_d_m / 2 if u.layout == "thermopile" else u.d_out_m / 2
    r_bulb = max(min(u.spacing_m / 2, 2.0), r_in * 2)
    r = math.log(r_bulb / r_in) / (2 * math.pi * k * L)
    if u.layout == "thermopile":
        r += math.log(u.pile_d_m / u.d_out_m) / (2 * math.pi * 2.0 * L)   # frozen sand fill inside the pile
    return r


def unit_conductance(u: Unit, p: Physics) -> float:
    r_cond = 1.0 / (p.u_cond * u.cond_area_m2 * p.exposure)
    return 1.0 / (r_cond + ground_resistance(u, p))


def winter_extraction_kwh(u: Unit, p: Physics, c: Climate, years_ahead: float = 0.0) -> float:
    return unit_conductance(u, p) * c.drive_degree_days(p.t_ground_c, years_ahead) * 24 / 1000


# ------------------------------------------------------------------------------------------------- costs
@dataclass(frozen=True)
class Costs:
    """Delivered prices to the owner. Incumbent values are calibrated to public prices; platform values are
    bottom-up NOAK costs with a margin."""
    # --- incumbent thermosyphon hardware (steel + CO2), price to owner
    inc_hw_base: float = 1000.0          # $/unit: UNAVCO 4.5" x 20 ft thermopile monument = $1,700
    inc_hw_per_m: float = 100.0          # $/m of tube
    inc_hw_per_m2: float = 150.0         # $/m2 of radiator fin area
    # --- platform hardware (6063 Al + NH3), bottom-up
    index: float = 2.5                   # finished/raw
    al_price: float = AL_US
    wall_m: float = 0.003                # 3 mm: code wall is 2.4 mm, +corrosion/handling allowance
    fin_kg_per_m2: float = 0.474
    misc_al_kg: float = 1.5
    coat_per_m: float = 12.0             # epoxy/PEO on buried tube, $/m (assumption)
    max_factory_len_m: float = 12.0
    field_joint: float = 150.0           # orbital friction-stir joint + local charge/test
    platform_margin: float = 0.25        # entrant gross margin on its own cost
    # --- civil works
    mobilization: float = 150_000.0      # remote rig/crew mobilization per project (assumption)
    drill_vert_per_m: float = 350.0      # drilled + slurried vertical hole, rural AK (assumption)
    drill_incl_per_m: float = 350.0      # cased inclined bore; calibrated so Dry Creek prices at ~CAD 2.3M
    drill_reduction: float = 0.0         # platform improvement on drilling (0 = none)
    pile_steel_kg_per_m: float = 60.3    # 10" sch 40 pipe
    pile_index: float = 2.0              # pipe mill + coating + freight vs HRC
    pile_remote_freight: float = 1.4
    pile_set_per_m: float = 60.0         # slurry, set, cut-off
    install_vert: float = 1500.0         # $/unit set, backfill, radiator, charge check (incumbent)
    install_incl: float = 2500.0         # $/unit inclined: riser, backfill, protection (incumbent)
    install_pad_per_m: float = 40.0      # $/m evaporator laid level in pad (incumbent flat loop, assumption)
    install_reduction: float = 0.0
    # --- engineering, monitoring, O&M
    eng_fixed: float = 150_000.0
    eng_frac: float = 0.05
    eng_reduction: float = 0.0
    sensor_string: float = 6000.0        # thermistor string installed (CSA S500:21 requires monitoring)
    units_per_string: int = 10
    monitor_fixed_yr: float = 5000.0
    monitor_per_unit_yr: float = 50.0
    failure_rate: float = 0.01           # share of units replaced per year (incumbent)
    rate: float = 0.08
    life: float = 30.0


def crf(rate: float, years: float) -> float:
    g = (1 + rate) ** years
    return rate * g / (g - 1)


def npv_factor(rate: float, years: float) -> float:
    return 1 / crf(rate, years)


def platform_unit_cost(u: Unit, c: Costs) -> float:
    length = u.evap_len_m + u.riser_len_m
    tube_kg = math.pi * u.d_out_m * c.wall_m * length * RHO_AL
    al_kg = tube_kg + u.cond_area_m2 * c.fin_kg_per_m2 + c.misc_al_kg
    nh3_kg = 0.033 * u.evap_len_m
    hw = (al_kg * c.al_price + nh3_kg * NH3) * c.index + c.coat_per_m * u.evap_len_m
    joints = max(0, math.ceil(length / c.max_factory_len_m) - 1)
    return (hw + joints * c.field_joint) * (1 + c.platform_margin)


def incumbent_unit_cost(u: Unit, c: Costs) -> float:
    return c.inc_hw_base + c.inc_hw_per_m * (u.evap_len_m + u.riser_len_m) + c.inc_hw_per_m2 * u.cond_area_m2


def pile_cost_per_m(c: Costs) -> float:
    steel = c.pile_steel_kg_per_m * HRC_US * c.pile_index * c.pile_remote_freight
    return steel + c.pile_set_per_m + c.drill_vert_per_m * (1 - c.drill_reduction)


@dataclass
class Bill:
    """Itemized installed price of one option."""
    items: dict = field(default_factory=dict)
    annual: dict = field(default_factory=dict)       # recurring $/yr
    one_offs: list = field(default_factory=list)     # (year, $) future lumps
    units: int = 0
    note: str = ""

    @property
    def capex(self) -> float:
        return sum(self.items.values())

    def npv(self, rate: float, life: float) -> float:
        pv = self.capex + sum(self.annual.values()) * npv_factor(rate, life)
        pv += sum(v / (1 + rate) ** y for y, v in self.one_offs if y <= life)
        return pv

    def annualized(self, rate: float, life: float) -> float:
        return self.npv(rate, life) * crf(rate, life)


def ts_system(n_units: int, u: Unit, c: Costs, platform: bool, *, bore_m: float | None = None,
              host_pile: bool = False) -> Bill:
    """Thermosyphon system: hardware, holes, install, engineering, monitoring."""
    b = Bill(units=n_units)
    hw = platform_unit_cost(u, c) if platform else incumbent_unit_cost(u, c)
    b.items["Thermosyphon hardware"] = n_units * hw
    if u.layout == "pad":
        b.items["Lay evaporators in pad"] = n_units * u.evap_len_m * c.install_pad_per_m * (1 - c.install_reduction)
        b.items["Risers + radiators set"] = n_units * c.install_vert * (1 - c.install_reduction)
    elif host_pile:
        b.items["Insert in pile + charge"] = n_units * 0.4 * c.install_vert * (1 - c.install_reduction)
    else:
        per_m = c.drill_incl_per_m if u.layout == "inclined" else c.drill_vert_per_m
        length = bore_m if bore_m is not None else u.evap_len_m
        b.items["Drilling / bores"] = n_units * length * per_m * (1 - c.drill_reduction)
        inst = c.install_incl if u.layout == "inclined" else c.install_vert
        b.items["Install + backfill"] = n_units * inst * (1 - c.install_reduction)
    b.items["Monitoring strings"] = math.ceil(n_units / c.units_per_string) * c.sensor_string
    b.annual["Monitoring"] = c.monitor_fixed_yr + c.monitor_per_unit_yr * n_units
    b.annual["Unit replacements"] = c.failure_rate * n_units * hw
    return b


def add_engineering_and_mob(b: Bill, c: Costs, mob: bool = True) -> Bill:
    base = b.capex
    if mob:
        b.items["Mobilization"] = c.mobilization
    b.items["Engineering + design"] = (c.eng_fixed + c.eng_frac * base) * (1 - c.eng_reduction)
    return b


def size_units(heat_kwh_yr: float, u: Unit, p: Physics, clim: Climate, years_ahead: float,
               min_units: int = 1) -> tuple[int, float]:
    q = winter_extraction_kwh(u, p, clim, years_ahead)
    return max(min_units, math.ceil(heat_kwh_yr / q)), q


def platform_costs(c: Costs, foak: bool = False) -> Costs:
    """Platform field productivity targets at NOAK; FOAK = incumbent field rates and index 3.5."""
    if foak:
        return replace(c, index=3.5, failure_rate=0.01)
    return replace(c, drill_reduction=0.20, install_reduction=0.40, eng_reduction=0.40, failure_rate=0.005,
                   mobilization=c.mobilization * 0.8)
