"""Shared finance helpers."""
from __future__ import annotations

from collections.abc import Sequence


def crf(rate: float, years: float) -> float:
    """Capital recovery factor: turns an upfront cost into an equal annual payment."""
    if rate == 0:
        return 1.0 / years
    growth = (1 + rate) ** years
    return rate * growth / (growth - 1)


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """Net present value of end-of-year cash flows starting in year 1."""
    return sum(cf / (1 + rate) ** (year + 1) for year, cf in enumerate(cashflows))
