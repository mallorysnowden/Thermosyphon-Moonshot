"""Cold bank vs business-as-usual (BAU) trim cooling for one data center.

Per 1 MW of IT load. Dry coolers are common to every case and left out, so the
costs below are only the trim-cooling system that handles hot days.

Configurations
--------------
BAU      Trim chillers sized for peak x redundancy, plus the power capacity
         to run them at peak, plus their electricity.
HYBRID   Keep the full BAU chiller plant (and its power capacity) as backup,
         and add a cold bank that carries the trim energy. Higher capex,
         lower opex.
REPLACE  No chillers. The cold bank is sized for peak x redundancy and carries
         all trim cooling. Only pump power is needed.

The cold bank's size is the larger of what the trim energy needs and what the
peak rate needs.

All costs are annualized ($/yr per MW of IT) at the customer's discount rate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .finance import crf


@dataclass
class Config:
    name: str
    capex: float  # $ per MW of IT
    annualized_capex: float  # $/yr
    om: float  # $/yr
    electricity: float  # $/yr
    thermosiphons: float = 0.0

    @property
    def opex(self) -> float:
        return self.om + self.electricity

    @property
    def annual_cost(self) -> float:
        return self.annualized_capex + self.opex


@dataclass
class Comparison:
    peak_kw_th: float
    trim_mwh_th: float
    bau: Config
    hybrid: Config
    replace: Config
    units_energy_limited: float
    units_peak_limited: float
    freed_peak_kw_e: float
    capacity_upside: float  # $/yr of lease revenue if freed power hosts more IT

    def saving(self, cfg: Config) -> float:
        return 1 - cfg.annual_cost / self.bau.annual_cost

    @property
    def cost_per_mwh(self) -> dict[str, float]:
        return {c.name: c.annual_cost / self.trim_mwh_th for c in (self.bau, self.hybrid, self.replace)}


def _cold_bank(v, peak_kw: float, energy_mwh: float, redundancy: float):
    deliverable = v["cold_bank.mwh_stored_per_unit"] * v["cold_bank.extraction_efficiency"]
    by_energy = energy_mwh / deliverable
    by_peak = peak_kw * redundancy / v["cold_bank.peak_kw_per_unit"]
    units = math.ceil(max(by_energy, by_peak))
    loop_capex = peak_kw * redundancy * v["cold_bank.loop_capex"]
    capex = units * v["cold_bank.unit_cost"] + loop_capex
    return units, capex, loop_capex, by_energy, by_peak


def compare(v) -> Comparison:
    peak = v["load.trim_share"] * 1000  # kW_th per MW of IT
    energy = v["load.trim_share"] * v["load.trim_hours"]  # MWh_th per MW of IT
    red = v["load.redundancy"]
    r = v["finance.discount_rate"]
    crf_eq = crf(r, v["finance.equipment_life"])
    crf_ts = crf(r, v["finance.thermosiphon_life"])
    price = v["power.electricity_price"]
    cop = v["chiller.cop"]

    # BAU
    chiller_capex = peak * red * v["chiller.capex"]
    power_capex = peak / cop * v["power.capacity_capex"]
    bau = Config(
        "BAU chillers",
        capex=chiller_capex + power_capex,
        annualized_capex=(chiller_capex + power_capex) * crf_eq,
        om=chiller_capex * v["chiller.om_share"],
        electricity=energy / cop * price,
    )

    pump_kw = peak * v["cold_bank.pump_energy"]  # kW_e at peak
    pump_power_capex = pump_kw * v["power.capacity_capex"]
    pump_elec = energy * v["cold_bank.pump_energy"] * price

    # HYBRID: full BAU plant kept as backup, cold bank sized for energy and peak (no redundancy)
    units_h, bank_capex_h, loop_h, _, _ = _cold_bank(v, peak, energy, 1.0)
    hybrid = Config(
        "Hybrid (chillers kept as backup)",
        capex=bau.capex + bank_capex_h,
        annualized_capex=bau.annualized_capex + bank_capex_h * crf_ts,
        om=bau.om + loop_h * v["cold_bank.om_share"],
        electricity=pump_elec,
        thermosiphons=units_h,
    )

    # REPLACE: no chillers; cold bank carries redundancy
    units_r, bank_capex_r, loop_r, by_energy, by_peak = _cold_bank(v, peak, energy, red)
    replace = Config(
        "Replace (no chillers)",
        capex=bank_capex_r + pump_power_capex,
        annualized_capex=bank_capex_r * crf_ts + pump_power_capex * crf_eq,
        om=loop_r * v["cold_bank.om_share"],
        electricity=pump_elec,
        thermosiphons=units_r,
    )

    freed = peak / cop - pump_kw
    upside = freed * v["upside.lease_rate"] * 12
    return Comparison(peak, energy, bau, hybrid, replace, by_energy, by_peak, freed, upside)


def breakeven_unit_cost(v) -> float:
    """Installed cost per thermosiphon at which REPLACE costs the same as BAU."""
    lo, hi = 0.0, 200_000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        c = compare({**v, "cold_bank.unit_cost": mid})
        if c.replace.annual_cost < c.bau.annual_cost:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
