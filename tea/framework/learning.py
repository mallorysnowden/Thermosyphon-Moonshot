"""Learning curves (Wright's law) for the path from FOAK to NOAK."""
from __future__ import annotations

import math


def exponent(learning_rate: float) -> float:
    """Wright's-law exponent b: cost falls by `learning_rate` per doubling of experience."""
    if learning_rate <= 0:
        return 0.0
    return -math.log2(1 - learning_rate)


def cost_multiplier(experience: float, experience_noak: float, noak_multiplier: float, learning_rate: float) -> float:
    """Cost relative to the incumbent at a given cumulative experience.

    Equals `noak_multiplier` once experience reaches NOAK, and is higher before
    that by (experience / experience_noak) ** -b. Learning is not extended past
    NOAK, so the model stays at NOAK conditions rather than assuming more.
    """
    if experience >= experience_noak:
        return noak_multiplier
    experience = max(experience, 1e-9)
    return noak_multiplier * (experience / experience_noak) ** (-exponent(learning_rate))
