#!/usr/bin/env python3
"""Open a Claude window already in its role, on the model its job calls for.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/open_terminal.py --role lane --name digest-agreement --reason design-latitude --task coordination/task_sheets/digest-agreement.md
    <venv python> scripts/open_terminal.py --role lane --name copy-march --reason prescribed --task coordination/task_sheets/copy-march.md --dry-run
    <venv python> scripts/open_terminal.py --role desk --name desk --model fable --fable-approved-by-owner
    <venv python> scripts/open_terminal.py --role lane --name copy-march --reason prescribed --task coordination/task_sheets/copy-march.md --no-remote-control --dry-run
    <venv python> scripts/open_terminal.py --reasons
    <venv python> scripts/open_terminal.py --list
    <venv python> scripts/open_terminal.py --close --name copy-march
    <venv python> scripts/open_terminal.py --close --wait --name copy-march
    <venv python> scripts/open_terminal.py --close --wait --timeout 300 --name copy-march
    <venv python> scripts/open_terminal.py --close --name copy-march --abandoned "stuck in a loop; reopened as copy-march-2"

WHY THIS EXISTS
---------------
Ported 2026-09-24 from FACOWORK (`_Frontier Awakening/_FACOWORK/scripts/`) to
HAZELHURST, and from there into the Starter Kit. FACOWORK's owner ruled that
batched work runs as one DESK window directing LANE windows the owner can see
and click into, never invisible subagents (FACOWORK R1, R2;
`kb/desk-and-lane-philosophy.md`). This is the program a desk runs to open a
lane: a named tab in this project's shared Windows Terminal window, coloured so
the room can be read at a glance, already running its first instruction so
nobody types anything into it.

WHERE THERE IS NO WINDOWS TERMINAL -- macOS, Linux, or Windows without `wt.exe`
on PATH -- nothing is guessed. The open makes every check it always makes,
prints the one line the owner pastes into a new terminal tab (POSIX sh, or
PowerShell on Windows; `wt.manual_line`), and records the open with
`opened_by: manual`. The lane acks the desk when it starts, as any lane does.

FACOWORK adapted it from Fantasy Football's `scripts/open_terminal.py`. LEFT
BEHIND (every lane works in the one project folder): separate working copies,
the Python-environment link, folder-trust handling, and window placement.

THIS FILE IS KIT-OWNED: identical in every project the Starter Kit seeds, so
nothing in it names the project. The environment variables, the shared window
and the close-marker prefix come from `scripts/project_identity.py`, derived
from the folder's name; the reason tokens come from this project's own
`scripts/reason_tokens.json`. An improvement made here goes back to the kit
with `python scripts/kit_sync.py push scripts/open_terminal.py`.

THE JOB DECIDES THE MODEL (FACOWORK R16)
----------------------------------------
A lane is opened with `--reason`, a token from :data:`REASONS`, and the reason
sets the model. The model is DERIVED from the reason and never passed beside
it, so a desk cannot name an expensive job and open a cheap window, or the
other way round. A job that fits no other reason is `design-latitude`, on Opus:
the unnamed case is the expensive one, so the list needs no escape flag. Fable
is on no row -- it takes the owner's own flag. Haiku is not a model this opens
at all (R17).

The tokens are this project's jobs, so they are DATA, in
`scripts/reason_tokens.json` (:func:`load_reasons` says what it holds), and
every project writes its own rows; `prescribed` and `design-latitude` are in
every project's file. A file that is missing, malformed, names another model,
or lacks either of those two is refused at import: nothing here opens a lane
on a guess. `--reasons` prints the table.

EVERY WINDOW STARTS WITH REMOTE CONTROL ON (the owner's ruling, 2026-09-26)
--------------------------------------------------------------------------
A lane stopped at a permission prompt while the owner is away from the
machine cannot be reached, and `/remote-control` cannot be typed into a lane
from outside it. So every window this opens -- lane and desk, a Windows
Terminal tab and the line pasted by hand, a fresh open and a `--resume` --
starts with `--remote-control <window name>` on its command line, the same
string as its `--name`, and the owner's phone lists it under the name on its
tab. A project prefix on that name (the phone's list is account-wide, and
other projects' windows share names) is DEFERRED: the docs do not say whether
`--remote-control <name>` also renames the session, and a rename would break
the name the desk and its lanes message by, `--close` and the taken-name
check. It waits for a visible-tab measurement of that. `--no-remote-control` opens
a window without it. The dry run prints which, and the record carries
`remote_control: true|false`, because the `wt.exe` line shows the argv only as
an encoded blob.

THE RECORD
----------
Every open and every close appends one line to
`coordination/launch_record.jsonl`: name, role, reason, model, when. A model
chosen at the open and printed once into a scrollback is a spend nobody can
audit afterwards. The record is also what `--close` and the lane cap read: this
program ends only windows it opened, and counts as lanes only windows it
opened. The CLI's session list is ACCOUNT-WIDE -- on 2026-09-18 it showed about
a hundred Fantasy Football sessions beside this project's -- so "everything
listed" is never the answer to "which windows are mine".

Exit codes:
    0 = done (or a dry run that would have been)
    2 = refused, or the launch failed; stderr says why
    3 = --close found no live window of that name
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from typing import NamedTuple, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import project_identity as identity  # noqa: E402
from wt import (TerminalError, Window, command_line, launch, manual_line,  # noqa: E402
                window_command)
from wt import available as wt_available  # noqa: E402

# The Windows console is cp1252 and cannot encode the arrows and check marks
# this project writes in; without this a task quoted back in a dry run dies
# with UnicodeEncodeError instead of being printed.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = identity.REPO
CLAUDE = "claude"

#: The two kinds of window, in the words FACOWORK's build plan used ("Names used
#: in this build"): the desk directs, a lane works. The draft check and the
#: final check are lanes too.
ROLES = ("desk", "lane")
DESK_ROLE = "desk"
LANE_ROLE = "lane"

#: The Windows Terminal window every role window opens a tab in. A NAME rather
#: than `0` ("most recently used"), which is whichever window last had focus --
#: the owner's -- so a mis-fire there is a lane's tab appearing where they are
#: typing. Derived from the project folder's name (`scripts/project_identity.py`).
SHARED_WINDOW = identity.SHARED_WINDOW

#: How a window is opened: as a Windows Terminal tab, or by the owner pasting
#: the printed line into a tab of their own (:func:`launch_mode`). Recorded as
#: `opened_by` on every open.
OPENED_BY_WT = "wt"
OPENED_BY_MANUAL = "manual"

#: The models a REASON can open. Aliases rather than pinned ids: an alias
#: follows the latest model in its family, and a pinned id would quietly age.
#: Haiku is absent by FACOWORK ruling R17, carried here, not by oversight.
ALLOWED_MODELS = ("opus", "sonnet")

#: The one model above the line, and the flag that is the only way onto it.
GATED_MODEL = "fable"
FABLE_FLAG = "--fable-approved-by-owner"

#: WHY A LANE OPENS ON THE MODEL IT DOES: this project's own list, in
#: `scripts/reason_tokens.json`. The file is seeded by the Starter Kit and is
#: the project's from then on; a new, changed or removed row is the owner's
#: ruling, not an edit. Judgment about money, law or what a document means is
#: Opus; copying and filing that a script can verify is Sonnet.
REASON_TOKENS = REPO / "scripts" / "reason_tokens.json"

#: The two rows every project's file carries, with the model each must open:
#: FACOWORK's build-work rows, kept whole. `design-latitude` is also the reason
#: an unlisted job belongs under, named in every refusal.
UNIVERSAL_REASONS = {"prescribed": "sonnet", "design-latitude": "opus"}
CATCH_ALL_REASON = "design-latitude"

#: What this launcher records in the reason's place for an open no reason
#: decides: a desk (R2), and a lane the owner put on Fable themselves. A token
#: spelled like either would be a way round the Fable gate.
OWNERS_CALL = "owners-call"
NOT_REASONS = ("not-a-decision", OWNERS_CALL)

#: A token is one word of the command line and of a task sheet's `reason:`.
_TOKEN = re.compile(r"^[a-z][a-z0-9-]*$")
_TOKEN_FIELDS = ("model", "job", "reads_source")
_FILE_FIELDS = ("about", "tokens")


class ReasonTokensError(Exception):
    """`scripts/reason_tokens.json` is missing, malformed, or breaks a rule."""


class Reason(NamedTuple):
    """One row of `scripts/reason_tokens.json`."""

    model: str
    job: str
    reads_source: bool


def load_reasons(path: Path | None = None) -> dict[str, Reason]:
    """The reason tokens in `path` (default :data:`REASON_TOKENS`), in file order.

    THE FORMAT, stdlib JSON::

        {"about": "<optional: what the file is, for whoever opens it>",
         "tokens": {"<token>": {"model": "sonnet" | "opus",
                                "job": "<one line: what the job is>",
                                "reads_source": true | false}}}

    `reads_source` true means the job works FROM a source document, so
    `desk_record.sheet_problems` refuses such a sheet whose `reads:` names only
    derived files (CLAUDE.md, Source of Truth: kb digests are derived).

    Refused, with the rule named: a missing or unreadable file, JSON that is
    not this shape, a token that is not one lower-case word, a field missing,
    extra or of the wrong type, a model other than sonnet or opus, a token
    spelled like one of :data:`NOT_REASONS`, and a file without `prescribed`
    on sonnet and `design-latitude` on opus.
    """
    path = REASON_TOKENS if path is None else path
    where = "scripts/reason_tokens.json" if path == REASON_TOKENS else str(path)

    def refuse(problem: str) -> ReasonTokensError:
        return ReasonTokensError(
            f"{where}: {problem}. No lane opens until it is fixed. The file is "
            '{"tokens": {"<token>": {"model": "sonnet|opus", "job": "<one line>", '
            '"reads_source": true|false}}}, and it holds '
            + " and ".join(f"{t!r} on {m}" for t, m in UNIVERSAL_REASONS.items()))

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise refuse(f"cannot be read ({exc.__class__.__name__}); a lane's model "
                     f"comes from the reason tokens there") from None
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise refuse(f"is not JSON ({exc})") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("tokens"), dict):
        raise refuse("has no `tokens` object")
    extra = sorted(set(raw) - set(_FILE_FIELDS))
    if extra:
        raise refuse(f"has key(s) {extra} beside `tokens`; only "
                     f"{list(_FILE_FIELDS)} are read")
    if not isinstance(raw.get("about", ""), str):
        raise refuse("`about` is not a string")
    table: dict[str, Reason] = {}
    for token, row in raw["tokens"].items():
        if not _TOKEN.match(token):
            raise refuse(f"{token!r} is not a token: one lower-case word of "
                         f"letters, digits and dashes")
        if token in NOT_REASONS:
            raise refuse(f"{token!r} is what the launcher records for an open no "
                         f"reason decides, so it cannot be a reason")
        if not isinstance(row, dict) or set(row) != set(_TOKEN_FIELDS):
            got = sorted(row) if isinstance(row, dict) else type(row).__name__
            raise refuse(f"{token!r} must have exactly {list(_TOKEN_FIELDS)}; "
                         f"it has {got}")
        if row["model"] not in ALLOWED_MODELS:
            raise refuse(f"{token!r} names model {row['model']!r}; a reason opens "
                         f"{' or '.join(ALLOWED_MODELS)}. Haiku is never opened "
                         f"(R17), and {GATED_MODEL} takes the owner's own flag")
        if not isinstance(row["job"], str) or not row["job"].strip() \
                or "\n" in row["job"]:
            raise refuse(f"{token!r} has no one-line `job`")
        if not isinstance(row["reads_source"], bool):
            raise refuse(f"{token!r} has `reads_source` {row['reads_source']!r}; "
                         f"it is true or false")
        table[token] = Reason(row["model"], row["job"].strip(), row["reads_source"])
    for token, model in UNIVERSAL_REASONS.items():
        if token not in table:
            raise refuse(f"{token!r} is missing; every project carries it")
        if table[token].model != model:
            raise refuse(f"{token!r} opens on {table[token].model}; it opens on "
                         f"{model} in every project")
    return table


def reason_tables(table: dict[str, Reason]) -> tuple[dict[str, tuple[str, str]],
                                                     tuple[str, ...]]:
    """:data:`REASONS` (token -> (model, job)) and :data:`SOURCE_REASONS`
    (the tokens whose job reads a source document), from a loaded table."""
    return ({token: (row.model, row.job) for token, row in table.items()},
            tuple(token for token, row in table.items() if row.reads_source))


# LOADED AT IMPORT, AND REFUSED LOUDLY. Run as a program, a bad file is one
# FAIL line and exit 2; imported (by `desk_record.py`, or a test), it raises.
try:
    REASON_TABLE = load_reasons()
except ReasonTokensError as _refusal:
    if __name__ != "__main__":
        raise
    print(f"FAIL - {_refusal}", file=sys.stderr)
    raise SystemExit(2) from None

#: token -> (model, what the job is), and the tokens whose job reads a source.
REASONS, SOURCE_REASONS = reason_tables(REASON_TABLE)

#: FACOWORK R2, carried: a desk runs on Fable. So the desk's model is a ruling
#: rather than a per-open decision, and `--reason` is refused on it. The owner
#: normally starts a desk by typing /desk in a window of their own, which needs
#: no launcher and runs on whatever model that window has.
DESK_MODEL = GATED_MODEL
DESK_WHY = (
    "a desk runs on Fable (FACOWORK ruling R2, carried here), so it is not a "
    "choice this open makes"
)

#: Tab colours, and what they are FOR: the slice 3 rehearsal asks the owner to
#: check that the tabs opened on the models the plan says, and a colour is the
#: only way to read that off fifteen tabs without clicking into each. The desk
#: is crimson -- the colour chosen for the seat in Fantasy Football, read off a
#: screenshot on 2026-08-26. Lanes are coloured BY MODEL. All four are named
#: CSS colours measured there to stay readable on an inactive tab, which
#: Terminal dims (navy and mediumblue failed that test and render near-black).
DESK_TAB_COLOR = "#DC143C"   # crimson
LANE_TAB_COLORS = {
    "opus": "#4169E1",       # royalblue
    "sonnet": "#3CB371",     # mediumseagreen
    "fable": "#DAA520",      # goldenrod -- a lane the owner put on Fable themselves
}

#: R23: a setting caps how many lanes are open at once, at the number measured
#: to run comfortably on the machine the design was built on.
MAX_OPEN_LANES = 15

#: Every window this opens runs under this mode, written on the command line
#: for the reason `--model` is: a rule that is not on the command line cannot
#: be read off the window running under it. The spelling is the CLI's own.
LAUNCHED_PERMISSION_MODE = "acceptEdits"

#: The CLI's own flag for a session reachable from the owner's phone
#: (`claude --help`: `--remote-control [name]`), and the launcher's way to
#: open a window without it.
REMOTE_CONTROL_FLAG = "--remote-control"
NO_REMOTE_CONTROL_FLAG = "--no-remote-control"

RECORD = REPO / "coordination" / "launch_record.jsonl"

#: Where `--close` plants the marker and where the window it closes looks for
#: it. The system temp directory: the path is baked into the window's command
#: line when it OPENS and written by a `--close` that may run minutes later.
CLOSE_MARKERS = Path(tempfile.gettempdir())

#: A name becomes one token of the first prompt and part of a filename.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

AGENTS_JSON = (CLAUDE, "agents", "--json")
BUSY_STATUS = "busy"
ABANDONED_FLAG = "--abandoned"
CLOSED_NOTHING = 3

#: `--close --wait`: how often the CLI's status is asked again, and how long
#: the wait lasts by default before it is a plain refusal. A lane sends `done:`
#: and then finishes its turn, and until that turn ends its status reads busy
#: -- so at S3 the desk tried and failed to close one lane eleven times.
WAIT_POLL_SECONDS = 5
WAIT_TIMEOUT_SECONDS = 600


class Tier(NamedTuple):
    """The model a window opens on, the token that chose it, and what that
    token means in words -- so the record is readable by somebody who was not
    there when the window was opened."""

    model: str
    reason: str
    why: str


# --- the model follows the job ----------------------------------------------


def reasons_block() -> str:
    """The vocabulary, as a refusal and `--reasons` print it: token, model and
    meaning, and which jobs must read a source document."""
    width = max([16, *(len(token) for token in REASONS)])
    return "\n".join(
        f"  {token:<{width}} {model:<7} {what}"
        + (" [reads: names a source document]" if token in SOURCE_REASONS else "")
        for token, (model, what) in REASONS.items()
    )


def list_reasons() -> int:
    """`--reasons`: the table, where it lives, and whose it is to change."""
    print("reason tokens (scripts/reason_tokens.json) -- the reason decides the "
          "model; a changed row is the owner's ruling:")
    print(reasons_block())
    print(f"  a job no row fits is {CATCH_ALL_REASON!r}, on "
          f"{REASONS[CATCH_ALL_REASON][0]}")
    return 0


def chosen_model(role: str, model: str | None, *, fable_approved: bool) -> str | None:
    """The model named on the command line, checked; None when none was named.

    The desk is the one role with a default, and its default is the gated
    model -- so a desk open without the owner's flag is refused here like any
    other ungranted Fable open.
    """
    if model is None:
        if role != DESK_ROLE:
            return None
        model = DESK_MODEL
    if model == GATED_MODEL:
        if fable_approved:
            return model
        raise TerminalError(
            f"--model {GATED_MODEL} needs {FABLE_FLAG}, and that approval has to "
            f"come from the owner themselves. A desk cannot approve it for a "
            f"lane, and no window can approve it for another."
            + (f" A desk runs on {GATED_MODEL} by ruling R2 -- the owner "
               f"normally starts one by typing /desk in a terminal "
               f"of their own, which needs no launcher at all."
               if role == DESK_ROLE else
               f" Without it a lane opens on the model its --reason names.")
        )
    if model in ALLOWED_MODELS:
        return model
    raise TerminalError(
        f"unknown model {model!r}; a reason opens {list(ALLOWED_MODELS)}, and "
        f"{GATED_MODEL!r} takes the owner's own flag. Haiku is not used in this "
        f"project (ruling R17)"
    )


def tier_choice(role: str, model: str | None, reason: str | None) -> Tier:
    """Which model this window opens on, and the reason recorded beside it.

    IN THIS ORDER, AND THE ORDER IS THE RULE:

    * The desk is not a decision (R2); passing `--reason` there is refused,
      because it would be accepting a choice that has no effect.
    * Fable on a lane is the owner's own call and outside the vocabulary.
    * A lane NAMES A REASON, always. No reason is a refusal, not a default.
    * An explicit `--model` that contradicts the reason's model is refused:
      letting the two disagree silently is exactly what deriving the model
      from the reason exists to prevent.
    """
    if role == DESK_ROLE:
        if reason:
            raise TerminalError(
                f"--reason is for a lane, and this is --role {DESK_ROLE}: "
                f"{DESK_WHY}"
            )
        if model != DESK_MODEL:
            raise TerminalError(
                f"a desk opens on {DESK_MODEL} (ruling R2), and --model {model} "
                f"says otherwise. A window on {model} is a lane: open it with "
                f"--role {LANE_ROLE} and the --reason for its job"
            )
        return Tier(DESK_MODEL, "not-a-decision", DESK_WHY)
    if model == GATED_MODEL:
        return Tier(model, OWNERS_CALL, (
            f"the owner's own approval, outside this vocabulary entirely -- the "
            f"{FABLE_FLAG} gate is what admitted it"
        ))
    if not reason:
        raise TerminalError(
            f"--role {LANE_ROLE} needs --reason: name the kind of job, and the "
            f"job decides the model.\n{reasons_block()}\n"
            f"If none of them fits, that is not a cheap lane: it is "
            f"{CATCH_ALL_REASON!r}, on {REASONS[CATCH_ALL_REASON][0]}"
        )
    if reason not in REASONS:
        raise TerminalError(
            f"{reason!r} is not a reason this launcher knows. The list is the "
            f"owner's job-by-job ruling rather than a vocabulary, so a new one is "
            f"a ruling and then a row in scripts/reason_tokens.json -- there is "
            f"no flag past it, because the job that fits nothing here is "
            f"{CATCH_ALL_REASON!r}.\n{reasons_block()}"
        )
    tier, why = REASONS[reason]
    if model is not None and model != tier:
        raise TerminalError(
            f"--reason {reason} opens on {tier}, and --model {model} says "
            f"otherwise. The reason decides the model here, so pass one of "
            f"them: drop --model, or name the reason that opens on {model}."
            f"\n{reasons_block()}"
        )
    return Tier(tier, reason, why)


# --- the window -------------------------------------------------------------


def checked_name(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise TerminalError(
            f"{name!r} cannot be a window name: it becomes one word of the "
            f"window's first instruction and part of a filename, so it is "
            f"letters, digits, dot, dash and underscore, starting with a "
            f"letter or digit"
        )
    return name


def role_prompt(role: str, name: str, task: str | None) -> str:
    """The slash command this window runs as its first instruction.

    Only the owner's typed command, or a launcher somebody ran, gives a
    window its role -- so the role command IS the first prompt, never a
    sentence asking the window to behave like one.
    """
    if role not in ROLES:
        raise TerminalError(f"unknown role {role!r}; expected one of {list(ROLES)}")
    if role == DESK_ROLE:
        if task:
            raise TerminalError(
                "--task is for a lane: a desk is told what to do by the owner, "
                "in its own window"
            )
        return "/desk"
    if not task or not task.strip():
        raise TerminalError(
            f"--role {LANE_ROLE} needs --task: the window would open with "
            f"nothing to do and no desk aware of it"
        )
    return f"/{role} {name} {task.strip()}"


def permission_args() -> list[str]:
    return ["--permission-mode", LAUNCHED_PERMISSION_MODE]


def remote_control_args(name: str, remote_control: bool) -> list[str]:
    """`--remote-control <name>`, or nothing when it is turned off.

    The value is ALWAYS passed: the CLI's value is optional, so a bare flag
    would take the next word of the command line as the session's name. And it
    is EXACTLY the `--name` string: whether `--remote-control <name>` also sets
    the session's name is unmeasured, and with the two the same, whichever one
    wins, the name the desk and its lanes message each other by cannot change.
    """
    return [REMOTE_CONTROL_FLAG, name] if remote_control else []


def session_cwd() -> str:
    """The working directory AS THE RUNNING SESSION SPELLS IT.

    Claude's folder-trust store is keyed on the path STRING, so a window
    started under a differently-cased spelling of the same directory is a
    folder it has never seen and it stops to ask (found in Fantasy Football,
    2026-08-22). So the literal string goes out unnormalised, and is only
    CHECKED against the workspace it must point at.
    """
    cwd = os.getcwd()
    if Path(cwd).resolve() != REPO:
        raise TerminalError(
            f"run this from the workspace root: the window inherits this "
            f"directory, and {cwd} is not {REPO}"
        )
    return cwd


def close_marker_path(name: str) -> Path:
    """The file whose existence means this window was closed ON PURPOSE."""
    marker = CLOSE_MARKERS / f"{identity.CLOSE_MARKER_PREFIX}{name}.closing"
    if marker.parent != CLOSE_MARKERS:
        raise TerminalError(
            f"{name!r} cannot be a window name: its close marker would be "
            f"{marker}, which is not a file in {CLOSE_MARKERS}"
        )
    return marker


def tab_color(role: str, model: str) -> str | None:
    return DESK_TAB_COLOR if role == DESK_ROLE else LANE_TAB_COLORS.get(model)


def window_for(role: str, name: str, task: str | None, model: str, *,
               resume: bool, remote_control: bool = True) -> Window:
    """The window to open, as `wt` wants it.

    `--resume` opens the persisted session by name and carries NO role prompt:
    that window is already in role. Remote Control is on unless
    `remote_control` is False, on every role and on a resume alike.
    """
    argv: list[str] = [CLAUDE, "--model", model, *permission_args(),
                       *remote_control_args(name, remote_control)]
    if resume:
        argv += ["--resume", name]
    else:
        argv += ["--name", name, role_prompt(role, name, task)]
    return Window(
        label=f"{name} ({role}, {model}{', resumed' if resume else ''})",
        argv=tuple(argv),
        # The window goes when the session does: a role window that stays open
        # after its session ends is a dead window that still looks live.
        keep_open=False,
        close_marker=str(close_marker_path(name)),
        window_target=SHARED_WINDOW,
        tab_title=name,
        tab_color=tab_color(role, model),
        # What `scripts/lane_guard.py` reads: a window knows its own role from
        # the moment it starts, with nothing to remember and nobody to ask.
        env=((identity.ROLE_ENV, role), (identity.WINDOW_ENV, name)),
    )


def launch_mode(os_name: str | None = None, has_wt: bool | None = None) -> str:
    """How this machine opens a window: :data:`OPENED_BY_WT` on Windows with
    `wt.exe` on PATH, :data:`OPENED_BY_MANUAL` everywhere else.

    Manual is not a failure. On macOS and Linux there is no one terminal to
    drive, and guessing one opens nothing or opens it where nobody looks; the
    owner pasting one printed line into a tab of their own is the reliable
    path, and the lane's ack tells the desk it started.
    """
    if not identity.is_windows(os_name):
        return OPENED_BY_MANUAL
    if has_wt is None:
        has_wt = wt_available()
    return OPENED_BY_WT if has_wt else OPENED_BY_MANUAL


def manual_reason(os_name: str | None = None) -> str:
    """Why this open is manual, in the words the printed banner uses."""
    return ("wt.exe is not on PATH" if identity.is_windows(os_name)
            else "this is not Windows, and no terminal is guessed at")


# --- the record -------------------------------------------------------------


def read_record(path: Path | None = None) -> list[dict]:
    """Every line of the launch record, oldest first. A line that is not JSON
    is refused rather than skipped: the record is what `--close` trusts."""
    path = RECORD if path is None else path
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise TerminalError(f"{path}:{number} is not JSON ({exc})") from exc
    return rows


def append_record(entry: dict, path: Path | None = None) -> None:
    path = RECORD if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def latest_by_name(rows: Sequence[dict]) -> dict[str, dict]:
    """The last thing the record says about each name -- an open or a close."""
    latest: dict[str, dict] = {}
    for row in rows:
        if row.get("name"):
            latest[str(row["name"])] = row
    return latest


def now_stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- what is live -----------------------------------------------------------


def live_sessions() -> list[dict]:
    """Every live Claude session on this ACCOUNT, as the CLI reports it."""
    try:
        proc = subprocess.run(AGENTS_JSON, capture_output=True, check=False)
    except OSError as exc:
        raise TerminalError(f"could not run `{' '.join(AGENTS_JSON)}`: {exc}") from exc
    if proc.returncode != 0:
        raise TerminalError(
            f"`{' '.join(AGENTS_JSON)}` failed (exit {proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    try:
        rows = json.loads(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise TerminalError(f"`claude agents --json` did not return JSON: {exc}") from exc
    return [row for row in rows if isinstance(row, dict)]


def here(rows: Sequence[dict]) -> list[dict]:
    """The sessions whose working directory is THIS workspace. The list is
    account-wide, and a short name is the owner's word rather than a unique id."""
    found = []
    for row in rows:
        try:
            if Path(str(row.get("cwd", ""))).resolve() == REPO:
                found.append(row)
        except OSError:
            continue
    return found


