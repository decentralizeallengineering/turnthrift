#!/usr/bin/env python3
"""PreToolUse hook: count consecutive read-only tool calls and suggest batching.

Reads the hook JSON on stdin. Read, Grep, Glob and read-only Bash commands
increase a per-session counter; any other tool call (Edit, Write, a Bash command
that may modify state) resets it. Once the counter reaches TURNTHRIFT_N
(default 4), and again at every multiple of it, the hook adds context asking
for one batched call. It never blocks a tool call and never fails: errors exit 0.

`turn_thrift.py reset` clears the counter; register it on UserPromptSubmit to
start each turn from zero.
State: $TURNTHRIFT_STATE_DIR (default: <tmp>/turnthrift), one small file per session.
"""
import json
import os
import re
import sys
import tempfile

MESSAGE = "batch reads: use burst or one combined command"
READ_TOOLS = {"Read", "Grep", "Glob"}
READ_COMMANDS = {
    "cat", "head", "tail", "ls", "grep", "egrep", "fgrep", "rg", "find", "wc", "stat", "file", "tree",
    "pwd", "echo", "which", "du", "df", "diff", "sort", "uniq", "cut", "awk", "nl", "burst", "readlink",
    "basename", "dirname", "realpath", "type", "env", "printenv", "date", "id", "uname", "ps",
}
READ_GIT = {"status", "log", "diff", "show", "branch", "ls-files", "rev-parse", "blame", "grep", "remote", "describe"}
WRITE_FLAGS = re.compile(r"(^|\s)(-delete|-exec|-fprint\w*|-i|--in-place)(\s|$)")


def state_dir():
    return os.environ.get("TURNTHRIFT_STATE_DIR") or os.path.join(tempfile.gettempdir(), "turnthrift")


def state_path(session_id):
    return os.path.join(state_dir(), re.sub(r"\W", "", session_id or "default") or "default")


def threshold():
    try:
        return max(1, int(os.environ.get("TURNTHRIFT_N", "4")))
    except ValueError:
        return 4


def bash_is_read_only(cmd):
    """Conservative: unknown commands, redirects to files, or write flags count as writes."""
    cmd = re.sub(r"\d*>&\d+|\d*>\s*/dev/null", "", cmd or "")
    if ">" in cmd or "`" in cmd or "$(" in cmd:
        return False
    for seg in re.split(r"\|\||&&|[|;&\n]", cmd):
        words = seg.split()
        while words and re.match(r"^\w+=", words[0]):
            words.pop(0)
        if not words:
            continue
        name = os.path.basename(words[0])
        if name == "git":
            rest = [w for w in words[1:] if not w.startswith("-")]
            if not rest or rest[0] not in READ_GIT:
                return False
        elif name == "sed":
            if not any(w == "-n" for w in words[1:]) or WRITE_FLAGS.search(seg):
                return False
        elif name not in READ_COMMANDS or WRITE_FLAGS.search(seg):
            return False
    return True


def is_read_only(tool, tool_input):
    if tool in READ_TOOLS:
        return True
    if tool == "Bash":
        return bash_is_read_only((tool_input or {}).get("command", ""))
    return False


def load_count(path):
    try:
        with open(path) as f:
            return int(json.load(f).get("count", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def save_count(path, count):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"count": count}, f)


def handle(data):
    """Update the counter for one hook payload; return the context string or None."""
    path = state_path(data.get("session_id"))
    if not is_read_only(data.get("tool_name"), data.get("tool_input")):
        save_count(path, 0)
        return None
    count = load_count(path) + 1
    save_count(path, count)
    if count % threshold() == 0:
        return MESSAGE
    return None


def main():
    try:
        data = json.load(sys.stdin)
        if len(sys.argv) > 1 and sys.argv[1] == "reset":
            save_count(state_path(data.get("session_id")), 0)
            return 0
        msg = handle(data)
        if msg:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
