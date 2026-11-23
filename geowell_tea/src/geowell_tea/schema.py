"""Configuration loading with provenance tracking.

Each leaf in the YAML files is either a plain value or a mapping
``{value, low?, high?, status, source}``.  ``load_case`` returns plain values
plus a provenance table so every exported result can list which inputs are
published, derived or merely assumed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from .geology import Geology
from .surfaces import SurfaceParams
from .wellbore import Well

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"
VALID_STATUS = {"published", "assumed", "derived", "measured"}


def _flatten(tree: dict, prefix: str = ""):
    values, prov = {}, []
    for k, v in tree.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and "value" in v:
            status = v.get("status", "assumed")
            if status not in VALID_STATUS:
                raise ValueError(f"{key}: status '{status}' not in {VALID_STATUS}")
            values[k] = v["value"]
            prov.append(dict(parameter=key, value=v["value"], low=v.get("low"), high=v.get("high"),
                             status=status, source=v.get("source", "")))
        elif isinstance(v, dict):
            sub_v, sub_p = _flatten(v, key + ".")
            values[k] = sub_v
            prov.extend(sub_p)
        else:
            values[k] = v
    return values, prov


@dataclass
class Case:
    name: str
    description: str
    geology: Geology
    well: Well
    surface: SurfaceParams
    load: dict
    prices: dict
    sim: dict
    params: dict  # flat cost/finance parameter dict (base values)
    ranges: dict  # name -> (low, base, high) for Monte Carlo / tornado
    provenance: list = field(default_factory=list)


def load_yaml(path) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def load_case(path, assumptions_path=None) -> Case:
    path = Path(path)
    if not path.exists():
        path = CONFIG_DIR / path
    raw = load_yaml(path)
    a_path = Path(assumptions_path) if assumptions_path else CONFIG_DIR / "assumptions.yaml"
    araw = load_yaml(a_path)
    cv, cprov = _flatten(raw)
    av, aprov = _flatten(araw, "assumptions.")
    g = cv["geology"]
    geo = Geology.linear(g["depth"], g["T_surface"], g["T_bottom"], k=g["k"], rho=g["rho"], cp=g["cp"],
                         groundwater_advection=bool(g.get("groundwater_advection", False)),
                         label=cv["case"]["name"])
    w = cv["well"]
    well = Well(casing_id=w["casing_id"], casing_wall=w.get("casing_wall", 0.0095),
                cement_thickness=w.get("cement_thickness", 0.025))
    s = av["surface"]
    ld = cv["load"]
    surface = SurfaceParams(T_supply=ld["T_supply"], T_return=ld["T_return"], approach=s["approach"],
                            eta_carnot=s["eta_carnot"], cop_max=s["cop_max"], min_lift=s["min_lift"],
                            ts_hp_coupling=str(cv.get("surface", {}).get("ts_hp_coupling", s.get("ts_hp_coupling", "direct_coupled"))))
    pr = cv["prices"]
    params = {}
    ranges = {}
    for section in ("finance", "common_capex", "coax_capex", "ts_capex"):
        params.update(av[section])
    params["equipment_size_factor"] = s["equipment_size_factor"]
    params["electricity_price"] = pr["electricity_price"]
    params["plugging_eol"] = pr["plugging_eol"]
    incumbent = pr["incumbent_fuel_price_per_MWh"] / pr["incumbent_efficiency"]
    params["incumbent_useful_cost"] = incumbent
    params["heat_price"] = incumbent * params["heat_price_share_of_incumbent"]
    for rec in aprov + cprov:
        name = rec["parameter"].split(".")[-1]
        if rec["low"] is not None and rec["high"] is not None and name in params:
            ranges[name] = (rec["low"], rec["value"], rec["high"])
    return Case(name=cv["case"]["name"], description=cv["case"]["description"], geology=geo, well=well,
                surface=surface, load=ld, prices=pr, sim=cv.get("simulation", {}), params=params,
                ranges=ranges, provenance=cprov + aprov)


def sample_params(base: dict, ranges: dict, n: int, seed: int = 7, keys=None) -> dict:
    """Independent triangular draws (low, mode=base, high) for every ranged parameter."""
    rng = np.random.default_rng(seed)
    out = {k: (np.full(n, v, dtype=float) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
           for k, v in base.items()}
    for k, (lo, mode, hi) in ranges.items():
        if keys is not None and k not in keys:
            continue
        if hi > lo:
            out[k] = rng.triangular(lo, min(max(mode, lo), hi), hi, n)
    if "heat_price_share_of_incumbent" in out:
        out["heat_price"] = out["incumbent_useful_cost"] * out["heat_price_share_of_incumbent"]
    return out
