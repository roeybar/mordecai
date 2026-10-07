"""Deterministic check of the homograph golden over the frame store.

  python -m mordecai.eval_torture --deterministic

For each golden homograph the toy solver and the greedy baseline each pick a
reading from the store's candidates; the gold reading either is among the
candidates (status ok or FAIL) or is not (status gap: a coverage gap, not a
failure). The two torture suites are judged suites: this module only counts
their items. It also checks the README challenge sentences
(demo_data/challenges.json): each must resolve to its intended senses and
produce its exact demo output; any miss, a gap included, is a failure.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

from . import challenges, frames, providers, sense_solver, text
from .stages import translate

GOLDENS = Path(__file__).resolve().parent.parent / "tests" / "goldens"


def load(name: str) -> dict:
    return json.loads((GOLDENS / name).read_text(encoding="utf-8"))


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def check_item(store, item: dict, lang: str = "he") -> list[dict]:
    """Rows {bare, occ, gold, solver, greedy, status} for one golden item."""
    tokens = text.tokenize(lang, item[lang])
    lat = sense_solver.lattice(store, lang, tokens)
    sol = sense_solver.solve(lat)
    gre = sense_solver.greedy(lat)
    rests = []
    for tok, cands in zip(tokens, lat):
        prefix = cands[0].prefix if cands else ""
        rests.append(text.bare(lang, tok)[len(prefix):])
    rows = []
    for h in item.get("homographs", []):
        want = text.bare(lang, h["bare"])
        occ = h.get("occ", 1)
        hits = [i for i, r in enumerate(rests) if r == want]
        gold = _nfc(h["reading"])
        row = {"bare": h["bare"], "occ": occ, "gold": gold, "solver": None, "greedy": None,
               "status": "gap"}
        if occ <= len(hits):
            i = hits[occ - 1]
            cands = [_nfc(r.reading) for r in lat[i]]
            if gold in cands:
                row["solver"] = _nfc(lat[i][sol.choice[i]].reading)
                row["greedy"] = _nfc(lat[i][gre[i]].reading)
                row["status"] = "ok" if row["solver"] == gold else "FAIL"
        rows.append(row)
    return rows


def check_challenge(store, ch: dict) -> dict:
    """Run one README challenge through the demo pipeline and compare it with the expected senses."""
    src, tgt = ch["source"], ch["target"]
    res = translate(ch["text"], src_lang=src, tgt_lang=tgt, provider=providers.get("demo"), store=store)
    lat = res.analysis.lattice
    rests = []
    for tok, c in zip(res.analysis.tokens, lat):
        rests.append(text.bare(src, tok)[len(c[0].prefix if c else ""):])

    def sense(r) -> str:
        return f"{_nfc(r.reading)}={_nfc(r.gloss(tgt))}"

    rows = []
    for h in ch["homographs"]:
        gold = f"{h['reading']}={h['gloss']}"
        row = {"bare": h["bare"], "occ": h["occ"], "gold": gold, "solver": None, "greedy": None,
               "status": "gap"}
        hits = [i for i, r in enumerate(rests) if r == text.bare(src, h["bare"])]
        if h["occ"] <= len(hits):
            i = hits[h["occ"] - 1]
            if gold in [sense(r) for r in lat[i]]:
                row["solver"] = sense(lat[i][res.resolution.choice[i]])
                row["greedy"] = sense(lat[i][res.resolution.greedy[i]])
                row["status"] = "ok" if row["solver"] == gold else "FAIL"
        rows.append(row)
    return {"rows": rows, "output": res.text, "output_ok": res.text == ch["demo_output"]}


def deterministic(store=None, out=print) -> int:
    store = store if store is not None else frames.store()
    fail = 0
    total = ok = greedy_ok = gaps = 0
    for item in load("homograph_he.json")["items"]:
        rows = check_item(store, item)
        out(f"item {item['id']}")
        for r in rows:
            out(f"  {r['status']:<4}  {r['bare']}#{r['occ']}  gold {r['gold']}  "
                f"solver {r['solver']}  greedy {r['greedy']}")
        a = sum(r["status"] == "ok" for r in rows)
        c = sum(r["greedy"] == r["gold"] for r in rows)
        n = sum(r["status"] == "gap" for r in rows)
        out(f"-> solver {a}/{len(rows)}, greedy {c}/{len(rows)}, coverage gaps {n}")
        fail += sum(r["status"] == "FAIL" for r in rows)
        total += len(rows)
        ok += a
        greedy_ok += c
        gaps += n
    out(f"summary: {total} homographs, solver {ok}, greedy {greedy_ok}, coverage gaps {gaps}, "
        f"failures {fail}")
    for ch in challenges.load():
        res = check_challenge(store, ch)
        out(f"challenge {ch['id']} ({ch['source']}->{ch['target']})")
        for r in res["rows"]:
            out(f"  {r['status']:<4}  {r['bare']}#{r['occ']}  gold {r['gold']}  "
                f"solver {r['solver']}  greedy {r['greedy']}")
        out(f"  {'ok' if res['output_ok'] else 'FAIL':<4}  demo output  {res['output']}")
        fail += sum(r["status"] != "ok" for r in res["rows"]) + (0 if res["output_ok"] else 1)
    for name in ("torture_he.json", "torture_ar.json"):
        items = load(name)["items"]
        cats = {i.get("category") for i in items}
        out(f"{name}: {len(items)} items in {len(cats)} categories; "
            "judged suites, no deterministic check in this toolkit")
    out("torture: FAIL" if fail else "torture: clean")
    return 1 if fail else 0


def main(argv: list[str]) -> int:
    if argv == ["--deterministic"]:
        return deterministic(frames.store())
    print("usage: python -m mordecai.eval_torture --deterministic")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
