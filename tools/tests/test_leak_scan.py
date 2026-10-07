"""Leak scanner tests on synthetic trees. The terms and the id below are made up for the test."""
import os
import subprocess

import leak_scan as ls
import pytest

FID = "ab" * 32
TERMS = ["# synthetic deny list", "zqxword", "zqx.lit"]  # term#2 (word), term#3 (literal)
E_ACUTE = chr(0xE9)
ALEF = chr(0x5D0)


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Roey Bar")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "roeybarltd@" + "gmail.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Roey Bar")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "roeybarltd@" + "gmail.com")


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "root"
    deny = tmp_path / "deny"
    root.mkdir()
    deny.mkdir()
    (deny / "terms.txt").write_text("\n".join(TERMS) + "\n", encoding="utf-8")
    (deny / "frame-ids.txt").write_text(FID + "\n", encoding="utf-8")
    return root, deny


def put(root, rel, content):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))


def scan(capsys, root, deny, *extra):
    code = ls.main(["--deny-dir", str(deny), *extra, str(root)])
    lines = capsys.readouterr().out.splitlines()
    return code, lines


def findings(lines):
    return [ln for ln in lines if ln.startswith("FINDING")]


def git(repo, *args, env=None):
    full = dict(os.environ)
    full.update(env or {})
    cmd = ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args]
    subprocess.run(cmd, cwd=repo, env=full, check=True, capture_output=True)


def commit(repo, msg, files=None, env=None):
    for rel, content in (files or {}).items():
        if content is None:
            (repo / rel).unlink()
        else:
            put(repo, rel, content)
    git(repo, "add", "-A")
    git(repo, "commit", "--allow-empty", "-m", msg, env=env)


def test_clean_tree_exits_zero(capsys, tree):
    root, deny = tree
    put(root, "a.txt", "nothing to see\n")
    code, lines = scan(capsys, root, deny)
    assert code == 0 and lines == ["findings: 0"]


def test_word_term_has_boundaries(capsys, tree):
    root, deny = tree
    put(root, "a.txt", "x zqxword y\n")
    put(root, "b.txt", "nozqxwordy\n")
    code, lines = scan(capsys, root, deny)
    assert code == 1
    assert findings(lines) == ["FINDING\tterm\tfile:a.txt:1\tterm#2"]
    assert lines[-1] == "findings: 1"


def test_literal_term_is_case_insensitive_and_escaped(capsys, tree):
    root, deny = tree
    put(root, "a.txt", "see ZQX.LIT here\n")
    put(root, "b.txt", "zqxXlit is not it\n")
    _, lines = scan(capsys, root, deny)
    assert findings(lines) == ["FINDING\tterm\tfile:a.txt:1\tterm#3"]


def test_frame_id(capsys, tree):
    root, deny = tree
    put(root, "a.txt", "id " + FID + " end\n")
    put(root, "b.txt", "c" + FID + "\n")
    _, lines = scan(capsys, root, deny)
    assert findings(lines) == ["FINDING\tframe_id\tfile:a.txt:1\tid"]
    assert FID not in "\n".join(lines)


def test_non_ascii(capsys, tree):
    root, deny = tree
    put(root, "m.py", "x = '" + E_ACUTE + "'\n")
    put(root, "h.py", "x = '" + ALEF + "'\n")
    put(root, "blocklists/x.txt", E_ACUTE + "\n")
    _, lines = scan(capsys, root, deny)
    assert findings(lines) == ["FINDING\tnon_ascii\tfile:m.py:1\tU+00E9"]


def test_size_limit_and_binary(capsys, tree):
    root, deny = tree
    put(root, "big.txt", b"a" * (ls.MAX_BYTES + 1))
    put(root, "ok.txt", b"a" * ls.MAX_BYTES)
    put(root, "bin.dat", b"\0" + FID.encode("ascii"))
    _, lines = scan(capsys, root, deny)
    assert findings(lines) == ["FINDING\tsize\tfile:big.txt\tbytes"]


def test_path_term_is_redacted_in_the_working_tree(capsys, tree):
    root, deny = tree
    put(root, "api/zqxword.py", "x = 1 # zqxword\n")
    code, lines = scan(capsys, root, deny)
    out = "\n".join(lines)
    assert code == 1
    assert "FINDING\tpath_term\tfile:api/<term#2>.py\tterm#2" in lines
    assert "FINDING\tterm\tfile:api/<term#2>.py:1\tterm#2" in lines
    assert "zqxword" not in out.lower()


def test_scan_skips_generated_directories(capsys, tree):
    root, deny = tree
    put(root, "e2e/report/r.html", "zqxword\n")
    put(root, "e2e/node_modules/x/y.js", "zqxword\n")
    put(root, "api/__pycache__/m.txt", "zqxword\n")
    _, lines = scan(capsys, root, deny)
    assert lines == ["findings: 0"]


