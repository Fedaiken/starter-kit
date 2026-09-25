"""Build a Windows Terminal invocation -- or, where there is none, the line to
paste into a terminal tab -- without knowing what it will run.

Adapted 2026-09-19 from Fantasy Football's `src/ffb/wt.py` (reconciliation
build, slice 1). `scripts/open_terminal.py` is the caller: it knows what a desk
and a lane are, and this module knows only how to get a command into a tab
intact. Left behind on purpose: window placement and sizing, which that project
needed for its draft boards and this one has no use for.

Everything below that says MEASURED was measured in Fantasy Football on this
same machine and Windows Terminal; the dates are kept so the claim can be
traced.

Carried from FACOWORK by way of HAZELHURST into the Starter Kit (2026-09-24);
the manual line for machines without Windows Terminal was added there.
This file is kit-owned: identical in every seeded project, and an improvement
made here goes back with `python scripts/kit_sync.py push scripts/wt.py`.

WHY THE COMMAND IS BASE64 AND NOT QUOTED
---------------------------------------
The prompt a window opens with is arbitrary prose -- a task, with spaces,
apostrophes and whatever punctuation the sentence needed. It has to survive two
re-parses to reach the program:

1. ``wt.exe`` splits its own command line on ``;``, which is how it separates
   panes. A semicolon in a task would open a second pane running the rest of
   the sentence.
2. ``powershell.exe -Command`` JOINS its remaining arguments with spaces and
   re-parses the result, so quoting does not survive the hand-off. Measured
   2026-08-22: ``x;calc`` passed as one argument ran the command and then
   ``calc`` as a second statement.

``-EncodedCommand`` takes base64 of UTF-16LE instead, and base64 is
``[A-Za-z0-9+/=]`` -- no space, no semicolon, no quote. The hazard is not
handled; it cannot arise.

THERE IS A THIRD HAND-OFF AND NOTHING HERE COVERS IT. What PowerShell passes to
a NATIVE PROGRAM is a separate layer, and a JSON argument does not survive it
(measured 2026-08-23 with ``claude --settings '{...}'``). The remedy is not
more quoting: write the value to a file and pass its path.

WHY A KILLED WINDOW NEEDS A MARKER AND NOT ``; exit 0``
-------------------------------------------------------
Windows Terminal's default ``closeOnExit`` is ``graceful``, which closes a pane
only on exit code 0, and the opener's ``--close`` ends a session with
``taskkill /F`` -- the only request Windows accepts for a console process. So
the program exits 1 and the pane stays behind reading ``[process exited with
code 1]``.

Ending the statement ``; exit 0`` would close that pane. It would also close
the pane of a Claude that died on its own, taking the error off the screen with
it -- the only place a window that never reached its prompt says why. So the
statement exits 0 for the deliberate case ALONE: ``--close`` plants a marker
file before it kills, and :func:`close_epilogue` exits 0 when it finds that
marker and passes the real exit code through when it does not. A crash keeps
its last screen; a window somebody closed on purpose goes.

A TAB IN A NAMED WINDOW
-----------------------
With a ``window_target`` the invocation is ``-w <target> new-tab``. Measured
2026-08-26: the name CREATES the window when it is absent and JOINS it when it
is present, and it never lands a tab in the window the owner is typing in --
which ``-w 0`` ("most recently used") would. A tab's pane exiting 0 closes that
tab and leaves the ones beside it.

``--title`` is passed and the application's own title is NOT suppressed:
``claude`` retitles the tab with the session name and a working/idle glyph, and
suppressing that would throw the glyph away. ``--title`` is what the tab reads
for the second before the session boots.

WHERE THERE IS NO WINDOWS TERMINAL: THE MANUAL LINE
---------------------------------------------------
On macOS and Linux -- and on a Windows machine without ``wt.exe`` on PATH --
nothing here guesses at a terminal program: there are dozens, each with its
own flags, and a wrong guess opens nothing or opens it somewhere nobody looks.
:func:`manual_line` instead builds the ONE line the owner pastes into a new
terminal tab: change to the project folder, set the window's two variables,
start ``claude`` with the same argv the Windows Terminal path runs. POSIX sh
syntax on macOS and Linux (bash and zsh read it the same), PowerShell syntax on
Windows. There is no close marker on that path: the tab is the owner's own
shell, and it stays at its prompt when the session ends.
"""

