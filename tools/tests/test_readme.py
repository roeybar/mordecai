"""README checks: the challenge sentences are copied from the goldens exactly and each has its test,
the languages table matches the registry, the README, docs/configuration.md and the goldens name no
third-party translator or model, and the README and docs/configuration.md carry no unlabelled score
and no bidi controls. The configuration table and the model-and-effort, content-gate and hosted-demo
paragraphs are in docs/configuration.md and are checked there; the whole of that file counts as a
"## Configuration" section (CONFIG_SECTION). The model ids configured in docker-compose.yml, and the
lists of them, are product configuration: their table cells are exempt from the name check inside a
"## Configuration" section. Inside "## Configuration" the backticked product identifiers in PRODUCT_IDS
and the one "Hosted demo: " paragraph (the hosted demo's data disclosure) are exempt as well."""
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CONFIG = (ROOT / "docs/configuration.md").read_text(encoding="utf-8")
# The whole of docs/configuration.md as one "## Configuration" section, for the name check.
CONFIG_SECTION = "## Configuration\n\n" + CONFIG
TRANSLATE = (ROOT / "api/mordecai/routes/translate.py").read_text(encoding="utf-8")
CH_PATH = ROOT / "api/mordecai/demo_data/challenges.json"
CHALLENGES = json.loads(CH_PATH.read_text(encoding="utf-8"))["items"]
GOLDEN = {i["id"]: i for i in json.loads(
    (ROOT / "api/tests/goldens/torture_he.json").read_text(encoding="utf-8"))["items"]}
TESTS = (ROOT / "api/tests/test_challenges.py").read_text(encoding="utf-8")
GOLDEN_FILES = ["homograph_he.json", "torture_he.json", "torture_ar.json"]
# The names the README must not mention; a check that forbids names has to name them.
NAME_LIST = ("opus", "grok", "gpt", "gemini", "claude", "google", "deepl", "bing", "copilot")
NAMES = re.compile(r"(?i)(?<![a-z])(" + "|".join(NAME_LIST) + r")(?![a-z])")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
CONFIG_IDS = sorted(set(re.findall(r"\$\{[A-Z_]+_MODEL:-([^}]+)\}", COMPOSE)))
CONFIG_LISTS = sorted(set(re.findall(r"\$\{[A-Z]+_MODELS:-([^}]+)\}", COMPOSE)))
PRODUCT_IDS = ("`gemini`", "`GEMINI_MODEL`", "`GEMINI_MODELS`", "`GEMINI_GATE_MODEL`", "`GEMINI_API_KEY`")
HOSTED = "Hosted demo: "
EXAMPLE = (ROOT / "docker-compose.hosted.example.yml").read_text(encoding="utf-8")
SCORE = re.compile(r"\b\d+\s*(?:/|of)\s*\d+\b")
BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
HEADINGS = [
    "## Two sentences to try in your translator",
    "## Try it here",
    "## What it is",
    "## Quickstart",
    "## Joint versus sequential disambiguation",
    "## Architecture",
    "## What the demo shows",
    "## Configuration",
    "## Languages",
    "## Tests",
    "## Status",
    "## License",
]


def sentence(c):
    return GOLDEN[c["id"]][c["source"]]


def without_config_cells(text):
    """The text with the table cell of each configured model id removed, only inside the
    "## Configuration" section; everything outside that section is left as it is."""
    head, sep, rest = text.partition("## Configuration")
    if not sep:
        return text
    body, sep2, tail = rest.partition("\n## ")
    for mid in CONFIG_IDS + CONFIG_LISTS:
        body = body.replace(f"| `{mid}` |", "| |")
    for pid in PRODUCT_IDS:
        body = body.replace(pid, "``")
    body = "\n".join("" if ln.startswith(HOSTED) else ln for ln in body.split("\n"))
    return head + sep + body + sep2 + tail


def registry():
    sys.path.insert(0, str(ROOT / "api"))
    try:
        return importlib.import_module("mordecai.langs")
    finally:
        sys.path.remove(str(ROOT / "api"))


@pytest.mark.parametrize("c", CHALLENGES, ids=[c["id"] for c in CHALLENGES])
def test_challenge_is_in_the_readme_as_in_the_golden(c):
    g = GOLDEN[c["id"]]
    if c["source"] == "he":
        assert f'<p dir="rtl">{g["he"]}</p>' in README
    else:
        assert "\n" + g["en"] + "\n" in README
    direction = "rtl" if c["target"] == "he" else "ltr"
    assert f'<p dir="{direction}">{g["gold_" + c["target"]]}</p>' in README
    assert c["id"] in TESTS
    assert README.index(sentence(c)) < README.index("## Try it here")


def test_only_challenge_sentences_are_quoted():
    quoted = {i for i, g in GOLDEN.items() if any(g.get(k) and g[k] in README for k in ("he", "en"))}
    assert quoted == {c["id"] for c in CHALLENGES}


