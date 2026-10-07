"""Language registry: the single source for language codes, scripts, direction
and status. The list is the 15 most spoken languages plus Hebrew. Pinned
source: Ethnologue 29th ed. (2026), plus Hebrew.

Status: VERIFIED means this repository holds goldens for that language whose
readings the golden itself attributes to a native-speaker reviewer. Every other
language is MACHINE-MADE, UNVERIFIED.
"""
from __future__ import annotations

from dataclasses import dataclass

VERIFIED = "VERIFIED"
UNVERIFIED = "MACHINE-MADE, UNVERIFIED"


@dataclass(frozen=True)
class Marks:
    """Optional vowel or diacritic marks that the UI's toggle can hide: the name of the marks
    as a word in the language's own script, and the inclusive, ordered code-point ranges the
    toggle strips. Display only: text.bare() keeps its own rule."""
    label: str
    ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Lang:
    code: str
    name: str
    script: str
    scripts: tuple[str, ...]
    direction: str
    status: str
    fold_case: bool = False
    strip_marks: bool = False
    split_chars: bool = False
    joiners: str = ""
    proclitics: tuple[str, ...] = ()
    proclitic_gloss_en: tuple[tuple[str, str], ...] = ()
    marks: Marks | None = None


_AR_PROCLITICS = ("و", "ف", "ب", "ك", "ل", "ال")
_AR_GLOSS = (("و", "and"), ("ف", "so"), ("ب", "with"), ("ك", "like"), ("ل", "for"), ("ال", "the"))

# Hebrew points: cantillation, vowel points, dagesh, meteg, rafe, the shin and sin dots, the upper and
# lower dots and qamats qatan. Maqaf, paseq, sof pasuq and nun hafukha are punctuation and stay.
_HE_MARKS = Marks("\u05e0\u05d9\u05e7\u05d5\u05d3", (
    (0x0591, 0x05BD), (0x05BF, 0x05BF), (0x05C1, 0x05C2), (0x05C4, 0x05C5), (0x05C7, 0x05C7)))
# Arabic-script harakat: tanween, fatha, damma, kasra, shadda and sukun (U+064B-U+0652), subscript alef,
# inverted damma and the noon ghunna mark (U+0656-U+0658), superscript alef (U+0670). Madda and hamza
# above and below (U+0653-U+0655) stay: they belong to a letter. Tatweel (U+0640) is not a mark.
_ARAB_MARK_RANGES = ((0x064B, 0x0652), (0x0656, 0x0658), (0x0670, 0x0670))
_AR_MARKS = Marks("\u062a\u0634\u0643\u064a\u0644", _ARAB_MARK_RANGES)
_UR_MARKS = Marks("\u0627\u0639\u0631\u0627\u0628", _ARAB_MARK_RANGES)


def _l(code, name, script, status=UNVERIFIED, direction="ltr", scripts=None, **kw) -> Lang:
    return Lang(code, name, script, scripts or (script,), direction, status, **kw)


LANGS: dict[str, Lang] = {
    lg.code: lg
    for lg in (
        _l("en", "English", "Latn", VERIFIED, fold_case=True),
        _l("zh", "Mandarin Chinese", "Hani", split_chars=True),
        _l("hi", "Hindi", "Deva"),
        _l("es", "Spanish", "Latn", fold_case=True),
        _l("ar", "Standard Arabic", "Arab", direction="rtl", strip_marks=True, marks=_AR_MARKS,
           proclitics=_AR_PROCLITICS, proclitic_gloss_en=_AR_GLOSS),
        _l("fr", "French", "Latn", fold_case=True),
        _l("bn", "Bengali", "Beng"),
        _l("pt", "Portuguese", "Latn", fold_case=True),
        _l("id", "Indonesian", "Latn", fold_case=True),
        _l("ur", "Urdu", "Arab", direction="rtl", strip_marks=True, marks=_UR_MARKS),
        _l("ru", "Russian", "Cyrl", fold_case=True),
        _l("de", "Standard German", "Latn", fold_case=True),
        _l("ja", "Japanese", "Jpan", scripts=("Hani", "Hira", "Kana"), split_chars=True),
        _l("pcm", "Nigerian Pidgin", "Latn", fold_case=True),
        _l("arz", "Egyptian Arabic", "Arab", direction="rtl", strip_marks=True, marks=_AR_MARKS,
           proclitics=_AR_PROCLITICS, proclitic_gloss_en=_AR_GLOSS),
        _l("he", "Hebrew", "Hebr", VERIFIED, "rtl", strip_marks=True, marks=_HE_MARKS,
           joiners="\u05f3\u05f4\"'",
           proclitics=("ו", "ה", "ב", "כ", "ל", "מ", "ש"),
           proclitic_gloss_en=(("ו", "and"), ("ה", "the"), ("ב", "in"), ("כ", "as"),
                               ("ל", "to"), ("מ", "from"), ("ש", "that"))),
    )
}


def get(code: str) -> Lang | None:
    return LANGS.get(code)


def known(code: str) -> bool:
    return code in LANGS


def _marks(m: Marks | None) -> dict | None:
    return None if m is None else {"label": m.label, "ranges": [list(r) for r in m.ranges]}


def public_list() -> list[dict]:
    return [
        {"code": lg.code, "name": lg.name, "script": lg.script,
         "direction": lg.direction, "status": lg.status, "marks": _marks(lg.marks)}
        for lg in LANGS.values()
    ]
