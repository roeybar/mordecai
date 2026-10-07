# Global sense-solver - design

An earlier version of this design stopped at "the lattice fixes recall and
greedy choice, not world knowledge". A solver that cannot tell that a storm,
not a hair, rocks a boat has not solved the problem. This version uses one
mechanism for recall, greedy choice, world knowledge, polysemy and niqqud: the
knowledge is encoded once instead of being reasoned out again for every query.

## Disambiguation as type checking
"A hair can't rock a boat" is a **selectional restriction**: the
event `rock(theme: boat)` requires an agent that is a *force/motion-cause*; a
*hair* is a small physical object; a *storm* is a natural force. The right reading
is the one whose **type satisfies the predicate's slot**.

So disambiguation = **typed constraint satisfaction**, not LLM reasoning:
- each candidate reading carries an **ontological type** (storm = event/force,
  hair = physical-object) - from the frame `kind` + lexicon features;
- each predicate carries **slot selectional restrictions** (`rock-a-boat.agent in
  {force, vehicle-motion-cause}`) - a stored resource;
- the coherent assignment is the one where **every predicate's arguments satisfy
  its slot types**. Propagate the constraints; the contradictions fall out.

That's the world-knowledge - *encoded as types + restrictions*, applied
**deterministically**. The model isn't asked "is this coherent?" each time; the
knowledge lives in the frame store and is checked like a type-checker checks a
program.

## Frames as the knowledge base
Here frames serve as a **typed knowledge substrate**.
Typed slots plus selectional restrictions turn "pick a sense" from a guess into
a constraint check, and the frame store's typed JSON documents are where that
knowledge is encoded.

## Encoding once versus reasoning per query
The knowledge ultimately comes from an LLM (or curation) either way - the
difference is *when and how*:

| | per-query LLM reasoning (earlier design) | encoded selectional resource (this design, not built here) |
|---|---|---|
| verifiable | no - varies per call | **yes - built offline, curated, reviewed before trusted** |
| deterministic | no | **yes - same input, same answer** |
| cost | an LLM call on every query | **once; then free deterministic checks** |
| reusable | no | **yes - accumulates into the frame store** |
| corpus needed | a live co-occurrence corpus | **no - selectional prefs are bootstrapped, not counted** |

This is the same move as "encode niqqud in a lexicon instead of guessing it each
time" - convert unreliable per-instance reasoning into a curated, deterministic,
growing resource (not built here). It also **sidesteps a co-occurrence corpus**:
selectional restrictions are a *structured* generalization of collocation
(predicate<->argument-type, not word<->word counts), so a small typed resource
replaces a giant corpus.

## The solver (design; only step 1 and a toy solver are built here)
1. **Typed candidate lattice** - per token, all readings from the lexicon, EACH
   tagged with its ontological type (frame `kind` + features). (recall OK)
2. **Constraint propagation** - for each predicate in the parse, keep only
   argument readings whose type satisfies the slot's selectional restriction;
   propagate until fixpoint. Contradictions (hair-as-boat-rocker) are eliminated,
   not out-voted. (greed OK, world-knowledge OK)
3. **Residual tiebreak** - if >1 assignment survives (genuinely ambiguous), THEN
   a cheap prior (frequency/field) or a single LLM tiebreak picks - but only over
   the already-type-valid options, never the absurd ones. (bounded, verifiable)
4. **Realize** - chosen reading -> niqqud + translation.
   (niqqud OK)

In this design every step is checkable against the frame store and a pick that violates a selectional restriction is rejected. The toy solver built here does not reject: a violated required slot costs one point (api/mordecai/sense_solver.py, _slot_terms).

## The real work: the selectional resource (built offline, curated, growing)
This is where the effort goes, and it's tractable because it's one-time + layered:
- **Layer 0 - coarse kind-typing.** entity / event / quality / function kinds
  from the frame vocabulary plus a hand-set semantic type per demo frame; this
  toolkit's toy solver checks slot types against those.
- **Layer 1 - predicate selectional prefs (bootstrapped, curated).** One offline
  LLM pass per predicate-frame: "what type must each argument be?" -> stored on the
  frame as slot restrictions, **reviewed before trust** (a human reviewer is
  ground truth on the hard cases). Accumulates in the frame store. Not built here.
- **Layer 2 - incremental.** New predicates/types added on demand as goldens
  surface gaps. The resource grows; it never needs a corpus.

## Status and limits
- This toolkit builds the typed candidate lattice and a toy solver
  (`sense_solver.py`): each slot binds the nearest word on one side, skipping
  words whose readings are all function words; the score is a chain of pairwise
  terms and an exact dynamic program finds the best assignment. General
  constraint propagation over a parse and the selectional resource are not built.
- With the demo provider a word without a frame is shown in brackets; with a keyed provider the model translates such a word without a fixed sense and the response does not flag that. A human reviewer is ground truth on the hard goldens.
- The design (not built here) can encode any selectional constraint that someone builds, so the
  remaining failures are knowledge that has not been encoded yet. That is a
  coverage problem (incremental and measurable), not a limit of the mechanism, for the design; the toy solver here has no such resource.
- The selectional resource still comes from an LLM or from curation; the
  difference is that it is built offline, verified, deterministic and reusable.
