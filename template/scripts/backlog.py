#!/usr/bin/env python3
"""The backlog ledger, `backlog.md`: every entry a desk logged for later and did not do.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere):
    <venv python> scripts/backlog.py                     # open count and the oldest entry
    <venv python> scripts/backlog.py list                # every open entry, one line each
    <venv python> scripts/backlog.py add "<short line>" --pointer <path[:line]> --from "<who logged it>" [--date YYYY-MM-DD]
    <venv python> scripts/backlog.py desk B3             # route: a desk job now
    <venv python> scripts/backlog.py park B3 --until "<what brings it back>"
    <venv python> scripts/backlog.py reword B3 "<short line>" --pointer <path[:line]> [--until "<what brings it back>"]
    <venv python> scripts/backlog.py reword B3 --note "<a shorter closing note>"   # a `## Closed` line
    <venv python> scripts/backlog.py close B3 --done "<the evidence: a commit, a path:line>"
    <venv python> scripts/backlog.py close B3 --dropped "<why nothing is lost>"
    <venv python> scripts/backlog.py check               # exit 1 on an unrouted, over-cap or
                                                         # pointerless entry, or a hand edit

WHY THIS EXISTS
---------------
A desk writes what it will not act on under `## Logged for later` in its desk
log, and `desk_save.py` archives the log under `closed/`. Nobody reads an
archive again: an item logged there is lost. So the backlog is one ledger with
one reader:
  * `desk_save.py` moves every Logged-for-later bullet of the desk it closes
    onto this ledger, in the same commit, parked until the blocker the bullet
    names (LOGGED FOR LATER, below);
  * `skills/close-session/SKILL.md` reads it every session and routes every
    entry -- a desk job now, parked with what brings it back, done with the
    evidence, or dropped with why -- through this script. `check` exits 1
    while any entry is unrouted, and the skill runs it before its commit.

THE FILE
--------
Written only by this script and `desk_save.py`. Each open entry is one line,
`- <id> · <logged> · <from> · <route> · <short line> → <pointer>`; `<route>`
is `open` (not yet routed), `desk job now`, or `parked until <what brings it
back>`. A closed entry leaves `## Open` for `## Closed`, which keeps the last
CLOSED_KEPT closings (older ones are in git history). A digest of everything
below the header sits on the `next id:` line, so a hand edit fails `check`
and is refused by every write. Ids are never reused.

A SHORT LINE AND A POINTER
--------------------------
An entry is one short line plus a pointer: the repo path (`:<line>` where one
fits) where its full words live -- the archived desk log, a task sheet, a kb
entry. `add`, `park` and `reword` refuse a line over ENTRY_CAP bytes and an
entry with no pointer or one naming no file; `close` caps its line at
CLOSED_CAP. Why: a ceiling on the whole file (doc_budgets.yaml) cannot shape
one entry. When entries were the logged bullet word for word, a handful of
long ones filled the file, and the only way back under its ceiling was to drop
entries that were not done. A cap per entry, at write time, makes the ceiling
measure how much work waits, not how wordy the loggers were.

LOGGED FOR LATER
----------------
A desk logs a find only when something outside its job blocks it -- an event
that has not happened, the owner's decision, another desk's live files, a
build that cannot run now. Anything else is done in the job. So each bullet
names its blocker, in this shape (BULLET):

    - <who>, <YYYY-MM-DD>, until <what brings it back>: <short line> — <their words>

`desk_save.py` refuses, before it closes anything, a bullet out of this shape
or with no blocker, and puts each one on the ledger as its short line, parked
until its blocker, pointing at the bullet's line in the archived desk log.

Exit codes: 0 = done; 1 = `check` found a problem; 2 = refused.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
#: The ledger, repo-relative. desk_save.py commits it by this path.
LEDGER_REL = "backlog.md"

SEP = " · "
OPEN = "open"
DESK = "desk job now"
PARKED = "parked until "
#: Closings kept in `## Closed` (older ones are in git history).
CLOSED_KEPT = 5
#: The most bytes one open entry's line may take, `- ` to its last character
#: (UTF-8, no line break). With the header, the `next id:` line and five
#: closings at CLOSED_CAP, an 8,000 b ceiling on backlog.md holds about 25
#: open entries at this cap (tests/test_backlog.py renders that ledger).
ENTRY_CAP = 250
#: The most bytes one `## Closed` line may take. The note is the closer's; the
#: excerpt of the entry's short line is cut to what is left, and a note that
#: leaves less than MIN_EXCERPT for it is refused.
CLOSED_CAP = 200
MIN_EXCERPT = 30
#: Between an entry's short line and its pointer.
POINTS = " → "

#: The heading of the desk-log section a desk logs into.
LOGGED = "## Logged for later"
#: A Logged-for-later bullet (without its `- `): who logged it, the day, the
#: blocker, the short line, then ` — ` and their words.
BULLET = re.compile(r"^(?P<who>[^,]+), (?P<date>\d{4}-\d{2}-\d{2}), until (?P<until>[^:]*[^:\s]): "
                    r"(?P<short>.+?) — (?P<words>.+)$")
BULLET_SHAPE = "- <who>, <YYYY-MM-DD>, until <what brings it back>: <short line> — <their words>"

HEADER = (
    "# Backlog\n"
    "\n"
    "What a desk logged for later and did not do, one line per open entry: "
    "id · logged · from · route · short line → where its full words are. "
    "`scripts/desk_save.py` adds a closing desk's `## Logged for later` bullets; "
    "`skills/close-session/SKILL.md` routes every entry through `scripts/backlog.py` "
    "(its docstring is the usage). Never edited by hand: the digest fails `backlog.py check`.\n"
)

_ID = re.compile(r"^B(\d+)$")
_NEXT = re.compile(r"^next id: B(\d+) · digest: ([0-9a-f]{12})$")
#: A pointer: a repo path with no spaces, and `:<line>` or `:<line>-<line>`.
_POINTER = re.compile(r"^(?P<path>[\w.\-/]*\w[\w.\-/]*?)(?::(?P<line>\d+)(?:-(?P<end>\d+))?)?$")
#: A `## Closed` line as `close` writes it.
_CLOSED = re.compile(r"^(?P<id>B\d+) · logged (?P<logged>\S+) · closed (?P<on>\S+) · "
                     r"(?P<kind>done|dropped): (?P<why>.*?) · from (?P<source>.*?) · (?P<excerpt>.*)$")


class Refused(Exception):
    """A write the ledger cannot take; the message says why and what to do."""


class Unsound(Refused):
    """The ledger on disk is not as this script last wrote it; `problems` names each way."""

    def __init__(self, message: str, problems: Sequence[str]):
        super().__init__(message)
        self.problems = list(problems)


@dataclass
class Entry:
    id: str
    logged: str
    source: str
    route: str
    text: str                  # the short line
    pointer: str = ""          # where its full words live: a repo path[:line]

    def line(self) -> str:
        last = self.text + (POINTS + self.pointer if self.pointer else "")
        return "- " + SEP.join((self.id, self.logged, self.source, self.route, last))


def size(line: str) -> int:
    return len(line.encode("utf-8"))


def split_pointer(text: str) -> tuple[str, str]:
    """(the short line, the pointer) of an entry's last field; the pointer is
    what follows its last ` → `, when that reads as a path; else empty."""
    if POINTS in text:
        short, pointer = text.rsplit(POINTS, 1)
        if _POINTER.match(pointer) and short.strip():
            return short.strip(), pointer
    return text, ""


def pointer_problem(pointer: str, root: Path | None) -> str | None:
    """What is wrong with `pointer`, or None. `root` is the folder the path is
    read from (the ledger's own); None checks the shape only."""
    if not pointer:
        return ("it has no pointer: end it with `--pointer <path[:line]>`, the repo path "
                "where its full words live (a closed desk log, a task sheet, a kb entry)")
    m = _POINTER.match(pointer)
    if not m:
        return f"its pointer {pointer!r} is not a repo path with no spaces, `:<line>` optional"
    if root is None:
        return None
    path = root / m.group("path")
    if not path.is_file():
        return f"its pointer {pointer!r} names no file on disk under {root.as_posix()}"
    if m.group("line"):
        lines = len(path.read_bytes().split(b"\n"))
        last = int(m.group("end") or m.group("line"))
        if not 1 <= int(m.group("line")) <= last <= lines:
            return f"its pointer {pointer!r} names a line {m.group('path')} does not have ({lines} lines)"
    return None


def over_cap(entry: Entry) -> str | None:
    """Why `entry`'s line is over ENTRY_CAP, saying what to shorten; or None."""
    n = size(entry.line())
    if n <= ENTRY_CAP:
        return None
    parts = [f"the short line ({size(entry.text)} b)"]
    if entry.route.startswith(PARKED):
        parts.append(f"the park text ({size(entry.route) - size(PARKED)} b)")
    return (f"its line is {n} b, over the {ENTRY_CAP} b cap by {n - ENTRY_CAP}: shorten "
            + " or ".join(parts) + "; the full words stay where its pointer leads")


def entry_problems(entry: Entry, root: Path | None) -> list[str]:
    """Every way `entry` breaks the cap or the pointer rule, each opening with its id."""
    found = (pointer_problem(entry.pointer, root), over_cap(entry))
    return [f"{entry.id}: {p}" for p in found if p]


def cut(text: str, room: int) -> str:
    """`text` cut to at most `room` bytes, ending in `…` when cut."""
    if size(text) <= room:
        return text
    out = text.encode("utf-8")[:max(room - size("…"), 0)].decode("utf-8", "ignore").rstrip()
    return out + "…"


@dataclass
class Ledger:
    next_id: int
    open: list
    closed: list               # the `## Closed` lines, newest last, without "- "

    def body(self) -> str:
        lines = ["## Open", ""] + [e.line() for e in self.open]
        lines += ["", f"## Closed (the last {CLOSED_KEPT}; older closings are in git history)", ""]
        lines += [f"- {c}" for c in self.closed]
        return "\n".join(lines) + "\n"

    def digest(self) -> str:
        return hashlib.sha256(f"{self.next_id}\n{self.body()}".encode("utf-8")).hexdigest()[:12]

    def render(self) -> str:
        return f"{HEADER}\nnext id: B{self.next_id} · digest: {self.digest()}\n\n{self.body()}"

    def find(self, entry_id: str) -> Entry:
        for e in self.open:
            if e.id == entry_id:
                return e
        raise Refused(f"{entry_id} is not an open entry of {LEDGER_REL} "
                      f"(`backlog.py list` prints every one)")


def empty() -> Ledger:
    return Ledger(next_id=1, open=[], closed=[])


def parse(text: str) -> tuple:
    """(the ledger in `text`, what is wrong with it: empty when sound)."""
    problems = []
    lines = text.replace("\r\n", "\n").split("\n")
    next_id, digest, section = None, None, None
    opened = []
    closed = []
    for n, line in enumerate(lines, 1):
        m = _NEXT.match(line)
        if m:
            next_id, digest = int(m.group(1)), m.group(2)
            continue
        if line.startswith("## "):
            section = "open" if line == "## Open" else "closed" if line.startswith("## Closed") else None
            continue
        if not line.startswith("- ") or section is None:
            continue
        if section == "closed":
            closed.append(line[2:])
            continue
        parts = line[2:].split(SEP, 4)
        if len(parts) != 5 or not _ID.match(parts[0]) or not all(p.strip() for p in parts):
            problems.append(f"line {n}: not `- <id> · <logged> · <from> · <route> · <entry>`")
            continue
        entry = Entry(*parts[:4], *split_pointer(parts[4]))
        if entry.route not in (OPEN, DESK) and not entry.route.startswith(PARKED):
            problems.append(f"line {n}: {entry.id}'s route {entry.route!r} is not "
                            f"`{OPEN}`, `{DESK}` or `{PARKED}<what brings it back>`")
        opened.append(entry)
    if next_id is None:
        problems.append("no `next id: B<n> · digest: <12 hex>` line")
        next_id = 1
    ledger = Ledger(next_id=next_id, open=opened, closed=closed)
    ids = [e.id for e in opened]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"{dup} is on more than one line")
    for e in opened:
        m = _ID.match(e.id)
        if m and int(m.group(1)) >= next_id:
            problems.append(f"{e.id} is not below `next id: B{next_id}`")
    if digest is not None and digest != ledger.digest():
        problems.append("its digest does not match its entries -- edited by hand, not by scripts/backlog.py")
    elif not problems and text.replace("\r\n", "\n") != ledger.render():
        problems.append("it holds text scripts/backlog.py does not write -- edited by hand")
    return ledger, problems


