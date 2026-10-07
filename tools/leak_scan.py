"""Leak scanner: checks a working tree (and, when there is one, its git history)
against a private deny directory that is never part of the tree.

  python tools/leak_scan.py [--deny-dir DIR] [--ref REF] [--no-history] ROOT

The deny directory holds terms.txt (one term per line) and frame-ids.txt (one
64-hex id per line); it comes from --deny-dir or the environment variable
LEAK_DENY_DIR. A finding prints as FINDING<TAB>kind<TAB>where<TAB>detail. The
detail is a term number, a code point, "bytes" or "id", and a deny term inside
a path is replaced by its term number, so the output never contains a term or
an id. The last line is "findings: N"; the exit status is 1 when N > 0, 2 for
a usage problem (missing or misplaced deny directory, git failure) and 0
otherwise. Stdlib only.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
SKIP_PATHS = {"e2e/report", "e2e/test-results"}
MAX_BYTES = 1048576
CONTENT_GLOBS = [
    "api/tests/goldens/*.json",
    "api/tests/lang_samples.json",
    "api/mordecai/demo_data/*.json",
    "blocklists/*.txt",
]
OK_RANGES = ((0x0590, 0x05FF), (0xFB1D, 0xFB4F), (0x0600, 0x06FF))
IDENTITY = ("Roey Bar", "roeybarltd@" + "gmail.com")
ID_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{64}(?![0-9a-fA-F])")
WORD_RE = re.compile(r"^[A-Za-z0-9_]+$")


class UsageError(Exception):
    pass


class Deny:
    def __init__(self, deny_dir: Path):
        self.terms: list[tuple[str, re.Pattern]] = []
        self.ids: set[str] = set()
        terms = deny_dir / "terms.txt"
        if terms.is_file():
            for n, line in enumerate(terms.read_text(encoding="utf-8").splitlines(), 1):
                t = line.strip()
                if not t or t.startswith("#"):
                    continue
                body = re.escape(t)
                if WORD_RE.match(t):
                    body = r"(?<![A-Za-z0-9_])" + body + r"(?![A-Za-z0-9_])"
                self.terms.append((f"term#{n}", re.compile(body, re.IGNORECASE)))
        ids = deny_dir / "frame-ids.txt"
        if ids.is_file():
            self.ids = {x.strip().lower() for x in ids.read_text(encoding="utf-8").splitlines() if x.strip()}

    def term_ids(self, s: str) -> list[str]:
        return [tid for tid, rx in self.terms if rx.search(s)]

    def redact(self, path: str) -> str:
        """The path with every deny-term match replaced by <term#N> (leftmost, longest first)."""
        spans = sorted((m.start(), -m.end(), tid) for tid, rx in self.terms for m in rx.finditer(path))
        out, pos = [], 0
        for start, neg_end, tid in spans:
            if start < pos:
                continue
            out.append(path[pos:start])
            out.append(f"<{tid}>")
            pos = -neg_end
        out.append(path[pos:])
        return "".join(out)


class Report:
    def __init__(self):
        self.items: list[tuple[str, str, str]] = []
        self._seen: set[tuple[str, str, str]] = set()

    def add(self, kind: str, where: str, detail: str) -> None:
        key = (kind, where, detail)
        if key not in self._seen:
            self._seen.add(key)
            self.items.append(key)


def is_content(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, g) for g in CONTENT_GLOBS)


def first_odd_char(line: str) -> str | None:
    for c in line:
        o = ord(c)
        if o > 127 and not any(lo <= o <= hi for lo, hi in OK_RANGES):
            return c
    return None


def scan_text(rep: Report, deny: Deny, text: str, where, ascii_check: bool) -> None:
    """Scan text line by line; where(n) gives the location string for line n."""
    for n, line in enumerate(text.split("\n"), 1):
        for tid in deny.term_ids(line):
            rep.add("term", where(n), tid)
        for m in ID_RE.finditer(line):
            if m.group(0) in deny.ids:
                rep.add("frame_id", where(n), "id")
        if ascii_check:
            c = first_odd_char(line)
            if c is not None:
                rep.add("non_ascii", where(n), f"U+{ord(c):04X}")


def scan_file(rep: Report, deny: Deny, path: Path, rel: str) -> None:
    red = deny.redact(rel)
    for tid in deny.term_ids(rel):
        rep.add("path_term", f"file:{red}", tid)
    size = path.stat().st_size
    if size > MAX_BYTES:
        rep.add("size", f"file:{red}", "bytes")
        return
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return
    scan_text(rep, deny, data.decode("utf-8", errors="replace"), lambda n: f"file:{red}:{n}",
              not is_content(rel))


