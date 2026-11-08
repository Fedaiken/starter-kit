#!/usr/bin/env python3
"""The desk's record: which lane owns which files, and what each lane was told.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/desk_record.py open-desk --desk the-desk --job "a year of statements into the records"
    <venv python> scripts/desk_record.py plan --lanes 12 --desk the-desk
    <venv python> scripts/desk_record.py plan --lanes 4 --reading Working/plan.md --desk the-desk
    <venv python> scripts/desk_record.py stamp copy-march coordination/desks/statements/task_sheets/copy-march.md --desk the-desk
    <venv python> scripts/desk_record.py own copy-march records/2025/March.md --desk the-desk
    <venv python> scripts/desk_record.py disown copy-march records/2025/March.md --desk the-desk
    <venv python> scripts/desk_record.py route records/2025/March.md --ruling "the March deposit was a refund, not income" --asked "unprompted" --desk the-desk
    <venv python> scripts/desk_record.py report-done copy-march
    <venv python> scripts/desk_record.py report-done copy-march --dry-run
    <venv python> scripts/desk_record.py show
    <venv python> scripts/desk_record.py show copy-march
    <venv python> scripts/desk_record.py close-desk --desk the-desk

A desk runs every one of these through its home, e.g.
`<venv python> scripts/desk_home.py statements desk_record.py show` (DESKS
SIDE BY SIDE, below). A lane runs `show` and `report-done` bare: the opener
started its window with the home already set.

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
an improvement made here goes back with `<venv python> scripts/kit_sync.py push
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

RECEIPTS BY SCRIPT
------------------
`report-done <lane>` runs every command the stamped sheet's `done:` names
ITSELF -- unpiped, from the project root, under THE DONE SHELL below --
writes each command, its exit code and the bytes it printed to
`<home>/done/<lane>.receipts.md`, prints them, and records the lane done only
when every command exited 0. A lane once ran its commands and copied the
output into its message by hand; a receipt typed by the window it vouches for
is testimony, and one run by this script is a measurement. `--dry-run` does
everything but run.

THE DONE SHELL
--------------
No shell at all: each command is split into words by POSIX rules (Python's
`shlex`, the rules the Bash tool reads a line by) and run as that list. So
nothing a shell does can happen -- no pipe (`| tail` reports the pipe's exit
code, not the command's), no redirect, no `&&` or `;`, no variable, no glob --
and the stamp refuses a `done:` command that needs one, a template placeholder
left in (`<lane>`), a Windows backslash outside quotes (POSIX reads it as an
escape), a first word that is not a program, or a git subcommand
`scripts/lane_guard.py` refuses (a command run by this script never passes
through the guard's hook). A lane finds out at the stamp, not at the end.

THE LANE BUDGET AND THE DESK'S OWN LOAD
---------------------------------------
The owner, 2026-11-02, after a desk warned of a crowded window on a guess: "it jsut
means you are not really tracking context accurately". Ported that day from
FACOWORK (`kb/lane-context-sizing.md`), three checks, each a measurement:

* `sheet_problems` refuses a sheet whose lane is predicted past the budget,
  from the bytes its `reads:` names (`scripts/lane_budget.py`), naming the
  remedy: split the unit.
* `plan` writes how many lanes each of this desk's windows takes (FACOWORK's
  `desk_plan.generic_plan`), from the meter's reading of this window. The stamp
  refuses `NO PLAN` until there is one -- a desk opened earlier plans the lanes
  it has left. Past a window's planned count, the load with one more lane is
  re-predicted from the meter: under the line the lane is stamped and
  `PLAN CHANGED` is printed and written to the desk log; past it the stamp
  refuses `PLANNED HANDOVER`. Under the count, a meter that says the rest no
  longer fits refuses `REPLAN`.
* The backstop (`handover_problem`): a desk at 60% of its window (70% for a
  window planned past 60%) stamps nothing more. An unreadable meter never
  refuses; it prints METER UNREADABLE.

A LANE'S GATE IS ITS OWN
------------------------
A `done:` command that runs `check_docs.py` is refused at the stamp unless its
`--only` names exactly the sheet's `owns:` paths: none outside them, none of
them left out. Unscoped, the gate measures every lane's documents, and one
lane's half-edited file failed three finished lanes (desk rules-check,
2026-10-27). The whole-tree gate is `desk_save.py`'s, before the one save.

SINGLE WRITER
-------------
The desk writes this record and nothing else does; a lane's writes are its
own `done/<lane>.json` and `done/<lane>.receipts.md` in the desk's home,
through `report-done`. `--desk` is
checked against the name on file: cooperative, not security, but it is the
difference between a lane that briefed itself and one that was briefed.

DESKS SIDE BY SIDE, EACH IN ITS OWN HOME
----------------------------------------
One record for the whole project meant a second desk could not open while any
other was on file -- a side effect of how the desk was built, never a ruling
(FACOWORK, 2026-09-26: "it should only ever be constrained with its own runs,
not other desks' runs"; "even the generic /desk should be able to run
concurrent ones with just different names"). So every desk lives in a HOME,
`coordination/desks/<name>/`: its record, sheets, done files, log and closed
archive. A desk runs each of its tools through `scripts/desk_home.py <name>`,
which sets the home variable (`project_identity.DESK_HOME_ENV`); the opener
hands the same home to every lane window it starts, so a lane's plain `show`
and `report-done` reach its own desk. A NEW desk with no home is refused at
`open-desk`, so a desk that forgot the wrapper finds out at its first act.
What the one record used to buy -- no two lanes own one file -- still holds
ACROSS desks: `stamp` and `own` refuse a path another live desk's lane holds,
and the ownership check and the save read another desk's files as that
desk's, never as strays. `coordination/` itself stays a home for a record
left there before homes (inherit it, save it); nothing new opens there.

THE STARTER KIT, THE ONE ROOT OUTSIDE THE PROJECT
-------------------------------------------------
Savecraft, 2026-11-07, the owner: "you always tell me this thing about the
starter kit having to do it itself, and I always tell you that Claude's never
run there, and you have to do it, and then you do it. So can we just cut the
back and forth?" A fix that belongs in the Starter Kit used to be ungivable:
every path outside the project was refused, so the desk fell back on "a
window in the kit folder". So ONE root outside the project is accepted: the
kit's, named once in `STARTER_KIT_DIR` (from the project root, so no account
name is written down and it holds for every project seeded beside the kit;
inside the kit itself it names no folder, and nothing outside is accepted). A
sheet names a kit path absolute (`C:/.../Starter_Kit/template/x.py`) or from
the project root (`../Starter_Kit/template/x.py`); `clean_path` writes it in
one form, the kit root's own spelling plus the path inside it, so every
overlap and live-lane check reads it as it reads a project path. The
ownership check reads the kit repo's changes beside the project's, each
checked against the desk's baseline, and `scripts/desk_save.py` commits the
owned kit paths in the kit repo, by path, as part of the one save. The kit's
root itself, its `.git`, and every other path outside the project are still
refused.

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
import shlex
import shutil
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

import project_identity as identity  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
COORDINATION = "coordination"

#: Where a desk lives (the docstring's DESKS SIDE BY SIDE): `coordination/` for
#: a record left from before homes, `coordination/desks/<name>/` for every desk
#: opened since, named by `HOME_ENV` -- set by `scripts/desk_home.py` for the
#: desk's own commands and by the opener for each lane window.
HOME_ENV = identity.DESK_HOME_ENV
DESKS_DIR = f"{COORDINATION}/desks"
#: What every desk's opener appends to, whatever its home; each homed desk owns
#: it by name, so whichever desk saves while it has changed saves it.
SHARED_LAUNCH_RECORD = f"{COORDINATION}/launch_record.jsonl"

#: The desk's own row. Everything in its home is the desk's -- this record,
#: task sheets, done files -- plus the launch record the opener appends to, or
#: every job's ownership check would fail on the desk's own bookkeeping
#: (carried from slice 1).
DESK_LANE = "desk"
NL = chr(10)

#: The Starter Kit's root, from the project root: the one folder outside the
#: project a sheet may name (the docstring's THE STARTER KIT). Read through
#: `kit_root`, which is None on a machine without the folder -- and inside the
#: kit itself, where it names none.
STARTER_KIT_DIR = "../Starter_Kit"

_HOME_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def home_path(name: str | None) -> str:
    """The repo-relative home of the desk named `name`; `coordination` for none."""
    name = (name or "").strip()
    if not name:
        return COORDINATION
    if not _HOME_NAME.match(name):
        raise ValueError(
            f"{HOME_ENV}={name!r} is not a desk home name: lowercase letters, "
            f"digits and dashes, named for the job, e.g. nola-sweets")
    return f"{DESKS_DIR}/{name}"


def use_home(name: str | None) -> None:
    """Point this module at the desk home `name` (None or "" = `coordination`)."""
    global HOME, RECORD, DONE_DIR, DESK_LOG, CLOSED_DIR, DESK_OWNS
    HOME = home_path(name)
    RECORD = REPO / HOME / "desk_record.json"
    DONE_DIR = REPO / HOME / "done"
    DESK_LOG = REPO / HOME / "desk_log.md"
    CLOSED_DIR = REPO / HOME / "closed"
    DESK_OWNS = (HOME,) if HOME == COORDINATION else (HOME, SHARED_LAUNCH_RECORD)


def home_name() -> str | None:
    """This desk's home name as `desk_home.py` takes it; None for `coordination/`."""
    return None if HOME == COORDINATION else HOME.rsplit("/", 1)[-1]


