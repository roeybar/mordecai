# Homograph torture test - design

The goldens in `api/tests/goldens/homograph_he.json` are designed so that local, sequential reading fails and only systematic joint solving succeeds. The claim is not that a solver is smarter than a reader, but that it weighs the whole passage at once where a freeform reader commits to one sense at a time.

## Why sequential reading can fail
Bare Hebrew (ktiv haser) leaves most vowels unmarked. `ספר` is one spelling for six words (book, barber, counted, told, frontier, tell (imperative)); `חמה` is sun, wrath or mother-in-law; `אתה` is "you" or "with her". A reader going left to right commits to a sense early (`ספר` as "book") and is then locally consistent but globally wrong. The `barber-minister-storm-sun-wrath` item has 14 forced resolutions.

## Two generation approaches
1. **Mined (data-driven)**: group a dictionary by niqqud-stripped form; bare
   forms with two or more vocalizations are homographs. The method is repeatable and limited by dictionary coverage. Neither the mining tool nor any mined item is part of this toolkit.
2. **Constructed (knowledge-driven)**: write a coherent passage that packs in the well-known semantic homographs the lexicon does not fully store (`ספר`x5, `חמה`x2, `שר`x2).

This repository ships no mined item; its goldens are constructed.

## Two solver approaches (the design target)
A sequential reader picks senses one at a time. A pipeline can go beyond sequential reading in two complementary ways:

1. **Niqqud restoration**: add the correct vowel points, which is itself the disambiguation (`סֵפֶר` vs `סַפָּר` vs `סָפַר`). Writing the chosen reading with
   its niqqud makes it explicit and verifiable rather than a hidden guess. This
   toolkit shows the niqqud stored on the demo frames; it has no niqqud
   restoration engine.
2. **Joint sense coherence (constraint satisfaction)**: for each token, enumerate the full set of readings from the lexicon (no recall failure), then pick the single assignment that makes the whole passage coherent: a book cannot "tell", wrath cannot "set", a hair cannot be sung about. This is constraint propagation over candidates, not left-to-right sequential choice.

These compose: enumerate candidates (lexicon) -> solve jointly (coherence) ->
realize the chosen reading with the correct niqqud (verifiable).

## Status
This toolkit builds only a toy joint solver (`api/mordecai/sense_solver.py`):
each slot binds the nearest word on one side, skipping words whose readings are
all function words, and the assignment is solved exactly over the demo frames.
It resolves the seed item and the two README challenge sentences on the demo
frames, whose types and priors were hand-set for those sentences; the general
solver and the selectional resource are not built, so the larger item remains
a coverage gap. On this set a native-speaker reviewer is ground truth: an automatic judge is a draft, and the reviewer's readings decide the hardest items.

## Files
- `api/tests/goldens/homograph_he.json` - 2 graded items (seed -> ספר passage).
- `api/mordecai/sense_solver.py` - candidate lattice, toy joint solver, sequential baseline (`greedy` in the code).
