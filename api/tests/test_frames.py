import json
import re
import unicodedata
from pathlib import Path

import pytest
from mordecai import frames
from mordecai.frames import FrameError, FrameStore, canonicalize

GOLD = json.loads((Path(__file__).parent / "goldens" / "homograph_he.json").read_text(encoding="utf-8"))


def fr(lemma="cat", **over):
    base = {"kind": "entity", "head": {"lemma": lemma, "pos": "noun"}}
    base.update(over)
    return base


def key(frame):
    return canonicalize(frame).key


def test_key_stable_under_attr_and_part_order():
    a = fr(attrs={"demo_set": "x", "register": "y"})
    b = fr(attrs={"register": "y", "demo_set": "x"})
    assert key(a) == key(b)
    c1, c2 = fr("one"), fr("two")
    p1 = fr("pair", parts=[{"rel": "has_part", "frame": c1}, {"rel": "has_part", "frame": c2}])
    p2 = fr("pair", parts=[{"rel": "has_part", "frame": c2}, {"rel": "has_part", "frame": c1}])
    assert key(p1) == key(p2)


def test_surfaces_and_feats_not_in_identity():
    base = key(fr())
    assert key(fr(surface={"en": "cat"}, feats={"rank": 3}, status="reviewed")) == base


def test_slots_identity():
    base = key(fr())
    optional = fr(slots=[{"role": "agent", "type": "x", "required": False}])
    required = fr(slots=[{"role": "agent", "type": "x", "required": True}])
    assert key(optional) == base
    assert key(required) != base


def test_attr_classes():
    base = key(fr())
    assert key(fr(attrs={"register": "formal"})) == base
    assert key(fr(attrs={"demo_set": "demo"})) != base


@pytest.mark.parametrize("bad", [
    {"kind": "nope", "head": {"lemma": "x"}},
    {"kind": "entity", "head": {"lemma": "x"}, "parts": [{"rel": "nope", "child": "k"}]},
    {"kind": "entity", "head": {"lemma": "x"}, "attrs": {"nope": "1"}},
    {"kind": "entity", "head": {"lemma": "x"}, "slots": [{"role": "nope"}]},
    {"kind": "entity", "head": {"lemma": "x"}, "parts": [{"rel": "has_part", "card": "nope", "child": "k"}]},
    {"kind": "entity", "head": {}},
    {"kind": "entity"},
])
def test_vocabulary_rejects(bad):
    with pytest.raises(FrameError):
        canonicalize(bad)


def test_put_children_by_reference_and_merge(tmp_path):
    st = FrameStore(tmp_path)
    child = fr("wheel")
    k = st.put(fr("car", parts=[{"rel": "has_part", "frame": child}]))
    doc = st.get(k)
    assert doc["parts"][0]["child"] == key(child)
    assert st.get(key(child)) is not None
    st.put(fr("cat", surface={"en": {"text": "cat", "status": "auto"}}))
    st.put(fr("cat", surface={"en": {"text": "cat", "status": "verified"}}))
    assert st.get(key(fr("cat")))["surface"]["en"]["status"] == "verified"


def test_bare_derivation():
    def bare(lang, txt):
        return canonicalize(fr(surface={lang: txt})).doc["surface"][lang]["bare"]

    assert bare("he", "שַׂעֲרָה") == "שערה"
    assert bare("ar", "الْمَاءُ") == "الماء"
    assert bare("en", "Water") == "water"


def test_alt_spellings_and_rebuild(demo, tmp_path):
    storm = [frames.canonicalize(f).key for f in frames.demo_frames() if f["head"]["lemma"] == "storm"][0]
    hits = demo.lookup_by_surface("he", "שערה")
    assert storm in hits and len(hits) == 2
    again = FrameStore(demo.root)
    assert again.count() == demo.count() == 23
    assert again.lookup_by_surface("he", "שערה") == hits


def test_inbox_rejects_bad_doc(tmp_path):
    st = FrameStore(tmp_path)
    (st.inbox / "bad.json").write_text('{"kind": "nope"}', encoding="utf-8")
    (st.inbox / "good.json").write_text(json.dumps(fr("ok")), encoding="utf-8")
    assert st.ingest_inbox() == {"ingested": 1, "rejected": 1}
    assert (st.rejected / "bad.json").exists() and (st.rejected / "bad.err").exists()


def test_readonly_store(tmp_path):
    missing = tmp_path / "nothing"
    st = FrameStore(missing, readonly=True)
    assert not missing.exists() and st.count() == 0
    with pytest.raises(FrameError, match="read-only"):
        st.put(fr())
    with pytest.raises(FrameError, match="read-only"):
        st.ingest_inbox()
    assert not missing.exists()


def test_demo_frames_carry_demo_set():
    for f in frames.demo_frames():
        assert f["attrs"]["demo_set"] == "demo"


def test_demo_golden_readings_match():
    def nfc(s):
        return unicodedata.normalize("NFC", s)

    gold = {(h["bare"], h.get("occ", 1)): nfc(h["reading"]) for h in GOLD["items"][0]["homographs"]}
    by_lemma = {f["head"]["lemma"]: nfc(f["surface"]["he"]["text"]) for f in frames.demo_frames()}
    assert by_lemma["hair"] == gold[("שערה", 1)]
    assert by_lemma["storm"] == gold[("שערה", 2)]
    assert by_lemma["eyebrow"] == gold[("גבה", 1)]


def test_demo_keys():
    keys = frames.demo_keys()
    assert len(keys) == 23 and keys == frames.demo_keys()
    assert all(re.fullmatch(r"[0-9a-f]{64}", k) for k in keys)


def test_store_singleton(fresh_store, monkeypatch, tmp_path):
    assert frames.store() is frames.store()
    frames._default_store = None
    monkeypatch.setenv("FRAMES_DIR", str(tmp_path / "absent"))
    st = frames.store()
    assert st.readonly and st.count() == 0