def test_one_reveal_per_challenge():
    assert README.count("<details>") == len(CHALLENGES)


def test_headings_in_order():
    found = [ln for ln in README.splitlines() if ln.startswith("## ")]
    assert found == HEADINGS


def test_quickstart_follows_the_screenshot():
    assert README.index("## Quickstart") > README.index("docs/screenshot.png")


def test_status_legend_defines_verified_by_the_goldens():
    assert ("VERIFIED means this repository holds goldens for that language (api/tests/goldens) "
            "whose readings the golden itself attributes to a native-speaker reviewer; it says "
            "nothing about the demo frames, which are hand-made for every language.") in README


def test_languages_table_matches_the_registry():
    section = README.split("## Languages")[1].split("## Tests")[0]
    rows = re.findall(r"^\| ([a-z]+) \| ([^|]+) \| ([^|]+) \|$", section, re.M)
    assert rows == [(lg.code, lg.name, lg.status) for lg in registry().LANGS.values()]
    assert "| ar | Standard Arabic | MACHINE-MADE, UNVERIFIED |" in README


def test_configured_model_ids_are_readme_table_cells():
    assert len(CONFIG_IDS) == 4
    assert all(f"| `{mid}` |" in CONFIG for mid in CONFIG_IDS)


def test_the_name_check_sees_every_name_and_spares_only_config_cells():
    for name in NAME_LIST:
        assert NAMES.search(without_config_cells(f"a {name.upper()} b"))
    cells = "## Configuration\n\n" + " ".join(f"| `{mid}` |" for mid in CONFIG_IDS)
    assert NAMES.search(without_config_cells(cells)) is None
    assert all(NAMES.search(without_config_cells(f"see {mid}")) for mid in CONFIG_IDS)
    wins = " ".join(f"| `{mid}` | wins |" for mid in CONFIG_IDS)
    inside = f"## Quickstart\n\nx\n\n## Configuration\n\n{wins}\n\n## Status\n\nok\n"
    assert NAMES.search(without_config_cells(inside)) is None
    after = inside.replace("ok\n", f"{wins}\n")
    assert NAMES.search(without_config_cells(after)) is not None
    before = inside.replace("x\n", f"{wins}\n")
    assert NAMES.search(without_config_cells(before)) is not None


def test_the_readme_names_no_third_party_translator_or_model():
    assert NAMES.search(without_config_cells(README)) is None
    assert NAMES.search(without_config_cells(CONFIG_SECTION)) is None
    assert NAMES.search(CONFIG) is not None


@pytest.mark.parametrize("name", GOLDEN_FILES)
def test_the_goldens_name_no_third_party_translator_or_model(name):
    assert NAMES.search((ROOT / "api/tests/goldens" / name).read_text(encoding="utf-8")) is None


def test_the_readme_carries_no_unlabelled_score():
    assert SCORE.search("got 4/7") and SCORE.search("4 of 7 right")
    assert SCORE.search(README) is None
    assert SCORE.search(CONFIG) is None


def test_no_bidi_controls():
    assert BIDI.search(README) is None
    assert BIDI.search(CONFIG) is None


def test_the_readme_describes_the_gate_as_built():
    for code in ("blocked_content", "gate_unavailable", "demo_examples_only"):
        assert f'"{code}"' in CONFIG and f'"{code}"' in TRANSLATE
    assert ("word lists for English and Hebrew" not in README
            and "word lists for English and Hebrew" not in CONFIG)
    assert "fails closed" in CONFIG


def test_the_exemption_is_narrow():
    still_caught = [
        "## Configuration\n\nSee Gemini.\n",
        "## Configuration\n\n`gemini` and gemini\n",
        "## Quickstart\n\nHosted demo: Gemini\n\n## Configuration\n\nx\n",
        "## Configuration\n\nx\n\n## Status\n\nHosted demo: Google\n",
        "## Configuration\n\nx Hosted demo: Google\n",
    ]
    for text in still_caught:
        assert NAMES.search(without_config_cells(text)), text
    exempt = ["## Configuration\n\nHosted demo: Google Gemini\n",
              "## Configuration\n\n`GEMINI_MODEL` `gemini`\n"]
    for text in exempt:
        assert NAMES.search(without_config_cells(text)) is None, text