try:
    use_home(os.environ.get(HOME_ENV))
    HOME_PROBLEM: str | None = None
except ValueError as _exc:
    use_home(None)
    HOME_PROBLEM = str(_exc)

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

#: The document gate, and the flag that scopes it to a lane's own files. On
#: desk rules-check (2026-10-27) every `done:` ran the gate on the whole tree,
#: and one lane's digest over budget failed three finished lanes' report-done
#: (`kb/desk-done-gate-blocks-on-other-lanes.md`). A lane's gate names its
#: sheet's `owns:` paths; the whole tree is `desk_save.py`'s to measure.
DOC_GATE = "check_docs.py"
ONLY_FLAG = "--only"


def doc_gate_problem(command: str, owns: Sequence[str]) -> str | None:
    """Why this `done:` command runs the document gate on more, or less, than
    the sheet's `owns:` paths; None when it is not the gate or is scoped to
    exactly them -- every `--only` path inside `owns:`, every `owns:` path
    reached by one."""
    words, why = command_words(command)
    if why:
        return None
    gate = next((n for n, word in enumerate(words[1:], start=1)
                 if word.replace("\\", "/").rsplit("/", 1)[-1] == DOC_GATE), None)
    if gate is None:
        return None
    scoped = f"{words[0]} {words[gate]} {ONLY_FLAG} {' '.join(owns)}"
    named: list[str] | None = None
    rest = words[gate + 1:]
    for n, word in enumerate(rest):
        if word.startswith(ONLY_FLAG + "="):
            named = (named or []) + [word.split("=", 1)[1]]
        elif word == ONLY_FLAG:
            named = named or []
            for value in rest[n + 1:]:
                if value.startswith("-"):
                    break
                named.append(value)
    if not named:
        return (f"it runs the document gate on the whole tree, so another lane's "
                f"unfinished document fails this lane's report-done. Scope it to "
                f"the sheet's `owns:`: `{scoped}` -- the whole-tree gate runs at "
                f"the desk's save")
    try:
        paths = [clean_path(p) for p in named]
    except DeskError as exc:
        return f"its `{ONLY_FLAG}` {exc}"
    outside = [p for p in paths if not any(covers(owned, p) for owned in owns)]
    if outside:
        return (f"its `{ONLY_FLAG}` names {', '.join(outside)}, which the sheet's "
                f"`owns:` does not list; a lane's gate measures its own files. "
                f"Write `{scoped}`")
    left_out = [owned for owned in owns if not any(covers(p, owned) for p in paths)]
    if left_out:
        return (f"its `{ONLY_FLAG}` leaves out {', '.join(left_out)}, which the "
                f"sheet owns, so a document there is never measured before the "
                f"save. Write `{scoped}`")
    return None

#: What names a COMMAND in a `done:` block: a script or interpreter, pytest, or
#: git with a subcommand. Lifted from Fantasy Football, where it was measured
#: against fifty real briefs: backticks are not required, because the defect is
#: a `done:` that names NO measurement, not one that is unquoted.
RUNNABLE = re.compile(r"\.(?:py|exe)\b|\bpytest\b|\bgit\s+[a-z][a-z-]*\b")

# --- the done shell (the docstring's THE DONE SHELL) --------------------------

#: A template placeholder the desk was meant to fill: `<lane>`, `<home>`,
#: `<N>`, `<YYYY-MM-DD>`, `<venv python>`. A letter first and a letter or digit
#: last, so `x<5 and y>2`, `a < b`, a redirect (`> out.txt`) and a closing tag
#: (`</b>`) are never one.
_PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9 _'-]*(?<=[A-Za-z0-9])>")
#: What sits beside a placeholder that stands in for part of a PATH:
#: `S<N>/`, `_<PC>_`, `<YYYY-MM-DD>.md`.
_PATH_BEFORE = ("/", "_")
_PATH_AFTER = re.compile(r"[/_]|\.[A-Za-z0-9]")
#: A quoted shell argument that is a Python program: `python.exe -c "..."`.
_PROGRAM_FLAG = re.compile(r"(?:^|\s)-c\s*$")
#: A string in a program handed to a call as its first argument -- `open('`,
#: `glob.glob('`, `exists(f'` -- and one being tested rather than used.
_CALL_OPEN = re.compile(r"\(\s*[rRbBfFuU]{0,2}$")
_COMPARED = re.compile(r"\s*(?:not\s+in\b|in\b|[=!]=)")
#: A list marker opening a `done:` line: `- `, `* `, `1. `, `2) `.
_LIST_MARK = re.compile(r"^(?:[-*]|\d+[.)])\s+")
#: What a shell would act on outside quotes. None of it happens here, so a
#: command that needs one is refused rather than run as something else.
_SHELL_CHARS = {"|": "a pipe", "&": "`&` or `&&`", ";": "`;`", "<": "a redirect",
                ">": "a redirect", "`": "a backtick substitution"}
_VARIABLE = re.compile(r"\$[({A-Za-z_]")
_FIRST_WORD = re.compile(r"""^(?:"([^"]*)"|'([^']*)'|(\S+))""")
#: A first word that is a program: a path or name ending `.exe`, or one of these.
PROGRAM_WORDS = ("git", "pytest", "python", "python3", "py")
#: How long one `done:` command may run before it is killed and fails.
DONE_TIMEOUT = 1800
#: The exit a command that could not be started is recorded with.
NOT_RUN_EXIT = 127


def quote_contexts(line: str) -> list[tuple[int | None, bool, int | None]]:
    """For each character of a command line: where the shell-quoted span it
    sits in opened (None outside quotes), whether that span is a `-c` program,
    and where the program's string it sits in opened (None outside one).
    Shell-style, read loosely: a backslash inside double quotes escapes the
    next character."""
    contexts: list[tuple[int | None, bool, int | None]] = []
    shell_quote, shell_open, program = "", None, False
    string_quote, string_open = "", None
    escaped = False
    for index, ch in enumerate(line):
        if not shell_quote:
            contexts.append((None, False, None))
            if ch in "'\"":
                shell_quote, shell_open = ch, index
                program = _PROGRAM_FLAG.search(line[:index]) is not None
            continue
        contexts.append((shell_open, program, string_open if string_quote else None))
        if escaped:
            escaped = False
        elif ch == "\\" and shell_quote == '"':
            escaped = True
        elif ch == shell_quote:
            shell_quote, string_quote, string_open = "", "", None
        elif program and string_quote:
            if ch == string_quote:
                string_quote, string_open = "", None
        elif program and ch in "'\"":
            string_quote, string_open = ch, index
            contexts[-1] = (shell_open, program, index)
    return contexts


