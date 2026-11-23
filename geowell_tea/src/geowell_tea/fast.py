"""Fast single-configuration thermosiphon calculator (backs the Streamlit UI).

The user fixes the configuration and the condensate-return method; only the condenser setpoint and the
insulated length are searched (3-10 simulations instead of the ~70-design, two-pass full grid).
Thermosiphon only: compared against the incumbent boiler, not against coaxial.

Configurations
--------------
* ``direct``: the condenser heats the customer's water directly (model architecture T_DIRECT).
* ``hybrid``: the condenser is the heat pump's evaporator (T_HP with direct coupling).
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .costs import economics
from .geology import Geology
from .levers import lever_steps
from .loads import load_series
from .optimize import annual_block
from .schema import load_case
from .simulate import Architecture, SimSettings, simulate
from .thermosiphon import ThermosiphonDesign

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"
PRESETS = {
    "Case A - Pennsylvania greenhouse (gas)": "case_a_pa.yaml",
    "Case B - North Dakota aquaculture (propane)": "case_b_nd.yaml",
    "Case A well, Dutch prices (gas)": "case_a_nl.yaml",
    "Case B well, Dutch prices (gas)": "case_b_nl.yaml",
}
PSM_THRESHOLD_KG = 4536.0  # 10,000 lb ammonia


@dataclass
class Inputs:
    preset: str = "Case A - Pennsylvania greenhouse (gas)"
    # well and rock
    depth_m: float = 1737.0
    T_surface_C: float = 12.0
    T_bottom_C: float = 80.0
    casing_id_mm: float = 150.0
    k_rock: float = 2.5
    # thermosiphon choices
    config: str = "hybrid"  # "direct" | "hybrid"
    condensate_return: str = "guided"  # "guided" | "film"
    insulation: str = "aerogel_n2"  # "aerogel_n2" | "n2_only" | "pip" | "vit_liner"
    ku_validated: float = 3.2
    cost_level: str = "noak"  # "foak" | "base" | "noak"
    pinned_T_cond: float | None = None
    full_coverage: bool = False  # only accept designs with <= 2 % unmet load in every year
    # heat demand
    peak_kW: float = 120.0
    flh: float = 5000.0
    shape: str = "western_pa"
    T_supply_C: float = 45.0
    T_return_C: float = 35.0
    distance_m: float = 250.0
    # prices / finance (None -> keep the preset's value)
    electricity_price: float | None = None  # $/kWh
    fuel_price_per_MWh: float | None = None
    boiler_efficiency: float | None = None
    discount_rate: float | None = None
    emission_factor: float | None = None  # t CO2 / MWh fuel
    years: int = 20
    n_z: int = 40


@dataclass
class Result:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    best: dict | None = None
    designs: pd.DataFrame | None = None
    timeseries: pd.DataFrame | None = None
    waterfall: pd.DataFrame | None = None
    breakevens: dict = field(default_factory=dict)
    incumbent: float = float("nan")


def preset_inputs(preset: str, **overrides) -> Inputs:
    """Inputs pre-filled from a preset case config (well, load and prices)."""
    c = load_case(CONFIG_DIR / PRESETS[preset])
    g = c.geology
    kw = dict(preset=preset, depth_m=float(g.depth), T_surface_C=float(g.profile_T[0]),
              T_bottom_C=float(g.profile_T[-1]), casing_id_mm=round(c.well.casing_id * 1e3, 1), k_rock=float(g.k),
              peak_kW=float(c.load["peak_month_kW"]), flh=float(c.load["flh"]), shape=c.load["shape"],
              T_supply_C=float(c.surface.T_supply), T_return_C=float(c.surface.T_return),
              distance_m=float(c.load["distance_m"]), electricity_price=float(c.params["electricity_price"]),
              fuel_price_per_MWh=float(c.prices["incumbent_fuel_price_per_MWh"]),
              boiler_efficiency=float(c.prices["incumbent_efficiency"]),
              discount_rate=float(c.params["discount_rate"]),
              emission_factor=c.prices.get("incumbent_emission_factor_t_per_MWh"))
    kw.update(overrides)
    return Inputs(**kw)


def build_case(inp: Inputs):
    case = load_case(CONFIG_DIR / PRESETS[inp.preset])
    geo = Geology.linear(inp.depth_m, inp.T_surface_C, inp.T_bottom_C, k=inp.k_rock,
                         rho=case.geology.rho, cp=case.geology.cp)
    well = replace(case.well, casing_id=inp.casing_id_mm / 1e3)
    surf = replace(case.surface, T_supply=inp.T_supply_C, T_return=inp.T_return_C, ts_hp_coupling="direct_coupled")
    p = dict(case.params)
    prices = dict(case.prices)
    if inp.electricity_price is not None:
        p["electricity_price"] = inp.electricity_price
    fuel = inp.fuel_price_per_MWh if inp.fuel_price_per_MWh is not None else prices["incumbent_fuel_price_per_MWh"]
    eff = inp.boiler_efficiency if inp.boiler_efficiency is not None else prices["incumbent_efficiency"]
    p["incumbent_useful_cost"] = fuel / eff
    p["heat_price"] = p["incumbent_useful_cost"] * p["heat_price_share_of_incumbent"]
    if inp.discount_rate is not None:
        p["discount_rate"] = inp.discount_rate
    p["ts_cost_level"] = inp.cost_level
    ef = inp.emission_factor if inp.emission_factor is not None else prices.get("incumbent_emission_factor_t_per_MWh")
    return case, geo, well, surf, p, (ef / eff if ef else float("nan"))


def candidate_designs(inp: Inputs, geo: Geology, surf) -> tuple[list[Architecture], list[str]]:
    """The small search space implied by the user's choices, plus pre-simulation errors."""
    errors = []
    T_dir = surf.T_supply + surf.approach
    if inp.config == "direct":
        arch_id = "T_DIRECT"
        setpoints = [inp.pinned_T_cond] if inp.pinned_T_cond else [T_dir, T_dir + 5]
    else:
        arch_id = "T_HP"
        setpoints = [inp.pinned_T_cond] if inp.pinned_T_cond else [10, 15, 20, 25, 30]
        setpoints = [T for T in setpoints if T < T_dir]
    usable = [T for T in setpoints if T <= geo.T_bottom - 8]
    if not usable:
        if inp.config == "direct":
            errors.append(f"Well too cold for direct heating: delivering {surf.T_supply:.0f} C needs a condenser at "
                          f">= {T_dir:.0f} C, but the rock is only {geo.T_bottom:.0f} C at the bottom (the condenser "
                          f"must be at least 8 C below it). Use the hybrid configuration or a lower supply temperature.")
        else:
            errors.append(f"Well too cold: the condenser setpoint must be at least 8 C below the bottom-hole "
                          f"temperature ({geo.T_bottom:.0f} C).")
        return [], errors
    if surf.T_supply <= surf.T_return:
        errors.append("Supply temperature must be above return temperature.")
        return [], errors
    archs = []
    for T in usable:
        L_auto = max(0.0, geo.depth_at_temperature(T + 3.0))
        for L in sorted({0.0, L_auto if L_auto >= 0.05 * geo.depth else 0.0}):
            archs.append(Architecture(arch_id, ts=ThermosiphonDesign(
                fluid="ammonia", T_top=float(T), insulated_length=float(L), insulation=inp.insulation,
                liquid_distribution=inp.condensate_return, guided_ku_validated=inp.ku_validated)))
    return archs, errors


