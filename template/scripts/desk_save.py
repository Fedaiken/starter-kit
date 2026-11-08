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
     the desk was ported from FACOWORK to HAZELHURST, 2026-09-24), run as
     `--write-kb`: it renders `kb/README.md` from the kb frontmatter as the
     desk's own act, then gates the whole tree. A lane's new kb entry
     therefore needs no lane to own the index (desk trade-import, 2026-10-29,
     `kb/desk-new-kb-entry-blocks-on-readme-owner.md`). A lane's new document
     with no budget row, or one over its ceiling, stops the save the same way,
     and the index is put back as it was. The index is not rendered when it is
     recorded as another window's or another live desk holds it;
     then, when a lane owned a path in the Starter Kit (`desk_record.py`,
     THE STARTER KIT), the kit's commit: one commit IN THE KIT REPO, by
     path, of the changed kit files lanes own, from the same message, pushed
     to the kit's `origin` at once; its hash is printed. It comes before the
     close because it is the one a rerun could not redo: a kit commit that
     fails refuses the save with nothing closed and nothing saved, and a
     project commit that fails after it leaves the kit's commit made and
     pushed, so the rerun saves the project alone. A failed kit push is said
     as plainly as a failed project push and ends the save with exit 3
     (Savecraft, 2026-11-07, the owner: "can we just cut the back and
     forth?" -- a kit fix is a lane's like any other, and the desk's one save
     is still the only one);
  2. `desk_record.py close-desk` -- the record, sheets and done files move under
     `closed/<stamp>/` in the desk's home;
  3. one commit, by path, of: every changed file a lane or the desk owns, plus
     everything changed in the desk's home (`coordination/desks/<home>/`), plus
     `kb/README.md` when step 1's render changed it. A path recorded as another
     window's work (`desk_record.py outside`), or held by another live desk,
     is never in it. A commit that fails -- another desk committing in the
     same moment holds git's `index.lock` -- puts the closed desk and the index
     back, so the save simply runs again;
  4. `git push origin main`.

