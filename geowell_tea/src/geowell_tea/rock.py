"""Shared transient formation model (1+1D).

The formation around the well is split into ``n_z`` depth slices.  In each slice
the radial conduction equation

    rho c_p dT/dt = (1/r) d/dr (k r dT/dr)

is solved with an implicit (backward-Euler) finite-volume scheme on a
logarithmically spaced radial mesh from the borehole wall ``r_b`` to ``r_far``.
The far boundary is adiabatic, so the model contains a finite amount of rock
heat and cannot be silently re-supplied from infinity.  Vertical conduction in
the rock is neglected (slices only interact through the fluid in the well);
this is the usual 1+1D simplification (Zolfagharroshan et al. 2024) and is
conservative because it omits the background geothermal heat flux.
Conductivity may vary by layer (``Geology.k_layers``).

Coupling to the well fluid is exactly implicit.  Because the radial system is
linear, the wall-cell temperature at the end of a step is

    T_cell0 = A - S * q'

where q' [W/m] is the heat extracted from the slice over the step, A is the
cell temperature with no extraction and S [m K/W] is the unit-flux response.
The well model therefore sees, per slice, a linear relation

    q' = (A - T_fluid) / (S + R_half + R_well)

which it solves together with its own fluid equations; the resulting q' is
then applied to the rock.  ``StepResponse`` carries A and S.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve_banded

from .geology import Geology


@dataclass
class StepResponse:
    A: np.ndarray  # cell-0 temperature with zero extraction [C], per slice
    S: np.ndarray  # cell-0 response to unit extraction [m K / W], per slice
    R_half: np.ndarray  # conduction resistance from cell-0 centre to borehole wall [m K/W], per slice
    dt: float

    @property
    def R_rock(self) -> np.ndarray:
        return self.S + self.R_half


class RockField:
    def __init__(self, geology: Geology, r_b: float, n_z: int = 60, n_r: int = 40,
                 r_far: float = 200.0, first_cell: float = 0.01):
        self.geo = geology
        self.r_b = r_b
        self.n_z = n_z
        self.n_r = n_r
        self.dz = geology.depth / n_z
        self.z = (np.arange(n_z) + 0.5) * self.dz
        faces = np.concatenate([[r_b], r_b + first_cell * np.geomspace(1, (r_far - r_b) / first_cell, n_r)])
        self.faces = faces
        self.rc = np.sqrt(faces[:-1] * faces[1:])
        self.vol = np.pi * (faces[1:] ** 2 - faces[:-1] ** 2)
        self.k_slice = geology.k_at(self.z)
        self.k_groups = {float(k): np.where(np.isclose(self.k_slice, k))[0] for k in np.unique(self.k_slice)}
        self.R_half = np.log(self.rc[0] / r_b) / (2 * np.pi * self.k_slice)
        self.C = geology.rho * geology.cp * self.vol
        self.T = np.repeat(geology.T0(self.z)[None, :], n_r, axis=0)  # (n_r, n_z)
        self.T_init = self.T.copy()
        self._cache: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
        self.cum_extracted_J = 0.0

    def _banded(self, dt: float, k: float):
        key = (dt, k)
        if key in self._cache:
            return self._cache[key]
        n = self.n_r
        G = 2 * np.pi * k / np.log(self.rc[1:] / self.rc[:-1])
        d = self.C / dt
        d = d.copy()
        d[:-1] += G
        d[1:] += G
        up = np.zeros(n)
        lo = np.zeros(n)
        up[1:] = -G
        lo[:-1] = -G
        ab = np.vstack([up, d, lo])
        e0 = np.zeros(n)
        e0[0] = 1.0
        S_vec = solve_banded((1, 1), ab, e0)
        self._cache[key] = (ab, S_vec)
        return ab, S_vec

    def response(self, dt: float) -> StepResponse:
        rhs = self.C[:, None] / dt * self.T
        T_free = np.empty_like(self.T)
        S_mat = np.empty_like(self.T)
        for k, idx in self.k_groups.items():
            ab, S_vec = self._banded(dt, k)
            T_free[:, idx] = solve_banded((1, 1), ab, rhs[:, idx])
            S_mat[:, idx] = S_vec[:, None]
        self._pending = (dt, T_free, S_mat)
        return StepResponse(A=T_free[0].copy(), S=S_mat[0].copy(), R_half=self.R_half, dt=dt)

    def apply(self, q: np.ndarray) -> None:
        """Advance the rock with extraction q' [W/m] per slice (positive = heat removed)."""
        dt, T_free, S_mat = self._pending
        self.T = T_free - S_mat * np.asarray(q)[None, :]
        self.cum_extracted_J += float(np.sum(q) * self.dz * dt)

    def wall_temperature(self, q: np.ndarray) -> np.ndarray:
        return self.T[0] - q * self.R_half

    def energy_deficit_J(self) -> float:
        """Heat removed from the rock since t=0, from the stored-energy change."""
        return float(np.sum(self.C[:, None] * (self.T_init - self.T)) * self.dz)
