"""Render providers. The demo provider needs no key; the others take the
caller's own key per request (BYOK). A key is used for that one call, is
never stored, never logged and never returned. The keyed providers also answer the
content gate's classifier call (complete) with the same key, on the provider's fixed classifier
model (<PROVIDER>_GATE_MODEL). GeminiProvider can also
run on the server's own key for the closed hosted demo (see hosted.py). OpenAIProvider maps an API
answer of 429 to ProviderQuotaExhausted, as GeminiProvider does."""
from __future__ import annotations

import http.cookiejar
import os
import re
import threading
from dataclasses import dataclass

import httpx

from . import langs, text


class ProviderError(Exception):
    pass


class ProviderNotConfigured(ProviderError):
    pass


class ProviderQuotaExhausted(ProviderError):
    """The provider answered 429: the key's quota is used up."""


@dataclass
class Chosen:
    index: int
    token: str
    prefix: str
    reading: str
    gloss: str


@dataclass
class RenderRequest:
    source_text: str
    source_lang: str
    target_lang: str
    tokens: list[str]
    chosen: list[Chosen | None]


def build_prompt(req: RenderRequest) -> tuple[str, str]:
    src = langs.get(req.source_lang)
    tgt = langs.get(req.target_lang)
    system = f"Translate the user's text from {src.name} to {tgt.name}. Output only the translation."
    user = req.source_text
    picked = [c for c in req.chosen if c is not None]
    if picked:
        user += "\n\nWord senses fixed by the frame solver (keep them):\n"
        user += "\n".join(f"- {c.token} (word {c.index + 1}): {c.gloss or c.reading}" for c in picked)
    return system, user


_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
RENDER_MAX_TOKENS = 1024       # the translation cap at a model's lowest effort level, or with no level table
RENDER_DEEP_MAX_TOKENS = 8192  # above the lowest level the model thinks more; thinking counts against the cap


class _NoCookies(http.cookiejar.DefaultCookiePolicy):
    """Refuses every cookie, so nothing a vendor sets rides on another visitor's request."""

    def set_ok(self, cookie, request):
        return False

    def return_ok(self, cookie, request):
        return False


_shared: httpx.Client | None = None
_shared_lock = threading.Lock()


def _make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    jar = http.cookiejar.CookieJar(policy=_NoCookies())
    if transport is None:
        return httpx.Client(timeout=30, cookies=jar)
    return httpx.Client(timeout=30, cookies=jar, transport=transport)


def _client() -> httpx.Client:
    global _shared
    if _shared is None:
        with _shared_lock:
            if _shared is None:
                _shared = _make_client()
    return _shared


class DemoProvider:
    name = "demo"
    needs_key = False
    notice = "Demo provider: a word-by-word gloss built from the demo frames. It is not a translation model."

    def render(self, req: RenderRequest, key: str | None) -> str:
        parts = []
        for tok, c in zip(req.tokens, req.chosen):
            if c is None:
                parts.append(f"[{tok}]")
            elif req.target_lang == "en":
                parts.append("-".join(text.proclitic_gloss(req.source_lang, c.prefix) + [c.gloss]))
            else:
                parts.append(c.gloss or f"[{tok}]")
        return " ".join(parts)


def _env_model(name: str) -> str | None:
    m = os.environ.get(name, "").strip()
    return m if _MODEL_RE.match(m) else None


