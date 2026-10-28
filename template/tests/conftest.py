"""Shared fixtures for the whole test suite.

A window started under a desk home (a desk or a lane) carries three environment
variables, and `scripts/desk_record.py`, `scripts/lane_guard.py` and
`scripts/open_terminal.py` read them. Left in place they leak into every test
that builds a throwaway desk, so the same tests passed in the owner's window and
failed in a lane's (measured Wed 2026-10-14: 11 failures in a lane window, none
with the variables unset). Every test runs with them cleared, in two steps:

1. At import. `desk_record.py` reads the home variable once, when it is
   imported (`use_home(os.environ.get(HOME_ENV))`), and the test modules import
   it at collection. A fixture runs after that, too late; pytest loads this file
   before any test module, so the variables are dropped here.
2. Before each test, for the code that reads them at call time.

The names come from `scripts/project_identity.py`, which derives them from the
project folder's name; none is hard-coded here. A test that needs one set does
it itself, with `monkeypatch.setenv`, after this fixture has run.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import project_identity as pi

#: The variables `scripts/open_terminal.py` and `scripts/desk_home.py` set.
WINDOW_VARS = (pi.DESK_HOME_ENV, pi.ROLE_ENV, pi.WINDOW_ENV)

for _name in WINDOW_VARS:
    os.environ.pop(_name, None)


@pytest.fixture(autouse=True)
def no_desk_window_variables(monkeypatch):
    """Run every test as if from a window that is neither a desk nor a lane."""
    for name in WINDOW_VARS:
        monkeypatch.delenv(name, raising=False)
