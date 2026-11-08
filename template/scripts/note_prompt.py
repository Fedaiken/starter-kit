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

AUTO MODE (2026-11-07). The log also holds one row each time a desk's or a
lane's window goes into auto mode and one when it leaves (`MODE_EVENT`),
written by `scripts/lane_guard.py`, which refuses such a window's tool calls
while it is there. A refused window is not "waiting", so the stall lookup
never finds it; `auto_mode_windows` does, and every desk act's banner names
the tab (`open_terminal.stalled_lines`) until the window's next call shows
the mode back. The owner, 2026-11-07: "I think the new launcher's messing up
and opening lanes with auto mode on instead of accept edits on".

Registered in the tracked `.claude/settings.json`. The log,
`coordination/prompts.jsonl`, is gitignored: machine-local stall telemetry.

Ported 2026-09-24 from FACOWORK by way of HAZELHURST into the Starter Kit.
This file is kit-owned: identical in every seeded project, and an improvement
made here goes back with `<venv python> scripts/kit_sync.py push
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


# --- a desk or lane window in auto mode (2026-11-07) ---------------------------

#: The `event` of the rows the lane guard writes here when a desk's or a lane's
#: window enters auto mode or leaves it. They are not pop-ups: the report and
#: the stall lookup skip them.
MODE_EVENT = "PermissionMode"
#: The `permission_mode` value Claude Code hands a hook in auto mode.
AUTO_MODE = "auto"


def mode_rows(log: Path) -> list[dict]:
    """The mode rows of both generations of the log, oldest first. Only the
    lines naming MODE_EVENT are parsed: the guard asks on every tool call."""
    rows: list[dict] = []
    for path in (log.with_suffix(".jsonl.1"), log):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            if MODE_EVENT not in line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, UnicodeError):
                continue
            if isinstance(row, dict) and row.get("event") == MODE_EVENT:
                rows.append(row)
    return rows


def in_auto_mode(log: Path | None = None) -> dict[str, dict]:
    """Session id -> the row that put it in auto mode, for every window whose
    last mode row says it went into auto mode."""
    found: dict[str, dict] = {}
    for row in mode_rows(LOG if log is None else log):
        session = str(row.get("session"))
        if row.get("mode") == AUTO_MODE:
            found[session] = row
        else:
            found.pop(session, None)
    return found


def note_mode(payload: dict, window: str | None, *, log: Path | None = None,
              now: datetime | None = None) -> bool:
    """Record a desk's or a lane's switch into auto mode, and its switch back:
    one row each way, however many tool calls come between. The lane guard
    calls it on every tool call it is handed in such a window; the mode back
    is seen at the window's next call. True when it wrote a row."""
    log = LOG if log is None else log
    session = payload.get("session_id")
    mode = payload.get("permission_mode")
    if not (isinstance(session, str) and session and isinstance(mode, str) and mode):
        return False
    auto = mode == AUTO_MODE
    if (session in in_auto_mode(log)) == auto:
        return False
    now = datetime.now().astimezone() if now is None else now
    append(log, {
        "when": now.isoformat(timespec="seconds"),
        "session": session,
        "event": MODE_EVENT,
        "tool": "permission mode",
        "mode": mode,
        "window": window or "?",
        "what": f"{window or '?'} {'went into auto mode' if auto else 'left auto mode for ' + mode}",
    })
    return True


def auto_mode_windows(live_here: Sequence[dict], *, log: Path | None = None) -> list[str]:
    """The names of the live windows on record as in auto mode, sorted -- for
    the banner every desk act prints (`open_terminal.stalled_lines`)."""
    found = in_auto_mode(log)
    return sorted(str(row.get("name")) for row in live_here
                  if str(row.get("sessionId")) in found)


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
    rows = [row for row in read_log(log) if row.get("event") != MODE_EVENT]
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
