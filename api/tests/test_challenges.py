import pytest
from mordecai import challenges, providers
from mordecai import eval_torture as ev
from mordecai import sense_solver as ss
from mordecai.stages import translate

from .conftest import BARK, BARK_EXPECTED, MW, MW_EXPECTED

IDS = ["mw-attention", "llm-bark"]
KLIPA = "\u05e7\u05b0\u05dc\u05b4\u05d9\u05e4\u05b8\u05bc\u05d4"
NVIHA = "\u05e0\u05b0\u05d1\u05b4\u05d9\u05d7\u05b8\u05d4"
BARK_GOLD = (
    "\u05e7\u05dc\u05d9\u05e4\u05ea \u05d4\u05d0\u05dc\u05d5\u05df "
    "\u05d4\u05d9\u05d9\u05ea\u05d4 \u05de\u05d7\u05d5\u05e1\u05e4\u05e1\u05ea"
)


def run(demo, ch):
    return translate(ch["text"], src_lang=ch["source"], tgt_lang=ch["target"],
                     provider=providers.get("demo"), store=demo)


def test_load():
    chs = challenges.load()
    assert [c["id"] for c in chs] == IDS
    mw, bark = chs
    assert mw["text"] == MW and mw["gold"] == "He noticed the door was open."
    assert bark["text"] == BARK and bark["gold"] == BARK_GOLD
    assert mw["demo_output"] == MW_EXPECTED and bark["demo_output"] == BARK_EXPECTED


@pytest.mark.parametrize("cid", IDS)
def test_challenge_resolves(demo, cid):
    ch = next(c for c in challenges.load() if c["id"] == cid)
    res = run(demo, ch)
    assert res.text == ch["demo_output"]
    assert res.verdict.ok
    assert res.repaired.notes == []
    assert res.resolution.score == 1
    assert ss.score(res.analysis.lattice, res.resolution.greedy) == 0
    chk = ev.check_challenge(demo, ch)
    assert chk["output_ok"]
    assert [r["status"] for r in chk["rows"]] == ["ok"] * len(ch["homographs"])
    assert all(r["greedy"] != r["gold"] for r in chk["rows"])


def test_mw_lattice(demo):
    res = run(demo, challenges.load()[0])
    lat, rs = res.analysis.lattice, res.resolution
    assert [len(c) for c in lat] == [1, 3, 2, 1, 1]
    assert [c[0].prefix for c in lat] == ["", "", "", "\u05e9\u05d4", ""]
    assert lat[1][rs.choice[1]].gloss("en") == "took"
    assert lat[2][rs.choice[2]].gloss("en") == "notice"
    assert lat[1][rs.greedy[1]].gloss("en") == "there"
    assert lat[2][rs.greedy[2]].gloss("en") == "heart"


def test_bark_lattice(demo):
    res = run(demo, challenges.load()[1])
    lat, rs = res.analysis.lattice, res.resolution
    assert ss.anchors(lat) == [1, 4, 5, 6]
    assert lat[1][rs.choice[1]].gloss("he") == KLIPA
    assert lat[1][rs.greedy[1]].gloss("he") == NVIHA
