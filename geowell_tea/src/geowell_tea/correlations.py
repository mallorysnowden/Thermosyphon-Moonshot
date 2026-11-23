"""Two-phase and coil heat-transfer correlations used by the benchmark papers.

* Cooper (1984) nucleate pool boiling - used by the Huang/Chen/Gruber SLGHP model
  (Gruber et al. 2026, Table 1):
      h = 55 Pr^(0.12 - 0.2 log10 Rp) (-log10 Pr)^-0.55 M^-0.5 q''^0.67
  Pr = reduced pressure, Rp = surface roughness [um], M [g/mol], q'' [W/m2].
* Imura et al. (1979) thermosyphon evaporator boiling - used by
  Zolfagharroshan et al. (2024) Eq. (5).
* Nusselt film condensation with the 0.925 coefficient - Zolfagharroshan Eq. (9).
* Mori-Nakayama / Schmidt helical-coil convection and friction -
  Zolfagharroshan Eqs. (12)-(18).

All return heat-transfer coefficients in W/(m2 K).  Inputs are SI.
"""
from __future__ import annotations

import math

import numpy as np

from .fluids import G, SaturationTable

P_ATM = 101325.0


def cooper(sat: SaturationTable, T_K, q_flux, roughness_um: float = 1.0):
    fc = sat.fc
    Pr = np.clip(sat.psat(T_K) / fc.Pc, 1e-4, 0.95)
    M = fc.M * 1000.0
    exponent = 0.12 - 0.2 * math.log10(max(roughness_um, 1e-3))
    q = np.maximum(np.abs(q_flux), 1.0)
    return 55.0 * Pr ** exponent * (-np.log10(Pr)) ** -0.55 * M ** -0.5 * q ** 0.67


def imura(sat: SaturationTable, T_K, q_flux):
    fc = sat.fc
    rho_l = sat.rhol(T_K)
    rho_v = sat.rhov(T_K)
    h_fg = sat.hfg(T_K)
    mu_l = sat.mu_l(T_K)
    P = sat.psat(T_K)
    q = np.maximum(np.abs(q_flux), 1.0)
    return (0.32 * rho_l ** 0.65 * fc.k_l ** 0.3 * fc.cp_l ** 0.7 * G ** 0.2 * q ** 0.4
            / (rho_v ** 0.25 * h_fg ** 0.4 * mu_l ** 0.1) * (P / P_ATM) ** 0.3)


def nusselt_condensation(sat: SaturationTable, T_K, q_flux, length):
    """Zolfagharroshan Eq. (9): h = 0.925 [k^3 rho^2 g h_fg / (mu q'' l)]^(1/3)."""
    fc = sat.fc
    rho_l = sat.rhol(T_K)
    h_fg = sat.hfg(T_K)
    mu_l = sat.mu_l(T_K)
    q = np.maximum(np.abs(q_flux), 1.0)
    L = np.maximum(length, 0.05)
    return 0.925 * (fc.k_l ** 3 * rho_l ** 2 * G * h_fg / (mu_l * q * L)) ** (1.0 / 3.0)


def helical_coil_h(flow_m3s: float, d_in: float, D_coil: float, T_C: float):
    """Coolant-side coefficient in a helical coil (water).  Returns (h, Nu, Re, dp_per_m).

    Critical Re by Schmidt; laminar: Eq. (13)-(14) (Pr/Pr_w ~ 1); turbulent: Mori-Nakayama Eq. (15).
    Friction: Mori-Nakayama Eq. (17)/(18)."""
    from .fluids import water_cp, water_k, water_mu, water_rho
    rho, mu, k, cp = (float(water_rho(T_C)), float(water_mu(T_C)), float(water_k(T_C)), float(water_cp(T_C)))
    area = math.pi / 4 * d_in ** 2
    v = flow_m3s / area
    Re = rho * v * d_in / mu
    Pr = cp * mu / k
    delta = d_in / D_coil
    Re_crit = 2300 * (1 + 8.6 * delta ** 0.45)
    if Re < Re_crit:
        m = 0.5 + 0.2903 * delta ** 0.194
        Nu = 3.74 + 0.064 * delta ** 0.9 * Re ** m * Pr ** (1 / 3)
        Dn = Re * math.sqrt(delta)
        f = 64 / Re * 0.108 * Dn ** 0.5 / (1 - 3.253 * Dn ** -0.5) if Dn > 11 else 64 / Re
    else:
        Nu = Re ** (5 / 6) * delta ** (1 / 12) * Pr ** 0.4 / 41 * (1 + 0.061 / (Re * delta ** 2.5) ** (1 / 6))
        f = 0.3 * delta ** 0.5 / (Re * delta ** 2) ** 0.2 * (1 + 0.112 / (Re * delta ** 2) ** 0.2)
    h = Nu * k / d_in
    dp_per_m = f / d_in * rho * v ** 2 / 2
    return h, Nu, Re, dp_per_m
