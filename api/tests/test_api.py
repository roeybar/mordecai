import json
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from mordecai import gate, providers
from mordecai.main import app
from mordecai.routes import translate as tr
from mordecai.stages import orchestrator

from .conftest import (
    BARK,
    BARK_EXPECTED,
    CHARGER_PHONE,
    CHARGER_RIFLE,
    D1,
    MW,
    MW_EXPECTED,
    SEED,
    SEED_EXPECTED,
    blocked_term,
    fake_classifier,
    provider_handler,
    set_models,
    split_body,
    use_handler,
)

KEY = "test-key-" + "Z9y8X7w6" * 3
GOLD = json.loads((Path(__file__).parent / "goldens" / "homograph_he.json").read_text(encoding="utf-8"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def post(client, body=None, headers=None, **over):
    data = {"text": SEED, "source": "he", "target": "en", "provider": "demo"}
    data.update(body or {})
    data.update(over)
    return client.post("/translate", json=data, headers=headers or {})


def test_health_and_lists(client):
    assert client.get("/health").json() == {"ok": True, "service": "mordecai", "contact": ""}
    langs = client.get("/languages").json()
    assert len(langs) == 16 and all(x["status"] and x["name"] for x in langs)
    assert [p["name"] for p in client.get("/providers").json()] == [
        "demo", "anthropic", "xai", "gemini", "openai"]
    ex = client.get("/example").json()
    assert [e["id"] for e in ex] == ["hair-eyebrow-storm-boat", "mw-attention", "llm-bark"]
    assert ex[0] == {"id": "hair-eyebrow-storm-boat", "text": GOLD["items"][0]["he"],
                     "source": "he", "target": "en"}
    assert ex[2] == {"id": "llm-bark", "text": BARK, "source": "en", "target": "he"}


def test_languages_carry_marks(client):
    r = client.get("/languages")
    body = r.json()
    assert all(list(x) == ["code", "name", "script", "direction", "status", "marks"] for x in body)
    marks = {x["code"]: x["marks"] for x in body}
    assert [c for c, m in marks.items() if m is not None] == ["ar", "ur", "arz", "he"]
    arab = [[0x064B, 0x0652], [0x0656, 0x0658], [0x0670, 0x0670]]
    assert marks["he"] == {"label": "\u05e0\u05d9\u05e7\u05d5\u05d3", "ranges": [
        [0x0591, 0x05BD], [0x05BF, 0x05BF], [0x05C1, 0x05C2], [0x05C4, 0x05C5], [0x05C7, 0x05C7]]}
    assert marks["ar"] == marks["arz"] == {"label": "\u062a\u0634\u0643\u064a\u0644", "ranges": arab}
    assert marks["ur"] == {"label": "\u0627\u0639\u0631\u0627\u0628", "ranges": arab}
    rest = r.text
    for m in marks.values():
        if m:
            rest = rest.replace(m["label"], "")
    assert rest.isascii()


def test_demo_translate(client):
    r = post(client)
    assert r.status_code == 200
    body = r.json()
    assert list(body)[:4] == ["text", "provider", "notice", "source"]
    assert body["text"] == SEED_EXPECTED and body["solver"]["score"] == 3
    assert body["verify"]["ok"] and body["source_status"] == "VERIFIED"
    assert body["greedy"][6]["reading"] == "שַׂעֲרָה" and body["readings"][6]["reading"] == "סְעָרָה"
    assert "Demo provider" in body["notice"]
    assert body["readings"][6]["choice"] >= 1


def test_readings_carry_the_choice(client):
    for e in client.get("/example").json():
        body = post(client, text=e["text"], source=e["source"], target=e["target"]).json()
        assert body["readings"]
        for r in body["readings"]:
            assert isinstance(r["choice"], int)
            assert r["candidates"][r["choice"]] == {"reading": r["reading"], "gloss": r["gloss"]}


@pytest.mark.parametrize("over,headers,status,error", [
    ({"source": "xx"}, None, 400, "unknown_language"),
    ({"target": "he"}, None, 400, "same_language"),
    ({"provider": "nope"}, None, 400, "unknown_provider"),
    ({"provider": "anthropic"}, None, 400, "key_required"),
    ({"provider": "anthropic"}, {"X-Provider-Key": "short"}, 400, "bad_key"),
])
def test_error_bodies(client, over, headers, status, error):
    r = post(client, over, headers)
    assert r.status_code == status and r.json() == {"error": error}


def test_validation_does_not_echo_or_log(client, caplog):
    caplog.set_level(logging.DEBUG)
    long = "q" * (tr.MAX_TEXT_CHARS + 1)
    r = post(client, text=long)
    assert r.status_code == 422 and r.json() == {"error": "bad_request"}
    assert "qqqqqqqq" not in r.text and "qqqqqqqq" not in caplog.text
    r = client.post("/translate", json={"text": "x", "source": "he", "target": "en", "extra": "SECRETVAL"})
    assert r.status_code == 422 and "SECRETVAL" not in r.text and "SECRETVAL" not in caplog.text


def debug_logs(caplog):
    for lg in ("", "httpx", "httpcore"):
        caplog.set_level(logging.DEBUG, logger=lg)


def keyed(client, text, provider="anthropic", source="en", target="he"):
    return post(client, text=text, source=source, target=target, provider=provider,
                headers={"X-Provider-Key": KEY})


def test_floor_blocks_before_any_call(client, monkeypatch):
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", "clean", seen=seen))
    term = blocked_term("en", "sexual")
    r = keyed(client, term)
    assert r.status_code == 422
    assert r.json() == {"error": "blocked_content", "category": "sexual", "stage": "input"}
    assert term not in r.text and seen == []


def test_output_floor_blocks_on_demo(client, monkeypatch):
    term = blocked_term("en", "sexual")
    monkeypatch.setattr(providers.DemoProvider, "render", lambda self, req, key: term)
    r = post(client)
    assert r.status_code == 422 and r.json()["stage"] == "output" and term not in r.text


def test_byok_key_not_in_body_or_logs(client, monkeypatch, caplog):
    debug_logs(caplog)
    use_handler(monkeypatch, provider_handler("anthropic", "clean", render=SEED_EXPECTED))
    r = post(client, provider="anthropic", headers={"X-Provider-Key": KEY})
    assert r.status_code == 200 and r.json()["text"] == SEED_EXPECTED
    assert KEY not in r.text and KEY not in caplog.text
    ok = provider_handler("anthropic", "clean")

    def handler(request):
        system, _ = split_body("anthropic", json.loads(request.content))
        return ok(request) if system == gate.SYSTEM_PROMPT else httpx.Response(500, text=KEY)

    use_handler(monkeypatch, handler)
    r = post(client, provider="anthropic", headers={"X-Provider-Key": KEY})
    assert r.status_code == 502 and r.json() == {"error": "upstream_failed"}
    assert KEY not in r.text and KEY not in caplog.text


def test_demo_accepts_only_examples(client, monkeypatch):
    calls = []
    monkeypatch.setattr(providers, "_client", lambda: calls.append(1))
    for e in client.get("/example").json():
        assert post(client, text=e["text"], source=e["source"], target=e["target"]).status_code == 200
    assert post(client, text="  " + SEED + "\n").status_code == 200
    for over in ({"text": "The water is cold.", "source": "en", "target": "he"}, {"target": "ar"}):
        r = post(client, **over)
        assert r.status_code == 422 and r.json() == {"error": "demo_examples_only"}
    assert calls == []


@pytest.mark.parametrize("name", ["anthropic", "xai", "gemini", "openai"])
def test_charger_phone_is_clean(client, monkeypatch, caplog, name):
    debug_logs(caplog)
    seen = []
    use_handler(monkeypatch, provider_handler(name, fake_classifier, seen=seen))
    r = keyed(client, CHARGER_PHONE, provider=name)
    assert r.status_code == 200 and r.json()["text"] == "rendered"
    assert len(seen) == 3
    users = [split_body(name, b)[1] for b in seen]
    assert "stage: input\nlanguage: English (en)\n" in users[0] and CHARGER_PHONE in users[0]
    assert "stage: output\nlanguage: Hebrew (he)\n" in users[2] and "rendered" in users[2]
    assert KEY not in r.text and KEY not in json.dumps(seen) and KEY not in caplog.text


@pytest.mark.parametrize("name", ["anthropic", "xai", "gemini", "openai"])
def test_charger_rifle_is_blocked(client, monkeypatch, caplog, name):
    debug_logs(caplog)
    seen = []
    use_handler(monkeypatch, provider_handler(name, fake_classifier, seen=seen))
    r = keyed(client, CHARGER_RIFLE, provider=name)
    assert r.status_code == 422
    assert r.json() == {"error": "blocked_content", "category": "weapons", "stage": "input"}
    assert len(seen) == 1 and "rifle" not in r.text
    assert KEY not in r.text and KEY not in caplog.text


def test_openai_quota_is_503(client, monkeypatch):
    use_handler(monkeypatch, lambda request: httpx.Response(429, text="quota"))
    r = keyed(client, CHARGER_PHONE, provider="openai")
    assert r.status_code == 503 and r.json() == {"error": "quota_exhausted"}


def test_classifier_request_shape(client, monkeypatch):
    seen, keys = [], []
    inner = provider_handler("anthropic", fake_classifier, seen=seen)

    def handler(request):
        keys.append(request.headers["x-api-key"])
        return inner(request)

    use_handler(monkeypatch, handler)
    assert keyed(client, CHARGER_PHONE).status_code == 200
    assert len(seen) == 3 and keys == [KEY] * 3
    for body in (seen[0], seen[2]):
        assert body["model"] == "m-anthropic" and body["max_tokens"] == gate.GATE_MAX_TOKENS
        assert "temperature" not in body
        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["system"][0]["text"] == gate.SYSTEM_PROMPT


@pytest.mark.parametrize("policy,status", [("strict", 422), ("relaxed", 200), ("off", 200)])
def test_output_stage_is_classified(client, monkeypatch, policy, status):
    monkeypatch.setenv("GATE_POLICY", policy)
    use_handler(monkeypatch, provider_handler(
        "anthropic", lambda user: "violence" if user.startswith("stage: output") else "clean"))
    r = keyed(client, CHARGER_PHONE)
    assert r.status_code == status
    if status == 422:
        assert r.json() == {"error": "blocked_content", "category": "violence", "stage": "output"}


@pytest.mark.parametrize("policy,verdict,status", [
    ("strict", "profanity", 422), ("relaxed", "profanity", 200), ("relaxed", "weapons", 422),
    ("off", "weapons", 200), ("off", "sexual", 422), ("off", "child_safety", 422),
    ("lenient", "profanity", 422),
])
def test_gate_policy_mapping(client, monkeypatch, policy, verdict, status):
    monkeypatch.setenv("GATE_POLICY", policy)
    use_handler(monkeypatch, provider_handler("anthropic", verdict))
    r = keyed(client, CHARGER_PHONE)
    assert r.status_code == status
    if status == 422:
        assert r.json() == {"error": "blocked_content", "category": verdict, "stage": "input"}


@pytest.mark.parametrize("kind", ["status-500", "prose", "not-json", "transport"])
def test_fail_closed_on_input(client, monkeypatch, caplog, kind):
    debug_logs(caplog)

    def transport_error(request):
        raise httpx.ConnectError("down")

    handler = {
        "status-500": lambda request: httpx.Response(500, text=KEY),
        "prose": provider_handler("anthropic", "I think it is fine"),
        "not-json": lambda request: httpx.Response(200, text="not json"),
        "transport": transport_error,
    }[kind]
    use_handler(monkeypatch, handler)
    r = keyed(client, "I think it is fine")
    assert r.status_code == 502
    assert r.json() == {"error": "gate_unavailable", "stage": "input"}
    assert KEY not in r.text and KEY not in caplog.text


def test_fail_closed_on_output(client, monkeypatch):
    use_handler(monkeypatch, provider_handler(
        "anthropic", lambda user: "unsure" if user.startswith("stage: output") else "clean"))
    r = keyed(client, CHARGER_PHONE)
    assert r.status_code == 502 and r.json() == {"error": "gate_unavailable", "stage": "output"}


def test_provider_not_configured(client, monkeypatch):
    monkeypatch.delenv("XAI_MODEL", raising=False)
    r = post(client, provider="xai", headers={"X-Provider-Key": KEY})
    assert r.status_code == 503 and r.json() == {"error": "provider_not_configured"}


def test_mw_challenge(client):
    r = post(client, text=MW)
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == MW_EXPECTED and body["solver"]["score"] == 1
    assert body["greedy"][1]["gloss"] == "there"


def test_bark_challenge(client):
    r = post(client, text=BARK, source="en", target="he")
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == BARK_EXPECTED and body["target_status"] == "VERIFIED"
    assert len(body["readings"]) == 7
    assert body["readings"][1]["gloss"] == "\u05e7\u05b0\u05dc\u05b4\u05d9\u05e4\u05b8\u05bc\u05d4"


def test_health_contact(client, monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", " someone@example.com ")
    assert client.get("/health").json()["contact"] == "someone@example.com"
    monkeypatch.setenv("CONTACT_EMAIL", "not an address")
    assert client.get("/health").json()["contact"] == ""


def test_providers_carry_models(client, monkeypatch):
    set_models(monkeypatch)
    rows = {p["name"]: p["models"] for p in client.get("/providers").json()}
    assert rows["demo"] == []
    levels = ["low", "medium", "high", "xhigh", "max"]
    gem = ["minimal", "low", "medium", "high"]
    want = {
        "anthropic": [{"id": m, "efforts": levels, "default": i == 0} for i, m in enumerate(D1["ANTHROPIC"])],
        "xai": [{"id": m, "efforts": [], "default": i == 0} for i, m in enumerate(D1["XAI"])],
        "gemini": [{"id": m, "efforts": gem, "default": i == 0} for i, m in enumerate(D1["GEMINI"])],
        "openai": [{"id": "gpt-6-luna", "efforts": ["none", *levels], "default": True},
                   {"id": "gpt-6.1-sol", "efforts": levels, "default": False}],
    }
    assert {k: rows[k] for k in want} == want


def route_post(client, route, headers=None, **fields):
    data = {"text": SEED, "source": "he", "target": "en", "provider": "demo"}
    data.update(fields)
    return client.post(route, json=data, headers=headers or {})


ROUTES = ["/translate", "/translate/stream"]
KEYED = {"X-Provider-Key": KEY}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("fields,keyed_call,status,error", [
    ({"provider": "anthropic", "model": "claude-opus-4-1"}, True, 400, "unknown_model"),
    ({"provider": "anthropic", "effort": "minimal"}, True, 400, "unknown_effort"),
    ({"provider": "openai", "model": "gpt-6.1-sol", "effort": "none"}, True, 400, "unknown_effort"),
    ({"provider": "xai", "effort": "low"}, True, 400, "unknown_effort"),
    ({"provider": "demo", "model": "gpt-6-luna"}, False, 400, "unknown_model"),
    ({"provider": "demo", "effort": "low"}, False, 400, "unknown_effort"),
    ({"provider": "anthropic", "model": "a/b"}, True, 422, "bad_request"),
])
def test_model_and_effort_refusals(client, monkeypatch, route, fields, keyed_call, status, error):
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", "clean", seen=seen))
    set_models(monkeypatch)
    r = route_post(client, route, KEYED if keyed_call else None, **fields)
    assert r.status_code == status and r.json() == {"error": error}
    assert r.headers["content-type"].startswith("application/json")
    assert seen == []


@pytest.mark.parametrize("route", ROUTES)
def test_picked_model_and_effort_reach_only_the_translation(client, monkeypatch, route):
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", fake_classifier, seen=seen))
    set_models(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_GATE_MODEL", "claude-haiku-5-5")
    r = route_post(client, route, KEYED, text=CHARGER_PHONE, source="en", target="he", provider="anthropic",
                   model="claude-opus-5-5", effort="high")
    assert r.status_code == 200
    assert len(seen) == 3
    for body in (seen[0], seen[2]):
        assert body["model"] == "claude-haiku-5-5" and body["output_config"] == {"effort": "low"}
        assert body["thinking"] == {"type": "disabled"} and body["max_tokens"] == gate.GATE_MAX_TOKENS
        assert "temperature" not in body and body["system"][0]["text"] == gate.SYSTEM_PROMPT
    body = seen[1]
    assert body["model"] == "claude-opus-5-5" and body["output_config"] == {"effort": "high"}
    assert "thinking" not in body and "temperature" not in body and body["max_tokens"] == 8192


STAGE_LINES = [b'{"stage":"input"}', b'{"stage":"translate"}', b'{"stage":"output"}']


@pytest.mark.parametrize("example", range(3))
def test_stream_demo_frames_and_final_body(client, example):
    e = client.get("/example").json()[example]
    fields = {"text": e["text"], "source": e["source"], "target": e["target"]}
    r = route_post(client, "/translate/stream", **fields)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert r.headers["x-accel-buffering"] == "no"
    assert r.content.endswith(b"\n")
    lines = r.content.split(b"\n")[:-1]
    assert lines[:3] == STAGE_LINES and len(lines) == 4
    assert lines[3] == route_post(client, "/translate", **fields).content


def stream_lines(r):
    return [json.loads(x) for x in r.content.split(b"\n")[:-1]]


def _reply_for(kind):
    clean = provider_handler("anthropic", "clean")

    def upstream_500(request):
        if split_body("anthropic", json.loads(request.content))[0] == gate.SYSTEM_PROMPT:
            return clean(request)
        return httpx.Response(500, text="boom")

    return {
        "input-blocked": provider_handler("anthropic", "weapons"),
        "output-blocked": provider_handler(
            "anthropic", lambda user: "violence" if user.startswith("stage: output") else "clean"),
        "upstream-500": upstream_500,
        "prose-verdict": provider_handler("anthropic", "I think it is fine"),
    }[kind]


@pytest.mark.parametrize("kind,frames_before", [("input-blocked", 1), ("output-blocked", 3),
                                                ("upstream-500", 2), ("prose-verdict", 1)])
def test_stream_refusals_match_translate(client, monkeypatch, kind, frames_before):
    use_handler(monkeypatch, _reply_for(kind))
    fields = {"text": CHARGER_PHONE, "source": "en", "target": "he", "provider": "anthropic"}
    plain = route_post(client, "/translate", KEYED, **fields)
    r = route_post(client, "/translate/stream", KEYED, **fields)
    lines = stream_lines(r)
    assert r.status_code == 200 and len(lines) == frames_before + 1
    assert lines[:frames_before] == [{"stage": s} for s in ("input", "translate", "output")][:frames_before]
    final = lines[-1]
    assert list(final)[:2] == ["error", "status"]
    assert final["status"] == plain.status_code != 200
    assert {k: v for k, v in final.items() if k != "status"} == plain.json()


def test_stream_refusal_before_the_first_stage_is_plain(client):
    r = route_post(client, "/translate/stream", source="xx")
    assert r.status_code == 400 and r.json() == {"error": "unknown_language"}
    assert r.headers["content-type"].startswith("application/json")
    r = route_post(client, "/translate/stream", text="The water is cold.", source="en", target="he")
    assert r.status_code == 422 and r.json() == {"error": "demo_examples_only"}
    assert r.headers["content-type"].startswith("application/json")


def test_stage_frames_sit_at_the_pipeline_boundaries(monkeypatch):
    events = []
    fake = type("Fake", (), {})

    def step(name, ret):
        def run(*a, **k):
            events.append(name)
            return ret
        return run

    def gate_check(text, *, lang, stage, provider, key, policy):
        events.append(f"gate:{stage}")
        return gate.GateResult(rejected=False)

    rendered = fake()
    rendered.text = "t"
    repaired = fake()
    repaired.text = "t"
    monkeypatch.setattr(orchestrator.s0_analyze, "analyze", step("S0", "A"))
    monkeypatch.setattr(orchestrator.s1_resolve, "resolve", step("S1", "R"))
    monkeypatch.setattr(orchestrator.s2_render, "render", step("S2", rendered))
    monkeypatch.setattr(orchestrator.s3_repair, "repair", step("S3", repaired))
    monkeypatch.setattr(orchestrator.s4_verify, "verify", step("S4", "V"))
    monkeypatch.setattr(gate, "check", gate_check)
    monkeypatch.setattr(tr, "_result", lambda body, out: {"ok": True})
    body = tr.TranslateIn(text="x", source="en", target="he", provider="anthropic")
    prov = providers.Bound(providers.get("anthropic"), None, None)
    for item in tr._stages(body, prov, KEY):
        events.append(item if isinstance(item, str) else item[0])
    assert events == ["input", "gate:input", "translate", "S0", "S1", "S2", "S3", "output", "S4",
                      "gate:output", 200]
