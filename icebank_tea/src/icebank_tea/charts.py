"""Charts for the data-center case: cost breakdown (BAU vs ice only) and sensitivity tornados.

Called by `python -m icebank_tea.run` when matplotlib is installed; writes outputs/figures/*.png.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .costs import CostInputs  # noqa: E402
from .run import BACKUP_LABEL, OUT, fmt_design  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
# One fixed color per cost item across both pies (orders validated for adjacent CVD / normal-vision separation)
COLOR = {"plant": "#2a78d6", "elec_service": "#eb6834", "thermosiphons": "#eda100", "pit": "#e87ba4",
         "discharge": "#008300", "energy": "#6250d6", "demand": "#e34948", "om": "#1baf7a",
         "water": "#8a8986"}  # water only appears for tower plants; a neutral, not a ninth hue
NAME = {"plant": "Chiller plant (capital)", "elec_service": "Electrical service (capital)",
        "thermosiphons": "Thermosiphons (capital)", "pit": "Insulated pit (capital)",
        "discharge": "Pumps, HX + dry cooler (capital)", "energy": "Electricity (energy)",
        "demand": "Demand charges", "om": "Operations and maintenance",
        "water": "Cooling-tower water and sewer"}
BAU_ORDER = ["plant", "demand", "energy", "elec_service", "om", "water"]
ICE_ORDER = ["pit", "thermosiphons", "discharge", "demand", "om", "elec_service", "energy", "water"]
LOW, HIGH = "#2a78d6", "#eb6834"

def esc(t: str) -> str:
    """Escape $ so matplotlib doesn't read paired dollar signs as math."""
    return t.replace("$", r"\$")


plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK, "axes.edgecolor": GRID})


def assumptions(res, ci: CostInputs, years: int) -> tuple[str, str, str]:
    c, b, r = res["case"], res["bau"], res["best"]["none"]
    d = r["design"]
    rej = "cooling towers" if c.heat_rejection == "tower" else "air-cooled, no water"
    bau = (f"Conventional: chillers ({rej}) for {c.peak_w / 1e6:.0f} MW peak, {c.redundancy:.1f}x redundancy at "
           f"${c.mech_usd_kw:.0f}/kW, plus pumps{' and tower fans' if c.heat_rejection == 'tower' else ''}; electricity {100 * c.elec_usd_kwh:.1f}¢/kWh; demand charge "
           f"${c.demand_summer:.2f} Jun-Sep / ${c.demand_winter:.2f} other months per kW; electrical service "
           f"${ci.elec_service_usd_kwe:.0f}/kWe of peak draw; {ci.life_mech:.0f}-yr life")
    ice = (f"Ice only (no chiller): {r['n_units']:,} thermosiphons at ${r['unit_usd']:.0f} each "
           f"(raw material x {ci.index:g}); {r['pit_ha']:.1f} ha x {d['depth_m']:.0f} m pit "
           f"({fmt_design(d)}); pumps at {ci.pump_cop:.0f} kW cooling per kWe, same electrical service cost; "
           f"worst-year unmet <= 0.1%; {ci.life_icebank:.0f}-yr life, first cooling after one winter")
    both = (f"Both: {100 * ci.rate:.0f}% discount rate, mass-production (NOAK) costs, median of {years} synthetic "
            f"weather years, {b['cold_mwh']:,.0f} MWh of cooling a year")
    return bau.replace("m2", "m²"), ice.replace("m2", "m²"), both


