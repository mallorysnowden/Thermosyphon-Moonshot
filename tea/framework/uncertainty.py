"""Sensitivity tools shared by every TEA: tornado, Monte Carlo and break-even."""
from __future__ import annotations

import random
from collections.abc import Callable

Model = Callable[[dict], float]  # inputs -> metric (usually NPV)


def tornado(params, base: dict, metric: Model) -> list[dict]:
    rows = []
    for key, p in params.items():
        if p.low is None or p.high is None or isinstance(p.base, list):
            continue
        lo, hi = metric({**base, key: p.low}), metric({**base, key: p.high})
        rows.append({"input": key, "low_value": p.low, "at_low": lo, "high_value": p.high,
                     "at_high": hi, "swing": abs(hi - lo)})
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return rows


def monte_carlo(params, base: dict, metric: Model, draws: int = 2000, seed: int = 7) -> list[float]:
    """Triangular(low, base, high) on every input that has a range; others at base."""
    rng = random.Random(seed)
    ranged = [(k, p) for k, p in params.items()
              if p.low is not None and p.high is not None and not isinstance(p.base, list)]
    out = []
    for _ in range(draws):
        v = dict(base)
        for k, p in ranged:
            lo, hi = sorted((p.low, p.high))
            mode = min(max(p.base, lo), hi)
            v[k] = lo if lo == hi else rng.triangular(lo, hi, mode)
        out.append(metric(v))
    return out


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    i = (len(s) - 1) * q
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def breakeven(base: dict, key: str, metric: Model, target: float, lo: float, hi: float, iters: int = 80) -> float | None:
    """Value of `key` in [lo, hi] at which metric equals target (bisection). None if no crossing."""
    f_lo, f_hi = metric({**base, key: lo}) - target, metric({**base, key: hi}) - target
    if f_lo == 0:
        return lo
    if f_lo * f_hi > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = metric({**base, key: mid}) - target
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2
