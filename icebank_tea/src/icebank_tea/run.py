"""Run the ice-bank TEA for every case and write outputs/ and RESULTS.md.

    python -m icebank_tea.run            # full run (~2 min)
    python -m icebank_tea.run --quick    # coarse grid, for testing
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .cases import CASES, Case, awhp_cop, day_of_year, month_of_doy, on_peak
from .costs import AL_WORLD, CostInputs, crf, pit_usd_per_m3, unit_bom, with_foak
from .store import KWH_PER_M3_ICE, Design, ElecInputs, Physics, simulate
from .weather import CLIMATES, chained_years, freezing_degree_days

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs"
BACKUPS = {"full": 1.0, "partial": 0.3, "none": 0.0}
BACKUP_LABEL = {"full": "Ice + full backup chiller", "partial": "Ice + 30% backup chiller (smart charging)",
                "none": "Ice only (no chiller)"}
# The 30% backup is evaluated with and without off-peak charging of the pit ("pcharge"); the cheaper one is
# reported as "partial" (smart charging: charge only where it lowers the annual cost).
RELIABILITY = 0.001  # worst-year unmet cooling must be <= 0.1% of a median year's cooling


def series(case: Case, years: int, seed0: int = 1000, t_air=None):
    cl = CLIMATES[case.climate]
    t = chained_years(cl, years, seed0) if t_air is None else t_air
    doy = day_of_year(len(t))
    return t, case.load_w(t, doy)


def monthly_peaks(x, month, warm=184 * 24):
    """(Y, 12) monthly maximum of an hourly series, calendar years after the warm-up."""
    Y = (len(x) - warm) // 8760
    out = np.zeros((Y, 12))
    for y in range(Y):
        sl = slice(warm + y * 8760, warm + (y + 1) * 8760)
        np.maximum.at(out[y], month[sl], x[sl])
    return out


def demand_cost(peaks_kw, case: Case):
    """Median-year demand charges for (Y, 12[, K]) monthly peak kW."""
    r = case.demand_rates()
    per_year = np.tensordot(peaks_kw, r, axes=([1], [0])) if peaks_kw.ndim == 2 else np.einsum("ymk,m->yk", peaks_kw, r)
    return np.median(per_year, axis=0)


def demand_cost_onoff(pk_on, pk_off, case: Case):
    """Median-year demand charges from (Y, 12[, K]) monthly on- and off-peak maxima (kW).

    TOU tariffs bill on-peak demand at the seasonal rate plus off-peak demand in excess of on-peak at
    demand_off_excess; other tariffs bill the monthly maximum at any hour.
    """
    r = case.demand_rates()
    if case.tou:
        billed = np.einsum("ym...,m->y...", pk_on, r) + case.demand_off_excess * np.maximum(pk_off - pk_on, 0).sum(axis=1)
    else:
        billed = np.einsum("ym...,m->y...", np.maximum(pk_on, pk_off), r)
    return np.median(billed, axis=0)


def energy_cost(kwh_on, kwh_off, case: Case):
    """Median-year energy cost for (Y[, K]) on- and off-peak kWh."""
    p_on, p_off = case.prices()
    return np.median(kwh_on * p_on + kwh_off * p_off, axis=0)


def make_elec(case: Case, t, load, ci: CostInputs) -> ElecInputs:
    """Hourly electricity inputs. The 30% backup may charge the pit in off-peak hours of months with load."""
    n = len(t)
    month = month_of_doy(day_of_year(n))
    onpk = on_peak(n)
    charge_ok = (~onpk) & np.isin(month, np.unique(month[load > 0])) if ci.chiller_charging else None
    heat = dict(heat_w=case.heat_w(t), heat_peak_w=case.heat_peak_w,
                awhp_kwe_per_w=1.0 / (awhp_cop(t) * 1e3) if case.heat_bau == "ashp" else None) if case.heating else {}
    return ElecInputs(month=month, onpk=onpk, kwe_per_w=(1.0 / case.cop(t) + case.aux_kw_per_kwth()) / 1e3,
                      peak_w=case.peak_w, pump_cop=ci.pump_cop, dc_cop=ci.dc_cop, charge_ok=charge_ok,
                      ice_cop_factor=ci.ice_cop_factor, **heat)


WSHP_T_COND = 55.0 + 3 + 273.15


def wshp_cop(t_store: float, eta: float = 0.5) -> float:
    """Pit-sourced heat pump COP (same formula as store.simulate): evaporating 5 K below the pit water."""
    return eta * WSHP_T_COND / (WSHP_T_COND - (t_store - 5 + 273.15))


def heat_service_kwe(case: Case, hp_frac: float) -> tuple[float, float]:
    """Electrical-service sizing for heating: (winter design-day kWe, summer kWe at the year-round floor).

    The pit heat pump is sized at hp_frac of peak heat (COP at a 0 degC pit in winter, 4 degC in summer); the
    rest is air-source heat pumps in the electrified case, or boilers (no kWe) in the gas case.
    """
    if not case.heating:
        return 0.0, 0.0
    P = case.heat_peak_w / 1e3
    base = case.heat_base_frac * P
    ashp = case.heat_bau == "ashp"
    win = hp_frac * P / wshp_cop(0.0) + (ashp and (1 - hp_frac) * P / float(awhp_cop(np.array([case.heat_t_design]))[0]))
    hp_sum = min(base, hp_frac * P)
    summer = hp_sum / wshp_cop(4.0) + (ashp and (base - hp_sum) / float(awhp_cop(np.array([DESIGN_SUMMER_T]))[0]))
    return float(win), float(summer)


DESIGN_SUMMER_T = 32.0


def water_usd_per_mwh_rejected(case: Case, ci: CostInputs) -> float:
    """Tower / evaporative-condenser water cost per MWh of heat rejected (0 for air-cooled plants)."""
    if case.heat_rejection != "tower":
        return 0.0
    evap = ci.evap_m3_per_mwh_rej
    blow = evap / (ci.cycles_of_conc - 1)
    makeup = evap + blow
    sewer_m3 = makeup if case.sewer_on == "makeup" else blow
    return ci.water_price_mult * (makeup * (case.water_usd_m3 + ci.tower_chem_usd_m3) + sewer_m3 * case.sewer_usd_m3)


def water_m3_per_mwh_rejected(case: Case, ci: CostInputs) -> float:
    if case.heat_rejection != "tower":
        return 0.0
    return ci.evap_m3_per_mwh_rej * ci.cycles_of_conc / (ci.cycles_of_conc - 1)


def bau(case: Case, t, load, ci: CostInputs, warm=184 * 24):
    """Annual cost of BAU cooling (median year).

    Electricity covers the chiller (COP) plus auxiliaries (chilled-water pumps; condenser pumps and tower fans
    for tower plants). Tower plants also pay for makeup water, treatment and sewer.
    """
    peak_kw = case.peak_w / 1e3
    cop = case.cop(t)
    aux = case.aux_kw_per_kwth()
    kwe = load * (1.0 / cop + aux) / 1e3                               # hourly BAU electric draw, kW
    heat = case.heat_w(t)
    if case.heating and case.heat_bau == "ashp":
        kwe = kwe + heat / awhp_cop(t) / 1e3                          # air-source heat pumps share the meter
    rej_mwh = load * (1.0 + 1.0 / cop) / 1e6                           # heat rejected each hour, MWh
    month = month_of_doy(day_of_year(len(t)))
    onpk = on_peak(len(t))
    Y = (len(t) - warm) // 8760
    per_year_mwh, per_year_kwh_e, per_year_rej, per_year_heat = [], [], [], []
    kwh_on, kwh_off = np.zeros(Y), np.zeros(Y)
    for y in range(Y):
        sl = slice(warm + y * 8760, warm + (y + 1) * 8760)
        per_year_mwh.append(load[sl].sum() / 1e6)
        per_year_kwh_e.append(kwe[sl].sum())
        per_year_rej.append(rej_mwh[sl].sum())
        per_year_heat.append(heat[sl].sum() / 1e6)
        kwh_on[y] = kwe[sl][onpk[sl]].sum(); kwh_off[y] = kwe[sl][~onpk[sl]].sum()
    cold = float(np.median(per_year_mwh)); kwh_e = float(np.median(per_year_kwh_e))
    rej = float(np.median(per_year_rej))
    heat_mwh = float(np.median(per_year_heat))
    # monthly peak draw, on- and off-peak (assumed to add fully to the site's billed peaks)
    pk_on = monthly_peaks(np.where(onpk, kwe, 0.0), month, warm)
    pk_off = monthly_peaks(np.where(onpk, 0.0, kwe), month, warm)
    mech = peak_kw * case.redundancy * case.mech_usd_kw + peak_kw * case.extra_bau_capex_usd_kw
    peak_kwe = peak_kw * (1.0 / case.peak_cop() + aux)                 # cooling plant only
    h_win, h_sum = heat_service_kwe(case, 0.0)
    service_kwe = max(peak_kwe + h_sum, h_win)
    svc = service_kwe * ci.elec_service_usd_kwe
    a = crf(ci.rate, ci.life_mech)
    heat_plant = case.heat_peak_w / 1e3 * ci.awhp_usd_kw if case.heating and case.heat_bau == "ashp" else 0.0
    heat_fuel = heat_mwh / case.boiler_eff * case.gas_usd_mwh * ci.gas_price_mult if case.heat_bau == "gas" else 0.0
    parts = dict(plant=mech * a, heat_plant=heat_plant * a, elec_service=svc * a,
                 energy=float(energy_cost(kwh_on, kwh_off, case)),
                 demand=float(demand_cost_onoff(pk_on, pk_off, case)), heat_fuel=heat_fuel,
                 water=rej * water_usd_per_mwh_rejected(case, ci), om=(mech + heat_plant) * ci.mech_om_frac)
    total = sum(parts.values())
    service = cold + heat_mwh
    return dict(cold_mwh=cold, heat_mwh=heat_mwh, service_mwh=service,
                cold_p90_mwh=float(np.percentile(per_year_mwh, 90)), kwh_e=kwh_e,
                mean_cop=cold * 1e3 / max(kwh_e, 1e-9), rej_per_mwh=rej / max(cold, 1e-9),
                water_m3=rej * water_m3_per_mwh_rejected(case, ci), capex=mech + svc + heat_plant, parts=parts,
                total=total, lcoc=total / max(service, 1e-9), peak_kwe=peak_kwe, service_kwe=service_kwe)


def evaluate(case: Case, designs, n_units, sim, ci: CostInputs, b: dict):
    """Annual cost of every design x unit count x backup level. Returns list of dict rows."""
    peak_kw = case.peak_w / 1e3
    M = len(n_units)
    a_ice = crf(ci.rate, ci.life_icebank) * (1 + ci.rate) ** ci.construction_lag_years
    a_mech = crf(ci.rate, ci.life_mech)
    cold = b["cold_mwh"]
    service = b["service_mwh"]
    heat_kw = case.heat_peak_w / 1e3
    ashp = case.heating and case.heat_bau == "ashp"
    w_rej = b["rej_per_mwh"] * water_usd_per_mwh_rejected(case, ci)   # $ per MWh the backup chiller delivers
    keys = [k for k in (*BACKUPS, "pcharge") if k in sim.elec]
    energy = {k: energy_cost(sim.elec[k]["kwh_on"], sim.elec[k]["kwh_off"], case) for k in keys}
    demand = {k: demand_cost_onoff(sim.elec[k]["pk_on"], sim.elec[k]["pk_off"], case) for k in keys}
    rows = []
    for i, d in enumerate(designs):
        bom = unit_bom(d, ci)
        dc_kw = d.dc_frac * peak_kw
        dc_capex = dc_kw * ci.dc_usd_kw
        hp = d.hp_frac if case.heating else 0.0
        hp_capex = hp * heat_kw * (ci.wshp_usd_kw + ci.hp_coil_usd_kw)
        aw_capex = (1 - hp) * heat_kw * ci.awhp_usd_kw if ashp else 0.0
        h_win, h_sum = heat_service_kwe(case, hp)
        for j, n in enumerate(n_units):
            k = i * M + j
            pit_m3 = n * d.pitch_m**2 * d.depth_m
            capex_units = n * bom["unit_usd"]
            capex_pit = pit_m3 * pit_usd_per_m3(pit_m3, ci)
            capex_dis = peak_kw * ci.discharge_usd_kw * 1.2
            ice_capex = capex_units + capex_pit + capex_dis
            unmet_y = sim.unmet_mwh[:, k]
            if case.heating:
                boiler_mwh = float(np.median(sim.boiler_heat_mwh[:, k]))
                hp_mwh = float(np.median(sim.hp_heat_mwh[:, k]))
            else:
                boiler_mwh = hp_mwh = 0.0
            fuel = boiler_mwh / case.boiler_eff * case.gas_usd_mwh * ci.gas_price_mult
            # Electrified case: the boilers are backup only, so heat pumps (pit + air-source) must carry the
            # heating to the same standard as the cooling (worst year <= 0.1% left to the boilers)
            heat_worst = (float(sim.boiler_heat_mwh[:, k].max()) / max(b["heat_mwh"], 1e-9)) if ashp else 0.0
            for key in keys:
                f = BACKUPS["partial" if key == "pcharge" else key]
                if key == "full":
                    backup_mwh, left_y = float(np.median(unmet_y)), np.zeros_like(unmet_y)
                elif key == "partial":
                    backup_mwh, left_y = float(np.median(sim.backup_partial_mwh[:, k])), sim.unmet_partial_mwh[:, k]
                elif key == "pcharge":
                    backup_mwh = float(np.median(sim.backup_pcharge_mwh[:, k] + sim.charge_mwh[:, k]))
                    left_y = sim.unmet_pcharge_mwh[:, k]
                else:
                    backup_mwh, left_y = 0.0, unmet_y
                worst = float(left_y.max()) / max(cold, 1e-9)
                mech = f * peak_kw * case.mech_usd_kw
                coil = f * peak_kw * ci.charge_coil_usd_kw if key == "pcharge" else 0.0
                # Electrical service: backup chiller + auxiliaries, discharge pumps, dry-cooler fans
                # (heating cases: the larger of summer cooling + the heating floor, or the winter heating peak)
                cool_kwe = f * b["peak_kwe"] + peak_kw / ci.pump_cop + dc_kw / ci.dc_cop
                svc = max(cool_kwe + h_sum, h_win + dc_kw / ci.dc_cop) * ci.elec_service_usd_kwe
                parts = dict(thermosiphons=capex_units * a_ice, pit=capex_pit * a_ice, discharge=capex_dis * a_ice,
                             dry_cooler=dc_capex * a_mech, backup_plant=(mech + coil) * a_mech,
                             heat_pump=hp_capex * a_mech, heat_plant=aw_capex * a_mech,
                             elec_service=svc * a_mech, energy=float(energy[key][k]), demand=float(demand[key][k]),
                             heat_fuel=fuel, water=backup_mwh * w_rej,
                             om=ice_capex * ci.icebank_om_frac
                             + (mech + coil + dc_capex + hp_capex + aw_capex) * ci.mech_om_frac)
                total = sum(parts.values())
                rows.append(dict(case=case.key, backup=key, design=asdict(d), n_units=int(round(n)),
                                 unit_usd=bom["unit_usd"], pit_m3=pit_m3, pit_ha=n * d.pitch_m**2 / 1e4,
                                 ice_capex=ice_capex, backup_capex=mech + coil + svc, parts=parts, total=total,
                                 lcoc=total / max(service, 1e-9), ratio=total / b["total"], worst_unmet_frac=worst,
                                 hp_heat_mwh=hp_mwh, boiler_heat_mwh=boiler_mwh,
                                 feasible=worst <= RELIABILITY and heat_worst <= RELIABILITY,
                                 heat_worst_frac=heat_worst,
                                 kwh_ice_per_unit=float(np.median(sim.frozen_mwh[:, k])) * 1e3 / n,
                                 dc_mwh=float(np.median(sim.dc_mwh[:, k])),
                                 charges=key == "pcharge",
                                 charge_mwh=float(np.median(sim.charge_mwh[:, k])) if key == "pcharge" else 0.0,
                                 losses_frac=float(np.median(sim.losses_mwh[:, k])) / max(cold, 1e-9), k=k))
    return rows


def best(rows, backup):
    """Cheapest feasible row. For the 30% backup, consider it with and without off-peak charging (smart)."""
    keys = ("partial", "pcharge") if backup == "partial" else (backup,)
    cands = [r for r in rows if r["backup"] in keys and r["feasible"]]
    if not cands:
        return None
    r = dict(min(cands, key=lambda r: r["total"]))
    r["backup"] = backup
    return r


def grid(quick: bool, heating: bool = False):
    if heating:
        # The pit heat pump makes ice too, so sparser thermosiphon fields (wide pitch) and a range of heat-pump
        # sizes are searched; the dry cooler is left out (the heat pump does its job in the shoulder seasons).
        pitches = [1.5, 3.0] if quick else [1.0, 1.5, 2.0, 3.0, 4.0]
        conds = [25.0] if quick else [25.0, 40.0]
        depths = [10.0] if quick else [10.0, 15.0]
        hps = [0.0, 0.5, 1.0] if quick else [0.0, 0.25, 0.5, 0.75, 1.0]
        return [Design(p, a, z, hp_frac=h) for p in pitches for a in conds for z in depths for h in hps]
    pitches = [1.0, 1.5] if quick else [0.8, 1.0, 1.25, 1.5, 2.0]
    conds = [25.0] if quick else [12.0, 25.0, 40.0]
    depths = [10.0] if quick else [10.0, 15.0]
    dcs = [0.0, 0.3] if quick else [0.0, 0.1, 0.3]   # dry-cooler recharge, fraction of peak load
    return [Design(p, a, z, dc_frac=c) for p in pitches for a in conds for z in depths for c in dcs]


def n_grid(b: dict, quick: bool, heating: bool = False) -> np.ndarray:
    ref = (np.pi * (0.85 / np.pi) * 9) * KWH_PER_M3_ICE  # ~650 kWh: 1 m pitch, 9 m tube, full cell
    n0 = max(b["cold_p90_mwh"] * 1e3 * 1.1 / ref, 5)
    lo = 0.03 if heating else 0.25   # wide-pitch fields need far fewer units for the same pit
    return np.unique(np.round(n0 * np.geomspace(lo, 6.0, 10 if quick else (34 if heating else 28))))


def fill_dates(case, d, n, t, load, phys, el=None, warm=184 * 24):
    """Median date each winter when the store reaches 50% and 90% of its peak ice."""
    sim = simulate([d], np.array([n]), t, load, case.t_use_max, CLIMATES[case.climate].ground_c, phys, trace=True,
                   el=el)
    tr = sim.trace
    out = []
    for w in range(len(tr) // 365):
        seg = tr[w * 365:(w + 1) * 365]
        if seg.max() <= 0:
            continue
        imax = int(np.argmax(seg)); imin = int(np.argmin(seg[:imax + 1]))  # refill starts at the low point
        lo, hi = seg[imin], seg[imax]
        i50 = imin + int(np.argmax(seg[imin:] >= lo + 0.5 * (hi - lo)))
        i90 = imin + int(np.argmax(seg[imin:] >= lo + 0.9 * (hi - lo)))
        out.append((i50, i90, float(hi), float(lo)))
    if not out:
        return None
    md = lambda i: (dt.date(2025, 7, 1) + dt.timedelta(days=int(np.median([o[i] for o in out])))).strftime("%b %d")
    return dict(half=md(0), ninety=md(1), peak_ice_frac=float(np.median([o[2] for o in out])),
                low_ice_frac=float(np.median([o[3] for o in out])))


def sensitivities(case, backup, b_fn, rows_fn, ci, base_row, base_bau):
    """One-at-a-time changes for one backup configuration of a case.

    Each entry records the ice/BAU ratio and both annualized costs ($/MWh of the base case's cooling)
    at the low and high input, with the ice bank re-optimized each time.
    """
    out = []

    def cost_only(label, lo_ci, hi_ci, lo_case=None, hi_case=None):
        e = dict(input=label)
        for side, cc, cs in (("low", lo_ci, lo_case or case), ("high", hi_ci, hi_case or case)):
            b = b_fn(cs, cc)
            r_best = best(rows_fn(cs, cc, b), backup)
            ice = r_best["total"] if r_best else float("nan")
            e[side] = ice / b["total"]
            e[f"bau_{side}"] = b["lcoc"]
            e[f"ice_{side}"] = ice / base_bau["service_mwh"]
        out.append(e)

    cost_only("Finished/raw index (2.0 / 3.5)", replace(ci, index=2.0), replace(ci, index=3.5))
    cost_only("Aluminium price (world $2.85 / US $5.3 x1.2)", replace(ci, al_price=AL_WORLD), replace(ci, al_price=ci.al_price * 1.2))
    cost_only("Pit cost (x0.7 / x1.5)", replace(ci, pit_mult=0.7), replace(ci, pit_mult=1.5))
    cost_only("Discount rate (6% / 10%)", replace(ci, rate=0.06), replace(ci, rate=0.10))
    cost_only("Electricity price (x0.67 / x1.5)", ci, ci, replace(case, elec_usd_kwh=case.elec_usd_kwh * 0.67),
              replace(case, elec_usd_kwh=case.elec_usd_kwh * 1.5))
    cost_only("BAU plant $/kW (x0.6 / x1.5)", ci, ci, replace(case, mech_usd_kw=case.mech_usd_kw * 0.6),
              replace(case, mech_usd_kw=case.mech_usd_kw * 1.5))
    cost_only("Electrical service cost ($0 / $1,500 per kWe)", replace(ci, elec_service_usd_kwe=0),
              replace(ci, elec_service_usd_kwe=1500))
    cost_only("Demand charge (none / x2, e.g. 12-month ratchet)", ci, ci,
              replace(case, demand_summer=0.0, demand_winter=0.0, demand_off_excess=0.0),
              replace(case, demand_summer=2 * case.demand_summer, demand_winter=2 * case.demand_winter,
                      demand_off_excess=2 * case.demand_off_excess))
    if case.heat_rejection == "tower":
        cost_only("Water + sewer price (x0.5 / x2)", replace(ci, water_price_mult=0.5), replace(ci, water_price_mult=2.0))
    elif case.key == "A":
        # One-sided: switch the BAU trim chillers to water-cooled with towers (better COP, but uses water)
        cost_only("Trim chillers (air-cooled / water-cooled + towers)", ci, ci, case,
                  replace(case, heat_rejection="tower"))
    if case.heating:
        cost_only("Gas price (x0.67 / x1.5)", replace(ci, gas_price_mult=0.67), replace(ci, gas_price_mult=1.5))
        cost_only("Pit heat pump $/kW (x0.6 / x1.5)", replace(ci, wshp_usd_kw=ci.wshp_usd_kw * 0.6),
                  replace(ci, wshp_usd_kw=ci.wshp_usd_kw * 1.5))
        if case.heat_bau == "ashp":
            cost_only("Air-source heat pump $/kW (x0.6 / x1.5)", replace(ci, awhp_usd_kw=ci.awhp_usd_kw * 0.6),
                      replace(ci, awhp_usd_kw=ci.awhp_usd_kw * 1.5))
    cost_only("FOAK costs (NOAK / FOAK)", ci, with_foak(ci))
    for r in out:
        r["base"] = base_row["ratio"]
        r["bau_base"] = base_bau["lcoc"]
        r["ice_base"] = base_row["lcoc"]
    return out


def physics_sensitivity(case, backup, designs, n_units, t, load, gc, phys, el, ci, b, base_row):
    """Condenser conductance, re-simulated (only the ice bank changes)."""
    e = dict(input="Condenser conductance (3 / 8 W/m2K)", base=base_row["ratio"], bau_base=b["lcoc"],
             ice_base=base_row["lcoc"])
    for side, u in (("low", 3.0), ("high", 8.0)):
        sim_u = simulate(designs, n_units, t, load, case.t_use_max, gc, replace(phys, u_cond=u),
                         partial_backup_w=0.3 * case.peak_w, el=el)
        r_best = best(evaluate(case, designs, n_units, sim_u, ci, b), backup)
        ice = r_best["total"] if r_best else float("nan")
        e[side] = ice / b["total"]; e[f"bau_{side}"] = b["lcoc"]; e[f"ice_{side}"] = ice / b["service_mwh"]
    return e


def run_case(case: Case, years: int, quick: bool, ci: CostInputs, phys: Physics, log=print):
    t, load = series(case, years)
    b = bau(case, t, load, ci)
    designs = grid(quick, case.heating)
    n_units = n_grid(b, quick, case.heating)
    gc = CLIMATES[case.climate].ground_c
    el = make_elec(case, t, load, ci)
    log(f"[{case.key}] simulating {len(designs)} designs x {len(n_units)} sizes over {years} years ...")
    sim = simulate(designs, n_units, t, load, case.t_use_max, gc, phys, partial_backup_w=0.3 * case.peak_w, el=el)
    cache = {"sim": sim}

    def rows_fn(cs, cc, bb):
        return evaluate(cs, designs, n_units, cache["sim"], cc, bb)

    def b_fn(cs, cc):
        return bau(cs, t, cs.load_w(t, day_of_year(len(t))) if cs is not case else load, cc)

    rows = rows_fn(case, ci, b)
    res = dict(case=case, bau=b, fdd=freezing_degree_days(t[184 * 24:]) / years, best={}, sens=None, fill=None,
               foak={})
    fr = rows_fn(case, with_foak(ci), bau(case, t, load, with_foak(ci)))
    for key in BACKUPS:
        res["best"][key] = best(rows, key)
        res["foak"][key] = best(fr, key)
    if case.heating:
        hps = sorted({d.hp_frac for d in designs})
        res["hp_curve"] = []
        for h in hps:
            sub = [r for r in rows if r["design"]["hp_frac"] == h]
            cands = [best(sub, key) for key in BACKUPS]
            cands = [c for c in cands if c]
            if cands:
                res["hp_curve"].append((h, min(c["ratio"] for c in cands)))
    # The configuration to stress-test: cheapest feasible one
    feas = [r for r in res["best"].values() if r]
    top = min(feas, key=lambda r: r["total"])
    res["top"] = top
    res["sens"] = sensitivities(case, top["backup"], b_fn, rows_fn, ci, top, b)
    res["sens"].append(physics_sensitivity(case, top["backup"], designs, n_units, t, load, gc, phys, el, ci, b, top))
    # Ice-only sensitivities as well (for the charts), unless that is already the top configuration
    ice = res["best"]["none"]
    if ice is not None:
        if top["backup"] == "none":
            res["sens_none"] = res["sens"]
        else:
            res["sens_none"] = sensitivities(case, "none", b_fn, rows_fn, ci, ice, b)
            res["sens_none"].append(physics_sensitivity(case, "none", designs, n_units, t, load, gc, phys, el, ci, b, ice))
    if res["best"]["none"]:
        r = res["best"]["none"]
        res["fill"] = fill_dates(case, Design(**r["design"]), r["n_units"], t, load, phys, el)
    return res


def fmt_design(d):
    dc = f", dry cooler {100 * d['dc_frac']:.0f}% of peak" if d.get("dc_frac", 0) > 0 else ""
    hp = f", pit heat pump {100 * d['hp_frac']:.0f}% of peak heat" if d.get("hp_frac", 0) > 0 else ""
    return f"{d['pitch_m']:.2g} m pitch, {d['cond_area_m2']:.0f} m2 fins, {d['depth_m']:.0f} m deep{dc}{hp}"


def write_outputs(results, ci, years, phys):
    OUT.mkdir(exist_ok=True)
    with open(OUT / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "config", "bau_lcoc_usd_mwh", "ice_lcoc_usd_mwh", "ratio_vs_bau", "foak_ratio",
                    "n_units", "unit_usd", "kwh_ice_per_unit", "pitch_m", "cond_area_m2", "depth_m", "pit_m3",
                    "pit_ha", "worst_year_unmet_pct", "losses_pct", "bau_demand_usd_mwh", "ice_demand_usd_mwh"])
        for res in results:
            for key, r in res["best"].items():
                if not r:
                    w.writerow([res["case"].key, BACKUP_LABEL[key]] + ["no feasible design"] + [""] * 15)
                    continue
                fo = res["foak"][key]
                d = r["design"]
                w.writerow([res["case"].key, BACKUP_LABEL[key], round(res["bau"]["lcoc"], 1), round(r["lcoc"], 1),
                            round(r["ratio"], 3), round(fo["ratio"], 3) if fo else "", r["n_units"],
                            round(r["unit_usd"]), round(r["kwh_ice_per_unit"]), d["pitch_m"], d["cond_area_m2"],
                            d["depth_m"], round(r["pit_m3"]), round(r["pit_ha"], 2), round(100 * r["worst_unmet_frac"], 3),
                            round(100 * r["losses_frac"], 1),
                            round(res["bau"]["parts"]["demand"] / res["bau"]["service_mwh"], 1),
                            round(r["parts"]["demand"] / res["bau"]["service_mwh"], 1)])
    with open(OUT / "sensitivity.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "config", "input", "base_ratio", "low_case_ratio", "high_case_ratio",
                    "bau_base_usd_mwh", "bau_low_usd_mwh", "bau_high_usd_mwh",
                    "ice_base_usd_mwh", "ice_low_usd_mwh", "ice_high_usd_mwh"])
        for res in results:
            sets = [(res["top"]["backup"], res["sens"])]
            if res.get("sens_none") is not None and res["sens_none"] is not res["sens"]:
                sets.append(("none", res["sens_none"]))
            for key, sens in sets:
                for s in sens:
                    w.writerow([res["case"].key, BACKUP_LABEL[key], s["input"]] +
                               [round(s[k], 3) for k in ("base", "low", "high")] +
                               [round(s[k], 1) for k in ("bau_base", "bau_low", "bau_high",
                                                         "ice_base", "ice_low", "ice_high")])
    bom_rows = []
    for res in results:
        r = res["top"]
        b = unit_bom(Design(**r["design"]), ci)
        bom_rows.append(dict(case=res["case"].key, **{k: round(v, 2) for k, v in b.items()}))
    with open(OUT / "unit_bom.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bom_rows[0].keys()))
        w.writeheader(); w.writerows(bom_rows)
    (OUT / "run_meta.json").write_text(json.dumps(dict(years=years, reliability=RELIABILITY, costs=asdict(ci),
                                                        physics=asdict(phys)), indent=1))
    write_results_md(results, ci, years)


def write_results_md(results, ci, years):
    L = []
    L.append("# Ice bank TEA: results\n")
    L.append("Generated by `python -m icebank_tea.run`. Ratio = ice-bank annual cost / BAU annual cost "
             "(below 1 means the ice bank is cheaper). NOAK costs unless marked FOAK.\n")
    L.append(f"Weather: {years} synthetic years per site. Store must leave no more than {RELIABILITY:.1%} of a "
             "median year's cooling unmet in its worst year (configs without a full backup chiller).\n")
    L.append("## Headline (demand charges included)\n")
    L.append("Cost of cooling in $ per MWh of cold delivered (median year), and the ratio to BAU in brackets. "
             "For the hospital cases (B, F), which include heating, it is $ per MWh of heat plus cold.\n")
    L.append("| Case | Why this case | BAU $/MWh | of which demand charges | Ice + full backup | Ice + 30% backup | "
             "Ice only | Ice only at FOAK |")
    L.append("|---|---|---|---|---|---|---|---|")
    for res in results:
        c = res["case"]; b = res["best"]; fo = res["foak"]; bb = res["bau"]
        cell = lambda r: f"{r['lcoc']:.0f} ({r['ratio']:.2f})" if r else "not feasible"
        L.append(f"| {c.title} | {c.why} | {bb['lcoc']:.0f} | {bb['parts']['demand'] / bb['service_mwh']:.0f} | "
                 f"{cell(b['full'])} | {cell(b['partial'])} | {cell(b['none'])} | "
                 f"{cell(fo['none'])} |")
    used = [res["case"].key for res in results if res["best"]["partial"] and res["best"]["partial"].get("charges")]
    L.append("\nSmart charging: the 30% backup also charges the pit in off-peak hours wherever that lowers the "
             f"annual cost. It is used in case(s) {', '.join(used) or 'none'}; elsewhere the 30% backup only covers "
             "what the pit cannot. FOAK costs are quoted against the BAU cost above.\n")
    heat_res = [res for res in results if res["case"].heating]
    if heat_res:
        L.append("\n## Hospital with heating: the pit as a heat-pump source\n")
        L.append("A water-to-water heat pump draws its heat from the pit and so makes ice; boilers (case B) or "
                 "air-source heat pumps (case F) cover what it does not. Heat-pump size is a fraction of the "
                 f"{heat_res[0]['case'].heat_peak_w / 1e6:.1f} MW heating peak. Annual cost in $k/yr; "
                 "heat from the pit heat pump as a share of the year's heat.\n")
        for res in heat_res:
            bb = res["bau"]; hm = bb["heat_mwh"]
            L.append(f"\n**{res['case'].key}. {res['case'].title}.**\n")
            L.append("| Case | Config | Annual cost, $k | Ratio | Pit heat pump size | Heat from pit heat pump | "
                     "Thermosiphons | Pit | Gas, $k | Heat pumps (capital), $k |")
            L.append("|---|---|---|---|---|---|---|---|---|---|")
            L.append(f"| {res['case'].key} | Conventional (BAU) | {bb['total'] / 1e3:,.0f} | 1.00 | - | 0% | - | - | "
                     f"{bb['parts']['heat_fuel'] / 1e3:,.0f} | {bb['parts']['heat_plant'] / 1e3:,.0f} |")
            for key in BACKUPS:
                r = res["best"][key]
                if not r:
                    continue
                p = r["parts"]
                L.append(f"| {res['case'].key} | {BACKUP_LABEL[key]} | {r['total'] / 1e3:,.0f} | {r['ratio']:.2f} | "
                         f"{100 * r['design']['hp_frac']:.0f}% | {100 * r['hp_heat_mwh'] / hm:.0f}% | "
                         f"{r['n_units']:,} at {r['design']['pitch_m']:g} m pitch | "
                         f"{r['pit_m3']:,.0f} m3 ({r['pit_ha']:.2f} ha) | {p['heat_fuel'] / 1e3:,.0f} | "
                         f"{(p['heat_pump'] + p['heat_plant']) / 1e3:,.0f} |")
            L.append(f"\n{res['case'].key}: {bb['heat_mwh']:,.0f} MWh of heat and {bb['cold_mwh']:,.0f} MWh of "
                     "cold a year (median).")
            hp_curve = res.get("hp_curve")
            if hp_curve:
                L.append(f"\nBest feasible ice-bank option at each heat-pump size ({res['case'].key}), ratio to BAU: "
                         + ", ".join(f"{100 * h:.0f}% -> {v:.2f}" for h, v in hp_curve) + ".")
        L.append("")
    L.append("\n## Best ice-only design per case\n")
    L.append("| Case | Thermosiphons | Cost per unit | Ice per unit per winter | Design | Pit | Worst-year unmet | Store 50% / 90% full |")
    L.append("|---|---|---|---|---|---|---|---|")
    for res in results:
        r = res["best"]["none"]
        if not r:
            L.append(f"| {res['case'].key} | no feasible design in the grid | | | | | | |")
            continue
        fd = res["fill"] or {}
        L.append(f"| {res['case'].key} | {r['n_units']:,} | ${r['unit_usd']:.0f} | {r['kwh_ice_per_unit']:.0f} kWh | "
                 f"{fmt_design(r['design'])} | {r['pit_m3']:,.0f} m3 ({r['pit_ha']:.2f} ha) | "
                 f"{100 * r['worst_unmet_frac']:.2f}% | {fd.get('half', '-')} / {fd.get('ninety', '-')} |")
    L.append("\n## Where the money goes ($ per MWh of cold; hospital cases B and F: per MWh of heat + cold)\n")
    L.append("Ice-bank options:\n")
    L.append("| Case | Config | Thermosiphons | Pit | Pumps + HX | Dry cooler | Backup chiller | Heat pumps | "
             "Electrical service | Energy | Demand charges | Gas | Water | O&M | Total |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for res in results:
        cold = res["bau"]["service_mwh"]
        for key in BACKUPS:
            r = res["best"][key]
            if r is None:
                continue
            p = r["parts"]
            p = dict(p, heat_pumps=p["heat_pump"] + p["heat_plant"])
            L.append(f"| {res['case'].key} | {BACKUP_LABEL[key]} | " + " | ".join(
                f"{p[k] / cold:.0f}" for k in ("thermosiphons", "pit", "discharge", "dry_cooler", "backup_plant",
                                               "heat_pumps", "elec_service",
                                               "energy", "demand", "heat_fuel", "water", "om")) + f" | {r['lcoc']:.0f} |")
    L.append("\nConventional (BAU):\n")
    L.append("| Case | Heat rejection | Chiller plant | Heat pumps | Electrical service | Energy (chiller + pumps/fans) | "
             "Demand charges | Gas | Water + sewer | O&M | Total | Water use, m3/yr |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for res in results:
        bb = res["bau"]; p = bb["parts"]; cold = bb["service_mwh"]; c = res["case"]
        L.append(f"| {c.key} | {'cooling towers' if c.heat_rejection == 'tower' else 'air-cooled'} | " + " | ".join(
            f"{p[k] / cold:.0f}" for k in ("plant", "heat_plant", "elec_service", "energy", "demand", "heat_fuel",
                                           "water", "om"))
            + f" | {bb['lcoc']:.0f} | {bb['water_m3']:,.0f} |")
    L.append("\n## Sensitivities (best configuration per case; ratio at the low / high input)\n")
    L.append("| Case | Input | Base | Low | High |")
    L.append("|---|---|---|---|---|")
    for res in results:
        for s in sorted(res["sens"], key=lambda s: -abs(np.nan_to_num(s["high"]) - np.nan_to_num(s["low"]))):
            L.append(f"| {res['case'].key} | {s['input']} | {s['base']:.2f} | {s['low']:.2f} | {s['high']:.2f} |")
    L.append("\n## Case notes\n")
    for res in results:
        c = res["case"]
        L.append(f"- **{c.key}. {c.title}.** {c.notes} Demand charge: {c.demand_note} "
                 f"Median freezing degree-days {res['fdd']:.0f} degC-days; "
                 f"median-year cooling {res['bau']['cold_mwh']:,.0f} MWh."
                 + (f" Heating: {c.heat_note}" if c.heating else ""))
    L.append("\nWater: " + " ".join(f"{c.key}: {c.water_note}" for c in (r["case"] for r in results) if c.water_note)
             + " Tower makeup = evaporation (1.6 m3 per MWh of heat rejected, ~1.8 gal per ton-hour) + blowdown at "
             "4 cycles of concentration, plus $0.15/m3 treatment chemicals.")
    L.append("\nDemand charges bill the chiller's (and discharge pumps') highest draw in each month, assuming it adds "
             "fully to the site's monthly peak. Ratchets, interim surcharges and coincident-peak tariffs are not "
             "modelled; the x2 sensitivity brackets them.")
    (ROOT / "RESULTS.md").write_text("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--years", type=int, default=12)
    ap.add_argument("--cases", default="ABCDEF")
    a = ap.parse_args(argv)
    ci, phys = CostInputs(), Physics()
    years = 4 if a.quick else a.years
    results = [run_case(CASES[k], years, a.quick, ci, phys) for k in a.cases]
    write_outputs(results, ci, years, phys)
    try:
        from .charts import make_charts
        for f in make_charts(results, ci, years):
            print("wrote", f)
    except ImportError:
        print("matplotlib not installed: skipping charts (pip install -e .[charts])")
    for res in results:
        print(res["case"].key, {k: (round(v["ratio"], 2) if v else None) for k, v in res["best"].items()},
              "BAU", round(res["bau"]["lcoc"]), "$/MWh")


if __name__ == "__main__":
    main()
