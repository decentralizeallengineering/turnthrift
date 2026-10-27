import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENUM = os.path.join(ROOT, "enum")


def enum(repo, *args):
    r = subprocess.run([sys.executable, ENUM, *args], cwd=repo, capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "pkg" / "billing.py").write_text(
        "TAX = 2\n\n\nclass Ledger:\n    pass\n\n\ndef total_due(items):\n    s = 0\n    for i in items:\n        s += i\n    return s * TAX\n\n\ndef other():\n    return 1\n")
    (tmp_path / "pkg" / "__main__.py").write_text("from pkg.billing import total_due\nprint(total_due([1, 2]))\n")
    (tmp_path / "tests" / "test_billing.py").write_text("from pkg.billing import total_due\n\n\ndef test_total():\n    assert total_due([1]) == 2\n")
    (tmp_path / "node_modules" / "junk.js").write_text("total_due total_due\n")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\0\0 total_due")
    (tmp_path / "Makefile").write_text("build:\n\techo ann\ntest:\n\techo ok\n")
    (tmp_path / "package.json").write_text('{"scripts": {"start": "node app.js"}}')
    env = dict(os.environ, GIT_AUTHOR_NAME="Ann Example", GIT_AUTHOR_EMAIL="ann@example.invalid",
               GIT_COMMITTER_NAME="Ann Example", GIT_COMMITTER_EMAIL="ann@example.invalid")
    for cmd in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "-m", "Add billing"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, env=env, check=True, capture_output=True, timeout=20)
    return str(tmp_path)


def test_map_sections(repo):
    code, out = enum(repo, "map")
    assert code == 0
    for part in ("pkg/ (", "10 largest files", ".py", "Add billing", "pkg/__main__.py", "start: node app.js", "targets: build test"):
        assert part in out
    assert "node_modules" not in out
    assert "narrow with --path or --max-lines" in out


def test_find_ranks_definitions_and_importers(repo):
    code, out = enum(repo, "find", "total_due", "Ledger")
    assert code == 0
    defs = out.split("== importers")[0]
    assert "pkg/billing.py:8: def total_due(items):" in defs
    assert "pkg/billing.py:4: class Ledger:" in defs
    importers = out.split("== importers of defining modules ==")[1].split("== hits")[0]
    assert "pkg/__main__.py:1" in importers and "tests/test_billing.py:1" in importers
    assert "junk.js" not in out and "logo.png" not in out
    assert "narrow with --path or --max-lines" in out


def test_around_body_callers_tests(repo):
    code, out = enum(repo, "around", "pkg/billing.py:10")
    assert code == 0
    assert "total_due pkg/billing.py:8-12" in out
    assert "return s * TAX" in out and "def other" not in out
    callers = out.split("== callers of total_due ==")[1].split("== tests")[0]
    assert "pkg/__main__.py:2" in callers
    tests = out.split("== tests mentioning total_due ==")[1]
    assert "tests/test_billing.py:5" in tests


def test_max_lines_caps_every_mode(repo):
    for args in (("map",), ("find", "total_due", "TAX"), ("around", "pkg/billing.py:10")):
        code, out = enum(repo, *args, "--max-lines", "6")
        assert code == 0
        lines = out.splitlines()
        assert len(lines) <= 6
        assert lines[-1] == "hint: narrow with --path or --max-lines"
