#!/usr/bin/env python3
"""Record every permission pop-up a window in this project stops at.

Usage (`<venv python>` is `.venv/Scripts/python.exe` on Windows and
`.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/note_prompt.py            # the hook itself; reads stdin
    <venv python> scripts/note_prompt.py --report   # what has stalled, by window name

WHY THIS EXISTS
---------------
Reconciliation build, slice 2. A window stopped at a permission pop-up looks
exactly like a window thinking, and the stalled session cannot report it -- a
fast allow-click and a silent pass are the same event from inside. The
`PermissionRequest` hook fires only when a tool call needs a decision FROM THE
USER (a call already covered by an allow rule never reaches it), so a line in
this log is not "a tool ran": it is a window that stopped and waited for the
owner. The desk reads `--report` to see a stalled lane and tell the owner.

Adapted from Fantasy Football's `scripts/note_prompt.py`, where it has run
since 2026-08-24. Simpler here: every window shares the one project folder
(R22), so there is no main-tree lookup. For the same reason the folder cannot
say WHICH window stalled -- the hook is handed a session id, and `--report`
turns ids into window names by asking the CLI what is live.

THREE RULES THE HOOK PATH CANNOT BREAK, because a hook that misbehaves breaks
the session it was added to defend:

1. NOTHING ON STDOUT. A `PermissionRequest` hook's stdout is parsed for
   decision fields; a stray line could allow or deny a call nobody ruled on.
2. IT ALWAYS EXITS 0. A non-zero exit raises a second notice in a window
   already holding a pop-up. The worst this script may do is miss a line.
3. IT NEVER PROMPTS. A hook is a subprocess, not a tool call.

Registered in the tracked `.claude/settings.json`. The log,
`coordination/prompts.jsonl`, is gitignored: machine-local stall telemetry.

Ported 2026-09-24 from FACOWORK by way of HAZELHURST into the Starter Kit.
This file is kit-owned: identical in every seeded project, and an improvement
made here goes back with `python scripts/kit_sync.py push
scripts/note_prompt.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "coordination" / "prompts.jsonl"

#: Rolled over past this, keeping one generation. A stall is rare by
#: construction, but a window opened in the wrong mode could fire steadily.
LOG_BYTE_CAP = 200_000

#: The tool-input keys worth one line, in the order looked for: WHAT the window
#: stopped on is a path outside the project, a shell command or a fetch.
INPUT_KEYS = ("command", "file_path", "path", "url", "pattern", "notebook_path")
VALUE_CHARS = 220


def one_line(tool_input: object) -> str:
    if isinstance(tool_input, dict):
        for key in INPUT_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                return value[:VALUE_CHARS]
        try:
            return json.dumps(tool_input)[:VALUE_CHARS]
        except (TypeError, ValueError):
            return "?"
    return str(tool_input)[:VALUE_CHARS]


def entry(payload: dict, *, now: datetime) -> dict:
    """One log line. `mode` is carried because it decides whether anybody is
    actually blocked: under `auto` the decision is made without a human."""
    return {
        "when": now.isoformat(timespec="seconds"),
        "session": str(payload.get("session_id") or "?"),
        "event": str(payload.get("hook_event_name") or "?"),
        "tool": str(payload.get("tool_name") or "?"),
        "mode": str(payload.get("permission_mode") or "?"),
        "what": one_line(payload.get("tool_input")),
    }


def append(log: Path, record: dict) -> None:
    """One line, one open, one write -- two windows stalling at once interleave
    whole lines rather than halves of two."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        if log.exists() and log.stat().st_size > LOG_BYTE_CAP:
            os.replace(log, log.with_suffix(".jsonl.1"))
        with log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        print(f"note_prompt: could not write {log}: {exc}", file=sys.stderr)


def read_log(log: Path) -> list[dict]:
    """Every entry, skipping any line that is not one: a report that raised on
    a half-written row would be unreadable exactly when the room was busiest."""
    try:
        text = log.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, UnicodeError):
            continue
        if isinstance(row, dict):
            found.append(row)
    return found


def session_names() -> dict[str, str]:
    """Session id -> window name, for what is live now. Best effort: a stalled
    lane is still live, which is the case this report exists for."""
    try:
        proc = subprocess.run(["claude", "agents", "--json"], capture_output=True,
                              check=False, timeout=60)
        rows = json.loads(proc.stdout.decode("utf-8", "replace") or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
    return {str(row.get("sessionId")): str(row.get("name"))
            for row in rows if isinstance(row, dict)}


def report(log: Path, names: dict[str, str]) -> int:
    rows = read_log(log)
    if not rows:
        print(f"no permission pop-ups recorded in {log}")
        return 0
    print(f"{len(rows)} permission pop-up(s) recorded in {log}, oldest first:")
    for row in rows:
        session = str(row.get("session", "?"))
        who = names.get(session, f"(ended) {session[:8]}")
        print(f"  {row.get('when', '?')}  {who:<22} {row.get('tool', '?')} "
              f"[{row.get('mode', '?')}]  {row.get('what', '?')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true",
                        help="print the pop-ups this project's windows have "
                             "stopped at, instead of recording one from stdin")
    return parser


def main(argv: Sequence[str] = ()) -> int:
    args = build_parser().parse_args(argv)
    if args.report:
        return report(LOG, session_names())

    # THE HOOK PATH, and everything in it is swallowed on purpose (rule 2).
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
        append(LOG, entry(payload, now=datetime.now().astimezone()))
    except Exception as exc:                       # noqa: BLE001 -- rule 2
        print(f"note_prompt: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
