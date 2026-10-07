from mordecai import eval_torture as ev


def test_deterministic_clean(demo):
    lines = []
    assert ev.deterministic(demo, out=lines.append) == 0
    text = "\n".join(lines)
    assert "torture: clean" in text
    assert "-> solver 3/3, greedy 2/3, coverage gaps 0" in text
    assert "judged suites, no deterministic check in this toolkit" in text
    assert "summary: 17 homographs, solver 5, greedy 4, coverage gaps 12, failures 0" in text
    assert "mega-page" not in text


def test_no_mined_item():
    ids = [i["id"] for i in ev.load("homograph_he.json")["items"]]
    assert ids == ["hair-eyebrow-storm-boat", "barber-minister-storm-sun-wrath"]
    for name in ("homograph_he.json", "torture_he.json", "torture_ar.json"):
        raw = (ev.GOLDENS / name).read_text(encoding="utf-8")
        assert '"mined"' not in raw and "_build" not in raw


def test_check_item_seed(demo):
    rows = ev.check_item(demo, ev.load("homograph_he.json")["items"][0])
    assert [r["status"] for r in rows] == ["ok", "ok", "ok"]
    assert [r["greedy"] == r["gold"] for r in rows] == [True, True, False]


def test_check_item_gap_is_not_an_exception(demo):
    for item in ev.load("homograph_he.json")["items"][1:]:
        rows = ev.check_item(demo, item)
        assert rows and {r["status"] for r in rows} <= {"ok", "gap"}


def test_goldens_load():
    for name in ("homograph_he.json", "torture_he.json", "torture_ar.json"):
        items = ev.load(name)["items"]
        assert items and all(i.get("id") for i in items)
    assert all("ar" in i or "gold_ar" in i for i in ev.load("torture_ar.json")["items"])


def test_main_usage(capsys):
    assert ev.main([]) == 2
    assert "usage" in capsys.readouterr().out


def test_challenge_blocks_ok(demo):
    lines = []
    assert ev.deterministic(demo, out=lines.append) == 0
    text = "\n".join(lines)
    assert "challenge mw-attention (he->en)" in text
    assert "challenge llm-bark (en->he)" in text
    assert "  ok    demo output  he took notice that-the-door open" in text
    assert "FAIL" not in text


def test_challenge_failure_is_reported(demo, monkeypatch):
    bad = [dict(c, demo_output="x") for c in ev.challenges.load()]
    monkeypatch.setattr(ev.challenges, "load", lambda: bad)
    lines = []
    assert ev.deterministic(demo, out=lines.append) == 1
    assert "torture: FAIL" in "\n".join(lines)
