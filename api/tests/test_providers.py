import json
import logging

import httpx
import pytest
from mordecai import providers
from mordecai.providers import (
    Chosen,
    ProviderError,
    ProviderNotConfigured,
    ProviderQuotaExhausted,
    RenderRequest,
)

from .conftest import D1, set_models

KEY = "test-key-" + "A1b2C3d4" * 3


def req():
    return RenderRequest("שלום עולם", "he", "en", ["שלום", "עולם"],
                         [Chosen(0, "שלום", "", "שָׁלוֹם", "peace"), None])


def use_transport(monkeypatch, handler):
    monkeypatch.setattr(providers, "_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=30))


def test_demo_needs_no_key():
    p = providers.get("demo")
    assert not p.needs_key and p.render(req(), None) == "peace [עולם]"
    assert [x["name"] for x in providers.public_list()] == ["demo", "anthropic", "xai", "gemini", "openai"]
    assert providers.get("nope") is None


def test_anthropic_request_shape(monkeypatch):
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": " peace world "}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("ANTHROPIC_MODEL", "model-from-env")
    assert providers.get("anthropic").render(req(), KEY) == "peace world"
    assert seen["headers"]["x-api-key"] == KEY
    assert seen["body"]["model"] == "model-from-env"
    assert seen["body"]["system"][0]["cache_control"] == {"type": "ephemeral"}
    user = seen["body"]["messages"][0]["content"]
    assert "Word senses fixed by the frame solver" in user and "- שלום (word 1): peace" in user


def test_anthropic_unset_model_and_upstream_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(ProviderNotConfigured):
        providers.get("anthropic").render(req(), KEY)
    use_transport(monkeypatch, lambda r: httpx.Response(500, text="boom"))
    monkeypatch.setenv("ANTHROPIC_MODEL", "m")
    with pytest.raises(ProviderError):
        providers.get("anthropic").render(req(), KEY)
    use_transport(monkeypatch, lambda r: httpx.Response(200, text="not json"))
    with pytest.raises(ProviderError):
        providers.get("anthropic").render(req(), KEY)


def test_xai_bearer_and_content(monkeypatch):
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": " hi "}}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("XAI_MODEL", "m")
    assert providers.get("xai").render(req(), KEY) == "hi"
    assert seen["auth"] == f"Bearer {KEY}" and seen["url"].endswith("/chat/completions")
    monkeypatch.delenv("XAI_MODEL")
    with pytest.raises(ProviderNotConfigured):
        providers.get("xai").render(req(), KEY)


@pytest.mark.parametrize("name,status", [("anthropic", 200), ("anthropic", 500), ("xai", 200), ("xai", 500),
                                         ("openai", 200), ("openai", 429), ("openai", 500)])
def test_key_never_logged(monkeypatch, caplog, name, status):
    ok = {"content": [{"type": "text", "text": "fine"}], "choices": [{"message": {"content": "fine"}}]}
    use_transport(monkeypatch, lambda r: httpx.Response(status, json=ok if status == 200 else {"e": 1}))
    monkeypatch.setenv("ANTHROPIC_MODEL", "m")
    monkeypatch.setenv("XAI_MODEL", "m")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    for lg in ("", "httpx", "httpcore"):
        caplog.set_level(logging.DEBUG, logger=lg)
    try:
        out = providers.get(name).render(req(), KEY)
    except ProviderError as e:
        out = str(e)
    assert KEY not in caplog.text and KEY not in out


def test_anthropic_complete_gate_shape(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"content": [{"type": "text", "text": "clean"}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("ANTHROPIC_MODEL", "m")
    p = providers.get("anthropic")
    assert p.complete("S", "U", KEY, max_tokens=8, temperature=0) == "clean"
    assert seen[0]["max_tokens"] == 8 and "temperature" not in seen[0]
    assert seen[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    p.render(req(), KEY)
    assert "temperature" not in seen[1] and seen[1]["max_tokens"] == 1024


def test_xai_complete_gate_shape(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "clean"}}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("XAI_MODEL", "m")
    p = providers.get("xai")
    assert p.complete("S", "U", KEY, max_tokens=8, temperature=0) == "clean"
    assert seen[0]["max_tokens"] == 8 and seen[0]["temperature"] == 0
    assert seen[0]["messages"][0] == {"role": "system", "content": "S"}
    p.render(req(), KEY)
    assert "temperature" not in seen[1] and seen[1]["max_tokens"] == 1024


def test_openai_request_shape(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": " hi "}}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    assert providers.get("openai").render(req(), KEY) == "hi"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    body = seen["body"]
    assert body["model"] == "gpt-6-luna"
    assert body["messages"][0]["content"].startswith("Translate the user's text from Hebrew to English")
    assert "Word senses fixed" in body["messages"][1]["content"]
    assert body["max_completion_tokens"] == 1024 and body["reasoning_effort"] == "none"
    assert "max_tokens" not in body and "temperature" not in body
    monkeypatch.delenv("OPENAI_MODEL")
    with pytest.raises(ProviderNotConfigured):
        providers.get("openai").render(req(), KEY)


def test_openai_complete_gate_shape(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "clean"}}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    p = providers.get("openai")
    assert p.complete("S", "U", KEY, max_tokens=8, temperature=0) == "clean"
    assert seen[0]["max_completion_tokens"] == 8 and seen[0]["reasoning_effort"] == "none"
    assert "max_tokens" not in seen[0] and "temperature" not in seen[0]
    assert seen[0]["messages"][0] == {"role": "system", "content": "S"}
    p.render(req(), KEY)
    assert seen[1]["max_completion_tokens"] == 1024 and "max_tokens" not in seen[1]


def test_openai_429_is_quota_and_xai_429_is_not(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.setenv("XAI_MODEL", "m")
    use_transport(monkeypatch, lambda r: httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderQuotaExhausted):
        providers.get("openai").render(req(), KEY)
    with pytest.raises(ProviderError) as e:
        providers.get("xai").render(req(), KEY)
    assert not isinstance(e.value, ProviderQuotaExhausted)
    use_transport(monkeypatch, lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(ProviderError) as e:
        providers.get("openai").render(req(), KEY)
    assert not isinstance(e.value, ProviderQuotaExhausted)


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/model-from-env:generateContent"


def gemini_reply(text="clean", **extra):
    cand = {"content": {"role": "model", "parts": [{"text": text}]}, **extra}
    return httpx.Response(200, json={"candidates": [cand]})


def test_gemini_request_shape(monkeypatch):
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return gemini_reply(" peace world ")

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("GEMINI_MODEL", "model-from-env")
    assert providers.get("gemini").render(req(), KEY) == "peace world"
    assert seen["url"] == GEMINI_URL and "key=" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == KEY and "authorization" not in seen["headers"]
    body = seen["body"]
    assert body["systemInstruction"]["parts"][0]["text"].startswith(
        "Translate the user's text from Hebrew to English")
    assert body["contents"][0]["role"] == "user"
    assert "Word senses fixed" in body["contents"][0]["parts"][0]["text"]
    assert body["generationConfig"] == {"maxOutputTokens": 1024}


def test_gemini_complete_gate_shape(monkeypatch):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
            {"text": "thinking about it", "thought": True}, {"text": " clean "}]}}]})

    use_transport(monkeypatch, handler)
    monkeypatch.setenv("GEMINI_MODEL", "m")
    p = providers.get("gemini")
    assert p.complete("S", "U", KEY, max_tokens=8, temperature=0) == "clean"
    # thought tokens count against the cap, so the classifier call never asks for fewer than 256
    assert seen[0]["generationConfig"] == {"maxOutputTokens": 256, "temperature": 0}
    assert seen[0]["systemInstruction"] == {"parts": [{"text": "S"}]}
    assert seen[0]["contents"] == [{"role": "user", "parts": [{"text": "U"}]}]
    assert "thinkingConfig" not in json.dumps(seen[0])
    p.render(req(), KEY)
    assert seen[1]["generationConfig"] == {"maxOutputTokens": 1024}