def open_lanes(live_here: Sequence[dict], rows: Sequence[dict]) -> list[str]:
    """Live sessions here whose latest record entry is a lane this opened."""
    latest = latest_by_name(rows)
    return sorted(
        str(row.get("name")) for row in live_here
        if latest.get(str(row.get("name")), {}).get("event") == "open"
        and latest[str(row.get("name"))].get("role") == LANE_ROLE
    )


def refuse_a_taken_name(name: str, live_here: Sequence[dict]) -> None:
    if any(row.get("name") == name for row in live_here):
        raise TerminalError(
            f"a live session in this workspace already answers to {name!r}. "
            f"Two windows under one name cannot be told apart by a message or "
            f"by --close; pick another name, or --resume is for reopening one "
            f"that has ended"
        )


def refuse_past_the_cap(live_here: Sequence[dict], rows: Sequence[dict]) -> None:
    lanes = open_lanes(live_here, rows)
    if len(lanes) >= MAX_OPEN_LANES:
        raise TerminalError(
            f"{len(lanes)} lanes are open and the cap is {MAX_OPEN_LANES} "
            f"(ruling R23): {lanes}. Close one that has reported done "
            f"(--close) and open this one again"
        )


def require_a_stamped_sheet(name: str, task: str | None, reason: str | None) -> None:
    """A lane opens on a task sheet the desk has stamped, or not at all.

    The stamp is where a sheet is checked (one unit, its files, a measurable
    done) and where the lane is given its files in the ownership record
    (`scripts/desk_record.py`). Refusing the open here is what makes both
    unskippable: a lane with no row is a writer the desk cannot route a
    correction to and the ownership check cannot attribute.
    """
    import desk_record

    try:
        record = desk_record.read_record()
        problem = desk_record.stamped_sheet_problem(record, name, task)
        if problem is None and reason not in (
                OWNERS_CALL, record["lanes"][name].get("reason")):
            # The sheet names the job, and the job decides the model (R16).
            problem = (f"the stamped sheet says `reason: "
                       f"{record['lanes'][name].get('reason')}` and this open "
                       f"says --reason {reason}")
    except desk_record.DeskError as exc:
        problem = str(exc)
    if problem:
        raise TerminalError(
            f"{problem}. A lane's --task is the path of its stamped task "
            f"sheet: write the sheet, then "
            f"`desk_record.py stamp {name} <sheet> --desk <you>`, then open it"
        )


