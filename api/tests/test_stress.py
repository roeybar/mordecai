import itertools
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from mordecai import gate, providers, text
from mordecai import sense_solver as ss
from mordecai.main import app
from mordecai.routes import translate as tr
from mordecai.stages import translate

from .conftest import (
    BARK,
    BARK_EXPECTED,
    CHARGER_PHONE,
    CHARGER_RIFLE,
    D1,
    KEY,
    MW,
    MW_EXPECTED,
    SEED,
    SEED_EXPECTED,
    fake_classifier,
    provider_handler,
    set_models,
    split_body,
    use_handler,
)


def run(demo):
    return translate(SEED, src_lang="he", tgt_lang="en", provider=providers.get("demo"), store=demo).text


def test_concurrent_translate(demo):
    with ThreadPoolExecutor(8) as ex:
        outs = list(ex.map(lambda _: run(demo), range(200)))
    assert set(outs) == {SEED_EXPECTED}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def body(txt):
    return {"text": txt, "source": "he", "target": "en", "provider": "demo"}


def test_sequential_posts(client):
    assert all(client.post("/translate", json=body(SEED)).status_code == 200 for _ in range(200))


def test_length_boundaries(client):
    r = client.post("/translate", json=body(""))
    assert r.status_code == 422 and r.json() == {"error": "bad_request"}
    r = client.post("/translate", json=body("ש" * tr.MAX_TEXT_CHARS))
    assert r.status_code == 422 and r.json() == {"error": "demo_examples_only"}
    r = client.post("/translate", json=body("ש" * (tr.MAX_TEXT_CHARS + 1)))
    assert r.status_code == 422 and r.json() == {"error": "bad_request"}


def test_keyed_max_length_reaches_the_classifier(client, monkeypatch):
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", "clean", seen=seen))
    long = "a" * tr.MAX_TEXT_CHARS
    payload = {"text": long, "source": "en", "target": "he", "provider": "anthropic"}
    r = client.post("/translate", json=payload, headers={"X-Provider-Key": KEY})
    assert r.status_code == 200
    assert long in split_body("anthropic", seen[0])[1]


def test_concurrent_classifier_calls(monkeypatch):
    use_handler(monkeypatch, provider_handler("anthropic", fake_classifier))
    prov = providers.get("anthropic")
    sentences = [CHARGER_PHONE, CHARGER_RIFLE]

    def one(i):
        r = gate.check(sentences[i % 2], lang="en", stage="input", provider=prov, key=KEY)
        return r.rejected == (i % 2 == 1)

    with ThreadPoolExecutor(8) as ex:
        assert all(ex.map(one, range(400)))


def test_random_verdicts_fail_closed():
    rnd = random.Random(4321)
    pool = [*gate.LABELS, " ", "\n", "\t", ".", ",", '"', "`", "{", "}", ":", "שלום", "\U0001f600",
            "safe", "ok"]
    for _ in range(500):
        reply = "".join(rnd.choice(pool) for _ in range(rnd.randint(0, 4)))
        try:
            assert gate.parse_verdict(reply) in gate.LABELS
        except gate.GateUnavailable:
            pass


def test_random_strings_never_5xx(client):
    rnd = random.Random(1234)
    pool = (["ש", "ל", "ו", "ם", "ַ", "ا", "ب", "َ", "\u6c34", "\u51b7", "a", "Z", "e", "\u0301",
             "\u200f", "\U0001f600", " ", ".", '"', "\u2014"] + [chr(i) for i in range(0, 32)])
    for _ in range(300):
        s = "".join(rnd.choice(pool) for _ in range(rnd.randint(1, 60)))
        for src, tgt in (("he", "en"), ("en", "he"), ("ar", "zh")):
            r = client.post("/translate", json={"text": s, "source": src, "target": tgt})
            assert r.status_code < 500, (src, tgt, repr(s))


