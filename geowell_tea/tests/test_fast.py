"""Fast calculator: matches the full model on the presets and reports clear errors."""
import pytest

from geowell_tea.fast import PRESETS, preset_inputs, run

CASE_A = list(PRESETS)[0]
CASE_B = list(PRESETS)[1]


def test_case_a_matches_full_model():
    r = run(preset_inputs(CASE_A, cost_level="base"), workers=1)
    assert r.ok and r.best["design"].startswith("T_HP")
    assert r.best["lcoh"] == pytest.approx(298.9, rel=0.03)  # full grid: $298.9/MWh


def test_case_b_full_coverage_needs_ku_44():
    strict = run(preset_inputs(CASE_B, cost_level="base", full_coverage=True), workers=1)
    field = run(preset_inputs(CASE_B, cost_level="base", full_coverage=True, ku_validated=4.4), workers=1)
    assert field.ok and field.best["lcoh"] == pytest.approx(125.0, rel=0.03)
    assert (not strict.ok) or strict.warnings  # strict: no validated full-coverage design


def test_direct_in_cold_well_is_an_error():
    r = run(preset_inputs(CASE_A, config="direct", T_bottom_C=50.0), workers=1)
    assert not r.ok and "too cold" in r.errors[0]


def test_hybrid_warning_and_waterfall():
    r = run(preset_inputs(CASE_A), workers=1)
    assert any("machinery room" in w for w in r.warnings)
    assert not any("Mach >" in w or "compressib" in w for w in r.warnings)
    assert list(r.waterfall.lcoh) == sorted(r.waterfall.lcoh, reverse=True)


def test_app_template_and_assumptions_table():
    from geowell_tea.fast import baked_in_assumptions
    r = run(preset_inputs(), workers=1)  # neutral template, no case preset
    assert r.ok
    a = baked_in_assumptions()
    assert not a.parameter.isin(["depth", "casing_id", "electricity_price", "discount_rate", "vit_per_m"]).any()
    assert a.value.map(type).eq(str).all()
