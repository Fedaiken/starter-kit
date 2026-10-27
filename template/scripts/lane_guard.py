#!/usr/bin/env python3
"""Refuse a lane's git commands that save, publish or throw work away -- and, in
every window, a PowerShell text write into a project file and the command
shapes that raise a permission pop-up.

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
by the lane rules. The two names are this project's, derived from its folder
name by `scripts/project_identity.py` (`Boat Log` -> `BOAT_LOG_ROLE`), so a
lane of one project is never read as another's.

This file is kit-owned (ported 2026-09-24 from FACOWORK by way of HAZELHURST
into the Starter Kit): identical in every seeded project, and an improvement
made here goes back with `<venv python> scripts/kit_sync.py push scripts/lane_guard.py`.

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

POWERSHELL TEXT WRITES -- EVERY WINDOW (ported 2026-10-26). The rule that holds
whatever `<PROJECT>_ROLE` is: the desk, the owner's own windows and lanes
alike. Windows PowerShell 5.1 writes `Set-Content` / `Add-Content` text in the
ANSI codepage and `Out-File` text in UTF-16, and `-Encoding utf8` adds a
byte-order mark; in the project this guard came from, a desk's two such edits
corrupted 244 lines of a run log. The desk improvised the edit, so no skill
file named it and no sentence in one would have stopped it. So the three
cmdlets (and 5.1's `sc` / `ac` aliases, where PowerShell reads the line) are
refused when their target is a file in the project folder, or a target the
guard cannot read; a target under the temp folder or outside the project
passes. The project folder is `$CLAUDE_PROJECT_DIR`, which Claude Code hands
every hook, else the folder `scripts/project_identity.py` names. The write side
is where the damage lands -- a mis-decoded read never written back harms
nothing -- and the `>` / `>>` redirections are left alone. A device (`NUL`,
`$null`) is not a file and passes.

LITERAL BLOCKS ARE TEXT. A PowerShell here-string (`$t = @'` .. `'@`) and a
bash heredoc (`<<'EOF'` .. `EOF`) carry text, not commands. A quote reader
that does not know them is left "inside a quote" by an apostrophe in the body
(`the owner's answers`): the write that follows the block runs unrefused, and
a body that merely mentions `Add-Content` is refused as a command. Each block
is folded into one quoted word before the line is read for the every-window
rules -- a double-quoted body (or an unquoted heredoc's) keeping its `$(...)`,
which the shell still runs.

POP-UP SHAPES -- EVERY WINDOW (ported 2026-10-26). Claude Code runs its own
safety checks on a shell command, and some of them ask the owner whatever the
permission mode -- and nobody is at a lane's screen to answer, while a pop-up
in a desk costs the owner exactly what one in a lane does. A hook runs before
those checks and its refusal reaches only the window, so the shapes a pop-up
log tied to a pop-up are refused here, each with the way to do the same thing
without one:
  * a Bash `rm` / `rmdir` whose path holds a shell variable or a substitution
    (`$X`, `${X}`, `$(...)`, a backtick) -- "Dangerous rm operation on
    possibly-empty variable path". Name the path literally, or delete inside
    Python. PowerShell's `Remove-Item $x` is not refused: it never raised one.
  * a Bash `sed -i` on a file outside the project folder and outside the temp
    folder (a memory file under `~/.claude`). Edit it with the Edit tool.
A target the line sets itself (`S="C:/..."; sed -i ... "$S/f"`) is read
before it is judged; an in-place edit whose target cannot be read is left
alone, since the log never tied one to a pop-up.

PATHS ARE READ AS THE MACHINE READS THEM (:func:`resolved`, `windows=`). On
Windows: drive letters, Git Bash's `/c/...` and `/tmp`, and case folded. On
macOS and Linux: POSIX paths as written, case kept -- a refusal on a
case-insensitive Mac volume is the safe direction to be wrong in.

Exit codes (the hook contract):
    0 = allowed -- not a shell command, or not a refused command
    2 = refused; the reason on stderr is shown to the window
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from pathlib import Path
from typing import Iterator, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

from project_identity import (REPO, ROLE_ENV, WINDOW_ENV, is_windows,  # noqa: E402
                              venv_python_rel)

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


# --- reading a command line ---------------------------------------------------

#: What separates one command from the next on a line, outside quotes.
#: Parentheses are NOT separators: `Remove-Item (Join-Path ...) -Recurse` must
#: stay one command, whose `(Join-Path` path is unreadable and so refused.
_SEPARATORS = ";|&\n"
_SEP = "\0"

#: Words after which the next word is a command, not an argument.
_PRECEDERS = {"sudo", "xargs", "-exec", "-execdir", "command", "nohup", "time",
              "/c", "/k", "call", "env", "exec", "if", "elif", "while", "until",
              "then", "do", "else", "!", "{", "("}

#: What may open a word and still leave a command inside it: a subshell, a
#: PowerShell sub-expression or array, a block -- `(rm -rf x)`, `$(Set-Content ...)`.
_OPENER = re.compile(r"^(?:\$\(|@\(|\(|\{)+")

#: A shell that runs its `-c` / `-Command` / `/c` argument as a command line,
#: and how that line is read: `bash` (quotes, `$(...)`, backticks, backslash
#: escapes), `ps` (quotes, `$(...)`) or `cmd` (no substitution at all).
_SHELLS = {"bash": "bash", "sh": "bash", "zsh": "bash",
           "powershell": "ps", "pwsh": "ps", "cmd": "cmd"}
_SHELL_ARG = {"-c", "-command", "/c", "/k"}
#: PowerShell's own "run this string": every non-flag argument is a command line.
_EVALUATORS = {"iex", "invoke-expression"}


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
    name = re.split(r"[\\/]", _OPENER.sub("", word))[-1].casefold()
    return name[:-4] if name.endswith(".exe") else name


def at_command_position(seg: Sequence[str], index: int) -> bool:
    if index == 0 or _OPENER.match(seg[index]):
        return True
    before = seg[index - 1]
    if before.casefold() in _PRECEDERS:
        return True
    # `A=1 B=2 cmd`, `env A=1 cmd`: an assignment keeps the command position.
    return bool(re.match(r"^\w+=", before)) and at_command_position(seg, index - 1)


def substitutions(command: str, mode: str) -> list[str]:
    """The bodies of the command substitutions the line's shell would run:
    `$( ... )` anywhere but inside single quotes, and in bash `` `...` `` too."""
    if mode == "cmd":
        return []
    bodies: list[str] = []
    quote = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote == "'":
            if ch == "'":
                quote = None
        elif mode == "bash" and ch == "\\":
            i += 2
            continue
        elif ch == "'" and quote is None:
            quote = "'"
        elif ch == '"':
            quote = None if quote == '"' else '"'
        elif command.startswith("$(", i):
            depth, j = 0, i + 1
            while j < n:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            bodies.append(command[i + 2:j])
            i = j + 1
            continue
        elif mode == "bash" and ch == "`":
            j = command.find("`", i + 1)
            j = n if j < 0 else j
            bodies.append(command[i + 1:j])
            i = j + 1
            continue
        i += 1
    return bodies


#: A PowerShell here-string's opener: `@'` or `@"` ending its line.
_PS_HERE_OPEN = re.compile(r"@(['\"])[ \t]*\r?\n")
#: A bash heredoc's operator and delimiter (`<<EOF`, `<<-'EOF'`, `<< "EOF"`);
#: not `<<<`, a here-string on one line, which the quote reader already reads.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\2")


def fold_ps_here_strings(command: str) -> str:
    """The line with each PowerShell here-string (`@'` .. `'@`, `@"` .. `"@`)
    folded into one quoted word. Its body is text, not commands, and a quote
    inside it (`the owner's answers`) must not leave the reader inside a quote.
    A double-quoted body keeps its `$(...)`, which PowerShell still runs."""
    out: list[str] = []
    quote = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            quote = None if ch == quote else quote
        else:
            opened = _PS_HERE_OPEN.match(command, i)
            if opened:
                mark = opened.group(1)
                close = re.compile(r"^[ \t]*" + re.escape(mark) + "@", re.M).search(
                    command, opened.end())
                body = command[opened.end():close.start() if close else n]
                out.append("''" if mark == "'" else '"' + body.replace('"', "") + '"')
                i = close.end() if close else n
                continue
            if ch in "'\"":
                quote = ch
        out.append(ch)
        i += 1
    return "".join(out)


def fold_heredocs(command: str) -> str:
    """The line with each bash heredoc's body folded into one quoted word on
    the operator's line. The body is the command's input, not commands: a
    quoted delimiter's body is dropped, an unquoted one's kept as a
    double-quoted word, so its `$(...)` and backticks are still read."""
    out: list[str] = []
    pending: list[tuple[bool, bool, str]] = []
    quote = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote == "'":
            quote = None if ch == "'" else quote
        elif ch == "\\" and quote is None:
            out.append(command[i:i + 2])
            i += 2
            continue
        elif ch == '"':
            quote = None if quote == '"' else '"'
        elif quote is None and ch == "'":
            quote = "'"
        elif quote is None and command.startswith("<<", i):
            found = _HEREDOC.match(command, i)
            if found:
                pending.append((bool(found.group(1)), bool(found.group(2)), found.group(3)))
                out.append(command[i:found.end()])
                i = found.end()
                continue
        elif quote is None and ch == "\n" and pending:
            i += 1
            for strip_tabs, quoted, delimiter in pending:
                body: list[str] = []
                while i < n:
                    end = command.find("\n", i)
                    end = n if end < 0 else end
                    line = command[i:end]
                    i = end + 1
                    if (line.lstrip("\t") if strip_tabs else line).rstrip("\r") == delimiter:
                        break
                    body.append(line)
                if not quoted:
                    text = "\n".join(body).replace('"', "").replace("\\", "")
                    out.append(' "' + text + '"')
            pending = []
            out.append("\n")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def fold_literal_blocks(command: str, mode: str) -> str:
    """The line with the multi-line text blocks its shell reads as data --
    PowerShell's here-strings, bash's heredocs -- each folded into a word."""
    if mode == "ps":
        return fold_ps_here_strings(command)
    if mode == "bash":
        return fold_heredocs(command)
    return command


def command_lines(command: str, mode: str, depth: int = 0
                  ) -> Iterator[tuple[str, str]]:
    """Every command line the line would run, with the shell reading it: the
    line itself, a shell's `-c` argument, an `Invoke-Expression` string and a
    command substitution's body -- each with its literal blocks folded."""
    if depth > 3:
        return
    command = fold_literal_blocks(command, mode)
    yield command, mode
    for seg in segments(command):
        for index, word in enumerate(seg):
            if not at_command_position(seg, index):
                continue
            name = command_name(word)
            args = seg[index + 1:]
            if name in _SHELLS:
                for at, arg in enumerate(args[:-1]):
                    if arg.casefold() in _SHELL_ARG:
                        yield from command_lines(args[at + 1], _SHELLS[name], depth + 1)
            elif name in _EVALUATORS:
                for arg in args:
                    if not arg.startswith("-"):
                        yield from command_lines(arg, "ps", depth + 1)
    for body in substitutions(command, mode):
        yield from command_lines(body, mode, depth + 1)


