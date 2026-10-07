from mordecai import providers
from mordecai.stages import s0_analyze, s1_resolve, s3_repair, s4_verify, translate

from .conftest import SEED, SEED_EXPECTED


def test_orchestrator_demo_output(demo):
    res = translate(SEED, src_lang="he", tgt_lang="en", provider=providers.get("demo"), store=demo)
    assert res.text == SEED_EXPECTED
    assert res.verdict.ok and res.resolution.score == 3
    assert res.rendered.provider == "demo"


def test_s3_repair():
    assert s3_repair.repair("a\u200bb", "en").text == "ab"
    assert s3_repair.repair("שלום עולם", "en").notes == ["script_mismatch"]
    assert s3_repair.repair("hello", "en").notes == []


def test_s4_notes_missing_gloss(demo):
    a = s0_analyze.analyze(SEED, "he", demo)
    r = s1_resolve.resolve(a)
    v = s4_verify.verify("", a, r, "en")
    assert not v.ok
    assert v.notes and v.notes[0]["issue"] == "chosen sense absent from output"
