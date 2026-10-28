"""Tests for scripts/agent_guard.py -- the hook that refuses Agent and Workflow.

The hook path is run as a real subprocess, the way Claude Code runs it: exit 2
with the reason on stderr refuses the call; exit 0 lets it through.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent_guard.py"


def run(payload: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], input=payload,
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


@pytest.mark.parametrize("tool", ["Agent", "Workflow"])
def test_refuses_subagent_tools(tool):
    done = run(json.dumps({"tool_name": tool, "tool_input": {"prompt": "x"}}))
    assert done.returncode == 2
    assert "REFUSED" in done.stderr and "/desk" in done.stderr
    assert done.stdout == ""


@pytest.mark.parametrize("tool", ["Read", "Grep", "Bash", "SendMessage"])
def test_lets_other_tools_through(tool):
    done = run(json.dumps({"tool_name": tool, "tool_input": {}}))
    assert done.returncode == 0
    assert done.stderr == ""


@pytest.mark.parametrize("payload", ["", "not json", "[1, 2]"])
def test_unreadable_payload_never_stops_a_window(payload):
    assert run(payload).returncode == 0
