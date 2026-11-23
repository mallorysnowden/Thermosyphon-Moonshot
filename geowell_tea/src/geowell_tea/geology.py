"""Undisturbed formation temperature and properties."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Geology:
    """Formation description shared by every downhole architecture.

    ``profile_z`` / ``profile_T`` define the undisturbed temperature T0(z) as a
    piecewise-linear curve (true vertical depth z positive downward, metres;
    temperature in deg C).  A linear gradient is the two-point special case.
    """
    depth: float  # usable true vertical depth [m]
    profile_z: list[float]
    profile_T: list[float]
    k: float = 2.5  # W/(m K)
    rho: float = 2400.0  # kg/m3
    cp: float = 900.0  # J/(kg K)
    groundwater_advection: bool = False  # not modelled; kept as an explicit flag
    label: str = ""
    provenance: dict = field(default_factory=dict)
    # optional layered conductivity: list of (z_top, k) pairs; k applies from z_top downward.
    # An "effective" k above the rock value is the crude proxy used for convective aquifers.
    k_layers: list | None = None

    def k_at(self, z):
        z = np.asarray(z, dtype=float)
        k = np.full(z.shape, self.k)
        if self.k_layers:
            for z_top, k_l in sorted(self.k_layers):
                k = np.where(z >= z_top, k_l, k)
        return k

    @classmethod
    def linear(cls, depth: float, T_surface: float, T_bottom: float, **kw) -> "Geology":
        return cls(depth=depth, profile_z=[0.0, depth], profile_T=[T_surface, T_bottom], **kw)

    @property
    def alpha(self) -> float:
        return self.k / (self.rho * self.cp)

    def T0(self, z):
        return np.interp(z, self.profile_z, self.profile_T)

    @property
    def T_bottom(self) -> float:
        return float(self.T0(self.depth))

    def depth_at_temperature(self, T: float) -> float:
        """Shallowest depth where the undisturbed rock reaches T (monotone profiles)."""
        zs = np.linspace(0, self.depth, 4001)
        Ts = self.T0(zs)
        idx = np.argmax(Ts >= T)
        if Ts[idx] < T:
            return self.depth
        return float(zs[idx])