def test_the_readme_describes_the_hosted_demo_as_built():
    for code in ("demo_limit", "quota_exhausted"):
        assert f'"{code}"' in CONFIG and f'"{code}"' in TRANSLATE
    lines = [ln for ln in CONFIG.splitlines() if ln.startswith(HOSTED)]
    assert len(lines) == 1
    line = lines[0]
    assert CONFIG.index("| `HOSTED_PROVIDER` |") < CONFIG.index(line)
    assert not any(ln.startswith(HOSTED) for ln in README.splitlines())
    for phrase in ("closed, invite-only", "gated address that the hosting setup provides", "ships no key",
                   "whichever provider is used",
                   "A request on this server counts once it passes the request checks, whichever provider, "
                   "including one that the content gate or the vendor then refuses; neither a malformed "
                   "request nor a request refused because the limit is reached counts.",
                   "free tier", "18", "European Economic Area, the United Kingdom or Switzerland",
                   "From Google's Gemini API Additional Terms of Service (Unpaid Services, effective "
                   "March 23, 2026): ",
                   "When you use Unpaid Services, including, for example, Google AI Studio and the unpaid "
                   "quota on Gemini API, Google uses the content you submit to the Services and any "
                   "generated responses to provide, improve, and develop Google products and services "
                   "and machine learning technologies, including Google's enterprise features, "
                   "products, and services, consistent with our Privacy Policy.",
                   "To help with quality and improve our products, human reviewers may read, annotate, "
                   "and process your API input and output.",
                   "Do not submit sensitive, confidential, or personal information to the Unpaid Services."):
        assert phrase in line, phrase
    assert "://" not in line and "public" not in line.lower()


def test_the_quickstart_names_the_example_chips():
    assert 'click an example sentence, then "Translate"' in README
    assert "Load the example" not in README


def test_the_hosted_override_example_holds_no_secret():
    assert "GEMINI_API_KEY: ${GEMINI_API_KEY:?" in EXAMPLE
    assert "AIza" not in EXAMPLE and "cpuset" not in EXAMPLE and "cpuset" not in COMPOSE
    assert "GEMINI_API_KEY" not in COMPOSE
    assert COMPOSE.count("mem_limit") == 4


def test_model_lists_are_readme_cells_and_hold_their_default():
    assert len(CONFIG_LISTS) == 4
    assert all(f"| `{lst}` |" in CONFIG for lst in CONFIG_LISTS)
    defaults = dict(re.findall(r"\$\{([A-Z]+)_MODEL:-([^}]+)\}", COMPOSE))
    lists = dict(re.findall(r"\$\{([A-Z]+)_MODELS:-([^}]+)\}", COMPOSE))
    assert sorted(defaults) == sorted(lists) == ["ANTHROPIC", "GEMINI", "OPENAI", "XAI"]
    assert all(defaults[p] in lists[p].split(",") for p in defaults)


def test_gate_models_default_to_the_translation_models():
    gates = dict(re.findall(r"\$\{([A-Z]+)_GATE_MODEL:-([^}]+)\}", COMPOSE))
    models = dict(re.findall(r"\$\{([A-Z]+)_MODEL:-([^}]+)\}", COMPOSE))
    assert len(gates) == 4 and gates == models


def contact_files(addr):
    skip_dirs = {".git", "node_modules", "report", "test-results", "__pycache__", ".pytest_cache",
                 ".ruff_cache"}
    found = set()
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if not path.is_file() or skip_dirs & set(rel.parts) or path.suffix == ".png":
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue
        if addr.encode("utf-8") in path.read_bytes():
            found.add(rel.as_posix())
    return found


def test_the_contact_default_is_empty():
    assert "CONTACT_EMAIL: ${CONTACT_EMAIL:-}" in COMPOSE
    sentence_a = ("This public toolkit is a demo on an example frame set, not the full mordecai; for the "
                  "full project, contact the author.")
    assert README.index(sentence_a) < README.index("## Two sentences")
    assert "| `CONTACT_EMAIL` | (empty) |" in CONFIG
    assert contact_files("@gmail" + ".com") == set()


def test_the_readme_names_the_model_and_effort_errors():
    for code in ("unknown_model", "unknown_effort"):
        assert f'"{code}"' in CONFIG and f'"{code}"' in TRANSLATE
    assert (
        "Model and effort: a translation request may name `model`, one of the provider's `*_MODELS` ids "
        "(absent means its `*_MODEL`), and `effort`, one of the levels that model accepts (absent means its "
        "lowest level). `GET /api/providers` lists, per provider, each model with its effort levels (lowest "
        "first) and whether it is the default. The effort is the vendor's own depth control: a thinking "
        "level, a reasoning effort or an effort level. The `xai` provider and a model without a level table "
        "take no effort, and a demo request that names either field gets 400. At the lowest level, a model "
        "whose vendor allows it runs with its thinking turned off. A model the provider does not offer gets "
        '400 `{"error": "unknown_model"}`, and an effort the model does not accept gets 400 '
        '`{"error": "unknown_effort"}`. The translation\'s output cap is 1024 tokens at the lowest level or '
        "for a model without a level table, and 8192 above the lowest level, because thinking counts "
        "against it.") in CONFIG


def test_the_readme_states_the_fixed_classifier_model():
    assert ("The classifier calls run on a fixed model per provider at its lowest effort level, whatever "
            "model and effort you pick for the translation (`ANTHROPIC_GATE_MODEL`, `XAI_GATE_MODEL`, "
            "`GEMINI_GATE_MODEL`, `OPENAI_GATE_MODEL`).") in CONFIG