def read(path: Path) -> Ledger:
    """The ledger at `path` for a write: an empty one when there is none yet;
    refused when it is unsound, since a write on top would stamp a hand edit
    as this script's."""
    if not path.is_file():
        return empty()
    ledger, problems = parse(path.read_text(encoding="utf-8"))
    if problems:
        raise Unsound(f"{LEDGER_REL} is not as scripts/backlog.py last wrote it: "
                      + "; ".join(problems)
                      + ". Put it back as the last commit has it, then run this again", problems)
    return ledger


def write(path: Path, ledger: Ledger) -> None:
    path.write_text(ledger.render(), encoding="utf-8", newline="\n")


# --- what desk_save.py calls --------------------------------------------------


def bullets_from_log(text: str) -> list:
    """(the line number a bullet starts on, the bullet on one line) for each
    bullet under the desk log's `## Logged for later`, or under a `## Ruling`
    heading after it (the log is append-only, so a bullet logged after a later
    ruling sits under that ruling). An indented line under a bullet continues it."""
    seen, counting, continues = False, False, False
    bullets = []
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if line.startswith("## "):
            if line.strip() == LOGGED:
                seen, counting = True, True
            else:
                counting = seen and line.startswith("## Ruling")
            continues = False
        elif counting and line.startswith("- "):
            bullets.append((n, line[2:].strip()))
            continues = True
        elif continues and line[:1] in (" ", "\t") and line.strip():
            bullets[-1] = (bullets[-1][0], bullets[-1][1] + " " + line.strip())
        else:
            continues = False
    return [(n, b) for n, b in bullets if b]


