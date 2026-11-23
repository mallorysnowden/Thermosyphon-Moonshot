"""Surface conversion: direct heat exchange, electric heat pump, adaptive (series
preheat + heat pump).  All temperatures in deg C, powers in W.

Every architecture delivers to the same hydronic load (supply/return
temperatures).  Direct heat is only useful when the source is above the supply
temperature by the heat-exchanger approach.  Heat-pump COP uses a transparent
Carnot-fraction model:

    COP = eta_carnot * T_cond[K] / (T_cond - T_evap),   T_cond = T_supply + approach

with a minimum lift and a COP cap.  ``Q_sink = Q_source + W_comp`` holds exactly.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SurfaceParams:
    T_supply: float = 45.0
    T_return: float = 35.0
    approach: float = 5.0  # K, every heat exchanger / evaporator / condenser
    eta_carnot: float = 0.50  # assumed (typical 0.4-0.6 for water-to-water units)
    cop_max: float = 8.0
    min_lift: float = 8.0  # K between evaporating and condensing temperature
    ts_hp_coupling: str = "secondary_loop"  # or "direct_coupled" (TS condenser = HP evaporator)
    secondary_loop_dp: float = 80e3  # Pa, TS condenser -> HP evaporator water loop
    pump_eff: float = 0.55


def cop(T_evap: float, T_cond: float, p: SurfaceParams) -> float:
    lift = max(T_cond - T_evap, p.min_lift)
    return min(p.eta_carnot * (T_cond + 273.15) / lift, p.cop_max)


@dataclass
class SurfaceResult:
    Q_useful: float  # W delivered to the hydronic load
    Q_direct: float  # W of that delivered without the compressor (direct / preheat)
    W_comp: float  # W compressor electricity
    W_aux_source: float  # W extra source-side pumping (TS secondary loop)
    cop: float  # heat-pump COP (0 if no heat pump)
    T_source: float  # temperature presented by the geothermal source [C]


def convert(mode: str, tech: str, Q_geo: float, src: dict, p: SurfaceParams) -> SurfaceResult:
    """Convert geothermal heat to useful heat.

    tech="TS": src = {"T_top": condenser saturation temperature}
    tech="C":  src = {"T_out", "T_in", "m", "cp"}
    mode in {"DIRECT", "HP", "ADAPTIVE"}
    """
    if Q_geo <= 0:
        return SurfaceResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    T_cond = p.T_supply + p.approach
    if tech == "TS":
        T_src = src["T_top"] - p.approach  # water leaving the TS condenser
        n_app = 2 if p.ts_hp_coupling == "secondary_loop" else 1
        T_evap = src["T_top"] - n_app * p.approach
        w_sec = 0.0
        if p.ts_hp_coupling == "secondary_loop":
            vdot = Q_geo / (4180.0 * 5.0 * 1000.0)
            w_sec = p.secondary_loop_dp * vdot / p.pump_eff
        if mode == "DIRECT":
            if T_src >= p.T_supply:
                return SurfaceResult(Q_geo, Q_geo, 0.0, 0.0, 0.0, T_src)
            return SurfaceResult(0.0, 0.0, 0.0, 0.0, 0.0, T_src)
        c = cop(T_evap, T_cond, p)
        k = c / (c - 1)
        if mode == "HP":
            Qu = Q_geo * k
            return SurfaceResult(Qu, 0.0, Qu - Q_geo, w_sec, c, T_src)
        # ADAPTIVE
        if T_src >= p.T_supply:
            return SurfaceResult(Q_geo, Q_geo, 0.0, 0.0, 0.0, T_src)
        phi = max(0.0, (T_src - p.T_return) / (p.T_supply - p.T_return))
        Qu = Q_geo * k / (1 - phi + phi * k)
        Q_pre = phi * Qu
        return SurfaceResult(Qu, Q_pre, Qu - Q_geo, w_sec, c, T_src)

    # coaxial: sensible stream from T_out down to T_in
    T_out, T_in, mcp = src["T_out"], src["T_in"], src["m"] * src["cp"]
    if mode == "DIRECT":
        if T_out - p.approach >= p.T_supply - 1e-6:
            return SurfaceResult(Q_geo, Q_geo, 0.0, 0.0, 0.0, T_out)
        return SurfaceResult(0.0, 0.0, 0.0, 0.0, 0.0, T_out)
    T_evap = T_in - p.approach
    c = cop(T_evap, T_cond, p)
    k = c / (c - 1)
    if mode == "HP":
        Qu = Q_geo * k
        return SurfaceResult(Qu, 0.0, Qu - Q_geo, 0.0, c, T_out)
    # ADAPTIVE: preheat HX first, then HP evaporator, in series on the source stream
    T_pre = min(p.T_supply, T_out - p.approach)
    phi = max(0.0, (T_pre - p.T_return) / (p.T_supply - p.T_return))
    pre_cap = max(0.0, mcp * (T_out - (p.T_return + p.approach)))
    pre_cap = min(pre_cap, Q_geo)
    Qu = Q_geo * k / (1 - phi + phi * k)
    Q_pre = phi * Qu
    if Q_pre > pre_cap:
        Q_pre = pre_cap
        Qu = Q_pre + (Q_geo - Q_pre) * k
    if Q_pre >= Q_geo - 1e-9 and phi >= 1.0:
        return SurfaceResult(Q_geo, Q_geo, 0.0, 0.0, 0.0, T_out)
    return SurfaceResult(Qu, Q_pre, Qu - Q_geo, 0.0, c, T_out)
