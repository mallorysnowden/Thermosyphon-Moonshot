"""Deep gravity thermosiphon (two-phase closed thermosyphon / super-long gravity
heat pipe) inserted in an existing well.

Thermal model (per time step, quasi-steady inside the pipe):

* The surface condenser fixes the saturation temperature at the top of the
  vapour column, ``T_top``.  Going down, the saturation pressure rises with the
  vapour's own weight and with the friction of the up-flowing vapour, so the
  local saturation temperature T_sat(z) is not uniform (this matters for long
  pipes; Gruber et al. 2026).
* Each depth slice exchanges q' = (A - T_sat(z)) / R(z) with the rock (A and
  the rock resistance come from the shared rock model).  Slices where the rock
  is colder than T_sat receive heat (parasitic condensation on the wall) unless
  insulated.  R(z) includes rock, cement, casing, water-filled annulus, string
  wall, optional vacuum insulation and the internal film resistance.
* Falling-film wetting: the condensate returning from the condenser runs down
  the wall and is consumed by evaporation.  Where the film rate falls below a
  minimum wetting rate the wall partially dries out ("film" mode).  "guided"
  mode carries condensate to depth in a small inner line (as in the Xiong'an
  ladder design), so the wall stays wetted at extra cost.
* An optional bottom liquid pool sees hydrostatically elevated T_sat.

Feasibility screening (returns FEASIBLE / UNVALIDATED / INFEASIBLE + reason):
counter-current flooding (Tien-Kutateladze / Wallis), vapour Mach number,
frictional pressure drop relative to the absolute pressure, critical point,
freezing, property-table range, stagnation (shut-in) pressure vs burst rating,
collapse under the water-filled annulus, and working-fluid inventory vs the
10,000 lb OSHA PSM / EPA RMP threshold for ammonia.

What is NOT modelled (flagged in outputs): transient start-up, geysering,
entrainment details, two-phase pool dynamics, non-condensable gas build-up,
interphase momentum exchange beyond an interfacial friction multiplier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from .fluids import G, saturation_table
from .rock import StepResponse
from .wellbore import (STEEL_K, Well, burst_pressure, collapse_pressure, darcy_friction,
                       required_wall, steel_mass_per_m)

FEASIBLE, UNVALIDATED, INFEASIBLE = "FEASIBLE", "UNVALIDATED", "INFEASIBLE"
_RANK = {FEASIBLE: 0, UNVALIDATED: 1, INFEASIBLE: 2}


def worst(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


@dataclass
class ThermosiphonDesign:
    fluid: str = "ammonia"
    T_top: float = 50.0  # saturation temperature at the condenser [C] (setpoint)
    insulated_length: float = 0.0  # m of vacuum-insulated string from the surface
    liquid_distribution: str = "film"  # "film" | "guided"
    gap: float = 0.008  # radial gap between inserted string and casing [m]
    t_ins: float = 0.012  # radial thickness taken by the insulation (VIT) [m]
    k_ins: float = 0.015  # VIT apparent conductivity [W/(m K)] (assumed)
    h_evap: float = 2500.0  # wetted-wall evaporation coefficient [W/(m2 K)] (assumed)
    h_cond: float = 3000.0  # wall condensation coefficient [W/(m2 K)] (assumed)
    h_dry: float = 25.0  # dry wall to vapour [W/(m2 K)] (assumed)
    gamma_min: float = 0.02  # minimum film wetting rate [kg/(m s)] (assumed)
    pool_depth: float = 5.0  # bottom liquid pool height [m]
    guide_od: float = 0.025  # condensate guide line OD for "guided" [m]
    friction_mult: float = 1.5  # interfacial roughness multiplier on vapour friction (assumed)
    flooding_C: float = 3.2  # Kutateladze flooding constant (Pushkina-Sorokin)
    yield_pa: float = 552e6  # L80 tubing
    max_design_pressure: float = 150e5  # Pa, surface equipment / string rating cap
    label: str = ""


@dataclass
class TSGeometry:
    od: float
    t_wall: float
    d_i: float  # bare-section inner diameter
    d_i_ins: float  # insulated-section inner diameter
    a_vap: float
    a_vap_ins: float
    collapse_dp: float
    flags: list = field(default_factory=list)
    status: str = FEASIBLE


class Thermosiphon:
    def __init__(self, design: ThermosiphonDesign, well: Well, depth: float, z: np.ndarray, dz: float):
        self.d = design
        self.well = well
        self.depth = depth
        self.z = z
        self.dz = dz
        self.sat = saturation_table(design.fluid)
        self.fc = self.sat.fc
        self.geom = self._geometry()
        self.status = self.geom.status
        self.flags: list[str] = list(self.geom.flags)
        self.ins_mask = z < design.insulated_length
        # static resistances outside the fluid [m K/W] per slice
        r_ci = well.casing_id / 2
        r_so = self.geom.od / 2
        r_si = self.geom.d_i / 2
        R_gap = math.log(r_ci / r_so) / (2 * math.pi * well.annulus_fluid_k)
        R_wall = math.log(r_so / r_si) / (2 * math.pi * STEEL_K)
        R_ins = math.log(r_si / (self.geom.d_i_ins / 2)) / (2 * math.pi * design.k_ins)
        self.R_static = well.R_casing_cement + R_gap + R_wall + np.where(self.ins_mask, R_ins, 0.0)
        self.D_wet = np.where(self.ins_mask, self.geom.d_i_ins, self.geom.d_i)
        self.A_vap = np.where(self.ins_mask, self.geom.a_vap_ins, self.geom.a_vap)
        self.max_mach = 0.0
        self.max_flood = 0.0
        self.max_dp_ratio = 0.0
        self.min_wet = 1.0
        self._check_static()

    # ------------------------------------------------------------------ geometry
    def _geometry(self) -> TSGeometry:
        d, w = self.d, self.well
        flags: list[str] = []
        status = FEASIBLE
        od = w.casing_id - 2 * d.gap
        rho_w = 1000.0
        T_low = max(d.T_top - 30.0, self.sat.T_min - 273.15 + 1)
        p_int_low = float(self.sat.psat(T_low + 273.15))
        dp_ext = rho_w * G * self.depth - p_int_low  # water-filled annulus, low-pressure shut-in
        t = required_wall(od, dp_ext, yield_pa=d.yield_pa)
        if t is None:
            status = INFEASIBLE
            flags.append(f"collapse: no wall <= 0.2*OD resists {dp_ext/1e5:.0f} bar external pressure")
            t = 0.2 * od
        d_i = od - 2 * t
        d_i_ins = d_i - 2 * d.t_ins
        guide_area = math.pi / 4 * d.guide_od ** 2 if d.liquid_distribution == "guided" else 0.0
        a_vap = math.pi / 4 * d_i ** 2 - guide_area
        a_vap_ins = math.pi / 4 * d_i_ins ** 2 - guide_area
        if d_i_ins <= 0.03 or a_vap_ins <= 0:
            status = INFEASIBLE
            flags.append("clearance: insulated bore too small")
        return TSGeometry(od, t, d_i, d_i_ins, a_vap, max(a_vap_ins, 1e-6), dp_ext, flags, status)

    def _check_static(self):
        d, fc = self.d, self.fc
        Ttop_K = d.T_top + 273.15
        if Ttop_K <= fc.T_freeze + 2:
            self._flag(INFEASIBLE, "condenser temperature at/below freezing point of working fluid")
        if Ttop_K >= fc.Tc - 3:
            self._flag(INFEASIBLE, f"condenser temperature above critical point ({fc.Tc-273.15:.1f} C)")
        elif not self.sat.in_range(Ttop_K):
            self._flag(UNVALIDATED, "condenser temperature outside property table")

    def _flag(self, level: str, msg: str):
        self.status = worst(self.status, level)
        if msg not in self.flags:
            self.flags.append(msg)

    # ------------------------------------------------------------------ physics
    def _profile(self, resp: StepResponse, T_top: float, iters: int = 14, tol: float = 0.02):
        """Solve q'(z) for a given top saturation temperature by damped fixed-point
        iteration on the saturation-temperature and wetting profiles.  Returns
        (q [W/m], Tsat [C], aux dict)."""
        d, sat = self.d, self.sat
        n = len(self.z)
        dz = self.dz
        R_rock = resp.R_rock
        Ttop_K = T_top + 273.15
        P_top = float(sat.psat(Ttop_K))
        Tsat_K = np.full(n, Ttop_K)
        wet = np.ones(n)
        q = np.zeros(n)
        P = np.full(n, P_top)
        converged = False
        for it in range(iters):
            h_fg = sat.hfg(Tsat_K)
            # internal film resistance (evaporation where rock hotter, condensation otherwise)
            evap_side = resp.A + 273.15 > Tsat_K
            h_wet = np.where(evap_side, d.h_evap, d.h_cond)
            h_eff = np.where(evap_side, wet * h_wet + (1 - wet) * d.h_dry, h_wet)
            R_film = 1.0 / (h_eff * math.pi * self.D_wet)
            R_tot = R_rock + self.R_static + R_film
            q = (resp.A + 273.15 - Tsat_K) / R_tot
            # vapour mass flow through the face at the top of each slice (upward)
            mv = np.clip(np.cumsum((q * dz / h_fg)[::-1])[::-1], 0.0, None)
            # liquid film flow at each slice (downward): condenser return + wall condensation - evaporation
            Q_top = float(np.sum(q) * dz)
            ml_top = max(Q_top, 0.0) / float(sat.hfg(Ttop_K))
            ml = ml_top - np.cumsum(q * dz / h_fg) + q * dz / h_fg * 0.5
            ml = np.clip(ml, 0.0, None)
            if d.liquid_distribution == "film":
                gamma = ml / (math.pi * self.D_wet)
                wet_new = np.clip(gamma / d.gamma_min, 0.0, 1.0)
                wet = wet_new if it == 0 else 0.5 * wet + 0.5 * wet_new
            else:
                wet = np.ones(n)
            # pressure profile: vapour weight + friction (vapour flows up, pressure rises downward)
            rho_v = sat.rhov(Tsat_K)
            v = mv / (rho_v * self.A_vap)
            Dh = np.sqrt(4 * self.A_vap / math.pi)
            Re = rho_v * v * Dh / sat.mu_v(Tsat_K)
            f = darcy_friction(Re) * d.friction_mult
            dPdz = rho_v * G + f / Dh * rho_v * v ** 2 / 2
            P = P_top + np.cumsum(dPdz * dz) - dPdz * dz / 2
            # bottom pool: hydrostatic liquid head
            pool = self.z > self.depth - d.pool_depth
            if np.any(pool):
                rho_l = sat.rhol(Tsat_K)
                P = np.where(pool, P + rho_l * G * (self.z - (self.depth - d.pool_depth)), P)
            T_new = np.minimum(sat.tsat(P), sat.T_max)
            change = float(np.max(np.abs(T_new - Tsat_K)))
            Tsat_K = Tsat_K + 0.5 * (T_new - Tsat_K)
            if change < tol and it > 1:
                converged = True
                break
        aux = dict(P=P, mv=mv, ml=ml, wet=wet, v=v, rho_v=rho_v, Tsat=Tsat_K - 273.15, P_top=P_top,
                   R_tot=R_tot, converged=converged)
        return q, Tsat_K - 273.15, aux

    def capability(self, resp: StepResponse, T_top: float | None = None):
        """Heat delivered to the surface condenser at the design setpoint."""
        T_top = self.d.T_top if T_top is None else T_top
        if self.status == INFEASIBLE:
            return np.zeros(len(self.z)), 0.0, {}
        q, Tsat, aux = self._profile(resp, T_top)
        Q = float(np.sum(q) * self.dz)
        if Q <= 0:
            return np.zeros(len(self.z)), 0.0, aux
        if not aux["converged"]:
            q2, _, aux2 = self._profile(resp, T_top, iters=60)
            if aux2["converged"]:
                q, aux = q2, aux2
                Q = float(np.sum(q) * self.dz)
            else:
                self._flag(UNVALIDATED, "saturation-pressure / flow iteration did not converge")
        self._screen(aux, Q, T_top)
        return q, Q, aux

    def stagnation(self, resp: StepResponse):
        """Condenser closed: T_top floats until net heat to the surface is zero.
        Deep rock then heats shallow rock through the pipe (internal short circuit).

        With zero net flow, sum_i (A_i - Tsat_i) / R_i = 0 and Tsat_i = T + dT_i
        (dT_i = vapour-head offset).  The floating temperature therefore has the
        closed form T = sum((A - dT)/R) / sum(1/R); two passes refresh dT and R."""
        if self.status == INFEASIBLE:
            return np.zeros(len(self.z)), self.d.T_top
        T_hi = min(float(np.max(resp.A)), self.sat.T_max - 273.15 - 1)
        if T_hi <= self.d.T_top:
            return np.zeros(len(self.z)), self.d.T_top
        prev = getattr(self, "_T_stag_prev", None)
        T = prev if prev is not None else float(np.mean(resp.A))
        T = min(max(T, self.d.T_top), T_hi)
        for _ in range(2):
            q, Tsat, aux = self._profile(resp, T, iters=4)
            off = Tsat - T
            R = aux["R_tot"]
            T = float(np.sum((resp.A - off) / R) / np.sum(1.0 / R))
            T = min(max(T, self.d.T_top), T_hi)
        q = (resp.A - (T + off)) / R
        if T <= self.d.T_top + 1e-9 and np.sum(q) > 0:
            # even at the setpoint the pipe would deliver heat: idle condenser means no flow at all
            return np.zeros(len(self.z)), T
        q = q - np.sum(q) / len(q)  # exactly zero-sum internal transfer
        self._T_stag_prev = T
        return q, T

    # ------------------------------------------------------------------ limits
    def _screen(self, aux, Q, T_top):
        d, sat = self.d, self.sat
        Tsat_K = aux["Tsat"] + 273.15
        rho_v = aux["rho_v"]
        rho_l = sat.rhol(Tsat_K)
        sigma = sat.sigma(Tsat_K)
        drho = rho_l - rho_v
        jg = aux["mv"] / (rho_v * self.A_vap)
        jl = aux["ml"] / (rho_l * self.A_vap) if d.liquid_distribution == "film" else 0.0 * jg
        scale = (G * sigma * drho) ** 0.25
        Ku_g = jg * np.sqrt(rho_v) / scale
        Ku_l = jl * np.sqrt(rho_l) / scale
        flood = (np.sqrt(Ku_g) + np.sqrt(Ku_l)) / math.sqrt(d.flooding_C)
        Dh = np.sqrt(4 * self.A_vap / math.pi)
        Dstar = Dh * np.sqrt(G * drho / sigma)
        # small-diameter tubes: Wallis form (C=0.725) is more restrictive
        jgs = jg * np.sqrt(rho_v / (G * Dh * drho))
        jls = jl * np.sqrt(rho_l / (G * Dh * drho))
        wallis = (np.sqrt(jgs) + np.sqrt(jls)) / math.sqrt(0.725)
        flood = np.where(Dstar < 30, np.maximum(flood, wallis), flood)
        fmax = float(np.max(flood))
        mach = float(np.max(aux["v"] / sat.sound_speed(Tsat_K, aux["P"])))
        dp_ratio = float((aux["P"][-1] - aux["P_top"] - np.sum(rho_v * G * self.dz)) / aux["P_top"])
        self.max_flood = max(self.max_flood, fmax)
        self.max_mach = max(self.max_mach, mach)
        self.max_dp_ratio = max(self.max_dp_ratio, dp_ratio)
        self.min_wet = min(self.min_wet, float(np.min(aux["wet"])))
        if d.liquid_distribution == "guided":
            # Condensate returns in its own line, so the counter-current film correlation is
            # conservative.  The Xiong'an ladder-design SLGHP carried ~1 MW through a 177.8 mm
            # section (Ku_g ~ 4.4 by our property estimates).  Beyond Ku_g = 3.2 is therefore
            # UNVALIDATED (outside correlation, inside demonstrated range up to ~6), above 6 INFEASIBLE.
            if fmax > math.sqrt(6.0 / d.flooding_C):
                self._flag(INFEASIBLE, "vapour Kutateladze number beyond demonstrated guided-return range (6)")
            elif fmax > 1.0:
                self._flag(UNVALIDATED, "vapour Kutateladze number above 3.2 (guided return; field-demonstrated only)")
        elif fmax > 1.0:
            self._flag(INFEASIBLE, "counter-current flooding limit exceeded")
        elif fmax > 0.7:
            self._flag(UNVALIDATED, "within 30 % of flooding limit")
        if mach > 0.7:
            self._flag(INFEASIBLE, "vapour velocity near sonic limit")
        elif mach > 0.2:
            self._flag(UNVALIDATED, "compressible vapour flow (Mach > 0.2) not modelled")
        if dp_ratio > 0.3:
            self._flag(UNVALIDATED, "vapour frictional pressure drop > 30 % of absolute pressure")
        if float(np.max(Tsat_K)) >= self.fc.Tc - 2:
            self._flag(INFEASIBLE, "column bottom reaches critical point during operation")

    def mechanical_checks(self, T_rock_max: float) -> None:
        d, sat, fc = self.d, self.sat, self.fc
        T_stag = min(T_rock_max + 273.15, sat.T_max)
        if T_rock_max + 273.15 > fc.Tc:
            self._flag(UNVALIDATED, "shut-in stagnation would be supercritical at depth (pressure estimate uncertain)")
            p_stag = fc.Pc * 1.1
        else:
            p_stag = float(sat.psat(T_stag))
        self.p_stag = p_stag
        p_burst = burst_pressure(self.geom.od, self.geom.t_wall, d.yield_pa)
        if p_stag > min(p_burst, d.max_design_pressure):
            self._flag(INFEASIBLE, f"shut-in pressure {p_stag/1e5:.0f} bar exceeds rating "
                                   f"{min(p_burst, d.max_design_pressure)/1e5:.0f} bar")

    # ------------------------------------------------------------------ bookkeeping
    def inventory_kg(self, aux) -> float:
        """Working-fluid charge: vapour + falling film (Nusselt thickness) + pool + guide line."""
        sat, d = self.sat, self.d
        if not aux:
            return 0.0
        Tsat_K = aux["Tsat"] + 273.15
        rho_v = aux["rho_v"]
        rho_l = sat.rhol(Tsat_K)
        vap = float(np.sum(rho_v * self.A_vap) * self.dz)
        gamma = aux["ml"] / (math.pi * self.D_wet)
        mu_l = sat.mu_l(Tsat_K)
        delta = (3 * mu_l * gamma / (rho_l ** 2 * G)) ** (1 / 3)
        film = float(np.sum(delta * math.pi * self.D_wet * rho_l) * self.dz)
        pool = d.pool_depth * self.geom.a_vap * float(rho_l[-1])
        guide = 0.0
        if d.liquid_distribution == "guided":
            guide = 0.3 * math.pi / 4 * (d.guide_od - 0.006) ** 2 * self.depth * float(np.mean(rho_l))
        return vap + film + pool + guide

    def steel_mass(self) -> float:
        return steel_mass_per_m(self.geom.od, self.geom.t_wall) * self.depth
