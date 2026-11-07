#!/usr/bin/env python3
"""How much of its context window each Claude window of this project holds.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/context_meter.py --report
    <venv python> scripts/context_meter.py --peaks --since 2026-11-02

WHY THIS EXISTS
---------------
The owner, 2026-11-02, after a desk here warned of a crowded window on a guess
while his status line read 24%: "it jsut means you are not really tracking
context accurately". A desk that guesses its own load either hands over a
window that had room or rides one into compaction, and compaction is a
failed run. FACOWORK measured this after a lane died at its ceiling
("Prompt is too long" at 970,937 tokens, Session 55); this is its
`scripts/context_meter.py`, ported 2026-11-02 (`kb/lane-context-sizing.md`).

WHAT IS MEASURED
----------------
Every window writes its own transcript,
`~/.claude/projects/<this project's key>/<sessionId>.jsonl`, one JSON entry per
line. Each real assistant turn carries `message.usage`, and
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens` on it is
the context that turn carried. `claude agents --json` (read through
`open_terminal.live_sessions`) names every live window's `sessionId`. So:

* a window's TOKENS NOW is that sum on its last real assistant entry, read from
  the tail of the file -- a live window's transcript runs to megabytes;
* its PEAK is the largest such sum on any turn;
* its LAST ERROR is the last assistant entry when that entry is an API error
  (`isApiErrorMessage: true`). The CLI writes such an entry itself, every usage
  count zero, so it is never a turn's tokens: a window dead at its ceiling
  still reads at the size it died at;
* its LAST TURN (:func:`last_turn`) is how its last assistant entry ended
  (`message.stop_reason`), when, and whether the turn -- back to the prompt
  that started it -- said `done:`, `question:` or `prompting:`, in its text or
  a `SendMessage`. The opener's IDLE, NOT DONE line reads it (FACOWORK desk
  decision DI19: a lane ended a turn mid-task and sat idle 27 minutes);
* THIS WINDOW is the live session whose pid is in this process's ancestry
  (`open_terminal.own_ancestry`), so a stamp knows which desk ran it without
  anyone passing a name. A Git Bash child whose walk up breaks before
  claude.exe (a script run as `bash x.sh`: Git Bash's exec ends the process it
  replaces) is matched by the CLAUDE_PID Claude puts in its environment,
  believed only when the process table shows the break was born after that
  claude.exe.

`--calibrate`, which refits the lane predictor on these peaks, is in
`scripts/lane_budget.py`, beside the predictor it tests; it builds on
:func:`lane_transcripts`, :func:`first_user_entry` and :func:`peak_tokens`.

BEST EFFORT, NEVER SILENT
-------------------------
A transcript that cannot be found or read gives None, never a guess and never
an exception into the act a caller rides on; the CLI prints
`METER UNREADABLE — <window>` for it. Reading a transcript is a plain file
read, which no permission prompt stops.

Exit codes:
    0 = printed (a METER UNREADABLE line is a printed finding, not a failure)
    2 = the live-window list itself could not be read (`--report`), or the
        arguments were wrong
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import open_terminal  # noqa: E402
import project_identity as identity  # noqa: E402
from wt import TerminalError  # noqa: E402

# The Windows console is cp1252 and cannot encode the em dash every
# METER UNREADABLE line carries.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = identity.REPO

#: The context window, measured on this machine twice. FACOWORK, Session 55
#: (2026-09-25T18:51:16Z): a lane carried 970,937 tokens on its last turn and its
#: next request came back "Prompt is too long". Savecraft, 2026-11-02: the desk
#: savecraft-e2 carried 244,859 tokens on its turn of 20:57:24Z (claude-opus-5-5),
#: and the owner's next message, 20:59:23Z, read the status line as "we are at 24%" --
#: 244,859 is 24.5% of 1,000,000 (desk transcript fe857878-...jsonl).
WINDOW_TOKENS = 1_000_000

#: The usage fields whose sum is the context a turn carried.
USAGE_FIELDS = ("input_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens")

#: The error fields that mean the window is dead at its ceiling rather than
#: stopped by something a resume gets past.
DEAD_ERROR = "invalid_request"
DEAD_TEXT = "Prompt is too long"

#: How much of a transcript's end is read first; doubled until an assistant
#: entry is found or the whole file has been read. One Read result can put
#: 300 KB on a single line, so the first bite is not the last.
TAIL_BYTES = 256 * 1024

UNREADABLE = "METER UNREADABLE — "

#: The mark `--report` puts on the window that ran it.
THIS_WINDOW = "<- THIS WINDOW"

_LANE_COMMAND = re.compile(
    r"<command-name>/lane</command-name>.*?<command-args>\s*([^\s<]+)", re.S)
_LANE_TYPED = re.compile(r"^\s*/lane\s+([^\s]+)")


def project_key(path: Path) -> str:
    """The folder name Claude gives a workspace under `projects/`: every
    character that is not a letter, digit or dash becomes a dash
    (`C:\\Users\\someone\\Claude\\Project` -> `C--Users-someone-Claude-Project`,
    the folder on disk)."""
    return re.sub(r"[^A-Za-z0-9-]", "-", str(path))


def _config_dir() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


#: This workspace's transcript folder.
PROJECT_DIR = _config_dir() / "projects" / project_key(REPO)


# --- one transcript ----------------------------------------------------------


def transcript_path(session_id: str) -> Path | None:
    """The transcript of `session_id`, or None when there is no such file."""
    if not session_id or not re.fullmatch(r"[A-Za-z0-9._-]+", str(session_id)):
        return None
    path = PROJECT_DIR / f"{session_id}.jsonl"
    return path if path.is_file() else None


def _entry(line: bytes | str) -> dict | None:
    """One transcript line as a dict; None for a line that is not one (a
    half-written last line of a live window, a blank)."""
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    line = line.strip()
    if not line:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    return entry if isinstance(entry, dict) else None


def _is_assistant(entry: dict) -> bool:
    """An assistant entry of the window itself -- a subagent's sidechain turn
    carries another context, not this window's."""
    return entry.get("type") == "assistant" and not entry.get("isSidechain")


