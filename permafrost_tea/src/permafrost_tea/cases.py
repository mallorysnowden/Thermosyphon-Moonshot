"""Four permafrost cases: two new builds (thermosyphon integrated with the foundation) and two retrofits
(standalone thermosyphons). Each returns {option name: Bill} plus sizing notes.

Sources (opened Nov 24 2026; see the deep-dive doc's Sources list):
- Dry Creek, Alaska Highway: 58 sloped units at 7 m, 34 m evaporators in cased bores at ~11 deg, 19.5 m2
  radiators, Arctic Foundations of Canada, 2019-20 (SRK; ICOP 2024). Budget CAD 1.3-2.3M (Transport Canada /
  Yukon).  -> calibrates incumbent inclined drilling.
- UNAVCO CO2 thermopile monument, 4.5" x 20 ft: $1,700 unit, $5,000-14,000 drilling.  -> incumbent hardware.
- Arctic Foundations of Canada (Piling Canada 2019): refrigerated piles can cut a 30 m pile to 12-15 m.
- Stebbins, AK school (KNOM 2025): piles up to 60 ft (18 m) in warm permafrost.
- Ross River School, Yukon: ~CAD 1.2-2M per relevel (2015, 2017 est.), CAD 1.6M bid for crawlspace
  refrigeration (2019), ~CAD 8M spent 1998-2023 incl. ~CAD 1M inspections.
- Alaska school construction: ~$431/sq ft average, rural approaching $1,000/sq ft (Alaska Business 2021).
- Roads: Yukon ~CAD 30k/km/yr to repair permafrost sections; ACE ~CAD 1M/km (repo inputs, platform TEA).
- CSA S500:21 requires monitoring for thermosyphon foundations.
Anything not listed is an assumption, marked as such.
"""
from __future__ import annotations

import math
from dataclasses import replace

from .model import (Bill, Climate, Costs, Physics, Unit, USD_PER_CAD, add_engineering_and_mob, crf,
                    incumbent_unit_cost, pile_cost_per_m, platform_costs, size_units, ts_system,
                    winter_extraction_kwh)

# Climates (approximate 1991-2020 normals, assumption-grade; warming 0.5 C/decade, winter-heavy)
BETHEL = Climate("Bethel / Y-K Delta, AK (warm permafrost)", maat_c=-0.5, amp_c=14.0)
DEADHORSE = Climate("Deadhorse / Prudhoe Bay, AK", maat_c=-11.0, amp_c=17.5)
ROSS_RIVER = Climate("Ross River, YT", maat_c=-4.0, amp_c=19.5)
BEAVER_CREEK = Climate("Beaver Creek, YT (Alaska Highway)", maat_c=-5.5, amp_c=21.0)

RELEVEL_USD = 1.2e6 * USD_PER_CAD      # Ross River 2017 estimate, CAD 1.2M


def _design_year(c: Costs) -> float:
    return c.life        # size to end-of-life climate


def floor_heat_kwh_m2(t_in: float, ins_m: float = 0.20, k_ins: float = 0.033, t_ground: float = -2.0,
                      edge_kwh_m2: float = 10.0) -> float:
    r = ins_m / k_ins + 0.5
    return (t_in - t_ground) / r * 8760 / 1000 + edge_kwh_m2


# ------------------------------------------------------------------- Case A: new elevated building, piles
def case_a(c: Costs, p: Physics, *, area_m2=1500.0, m2_per_pile=12.0, conv_depth=18.0, tp_depth=12.0,
           p_relevel_conv=0.5, p_relevel_tp=0.1, foak=False, clim=BETHEL) -> dict:
    """1,500 m2 rural school/clinic on steel pipe piles in warm permafrost."""
    n = math.ceil(area_m2 / m2_per_pile)
    out = {}
    # A0 conventional adfreeze piles
    b = Bill(units=n, note=f"{n} piles x {conv_depth:.0f} m")
    b.items["Piles (drill, steel, set)"] = n * conv_depth * pile_cost_per_m(c)
    add_engineering_and_mob(b, replace(c, eng_fixed=60_000, eng_frac=0.03))
    b.one_offs.append((15, p_relevel_conv * RELEVEL_USD))
    out["Adfreeze piles, 18 m (BAU)"] = b

    unit = Unit(evap_len_m=tp_depth, cond_area_m2=6.0, layout="thermopile", spacing_m=math.sqrt(m2_per_pile))
    need = 15.0 * m2_per_pile * 1.5      # kWh/yr per pile: warming + pile conduction (assumption)
    q = winter_extraction_kwh(unit, p, clim, _design_year(c))
    for label, plat in (("Incumbent thermopiles, 12 m", False), ("Platform thermopiles, 12 m (NOAK)", True)):
        cc = (platform_costs(c, foak) if plat else c)
        b = ts_system(n, unit, cc, plat, host_pile=True)
        b.items = {"Piles (drill, steel, set)": n * tp_depth * pile_cost_per_m(cc), **b.items}
        add_engineering_and_mob(b, cc)
        b.one_offs.append((15, p_relevel_tp * RELEVEL_USD))
        b.note = f"{n} thermopiles x {tp_depth:.0f} m; capacity {q:.0f} kWh vs {need:.0f} kWh needed per pile"
        if foak and plat:
            label = "Platform thermopiles, 12 m (FOAK)"
        out[label] = b
    return out


