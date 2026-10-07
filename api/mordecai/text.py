"""Script detection, normalisation and tokenisation for the registered
languages. Depends only on langs and unicodedata. No dictionary, no
morphology: proclitic splitting only lists candidate splits."""
from __future__ import annotations

import unicodedata

from . import langs

_RANGES: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    ("Latn", ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F), (0x1E00, 0x1EFF))),
    ("Hebr", ((0x0590, 0x05FF), (0xFB1D, 0xFB4F))),
    ("Arab", ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("Cyrl", ((0x0400, 0x052F),)),
    ("Deva", ((0x0900, 0x097F),)),
    ("Beng", ((0x0980, 0x09FF),)),
    ("Hani", ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))),
    ("Hira", ((0x3040, 0x309F),)),
    ("Kana", ((0x30A0, 0x30FF), (0x31F0, 0x31FF))),
)


def script_of(ch: str) -> str:
    cp = ord(ch)
    if cp in (0xD7, 0xF7):
        return "Zyyy"
    for name, spans in _RANGES:
        for lo, hi in spans:
            if lo <= cp <= hi:
                return name
    return "Zyyy"


def dominant_script(s: str) -> str:
    counts: dict[str, int] = {}
    for ch in s:
        if unicodedata.category(ch).startswith("L"):
            sc = script_of(ch)
            counts[sc] = counts.get(sc, 0) + 1
    best, best_n = "Zyyy", 0
    for sc, n in counts.items():
        if n > best_n:
            best, best_n = sc, n
    return best


def normalise(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = "".join(ch for ch in s if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    return s.strip()


def bare(code: str, s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    lg = langs.get(code)
    if lg is None:
        return s
    if lg.strip_marks:
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn" and ch != "ـ")
    if lg.fold_case:
        s = s.casefold()
    return s


def _is_word(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat[0] in "LM" or cat == "Nd"


def tokenize(code: str, s: str) -> list[str]:
    lg = langs.get(code)
    if lg is None:
        raise ValueError(f"unknown language {code!r}")
    s = unicodedata.normalize("NFC", s)
    out: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            out.append("".join(cur))
            cur.clear()

    for i, ch in enumerate(s):
        if _is_word(ch):
            if lg.split_chars and script_of(ch) in ("Hani", "Hira", "Kana"):
                flush()
                out.append(ch)
            else:
                cur.append(ch)
        elif ch in lg.joiners and cur and i + 1 < len(s) and _is_word(s[i + 1]):
            cur.append(ch)
        else:
            flush()
    flush()
    return out


def proclitic_splits(code: str, bare_token: str) -> list[tuple[str, str]]:
    lg = langs.get(code)
    if lg is None or not lg.proclitics:
        return []
    out: list[tuple[str, str]] = []
    depth2 = [p1 + p2 for p1 in lg.proclitics for p2 in lg.proclitics]
    for prefix in depth2 + list(lg.proclitics):
        if bare_token.startswith(prefix) and len(bare_token) - len(prefix) >= 2:
            split = (prefix, bare_token[len(prefix):])
            if split not in out:
                out.append(split)
    return out


def proclitic_gloss(code: str, prefix: str) -> list[str]:
    lg = langs.get(code)
    if lg is None or not prefix:
        return []
    table = sorted(lg.proclitic_gloss_en, key=lambda kv: -len(kv[0]))
    out: list[str] = []
    rest = prefix
    while rest:
        for p, gloss in table:
            if rest.startswith(p):
                out.append(gloss)
                rest = rest[len(p):]
                break
        else:
            break
    return out
