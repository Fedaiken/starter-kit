#!/usr/bin/env python3
"""Refuse the Agent and Workflow tools in every window of this project.

Wired as a `PreToolUse` hook in `.claude/settings.json`; it reads the hook's
JSON payload on stdin, and exit 2 with a reason on stderr refuses the call.

WHY THIS EXISTS
---------------
`kb/desk-and-lane-philosophy.md`, rule 1: "Subagents are retired for batched
work -- invisible workers cannot be stepped into or corrected mid-task." On
2026-09-30 a window broke that rule anyway: it launched four background
subagents for a 120-note sweep, the owner asked why, and their work was thrown
away when the job was rerun as a desk ("what a waste of usage"). A rule a
window has to remember is not a control (the cardinal rule), so the owner
chose a hook (2026-09-30). It went into a second project on 2026-10-26, after
a window there launched a background agent for a two-project survey and the
owner stopped it, and from there into the Starter Kit.

Both tools are refused, not only batched uses of them: nothing on the payload
says whether one call is part of a batch, and a single lookup is done in the
window itself with Read, Grep and Glob.

This file is kit-owned; an improvement goes back with
`<venv python> scripts/kit_sync.py push scripts/agent_guard.py`.
"""
import json
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REFUSED_TOOLS = ("Agent", "Workflow")

REASON = (
    "REFUSED: subagents and workflows are retired in this project "
    "(kb/desk-and-lane-philosophy.md rule 1; the owner's ruling, 2026-09-30). "
    "Do a single lookup in this window with Read, Grep and Glob. "
    "Batched work runs as a desk with visible lane windows: tell the owner it needs "
    "/desk, or in a window whose save closed its desk, reopen it on the owner's words."
)


def verdict(payload: dict) -> str | None:
    """The refusal for this call, or None to let it run."""
    if payload.get("tool_name") in REFUSED_TOOLS:
        return REASON
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, UnicodeError):
        return 0  # an unreadable payload is not a reason to stop a window
    if not isinstance(payload, dict):
        return 0
    said = verdict(payload)
    if said is None:
        return 0
    print(said, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
