# turnthrift

Small Claude Code tools that cut model round trips and reply length, so a session uses less of your quota. Each tool call and each long reply costs tokens; these tools batch the first and nudge against the second. Python standard library only, no network, no model.

- `burst`: runs many read-only commands and file excerpts in parallel in one shell call.
- `hooks/turn_thrift.py`: PreToolUse hook that suggests batching after several read-only calls in a row. It never blocks.
- `hooks/brevity_stop.py`: Stop hook that asks for detail to move to a file when a reply is over a word limit.

## Install

    cp burst ~/.local/bin/ && chmod +x ~/.local/bin/burst
    mkdir -p ~/.claude/hooks && cp hooks/*.py ~/.claude/hooks/

Add to `~/.claude/settings.json`:

    {"hooks": {
      "PreToolUse": [{"matcher": "Bash|Read|Grep|Edit|Write",
        "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/turn_thrift.py"}]}],
      "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/turn_thrift.py reset"}]}],
      "Stop": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/brevity_stop.py"}]}]}}

The Edit and Write matchers and the `reset` entry are optional: they let the counter restart on a write and at each new prompt.

## Configure

- `burst`: `-t` seconds per item (default 20, env `BURST_TIMEOUT`), `-H` head lines (40, `BURST_HEAD`), `-T` tail lines (10, `BURST_TAIL`), `-j` parallel jobs (16), `-f FILE` one command per line (`#` comments; a leading `@5 ` sets that item's timeout to 5 s).
- `turn_thrift.py`: `TURNTHRIFT_N` calls before the hint (default 4, repeats every N), `TURNTHRIFT_STATE_DIR` for the per-session counter files (default `<tmp>/turnthrift`).
- `brevity_stop.py`: `BREVITY_MAX_WORDS` (default 100), `BREVITY_OFF=1` to disable. It uses a block decision, which asks for one more reply, but only once per turn. Remove the hook if a resend costs you more than the long reply.

burst does not sandbox anything; give it only commands that do not change state.

## Example

Toy task: understand a small repository (3 source files of 200 lines, one `TODO`). Measured with a throwaway git repo.

Before, 8 tool calls (8 model round trips): `ls src`, `git log --oneline`, `git status --short`, `grep -rn TODO src`, `wc -l src/*.py`, then three file excerpts.

After, 1 tool call:

    burst "ls src" "git log --oneline" "git status --short" "grep -rn TODO src" "wc -l src/*.py" \
      --files src/mod1.py:1-5 src/mod2.py:100-102 src/mod3.py:198-200

Output is grouped, in input order:

    == ls src ==
    mod1.py
    mod2.py
    mod3.py
    == grep -rn TODO src ==
    src/mod1.py:201:TODO fix
    == src/mod1.py:1-5 ==
    1	line 1
    ...

Wall time with three commands that each take one second: run one after another 3.01 s, with `burst` 1.03 s (measured). Commands that run past their timeout are killed and reported as `[timeout after 1s]`; long output keeps the head and tail with `[... 97 lines omitted ...]` in between.

The hook, fed five read-only Bash calls from one session, stayed silent on calls 1 to 3 and added `batch reads: use burst or one combined command` on call 4 (measured; call 5 was silent, and the hint repeats on call 8).

## Tests

    python3 -m pytest

## License

Apache-2.0, see `LICENSE` and `NOTICE`.
