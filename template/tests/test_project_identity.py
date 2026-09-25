"""Tests for scripts/project_identity.py -- every name the desk-and-lane
scripts derive from the project folder's name.

Kit-owned: the same bytes pass in every seeded project, so nothing here pins
this project's own name; the rules are tested on names given to the functions.
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import project_identity as pi

REPO = Path(__file__).resolve().parents[1]

#: What PowerShell and `wt.ps_statement` accept as a variable name.
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def test_the_name_is_the_folders_name():
    assert pi.REPO == REPO
    assert pi.NAME == REPO.name


def test_everything_is_derived_from_the_name_in_one_place():
    assert pi.ROLE_ENV == pi.env_slug(pi.NAME) + "_ROLE"
    assert pi.WINDOW_ENV == pi.env_slug(pi.NAME) + "_WINDOW"
    assert pi.SHARED_WINDOW == pi.window_slug(pi.NAME)
    assert pi.CLOSE_MARKER_PREFIX == pi.SHARED_WINDOW + "-terminal-"


@pytest.mark.parametrize("name, env, window", [
    ("Boat Log", "BOAT_LOG", "boat-log"),
    ("TESTDESK", "TESTDESK", "testdesk"),
    ("Fantasy_Football", "FANTASY_FOOTBALL", "fantasy-football"),
    ("_Frontier Awakening", "_FRONTIER_AWAKENING", "frontier-awakening"),
    ("Owner's  Taxes & Co.", "OWNER_S_TAXES_CO_", "owner-s-taxes-co"),
    ("2026 Taxes", "_2026_TAXES", "2026-taxes"),
])
def test_a_name_becomes_its_variables_and_its_window(name, env, window):
    assert pi.env_slug(name) == env
    assert pi.window_slug(name) == window


@pytest.mark.parametrize("name", ["2026", "new", "last", "---", "New"])
def test_a_window_name_wt_would_misread_is_prefixed(name):
    """`wt.exe -w 2026` is a window id and `-w new` is a fresh window each
    time; neither is the shared window a lane's tab must land in."""
    window = pi.window_slug(name)
    assert window.startswith("project")
    assert not window.isdigit() and window not in ("new", "last")


@pytest.mark.parametrize("name", ["Boat Log", "2026 Taxes", "_x", "!!", "Café Notes", pi.NAME])
def test_every_derived_variable_is_a_legal_name(name):
    for suffix in ("_ROLE", "_WINDOW"):
        assert ENV_NAME.match(pi.env_slug(name) + suffix)


@pytest.mark.parametrize("name", ["Boat Log", "-lead", "Owner's Project", pi.NAME])
def test_every_window_name_is_one_plain_word(name):
    """It is a `wt.exe -w` argument and part of a temp file's name: no space,
    no leading dash, nothing a shell or a filename would act on."""
    window = pi.window_slug(name)
    assert re.match(r"^[a-z0-9][a-z0-9-]*$", window) and not window.endswith("-")


# --- the machine: where the project's interpreter lives -------------------------


@pytest.mark.parametrize("os_name, rel", [
    ("nt", ".venv/Scripts/python.exe"),
    ("posix", ".venv/bin/python"),
])
def test_the_venv_interpreter_is_per_os(os_name, rel):
    assert pi.venv_python_rel(os_name) == rel
    root = Path("some") / "project"
    assert pi.venv_python(root, os_name) == root / rel
    assert pi.venv_python(None, os_name) == REPO / rel
    assert pi.settings_python(os_name) == "${CLAUDE_PROJECT_DIR}/" + rel


def test_the_default_is_this_machine():
    assert pi.is_windows() == (os.name == "nt")
    assert pi.venv_python_rel() == pi.venv_python_rel(os.name)
    assert pi.venv_python() == REPO / pi.venv_python_rel(os.name)


@pytest.mark.parametrize("os_name, matcher, allow", [
    ("nt", "Bash|PowerShell",
     ["Bash(.venv/Scripts/python.exe *)", "PowerShell(.venv/Scripts/python.exe *)"]),
    ("posix", "Bash", ["Bash(.venv/bin/python *)"]),
])
def test_the_settings_values_follow_the_os(os_name, matcher, allow):
    """PowerShell is a Claude Code tool on Windows only, so the guard's matcher
    and the allow rules name it there and nowhere else."""
    assert pi.hook_matcher(os_name) == matcher
    assert pi.venv_allow_rules(os_name) == allow