def test_gemini_errors(monkeypatch):
    p = providers.get("gemini")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(ProviderNotConfigured):
        p.render(req(), KEY)
    monkeypatch.setenv("GEMINI_MODEL", "a/b")
    with pytest.raises(ProviderNotConfigured):
        p.render(req(), KEY)
    monkeypatch.setenv("GEMINI_MODEL", "m")

    def transport_error(request):
        raise httpx.ConnectError("down")

    use_transport(monkeypatch, lambda r: httpx.Response(500, text="boom"))
    with pytest.raises(ProviderError) as e:
        p.render(req(), KEY)
    assert not isinstance(e.value, ProviderQuotaExhausted)
    use_transport(monkeypatch, lambda r: httpx.Response(429, text="slow down"))
    with pytest.raises(ProviderQuotaExhausted) as e:
        p.render(req(), KEY)
    assert isinstance(e.value, ProviderError)
    bad = [
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"candidates": []}),
        lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
        transport_error,
    ]
    for handler in bad:
        use_transport(monkeypatch, handler)
        with pytest.raises(ProviderError):
            p.render(req(), KEY)


def _candidate(**c):
    return httpx.Response(200, json={"candidates": [c]})


@pytest.mark.parametrize("response", [
    _candidate(finishReason="MAX_TOKENS", content={"role": "model"}),
    _candidate(finishReason="MAX_TOKENS", content={"role": "model", "parts": []}),
    _candidate(finishReason="MAX_TOKENS", content={"role": "model", "parts": [{"text": "cle"}]}),
    _candidate(content={"role": "model", "parts": [{"text": " "}]}),
    _candidate(content={"role": "model", "parts": [{"text": "only thoughts", "thought": True}]}),
], ids=["no-parts", "empty-parts", "cut-off-text", "blank-text", "thought-only"])
def test_gemini_empty_or_truncated_is_an_error(monkeypatch, response):
    use_transport(monkeypatch, lambda r: response)
    monkeypatch.setenv("GEMINI_MODEL", "m")
    with pytest.raises(ProviderError):
        providers.get("gemini").complete("S", "U", KEY, max_tokens=8, temperature=0)