def commands(command: str, mode: str) -> Iterator[tuple[list[str], int, str]]:
    """Every command the line would run, as (its segment, the index of its name,
    the shell reading it) -- those inside a shell's `-c` argument, an
    `Invoke-Expression` string and a command substitution included."""
    for line, reader in command_lines(command, mode):
        for seg in segments(line):
            for index in range(len(seg)):
                if at_command_position(seg, index):
                    yield seg, index, reader


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


def under(path: str, roots: Sequence[str]) -> bool:
    """Whether `path` is strictly inside one of `roots` (normalised paths)."""
    return any(path.startswith(root.rstrip("/") + "/") for root in roots)


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
                    outside(f"{_OPENER.sub('', word)} (recursive)", paths)
    return found


# --- the project folder (the every-window rules) ------------------------------


def project_root(environ: dict[str, str], *, windows: bool | None = None) -> str:
    """The project folder, normalised: `$CLAUDE_PROJECT_DIR`, which Claude Code
    hands every hook, else the folder `project_identity` names."""
    windows = is_windows() if windows is None else windows
    root = environ.get("CLAUDE_PROJECT_DIR") or str(REPO)
    return normal(root.replace("\\", "/"), windows)


def in_project(path: str, root: str) -> bool:
    return path == root or under(path, [root])


