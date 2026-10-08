# mordecai

This public toolkit is a demo on an example frame set, not the full mordecai; for the full project, contact the author.

## Two sentences to try in your translator

Paste each sentence into the translator you use, then expand the section below it to see the intended meaning.

**Hebrew**

<p dir="rtl">הוא שם לב שהדלת פתוחה</p>

<details>
<summary>Intended meaning</summary>
<p dir="ltr">He noticed the door was open.</p>
</details>

**English**

The bark of the oak was rough.

<details>
<summary>Intended meaning (in Hebrew)</summary>
<p dir="rtl">קליפת האלון הייתה מחוספסת</p>
</details>

Both sentences come from this repository's torture tests (`api/tests/goldens/torture_he.json`, items `mw-attention` and `llm-bark`). The toolkit's demo resolves both with frames hand-set for these sentences, and `api/tests/test_challenges.py` checks that on every test run.

## Try it here

The toolkit runs on your own machine from a fresh clone (see Quickstart below); the demo provider resolves both sentences with no API key.

## What it is

mordecai is a research toolkit for resolving homographs with typed frames.

![mordecai demo resolving the Hebrew challenge sentence](docs/screenshot.png)

## Quickstart

```sh
git clone https://github.com/roeybar/mordecai && cd mordecai
docker compose up -d --build --wait
```

Open http://localhost:8080, click an example sentence, then "Translate". No API key is needed: the demo provider runs offline on the built-in demo frames and accepts only the example sentences.

## Joint versus sequential disambiguation

Hebrew written without vowel points leaves most vowels unmarked, so one spelling can stand for several different words. The seed item of `api/tests/goldens/homograph_he.json` is a short sentence where the same letters appear as "hair" and as "storm", next to "eyebrow":

<p dir="rtl">הייתה לי שערה בגבה בזמן שהייתה שערה שטילטלה בסירה</p>

The gold readings for the three homographs, in order, are:

<p dir="rtl">שַׂעֲרָה / גַּבָּה / סְעָרָה</p>

A sequential reader commits to each sense as it meets it and can be locally consistent but globally wrong. Solving the whole sentence at once avoids that: on the demo frames the toy solver picks all three gold readings, while the sequential baseline (`greedy` in the code) reads the second occurrence of the repeated spelling as "hair" again. `api/tests/test_sense_solver.py` checks both picks on every test run. The design notes are in [docs/homograph-torture-design.md](docs/homograph-torture-design.md) and [docs/global-sense-solver-spec.md](docs/global-sense-solver-spec.md).

## Architecture

```
browser -> web (nginx) -> api
                           gate        input: floor lists, then a classifier call (keyed providers)
                           S0 analyze  tokenize, candidate lattice from the frame store
                           S1 resolve  toy joint solver, plus the sequential baseline
                           S2 render   provider: demo, or a keyed provider (see Configuration)
                           S3 repair   normalise the output, flag a script mismatch
                           S4 verify   chosen senses present in the output
                           gate        output: floor lists, then a classifier call (keyed providers)
```

A frame is a nested JSON document with a canonical key: a hash over its semantic identity (kind, head, identity-class attributes, parts, required slots). Surfaces and features are not hashed. A controlled vocabulary is enforced when a frame is canonicalized.

## What the demo shows

The output line is a word-by-word gloss built from the demo frames, not a translation. Under the output, "How each word was read" lists each word that has candidates in the frame store, with the solver's pick, the sequential baseline (the first candidate) marked "differs" or "same", and all candidates. The demo frames (`api/mordecai/demo_data/demo_frames.json`) were hand-made for the three example sentences; their types, priors and slot bindings were hand-set for those sentences, so the demo shows the mechanism and is not an accuracy result. The solver is a toy: each slot binds the nearest word on one side, skipping function words, and an exact dynamic program picks the best assignment. Hebrew readings not taken from the goldens are hand-made and not reviewed by a speaker.

## Configuration

All variables are optional (see `.env.example`). With the defaults, the demo provider runs offline on the built-in demo frames.

Bring your own key: the `anthropic`, `xai`, `gemini` and `openai` providers need a key. It goes in the `X-Provider-Key` header of the request, is used for that request only (the translation and its two content checks), and is never stored or logged.

The configuration reference (the variables and their defaults, model and effort, your own frames, the content gate, the hosted demo and the streaming endpoint) is in [docs/configuration.md](docs/configuration.md).

## Languages

The registry lists 16 languages. Source: Ethnologue 29th ed. (2026), plus Hebrew.

| Code | Language | Status |
|---|---|---|
| en | English | VERIFIED |
| zh | Mandarin Chinese | MACHINE-MADE, UNVERIFIED |
| hi | Hindi | MACHINE-MADE, UNVERIFIED |
| es | Spanish | MACHINE-MADE, UNVERIFIED |
| ar | Standard Arabic | MACHINE-MADE, UNVERIFIED |
| fr | French | MACHINE-MADE, UNVERIFIED |
| bn | Bengali | MACHINE-MADE, UNVERIFIED |
| pt | Portuguese | MACHINE-MADE, UNVERIFIED |
| id | Indonesian | MACHINE-MADE, UNVERIFIED |
| ur | Urdu | MACHINE-MADE, UNVERIFIED |
| ru | Russian | MACHINE-MADE, UNVERIFIED |
| de | Standard German | MACHINE-MADE, UNVERIFIED |
| ja | Japanese | MACHINE-MADE, UNVERIFIED |
| pcm | Nigerian Pidgin | MACHINE-MADE, UNVERIFIED |
| arz | Egyptian Arabic | MACHINE-MADE, UNVERIFIED |
| he | Hebrew | VERIFIED |

VERIFIED means this repository holds goldens for that language (api/tests/goldens) whose readings the golden itself attributes to a native-speaker reviewer; it says nothing about the demo frames, which are hand-made for every language. MACHINE-MADE, UNVERIFIED means no speaker has checked it, and no quality is claimed. The test samples in `api/tests/lang_samples.json` were written by this toolkit's author and are not reviewed by speakers.

## Tests

```sh
docker compose run --rm --no-deps api python -m pytest
docker compose run --rm --no-deps api python -m mordecai.eval_torture --deterministic
docker compose --profile tools run --rm check
docker compose up -d --build --wait
docker compose --profile tools run --rm e2e
```

The first command runs the api suite, the second the deterministic torture check, the third lint and the tool tests, and the last the browser tests against the running stack.

Content files (the goldens, the language samples, the demo frames and the blocklists) hold text in their own scripts; every other text file in the repository is ASCII apart from Hebrew and Arabic characters (examples in tests and docs, and the prefix-letter tables in the code).

To stop it: `docker compose down`.

## Status

An unfinished research prototype.

What worked: canonical frame identity with a vocabulary check; a staged pipeline with typed hand-offs; goldens that expose the failure of sequential reading.

What did not: the general solver and the selectional resource are not built, so the larger golden item remains a coverage gap here.

Why frames need an expert: the sense inventory, the slot types and the Hebrew readings all come from a person who reads the language. Without that review the frames only repeat guesses.

## License

PolyForm Noncommercial 1.0.0 (`PolyForm-Noncommercial-1.0.0`), a source-available license: any noncommercial use is permitted. See `LICENSE`.
