# Joint sense-solver - design

An earlier version of this design stopped at "the lattice fixes recall and
greedy choice, not world knowledge". A solver that cannot tell that a storm,
not a hair, rocks a boat has not solved the problem. This version proposes one mechanism that covers recall, the failure of sequential choice, the need for world knowledge, polysemy and niqqud: the knowledge is encoded once instead of being reasoned out again for every query.

## Disambiguation as type checking
"A hair cannot rock a boat" is a selectional restriction: the event `rock(theme: boat)` requires an agent that is a *force/motion-cause*; a *hair* is a small physical object; a *storm* is a natural force. The correct reading is the one whose type satisfies the predicate's slot.

Disambiguation is therefore typed constraint satisfaction, not LLM reasoning:
- each candidate reading carries an ontological type (storm: event/force; hair: physical object), taken from the frame `kind` and lexicon features;
- each predicate carries selectional restrictions on its slots (`rock-a-boat.agent in {force, vehicle-motion-cause}`), held in a stored resource;
- the coherent assignment is the one in which every predicate's arguments satisfy its slot types. Propagating the constraints eliminates the contradictory readings.

This is the world knowledge, encoded as types and restrictions and applied deterministically. The model is not asked "is this coherent?" for each query; the knowledge is held in the frame store and checked the way a type checker checks a program.

## Frames as the knowledge base
In this design, frames serve as a typed knowledge base.
Typed slots and selectional restrictions turn sense selection from a guess into a constraint check, and the frame store's typed JSON documents hold that knowledge.

## Encoding once versus reasoning per query
In both approaches the knowledge comes from an LLM or from curation; they differ in when and how it is applied:

| | per-query LLM reasoning (earlier design) | encoded selectional resource (this design, not built here) |
|---|---|---|
| verifiable | no: varies per call | yes: built offline, curated, reviewed before it is trusted |
| deterministic | no | yes: same input, same answer when the tiebreak is a prior |
| cost | an LLM call on every query | a one-time build, then deterministic checks; a model call only for a residual tiebreak |
| reusable | no | yes: accumulates in the frame store |
| corpus needed | a live co-occurrence corpus | no: selectional preferences are bootstrapped, not counted |

This follows the same principle as encoding niqqud in a lexicon instead of guessing it each time: unreliable per-instance reasoning becomes a curated, deterministic, growing resource (not built here). The design also does not need a co-occurrence corpus: selectional restrictions are a structured generalization of collocation (predicate<->argument-type, not word<->word counts), so a small typed resource is meant to take the place of a large corpus.

## The solver (design; only step 1 and a toy solver are built here)
1. **Typed candidate lattice**: for each token, all readings from the lexicon, each tagged with its ontological type (frame `kind` and features). Addresses recall.
2. **Constraint propagation**: for each predicate in the parse, keep only the argument readings whose type satisfies the slot's selectional restriction, and propagate until a fixed point is reached. Contradictory readings (a hair as what rocks the boat) are eliminated, not out-voted. Addresses the failure of sequential choice and the need for world knowledge.
3. **Residual tiebreak**: if more than one assignment survives (the sentence is genuinely ambiguous), an inexpensive prior (frequency or field) or a single LLM call chooses, but only among the assignments that are already type-valid. The choice is bounded and verifiable.
4. **Realize**: render the chosen reading with its niqqud and its translation. Addresses niqqud.

In this design every step is checkable against the frame store and a pick that violates a selectional restriction is rejected. The toy solver built here does not reject: a violated required slot costs one point (api/mordecai/sense_solver.py, _slot_terms).

## The selectional resource (design: built offline, curated, growing)
Most of the effort in this design goes here; it is tractable because the resource is built once and in layers:
- **Layer 0: coarse kind typing.** Entity, event, quality and function kinds from the frame vocabulary, plus a hand-set semantic type per demo frame; this toolkit's toy solver checks slot types against these.
- **Layer 1: predicate selectional preferences (bootstrapped, curated).** One offline LLM pass per predicate frame asks what type each argument must be; the answers are stored on the frame as slot restrictions and reviewed before they are trusted (a human reviewer is ground truth on the hard cases). The layer accumulates in the frame store. Not built here.
- **Layer 2: incremental.** New predicates and types are added when goldens expose gaps. The resource grows and does not need a corpus.

## Status and limits
- This toolkit builds the typed candidate lattice and a toy solver
  (`sense_solver.py`): each slot binds the nearest word on one side, skipping
  words whose readings are all function words; the score is a chain of pairwise
  terms and an exact dynamic program finds the best assignment. General
  constraint propagation over a parse and the selectional resource are not built.
- With the demo provider a word without a frame is shown in brackets; with a keyed provider the model translates such a word without a fixed sense and the response does not flag that. A human reviewer is ground truth on the hard goldens.
- The design (not built here) can encode any selectional constraint that someone builds, so the
  remaining failures are knowledge that has not been encoded yet. For the design, that is a coverage problem (incremental and measurable), not a limit of the mechanism; the toy solver here has no such resource.
- The selectional resource still comes from an LLM or from curation; the
  difference is that it is built offline, verified, deterministic and reusable.