In a project with `scripts/backlog.py` (the backlog ledger), step 1 also
refuses a desk log whose `## Logged for later` bullets are out of shape or
name no blocker, and step 3 puts each bullet on `backlog.md` -- its short
line, parked until its blocker, pointing at its line in the archived log --
in the same commit (backlog.py's docstring, LOGGED FOR LATER). Without that
script the save does none of this.

This file is kit-owned: identical in every project the Starter Kit seeds, and
an improvement made here goes back with `<venv python> scripts/kit_sync.py push
scripts/desk_save.py`.

Exit codes:
    0 = saved and pushed (or, with --dry-run, the list was printed)
    1 = refused: a changed file without exactly one owner, a lane still open,
        or the document gate failing
    2 = no desk record, not the desk, git could not be read, or a commit
        failed (the closed desk is put back; run the save again)
    3 = the commits were made and a push FAILED, the project's or the
        Starter Kit's -- say so to the owner in that turn
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from datetime import date
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

#: The kb index the gate renders from entry frontmatter (`--write-kb`). The
#: save renders it, so no lane need own it.
KB_INDEX = "kb/README.md"


def doc_gate_failure(repo: Path, *args: str) -> str | None:
    """What the document gate printed when it failed, or None when it passed.

    Run BEFORE the desk is closed, so a refusal leaves the room as it was. The
    gate reads untracked files too, so a lane's new document is checked here
    rather than after it is committed. `args` go to the gate: `--write-kb`
    for the save, `--as-rendered` for a dry run.
    """
    gate = repo / DOC_GATE
    if not gate.exists():
        return None
    proc = subprocess.run([sys.executable, str(gate), *args], cwd=str(repo),
                          capture_output=True, check=False)
    return None if proc.returncode == 0 else (said(proc) or f"exit {proc.returncode}")


def render_blocker(theirs: Sequence[str]) -> str | None:
    """Why the save may not render the kb index, or None when it renders it."""
    if KB_INDEX in theirs:
        return "it is recorded as another window's work"
    claim = dr.another_desks_claim(KB_INDEX)
    return None if claim is None else f"another live desk holds it: {claim}"


def read_index() -> bytes | None:
    index = dr.REPO / KB_INDEX
    return index.read_bytes() if index.is_file() else None


def unrender(before: bytes | None, new: Sequence[str] = ()) -> None:
    """Put the kb index back as it was before the save rendered it. A refused
    or failed save leaves the room as it was; a rendered index that no lane
    owns would also fail the next run's ownership check."""
    if KB_INDEX in new:
        git(dr.REPO, "reset", "-q", paths=[KB_INDEX])
    index = dr.REPO / KB_INDEX
    if before is None:
        index.unlink(missing_ok=True)
    else:
        index.write_bytes(before)


#: The backlog ledger's script. A project without it saves as before.
LEDGER_SCRIPT = Path("scripts") / "backlog.py"


def backlog_module():
    """backlog.py, when this project has it; else None."""
    if not (dr.REPO / LEDGER_SCRIPT).is_file():
        return None
    return importlib.import_module("backlog")


def logged_refusal(bl) -> str | None:
    """Why the desk log's Logged-for-later bullets cannot go on the ledger, or
    None. Run before the desk is closed, so a refusal leaves the room as it was."""
    if bl is None or not dr.DESK_LOG.is_file():
        return None
    log = dr.DESK_LOG.relative_to(dr.REPO).as_posix()
    problems = bl.logged_problems(dr.DESK_LOG.read_text(encoding="utf-8"), log)
    try:
        bl.read(dr.REPO / bl.LEDGER_REL)
    except bl.Refused as exc:
        problems.append(str(exc))
    if not problems:
        return None
    return ("\n".join(f"  {p}" for p in problems)
            + f"\nREFUSED - nothing was closed and nothing was saved. Each Logged-for-later bullet is "
              f"`{bl.BULLET_SHAPE}`; work nothing outside the job blocks is done in the job.")


def owned_changes(record: dict) -> tuple[list[str], list[str], list[str]]:
    """(paths this desk saves, ownership failures, paths that are another window's)."""
    changed = dr.changed_since_baseline(record)
    by_owner, failures = co.findings(record, changed)
    theirs = [line.split("  -- ")[0] for line in by_owner.pop(co.OUTSIDE, [])]
    mine = sorted(path for paths in by_owner.values() for path in paths)
    return mine, failures, theirs


def kit_split(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """(the project's paths, the Starter Kit's) of `paths`, order kept."""
    kit = [p for p in paths if dr.kit_rel(p) is not None]
    return [p for p in paths if p not in set(kit)], kit


def commit_kit(message: str, owned: Sequence[str]) -> tuple[str | None, str | None]:
    """(the kit commit's short hash, None), or (None, why it failed): one
    commit in the Starter Kit's repo, by path, of the kit paths `owned`, from
    the save's own message. A new file is made known to git with `git add -N`
    first, and taken back out when the commit fails."""
    root = dr.kit_root()
    if root is None:
        return None, f"the Starter Kit ({dr.kit_root_text()}) is gone"
    inside = [dr.kit_rel(p) for p in owned]
    try:
        new = sorted(untracked(root) & set(inside))
    except dr.DeskError as exc:
        return None, f"in the Starter Kit: {exc}"
    if new:
        proc = git(root, "add", "-N", paths=new)
        if proc.returncode != 0:
            return None, f"`git add -N` in the Starter Kit failed: {said(proc)}"
    proc = git(root, "commit", "-m", message, paths=inside)
    if proc.returncode != 0:
        if new:
            git(root, "reset", "-q", paths=new)
        return None, f"`git commit` in the Starter Kit failed: {said(proc)}"
    head = git(root, "rev-parse", "--short", "HEAD")
    return head.stdout.decode("utf-8", "replace").strip() or "(no hash)", None


def push_kit() -> str | None:
    """Why the Starter Kit's push failed, or None when it went to `origin`."""
    proc = git(dr.kit_root(), "push", "origin", "HEAD")
    return None if proc.returncode == 0 else said(proc)


def restore(target: Path, new: Sequence[str]) -> int:
    """After a commit that FAILED: put the closed desk back, so the record is
    live again and the save can simply run again. Exit 2 either way.

    Closing comes before the commit (the archive is part of what is saved), so
    a failed commit used to leave no record: the ownership check and this save
    then refused "there is no desk record", and the work sat unsaved with
    nothing to save it by (FACOWORK, P-F9). With desks side by side, two saves
    in one moment make that failure ordinary. The `git add -N` marks made on
    the archived files are taken back too, or the rerun would find them
    pointing at files that moved away.
    """
    archived = target.relative_to(dr.REPO).as_posix()
    marks = [p for p in new if dr.covers(archived, p)]
    if marks:
        git(dr.REPO, "reset", "-q", paths=marks)
    try:
        dr.reopen_archived(target)
    except (dr.DeskError, OSError) as exc:
        print(f"the record was NOT restored: {exc}. It is under {archived}; move "
              f"it back to {dr.HOME}/ by hand, then run desk_save again",
              file=sys.stderr)
        return 2
    print("record restored — run desk_save again", file=sys.stderr)
    return 2


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
    renders = (dr.REPO / DOC_GATE).exists()
    if renders:
        blocker = render_blocker(theirs)
        if blocker is not None:
            renders = False
            print(f"not rendered: {KB_INDEX} -- {blocker}")
    before = read_index()
    render_flag = ("--as-rendered",) if dry_run else ("--write-kb",)
    gate = doc_gate_failure(dr.REPO, *(render_flag if renders else ()))
    rendered = renders and not dry_run and read_index() != before
    if gate is not None:
        if rendered:
            unrender(before)
        print(gate, file=sys.stderr)
        print(f"REFUSED - the document gate ({DOC_GATE.as_posix()}) fails; nothing "
              "was closed and nothing was saved. Fix the document, or give it a "
              "row in doc_budgets.yaml, then save again.", file=sys.stderr)
        return 1
    bl = backlog_module()
    refusal = logged_refusal(bl)
    if refusal is not None:
        if rendered:
            unrender(before)
        print(refusal, file=sys.stderr)
        return 1
    for path in theirs:
        print(f"left alone (another window's): {path}")
    if dry_run:
        if renders:
            print(f"would render: {KB_INDEX} ({DOC_GATE.as_posix()} --write-kb), "
                  f"saved in the commit if that changes it")
        project, kit = kit_split(mine)
        for path in project:
            print(f"would save: {path}")
        for path in kit:
            print(f"would save in the Starter Kit ({dr.kit_root_text()}): {dr.kit_rel(path)}")
        print(f"DRY RUN - {len(project)} path(s)"
              + (f" and {len(kit)} in the Starter Kit's own commit" if kit else "")
              + f", plus whatever closing the desk moves under {dr.HOME}/. "
              f"Nothing was closed or saved.")
        return 0

    if rendered:
        print(f"rendered: {KB_INDEX}")
    # The Starter Kit's commit, before the close (the docstring, step 1's end).
    mine, kit = kit_split(mine)
    kit_hash: str | None = None
    kit_push_failed: str | None = None
    if kit:
        kit_hash, failed = commit_kit(message, kit)
        if failed is not None:
            if rendered:
                unrender(before)
            print(f"FAIL - {failed}\nNothing was closed and nothing was saved, here or "
                  f"in the kit: run the save again.", file=sys.stderr)
            return 2
        print(f"SAVED IN THE STARTER KIT - commit {kit_hash}, {len(kit)} path(s) in "
              f"{dr.kit_root_text()}")
        if push:
            kit_push_failed = push_kit()
            if kit_push_failed is None:
                print("PUSHED - the Starter Kit's origin")
            else:
                print(f"KIT PUSH FAILED - kit commit {kit_hash} is local only. Tell the "
                      f"owner now.\n{kit_push_failed}", file=sys.stderr)
    target = dr.archive_desk(desk)
    print(f"desk closed; its record is under {target.relative_to(dr.REPO).as_posix()}")

    # The desk log's Logged-for-later bullets go on the backlog ledger, each
    # pointing at its line in the archived log (checked before the close).
    ledger_before = None
    ledger_moved = False
    archived_log = target / dr.DESK_LOG.name
    if bl is not None and archived_log.is_file():
        ledger_path = dr.REPO / bl.LEDGER_REL
        ledger_before = ledger_path.read_bytes() if ledger_path.is_file() else None
        try:
            ledger = bl.read(ledger_path)
            added = bl.move_logged(ledger, archived_log.read_text(encoding="utf-8"),
                                   archived_log.relative_to(dr.REPO).as_posix(), f"desk {desk}",
                                   date.today().isoformat(), dr.REPO)
        except bl.Refused as exc:
            print(f"FAIL - the backlog ledger did not take the logged bullets: {exc}", file=sys.stderr)
            if rendered:
                unrender(before)
            return restore(target, [])
        if added:
            bl.write(ledger_path, ledger)
            ledger_moved = True
            print(f"logged for later: {len(added)} item(s) parked on {bl.LEDGER_REL} "
                  f"({', '.join(e.id for e in added)})")

    # Closing moved files within the desk's home, so the list is taken again:
    # what this desk owned and is still changed, plus everything in its home
    # that no other live desk holds (a desk left at `coordination/` has the
    # homes of the desks under `coordination/desks/` inside its own), plus the
    # kb index this save rendered.
    now = dr.git_changed()
    others = dr.other_desks()
    paths = sorted({p for p in now if p in set(mine) or (rendered and p == KB_INDEX)
                    or (ledger_moved and p == bl.LEDGER_REL)
                    or (dr.covers(dr.HOME, p) and dr.another_desks_claim(p, others) is None)})
    paths = [p for p in paths if p not in set(theirs)]
    if not paths:
        print("NOTHING TO SAVE - the desk is closed and no owned file changed"
              + (" here." if kit else "."))
        return 3 if kit_push_failed is not None else 0
    new = sorted(untracked(dr.REPO) & set(paths))
    failed = None
    if new:
        proc = git(dr.REPO, "add", "-N", paths=new)
        if proc.returncode != 0:
            failed = f"`git add -N` failed, and nothing was saved: {said(proc)}"
    if failed is None:
        proc = git(dr.REPO, "commit", "-m", message, paths=paths)
        if proc.returncode != 0:
            failed = f"`git commit` failed, and nothing was saved: {said(proc)}"
    if failed is not None:
        print(f"FAIL - {failed}", file=sys.stderr)
        if rendered:
            unrender(before, new)
        if ledger_moved:
            ledger_path = dr.REPO / bl.LEDGER_REL
            if bl.LEDGER_REL in new:
                git(dr.REPO, "reset", "-q", paths=[bl.LEDGER_REL])
            if ledger_before is None:
                ledger_path.unlink()
            else:
                ledger_path.write_bytes(ledger_before)
        if kit:
            print(f"the Starter Kit's commit {kit_hash} stands"
                  + (" and is NOT pushed -- tell the owner now" if kit_push_failed else "")
                  + "; the rerun saves this project alone", file=sys.stderr)
        return restore(target, new)
    print(f"SAVED - {len(paths)} path(s) in one commit: {message}")
    if not push:
        return 0
    proc = git(dr.REPO, "push", "origin", "main")
    if proc.returncode != 0:
        print(f"PUSH FAILED - the commit is local only. Tell the owner now.\n{said(proc)}",
              file=sys.stderr)
        return 3
    print("PUSHED - origin/main")
    if kit_push_failed is not None:
        print(f"KIT PUSH FAILED - repeated: kit commit {kit_hash} is local only. Tell "
              f"the owner now.", file=sys.stderr)
        return 3
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
