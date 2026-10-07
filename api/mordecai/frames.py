"""Frame store. Frames are nested JSON documents; a word is a leaf frame, a phrase
references child frames by canonical_key. canonical_key = sha256 over the
NFC-normalized semantic identity {kind, head, identity-class attrs, parts,
required slots}; surfaces, feats and counters are not hashed. A controlled
vocabulary (VOCAB_PATH) is enforced at canonicalize time. The api opens the
store read-only; documents dropped in inbox/ are ingested by ingest_inbox().
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import text

log = logging.getLogger(__name__)

_VOCAB_PATH = Path(
    os.environ.get("VOCAB_PATH") or Path(__file__).resolve().parent / "demo_data" / "demo_vocab.json"
)


class FrameError(ValueError):
    """Frame violates the schema or the controlled vocabulary."""


_vocab: dict | None = None


def vocab() -> dict:
    global _vocab
    if _vocab is None:
        _vocab = json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))
    return _vocab


# normalization

_CARD_ALIASES = {"a": "1", "an": "1", "one": "1", "single": "1"}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _norm_lemma(s: str) -> str:
    return _nfc(str(s)).strip().lower()


def _norm_card(c) -> str:
    s = str(c).strip().lower()
    s = _CARD_ALIASES.get(s, s)
    if s.isdigit():
        return str(int(s))  # "01" -> "1"
    if s not in vocab()["cards"]:
        raise FrameError(f"unknown card {c!r} (allowed: ints or {vocab()['cards']})")
    return s


def _norm_attr_value(v) -> str:
    # Conservative on purpose: NFC + trim + ascii-lowercase. Near-synonyms
    # are not folded (cyan stays cyan); folding them causes attribute drift.
    return _norm_lemma(v)


# canonicalization (pure, no IO)

@dataclass
class Canon:
    """Result of canonicalizing one frame (and, transitively, its parts)."""
    key: str
    doc: dict                      # storable doc - parts hold child refs
    children: list["Canon"] = field(default_factory=list)

    def walk(self):
        """Yield children depth-first, then self."""
        for c in self.children:
            yield from c.walk()
        yield self


def canonicalize(frame: dict) -> Canon:
    """Validate against the controlled vocab, normalize, and compute the
    canonical key. Accepts inline-nested children under parts[].frame;
    returns a Canon whose doc references children by canonical_key.

    Raises FrameError on any vocabulary violation - the store must not
    fragment on invented relation/attr names.
    """
    v = vocab()
    if not isinstance(frame, dict):
        raise FrameError("frame must be a dict")

    kind = frame.get("kind")
    if kind not in v["kinds"]:
        raise FrameError(f"unknown kind {kind!r} (allowed: {v['kinds']})")

    head = frame.get("head") or {}
    lemma = head.get("lemma")
    if not lemma:
        raise FrameError("head.lemma is required")
    head_c = {"lemma": _norm_lemma(lemma), "pos": _norm_lemma(head.get("pos") or "")}

    attrs_in = frame.get("attrs") or {}
    attrs_c = {}
    for k, val in attrs_in.items():
        if k not in v["attrs"]:
            raise FrameError(f"unknown attr key {k!r} (allowed: {v['attrs']})")
        attrs_c[k] = _norm_attr_value(val)

    children: list[Canon] = []
    parts_c = []
    for p in frame.get("parts") or []:
        rel = p.get("rel")
        if rel not in v["rels"]:
            raise FrameError(f"unknown rel {rel!r} (allowed: {v['rels']})")
        card = _norm_card(p.get("card", "1"))
        if "frame" in p:
            child = canonicalize(p["frame"])
            children.append(child)
            child_key = child.key
        elif "child" in p:
            child_key = str(p["child"])
        else:
            raise FrameError("part needs an inline 'frame' or a 'child' key ref")
        parts_c.append({"rel": rel, "card": card, "child": child_key})
    parts_c.sort(key=lambda x: (x["rel"], x["child"]))

    slots_c = []
    for s in frame.get("slots") or []:
        role = s.get("role")
        if role not in v["slot_roles"]:
            raise FrameError(f"unknown slot role {role!r} (allowed: {v['slot_roles']})")
        slots_c.append({
            "role": role,
            "type": _norm_lemma(s.get("type") or ""),
            "required": bool(s.get("required", False)),
        })
    slots_c.sort(key=lambda x: x["role"])

    # Identity = semantics only. Surfaces/feats/status/uses accrue to
    # one identity and must not split it. Within attrs, only IDENTITY-class
    # attrs (truth-conditional) fork the key; SURFACE-class attrs (e.g. voice =
    # active/passive packaging) ride on the doc for render but never split
    # identity. Unknown attrs default to identity (fail-safe).
    _aclass = v.get("attr_class", {})
    id_attrs = {k: val for k, val in attrs_c.items()
                if _aclass.get(k, "identity") == "identity"}
    identity = {
        "kind": kind,
        "head": head_c,
        "attrs": id_attrs,
        "parts": parts_c,
        "slots": [s for s in slots_c if s["required"]],
    }
    key = hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    doc = {
        "canonical_key": key,
        "kind": kind,
        "head": head_c,
        "attrs": attrs_c,
        "parts": parts_c,
        "slots": slots_c,
        "surface": _norm_surfaces(frame.get("surface") or {}),
        "feats": frame.get("feats") or {},        # grammatical metadata, unhashed
        "gloss": _norm_gloss(frame.get("gloss")),  # definitions per lang, unhashed
        "status": frame.get("status", "auto"),
        "source": frame.get("source", "manual"),
        "uses": int(frame.get("uses", 0)),
        "created_at": int(frame.get("created_at") or time.time()),
    }
    if doc["status"] not in v["frame_status"]:
        raise FrameError(f"unknown status {doc['status']!r}")
    return Canon(key=key, doc=doc, children=children)


def _norm_gloss(gloss) -> dict:
    """Definitions per language: {"en": [str, ...], "he": [...]}. Deduped,
    order-preserving, unhashed."""
    if not isinstance(gloss, dict):
        return {}
    out = {}
    for lang, defs in gloss.items():
        if isinstance(defs, str):
            defs = [defs]
        seen, clean = set(), []
        for d in defs or []:
            d = _nfc(str(d)).strip()
            if d and d not in seen:
                seen.add(d)
                clean.append(d)
        if clean:
            out[lang] = clean
    return out


def _norm_surfaces(surface: dict) -> dict:
    v = vocab()
    out = {}
    for lang, s in surface.items():
        if isinstance(s, str):
            s = {"text": s}
        status = s.get("status", "auto")
        if status not in v["surface_status"]:
            raise FrameError(f"unknown surface status {status!r}")
        entry = {"text": _nfc(s["text"]), "status": status}
        for extra in ("bare", "niqqud", "verified_by"):
            if s.get(extra):
                entry[extra] = _nfc(str(s[extra]))
        if "bare" not in entry:
            entry["bare"] = text.bare(lang, entry["text"])
        alts = sorted(
            {text.bare(lang, a) for a in (s.get("alt") or []) if a} - {text.bare(lang, entry["bare"])}
        )
        if alts:
            entry["alt"] = alts
        ph = s.get("phon")                       # pronunciation, additive (not in identity)
        if isinstance(ph, dict):
            entry["phon"] = {k: ph[k] for k in ("ipa", "roman", "src", "status")
                             if ph.get(k)}
        out[lang] = entry
    return out


# the store

_STATUS_RANK = {"source": 0, "auto": 0, "verified": 1, "locked": 2}

DEMO_FRAMES_PATH = Path(__file__).resolve().parent / "demo_data" / "demo_frames.json"


class FrameStore:
    def __init__(self, root: Path | str, *, readonly: bool = False):
        self.root = Path(root)
        self.readonly = readonly
        self.inbox = self.root / "inbox"
        self.rejected = self.inbox / "rejected"
        if not readonly:
            self.root.mkdir(parents=True, exist_ok=True)
            self.inbox.mkdir(parents=True, exist_ok=True)
        # in-memory indexes - rebuilt from the docs, never authoritative
        self._path: dict[str, Path] = {}
        self._by_head: dict[str, set[str]] = defaultdict(set)
        self._by_surface: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.build_index()

    # index
    def build_index(self) -> dict:
        t0 = time.perf_counter()
        self._path.clear()
        self._by_head.clear()
        self._by_surface.clear()
        n = 0
        if not self.root.is_dir():
            return {"docs": 0, "seconds": 0.0}
        for shard in self.root.iterdir():
            if not shard.is_dir() or shard.name == "inbox":
                continue
            for f in shard.iterdir():
                if f.suffix != ".json":
                    continue
                try:
                    doc = json.loads(f.read_text(encoding="utf-8"))
                    self._index_doc(doc, f)
                    n += 1
                except Exception as e:
                    log.warning("frames: unreadable doc %s: %s", f, e)
        elapsed = time.perf_counter() - t0
        log.info("frames: indexed %d docs in %.2fs", n, elapsed)
        return {"docs": n, "seconds": round(elapsed, 3)}

    def _index_doc(self, doc: dict, path: Path) -> None:
        key = doc["canonical_key"]
        self._path[key] = path
        self._by_head[doc["head"]["lemma"]].add(key)
        for lang, surf in doc.get("surface", {}).items():
            forms = [text.bare(lang, surf.get("bare") or surf["text"])]
            forms += [text.bare(lang, a) for a in surf.get("alt") or []]
            for form in forms:
                self._by_surface[(lang, form)].add(key)

    # io
    def _doc_path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def _write(self, doc: dict, *, fsync: bool = True) -> Path:
        path = self._doc_path(doc["canonical_key"])
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=1)
                fh.flush()
                if fsync:
                    os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        self._index_doc(doc, path)
        return path

    # public api
    def put(self, frame: dict, *, fsync: bool = True) -> str:
        """Canonicalize + persist a frame (and its inline children,
        depth-first). Existing docs merge rather than clobber: surfaces
        fill missing languages; an existing surface is only replaced by
        a strictly higher-status one; locked frames keep their status.
        Returns the canonical_key."""
        if self.readonly:
            raise FrameError("store is read-only")
        canon = canonicalize(frame)
        for c in canon.walk():
            existing = self.get(c.key)
            if existing is None:
                self._write(c.doc, fsync=fsync)
            else:
                self._write(self._merge(existing, c.doc), fsync=fsync)
        return canon.key

    @staticmethod
    def _merge(old: dict, new: dict) -> dict:
        out = dict(old)
        for lang, s in new.get("surface", {}).items():
            cur = out.setdefault("surface", {}).get(lang)
            if cur is None or _STATUS_RANK[s["status"]] > _STATUS_RANK[cur["status"]]:
                out["surface"][lang] = s
            elif not cur.get("phon") and s.get("phon"):
                cur["phon"] = s["phon"]          # backfill pronunciation onto the kept surface
        for k, val in new.get("feats", {}).items():
            out.setdefault("feats", {}).setdefault(k, val)
        if new.get("gloss"):                      # union definitions across sources
            g = out.setdefault("gloss", {})
            for lang, defs in new["gloss"].items():
                merged = list(g.get(lang, []))
                for d in defs:
                    if d not in merged:
                        merged.append(d)
                g[lang] = merged
        if _STATUS_RANK.get(new.get("status"), 0) > _STATUS_RANK.get(out.get("status"), 0):
            out["status"] = new["status"]
        return out

    def get(self, key: str, *, resolve: int = 0) -> dict | None:
        path = self._path.get(key)
        if path is None:
            return None
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if resolve > 0:
            doc = dict(doc)
            doc["parts"] = [
                {**p, "frame": self.get(p["child"], resolve=resolve - 1) or p["child"]}
                for p in doc.get("parts", [])
            ]
        return doc

    def count(self) -> int:
        return len(self._path)

    def stats(self) -> dict:
        return {"docs": len(self._path), "heads": len(self._by_head),
                "surfaces": len(self._by_surface)}

    def lookup_by_head(self, lemma: str) -> list[str]:
        return sorted(self._by_head.get(_norm_lemma(lemma), ()))

    def lookup_by_surface(self, lang: str, s: str) -> list[str]:
        return sorted(self._by_surface.get((lang, text.bare(lang, s).strip()), ()))

    # inbox
    def ingest_inbox(self) -> dict:
        """Fold the documents dropped in inbox/ into the store. Success ->
        file removed; failure -> moved to inbox/rejected/ + .err note."""
        if self.readonly:
            raise FrameError("store is read-only")
        ok = bad = 0
        for f in sorted(self.inbox.glob("*.json")):
            try:
                self.put(json.loads(f.read_text(encoding="utf-8")))
                f.unlink()
                ok += 1
            except Exception as e:
                self.rejected.mkdir(parents=True, exist_ok=True)
                dest = self.rejected / f.name
                f.replace(dest)
                dest.with_suffix(".err").write_text(str(e), encoding="utf-8")
                bad += 1
        return {"ingested": ok, "rejected": bad}


_default_store = None


def demo_frames() -> list[dict]:
    """The hand-made demo frames shipped with the toolkit."""
    return json.loads(DEMO_FRAMES_PATH.read_text(encoding="utf-8"))["frames"]


def demo_store(root: Path | str | None = None) -> FrameStore:
    """A writable store filled with the demo frames (a temp dir by default)."""
    st = FrameStore(root if root is not None else tempfile.mkdtemp(prefix="mordecai-demo-"))
    for fr in demo_frames():
        st.put(fr, fsync=False)
    return st


def demo_keys() -> list[str]:
    return sorted({c.key for fr in demo_frames() for c in canonicalize(fr).walk()})


def store() -> FrameStore:
    """Lazy process-wide frame store: FRAMES_DIR opened read-only when set,
    otherwise the demo store."""
    global _default_store
    if _default_store is None:
        d = os.environ.get("FRAMES_DIR")
        _default_store = FrameStore(d, readonly=True) if d else demo_store()
    return _default_store


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["demo-keys"]:
        print("\n".join(demo_keys()))
    else:
        print("usage: python -m mordecai.frames demo-keys")
        sys.exit(2)
