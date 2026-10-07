# Floor lists

The content gate's floor: terms refused in every context, checked on every request before the classifier and the translation, with or without a key, under every `GATE_POLICY`. The floor is deliberately strict: a listed term is refused even in a medical, legal, news or literary sentence. Everything not on the floor is judged in context by the content classifier (see the main README, Configuration).

One file per `(language, category)`: `en` and `he`, `child_safety` and `sexual`.
Each line is a single trigger term; an English line may also be a phrase. A Hebrew line must be one word: Hebrew matching compares single tokens, so a Hebrew phrase never matches. Lines starting with `#` are ignored. Matching is whole-word (English: regex `\b`; Hebrew: whitespace and punctuation token split, with prefix stripping for ו/ה/ב/כ/ל/מ/ש combinations). Other languages are checked against the English lists.

## Curation rules

- A term belongs here when the author wants it refused in every context, innocent senses included; that trade-off is deliberate.
- The gate **rejects** on match; it never sanitizes. A term is removed only by editing the list.
- Hebrew matching strips standard prefixes, so adding `מילה` also
  catches `הומילה`, `שמילה`, `וכשמילה`, etc.
- After editing, rebuild the api image: `docker compose up -d --build`.
