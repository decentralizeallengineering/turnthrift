#!/usr/bin/env python3
"""Stop hook: nudge once per turn when the last assistant reply is too long.

Reads the hook JSON on stdin. If the reply has more than BREVITY_MAX_WORDS words
(default 100), it prints a block decision whose reason asks for the detail to
move to a file. When the hook is already active for this turn it stays silent,
so the nudge happens at most once. Replies at or under the limit produce no
output. Errors exit 0. Set BREVITY_OFF=1 to disable.

The reply text comes from `last_assistant_message` if present, otherwise from
the last assistant entry of the transcript file.
"""
import json
import os
import sys


def max_words():
    try:
        return max(1, int(os.environ.get("BREVITY_MAX_WORDS", "100")))
    except ValueError:
        return 100


def transcript_reply(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 400_000))
            lines = f.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        msg = entry.get("message") or {}
        if entry.get("type") != "assistant" and msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        text = " ".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
        if text.strip():
            return text
    return ""


def reply_words(data):
    text = data.get("last_assistant_message") or transcript_reply(data.get("transcript_path") or "")
    return len(text.split())


def main():
    try:
        if os.environ.get("BREVITY_OFF"):
            return 0
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            return 0
        limit = max_words()
        if reply_words(data) > limit:
            print(json.dumps({"decision": "block", "reason": "reply over %d words; move detail to a file" % limit}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