class _Keyed:
    """A provider that runs on a key. Its default translation model, the models a request may pick,
    each model's effort levels (lowest first) and its fixed classifier model all come from the
    environment (README, Configuration)."""
    env = ""
    efforts_by_model: dict[str, tuple[str, ...]] = {}

    def default_model(self) -> str | None:
        return _env_model(f"{self.env}_MODEL")

    def models(self) -> list[str]:
        d = self.default_model()
        if d is None:
            return []
        raw = (m.strip() for m in os.environ.get(f"{self.env}_MODELS", "").split(","))
        listed = list(dict.fromkeys(m for m in raw if _MODEL_RE.match(m)))
        return listed if d in listed else [d, *listed]

    def gate_model(self) -> str | None:
        return _env_model(f"{self.env}_GATE_MODEL") or self.default_model()

    def efforts(self, model: str) -> tuple[str, ...]:
        return self.efforts_by_model.get(model, ())

    def render(self, req: RenderRequest, key: str | None, *, model: str | None = None,
               effort: str | None = None) -> str:
        model = model or self.default_model()
        if model is None:
            raise ProviderNotConfigured(f"{self.env}_MODEL is not set")
        levels = self.efforts(model)
        effort = effort or (levels[0] if levels else None)
        deep = bool(levels) and effort != levels[0]
        return self._call(*build_prompt(req), key, model=model, effort=effort,
                          max_tokens=RENDER_DEEP_MAX_TOKENS if deep else RENDER_MAX_TOKENS, temperature=None)

    def complete(self, system: str, user: str, key: str | None, *, max_tokens: int = 1024,
                 temperature: float | None = None) -> str:
        """The content gate's classifier call: the gate model at its lowest level, whatever the
        translation picked."""
        model = self.gate_model()
        if model is None:
            raise ProviderNotConfigured(f"{self.env}_MODEL is not set")
        levels = self.efforts(model)
        return self._call(system, user, key, model=model, effort=levels[0] if levels else None,
                          max_tokens=max_tokens, temperature=temperature)


ANTHROPIC_LEVELS = ("low", "medium", "high", "xhigh", "max")
OPENAI_LEVELS = ("low", "medium", "high", "xhigh", "max")
GEMINI_LEVELS = ("minimal", "low", "medium", "high")


class AnthropicProvider(_Keyed):
    name = "anthropic"
    needs_key = True
    notice = ("Rendered by the Anthropic API with your key. "
              "The key is used for this request only and is not stored.")
    env = "ANTHROPIC"
    efforts_by_model = {"claude-haiku-5-5": ANTHROPIC_LEVELS, "claude-sonnet-5-5": ANTHROPIC_LEVELS,
                        "claude-opus-5-5": ANTHROPIC_LEVELS}
    # thinking at the lowest level; Opus 5.5 cannot turn thinking off, so it has no entry
    thinking_off = {"claude-haiku-5-5": {"type": "disabled"}, "claude-sonnet-5-5": {"type": "between_tools"}}

    def _call(self, system: str, user: str, key: str | None, *, model: str, effort: str | None,
              max_tokens: int, temperature: float | None) -> str:
        headers = {"x-api-key": key or "", "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": model, "max_tokens": max_tokens,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": user}]}
        levels = self.efforts(model)
        # no temperature is sent (the caller's value is dropped here): the 5.5 models reject a
        # non-default one, and they reject an assistant prefill too
        if effort is not None:
            body["output_config"] = {"effort": effort}
            if effort == levels[0] and model in self.thinking_off:
                body["thinking"] = self.thinking_off[model]
        try:
            c = _client()
            r = c.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            if r.status_code != 200:
                raise ProviderError("upstream_failed")
            blocks = r.json()["content"]
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("upstream_failed") from e


def _chat_completions(base: str, key: str | None, model: str, system: str, user: str, *,
                      max_tokens: int = 1024, temperature: float | None = None,
                      quota_on_429: bool = False, use_max_completion_tokens: bool = False,
                      reasoning_effort: str | None = None) -> str:
    body = {"model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    body["max_completion_tokens" if use_max_completion_tokens else "max_tokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    try:
        c = _client()
        r = c.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key or ''}"},
                   json=body)
        if quota_on_429 and r.status_code == 429:
            raise ProviderQuotaExhausted("quota_exhausted")
        if r.status_code != 200:
            raise ProviderError("upstream_failed")
        return r.json()["choices"][0]["message"]["content"].strip()
    except ProviderError:
        raise
    except Exception as e:
        raise ProviderError("upstream_failed") from e


class XaiProvider(_Keyed):
    name = "xai"
    needs_key = True
    notice = ("Rendered by the xAI API with your key. "
              "The key is used for this request only and is not stored.")
    env = "XAI"
    efforts_by_model = {}

    def _call(self, system: str, user: str, key: str | None, *, model: str, effort: str | None,
              max_tokens: int, temperature: float | None) -> str:
        return _chat_completions("https://api.x.ai/v1", key, model, system, user,
                                 max_tokens=max_tokens, temperature=temperature)


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MIN_TOKENS = 256  # gemini-3.x thinks by default and thought tokens count against the cap


