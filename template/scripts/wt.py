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
made here goes back with `<venv python> scripts/kit_sync.py push scripts/wt.py`.

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

TABS IN ONE WINDOW
------------------
With a ``join`` the invocation is ``-w <name> new-tab``: measured 2026-08-26,
the name CREATES the window when it is absent and JOINS it when it is present,
and it never lands a tab in the window the owner is typing in -- which ``-w 0``
("most recently used") would. Without one it is ``-w new``, a window of its
own. A pane exiting 0 closes its tab.

A JOIN TAKES THE FRONT UNLESS THE WINDOW IS MINIMIZED (measured 2026-11-07,
Terminal 1.24.12741.0, game in front): joining an open window took the front
every time; joining a minimized one did not, three runs of three -- Terminal
restored it behind the game. So a caller that joins minimizes the window first
with :func:`tuck`, which never touches the window in front and activates
nothing. ``scripts/open_terminal.py`` decides per open whether to join at all
(its TABS IN ONE WINDOW, WITHOUT TAKING FOCUS).

``--title`` is passed and the application's own title is NOT suppressed:
``claude`` retitles the tab with the session name and a working/idle glyph, and
suppressing that would throw the glyph away. ``--title`` is what the tab reads
for the second before the session boots.

AN OPEN NEVER TAKES THE OWNER'S FOCUS
------------------------------------
The owner, 2026-11-07, playing a game: every lane that opened "pops me out of
the game and makes it so that like I'm on that lanes tab". Their rulings the
same evening: no open ever takes focus -- lane, desk, ``--resume``, in play or
not -- with no if-then.

Measured that evening on Terminal 1.24.12741.0, with the game in front:

1. Terminal has NO option for opening without focus. Its command line knows
   ``--focus``, ``--fullscreen``, ``--maximized``, ``--size`` and
   ``--window`` (read out of its own ``TerminalApp.dll``).
2. The game MINIMIZES ITSELF the moment it loses the front: 0.08 s after
   Terminal took it. So a theft of any length pulls the owner out, and giving
   the front back afterwards cannot help. A hand-back that did exactly that
   -- the front was back within about 0.2 s -- was built and shipped the same
   evening, did not hold in play, and fought the owner's own Alt+Tab. It is
   gone; do not rebuild it.
3. A ``-w <name>`` that JOINS an open window took the front every time,
   0.08-0.36 s after the hand-off -- also when started minimized. One that
   joins a MINIMIZED window did not, three runs of three (TABS IN ONE
   WINDOW, above).
4. A ``-w <name>`` that CREATES its window did not take the front, every run.

So :func:`launch` starts Terminal minimized and not activated
(:func:`startup_info`). Terminal has no flag for it; Windows hands a program
the show state its starter asks for. It does NOT reliably minimize: a window
Terminal created with it came up minimized in two runs and, in a clean third,
not minimized but behind the window in front. In none did it take the front.