def require_a_safe_close(name: str, row: dict, abandoned: str | None) -> None:
    """The desk cannot close a lane that is mid-task or has not reported done.

    TWO FACTS, BOTH ASKED RATHER THAN INFERRED. Whether the lane REPORTED DONE
    since it was last put to work is read from the desk record -- a correction
    routed to a finished lane puts it back to work, so an earlier `done` stops
    counting. Whether it is MID-TURN is the CLI's own `status`: measured in
    Fantasy Football 2026-08-30, a close on a stale finished record killed a
    lane inside new work. A window with no row in the desk record is not a
    lane of this desk and closes plainly -- tidying strays is what --close is
    for. `--abandoned "<why>"` is the way past both, and the why is recorded.
    """
    if abandoned:
        return
    import desk_record

    try:
        a_lane = desk_record.is_a_lane(name)
        problem = desk_record.close_problem(name)
    except desk_record.DeskError as exc:
        # An unreadable record is no evidence that the lane finished.
        a_lane, problem = True, str(exc)
    if problem is None and a_lane \
            and str(row.get("status") or "").strip().lower() == BUSY_STATUS:
        problem = (f"{name} is {BUSY_STATUS.upper()} -- it is mid-turn, and what "
                   f"a close ends is whatever it has not written yet. Let the "
                   f"close wait for it to go idle: --close --wait --name {name}")
    if problem:
        raise TerminalError(
            f"{problem}.\n  If the window is abandoned and will never report, "
            f"say so and it closes: --close --name {name} {ABANDONED_FLAG} \"<why>\""
        )