def placeholders_left(done: str) -> list[str]:
    """Every template placeholder left in a `done:` command line, in order.

    A placeholder counts when it is an ARGUMENT: bare (`--lane <lane>`,
    `<home>/done/...`), or part of a quoted path (`"records/<N>.md"`). Inside
    a `-c` program it counts only in a PATH HANDED TO A CALL
    (`open('records/<N>/x.md')`), never in a string the check TESTS FOR (`'<lane>'
    in text`) -- and Python's own `<` and `>` (`len(t)<n and m>0`) are not
    placeholders. Prose in a `done:` block is not a command and is not read.
    """
    found: list[str] = []
    for line in done.splitlines():
        if RUNNABLE.search(line) is None:
            continue
        contexts = quote_contexts(line)
        for mark in _PLACEHOLDER.finditer(line):
            shell_open, program, string_open = contexts[mark.start()]
            path_part = (line[mark.start() - 1:mark.start()] in _PATH_BEFORE
                         or _PATH_AFTER.match(line, mark.end()) is not None)
            if shell_open is None:
                counts = True
            elif not program:
                counts = path_part
            elif string_open is None:
                counts = False
            else:
                close = line.find(line[string_open], mark.end())
                after = line[close + 1:] if close != -1 else ""
                counts = (path_part
                          and _CALL_OPEN.search(line[:string_open]) is not None
                          and _COMPARED.match(after) is None)
            if counts:
                found.append(mark.group(0))
    return found


def is_program(word: str) -> bool:
    name = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name.endswith(".exe") or name in PROGRAM_WORDS


def done_commands(done: str) -> list[str]:
    """The commands a `done:` block names, in order: a line that opens with a
    backtick is the span inside it (`` `cmd` exits 0 ``), any other line is
    whole, a list marker dropped. It is a command when RUNNABLE finds one in
    it AND it opens with a program; anything else is prose and is not run. A
    parenthesized note -- a paragraph opening `(` through the line that closes
    it -- is prose on every line, whatever a line of it opens with."""
    found: list[str] = []
    in_note = False
    for line in done.splitlines():
        stripped = line.strip()
        if not stripped:
            in_note = False
            continue
        if in_note or stripped.startswith("("):
            in_note = not re.search(r"\)[.;:]?$", stripped)
            continue
        text = _LIST_MARK.sub("", stripped)
        if text.startswith("`"):
            close = text.find("`", 1)
            text = text[1:close] if close > 0 else text[1:]
        text = text.strip()
        first = _FIRST_WORD.match(text)
        if (text and RUNNABLE.search(text) and first
                and is_program(next(g for g in first.groups() if g is not None))):
            found.append(text)
    return found


def command_words(command: str) -> tuple[list[str] | None, str | None]:
    """(the words the done shell runs, None), or (None, why it cannot)."""
    contexts = quote_contexts(command)
    for index, ch in enumerate(command):
        if contexts[index][0] is not None:
            continue
        if ch in _SHELL_CHARS:
            return None, (f"it needs a shell for {_SHELL_CHARS[ch]} (`{ch}` outside "
                          f"quotes), and report-done runs no shell: run the one "
                          f"command, unpiped")
        if ch == "\\":
            return None, ("it carries a backslash outside quotes, which POSIX word "
                          "rules read as an escape: write the path with forward slashes")
        if ch == "$" and _VARIABLE.match(command, index):
            return None, "it names a shell variable, and report-done expands none"
    try:
        words = shlex.split(command, posix=True)
    except ValueError as exc:
        return None, f"its quotes do not close ({exc})"
    if not words:
        return None, "it is empty"
    if not is_program(words[0]):
        return None, (f"its first word `{words[0]}` is not a program: open the line "
                      f"with the interpreter or git, or put prose outside the backticks")
    return words, None


def command_problem(command: str) -> str | None:
    """Why the stamp refuses this `done:` command, or None: it does not split
    into words under the done shell, or it runs a git subcommand the lane
    guard refuses -- a command run by `report-done` never meets the guard."""
    _words, why = command_words(command)
    if why:
        return why
    from lane_guard import REFUSED, refused_subcommands
    refused = refused_subcommands(command)
    if refused:
        return (f"it runs `git {refused[0]}`, which a lane never runs: "
                f"{REFUSED[refused[0]]}")
    return None


def resolve_program(program: str, repo: Path) -> str | None:
    """The program's full path: a path with a slash from the project root
    (Windows resolves a relative program against the CALLER's folder, not the
    one it is started in), a bare name from PATH; None when there is none."""
    path = program.replace("\\", "/")
    if "/" in path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = repo / candidate
        return str(candidate) if candidate.is_file() else None
    return shutil.which(program)


def dry_run(command: str, repo: Path | None = None) -> tuple[list[str] | None, str | None]:
    """Everything `report-done` does to a command but run it: (the argv it
    would start, None), or (None, why it cannot start)."""
    repo = REPO if repo is None else repo
    why = command_problem(command)
    if why:
        return None, why
    words, _ = command_words(command)
    program = resolve_program(words[0], repo)
    if program is None:
        return None, f"no program `{words[0]}` from {repo.as_posix()}"
    return [program, *words[1:]], None


