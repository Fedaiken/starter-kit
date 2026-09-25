#!/usr/bin/env python3
"""The desk's record: which lane owns which files, and what each lane was told.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/desk_record.py open-desk --desk the-desk --job "a year of statements into the records"
    <venv python> scripts/desk_record.py stamp copy-march coordination/task_sheets/copy-march.md --desk the-desk
    <venv python> scripts/desk_record.py own copy-march records/2025/March.md --desk the-desk
    <venv python> scripts/desk_record.py disown copy-march records/2025/March.md --desk the-desk
    <venv python> scripts/desk_record.py route records/2025/March.md --ruling "the March deposit was a refund, not income" --desk the-desk
    <venv python> scripts/desk_record.py report-done copy-march
    <venv python> scripts/desk_record.py show
    <venv python> scripts/desk_record.py show copy-march
    <venv python> scripts/desk_record.py close-desk --desk the-desk

WHY THIS EXISTS
---------------
FACOWORK's reconciliation build, slice 2 (`Workflow_Templates/
plan_reconciliation_terminals_build.md`), ported 2026-09-24 to HAZELHURST and
from there into the Starter Kit. Every lane works in the one project folder
(R22) and makes its own edits (R5), so nothing in git says which lane a
changed file belongs to. This record does, and it is what the desk routes
the owner's corrections by (R6). Every change to who owns what is AN ACT ON THIS
FILE -- never a sentence in a message -- so a replacement desk, the final
check and `scripts/check_ownership.py` all read the same answer.

Adapted from the claims register and brief stamps in Fantasy Football's
`scripts/push_token.py`. Simpler here: ownership is whole folders or files in
one shared tree, there is no push queue, and only the desk ever saves to git.

This file is kit-owned: identical in every project the Starter Kit seeds, and
an improvement made here goes back with `python scripts/kit_sync.py push
scripts/desk_record.py`. What differs by project -- the reason tokens, and
which of them read a source document -- is read from
`scripts/reason_tokens.json` through `scripts/open_terminal.py`.

ONE ACT, NOT TWO
----------------
* `stamp` reads a task sheet, refuses one a lane could not finish, records its
  digest AND writes the sheet's `owns:` paths into the record. A lane cannot be
  briefed without being given its files, and `scripts/open_terminal.py` refuses
  to open a lane whose sheet is not stamped.
* `route` writes the owner's ruling to the desk log FIRST (R18), then puts every
  lane that owns an affected path back to work -- so a lane a correction was
  sent to cannot be closed on the strength of a `done` it reported earlier --
  and prints the line to send each one.

SINGLE WRITER
-------------
The desk writes this record and nothing else does; a lane's one write is its
own `coordination/done/<lane>.json`, through `report-done`. `--desk` is checked
against the name on file: cooperative, not security, but it is the difference
between a lane that briefed itself and one that was briefed.

Exit codes:
    0 = done
    2 = refused; stderr says why and names the remedy
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The Windows console is cp1252 and cannot encode the arrows this project
# writes in; a ruling quoted back would die instead of being printed.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
COORDINATION = "coordination"
RECORD = REPO / COORDINATION / "desk_record.json"
DONE_DIR = REPO / COORDINATION / "done"
DESK_LOG = REPO / COORDINATION / "desk_log.md"
CLOSED_DIR = REPO / COORDINATION / "closed"

#: The desk's own row. Everything under `coordination/` is the desk's -- this
#: record, the launch record the opener appends to, task sheets, done files --
#: or every job's ownership check would fail on the desk's own bookkeeping
#: (carried from slice 1).
DESK_LANE = "desk"
NL = chr(10)
DESK_OWNS = (COORDINATION,)

#: The fields of a task sheet, each opening a line. `owns:` and `reads:` are
#: lists of `- path` lines; the rest are text.
SHEET_FIELDS = ("unit", "reason", "owns", "reads", "task", "done")
_FIELD = re.compile(r"^(unit|reason|owns|reads|task|done):[ \t]*(.*)$", re.I | re.M)

#: What joins two units into one line. R23: a lane is one unit of work -- a
#: month of records, a document, a question, a letter, a category.
_TWO_UNITS = re.compile(r"[;,+&]|\band\b", re.I)

#: What the second-unit test does NOT read. Text in parentheses describes the
#: one unit ("the first quarter (January, February and March)"), and a dash sets
#: off a gloss on it; neither joins a second unit. Measured at the S3 build,
#: where the stamp refused one-unit sheets over the commas in an aside. The
#: innermost pair goes first, so a nested aside is removed whole.
_ASIDE = re.compile(r"\([^()]*\)")
_DASHES = (" --- ", " -- ", " — ", " – ")

#: A `done:` line that runs pytest must name a test file or folder under
#: `tests/`. The whole tree takes minutes per lane, and it reports every other
#: lane's breakage as this lane's -- the S3 build's desk wrote that fault into
#: three sheets.
_PYTEST = re.compile(r"\bpytest\b")
_TEST_PATH = re.compile(r"(?<![\w.-])tests/[\w.-][^\s`'\"]*")


def unit_text(unit: str) -> str:
    """The `unit:` line as the second-unit test reads it: asides removed,
    dashes blanked."""
    text = unit
    while _ASIDE.search(text):
        text = _ASIDE.sub(" ", text)
    for dash in _DASHES:
        text = text.replace(dash, " ")
    return text


def whole_suite_lines(done: str) -> list[str]:
    """Every `done:` line that runs pytest without naming a path under
    `tests/` -- a bare `pytest`, `pytest tests`, `-m pytest -q`."""
    return [line.strip() for line in done.splitlines()
            if _PYTEST.search(line)
            and not _TEST_PATH.search(line.replace("\\", "/"))]

#: What names a COMMAND in a `done:` block: a script or interpreter, pytest, or
#: git with a subcommand. Lifted from Fantasy Football, where it was measured
#: against fifty real briefs: backticks are not required, because the defect is
#: a `done:` that names NO measurement, not one that is unquoted.
RUNNABLE = re.compile(r"\.(?:py|exe)\b|\bpytest\b|\bgit\s+[a-z][a-z-]*\b")

#: A lane that works FROM a source document reads the document, never only a
#: summary of it (CLAUDE.md, Source of Truth: kb digests are derived). So a
#: sheet whose reason is marked `reads_source` in `scripts/reason_tokens.json`
#: and whose `reads:` names nothing outside the derived roots is refused at the
#: stamp. Replaces FACOWORK's "a judging lane reads the full recap" rule, which
#: is the same rule for that project.
DERIVED_ROOTS = ("kb/",)


def reason_lists() -> tuple[dict, str, tuple[str, ...]]:
    """This project's reasons, the catch-all, and the reasons that read a
    source -- from `scripts/reason_tokens.json`, through the opener, which
    refuses a bad file. That refusal reaches the desk as a DeskError naming
    the file, never as a traceback."""
    try:
        import open_terminal
    except Exception as exc:  # noqa: BLE001 -- the tokens file refused to load
        raise DeskError(str(exc)) from exc
    return (open_terminal.REASONS, open_terminal.CATCH_ALL_REASON,
            open_terminal.SOURCE_REASONS)

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: What a template marker is written with. `<lane>` and `CT<N>` are placeholders
#: and `(only when ...)` is a note to the desk, so a path carrying any of these
#: four is a template left unfilled, never a real path: the file-naming rule
#: bans parentheses in names and Windows bans `<` and `>`.
MARKER_CHARS = "()<>"


class DeskError(Exception):
    """A refusal. The message names the remedy."""


# --- paths ------------------------------------------------------------------


def clean_path(raw: str) -> str:
    """A repo-relative path, forward slashes, no trailing slash -- or a refusal.

    Repo-relative is a format rule, not a preference: a path outside the
    project sends a lane at a folder the harness stops to ask the owner
    about, with nobody at that screen.
    """
    path = raw.strip().strip("`").replace("\\", "/").rstrip("/")
    while path.startswith("./"):
        path = path[2:]
    parts = path.split("/")
    if (not path or path == "." or path.startswith("/") or ":" in parts[0]
            or ".." in parts or parts[0] == ".git"):
        raise DeskError(
            f"{raw!r} is not a path inside this project. Paths are "
            f"repo-relative (e.g. records/2025/March.md), never absolute, "
            f"never `..`, never the whole project"
        )
    return path


def marker_problem(raw: str) -> str | None:
    """Why `raw` is a template marker and not a path, or None when it is clean.

    Kept out of `clean_path` on purpose: `disown` runs paths through that too,
    and a marker that already reached the record must stay possible to take
    back out. Only the acts that GIVE a path (the stamp, `own`) ask this.
    """
    marks = [f"`{ch}`" for ch in MARKER_CHARS if ch in raw]
    if not marks:
        return None
    return (f"carries {', '.join(marks)}: a template placeholder or marker was "
            f"left in")


def covers(owned: str, path: str) -> bool:
    """Whether owning `owned` means owning `path`: the same file, or a folder
    above it. Case is folded because Windows and macOS file systems ignore
    case by default; on a case-sensitive Linux tree folding can only make two
    lanes' paths collide sooner, which the stamp then refuses -- the safe
    direction."""
    owned, path = owned.casefold(), path.casefold()
    return path == owned or path.startswith(owned + "/")


def overlap(a: str, b: str) -> bool:
    return covers(a, b) or covers(b, a)


def owners_of(record: dict, path: str) -> list[str]:
    return sorted(
        lane for lane, row in record["lanes"].items()
        if any(covers(owned, path) for owned in row.get("owns", []))
    )


# --- the record -------------------------------------------------------------


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_record(path: Path | None = None) -> dict | None:
    path = RECORD if path is None else path
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeskError(f"{path} is not JSON ({exc}); it is the desk's to repair") from exc
    if not isinstance(record, dict) or "lanes" not in record:
        raise DeskError(f"{path} is not a desk record: it has no `lanes`")
    return record


def write_record(record: dict, path: Path | None = None) -> None:
    """Whole-file replace, so a reader never sees half a record."""
    path = RECORD if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = path.with_suffix(".json.writing")
    scratch.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
    os.replace(scratch, path)


def require_record() -> dict:
    record = read_record()
    if record is None:
        raise DeskError(
            "there is no desk record, so there is no desk. The owner starts one "
            "by typing /desk in a window of their own, and "
            "that window runs `desk_record.py open-desk`"
        )
    return record


def require_the_desk(record: dict, actor: str | None) -> None:
    if not actor:
        raise DeskError("this act is the desk's: pass --desk <your session name>")
    if actor != record.get("desk"):
        raise DeskError(
            f"--desk {actor!r} is not the desk; the record names "
            f"{record.get('desk')!r}. A lane does not write the record -- ask "
            f"the desk in one line. A REPLACEMENT desk takes over with "
            f"`open-desk --inherit`"
        )


def lane_row(record: dict, lane: str) -> dict:
    row = record["lanes"].get(lane)
    if row is None or lane == DESK_LANE:
        raise DeskError(
            f"the record has no lane {lane!r}. Lanes on file: "
            f"{sorted(n for n in record['lanes'] if n != DESK_LANE)}. A lane "
            f"gets its row when its task sheet is stamped"
        )
    return row


def is_closed(row: dict) -> bool:
    return bool(row.get("closed"))


# --- what git says has changed ----------------------------------------------


def git_changed(repo: Path | None = None) -> list[str]:
    """Every path git lists as changed or untracked, repo-relative."""
    repo = REPO if repo is None else repo
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=str(repo), capture_output=True, check=False,
    )
    if proc.returncode != 0:
        raise DeskError(f"`git status` failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    tokens = proc.stdout.decode("utf-8", "replace").split("\0")
    found: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if len(token) < 4:
            continue
        found.append(token[3:])
        # A rename or copy carries its SOURCE as the next token, and the source
        # is a file that changed too (it went away).
        if token[0] in "RC" or token[1] in "RC":
            if index < len(tokens) and tokens[index]:
                found.append(tokens[index])
            index += 1
    return sorted(set(found))


def file_stamp(repo: Path, path: str) -> list[int] | None:
    try:
        stat = (repo / path).stat()
    except OSError:
        return None
    return [stat.st_size, stat.st_mtime_ns]


def take_baseline(repo: Path | None = None) -> dict:
    """What was ALREADY changed when the desk opened, with each file's size and
    time. The owner's tree is rarely clean (an Inbox drop, a session's audio
    folder), and those files are nobody's lane. A baseline file that changes
    AFTERWARDS no longer matches its stamp and is checked like any other."""
    repo = REPO if repo is None else repo
    return {path: file_stamp(repo, path) for path in git_changed(repo)
            if not covers(COORDINATION, path)}


def changed_since_baseline(record: dict, repo: Path | None = None) -> list[str]:
    repo = REPO if repo is None else repo
    baseline = record.get("baseline", {})
    return [path for path in git_changed(repo)
            if path not in baseline or baseline[path] != file_stamp(repo, path)]


# --- task sheets ------------------------------------------------------------


def sheet_digest(text: str) -> str:
    """Over text, newlines normalised: a sheet written by one window's editor
    and read by another can differ by a `\\r` and nothing else, and "this sheet
    changed since it was stamped" must never cry wolf."""
    return hashlib.sha256(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def parse_sheet(text: str) -> tuple[dict[str, str], list[str]]:
    """The sheet's fields, and every field that appears more than once."""
    fields: dict[str, str] = {}
    twice: list[str] = []
    marks = list(_FIELD.finditer(text))
    for number, mark in enumerate(marks):
        name = mark.group(1).lower()
        end = marks[number + 1].start() if number + 1 < len(marks) else len(text)
        body = (mark.group(2) + text[mark.end():end]).strip()
        if name in fields:
            twice.append(name)
        else:
            fields[name] = body
    return fields, twice


def list_items(body: str) -> list[str]:
    return [line.strip()[1:].strip() for line in body.splitlines()
            if line.strip().startswith("-") and line.strip()[1:].strip()]


def sheet_problems(text: str, repo: Path | None = None) -> list[str]:
    """Why a lane could not work from this sheet. Empty is the pass.

    THE STAMP IS WHERE A SHEET IS READ. A lane reads its sheet as a
    specification and finds out at the END that it could not be finished,
    having done the work; the desk is the only window that can fix the text,
    so the refusal belongs in the desk's own act.
    """
    REASONS, CATCH_ALL_REASON, SOURCE_REASONS = reason_lists()

    repo = REPO if repo is None else repo
    fields, twice = parse_sheet(text)
    problems = [f"`{name}:` appears more than once" for name in twice]
    for name in SHEET_FIELDS:
        if not fields.get(name):
            problems.append(f"it has no `{name}:`")
    if problems:
        return problems + [
            "a task sheet is: `unit:` one line; `reason:` one token; `owns:` "
            "and `reads:` as `- path` lines; `task:` what to do; `done:` the "
            "command whose output finishes the lane"
        ]

    unit = fields["unit"]
    if "\n" in unit or _TWO_UNITS.search(unit_text(unit)):
        problems.append(
            f"`unit: {unit.splitlines()[0]}` reads as more than one unit of "
            f"work. A lane is ONE unit (ruling R23) -- one month of records, one "
            f"document, one question, one letter; a second unit is a second sheet "
            f"and a second lane"
        )
    reason = fields["reason"].split()[0]
    if reason not in REASONS:
        problems.append(
            f"`reason: {reason}` is not on the launcher's list {list(REASONS)} "
            f"(scripts/reason_tokens.json; `open_terminal.py --reasons` prints "
            f"it); a job that fits none is {CATCH_ALL_REASON!r}"
        )

    owns: list[str] = []
    for raw in list_items(fields["owns"]):
        left_in = marker_problem(raw)
        if left_in:
            problems.append(f"owns: `- {raw}` {left_in}. Fill it in with the "
                            f"real path, or delete the line")
            continue
        try:
            path = clean_path(raw)
        except DeskError as exc:
            problems.append(f"owns: {exc}")
            continue
        if overlap(COORDINATION, path):
            problems.append(f"owns: {path} is the desk's own folder")
        owns.append(path)
    if not owns:
        problems.append(
            "`owns:` names no files. A lane with no files cannot be sent a "
            "correction, because the desk routes by who owns what (R6)"
        )

    reads: list[str] = []
    for raw in list_items(fields["reads"]):
        left_in = marker_problem(raw)
        if left_in:
            problems.append(f"reads: `- {raw}` {left_in}. Fill it in with the "
                            f"real path, or delete the line")
            continue
        try:
            path = clean_path(raw)
        except DeskError as exc:
            problems.append(f"reads: {exc}")
            continue
        if not (repo / path).exists():
            problems.append(f"reads: {path} does not exist")
        reads.append(path)
    if reason in SOURCE_REASONS and not any(
            not any((path + "/").startswith(root) for root in DERIVED_ROOTS)
            for path in reads):
        problems.append(
            f"a {reason} lane works from the SOURCE document, and `reads:` "
            f"names only derived files ({', '.join(DERIVED_ROOTS)}). Name the "
            f"document itself -- the agreement, the statement, the letter"
        )

    if RUNNABLE.search(fields["done"]) is None:
        problems.append(
            "`done:` names no runnable command. Done is a MEASUREMENT -- a "
            "script whose output the lane quotes back -- never prose like "
            "\"the text reads correctly\", which is settled by whoever is "
            "asked last"
        )
    for line in whole_suite_lines(fields["done"]):
        problems.append(
            f"`done:` runs the whole test suite: `{line}`. Name the lane's own "
            f"test files (`pytest tests/test_<x>.py`) -- a whole-tree run takes "
            f"minutes per lane and reports every other lane's breakage as this "
            f"lane's"
        )
    return problems


def sheet_owns(text: str) -> list[str]:
    return [clean_path(raw) for raw in list_items(parse_sheet(text)[0].get("owns", ""))]


def read_sheet(sheet: str) -> tuple[str, str]:
    path = clean_path(sheet)
    try:
        return path, (REPO / path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DeskError(
            f"no task sheet at {path} ({exc.__class__.__name__}). Write the "
            f"sheet first -- a stamp is testimony ABOUT a document"
        ) from exc


def collisions(record: dict, lane: str, paths: Sequence[str]) -> list[str]:
    return [
        f"{path} overlaps {owned}, which is {other}'s"
        for path in paths
        for other, row in record["lanes"].items()
        if other != lane and not is_closed(row)
        for owned in row.get("owns", [])
        if overlap(path, owned)
    ]


def take_from_closed(record: dict, lane: str, paths: Sequence[str]) -> list[str]:
    """Paths a CLOSED lane held pass to the lane now being given them.

    A closed lane cannot edit any more, so its successor -- the applying lane
    after the drafting lane, or `<lane>-2` after an abandoned `<lane>` -- takes
    its files and every changed file still has exactly one owner. The one case
    that cannot be settled here is a closed lane holding a FOLDER ABOVE the new
    path: which of the rest stays with it is the desk's call.
    """
    moved: list[str] = []
    for other, row in record["lanes"].items():
        if other in (lane, DESK_LANE) or not is_closed(row):
            continue
        for owned in list(row.get("owns", [])):
            for path in paths:
                if covers(path, owned):
                    row["owns"].remove(owned)
                    moved.append(f"{owned} passes from {other} (closed) to {lane}")
                    break
                if covers(owned, path):
                    raise DeskError(
                        f"{other} is closed and owns {owned}, which is ABOVE "
                        f"{path}. Settle it first: `disown {other} {owned}`, "
                        f"then give each lane what is really its own. Nothing "
                        f"was changed."
                    )
    return moved


def stamped_sheet_problem(record: dict | None, lane: str, sheet: str | None = None) -> str | None:
    """Why `lane` has no stamped sheet to work from, or None when it has.

    Asked by the opener before a lane opens and by the lane as its first act:
    the check is AUTHORSHIP -- the desk stamped this text -- not existence.
    """
    if record is None:
        return "there is no desk record, so no desk stamped anything"
    row = record["lanes"].get(lane)
    if row is None or lane == DESK_LANE or not row.get("sha256"):
        return f"the desk has stamped no task sheet for {lane!r}"
    if is_closed(row):
        return f"{lane!r} is recorded as closed; a new piece of work is a new lane name"
    if sheet is not None:
        try:
            asked = clean_path(sheet)
        except DeskError as exc:
            return str(exc)
        if asked.casefold() != row["sheet"].casefold():
            return f"{lane!r} was stamped from {row['sheet']}, not {asked}"
    try:
        text = (REPO / row["sheet"]).read_text(encoding="utf-8")
    except OSError:
        return f"{row['sheet']} is stamped for {lane!r} and is no longer on disk"
    if sheet_digest(text) != row["sha256"]:
        return (f"{row['sheet']} has changed since the desk stamped it; the "
                f"desk stamps it again if the change is its own")
    return None


# --- done -------------------------------------------------------------------


def done_path(lane: str, *, done_dir: Path | None = None) -> Path:
    """Where `lane`'s done file is. `done_dir` names another folder, for a reader
    that was handed a record by path and so reads done files from beside THAT
    record (FACOWORK's `verify_recon_window.py --record`); None is this module's own."""
    folder = DONE_DIR if done_dir is None else done_dir
    return folder / f"{lane}.json"


#: How far after one act the next is stamped when the clock has not moved. The
#: Windows clock ticks about every 15 ms, so a `done` and a correction made in
#: one tick carry the same `time.time()`. Which of the two came first is decided
#: by the order the acts were made in, never by the clock's resolution.
AFTER = 0.001


def done_at(lane: str, *, done_dir: Path | None = None) -> float | None:
    """When `lane` last reported done, or None if it never has."""
    try:
        said = json.loads(done_path(lane, done_dir=done_dir).read_text(encoding="utf-8"))
        return float(said["at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def working_since_now(lane: str) -> float:
    """The `working_since` for putting `lane` (back) to work: now, and strictly
    after any `done` it has already reported, so that done stops counting."""
    now = time.time()
    said = done_at(lane)
    return now if said is None else max(now, said + AFTER)


def reported_done(row: dict, lane: str, *, done_dir: Path | None = None) -> bool:
    """A lane is done when it SAID so after it was last put to work. A `route`
    moves `working_since` forward, so an earlier `done` stops counting. Strictly
    after: `report_done` and `working_since_now` keep the two numbers apart
    whatever the clock's resolution, so an equal pair is never a done. This is
    the one statement of the rule -- FACOWORK's `verify_recon_window.py` calls it, with
    `done_dir` pointing at the folder beside the record it was given."""
    said = done_at(lane, done_dir=done_dir)
    try:
        return said is not None and said > float(row.get("working_since", 0))
    except (ValueError, TypeError):
        return False


def lane_state(row: dict, lane: str) -> str:
    if is_closed(row):
        why = row["closed"].get("abandoned")
        return f"closed ({'abandoned: ' + why if why else 'done'})"
    return "reported done" if reported_done(row, lane) else "working"


def is_a_lane(lane: str) -> bool:
    """Whether the desk record has a live row for this window."""
    record = read_record()
    return (record is not None and lane != DESK_LANE
            and lane in record["lanes"] and not is_closed(record["lanes"][lane]))


def close_problem(lane: str) -> str | None:
    """Why the desk may not close `lane`, or None. A window with no row is not
    a lane of this desk, and closing strays is what `--close` is for."""
    record = read_record()
    if record is None or lane not in record["lanes"] or lane == DESK_LANE:
        return None
    row = record["lanes"][lane]
    if is_closed(row) or reported_done(row, lane):
        return None
    return (
        f"{lane} has not reported done since it was last put to work "
        f"({row.get('working_since_iso', '?')}). It reports by running "
        f"`desk_record.py report-done {lane}` -- ask it for that"
    )


def record_close(lane: str, *, abandoned: str | None = None) -> None:
    """Called by the opener once the window is gone. The row and its paths
    STAY: the ownership check at the end of the job still has to attribute
    every file this lane changed."""
    record = read_record()
    if record is None or lane not in record["lanes"] or lane == DESK_LANE:
        return
    record["lanes"][lane]["closed"] = {"at": now_iso(), "abandoned": abandoned}
    write_record(record)


# --- the acts ---------------------------------------------------------------


def open_desk(desk: str, job: str, *, inherit: bool) -> list[str]:
    record = read_record()
    if record is not None:
        if not inherit:
            raise DeskError(
                f"a desk record is already on file: desk {record.get('desk')!r}, "
                f"job {record.get('job')!r}. If that desk is gone and you are "
                f"its replacement, run this again with --inherit; if its job "
                f"is finished, it is closed with `close-desk` first"
            )
        was = record.get("desk")
        record["desk"] = desk
        record.setdefault("inherited", []).append({"from": was, "to": desk, "at": now_iso()})
        write_record(record)
        return [f"{desk} is the desk now (was {was}); job: {record.get('job')}",
                *show_lines(record)]
    if not job.strip():
        raise DeskError("a new desk says what it is for: --job \"<one line>\"")
    record = {
        "desk": desk, "job": job.strip(), "opened_at": now_iso(),
        "baseline": take_baseline(),
        "lanes": {DESK_LANE: {"owns": list(DESK_OWNS)}},
    }
    write_record(record)
    return [f"desk {desk} opened: {job.strip()}",
            f"  {len(record['baseline'])} file(s) were already changed and are "
            f"nobody's lane unless they change again"]


def stamp(desk: str, lane: str, sheet: str) -> list[str]:
    record = require_record()
    require_the_desk(record, desk)
    if not _SAFE_NAME.match(lane) or lane == DESK_LANE:
        raise DeskError(f"{lane!r} cannot be a lane name")
    path, text = read_sheet(sheet)
    problems = sheet_problems(text)
    if problems:
        raise DeskError(
            f"{path} is not a sheet a lane could finish:\n"
            + "\n".join(f"  - {p}" for p in problems) + "\nNothing was stamped."
        )
    owns = sheet_owns(text)
    hits = collisions(record, lane, owns)
    if hits:
        raise DeskError(
            "two lanes cannot own one file:\n"
            + "\n".join(f"  - {h}" for h in hits)
            + "\nNarrow one of them (`disown`), then stamp again. Nothing was stamped."
        )
    existing = record["lanes"].get(lane)
    if existing and is_closed(existing):
        raise DeskError(f"{lane!r} is recorded as closed; a new piece of work is a new lane name")
    moved = take_from_closed(record, lane, owns)
    fields = parse_sheet(text)[0]
    at = working_since_now(lane)
    record["lanes"][lane] = {
        "sheet": path, "sha256": sheet_digest(text), "stamped_at": now_iso(),
        "unit": fields["unit"], "reason": fields["reason"].split()[0],
        "owns": owns, "working_since": at, "working_since_iso": now_iso(),
        "closed": None,
    }
    write_record(record)
    return [f"stamped {path} for {lane} ({record['lanes'][lane]['sha256'][:12]}); "
            f"{lane} owns {owns}", *(f"  {line}" for line in moved)]


def own(desk: str, lane: str, paths: Sequence[str], *, give: bool) -> list[str]:
    record = require_record()
    require_the_desk(record, desk)
    row = record["lanes"].get(lane) if lane == DESK_LANE else lane_row(record, lane)
    if give:
        for raw in paths:
            left_in = marker_problem(raw)
            if left_in:
                raise DeskError(f"{raw!r} {left_in}, so it is not a path. Give "
                                f"the real path. Nothing was changed.")
    cleaned = [clean_path(p) for p in paths]
    if give:
        hits = collisions(record, lane, cleaned)
        if hits:
            raise DeskError("two lanes cannot own one file:\n"
                            + "\n".join(f"  - {h}" for h in hits)
                            + "\nNothing was changed.")
        take_from_closed(record, lane, cleaned)
        row["owns"] = sorted(set(row.get("owns", [])) | set(cleaned))
        verb = "now owns"
    else:
        missing = [p for p in cleaned if p not in row.get("owns", [])]
        if missing:
            raise DeskError(f"{lane} does not own {missing}; it owns {row.get('owns', [])}")
        row["owns"] = [p for p in row["owns"] if p not in cleaned]
        verb = "no longer owns"
    write_record(record)
    said = [f"{lane} {verb} {cleaned}"]
    if lane != DESK_LANE:
        said.append(f"  send: [desk] ownership: {lane} {verb} {', '.join(cleaned)}")
    return said


def outside_of(record: dict, path: str) -> str | None:
    """Why `path` is on record as another window's work, or None if it is not."""
    for marked, why in record.get("outside", {}).items():
        if covers(marked, path):
            return str(why)
    return None


def outside(desk: str, paths: Sequence[str], why: str) -> list[str]:
    """Record paths as NOT this desk's: another window changed them.

    The owner runs a desk beside other work. In the first real run their recap window
    changed its scratchpad while the desk was open, the ownership check called
    it a stray -- correctly, by its only rule -- and the one way past was for
    the desk to take a file that was not its own. This is the honest act: the
    check passes such a path under its own heading, and the save never stages
    it. Refused for a path any lane owns or that holds a lane's files: a stray
    inside a lane's unit is never somebody else's.
    """
    record = require_record()
    require_the_desk(record, desk)
    if not why.strip():
        raise DeskError("--why is empty: say which window's work this is")
    cleaned = [clean_path(p) for p in paths]
    hits = [f"{p}: {lane} owns {owned}" for p in cleaned
            for lane, row in record["lanes"].items()
            for owned in row.get("owns", []) if overlap(owned, p)]
    if hits:
        raise DeskError("a path a lane owns cannot be another window's work:" + NL
                        + NL.join(f"  - {h}" for h in hits) + NL + "Nothing was changed.")
    marks = record.setdefault("outside", {})
    for p in cleaned:
        marks[p] = why.strip()
    write_record(record)
    return [f"outside this desk: {p} -- {why.strip()}" for p in cleaned] + [
        "  the ownership check passes these and the save does not stage them"]


def route(desk: str, paths: Sequence[str], ruling: str, log: str | None) -> list[str]:
    """The owner's ruling to disk, THEN to every lane it affects (R18, then R6)."""
    record = require_record()
    require_the_desk(record, desk)
    if not ruling.strip():
        raise DeskError("--ruling carries the owner's words, word for word; it cannot be empty")
    cleaned = [clean_path(p) for p in paths]
    log_path = DESK_LOG if log is None else REPO / clean_path(log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n## Ruling, {now_iso()}\n\n> {ruling.strip()}\n\n"
                     f"Affects: {', '.join(cleaned)}\n")
    affected = sorted({
        lane for path in cleaned for lane, row in record["lanes"].items()
        if lane != DESK_LANE and any(overlap(owned, path) for owned in row.get("owns", []))
    })
    said = [f"ruling written to {log_path.relative_to(REPO).as_posix()}"]
    for lane in affected:
        row = record["lanes"][lane]
        if is_closed(row):
            said.append(f"  {lane} owns an affected path and is CLOSED: reopen its "
                        f"work as a new lane from a new sheet")
            continue
        row["working_since"] = working_since_now(lane)
        row["working_since_iso"] = now_iso()
        said.append(f"  send to {lane}: [desk] correction: {ruling.strip()} "
                    f"-- affects: {', '.join(cleaned)}")
    if not affected:
        said.append("  no lane owns an affected path; nothing to send")
    write_record(record)
    return said


def report_done(lane: str) -> list[str]:
    record = require_record()
    row = lane_row(record, lane)
    problem = stamped_sheet_problem(record, lane)
    if problem:
        raise DeskError(f"{problem}. Tell the desk in one line; nothing was recorded")
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    # Strictly after the lane was last put to work, even inside one clock tick.
    at = max(time.time(), float(row.get("working_since", 0)) + AFTER)
    done_path(lane).write_text(
        json.dumps({"lane": lane, "at": at, "at_iso": now_iso()}) + "\n",
        encoding="utf-8", newline="\n")
    return [f"{lane} is recorded as done. Send the desk your `done:` line with "
            f"its receipts; the desk closes this window, you do not"]


def show_lines(record: dict, lane: str | None = None) -> list[str]:
    lines = [f"desk: {record.get('desk')}  job: {record.get('job')}"]
    for name, row in sorted(record["lanes"].items()):
        if lane and name != lane:
            continue
        if name == DESK_LANE:
            lines.append(f"  {name:<20} owns {row.get('owns', [])}")
            continue
        lines.append(f"  {name:<20} {lane_state(row, name):<24} {row.get('reason')}, "
                     f"unit: {row.get('unit')}")
        lines.append(f"  {'':<20} sheet {row.get('sheet')} "
                     f"({str(row.get('sha256'))[:12]}); owns {row.get('owns', [])}")
    return lines


def show(lane: str | None) -> list[str]:
    record = require_record()
    if lane:
        lane_row(record, lane)
        problem = stamped_sheet_problem(record, lane)
        if problem:
            raise DeskError(problem)
    return show_lines(record, lane)


def close_desk(desk: str) -> list[str]:
    """Archive, never delete: the record, sheets and done files of a finished
    job move under `coordination/closed/<stamp>/`."""
    record = require_record()
    require_the_desk(record, desk)
    open_lanes = [name for name, row in record["lanes"].items()
                  if name != DESK_LANE and not is_closed(row)]
    if open_lanes:
        raise DeskError(
            f"lanes not yet closed: {open_lanes}. Close each with "
            f"`open_terminal.py --close --name <lane>` first"
        )
    target = CLOSED_DIR / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target.mkdir(parents=True)
    os.replace(RECORD, target / RECORD.name)
    for folder in (DONE_DIR, REPO / COORDINATION / "task_sheets"):
        if folder.exists():
            os.replace(folder, target / folder.name)
    if DESK_LOG.exists():
        os.replace(DESK_LOG, target / DESK_LOG.name)
    return [f"desk closed; its record is under {target.relative_to(REPO).as_posix()}"]


# --- the command line -------------------------------------------------------


#: The acts only the desk performs. Each ends with the stall banner, so the desk
#: is shown a lane stopped at a pop-up by the commands it runs anyway -- it does
#: not have to remember to look (the 2026-09-19 rehearsal, finding 2).
DESK_ACTS = ("open-desk", "stamp", "own", "disown", "outside", "route")


def stall_banner() -> list[str]:
    if "PYTEST_CURRENT_TEST" in os.environ:  # the real CLI is not a test's business
        return []
    try:
        from open_terminal import stalled_lines
        return stalled_lines()
    except Exception:  # noqa: BLE001 -- a banner never breaks the act it rides on
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    acts = parser.add_subparsers(dest="act", required=True)

    def desk_act(name: str, text: str) -> argparse.ArgumentParser:
        sub = acts.add_parser(name, help=text)
        sub.add_argument("--desk", help="the desk's own session name, as ListAgents prints it")
        return sub

    sub = desk_act("open-desk", "start the record for a new job, or --inherit a live one")
    sub.add_argument("--job", default="", help="one line: what this desk is for")
    sub.add_argument("--inherit", action="store_true",
                     help="take over a record whose desk window is gone")
    sub = desk_act("stamp", "check a task sheet, record it, and give the lane its files")
    sub.add_argument("lane")
    sub.add_argument("sheet")
    for name, text in (("own", "give a lane more paths"), ("disown", "take paths back")):
        sub = desk_act(name, text)
        sub.add_argument("lane")
        sub.add_argument("paths", nargs="+")
    sub = desk_act("outside", "record a changed path as another window's work, not this desk's")
    sub.add_argument("paths", nargs="+")
    sub.add_argument("--why", required=True,
                     help="whose work it is -- which window, doing what")
    sub = desk_act("route", "write the owner's ruling to disk, then name every lane it affects")
    sub.add_argument("paths", nargs="+")
    sub.add_argument("--ruling", required=True, help="the owner's words, word for word")
    sub.add_argument("--log", help="the log to append to (default coordination/desk_log.md)")
    sub = acts.add_parser("report-done", help="a lane records that its work is finished")
    sub.add_argument("lane")
    sub = acts.add_parser("show", help="the desk, its lanes, and what each owns")
    sub.add_argument("lane", nargs="?")
    desk_act("close-desk", "archive the record of a finished job")
    return parser


def main(argv: Sequence[str] = ()) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.act == "open-desk":
            if not args.desk:
                raise DeskError("pass --desk <your session name>")
            said = open_desk(args.desk, args.job, inherit=args.inherit)
        elif args.act == "stamp":
            said = stamp(args.desk, args.lane, args.sheet)
        elif args.act in ("own", "disown"):
            said = own(args.desk, args.lane, args.paths, give=args.act == "own")
        elif args.act == "outside":
            said = outside(args.desk, args.paths, args.why)
        elif args.act == "route":
            said = route(args.desk, args.paths, args.ruling, args.log)
        elif args.act == "report-done":
            said = report_done(args.lane)
        elif args.act == "show":
            said = show(args.lane)
        else:
            said = close_desk(args.desk)
    except DeskError as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 2
    print("\n".join(said))
    if args.act in DESK_ACTS:
        for line in stall_banner():
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
