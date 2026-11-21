"""Existing-well geometry and pipe mechanics shared by both architectures."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

STEEL_K = 45.0  # W/(m K)
STEEL_E = 207e9  # Pa
STEEL_NU = 0.3
STEEL_RHO = 7850.0  # kg/m3


@dataclass
class Well:
    """Usable existing wellbore.  ``casing_id`` is the clear inner diameter that
    both architectures must fit inside (the clearance budget)."""
    casing_id: float = 0.150  # m
    casing_wall: float = 0.0095  # m
    cement_thickness: float = 0.025  # m (casing OD to drilled-hole wall)
    k_cement: float = 0.9  # W/(m K)
    annulus_fluid_k: float = 0.60  # water-filled annulus between inserted string and casing

    @property
    def casing_od(self) -> float:
        return self.casing_id + 2 * self.casing_wall

    @property
    def r_b(self) -> float:
        """Radius of the rock face (drilled hole)."""
        return self.casing_od / 2 + self.cement_thickness

    @property
    def R_casing_cement(self) -> float:
        """Conduction resistance casing ID -> rock face [m K / W]."""
        r_ci, r_co = self.casing_id / 2, self.casing_od / 2
        return (math.log(r_co / r_ci) / (2 * math.pi * STEEL_K)
                + math.log(self.r_b / r_co) / (2 * math.pi * self.k_cement))


def collapse_pressure(od: float, t: float, yield_pa: float = 552e6) -> float:
    """Conservative collapse resistance [Pa]: 0.8 x min(yield collapse, elastic collapse).

    Simplified from the API 5C3 regimes (the transition regime lies below both
    limiting curves, hence the 0.8 factor).  Screening only."""
    x = od / t
    p_yield = 2 * yield_pa * (x - 1) / x ** 2
    p_elastic = 2 * STEEL_E / (1 - STEEL_NU ** 2) / (x * (x - 1) ** 2)
    return 0.8 * min(p_yield, p_elastic)


def required_wall(od: float, dp_external: float, t_min: float = 0.0055, sf: float = 1.125,
                  yield_pa: float = 552e6) -> float | None:
    """Smallest wall [m] whose collapse resistance >= sf x net external pressure.
    Returns None if no reasonable wall (t <= 0.2 od) satisfies it."""
    t = t_min
    while t <= 0.2 * od:
        if collapse_pressure(od, t, yield_pa) >= sf * max(dp_external, 0.0):
            return t
        t += 0.0005
    return None


def burst_pressure(od: float, t: float, yield_pa: float = 552e6, design_factor: float = 0.8) -> float:
    """Barlow internal-yield pressure with design factor [Pa]."""
    return design_factor * 2 * yield_pa * t / od


def steel_mass_per_m(od: float, t: float) -> float:
    return STEEL_RHO * math.pi / 4 * (od ** 2 - (od - 2 * t) ** 2)


def darcy_friction(Re, rel_rough: float = 4.5e-5 / 0.1):
    """Darcy friction factor: laminar 64/Re, turbulent Haaland."""
    Re = np.maximum(np.asarray(Re, dtype=float), 1.0)
    lam = 64.0 / Re
    turb = (-1.8 * np.log10((rel_rough / 3.7) ** 1.11 + 6.9 / Re)) ** -2
    return np.where(Re < 2300, lam, turb)


def gnielinski_nu(Re, Pr):
    Re = np.maximum(np.asarray(Re, dtype=float), 1.0)
    f = (0.790 * np.log(np.maximum(Re, 3000)) - 1.64) ** -2
    nu_t = (f / 8) * (Re - 1000) * Pr / (1 + 12.7 * np.sqrt(f / 8) * (Pr ** (2 / 3) - 1))
    return np.where(Re < 2300, 4.36, np.maximum(nu_t, 4.36))