def _turn_tokens(entry: dict) -> int | None:
    """The context a real assistant turn carried; None for an API-error entry
    (all zeros, written by the CLI) or an entry with no usage."""
    if not _is_assistant(entry) or entry.get("isApiErrorMessage"):
        return None
    usage = (entry.get("message") or {}).get("usage")
    if not isinstance(usage, dict):
        return None
    total = 0
    for name in USAGE_FIELDS:
        value = usage.get(name)
        if isinstance(value, int):
            total += value
    return total or None


def _tail_bites(path: Path):
    """The file's end in growing bites: each yield is `(entries, whole)`, the
    complete entries of the bite LAST FIRST, and whether the bite reached the
    start of the file. Each bite holds the one before it, so a reader scans the
    newest yield only and stops as soon as it has its answer."""
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        bite = TAIL_BYTES
        while True:
            start = max(0, size - bite)
            handle.seek(start)
            data = handle.read(size - start)
            lines = data.split(b"\n")
            if start > 0:
                lines = lines[1:]   # the first line is cut mid-way
            entries = [e for e in (_entry(line) for line in reversed(lines))
                       if e is not None]
            yield entries, start == 0
            if start == 0:
                return
            bite *= 2


def _tail_entries(path: Path, wanted) -> dict | None:
    """The LAST entry of `path` for which `wanted(entry)` is true, reading the
    file from its end in growing bites."""
    for entries, _whole in _tail_bites(path):
        for entry in entries:
            if wanted(entry):
                return entry
    return None


def tokens_now(path) -> int | None:
    """The context the window's last real assistant turn carried; None when
    the file cannot be read or holds no such turn."""
    try:
        entry = _tail_entries(Path(path), lambda e: _turn_tokens(e) is not None)
    except (OSError, TypeError):
        return None
    return None if entry is None else _turn_tokens(entry)


def peak_tokens(path) -> int | None:
    """The largest context any assistant turn of the window carried."""
    peak = None
    try:
        with open(Path(path), "rb") as handle:
            for line in handle:
                if b'"assistant"' not in line or b'"usage"' not in line:
                    continue
                entry = _entry(line)
                tokens = None if entry is None else _turn_tokens(entry)
                if tokens is not None and (peak is None or tokens > peak):
                    peak = tokens
    except (OSError, TypeError):
        return None
    return peak


def message_text(entry: dict) -> str:
    """The text of an entry's message: a string, or its text blocks joined."""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(block.get("text", "")) for block in content
                        if isinstance(block, dict) and block.get("type") == "text")
    return ""


def last_error(path) -> dict | None:
    """`{"error", "text", "at"}` when the window's last assistant entry is an
    API error; None when it is a real turn, or the file cannot be read. A
    window resumed after an error has real turns after it, so it reads None."""
    try:
        entry = _tail_entries(Path(path), _is_assistant)
    except (OSError, TypeError):
        return None
    if entry is None or not entry.get("isApiErrorMessage"):
        return None
    return {"error": entry.get("error"), "text": message_text(entry),
            "at": entry.get("timestamp")}


