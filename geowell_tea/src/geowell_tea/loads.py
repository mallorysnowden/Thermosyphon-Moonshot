"""Customer heat-demand profiles (monthly resolution).

Monthly averages hide hourly peaks; the model therefore reports a
"peak-month average" capacity, not an hourly design peak (see MODEL_LIMITATIONS).
"""
from __future__ import annotations

import numpy as np

# Approximate monthly heating-degree-day shares for western Pennsylvania and
# western North Dakota (shape only; scenario assumption, not station data).
HDD_SHAPE = {
    "western_pa": np.array([1050, 880, 730, 410, 170, 30, 5, 10, 80, 340, 620, 920], float),
    "western_nd": np.array([1650, 1350, 1100, 650, 330, 90, 30, 50, 280, 640, 1100, 1500], float),
    "flat": np.ones(12),
}


def monthly_fractions(shape: str, flh: float) -> np.ndarray:
    """Monthly load as a fraction of the peak-month load, with the requested
    full-load-equivalent hours per year (relative to the peak-month load):

        f_m = a + b * HDD_m / max(HDD),  max f = 1,  mean f = flh / 8760
    """
    hdd = HDD_SHAPE[shape]
    s = hdd / hdd.max()
    target = flh / 8760.0
    if shape == "flat" or np.allclose(s, s[0]):
        return np.full(12, min(target, 1.0))
    # a + b = 1 ; a + b*mean(s) = target
    b = (1 - target) / (1 - s.mean())
    a = 1 - b
    if a < 0:  # requested FLH too low for this shape: pure HDD scaling
        return s * target / s.mean()
    return a + b * s


def load_series(peak_W: float, shape: str, flh: float, years: int,
                ramp: list[float] | None = None) -> np.ndarray:
    f = monthly_fractions(shape, flh)
    L = np.tile(f, years) * peak_W
    if ramp:
        for y, r in enumerate(ramp):
            L[12 * y:12 * (y + 1)] *= r
    return L
