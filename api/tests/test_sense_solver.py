from mordecai import sense_solver as ss
from mordecai import text

from .conftest import SEED


def lat_of(demo):
    return ss.lattice(demo, "he", text.tokenize("he", SEED))


def test_lattice_shape(demo):
    lat = lat_of(demo)
    assert [len(c) for c in lat] == [1, 1, 2, 2, 1, 1, 2, 1, 1]
    assert [c[0].prefix for c in lat] == ["", "", "", "ב", "", "ש", "", "ש", "ב"]


def test_solver_picks_gold_and_greedy_misses(demo):
    lat = lat_of(demo)
    sol = ss.solve(lat)
    assert sol.score == 3 and sol.evaluated > 0
    assert lat[2][sol.choice[2]].gloss("en") == "hair"
    assert lat[3][sol.choice[3]].gloss("en") == "eyebrow"
    assert lat[6][sol.choice[6]].gloss("en") == "storm"
    g = ss.greedy(lat)
    assert lat[6][g[6]].gloss("en") == "hair"
    assert ss.score(lat, g) == 1


def test_empty_position_gives_none(demo):
    lat = ss.lattice(demo, "he", ["xyzzy", "שלום"])
    assert lat == [[], []]
    sol = ss.solve(lat)
    assert sol.choice == [None, None] and sol.score == 0
    assert ss.greedy(lat) == [None, None]
    assert ss.solve([]).choice == []


def test_anchors_skip_function_words(demo):
    assert ss.anchors(lat_of(demo)) == [0, 1, 2, 3, 5, 6, 7, 8]


A = ss.Reading("a", "", "a", {}, slots=(("patient", "x", False),), bind={"patient": "right"})
F = ss.Reading("f", "", "f", {}, kind="function")
B = ss.Reading("b", "", "b", {}, sem="x")
E = ss.Reading("e", "", "e", {}, kind="entity")


def test_function_words_are_transparent():
    assert ss.solve([[A], [F], [F], [B]]).score == 1
    assert ss.solve([[A], [E], [B]]).score == 0
    assert ss.solve([[F], [F]]).choice == [0, 0]


def test_empty_and_mixed_positions_are_not_transparent():
    assert ss.solve([[A], [], [B]]).score == 0
    assert ss.solve([[A], [F, E], [B]]).score == 0