class GeminiProvider(_Keyed):
    name = "gemini"
    needs_key = True
    notice = ("Rendered by the Gemini API with your key. "
              "The key is used for this request only and is not stored.")
    hosted_notice = "Rendered by the Gemini API on this demo's own key (hosted demo, free tier)."
    env = "GEMINI"
    # the five curated models each accept every level in GEMINI_LEVELS; minimal is the lowest
    efforts_by_model = {m: GEMINI_LEVELS for m in ("gemini-3.5-flash", "gemini-3.1-flash-lite",
                                                   "gemini-3-flash-preview", "gemini-3.6-flash",
                                                   "gemini-3.5-flash-lite")}

    def _call(self, system: str, user: str, key: str | None, *, model: str, effort: str | None,
              max_tokens: int, temperature: float | None) -> str:
        config: dict = {"maxOutputTokens": max(max_tokens, GEMINI_MIN_TOKENS)}
        if temperature is not None:
            config["temperature"] = temperature
        if effort is not None:
            config["thinkingConfig"] = {"thinkingLevel": effort}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": config}
        headers = {"x-goog-api-key": key or "", "content-type": "application/json"}
        try:
            c = _client()
            r = c.post(f"{GEMINI_BASE}/models/{model}:generateContent", headers=headers, json=body)
            if r.status_code == 429:
                raise ProviderQuotaExhausted("quota_exhausted")
            if r.status_code != 200:
                raise ProviderError("upstream_failed")
            cand = r.json()["candidates"][0]
            out = "".join(p.get("text", "") for p in cand["content"]["parts"]
                          if not p.get("thought")).strip()
            if cand.get("finishReason") == "MAX_TOKENS" or not out:
                raise ProviderError("upstream_failed")  # cut off or empty: never a usable answer
            return out
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("upstream_failed") from e


class OpenAIProvider(_Keyed):
    name = "openai"
    needs_key = True
    notice = ("Rendered by the OpenAI API with your key. "
              "The key is used for this request only and is not stored.")
    env = "OPENAI"
    efforts_by_model = {"gpt-6-luna": ("none", *OPENAI_LEVELS), "gpt-6.1-sol": OPENAI_LEVELS}

    def _call(self, system: str, user: str, key: str | None, *, model: str, effort: str | None,
              max_tokens: int, temperature: float | None) -> str:
        # reasoning-capable model: the cap is max_completion_tokens, no temperature is sent
        # (the caller's value is dropped here), and the effort is the model's reasoning_effort
        return _chat_completions("https://api.openai.com/v1", key, model, system, user,
                                 max_tokens=max_tokens, temperature=None, quota_on_429=True,
                                 use_max_completion_tokens=True, reasoning_effort=effort)


PROVIDERS = {p.name: p for p in (DemoProvider(), AnthropicProvider(), XaiProvider(), GeminiProvider(),
                                  OpenAIProvider())}


def get(name: str):
    return PROVIDERS.get(name)


class Bound:
    """A keyed or hosted provider with one request's translation model and effort: render uses them;
    complete, the classifier call, keeps the fixed gate model."""

    def __init__(self, base, model: str | None, effort: str | None):
        self.base, self.model, self.effort = base, model, effort
        self.name, self.notice, self.needs_key = base.name, base.notice, base.needs_key
        self.hosted = getattr(base, "hosted", False)

    def render(self, req, key):
        return self.base.render(req, key, model=self.model, effort=self.effort)

    def complete(self, system, user, key, *, max_tokens=1024, temperature=None):
        return self.base.complete(system, user, key, max_tokens=max_tokens, temperature=temperature)


def models_list(p) -> list[dict]:
    if not hasattr(p, "models"):
        return []
    d = p.default_model()
    return [{"id": m, "efforts": list(p.efforts(m)), "default": m == d} for m in p.models()]


def public_list() -> list[dict]:
    return [{"name": p.name, "label": p.name, "needs_key": p.needs_key, "hosted": False, "notice": p.notice,
             "models": models_list(p)}
            for p in PROVIDERS.values()]