from __future__ import annotations

import base64
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping, NamedTuple, Sequence

# The Windows console is cp1252 and cannot encode the arrows and check marks
# this project writes in; without this a task quoted back in a dry run dies
# with UnicodeEncodeError instead of being printed.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


class TerminalError(Exception):
    """A window could not be built, opened or closed."""


#: The launcher itself. Not a fixed path: `wt.exe` is a Store alias on PATH.
TERMINAL = "wt.exe"

SHELL = "powershell.exe"

#: `-EncodedCommand` is what makes the command immune to both re-parses;
#: `-NoExit` is the one a caller chooses -- see :func:`shell_args`.
SHELL_ARGS = ("-NoExit", "-EncodedCommand")


def shell_args(*, keep_open: bool) -> tuple[str, ...]:
    """The shell switches for a window that does, or does not, outlive its job.

    A window holding a CONVERSATION does not keep `-NoExit`: a role window that
    stays open after its session ends is a dead window that still looks live.
    """
    return SHELL_ARGS if keep_open else ("-EncodedCommand",)


class Window(NamedTuple):
    """One window to open: what to call it, and the argv it runs.

    ``close_marker`` is a path whose EXISTENCE, when the program has exited,
    means the program was stopped on purpose rather than having failed; see
    :func:`close_epilogue`. The path is only ever a string to this module.

    ``window_target`` is the NAME OF THE WINDOW this opens into: with one, the
    invocation is ``-w <target> new-tab``; without one it is ``-w new``.

    ``tab_color`` is the caller's word, not this module's -- nothing here knows
    what a role or a model is.
    """

    label: str
    argv: tuple[str, ...]
    keep_open: bool = True
    close_marker: str | None = None
    window_target: str | None = None
    tab_title: str | None = None
    tab_color: str | None = None
    env: tuple[tuple[str, str], ...] = ()


def quote(token: str) -> str:
    """A token as it would be typed. Only quoted when it has to be.

    A LEADING `#` HAS TO BE: a tab colour is `#RRGGBB`, and PowerShell starts a
    comment at a `#` that begins a token (measured 2026-08-26). This line is
    printed to be PASTED -- it is the manual path a failed launch leaves on
    screen -- so an unquoted colour would hand over a line that stops at the
    colour.
    """
    return f'"{token}"' if (" " in token or not token or token.startswith("#")) else token


def command_line(argv: Sequence[str]) -> str:
    """One pasteable line, for a dry run and for a failure message."""
    return " ".join(quote(token) for token in argv)


def ps_quote(token: str) -> str:
    """One token as a PowerShell single-quoted string.

    Single quotes rather than double: PowerShell expands nothing inside them,
    so a ``$`` or a backtick in a task is a character. The single quote itself
    -- any English possessive -- is doubled.
    """
    return "'" + str(token).replace("'", "''") + "'"


