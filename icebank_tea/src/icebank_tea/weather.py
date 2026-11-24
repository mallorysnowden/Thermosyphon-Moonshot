"""Hourly air temperature for each site.

Default: synthetic years built from monthly normals plus day-to-day weather
(AR(1) anomalies) and a daily cycle, tuned so freezing degree-days and hot-day
counts are roughly right. This is a placeholder for real hourly records:
pass an hourly CSV (one temperature column, degC) to `load_csv` to replace it.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field

import numpy as np

HOURS = 8760
MID_DOY = np.array([15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349])


@dataclass(frozen=True)
class Climate:
    name: str
    monthly_mean_c: tuple[float, ...]       # Jan..Dec daily-mean normals
    diurnal_half_range_c: tuple[float, ...]  # Jan..Dec, half of (max - min)
    sigma_winter: float                      # sd of daily anomaly in mid-winter, degC
    sigma_summer: float                      # sd of daily anomaly in mid-summer, degC
    ground_c: float                          # deep ground temperature around the pit
    source: str = ""
    ar1: float = 0.75


CLIMATES = {
    "fargo": Climate(
        "Fargo, ND",
        (-13.0, -10.3, -2.7, 6.1, 13.7, 19.3, 21.5, 20.4, 15.6, 7.5, -1.4, -9.1),
        (4.5, 5.0, 5.0, 6.5, 6.5, 6.5, 6.5, 6.8, 6.5, 6.0, 4.5, 4.0),
        6.5, 4.0, 7.0,
        "Monthly means: 1991-2020 normals, Hector Intl (Wikipedia climate table). Spread and daily range: tuned.",
    ),
    "minneapolis": Climate(
        "Minneapolis, MN",
        (-8.8, -6.3, 0.7, 8.4, 15.3, 20.9, 23.5, 22.1, 17.5, 9.7, 1.6, -5.6),
        (4.0, 4.5, 5.0, 5.8, 5.5, 5.2, 5.1, 5.0, 5.5, 5.5, 4.0, 3.8),
        5.5, 3.8, 9.0,
        "Monthly means: 1991-2020 normals, MSP (Wikipedia climate table). Spread and daily range: tuned.",
    ),
    "dillingham": Climate(
        "Dillingham / Naknek, AK",
        (-9.4, -7.7, -5.4, -0.2, 6.3, 10.7, 12.8, 12.0, 8.2, 0.8, -5.4, -8.3),
        (4.0, 4.5, 4.5, 4.0, 4.0, 3.8, 3.4, 3.4, 3.5, 3.5, 3.5, 4.0),
        6.0, 2.2, 3.0,
        "Monthly means: 1981-2010 normals, Dillingham (Wikipedia climate table). Spread and daily range: tuned.",
    ),
    "beijing": Climate(
        "Beijing (calibration only)",
        (-3.1, 0.3, 6.7, 14.8, 20.8, 24.9, 26.7, 25.5, 20.8, 13.7, 5.0, -0.9),
        (5.5, 5.8, 6.0, 6.2, 6.0, 5.0, 4.0, 4.2, 5.0, 5.5, 5.5, 5.5),
        3.6, 1.8, 13.0,
        "Approximate normals (memory); used only to check against Yan et al. 2016 / Li et al. 2020.",
    ),
}


def _interp_monthly(vals) -> np.ndarray:
    doy = np.arange(365)
    x = np.concatenate([MID_DOY - 365, MID_DOY, MID_DOY + 365])
    y = np.concatenate([vals, vals, vals])
    return np.interp(doy, x, y)


def synth_year(cl: Climate, seed: int) -> np.ndarray:
    """8760 hourly temperatures, Jan 1 .. Dec 31."""
    rng = np.random.default_rng(seed)
    mean_d = _interp_monthly(cl.monthly_mean_c)
    amp_d = _interp_monthly(cl.diurnal_half_range_c)
    w = 0.5 * (1 + np.cos(2 * np.pi * (np.arange(365) - 15) / 365))  # 1 in mid-January
    sd_d = cl.sigma_summer + (cl.sigma_winter - cl.sigma_summer) * w
    eps = rng.standard_normal(365)
    a = np.zeros(365)
    for d in range(1, 365):
        a[d] = cl.ar1 * a[d - 1] + np.sqrt(1 - cl.ar1**2) * eps[d]
    daily = mean_d + sd_d * a
    diurnal = np.cos(2 * np.pi * (np.arange(24) - 15) / 24)  # warmest at 15:00
    return (daily[:, None] + amp_d[:, None] * diurnal[None, :]).reshape(-1)


def chained_years(cl: Climate, n_years: int, seed0: int = 1000) -> np.ndarray:
    """Hourly series: a half-year warm-up (Jul-Dec of year 0) then n_years calendar years."""
    years = [synth_year(cl, seed0 + i) for i in range(n_years + 1)]
    warmup = years[0][181 * 24:]
    return np.concatenate([warmup] + years[1:])


def load_csv(path: str, column: str = "temp_c") -> np.ndarray:
    """Read an hourly temperature series (degC) from a CSV with a header row."""
    with open(path, newline="") as f:
        return np.array([float(row[column]) for row in csv.DictReader(f)])


def freezing_degree_days(t_hourly: np.ndarray) -> float:
    return float(np.clip(-t_hourly, 0, None).sum() / 24)