def _sim(args):
    arch, geo, well, surf, L, sim = args
    return simulate(arch, geo, well, surf, L, sim)


def _lcoh(r, p, dist):
    return float(economics(r.arch.arch_id, dict(r.quantities, distance_m=dist), annual_block(r), p)["lcoh"])


def _unmet_max(r):
    load = r.annual(r.load)
    return float(np.max(np.asarray(r.E_backup) / np.maximum(load, 1e-9)))


_ERROR_HINTS = [
    ("critical point", "Ammonia would exceed its critical point (132 C) in this well: the well is too hot for an "
                       "ammonia thermosiphon."),
    ("shut-in pressure", "Shut-in pressure exceeds the string's rating at this depth and temperature."),
    ("collapse", "No practical wall thickness resists the external pressure for this casing size and depth."),
    ("clearance", "The insulated bore is too small for this casing: choose a thinner insulation or larger casing."),
    ("freezing", "Condenser setpoint is at or below the fluid's freezing point."),
]
_WARN_HINTS = [
    ("Kutateladze", "Guided return operates above the validated Ku limit you selected: performance depends on the "
                    "rig test of the stepped-reflux internals."),
    ("within 30 % of flooding", "Falling-film return is within 30 % of its flooding limit: unvalidated."),
    ("Mach >", "Vapour speed is high (Mach > 0.2): compressibility not modelled."),
    ("pressure drop", "Vapour pressure drop exceeds 30 % of absolute pressure: unvalidated."),
    ("property table", "Condenser temperature outside the fluid property table."),
    ("stagnation", "Shut-in stagnation pressure estimate is uncertain (supercritical at depth)."),
    ("transport-limited", "Output is throttled by the vapour flow limit in some months."),
]


def _explain(flags, table):
    out = []
    for f in flags:
        for key, msg in table:
            if key.lower() in f.lower() and msg not in out:
                out.append(msg)
    return out


