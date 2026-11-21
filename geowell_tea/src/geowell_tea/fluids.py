"""Working-fluid properties.

CoolProp (the brief's preferred property library) is not installed in the build
environment and package installation was not possible, so this module provides a
transparent, dependency-free substitute:

* Saturation pressure, saturated-vapour density and latent heat from the
  Peng-Robinson cubic equation of state (Soave alpha function), solved by
  fugacity equality.  Latent heat comes from the PR residual enthalpies.
* Saturated-liquid density from the Rackett equation (water: an empirical fit),
  because PR liquid densities are poor (10-20 % error).
* Transport properties (viscosity, surface tension, liquid conductivity) are
  single reference values with simple temperature scalings.  They feed only
  the screening limits (flooding, film wetting, friction), not the energy balance.

Accuracy is checked in tests/test_properties.py against a handful of
well-known reference values (status: tolerances of 3-8 %).  Swap in CoolProp
by implementing the same ``SaturationTable`` interface if it is available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import math

import numpy as np

R_U = 8.314462618  # J/(mol K)
G = 9.80665


@dataclass(frozen=True)
class FluidConstants:
    name: str
    Tc: float  # K
    Pc: float  # Pa
    omega: float
    M: float  # kg/mol
    T_freeze: float  # K (triple / freezing point)
    Z_ra: float | None  # Rackett parameter (None -> custom liquid density)
    # transport reference values at T_ref (approximate literature values; assumed)
    T_ref: float
    sigma_ref: float  # N/m
    mu_l_ref: float  # Pa s
    mu_v_ref: float  # Pa s
    k_l: float  # W/(m K)
    cp_l: float  # J/(kg K)
    gamma_v: float  # vapour heat-capacity ratio (ideal-gas approx.)
    toxicity: str
    notes: str = ""


FLUIDS: dict[str, FluidConstants] = {
    "ammonia": FluidConstants("ammonia", 405.40, 11.333e6, 0.256, 0.017031, 195.5, 0.2465,
                              298.15, 0.0200, 1.30e-4, 1.01e-5, 0.48, 4740.0, 1.31,
                              "toxic (OSHA PSM / EPA RMP threshold 10,000 lb)",
                              "Used by the Xiong'an 4,149 m and Taiyuan SLGHP field systems."),
    "water": FluidConstants("water", 647.096, 22.064e6, 0.3443, 0.018015, 273.16, None,
                            298.15, 0.0720, 8.90e-4, 1.00e-5, 0.60, 4180.0, 1.33,
                            "none", "Very low vapour pressure at 30-80 C: sub-atmospheric, high vapour velocity."),
    "propane": FluidConstants("propane", 369.83, 4.248e6, 0.1523, 0.04410, 85.5, 0.2766,
                              298.15, 0.0070, 0.98e-4, 0.82e-5, 0.094, 2600.0, 1.13,
                              "flammable", "Critical point 96.7 C: hot wells stagnate supercritical."),
    "isobutane": FluidConstants("isobutane", 407.81, 3.629e6, 0.184, 0.05812, 113.7, 0.2754,
                                298.15, 0.0095, 1.50e-4, 0.75e-5, 0.088, 2400.0, 1.10,
                                "flammable"),
    "pentane": FluidConstants("pentane", 469.70, 3.370e6, 0.251, 0.07215, 143.5, 0.2684,
                              298.15, 0.0155, 2.20e-4, 0.67e-5, 0.110, 2300.0, 1.07,
                              "flammable", "Working fluid of the Zolfagharroshan (2024) benchmark."),
    "co2": FluidConstants("co2", 304.13, 7.3773e6, 0.2239, 0.04401, 216.6, 0.2722,
                          273.15, 0.0045, 1.00e-4, 1.40e-5, 0.11, 2500.0, 1.29,
                          "asphyxiant", "Critical point 31.0 C: no two-phase condensation above it."),
}


def _pr_params(fc: FluidConstants, T):
    Tr = T / fc.Tc
    kappa = 0.37464 + 1.54226 * fc.omega - 0.26992 * fc.omega ** 2
    sq = np.sqrt(Tr)
    alpha = (1.0 + kappa * (1.0 - sq)) ** 2
    a_c = 0.45724 * R_U ** 2 * fc.Tc ** 2 / fc.Pc
    a = a_c * alpha
    b = 0.07780 * R_U * fc.Tc / fc.Pc
    # da/dT
    dadT = -a_c * kappa * np.sqrt(alpha / (T * fc.Tc))
    return a, b, dadT


def _cubic_roots(A, B):
    c2 = -(1.0 - B)
    c1 = A - 3 * B ** 2 - 2 * B
    c0 = -(A * B - B ** 2 - B ** 3)
    roots = np.roots([1.0, c2, c1, c0])
    real = np.sort(roots[np.abs(roots.imag) < 1e-9].real)
    real = real[real > B]
    return real


def _ln_phi(Z, A, B):
    s2 = math.sqrt(2.0)
    return Z - 1 - math.log(Z - B) - A / (2 * s2 * B) * math.log((Z + (1 + s2) * B) / (Z + (1 - s2) * B))


def _h_dep(Z, A, B, T, a, b, dadT):
    """Residual molar enthalpy H - H_ig [J/mol] for PR."""
    s2 = math.sqrt(2.0)
    return R_U * T * (Z - 1) + (T * dadT - a) / (2 * s2 * b) * math.log(
        (Z + (1 + s2) * B) / (Z + (1 - s2) * B))


def pr_saturation(fc: FluidConstants, T: float) -> tuple[float, float, float]:
    """Return (Psat [Pa], rho_v [kg/m3], h_fg [J/kg]) from Peng-Robinson at T [K]."""
    if T >= fc.Tc:
        raise ValueError(f"{fc.name}: T={T:.1f} K is above the critical point {fc.Tc:.1f} K")
    a, b, dadT = _pr_params(fc, T)
    Tr = T / fc.Tc
    P = fc.Pc * math.exp(5.373 * (1 + fc.omega) * (1 - 1 / Tr))  # Wilson initial guess
    for _ in range(200):
        A = a * P / (R_U * T) ** 2
        B = b * P / (R_U * T)
        roots = _cubic_roots(A, B)
        if len(roots) < 2:
            # Only one phase root: nudge pressure toward the two-phase region
            Zr = roots[0] if len(roots) else 1.0
            P *= 1.05 if Zr > 0.3 else 0.95
            continue
        Zl, Zv = roots[0], roots[-1]
        ratio = math.exp(_ln_phi(Zl, A, B) - _ln_phi(Zv, A, B))
        P_new = P * ratio
        if abs(P_new / P - 1) < 1e-10:
            P = P_new
            break
        P = P_new
    A = a * P / (R_U * T) ** 2
    B = b * P / (R_U * T)
    roots = _cubic_roots(A, B)
    Zl, Zv = roots[0], roots[-1]
    rho_v = P * fc.M / (Zv * R_U * T)
    h_fg = (_h_dep(Zv, A, B, T, a, b, dadT) - _h_dep(Zl, A, B, T, a, b, dadT)) / fc.M
    return P, rho_v, h_fg


_IF97_N = (0.11670521452767e4, -0.72421316703206e6, -0.17073846940092e2, 0.12020824702470e5,
           -0.32325550322333e7, 0.14915108613530e2, -0.48232657361591e4, 0.40511340542057e6,
           -0.23855557567849, 0.65017534844798e3)


def water_psat_if97(T: float) -> float:
    """IAPWS-IF97 Region-4 saturation pressure [Pa] (273.15-647.096 K)."""
    n = _IF97_N
    th = T + n[8] / (T - n[9])
    A = th ** 2 + n[0] * th + n[1]
    B = n[2] * th ** 2 + n[3] * th + n[4]
    C = n[5] * th ** 2 + n[6] * th + n[7]
    return (2 * C / (-B + math.sqrt(B * B - 4 * A * C))) ** 4 * 1e6


def water_saturation(T: float) -> tuple[float, float, float]:
    """Water: IF97 Psat; vapour density from the PR vapour root at that pressure;
    latent heat by Clausius-Clapeyron (PR is >10 % off for water at 30-80 C)."""
    fc = FLUIDS["water"]
    P = water_psat_if97(T)
    a, b, _ = _pr_params(fc, T)
    A = a * P / (R_U * T) ** 2
    B = b * P / (R_U * T)
    Zv = _cubic_roots(A, B)[-1]
    rho_v = P * fc.M / (Zv * R_U * T)
    dT = 0.05
    dPdT = (water_psat_if97(T + dT) - water_psat_if97(T - dT)) / (2 * dT)
    rho_l = float(liquid_density(fc, T))
    h_fg = T * (1 / rho_v - 1 / rho_l) * dPdT
    return P, rho_v, h_fg


def liquid_density(fc: FluidConstants, T):
    T = np.asarray(T, dtype=float)
    if fc.name == "water":
        Tc_ = T - 273.15
        return 1000.6 - 0.0128 * np.abs(Tc_) ** 1.76
    Tr = np.minimum(T / fc.Tc, 0.999)
    v = R_U * fc.Tc / fc.Pc * fc.Z_ra ** (1 + (1 - Tr) ** (2.0 / 7.0))
    return fc.M / v


@dataclass
class SaturationTable:
    """Pre-tabulated saturation properties for fast vectorised interpolation."""
    fc: FluidConstants
    T: np.ndarray = field(repr=False)
    P: np.ndarray = field(repr=False)
    rho_v: np.ndarray = field(repr=False)
    rho_l: np.ndarray = field(repr=False)
    h_fg: np.ndarray = field(repr=False)

    @property
    def T_min(self) -> float:
        return float(self.T[0])

    @property
    def T_max(self) -> float:
        return float(self.T[-1])

    def in_range(self, T) -> np.ndarray:
        T = np.asarray(T)
        return (T >= self.T_min) & (T <= self.T_max)

    def psat(self, T):
        return np.exp(np.interp(T, self.T, np.log(self.P)))

    def tsat(self, P):
        return np.interp(np.log(P), np.log(self.P), self.T)

    def rhov(self, T):
        return np.interp(T, self.T, self.rho_v)

    def rhol(self, T):
        return np.interp(T, self.T, self.rho_l)

    def hfg(self, T):
        return np.interp(T, self.T, self.h_fg)

    def sigma(self, T):
        fc = self.fc
        Tr = np.clip(np.asarray(T) / fc.Tc, 0, 0.999)
        Tr0 = fc.T_ref / fc.Tc
        return fc.sigma_ref * ((1 - Tr) / (1 - Tr0)) ** 1.26

    def mu_l(self, T):
        fc = self.fc
        return fc.mu_l_ref * np.exp(1000.0 * (1.0 / np.asarray(T) - 1.0 / fc.T_ref))

    def mu_v(self, T):
        fc = self.fc
        return fc.mu_v_ref * (np.asarray(T) / fc.T_ref) ** 0.7

    def sound_speed(self, T, P):
        """Ideal-gas-like vapour sound speed with real-gas Z from the table."""
        fc = self.fc
        T = np.asarray(T)
        Z = P * fc.M / (self.rhov(T) * R_U * T)
        return np.sqrt(fc.gamma_v * Z * R_U * T / fc.M)


@lru_cache(maxsize=None)
def saturation_table(name: str, n: int = 240) -> SaturationTable:
    fc = FLUIDS[name]
    T_lo = max(fc.T_freeze + 2.0, 220.0)
    T_hi = 0.985 * fc.Tc
    Ts = np.linspace(T_lo, T_hi, n)
    P = np.empty(n)
    rv = np.empty(n)
    hf = np.empty(n)
    sat = water_saturation if name == "water" else (lambda T: pr_saturation(fc, T))
    for i, T in enumerate(Ts):
        P[i], rv[i], hf[i] = sat(float(T))
    rl = liquid_density(fc, Ts)
    return SaturationTable(fc, Ts, P, rv, rl, hf)


# ---------------------------------------------------------------------------
# Single-phase water (coaxial circulation fluid)
# ---------------------------------------------------------------------------

def water_rho(Tc):
    Tc = np.asarray(Tc, dtype=float)
    return 1000.6 - 0.0128 * np.abs(Tc) ** 1.76


def water_cp(Tc):
    Tc = np.asarray(Tc, dtype=float)
    return 4217.0 - 3.2 * Tc + 0.06 * Tc ** 2 - 2.5e-4 * Tc ** 3 + 0.0 * Tc


def water_mu(Tc):
    TK = np.asarray(Tc, dtype=float) + 273.15
    return 2.414e-5 * 10 ** (247.8 / (TK - 140.0))


def water_k(Tc):
    Tc = np.asarray(Tc, dtype=float)
    return 0.569 + 1.75e-3 * Tc - 7.0e-6 * Tc ** 2
