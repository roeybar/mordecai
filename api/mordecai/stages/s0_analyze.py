"""S0: tokenize the source text and build the candidate lattice from the
frame store. It does not parse, tag or disambiguate; every candidate stays."""
from __future__ import annotations

from .. import sense_solver, text
from .types import Analysis


def analyze(source: str, src_lang: str, store) -> Analysis:
    tokens = text.tokenize(src_lang, source)
    return Analysis(source, src_lang, tokens, sense_solver.lattice(store, src_lang, tokens))
