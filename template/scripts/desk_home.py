#!/usr/bin/env python3
"""Run one desk tool under a desk HOME of its own, so desks run side by side.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/desk_home.py statements desk_record.py open-desk --desk the-desk --job "a year of statements into the records"
    <venv python> scripts/desk_home.py statements open_terminal.py --role lane --name copy-march --reason prescribed --task coordination/desks/statements/task_sheets/copy-march.md
    <venv python> scripts/desk_home.py statements desk_save.py --desk the-desk -m "a year of statements filed"

WHY THIS EXISTS
---------------
There was one desk record for the whole project, `coordination/desk_record.json`,
so a second desk could not open while any other was on file -- a side effect
of how the desk was built, never a ruling. FACOWORK found it first (2026-09-26:
"it should only ever be constrained with its own runs, not other desks' runs")
and built the homes; Travel_Helper carried them to the generic `/desk` and
into the Starter Kit the same day. A desk now lives in a home of its own,
`coordination/desks/<home>/`, and this runs a desk tool with the home variable
(`project_identity.DESK_HOME_ENV`) set -- which is all a desk tool needs to
read and write that home's record. The opener hands the same home to every
lane window it opens, so a lane runs the plain commands of
`skills/lane/SKILL.md` and reaches its own desk with nothing to remember.

A shell's environment does not survive from one of the desk's commands to the
next, so the desk runs EVERY desk command through this. One it forgets is
refused at once: `open-desk` refuses a new desk with no home, and every other
act finds no record in `coordination/` and says so. Two desks in ONE home
still refuse each other, which is the point.

Only the desk tools are run through it; anything else is refused.

This file is kit-owned: identical in every project the Starter Kit seeds, and
an improvement made here goes back with `python scripts/kit_sync.py push
scripts/desk_home.py`.

Exit codes: the tool's own; 2 = refused here (a bad home or an unknown tool).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import desk_record as dr  # noqa: E402

#: The tools a desk runs. Each reads its home from `dr.HOME_ENV`.
DESK_TOOLS = ("desk_record.py", "check_ownership.py", "desk_save.py",
              "open_terminal.py", "note_prompt.py")


def command(home: str, tool: str, args: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    """The command line and environment that run `tool` under `home`, or a
    ValueError naming what is wrong."""
    if not home.strip():
        raise ValueError("name the home: a short name for the job, e.g. nola-sweets")
    dr.home_path(home)  # raises ValueError on a name that is not a home
    if tool not in DESK_TOOLS:
        raise ValueError(f"{tool!r} is not a desk tool; this runs {list(DESK_TOOLS)}")
    env = dict(os.environ)
    env[dr.HOME_ENV] = home
    return [sys.executable, str(SCRIPTS / tool), *args], env


def main(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        print(__doc__.split("WHY THIS EXISTS")[0].strip(), file=sys.stderr)
        return 2
    try:
        cmd, env = command(argv[0], argv[1], argv[2:])
    except ValueError as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 2
    return subprocess.run(cmd, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