# ------------------------------------------------------------- Case B: new heated slab (data hall / hangar)
def case_b(c: Costs, p: Physics, *, side_m=100.0, t_in=25.0, sf=1.5, foak=False, clim=DEADHORSE) -> dict:
    """10,000 m2 heated slab-on-grade on a gravel pad (data hall, hangar, plant), North Slope."""
    area = side_m * side_m
    heat = floor_heat_kwh_m2(t_in) * sf * area
    out = {}
    insulation = 50.0 * area          # 200 mm XPS installed, $/m2 (assumption); same for both slab options
    slab = 150.0 * area               # slab-on-grade concrete (assumption)

    # B0: elevated building on piles over the pad (common North Slope practice)
    n_p = math.ceil(area / 20.0)      # heavy floors: 1 pile per 20 m2 (assumption)
    b = Bill(units=n_p, note=f"{n_p} piles x 10 m + structural floor")
    b.items["Piles (drill, steel, set)"] = n_p * 10.0 * pile_cost_per_m(c)
    b.items["Elevated structural floor"] = 400.0 * area      # vs slab, assumption
    add_engineering_and_mob(b, replace(c, eng_fixed=100_000, eng_frac=0.03))
    out["Elevated on piles (BAU)"] = b

    for label, plat in (("Incumbent flat-loop thermosyphons", False), ("Platform pad thermosyphons (NOAK)", True)):
        cc = platform_costs(c, foak) if plat else c
        best = None
        for spacing in (1.5, 2.0, 2.5, 3.0):   # wider than 3 m leaves warm strips between pipes
            for cond in (15.0, 25.0, 40.0, 60.0):
                u = Unit(evap_len_m=side_m / 2, cond_area_m2=cond, layout="pad", spacing_m=spacing,
                         d_out_m=0.080 if plat else 0.050)
                n_geom = math.ceil(2 * side_m / spacing)
                n, q = size_units(heat, u, p, clim, _design_year(c), n_geom)
                if plat:
                    bb = ts_system(n, u, cc, True)
                else:
                    bb = ts_system(n, u, replace(cc, inc_hw_per_m=50.0), False)
                if best is None or bb.capex < best[0].capex:
                    best = (bb, u, n, q)
        bb, u, n, q = best
        bb.items = {"Slab + insulation": slab + insulation, **bb.items}
        add_engineering_and_mob(bb, cc)
        bb.note = (f"{n} units, {u.spacing_m} m pitch, {u.cond_area_m2:.0f} m2 condensers, "
                   f"{q/1000:.1f} MWh/unit/yr at end of life; design heat {heat/1e6:.2f} GWh/yr")
        if foak and plat:
            label = "Platform pad thermosyphons (FOAK)"
        out[label] = bb
    return out