def run_done_command(argv: Sequence[str], cwd: Path) -> tuple[int, str]:
    """(exit code, everything it printed, stdout and stderr as they came --
    unbuffered, so a Python program's two streams keep the order it wrote)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    try:
        proc = subprocess.run(list(argv), cwd=str(cwd), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                              env=env, timeout=DONE_TIMEOUT, check=False)
    except subprocess.TimeoutExpired as exc:
        said = (exc.output or b"").decode("utf-8", "replace").replace("\r\n", "\n")
        return -1, said + f"\n[report-done: killed after {DONE_TIMEOUT} seconds]\n"
    except OSError as exc:
        return NOT_RUN_EXIT, f"[report-done: could not start it: {exc}]\n"
    return proc.returncode, proc.stdout.decode("utf-8", "replace").replace("\r\n", "\n")

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


def kit_root() -> Path | None:
    """The Starter Kit's root as this machine spells it, or None when the
    folder `STARTER_KIT_DIR` names is not here."""
    root = (REPO / STARTER_KIT_DIR).resolve()
    return root if root.is_dir() else None


def kit_rel(path: str) -> str | None:
    """Where a path `clean_path` returned sits inside the kit repo, or None
    when it is not a kit path."""
    root = kit_root()
    if root is None:
        return None
    top = root.as_posix()
    if path.casefold().startswith(top.casefold() + "/"):
        return path[len(top) + 1:]
    return None


def kit_path(path: str) -> str | None:
    """`path` (forward slashes) in the one form a kit path is written in --
    the kit root's own spelling, `/`, the path inside the kit -- or None when
    it does not point inside the kit. Absolute, or from the project root
    through `..`; anything else is a project path and None."""
    parts = path.split("/")
    absolute = path.startswith("/") or ":" in parts[0]
    if not absolute and ".." not in parts:
        return None
    root = kit_root()
    if root is None:
        return None
    full = Path(os.path.normpath(Path(path) if absolute else REPO / path)).as_posix()
    top = root.as_posix()
    if not full.casefold().startswith(top.casefold() + "/"):
        return None
    inside = full[len(top) + 1:]
    if inside.split("/")[0].casefold() == ".git":
        raise DeskError(f"{path!r} is inside the Starter Kit's `.git`, which no lane owns")
    return f"{top}/{inside}"


def kit_root_text() -> str:
    root = kit_root()
    return (root.as_posix() if root is not None
            else f"{STARTER_KIT_DIR} from the project root, which is not on this machine")


def clean_path(raw: str) -> str:
    """A repo-relative path, forward slashes, no trailing slash -- a path
    inside the Starter Kit in its one form (`kit_path`) -- or a refusal.

    Repo-relative is a format rule, not a preference: a path outside the
    project sends a lane at a folder the harness stops to ask the owner
    about, with nobody at that screen. The kit is the one exception (the
    docstring's THE STARTER KIT): the opener adds its folder to a lane that
    owns a kit path, so no pop-up stops it.
    """
    path = raw.strip().strip("`").replace("\\", "/").rstrip("/")
    while path.startswith("./"):
        path = path[2:]
    kit = kit_path(path) if path else None
    if kit is not None:
        return kit
    parts = path.split("/")
    if (not path or path == "." or path.startswith("/") or ":" in parts[0]
            or ".." in parts or parts[0] == ".git"):
        raise DeskError(
            f"{raw!r} is not a path inside this project. Paths are "
            f"repo-relative (e.g. records/2025/March.md), never absolute, "
            f"never `..`, never the whole project. The one root outside it a "
            f"path may name is the Starter Kit's ({kit_root_text()}), and a "
            f"path inside it, never the kit itself"
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


# --- the other desks --------------------------------------------------------


def other_desks() -> dict[str, dict]:
    """Every OTHER live desk's record, by its home: the one at `coordination/`
    and each under `coordination/desks/<name>/`, this desk's own left out. An
    unreadable record is skipped here -- it is that desk's to repair, and its
    own acts say so."""
    found: dict[str, dict] = {}
    candidates = [REPO / COORDINATION / "desk_record.json",
                  *sorted((REPO / DESKS_DIR).glob("*/desk_record.json"))]
    for path in candidates:
        home = path.parent.relative_to(REPO).as_posix()
        if home == HOME:
            continue
        try:
            record = read_record(path)
        except DeskError:
            continue
        if record is not None:
            found[home] = record
    return found


def home_of(path: str, homes: Sequence[str]) -> str | None:
    """The most specific of `homes` that holds `path`, or None."""
    holding = [home for home in homes if covers(home, path)]
    return max(holding, key=len) if holding else None


def another_desks_claim(path: str, others: dict[str, dict] | None = None) -> str | None:
    """Why `path` is another live desk's, or None when it is no other desk's.

    Another desk's own home (its record, sheets, done files), and any file one
    of its lanes or its desk row holds outside `coordination/`. Inside
    `coordination/` only the homes decide: the shared launch record is owned by
    every homed desk by name, and a desk at `coordination/` owns the whole
    folder, so ownership rows there would make every desk claim every other's.
    """
    others = other_desks() if others is None else others
    home = home_of(path, [HOME, *others])
    if home is not None and home != HOME:
        return f"desk {others[home].get('desk')!r} ({home}): {others[home].get('job')}"
    if covers(COORDINATION, path):
        return None
    for home, record in others.items():
        for lane, row in record["lanes"].items():
            if any(covers(owned, path) for owned in row.get("owns", [])):
                return (f"desk {record.get('desk')!r} ({home}), lane {lane}: "
                        f"{record.get('job')}")
    return None


def other_desks_collisions(paths: Sequence[str]) -> list[str]:
    """A path given here that sits inside, or above, a file another live desk
    holds. Two desks never hand out one file."""
    hits: list[str] = []
    for home, record in other_desks().items():
        for path in paths:
            for lane, row in record["lanes"].items():
                for owned in row.get("owns", []):
                    if covers(COORDINATION, owned):
                        continue
                    if overlap(path, owned):
                        hits.append(f"{path} overlaps {owned}, which is {lane}'s "
                                    f"at desk {record.get('desk')!r} ({home})")
    return hits


def another_desks_lane(name: str) -> str | None:
    """Which other live desk has `name` as an unclosed lane, or None. The
    opener asks before a close: a lane is closed by its own desk, whose record
    the close updates -- closed from here, its row would stay open for good."""
    if name == DESK_LANE:
        return None
    for home, record in other_desks().items():
        row = record["lanes"].get(name)
        if row is not None and not is_closed(row):
            return f"desk {record.get('desk')!r} ({home})"
    return None


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


def require_home() -> None:
    if HOME_PROBLEM:
        raise DeskError(HOME_PROBLEM)


def require_record() -> dict:
    require_home()
    record = read_record()
    if record is None:
        raise DeskError(
            f"there is no desk record in {HOME}/, so there is no desk here. The "
            f"owner starts one by typing /desk in a window of their own, and "
            f"that window runs `desk_record.py open-desk` through `scripts/"
            f"desk_home.py <home>`. A desk's tools always run through that "
            f"wrapper; a bare desk command reads `coordination/`, where no new "
            f"desk opens. Desks on file: {sorted(other_desks()) or 'none'}"
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


def kit_changed() -> list[str]:
    """Every path git lists as changed or untracked in the Starter Kit's repo,
    in the one form a kit path is written in (`kit_path`); none when the kit
    or its repo is not on this machine."""
    root = kit_root()
    if root is None or not (root / ".git").exists():
        return []
    try:
        inside = git_changed(root)
    except DeskError as exc:
        raise DeskError(f"in the Starter Kit ({root.as_posix()}): {exc}") from exc
    return [f"{root.as_posix()}/{path}" for path in inside]


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
    AFTERWARDS no longer matches its stamp and is checked like any other. The
    Starter Kit's changes are taken the same way, each by its kit path."""
    repo = REPO if repo is None else repo
    baseline = {path: file_stamp(repo, path) for path in git_changed(repo)
                if not covers(COORDINATION, path)}
    baseline.update({path: file_stamp(repo, path) for path in kit_changed()})
    return baseline


def changed_since_baseline(record: dict, repo: Path | None = None) -> list[str]:
    """What changed since the desk opened: the project's files, then the
    Starter Kit's, each by its kit path (the docstring's THE STARTER KIT)."""
    repo = REPO if repo is None else repo
    baseline = record.get("baseline", {})
    return [path for path in git_changed(repo) + kit_changed()
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
            "command `report-done` runs and records -- never prose like "
            "\"the text reads correctly\", which is settled by whoever is "
            "asked last"
        )
    left_in = placeholders_left(fields["done"])
    if left_in:
        problems.append(
            f"`done:` still carries the template placeholder(s) "
            f"{', '.join(dict.fromkeys(left_in))}. The command fails when "
            f"report-done runs it, after the work is done -- fill each one in "
            f"with the real value"
        )
    commands = done_commands(fields["done"])
    if RUNNABLE.search(fields["done"]) and not commands:
        problems.append(
            "`done:` names a command only inside prose. `report-done` runs a line "
            "that opens with the command, or the span inside a line's opening "
            "backticks -- start the line with the command"
        )
    for command in commands:
        if placeholders_left(command):
            continue
        why = command_problem(command)
        if why:
            problems.append(f"`done:` command `{command}` cannot be run by "
                            f"`report-done` as written: {why}")
            continue
        why = doc_gate_problem(command, owns)
        if why:
            problems.append(f"`done:` command `{command}` is refused: {why}")
    for line in whole_suite_lines(fields["done"]):
        problems.append(
            f"`done:` runs the whole test suite: `{line}`. Name the lane's own "
            f"test files (`pytest tests/test_<x>.py`) -- a whole-tree run takes "
            f"minutes per lane and reports every other lane's breakage as this "
            f"lane's"
        )
    # The lane budget: a unit too big for one window is split here, before it
    # opens -- never after it compacts (`scripts/lane_budget.py`).
    from lane_budget import budget_problem
    over = budget_problem(text, repo)
    if over:
        problems.append(over)
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


# --- the desk's own load (the docstring's THE DESK PLANS ITS LOAD) ----------

#: The context window, `context_meter.WINDOW_TOKENS` (measured; a test holds
#: the two equal). Not imported: every desk command loads this module, and the
#: meter is read only when a reading is wanted.
WINDOW_TOKENS = 1_000_000

#: The line a window is planned under and the ceiling one that cannot be cut
#: may be planned to (FACOWORK desk decision DB1, its owner's words: "60% is the
#: target we can hit 70% for the right reasons"). The stamp refuses at
#: CEILING_PERCENT always, and from LINE_PERCENT unless the plan put this
#: window past 60% on purpose.
LINE_TOKENS = 600_000
CEILING_TOKENS = 700_000
LINE_PERCENT = 60
CEILING_PERCENT = 70

#: What a window carries on its first turn, before it reads anything (system
#: prompt, CLAUDE.md, memory, tools). Measured here: 30 windows of this project
#: since 2026-11-01 carried 36,869-43,540 on their first turn (median 37,301);
#: the largest is taken, so a plan never under-prices a start. FACOWORK's was
#: 69,000.
START_TOKENS = 43_540

#: What one lane costs the desk: its sheet written, stamped, opened, its ack,
#: its questions, its receipts read, its close. FACOWORK's segment A was 9,600 a
#: lane before its cuts (receipts by script, no ack, log rows by script,
#: generated sheets) and 4,700 after; this desk has the first and the third of
#: those and not the other two -- its sheets are written by hand and every lane
#: acks -- so it takes the figure before the cuts. UNTIL CALIBRATED: no desk of
#: this project has been measured lane by lane yet.
PER_LANE_TOKENS = 9_600

#: Tokens per byte of what the desk still reads (`plan --reading`): FACOWORK's
#: K_READ_UNMEASURED, its fit for a desk whose reading it had not measured.
K_READ = 0.61

#: Margin in every prediction for the work no plan names (a re-cut sheet, a
#: long ruling): FACOWORK's RESERVE_TOKENS.
RESERVE_TOKENS = 50_000

PLAN_CHANGED = "PLAN CHANGED"
PLANNED_HANDOVER = "PLANNED HANDOVER"
NO_PLAN = "NO PLAN"
REPLAN = "REPLAN"
METER_UNREADABLE = "METER UNREADABLE — "


class PlanCheck:
    """What the plan says about stamping one more lane now. `ok` False is a
    refusal (`code` NO PLAN, REPLAN or PLANNED HANDOVER); True is OK or PLAN
    CHANGED, the latter carrying the window's new lane count and prediction
    for the caller to write."""

    def __init__(self, ok: bool, code: str, message: str, *, window: int | None = None,
                 planned_past_60: bool = False, projected: int | None = None,
                 new_lanes: int | None = None, predicted_from: str | None = None):
        self.ok, self.code, self.message = ok, code, message
        self.window, self.planned_past_60 = window, planned_past_60
        self.projected, self.new_lanes = projected, new_lanes
        self.predicted_from = predicted_from


def _number(n: int) -> str:
    return {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def reading_bytes(paths: Sequence[str]) -> int:
    total = 0
    for rel in paths:
        path = REPO / rel
        if path.is_dir():
            total += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        elif path.is_file():
            total += path.stat().st_size
        else:
            raise DeskError(f"--reading {rel}: nothing there to read. Nothing was planned")
    return total


def ends_after(windows: Sequence[dict]) -> list[int]:
    """The cumulative lane count each window but the last hands over after."""
    ends, total = [], 0
    for w in list(windows)[:-1]:
        total += int(w.get("lanes", 0))
        ends.append(total)
    return ends


def make_plan(lanes: int, reading: int = 0, *, tokens_now: int | None = None) -> dict:
    """How many lanes each window of this job takes (FACOWORK's
    `desk_plan.generic_plan`): (LINE - the load now - K_READ x bytes still to
    read - the reserve) / PER_LANE_TOKENS. The first window starts from the
    meter when it can be read, else from START_TOKENS plus its reading; every
    later window from START_TOKENS plus the reading. A window that cannot take
    one lane under the line takes one to the ceiling, marked past 60%; not even
    that is refused."""
    if lanes < 0:
        raise DeskError("--lanes is how many lanes this job still opens: 0 or more")
    reading_tokens = K_READ * reading

    def capacity(base: float, line: int) -> int:
        return int((line - base - RESERVE_TOKENS) // PER_LANE_TOKENS)

    first_base = tokens_now if tokens_now is not None else START_TOKENS + reading_tokens
    next_base = START_TOKENS + reading_tokens
    windows, left, k = [], lanes, 1
    while True:
        base = first_base if k == 1 else next_base
        cap, past = capacity(base, LINE_TOKENS), False
        if cap < 1 and left > 0:
            if capacity(base, CEILING_TOKENS) < 1:
                raise DeskError(
                    f"window {k} cannot take one lane even at the {CEILING_TOKENS:,}-"
                    f"token ceiling: it starts at {int(base):,} with the reserve "
                    f"{RESERVE_TOKENS:,} and {PER_LANE_TOKENS:,} a lane. Cut what the "
                    f"desk reads, or hand this window over now. Nothing was planned")
            cap, past = 1, True
        take = min(max(cap, 0), left)
        predicted = int(round(base + PER_LANE_TOKENS * take + RESERVE_TOKENS))
        windows.append({"k": k, "lanes": take, "predicted": predicted,
                        "past_60": past or predicted > LINE_TOKENS})
        left -= take
        if left <= 0:
            break
        k += 1
        if k > 50:
            raise DeskError("more than 50 windows: cut the job. Nothing was planned")
    ends = ends_after(windows)
    if len(windows) == 1:
        said = "This job fits in one desk window."
    elif len(ends) == 1:
        said = (f"This job takes {_number(len(windows))} desk windows; after the "
                f"{_ordinal(ends[0])} lane I'll ask you to open a fresh desk window.")
    else:
        said = (f"This job takes {_number(len(windows))} desk windows; after lanes "
                f"{', '.join(str(e) for e in ends[:-1])} and {ends[-1]} I'll ask you to "
                f"open a fresh desk window each time.")
    for w in windows:
        if w["past_60"]:
            said += (f" Window {w['k']} is planned past 60% "
                     f"({100 * w['predicted'] / WINDOW_TOKENS:.0f}%); it stops for "
                     f"certain at 70%.")
    return {"lanes": lanes, "reading_bytes": reading, "per_lane": PER_LANE_TOKENS,
            "tokens_at_plan": tokens_now, "windows": windows, "ends_after": ends,
            "owner_line": said, "planned_at": now_iso(), "window": 1}


def window_tag(plan: dict, k: int) -> str:
    return f"{plan.get('planned_at', '')}#{k}"


def plan_window_row(plan: dict, k: int) -> dict | None:
    return next((w for w in plan.get("windows", []) if w.get("k") == k), None)


def opened_in_window(record: dict, plan: dict, k: int) -> int:
    tag = window_tag(plan, k)
    return sum(1 for name, row in record["lanes"].items()
               if name != DESK_LANE and row.get("plan_window") == tag)


def window_line(plan: dict, k: int) -> str:
    w = plan_window_row(plan, k) or {}
    return (f"window {k} of {len(plan.get('windows', []))} of this job's plan: "
            f"{w.get('lanes', '?')} lane(s), predicted {w.get('predicted', 0):,}"
            + (" — planned past 60%" if w.get("past_60") else ""))


def advance_window(record: dict) -> str | None:
    """On an inherit: a desk whose window opened every lane it was planned for
    goes on as the next window (the PLANNED HANDOVER's successor); one that
    died mid-window goes on as the same window. The line to print."""
    plan = record.get("plan")
    if not plan:
        return None
    k = int(plan.get("window") or 1)
    w = plan_window_row(plan, k)
    if w and opened_in_window(record, plan, k) >= w["lanes"] and plan_window_row(plan, k + 1):
        plan["window"] = k = k + 1
    return window_line(plan, k)


def desk_meter() -> tuple[str | None, int | None, float | None] | None:
    """(this window's name, tokens, percent of its window) as the context
    meter reads the window running this process; tokens and percent None when
    it cannot be read. None under pytest: a test runs inside whatever window
    launched it, which is not a desk -- a test that wants a reading
    monkeypatches this function."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        return None
    try:
        import context_meter
        session = context_meter.this_window()
        if session is None:
            return None, None, None
        state = context_meter.window_state(session)
        return state["name"], state["tokens"], state["percent"]
    except Exception:  # noqa: BLE001 -- a meter never breaks the act it rides on
        return None, None, None


def plan_command(desk: str, lanes: str = "<the lanes this job still opens>") -> str:
    home = home_name() or "<home>"
    return (f"`<venv python> scripts/desk_home.py {home} desk_record.py plan --lanes "
            f"{lanes} [--reading <what the desk still reads>] --desk {desk}`")


def handover_text(desk: str, why: str) -> str:
    home = home_name() or "<home>"
    return (f"{why} Hand over now:\n"
            f"  1. write the desk log's `## Handover` section: the job, each open "
            f"lane and what it is doing, what is owed next\n"
            f"  2. tell the owner in one plain line: close this desk's tab, then type "
            f"`/desk` in a fresh window and say \"take over desk {home}\"; it inherits "
            f"this record (`open-desk --inherit`) and stamps this sheet itself.\n"
            f"Live lanes keep working. Nothing was stamped.")


def generic_check(plan: dict, window: int, opened: int, tokens: int | None,
                  desk: str = "<you>") -> PlanCheck:
    """May window `window`, having opened `opened` lanes, stamp one more? The
    planned count is a prediction, never a stop on its own (FACOWORK's owner,
    on a desk refused its 10th lane at about 26%: "feels like more babysitting
    with out value add"). Past it, the load with one more lane is re-predicted:
    under the line, PLAN CHANGED; over it, PLANNED HANDOVER. Under the count,
    a meter that says the rest no longer fits is a REPLAN."""
    w = plan_window_row(plan, window)
    if w is None:
        return PlanCheck(False, REPLAN,
                         f"{REPLAN} — window {window} is past the plan's "
                         f"{len(plan.get('windows', []))} window(s): re-plan the lanes "
                         f"this job has left, {plan_command(desk)}. Nothing was stamped.",
                         window=window)
    past = bool(w.get("past_60"))
    line = CEILING_TOKENS if past else LINE_TOKENS
    per_lane = int(plan.get("per_lane") or PER_LANE_TOKENS)
    if opened >= int(w["lanes"]):
        new = opened + 1
        if tokens is not None:
            projected = int(round(tokens + per_lane + RESERVE_TOKENS))
            how = f"{tokens:,} now + one more lane {per_lane:,} + reserve {RESERVE_TOKENS:,}"
            source = "meter"
        else:
            projected = int(w["predicted"]) + per_lane * (new - int(w["lanes"]))
            how = (f"the plan's {int(w['predicted']):,} for {w['lanes']} lane(s) + "
                   f"{new - int(w['lanes'])} more x {per_lane:,} (the meter unreadable)")
            source = "plan"
        percent = 100 * projected / WINDOW_TOKENS
        if projected <= line:
            return PlanCheck(True, PLAN_CHANGED,
                             f"{PLAN_CHANGED} — window {window} was planned for "
                             f"{w['lanes']} lane(s) and has opened {opened}; {how} = "
                             f"{projected:,} ({percent:.1f}%), under {line:,}: window "
                             f"{window} now takes {new} lane(s), predicted {projected:,}",
                             window=window, planned_past_60=past, projected=projected,
                             new_lanes=new, predicted_from=source)
        return PlanCheck(False, PLANNED_HANDOVER, handover_text(
            desk, f"{PLANNED_HANDOVER} — window {window} was planned for {w['lanes']} "
                  f"lane(s) and has opened {opened}, and one more does not fit: {how} = "
                  f"{projected:,} ({percent:.1f}%), past {line:,}."),
            window=window, planned_past_60=past, projected=projected,
            predicted_from=source)
    if tokens is None:
        return PlanCheck(True, "OK", f"{METER_UNREADABLE}{desk}", window=window,
                         planned_past_60=past)
    left = int(w["lanes"]) - opened
    projected = int(round(tokens + per_lane * left + RESERVE_TOKENS))
    if projected <= line:
        return PlanCheck(True, "OK", f"window {window}: {projected:,} projected",
                         window=window, planned_past_60=past, projected=projected)
    earlier = sum(int(x["lanes"]) for x in plan.get("windows", []) if x["k"] < window)
    job_left = max(int(plan.get("lanes", 0)) - earlier - opened, 1)
    return PlanCheck(False, REPLAN,
                     f"{REPLAN} — this window's plan no longer fits: {tokens:,} now + "
                     f"{left} planned lane(s) x {per_lane:,} + reserve {RESERVE_TOKENS:,} "
                     f"= {projected:,}, past {line:,}, so its handover comes earlier than "
                     f"planned. Re-plan the {job_left} lane(s) the job has left from "
                     f"where this window stands, {plan_command(desk, str(job_left))}, "
                     f"tell the owner the line it prints, then stamp this lane again. "
                     f"Nothing was stamped.", window=window, planned_past_60=past,
                     projected=projected)


def plan_check(record: dict, desk: str, lane: str, tokens: int | None) -> PlanCheck:
    """What the plan says about stamping `lane` now. A desk with no plan
    stamps nothing: it plans first, and a desk opened before plans existed
    plans the lanes it has left."""
    plan = record.get("plan")
    if not plan:
        return PlanCheck(False, NO_PLAN,
                         f"{NO_PLAN} — this desk has not planned its own load, so no "
                         f"lane is stamped yet. Plan the lanes this job still opens: "
                         f"{plan_command(desk)}, and tell the owner the line it prints. "
                         f"Nothing was stamped.")
    k = int(plan.get("window") or 1)
    opened = opened_in_window(record, plan, k)
    existing = record["lanes"].get(lane)
    if existing and not is_closed(existing) and existing.get("plan_window") == window_tag(plan, k):
        # A re-stamp is the same lane, not one more.
        w = plan_window_row(plan, k)
        opened = min(opened, max(int((w or {}).get("lanes", 1)) - 1, 0))
    return generic_check(plan, k, opened, tokens, desk)


def handover_problem(desk: str, planned_past_60: bool, reading) -> tuple[str | None, str | None]:
    """(why the stamp refuses for the desk's own fill, a METER UNREADABLE
    line) -- each None when it does not apply. The backstop: the plan should
    act first, so a refusal here is a calibration miss. An unreadable meter
    never refuses."""
    if reading is None:
        return None, None
    _name, tokens, percent = reading
    if percent is None:
        return None, f"{METER_UNREADABLE}{desk}"
    line = CEILING_PERCENT if planned_past_60 else LINE_PERCENT
    if percent < line:
        return None, None
    why = (f"at or past the {CEILING_PERCENT}% line" if line == CEILING_PERCENT
           else f"at or past the {LINE_PERCENT}% line, and its plan did not put this "
                f"window past 60%")
    return handover_text(desk, f"the desk {desk} holds {tokens:,} tokens, {percent}% of "
                               f"its window -- {why}, so it stamps no more lanes. This "
                               f"is the backstop; the plan should have acted first."), None


def change_plan(plan: dict, planned: PlanCheck) -> str:
    """A lane let through past its window's planned count: the window's row
    takes the new count and prediction, kept in `changes` beside the numbers
    before. Returns the PLAN CHANGED line."""
    k = int(planned.window or plan.get("window") or 1)
    w = plan_window_row(plan, k)
    before, before_predicted = int(w["lanes"]), int(w.get("predicted", 0))
    w["lanes"], w["predicted"] = int(planned.new_lanes), int(planned.projected)
    plan["lanes"] = sum(int(x.get("lanes", 0)) for x in plan.get("windows", []))
    plan["ends_after"] = ends_after(plan.get("windows", []))
    plan.setdefault("changes", []).append({
        "at": now_iso(), "window": k, "lanes_before": before, "lanes": w["lanes"],
        "predicted_before": before_predicted, "predicted": w["predicted"],
        "predicted_from": planned.predicted_from, "line": planned.message})
    return planned.message


def log_plan_change(line: str) -> None:
    """The PLAN CHANGED line into the desk log -- the owner's record of it,
    with no stop for them."""
    DESK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DESK_LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n## Plan changed, {now_iso()}\n\n{line}\n")


def plan_desk(desk: str, lanes: int, reading: Sequence[str] = ()) -> list[str]:
    """The `plan` act: how many lanes each window of this job takes, written
    into the record -- before the first stamp, or again from where a live desk
    stands (it counts from the meter). A plan replaced is kept in
    `plans_before`; the lanes already stamped count against the new plan's
    first window only from here on."""
    record = require_record()
    require_the_desk(record, desk)
    paths = [clean_path(p) for p in reading]
    meter = desk_meter()
    got = make_plan(lanes, reading_bytes(paths), tokens_now=meter[1] if meter else None)
    got["reading"] = paths
    if record.get("plan"):
        record.setdefault("plans_before", []).append(record["plan"])
    record["plan"] = got
    write_record(record)
    return [*(f"window {w['k']}: {w['lanes']} lane(s), predicted {w['predicted']:,}"
              + (" — planned past 60%" if w["past_60"] else "") for w in got["windows"]),
            f"owner line: {got['owner_line']}"]


# --- the acts ---------------------------------------------------------------


def open_desk(desk: str, job: str, *, inherit: bool) -> list[str]:
    require_home()
    record = read_record()
    if record is not None:
        if not inherit:
            raise DeskError(
                f"a desk record is already on file in {HOME}/: desk "
                f"{record.get('desk')!r}, job {record.get('job')!r}. A NEW job "
                f"opens under a home name of its own -- desks run side by side, "
                f"and this home is taken. Only if that desk's window is gone "
                f"and you are its replacement, run this again with --inherit"
            )
        was = record.get("desk")
        record["desk"] = desk
        record.setdefault("inherited", []).append({"from": was, "to": desk, "at": now_iso()})
        window = advance_window(record)
        write_record(record)
        return [f"{desk} is the desk now (was {was}); job: {record.get('job')}",
                *([f"  {window}"] if window else []), *show_lines(record)]
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
            f"nobody's lane unless they change again",
            f"  next, before the first stamp, plan this job's load: {plan_command(desk)}"]


def stamp(desk: str, lane: str, sheet: str) -> list[str]:
    record = require_record()
    require_the_desk(record, desk)
    if not _SAFE_NAME.match(lane) or lane == DESK_LANE:
        raise DeskError(f"{lane!r} cannot be a lane name")
    path, text = read_sheet(sheet)
    meter = desk_meter()
    planned = plan_check(record, desk, lane, meter[1] if meter else None)
    full, unreadable = handover_problem(desk, planned.planned_past_60, meter)
    if full:
        raise DeskError(full)
    problems = sheet_problems(text)
    if problems:
        raise DeskError(
            f"{path} is not a sheet a lane could finish:\n"
            + "\n".join(f"  - {p}" for p in problems) + "\nNothing was stamped."
        )
    if not planned.ok:
        raise DeskError(planned.message)
    owns = sheet_owns(text)
    hits = collisions(record, lane, owns) + other_desks_collisions(owns)
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
    # A RESTAMP keeps what `own` gave the lane since: the record, not the
    # sheet, is the grant, and a restamp that reset `owns` to the sheet's list
    # silently took four files from a working lane (Savecraft, 2026-11-07).
    # Taking one back is `disown`, an act of its own.
    kept = [p for p in (existing or {}).get("owns", [])
            if not any(covers(o, p) for o in owns)]
    fields = parse_sheet(text)[0]
    at = working_since_now(lane)
    record["lanes"][lane] = {
        "sheet": path, "sha256": sheet_digest(text), "stamped_at": now_iso(),
        "unit": fields["unit"], "reason": fields["reason"].split()[0],
        "owns": owns + kept, "working_since": at, "working_since_iso": now_iso(),
        "closed": None,
    }
    plan = record["plan"]
    row = record["lanes"][lane]
    row["plan_window"] = ((existing or {}).get("plan_window")
                          or window_tag(plan, int(plan.get("window") or 1)))
    changed = change_plan(plan, planned) if planned.code == PLAN_CHANGED else None
    if changed:
        log_plan_change(changed)
    write_record(record)
    return [f"stamped {path} for {lane} ({record['lanes'][lane]['sha256'][:12]}); "
            f"{lane} owns {owns}", *(f"  {line}" for line in moved),
            *([f"  kept, given by `own` since the last stamp: {kept} -- `disown` "
               f"takes one back"] if kept else []),
            *([changed] if changed else []), *([unreadable] if unreadable else [])]


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
        hits = collisions(record, lane, cleaned) + other_desks_collisions(
            [p for p in cleaned if not covers(COORDINATION, p)])
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


def route(desk: str, paths: Sequence[str], ruling: str, log: str | None,
          asked: str | None = None) -> list[str]:
    """The owner's ruling to disk, THEN to every lane it affects (R18, then R6).

    `asked` is the question the ruling answers ("unprompted" when none): a bare
    "1" or "yes" means nothing to a lane without it."""
    record = require_record()
    require_the_desk(record, desk)
    if not ruling.strip():
        raise DeskError("--ruling carries the owner's words, word for word; it cannot be empty")
    if asked is not None and not asked.strip():
        raise DeskError("--asked carries the question the ruling answers, or 'unprompted'; "
                        "it cannot be empty")
    context = ""
    if asked and asked.strip().lower() != "unprompted":
        context = f" (answering: {asked.strip()})"
    cleaned = [clean_path(p) for p in paths]
    log_path = DESK_LOG if log is None else REPO / clean_path(log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"\n## Ruling, {now_iso()}\n\n> {ruling.strip()}\n\n"
                     + (f"Answering: {asked.strip()}\n\n" if asked else "")
                     + f"Affects: {', '.join(cleaned)}\n")
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
        said.append(f"  send to {lane}: [desk] correction: {ruling.strip()}{context} "
                    f"-- affects: {', '.join(cleaned)}")
    if not affected:
        said.append("  no lane owns an affected path; nothing to send")
    write_record(record)
    return said


def receipts_path(lane: str) -> Path:
    """Where `report-done` writes `lane`'s receipts, beside its done file."""
    return DONE_DIR / f"{lane}.receipts.md"


def receipts_text(lane: str, digest: str, ran: str,
                  results: Sequence[tuple[str, int, str]]) -> str:
    """The receipts file: `# Receipts: <lane>`, `sheet: <12>`, `ran: <ISO>`,
    then per command a blank line, `$ <command as the sheet names it>`,
    `exit: <n>` on the very next line, and the bytes it printed."""
    parts = [f"# Receipts: {lane}\n", f"sheet: {digest[:12]}\n", f"ran: {ran}\n"]
    for command, code, printed in results:
        parts.append(f"\n$ {command}\nexit: {code}\n")
        if printed:
            parts.append(printed if printed.endswith("\n") else printed + "\n")
    return "".join(parts)


def report_done(lane: str, *, dry: bool = False) -> list[str]:
    """Run every command the stamped sheet's `done:` names, write the
    receipts, and record the lane done only when every one exited 0 (the
    docstring's RECEIPTS BY SCRIPT). `dry` does everything but run them, and
    records nothing."""
    record = require_record()
    row = lane_row(record, lane)
    problem = stamped_sheet_problem(record, lane)
    if problem:
        raise DeskError(f"{problem}. Tell the desk in one line; nothing was recorded")
    text = (REPO / row["sheet"]).read_text(encoding="utf-8")
    commands = done_commands(parse_sheet(text)[0].get("done", ""))
    if not commands:
        raise DeskError(f"{row['sheet']}'s `done:` names no command report-done can "
                        f"run. Tell the desk in one line; nothing was recorded")
    if dry:
        lines, refused = [], 0
        for command in commands:
            argv, why = dry_run(command)
            lines.append(f"$ {command}")
            if why:
                refused += 1
                lines.append(f"  would not run: {why}")
            else:
                lines.append(f"  would run: {argv}")
        lines.append(f"dry run: {len(commands) - refused} of {len(commands)} command(s) "
                     f"would run from {REPO.as_posix()}; nothing was run or recorded")
        if refused:
            raise DeskError(NL.join(lines))
        return lines
    ran = now_iso()
    results = []
    for command in commands:
        argv, why = dry_run(command)
        if why:
            results.append((command, NOT_RUN_EXIT, f"[report-done: not run: {why}]\n"))
        else:
            code, printed = run_done_command(argv, REPO)
            results.append((command, code, printed))
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    receipts = receipts_text(lane, row["sha256"], ran, results)
    receipts_path(lane).write_text(receipts, encoding="utf-8", newline="\n")
    where = receipts_path(lane).relative_to(REPO).as_posix()
    failed = [command for command, code, _ in results if code != 0]
    if failed:
        raise DeskError(
            f"{receipts}\n{len(failed)} of {len(results)} `done:` command(s) did not "
            f"exit 0: {', '.join(f'`{c}`' for c in failed)}. {lane} is NOT recorded as "
            f"done (receipts in {where}). Fix the work and run report-done again; if it "
            f"cannot pass, that is a `question:` to the desk")
    # Strictly after the lane was last put to work, even inside one clock tick.
    at = max(time.time(), float(row.get("working_since", 0)) + AFTER)
    done_path(lane).write_text(
        json.dumps({"lane": lane, "at": at, "at_iso": now_iso(),
                    "sheet": row["sha256"][:12], "receipts": where}) + "\n",
        encoding="utf-8", newline="\n")
    return [receipts.rstrip("\n"), "",
            f"{lane} is recorded as done: every `done:` command exited 0, receipts in "
            f"{where}. Send the desk ({record.get('desk')}) `done: {lane}, <the paths "
            f"you changed>` and `receipts: {where}`; the desk closes this window, you "
            f"do not"]


def show_lines(record: dict, lane: str | None = None) -> list[str]:
    lines = [f"desk: {record.get('desk')}  job: {record.get('job')}"]
    plan = record.get("plan")
    if not lane:
        lines.append(f"  plan: {window_line(plan, int(plan.get('window') or 1))}" if plan
                     else f"  plan: {NO_PLAN} -- the stamp refuses until the desk plans")
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
    job move under `closed/<stamp>/` in the desk's home."""
    target = archive_desk(desk)
    return [f"desk closed; its record is under {target.relative_to(REPO).as_posix()}"]


def archived_moves(target: Path) -> list[tuple[Path, Path]]:
    """(where each piece of a closed desk lives under `target`, where it lived
    while the desk was open)."""
    return [(target / RECORD.name, RECORD),
            (target / DONE_DIR.name, DONE_DIR),
            (target / "task_sheets", REPO / HOME / "task_sheets"),
            (target / DESK_LOG.name, DESK_LOG)]


def reopen_archived(target: Path) -> None:
    """Undo :func:`archive_desk`: the record, done files, sheets and log move
    back from `target`, and the emptied folder goes.

    For the save whose commit FAILED after it had closed the desk -- a second
    desk committing in the same moment holds git's `index.lock` (FACOWORK,
    session-recap wave 4 paper walk, P-F9). With the record archived, the
    ownership check and the save itself refuse "there is no desk record", and
    the work sits unsaved with nothing to save it by. Restored, `desk_save.py`
    simply runs again.
    """
    moves = [(src, dest) for src, dest in archived_moves(target) if src.exists()]
    in_the_way = [dest.relative_to(REPO).as_posix() for _, dest in moves if dest.exists()]
    if in_the_way:
        raise DeskError(
            f"cannot move the closed desk back from "
            f"{target.relative_to(REPO).as_posix()}: {in_the_way} already exist "
            f"(a desk opened since?). Nothing was moved"
        )
    for src, dest in moves:
        os.replace(src, dest)
    target.rmdir()


def archive_desk(desk: str) -> Path:
    """The move :func:`close_desk` makes; the folder it moved everything to."""
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
    for archived, live in archived_moves(target):
        if live.exists():
            os.replace(live, archived)
    return target


# --- the command line -------------------------------------------------------


#: The acts only the desk performs. Each ends with the stall banner, so the desk
#: is shown a lane stopped at a pop-up by the commands it runs anyway -- it does
#: not have to remember to look (the 2026-09-19 rehearsal, finding 2).
DESK_ACTS = ("open-desk", "plan", "stamp", "own", "disown", "outside", "route")


def no_home_problem(inherit: bool) -> str | None:
    """Why a NEW desk may not open here, or None. Every new desk names a home
    (the docstring's DESKS SIDE BY SIDE); `coordination/` keeps only a record
    left there from before homes, which may still be inherited."""
    if HOME != COORDINATION or (inherit and RECORD.exists()):
        return None
    return (f"a new desk opens in a home of its own, so desks run side by side: "
            f"`<venv python> scripts/desk_home.py <home> desk_record.py open-desk "
            f"--desk <you> --job \"...\"`, <home> a short name for the job "
            f"(lowercase letters, digits, dashes), and every later desk command "
            f"through the same wrapper. Homes on file: "
            f"{sorted(other_desks()) or 'none'}. Nothing was opened")


def live_desk_problem(record: dict, actor: str) -> str | None:
    """Why `actor` may not inherit `record`, or None. A desk whose window is
    still live is not gone, and taking its record would leave two windows
    each believing it is that desk. Best effort: an unreadable session list
    lets the inherit through, as it always did."""
    was = record.get("desk")
    if not was or was == actor:
        return None
    try:
        import open_terminal
        live = [row for row in open_terminal.here(open_terminal.live_sessions())
                if row.get("name") == was]
        mine = open_terminal.own_ancestry() if live else set()
    except Exception:  # noqa: BLE001 -- see the docstring
        return None
    if any(row.get("pid") not in mine for row in live):
        return (f"desk {was!r} is live in this workspace, so it is not gone and "
                f"{HOME}/ is not yours to inherit. A new job opens under a home "
                f"name of its own. Nothing was changed")
    return None


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
    sub = desk_act("plan", "plan this desk's own load: how many lanes each window takes")
    sub.add_argument("--lanes", type=int, required=True,
                     help="how many lanes this job still opens")
    sub.add_argument("--reading", nargs="*", default=[],
                     help="what the desk itself still reads, beyond the lanes")
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
    sub.add_argument("--asked", required=True,
                     help="the question the ruling answers, as put to the owner, or 'unprompted'")
    sub.add_argument("--log", help="the log to append to (default desk_log.md in the desk's home)")
    sub = acts.add_parser("report-done", help="run the sheet's `done:` commands; record done on all-zero")
    sub.add_argument("lane")
    sub.add_argument("--dry-run", action="store_true",
                     help="split and resolve every `done:` command; run and record nothing")
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
            require_home()
            problem = no_home_problem(args.inherit)
            if problem is None and args.inherit and (on_file := read_record()):
                problem = live_desk_problem(on_file, args.desk)
            if problem:
                raise DeskError(problem)
            said = open_desk(args.desk, args.job, inherit=args.inherit)
        elif args.act == "plan":
            said = plan_desk(args.desk, args.lanes, args.reading)
        elif args.act == "stamp":
            said = stamp(args.desk, args.lane, args.sheet)
        elif args.act in ("own", "disown"):
            said = own(args.desk, args.lane, args.paths, give=args.act == "own")
        elif args.act == "outside":
            said = outside(args.desk, args.paths, args.why)
        elif args.act == "route":
            said = route(args.desk, args.paths, args.ruling, args.log, args.asked)
        elif args.act == "report-done":
            said = report_done(args.lane, dry=args.dry_run)
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
