"""Pumped closed-loop coaxial borehole heat exchanger in an existing well.

Water descends the annulus between the casing and an insulated centre tube
(vacuum-insulated tubing, VIT) and returns up the centre tube.  The model is
depth-resolved and couples to the same rock model as the thermosiphon:

    annulus cell i (flow down):  m cp (T_a[i] - T_a[i-1]) = q_rock[i] dz + (T_c[i] - T_a[i]) dz / R_sc
    centre  cell i (flow up):    m cp (T_c[i] - T_c[i+1]) = (T_a[i] - T_c[i]) dz / R_sc
    q_rock[i] = (A[i] - T_a[i]) / (R_rock[i] + R_well)

with T_a[-1] = T_in and T_c[n] = T_a[n-1] (turn-around at the bottom).  R_sc is
the thermal short circuit through the insulated centre tube.  The system is
linear and is solved directly each step; the upwind discretisation conserves
energy exactly (sum of rock heat = m cp (T_out - T_in)).

Hydraulics: Darcy friction in annulus and tube, minor losses, a surface heat
exchanger pressure drop, and the buoyancy (thermosiphon) pressure that the
cold descending and warm ascending columns create.  The static head rho g L is
NOT counted as pump work in a closed loop.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math

import numpy as np
from scipy.linalg import solve_banded

from .fluids import G, water_cp, water_k, water_mu, water_rho
from .rock import StepResponse
from .thermosiphon import FEASIBLE, INFEASIBLE, UNVALIDATED, worst
from .wellbore import Well, darcy_friction, gnielinski_nu


@dataclass
class CoaxialDesign:
    tube_od: float = 0.0889  # VIT outer diameter [m] (3-1/2")
    tube_id: float = 0.0620  # VIT inner flow diameter [m]
    k_ins: float = 0.015  # VIT apparent conductivity [W/(m K)] (assumed, same as TS insulation)
    m_dot: float = 3.0  # kg/s (fixed-flow modes) or maximum flow (direct mode)
    T_in: float = 40.0  # inlet temperature [C] (HP / adaptive modes; direct uses return+approach)
    variable_flow_target: float | None = None  # direct mode: hold T_out >= this [C]
    min_flow: float = 0.3  # kg/s
    minor_K: float = 10.0  # lumped minor-loss coefficient
    hx_dp: float = 50e3  # surface heat exchanger / evaporator pressure drop [Pa]
    pump_eff: float = 0.55  # wire-to-water
    max_pump_dp: float = 25e5  # Pa
    max_velocity: float = 3.0  # m/s
    label: str = ""


class Coaxial:
    def __init__(self, design: CoaxialDesign, well: Well, depth: float, z: np.ndarray, dz: float):
        self.d = design
        self.well = well
        self.depth = depth
        self.z = z
        self.dz = dz
        self.n = len(z)
        self.status = FEASIBLE
        self.flags: list[str] = []
        D_ci = well.casing_id
        if design.tube_od > D_ci - 0.03:
            self._flag(INFEASIBLE, "centre tube leaves < 15 mm annular gap")
        self.A_ann = math.pi / 4 * (D_ci ** 2 - design.tube_od ** 2)
        self.Dh_ann = D_ci - design.tube_od
        self.A_tube = math.pi / 4 * design.tube_id ** 2
        self.max_dp = 0.0
        self.max_v = 0.0
        if design.T_in < 3.0:
            self._flag(UNVALIDATED, "inlet below 3 C needs antifreeze (glycol properties not modelled)")

    def _flag(self, level, msg):
        self.status = worst(self.status, level)
        if msg not in self.flags:
            self.flags.append(msg)

    def _coefficients(self, m: float, T_mean: float):
        d, w = self.d, self.well
        rho, cp, mu, k = (float(water_rho(T_mean)), float(water_cp(T_mean)),
                          float(water_mu(T_mean)), float(water_k(T_mean)))
        Pr = cp * mu / k
        v_a = m / (rho * self.A_ann)
        v_t = m / (rho * self.A_tube)
        Re_a = rho * v_a * self.Dh_ann / mu
        Re_t = rho * v_t * d.tube_id / mu
        h_a = float(gnielinski_nu(Re_a, Pr)) * k / self.Dh_ann
        h_t = float(gnielinski_nu(Re_t, Pr)) * k / d.tube_id
        R_well = 1.0 / (h_a * math.pi * w.casing_id) + w.R_casing_cement
        R_sc = (1.0 / (h_t * math.pi * d.tube_id)
                + math.log(d.tube_od / d.tube_id) / (2 * math.pi * d.k_ins)
                + 1.0 / (h_a * math.pi * d.tube_od))
        return dict(rho=rho, cp=cp, mu=mu, v_a=v_a, v_t=v_t, Re_a=Re_a, Re_t=Re_t, R_well=R_well, R_sc=R_sc)

    def solve(self, resp: StepResponse, m: float, T_in: float):
        """Return (q [W/m], T_a, T_c, Q [W], coefficient dict)."""
        n, dz = self.n, self.dz
        T_guess = 0.5 * (T_in + float(np.mean(resp.A)))
        for _ in range(2):
            c = self._coefficients(m, T_guess)
            mcp = m * c["cp"]
            Rr = resp.R_rock + c["R_well"]
            g = dz / Rr  # rock conductance per slice [W/K]
            s = dz / c["R_sc"]  # short-circuit conductance per slice
            # unknown ordering: x[2i] = T_a[i], x[2i+1] = T_c[i]
            N = 2 * n
            # banded storage: ab[2 + row - col, col]; unknowns x[2i]=T_a[i], x[2i+1]=T_c[i]
            ab = np.zeros((5, N))
            idx = np.arange(n)
            # annulus rows: mcp T_a[i] - mcp T_a[i-1] = g (A - T_a[i]) + s (T_c[i] - T_a[i])
            ab[2, 2 * idx] = mcp + g + s
            ab[1, 2 * idx + 1] = -s
            ab[4, 2 * idx[:-1]] = -mcp  # row 2i (i>=1), col 2i-2
            # centre rows: mcp T_c[i] - mcp T_c[i+1] = s (T_a[i] - T_c[i])
            ab[2, 2 * idx + 1] = mcp + s
            ab[3, 2 * idx] = -s
            ab[0, 2 * idx[1:] + 1] = -mcp  # row 2i+1 (i<n-1), col 2i+3
            ab[3, 2 * (n - 1)] += -mcp  # bottom turn-around: T_c[n] = T_a[n-1]
            rhs = np.zeros(N)
            rhs[0::2] = g * resp.A
            rhs[0] += mcp * T_in
            x = solve_banded((2, 2), ab, rhs)
            T_a, T_c = x[0::2], x[1::2]
            T_guess = float(np.mean(np.concatenate([T_a, T_c])))
        q = g / dz * (resp.A - T_a)
        Q = float(np.sum(q) * dz)
        return q, T_a, T_c, Q, c

    def pump_power(self, m: float, T_a: np.ndarray, T_c: np.ndarray, c: dict) -> tuple[float, float]:
        """Electric pump power [W] and pump pressure rise [Pa]."""
        d = self.d
        rho = c["rho"]
        f_a = float(darcy_friction(c["Re_a"], 4.5e-5 / self.Dh_ann))
        f_t = float(darcy_friction(c["Re_t"], 1.5e-5 / d.tube_id))
        dp_f = (f_a * self.depth / self.Dh_ann * rho * c["v_a"] ** 2 / 2
                + f_t * self.depth / d.tube_id * rho * c["v_t"] ** 2 / 2
                + d.minor_K * rho * c["v_t"] ** 2 / 2 + d.hx_dp)
        dp_buoy = G * self.dz * float(np.sum(water_rho(T_a) - water_rho(T_c)))
        dp = max(dp_f - dp_buoy, 0.0)
        W = dp * m / rho / d.pump_eff
        self.max_dp = max(self.max_dp, dp)
        self.max_v = max(self.max_v, c["v_t"], c["v_a"])
        if dp > d.max_pump_dp:
            self._flag(INFEASIBLE, "pump pressure exceeds limit")
        if max(c["v_t"], c["v_a"]) > d.max_velocity:
            self._flag(INFEASIBLE, "flow velocity exceeds erosion/pressure-drop limit")
        return W, dp

    def max_flow_within_limits(self, T_mean: float = 30.0, margin: float = 0.9) -> float:
        """Largest flow [kg/s] whose friction pressure rise and velocity stay within
        ``margin`` x the pump and velocity limits (buoyancy credit ignored)."""
        d = self.d
        lo, hi = 0.05, 20.0
        for _ in range(40):
            m = 0.5 * (lo + hi)
            c = self._coefficients(m, T_mean)
            f_a = float(darcy_friction(c["Re_a"], 4.5e-5 / self.Dh_ann))
            f_t = float(darcy_friction(c["Re_t"], 1.5e-5 / d.tube_id))
            dp = (f_a * self.depth / self.Dh_ann * c["rho"] * c["v_a"] ** 2 / 2
                  + f_t * self.depth / d.tube_id * c["rho"] * c["v_t"] ** 2 / 2
                  + d.minor_K * c["rho"] * c["v_t"] ** 2 / 2 + d.hx_dp)
            ok = dp <= margin * d.max_pump_dp and max(c["v_a"], c["v_t"]) <= margin * d.max_velocity
            lo, hi = (m, hi) if ok else (lo, m)
        return lo

    def capability(self, resp: StepResponse):
        """Heat extraction at the operating point for this step.

        Fixed-flow modes: m = design m_dot, inlet = T_in.
        Variable-flow (direct): largest flow <= m_dot keeping T_out >= target."""
        d = self.d
        if self.status == INFEASIBLE:
            return np.zeros(self.n), 0.0, {}
        if d.variable_flow_target is not None and not hasattr(self, "_m_cap"):
            # the flow controller never exceeds the pump / velocity envelope
            self._m_cap = min(d.m_dot, self.max_flow_within_limits())
            self.d = d = replace(d, m_dot=self._m_cap)
        if d.variable_flow_target is None:
            m = d.m_dot
            q, T_a, T_c, Q, c = self.solve(resp, m, d.T_in)
        else:
            target = d.variable_flow_target
            q, T_a, T_c, Q, c = self.solve(resp, d.m_dot, d.T_in)
            m = d.m_dot
            if T_c[0] < target:
                lo, hi = d.min_flow, d.m_dot
                m_prev = getattr(self, "_m_prev", None)
                if m_prev:  # warm start: flow changes slowly between steps
                    lo_w, hi_w = max(d.min_flow, 0.8 * m_prev), min(d.m_dot, 1.1 * m_prev)
                    if self.solve(resp, lo_w, d.T_in)[2][0] >= target:
                        lo = lo_w
                        if self.solve(resp, hi_w, d.T_in)[2][0] < target:
                            hi = hi_w
                ql, T_al, T_cl, Ql, cl = self.solve(resp, lo, d.T_in)
                if T_cl[0] < target:
                    return np.zeros(self.n), 0.0, dict(T_out=T_cl[0], m=0.0, W_pump=0.0)
                for _ in range(9):
                    mid = 0.5 * (lo + hi)
                    qm, T_am, T_cm, Qm, cm = self.solve(resp, mid, d.T_in)
                    if T_cm[0] >= target:
                        lo, ql, T_al, T_cl, Ql, cl = mid, qm, T_am, T_cm, Qm, cm
                    else:
                        hi = mid
                m, q, T_a, T_c, Q, c = lo, ql, T_al, T_cl, Ql, cl
                self._m_prev = m
        if Q <= 0:
            return np.zeros(self.n), 0.0, dict(T_out=T_c[0], m=m, W_pump=0.0)
        W, dp = self.pump_power(m, T_a, T_c, c)
        return q, Q, dict(T_out=float(T_c[0]), T_in=d.T_in, m=m, cp=c["cp"], W_pump=W, dp=dp,
                          T_a=T_a, T_c=T_c)
