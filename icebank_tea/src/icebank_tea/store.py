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
class SimResult:
    years: int
    annual_cold_mwh: np.ndarray      # (Y,) load per year, whole pit
    unmet_mwh: np.ndarray            # (Y, K) whole pit, no backup
    unmet_partial_mwh: np.ndarray    # (Y, K) left over after a partial backup
    backup_partial_mwh: np.ndarray   # (Y, K) energy the partial backup supplies
    frozen_mwh: np.ndarray           # (Y, K) ice made (cold charged) per year, whole pit
    losses_mwh: np.ndarray           # (Y, K)
    end_ice_frac: np.ndarray         # (K,) ice fraction at the end of the run
    trace: np.ndarray | None = None  # daily ice fraction for K=0 when requested


def simulate(designs: list[Design], n_units: np.ndarray, t_air: np.ndarray, load_w: np.ndarray,
             t_use_max: float, ground_c: float, phys: Physics, partial_backup_w: float = 0.0,
             warmup_hours: int = 184 * 24, trace: bool = False) -> SimResult:
    """Run every design x unit count over the hourly series.

    t_air and load_w start on Jul 1 of a warm-up year; full calendar years follow.
    n_units: (M,) candidate unit counts, used for every design.
    """
    D, M = len(designs), len(n_units)
    K = D * M
    rep = lambda a: np.repeat(np.asarray(a, float), M)
    p = rep([d.pitch_m for d in designs]); depth = rep([d.depth_m for d in designs])
    L = depth - 1.0
    r_o = rep([d.r_out_m for d in designs]); r_i = rep([d.r_in_m for d in designs])
    ac = rep([d.cond_area_m2 for d in designs]); fmax = rep([d.max_ice_frac for d in designs])
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

    H = phys.t_water_start * cap_w  # J per cell (warm water before the first winter)
    n_hours = len(t_air)
    Y = (n_hours - warmup_hours) // 8760
    yr = lambda h: (h - warmup_hours) // 8760
    unmet = np.zeros((Y, K)); unmet_p = np.zeros((Y, K)); backup_p = np.zeros((Y, K))
    frozen = np.zeros((Y, K)); losses = np.zeros((Y, K)); annual = np.zeros(Y)
    part_cell = partial_backup_w / N
    tr = [] if trace else None
    inv_2pikL = 1.0 / (2 * np.pi * K_ICE * L)

    for h in range(n_hours):
        ta = t_air[h]
        ice = H < 0
        v_ice = np.where(ice, -H / (RHO_ICE * L_F), 0.0)
        t_store = np.where(ice, 0.0, H / cap_w)
        r = np.sqrt(v_ice / (np.pi * L) + r_o**2)
        drive = t_store - dt_head - ta
        q_f = np.where((drive > 0) & (H > h_min + 1.0), drive / (np.log(r / r_o) * inv_2pikL + r_ev + r_c), 0.0)
        gain = ta - t_store
        q_loss = phys.u_cover * a_top * np.where(gain > 0, gain, 0.0) + phys.u_ground * a_gnd * (ground_c - t_store)
        q_load = load_w[h] / N
        usable = ice | (t_store < t_use_max)
        served = np.where(usable, q_load, 0.0)
        short = q_load - served
        H = np.maximum(H + (served + q_loss - q_f) * 3600.0, h_min)
        if h >= warmup_hours:
            y = yr(h)
            if y < Y:
                unmet[y] += short * N
                bp = np.minimum(short, part_cell)
                backup_p[y] += bp * N
                unmet_p[y] += (short - bp) * N
                frozen[y] += q_f * N
                losses[y] += q_loss * N
                annual[y] += load_w[h]
        if trace and h % 24 == 0:
            tr.append(float(v_ice[0] / (p[0] ** 2 * L[0])))
    to_mwh = 1.0 / 1e6  # W*h -> MWh
    return SimResult(Y, annual * to_mwh, unmet * to_mwh, unmet_p * to_mwh, backup_p * to_mwh,
                     frozen * to_mwh, losses * to_mwh,
                     np.where(H < 0, -H / (RHO_ICE * L_F), 0) / (p**2 * L),
                     np.array(tr) if trace else None)
