"""The four case studies and their business-as-usual (BAU) cooling.

Each case gives an hourly cooling load (W thermal), the warmest store water the
application can still use, and the BAU plant the ice bank would replace.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np


def day_of_year(n_hours: int, start_doy: int = 181) -> np.ndarray:
    """Day of year for each hour of a series starting Jul 1 (doy 181, 0-based)."""
    days = (start_doy + np.arange(n_hours) // 24)
    return days % 365  # years are 365 days; the warm-up half-year has 184 days


_MONTH_STARTS = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30])


def month_of_doy(doy: np.ndarray) -> np.ndarray:
    """Calendar month (0 = Jan ... 11 = Dec) for a 0-based day of a 365-day year."""
    return np.searchsorted(_MONTH_STARTS, np.asarray(doy), side="right") - 1


@dataclass(frozen=True)
class Case:
    key: str
    title: str
    climate: str
    peak_w: float                       # design peak cooling, W thermal
    t_use_max: float                    # warmest store water still useful, degC
    mech_usd_kw: float                  # BAU mechanical plant, installed $/kWth
    redundancy: float                   # BAU installed / peak (N+1)
    elec_usd_kwh: float
    why: str
    notes: str = ""
    extra_bau_capex_usd_kw: float = 0.0  # e.g. dry-cooler economiser the ice option doesn't need
    # Monthly demand charge on the chiller's peak electric draw, $/kW-month
    demand_summer: float = 0.0
    demand_winter: float = 0.0
    summer_months: tuple = (5, 6, 7, 8)   # 0-based: Jun-Sep
    demand_note: str = ""

    def demand_rates(self) -> np.ndarray:
        """$/kW for each calendar month (index 0 = Jan)."""
        r = np.full(12, self.demand_winter)
        r[list(self.summer_months)] = self.demand_summer
        return r

    def load_w(self, t_air: np.ndarray, doy: np.ndarray) -> np.ndarray:
        return LOADS[self.key](self, t_air, doy)

    def cop(self, t_air: np.ndarray) -> np.ndarray:
        return COPS[self.key](self, t_air)

    def peak_cop(self) -> float:
        return float(self.cop(np.array([DESIGN_T[self.key]]))[0])


# --- data center: trim cooling above what dry coolers can do --------------------
DC_SUPPLY, DC_RETURN, DC_APPROACH = 32.0, 42.0, 8.0


def _dc_load(c, t, doy):
    frac = (t + DC_APPROACH - DC_SUPPLY) / (DC_RETURN - DC_SUPPLY)
    return c.peak_w * np.clip(frac, 0, 1)


def _dc_cop(c, t):
    te = DC_SUPPLY - 3 + 273.15
    tc = np.maximum(t + 12 + 273.15, te + 5)
    return np.clip(0.35 * te / (tc - te), 2.5, 8.0)


# --- hospital: comfort + process chilled water, May-Sep --------------------------
def _hosp_load(c, t, doy):
    season = (doy >= 120) & (doy < 273)
    return c.peak_w * np.where(season, 0.15 + 0.85 * np.clip((t - 12.0) / 20.0, 0, 1), 0.0)


# --- salmon processor: six-week summer burst --------------------------------------
def _salmon_load(c, t, doy):
    on = (doy >= 175) & (doy < 217)
    return c.peak_w * np.where(on, 0.35 + 0.65 * np.exp(-0.5 * ((doy - 193) / 8.0) ** 2), 0.0)


# --- year-round process cooling (tests "cool all year") ---------------------------
def _process_load(c, t, doy):
    return np.full_like(t, c.peak_w, dtype=float)


def _process_cop(c, t):
    # Chiller at 5 degC supply; free cooling through a dry cooler below -3 degC (fans only)
    return np.where(t < -3.0, 50.0, 5.0)


LOADS = {"A": _dc_load, "B": _hosp_load, "C": _salmon_load, "D": _process_load}
COPS = {"A": _dc_cop, "B": lambda c, t: np.full_like(t, 4.7, dtype=float),
        "C": lambda c, t: np.full_like(t, 3.0, dtype=float), "D": _process_cop}
DESIGN_T = {"A": 35.0, "B": 32.0, "C": 15.0, "D": 32.0}

CASES = {
    "A": Case("A", "AI data center, 100 MW IT (Fargo / Ellendale, ND)", "fargo", 100e6, 27.0, 230.0, 1.2, 0.075,
              "Big, growing market; chillers sit idle except on hot days, so the ice bank competes with idle capacity.",
              "Trim above what dry coolers can do at 32 degC supply / 42 degC return, 8 K approach. "
              "Electricity 7.5 c/kWh (ND industrial 7.25 c, EIA 2024).",
              demand_summer=13.28, demand_winter=8.93,
              demand_note="Xcel Energy ND General Time of Day (D17) on-peak demand, $15.38 Jun-Sep / $11.03 Oct-May, "
                          "less the $2.10 transmission-voltage discount (NDPSC PU-24-376 tariff sheets)."),
    "B": Case("B", "Hospital / campus, 3.5 MWth (Minneapolis, MN)", "minneapolis", 3.5e6, 4.0, 430.0, 1.5, 0.125,
              "Control case: chillers run all summer on cheap power, so it should lose.",
              "Water-cooled chiller plant, 3 x 50%, ~$1,500/ton, COP 4.7. Electricity 12.5 c/kWh (MN commercial 12.15 c).",
              demand_summer=19.86, demand_winter=15.27,
              demand_note="Xcel Energy MN General Time of Day demand, $19.86 summer / $15.27 winter "
                          "(2026 rates proposed in the MN electric rate case)."),
    "C": Case("C", "Salmon processor, 1.5 MWth (Naknek, Bristol Bay, AK)", "dillingham", 1.5e6, 1.5, 710.0, 1.2, 0.45,
              "Best seasonal match: long freezing winter, six-week summer burst, diesel power.",
              "Ammonia refrigeration, COP 3. Electricity 45 c/kWh (diesel self-generation; Naknek fuel $6.75/gal). "
              "Ice alone chills to about +1 degC, not the -1 degC of refrigerated seawater.",
              demand_summer=12.0, demand_winter=12.0,
              demand_note="Nushagak Cooperative (Dillingham) Large Commercial Seasonal rate, $12.00/kW; Naknek Electric's "
                          "tariff is not published online. A self-generating plant pays none (generators are in the "
                          "electrical-service credit)."),
    "D": Case("D", "Year-round process cooling, 1 MWth at 5 degC (Fargo, ND)", "fargo", 1.0e6, 3.0, 430.0, 1.2, 0.075,
              "Tests cooling all year: thermosiphons serve the load directly in winter and the store carries summer.",
              "BAU: chiller plus a dry-cooler economiser that cools for free below -3 degC.",
              extra_bau_capex_usd_kw=60.0, demand_summer=15.38, demand_winter=11.03,
              demand_note="Xcel Energy ND General Service (D16) at secondary voltage, $15.38 Jun-Sep / $11.03 Oct-May "
                          "(NDPSC PU-24-376 tariff sheets)."),
}
