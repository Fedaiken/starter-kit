"""The lane guard: a lane's saving and destroying git commands are refused.

Kit-owned, like the guard: the role and window variables are read from
`scripts/project_identity.py`, so the same bytes pass in every seeded project.
The path rules are tested in BOTH forms on any machine -- Windows paths with
`windows=True`, macOS/Linux paths with `windows=False` -- against stand-in
folders, never the real project or temp folder.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import lane_guard as lg  # noqa: E402
import project_identity as pi  # noqa: E402

LANE = {pi.ROLE_ENV: "lane", pi.WINDOW_ENV: "lane-alpha"}

#: What every delete refusal says, whatever the machine.
WHY = "permission pop-up the owner had to find"


def shell(command: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}}


@pytest.mark.parametrize("command", [
    "git commit -m x",
    "git push origin main",
    'cd "C:/a b" && git add . && git commit -m "x"',
    "cd '/Users/someone/Boat Log' && git commit -m x",
    "git -C some/dir commit -m x",
    "git --no-pager -c user.name=x stash",
    "git.exe reset --hard",
    "git checkout -- .",
    "git restore scripts/x.py",
    "git clean -fd",
    "echo hi; git rebase main",
])
def test_a_lane_is_refused(command):
    said = lg.verdict(shell(command), LANE)
    assert said and "lane-alpha" in said and "REFUSED" in said


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_both_shells_are_guarded(tool):
    assert lg.verdict(shell("git commit -m x", tool), LANE)


@pytest.mark.parametrize("command", [
    "git status --short",
    "git diff -- scripts/x.py",
    "git log --oneline -3",
    "git show HEAD:tests/x.py",
    "git grep -n working_since scripts/x.py",
    "git ls-files",
    ".venv/Scripts/python.exe -m pytest tests -q",
    ".venv/bin/python -m pytest tests -q",
    "cat legit-commit-notes.md",
    "ls .git/commit",
])
def test_a_lane_may_look(command):
    assert lg.verdict(shell(command), LANE) is None


def test_a_window_the_owner_opened_is_never_refused():
    assert lg.verdict(shell("git commit -m x"), {}) is None


def test_a_desk_is_never_refused():
    assert lg.verdict(shell("git push origin main"), {pi.ROLE_ENV: "desk"}) is None


def test_other_tools_are_not_its_business():
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "git commit"}}
    assert lg.verdict(payload, LANE) is None


def test_every_refused_command_is_named_once_with_its_reason():
    said = lg.verdict(shell("git add . && git commit -m x && git commit --amend"), LANE)
    assert said.count("`git commit`") == 1 and "`git add`" in said
    assert "only the desk saves" in said


def test_main_exits_2_with_the_reason_on_stderr(monkeypatch, capsys):
    monkeypatch.setenv(pi.ROLE_ENV, "lane")
    monkeypatch.setenv(pi.WINDOW_ENV, "lane-alpha")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(shell("git commit -m x"))))
    assert lg.main() == 2
    assert "REFUSED for lane lane-alpha" in capsys.readouterr().err


def test_main_allows_and_survives_a_bad_payload(monkeypatch):
    monkeypatch.setenv(pi.ROLE_ENV, "lane")
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert lg.main() == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(shell("git status"))))
    assert lg.main() == 0


# --- recursive deletes outside the scratchpad (F57), Windows paths -------------

#: A stand-in Windows machine: home, temp folder and project on drives no real
#: project sits on. With the real temp folder, a project that itself sits under
#: `%TEMP%\claude\` -- a throwaway one seeded into a session's scratchpad to
#: test the kit -- would make every project path "scratch" and every refusal
#: below an allowance.
HOME = r"Q:\Users\someone"
TEMP = HOME + r"\AppData\Local\Temp"
SCRATCH = TEMP + r"\claude\C--proj\e13f\scratchpad"
PROJECT = r"P:\Work\Boat Log"
PROJECT_BASH = "/p/Work/Boat Log"         # the same folder as Git Bash spells it
ROOM = {**LANE, "TEMP": TEMP, "TMP": TEMP, "USERPROFILE": HOME}


def win(command: str, tool: str = "Bash", environ: dict | None = None) -> str | None:
    payload = {**shell(command, tool), "cwd": PROJECT}
    return lg.verdict(payload, ROOM if environ is None else environ, windows=True)


@pytest.mark.parametrize("command, tool", [
    # The S3 incident: a scratch `rm -rf` on a variable path.
    ('rm -rf "$scratch_dir"', "Bash"),
    ("rm -rf records/2025/March", "Bash"),
    ("rm -r -f records", "Bash"),
    ("rm -fr ./tmp_apply", "Bash"),
    ('rm -R "' + PROJECT_BASH + '"', "Bash"),
    ("rm --recursive records/2025", "Bash"),
    ("cd records && rm -rf 2025", "Bash"),
    ("find . -name '*.bak' -exec rm -rf {} +", "Bash"),
    ("ls | xargs rm -rf", "Bash"),
    ('rm -rf "$TEMP/claude/../../../../../Work/Boat Log"', "Bash"),
    ("rm -rf $TEMP/claude", "Bash"),
    ("rm -rf $TEMP/other-tool/cache", "Bash"),
    ('bash -c "rm -rf records/2025"', "Bash"),
    ("Remove-Item -Recurse -Force records\\2025\\March", "PowerShell"),
    ("Remove-Item $scratch -Recurse -Force", "PowerShell"),
    ("Remove-Item -Path $env:TEMP\\claude\\x,records -Recurse", "PowerShell"),
    ("Remove-Item (Join-Path $env:TEMP 'claude\\x') -Recurse", "PowerShell"),
    ("Get-ChildItem records | Remove-Item -Recurse", "PowerShell"),
    ("rm -r records\\2025", "PowerShell"),
    ("ri -rec records", "PowerShell"),
    ("cmd /c rmdir /s /q records\\2025", "PowerShell"),
    ('cmd /c "rd /S /Q P:\\Work"', "PowerShell"),
    ("powershell -Command \"Remove-Item -Recurse records\"", "Bash"),
    ('.venv/Scripts/python.exe -c "import shutil; shutil.rmtree(\'records/2025\')"', "Bash"),
    ('.venv/Scripts/python.exe -c "import shutil,os; shutil.rmtree(os.environ[\'X\'])"', "PowerShell"),
    ("python - <<'EOF'\nfrom shutil import rmtree\nrmtree(r'" + HOME + "')\nEOF", "Bash"),
])
def test_a_recursive_delete_outside_the_scratchpad_is_refused(command, tool):
    said = win(command, tool)
    assert said and "REFUSED for lane lane-alpha" in said
    assert "recursive delete outside your scratchpad" in said
    assert WHY in said, "the refusal does not say why"


@pytest.mark.parametrize("command, tool", [
    ("rm -rf " + SCRATCH.replace("\\", "/") + "/apply_rehearsal", "Bash"),
    ('rm -rf "$TEMP/claude/C--proj/e13f/scratchpad/x"', "Bash"),
    ("rm -rf ${TMP}/claude/C--proj/e13f/scratchpad/x", "Bash"),
    ("rm -rf /tmp/claude/C--proj/e13f/scratchpad/x", "Bash"),
    ("rm -rf /q/Users/someone/AppData/Local/Temp/claude/C--proj/e13f/scratchpad/x", "Bash"),
    ("rm -rf ~/AppData/Local/Temp/claude/C--proj/x/*", "Bash"),
    ("Remove-Item -Recurse -Force \"$env:TEMP\\claude\\C--proj\\e13f\\scratchpad\\x\"", "PowerShell"),
    ("Remove-Item -LiteralPath '" + SCRATCH + "\\y' -Recurse", "PowerShell"),
    ("cmd /c rmdir /s /q %TEMP%\\claude\\C--proj\\x", "PowerShell"),
    ("python -c \"import shutil; shutil.rmtree(r'" + SCRATCH + "\\z')\"", "Bash"),
])
def test_a_recursive_delete_inside_the_scratchpad_is_allowed(command, tool):
    assert win(command, tool) is None


@pytest.mark.parametrize("command, tool", [
    ("rm records/reconciliation_s3/tmp.md", "Bash"),
    ("rm -f scratch_note.txt", "Bash"),
    ("Remove-Item -Force coordination\\old.txt", "PowerShell"),
    ("rm -Force old.txt", "PowerShell"),
    ("rmdir empty_folder", "Bash"),
    ("echo rm -rf records", "Bash"),
    ("rg -n 'rm -rf' scripts", "Bash"),
    (".venv/Scripts/python.exe -m pytest tests/test_lane_guard.py -q", "Bash"),
])
def test_what_is_not_a_recursive_delete_is_not_this_rules_business(command, tool):
    assert win(command, tool) is None


def test_the_scratchpad_allowance_is_not_a_prefix_trick():
    """`claude-old` is not `claude`, and the claude folder itself holds every
    session's scratchpad, so neither is a lane's to delete."""
    for path in ("$TEMP/claude-old/x", "$TEMP/claude", "$TEMP/claude/"):
        assert win("rm -rf " + path)


def test_a_delete_refusal_names_the_path_and_the_scratchpad():
    said = win("rm -rf records/2025")
    assert "`records/2025`" in said
    assert "q:/users/someone/appdata/local/temp/claude/..." in said
    said = win('rm -rf "$scratch_dir"')
    assert "cannot read" in said


def test_a_git_refusal_and_a_delete_refusal_are_both_named():
    said = win("git stash && rm -rf 2025")
    assert "`git stash`" in said and "recursive delete" in said


def test_git_rm_is_refused_as_git_and_not_twice():
    said = win("git rm -r records/2025")
    assert "`git rm`" in said and "recursive delete" not in said


def test_a_delete_in_a_window_the_owner_opened_is_never_refused():
    assert win("rm -rf records", environ={"TEMP": TEMP}) is None


# --- the same rules on macOS and Linux paths -----------------------------------

#: A stand-in Mac: `$TMPDIR` under /var/folders, as macOS sets it, and a
#: project in the owner's home folder.
P_HOME = "/Users/someone"
P_TMPDIR = "/var/folders/xy/abc123/T/"
P_PROJECT = P_HOME + "/work/Boat Log"
P_ROOM = {**LANE, "HOME": P_HOME, "TMPDIR": P_TMPDIR}


def posix(command: str, environ: dict | None = None) -> str | None:
    payload = {**shell(command, "Bash"), "cwd": P_PROJECT}
    return lg.verdict(payload, P_ROOM if environ is None else environ, windows=False)


@pytest.mark.parametrize("command", [
    'rm -rf "$scratch_dir"',
    "rm -rf records/2025/March",
    "rm -rf .",
    "rm -rf '" + P_PROJECT + "'",
    "rm -rf ~/work",
    "rm -rf $TMPDIR/claude",
    "rm -rf $TMPDIR/claude-old/x",
    "rm -rf /tmp/other-tool/cache",
    "rm -rf /var/folders/xy/abc123/T/claude/../../../../../../Users/someone",
    'zsh -c "rm -rf records/2025"',
    "rm -rf /c/Users/someone/AppData/Local/Temp/claude/x",   # /c is a real folder here
    "rm -rf /TMP/claude/x",                                  # case is kept on POSIX
    "python3 -c \"import shutil; shutil.rmtree('records')\"",
])
def test_posix_a_recursive_delete_outside_the_scratchpad_is_refused(command):
    said = posix(command)
    assert said and "recursive delete outside your scratchpad" in said and WHY in said


@pytest.mark.parametrize("command", [
    "rm -rf $TMPDIR/claude/-Users-someone-work-Boat-Log/e13f/scratchpad/x",
    'rm -rf "${TMPDIR}claude/-Users-someone/e13f/scratchpad/x"',
    "rm -rf /var/folders/xy/abc123/T/claude/p/s/scratchpad/x",
    "rm -rf /private/var/folders/xy/abc123/T/claude/p/s/scratchpad/x",
    "rm -rf /tmp/claude/p/s/scratchpad/x",
    "rm -rf /private/tmp/claude-501/p/s/scratchpad/x",
    "rm -rf /tmp/claude-1000/p/s/scratchpad/x",
    "python3 -c \"import shutil; shutil.rmtree('/tmp/claude/p/s/x')\"",
])
def test_posix_a_recursive_delete_inside_the_scratchpad_is_allowed(command):
    assert posix(command) is None


def test_posix_tmp_is_scratch_even_with_no_tmpdir():
    """Linux sets no `$TMPDIR` by default; the temp folder is then /tmp."""
    environ = {**LANE, "HOME": "/home/someone"}
    assert posix("rm -rf /tmp/claude/p/s/scratchpad/x", environ) is None
    assert posix("rm -rf /tmp/claude", environ)


def test_posix_a_refusal_names_the_posix_scratchpad():
    said = posix("rm -rf records/2025")
    assert "/var/folders/xy/abc123/T/claude/..." in said and "/tmp/claude/..." in said
    assert "q:/" not in said and "%TEMP%" not in said


def test_posix_paths_are_read_as_posix():
    environ = {"HOME": P_HOME, "TMPDIR": P_TMPDIR}
    assert lg.resolved("~/x", environ, None, windows=False) == P_HOME + "/x"
    assert lg.resolved("a/../b", environ, "/srv/p", windows=False) == "/srv/p/b"
    assert lg.resolved("/private/tmp/x", environ, None, windows=False) == "/tmp/x"
    assert lg.resolved("/Users/Some/X", environ, None, windows=False) == "/Users/Some/X"
    assert lg.resolved("C:/x", environ, None, windows=False) is None   # relative, no cwd
    assert lg.resolved("/c/x", {"TEMP": TEMP}, None, windows=True) == "c:/x"
    assert lg.resolved("/c/x", environ, None, windows=False) == "/c/x"


def test_main_refuses_a_recursive_delete_with_exit_2(monkeypatch, capsys):
    """Through the real stdin and environment, on whatever machine this is."""
    for key, value in LANE.items():
        monkeypatch.setenv(key, value)
    payload = {**shell('rm -rf "$scratch_dir"'), "cwd": str(Path.cwd())}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert lg.main() == 2
    assert "recursive delete outside your scratchpad" in capsys.readouterr().err


# --- the settings the seeder writes ---------------------------------------------


def test_the_tracked_settings_wire_the_guard_to_this_machines_shells():
    """`Bash|PowerShell` on Windows, `Bash` elsewhere, run by this machine's
    venv interpreter -- the values come from `project_identity`, not literals."""
    repo = Path(__file__).resolve().parent.parent
    settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    (entry,) = settings["hooks"]["PreToolUse"]
    assert set(entry["matcher"].split("|")) == set(pi.shell_tools())
    (hook,) = entry["hooks"]
    assert hook["args"] == ["${CLAUDE_PROJECT_DIR}/scripts/lane_guard.py"]
    assert hook["command"] == pi.settings_python()