def logged_problems(text: str, log_name: str = "the desk log") -> list:
    """What is wrong with the desk log's Logged-for-later bullets, one line each:
    a bullet out of BULLET's shape, or one that names no blocker."""
    problems = []
    for n, bullet in bullets_from_log(text):
        text1 = " ".join(bullet.split())
        if BULLET.match(text1):
            continue
        if ", until " not in text1.split(":", 1)[0]:
            problems.append(f"{log_name}:{n} names no blocker -- work nothing outside the job blocks "
                            f"is done in the job, not logged: {cut(text1, 100)}")
        else:
            problems.append(f"{log_name}:{n} is not `{BULLET_SHAPE}`: {cut(text1, 100)}")
    return problems


def move_logged(ledger: Ledger, text: str, archived_log: str, source: str, logged: str,
                root: Path | None) -> list:
    """Put each Logged-for-later bullet of the desk log `text` on the ledger:
    its short line, parked until its blocker, pointing at its line in
    `archived_log` (repo-relative). Returns the entries added. Refused, with
    nothing added, on a bullet out of shape or over ENTRY_CAP."""
    problems = logged_problems(text, archived_log)
    if problems:
        raise Refused("; ".join(problems))
    have = {(e.source, e.text) for e in ledger.open}
    fresh = []
    found = []
    next_id = ledger.next_id
    for n, bullet in bullets_from_log(text):
        m = BULLET.match(" ".join(bullet.split()))
        short = one_line(m.group("short"), "the short line")
        if (source, short) in have:
            continue
        entry = Entry(f"B{next_id}", logged, source, PARKED + one_line(m.group("until"), "the blocker"),
                      short, f"{archived_log}:{n}")
        found += entry_problems(entry, root)
        next_id += 1
        have.add((source, short))
        fresh.append(entry)
    if found:
        raise Refused(f"not added to {LEDGER_REL} (nothing was): " + "; ".join(found))
    ledger.next_id = next_id
    ledger.open.extend(fresh)
    return fresh