def synthetic(rnd):
    sems = ["a", "b", "c"]
    lat = []
    for i in range(rnd.randint(1, 7)):
        cands = []
        for j in range(rnd.randint(0, 3)):
            slots = tuple((rnd.choice(["agent", "patient"]), rnd.choice(sems), rnd.random() < 0.5)
                          for _ in range(rnd.randint(0, 2)))
            bind = {r: rnd.choice(["left", "right"]) for r, _, _ in slots}
            cands.append(ss.Reading(f"k{i}{j}", "", f"r{i}{j}", {}, sem=rnd.choice(sems), slots=slots,
                                    bind=bind, kind=rnd.choice(["entity", "event", "function"])))
        lat.append(cands)
    return lat


# For every lattice, including function-kind candidates and empty positions, solve(lat) equals the
# first optimum of itertools.product over the options (an empty position is [None]) under score().
# Transparent positions therefore take 0.
def test_solver_equals_brute_force():
    rnd = random.Random(99)
    for _ in range(200):
        lat = synthetic(rnd)
        opts = [list(range(len(c))) or [None] for c in lat]
        best, best_choice = None, None
        for choice in itertools.product(*opts):
            sc = ss.score(lat, list(choice))
            if best is None or sc > best:
                best, best_choice = sc, list(choice)
        sol = ss.solve(lat)
        assert (sol.score, sol.choice) == (best, best_choice)


def test_long_input_is_fast(demo):
    long = " ".join([SEED] * (100_000 // (len(SEED) + 1)))
    t0 = time.perf_counter()
    tokens = text.tokenize("he", long)
    sol = ss.solve(ss.lattice(demo, "he", tokens))
    assert time.perf_counter() - t0 < 5 and len(sol.choice) == len(tokens)


def test_concurrent_challenges(demo):
    cases = [(SEED, "he", "en", SEED_EXPECTED), (MW, "he", "en", MW_EXPECTED),
             (BARK, "en", "he", BARK_EXPECTED)]

    def one(i):
        txt, src, tgt, want = cases[i % 3]
        out = translate(txt, src_lang=src, tgt_lang=tgt, provider=providers.get("demo"), store=demo).text
        return out == want

    with ThreadPoolExecutor(8) as ex:
        assert all(ex.map(one, range(300)))


def test_long_english_input_is_fast(demo):
    long = " ".join([BARK] * (100_000 // (len(BARK) + 1)))
    t0 = time.perf_counter()
    tokens = text.tokenize("en", long)
    sol = ss.solve(ss.lattice(demo, "en", tokens))
    assert time.perf_counter() - t0 < 5 and len(sol.choice) == len(tokens)


def test_random_model_and_effort_never_5xx(client, monkeypatch):
    # one reply that every provider's parser accepts; every request is classified "clean"
    reply = {"content": [{"type": "text", "text": "clean"}], "choices": [{"message": {"content": "clean"}}],
             "candidates": [{"content": {"role": "model", "parts": [{"text": "clean"}]}}]}
    use_handler(monkeypatch, lambda request: httpx.Response(200, json=reply))
    set_models(monkeypatch)
    ids = [m for ms in D1.values() for m in ms]
    models = [*ids, "x", "", "a" * 64, "a" * 65, "MAX", "a/b", None, None]
    efforts = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "x", "", "a" * 16, "a" * 17,
               "MAX", "a/b", None, None]
    rnd = random.Random(2468)
    for _ in range(300):
        payload = {"text": SEED, "source": "he", "target": "en",
                   "provider": rnd.choice(["demo", "anthropic", "xai", "gemini", "openai", "nope"])}
        for field, pool in (("model", models), ("effort", efforts)):
            v = rnd.choice(pool)
            if v is not None:
                payload[field] = v
        r = client.post("/translate/stream", json=payload, headers={"X-Provider-Key": KEY})
        assert r.status_code < 500, payload
        if r.status_code == 200:
            assert all(isinstance(json.loads(x), dict) for x in r.content.split(b"\n")[:-1])


def test_concurrent_streams(client):
    def one(_):
        r = client.post("/translate/stream", json=body(SEED))
        lines = [json.loads(x) for x in r.content.split(b"\n")[:-1]]
        stages = [x["stage"] for x in lines[:3]]
        return r.status_code == 200 and stages == ["input", "translate", "output"] \
            and len(lines) == 4 and lines[3]["text"] == SEED_EXPECTED

    with ThreadPoolExecutor(8) as ex:
        assert all(ex.map(one, range(8 * 64)))
