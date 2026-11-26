"""The four case studies and their business-as-usual (BAU) cooling.

Each case gives an hourly cooling load (W thermal), the warmest store water the
application can still use, and the BAU plant the ice bank would replace.
"""
from __future__ import annotations

from dataclasses import dataclass, replace, field
from typing import Callable

import numpy as np


def day_of_year(n_hours: int, start_doy: int = 181) -> np.ndarray:
    """Day of year for each hour of a series starting Jul 1 (doy 181, 0-based)."""
    days = (start_doy + np.arange(n_hours) // 24)
    return days % 365  # years are 365 days; the warm-up half-year has 184 days


_MONTH_STARTS = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30])


def on_peak(n_hours: int, start_weekday: int = 0) -> np.ndarray:
    """Utility on-peak hours: 9 a.m.-9 p.m., Monday-Friday (Xcel TOD definition; holidays ignored).
    The series starts on Jul 1 at 00:00, taken as a Monday."""
    h = np.arange(n_hours)
    hod = h % 24
    wd = (h // 24 + start_weekday) % 7
    return (hod >= 9) & (hod < 21) & (wd < 5)


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
    # How the BAU plant rejects heat: "air" (dry/air-cooled condensers) or "tower" (cooling tower or
    # evaporative condenser, which uses water and has condenser-water pumps and fans)
    heat_rejection: str = "air"
    water_usd_m3: float = 0.0           # makeup water, $/m3
    sewer_usd_m3: float = 0.0           # sewer, $/m3 of water billed for sewer
    sewer_on: str = "makeup"            # "makeup" (billed on all water used) or "blowdown" (evaporation deduct meter)
    water_note: str = ""
    # Time-of-use energy prices as multiples of elec_usd_kwh (1.0 / 1.0 = flat), and demand billing:
    # TOU tariffs bill on-peak demand at demand_summer/winter plus off-peak demand above on-peak at demand_off_excess
    tou: bool = False
    tou_on_mult: float = 1.0
    tou_off_mult: float = 1.0
    demand_off_excess: float = 0.0
    tou_note: str = ""
    # Data-center facility water (cases A, E): supply / return temperatures, degC
    dc_supply: float = 32.0
    dc_return: float = 42.0
    # Heating (hospital cases B, F). heat_peak_w = 0 means a cooling-only case. Hourly heat demand is
    # heat_peak_w x [base + (1 - base) x clip((t_balance - t) / (t_balance - t_design), 0, 1)]: a year-round floor
    # (reheat, domestic hot water) plus space heating that grows linearly below the balance point.
    heat_peak_w: float = 0.0
    heat_base_frac: float = 0.25
    heat_t_balance: float = 15.0
    heat_t_design: float = -26.0
    heat_bau: str = "gas"               # "gas": boilers serve heat; "ashp": air-to-water heat pumps (electrified)
    gas_usd_mwh: float = 23.0           # $ per MWh of gas (HHV)
    boiler_eff: float = 0.82
    heat_note: str = ""

    @property
    def heating(self) -> bool:
        return self.heat_peak_w > 0

    def heat_w(self, t_air: np.ndarray) -> np.ndarray:
        """Hourly heating demand, W (zeros for cooling-only cases)."""
        if not self.heating:
            return np.zeros_like(t_air, dtype=float)
        f = np.clip((self.heat_t_balance - t_air) / (self.heat_t_balance - self.heat_t_design), 0, 1)
        return self.heat_peak_w * (self.heat_base_frac + (1 - self.heat_base_frac) * f)

    def prices(self) -> tuple[float, float]:
        """($/kWh on-peak, $/kWh off-peak)."""
        return self.elec_usd_kwh * self.tou_on_mult, self.elec_usd_kwh * self.tou_off_mult

    def aux_kw_per_kwth(self) -> float:
        """BAU auxiliary electric draw per kW of cooling, not in the chiller COP: chilled-water pumps (0.015),
        plus condenser-water pumps and tower fans (0.015 each) for tower plants."""
        return 0.045 if self.heat_rejection == "tower" else 0.015

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
    frac = (t + DC_APPROACH - c.dc_supply) / (c.dc_return - c.dc_supply)
    return c.peak_w * np.clip(frac, 0, 1)


def _dc_cop(c, t):
    te = c.dc_supply - 3 + 273.15
    if c.heat_rejection == "tower":
        # Condensing ~11 K above wet bulb; wet bulb proxy = dry bulb minus a depression that grows with heat
        wb = t - np.clip(0.3 * t, 1.0, 10.0)
        tc = np.maximum(wb + 11 + 273.15, te + 5)
    else:
        tc = np.maximum(t + 12 + 273.15, te + 5)
    return np.clip(0.35 * te / (tc - te), 2.5, 8.0)


def awhp_cop(t_air: np.ndarray, t_supply: float = 55.0) -> np.ndarray:
    """Air-to-water heat pump COP: 45% of Carnot, condensing 3 K above supply, evaporating 8 K below the air,
    clipped to 1.3-4.5 (cold-climate units at -25 degC deliver about 1.5)."""
    tc = t_supply + 3 + 273.15
    te = np.minimum(t_air + 273.15 - 8, tc - 15)
    return np.clip(0.45 * tc / (tc - te), 1.3, 4.5)


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


LOADS = {"A": _dc_load, "B": _hosp_load, "C": _salmon_load, "D": _process_load, "E": _dc_load, "F": _hosp_load}
COPS = {"A": _dc_cop, "B": lambda c, t: np.full_like(t, 4.7, dtype=float),
        "C": lambda c, t: np.full_like(t, 3.0, dtype=float), "D": _process_cop, "E": _dc_cop,
        "F": lambda c, t: np.full_like(t, 4.7, dtype=float)}
DESIGN_T = {"A": 35.0, "B": 32.0, "C": 15.0, "D": 32.0, "E": 35.0, "F": 32.0}

CASES = {
    "A": Case("A", "AI data center, 100 MW IT (Fargo / Ellendale, ND)", "fargo", 100e6, 27.0, 230.0, 1.2, 0.075,
              "Big, growing market; chillers sit idle except on hot days, so the ice bank competes with idle capacity.",
              "Trim above what dry coolers can do at 32 degC supply / 42 degC return, 8 K approach. "
              "Electricity 7.5 c/kWh (ND industrial 7.25 c, EIA 2024). Air-cooled trim chillers (no water); "
              "a water-cooled tower variant is a sensitivity.",
              water_usd_m3=5.05 / 3.785, sewer_usd_m3=2.55 / 3.785,
              water_note="Fargo water $5.05 per 1,000 gal above 2 million gal/month, sewer $2.55 per 1,000 gal billed "
                         "on all water used (fargond.gov). Used only in the tower sensitivity.",
              demand_summer=13.28, demand_winter=8.93,
              tou=True, tou_on_mult=9.21 / 7.5, tou_off_mult=6.56 / 7.5, demand_off_excess=2.10,
              tou_note="Xcel ND D17 energy 5.674 c on-peak / 3.018 c off-peak plus a flat 3.54 c fuel/rider adder that "
                       "keeps the 7.5 c all-hours average; off-peak demand above on-peak billed at $2.10/kW.",
              demand_note="Xcel Energy ND General Time of Day (D17) on-peak demand, $15.38 Jun-Sep / $11.03 Oct-May, "
                          "less the $2.10 transmission-voltage discount (NDPSC PU-24-376 tariff sheets)."),
    "B": Case("B", "Hospital, 3.5 MW cooling + 1.9 MW heating (Minneapolis, MN), gas-heated BAU", "minneapolis",
              3.5e6, 4.0, 430.0, 1.5, 0.125,
              "Heating and cooling: a heat pump that draws its heat from the pit makes ice all winter.",
              "Cooling: water-cooled chiller plant with cooling towers, 3 x 50%, ~$1,500/ton, COP 4.7. "
              "Heating: gas boilers at 82%, gas $7.00/Mcf (MN commercial $6.44/Mcf, Nov 2025, EIA). "
              "Electricity 12.5 c/kWh (MN commercial 12.15 c).",
              heat_peak_w=1.91e6, heat_bau="gas", gas_usd_mwh=7.0 / (1.037 * 0.29307),
              heat_note="300,000 ft2 hospital (about 300 ft2 per ton of cooling) using 80 kBtu/ft2-yr of delivered "
                        "space heat, reheat and hot water (DOE reference hospitals: 52-108), 7,000 MWh/yr: a 25% "
                        "year-round floor plus space heat below 15 degC, peaking at 1.9 MW at -26 degC. Steam for "
                        "sterilisers and humidifiers stays on boilers in every option and is left out. Boilers stay "
                        "in every option as backup, so their capital cost cancels.",
              heat_rejection="tower", water_usd_m3=3.82 * 1.09025 / 2.832, sewer_usd_m3=5.63 / 2.832,
              water_note="Minneapolis water $3.82 per 100 ft3 plus 9.025% water tax, sewer $5.63 per 100 ft3; "
                         "commercial sewer is billed on actual water use (minneapolismn.gov).",
              demand_summer=19.86, demand_winter=15.27,
              tou=True, tou_on_mult=14.86 / 12.5, tou_off_mult=11.19 / 12.5, demand_off_excess=3.00,
              tou_note="On/off-peak spread from Xcel's General TOD energy charges (8.269 / 4.594 c, SD rate book, used "
                       "as a proxy for MN) plus a flat adder keeping the 12.5 c average; off-peak excess demand $3/kW.",
              demand_note="Xcel Energy MN General Time of Day demand, $19.86 summer / $15.27 winter "
                          "(2026 rates proposed in the MN electric rate case)."),
    "C": Case("C", "Salmon processor, 1.5 MWth (Naknek, Bristol Bay, AK)", "dillingham", 1.5e6, 1.5, 710.0, 1.2, 0.45,
              "Best seasonal match: long freezing winter, six-week summer burst, diesel power.",
              "Ammonia refrigeration with evaporative condensers, COP 3. Electricity 45 c/kWh (diesel self-generation; Naknek fuel $6.75/gal). "
              "Ice alone chills to about +1 degC, not the -1 degC of refrigerated seawater.",
              heat_rejection="tower", water_usd_m3=1.0, sewer_usd_m3=0.0,
              water_note="Self-supplied well water with treatment, $1.00/m3 (assumption); no municipal sewer.",
              demand_summer=12.0, demand_winter=12.0,
              demand_note="Nushagak Cooperative (Dillingham) Large Commercial Seasonal rate, $12.00/kW; Naknek Electric's "
                          "tariff is not published online. A self-generating plant pays none (generators are in the "
                          "electrical service cost)."),
    "D": Case("D", "Year-round process cooling, 1 MWth at 5 degC (Fargo, ND)", "fargo", 1.0e6, 3.0, 430.0, 1.2, 0.075,
              "Tests cooling all year: thermosiphons serve the load directly in winter and the store carries summer.",
              "BAU: air-cooled chiller plus a dry-cooler economiser that cools for free below -3 degC (no water).",
              extra_bau_capex_usd_kw=60.0, demand_summer=15.38, demand_winter=11.03,
              demand_note="Xcel Energy ND General Service (D16) at secondary voltage, $15.38 Jun-Sep / $11.03 Oct-May "
                          "(NDPSC PU-24-376 tariff sheets)."),
}

# Variant of A: an air-cooled data hall (chilled water to CRAH coils at 18 / 26 degC). Same site, plant cost,
# tariffs and electrical assumptions; dry coolers carry the load alone below ~10 degC outside, chillers or ice
# do the rest, and pit water is only useful up to 13 degC (5 K heat-exchanger approach).
CASES["E"] = replace(
    CASES["A"], key="E", title="Air-cooled data center, 100 MW IT (Fargo / Ellendale, ND)", t_use_max=13.0,
    dc_supply=18.0, dc_return=26.0,
    why="Tests an air-cooled hall: far more chiller hours, but pit water must stay below 13 degC.",
    notes="Chilled water 18 degC supply / 26 degC return to air handlers, 8 K dry-cooler approach; otherwise as A.")

# Variant of B: the electrified hospital. Without the ice bank, air-to-water heat pumps (sized for the peak, $600/kW)
# carry the heating; the boilers stay only as backup. The ice-bank options replace part of that air-source fleet
# with the pit-sourced heat pump.
CASES["F"] = replace(
    CASES["B"], key="F", title="Hospital, 3.5 MW cooling + 1.9 MW heating (Minneapolis, MN), electrified BAU",
    heat_bau="ashp",
    why="Same hospital, but the comparison is an all-electric plant with air-source heat pumps.",
    notes=CASES["B"].notes.replace("Heating: gas boilers at 82%, gas $7.00/Mcf (MN commercial $6.44/Mcf, Nov 2025, EIA).",
                                   "Heating: air-to-water heat pumps, $600/kW, COP about 1.6 at -26 degC, 2.7 at 10 degC "
                                   "(55 degC supply); boilers kept as backup only."))