def add(ledger: Ledger, bullets: Sequence[str], source: str, logged: str, *,
        pointer: str | None = None, root: Path | None = REPO) -> list:
    """Put each bullet on the ledger as an `open` entry from `source`; returns
    the entries added. A bullet already open from the same source is not added
    twice. A bullet is `<short line> → <pointer>`, or its short line alone with
    the pointer given as `pointer`. Refused, with nothing added, when any bullet
    has no pointer, points at no file under `root`, or makes a line over ENTRY_CAP."""
    if SEP.strip() in source:
        raise Refused(f"the source {source!r} may not hold {SEP.strip()!r}")
    have = {(e.source, e.text) for e in ledger.open}
    fresh = []
    problems = []
    next_id = ledger.next_id
    for bullet in bullets:
        text, own = split_pointer(" ".join(bullet.split()))
        if not text or (source, text) in have:
            continue
        entry = Entry(f"B{next_id}", logged, source, OPEN, text, own or pointer or "")
        problems += entry_problems(entry, root)
        next_id += 1
        have.add((source, text))
        fresh.append(entry)
    if problems:
        raise Refused(f"not added to {LEDGER_REL} (nothing was): " + "; ".join(problems))
    ledger.next_id = next_id
    ledger.open.extend(fresh)
    return fresh


