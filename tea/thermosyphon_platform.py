"""Thermosyphon platform ("Project Cryo") TEA, v2, on the standard framework.

Markets are sized as addressable installed value per year at incumbent prices,
so one cost structure serves all of them:

    revenue       = installed value x (1 - price discount)
    cost of sales = installed value x incumbent cost share x sum_c(share_c x multiplier_c)

Each component c (hardware, install, logistics, engineering) has a NOAK cost
reduction target and a learning rate. Its multiplier falls from FOAK to NOAK
with cumulative installed value (Wright's law) and stays at NOAK after.
Service revenue (monitoring, maintenance) is earned on the installed base.
Glacier grants are cost-reimbursed research funding.
"""
from __future__ import annotations

from .finance import crf, irr, npv
from .framework.learning import cost_multiplier
from .framework.result import FunctionalUnit, KillMetric, StandardResult, YearRow
from .framework.uncertainty import breakeven

COMPONENTS = ("hardware", "install", "logistics", "engineering")
STREAMS = ("foundations", "cold_bank", "remote", "roads", "mining")


def _noak_multiplier(v, c: str) -> float:
    m = 1 - v[f"cost.noak_reduction_{c}"]
    if c in ("hardware", "install"):
        m /= v["performance.heat_removal_multiplier"]
    return m


def component_multipliers(v, experience: float) -> dict[str, float]:
    return {
        c: cost_multiplier(experience, v["learning.noak_experience"], _noak_multiplier(v, c), v[f"learning.rate_{c}"])
        for c in COMPONENTS
    }


def blended(v, mults: dict[str, float]) -> float:
    """Cost of sales per $ of installed value at incumbent prices."""
    return v["company.incumbent_cost_share"] * sum(v[f"cost.share_{c}"] * mults[c] for c in COMPONENTS)


def market_values(v) -> dict[str, float]:
    """Our addressable installed value per year at full ramp (incumbent prices)."""
    area = v["foundations.dc_mw_per_year"] * v["foundations.adoption"] * v["foundations.m2_per_mw"] + v["foundations.other_m2_per_year"]
    return {
        "foundations": area * v["foundations.price_per_m2"] * v["foundations.share"],
        "cold_bank": v["cold_bank.mw_per_year"] * v["cold_bank.value_per_mw"] * v["cold_bank.share"],
        "remote": v["remote.sites_per_year"] * v["remote.price_per_site"] * v["remote.share"],
        "roads": v["roads.km_per_year"] * v["roads.price_per_km"] * v["roads.share"],
        "mining": v["mining.addressable_per_year"] * v["mining.share"],
    }


def functional_units(v) -> list[FunctionalUnit]:
    r = v["finance.customer_discount_rate"]
    d = v["company.price_discount"]
    noak_cost = blended(v, {c: _noak_multiplier(v, c) for c in COMPONENTS})  # per $ incumbent price
    mon = v["services.monitoring_fee"]

    def annual(price: float, life: float, failure: float, extra: float = 0.0) -> float:
        return price * crf(r, life) + failure * price + mon * price + extra

    p = v["foundations.price_per_m2"]
    life_f = v["foundations.life"]
    found = FunctionalUnit(
        "Permafrost foundation", "$/m2 protected per yr",
        {
            "Entrant at NOAK price": annual(p * (1 - d), life_f, v["reliability.failure_rate_entrant"]),
            "Incumbent thermosyphons": annual(p, life_f, v["reliability.failure_rate_incumbent"]),
            "Entrant if priced at NOAK cost": annual(p * noak_cost, life_f, v["reliability.failure_rate_entrant"]),
        },
        "Alternatives such as gravel pads or piles can't be priced per m2 from public data, so BAU here is the incumbent thermosyphon system.",
    )

    k = v["roads.price_per_km"]
    life_r = v["roads.life"]
    repair = v["roads.repair_per_km_year"]
    residual = v["roads.residual_repair"] * repair
    roads = FunctionalUnit(
        "Road or runway on warm permafrost", "$/km protected per yr",
        {
            "Entrant at NOAK price": annual(k * (1 - d), life_r, v["reliability.failure_rate_entrant"], residual),
            "Repair as it settles": repair,
            "Air-convection embankment": v["roads.ace_per_km"] * crf(r, life_r) + residual,
            "Incumbent thermosyphons": annual(k, life_r, v["reliability.failure_rate_incumbent"], residual),
            "Entrant if priced at NOAK cost": annual(k * noak_cost, life_r, v["reliability.failure_rate_entrant"], residual),
        },
        "Thermosyphons are only chosen where repair or air-convection can't hold the road (warm, ice-rich permafrost).",
    )
    return [found, roads]


