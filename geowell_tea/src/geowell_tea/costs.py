"""Cost model and lifetime economics (real 2026 USD, pre-tax, unlevered).

Every number here is a *parameter*, loaded from ``configs/assumptions.yaml``
with base/low/high and a provenance tag.  No value is a vendor quote.  The
functions accept either floats (base case) or numpy arrays (Monte Carlo draws)
and broadcast.

LCOH (geothermal-only) = PV(all project costs incl. replacements and end-of-life)
                         / PV(useful heat delivered by the geothermal system)
Site-blended cost      = (PV(project costs) + PV(backup heat cost)) / PV(total customer load)
NPV                    = -CAPEX + PV(heat_price * useful heat - OPEX - replacements) - PV(end-of-life)
"""
from __future__ import annotations

import numpy as np

SAFETY_SYSTEM_KEY = {"ammonia": "ts_safety_ammonia", "propane": "ts_safety_hydrocarbon",
                     "isobutane": "ts_safety_hydrocarbon", "pentane": "ts_safety_hydrocarbon",
                     "water": "ts_safety_water", "co2": "ts_safety_co2"}


def capex_breakdown(arch_id: str, q: dict, p: dict) -> dict:
    """CAPEX items [$].  ``q`` = SimResult.quantities, ``p`` = parameter dict."""
    tech = "TS" if arch_id.startswith("T_") else "C"
    mode = arch_id.split("_", 1)[1]
    depth = q["depth_m"]
    size = p["equipment_size_factor"]
    peak_geo_kW = size * q["peak_geo_W"] / 1e3
    peak_useful_kW = size * q["peak_useful_W"] / 1e3
    peak_pump_kW = size * q["peak_pump_W"] / 1e3
    items = {}
    # ---- common to both architectures (well reuse, permits, surface, distribution) ----
    items["well_acquisition_legal"] = p["well_acquisition_legal"]
    items["permits_engineering"] = p["permits_engineering"]
    items["mit_logging"] = p["mit_logging"]
    items["cleanout_workover"] = p["rig_spread_per_day"] * (p["cleanout_days_base"] + p["cleanout_days_per_km"] * depth / 1000)
    items["surface_plant"] = p["surface_plant_base"]
    items["distribution_pipe"] = p["distribution_trench_per_m"] * q.get("distance_m", 250.0)
    items["instrumentation_controls"] = p["instrumentation_controls"]
    hp_modes = mode in ("HP", "ADAPTIVE")
    items["heat_pump"] = p["hp_per_kw"] * peak_useful_kW if hp_modes else 0.0 * peak_useful_kW
    common = sum(items.values())
    arch = {}
    if tech == "C":
        arch["vit_centre_string"] = p["vit_per_m"] * depth * (p["composite_tube_factor"] if q.get("composite", False) else 1.0)
        arch["string_running"] = p["rig_spread_per_day"] * depth / p["coax_run_m_per_day"]
        arch["circulation_pump"] = p["circ_pump_base"] + p["circ_pump_per_kw"] * peak_pump_kW
        arch["surface_hx"] = p["hx_per_kw"] * peak_geo_kW if mode in ("DIRECT", "ADAPTIVE") else 0.0 * peak_geo_kW
        mult = p["coax_capex_mult"]
    else:
        ins = q["insulated_m"]
        bare = depth - ins
        arch["pressure_string"] = (p["ts_string_per_m_base"] + p["steel_per_kg"] * q["steel_kg"] / depth) * bare
        arch["insulated_string"] = p["vit_per_m"] * ins
        arch["condensate_guide"] = p["guide_line_per_m"] * depth if q.get("guided") else 0.0
        arch["internals"] = p["ts_internals_per_m"] * depth
        arch["string_running"] = p["rig_spread_per_day"] * depth / p["ts_run_m_per_day"]
        arch["pressure_test_charge"] = p["ts_pressure_test_charge"] + p["ts_fluid_per_kg"] * q.get("inventory_kg", 0.0)
        arch["condenser"] = p["condenser_base"] + p["condenser_per_kw"] * peak_geo_kW
        arch["safety_system"] = p[SAFETY_SYSTEM_KEY.get(q.get("fluid", "ammonia"), "ts_safety_ammonia")]
        arch["psm_rmp_program"] = p["psm_rmp_capex"] if q.get("inventory_kg", 0.0) > 4536 else 0.0
        arch["secondary_loop"] = p["secondary_loop_cost"] if hp_modes else 0.0
        arch["preheat_hx"] = p["hx_per_kw"] * peak_geo_kW if mode == "ADAPTIVE" else 0.0 * peak_geo_kW
        packer = bool(q.get("packer", False))
        arch["packer_hardware"] = p["ts_packer_hardware"] if packer else 0.0
        arch["ip_license"] = p["ts_ip_license_per_kw"] * peak_geo_kW if packer else 0.0 * peak_geo_kW
        mult = p["ts_capex_mult"]
    arch = {k: v * mult for k, v in arch.items()}
    items.update(arch)
    subtotal = common + sum(arch.values())
    items["contingency"] = p["contingency"] * subtotal
    return items


