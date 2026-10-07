"""S3: normalise the rendered text and flag a script mismatch with the
target language. It does no agreement or morphology repair."""
from __future__ import annotations

from .. import langs, text
from .types import Repaired


def repair(text_out: str, target: str) -> Repaired:
    out = text.normalise(text_out)
    notes: list[str] = []
    lg = langs.get(target)
    dom = text.dominant_script(out)
    if lg is not None and dom != "Zyyy" and dom not in lg.scripts:
        notes.append("script_mismatch")
    return Repaired(out, notes)
