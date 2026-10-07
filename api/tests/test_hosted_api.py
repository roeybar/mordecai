import json
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from mordecai import gate, hosted, providers
from mordecai.main import app
from mordecai.routes import translate as tr

from .conftest import (
    CHARGER_PHONE,
    CHARGER_RIFLE,
    SEED,
    SERVER_KEY,
    blocked_term,
    fake_classifier,
    provider_handler,
    set_models,
    split_body,
    use_handler,
)

KEY = "test-key-" + "B5n6M7q8" * 3
PEER = "203.0.113.7"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def hclient(hosted_on):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def who(monkeypatch):
    w = {"peer": PEER}
    monkeypatch.setattr(tr, "_peer", lambda r: w["peer"])
    return w


@pytest.fixture
def upstream(monkeypatch):
    """The mocked Gemini API: records the bodies and the x-goog-api-key of every call."""
    rec = {"seen": [], "keys": []}
    inner = provider_handler("gemini", fake_classifier, seen=rec["seen"])

    def handler(request):
        rec["keys"].append(request.headers["x-goog-api-key"])
        return inner(request)

    use_handler(monkeypatch, handler)
    return rec


def hpost(client, text=CHARGER_PHONE, provider="hosted", headers=None, source="en", target="he"):
    return client.post("/translate", headers=headers or {},
                       json={"text": text, "source": source, "target": target, "provider": provider})


def debug_logs(caplog):
    for lg in ("", "httpx", "httpcore"):
        caplog.set_level(logging.DEBUG, logger=lg)


def test_fresh_clone_has_no_hosted_provider(client, who):
    plist = client.get("/providers").json()
    assert [p["name"] for p in plist] == ["demo", "anthropic", "xai", "gemini", "openai"]
    assert all(p["hosted"] is False and p["label"] == p["name"] for p in plist)
    r = hpost(client)
    assert r.status_code == 400 and r.json() == {"error": "unknown_provider"}
    for _ in range(5):
        r = hpost(client, text=SEED, provider="demo", source="he", target="en")
        assert r.status_code == 200
    assert len(hosted.LIMITER) == 0


def test_listed_when_configured(hclient):
    plist = hclient.get("/providers").json()
    assert [p["name"] for p in plist] == ["demo", "anthropic", "xai", "gemini", "openai", "hosted"]
    assert plist[-1] == {"name": "hosted", "label": "gemini (hosted)", "needs_key": False, "hosted": True,
                         "notice": providers.get("gemini").hosted_notice,
                         "models": [{"id": "m-gemini", "efforts": [], "default": True}]}
    assert all(p["hosted"] is False for p in plist[:-1])
    assert SERVER_KEY not in json.dumps(plist)


def test_only_gemini_can_be_the_hosted_provider(monkeypatch):
    # The hosted banner and the terms paragraph in web/static/index.html name Google for the
    # hosted provider, so gemini must stay the only provider that can run on the server's key.
    assert list(hosted.SERVER_KEY_ENV) == ["gemini"]
    for name in ("anthropic", "xai", "openai", "demo"):
        monkeypatch.setenv("HOSTED_PROVIDER", name)
        assert hosted.load().on is False


