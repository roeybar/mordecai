"""S4: check that every chosen sense with a gloss shows up in the output.
A substring check only; it does not compare frames or judge fluency."""
from __future__ import annotations

from .types import Analysis, Resolution, Verdict


def verify(text_out: str, a: Analysis, r: Resolution, target: str) -> Verdict:
    low = text_out.lower()
    notes: list[dict] = []
    for i, c in enumerate(r.choice):
        if c is None:
            continue
        expected = a.lattice[i][c].gloss(target)
        if expected and expected.lower() not in low:
            notes.append({"token": a.tokens[i], "expected": expected,
                          "issue": "chosen sense absent from output"})
    return Verdict(not notes, notes)
