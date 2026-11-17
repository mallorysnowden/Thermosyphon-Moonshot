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


def irr(cashflows: Sequence[float], lo: float = -0.99, hi: float = 10.0) -> float | None:
    """Internal rate of return (year-1 start), or None if NPV never crosses zero."""
    f_lo, f_hi = npv(lo, cashflows), npv(hi, cashflows)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid, cashflows)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2