# --- routing ------------------------------------------------------------------


def one_line(note: str, what: str) -> str:
    note = " ".join(note.split())
    if not note:
        raise Refused(f"{what} cannot be empty")
    if SEP.strip() in note:
        raise Refused(f"{what} may not hold {SEP.strip()!r}, the ledger's field separator")
    return note


def route_desk(ledger: Ledger, entry_id: str) -> Entry:
    entry = ledger.find(entry_id)
    entry.route = DESK
    return entry


def route_park(ledger: Ledger, entry_id: str, until: str) -> Entry:
    entry = ledger.find(entry_id)
    route = PARKED + one_line(until, "--until (what brings it back)")
    new = Entry(entry.id, entry.logged, entry.source, route, entry.text, entry.pointer)
    problem = over_cap(new)
    if problem:
        raise Refused(f"{entry_id} not parked: {problem}")
    entry.route = route
    return entry


def reword(ledger: Ledger, entry_id: str, text: str, pointer: str, *, until: str | None = None,
           root: Path | None = REPO) -> Entry:
    """Give open entry `entry_id` a new short line and pointer (and, when it is
    parked, a new park text), keeping its id, logged date, from and route. The
    same cap and pointer rule as `add`; refused with the entry unchanged."""
    entry = ledger.find(entry_id)
    short = one_line(text, "the short line")
    if POINTS in short and split_pointer(short)[1]:
        raise Refused("give the pointer as --pointer, not inside the short line")
    route = entry.route
    if until is not None:
        if not route.startswith(PARKED):
            raise Refused(f"{entry_id} is not parked ({route!r}): --until rewords a park text only")
        route = PARKED + one_line(until, "--until (what brings it back)")
    new = Entry(entry.id, entry.logged, entry.source, route, short, pointer.strip())
    problems = entry_problems(new, root)
    if problems:
        raise Refused(f"{entry_id} not reworded: " + "; ".join(problems))
    entry.route, entry.text, entry.pointer = new.route, new.text, new.pointer
    return entry


def closed_line(entry_id: str, logged: str, on: str, kind: str, why: str, source: str,
                excerpt: str) -> str:
    """A `## Closed` line (without `- `) within CLOSED_CAP: the excerpt of the
    short line is cut to the room the note leaves; refused when that is less
    than MIN_EXCERPT."""
    fixed = SEP.join((entry_id, f"logged {logged}", f"closed {on}", f"{kind}: {why}",
                      f"from {source}")) + SEP
    room = CLOSED_CAP - size("- " + fixed)
    if room < MIN_EXCERPT:
        raise Refused(f"the {kind} note is {size(why)} b; a closed line is capped at {CLOSED_CAP} b, "
                      f"so with {entry_id}'s fields it may take at most "
                      f"{size(why) - (MIN_EXCERPT - room)} b. Name the evidence by its path:line "
                      f"or commit; the words stay there")
    return fixed + cut(excerpt, room)


