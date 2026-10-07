"""Translate routes. Errors are small fixed bodies: they never echo the input,
the key or the matched term."""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .. import challenges, frames, gate, hosted, langs, providers
from ..stages import orchestrator

log = logging.getLogger(__name__)
router = APIRouter()

MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "4000"))
_KEY_RE = re.compile(r"^[\x21-\x7e]{16,512}$")
_GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "goldens" / "homograph_he.json"


class TranslateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    source: str = Field(pattern=r"^[a-z]{2,3}$")
    target: str = Field(pattern=r"^[a-z]{2,3}$")
    provider: str = Field(default="demo", pattern=r"^[a-z_]{1,20}$")
    model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,64}$")
    effort: str | None = Field(default=None, pattern=r"^[a-z]{1,16}$")


def _err(status: int, error: str, **extra) -> JSONResponse:
    return JSONResponse({"error": error, **extra}, status_code=status)


@router.get("/languages")
def languages():
    return langs.public_list()


@router.get("/providers")
def provider_list():
    return providers.public_list() + hosted.public_list()


def _examples() -> list[dict]:
    item = json.loads(_GOLDEN.read_text(encoding="utf-8"))["items"][0]
    out = [{"id": item["id"], "text": item["he"], "source": "he", "target": "en"}]
    out += [{"id": c["id"], "text": c["text"], "source": c["source"], "target": c["target"]}
            for c in challenges.load()]
    return out


@router.get("/example")
def example():
    return _examples()


def _is_example(body: TranslateIn) -> bool:
    """The demo provider has no classifier (no key), so it accepts only the built-in examples."""
    t = unicodedata.normalize("NFC", body.text.strip())
    return any(unicodedata.normalize("NFC", e["text"]) == t and e["source"] == body.source
               and e["target"] == body.target for e in _examples())


def _peer(request: Request) -> str | None:
    return request.client.host if request.client else None


def _admit(request: Request, prov) -> tuple[JSONResponse | None, str | None]:
    """Hosted mode only: the hosted provider needs the server key (checked first, nothing counted);
    then every request, whichever provider, counts one attempt against the visitor's limit."""
    cfg = hosted.config()
    if not cfg.on:
        return None, None
    is_hosted = getattr(prov, "hosted", False)
    if is_hosted and not cfg.key:
        return _err(503, "provider_not_configured"), None
    who = hosted.client_key(_peer(request), request.headers.get("x-forwarded-for"), cfg.trusted)
    if not hosted.LIMITER.hit(who):
        log.info("hosted: demo limit reached")
        return _err(429, "demo_limit", attempts=hosted.ATTEMPTS), None
    return None, (cfg.key if is_hosted else None)


def _prepare(body: TranslateIn, request: Request, x_provider_key: str | None):
    """The request checks and the hosted admission, shared by both translate routes: (refusal, None),
    or (None, (provider, key)) once admitted (counted, in hosted mode)."""
    if not langs.known(body.source) or not langs.known(body.target):
        return _err(400, "unknown_language"), None
    if body.source == body.target:
        return _err(400, "same_language"), None
    prov = hosted.provider() if body.provider == hosted.NAME else providers.get(body.provider)
    if prov is None:
        return _err(400, "unknown_provider"), None
    if x_provider_key is not None and not _KEY_RE.match(x_provider_key):
        return _err(400, "bad_key"), None
    if prov.needs_key and x_provider_key is None:
        return _err(400, "key_required"), None
    models = prov.models() if hasattr(prov, "models") else []
    if body.model is not None and body.model not in models:
        return _err(400, "unknown_model"), None
    chosen = body.model or (prov.default_model() if hasattr(prov, "default_model") else None)
    if body.effort is not None and (chosen is None or body.effort not in prov.efforts(chosen)):
        return _err(400, "unknown_effort"), None

    if not hasattr(prov, "complete") and not _is_example(body):
        return _err(422, "demo_examples_only"), None
    refused, server_key = _admit(request, prov)
    if refused is not None:
        return refused, None
    key = server_key if getattr(prov, "hosted", False) else x_provider_key
    if hasattr(prov, "models"):
        prov = providers.Bound(prov, body.model, body.effort)
    return None, (prov, key)


