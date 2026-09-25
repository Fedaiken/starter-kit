#!/usr/bin/env python3
"""Every file git lists as changed belongs to exactly one lane, or this fails.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere):
    <venv python> scripts/check_ownership.py

WHY THIS EXISTS
---------------
Design ruling R22: every lane works in the one project folder and only the desk
saves to git, so a stray edit is not refused at the moment it is made -- it is
caught HERE, at the end of the job, before anything is saved. The final check
runs this, and the desk runs it again immediately before its one save; the job
does not close while it fails.

It reads `coordination/desk_record.json` (`scripts/desk_record.py`). A file
that was already changed when the desk opened, and has not changed since, is
nobody's lane and is left out -- the owner's tree is rarely clean. Everything
under `coordination/` is the desk's own. A file another window changed WHILE
the desk was open is recorded with `desk_record.py outside <path> --why ...`
and is listed under its own heading: not a failure, and never staged.

On a pass it prints the changed files grouped by owner, which is also the list
the desk's one save stages by path.

Ported 2026-09-24 from FACOWORK by way of HAZELHURST into the Starter Kit.
This file is kit-owned: identical in every seeded project, and an improvement
made here goes back with `python scripts/kit_sync.py push
scripts/check_ownership.py`.

Exit codes:
    0 = every changed file has exactly one owner
    1 = at least one changed file has no owner, or more than one; each is named
    2 = there is no desk record to check against, or git could not be read
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import desk_record as dr  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


OUTSIDE = "(outside this desk -- NOT staged by the save)"


def findings(record: dict, changed: Sequence[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Changed files by their one owner, and a line for each file without one.

    A path the desk recorded with `desk_record.py outside` is another window's
    work: it is listed under its own heading with the reason, and is no failure.
    A lane's claim always wins -- `outside` refuses a path a lane owns.
    """
    by_owner: dict[str, list[str]] = {}
    failures: list[str] = []
    for path in changed:
        owners = dr.owners_of(record, path)
        why = dr.outside_of(record, path)
        if not owners and why is not None:
            by_owner.setdefault(OUTSIDE, []).append(f"{path}  -- {why}")
        elif len(owners) == 1:
            by_owner.setdefault(owners[0], []).append(path)
        elif not owners:
            failures.append(f"{path}: NO lane owns this file")
        else:
            failures.append(f"{path}: owned by {len(owners)} lanes: {', '.join(owners)}")
    return by_owner, failures


def main(argv: Sequence[str] = ()) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    try:
        record = dr.require_record()
        changed = dr.changed_since_baseline(record)
    except dr.DeskError as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 2
    by_owner, failures = findings(record, changed)
    for owner in sorted(by_owner):
        print(f"{owner}: {len(by_owner[owner])} changed file(s)")
        for path in by_owner[owner]:
            print(f"  {path}")
    if failures:
        sys.stdout.flush()
        print(f"FAIL - {len(failures)} changed file(s) without exactly one owner:",
              file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print("  Each is a stray edit, or a file the desk has not yet given a "
              "lane (`desk_record.py own`). Nothing is saved until this passes.",
              file=sys.stderr)
        return 1
    theirs = len(by_owner.get(OUTSIDE, []))
    print(f"PASS - {len(changed) - theirs} changed file(s), each with exactly one owner"
          + (f"; {theirs} more are another window's and are not this desk's to save"
             if theirs else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
