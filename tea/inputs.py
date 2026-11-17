"""Load TEA inputs from a TOML file.

Each input is a table with ``base`` and optional ``low``, ``high``, ``unit`` and
``source``. Inputs are addressed as ``"section.name"``, for example
``"foundations.market_share"``.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Param:
    key: str
    base: Any
    low: Any = None
    high: Any = None
    unit: str = ""
    source: str = ""


def load_params(path: str | Path) -> dict[str, Param]:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    params: dict[str, Param] = {}
    for section, entries in raw.items():
        for name, spec in entries.items():
            key = f"{section}.{name}"
            params[key] = Param(
                key=key,
                base=spec["base"],
                low=spec.get("low"),
                high=spec.get("high"),
                unit=spec.get("unit", ""),
                source=spec.get("source", ""),
            )
    return params


def base_values(params: dict[str, Param]) -> dict[str, Any]:
    return {key: p.base for key, p in params.items()}
