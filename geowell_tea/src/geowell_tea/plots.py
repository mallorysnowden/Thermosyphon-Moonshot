"""Matplotlib figures (optional dependency)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAVE_MPL = True
except Exception:  # pragma: no cover
    HAVE_MPL = False

COLORS = {"T_DIRECT": "#1b7837", "T_HP": "#5aae61", "T_ADAPTIVE": "#a6dba0",
          "C_DIRECT": "#762a83", "C_HP": "#9970ab", "C_ADAPTIVE": "#c2a5cf"}


def heat_vs_time(best: dict, path: Path):
    if not HAVE_MPL:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    for a, (res, s) in sorted(best.items()):
        t = np.arange(res.months) / 12
        axes[0].plot(t, res.Q_geo_cap / 1e3, color=COLORS[a], label=a)
        axes[1].plot(t, res.T_source, color=COLORS[a], label=a)
    axes[0].set(xlabel="year", ylabel="geothermal capability [kW]", title="Heat extraction capability (economic optimum per architecture)")
    axes[1].set(xlabel="year", ylabel="source temperature [C]", title="Source temperature presented to surface")
    for ax in axes:
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def depth_profiles(best: dict, path: Path):
    if not HAVE_MPL:
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    any_res = next(iter(best.values()))[0]
    axes[0].plot(any_res.T_rock_init, any_res.z, "k--", label="undisturbed rock")
    for a, (res, s) in sorted(best.items()):
        axes[0].plot(res.T_rock_wall_final, res.z, color=COLORS[a], label=f"{a} wall, year 20")
        axes[1].plot(res.q_final, res.z, color=COLORS[a], label=a)
    axes[0].set(xlabel="temperature [C]", ylabel="depth [m]", title="Rock-face temperature")
    axes[1].set(xlabel="heat flux q' [W/m] (capability, final step)", title="Active exchange profile")
    axes[1].axvline(0, color="grey", lw=0.8)
    for ax in axes:
        ax.invert_yaxis() if ax is axes[0] else None
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def summary_bars(best: dict, path: Path):
    if not HAVE_MPL:
        return
    archs = sorted(best)
    vals = {k: [best[a][1][k] for a in archs] for k in
            ("geo_capability_kW_y20", "useful_capability_kW_y20", "lcoh", "SPF_system")}
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    x = np.arange(len(archs))
    axes[0].bar(x - 0.2, vals["geo_capability_kW_y20"], 0.4, label="geothermal kW (yr 20)",
                color=[COLORS[a] for a in archs])
    axes[0].bar(x + 0.2, vals["useful_capability_kW_y20"], 0.4, label="useful kW (yr 20)", color="#bbbbbb")
    axes[0].set_title("Capability, year 20")
    axes[1].bar(x, vals["lcoh"], color=[COLORS[a] for a in archs])
    axes[1].set_title("LCOH of geothermal useful heat [$/MWh]")
    axes[2].bar(x, vals["SPF_system"], color=[COLORS[a] for a in archs])
    axes[2].set_title("System SPF (useful heat / all electricity)")
    for ax in axes:
        ax.set_xticks(x, archs, rotation=30, fontsize=8)
        ax.grid(alpha=0.3, axis="y")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def electricity_crossover(df, path: Path):
    if not HAVE_MPL:
        return
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for a in sorted(df["architecture"].unique()):
        d = df[df["architecture"] == a]
        ax.plot(d["electricity_price"], d["lcoh"], marker="o", color=COLORS[a], label=a)
    ax.set(xlabel="electricity price [$/kWh]", ylabel="LCOH [$/MWh] (re-optimised per price)",
           title="Electricity-price sensitivity")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def tornado(df, path: Path, title: str):
    if not HAVE_MPL or df.empty:
        return
    d = df.reindex(df["swing"].abs().sort_values().index)
    fig, ax = plt.subplots(figsize=(8, 0.35 * len(d) + 1.5))
    y = np.arange(len(d))
    ax.barh(y, d["ratio_high"] - d["ratio_base"], left=d["ratio_base"], color="#d6604d", label="param high")
    ax.barh(y, d["ratio_low"] - d["ratio_base"], left=d["ratio_base"], color="#4393c3", label="param low")
    ax.axvline(1.0, color="k", lw=1)
    ax.set_yticks(y, d["parameter"], fontsize=8)
    ax.set(xlabel="LCOH(best thermosiphon) / LCOH(best coaxial)", title=title)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def envelope_map(df, path: Path, value="p_ts_wins", title=""):
    if not HAVE_MPL:
        return
    dias = sorted(df["casing_id"].unique())
    fig, axes = plt.subplots(1, len(dias), figsize=(4.2 * len(dias), 4.2), sharey=True)
    axes = np.atleast_1d(axes)
    depths = sorted(df["depth"].unique())
    bhts = sorted(df["bht"].unique())
    for ax, D in zip(axes, dias):
        grid = np.full((len(bhts), len(depths)), np.nan)
        for _, r in df[df["casing_id"] == D].iterrows():
            grid[bhts.index(r["bht"]), depths.index(r["depth"])] = r[value]
        im = ax.imshow(grid, origin="lower", aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
        ax.set_xticks(range(len(depths)), [f"{d/1000:.1f}" for d in depths])
        ax.set_yticks(range(len(bhts)), [f"{b:.0f}" for b in bhts])
        ax.set(xlabel="depth [km]", title=f"casing ID {D*1000:.0f} mm")
        for i in range(len(bhts)):
            for j in range(len(depths)):
                if np.isfinite(grid[i, j]):
                    ax.text(j, i, f"{grid[i, j]:.2f}", ha="center", va="center", fontsize=7)
    axes[0].set_ylabel("bottom-hole temperature [C]")
    fig.colorbar(im, ax=axes.tolist(), shrink=0.8, label=value)
    fig.suptitle(title)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
