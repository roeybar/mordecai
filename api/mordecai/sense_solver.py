"""Toy global sense solver over the frame store.

Candidate lattice: one list of Readings per token, looked up by surface in the
store (with proclitic splits as a fallback). Each frame slot binds the nearest
word on one side (feats.bind says left or right). A word whose readings are all
function words (kind "function") is transparent and skipped, so in "the bark of
the oak" the slot of bark reaches oak. The score is a chain of pairwise terms
over the other words, and an exact dynamic program finds the best assignment in
linear time. This is a toy: one neighbour per side, demo frames hand-set for the
example sentences. General constraint propagation over a parse and a selectional
resource are not built.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import text


@dataclass
class Reading:
    key: str
    prefix: str
    reading: str
    surfaces: dict[str, str]
    sem: str = ""
    rank: int = 100
    slots: tuple[tuple[str, str, bool], ...] = ()
    bind: dict[str, str] = field(default_factory=dict)
    kind: str = ""

    def gloss(self, target: str) -> str:
        return self.surfaces.get(target) or self.surfaces.get("en") or ""


def _reading(store, lang: str, key: str, prefix: str) -> Reading:
    doc = store.get(key)
    feats = doc.get("feats") or {}
    surfaces = {lg: s["text"] for lg, s in doc.get("surface", {}).items()}
    return Reading(
        key=key,
        prefix=prefix,
        reading=surfaces.get(lang, ""),
        surfaces=surfaces,
        sem=str(feats.get("sem") or ""),
        rank=int(feats.get("rank", 100)),
        slots=tuple((s["role"], s["type"], bool(s["required"])) for s in doc.get("slots") or []),
        bind=dict(feats.get("bind") or {}),
        kind=str(doc.get("kind") or ""),
    )


def candidates(store, lang: str, token: str) -> list[Reading]:
    b = text.bare(lang, token)
    keys = store.lookup_by_surface(lang, b)
    prefix = ""
    if not keys:
        for p, rest in text.proclitic_splits(lang, b):
            hit = store.lookup_by_surface(lang, rest)
            if hit:
                keys, prefix = hit, p
                break
    out = [_reading(store, lang, k, prefix) for k in keys]
    out.sort(key=lambda r: (r.rank, r.key))
    return out


def lattice(store, lang: str, tokens: list[str]) -> list[list[Reading]]:
    seen: dict[str, list[Reading]] = {}
    out = []
    for t in tokens:
        if t not in seen:
            seen[t] = candidates(store, lang, t)
        out.append(seen[t])
    return out


def _slot_terms(a: Reading | None, b: Reading | None, side: str) -> int:
    """Terms for the slots of a that bind the neighbour on `side`, tested against b."""
    if a is None:
        return 0
    total = 0
    for role, typ, required in a.slots:
        if a.bind.get(role) != side or b is None:
            continue
        if b.sem == typ:
            total += 1
        elif required:
            total -= 1
    return total


def pair_score(a: Reading | None, b: Reading | None) -> int:
    """Score for left reading a and right reading b (None = no candidates)."""
    return _slot_terms(a, b, "right") + _slot_terms(b, a, "left")


def transparent(cands: list[Reading]) -> bool:
    return bool(cands) and all(r.kind == "function" for r in cands)


def anchors(lat: list[list[Reading]]) -> list[int]:
    return [i for i, c in enumerate(lat) if not transparent(c)]


def score(lat: list[list[Reading]], choice: list[int | None]) -> int:
    def at(i: int) -> Reading | None:
        return None if choice[i] is None else lat[i][choice[i]]

    a = anchors(lat)
    return sum(pair_score(at(x), at(y)) for x, y in zip(a, a[1:]))


@dataclass
class Solution:
    choice: list[int | None]
    score: int
    evaluated: int


def _options(cands: list[Reading]) -> list[int | None]:
    return list(range(len(cands))) if cands else [None]


def _solve_chain(lat: list[list[Reading]]) -> Solution:
    """Exact backward DP; equals the lexicographically first optimum of brute force."""
    n = len(lat)
    if n == 0:
        return Solution([], 0, 0)
    evaluated = 0
    opts = [_options(c) for c in lat]

    def rd(i: int, c: int | None) -> Reading | None:
        return None if c is None else lat[i][c]

    best: list[dict[int | None, int]] = [{} for _ in range(n)]
    for c in opts[n - 1]:
        best[n - 1][c] = 0
    for i in range(n - 2, -1, -1):
        for c in opts[i]:
            top = None
            for d in opts[i + 1]:
                evaluated += 1
                v = pair_score(rd(i, c), rd(i + 1, d)) + best[i + 1][d]
                if top is None or v > top:
                    top = v
            best[i][c] = top
    top0 = max(best[0].values())
    choice: list[int | None] = [next(c for c in opts[0] if best[0][c] == top0)]
    for i in range(n - 1):
        cur = choice[i]
        want = best[i][cur]
        nxt = next(
            d for d in opts[i + 1]
            if pair_score(rd(i, cur), rd(i + 1, d)) + best[i + 1][d] == want
        )
        choice.append(nxt)
    return Solution(choice, top0, evaluated)


def solve(lat: list[list[Reading]]) -> Solution:
    """Exact DP over the non-transparent positions; a transparent position takes its first reading.
    Equals the lexicographically first optimum of brute force over score()."""
    anc = anchors(lat)
    choice: list[int | None] = [0 if transparent(c) else None for c in lat]
    sub = _solve_chain([lat[i] for i in anc])
    for i, c in zip(anc, sub.choice):
        choice[i] = c
    return Solution(choice, sub.score, sub.evaluated)


def greedy(lat: list[list[Reading]]) -> list[int | None]:
    """The baseline: the first candidate everywhere, None where there are none."""
    return [0 if c else None for c in lat]
