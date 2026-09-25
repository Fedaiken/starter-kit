#!/usr/bin/env python3
"""The desk's one save, as one act: ownership check, close the desk, commit by path, push.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere):
    <venv python> scripts/desk_save.py --desk <you> -m "<what the job did>"
    <venv python> scripts/desk_save.py --desk <you> -m "..." --dry-run

WHY THIS EXISTS
---------------
The owner runs desks beside other windows, and git has ONE index per folder. A
save made as `git add <paths>` and then `git commit` leaves a gap between the
two in which another window's commit takes everything the desk had staged. It
happened in FACOWORK: the desk of build step 4d staged 57 files, the owner's
recap window committed between the two commands, and the whole step landed
under a recap message (commit 04d34fd5). The same gap runs the other way --
another window's `git add` rides out in the desk's commit.

So the save never uses the shared index as a waiting room. It commits BY PATH
(`git commit -- <paths>`), which takes exactly those paths' content from the
working tree and leaves whatever anyone else has staged where it was. A new file
is made known to git first with `git add -N`, which stages no content.

It is also the four steps of the desk skill's Step 7 that used to be four things
to remember, in the only order that works:

  1. the ownership check -- every changed file has exactly one owner. A failure
     stops here: nothing is closed, nothing is saved, each stray is named;
     then this project's document gate, `scripts/check_docs.py` (added when
     the desk was ported from FACOWORK to HAZELHURST, 2026-09-24): a lane's
     new document with no budget row, or one over its ceiling, stops the save
     the same way;
  2. `desk_record.py close-desk` -- the record, sheets and done files move under
     `coordination/closed/<stamp>/`;
  3. one commit, by path, of: every changed file a lane or the desk owns, plus
     everything changed under `coordination/`. A path recorded as another
     window's work (`desk_record.py outside`) is never in it;
  4. `git push origin main`.

This file is kit-owned: identical in every project the Starter Kit seeds, and
an improvement made here goes back with `python scripts/kit_sync.py push
scripts/desk_save.py`.

Exit codes:
    0 = saved and pushed (or, with --dry-run, the list was printed)
    1 = refused: a changed file without exactly one owner, a lane still open,
        or the document gate failing
    2 = no desk record, not the desk, or git could not be read
    3 = the commit was made and the push FAILED -- say so to the owner in that turn
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_ownership as co  # noqa: E402
import desk_record as dr  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def git(repo: Path, *args: str, paths: Sequence[str] | None = None) -> subprocess.CompletedProcess:
    """One git command. Paths go in on stdin, NUL-separated: a tracker's save can
    name hundreds of files, and a command line has a ceiling on every machine
    (about 32,000 characters on Windows)."""
    cmd = ["git", *args]
    data = None
    if paths is not None:
        cmd += ["--pathspec-from-file=-", "--pathspec-file-nul"]
        data = "\0".join(paths).encode("utf-8")
    return subprocess.run(cmd, cwd=str(repo), input=data, capture_output=True, check=False)


def said(proc: subprocess.CompletedProcess) -> str:
    return (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()


def untracked(repo: Path) -> set[str]:
    proc = git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    if proc.returncode != 0:
        raise dr.DeskError(f"`git ls-files` failed: {said(proc)}")
    return {p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p}


#: This project's document gate. Absent in a stand-in workspace, where the
#: save goes on without it.
DOC_GATE = Path("scripts") / "check_docs.py"


def doc_gate_failure(repo: Path) -> str | None:
    """What the document gate printed when it failed, or None when it passed.

    Run BEFORE the desk is closed, so a refusal leaves the room as it was. The
    gate reads untracked files too, so a lane's new document is checked here
    rather than after it is committed.
    """
    gate = repo / DOC_GATE
    if not gate.exists():
        return None
    proc = subprocess.run([sys.executable, str(gate)], cwd=str(repo),
                          capture_output=True, check=False)
    return None if proc.returncode == 0 else (said(proc) or f"exit {proc.returncode}")


def owned_changes(record: dict) -> tuple[list[str], list[str], list[str]]:
    """(paths this desk saves, ownership failures, paths that are another window's)."""
    changed = dr.changed_since_baseline(record)
    by_owner, failures = co.findings(record, changed)
    theirs = [line.split("  -- ")[0] for line in by_owner.pop(co.OUTSIDE, [])]
    mine = sorted(path for paths in by_owner.values() for path in paths)
    return mine, failures, theirs


def save(desk: str, message: str, *, dry_run: bool = False, push: bool = True) -> int:
    record = dr.require_record()
    dr.require_the_desk(record, desk)
    mine, failures, theirs = owned_changes(record)
    open_lanes = [name for name, row in record["lanes"].items()
                  if name != dr.DESK_LANE and not dr.is_closed(row)]
    if failures or open_lanes:
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        if open_lanes:
            print(f"  lanes not yet closed: {open_lanes}", file=sys.stderr)
        print("REFUSED - nothing was closed and nothing was saved. A stray edit is "
              "given to its lane (`desk_record.py own`), undone by its maker, or "
              "recorded as another window's (`desk_record.py outside`).", file=sys.stderr)
        return 1
    gate = doc_gate_failure(dr.REPO)
    if gate is not None:
        print(gate, file=sys.stderr)
        print(f"REFUSED - the document gate ({DOC_GATE.as_posix()}) fails; nothing "
              "was closed and nothing was saved. Fix the document, or give it a "
              "row in doc_budgets.yaml, then save again.", file=sys.stderr)
        return 1
    for path in theirs:
        print(f"left alone (another window's): {path}")
    if dry_run:
        for path in mine:
            print(f"would save: {path}")
        print(f"DRY RUN - {len(mine)} path(s), plus whatever closing the desk moves "
              f"under {dr.COORDINATION}/. Nothing was closed or saved.")
        return 0

    for line in dr.close_desk(desk):
        print(line)

    # Closing moved files under coordination/, so the list is taken again: what
    # this desk owned and is still changed, plus everything under coordination/.
    now = dr.git_changed()
    paths = sorted({p for p in now if p in set(mine) or dr.covers(dr.COORDINATION, p)})
    paths = [p for p in paths if p not in set(theirs)]
    if not paths:
        print("NOTHING TO SAVE - the desk is closed and no owned file changed.")
        return 0
    new = sorted(untracked(dr.REPO) & set(paths))
    if new:
        proc = git(dr.REPO, "add", "-N", paths=new)
        if proc.returncode != 0:
            raise dr.DeskError(f"`git add -N` failed: {said(proc)}")
    proc = git(dr.REPO, "commit", "-m", message, paths=paths)
    if proc.returncode != 0:
        raise dr.DeskError(f"`git commit` failed, and nothing was saved: {said(proc)}")
    print(f"SAVED - {len(paths)} path(s) in one commit: {message}")
    if not push:
        return 0
    proc = git(dr.REPO, "push", "origin", "main")
    if proc.returncode != 0:
        print(f"PUSH FAILED - the commit is local only. Tell the owner now.\n{said(proc)}",
              file=sys.stderr)
        return 3
    print("PUSHED - origin/main")
    return 0


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--desk", required=True,
                        help="the desk's own session name, as ListAgents prints it")
    parser.add_argument("-m", "--message", required=True,
                        help="the commit message: what the job did")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be saved; close and save nothing")
    parser.add_argument("--no-push", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        return save(args.desk, args.message, dry_run=args.dry_run, push=not args.no_push)
    except dr.DeskError as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
