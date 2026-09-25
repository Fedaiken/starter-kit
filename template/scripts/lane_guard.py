#!/usr/bin/env python3
"""Refuse a lane's git commands that save, publish or throw work away.

Wired as a `PreToolUse` hook on the shell tools in `.claude/settings.json`
(matcher `Bash|PowerShell` on Windows, `Bash` elsewhere --
`project_identity.hook_matcher`); it reads the hook's JSON payload on stdin.

WHY THIS EXISTS
---------------
Design ruling R22: every lane works in the ONE project folder and only the desk
saves to git. Until 2026-09-19 two things held a lane to that: a sentence in the
lane skill, and a permission pop-up on `git commit`. The owner had the pop-ups
removed -- committing and pushing is Claude's standing job, not a prompt to
babysit -- which left only the sentence. A sentence a window has to remember
is not a control (the project's cardinal rule).

So the refusal lives here, and costs the owner nothing: a lane that tries is
told no on the spot, with the reason, and carries on. It also refuses the commands
that destroy uncommitted work -- in a folder fifteen lanes share, one lane's
`git checkout -- .` or `git reset --hard` takes every other lane's edits with
it, and nothing downstream can catch that.

HOW IT KNOWS IT IS IN A LANE: `scripts/open_terminal.py` starts every window it
opens with `<PROJECT>_ROLE` and `<PROJECT>_WINDOW` in its environment (the
line printed for a manual open sets them the same way), and a hook inherits
the window's environment. No CLI call, no lookup, nothing to be stale. A
window the owner opened themselves has neither variable and is never refused
here. The two names are this project's, derived from its folder name by
`scripts/project_identity.py` (`Boat Log` -> `BOAT_LOG_ROLE`), so a lane of one
project is never read as another's.

This file is kit-owned (ported 2026-09-24 from FACOWORK by way of HAZELHURST
into the Starter Kit): identical in every seeded project, and an improvement
made here goes back with `python scripts/kit_sync.py push scripts/lane_guard.py`.

RECURSIVE DELETES (F57, S3). A lane also never deletes a tree anywhere but its
own scratchpad. At Session 3 an applying lane that could not land a block wrote
scratch scripts to rehearse the apply, then ran `rm -rf` on a variable path to
tidy up; the harness could not tell where the variable pointed, stopped at a
permission pop-up, and the owner had to find the tab. So a recursive delete --
`rm -r`/`-rf`, `Remove-Item -Recurse` (and its aliases), `rmdir /s`, `rd /s`,
`del /s`, `shutil.rmtree(...)` in inline Python -- is refused unless every path
it names is, literally, under `<temp>/claude/` or `<temp>/claude-<uid>/`, where
each session's scratchpad lives. `<temp>` is any of `%TEMP%`, `%TMP%` and
`$TMPDIR`, plus `/tmp` on macOS and Linux (where `/private/tmp` and
`/private/var` are read as the `/tmp` and `/var` they are). A path the guard
cannot read -- a variable it cannot expand, input from a pipe -- is not under
the scratchpad, by construction.

PATHS ARE READ AS THE MACHINE READS THEM (:func:`resolved`, `windows=`). On
Windows: drive letters, Git Bash's `/c/...` and `/tmp`, and case folded. On
macOS and Linux: POSIX paths as written, case kept -- a refusal on a
case-insensitive Mac volume is the safe direction to be wrong in.

Exit codes (the hook contract):
    0 = allowed -- not a lane, not a shell command, or not a refused command
    2 = refused; the reason on stderr is shown to the lane
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_identity import ROLE_ENV, WINDOW_ENV, is_windows  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

LANE_ROLE = "lane"
SHELL_TOOLS = ("Bash", "PowerShell")

#: git subcommands a lane never runs, each with what it would do to the room.
REFUSED = {
    "commit": "only the desk saves to git (R22)",
    "push": "only the desk saves to git (R22)",
    "stash": "a stash takes every lane's uncommitted work, not just yours",
    "reset": "it can throw away every lane's uncommitted work",
    "clean": "it deletes untracked files, other lanes' new files included",
    "checkout": "it can overwrite files other lanes are editing",
    "restore": "it can overwrite files other lanes are editing",
    "switch": "every lane shares this one working folder and its one branch",
    "rebase": "only the desk touches history",
    "merge": "only the desk touches history",
    "revert": "only the desk touches history",
    "cherry-pick": "only the desk touches history",
    "rm": "it stages a deletion; delete the file and let the desk's save record it",
    "mv": "it stages a rename; move the file and let the desk's save record it",
    "add": "staging is part of the desk's one save",
}

#: `git`, optionally with global options (`-C dir`, `-c k=v`, `--no-pager`),
#: then the subcommand. Matched anywhere in the line, so `cd x && git commit`
#: and `a; git push` are both seen.
_GIT = re.compile(
    r"(?<![\w./-])git(?:\.exe)?"
    r"(?:\s+(?:-[Cc]\s+\S+|--[\w-]+(?:=\S+)?|-\w))*"
    r"\s+([a-z][a-z-]*)"
)


def refused_subcommands(command: str) -> list[str]:
    """Every refused git subcommand the line would run, in order, once each."""
    found: list[str] = []
    for match in _GIT.finditer(command):
        sub = match.group(1)
        if sub in REFUSED and sub not in found:
            found.append(sub)
    return found


# --- recursive deletes -------------------------------------------------------

#: The folder under the temp directory that holds every session's scratchpad
#: (`%TEMP%\claude\<project>\<session>\scratchpad` on Windows; `claude` or
#: `claude-<uid>` under the temp folder elsewhere). A tree under it is
#: scratch; nothing else is a lane's to delete wholesale.
SCRATCH_DIR = "claude"
_SCRATCH_NAME = re.compile(r"^claude(?:-\d+)?$")
TEMP_VARS = ("TEMP", "TMP", "TMPDIR")

#: The temp folder a POSIX machine uses when no variable names one.
POSIX_TMP = "/tmp"

#: What separates one command from the next on a line, outside quotes.
#: Parentheses are NOT separators: `Remove-Item (Join-Path ...) -Recurse` must
#: stay one command, whose `(Join-Path` path is unreadable and so refused.
_SEPARATORS = ";|&\n"
_SEP = "\0"

#: Words after which the next word is a command, not an argument.
_PRECEDERS = {"sudo", "xargs", "-exec", "-execdir", "command", "nohup", "time",
              "/c", "/k", "call"}

#: A shell that runs its `-c` / `-Command` / `/c` argument as a command line.
_SHELLS = {"bash", "sh", "zsh", "powershell", "pwsh", "cmd"}
_SHELL_ARG = {"-c", "-command", "/c", "/k"}

#: Delete commands, and how each spells "recursive".
_RM = {"rm"}
_REMOVE_ITEM = {"remove-item", "ri", "del", "erase", "rd", "rmdir"}
_RM_CLUSTER = re.compile(r"^-[fiIrRdv]+$")      # bash `rm -rf`, `-Rf`, `-fr`
_CMD_FLAG = re.compile(r"^/[A-Za-z?]$")          # cmd `rmdir /s /q`
_PS_PATH_PARAMS = {"-path", "-literalpath", "-lp"}

_VAR = re.compile(r"\$env:(\w+)|\$\{(\w+)\}|\$(\w+)|%(\w+)%", re.I)
_RMTREE = re.compile(r"\brmtree\s*\(")
_RMTREE_LITERAL = re.compile(r"\s*[rRbBuU]*(['\"])(.*?)\1\s*[,)]")

#: What a path the guard cannot read is shown as.
UNREADABLE = "a path this guard cannot read (a variable it cannot expand, a sub-command or a pipe)"


def split_words(command: str) -> list[str]:
    """The line's words, quotes removed, with `_SEP` wherever a command ends."""
    words: list[str] = []
    word: list[str] = []
    quote = None
    started = False

    def flush() -> None:
        nonlocal started
        if started or word:
            words.append("".join(word))
        word.clear()
        started = False

    for ch in command:
        if quote:
            if ch == quote:
                quote = None
            else:
                word.append(ch)
        elif ch in "'\"":
            quote, started = ch, True
        elif ch in _SEPARATORS:
            flush()
            words.append(_SEP)
        elif ch.isspace():
            flush()
        else:
            word.append(ch)
    flush()
    return words