# ------------------------------------------------------- Case C: retrofit of an existing heated building
def case_c(c: Costs, p: Physics, *, width=30.0, length=50.0, thaw_depth=4.0, latent_kwh_m3=30.0,
           ongoing_kwh_m2=25.0, sf=1.3, refreeze_winters=3, relevel_every=5, foak=False,
           clim=ROSS_RIVER, elec=0.30) -> dict:
    """1,500 m2 school on degrading permafrost (Ross River-type). 30-yr NPV of keep-repairing vs stabilizing."""
    area = width * length
    heat = (area * thaw_depth * latent_kwh_m3 / refreeze_winters + area * ongoing_kwh_m2) * sf
    inspect = 1.0e6 * USD_PER_CAD / 25      # Ross River ~CAD 1M of inspections over ~25 yr
    out = {}

    b = Bill(note=f"relevel every {relevel_every} yr at ${RELEVEL_USD/1e6:.2f}M")
    b.items["(none up front)"] = 0.0
    b.annual["Inspections"] = inspect
    b.one_offs += [(y, RELEVEL_USD) for y in range(relevel_every, int(c.life) + 1, relevel_every)]
    out["Keep relevelling (BAU)"] = b

    b = Bill(note="new 1,500 m2 school at $6,000/m2 (~$560/sq ft)")
    b.items["Replace school"] = 6000.0 * area
    out["Replace the school"] = b

    b = Bill(note="Ross River 2019 bid CAD 1.6M; COP 2.5; replace plant at yr 15")
    capex = 1.6e6 * USD_PER_CAD
    b.items["Crawlspace refrigeration"] = capex
    b.annual["Power"] = heat / sf / 2.5 * elec
    b.annual["O&M (3%/yr)"] = 0.03 * capex
    b.annual["Inspections"] = inspect
    b.one_offs += [(1, RELEVEL_USD), (15, 0.5 * capex)]
    out["Active refrigeration"] = b

    for label, plat in (("Incumbent inclined thermosyphons", False), ("Platform inclined thermosyphons (NOAK)", True)):
        cc = platform_costs(c, foak) if plat else c
        best = None
        for spacing in (1.5, 2.0, 2.5, 3.0):
            for cond in (12.0, 20.0, 30.0):
                u = Unit(evap_len_m=width * 0.6 / math.cos(math.radians(11)), cond_area_m2=cond,
                         layout="inclined", spacing_m=spacing, riser_len_m=4.0)
                n_geom = math.ceil(2 * length / spacing)
                n, q = size_units(heat, u, p, clim, refreeze_winters, n_geom)
                bb = ts_system(n, u, cc, plat)
                if best is None or bb.capex < best[0].capex:
                    best = (bb, u, n, q)
        bb, u, n, q = best
        add_engineering_and_mob(bb, cc)
        bb.annual["Inspections"] = inspect * 0.5
        bb.one_offs.append((refreeze_winters, RELEVEL_USD))
        bb.note = (f"{n} units from both long sides, {u.spacing_m} m pitch, {u.evap_len_m:.0f} m evaporators, "
                   f"{u.cond_area_m2:.0f} m2 condensers; refreeze in {refreeze_winters} winters, then one relevel")
        if foak and plat:
            label = "Platform inclined thermosyphons (FOAK)"
        out[label] = bb
    return out


# ------------------------------------------------------------------ Case D: road on warm, ice-rich ground
def case_d(c: Costs, p: Physics, *, km=1.0, repair_cad=30_000.0, ace_cad=1.0e6, residual=0.25,
           foak=False, clim=BEAVER_CREEK) -> dict:
    """1 km of highway on warm ice-rich permafrost, Dry Creek design (7 m, 34 m inclined, 19.5 m2)."""
    repair = repair_cad * USD_PER_CAD * km
    out = {}
    b = Bill(note="Yukon ~CAD 30k/km/yr on permafrost sections")
    b.items["(none up front)"] = 0.0
    b.annual["Repair as it settles"] = repair
    out["Repair as it settles (BAU)"] = b

    b = Bill(note="Yukon ~CAD 1M/km; 25% of repairs remain")
    b.items["Air-convection embankment"] = ace_cad * USD_PER_CAD * km
    b.annual["Residual repair"] = residual * repair
    out["Air-convection embankment"] = b

    u = Unit(evap_len_m=34.0, cond_area_m2=19.5, layout="inclined", spacing_m=7.0, riser_len_m=4.0)
    n = math.ceil(km * 1000 / 7.0)
    for label, plat in (("Incumbent sloped thermosyphons", False), ("Platform sloped thermosyphons (NOAK)", True)):
        cc = platform_costs(c, foak) if plat else c
        bb = ts_system(n, u, cc, plat)
        add_engineering_and_mob(bb, cc)
        bb.annual["Residual repair"] = residual * repair
        q = winter_extraction_kwh(u, p, clim, 0.0)
        bb.note = f"{n} units/km; {q/1000:.1f} MWh/unit/yr today"
        if foak and plat:
            label = "Platform sloped thermosyphons (FOAK)"
        out[label] = bb
    return out


def dry_creek_check(c: Costs) -> float:
    """Incumbent price for the 58-unit Dry Creek job; budget was CAD 1.3-2.3M (USD 0.95-1.68M)."""
    u = Unit(evap_len_m=34.0, cond_area_m2=19.5, layout="inclined", spacing_m=7.0, riser_len_m=4.0)
    b = ts_system(58, u, c, False)
    add_engineering_and_mob(b, c)
    return b.capex


CASES = {
    "A": ("New elevated building on piles, warm permafrost (1,500 m2, Y-K Delta)", case_a, "$/m2", 1500.0),
    "B": ("New heated slab: data hall / hangar (10,000 m2, North Slope)", case_b, "$/m2", 10_000.0),
    "C": ("Retrofit: existing school on thawing ground (1,500 m2, Ross River-type)", case_c, "$/m2", 1500.0),
    "D": ("Retrofit: 1 km of highway on warm ice-rich permafrost (Alaska Highway)", case_d, "$/km", 1.0),
}
