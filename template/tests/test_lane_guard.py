"""The lane guard: a lane's saving and destroying git commands are refused --
and, in every window, a PowerShell text write into the project and the command
shapes that raise a permission pop-up.

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

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

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


def test_the_git_rule_keeps_the_shape_desk_record_imports():
    """`scripts/desk_record.py`'s stamp calls `refused_subcommands(command)`
    with one argument and reads `REFUSED`."""
    assert lg.refused_subcommands("git add . && git commit -m x") == ["add", "commit"]
    assert "commit" in lg.REFUSED and "push" in lg.REFUSED


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


@pytest.mark.parametrize("command", [
    'rm -rf "$TEMP/claude/C--proj/e13f/scratchpad/x"',
    "rm -rf ${TMP}/claude/C--proj/e13f/scratchpad/x",
])
def test_a_scratch_delete_by_variable_passes_this_rule_but_meets_the_popup_rule(command):
    """Allowed by the recursive-delete rule before the pop-up rule was ported,
    and still: the scratchpad reading is unchanged. A Bash `rm` on a variable
    path now meets the every-window pop-up rule -- write the scratch path out."""
    assert lg.refused_deletes(command, ROOM, PROJECT, windows=True) == []
    said = win(command)
    assert said and "raises a permission pop-up" in said
    assert "recursive delete outside your scratchpad" not in said
    assert "not `$TEMP/...`" in said, "the refusal does not name the fix"


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
    "rm -rf /var/folders/xy/abc123/T/claude/p/s/scratchpad/x",
    "rm -rf /private/var/folders/xy/abc123/T/claude/p/s/scratchpad/x",
    "rm -rf /tmp/claude/p/s/scratchpad/x",
    "rm -rf /private/tmp/claude-501/p/s/scratchpad/x",
    "rm -rf /tmp/claude-1000/p/s/scratchpad/x",
    "python3 -c \"import shutil; shutil.rmtree('/tmp/claude/p/s/x')\"",
])
def test_posix_a_recursive_delete_inside_the_scratchpad_is_allowed(command):
    assert posix(command) is None


@pytest.mark.parametrize("command", [
    "rm -rf $TMPDIR/claude/-Users-someone-work-Boat-Log/e13f/scratchpad/x",
    'rm -rf "${TMPDIR}claude/-Users-someone/e13f/scratchpad/x"',
])
def test_posix_a_scratch_delete_by_variable_meets_the_popup_rule(command):
    assert lg.refused_deletes(command, P_ROOM, P_PROJECT, windows=False) == []
    said = posix(command)
    assert said and "raises a permission pop-up" in said
    assert "recursive delete outside your scratchpad" not in said


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


# --- PowerShell text writes into the project, every window ----------------------

#: A window with no role at all, the project named the way Claude Code names it
#: to a hook.
WINDOW = {"TEMP": TEMP, "TMP": TEMP, "USERPROFILE": HOME, "CLAUDE_PROJECT_DIR": PROJECT}
DESK = {**WINDOW, pi.ROLE_ENV: "desk", pi.WINDOW_ENV: "the-desk"}
LANE_ROOM = {**ROOM, "CLAUDE_PROJECT_DIR": PROJECT}
EVERY = pytest.mark.parametrize("environ", [LANE_ROOM, DESK, WINDOW],
                                ids=["lane", "desk", "no-role"])

#: What every write refusal says.
WRITE_WHY = "244 lines"


@pytest.mark.parametrize("command, tool", [
    ("Set-Content -Path records/x.md -Value x", "PowerShell"),
    ("(Get-Content f.md -Raw) -replace 'a','b' | Set-Content f.md -Encoding utf8", "PowerShell"),
    ("Add-Content -LiteralPath '" + PROJECT + "\\coordination\\log.md' 'a line'", "PowerShell"),
    ('"x" | Out-File -FilePath notes.md -Append', "PowerShell"),
    ("Out-File notes.md", "PowerShell"),
    ("Set-Content -Value y -Path x.md", "PowerShell"),
    ("Set-Content -Path:x.md -Value y", "PowerShell"),
    ("Set-Content -Lit x.md y", "PowerShell"),
    ("Set-Content $env:TEMP\\a.txt,x.md y", "PowerShell"),
    ("sc x.md 'y'", "PowerShell"),
    ("ac records\\x.md 'y'", "PowerShell"),
    ("$p = 'records\\2025\\log.md'; (Get-Content $p -Raw) -replace 'a','b' | Set-Content $p",
     "PowerShell"),
    ("$p='x.md'; Set-Content $p y", "PowerShell"),
    ("$p = Join-Path $pwd 'x.md'; Set-Content $p y", "PowerShell"),
    ("Set-Content $somewhere y", "PowerShell"),
    ("Get-ChildItem *.md | Set-Content -Value y", "PowerShell"),
    ('powershell -Command "Set-Content x.md y"', "Bash"),
    ('powershell -Command "sc x.md y"', "Bash"),
    ("cd x; Set-Content '" + PROJECT + "\\x.md' y", "PowerShell"),
    ("Set-Content '" + PROJECT_BASH + "/x.md' y", "PowerShell"),
])
@EVERY
def test_a_powershell_text_write_into_the_project_is_refused(command, tool, environ):
    said = win(command, tool, environ)
    assert said and "REFUSED" in said
    assert "PowerShell text write into a project file" in said
    assert "Edit or Write tool" in said and "Python script" in said
    assert WRITE_WHY in said and "ANSI codepage" in said, "the refusal does not say why"


def test_outside_a_lane_the_write_refusal_is_for_this_window():
    said = win("Set-Content -Path records/x.md -Value x", "PowerShell", WINDOW)
    assert said.startswith("REFUSED in this window:")
    said = win("Set-Content -Path records/x.md -Value x", "PowerShell", DESK)
    assert said.startswith("REFUSED in this window:")


@pytest.mark.parametrize("command, tool", [
    ("Set-Content -Path $env:TEMP\\claude\\x.txt -Value y", "PowerShell"),
    ('"x" | Out-File -FilePath "$env:TEMP\\out.txt"', "PowerShell"),
    ("Add-Content " + TEMP + "\\notes.txt y", "PowerShell"),
    ("Set-Content -Path " + HOME + "\\Documents\\x.txt -Value y", "PowerShell"),
    ("Set-Content -Path 'P:\\Work\\Boat Log Two\\x.txt' -Value y", "PowerShell"),
    ("$p = \"$env:TEMP\\x.txt\"; Set-Content $p y", "PowerShell"),
    ('"x" > notes.md', "PowerShell"),
    ('"x" >> notes.md', "PowerShell"),
    ("Get-Content x.md -Raw", "PowerShell"),
    ("Select-String -Pattern 'Out-File' -Path x.md", "PowerShell"),
    ("Write-Output 'Set-Content x.md y'", "PowerShell"),
    ("rg -n 'Set-Content' skills", "Bash"),
    ("echo Set-Content x.md", "Bash"),
    ("sc query", "Bash"),
    (".venv/Scripts/python.exe scripts/check_docs.py", "PowerShell"),
])
@pytest.mark.parametrize("environ", [DESK, WINDOW], ids=["desk", "no-role"])
def test_what_is_not_a_powershell_write_into_the_project_passes(command, tool, environ):
    assert win(command, tool, environ) is None


def test_the_write_refusal_names_the_command_and_the_target():
    said = win("Set-Content -Path records/x.md -Value x", "PowerShell", WINDOW)
    assert "`Set-Content` on `records/x.md`" in said
    said = win("Set-Content $somewhere y", "PowerShell", WINDOW)
    assert "cannot read" in said


def test_in_a_lane_a_write_and_a_git_refusal_are_both_named():
    said = win("Set-Content x.md y; git commit -m x", "PowerShell", LANE_ROOM)
    assert "REFUSED for lane lane-alpha" in said
    assert "`git commit`" in said and WRITE_WHY in said


def test_the_project_folder_defaults_to_the_one_project_identity_names():
    """Claude Code hands a hook `$CLAUDE_PROJECT_DIR`; without it, the folder
    that holds `scripts/` -- derived, never written in."""
    expected = lg.normal(str(pi.REPO).replace("\\", "/"), True)
    assert lg.project_root({}, windows=True) == expected
    target = str(pi.REPO / "records" / "x.md")
    payload = {**shell(f"Set-Content '{target}' y", "PowerShell"), "cwd": PROJECT}
    assert lg.verdict(payload, {"TEMP": TEMP}, windows=True)


def test_the_refusals_name_no_project():
    """Kit-owned: the reasons are the same bytes in every seeded project."""
    for text in (lg.WRITE_REASON, lg.POPUP_REASON):
        assert pi.NAME not in text
        assert "FACOWORK" not in text and "GM" not in text


def test_main_refuses_a_write_with_no_role_with_exit_2(monkeypatch, capsys):
    """From a stand-in project outside a stand-in temp folder: the kit tests a
    seeded project by seeding it into a scratchpad, where a write is allowed,
    so the real working folder would pass there for the wrong reason."""
    project = str(Path.home() / "stand-in-project")       # read as a path, never created
    monkeypatch.delenv(pi.ROLE_ENV, raising=False)
    for var in lg.TEMP_VARS:
        monkeypatch.setenv(var, str(Path.home() / "stand-in-temp"))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", project)
    payload = {**shell("Set-Content x.md y", "PowerShell"), "cwd": project}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert lg.main() == 2
    assert "REFUSED in this window" in capsys.readouterr().err


# --- literal blocks are text, not commands --------------------------------------

#: A here-string whose body holds an apostrophe, then the write -- the shape a
#: quote reader that does not know here-strings lets through.
HERE_THEN_WRITE = ("$t = @'\n\n\n# --- an excerpt ---\n\n"
                   "SLICE_LOG = \"\"\"\\\n## The owner's answers, word for word\n\"\"\"\n'@\n"
                   "Add-Content -Path tests/test_x.py -Value $t -Encoding utf8 -NoNewline")


@pytest.mark.parametrize("command", [
    HERE_THEN_WRITE,
    "$t = @'\nit's\n'@; Set-Content x.md $t",
    "$t = @\"\nthe owner's \"word\"\n\"@\nOut-File -FilePath notes.md -InputObject $t",
    "@'\nthe lane's text\n'@ | Set-Content -Encoding utf8 records/x.md",
    "@'\nit's\n'@ | Out-File notes.md -Append",
    "$t = @'\nit's\n  '@\nac records\\x.md $t",
    "$a = @'\none's\n'@\n$b = @\"\ntwo's\n\"@\nAdd-Content x.md $a; Add-Content y.md $b",
])
@EVERY
def test_a_write_after_a_here_string_is_refused_in_every_window(command, environ):
    said = win(command, "PowerShell", environ)
    assert said and "PowerShell text write into a project file" in said
    assert WRITE_WHY in said


def test_the_write_after_a_here_string_names_its_target():
    said = win(HERE_THEN_WRITE, "PowerShell", WINDOW)
    assert "`Add-Content` on `tests/test_x.py`" in said


@pytest.mark.parametrize("command", [
    # The body is text: a write it mentions is not a write.
    "$t = @'\nSet-Content x.md y; it's\n'@; Write-Output $t",
    "@\"\nAdd-Content records/x.md y\n\"@ | Write-Output",
    # A here-string written to scratch.
    '$sp = "' + SCRATCH + '"\n@"\nimport sys\nprint(\'it\'s\')\n"@ | '
    'Set-Content -Encoding utf8 "$sp\\inspect.py"\n.venv/Scripts/python.exe "$sp\\inspect.py"',
])
@pytest.mark.parametrize("environ", [DESK, WINDOW], ids=["desk", "no-role"])
def test_a_here_strings_body_is_not_a_write(command, environ):
    assert win(command, "PowerShell", environ) is None


def test_a_double_quoted_here_string_still_runs_its_subexpression():
    command = "$t = @\"\nthe lane's $(Set-Content x.md y)\n\"@"
    said = win(command, "PowerShell", WINDOW)
    assert said and "`Set-Content` on `x.md`" in said


@pytest.mark.parametrize("command", [
    # A commit message from a heredoc that mentions the refused shapes.
    "git commit -F - <<'EOF'\nStop Set-Content x.md y and rm \"$X/y\"; it's text\nEOF",
    "cat <<'EOF' > notes.txt\nOut-File notes.md; sed -i 's/a/b/' ~/x.md\nEOF",
    ".venv/Scripts/python.exe - <<'EOF'\nfor c in cmds:\n"
    "    if \"Add-Content\" in c or \"Set-Content\" in c:\n        print(c)\nEOF",
    "python - <<-'PY'\n\tprint(\"rm $X\")\n\tPY\necho done",
])
@pytest.mark.parametrize("environ", [DESK, WINDOW], ids=["desk", "no-role"])
def test_a_heredocs_body_is_not_a_command(command, environ):
    assert win(command, "Bash", environ) is None


@pytest.mark.parametrize("command", [
    "cat <<'EOF' > notes.txt\nthe owner's answer\nEOF\nrm \"$X/y\"",
    "cat <<EOF\nthe lane's $(rm \"$X/y\")\nEOF",
    "cat <<EOF\nit's `rm $X`\nEOF",
])
def test_a_command_after_or_inside_a_heredoc_is_still_read(command):
    said = win(command, "Bash", WINDOW)
    assert said and "raises a permission pop-up" in said


@pytest.mark.parametrize("command", [
    ".venv/Scripts/python.exe -c \"print(1)\"; Add-Content -Path NUL -Value x "
    "-ErrorAction SilentlyContinue",
    "Set-Content nul y",
    "Out-File -FilePath NUL",
    "Out-File $null",
    "Add-Content -Path con -Value x",
    "Set-Content -LiteralPath C:\\x\\NUL.txt y",
])
@EVERY
def test_a_write_to_a_device_is_not_a_write_into_the_project(command, environ):
    assert win(command, "PowerShell", environ) is None


def test_a_device_name_inside_a_file_name_is_still_a_file():
    for target in ("null.md", "nullable.md", "records/console.md", "conx.md"):
        assert win(f"Set-Content {target} y", "PowerShell", WINDOW), target


# --- command shapes that raise a permission pop-up, every window ----------------

MEMORY = "/q/Users/someone/.claude/projects/C--proj/memory"
POPUP_WHY = "we should not be doing things"


@pytest.mark.parametrize("command, tool", [
    # The pop-up that set the rule: a plain `rm` on a variable path.
    ('S="$TEMP/claude/acceptance-2"; R="$S/root"; T=records/cleanup/reports; '
     'rm "$R/$T/x-nokept.md" "$R/$T/x-badkept.md"', "Bash"),
    ('cd "P:/Work/Boat Log" && SCRATCH="$TEMP/recon_smoke" && rm -rf "$SCRATCH" '
     '&& mkdir -p "$SCRATCH/piles"', "Bash"),
    ('S="Q:/Users/someone/AppData/Local/Temp/claude/C--proj/cc18/scratchpad/integ"; '
     'rm -rf "$S"; mkdir -p "$S/run"', "Bash"),
    ('for s in a b; do rm -rf "$SCR/$s"; done', "Bash"),
    ("rm -f ${OUT}/x.txt", "Bash"),
    ("rm $(ls *.bak)", "Bash"),
    ("rm `cat old_files.txt`", "Bash"),
    ('rmdir "$D"', "Bash"),
    ("bash -c 'rm -f $X'", "Bash"),
    ('bash -c "rm -rf $HOME/x"', "PowerShell"),
    # An in-place edit outside the project (a memory file).
    (f'M="{MEMORY}"; sed -i \'s/^name: a-b$/name: a_b/\' "$M/project_x.md" '
     f'&& grep -n name "$M/project_x.md"', "Bash"),
    ("sed -i 's/a/b/' Q:/Users/someone/.claude/projects/C--proj/memory/x.md", "Bash"),
    ("sed -i -e 's/a/b/' ~/notes.md", "Bash"),
    ("sed --in-place 's/a/b/' /q/Users/someone/Documents/x.md", "Bash"),
    ("sed -Ei.bak 's/a/b/' /q/Users/someone/Documents/x.md", "Bash"),
])
@EVERY
def test_a_popup_shape_is_refused_in_every_window(command, tool, environ):
    said = win(command, tool, environ)
    assert said and "REFUSED" in said and "raises a permission pop-up" in said
    assert "Python" in said and "Edit tool" in said, "the refusal does not name the other way"
    assert POPUP_WHY in said, "the refusal does not say why"


def test_the_popup_refusal_names_the_command_and_the_path():
    said = win('rm "$R/$T/x-nokept.md"', environ=DESK)
    assert said.startswith("REFUSED in this window:")
    assert "`rm` on `$R/$T/x-nokept.md`" in said and "possibly-empty variable path" in said
    said = win(f"sed -i 's/a/b/' {MEMORY}/x.md", environ=DESK)
    assert f"`sed -i` on `{MEMORY}/x.md` -- a file outside the project folder" in said


def test_in_a_lane_a_popup_and_a_recursive_delete_are_both_named():
    said = win('rm -rf "$scratch_dir"', environ=LANE_ROOM)
    assert "REFUSED for lane lane-alpha" in said
    assert "recursive delete outside your scratchpad" in said
    assert "raises a permission pop-up" in said


@pytest.mark.parametrize("command, tool", [
    # The same deletes, the path written out, or done inside Python.
    ("rm " + SCRATCH.replace("\\", "/") + "/x-nokept.md", "Bash"),
    ('rm "' + SCRATCH.replace("\\", "/") + '/root/records/x-nokept.md"', "Bash"),
    ("rm -rf " + SCRATCH.replace("\\", "/") + "/sim1", "Bash"),
    ("rmdir " + SCRATCH.replace("\\", "/") + "/empty", "Bash"),
    ('.venv/Scripts/python.exe -c "import os; os.remove(os.path.join(os.environ[\'TEMP\'], '
     '\'claude\', \'x.md\'))"', "Bash"),
    # PowerShell's variable deletes never raised one; not this rule's business.
    ("Remove-Item $f -ErrorAction SilentlyContinue", "PowerShell"),
    ('Remove-Item -LiteralPath "$env:TEMP\\claude\\x.txt"', "PowerShell"),
    ("$o = Join-Path $env:TEMP 'claude\\o.txt'; Remove-Item $o", "PowerShell"),
    # Text that mentions the shape, and a delete whose paths come from find.
    ('echo "rm $X"', "Bash"),
    ("grep -n 'rm \"$R' f.md", "Bash"),
    ("find . -name '*.tmp' -exec rm {} +", "Bash"),
    # In-place edits inside the project or the temp folder, or of a path it cannot read.
    ("sed -i 's/a/b/' tests/test_x.py", "Bash"),
    ("sed -i 's/a/b/' '" + PROJECT + "\\scripts\\x.py'", "Bash"),
    ('S="/q/Users/someone/AppData/Local/Temp/claude/C--proj/03e2/scratchpad"; '
     'sed -i \'s/a/b/\' "$S/pi_map.py"', "Bash"),
    ("sed -i 's/a/b/' \"$TEMP/old_rl.py\"", "Bash"),
    ("sed -i 's/a/b/' \"$UNSET/x.md\"", "Bash"),
    # Not in place: a read, or a write by redirection.
    (f"sed -n '1,5p' {MEMORY}/x.md", "Bash"),
    (f"sed 's/a/b/' {MEMORY}/x.md > out.md", "Bash"),
    ("sed -e 's/i/j/' -n Q:/Users/someone/x.md", "Bash"),
])
@pytest.mark.parametrize("environ", [DESK, WINDOW], ids=["desk", "no-role"])
def test_the_other_way_passes(command, tool, environ):
    assert win(command, tool, environ) is None


@pytest.mark.parametrize("payload", [
    # Legitimate pop-ups with no other way: a settings edit, a command file
    # under `.claude/`, the update-config skill. The guard never sees them.
    {"tool_name": "Edit", "tool_input": {"file_path": PROJECT + "\\.claude\\settings.json"}},
    {"tool_name": "Write", "tool_input": {"file_path": PROJECT + "\\.claude\\commands\\x.md"}},
    {"tool_name": "Skill", "tool_input": {"skill": "update-config"}},
    # What the lane and desk skills tell a window to run.
    {**shell(".venv/Scripts/python.exe scripts/desk_record.py show guard-write",
             "PowerShell"), "cwd": PROJECT},
    {**shell(".venv/Scripts/python.exe scripts/desk_record.py report-done guard-write",
             "PowerShell"), "cwd": PROJECT},
    {**shell(".venv/Scripts/python.exe scripts/check_docs.py", "Bash"), "cwd": PROJECT},
    {**shell("git commit -F Working/commit_msg.txt && git push", "Bash"), "cwd": PROJECT},
])
def test_legitimate_prompts_and_prescribed_commands_are_not_refused(payload):
    assert lg.verdict(payload, DESK, windows=True) is None
    assert lg.verdict(payload, WINDOW, windows=True) is None


# --- the every-window rules on macOS and Linux paths ---------------------------

P_WINDOW = {"HOME": P_HOME, "TMPDIR": P_TMPDIR, "CLAUDE_PROJECT_DIR": P_PROJECT}


@pytest.mark.parametrize("command", [
    'pwsh -Command "Set-Content x.md y"',
    "pwsh -Command \"Out-File '" + P_PROJECT + "/notes.md'\"",
    'rm "$X/y"',
    "sed -i 's/a/b/' ~/.claude/projects/p/memory/x.md",
    "sed -i 's/a/b/' '/Users/someone/work/Boat Log Two/x.md'",
])
def test_posix_the_every_window_rules_hold(command):
    said = posix(command, P_WINDOW)
    assert said and said.startswith("REFUSED in this window:")


@pytest.mark.parametrize("command", [
    "sed -i 's/a/b/' tests/test_x.py",
    "sed -i 's/a/b/' /tmp/claude/p/s/x.py",
    "sed -i 's/a/b/' /private/var/folders/xy/abc123/T/x.py",
    "pwsh -Command \"Set-Content /tmp/x.txt y\"",
    "rm /tmp/claude/p/s/scratchpad/x.md",
])
def test_posix_the_other_way_passes(command):
    assert posix(command, P_WINDOW) is None


# --- the settings the seeder writes ---------------------------------------------


def test_the_tracked_settings_wire_the_guard_to_this_machines_shells():
    """`Bash|PowerShell` on Windows, `Bash` elsewhere, run by this machine's
    venv interpreter -- the values come from `project_identity`, not literals."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    # A project may add PreToolUse hooks for other tools; the guard's is the shell one.
    (entry,) = [e for e in settings["hooks"]["PreToolUse"]
                if any("lane_guard.py" in a for h in e["hooks"] for a in h.get("args", []))]
    assert set(entry["matcher"].split("|")) == set(pi.shell_tools())
    (hook,) = entry["hooks"]
    assert hook["args"] == ["${CLAUDE_PROJECT_DIR}/scripts/lane_guard.py"]
    assert hook["command"] == pi.settings_python()