def annual_opex(arch_id: str, q: dict, p: dict, E_elec_MWh, capex_items: dict):
    """Annual operating cost [$/yr] (array over years, broadcast with params)."""
    tech = "TS" if arch_id.startswith("T_") else "C"
    fixed = p["om_common_per_yr"]
    fixed = fixed + p["hp_om_frac"] * capex_items.get("heat_pump", 0.0)
    if tech == "C":
        fixed = fixed + p["coax_om_per_yr"]
    else:
        fixed = fixed + p["ts_om_per_yr"] + p["ts_leak_allowance_per_yr"]
        if q.get("inventory_kg", 0.0) > 4536:
            fixed = fixed + p["psm_rmp_per_yr"]
    elec = np.asarray(E_elec_MWh)[None, :] * 1000.0 * np.atleast_1d(p["electricity_price"])[:, None]
    return np.atleast_1d(fixed)[:, None] + elec


def replacements(arch_id: str, capex_items: dict, p: dict, years: int):
    """Replacement cash flows [$] by year (array years)."""
    out = np.zeros((np.atleast_1d(p["discount_rate"]).size, years))
    hp = np.atleast_1d(capex_items.get("heat_pump", 0.0))
    yr = int(p["hp_replacement_year"]) if np.isscalar(p["hp_replacement_year"]) else 15
    if yr <= years:
        out[:, yr - 1] += hp * p["hp_replacement_fraction"]
    if arch_id.startswith("C_"):
        pump = np.atleast_1d(capex_items.get("circulation_pump", 0.0))
        out[:, 9] += pump * 0.5
    return out


def economics(arch_id: str, q: dict, annual: dict, p: dict) -> dict:
    """Lifetime economics.  ``annual`` has arrays (MWh/yr): useful, elec, backup, load."""
    years = len(annual["useful"])
    r = np.atleast_1d(p["discount_rate"])
    t = np.arange(1, years + 1)
    v = 1.0 / (1.0 + r[:, None]) ** t[None, :]
    items = capex_breakdown(arch_id, q, p)
    capex = sum(np.atleast_1d(x) for x in items.values())
    opex = annual_opex(arch_id, q, p, annual["elec"], items)
    repl = replacements(arch_id, items, p, years)
    eol = np.atleast_1d(p["plugging_eol"])
    pv_cost = capex + np.sum((opex + repl) * v, axis=1) + eol * v[:, -1]
    pv_useful = np.sum(np.asarray(annual["useful"])[None, :] * v, axis=1)
    lcoh = np.where(pv_useful > 0, pv_cost / np.maximum(pv_useful, 1e-9), np.inf)
    heat_price = np.atleast_1d(p["heat_price"])
    pv_rev = np.sum(np.asarray(annual["useful"])[None, :] * 1.0 * heat_price[:, None] * v, axis=1)
    npv = pv_rev - pv_cost
    backup_price = np.atleast_1d(p["incumbent_useful_cost"])
    pv_backup = np.sum(np.asarray(annual["backup"])[None, :] * backup_price[:, None] * v, axis=1)
    pv_load = np.sum(np.asarray(annual["load"])[None, :] * v, axis=1)
    site = np.where(pv_load > 0, (pv_cost + pv_backup) / np.maximum(pv_load, 1e-9), np.nan)
    pv_incumbent_only = np.sum(np.asarray(annual["load"])[None, :] * backup_price[:, None] * v, axis=1)
    be_price = pv_cost / np.maximum(pv_useful, 1e-9)  # NPV=0 heat price (= LCOH by construction)
    out = dict(capex=capex, pv_cost=pv_cost, pv_useful_MWh=pv_useful, lcoh=lcoh, npv=npv,
               site_cost_per_MWh=site, incumbent_only_cost_per_MWh=np.where(pv_load > 0, pv_incumbent_only / np.maximum(pv_load, 1e-9), np.nan),
               breakeven_heat_price=be_price, opex_y1=opex[:, 0])
    if r.size == 1:
        out = {k: float(np.asarray(v_).ravel()[0]) for k, v_ in out.items()}
        out["capex_items"] = {k: float(np.asarray(x).ravel()[0]) for k, x in items.items()}
    return out
