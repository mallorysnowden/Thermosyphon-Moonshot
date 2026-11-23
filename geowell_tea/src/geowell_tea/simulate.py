"""Time-marching simulation of one architecture in one well.

Monthly steps by default.  Each step:

1. the shared rock model gives the per-slice linear response (A, S);
2. the downhole exchanger computes its capability at its operating setpoint;
3. the surface model converts geothermal heat to useful heat (direct / HP / adaptive);
4. dispatch: the system runs a fraction f = min(1, load / capability) of the
   step (duty cycling); the backup covers the rest of the load;
5. the rock is advanced with the time-averaged extraction.  For a thermosiphon,
   the idle fraction (1 - f) is spent in *stagnation*: with the condenser closed
   the pipe keeps moving heat from deep hot rock to shallower cold rock.

``load=None`` runs the resource-only test (sink never limiting).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np

from .coaxial import Coaxial, CoaxialDesign
from .geology import Geology
from .rock import RockField
from .surfaces import SurfaceParams, convert
from .thermosiphon import FEASIBLE, INFEASIBLE, UNVALIDATED, Thermosiphon, ThermosiphonDesign, worst
from .wellbore import Well

SEC_PER_MONTH = 365.25 / 12 * 86400


@dataclass
class Architecture:
    arch_id: str  # T_DIRECT, T_HP, T_ADAPTIVE, C_DIRECT, C_HP, C_ADAPTIVE
    ts: ThermosiphonDesign | None = None
    coax: CoaxialDesign | None = None

    @property
    def tech(self) -> str:
        return "TS" if self.arch_id.startswith("T_") else "C"

    @property
    def mode(self) -> str:
        return self.arch_id.split("_", 1)[1]

    def describe(self) -> str:
        if self.tech == "TS":
            d = self.ts
            tail = "packer[IP]" if d.architecture == "packer" else d.liquid_distribution
            return f"{self.arch_id} {d.fluid} T_top={d.T_top:.0f}C ins={d.insulated_length:.0f}m {tail}"
        d = self.coax
        tin = "var" if d.variable_flow_target is not None else f"{d.T_in:.0f}C"
        return f"{self.arch_id} VIT{d.tube_od*1000:.0f}mm m={d.m_dot:.1f}kg/s T_in={tin}"


@dataclass
class SimSettings:
    years: int = 20
    n_z: int = 50
    n_r: int = 36
    r_far: float = 200.0
    far_field: str = "adiabatic"
    distance_m: float = 250.0  # well to customer, one way
    delivery_dp_per_m: float = 250.0  # Pa/m hydronic delivery pipe gradient
    customer_dp: float = 100e3  # Pa customer-side loop
    pump_eff: float = 0.55
    controls_W: float = 500.0


@dataclass
class SimResult:
    arch: Architecture
    status: str
    flags: list
    months: int
    Q_geo_cap: np.ndarray  # W capability per month
    Q_useful_cap: np.ndarray
    Q_geo: np.ndarray  # W actually extracted (time-averaged)
    Q_useful: np.ndarray
    Q_direct: np.ndarray
    W_comp: np.ndarray
    W_pump_source: np.ndarray
    W_delivery: np.ndarray
    W_controls: np.ndarray
    load: np.ndarray
    T_source: np.ndarray
    cop: np.ndarray
    T_rock_wall_final: np.ndarray
    T_rock_init: np.ndarray
    q_final: np.ndarray
    z: np.ndarray
    energy_residual: float
    quantities: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    # ---- annual aggregates (MWh) ----
    def annual(self, arr: np.ndarray) -> np.ndarray:
        return arr.reshape(-1, 12).sum(axis=1) * SEC_PER_MONTH / 3.6e9

    @property
    def E_geo(self):
        return self.annual(self.Q_geo)

    @property
    def E_useful(self):
        return self.annual(self.Q_useful)

    @property
    def E_elec(self):
        return self.annual(self.W_comp + self.W_pump_source + self.W_delivery + self.W_controls)

    @property
    def E_backup(self):
        return self.annual(np.maximum(self.load - self.Q_useful, 0.0)) if np.all(np.isfinite(self.load)) \
            else np.zeros(self.months // 12)

    def summary(self) -> dict:
        y = self.E_useful
        g = self.E_geo
        e = self.E_elec
        yr = lambda arr, k: float(arr[min(k, len(arr) - 1)])  # noqa: E731
        cap_y = self.Q_geo_cap.reshape(-1, 12).mean(axis=1) / 1e3
        ucap_y = self.Q_useful_cap.reshape(-1, 12).mean(axis=1) / 1e3
        sustain = float(g[-1] / g[2]) if g[2] > 0 else float("nan")
        cap_sus = float(cap_y[-1] / cap_y[2]) if cap_y[2] > 0 else float("nan")
        return {
            "architecture": self.arch.arch_id,
            "design": self.arch.describe(),
            "status": self.status,
            "flags": "; ".join(self.flags),
            "geo_capability_kW_t0": float(self.Q_geo_cap[0] / 1e3),
            "geo_capability_kW_y1": yr(cap_y, 0),
            "geo_capability_kW_y10": yr(cap_y, 9),
            "geo_capability_kW_y20": yr(cap_y, 19),
            "useful_capability_kW_y1": yr(ucap_y, 0),
            "useful_capability_kW_y20": yr(ucap_y, 19),
            "E_geo_MWh_total": float(g.sum()),
            "E_useful_MWh_y1": yr(y, 0),
            "E_useful_MWh_y20": yr(y, 19),
            "E_useful_MWh_total": float(y.sum()),
            "E_elec_MWh_total": float(e.sum()),
            "elec_per_useful": float(e.sum() / y.sum()) if y.sum() > 0 else float("nan"),
            "SPF_system": float(y.sum() / e.sum()) if e.sum() > 0 else float("nan"),
            "direct_share": float(self.annual(self.Q_direct).sum() / y.sum()) if y.sum() > 0 else 0.0,
            "E_backup_MWh_total": float(self.E_backup.sum()),
            "unmet_share": float(self.E_backup.sum() / self.annual(self.load).sum())
            if np.all(np.isfinite(self.load)) and self.load.sum() > 0 else float("nan"),
            "y20_over_y3_extraction": sustain,
            "y20_over_y3_capability": cap_sus,
            "sustainable_80pct": bool(cap_sus >= 0.8) if not math.isnan(cap_sus) else False,
            "energy_residual": self.energy_residual,
            **{f"q_{k}": v for k, v in self.quantities.items()},
        }


def simulate(arch: Architecture, geo: Geology, well: Well, surface: SurfaceParams,
             load: np.ndarray | None, sim: SimSettings) -> SimResult:
    rock = RockField(geo, well.r_b, n_z=sim.n_z, n_r=sim.n_r, r_far=sim.r_far, far_field=sim.far_field)
    months = 12 * sim.years
    if arch.tech == "TS":
        ex = Thermosiphon(arch.ts, well, geo.depth, rock.z, rock.dz)
        ex.mechanical_checks(geo.T_bottom)
    else:
        ex = Coaxial(arch.coax, well, geo.depth, rock.z, rock.dz)
    L = np.full(months, np.inf) if load is None else np.asarray(load, float)[:months]
    rec = {k: np.zeros(months) for k in ("Qgc", "Quc", "Qg", "Qu", "Qd", "Wc", "Wp", "Wd", "Wctl", "Ts", "cop")}
    T_init = rock.T[0].copy()
    sum_q_J = 0.0
    aux_last = {}
    q_last = np.zeros(rock.n_z)
    cp_w, dT_load = 4180.0, surface.T_supply - surface.T_return
    dp_del = sim.customer_dp + sim.delivery_dp_per_m * 2 * sim.distance_m
    max_inventory = 0.0
    for m in range(months):
        resp = rock.response(SEC_PER_MONTH)
        q, Q, aux = ex.capability(resp)
        if arch.tech == "TS":
            src = {"T_top": aux.get("T_top", arch.ts.T_top) if aux else arch.ts.T_top}
        else:
            src = {"T_out": aux.get("T_out", 0.0), "T_in": arch.coax.T_in, "m": aux.get("m", 0.0),
                   "cp": aux.get("cp", 4180.0)}
        sr = convert(arch.mode, arch.tech, Q, src, surface)
        f = min(1.0, L[m] / sr.Q_useful) if sr.Q_useful > 0 else 0.0
        flux = f * q if sr.Q_useful > 0 else 0.0 * q
        if arch.tech == "TS" and f < 0.999 and ex.status != INFEASIBLE:
            q_stag, _ = ex.stagnation(resp)
            flux = flux + (1 - f) * q_stag
        rock.apply(flux)
        sum_q_J += float(np.sum(flux) * rock.dz * SEC_PER_MONTH)
        Qu = f * sr.Q_useful
        rec["Qgc"][m] = Q if sr.Q_useful > 0 else 0.0
        rec["Quc"][m] = sr.Q_useful
        rec["Qg"][m] = f * Q if sr.Q_useful > 0 else 0.0
        rec["Qu"][m] = Qu
        rec["Qd"][m] = f * sr.Q_direct
        rec["Wc"][m] = f * sr.W_comp
        rec["Wp"][m] = f * (aux.get("W_pump", 0.0) if arch.tech == "C" else 0.0) + f * sr.W_aux_source
        rec["Wd"][m] = Qu / (cp_w * dT_load * 1000.0) * dp_del / sim.pump_eff
        rec["Wctl"][m] = sim.controls_W
        rec["Ts"][m] = sr.T_source
        rec["cop"][m] = sr.cop
        if aux:
            aux_last = aux
            q_last = q
            if arch.tech == "TS" and Q > 0:
                max_inventory = max(max_inventory, ex.inventory_kg(aux))
    status = ex.status
    flags = list(ex.flags)
    # end-to-end energy balance: heat delivered to the surface vs heat lost by the rock
    delivered_J = float(np.sum(rec["Qg"]) * SEC_PER_MONTH)
    deficit = rock.energy_deficit_J() + rock.far_field_inflow_J
    resid = (delivered_J - deficit) / max(abs(deficit), 3.6e9)  # floor at 1 MWh for idle designs
    quantities = {"depth_m": geo.depth}
    diagnostics = {}
    if arch.tech == "TS":
        quantities.update(
            string_od_m=ex.geom.od, string_wall_m=ex.geom.t_wall, string_id_m=ex.geom.d_i,
            steel_kg=ex.steel_mass(), insulated_m=min(arch.ts.insulated_length, geo.depth),
            guided=arch.ts.liquid_distribution == "guided", inventory_kg=max_inventory,
            packer=arch.ts.architecture == "packer",
            insulation=arch.ts.insulation, ins_t_m=ex.ins_t,
            ins_od_m=ex.geom.d_i_ins + 2 * ex.geom.t_wall,
            direct_coupled=surface.ts_hp_coupling == "direct_coupled",
            fluid=arch.ts.fluid, p_stag_bar=getattr(ex, "p_stag", 0.0) / 1e5)
        if surface.ts_hp_coupling == "direct_coupled" and arch.arch_id in ("T_HP", "T_ADAPTIVE") and arch.ts.fluid == "ammonia":
            flags.append("direct coupling: ammonia enters the heat-pump machinery room (IIAR 2/9 scope; "
                         "HP charge counts toward the PSM/RMP threshold)")
        if ex.throttled_steps:
            flags.append(f"transport-limited: condenser throttled in {ex.throttled_steps} of {months} steps")
        diagnostics.update(max_flood=ex.max_flood, max_mach=ex.max_mach, max_dp_ratio=ex.max_dp_ratio,
                           throttled_steps=ex.throttled_steps,
                           min_wet=ex.min_wet,
                           Tsat_bottom=float(aux_last["Tsat"][-1]) if aux_last else float("nan"))
        if max_inventory > 4536:
            flags.append("ammonia inventory above 10,000 lb: OSHA PSM / EPA RMP programs apply"
                         if arch.ts.fluid == "ammonia" else "large flammable inventory")
    else:
        quantities.update(vit_m=geo.depth, tube_od_m=arch.coax.tube_od,
                          max_pump_dp_bar=ex.max_dp / 1e5)
        diagnostics.update(max_velocity=ex.max_v)
    quantities["peak_geo_W"] = float(rec["Qg"].max())
    quantities["peak_useful_W"] = float(rec["Qu"].max())
    quantities["peak_comp_W"] = float(rec["Wc"].max())
    quantities["peak_pump_W"] = float(rec["Wp"].max())
    quantities["peak_cap_geo_W"] = float(rec["Qgc"].max())
    return SimResult(arch, status, flags, months, rec["Qgc"], rec["Quc"], rec["Qg"], rec["Qu"], rec["Qd"],
                     rec["Wc"], rec["Wp"], rec["Wd"], rec["Wctl"], L, rec["Ts"], rec["cop"],
                     rock.wall_temperature(q_last * 0), T_init, q_last, rock.z, resid, quantities, diagnostics)
