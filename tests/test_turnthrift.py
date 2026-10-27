import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BURST = os.path.join(ROOT, "burst")
TURN = os.path.join(ROOT, "hooks", "turn_thrift.py")
BREVITY = os.path.join(ROOT, "hooks", "brevity_stop.py")


def run(script, args=(), stdin=None, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, script, *args], input=stdin, capture_output=True, text=True, env=e, timeout=60)


def hook(tool, tool_input, tmp_path, session="ann-example", **env):
    payload = json.dumps({"session_id": session, "tool_name": tool, "tool_input": tool_input})
    return run(TURN, stdin=payload, env=dict(TURNTHRIFT_STATE_DIR=str(tmp_path), **env))


def test_burst_runs_in_parallel_with_headers():
    start = time.time()
    r = run(BURST, ["sleep 1; echo one", "sleep 1; echo two", "sleep 1; echo three"])
    assert time.time() - start < 2.5
    assert r.stdout.index("== sleep 1; echo one ==") < r.stdout.index("== sleep 1; echo two ==")
    assert "three" in r.stdout


def test_burst_caps_and_timeout():
    r = run(BURST, ["-H", "2", "-T", "1", "-t", "1", "seq 1 100", "sleep 30; echo AFTERSLEEP"])
    assert "1\n2\n[... 97 lines omitted ...]\n100" in r.stdout
    assert "[timeout after 1s]" in r.stdout
    assert "\nAFTERSLEEP" not in r.stdout


def test_burst_file_excerpts(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("\n".join("line%d" % i for i in range(1, 11)))
    r = run(BURST, ["--files", "%s:3-4,9-9" % f])
    assert "3\tline3\n4\tline4\n9\tline9" in r.stdout
    assert "line5" not in r.stdout


def test_hook_counts_then_adds_context_and_never_blocks(tmp_path):
    outs = [hook("Read", {"file_path": "x"}, tmp_path) for _ in range(4)]
    assert all(o.returncode == 0 for o in outs)
    assert [bool(o.stdout) for o in outs] == [False, False, False, True]
    ctx = json.loads(outs[3].stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx == "batch reads: use burst or one combined command"
    assert "decision" not in outs[3].stdout


def test_hook_resets_on_write(tmp_path):
    for _ in range(3):
        hook("Grep", {"pattern": "x"}, tmp_path)
    hook("Edit", {"file_path": "x"}, tmp_path)
    assert not hook("Bash", {"command": "ls -la"}, tmp_path).stdout
    for _ in range(2):
        hook("Bash", {"command": "cat a | head -5"}, tmp_path)
    assert hook("Bash", {"command": "git log --oneline"}, tmp_path).stdout
    hook("Bash", {"command": "echo hi > out.txt"}, tmp_path)
    assert not hook("Read", {"file_path": "x"}, tmp_path).stdout


def test_brevity_silent_under_limit_and_nudges_once():
    short = json.dumps({"last_assistant_message": "word " * 100})
    assert run(BREVITY, stdin=short).stdout == ""
    long = json.dumps({"last_assistant_message": "word " * 101})
    out = run(BREVITY, stdin=long)
    assert json.loads(out.stdout)["reason"] == "reply over 100 words; move detail to a file"
    again = json.dumps({"last_assistant_message": "word " * 101, "stop_hook_active": True})
    assert run(BREVITY, stdin=again).stdout == ""
    custom = run(BREVITY, stdin=short, env={"BREVITY_MAX_WORDS": "50"})
    assert "over 50 words" in custom.stdout