def is_dead_at_ceiling(err: dict | None) -> bool:
    """True for the error a window cannot be resumed past: its prompt no
    longer fits (`invalid_request`, "Prompt is too long"). Every other API
    error -- a server error mid-response, overloaded, rate-limited -- is
    resumable."""
    if not err:
        return False
    return err.get("error") == DEAD_ERROR or DEAD_TEXT in str(err.get("text") or "")


# --- the last turn (the IDLE, NOT DONE line) ---------------------------------

#: The lines a lane sends the desk that end its work for now: it finished, or
#: it is waiting on the desk (skills/lane/SKILL.md, Step 3 and Step 5).
REPORT_KINDS = ("done", "question", "prompting")

#: Lower case, as the protocol writes them: a "Done:" heading in a lane's
#: prose is not the line.
_REPORT = re.compile(r"^[\s>*_`\-]*(" + "|".join(REPORT_KINDS) + r")\s*:", re.M)


def _is_tool_result(entry: dict) -> bool:
    content = (entry.get("message") or {}).get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _is_prompt(entry: dict) -> bool:
    """A user entry that starts a turn: something typed (the owner, a role
    command) or a message from another session, which the CLI records as a
    meta entry of origin `peer` (measured in FACOWORK, 2026-09-28). Never a
    tool result, a sidechain, or a meta entry the CLI injects mid-turn."""
    if entry.get("type") != "user" or entry.get("isSidechain") \
            or _is_tool_result(entry):
        return False
    if entry.get("isMeta"):
        origin = entry.get("origin")
        return isinstance(origin, dict) and origin.get("kind") == "peer"
    return True


def _said(entry: dict) -> list[str]:
    """What an assistant entry said: its text blocks, and every string a
    `SendMessage` it made carries -- a lane's `done:` and `question:` lines go
    to the desk through that tool, not into its text."""
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    said = []
    for block in content if isinstance(content, list) else ():
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            said.append(str(block.get("text", "")))
        elif block.get("type") == "tool_use" and block.get("name") == "SendMessage":
            said += [v for v in (block.get("input") or {}).values()
                     if isinstance(v, str)]
    return said


def reports_in(texts) -> set[str]:
    """Which of REPORT_KINDS open a line anywhere in `texts` (`done:`,
    `question: ...`; a quote, bullet, bold or backtick before it allowed)."""
    found = set()
    for text in texts:
        found |= {m.group(1) for m in _REPORT.finditer(str(text))}
    return found


def last_turn(path) -> dict | None:
    """`{"stop_reason", "at", "reports"}` for the window's last turn: how its
    last assistant entry ended (`end_turn`, `tool_use`, ...), when, and which
    REPORT_KINDS the turn said since the prompt that started it. None when the
    file cannot be read, holds no assistant entry, or its last assistant entry
    is an API error (that window's line is NEEDS THE DESK or DEAD AT ITS
    CEILING, not this one)."""
    try:
        for entries, whole in _tail_bites(Path(path)):
            turn: list[dict] = []
            for entry in entries:
                if _is_prompt(entry):
                    break
                if _is_assistant(entry):
                    turn.append(entry)
            else:
                if not whole:
                    continue
            break
        else:
            return None
    except (OSError, TypeError):
        return None
    if not turn or turn[0].get("isApiErrorMessage"):
        return None
    said = [text for entry in turn for text in _said(entry)]
    return {"stop_reason": (turn[0].get("message") or {}).get("stop_reason"),
            "at": turn[0].get("timestamp"), "reports": reports_in(said)}


# --- live windows ------------------------------------------------------------


def percent_of_window(tokens: int | None) -> float | None:
    return None if tokens is None else round(100 * tokens / WINDOW_TOKENS, 1)


def window_state(session: dict, *, peak: bool = False) -> dict:
    """`{"name", "session_id", "tokens", "percent", "error"}` for one live
    session as `claude agents --json` reports it, and `"peak"` when asked for
    (it reads the whole file); `tokens` and `percent` are None when its
    transcript cannot be found or read."""
    session_id = str(session.get("sessionId") or "")
    path = transcript_path(session_id)
    tokens = None if path is None else tokens_now(path)
    state = {
        "name": session.get("name"),
        "session_id": session_id,
        "tokens": tokens,
        "percent": percent_of_window(tokens),
        "error": None if path is None else last_error(path),
    }
    if peak:
        state["peak"] = None if path is None else peak_tokens(path)
    return state