def _donut(ax, parts, order, cold, scale):
    keys = [k for k in order if parts.get(k, 0) > 0]
    vals = np.array([parts[k] / cold for k in keys])
    total = vals.sum()
    wedges, _ = ax.pie(vals, colors=[COLOR[k] for k in keys], startangle=90, counterclock=False, radius=scale,
                       wedgeprops=dict(width=0.38 * scale, edgecolor=SURFACE, linewidth=2))
    # Place labels outside, then push apart labels on the same side that would overlap
    labs = []
    for w, k, v in zip(wedges, keys, vals):
        ang = np.deg2rad((w.theta1 + w.theta2) / 2)
        labs.append(dict(k=k, v=v, x=np.cos(ang), y=np.sin(ang), ty=np.sin(ang) * 1.2))
    for side in (1, -1):
        grp = sorted((l for l in labs if np.sign(l["x"]) == side or (l["x"] == 0 and side == 1)),
                     key=lambda l: -l["ty"])
        for a, b in zip(grp, grp[1:]):
            if a["ty"] - b["ty"] < 0.2:
                b["ty"] = a["ty"] - 0.2
    for l in labs:
        x, y = l["x"], l["y"]
        ax.annotate(f"{NAME[l['k']]}\n${l['v']:.0f}/MWh ({100 * l['v'] / total:.0f}%)",
                    xy=(x * scale * 0.97, y * scale * 0.97), xytext=(np.sign(x or 1) * max(abs(x) * 1.22, 0.55), l["ty"]),
                    ha="left" if x >= 0 else "right", va="center", fontsize=8.5, color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.text(0, 0.08, f"${total:.0f}", ha="center", va="center", fontsize=20, fontweight="bold", color=INK)
    ax.text(0, -0.16, "per MWh", ha="center", va="center", fontsize=9, color=INK2)
    ax.set_xlim(-2.3, 2.3); ax.set_ylim(-1.45, 1.45); ax.set_aspect("equal")
    return total


def pies(res, ci, years, path: Path):
    bau_txt, ice_txt, both_txt = assumptions(res, ci, years)
    cold = res["bau"]["service_mwh"]
    bp, ip = res["bau"]["parts"], dict(res["best"]["none"]["parts"])
    ip["discharge"] = ip.get("discharge", 0.0) + ip.pop("dry_cooler", 0.0)  # one slice for the water-side plant
    bt = sum(bp.values()) / cold; it = sum(ip.values()) / cold
    fig, axes = plt.subplots(1, 2, figsize=(16, 7.8), facecolor=SURFACE)
    fig.suptitle(f"{res['case'].title}: what a MWh of cooling costs", x=0.04, ha="left", fontsize=15,
                 fontweight="bold", y=0.975)
    fig.text(0.04, 0.905, esc("\n".join(_wrap(t, 175) for t in (bau_txt, ice_txt, both_txt))), fontsize=8.5,
             color=INK2, va="top", linespacing=1.45)
    _donut(axes[0], bp, BAU_ORDER, cold, 1.0)
    _donut(axes[1], ip, ICE_ORDER, cold, float(np.sqrt(it / bt)))  # ring area scales with total cost
    for ax, title in ((axes[0], "Conventional chillers (BAU)"), (axes[1], "Ice bank only, no chiller")):
        ax.set_title(title, fontsize=12, fontweight="bold", color=INK, pad=4)
        ax.set_facecolor(SURFACE)
    fig.text(0.04, 0.03, f"Ice only costs {it / bt:.2f}x conventional. Ring size scales with total cost. "
             "Capital is annualized; demand charges bill each month's peak chiller (or pump) draw.",
             fontsize=8.5, color=INK2)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.76, bottom=0.08, wspace=0.0)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def _wrap(text, width):
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width:
            lines.append(line); line = w
        else:
            line = f"{line} {w}".strip()
    return "\n".join(lines + [line])


