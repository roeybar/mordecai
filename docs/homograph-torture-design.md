# Homograph torture test - design

The goldens in `api/tests/goldens/homograph_he.json` are engineered so that **local,
greedy reading fails and only systematic global solving wins.** The point is not
that a solver is smarter than a reader: it is *systematic* where a freeform
reader is *greedy*.

## Why a greedy reader slips
Bare Hebrew (ktiv haser) hides the vowels. `ספר` is one spelling for **six**
words (book / barber / counted / told / frontier / tell!); `חמה` is sun / wrath /
mother-in-law; `אתה` is "you" / "with her". A reader going left-to-right
**commits** to a sense early ("`ספר` = book") and is then locally consistent but
globally wrong. The `barber-minister-storm-sun-wrath` item has **14** forced resolutions.

## Two generation approaches
1. **Mined (data-driven)** - group a dictionary by niqqud-stripped form; bare
   forms with two or more vocalizations are homographs. Repeatable; limited by
   dictionary coverage. Neither the mining tool nor any mined item is part of this toolkit.
2. **Constructed (knowledge-driven)** - author a coherent passage packing the
   classic semantic homographs the lexicon doesn't fully store (`ספר`x5, `חמה`x2,
   `שר`x2). Maximal density, artful coherence.

This repository ships no mined item; its goldens are constructed.

## Both solver approaches (the target to build)
A greedy reader picks senses one-at-a-time. A pipeline can do what a reader
can't, two complementary ways:

1. **Niqqud restoration** - add the correct vowel points, which *is* the
   disambiguation (`סֵפֶר` vs `סַפָּר` vs `סָפַר`). Writing the chosen reading with
   its niqqud makes it **explicit and verifiable**, not a hidden guess. This
   toolkit shows the niqqud stored on the demo frames; it has no niqqud
   restoration engine.
2. **Global sense-coherence (constraint satisfaction)** - for *each* token,
   enumerate the full reading-set from the lexicon (no recall failure), then pick
   the single assignment that makes the **whole** passage coherent - a book can't
   "tell", wrath can't "set", a hair can't be sung about. This is constraint
   propagation over candidates, not left-to-right greed.

These compose: enumerate candidates (lexicon) -> solve globally (coherence) ->
realize the winner with correct niqqud (verifiable).

## Honest status
This toolkit builds only a toy global solver (`api/mordecai/sense_solver.py`):
each slot binds the nearest word on one side, skipping words whose readings are
all function words, and the assignment is solved exactly over the demo frames.
It resolves the seed item and the two README challenge sentences on the demo
frames, whose types and priors were hand-set for those sentences; the general
solver and the selectional resource are not built, so the larger item remains
a coverage gap. On this set a native-speaker reviewer is **ground truth**: an
automatic judge is a draft, and the reviewer's readings decide the hardest items.

## Files
- `api/tests/goldens/homograph_he.json` - 2 graded items (seed -> ספר passage).
- `api/mordecai/sense_solver.py` - candidate lattice, toy global solver, greedy baseline.