def ancestry_from(table: list, pid: int) -> set[int]:
    """`pid` and every pid above it in `table`, stopping at a recycled parent.

    Windows keeps a dead parent's pid in ParentProcessId and hands that pid to
    a later process, so a walk by pid alone can climb out of this process's
    tree into an unrelated one: on 2026-09-20 a desk's dead ancestor pid had
    been reused inside a lane's tree, and the close refused that lane as "the
    session running this command". A real parent is never younger than its
    child, so the walk stops at a "parent" created after the child.
    """
    rows = {
        row["ProcessId"]: row
        for row in table
        if isinstance(row, dict)
        and isinstance(row.get("ProcessId"), int)
        and isinstance(row.get("ParentProcessId"), int)
    }
    chain: set[int] = set()
    while pid in rows and pid not in chain:
        chain.add(pid)
        child = rows[pid]
        parent = rows.get(child["ParentProcessId"])
        if parent is None:
            break
        born, parent_born = child.get("Created"), parent.get("Created")
        if (isinstance(born, int) and isinstance(parent_born, int)
                and parent_born > born):
            break
        pid = parent["ProcessId"]
    return chain


#: The process table, per machine. Windows: every process with its parent and
#: creation time, as JSON. Elsewhere: `ps`, which macOS and Linux both carry,
#: with no creation time -- a POSIX parent that dies hands its children to
#: pid 1 rather than leaving a stale parent pid behind, so the recycled-parent
#: guard in :func:`ancestry_from` is not needed there.
WINDOWS_PROCESS_TABLE = (
    "powershell", "-NoProfile", "-Command",
    ("Get-CimInstance Win32_Process | Select-Object ProcessId,"
     "ParentProcessId,@{n='Created';e={if ($_.CreationDate) "
     "{$_.CreationDate.ToFileTimeUtc()} else {$null}}} "
     "| ConvertTo-Json -Compress"))