def run(v) -> StandardResult:
    horizon = int(v["finance.horizon"])
    rd_years = int(round(v["company.rd_years"]))
    ramp = v["company.ramp"]
    markets = market_values(v)
    full = sum(markets.values())
    disc = v["company.price_discount"]
    attach = v["services.attach_rate"]

    experience = v["learning.first_year_experience"]
    installed_base = 0.0
    cumulative = 0.0
    rows: list[YearRow] = []
    learning_investment = 0.0
    noak_year = None
    noak_mults = {c: _noak_multiplier(v, c) for c in COMPONENTS}

    for t in range(1, horizon + 1):
        streams = {s: 0.0 for s in STREAMS}
        k = t - rd_years
        if k >= 1:
            share = ramp[min(k, len(ramp)) - 1] * (1 + v["company.market_growth"]) ** (k - 1)
            installed = share * full
            streams = {s: share * markets[s] * (1 - disc) for s in STREAMS}
            phase = "commercial"
        else:
            installed = 0.0
            phase = "R&D"

        mults = component_multipliers(v, experience)
        unit_cost = blended(v, mults)
        cost_of_sales = installed * unit_cost
        learning_investment += installed * (unit_cost - blended(v, noak_mults))

        monitoring = installed_base * attach * v["services.monitoring_fee"]
        maintenance = installed_base * attach * v["services.maintenance_fee"]
        service_cost = monitoring * (1 - v["services.monitoring_margin"]) + maintenance * (1 - v["services.maintenance_margin"])
        grants = v["glacier.grants"]
        streams.update(monitoring=monitoring, maintenance=maintenance, glacier_grants=grants)

        revenue = sum(streams.values())
        cos = cost_of_sales + service_cost + grants  # grants pay for research of equal cost
        gross = revenue - cos
        opex = v["company.rd_opex"] if phase == "R&D" else v["company.commercial_opex"]
        ebit = gross - opex
        cumulative += ebit
        rows.append(YearRow(t, phase, revenue, cos, gross, opex, ebit, cumulative,
                            unit_cost / v["company.incumbent_cost_share"], streams))

        experience += installed
        installed_base += installed
        if noak_year is None and experience >= v["learning.noak_experience"]:
            noak_year = t

    cash = [r.ebit for r in rows]
    rate = v["finance.company_discount_rate"]
    went_negative = False
    breakeven_year = None
    for r in rows:
        if r.cumulative_cash < 0:
            went_negative = True
        elif went_negative and breakeven_year is None:
            breakeven_year = r.year

    foak = component_multipliers(v, v["learning.first_year_experience"])
    fus = functional_units(v)
    noak_reduction = 1 - blended(v, noak_mults) / v["company.incumbent_cost_share"]
    roads_fu = fus[1].options
    big = v["scale.big_enough_revenue"]
    kills = [
        KillMetric("NOAK installed-cost reduction vs incumbent", noak_reduction, 0.30, "fraction", noak_reduction >= 0.30,
                   "Phase 1 kill: no meaningful cost advantage. 30% threshold is a judgment."),
        KillMetric("10x test: incumbent life-cycle cost / ours at NOAK cost (foundations)",
                   fus[0].options["Incumbent thermosyphons"] / fus[0].options["Entrant if priced at NOAK cost"], 10.0, "x",
                   fus[0].options["Incumbent thermosyphons"] / fus[0].options["Entrant if priced at NOAK cost"] >= 10,
                   "The Project Cryo target"),
        KillMetric("Roads: our NOAK cost vs repairing as it settles",
                   roads_fu["Entrant if priced at NOAK cost"] / roads_fu["Repair as it settles"], 1.0, "x (<=1 to win)",
                   roads_fu["Entrant if priced at NOAK cost"] <= roads_fu["Repair as it settles"]),
        KillMetric("Revenue at full scale vs big-enough line", rows[-1].revenue / big, 1.0, "x", rows[-1].revenue >= big),
    ]
    return StandardResult(
        project="Thermosyphon platform (Project Cryo)",
        years=rows,
        npv=npv(rate, cash),
        irr=irr(cash),
        peak_cash_need=-min(0.0, min(r.cumulative_cash for r in rows)),
        breakeven_year=breakeven_year,
        full_scale_revenue=rows[-1].revenue,
        functional_units=fus,
        learning={c: (foak[c], noak_mults[c]) for c in COMPONENTS},
        noak_year=noak_year,
        learning_investment=learning_investment,
        kill_metrics=kills,
        notes=[
            "Cash flow is EBIT: no taxes, working capital or capital equipment, and no terminal value.",
            "Customer price is value-based (incumbent price less a discount), so our cost cuts become margin, not lower customer cost.",
        ],
    )


def breakevens(v) -> list[dict]:
    """Project-specific break-even questions for the report."""
    npv_of = lambda x: run(x).npv  # noqa: E731

    def roads_gap(x):
        o = functional_units(x)[1].options
        return o["Entrant if priced at NOAK cost"] - o["Repair as it settles"]

    out = []
    for key, lo, hi, label in [
        ("foundations.dc_mw_per_year", 0, 20_000, "Arctic data center MW/yr for NPV = 0"),
        ("company.price_discount", 0.0, 0.9, "Price discount at which NPV = 0"),
        ("mining.addressable_per_year", 0, 2_000_000_000, "Mining freeze-work $/yr for NPV = 0"),
    ]:
        out.append({"question": label, "input": key, "answer": breakeven(v, key, npv_of, 0.0, lo, hi), "base": v[key]})
    out.append({"question": "Incumbent road cost per km at which our NOAK cost equals repairing as it settles",
                "input": "roads.price_per_km", "answer": breakeven(v, "roads.price_per_km", roads_gap, 0.0, 1.0, 1e8),
                "base": v["roads.price_per_km"]})
    return out
