"""Who this project is, to the desk-and-lane scripts: every name they derive
from the project folder's name, in one place.

WHY THIS EXISTS
---------------
The desk-and-lane scripts are kit-owned: byte-identical in every project the
Starter Kit seeds, kept in step by `scripts/kit_sync.py` (an improvement made
in a project goes back with `python scripts/kit_sync.py push <path>`). So none
of them may name the project it runs in. In the first port (from FACOWORK to
HAZELHURST, 2026-09-24) the project's name was written into four places: the
role variable, the window variable, the shared Windows Terminal window and the
close-marker prefix. A lane opened in one project must never be read as
another's, so each of the four still has to be this project's -- it is DERIVED
here from the folder name, and every other script imports it from here.

A project named `Boat Log` gets `BOAT_LOG_ROLE`, `BOAT_LOG_WINDOW`, the window
`boat-log` and the marker prefix `boat-log-terminal-`.

THE MACHINE, TOO. The kit runs on Windows, macOS and Linux, and the one fact
about the machine every script, test and settings file needs is where the
project's own interpreter lives: `.venv/Scripts/python.exe` on Windows,
`.venv/bin/python` everywhere else. It is stated here once
(:func:`venv_python`), with the `.claude/settings.json` values that follow from
it, and every function takes an explicit `os_name` (`"nt"` or `"posix"`, as
`os.name` spells them) so a test can check both forms on either machine.

Stdlib only, and cheap to import: `scripts/lane_guard.py` imports this on
every shell call a window makes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: The project root: the folder that holds `scripts/`.
REPO = Path(__file__).resolve().parent.parent

#: The project's name is its folder's name. Nothing else is asked.
NAME = REPO.name

#: What `wt.exe -w <name>` reads as something other than a window name: a
#: number is a window id, `new` opens a fresh window every time and `last` is
#: whichever window was used last -- the owner's, so a lane's tab would land
#: where they are typing.
_WT_RESERVED = ("new", "last")


# --- the machine ---------------------------------------------------------------


def is_windows(os_name: str | None = None) -> bool:
    """Whether `os_name` (default: this machine's `os.name`) is Windows."""
    return (os.name if os_name is None else os_name) == "nt"


def venv_python_rel(os_name: str | None = None) -> str:
    """The project interpreter, relative to the project root, forward slashes:
    `.venv/Scripts/python.exe` on Windows, `.venv/bin/python` elsewhere.

    The form written into skills as `<venv python>` and into permission rules.
    """
    return ".venv/Scripts/python.exe" if is_windows(os_name) else ".venv/bin/python"


def venv_python(root: Path | str | None = None, os_name: str | None = None) -> Path:
    """The project interpreter under `root` (default: this project)."""
    return Path(REPO if root is None else root) / venv_python_rel(os_name)


#: What Claude Code expands to the project folder inside a hook command.
PROJECT_DIR_VAR = "${CLAUDE_PROJECT_DIR}"


def settings_python(os_name: str | None = None) -> str:
    """A hook's `command` in `.claude/settings.json`: the interpreter by the
    project-folder variable, so the file is the same on every checkout."""
    return f"{PROJECT_DIR_VAR}/{venv_python_rel(os_name)}"


def shell_tools(os_name: str | None = None) -> tuple[str, ...]:
    """The Claude Code tools that run a shell command on this machine. The
    PowerShell tool exists only on Windows."""
    return ("Bash", "PowerShell") if is_windows(os_name) else ("Bash",)


def hook_matcher(os_name: str | None = None) -> str:
    """The `PreToolUse` matcher `scripts/lane_guard.py` is wired under."""
    return "|".join(shell_tools(os_name))


def venv_allow_rules(os_name: str | None = None) -> list[str]:
    """The permission rules that let any window run the project's scripts."""
    return [f"{tool}({venv_python_rel(os_name)} *)" for tool in shell_tools(os_name)]


# --- the project's names --------------------------------------------------------


def env_slug(name: str) -> str:
    """`name` uppercased with every run of non-alphanumerics replaced by `_`.

    An environment variable cannot begin with a digit, so a name that would
    (`2026 Taxes`) is given a leading `_`.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).upper()
    return "_" + slug if not slug or slug[0].isdigit() else slug


def window_slug(name: str) -> str:
    """`name` lowercased with every run of non-alphanumerics replaced by `-`.

    Leading and trailing dashes are dropped, because `wt.exe -w -name` reads a
    leading dash as an option; a name `wt.exe` would read as something other
    than a window name (a number, `new`, `last`, or nothing) is prefixed.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug or slug.isdigit() or slug in _WT_RESERVED:
        slug = "project-" + slug if slug else "project"
    return slug


#: The environment variables `scripts/open_terminal.py` starts every window
#: with, and `scripts/lane_guard.py` reads to know it is inside a lane.
ENV_SLUG = env_slug(NAME)
ROLE_ENV = f"{ENV_SLUG}_ROLE"
WINDOW_ENV = f"{ENV_SLUG}_WINDOW"

#: The Windows Terminal window every desk and lane tab opens in.
SHARED_WINDOW = window_slug(NAME)

#: Every close marker is `<CLOSE_MARKER_PREFIX><window name>.closing` in the
#: system temp directory (`scripts/open_terminal.py`, `close_marker_path`).
CLOSE_MARKER_PREFIX = f"{SHARED_WINDOW}-terminal-"