@pytest.mark.parametrize("status", [200, 429, 500])
def test_gemini_key_never_logged(monkeypatch, caplog, status):
    use_transport(monkeypatch, lambda r: gemini_reply("fine") if status == 200
                  else httpx.Response(status, json={"e": 1}))
    monkeypatch.setenv("GEMINI_MODEL", "m")
    for lg in ("", "httpx", "httpcore"):
        caplog.set_level(logging.DEBUG, logger=lg)
    try:
        out = providers.get("gemini").render(req(), KEY)
    except ProviderError as e:
        out = str(e)
    assert KEY not in caplog.text and KEY not in out


def test_client_is_reused(monkeypatch):
    monkeypatch.setattr(providers, "_shared", None)
    first = providers._client()
    try:
        assert providers._client() is first
        assert isinstance(first, httpx.Client) and first.timeout == httpx.Timeout(30)
        assert not first.is_closed
        first.cookies.extract_cookies(httpx.Response(
            200, headers={"set-cookie": "a=b; Path=/"}, request=httpx.Request("GET", "https://vendor.test/")))
        assert len(first.cookies.jar) == 0
    finally:
        first.close()


def test_client_keeps_no_cookies(monkeypatch):
    seen = []
    make = providers._make_client

    def handler(request):
        seen.append(request.headers)
        headers = {"set-cookie": "__cf_bm=abc; Path=/"} if len(seen) == 1 else {}
        return httpx.Response(200, json={"ok": True}, headers=headers)

    monkeypatch.setattr(providers, "_shared", None)
    monkeypatch.setattr(providers, "_make_client",
                        lambda transport=None: make(transport=httpx.MockTransport(handler)))
    first = providers._client()
    first.post("https://vendor.test/v1", json={})
    second = providers._client()
    second.post("https://vendor.test/v1", json={})
    assert second is first and providers._shared is first
    assert len(seen) == 2 and "cookie" not in seen[1]
    assert len(providers._client().cookies.jar) == 0


