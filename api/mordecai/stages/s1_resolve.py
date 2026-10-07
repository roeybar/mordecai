"""S1: pick one reading per token with the toy global solver and, for
comparison, the greedy first-candidate baseline. Slots bind the nearest word on
each side, skipping function words; it does not parse."""
from __future__ import annotations

from .. import sense_solver
from .types import Analysis, Resolution


def resolve(a: Analysis) -> Resolution:
    sol = sense_solver.solve(a.lattice)
    return Resolution(sol.choice, sense_solver.greedy(a.lattice), sol.score, sol.evaluated)