def close(ledger: Ledger, entry_id: str, note: str, on: str) -> str:
    """Take `entry_id` off `## Open`; returns its `## Closed` line. `note` is
    `done: <evidence>` or `dropped: <why>`."""
    kind, _, why = note.partition(":")
    if kind not in ("done", "dropped"):
        raise Refused("a closing note is `done: <the evidence>` or `dropped: <why>`")
    why = one_line(why, f"the {kind} note")
    entry = ledger.find(entry_id)
    line = closed_line(entry.id, entry.logged, on, kind, why, entry.source, entry.text)
    ledger.open.remove(entry)
    ledger.closed = (ledger.closed + [line])[-CLOSED_KEPT:]
    return line


def reword_closed(ledger: Ledger, entry_id: str, note: str) -> str:
    """Give `## Closed` line `entry_id` a new note (its kind kept), the excerpt
    re-cut to fit CLOSED_CAP; returns the new line."""
    for i, line in enumerate(ledger.closed):
        m = _CLOSED.match(line)
        if m and m.group("id") == entry_id:
            why = one_line(note, f"the {m.group('kind')} note")
            excerpt = m.group("excerpt")
            if excerpt.endswith("…"):
                excerpt = excerpt[:-1]
            new = closed_line(entry_id, m.group("logged"), m.group("on"), m.group("kind"), why,
                              m.group("source"), excerpt)
            ledger.closed[i] = new
            return new
    raise Refused(f"{entry_id} is not a `## Closed` line of {LEDGER_REL}")


# --- what the reader is shown ---------------------------------------------------


def age(logged: str, today: date) -> str:
    try:
        days = (today - date.fromisoformat(logged)).days
    except ValueError:
        return "logged on an unreadable date"
    return f"{days} day{'s' if days != 1 else ''} old"


def status(ledger: Ledger, today: date) -> str:
    """The open count by route, and the oldest open entry."""
    if not ledger.open:
        return f"{LEDGER_REL}: 0 open"
    unrouted = sum(e.route == OPEN for e in ledger.open)
    desk = sum(e.route == DESK for e in ledger.open)
    parked = sum(e.route.startswith(PARKED) for e in ledger.open)
    oldest = min(ledger.open, key=lambda e: (e.logged, int(e.id[1:])))
    return (f"{LEDGER_REL}: {len(ledger.open)} open ({unrouted} unrouted, {desk} {DESK}, "
            f"{parked} parked); oldest {oldest.id}, logged {oldest.logged}, "
            f"{age(oldest.logged, today)}, from {oldest.source}: {oldest.text}")


def check(path: Path) -> tuple:
    if not path.is_file():
        return 0, [f"OK - no {LEDGER_REL} yet, so nothing is unrouted"]
    ledger, problems = parse(path.read_text(encoding="utf-8"))
    lines = [f"FAIL - {p}" for p in problems]
    for e in ledger.open:
        if e.route == OPEN:
            lines.append(f"FAIL - {e.id} is unrouted: `backlog.py desk {e.id}`, "
                         f"`park {e.id} --until ...`, or `close {e.id} --done|--dropped ...`")
        lines += [f"FAIL - {p} (`backlog.py reword {e.id} ...`)" for p in entry_problems(e, path.parent)]
    for c in ledger.closed:
        if size("- " + c) > CLOSED_CAP:
            lines.append(f"FAIL - closed {c.split(SEP, 1)[0]}: its line is {size('- ' + c)} b, over the "
                         f"{CLOSED_CAP} b cap (`backlog.py reword {c.split(SEP, 1)[0]} --note ...`)")
    if lines:
        return 1, lines + [f"{len(lines)} problem(s) in {LEDGER_REL}"]
    return 0, [f"OK - {len(ledger.open)} open in {LEDGER_REL}, every one routed, "
               f"within its cap and pointing at its words"]


# --- the command line -----------------------------------------------------------