def test_model_lists_and_gate_model_from_env(monkeypatch):
    p = providers.get("anthropic")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_MODELS", "b,c")
    assert p.default_model() is None and p.models() == [] and p.gate_model() is None
    monkeypatch.setenv("ANTHROPIC_MODEL", "a")
    assert p.models() == ["a", "b", "c"]  # the default missing from the list is prepended
    monkeypatch.setenv("ANTHROPIC_MODELS", "b, a ,bad/id,,b,c d,x" + "y" * 70)
    assert p.models() == ["b", "a"]  # bad ids and repeats are dropped, the listed order is kept
    monkeypatch.delenv("ANTHROPIC_MODELS")
    assert p.models() == ["a"]
    assert p.gate_model() == "a"
    monkeypatch.setenv("ANTHROPIC_GATE_MODEL", "g")
    assert p.gate_model() == "g"
    monkeypatch.setenv("ANTHROPIC_GATE_MODEL", "bad/id")
    assert p.gate_model() == "a"
    monkeypatch.setenv("ANTHROPIC_MODEL", "bad/id")
    assert p.default_model() is None and p.models() == []


def test_public_list_carries_models(monkeypatch):
    set_models(monkeypatch)
    rows = {p["name"]: p["models"] for p in providers.public_list()}
    assert rows["demo"] == []
    gem = rows["gemini"]
    assert [m["id"] for m in gem] == D1["GEMINI"]
    assert [m["default"] for m in gem] == [True, False, False, False, False]
    assert all(m["efforts"] == ["minimal", "low", "medium", "high"] for m in gem)
    assert all(list(m) == ["id", "efforts", "default"] for m in gem)
    assert all(m["efforts"] == [] for m in rows["xai"])
    assert rows["openai"][0]["efforts"] == ["none", "low", "medium", "high", "xhigh", "max"]
    assert rows["openai"][1]["efforts"] == ["low", "medium", "high", "xhigh", "max"]


ANY_REPLY = {"content": [{"type": "text", "text": "ok"}], "choices": [{"message": {"content": "ok"}}],
             "candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}}]}


def sent(monkeypatch, call):
    """The (url, body) of every vendor request `call` makes."""
    seen = []

    def handler(request):
        seen.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=ANY_REPLY)

    use_transport(monkeypatch, handler)
    call()
    return seen


G = "generationConfig"
EFFORT_CASES = [
    ("gemini", None, None, {G: {"maxOutputTokens": 1024, "thinkingConfig": {"thinkingLevel": "minimal"}}}),
    ("gemini", "gemini-3.5-flash", "high",
     {G: {"maxOutputTokens": 8192, "thinkingConfig": {"thinkingLevel": "high"}}}),
    ("gemini", "gemini-3.6-flash", None,
     {G: {"maxOutputTokens": 1024, "thinkingConfig": {"thinkingLevel": "minimal"}}}),
    ("openai", None, None, {"model": "gpt-6-luna", "reasoning_effort": "none", "max_completion_tokens": 1024,
                            "temperature": None}),
    ("openai", "gpt-6.1-sol", None, {"model": "gpt-6.1-sol", "reasoning_effort": "low",
                                     "max_completion_tokens": 1024}),
    ("openai", "gpt-6.1-sol", "max", {"model": "gpt-6.1-sol", "reasoning_effort": "max",
                                       "max_completion_tokens": 8192}),
    ("anthropic", None, None, {"model": "claude-haiku-5-5", "output_config": {"effort": "low"},
                               "thinking": {"type": "disabled"}, "max_tokens": 1024, "temperature": None}),
    ("anthropic", "claude-haiku-5-5", "high", {"output_config": {"effort": "high"}, "thinking": None,
                                               "max_tokens": 8192, "temperature": None}),
    ("anthropic", "claude-sonnet-5-5", None, {"output_config": {"effort": "low"},
                                              "thinking": {"type": "between_tools"}, "max_tokens": 1024,
                                              "temperature": None}),
    ("anthropic", "claude-opus-5-5", None, {"model": "claude-opus-5-5", "output_config": {"effort": "low"},
                                            "thinking": None, "max_tokens": 1024, "temperature": None}),
    ("xai", "grok-4.7", None, {"model": "grok-4.7", "max_tokens": 1024, "reasoning_effort": None,
                               "temperature": None}),
]


