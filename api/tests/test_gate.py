import logging

import httpx
import pytest
from mordecai import gate, providers
from mordecai.providers import ProviderNotConfigured

from .conftest import (
    CHARGER_PHONE,
    CHARGER_RIFLE,
    KEY,
    blocked_term,
    fake_classifier,
    provider_handler,
    use_handler,
)

EM = chr(0x2014)
# Hebrew fixed words of "The article describes the word": the listed term is read from the list at run time
HE_FRAME = (
    "\u05d4\u05de\u05d0\u05de\u05e8 "
    "\u05de\u05ea\u05d0\u05e8 \u05d0\u05ea \u05d4\u05de\u05d9\u05dc\u05d4"
)
# listed terms in innocent senses: the floor refuses them by design (language, text, category);
# each sentence is composed around a term read from the list at run time, never typed here
LISTED_INNOCENT = [
    ("en", f"The patient was examined and the notes record {blocked_term('en', 'sexual')}.", "sexual"),
    ("en", f"A court heard evidence of {blocked_term('en', 'child_safety')} at the school.", "child_safety"),
    ("he", f"{HE_FRAME} {blocked_term('he', 'sexual')}", "sexual"),
]
# no listed term: the floor passes it and the classifier judges it
OFF_THE_FLOOR = "The documentary covers sex education in schools."
ANTH = providers.get("anthropic")
DEMO = providers.get("demo")


def check(text, provider=ANTH, lang="en", stage="input", policy="strict"):
    return gate.check(text, lang=lang, stage=stage, provider=provider, key=KEY, policy=policy)


def test_lists_hold_only_the_floor():
    assert {c for _, c in gate._LISTS} == {"child_safety", "sexual"}
    assert {lg for lg, _ in gate._LISTS} == {"en", "he"}


@pytest.mark.parametrize("lang", ["en", "he"])
@pytest.mark.parametrize("category", ["child_safety", "sexual"])
def test_floor_rejects_each_category(lang, category):
    r = gate.floor(blocked_term(lang, category), lang)
    assert r.rejected and r.category == category


def test_floor_english_list_applies_to_other_languages():
    assert gate.floor(blocked_term("en", "sexual"), "hi").rejected


def test_floor_hebrew_prefix_and_dash_join():
    t = blocked_term("he", "sexual")
    assert gate.floor("ו" + t, "he").rejected
    # a blocked term joined to a word by an em-dash must still be split out
    assert gate.floor(t + EM + "שלום", "he").rejected
    assert gate.floor("שלום" + EM + t, "he").rejected


def test_floor_passes_ordinary_text():
    assert not gate.floor(CHARGER_PHONE, "en").rejected
    assert not gate.floor(CHARGER_RIFLE, "en").rejected
    assert not gate.floor("המים קרים", "he").rejected
    assert not gate.floor("", "en").rejected


@pytest.mark.parametrize(
    "lang,text,category", LISTED_INNOCENT, ids=["en-sexual", "en-child_safety", "he-sexual"]
)
def test_floor_refuses_listed_terms_even_in_innocent_senses(monkeypatch, lang, text, category):
    r = gate.floor(text, lang)
    assert r.rejected and r.category == category
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", "clean", seen=seen))
    r = check(text, lang=lang)
    assert r.rejected and r.category == category and seen == []


def test_text_off_the_floor_reaches_the_classifier(monkeypatch):
    assert not gate.floor(OFF_THE_FLOOR, "en").rejected
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", "clean", seen=seen))
    assert not check(OFF_THE_FLOOR).rejected
    assert len(seen) == 1


def test_floor_runs_before_the_classifier(monkeypatch):
    seen = []
    use_handler(monkeypatch, provider_handler("anthropic", "clean", seen=seen))
    r = check(blocked_term("en", "sexual"))
    assert r.rejected and r.category == "sexual" and seen == []


def test_demo_provider_never_calls_the_classifier(monkeypatch):
    monkeypatch.setattr(providers, "_client", lambda: pytest.fail("the classifier was called"))
    assert not check(CHARGER_RIFLE, provider=DEMO).rejected


@pytest.mark.parametrize("name", ["anthropic", "xai"])
def test_charger_both_ways(monkeypatch, name):
    use_handler(monkeypatch, provider_handler(name, fake_classifier))
    prov = providers.get(name)
    assert not check(CHARGER_PHONE, provider=prov).rejected
    r = check(CHARGER_RIFLE, provider=prov)
    assert r.rejected and r.category == "weapons"


@pytest.mark.parametrize("reply,label", [
    ("clean", "clean"), (" Weapons\n", "weapons"), ("`hate`", "hate"), ('"fraud"', "fraud"),
    ("profanity.", "profanity"), ("CHILD_SAFETY", "child_safety"),
])
def test_parse_verdict_accepts(reply, label):
    assert gate.parse_verdict(reply) == label


@pytest.mark.parametrize("reply", [
    "", "safe", "clean, mostly", "weapons hate", '{"category": "clean"}', "clean\nweapons", "x" * 5000,
])
def test_parse_verdict_refuses(reply):
    with pytest.raises(gate.GateUnavailable):
        gate.parse_verdict(reply)


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(500, text=KEY),
    lambda r: httpx.Response(200, json={"content": []}),
    provider_handler("anthropic", "maybe"),
], ids=["status-500", "no-content", "prose"])
def test_fail_closed(monkeypatch, handler):
    use_handler(monkeypatch, handler)
    with pytest.raises(gate.GateUnavailable):
        check(CHARGER_PHONE)


def test_provider_not_configured_passes_through(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(ProviderNotConfigured):
        check(CHARGER_PHONE)


def test_build_user():
    assert gate.build_user("I", "he", "output") == "stage: output\nlanguage: Hebrew (he)\ntext:\n<<<\nI\n>>>"
    with pytest.raises(ValueError):
        gate.build_user("I", "he", "middle")


@pytest.mark.parametrize("value,want", [
    (None, "strict"), ("relaxed", "relaxed"), (" OFF ", "off"), ("lenient", "strict"), ("", "strict"),
])
def test_policy(monkeypatch, value, want):
    if value is None:
        monkeypatch.delenv("GATE_POLICY", raising=False)
    else:
        monkeypatch.setenv("GATE_POLICY", value)
    assert gate.policy() == want


def test_policy_mapping_table():
    def enforced(p):
        return {c for c in gate.CATEGORIES if gate._category_enforced(c, p)}

    assert enforced("strict") == set(gate.CATEGORIES) and len(enforced("strict")) == 9
    assert enforced("relaxed") == {"child_safety", "sexual", "weapons", "illegal", "fraud", "self_harm"}
    assert enforced("off") == {"child_safety", "sexual"}


def test_prompt_lists_every_label_in_precedence_order():
    p = gate.SYSTEM_PROMPT
    assert p.isascii() and p.endswith("and nothing else.")
    for label in (*gate.CATEGORIES, gate.CLEAN):
        assert p.count(f"\n{label} - ") == 1
    at = [p.index(f"\n{c} - ") for c in gate.CATEGORIES]
    assert at == sorted(at)
    assert gate.CATEGORIES[:2] == ("child_safety", "sexual")


def test_logs_carry_stage_and_category_only(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    use_handler(monkeypatch, provider_handler("anthropic", fake_classifier))
    gate.log_rejection("input", check(CHARGER_RIFLE))
    gate.log_rejection("output", check(CHARGER_RIFLE, stage="output"))
    assert "stage=input category=weapons" in caplog.text and "stage=output" in caplog.text
    assert KEY not in caplog.text and CHARGER_RIFLE not in caplog.text