POSIX_PROCESS_TABLE = ("ps", "-A", "-o", "pid=,ppid=")


def parse_ps(text: str) -> list[dict]:
    """`ps -A -o pid=,ppid=` output as the rows :func:`ancestry_from` reads."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append({"ProcessId": int(parts[0]),
                         "ParentProcessId": int(parts[1]), "Created": None})
    return rows


def process_table(os_name: str | None = None) -> list:
    """Every process with its parent; empty when it cannot be read."""
    windows = identity.is_windows(os_name)
    try:
        proc = subprocess.run(
            list(WINDOWS_PROCESS_TABLE if windows else POSIX_PROCESS_TABLE),
            capture_output=True, check=False, timeout=60,
        )
        text = proc.stdout.decode("utf-8", "replace")
        if not windows:
            return parse_ps(text)
        table = json.loads(text or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    return [table] if isinstance(table, dict) else table


def own_ancestry() -> set[int]:
    """This process's pid and every live pid above it; empty when unreadable.

    The session that runs this command is an ANCESTOR of this interpreter
    (measured in Fantasy Football, 2026-09-12), and a tree kill of an
    ancestor takes the closer down with it.
    """
    return ancestry_from(process_table(), os.getpid())


def kill_command(pid: object, os_name: str | None = None) -> list[str]:
    """The command that ends the Claude process `pid`.

    Windows: `taskkill /T /F` -- without `/F` Windows refuses to end a console
    process, which owns no window to send a close to; `/T` takes the shells it
    started with it. Elsewhere: `kill -TERM`, the polite signal, which a
    Claude session answers by ending itself and what it started. The tab the
    owner pasted the line into stays open at its shell prompt.
    """
    if identity.is_windows(os_name):
        return ["taskkill", "/PID", str(pid), "/T", "/F"]
    return ["kill", "-TERM", str(pid)]


# --- --list -----------------------------------------------------------------


def list_windows() -> int:
    live_here = here(live_sessions())
    latest = latest_by_name(read_record())
    if not live_here:
        print("no live Claude session in this workspace")
        return 0
    print(f"{len(live_here)} live in this workspace "
          f"(cap on lanes open at once: {MAX_OPEN_LANES})")
    for row in sorted(live_here, key=lambda r: str(r.get("name"))):
        name = str(row.get("name"))
        entry = latest.get(name)
        if entry and entry.get("event") == "open":
            what = (f"{entry.get('role')}, {entry.get('model')} - "
                    f"{entry.get('reason')}, opened {entry.get('at')}")
        else:
            what = "not opened by this launcher (the owner's own window, or a desk they started)"
        print(f"  {name:<24} {str(row.get('status')):<6} {what}")
    for line in stalled_lines(live_here):
        print(line)
    return 0


#: What the CLI reports for a session stopped at a question only a person can
#: answer -- measured 2026-09-19 on a lane sitting at a permission pop-up.
STALLED_STATUS = "waiting"


#: The banner's opening words, so a test and a skill can name them exactly.
NEEDS_OWNER = "NEEDS THE OWNER"


def stalled_lines(live_here: Sequence[dict] | None = None) -> list[str]:
    """One loud line per window that is stopped waiting for the owner.

    A WINDOW AT A POP-UP LOOKS LIKE A WINDOW THINKING, and it cannot say so
    itself. In the first real desk run (2026-09-19) two lanes sat at a pop-up
    while the desk waited for their acks, and the owner told the desk. "The desk
    looks for stalls" was a sentence in its skill and did not happen -- so every
    act the desk performs anyway (`--list`, an open, a close, and every
    `desk_record.py` act) ends by printing these lines. Best effort by design:
    it never raises, because it rides on commands that must not fail for it.
    """
    try:
        if live_here is None:
            live_here = here(live_sessions())
        stalled = [row for row in live_here if str(row.get("status")) == STALLED_STATUS]
        if not stalled:
            return []
        import note_prompt
        last: dict[str, dict] = {}
        for entry in note_prompt.read_log(note_prompt.LOG):
            last[str(entry.get("session"))] = entry
        lines = []
        for row in sorted(stalled, key=lambda r: str(r.get("name"))):
            entry = last.get(str(row.get("sessionId")))
            what = (f"{entry.get('tool')}: {entry.get('what')}" if entry
                    else "no pop-up on record -- it may be asking the owner a question")
            lines.append(f"{NEEDS_OWNER} -- the `{row.get('name')}` tab is stopped "
                         f"and waiting for the owner: {what}")
        return lines + ["  Tell the owner which tab, in this turn."]
    except Exception:  # noqa: BLE001 -- a banner must never break the act it rides on
        return []


# --- --close ----------------------------------------------------------------


def wait_until_idle(name: str, row: dict, timeout: float) -> dict | None:
    """The live row for `name` once its status is no longer busy; None when the
    session ended while this waited. Refused when it is still busy at the end
    of `timeout` seconds, and refused AT ONCE when it stops to wait on the
    owner: a window at a pop-up is not finishing a turn, it is asking
    something, and the owner -- not a wait -- is what it needs.

    `--wait` asks the same two facts the close does, just more than once: the
    CLI's status, and (afterwards, in :func:`require_a_safe_close`) whether the
    lane reported done. It never substitutes a timer for either.
    """
    deadline = monotonic() + timeout
    pid = row.get("pid")
    announced = False
    while str(row.get("status") or "").strip().lower() == BUSY_STATUS:
        if not announced:
            print(f"  {name} is {BUSY_STATUS} -- waiting up to {timeout:g}s for it "
                  f"to go idle", flush=True)
            announced = True
        left = deadline - monotonic()
        if left <= 0:
            raise TerminalError(
                f"{name} is still {BUSY_STATUS.upper()} after {timeout:g}s of "
                f"--wait; nothing was closed. Look at its tab, then run the "
                f"close again")
        sleep(min(WAIT_POLL_SECONDS, left))
        matches = [r for r in here(live_sessions()) if r.get("name") == name]
        if not matches:
            return None
        if len(matches) > 1 or matches[0].get("pid") != pid:
            raise TerminalError(
                f"while --wait waited, the session answering to {name!r} changed "
                f"(pid {pid} -> {[r.get('pid') for r in matches]}); nothing was "
                f"closed. Look at the tabs before closing anything by that name")
        row = matches[0]
    if str(row.get("status") or "").strip().lower() == STALLED_STATUS:
        raise TerminalError(
            f"{name} is {STALLED_STATUS.upper()} -- stopped at a permission pop-up "
            f"or a question only the owner can answer, not finishing a turn. "
            f"--wait closes only an idle lane: tell the owner which tab")
    return row


def close_window(name: str, *, dry_run: bool, abandoned: str | None = None,
                 wait: bool = False, timeout: float = WAIT_TIMEOUT_SECONDS) -> int:
    """End the Claude process behind `name`, once :func:`require_a_safe_close`
    agrees the lane has reported done and is not mid-task.

    `wait=True` (`--close --wait`) first waits, up to `timeout` seconds, for a
    busy lane to finish its turn (:func:`wait_until_idle`); the checks that
    follow are the same ones a plain close makes.

    THIS ENDS THE PROCESS FROM OUTSIDE (:func:`kill_command`: `taskkill /T /F`
    on Windows, `kill -TERM` elsewhere). A transcript is written turn by turn,
    so the record survives; what does not is anything the session was midway
    through.

    Three refusals, each before anything is touched: a name this launcher never
    opened (the owner's own window is not the desk's to end), a name live only
    in another project, and the session running this command.

    THE MARKER IS PLANTED BEFORE THE KILL: a Windows Terminal pane's shell
    looks for it only once its program has exited, so a marker written first
    is always there in time (a manually opened tab never reads it; it is
    cleared at the next open of that name). The outcome is read off the END
    STATE, not the kill's exit code -- `taskkill /T` exits non-zero when any
    child refuses, even though the session named is already gone.
    """
    entry = latest_by_name(read_record()).get(name)
    if entry is None:
        raise TerminalError(
            f"this launcher has no record of opening {name!r}, and it ends "
            f"only windows it opened. A window the owner started is theirs to close"
        )
    live = live_sessions()
    matches = [row for row in here(live) if row.get("name") == name]
    if not matches:
        elsewhere = [str(row.get("cwd")) for row in live if row.get("name") == name]
        if elsewhere:
            raise TerminalError(
                f"the only live session named {name!r} is in {elsewhere}, which "
                f"is not this workspace. Nothing was closed"
            )
        names = sorted(str(row.get("name")) for row in here(live))
        print(f"{name}: no live session in this workspace answers to that "
              f"name. Live here: {names}", flush=True)
        print(f"FAIL - {'would close' if dry_run else 'closed'} nothing under "
              f"{name!r}", file=sys.stderr)
        return CLOSED_NOTHING
    if len(matches) > 1:
        raise TerminalError(
            f"{len(matches)} live sessions answer to {name!r}: "
            f"{[row.get('pid') for row in matches]}. Close the right one by hand"
        )
    row = matches[0]
    pid = row.get("pid")
    print(f"{name}: pid {pid}, session {row.get('sessionId')}, "
          f"{row.get('status')}", flush=True)
    if pid in own_ancestry():
        raise TerminalError(
            f"{name} is the session running this command. Ending it from "
            f"inside takes this command down with it; close that tab by hand"
        )
    if wait:
        row = wait_until_idle(name, row, timeout)
        if row is None:
            print(f"{name}: its session ended while --wait waited; there is "
                  f"nothing left to close", flush=True)
            print(f"FAIL - {'would close' if dry_run else 'closed'} nothing under "
                  f"{name!r}", file=sys.stderr)
            return CLOSED_NOTHING
        print(f"  {name} is {row.get('status')}", flush=True)
    require_a_safe_close(name, row, abandoned)
    if dry_run:
        print("  --dry-run: nothing was closed", flush=True)
        return 0
    marker = close_marker_path(name)
    marker.write_text(
        f"{name}: closed by open_terminal.py --close, pid {pid}\n", encoding="utf-8"
    )
    proc = subprocess.run(kill_command(pid), capture_output=True, check=False)
    if proc.returncode != 0:
        try:
            still = any(r.get("name") == name for r in here(live_sessions()))
        except TerminalError:
            still = True    # an unreadable list is no evidence a window is gone
        if still:
            marker.unlink(missing_ok=True)
            said = " ".join(
                part.decode("utf-8", "replace").strip()
                for part in (proc.stdout, proc.stderr) if part.strip()
            )
            sys.stdout.flush()
            print(f"FAIL - could not close pid {pid}, and it is still live: {said}",
                  file=sys.stderr)
            return 2
    entry = {"at": now_stamp(), "event": "close", "name": name, "pid": pid}
    if abandoned:
        entry["abandoned"] = abandoned
    append_record(entry)
    import desk_record
    try:
        # The row and its paths stay: the ownership check still has to
        # attribute every file this lane changed.
        desk_record.record_close(name, abandoned=abandoned)
    except desk_record.DeskError as exc:
        print(f"  the window is closed, but the desk record was not updated: {exc}",
              flush=True)
    print(f"  closed pid {pid}; {marker.name} tells its pane to go", flush=True)
    return 0


# --- the command line -------------------------------------------------------


def check_wait(close: bool, wait: bool, timeout: float | None,
               abandoned: str | None) -> float:
    """The seconds `--close --wait` may wait, or a refusal for a combination
    that would be accepted and then mean nothing."""
    if (wait or timeout is not None) and not close:
        raise TerminalError("--wait and --timeout are for --close")
    if timeout is not None and not wait:
        raise TerminalError("--timeout is how long --wait waits; pass --wait with it")
    if wait and abandoned:
        raise TerminalError(
            f"{ABANDONED_FLAG} closes a lane now, whatever it is doing, and "
            f"--wait waits for it to finish; pass one of them")
    if timeout is not None and not timeout > 0:
        raise TerminalError(f"--timeout {timeout:g} is not a positive number of seconds")
    return WAIT_TIMEOUT_SECONDS if timeout is None else timeout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--role", choices=ROLES,
                        help="which role command the window opens with")
    parser.add_argument("--name",
                        help="the short name for the window; the session's "
                             "display name and the tab's title")
    parser.add_argument("--task",
                        help="what the lane is to do -- normally the path of "
                             "its task sheet; required by --role lane")
    parser.add_argument("--reason", metavar="REASON",
                        help=f"the kind of job, one of {list(REASONS)} "
                             "(scripts/reason_tokens.json); the reason decides "
                             "the model, so do not pass --model beside it")
    parser.add_argument("--reasons", action="store_true",
                        help="print the reason tokens: each one's model and job")
    parser.add_argument("--model",
                        help=f"one of {list(ALLOWED_MODELS)}, or {GATED_MODEL} "
                             f"with {FABLE_FLAG}; refused if it contradicts "
                             "--reason")
    parser.add_argument(FABLE_FLAG, action="store_true",
                        help="the owner's own approval to open this window on fable")
    parser.add_argument("--resume", action="store_true",
                        help="reopen the persisted session of this name, in "
                             "role already")
    parser.add_argument(NO_REMOTE_CONTROL_FLAG, dest="remote_control",
                        action="store_false",
                        help=f"open the window without {REMOTE_CONTROL_FLAG} "
                             "<name>; every window has it otherwise")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command line and the first "
                             "instruction; open nothing and record nothing")
    parser.add_argument("--list", action="store_true",
                        help="show the live windows in this workspace, with "
                             "the reason and model of each one this opened")
    parser.add_argument("--close", action="store_true",
                        help="end the live window of this name instead of "
                             "opening one; refused for a lane that has not "
                             "reported done or is mid-turn (--wait waits "
                             "out the turn)")
    parser.add_argument(ABANDONED_FLAG, metavar="WHY",
                        help="with --close: end a lane that will never report "
                             "done, recording why")
    parser.add_argument("--wait", action="store_true",
                        help="with --close: wait for a busy lane to go idle "
                             "(it sent done: and is finishing its turn), then "
                             "close it with the usual checks")
    parser.add_argument("--timeout", type=float, metavar="SECONDS",
                        help=f"with --close --wait: how long to wait before "
                             f"refusing (default {WAIT_TIMEOUT_SECONDS})")
    return parser


def main(argv: Sequence[str] = ()) -> int:
    """The act, then the stall banner: an open and a close are moments the desk
    is looking at this output anyway (`--list` prints the banner itself)."""
    code = run(argv)
    if not {"--list", "--reasons", "--dry-run", "-h", "--help"} & set(argv):
        for line in stalled_lines():
            print(line)
    return code


def run(argv: Sequence[str] = ()) -> int:
    args = build_parser().parse_args(argv)
    if args.reasons:
        return list_reasons()
    try:
        if args.list:
            return list_windows()
        if not args.name:
            raise TerminalError("--name is required unless --list is given")
        name = checked_name(args.name)
        abandoned = (args.abandoned or "").strip() or None
        timeout = check_wait(args.close, args.wait, args.timeout, abandoned)
        if args.close:
            session_cwd()
            return close_window(name, dry_run=args.dry_run, abandoned=abandoned,
                                wait=args.wait, timeout=timeout)
        if not args.role:
            raise TerminalError("--role is required unless --close or --list is given")

        # EVERY REFUSAL BEFORE ANYTHING IS WRITTEN OR OPENED, and identically
        # under --dry-run: a rehearsal that reported an open the real run would
        # refuse is a rehearsal that lies.
        model = chosen_model(args.role, args.model,
                             fable_approved=args.fable_approved_by_owner)
        tier = tier_choice(args.role, model, args.reason)
        cwd = session_cwd()
        window = window_for(args.role, name, args.task, tier.model,
                            resume=args.resume, remote_control=args.remote_control)
        mode = launch_mode()
        command = window_command(window, cwd=cwd) if mode == OPENED_BY_WT else None
        live_here = here(live_sessions())
        if not args.resume:
            refuse_a_taken_name(name, live_here)
        if args.role == LANE_ROLE:
            refuse_past_the_cap(live_here, read_record())
            if not args.resume:
                require_a_stamped_sheet(name, args.task, tier.reason)
    except TerminalError as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 2

    if command is not None:
        print(f"{window.label} as a tab in the {window.window_target!r} window, "
              f"{window.tab_color or 'uncoloured'}")
    else:
        print(f"{window.label}, opened by hand: {manual_reason()}")
    print(f"  model: {tier.model} - {tier.reason}: {tier.why}")
    print(f"  first instruction: {window.argv[-1]}")
    print(f"  remote control: {name}" if args.remote_control
          else f"  remote control: off ({NO_REMOTE_CONTROL_FLAG})")
    if command is not None:
        print(f"  closes its pane on: {window.close_marker}")
        print(f"  {command_line(command)}")
    elif args.dry_run:
        print(f"  {manual_line(window, cwd=cwd)}")
    if args.dry_run:
        print("  --dry-run: nothing was opened and nothing was recorded")
        return 0

    # A marker from a PREVIOUS window of this name would make this window's
    # first crash look deliberate and close the pane over the error.
    close_marker_path(name).unlink(missing_ok=True)
    if command is None:
        print_manual_open(window, cwd)
    else:
        try:
            launch(command)
        except (TerminalError, subprocess.CalledProcessError, OSError) as exc:
            # No window, but the first instruction above is the whole of what
            # would have been typed into one, so the manual path is on screen.
            print(f"FAIL - {exc}", file=sys.stderr)
            return 2
    # AFTER THE LAUNCH, so the record never claims a window that did not open.
    # A manual open is recorded at once: the line is the open, and the lane's
    # ack is what tells the desk the owner pasted it.
    append_record({
        "at": now_stamp(), "event": "open", "name": name, "role": args.role,
        "reason": tier.reason, "model": tier.model,
        "task": (args.task or "").strip(), "resumed": bool(args.resume),
        "opened_by": OPENED_BY_WT if command is not None else OPENED_BY_MANUAL,
        "remote_control": bool(args.remote_control),
    })
    return 0


def print_manual_open(window: Window, cwd: str) -> None:
    """The banner a manual open ends with: which tab to open, the one line to
    paste into it, and what the desk does next. Printed loud and last, because
    it is the whole of the open -- nothing else will start this window."""
    print(f"OPEN BY HAND - {manual_reason()}. Tell the owner: open a new "
          f"terminal tab, name it {window.tab_title or 'after the window'}, and "
          f"paste this one line:")
    print(f"  {manual_line(window, cwd=cwd)}")
    print("  Recorded as opened (opened_by: manual). Wait for its ack before "
          "counting it as started.")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