# --- PowerShell text writes into the project (every window) --------------------

#: The cmdlets that write text through PowerShell's own encoding, and the
#: aliases 5.1 ships for two of them -- the aliases counted only where
#: PowerShell reads the line (in bash, `sc` is not Set-Content).
_PS_WRITERS = {"set-content", "add-content", "out-file"}
_PS_WRITER_ALIASES = {"sc", "ac"}

#: The writers' parameters: those naming the target, those taking a value, and
#: switches. PowerShell accepts any unambiguous prefix; an unknown parameter is
#: read as a switch, so a value after it counts as a positional -- which can
#: only ever add a refusal, never hide a target.
_PS_TARGETS = ("-path", "-literalpath", "-pspath", "-filepath", "-lp")
_PS_VALUED = ("-value", "-encoding", "-stream", "-filter", "-include", "-exclude",
              "-credential", "-width", "-inputobject", "-erroraction",
              "-warningaction", "-informationaction", "-errorvariable",
              "-warningvariable", "-informationvariable", "-outvariable",
              "-outbuffer", "-pipelinevariable")
_PS_SWITCHES = ("-force", "-nonewline", "-passthru", "-whatif", "-confirm",
                "-append", "-noclobber", "-asbytestream", "-usetransaction",
                "-verbose", "-debug")
