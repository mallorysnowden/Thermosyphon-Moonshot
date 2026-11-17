"""Thermosiphon platform TEA.

Four revenue streams:

A. Foundations for Arctic data centers built on permafrost.
B. Cold bank: thermosiphons freeze ground in winter; the data center draws
   that cold in summer to replace trim chillers.
C. Remote sites (telecom towers, satellite antennas, weather stations):
   thermosiphon foundation packages plus a monitoring subscription.
D. Glacier research grants (cost-reimbursed, no profit counted).

All money is in today's dollars, pre-tax, with no working capital.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .finance import crf, npv

V = dict  # a flat mapping of "section.name" -> value


@dataclass
class Foundations:
    entrant_cost_per_m2: float
    entrant_price_per_m2: float
    gross_margin: float
    area_m2_per_year: float
    revenue: float
    gross_profit: float
    share_of_dc_build_cost: float
    revenue_per_mw: float


@dataclass
class ColdBank:
    trim_mwh_per_year: float
    units_per_year: float
    entrant_unit_cost: float
    revenue: float
    gross_profit: float
    gross_margin: float
    units_per_mw: float
    revenue_per_mw: float
    customer_cost_cold_bank: float  # $/MWh_th
    customer_cost_chiller: float  # $/MWh_th
    customer_saving: float


@dataclass
class RemoteSites:
    sites_per_year: float
    foundation_revenue: float
    foundation_gross_profit: float
    subscription_per_site: float


@dataclass
class YearRow:
    year: int
    ramp: float
    sites_in_service: float
    revenue: float
    gross_profit: float
    operating_cost: float
    ebit: float
    discount_factor: float
    present_value: float


@dataclass
class Result:
    foundations: Foundations
    cold_bank: ColdBank
    remote_sites: RemoteSites
    grants: float
    years: list[YearRow] = field(default_factory=list)
    npv: float = 0.0

    @property
    def revenue_per_mw_both(self) -> float:
        """Revenue per MW if a data center buys both foundations and a cold bank."""
        return self.foundations.revenue_per_mw + self.cold_bank.revenue_per_mw


def chiller_cost_per_mwh(v: V, trim_hours: float | None = None) -> float:
    """Customer's cost of trim cooling from a chiller, $/MWh_th.

    Electricity over COP, plus chiller capex and the generation capacity needed
    to run it, annualized and spread over the trim hours.
    """
    hours = v["cold_bank.trim_hours"] if trim_hours is None else trim_hours
    cop = v["cold_bank.chiller_cop"]
    annualize = crf(v["general.customer_discount_rate"], v["cold_bank.equipment_life"])
    capex_per_kw_th = v["cold_bank.chiller_capex"] + v["cold_bank.generation_capex"] / cop
    return v["cold_bank.electricity_price"] / cop + capex_per_kw_th * annualize * 1000 / hours


def cold_bank_cost_per_mwh(v: V, at_cost: bool = False) -> float:
    """Customer's (or our) annualized cost of cold-bank cooling, $/MWh_th."""
    annualize = crf(v["general.customer_discount_rate"], v["cold_bank.thermosiphon_life"])
    if at_cost:
        unit_cost = v["cold_bank.unit_cost"] * (1 - v["cold_bank.entrant_cost_reduction"])
        return unit_cost / v["cold_bank.mwh_per_unit"] * annualize
    return v["cold_bank.price_per_mwh_year"] * annualize


def foundations(v: V) -> Foundations:
    price_inc = v["foundations.incumbent_price_per_m2"]
    cost = price_inc * v["foundations.incumbent_cost_share"] * (1 - v["foundations.entrant_cost_reduction"])
    price = price_inc * (1 - v["foundations.entrant_price_discount"])
    area = v["foundations.dc_mw_per_year"] * v["foundations.market_share"] * v["foundations.footprint_m2_per_mw"]
    return Foundations(
        entrant_cost_per_m2=cost,
        entrant_price_per_m2=price,
        gross_margin=(price - cost) / price,
        area_m2_per_year=area,
        revenue=area * price,
        gross_profit=area * (price - cost),
        share_of_dc_build_cost=v["foundations.footprint_m2_per_mw"] * price_inc / v["foundations.dc_build_cost_per_mw"],
        revenue_per_mw=v["foundations.footprint_m2_per_mw"] * price,
    )


