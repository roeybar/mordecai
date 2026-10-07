"""The README challenge sentences (demo_data/challenges.json). The sentence and
its intended meaning are read from torture_he.json by item id, so the README,
the tests and the golden share one source. The expected senses and demo output
are hand-set for the demo frames."""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

PATH = Path(__file__).resolve().parent / "demo_data" / "challenges.json"
GOLDEN = Path(__file__).resolve().parent.parent / "tests" / "goldens" / "torture_he.json"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def load() -> list[dict]:
    """The challenge items in file order; a missing golden id raises KeyError."""
    items = json.loads(GOLDEN.read_text(encoding="utf-8"))["items"]
    by_id = {i["id"]: i for i in items}
    out = []
    for c in json.loads(PATH.read_text(encoding="utf-8"))["items"]:
        g = by_id[c["id"]]
        out.append({
            "id": c["id"],
            "source": c["source"],
            "target": c["target"],
            "text": g[c["source"]],
            "gold": g["gold_" + c["target"]],
            "homographs": [
                {"bare": h["bare"], "occ": int(h.get("occ", 1)),
                 "reading": _nfc(h["reading"]), "gloss": _nfc(h["gloss"])}
                for h in c["homographs"]
            ],
            "demo_output": _nfc(c["demo_output"]),
        })
    return out
