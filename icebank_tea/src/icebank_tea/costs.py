"""Costs: thermosiphon bill of materials (raw material x index), pit, plant, finance.

NOAK philosophy matches geowell_tea: NOAK hardware = raw-material cost x a
finished-to-raw index (base 2.5, range 2-3.5), plus installation priced
bottom-up. FOAK = index 3.5, manual installation, and pricier civil works.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .store import Design

# Raw material prices, 2026 USD/kg
AL_US = 5.3        # LME cash + US Midwest premium (~$1.10/lb, Sep 2026, S&P Global Platts)
AL_WORLD = 2.85    # LME-level price, no US tariff premium (sensitivity)
HRC_US = 1375 / 907.2  # US hot-rolled coil, ~$1,375/short ton mid-Nov 2026 (same basis as geowell_tea)
NH3 = 0.6          # anhydrous ammonia
RHO_AL = 2700.0


@dataclass(frozen=True)
class CostInputs:
    index: float = 2.5                 # finished / raw-material cost
    al_price: float = AL_US
    design_pressure_mpa: float = 2.6   # ammonia saturation at ~60 degC (sun-heated condenser in summer)
    allowable_mpa: float = 43.0        # welded 6000-series aluminium, code-level allowable (approx.)
    min_wall_m: float = 0.0015
    fin_kg_per_m2: float = 0.474       # 1100 fins 0.35 mm, from Li et al. 2020 geometry
    misc_al_kg: float = 1.0            # caps, fill port, return insert
    nh3_kg_per_m_evap: float = 0.033   # ~0.3 kg for a 9 m evaporator
    condenser_len_m: float = 3.0
    rack_steel_kg: float = 4.0         # galvanised rack share per unit
    install_per_unit: float = 8000 / 16 / 36 + 200 / 36  # crane crew $8k/day, 16 racks/day of 36, $200/rack QA
    max_factory_len_m: float = 12.0    # longest unit that ships sealed in a 40 ft container
    field_joint_usd: float = 150.0     # longer units: one orbital friction-stir joint + on-site charge and test (assumption)
    pit_mult: float = 1.0
    pit_ice_premium: float = 1.2       # cover anchoring and tube-rack structure for ice
    discharge_usd_kw: float = 40.0     # plate HX, pumps, piping, controls per kWth (x1.2 for N+1 pumps)
    icebank_om_frac: float = 0.01
    mech_om_frac: float = 0.025
    pump_cop: float = 40.0             # kWth delivered per kWe of pumping
    elec_service_usd_kwe: float = 600.0  # electrical service + generators per kW of peak draw (chillers and pumps)
    # Cooling-tower / evaporative-condenser water (only where the BAU plant rejects heat that way)
    evap_m3_per_mwh_rej: float = 1.6   # ~1.8 gal evaporated per ton-hour of cooling (EPA WaterSense) at COP ~4.7
    cycles_of_conc: float = 4.0        # blowdown = evaporation / (cycles - 1)
    tower_chem_usd_m3: float = 0.15    # water treatment chemicals per m3 of makeup (assumption)
    water_price_mult: float = 1.0      # sensitivity knob on water + sewer prices
    # Night / shoulder-season dry-cooler recharge of the store (sensible, liquid water only)
    dc_usd_kw: float = 70.0            # dry cooler + piping per kW at a 10 K ITD (BAU economiser uses $60/kW)
    dc_cop: float = 40.0               # kW heat moved per kW of fans + pumps at full capacity
    # Smart off-peak charging of the store by the 30% backup chiller (used only where it lowers cost)
    charge_coil_usd_kw: float = 30.0   # ice-on-coil / brine loop in the pit per kW of charging capacity (assumption)
    ice_cop_factor: float = 0.7        # chiller COP and capacity when making ice vs chilled water
    chiller_charging: bool = True
    rate: float = 0.08                 # repo convention: customer discount rate (inputs/conventions.toml)
    life_icebank: float = 25.0
    life_mech: float = 20.0
    construction_lag_years: float = 1.0  # the pit needs one winter before its first summer


FOAK = dict(index=3.5, install_per_unit=250.0, pit_mult=1.3, discharge_usd_kw=60.0)


def crf(rate: float, years: float) -> float:
    if rate == 0:
        return 1.0 / years
    g = (1 + rate) ** years
    return rate * g / (g - 1)


def wall_m(d: Design, c: CostInputs) -> float:
    return max(c.design_pressure_mpa * 2 * d.r_out_m / (2 * c.allowable_mpa), c.min_wall_m)


def unit_bom(d: Design, c: CostInputs) -> dict:
    """Bill of materials and NOAK cost of one installed thermosiphon."""
    length = d.evap_len_m + c.condenser_len_m
    t = wall_m(d, c)
    tube_kg = math.pi * 2 * d.r_out_m * t * length * RHO_AL
    fin_kg = d.cond_area_m2 * c.fin_kg_per_m2
    al_kg = tube_kg + fin_kg + c.misc_al_kg
    nh3_kg = c.nh3_kg_per_m_evap * d.evap_len_m
    raw = al_kg * c.al_price + nh3_kg * NH3
    rack = c.rack_steel_kg * HRC_US * c.index
    hardware = raw * c.index
    joint = c.field_joint_usd if length > c.max_factory_len_m + 1e-9 else 0.0
    return dict(length_m=length, wall_mm=t * 1e3, tube_kg=tube_kg, fin_kg=fin_kg, al_kg=al_kg, nh3_kg=nh3_kg,
                raw_usd=raw, hardware_usd=hardware, rack_usd=rack, install_usd=c.install_per_unit,
                field_joint_usd=joint, unit_usd=hardware + rack + c.install_per_unit + joint)


def pit_usd_per_m3(volume_m3: float, c: CostInputs) -> float:
    """Danish pit-storage power law (EUR 2015/m3 = 2240 V^-0.37; Marstal, Dronninglund, Vojens, Gram,
    Toftlund), x1.08 USD/EUR, x1.35 escalation to 2026 (assumption), x ice premium."""
    return 2240.0 * max(volume_m3, 1000.0) ** -0.37 * 1.08 * 1.35 * c.pit_ice_premium * c.pit_mult


def with_foak(c: CostInputs) -> CostInputs:
    return replace(c, **FOAK)
