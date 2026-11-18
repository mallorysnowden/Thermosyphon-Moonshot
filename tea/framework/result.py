"""The standard result every project model returns."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class YearRow:
    year: int
    phase: str
    revenue: float
    cost_of_sales: float
    gross_profit: float
    operating_cost: float
    ebit: float
    cumulative_cash: float
    cost_multiplier: float  # blended cost vs incumbent; 1.0 = incumbent cost
    revenue_by_stream: dict[str, float] = field(default_factory=dict)
    capex: float = 0.0  # capital spent this year (cumulative_cash already nets it out)


@dataclass
class FunctionalUnit:
    """Customer life-cycle cost of the project vs BAU options, in one unit."""
    label: str
    unit: str
    options: dict[str, float]  # name -> annualized cost per unit; first entry is the project
    note: str = ""

    @property
    def project(self) -> tuple[str, float]:
        name = next(iter(self.options))
        return name, self.options[name]

    @property
    def best_bau(self) -> tuple[str, float]:
        others = {k: v for k, v in list(self.options.items())[1:]}
        name = min(others, key=others.get)
        return name, others[name]


@dataclass
class KillMetric:
    name: str
    value: float
    threshold: float
    unit: str
    passes: bool
    note: str = ""


@dataclass
class StandardResult:
    project: str
    years: list[YearRow]
    npv: float
    irr: float | None
    peak_cash_need: float
    breakeven_year: int | None
    full_scale_revenue: float
    functional_units: list[FunctionalUnit]
    learning: dict[str, tuple[float, float]]  # component -> (FOAK multiplier, NOAK multiplier)
    noak_year: int | None
    learning_investment: float  # extra cost paid above NOAK cost while learning
    kill_metrics: list[KillMetric]
    notes: list[str] = field(default_factory=list)
    tables: list[tuple[str, list[str], list[list[str]]]] = field(default_factory=list)  # (title, headers, rows)