def _tornado(ax, sens, which, other_base, other_label, xlim):
    rows = []
    for s in sens:
        lo, hi, base = s[f"{which}_low"], s[f"{which}_high"], s[f"{which}_base"]
        if np.isnan(lo) or np.isnan(hi) or max(abs(lo - base), abs(hi - base)) < 0.5:
            continue
        rows.append((s["input"], lo, hi, base))
    rows.sort(key=lambda r: abs(r[2] - r[1]))
    base = rows[0][3] if rows else sens[0][f"{which}_base"]
    for i, (name, lo, hi, _) in enumerate(rows):
        for v, col in ((lo, LOW), (hi, HIGH)):
            if abs(v - base) < 0.5:
                continue
            ax.barh(i, v - base, left=base, height=0.55, color=col, edgecolor=SURFACE, linewidth=2)
            ax.text(v + (1.5 if v >= base else -1.5), i, f"${v:.0f}", va="center",
                    ha="left" if v >= base else "right", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(rows)), [esc(r[0]) for r in rows], fontsize=9)
    ax.axvline(base, color=INK, lw=1.2)
    ax.axvline(other_base, color=INK2, lw=1, ls="--")
    ax.text(other_base, len(rows) - 0.35, f" {other_label} ${other_base:.0f}", color=INK2, fontsize=8.5, va="bottom")
    ax.text(base, -0.85, f"base ${base:.0f}", ha="center", va="top", fontsize=8.5, color=INK)
    ax.set_xlim(*xlim); ax.set_ylim(-1.1, len(rows) - 0.1)
    ax.set_xlabel("Cost of cooling, $ per MWh of cold")
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)


def tornados(res, ci, years, path: Path):
    bau_txt, ice_txt, both_txt = assumptions(res, ci, years)
    sens = res["sens_none"]
    vals = [s[k] for s in sens for k in ("bau_low", "bau_high", "ice_low", "ice_high") if not np.isnan(s[k])]
    pad = 0.08 * (max(vals) - min(vals))
    xlim = (min(vals) - 3 * pad, max(vals) + 2 * pad)
    fig, axes = plt.subplots(1, 2, figsize=(16, 8.2), facecolor=SURFACE, sharex=True)
    fig.suptitle(f"{res['case'].title}: what moves the cost of cooling", x=0.04, ha="left", fontsize=15,
                 fontweight="bold", y=0.975)
    fig.text(0.04, 0.905, esc("\n".join(_wrap(t, 175) for t in (bau_txt, ice_txt, both_txt))), fontsize=8.5,
             color=INK2, va="top", linespacing=1.45)
    bau_base, ice_base = sens[0]["bau_base"], sens[0]["ice_base"]
    _tornado(axes[0], sens, "bau", ice_base, "ice only", xlim)
    _tornado(axes[1], sens, "ice", bau_base, "conventional", xlim)
    axes[0].set_title("Conventional chillers (BAU)", fontsize=12, fontweight="bold", loc="left")
    axes[1].set_title("Ice bank only, no chiller", fontsize=12, fontweight="bold",
                      loc="left")
    for ax in axes:
        ax.set_facecolor(SURFACE)
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=LOW, label="Input at its low value (first number in brackets)"),
                        Patch(color=HIGH, label="Input at its high value (second number)")],
               loc="lower left", bbox_to_anchor=(0.035, 0.0), ncol=2, frameon=False, fontsize=9)
    fig.text(0.04, 0.055, "Each bar changes one input and keeps the rest at base. The ice bank is re-sized for each input; "
             "the dashed line marks the other option's base cost.", fontsize=8.5, color=INK2)
    fig.subplots_adjust(left=0.21, right=0.98, top=0.7, bottom=0.16, wspace=0.75)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)


def make_charts(results, ci: CostInputs, years: int, case_key: str = "A") -> list[Path]:
    res = next((r for r in results if r["case"].key == case_key), None)
    if res is None or res["best"]["none"] is None:
        return []
    out = OUT / "figures"
    out.mkdir(parents=True, exist_ok=True)
    p1, p2 = out / f"{case_key}_cost_breakdown.png", out / f"{case_key}_tornado.png"
    pies(res, ci, years, p1)
    tornados(res, ci, years, p2)
    return [p1, p2]


__all__ = ["make_charts", "BACKUP_LABEL"]