def segments(command: str) -> list[list[str]]:
    found: list[list[str]] = [[]]
    for word in split_words(command):
        if word == _SEP:
            found.append([])
        else:
            found[-1].append(word)
    return [seg for seg in found if seg]


def command_name(word: str) -> str:
    name = re.split(r"[\\/]", word)[-1].casefold()
    return name[:-4] if name.endswith(".exe") else name


def at_command_position(seg: Sequence[str], index: int) -> bool:
    if index == 0:
        return True
    if seg[index - 1].casefold() in _PRECEDERS:
        return True
    return all(re.match(r"^\w+=", word) for word in seg[:index])


def is_recurse_flag(word: str) -> bool:
    """`-r` .. `-Recurse`: PowerShell accepts any unambiguous prefix."""
    low = word.casefold()
    return len(low) >= 2 and "-recurse".startswith(low)


def delete_targets(seg: Sequence[str], index: int) -> tuple[bool, list[str]]:
    """Whether the delete command at `seg[index]` is recursive, and the paths
    it names."""
    name = command_name(seg[index])
    args = list(seg[index + 1:])
    recursive = False
    paths: list[str] = []
    only_paths = False
    for arg in args:
        low = arg.casefold()
        if only_paths:
            paths.append(arg)
        elif arg == "--":
            only_paths = True
        elif name in _RM and (low == "--recursive" or is_recurse_flag(arg)
                              or (_RM_CLUSTER.match(arg) and "r" in low[1:])):
            recursive = True
        elif name in _REMOVE_ITEM and (is_recurse_flag(arg) or low == "/s"):
            recursive = True
        elif arg.startswith("-") or (name in _REMOVE_ITEM and _CMD_FLAG.match(arg)):
            continue        # another flag; a -Path value is the word after it
        else:
            # PowerShell's `rm a,b` is two paths; split for every spelling, so
            # a scratch path cannot carry a project path past the check.
            paths.extend(p for p in arg.split(",") if p)
    return recursive, paths


