"""Streamlit UI for the fast thermosiphon calculator (geowell_tea.fast).

Run locally:   pip install streamlit && streamlit run app.py
Hugging Face:  see README section "Web calculator".
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from geowell_tea.fast import LOAD_SHAPES, Inputs, baked_in_assumptions, preset_inputs, run  # noqa: E402

st.set_page_config(page_title="Thermosiphon heat from reused wells", layout="wide")


@st.cache_data(show_spinner=False, max_entries=64)
def cached_run(kw: dict):
    r = run(Inputs(**kw), workers=2 if sys.platform.startswith("linux") else 1)
    return asdict(r) if hasattr(r, "__dataclass_fields__") else r


st.title("Thermosiphon heat from a reused oil & gas well")
st.caption("Fast calculator built on the geowell_tea TEA model. Thermosiphon only, compared against the incumbent "
           "boiler. Costs are assumptions, not quotes - see the repo's MODEL_LIMITATIONS.md.")

with st.sidebar:
    d = preset_inputs()  # neutral starting values (configs/app_defaults.yaml)
    k = ""

    st.header("Thermosiphon")
    config = st.radio("Configuration", ["hybrid", "direct"], key=f"cfg{k}", horizontal=True,
                      format_func=lambda c: {"hybrid": "Hybrid (condenser = heat-pump evaporator)",
                                             "direct": "Direct heat (no heat pump)"}[c])
    ret = st.radio("Condensate return", ["guided", "film"], key=f"ret{k}", horizontal=True,
                   format_func=lambda c: {"guided": "Guided (stepped reflux)", "film": "Falling film"}[c])
    cost_level = st.radio("Cost level", ["noak", "base", "foak"], key=f"lvl{k}", horizontal=True,
                          format_func=str.upper)
    ku = st.select_slider("Guided-return validated up to Ku", options=[3.2, 4.4, 6.0], value=3.2, key=f"ku{k}",
                          help="3.2 = established correlations; 4.4 = Xiong'an field estimate; 6 = optimistic")
    full_cov = st.checkbox("Require full coverage (<= 2 % unmet every year)", value=False, key=f"fc{k}")
    with st.expander("Advanced"):
        insulation = st.selectbox("Insulation (upper string)", ["aerogel_n2", "n2_only", "pip", "vit_liner"],
                                  key=f"ins{k}", format_func=lambda c: {
                                      "aerogel_n2": "Factory aerogel + N2-capped annulus",
                                      "n2_only": "N2-capped annulus + low-e foil only",
                                      "pip": "Pipe-in-pipe (liquid annulus)",
                                      "vit_liner": "VIT liner (reference)"}[c])
        pin = st.checkbox("Pin condenser temperature", key=f"pin{k}")
        T_pin = st.number_input("Condenser temperature [C]", 0.0, 120.0, 20.0, 1.0, key=f"tp{k}", disabled=not pin)

    st.header("Well and rock")
    depth = st.number_input("Depth [m]", 300.0, 6000.0, d.depth_m, 50.0, key=f"dep{k}")
    T_bot = st.number_input("Bottom-hole temperature [C]", 20.0, 200.0, d.T_bottom_C, 1.0, key=f"tb{k}")
    T_surf = st.number_input("Surface temperature [C]", -5.0, 30.0, d.T_surface_C, 1.0, key=f"ts{k}")
    casing = st.number_input("Casing inner diameter [mm]", 60.0, 340.0, d.casing_id_mm, 1.0, key=f"cid{k}")
    k_rock = st.number_input("Rock conductivity [W/m/K]", 1.0, 5.0, d.k_rock, 0.1, key=f"kr{k}")

    st.header("Heat demand")
    peak = st.number_input("Peak-month demand [kW]", 10.0, 5000.0, d.peak_kW, 10.0, key=f"pk{k}")
    flh = st.number_input("Full-load hours per year", 500.0, 8760.0, d.flh, 100.0, key=f"flh{k}")
    shape = st.selectbox("Seasonal load shape", list(LOAD_SHAPES), index=list(LOAD_SHAPES).index(d.shape),
                         format_func=LOAD_SHAPES.get, key=f"sh{k}")
    T_sup = st.number_input("Supply temperature [C]", 20.0, 90.0, d.T_supply_C, 1.0, key=f"tsu{k}")
    T_ret = st.number_input("Return temperature [C]", 10.0, 80.0, d.T_return_C, 1.0, key=f"tre{k}")
    dist = st.number_input("Distance to customer [m]", 0.0, 5000.0, d.distance_m, 25.0, key=f"dis{k}")

    st.header("Prices and finance")
    elec = st.number_input("Electricity [$/kWh]", 0.01, 0.60, d.electricity_price, 0.005, format="%.3f", key=f"el{k}")
    fuel = st.number_input("Incumbent fuel [$/MWh fuel]", 5.0, 300.0, d.fuel_price_per_MWh, 1.0, key=f"fu{k}")
    eff = st.number_input("Boiler efficiency", 0.5, 1.0, d.boiler_efficiency, 0.01, key=f"ef{k}")
    ef = st.number_input("Fuel CO2 [t/MWh fuel]", 0.0, 0.5, float(d.emission_factor or 0.181), 0.001,
                         format="%.3f", key=f"co{k}")
    disc = st.number_input("Real discount rate", 0.0, 0.2, d.discount_rate, 0.005, format="%.3f", key=f"dr{k}")
    plug = st.number_input("End-of-life plugging cost [$]", 0.0, 1_000_000.0, d.plugging_eol, 5000.0, key=f"pl{k}")

kw = dict(preset=None, depth_m=depth, T_surface_C=T_surf, T_bottom_C=T_bot, casing_id_mm=casing, k_rock=k_rock,
          config=config, condensate_return=ret, insulation=insulation, ku_validated=float(ku), cost_level=cost_level,
          pinned_T_cond=float(T_pin) if pin else None, full_coverage=full_cov, peak_kW=peak, flh=flh, shape=shape,
          T_supply_C=T_sup, T_return_C=T_ret, distance_m=dist, electricity_price=elec, fuel_price_per_MWh=fuel,
          boiler_efficiency=eff, discount_rate=disc, emission_factor=ef, plugging_eol=plug)

with st.spinner("Simulating 20 years of operation..."):
    r = cached_run(kw)

for e in r["errors"]:
    st.error(e)
for w in r["warnings"]:
    st.warning(w)

if r["ok"]:
    b = r["best"]
    inc = r["incumbent"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(f"Thermosiphon heat cost ({cost_level.upper()})", f"${b['lcoh']:.0f}/MWh")
    c2.metric("Incumbent boiler", f"${inc:.0f}/MWh", f"{b['lcoh'] / inc:.1f}x" if inc else None, delta_color="off")
    c3.metric("Unmet load (worst year)", f"{b['unmet_max']:.0%}")
    c4.metric("Well capability yr 1 / yr 20", f"{b['capability_kW_y1']:.0f} / {b['capability_kW_y20']:.0f} kW")
    cp = r["breakevens"].get("carbon_price_for_parity", float("nan"))
    c5.metric("CO2 price for parity", "none needed" if cp == 0 else (f"${cp:.0f}/t" if cp == cp else "n/a"))
    st.markdown(f"**Best design:** {b['design']} · ammonia charge {b['ammonia_kg']:.0f} kg · "
                f"{b['useful_MWh_per_yr']:.0f} MWh/yr of useful heat. Heat cost counts geothermal heat only; "
                "unmet load is bought from the backup boiler.")

    left, right = st.columns(2)
    with left:
        st.subheader("Output over time")
        ts = pd.DataFrame(r["timeseries"]).set_index("year")
        st.line_chart(ts[["useful_heat_MWh", "load_MWh"]], y_label="MWh per year")
        st.line_chart(ts[["capability_kW"]], y_label="kW (geothermal capability)")
    with right:
        st.subheader("What would need to be true")
        wf = pd.DataFrame(r["waterfall"])
        wf["incumbent"] = inc
        st.bar_chart(wf.set_index("step")[["lcoh"]], horizontal=True, x_label="$/MWh")
        st.dataframe(wf.rename(columns={"lcoh": "$/MWh", "vs_incumbent": "vs incumbent",
                                        "carbon_price_for_parity": "CO2 $/t for parity"}).round(1),
                     hide_index=True, use_container_width=True)
        st.caption("Levers apply to the thermosiphon only and are cumulative: (1) NOAK manufacturing + automated "
                   "install; (2) standardised well-reuse programme; (3) heat pump $500/kW; (4) 6 % financing.")

if r.get("designs") is not None:
    with st.expander("All designs evaluated"):
        st.dataframe(pd.DataFrame(r["designs"]).round(2), hide_index=True, use_container_width=True)

with st.expander("Baked-in assumptions (deep dive)"):
    st.markdown("Everything the calculator uses that is not an input above. Values come from "
                "`configs/assumptions.yaml` and `configs/app_defaults.yaml`; *status* says whether a value is "
                "published, derived or assumed. NOAK costs are built from raw materials x `ts_noak_index` plus the "
                "automated-installation parameters; FOAK = base x `ts_foak_mult`. Model limitations: "
                "MODEL_LIMITATIONS.md in the repo.")
    assumptions = baked_in_assumptions()
    for group, g in assumptions.groupby("group", sort=False):
        st.markdown(f"**{group}**")
        st.dataframe(g.drop(columns="group"), hide_index=True, use_container_width=True)
