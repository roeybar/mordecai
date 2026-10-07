import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mordecai import frames, gate, hosted, providers  # noqa: E402

KEY = "test-key-" + "G4t3K3y9" * 3
SERVER_KEY = "server-key-" + "H0st3dK3" * 3
TRUSTED = "172.30.47.0/24"
CHARGER_PHONE = "I forgot my phone charger at home."
CHARGER_RIFLE = "Press the rounds from the charger into the rifle magazine."
SEED ="הייתה לי שערה בגבה בזמן שהייתה שערה שטילטלה בסירה"
SEED_EXPECTED = "was to me hair in-eyebrow while that-was storm that-rocked in-boat"


@pytest.fixture
def demo(tmp_path):
    return frames.demo_store(tmp_path / "frames")


@pytest.fixture
def fresh_store(monkeypatch):
    monkeypatch.delenv("FRAMES_DIR", raising=False)
    frames._default_store = None
    yield
    frames._default_store = None


def blocked_term(lang: str, category: str) -> str:
    """First single-word term of a blocklist file, read at run time (never typed in a test)."""
    path = gate.BLOCKLIST_DIR / f"{lang}.{category}.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and " " not in line:
            return line
    raise AssertionError(f"no single-word term in {path.name}")


def fake_classifier(user: str) -> str:
    """A canned verdict for the charger pair: the rifle sentence is weapons, the rest is clean."""
    return "weapons" if "rifle" in user else "clean"


def split_body(name: str, body: dict) -> tuple[str, str]:
    """(system, user) of a provider request body."""
    if name == "anthropic":
        return body["system"][0]["text"], body["messages"][0]["content"]
    if name == "gemini":
        return body["systemInstruction"]["parts"][0]["text"], body["contents"][0]["parts"][0]["text"]
    return body["messages"][0]["content"], body["messages"][1]["content"]


def provider_handler(name: str, verdict, render="rendered", seen=None):
    """A MockTransport handler: a request whose system text is the gate prompt gets the verdict
    (a string, or a function of the user message); any other request is a render and gets `render`."""
    def handler(request):
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        system, user = split_body(name, body)
        if system == gate.SYSTEM_PROMPT:
            out = verdict(user) if callable(verdict) else verdict
        else:
            out = render
        if name == "anthropic":
            return httpx.Response(200, json={"content": [{"type": "text", "text": out}]})
        if name == "gemini":
            return httpx.Response(200, json={"candidates": [{"content": {"role": "model",
                                                                         "parts": [{"text": out}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": out}}]})
    return handler


def use_handler(monkeypatch, handler):
    monkeypatch.setattr(providers, "_client",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=30))
    monkeypatch.setenv("ANTHROPIC_MODEL", "m-anthropic")
    monkeypatch.setenv("XAI_MODEL", "m-xai")
    monkeypatch.setenv("GEMINI_MODEL", "m-gemini")
    monkeypatch.setenv("OPENAI_MODEL", "m-openai")


# The compose model lists, default first.
D1 = {
    "ANTHROPIC": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    "XAI": ["grok-4.20-0309-non-reasoning", "grok-4.20-0309-reasoning", "grok-4.3", "grok-4.7"],
    "GEMINI": ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.6-flash",
               "gemini-3.5-flash-lite"],
    "OPENAI": ["gpt-6-luna", "gpt-6.1-sol"],
}


def set_models(monkeypatch):
    """Each provider's default model and model list as in docker-compose.yml."""
    for p, ids in D1.items():
        monkeypatch.setenv(f"{p}_MODEL", ids[0])
        monkeypatch.setenv(f"{p}_MODELS", ",".join(ids))


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def hosted_off(monkeypatch):
    for name in ("HOSTED_PROVIDER", "GEMINI_API_KEY", "TRUSTED_PROXIES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(hosted, "LIMITER", hosted.Limiter())
    hosted._config = None
    yield
    hosted._config = None


@pytest.fixture(autouse=True)
def model_env_off(monkeypatch):
    """The api tests run in the compose container and would see its model lists, gate models and
    contact address; each test starts without them."""
    for p in ("ANTHROPIC", "XAI", "GEMINI", "OPENAI"):
        monkeypatch.delenv(f"{p}_MODELS", raising=False)
        monkeypatch.delenv(f"{p}_GATE_MODEL", raising=False)
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)


@pytest.fixture
def hosted_on(monkeypatch, hosted_off):
    monkeypatch.setenv("HOSTED_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", SERVER_KEY)
    monkeypatch.setenv("TRUSTED_PROXIES", TRUSTED)
    monkeypatch.setenv("GEMINI_MODEL", "m-gemini")
    return hosted.reload()


MW = (
    "\u05d4\u05d5\u05d0 \u05e9\u05dd \u05dc\u05d1 \u05e9\u05d4\u05d3\u05dc\u05ea "
    "\u05e4\u05ea\u05d5\u05d7\u05d4"
)
MW_EXPECTED = "he took notice that-the-door open"
BARK = "The bark of the oak was rough."
BARK_EXPECTED = (
    "\u05d4\u05b7 \u05e7\u05b0\u05dc\u05b4\u05d9\u05e4\u05b8\u05bc\u05d4 "
    "\u05e9\u05b6\u05c1\u05dc \u05d4\u05b7 \u05d0\u05b7\u05dc\u05bc\u05d5\u05b9\u05df "
    "\u05d4\u05b8\u05d9\u05b0\u05ea\u05b8\u05d4 "
    "\u05de\u05b0\u05d7\u05bb\u05e1\u05b0\u05e4\u05b6\u05bc\u05e1\u05b6\u05ea"
)