_PS_PARAMS = _PS_TARGETS + _PS_VALUED + _PS_SWITCHES

#: `$p = 'x'` (three words) or `$p='x'` (one) -- a PowerShell variable the line
#: sets itself, so a later `Set-Content $p` can be read.
_PS_ASSIGN = re.compile(r"^\$(\w+)=(.+)$")
_PS_VARIABLE = re.compile(r"^\$(\w+)$")
#: What a variable the line sets but the guard cannot read expands to.
_UNREADABLE_VALUE = "$unreadable"

WRITE_REASON = (
    "Windows PowerShell 5.1 writes `Set-Content` / `Add-Content` text in the "
    "ANSI codepage and `Out-File` text in UTF-16, and `-Encoding utf8` adds a "
    "byte-order mark -- in the project this guard came from, two such edits "
    "corrupted 244 lines of a run log. Edit a project file with the Edit or "
    "Write tool, or write it from a Python script "
    f"(`{venv_python_rel()}`, `encoding=\"utf-8\"`). This rule holds in every "
    "window, not only a lane's; a target under the temp folder or outside the "
    "project is not its business.")


def ps_parameter(word: str) -> str:
    """The full name of the parameter `word` spells (`-lit` -> `-literalpath`),
    or the word itself when it is unknown or ambiguous."""
    low = word.casefold()
    if low in _PS_PARAMS:
        return low
    hits = [name for name in _PS_PARAMS if name.startswith(low)]
    return hits[0] if len(hits) == 1 else low


def write_targets(seg: Sequence[str], index: int) -> list[str]:
    """The paths the writer at `seg[index]` writes to: its `-Path` (or
    `-LiteralPath`, `-FilePath`) values, else its first positional argument."""
    explicit: list[str] = []
    positional: list[str] = []
    take = None
    for arg in seg[index + 1:]:
        if take:
            if take == "target":
                explicit.append(arg)
            take = None
        elif re.match(r"^-[A-Za-z]", arg):
            name, colon, attached = arg.partition(":")
            param = ps_parameter(name)
            if param in _PS_TARGETS:
                if colon:
                    explicit.append(attached)
                else:
                    take = "target"
            elif param in _PS_VALUED and not colon:
                take = "value"
        else:
            positional.append(arg)
    return [p for raw in (explicit or positional[:1])
            for p in raw.rstrip(")}").split(",") if p]


