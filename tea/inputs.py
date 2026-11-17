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
        if not isinstance(entries, dict):
            continue
        for name, spec in entries.items():
            if not isinstance(spec, dict) or "base" not in spec:
                continue  # metadata such as [meta] titles, not a numeric input
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


def load_meta(path: str | Path) -> dict[str, Any]:
    """The [meta] table of an inputs file (project name, functional units, notes)."""
    with open(path, "rb") as f:
        return tomllib.load(f).get("meta", {})
