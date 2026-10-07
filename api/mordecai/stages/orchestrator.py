"""Pipeline driver: S0 analyze, S1 resolve, S2 render, S3 repair, S4 verify.
It wires the stages together and holds no state of its own."""
from __future__ import annotations

from .. import frames
from . import s0_analyze, s1_resolve, s2_render, s3_repair, s4_verify
from .types import PipelineResult


def prepare(source: str, *, src_lang: str, tgt_lang: str, provider, key: str | None = None, store=None):
    """S0 analyze, S1 resolve, S2 render, S3 repair."""
    st = store if store is not None else frames.store()
    a = s0_analyze.analyze(source, src_lang, st)
    r = s1_resolve.resolve(a)
    rendered = s2_render.render(a, r, tgt_lang, provider, key)
    return a, r, rendered, s3_repair.repair(rendered.text, tgt_lang)


def finish(a, r, rendered, repaired, *, src_lang: str, tgt_lang: str) -> PipelineResult:
    """S4 verify, and the result."""
    verdict = s4_verify.verify(repaired.text, a, r, tgt_lang)
    return PipelineResult(repaired.text, src_lang, tgt_lang, a, r, rendered, repaired, verdict)


def translate(source: str, *, src_lang: str, tgt_lang: str, provider, key: str | None = None,
              store=None) -> PipelineResult:
    a, r, rendered, repaired = prepare(source, src_lang=src_lang, tgt_lang=tgt_lang, provider=provider,
                                       key=key, store=store)
    return finish(a, r, rendered, repaired, src_lang=src_lang, tgt_lang=tgt_lang)