def close_epilogue(marker: str) -> str:
    """What a window's statement ends with when a killed pane must still close.

    1. ``$code`` takes ``$LASTEXITCODE``, or 1 when that is ``$null`` -- which
       it is when the program never ran at all, and ``exit $null`` exits 0,
       closing the pane over the one message explaining why it is empty.
    2. The marker, if there, means somebody asked for this window to end: the
       code becomes 0. It is REMOVED as it is read, so the next window of this
       name starts without one.
    3. ``exit $code``: the shell's own exit code is what Terminal reads.
    """
    quoted = ps_quote(marker)
    return (
        "; $code = if ($null -eq $LASTEXITCODE) { 1 } else { $LASTEXITCODE }"
        f"; if (Test-Path -LiteralPath {quoted}) {{ "
        f"Remove-Item -LiteralPath {quoted} -Force -ErrorAction SilentlyContinue"
        "; $code = 0 }"
        "; exit $code"
    )


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def ps_statement(argv: Sequence[str], *, close_marker: str | None = None,
                 env: Sequence[tuple[str, str]] = ()) -> str:
    """``argv`` as one PowerShell statement, every token single-quoted.

    ``env`` is set in the shell BEFORE the program starts, so the program and
    everything it starts -- a Claude window's hooks included -- inherit it.
    That is how a hook knows it is running inside a lane without asking the
    CLI who is live, which costs seconds on every shell call.
    """
    if not argv:
        raise TerminalError("a window needs a command to run; argv is empty")
    for name, _ in env:
        if not _ENV_NAME.match(name):
            raise TerminalError(f"not an environment variable name: {name!r}")
    sets = "".join(f"$env:{name} = {ps_quote(value)}; " for name, value in env)
    statement = sets + "& " + " ".join(ps_quote(token) for token in argv)
    if close_marker is None:
        return statement
    return statement + close_epilogue(close_marker)


_BASE64_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
)


def encode_command(statement: str) -> str:
    """A PowerShell statement as the base64 ``-EncodedCommand`` expects.

    Checked against the base64 alphabet before it is returned: the whole reason
    this exists is that the output carries no character either parser can act
    on.
    """
    blob = base64.b64encode(statement.encode("utf-16-le")).decode("ascii")
    if not set(blob) <= set(_BASE64_ALPHABET):
        raise TerminalError(
            f"encoded command carries characters outside base64: "
            f"{sorted(set(blob) - set(_BASE64_ALPHABET))}"
        )
    return blob


#: What Windows Terminal accepts as a tab colour. A VALUE OF ANY OTHER SHAPE IS
#: SWALLOWED -- measured 2026-08-26, `--tabColor notacolour` exited 0 and the
#: tab came up uncoloured -- so it is checked here rather than left to Terminal.
_TAB_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def window_command(window: Window, *, cwd: Path | str) -> list[str]:
    """The whole ``wt.exe`` invocation for one window, as argv tokens."""
    if window.close_marker is not None and window.keep_open:
        # `-NoExit` drops to a prompt when the statement finishes, and the
        # epilogue's `exit` would close THAT. Refused rather than silently
        # preferred, because either one alone is correct.
        raise TerminalError(
            f"window {window.label!r} asks for both -NoExit and a close marker: "
            f"the marker's `exit` would close the shell -NoExit keeps open"
        )
    if window.tab_color is not None and not _TAB_COLOR.match(window.tab_color):
        raise TerminalError(
            f"tab colour {window.tab_color!r} for window {window.label!r} is not "
            f"#RRGGBB. Windows Terminal SWALLOWS a colour it cannot read -- the "
            f"tab opens uncoloured and nothing is reported"
        )
    if window.window_target is None:
        command = [TERMINAL, "-w", "new"]
    else:
        # `new-tab` is written out although `wt.exe` assumes it: this is the
        # line a dry run prints, and the shape should be readable in it.
        command = [TERMINAL, "-w", window.window_target, "new-tab"]
    if window.tab_title is not None:
        command += ["--title", window.tab_title]
    if window.tab_color is not None:
        command += ["--tabColor", window.tab_color]
    command += ["-d", str(cwd)]
    command += [
        SHELL,
        *shell_args(keep_open=window.keep_open),
        encode_command(ps_statement(window.argv, close_marker=window.close_marker,
                                    env=window.env)),
    ]
    return command


#: Every environment variable a Claude session sets on itself carries this
#: prefix. A PREFIX rather than a list, so a marker a future version adds is
#: stripped on the day it appears.
_SESSION_PREFIX = "CLAUDE"

#: The tool shell's description of ITSELF as a place with nobody sitting at it.
#: Found 2026-08-23: every launcher-opened window came up colourless because
#: the harness sets ``NO_COLOR=1`` in tool shells and the window inherited it.
#: A class rather than the one name: colour, terminal identity, and the two
#: "do not ask me anything" switches -- which cost more than colour, because a
#: window that needs to authenticate would FAIL instead of prompting the human
#: sitting in front of it.
HEADLESS_MARKERS = frozenset({
    "NO_COLOR",
    "FORCE_COLOR",
    "CLICOLOR",
    "CLICOLOR_FORCE",
    "COLORTERM",
    "TERM",
    "CI",
    "GIT_TERMINAL_PROMPT",
    "GCM_INTERACTIVE",
})