def scan_tree(rep: Report, deny: Deny, root: Path) -> None:
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and (d if rel_dir == "." else f"{rel_dir}/{d}") not in SKIP_PATHS
        )
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.is_symlink():
                continue
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            scan_file(rep, deny, p, rel)


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    cmd = ["git", "-c", "safe.directory=*", "-C", str(root), *args]
    try:
        res = subprocess.run(cmd, input=data, capture_output=True, check=False)
    except OSError as exc:
        raise UsageError(f"git unavailable: {exc.__class__.__name__}") from None
    if res.returncode != 0:
        raise UsageError("git failed: " + args[0])
    return res.stdout


def scan_commits(rep: Report, deny: Deny, root: Path, ref: str | None) -> None:
    fmt = "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x1e"
    out = git(root, "log", ref if ref else "--all", fmt).decode("utf-8", errors="replace")
    for rec in out.split("\x1e"):
        rec = rec.lstrip("\n")
        if not rec.strip():
            continue
        h, an, ae, cn, ce, body = rec.split("\x00", 5)
        where = f"commit:{h[:12]}"
        if (an, ae) != IDENTITY:
            rep.add("identity", where, "author")
        if (cn, ce) != IDENTITY:
            rep.add("identity", where, "committer")
        scan_text(rep, deny, body, lambda n, w=where: w, True)


def scan_blobs(rep: Report, deny: Deny, root: Path, ref: str | None) -> None:
    commits = git(root, "rev-list", ref if ref else "--all").decode("ascii", errors="replace").split()
    pairs: dict[tuple[str, str], None] = {}
    first_path: dict[str, str] = {}
    for commit in commits:
        for entry in git(root, "ls-tree", "-r", "-z", commit).split(b"\0"):
            meta, _, raw_path = entry.partition(b"\t")
            fields = meta.split()
            if len(fields) != 3 or fields[1] != b"blob":
                continue
            sha, path = fields[2].decode("ascii"), raw_path.decode("utf-8", errors="replace")
            pairs.setdefault((sha, path))
            first_path.setdefault(sha, path)
    for sha, path in pairs:
        where = f"blob:{sha[:12]}:{deny.redact(path)}"
        for tid in deny.term_ids(path):
            rep.add("path_term", where, tid)
    if not first_path:
        return
    raw = git(root, "cat-file", "--batch", data=("\n".join(first_path) + "\n").encode("ascii"))
    pos = 0
    while pos < len(raw):
        nl = raw.index(b"\n", pos)
        header = raw[pos:nl].split()
        if len(header) != 3:
            pos = nl + 1
            continue
        sha, kind, size = header[0].decode("ascii"), header[1], int(header[2])
        body = raw[nl + 1:nl + 1 + size]
        pos = nl + 1 + size + 1
        if kind != b"blob":
            continue
        path = first_path.get(sha, "")
        where = f"blob:{sha[:12]}:{deny.redact(path)}"
        if size > MAX_BYTES:
            rep.add("size", where, "bytes")
            continue
        if b"\0" in body[:8192]:
            continue
        scan_text(rep, deny, body.decode("utf-8", errors="replace"), lambda n, w=where: w,
                  not is_content(path))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="leak_scan.py")
    ap.add_argument("--deny-dir")
    ap.add_argument("--ref")
    ap.add_argument("--no-history", action="store_true")
    ap.add_argument("root")
    args = ap.parse_args(argv)
    try:
        deny_arg = args.deny_dir or os.environ.get("LEAK_DENY_DIR")
        root = Path(args.root).resolve()
        if not deny_arg or not root.is_dir():
            raise UsageError("usage: a root directory and a deny directory are required")
        deny_dir = Path(deny_arg).resolve()
        if not deny_dir.is_dir() or not ((deny_dir / "terms.txt").is_file()
                                         or (deny_dir / "frame-ids.txt").is_file()):
            raise UsageError("the deny directory is missing or has no terms.txt / frame-ids.txt")
        if deny_dir == root or root in deny_dir.parents:
            raise UsageError("the deny directory must not be inside the scanned root")
        deny = Deny(deny_dir)
        rep = Report()
        scan_tree(rep, deny, root)
        if (root / ".git").exists() and not args.no_history:
            scan_commits(rep, deny, root, args.ref)
            scan_blobs(rep, deny, root, args.ref)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for kind, where, detail in rep.items:
        print(f"FINDING\t{kind}\t{where}\t{detail}")
    print(f"findings: {len(rep.items)}")
    return 1 if rep.items else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