THE PROOF IS EVERY REAL OPEN, NOT A TEST LAUNCH. Test launches landed on the
owner's play that evening, so none is run any more: :func:`launch` reads the
window in front before the open and a second after -- read only -- and returns
a :class:`FocusCheck`, which the opener records and prints as ``FOCUS MOVED``
when the window changed.

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
import time
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

    ``join`` is the NAME of a window to open into as a tab (``-w <join>
    new-tab``); without one the window is a new one (``-w new``). A caller
    that joins minimizes the window first (:func:`tuck`): joining a window
    that is not minimized takes the front (TABS IN ONE WINDOW, below).

    ``tab_color`` is the caller's word, not this module's -- nothing here knows
    what a role or a model is.
    """

    label: str
    argv: tuple[str, ...]
    keep_open: bool = True
    close_marker: str | None = None
    join: str | None = None
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
    if window.join is None:
        command = [TERMINAL, "-w", "new"]
    else:
        # `new-tab` is written out although `wt.exe` assumes it: this is the
        # line a dry run prints, and the shape should be readable in it.
        command = [TERMINAL, "-w", window.join, "new-tab"]
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


#: Win32 ``SW_SHOWMINNOACTIVE``: shown minimized, and not activated.
SW_SHOWMINNOACTIVE = 7


def startup_info():
    """How every window is started: minimized and not activated, so an open
    never takes the front from whatever the owner has there. ``None`` off
    Windows, where there is no Terminal to start."""
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = SW_SHOWMINNOACTIVE
    return info


#: Seconds after the hand-off that the window in front is read again. Measured
#: 2026-11-07: a Terminal that took the front had it 0.22-0.36 s after.
FOCUS_CHECK_DELAY = 1.0


#: The window class of every Windows Terminal window (read off the live windows
#: 2026-11-07, Terminal 1.24.12741.0).
TERMINAL_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"


class Front(NamedTuple):
    """One window as the focus check reads it: its handle (``None`` for
    nothing), its title, and whether it is a Terminal window."""

    handle: int | None
    title: str = ""
    terminal: bool = False


def _user32():
    """user32 with the four READ-ONLY calls the focus check makes. Nothing here
    ever moves the front: the measurement is not allowed to become the thing it
    measures (2026-11-07: a test that put the game back pushed the owner out of
    whatever else they were doing)."""
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL("user32")
    user.GetForegroundWindow.argtypes = []
    user.GetForegroundWindow.restype = wintypes.HWND
    for name in ("GetWindowTextW", "GetClassNameW"):
        getattr(user, name).argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                                 wintypes.LPARAM]
    return ctypes, wintypes, user


def _text(ctypes, call, handle) -> str:
    buffer = ctypes.create_unicode_buffer(512)
    call(handle, buffer, 512)
    return buffer.value


def front_window() -> Front:
    """The window in front. ``Front(None)`` off Windows or when nothing is."""
    if os.name != "nt":
        return Front(None)
    ctypes, _, user = _user32()
    handle = user.GetForegroundWindow()
    if not handle:
        return Front(None)
    return Front(handle, _text(ctypes, user.GetWindowTextW, handle),
                 _text(ctypes, user.GetClassNameW, handle) == TERMINAL_CLASS)


def terminal_windows() -> frozenset[int]:
    """Every Terminal window open now, by handle. Empty off Windows."""
    if os.name != "nt":
        return frozenset()
    ctypes, wintypes, user = _user32()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(handle, _):
        if _text(ctypes, user.GetClassNameW, handle) == TERMINAL_CLASS:
            found.append(handle)
        return True

    user.EnumWindows(each, 0)
    return frozenset(found)


def titled_as(title: str, name: str) -> bool:
    """Whether a window's title is ``name`` as Claude shows it: the name
    itself, or a working glyph and the name (``✳ lane-alpha``). A name inside
    a longer one (``lane-alpha-2``) is not it."""
    return bool(name) and re.search(rf"(?:^|\s){re.escape(name)}$", title) is not None


def terminal_windows_titled(names: Sequence[str]) -> list[int]:
    """The Terminal windows whose title is one of ``names`` -- for a project,
    its own shared window, whose title is the name of the tab selected in it.
    Read only. Empty off Windows."""
    if os.name != "nt" or not names:
        return []
    ctypes, _, user = _user32()
    return [handle for handle in sorted(terminal_windows())
            if any(titled_as(_text(ctypes, user.GetWindowTextW, handle), name) for name in names)]


def tuck(handles: Sequence[int]) -> list[int]:
    """Minimize each window in ``handles`` that is neither in front nor
    minimized already, WITHOUT ACTIVATING anything (``SW_SHOWMINNOACTIVE``).
    Returns the windows it minimized.

    This is the one call here that changes a window, and it cannot move the
    front: it never touches the window in front, and minimizing a window
    behind it activates nothing. Off Windows it does nothing.
    """
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL("user32")
    user.GetForegroundWindow.restype = wintypes.HWND
    user.IsIconic.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    front = user.GetForegroundWindow()
    tucked = []
    for handle in handles:
        if handle and handle != front and not user.IsIconic(handle):
            user.ShowWindow(handle, SW_SHOWMINNOACTIVE)
            tucked.append(handle)
    return tucked


def window_title(command: Sequence[str]) -> str | None:
    """The ``--title`` an invocation gives its window, or ``None``."""
    command = list(command)
    if "--title" in command and command.index("--title") + 1 < len(command):
        return command[command.index("--title") + 1]
    return None


class FocusCheck(NamedTuple):
    """The window in front just before an open and :data:`FOCUS_CHECK_DELAY`
    after: the proof, on every real open, that it took nothing.

    1. Windows are compared by HANDLE, never by title: a Claude tab retitles
       itself with a working glyph every second, so a title is no identity.
    2. ``moved_by_open``: the window in front after is the window the open
       CREATED -- a Terminal window that was not there before the open, or one
       whose title ends with the open's own ``--title`` (Claude shows ``✳
       <name>``). Only this prints ``FOCUS MOVED``.
    3. ``moved_by_other``: the front changed to anything else -- the owner's
       own Alt+Tab, measured the evening this was built ("Task Switching -> ✳
       syxplay"). Recorded, never flagged.
    """

    before: str
    after: str
    moved_by_open: bool
    moved_by_other: bool

    @classmethod
    def read(cls, before: Front, after: Front, known: frozenset[int],
             title: str | None) -> "FocusCheck":
        changed = before.handle != after.handle
        created = after.terminal and after.handle not in known
        named = bool(title) and titled_as(after.title, title)
        ours = changed and after.handle is not None and (created or named)
        return cls(before.title, after.title, ours, changed and not ours)

    def warning(self) -> str | None:
        """The line an opener prints when the open took the front; ``None``
        when it did not -- including when something else did."""
        if not self.moved_by_open:
            return None
        return f"FOCUS MOVED: {self.before or '(nothing)'} -> {self.after or '(nothing)'}"


def launch(command: Sequence[str], *, env: Mapping[str, str] | None = None) -> FocusCheck:
    """Open one window, and say whether the front moved.

    The environment is cleaned by :func:`child_environment` on the way through,
    without the caller asking. A caller who has to remember to clean it is the
    arrangement that produced the child-session defect in the first place.

    The window starts minimized and not activated (:func:`startup_info`), the
    same way, for every caller: nothing a caller passes turns that off. The
    window in front is read before and after (:class:`FocusCheck`), so every
    real open proves that, or names the window that took the front.
    """
    if not available():
        raise TerminalError(
            f"{TERMINAL} is not on PATH, so no window can be opened from here"
        )
    before, known = front_window(), terminal_windows()
    subprocess.run(list(command), check=True, env=child_environment(env),
                   startupinfo=startup_info())
    time.sleep(FOCUS_CHECK_DELAY)
    return FocusCheck.read(before, front_window(), known, window_title(command))