def child_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of ``env`` with everything describing THIS shell removed.

    1. THIS SESSION'S IDENTITY, by the ``CLAUDE`` prefix. One of those
       variables tells Claude it is a CHILD SESSION; found 2026-08-22, when the
       first launcher-opened window came up with transcript saving off -- it
       could not be resumed and left no record.
    2. THIS SHELL'S DESCRIPTION OF ITSELF as headless, in
       :data:`HEADLESS_MARKERS`.

    Genuine user configuration is not lost: the window opens a shell, the shell
    loads the user's profile, and anything set there is set again.
    """
    source = os.environ if env is None else env
    return {
        key: value
        for key, value in source.items()
        if not key.upper().startswith(_SESSION_PREFIX)
        and key.upper() not in HEADLESS_MARKERS
    }


def available() -> bool:
    """Whether ``wt.exe`` is on PATH at all."""
    return shutil.which(TERMINAL) is not None


# --- the manual line, where there is no Windows Terminal -----------------------


def sh_quote(token: str) -> str:
    """One token for a POSIX shell, ALWAYS single-quoted -- used for the
    project folder, whose name so often carries a space that the person
    reading the line should see it quoted every time. A single quote inside is
    closed, escaped and reopened. Other tokens are quoted only when they need
    it (`shlex.quote`)."""
    return "'" + str(token).replace("'", "'\"'\"'") + "'"


def posix_line(argv: Sequence[str], *, cwd: Path | str,
               env: Sequence[tuple[str, str]] = ()) -> str:
    """``cd '<cwd>' && NAME=value ... 'claude' ...`` -- one line for sh, bash
    or zsh. The variables are set for the program alone, so the tab's shell is
    left as it was."""
    if not argv:
        raise TerminalError("a window needs a command to run; argv is empty")
    for name, _ in env:
        if not _ENV_NAME.match(name):
            raise TerminalError(f"not an environment variable name: {name!r}")
    sets = "".join(f"{name}={shlex.quote(value)} " for name, value in env)
    return (f"cd {sh_quote(str(cwd))} && {sets}"
            + " ".join(shlex.quote(token) for token in argv))


def powershell_line(argv: Sequence[str], *, cwd: Path | str,
                    env: Sequence[tuple[str, str]] = ()) -> str:
    """``Set-Location -LiteralPath '<cwd>'; $env:NAME = 'value'; & 'claude' ...``
    -- one line for a PowerShell tab, every token single-quoted as
    :func:`ps_statement` quotes it."""
    return f"Set-Location -LiteralPath {ps_quote(str(cwd))}; " + ps_statement(argv, env=env)


def manual_line(window: Window, *, cwd: Path | str, os_name: str | None = None) -> str:
    """The line the owner pastes into a new terminal tab to start ``window``
    by hand: PowerShell on Windows (``os_name`` ``"nt"``), POSIX sh elsewhere.
    The window's argv and environment are exactly what the Windows Terminal
    path would run; its tab title, colour and close marker have no meaning in
    a tab this program did not open, and are left out."""
    windows = (os.name if os_name is None else os_name) == "nt"
    build = powershell_line if windows else posix_line
    return build(window.argv, cwd=cwd, env=window.env)


def launch(command: Sequence[str], *, env: Mapping[str, str] | None = None) -> None:
    """Open one window. Returns as soon as Terminal has taken the hand-off.

    The environment is cleaned by :func:`child_environment` on the way through,
    without the caller asking. A caller who has to remember to clean it is the
    arrangement that produced the child-session defect in the first place.
    """
    if not available():
        raise TerminalError(
            f"{TERMINAL} is not on PATH, so no window can be opened from here"
        )
    subprocess.run(list(command), check=True, env=child_environment(env))