def assignments(command: str, environ: dict[str, str]) -> dict[str, str]:
    """The variables the line sets itself, each as the guard reads its value --
    `_UNREADABLE_VALUE` where it cannot (`$p = Join-Path ...`)."""
    found: dict[str, str] = {}
    for seg in segments(fold_ps_here_strings(command)):
        variable = _PS_VARIABLE.match(seg[0])
        joined = _PS_ASSIGN.match(seg[0]) if len(seg) == 1 else None
        if variable and len(seg) >= 3 and seg[1] == "=":
            name, value = variable.group(1), seg[2] if len(seg) == 3 else None
        elif joined:
            name, value = joined.groups()
        else:
            continue
        text = expand(value, {**environ, **found}) if value is not None else None
        readable = text is not None and not any(ch in text for ch in "`(){}")
        found[name] = text if readable else _UNREADABLE_VALUE
    return found


#: Windows' reserved device names: `NUL`, `CON` .. -- in any folder and with
#: any extension, a write to one reaches the device, never a file.
_DEVICES = {"nul", "con", "prn", "aux", *(f"com{n}" for n in range(1, 10)),
            *(f"lpt{n}" for n in range(1, 10))}


def is_device(raw: str) -> bool:
    """Whether `raw` names a device rather than a file: a reserved name, or
    PowerShell's `$null`."""
    text = raw.strip()
    if text.casefold() == "$null":
        return True
    stem = re.split(r"[\\/]", text)[-1].split(".")[0].rstrip(" :")
    return stem.casefold() in _DEVICES


def refused_writes(command: str, environ: dict[str, str], cwd: str | None,
                   mode: str = "ps", *, windows: bool | None = None) -> list[str]:
    """One line per PowerShell text write on the command line whose target is
    in the project folder or cannot be read."""
    windows = is_windows() if windows is None else windows
    found: list[str] = []
    root = project_root(environ, windows=windows)
    temps = temp_bases(environ, windows=windows)
    known = {**environ, **assignments(command, environ)}
    for seg, index, reader in commands(command, mode):
        name = command_name(seg[index])
        if name not in _PS_WRITERS and not (reader == "ps" and name in _PS_WRITER_ALIASES):
            continue
        what = _OPENER.sub("", seg[index])
        paths = write_targets(seg, index)
        if not paths:
            found.append(f"`{what}` on {UNREADABLE}")
        for raw in paths:
            if is_device(raw):
                continue
            path = resolved(raw, known, cwd, windows=windows)
            if path is None:
                found.append(f"`{what}` on `{raw}` -- {UNREADABLE}")
            elif under(path, temps):
                continue
            elif in_project(path, root):
                found.append(f"`{what}` on `{raw}`")
    return found


# --- command shapes that raise a permission pop-up (every window) -------------

#: Bash deletes Claude Code stops on a variable path, asking the owner.
_POPUP_DELETES = {"rm", "rmdir"}
#: What in a path makes Claude Code call it "possibly-empty": a variable, a
#: `$(...)` or a backtick -- anything the shell fills in at run time.
_RUNTIME_PATH = re.compile(r"[$`]")
#: `S="C:/x"` as one word (its quotes gone): a variable a bash line sets itself.
_BASH_ASSIGN = re.compile(r"^([A-Za-z_]\w*)=(.*)$", re.S)

POPUP_REASON = (
    "Claude Code asks the owner before running these, whatever the permission "
    "mode, and nobody is at a lane's screen to answer; a hook refusal reaches "
    "only this window. As one owner said of a lane's `rm \"$R/$T/x-nokept.md\"`: "
    "\"we should not be doing things in a way that generates prompts like "
    "this\". Do the same thing another way: write the path out literally in "
    "the command -- the temp folder's full path, not `$TEMP/...` or `$VAR/...` "
    "-- or delete inside Python (`os.remove(...)` on a path built there); edit "
    "a file outside the project with the Edit tool. This "
    "rule holds in every window, not only a lane's.")


