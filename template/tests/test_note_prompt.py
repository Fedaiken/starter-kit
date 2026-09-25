"""Tests for scripts/note_prompt.py -- the permission pop-up log.

Reconciliation build, slice 2. The hook path is run as a real subprocess, the
way Claude Code runs it, because its three rules (nothing on stdout, always
exit 0, swallow everything) are properties of the process, not of a function.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import note_prompt as np
import project_identity as pi

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "note_prompt.py"

PAYLOAD = {
    "session_id": "abc-123", "hook_event_name": "PermissionRequest",
    "tool_name": "Write", "permission_mode": "acceptEdits",
    "tool_input": {"file_path": "C:/elsewhere/→.md", "content": "x" * 5000},
}


@pytest.fixture
def log(tmp_path, monkeypatch):
    monkeypatch.setattr(np, "LOG", tmp_path / "coordination" / "prompts.jsonl")
    return np.LOG


def run_hook(monkeypatch, text):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    return np.main([])


def test_one_stall_is_one_line_saying_who_what_and_under_which_mode(log, monkeypatch):
    assert run_hook(monkeypatch, json.dumps(PAYLOAD)) == 0
    (row,) = np.read_log(log)
    assert (row["session"], row["tool"], row["mode"]) == ("abc-123", "Write", "acceptEdits")
    assert row["what"] == "C:/elsewhere/→.md", "the content, not the path, was logged"


@pytest.mark.parametrize("text", ["", "not json", "[1, 2]", '{"tool_input": 7}'])
def test_the_hook_never_fails_whatever_it_is_handed(log, monkeypatch, capsys, text):
    assert run_hook(monkeypatch, text) == 0
    assert capsys.readouterr().out == ""


def test_as_a_process_it_prints_nothing_and_exits_zero():
    """stdout is parsed for a permission DECISION; one stray line rules on a
    call nobody meant to rule on. Bad input, so nothing is written either."""
    proc = subprocess.run([sys.executable, str(SCRIPT)], input=b"not json",
                          capture_output=True, check=False)
    assert (proc.returncode, proc.stdout) == (0, b"")


def test_the_log_rolls_over_and_keeps_one_generation(log, monkeypatch):
    monkeypatch.setattr(np, "LOG_BYTE_CAP", 10)
    run_hook(monkeypatch, json.dumps(PAYLOAD))
    run_hook(monkeypatch, json.dumps(PAYLOAD))
    assert len(np.read_log(log)) == 1
    assert len(np.read_log(log.with_suffix(".jsonl.1"))) == 1


def test_a_half_written_line_does_not_break_the_report(log, capsys):
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(np.entry(PAYLOAD, now=np.datetime.now())) + '\n{"half', encoding="utf-8")
    assert np.report(log, {"abc-123": "lane-alpha"}) == 0
    out = capsys.readouterr().out
    assert "1 permission pop-up(s)" in out and "lane-alpha" in out


def test_the_report_names_the_window_not_the_session_id(log, capsys):
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(np.entry(PAYLOAD, now=np.datetime.now())) + "\n", encoding="utf-8")
    np.report(log, {})
    assert "(ended) abc-123" in capsys.readouterr().out


def test_the_tracked_settings_register_the_hook_and_let_lanes_run_the_scripts():
    """The interpreter and the allow rules are this machine's
    (`project_identity`): `.venv/Scripts/python.exe` and a PowerShell rule on
    Windows, `.venv/bin/python` and Bash alone elsewhere."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    for event in ("PermissionRequest", "PermissionDenied"):
        (hook,) = settings["hooks"][event][0]["hooks"]
        assert hook["args"] == ["${CLAUDE_PROJECT_DIR}/scripts/note_prompt.py"]
        assert hook["command"] == pi.settings_python()
    allow = settings["permissions"]["allow"]
    for rule in (*pi.venv_allow_rules(), "SendMessage", "ListAgents"):
        assert rule in allow
    # R22: only the desk saves, and a stash in a folder fifteen lanes share
    # takes every lane's work with it.
    assert "Bash(git stash*)" in settings["permissions"]["deny"]


@pytest.mark.parametrize("path", ["coordination/prompts.jsonl", "coordination/prompts.jsonl.1"])
def test_the_log_and_its_rollover_are_gitignored(path):
    proc = subprocess.run(["git", "check-ignore", "-q", path], cwd=str(ROOT), check=False)
    assert proc.returncode == 0, f"{path} is not gitignored"
