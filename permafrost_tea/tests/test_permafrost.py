from permafrost_tea.cases import BEAVER_CREEK, dry_creek_check
from permafrost_tea.model import Costs, Physics, Unit, incumbent_unit_cost, platform_unit_cost, winter_extraction_kwh
from permafrost_tea.run import evaluate


def test_dry_creek_calibration_within_budget():
    usd = dry_creek_check(Costs())
    assert 0.95e6 <= usd <= 1.75e6        # CAD 1.3-2.3M at 0.73


def test_warming_cuts_capacity():
    u = Unit(34, 19.5, 4.0, layout="inclined", spacing_m=7)
    p = Physics()
    assert winter_extraction_kwh(u, p, BEAVER_CREEK, 30) < winter_extraction_kwh(u, p, BEAVER_CREEK, 0)


def test_platform_hardware_cheaper_than_incumbent():
    u = Unit(12, 6, layout="thermopile")
    assert platform_unit_cost(u, Costs()) < incumbent_unit_cost(u, Costs())


def test_every_case_has_one_bau():
    for k in "ABCD":
        rows = evaluate(k, Costs(), Physics())
        assert sum("BAU" in r["option"] for r in rows) == 1