def _gate(text: str, lang: str, stage: str, prov, key, policy):
    """None when the text passes, else (status, body) of the refusal."""
    try:
        res = gate.check(text, lang=lang, stage=stage, provider=prov, key=key, policy=policy)
    except providers.ProviderNotConfigured:
        return 503, {"error": "provider_not_configured"}
    except providers.ProviderQuotaExhausted:
        return 503, {"error": "quota_exhausted"}
    except gate.GateUnavailable:
        gate.log_unavailable(stage)
        return 502, {"error": "gate_unavailable", "stage": stage}
    if res.rejected:
        gate.log_rejection(stage, res)
        return 422, {"error": "blocked_content", "category": res.category, "stage": stage}
    return None


def _result(body: TranslateIn, out) -> dict:
    an, rs = out.analysis, out.resolution
    readings = []
    greedy_rows = []
    for i, (tok, cands) in enumerate(zip(an.tokens, an.lattice)):
        if not cands:
            continue
        pick = cands[rs.choice[i]]
        readings.append({
            "index": i, "token": tok, "prefix": pick.prefix, "reading": pick.reading,
            "gloss": pick.gloss(body.target),
            "candidates": [{"reading": c.reading, "gloss": c.gloss(body.target)} for c in cands],
            "choice": rs.choice[i],
        })
        g = cands[rs.greedy[i]]
        greedy_rows.append({"index": i, "token": tok, "reading": g.reading,
                            "gloss": g.gloss(body.target)})
    return {
        "text": out.text,
        "provider": out.rendered.provider,
        "notice": out.rendered.notice,
        "source": body.source,
        "target": body.target,
        "source_status": langs.get(body.source).status,
        "target_status": langs.get(body.target).status,
        "readings": readings,
        "greedy": greedy_rows,
        "solver": {"score": rs.score, "evaluated": rs.evaluated},
        "verify": {"ok": out.verdict.ok, "notes": out.verdict.notes},
        "notes": out.repaired.notes,
    }


def _stages(body: TranslateIn, prov, key):
    """Yields "input" before the input gate, "translate" before S0-S3, "output" before S4 and the
    output gate, then (status, body) as POST /translate answers."""
    policy = gate.policy()
    yield "input"
    refused = _gate(body.text, body.source, "input", prov, key, policy)
    if refused:
        yield refused
        return
    yield "translate"
    try:
        a, r, rendered, repaired = orchestrator.prepare(body.text, src_lang=body.source, tgt_lang=body.target,
                                                       provider=prov, key=key, store=frames.store())
    except providers.ProviderNotConfigured:
        yield 503, {"error": "provider_not_configured"}
        return
    except providers.ProviderQuotaExhausted:
        yield 503, {"error": "quota_exhausted"}
        return
    except providers.ProviderError:
        yield 502, {"error": "upstream_failed"}
        return
    yield "output"
    out = orchestrator.finish(a, r, rendered, repaired, src_lang=body.source, tgt_lang=body.target)
    refused = _gate(out.text, body.target, "output", prov, key, policy)
    yield refused or (200, _result(body, out))


@router.post("/translate")
def translate(body: TranslateIn, request: Request, x_provider_key: str | None = Header(default=None)):
    refused, ready = _prepare(body, request, x_provider_key)
    if refused is not None:
        return refused
    for item in _stages(body, *ready):
        last = item
    status, payload = last
    return payload if status == 200 else JSONResponse(payload, status_code=status)


def _line(obj) -> bytes:
    """One NDJSON line, in the bytes Starlette's JSONResponse writes."""
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"


def _ndjson(body: TranslateIn, prov, key):
    for item in _stages(body, prov, key):
        if isinstance(item, str):
            yield _line({"stage": item})
            continue
        status, p = item
        if status == 200:
            yield _line(p)
        else:
            rest = {k: v for k, v in p.items() if k != "error"}
            yield _line({"error": p["error"], "status": status, **rest})


@router.post("/translate/stream")
def translate_stream(body: TranslateIn, request: Request, x_provider_key: str | None = Header(default=None)):
    refused, ready = _prepare(body, request, x_provider_key)
    if refused is not None:
        return refused
    return StreamingResponse(_ndjson(body, *ready), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no"})