def cold_bank(v: V) -> ColdBank:
    trim_per_mw = v["cold_bank.trim_share"] * v["cold_bank.trim_hours"]  # MWh_th per MW of IT
    trim = v["cold_bank.dc_mw_per_year"] * v["cold_bank.market_share"] * trim_per_mw
    units = trim / v["cold_bank.mwh_per_unit"]
    unit_cost = v["cold_bank.unit_cost"] * (1 - v["cold_bank.entrant_cost_reduction"])
    revenue = trim * v["cold_bank.price_per_mwh_year"]
    gross_profit = revenue - units * unit_cost
    bank = cold_bank_cost_per_mwh(v)
    chiller = chiller_cost_per_mwh(v)
    return ColdBank(
        trim_mwh_per_year=trim,
        units_per_year=units,
        entrant_unit_cost=unit_cost,
        revenue=revenue,
        gross_profit=gross_profit,
        gross_margin=gross_profit / revenue if revenue else 0.0,
        units_per_mw=trim_per_mw / v["cold_bank.mwh_per_unit"],
        revenue_per_mw=trim_per_mw * v["cold_bank.price_per_mwh_year"],
        customer_cost_cold_bank=bank,
        customer_cost_chiller=chiller,
        customer_saving=1 - bank / chiller,
    )


def remote_sites(v: V) -> RemoteSites:
    sites = v["remote_sites.sites_per_year"] * v["remote_sites.market_share"]
    revenue = sites * v["remote_sites.foundation_price"]
    return RemoteSites(
        sites_per_year=sites,
        foundation_revenue=revenue,
        foundation_gross_profit=revenue * (1 - v["remote_sites.cogs_share"]),
        subscription_per_site=v["remote_sites.subscription"],
    )


def run(v: V) -> Result:
    a, b, c = foundations(v), cold_bank(v), remote_sites(v)
    grants = v["glacier.grants"]
    rate = v["general.company_discount_rate"]
    opex = v["general.operating_cost"]
    ramp = v["general.ramp"]

    full_revenue = a.revenue + b.revenue + c.foundation_revenue
    full_gross_profit = a.gross_profit + b.gross_profit + c.foundation_gross_profit

    rows: list[YearRow] = []
    cumulative_ramp = 0.0
    for i, r in enumerate(ramp):
        year = i + 1
        cumulative_ramp += r
        sites = cumulative_ramp * c.sites_per_year
        subscriptions = sites * c.subscription_per_site
        revenue = r * full_revenue + subscriptions + grants
        gross_profit = r * full_gross_profit + subscriptions * v["remote_sites.subscription_margin"]
        ebit = gross_profit - opex
        df = 1 / (1 + rate) ** year
        rows.append(YearRow(year, r, sites, revenue, gross_profit, opex, ebit, df, ebit * df))

    result = Result(a, b, c, grants, rows)
    result.npv = npv(rate, [row.ebit for row in rows])
    return result


def sensitivity(params, v: V | None = None) -> list[dict]:
    """One-at-a-time sweep: each input with a low/high moves alone; others stay at base.

    Returns rows sorted by NPV swing, largest first.
    """
    from .inputs import base_values

    base = base_values(params) if v is None else dict(v)
    rows = []
    for key, p in params.items():
        if p.low is None or p.high is None or isinstance(p.base, list):
            continue
        low = run({**base, key: p.low}).npv
        high = run({**base, key: p.high}).npv
        rows.append({
            "input": key,
            "low_value": p.low,
            "npv_at_low": low,
            "high_value": p.high,
            "npv_at_high": high,
            "swing": abs(high - low),
        })
    rows.sort(key=lambda r: r["swing"], reverse=True)
    return rows