@pytest.mark.parametrize("name,model,effort,want", EFFORT_CASES,
                         ids=[f"{c[0]}-{c[1] or 'default'}-{c[2] or 'lowest'}" for c in EFFORT_CASES])
def test_effort_request_shape(monkeypatch, name, model, effort, want):
    set_models(monkeypatch)
    p = providers.Bound(providers.get(name), model, effort)
    seen = sent(monkeypatch, lambda: p.render(req(), KEY))
    assert len(seen) == 1
    body = seen[0][1]
    assert {k: body.get(k) for k in want} == want


CLASSIFIER_CASES = [
    ("anthropic", "claude-opus-5-5", "claude-haiku-5-5"),
    ("gemini", "gemini-3.6-flash", "gemini-3.5-flash"),
    ("openai", "gpt-6.1-sol", "gpt-6-luna"),
    ("xai", "grok-4.7", "grok-4.20-0309-non-reasoning"),
]


@pytest.mark.parametrize("name,translation_model,gate_model", CLASSIFIER_CASES,
                         ids=[c[0] for c in CLASSIFIER_CASES])
def test_classifier_call_uses_the_gate_model(monkeypatch, name, translation_model, gate_model):
    set_models(monkeypatch)
    env = name.upper()
    monkeypatch.setenv(f"{env}_MODEL", translation_model)
    monkeypatch.setenv(f"{env}_GATE_MODEL", gate_model)
    p = providers.get(name)
    seen = sent(monkeypatch, lambda: p.complete("S", "U", KEY, max_tokens=8, temperature=0))
    url, body = seen[0]
    if name == "anthropic":
        assert body["model"] == gate_model and body["output_config"] == {"effort": "low"}
        assert body["thinking"] == {"type": "disabled"} and "temperature" not in body
        assert body["max_tokens"] == 8
    elif name == "gemini":
        assert f"models/{gate_model}:" in url
        assert body[G] == {"maxOutputTokens": 256, "temperature": 0,
                           "thinkingConfig": {"thinkingLevel": "minimal"}}
    elif name == "openai":
        assert body["model"] == gate_model and body["reasoning_effort"] == "none"
        assert body["max_completion_tokens"] == 8 and "temperature" not in body
    else:
        assert body["model"] == gate_model and body["temperature"] == 0 and body["max_tokens"] == 8
        assert "reasoning_effort" not in body


def test_bound_render_takes_the_pick_and_complete_does_not(monkeypatch):
    set_models(monkeypatch)
    p = providers.Bound(providers.get("anthropic"), "claude-opus-5-5", "high")
    assert (p.name, p.needs_key, p.hosted) == ("anthropic", True, False)
    seen = sent(monkeypatch,
                lambda: (p.render(req(), KEY), p.complete("S", "U", KEY, max_tokens=8, temperature=0)))
    render, gate = seen[0][1], seen[1][1]
    assert render["model"] == "claude-opus-5-5" and render["output_config"] == {"effort": "high"}
    assert gate["model"] == "claude-haiku-5-5" and gate["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("name", ["gemini", "openai", "anthropic"])
def test_a_model_without_a_level_table_sends_no_effort(monkeypatch, name):
    monkeypatch.setenv(f"{name.upper()}_MODEL", "some-model")
    p = providers.get(name)
    seen = sent(monkeypatch, lambda: p.render(req(), KEY))
    flat = json.dumps(seen[0][1])
    for word in ("thinkingConfig", "reasoning_effort", "output_config", "thinking\""):
        assert word not in flat
    body = seen[0][1]
    cap = body.get("max_tokens") or body.get("max_completion_tokens") or body[G]["maxOutputTokens"]
    assert cap == 1024