def bash_assignments(command: str, environ: dict[str, str]) -> dict[str, str]:
    """The variables a bash line sets itself (`S="C:/x"; ...`), each as the
    guard reads its value -- `_UNREADABLE_VALUE` where it cannot."""
    found: dict[str, str] = {}
    for seg in segments(fold_heredocs(command)):
        joined = _BASH_ASSIGN.match(seg[0]) if len(seg) == 1 else None
        if not joined:
            continue
        name, value = joined.groups()
        text = expand(value, {**environ, **found})
        readable = text is not None and not any(ch in text for ch in "`(){}")
        found[name] = text if readable else _UNREADABLE_VALUE
    return found


def sed_in_place_targets(seg: Sequence[str], index: int) -> list[str] | None:
    """The files the `sed` at `seg[index]` edits in place, or None when it
    does not edit in place (no `-i` / `--in-place`)."""
    in_place = False
    script_given = False
    operands: list[str] = []
    take = False
    for arg in seg[index + 1:]:
        if take:
            take = False
        elif arg in ("-e", "--expression", "-f", "--file"):
            script_given, take = True, True
        elif arg.startswith(("--expression=", "--file=")):
            script_given = True
        elif arg.startswith("--in-place") or re.match(r"^-[a-zA-Z]*i", arg):
            in_place = True
            # `-ie` style clusters end in a flag that takes the script
            if re.match(r"^-[a-zA-Z]*[ef]$", arg):
                script_given, take = True, True
        elif arg.startswith("-"):
            continue
        else:
            operands.append(arg)
    if not in_place:
        return None
    return operands if script_given else operands[1:]


def refused_popups(command: str, environ: dict[str, str], cwd: str | None,
                   mode: str = "bash", *, windows: bool | None = None) -> list[str]:
    """One line per command on the line whose shape raises a permission
    pop-up, naming the command and the path."""
    windows = is_windows() if windows is None else windows
    found: list[str] = []
    root = project_root(environ, windows=windows)
    temps = temp_bases(environ, windows=windows)
    known: dict[str, str] | None = None
    for seg, index, reader in commands(command, mode):
        if reader != "bash":
            continue
        name = command_name(seg[index])
        what = _OPENER.sub("", seg[index])
        if name in _POPUP_DELETES:
            _, paths = delete_targets(seg, index)
            for raw in paths:
                if _RUNTIME_PATH.search(raw):
                    found.append(f"`{what}` on `{raw}` -- a path filled in at run "
                                 f"time (\"possibly-empty variable path\")")
        elif name == "sed":
            for raw in sed_in_place_targets(seg, index) or ():
                if known is None:
                    known = {**environ, **bash_assignments(command, environ)}
                path = resolved(raw, known, cwd, windows=windows)
                if path is None or under(path, temps):
                    continue
                if not in_project(path, root):
                    found.append(f"`{what} -i` on `{raw}` -- a file outside the "
                                 f"project folder")
    return found


# --- the verdict ---------------------------------------------------------------


def verdict(payload: dict, environ: dict[str, str], *,
            windows: bool | None = None) -> str | None:
    """The refusal to show the window, or None to allow. `windows` says how
    paths are read; it defaults to this machine."""
    windows = is_windows() if windows is None else windows
    tool = payload.get("tool_name")
    if tool not in SHELL_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    mode = "bash" if tool == "Bash" else "ps"

    # The every-window rules, before the role is asked.
    writes = refused_writes(command, environ, cwd, mode, windows=windows)
    write_said = (f"a PowerShell text write into a project file: "
                  f"{'; '.join(writes)}. {WRITE_REASON}") if writes else None
    popups = refused_popups(command, environ, cwd, mode, windows=windows)
    popup_said = (f"a command shape that raises a permission pop-up: "
                  f"{'; '.join(popups)}. {POPUP_REASON}") if popups else None
    every_window = " ".join(s for s in (write_said, popup_said) if s)
    if environ.get(ROLE_ENV) != LANE_ROLE:
        return f"REFUSED in this window: {every_window}" if every_window else None

    subs = refused_subcommands(command)
    deletes = refused_deletes(command, environ, cwd, windows=windows)
    if not subs and not deletes and not every_window:
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
    if every_window:
        said.append(every_window)
    if subs or deletes:
        said.append("If your task truly needs this, send the desk `question:` "
                    "-- do not look for another way to run it.")
    return f"REFUSED for lane {lane}: {' '.join(said)}"


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