def test_deny_dir_errors_exit_two(capsys, tree, tmp_path):
    root, deny = tree
    inside = root / "deny"
    inside.mkdir()
    (inside / "terms.txt").write_text("zqxword\n", encoding="utf-8")
    assert scan(capsys, root, inside)[0] == 2
    assert scan(capsys, root, tmp_path / "missing")[0] == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert scan(capsys, root, empty)[0] == 2


def test_deny_dir_from_environment(capsys, monkeypatch, tree):
    root, deny = tree
    put(root, "a.txt", "zqxword\n")
    monkeypatch.setenv("LEAK_DENY_DIR", str(deny))
    assert ls.main([str(root)]) == 1
    assert "term#2" in capsys.readouterr().out


def test_history_commit_message_and_identity(capsys, tree):
    root, deny = tree
    git(root, "init")
    commit(root, "first clean commit", {"a.txt": "fine\n"})
    commit(root, "mentions zqxword here", {"b.txt": "fine\n"})
    commit(root, "other author", {"c.txt": "fine\n"},
           env={"GIT_AUTHOR_NAME": "someone", "GIT_AUTHOR_EMAIL": "s@example.invalid"})
    code, lines = scan(capsys, root, deny)
    kinds = sorted(ln.split("\t")[1] for ln in findings(lines))
    assert code == 1 and kinds == ["identity", "term"]
    assert all(ln.split("\t")[2].startswith("commit:") for ln in findings(lines))
    assert "zqxword" not in "\n".join(lines).lower()
    assert scan(capsys, root, deny, "--no-history")[1] == ["findings: 0"]


def test_history_deleted_blob_and_path(capsys, tree):
    root, deny = tree
    git(root, "init")
    commit(root, "add", {"old/zqxword.py": "x = 'zqxword'\n"})
    commit(root, "remove", {"old/zqxword.py": None, "keep.txt": "fine\n"})
    code, lines = scan(capsys, root, deny)
    out = "\n".join(lines)
    assert code == 1
    kinds = sorted(ln.split("\t")[1] for ln in findings(lines))
    assert kinds == ["path_term", "term"]
    assert all(ln.split("\t")[2].startswith("blob:") for ln in findings(lines))
    assert "/<term#2>.py" in out
    assert "zqxword" not in out.lower()


def test_history_sees_a_renamed_path_but_a_clean_ref_does_not(capsys, tree):
    root, deny = tree
    git(root, "init")
    commit(root, "add", {"old/zqxword.py": "x = 1\n"})
    git(root, "mv", "old/zqxword.py", "old/clean.py")
    git(root, "commit", "-m", "rename")
    git(root, "checkout", "--orphan", "clean")
    git(root, "rm", "-r", "-q", "--cached", ".")
    git(root, "add", "old/clean.py")
    git(root, "commit", "-m", "squashed")
    code, lines = scan(capsys, root, deny)
    hits = [ln for ln in findings(lines) if ln.split("\t")[1] == "path_term"]
    assert code == 1 and len(hits) == 1
    where = hits[0].split("\t")[2]
    assert where.startswith("blob:") and "<term#2>" in where
    assert "zqxword" not in where
    assert "zqxword" not in "\n".join(lines).lower()
    code, lines = scan(capsys, root, deny, "--ref", "clean")
    assert code == 0 and lines == ["findings: 0"]


def test_ref_limits_history(capsys, tree):
    root, deny = tree
    git(root, "init")
    commit(root, "clean", {"a.txt": "fine\n"})
    git(root, "checkout", "-b", "side")
    commit(root, "mentions zqxword", {"b.txt": "zqxword\n"})
    git(root, "checkout", "main")
    assert scan(capsys, root, deny, "--no-history")[1] == ["findings: 0"]
    assert scan(capsys, root, deny, "--ref", "main")[1] == ["findings: 0"]
    code, lines = scan(capsys, root, deny)
    assert code == 1 and len(findings(lines)) == 2
    code, lines = scan(capsys, root, deny, "--ref", "side")
    assert code == 1 and len(findings(lines)) == 2


def test_output_never_contains_a_term_or_an_id(capsys, tree):
    root, deny = tree
    put(root, "zqxword/zqx.lit.py", "zqxword ZQX.LIT " + FID + "\n")
    git(root, "init")
    commit(root, "zqxword " + FID, {"b.txt": "zqxword\n"})
    code, lines = scan(capsys, root, deny)
    out = "\n".join(lines).lower()
    assert code == 1
    assert "zqxword" not in out and "zqx.lit" not in out and FID not in out