def expand(raw: str, environ: dict[str, str]) -> str | None:
    """`raw` with the environment's variables expanded, or None when it names
    one the environment does not have (a variable the lane set itself)."""
    lower = {key.casefold(): value for key, value in environ.items()}
    missing = False

    def value(match: re.Match) -> str:
        nonlocal missing
        name = next(group for group in match.groups() if group)
        found = lower.get(name.casefold())
        if found is None:
            missing = True
            return match.group(0)
        return found

    text = _VAR.sub(value, raw)
    return None if missing or "$" in text else text


#: macOS keeps /tmp and /var as links into /private; a path through either
#: spelling is the same folder.
_PRIVATE = re.compile(r"^/private(?=/(?:tmp|var)(?:/|$))")


def normal(text: str, windows: bool) -> str:
    """A forward-slash absolute path normalised the way the machine compares
    paths: case folded on Windows, `/private` dropped on macOS."""
    text = posixpath.normpath(text)
    return text.casefold() if windows else _PRIVATE.sub("", text)


def resolved(raw: str, environ: dict[str, str], cwd: str | None, *,
             windows: bool | None = None) -> str | None:
    """`raw` as an absolute, normalised path with forward slashes (case folded
    on Windows); None when it cannot be read. `windows` defaults to this
    machine."""
    windows = is_windows() if windows is None else windows
    text = expand(raw.strip(), environ)
    if not text or any(ch in text for ch in "`(){}"):
        return None
    if text == "~" or text.startswith(("~/", "~\\")):
        home = (environ.get("USERPROFILE") or environ.get("HOME")) if windows \
            else environ.get("HOME")
        if not home:
            return None
        text = home + text[1:]
    text = text.replace("\\", "/")
    if windows:
        drive = re.match(r"^/([A-Za-z])(?=/|$)", text)        # Git Bash's /c/...
        if drive:
            text = drive.group(1) + ":" + text[2:]
        elif text == "/tmp" or text.startswith("/tmp/"):       # Git Bash's /tmp
            temp = environ.get("TEMP") or environ.get("TMP")
            if not temp:
                return None
            text = temp.replace("\\", "/") + text[4:]
        absolute = bool(re.match(r"^[A-Za-z]:/", text)) or text.startswith("/")
    else:
        absolute = text.startswith("/")
    if not absolute:
        if not cwd:
            return None
        text = cwd.replace("\\", "/").rstrip("/") + "/" + text
    return normal(text, windows)


def temp_bases(environ: dict[str, str], *, windows: bool | None = None) -> list[str]:
    """Every temp folder a session's scratchpad may sit under, normalised."""
    windows = is_windows() if windows is None else windows
    bases: list[str] = []
    named = [environ[var].replace("\\", "/") for var in TEMP_VARS if environ.get(var)]
    for base in named + ([] if windows else [POSIX_TMP]):
        base = normal(base, windows)
        if base not in bases:
            bases.append(base)
    return bases


