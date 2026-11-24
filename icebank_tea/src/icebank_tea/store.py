"""Hour-by-hour ice store: thermosiphons freeze, the load melts, losses leak in.

The pit is made of identical cells: one thermosiphon in a square column of
water (pitch x pitch x depth). All cells behave the same, so one cell is
simulated per (design, unit count) and the load per cell is load / N.

Each hour, per cell:
  freezing   q_f = drive / (R_ice + R_evap + R_cond)   when air is colder than the
             store (thermal diode); R_ice grows with ln(r_ice / r_tube)
  load       served from the store if there is ice, or if the water is still
             colder than the application's usable limit; otherwise unmet
  losses     floating cover (only when air is warmer than the store) + ground
The store's state is one enthalpy number relative to 0 degC water, so freezing,
melting and warming water are handled by one balance.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RHO_ICE, L_F, K_ICE = 917.0, 334e3, 2.2
RHO_W, CP_W = 1000.0, 4190.0
KWH_PER_M3_ICE = RHO_ICE * L_F / 3.6e6  # 85.1


@dataclass(frozen=True)
class Design:
    pitch_m: float        # square spacing between tubes
    cond_area_m2: float   # condenser fin area per thermosiphon
    depth_m: float        # pit water depth; evaporator = depth - 1 m
    r_out_m: float = 0.04
    r_in_m: float = 0.0377
    max_ice_frac: float = 0.85
    dc_frac: float = 0.0  # night/shoulder dry-cooler recharge: capacity as a fraction of peak load at a 10 K ITD

    @property
    def evap_len_m(self) -> float:
        return self.depth_m - 1.0


@dataclass(frozen=True)
class Physics:
    u_cond: float = 5.0         # W/m2K on dense-fin area; fits Li et al. 2020 (~2.5 m/s wind)
    h_evap: float = 2000.0      # W/m2K boiling inside the tube
    head_k_per_m: float = 0.15  # liquid-column penalty with stepped reflux / grooves (ammonia)
    u_cover: float = 0.25       # W/m2K floating insulated cover
    u_ground: float = 0.15      # W/m2K effective, sides and bottom
    t_water_start: float = 10.0 # degC pit water before the first winter


@dataclass
class ElecInputs:
    """Hourly inputs for electricity accounting (energy split on/off peak, monthly peak draw on/off peak)."""
    month: np.ndarray                 # calendar month 0-11
    onpk: np.ndarray                  # bool, utility on-peak hour
    kwe_per_w: np.ndarray             # backup chiller + auxiliaries, kWe per W of cooling
    peak_w: float                     # design peak load, W (sizes the dry cooler)
    pump_cop: float = 40.0            # store discharge pumps, W cooling per W electric
    dc_cop: float = 40.0              # dry-cooler fans + pumps at full capacity
    dc_itd: float = 10.0              # K: dry cooler rated at dc_frac x peak with water 10 K above air
    dc_min_dt: float = 2.0            # K: run the dry cooler only when water is this much warmer than air
    charge_ok: np.ndarray | None = None  # bool: hours the partial backup may charge the store (None = off)
    ice_cop_factor: float = 0.7       # chiller COP and capacity when charging below 4 degC (ice making)


CONFIGS = ("none", "full", "partial", "pcharge")


@dataclass
class SimResult:
    years: int
    annual_cold_mwh: np.ndarray      # (Y,) load per year, whole pit
    unmet_mwh: np.ndarray            # (Y, K) whole pit, no backup
    unmet_partial_mwh: np.ndarray    # (Y, K) left over after a partial backup
    backup_partial_mwh: np.ndarray   # (Y, K) energy the partial backup supplies
    frozen_mwh: np.ndarray           # (Y, K) cold put in by thermosiphons per year, whole pit
    losses_mwh: np.ndarray           # (Y, K)
    end_ice_frac: np.ndarray         # (K,) ice fraction at the end of the run
    trace: np.ndarray | None = None  # daily ice fraction for K=0 when requested
    dc_mwh: np.ndarray | None = None              # (Y, K) cold put in by the dry cooler
    unmet_pcharge_mwh: np.ndarray | None = None   # (Y, K) partial backup with off-peak charging
    backup_pcharge_mwh: np.ndarray | None = None  # (Y, K) backup serving load directly (pcharge)
    charge_mwh: np.ndarray | None = None          # (Y, K) cold charged into the store by the chiller
    # elec[config] = dict(kwh_on, kwh_off: (Y, K); pk_on, pk_off: (Y, 12, K) monthly max kWe)
    elec: dict | None = None


def simulate(designs: list[Design], n_units: np.ndarray, t_air: np.ndarray, load_w: np.ndarray,
             t_use_max: float, ground_c: float, phys: Physics, partial_backup_w: float = 0.0,
             warmup_hours: int = 184 * 24, trace: bool = False, el: ElecInputs | None = None) -> SimResult:
    """Run every design x unit count over the hourly series.

    t_air and load_w start on Jul 1 of a warm-up year; full calendar years follow.
    n_units: (M,) candidate unit counts, used for every design.
    One store trajectory serves "none", "full" and "partial" (backup only covers what the store can't).
    With el.charge_ok, a second trajectory ("pcharge") lets the partial backup also charge the store off-peak.
    Thermosiphons cool the store whenever the air is colder (any season); a dry cooler (dc_frac > 0)
    adds sensible recharge of liquid water when the air is at least dc_min_dt colder.
    """
    D, M = len(designs), len(n_units)
    K = D * M
    rep = lambda a: np.repeat(np.asarray(a, float), M)
    p = rep([d.pitch_m for d in designs]); depth = rep([d.depth_m for d in designs])
    L = depth - 1.0
    r_o = rep([d.r_out_m for d in designs]); r_i = rep([d.r_in_m for d in designs])
    ac = rep([d.cond_area_m2 for d in designs]); fmax = rep([d.max_ice_frac for d in designs])
    dcf = rep([d.dc_frac for d in designs])
    N = np.tile(np.asarray(n_units, float), D)
    v_water = p**2 * depth
    a_top = p**2
    a_gnd = p**2 + 4 * depth * p / np.sqrt(N)
    r_max = np.sqrt(fmax * p**2 / np.pi + r_o**2)
    v_ice_max = np.pi * (r_max**2 - r_o**2) * L
    r_ev = 1.0 / (phys.h_evap * 2 * np.pi * r_i * L)
    r_c = 1.0 / (phys.u_cond * ac)
    dt_head = phys.head_k_per_m * L / 2
    cap_w = RHO_W * CP_W * v_water                 # J/K
    h_min = -v_ice_max * RHO_ICE * L_F            # most negative enthalpy (full of ice)
    inv_2pikL = 1.0 / (2 * np.pi * K_ICE * L)
    peak_w = el.peak_w if el is not None else 0.0
    dc_ua_cell = dcf * peak_w / (el.dc_itd if el is not None else 10.0) / N   # W/K per cell
    dc_kwe = dcf * peak_w / 1e3 / (el.dc_cop if el is not None else 40.0)    # whole-pit fan+pump kWe when on
    dc_min_dt = el.dc_min_dt if el is not None else 2.0

    def step(H, ta, q_load):
        ice = H < 0
        v_ice = np.where(ice, -H / (RHO_ICE * L_F), 0.0)
        t_store = np.where(ice, 0.0, H / cap_w)
        r = np.sqrt(v_ice / (np.pi * L) + r_o**2)
        drive = t_store - dt_head - ta
        q_f = np.where((drive > 0) & (H > h_min + 1.0), drive / (np.log(r / r_o) * inv_2pikL + r_ev + r_c), 0.0)
        # dry cooler: sensible only, liquid water above 1 degC, never below 1 degC in the hour
        dt_dc = t_store - ta
        dc_on = (~ice) & (dt_dc >= dc_min_dt) & (t_store > 1.0) & (dc_ua_cell > 0)
        q_dc = np.where(dc_on, np.minimum(dc_ua_cell * dt_dc, (t_store - 1.0) * cap_w / 3600.0), 0.0)
        gain = ta - t_store
        q_loss = phys.u_cover * a_top * np.where(gain > 0, gain, 0.0) + phys.u_ground * a_gnd * (ground_c - t_store)
        usable = ice | (t_store < t_use_max)
        served = np.where(usable, q_load, 0.0)
        return v_ice, t_store, q_f, q_dc, dc_on, q_loss, served, q_load - served

    H = phys.t_water_start * cap_w  # J per cell (warm water before the first winter)
    charging = el is not None and el.charge_ok is not None
    Hc = H.copy() if charging else None
    n_hours = len(t_air)
    Y = (n_hours - warmup_hours) // 8760
    yr = lambda h: (h - warmup_hours) // 8760
    Z = lambda: np.zeros((Y, K))
    unmet, unmet_p, backup_p, frozen, losses, dcm = Z(), Z(), Z(), Z(), Z(), Z()
    unmet_pc, backup_pc, charged = Z(), Z(), Z()
    annual = np.zeros(Y)
    part_cell = partial_backup_w / N
    tr = [] if trace else None
    elec = None
    if el is not None:
        elec = {c: dict(kwh_on=Z(), kwh_off=Z(), pk_on=np.zeros((Y, 12, K)), pk_off=np.zeros((Y, 12, K)))
                for c in CONFIGS if c != "pcharge" or charging}
    for h in range(n_hours):
        ta = t_air[h]
        q_load = load_w[h] / N
        v_ice, t_store, q_f, q_dc, dc_on, q_loss, served, short = step(H, ta, q_load)
        H = np.maximum(H + (served + q_loss - q_f - q_dc) * 3600.0, h_min)
        if charging:
            _, t_c, q_fc, q_dcc, dc_onc, q_lossc, served_c, short_c = step(Hc, ta, q_load)
            bp_c = np.minimum(short_c, part_cell)
            q_ch = np.zeros(K); ice_mode = t_c < 4.0
            if el.charge_ok[h]:
                derate = np.where(ice_mode, el.ice_cop_factor, 1.0)
                room = np.maximum(Hc - h_min, 0.0) / 3600.0
                q_ch = np.minimum(np.maximum(part_cell - bp_c, 0.0) * derate, room)
            Hc = np.maximum(Hc + (served_c + q_lossc - q_fc - q_dcc - q_ch) * 3600.0, h_min)
        if h >= warmup_hours:
            y = yr(h)
            if y < Y:
                unmet[y] += short * N
                bp = np.minimum(short, part_cell)
                backup_p[y] += bp * N
                unmet_p[y] += (short - bp) * N
                frozen[y] += q_f * N
                dcm[y] += q_dc * N
                losses[y] += q_loss * N
                annual[y] += load_w[h]
                if charging:
                    unmet_pc[y] += (short_c - bp_c) * N
                    backup_pc[y] += bp_c * N
                    charged[y] += q_ch * N
                if el is not None:
                    kpw = el.kwe_per_w[h] * N
                    base = served * N / el.pump_cop / 1e3 + np.where(dc_on, dc_kwe, 0.0)
                    kw = {"none": base, "full": base + short * kpw, "partial": base + bp * kpw}
                    if charging:
                        kw["pcharge"] = (served_c * N / el.pump_cop / 1e3 + np.where(dc_onc, dc_kwe, 0.0)
                                         + bp_c * kpw + q_ch * kpw / np.where(ice_mode, el.ice_cop_factor, 1.0))
                    tag = "on" if el.onpk[h] else "off"
                    m = el.month[h]
                    for c, v in kw.items():
                        e = elec[c]
                        e["kwh_" + tag][y] += v
                        np.maximum(e["pk_" + tag][y, m], v, out=e["pk_" + tag][y, m])
        if trace and h % 24 == 0:
            tr.append(float(v_ice[0] / (p[0] ** 2 * L[0])))
    to_mwh = 1.0 / 1e6  # W*h -> MWh
    return SimResult(Y, annual * to_mwh, unmet * to_mwh, unmet_p * to_mwh, backup_p * to_mwh,
                     frozen * to_mwh, losses * to_mwh,
                     np.where(H < 0, -H / (RHO_ICE * L_F), 0) / (p**2 * L),
                     trace=np.array(tr) if trace else None, dc_mwh=dcm * to_mwh,
                     unmet_pcharge_mwh=unmet_pc * to_mwh if charging else None,
                     backup_pcharge_mwh=backup_pc * to_mwh if charging else None,
                     charge_mwh=charged * to_mwh if charging else None, elec=elec)