def this_window(sessions: list[dict] | None = None) -> dict | None:
    """The live session running this process -- the one whose pid is in this
    process's ancestry, else the one Claude's environment names when the
    process table shows this process can be its child (:func:`_env_window`).
    None when the list cannot be read, or when no session (or more than one
    in this workspace) matches."""
    try:
        if sessions is None:
            sessions = open_terminal.live_sessions()
    except TerminalError:
        return None
    ancestry = open_terminal.own_ancestry()
    mine = [row for row in sessions if ancestry and row.get("pid") in ancestry]
    if not mine:
        return _env_window(sessions)
    if len(mine) > 1:
        mine = open_terminal.here(mine)
    return mine[0] if len(mine) == 1 else None


# --- a Git Bash child ---------------------------------------------------------
#
# Measured in FACOWORK 2026-10-15: the Bash tool's shell runs a script it is
# handed (`bash "$TMP/x.sh"`) by exec, and Git Bash's exec ends the Windows
# process it replaces. The script's bash keeps that process's pid as its
# ParentProcessId, the pid is in no live row, and the walk up stops there, so a
# desk act printed METER UNREADABLE where the same act run plainly read it.
# Claude sets CLAUDE_PID (its own pid) and CLAUDE_CODE_SESSION_ID in every
# child's environment (both present in this project's lane windows,
# 2026-11-02), and they survive that exec; but an environment can be inherited
# by a shell that is not Claude's child, so it is believed only when the
# process table agrees.


def _can_be_child_of(pid: int, table: list) -> bool:
    """Whether this process can descend from `pid` although the walk up from
    it never reaches `pid`: the walk's top -- the oldest process it reaches,
    where a parent is gone or recycled -- was born after `pid` was. A shell
    whose chain climbs whole past processes older than `pid` is not its child,
    whatever its environment says. False where the table has no creation
    times (`ps` on macOS and Linux), so the environment is never believed
    there on its own."""
    born = {row.get("ProcessId"): row.get("Created") for row in table
            if isinstance(row, dict)}
    claude_born = born.get(pid)
    chain = open_terminal.ancestry_from(table, os.getpid())
    if not chain:
        return False
    if pid in chain:
        return True
    if not isinstance(claude_born, int):
        return False
    created = [born.get(p) for p in chain]
    if not all(isinstance(c, int) for c in created):
        return False
    return min(created) > claude_born


def _env_window(sessions: list[dict]) -> dict | None:
    """The live row Claude's environment names -- the one whose pid is
    CLAUDE_PID and, when CLAUDE_CODE_SESSION_ID is set, whose sessionId is
    that -- if the process table shows this process can be its child. None
    otherwise: unreadable, never another window's number."""
    try:
        pid = int(os.environ.get("CLAUDE_PID", ""))
    except ValueError:
        return None
    rows = [row for row in sessions if row.get("pid") == pid]
    if len(rows) != 1:
        return None
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session_id and rows[0].get("sessionId") != session_id:
        return None
    return rows[0] if _can_be_child_of(pid, open_terminal.process_table()) else None


# --- lane transcripts --------------------------------------------------------


def lane_name(entry: dict) -> str | None:
    """The lane name if this user entry is the `/lane <name> <sheet>` role
    command -- as the opener's slash command records it, or typed plain."""
    text = message_text(entry)
    found = _LANE_COMMAND.search(text) or _LANE_TYPED.match(text)
    return found.group(1) if found else None


def first_user_entry(path: Path) -> dict | None:
    """The window's first user message: not a meta entry, not a tool result."""
    with open(path, "rb") as handle:
        for line in handle:
            if b'"user"' not in line:
                continue
            entry = _entry(line)
            if entry is None or entry.get("type") != "user" \
                    or entry.get("isMeta") or entry.get("isSidechain") \
                    or _is_tool_result(entry):
                continue
            return entry
    return None


def _since_date(since: str | None) -> date | None:
    if not since:
        return None
    try:
        return datetime.fromisoformat(since).date()
    except ValueError:
        return date.fromisoformat(since)