def scratch_roots(environ: dict[str, str], *, windows: bool | None = None) -> list[str]:
    """The scratch folders, as a refusal names them."""
    return [f"{base}/{SCRATCH_DIR}"
            for base in temp_bases(environ, windows=windows)]


def under_scratch(raw: str, environ: dict[str, str], cwd: str | None, *,
                  windows: bool | None = None) -> bool:
    """Whether `raw` is strictly inside `<temp>/claude/` or `<temp>/claude-<uid>/`
    -- never the folder itself, which holds every session's scratchpad."""
    path = resolved(raw, environ, cwd, windows=windows)
    if path is None:
        return False
    for base in temp_bases(environ, windows=windows):
        if path.startswith(base.rstrip("/") + "/"):
            first, _, rest = path[len(base.rstrip("/")) + 1:].partition("/")
            if _SCRATCH_NAME.match(first) and rest:
                return True
    return False


def refused_deletes(command: str, environ: dict[str, str], cwd: str | None,
                    depth: int = 0, *, windows: bool | None = None) -> list[str]:
    """One line per recursive delete on the command line whose target is not
    under the scratchpad, naming the command and the path."""
    windows = is_windows() if windows is None else windows
    found: list[str] = []

    def outside(what: str, paths: Sequence[str]) -> None:
        if not paths:
            found.append(f"`{what}` on {UNREADABLE}")
        for raw in paths:
            if not under_scratch(raw, environ, cwd, windows=windows):
                shown = (raw if resolved(raw, environ, cwd, windows=windows)
                         else f"{raw} -- {UNREADABLE}")
                found.append(f"`{what}` on `{shown}`")

    for match in _RMTREE.finditer(command):
        literal = _RMTREE_LITERAL.match(command, match.end())
        outside("shutil.rmtree", [literal.group(2)] if literal else [])
    for seg in segments(command):
        for index, word in enumerate(seg):
            if not at_command_position(seg, index):
                continue
            name = command_name(word)
            if name in _SHELLS and depth < 3:
                args = seg[index + 1:]
                for at, arg in enumerate(args[:-1]):
                    if arg.casefold() in _SHELL_ARG:
                        found += refused_deletes(args[at + 1], environ, cwd,
                                                 depth + 1, windows=windows)
            if name in _RM or name in _REMOVE_ITEM:
                recursive, paths = delete_targets(seg, index)
                if recursive:
                    outside(f"{word} (recursive)", paths)
    return found


def verdict(payload: dict, environ: dict[str, str], *,
            windows: bool | None = None) -> str | None:
    """The refusal to show the lane, or None to allow. `windows` says how
    paths are read; it defaults to this machine."""
    windows = is_windows() if windows is None else windows
    if environ.get(ROLE_ENV) != LANE_ROLE:
        return None
    if payload.get("tool_name") not in SHELL_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    subs = refused_subcommands(command)
    deletes = refused_deletes(command, environ, cwd, windows=windows)
    if not subs and not deletes:
        return None
    lane = environ.get(WINDOW_ENV, "this lane")
    said = []
    if subs:
        reasons = "; ".join(f"`git {sub}` -- {REFUSED[sub]}" for sub in subs)
        said.append(f"{reasons}. A lane edits the files it owns and reports to "
                    "the desk; the desk makes the job's one save.")
    if deletes:
        roots = " or ".join(f"{root}/..." for root in
                            scratch_roots(environ, windows=windows)) \
            or "the temp folder's claude/..."
        said.append(
            f"a recursive delete outside your scratchpad: {'; '.join(deletes)}. "
            f"A lane deletes a tree only under its own scratchpad ({roots}), "
            f"named by a path this guard can read -- in FACOWORK a lane's scratch "
            f"`rm -rf` on a variable path raised a permission pop-up the owner had "
            f"to find. Project files are never a lane's to delete this way, and "
            f"a block you cannot land is a `question:` to the desk, not a "
            f"scratch rehearsal.")
    return (f"REFUSED for lane {lane}: {' '.join(said)} If your task truly needs "
            "this, send the desk `question:` -- do not look for another way to "
            "run it.")


def main(argv: Sequence[str] = ()) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, UnicodeError):
        return 0  # an unreadable payload is not a reason to stop a window
    if not isinstance(payload, dict):
        return 0
    said = verdict(payload, dict(os.environ))
    if said is None:
        return 0
    print(said, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
