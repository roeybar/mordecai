import json
import re
import unicodedata
from pathlib import Path

import pytest
from mordecai import langs, text

from .conftest import BARK_EXPECTED

SAMPLES = {k: v for k, v in json.loads(
    (Path(__file__).parent / "lang_samples.json").read_text(encoding="utf-8")).items() if k != "_doc"}
CODES = ["en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "id", "ur", "ru", "de", "ja", "pcm", "arz", "he"]
HE_LABEL = "\u05e0\u05d9\u05e7\u05d5\u05d3"
AR_LABEL = "\u062a\u0634\u0643\u064a\u0644"
UR_LABEL = "\u0627\u0639\u0631\u0627\u0628"
HE_RANGES = ((0x0591, 0x05BD), (0x05BF, 0x05BF), (0x05C1, 0x05C2), (0x05C4, 0x05C5), (0x05C7, 0x05C7))
ARAB_RANGES = ((0x064B, 0x0652), (0x0656, 0x0658), (0x0670, 0x0670))
# The e2e Arabic stub (demo.spec.ts): tanween, fatha, damma, kasra, shadda, sukun, superscript alef go;
# the hamza above written as its own mark (U+0654) stays.
AR_MARKED = ("\u0623\u064e\u0646\u064e\u0627 \u0645\u064f\u062f\u064e\u0631\u0650\u0651\u0633\u064c "
             "\u0645\u0650\u0646\u0652 \u0647\u0670\u0630\u064e\u0627 "
             "\u0633\u064f\u0648\u0654\u064e\u0627\u0644\u064b\u0627")
AR_BARE = ("\u0623\u0646\u0627 \u0645\u062f\u0631\u0633 \u0645\u0646 \u0647\u0630\u0627 "
           "\u0633\u0648\u0654\u0627\u0644\u0627")


def test_registry_order_and_statuses():
    assert list(langs.LANGS) == CODES
    assert {c for c, lg in langs.LANGS.items() if lg.status == langs.VERIFIED} == {"en", "he"}
    assert all(lg.status == langs.UNVERIFIED for c, lg in langs.LANGS.items() if c not in {"en", "he"})
    assert langs.get("xx") is None and not langs.known("xx") and langs.known("he")
    assert [d["code"] for d in langs.public_list()] == CODES


@pytest.mark.parametrize("code", CODES)
def test_sample_vectors(code):
    s, lg = SAMPLES[code], langs.LANGS[code]
    assert text.dominant_script(s["text"]) in lg.scripts
    assert (lg.direction == "rtl") == (code in {"he", "ar", "ur", "arz"})
    assert text.tokenize(code, s["text"]) == s["tokens"]
    for given, want in s["bare"]:
        assert text.bare(code, given) == want
    n = text.normalise(s["text"])
    assert unicodedata.is_normalized("NFC", n) and text.normalise(n) == n


def test_he_joiners():
    assert text.tokenize("he", 'צה"ל') == ['צה"ל']
    assert text.tokenize("he", '"שלום"') == ["שלום"]


def test_proclitic_splits_and_gloss():
    assert text.proclitic_splits("he", "שהייתה") == [("שה", "ייתה"), ("ש", "הייתה")]
    assert text.proclitic_splits("he", "בסירה") == [("ב", "סירה")]
    assert text.proclitic_splits("ar", "والكتاب") == [("وال", "كتاب"), ("و", "الكتاب")]
    assert text.proclitic_splits("en", "water") == []
    assert text.proclitic_gloss("he", "שה") == ["that", "the"]
    assert text.proclitic_gloss("he", "") == []


def test_unknown_language_and_misc():
    with pytest.raises(ValueError):
        text.tokenize("xx", "abc")
    assert text.bare("xx", "Abc") == "Abc"
    assert text.dominant_script("123 !!") == "Zyyy"
    assert text.script_of("\u00d7") == "Zyyy"
    assert text.normalise("a\u200bb\ufeff\x00c ") == "abc"


def _strip(ranges, s):
    return "".join(ch for ch in s if not any(lo <= ord(ch) <= hi for lo, hi in ranges))


def test_marks_registry():
    marks = {c: lg.marks for c, lg in langs.LANGS.items() if lg.marks is not None}
    assert list(marks) == ["ar", "ur", "arz", "he"]
    assert {c: m.label for c, m in marks.items()} == {
        "ar": AR_LABEL, "ur": UR_LABEL, "arz": AR_LABEL, "he": HE_LABEL}
    assert marks["he"].ranges == HE_RANGES
    assert marks["ar"].ranges == marks["arz"].ranges == marks["ur"].ranges == ARAB_RANGES
    kept = (0x0640, 0x0653, 0x0654, 0x0655, 0x05BE, 0x05C0, 0x05C3, 0x05C6)
    for code, m in marks.items():
        lg = langs.LANGS[code]
        assert lg.strip_marks and lg.direction == "rtl"
        assert unicodedata.is_normalized("NFC", m.label)
        assert all(unicodedata.category(ch) == "Lo" and text.script_of(ch) == lg.script for ch in m.label)
        prev = -1
        for lo, hi in m.ranges:
            assert prev < lo <= hi <= 0xFFFF
            prev = hi
            assert all(unicodedata.category(chr(cp)) == "Mn" and text.script_of(chr(cp)) == lg.script
                       for cp in range(lo, hi + 1))
        assert not any(lo <= cp <= hi for lo, hi in m.ranges for cp in kept)


def test_marks_strip_vectors():
    he = langs.LANGS["he"].marks.ranges
    old = re.sub("[\u0591-\u05bd\u05bf\u05c1\u05c2\u05c4\u05c5\u05c7]", "", BARK_EXPECTED)
    assert _strip(he, BARK_EXPECTED) == old != BARK_EXPECTED
    ar = langs.LANGS["ar"].marks.ranges
    assert _strip(ar, AR_MARKED) == AR_BARE
    assert text.bare("ar", AR_BARE) == text.bare("ar", AR_MARKED)


@pytest.mark.parametrize("code", ["ar", "ur", "arz", "he"])
def test_marks_strip_only_what_bare_strips(code):
    ranges = langs.LANGS[code].marks.ranges
    for given, want in SAMPLES[code]["bare"]:
        assert text.bare(code, _strip(ranges, given)) == want