def lane_transcripts(since: str | None = None,
                     folder: Path | None = None) -> dict[str, Path]:
    """Every transcript in the project folder whose first user message is
    `/lane <name> ...`, keyed by lane name. A name used twice keeps the window
    started latest. `since`, an ISO date, keeps only transcripts modified on or
    after it. An unreadable file is skipped -- it cannot be named a lane."""
    folder = PROJECT_DIR if folder is None else Path(folder)
    cutoff = _since_date(since)
    found: dict[str, tuple[str, Path]] = {}
    try:
        paths = sorted(folder.glob("*.jsonl"))
    except OSError:
        return {}
    for path in paths:
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime).date()
            if cutoff is not None and modified < cutoff:
                continue
            entry = first_user_entry(path)
        except OSError:
            continue
        name = None if entry is None else lane_name(entry)
        if not name:
            continue
        started = str(entry.get("timestamp") or "") or datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc).isoformat()
        if name not in found or started >= found[name][0]:
            found[name] = (started, path)
    return {name: path for name, (_, path) in sorted(found.items())}


# --- the command line --------------------------------------------------------


def tokens_text(tokens: int, percent: float) -> str:
    return f"{tokens:>9,} tokens  {percent:5.1f}%"


def error_text(err: dict | None) -> str:
    if not err:
        return ""
    kind = ("DEAD AT ITS CEILING" if is_dead_at_ceiling(err)
            else "STOPPED ON AN API ERROR (resumable)")
    return f"  {kind}: {err.get('error')} at {err.get('at')}: \"{err.get('text')}\""


def report_lines(sessions: list[dict], mine: dict | None = None) -> list[str]:
    """One line per live window: tokens now, share of the window, peak, and
    the THIS WINDOW mark on the one that ran this (`mine`)."""
    lines = []
    mine_id = str((mine or {}).get("sessionId") or "")
    for session in sorted(sessions, key=lambda r: str(r.get("name"))):
        state = window_state(session, peak=True)
        name = str(state["name"])
        mark = f"  {THIS_WINDOW}" if mine_id and state["session_id"] == mine_id else ""
        if state["tokens"] is None:
            lines.append(f"{UNREADABLE}{name}{mark}{error_text(state['error'])}")
            continue
        peak = state.get("peak")
        peak_said = f"  peak {peak:>9,}" if peak is not None else "  peak unreadable"
        lines.append(f"  {name:<24} {tokens_text(state['tokens'], state['percent'])}"
                     f"{peak_said}{mark}{error_text(state['error'])}")
    return lines


def report() -> int:
    try:
        live = open_terminal.live_sessions()
    except TerminalError as exc:
        print(f"{UNREADABLE}every window: {exc}", file=sys.stderr)
        return 2
    live_here = open_terminal.here(live)
    if not live_here:
        print("no live Claude session in this workspace")
        return 0
    mine = this_window(live)
    print(f"{len(live_here)} live in this workspace "
          f"(window: {WINDOW_TOKENS:,} tokens); tokens now, share of the window, peak")
    for line in report_lines(live_here, mine):
        print(line)
    if mine is None or not any(row.get("sessionId") == mine.get("sessionId")
                               for row in live_here):
        print(f"{UNREADABLE}this window: it is not one of the live sessions here")
    return 0


def peaks_lines(since: str | None, folder: Path | None = None) -> list[str]:
    lines = []
    for name, path in lane_transcripts(since, folder).items():
        peak = peak_tokens(path)
        if peak is None:
            lines.append(f"{UNREADABLE}{name} ({path.name})")
            continue
        lines.append(f"  {name:<28} {tokens_text(peak, percent_of_window(peak))}"
                     f"  {path.stem}")
    return lines


def peaks(since: str | None) -> int:
    lines = peaks_lines(since)
    print(f"{len(lines)} lane transcript(s)"
          + (f" modified on or after {since}" if since else "")
          + f" -- peak per lane (window: {WINDOW_TOKENS:,} tokens)")
    for line in lines:
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", action="store_true",
                      help="every live window in this workspace: tokens now, "
                           "share of the window, peak, error state; THIS WINDOW "
                           "marked")
    mode.add_argument("--peaks", action="store_true",
                      help="every lane transcript with its peak tokens")
    parser.add_argument("--since", metavar="ISO_DATE",
                        help="with --peaks: only transcripts modified on or "
                             "after this date")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.since and not args.peaks:
        parser.error("--since is for --peaks")
    if args.since:
        try:
            _since_date(args.since)
        except ValueError:
            parser.error(f"--since {args.since!r} is not an ISO date")
    return report() if args.report else peaks(args.since)


if __name__ == "__main__":
    raise SystemExit(main())