def test_server_key_is_used_and_never_forwarded_or_returned(hclient, who, upstream):
    r = hpost(hclient, headers={"X-Provider-Key": KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "hosted" and body["notice"] == providers.get("gemini").hosted_notice
    assert upstream["keys"] == [SERVER_KEY] * 3
    assert SERVER_KEY not in json.dumps(upstream["seen"]) and KEY not in json.dumps(upstream["seen"])
    assert SERVER_KEY not in r.text and KEY not in r.text


def test_the_fourth_attempt_is_refused_without_a_call(hclient, who, upstream):
    for _ in range(3):
        assert hpost(hclient).status_code == 200
    r = hpost(hclient)
    assert r.status_code == 429 and r.json() == {"error": "demo_limit", "attempts": 3}
    assert len(upstream["seen"]) == 9
    who["peer"] = "203.0.113.9"
    assert hpost(hclient).status_code == 200


def test_refused_text_counts_as_an_attempt(hclient, who, upstream):
    for _ in range(3):
        r = hpost(hclient, text=CHARGER_RIFLE)
        assert r.status_code == 422 and r.json()["category"] == "weapons"
    assert hpost(hclient).status_code == 429


def test_ipv6_attempts_group_by_64(hclient, who, upstream):
    for peer in ("2001:db8:1:2::1", "2001:db8:1:2:ffff::2", "2001:db8:1:2::3"):
        who["peer"] = peer
        assert hpost(hclient).status_code == 200
    who["peer"] = "2001:db8:1:2::4"
    assert hpost(hclient).status_code == 429
    who["peer"] = "2001:db8:1:3::1"
    assert hpost(hclient).status_code == 200


def test_forwarded_for_counts_only_behind_a_trusted_peer(hclient, who, upstream):
    who["peer"] = "172.30.47.3"
    xff = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(3):
        assert hpost(hclient, headers=xff).status_code == 200
    assert hpost(hclient, headers=xff).status_code == 429
    assert hpost(hclient, headers={"X-Forwarded-For": "203.0.113.8"}).status_code == 200
    who["peer"] = "198.51.100.9"
    codes = [hpost(hclient, headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code
             for i in range(20, 24)]
    assert codes == [200, 200, 200, 429]


def quota_handler(stage_user_prefix):
    """Gemini answers 429 for the call whose user text starts with the prefix ("" means render)."""
    ok = provider_handler("gemini", "clean")

    def handler(request):
        system, user = split_body("gemini", json.loads(request.content))
        gated = system == gate.SYSTEM_PROMPT
        hit = user.startswith(stage_user_prefix) if gated else stage_user_prefix == ""
        return httpx.Response(429, text="quota") if hit else ok(request)
    return handler


@pytest.mark.parametrize("where", ["stage: input", "", "stage: output"], ids=["input", "render", "output"])
def test_quota_exhausted_at_each_call(hclient, who, monkeypatch, where):
    use_handler(monkeypatch, quota_handler(where))
    r = hpost(hclient)
    assert r.status_code == 503 and r.json() == {"error": "quota_exhausted"}


def test_truncated_classifier_reply_fails_closed(hclient, who, monkeypatch):
    use_handler(monkeypatch, lambda request: httpx.Response(200, json={"candidates": [{
        "finishReason": "MAX_TOKENS", "content": {"role": "model"}}]}))
    r = hpost(hclient)
    assert r.status_code == 502 and r.json() == {"error": "gate_unavailable", "stage": "input"}


def test_normal_reply_passes_and_the_token_caps_are_sent(hclient, who, upstream):
    r = hpost(hclient)
    assert r.status_code == 200 and r.json()["text"] == "rendered"
    seen = upstream["seen"]
    assert [b["generationConfig"] for b in seen] == [
        {"maxOutputTokens": 256, "temperature": 0},
        {"maxOutputTokens": 1024},
        {"maxOutputTokens": 256, "temperature": 0},
    ]
    assert "thinkingConfig" not in json.dumps(seen)


def test_an_empty_server_key_is_not_configured_and_counts_nothing(hclient, who, upstream, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    hosted.reload()
    r = hpost(hclient)
    assert r.status_code == 503 and r.json() == {"error": "provider_not_configured"}
    assert upstream["seen"] == [] and len(hosted.LIMITER) == 0


def test_the_server_key_is_never_logged_or_returned(hosted_on, who, monkeypatch, caplog):
    debug_logs(caplog)
    ok = provider_handler("gemini", "clean")
    mode = {"m": "ok"}

    def handler(request):
        system, user = split_body("gemini", json.loads(request.content))
        if mode["m"] == "quota":
            return httpx.Response(429, text=SERVER_KEY)
        if mode["m"] == "500" and system != gate.SYSTEM_PROMPT:
            return httpx.Response(500, text=SERVER_KEY)
        return ok(request)

    use_handler(monkeypatch, handler)
    with TestClient(app) as c:
        texts = []
        for m in ("ok", "quota", "500"):
            mode["m"] = m
            r = hpost(c)
            texts.append((m, r.status_code, r.text))
        r = hpost(c)
        texts.append(("limit", r.status_code, r.text))
        texts.append(("providers", 200, c.get("/providers").text))
    assert [(m, s) for m, s, _ in texts[:4]] == [("ok", 200), ("quota", 503), ("500", 502), ("limit", 429)]
    assert all(SERVER_KEY not in t for _, _, t in texts) and SERVER_KEY not in caplog.text
    assert "hosted: provider=gemini key=set trusted_proxies=1" in caplog.text


def test_bring_your_own_key_counts_under_hosted_mode(hclient, who, upstream, monkeypatch):
    for _ in range(3):
        r = hpost(hclient, provider="gemini", headers={"X-Provider-Key": KEY})
        assert r.status_code == 200
    assert len(hosted.LIMITER) == 1
    r = hpost(hclient, provider="gemini", headers={"X-Provider-Key": KEY})
    assert r.status_code == 429 and r.json() == {"error": "demo_limit", "attempts": 3}
    assert upstream["keys"] == [KEY] * 9
    who["peer"] = "203.0.113.50"
    use_handler(monkeypatch, lambda request: httpx.Response(429, text="quota"))
    r = hpost(hclient, provider="gemini", headers={"X-Provider-Key": KEY})
    assert r.status_code == 503 and r.json() == {"error": "quota_exhausted"}


def test_the_demo_counts_under_hosted_mode(hclient, who):
    for _ in range(3):
        assert hpost(hclient, text=SEED, provider="demo", source="he", target="en").status_code == 200
    r = hpost(hclient, text=SEED, provider="demo", source="he", target="en")
    assert r.status_code == 429 and r.json() == {"error": "demo_limit", "attempts": 3}


def test_attempts_are_shared_across_providers(hclient, who, upstream):
    assert hpost(hclient).status_code == 200
    assert hpost(hclient, provider="gemini", headers={"X-Provider-Key": KEY}).status_code == 200
    assert hpost(hclient, text=SEED, provider="demo", source="he", target="en").status_code == 200
    r = hpost(hclient)
    assert r.status_code == 429 and r.json() == {"error": "demo_limit", "attempts": 3}
    assert len(upstream["seen"]) == 6


def test_request_checks_do_not_count_under_hosted_mode(hclient, who, upstream):
    short = {"X-Provider-Key": "short"}
    checks = [
        (hpost(hclient, source="xx"), 400, "unknown_language"),
        (hpost(hclient, source="en", target="en"), 400, "same_language"),
        (hpost(hclient, provider="nope"), 400, "unknown_provider"),
        (hpost(hclient, provider="anthropic", headers=short), 400, "bad_key"),
        (hpost(hclient, provider="anthropic"), 400, "key_required"),
        (hpost(hclient, text="Good morning.", provider="demo", source="en", target="he"),
         422, "demo_examples_only"),
        (hpost(hclient, text=""), 422, "bad_request"),
    ]
    for r, status, error in checks:
        assert r.status_code == status and r.json() == {"error": error}
    assert len(hosted.LIMITER) == 0 and upstream["seen"] == []
    for _ in range(3):
        assert hpost(hclient).status_code == 200
    assert hpost(hclient).status_code == 429


def test_every_provider_runs_the_gate_and_counts_in_hosted_mode(hclient, who, upstream, monkeypatch):
    term = blocked_term("en", "sexual")
    responses = [hpost(hclient, text=term)]
    assert responses[0].status_code == 422 and responses[0].json()["stage"] == "input"
    assert upstream["seen"] == []
    responses.append(hpost(hclient, text=term, provider="gemini", headers={"X-Provider-Key": KEY}))
    assert responses[1].status_code == 422 and responses[1].json()["stage"] == "input"
    monkeypatch.setattr(providers.DemoProvider, "render", lambda self, req, key: term)
    responses.append(hpost(hclient, text=SEED, provider="demo", source="he", target="en"))
    assert responses[2].status_code == 422 and responses[2].json()["stage"] == "output"
    responses.append(hpost(hclient))
    assert responses[3].status_code == 429
    assert all(term not in r.text for r in responses)


def test_concurrent_mixed_requests_admit_exactly_the_limit(hclient, who, upstream):
    def one(i):
        if i % 2:
            return hpost(hclient).status_code
        return hpost(hclient, text=SEED, provider="demo", source="he", target="en").status_code

    with ThreadPoolExecutor(8) as pool:
        statuses = list(pool.map(one, range(24)))
    assert sorted(statuses) == [200] * 3 + [429] * 21


def spost(client, route="/translate/stream", text=CHARGER_PHONE, provider="hosted", headers=None,
          source="en", target="he", **extra):
    return client.post(route, headers=headers or {}, json={
        "text": text, "source": source, "target": target, "provider": provider, **extra})


def test_hosted_model_and_effort_are_fixed(hclient, who, upstream, monkeypatch):
    set_models(monkeypatch)
    assert hclient.get("/providers").json()[-1]["models"] == [
        {"id": "gemini-3.5-flash", "efforts": ["minimal"], "default": True}]
    for route in ("/translate", "/translate/stream"):
        r = spost(hclient, route, model="gemini-3.5-flash-lite")
        assert r.status_code == 400 and r.json() == {"error": "unknown_model"}
        r = spost(hclient, route, effort="high")
        assert r.status_code == 400 and r.json() == {"error": "unknown_effort"}
    assert len(hosted.LIMITER) == 0 and upstream["seen"] == []
    r = spost(hclient, "/translate", model="gemini-3.5-flash", effort="minimal")
    assert r.status_code == 200
    assert upstream["seen"][1]["generationConfig"] == {
        "maxOutputTokens": 1024, "thinkingConfig": {"thinkingLevel": "minimal"}}
    r = spost(hclient, "/translate", provider="gemini", headers={"X-Provider-Key": KEY},
              model="gemini-3.5-flash-lite", effort="high")
    assert r.status_code == 200
    assert upstream["seen"][4]["generationConfig"] == {
        "maxOutputTokens": 8192, "thinkingConfig": {"thinkingLevel": "high"}}
    assert upstream["seen"][3]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}


def test_a_stream_request_counts_once(hclient, who, upstream):
    for _ in range(3):
        r = spost(hclient)
        lines = r.content.split(b"\n")[:-1]
        assert r.status_code == 200 and len(lines) == 4 and json.loads(lines[3])["provider"] == "hosted"
    r = spost(hclient)
    assert r.status_code == 429 and r.json() == {"error": "demo_limit", "attempts": 3}
    assert r.headers["content-type"].startswith("application/json")
    assert len(upstream["seen"]) == 9


def test_a_stream_refusal_before_the_first_stage_counts_nothing(hclient, who, upstream):
    assert spost(hclient, source="xx").status_code == 400
    assert spost(hclient, headers={"X-Provider-Key": "short"}).status_code == 400
    assert spost(hclient, provider="demo", text="The water is cold.").status_code == 422
    assert spost(hclient, provider="anthropic").status_code == 400
    assert len(hosted.LIMITER) == 0 and upstream["seen"] == []


def test_concurrent_stream_and_plain_requests_admit_exactly_the_limit(hclient, who, upstream):
    def one(i):
        if i % 3 == 0:
            return hpost(hclient).status_code
        if i % 3 == 1:
            return spost(hclient).status_code
        return spost(hclient, text=SEED, provider="demo", source="he", target="en").status_code

    with ThreadPoolExecutor(8) as pool:
        statuses = list(pool.map(one, range(24)))
    assert sorted(statuses) == [200] * 3 + [429] * 21