def run(inp: Inputs, workers: int = 2) -> Result:
    case, geo, well, surf, p, ef_useful = build_case(inp)
    archs, errors = candidate_designs(inp, geo, surf)
    inc = p["incumbent_useful_cost"]
    if errors:
        return Result(ok=False, errors=errors, incumbent=inc)
    sim = SimSettings(years=inp.years, n_z=inp.n_z, n_r=32, distance_m=inp.distance_m)
    L = load_series(inp.peak_kW * 1e3, inp.shape, inp.flh, sim.years)
    jobs = [(a, geo, well, surf, L, sim) for a in archs]
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_sim, jobs))
    else:
        results = [_sim(j) for j in jobs]

    rows = []
    for r in results:
        delivered = float(np.sum(r.E_useful))
        rows.append(dict(design=r.arch.describe(), T_cond_C=r.arch.ts.T_top, insulated_m=r.arch.ts.insulated_length,
                         status=r.status if delivered > 0 else "NO OPERABLE POINT",
                         lcoh=_lcoh(r, p, inp.distance_m) if delivered > 0 else float("nan"),
                         unmet_max=_unmet_max(r), useful_MWh_per_yr=delivered / inp.years,
                         capability_kW_y1=float(np.mean(r.Q_geo_cap[:12]) / 1e3),
                         capability_kW_y20=float(np.mean(r.Q_geo_cap[-12:]) / 1e3),
                         ammonia_kg=r.quantities.get("inventory_kg", 0.0), flags="; ".join(r.flags), _r=r))
    df = pd.DataFrame(rows)
    if inp.full_coverage:
        covered = df[(df.unmet_max <= 0.02) & df.status.isin(["FEASIBLE", "UNVALIDATED"])]
        if not len(covered):
            served = df[df.status.isin(["FEASIBLE", "UNVALIDATED"])]
            best_cov = 1 - served.unmet_max.min() if len(served) else 0.0
            return Result(ok=False, errors=[
                f"No design covers the full load (<= 2 % unmet in every year). The best covers about {best_cov:.0%} in "
                "its worst year. Reduce the peak demand, use a deeper/hotter well, choose hybrid, or untick "
                "'require full coverage' to let a backup boiler cover the rest."], designs=df.drop(columns="_r"),
                incumbent=inc)
        df_sel = covered
    else:
        df_sel = df
    valid = df_sel[df_sel.status == "FEASIBLE"]
    allow = valid if len(valid) else df_sel[df_sel.status == "UNVALIDATED"]
    if not len(allow):
        errs = []
        if (df.status == "NO OPERABLE POINT").all():
            errs.append("No operable point: the vapour flow exceeds the flooding / speed limit at every condenser "
                        "setpoint, so condensate cannot return. The bore is too small for this well; try guided "
                        "return, a larger casing, or (hybrid) a warmer condenser.")
        errs += _explain(" | ".join(df.flags).split("; "), _ERROR_HINTS)
        return Result(ok=False, errors=errs or ["No valid design for these inputs."], designs=df.drop(columns="_r"),
                      incumbent=inc)
    best_row = allow.loc[allow.lcoh.idxmin()]
    r = best_row._r
    warnings = []
    if not len(valid):
        warnings.append("No fully validated design: the result below relies on an UNVALIDATED design.")
    warnings += _explain(r.flags, _WARN_HINTS)
    if best_row.unmet_max > 0.02:
        warnings.append(f"Up to {best_row.unmet_max:.0%} of the load is unmet in some year; the backup boiler "
                        "covers the rest at the incumbent's cost (not included in the thermosiphon heat cost).")
    if best_row.ammonia_kg > PSM_THRESHOLD_KG:
        warnings.append("Ammonia charge exceeds 10,000 lb: OSHA PSM / EPA RMP programme required.")
    if inp.config == "hybrid":
        warnings.append("Hybrid: ammonia enters the heat-pump machinery room (IIAR 2/9 scope; heat-pump charge "
                        "counts toward the PSM/RMP threshold).")

    # waterfall: thermosiphon only, against the incumbent
    def best_lcoh(pp):
        vals = [_lcoh(x._r, pp, inp.distance_m) for _, x in allow.iterrows()]
        return min(vals)

    base_p = dict(p)
    steps = [("FOAK (1.5x base)", dict(base_p, ts_cost_level="foak"))] + lever_steps(dict(base_p))
    wf = pd.DataFrame([dict(step=lab, lcoh=best_lcoh(pp)) for lab, pp in steps])
    wf["vs_incumbent"] = wf.lcoh - inc
    wf["carbon_price_for_parity"] = (wf.lcoh - inc).clip(lower=0) / ef_useful if np.isfinite(ef_useful) else np.nan

    ts = pd.DataFrame({
        "year": np.arange(1, inp.years + 1),
        "capability_kW": [float(np.mean(r.Q_geo_cap[12 * i:12 * i + 12]) / 1e3) for i in range(inp.years)],
        "useful_heat_MWh": np.asarray(r.E_useful) if np.ndim(r.E_useful) else np.nan,
        "load_MWh": r.annual(r.load),
    })
    best = dict(best_row.drop(labels="_r"))
    best["lcoh_at_selected_cost_level"] = best_row.lcoh
    return Result(ok=True, warnings=warnings, best=best, designs=df.drop(columns="_r"), timeseries=ts,
                  waterfall=wf, incumbent=inc,
                  breakevens=dict(carbon_price_for_parity=max(0.0, (best_row.lcoh - inc)) / ef_useful
                                  if np.isfinite(ef_useful) else float("nan")))