def main(argv: Sequence[str] = (), *, path: Path | None = None, today: date | None = None) -> int:
    path = path or REPO / LEDGER_REL
    today = today or date.today()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="the open count and the oldest entry (the default)")
    sub.add_parser("list", help="every open entry, one line each")
    sub.add_parser("check", help="exit 1 on an unrouted, over-cap or pointerless entry, or a hand edit")
    pointer_help = ("the repo path, with :<line> where one fits, where the entry's full words live "
                    "(a closed desk log, a task sheet, a kb entry); it must be on disk")
    p = sub.add_parser("add", help="a new open entry; prints its id")
    p.add_argument("entry", help=f"the short line; with its fields and pointer the line is at most {ENTRY_CAP} b")
    p.add_argument("--pointer", help=pointer_help)
    p.add_argument("--from", dest="source", required=True,
                   help="who logged it: `desk <name>`, `session <YYYY-MM-DD>`")
    p.add_argument("--date", help="the day it became backlog (default today), YYYY-MM-DD")
    p = sub.add_parser("desk", help="route: a desk job now")
    p.add_argument("id")
    p = sub.add_parser("park", help="route: parked, with what brings it back")
    p.add_argument("id")
    p.add_argument("--until", required=True, help="what brings it back")
    p = sub.add_parser("reword", help="shorten an open entry (id, date, from and route kept) "
                                      "or a closed line's note")
    p.add_argument("id")
    p.add_argument("entry", nargs="?", help="the open entry's new short line")
    p.add_argument("--pointer", help=pointer_help)
    p.add_argument("--until", help="a parked entry's new park text")
    p.add_argument("--note", help="a `## Closed` line's new note (its done/dropped kept)")
    p = sub.add_parser("close", help="take an entry off the ledger, with a note")
    p.add_argument("id")
    how = p.add_mutually_exclusive_group(required=True)
    how.add_argument("--done", help="the evidence that it is done: a commit, a path:line")
    how.add_argument("--dropped", help="why dropping it loses nothing")
    args = parser.parse_args(list(argv))

    try:
        if args.cmd == "check":
            code, lines = check(path)
            print("\n".join(lines))
            return code
        ledger = read(path)
        if args.cmd in (None, "status"):
            print(status(ledger, today))
            return 0
        if args.cmd == "list":
            for e in ledger.open:
                print(e.line()[2:])
            print(status(ledger, today).split("; oldest")[0])
            return 0
        if args.cmd == "add":
            text = " ".join(args.entry.split())
            if not text:
                raise Refused("the entry cannot be empty")
            source = one_line(args.source, "--from (who logged it)")
            try:
                logged = date.fromisoformat(args.date).isoformat() if args.date else today.isoformat()
            except ValueError:
                raise Refused(f"--date {args.date!r} is not a date written YYYY-MM-DD") from None
            added = add(ledger, [text], source, logged, pointer=args.pointer, root=path.parent)
            if not added:
                short = split_pointer(text)[0]
                have = next(e for e in ledger.open if (e.source, e.text) == (source, short))
                print(f"already open: {have.id} (nothing written)")
                return 0
            write(path, ledger)
            print(added[0].id)
            print(status(ledger, today))
            return 0
        if args.cmd == "desk":
            said = route_desk(ledger, args.id).line()[2:]
        elif args.cmd == "park":
            said = route_park(ledger, args.id, args.until).line()[2:]
        elif args.cmd == "reword" and args.note is not None:
            if args.entry is not None or args.pointer is not None or args.until is not None:
                raise Refused("--note rewords a closed line alone: give no short line, --pointer or --until")
            said = "closed: " + reword_closed(ledger, args.id, args.note)
        elif args.cmd == "reword":
            if args.entry is None or args.pointer is None:
                raise Refused("reword an open entry with its new short line and --pointer <path[:line]>")
            said = reword(ledger, args.id, args.entry, args.pointer, until=args.until,
                          root=path.parent).line()[2:]
        else:
            note = f"done: {args.done}" if args.done is not None else f"dropped: {args.dropped}"
            said = "closed: " + close(ledger, args.id, note, today.isoformat())
        write(path, ledger)
        print(said)
        print(status(ledger, today))
        return 0
    except Refused as exc:
        print(f"REFUSED - {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
