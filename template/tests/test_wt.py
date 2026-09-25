"""Tests for scripts/wt.py -- the Windows Terminal invocation, and the line
to paste where there is no Windows Terminal.

Adapted from Fantasy Football's tests/test_wt.py with the module, and carried
by way of FACOWORK and HAZELHURST into the Starter Kit (kit-owned). The tests
that start a real PowerShell are the ones that matter most: what has to be true
is what the shell hands the program after parsing, and the only way to know
that is to ask a shell.
"""
import base64
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import project_identity as pi
import wt
from wt import (TerminalError, Window, child_environment, command_line,
                encode_command, manual_line, posix_line, powershell_line,
                ps_statement, quote, window_command)

REPO = Path(__file__).resolve().parents[1]

# Every character either parser acts on, plus the two PowerShell would expand
# inside a double-quoted string.
HOSTILE = """a b; c & d | e 'f' "g" $h `i"""

needs_powershell = pytest.mark.skipif(
    os.name != "nt", reason="asks a real powershell.exe")


def _decoded(command):
    return base64.b64decode(command[-1]).decode("utf-16-le")


def _shell_exit_code(blob):
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-EncodedCommand", blob],
        capture_output=True, check=False,
    ).returncode


# --- the encoding, which is the whole point ---------------------------------


def test_the_blob_carries_nothing_either_parser_can_act_on():
    blob = encode_command(ps_statement(["claude", "--name", "x", HOSTILE]))
    for hazard in (" ", ";", "&", "|", "'", '"', "$", "`"):
        assert hazard not in blob, "%r survived into the encoded command" % hazard


@needs_powershell
def test_a_hostile_task_arrives_whole():
    blob = encode_command(ps_statement(["Write-Output", HOSTILE]))
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-EncodedCommand", blob],
        capture_output=True, check=True,
    )
    assert proc.stdout.decode("utf-8", "replace").strip() == HOSTILE


def test_a_single_quote_is_doubled_rather_than_escaped():
    statement = ps_statement(["claude", "the owner's task"])
    assert statement == "& 'claude' 'the owner''s task'"
    assert _decoded(window_command(
        Window(label="x", argv=("claude", "the owner's task")), cwd=REPO)) == statement


def test_the_encoding_is_utf_16le():
    statement = ps_statement(["claude", "a task"])
    assert base64.b64decode(encode_command(statement)).decode("utf-16-le") == statement


def test_an_empty_argv_is_refused():
    with pytest.raises(TerminalError):
        ps_statement([])


# --- the argv ---------------------------------------------------------------


def test_a_window_target_builds_a_tab_and_no_target_builds_a_window():
    tab = window_command(
        Window(label="x", argv=("claude",), window_target="shared-window"), cwd=REPO)
    assert tab[:4] == ["wt.exe", "-w", "shared-window", "new-tab"]
    own = window_command(Window(label="x", argv=("claude",)), cwd=REPO)
    assert own[:3] == ["wt.exe", "-w", "new"]
    assert "new-tab" not in own


def test_the_working_directory_with_a_space_is_one_token():
    """This workspace's own path has a space in it."""
    command = window_command(
        Window(label="x", argv=("claude",)), cwd="C:/a folder/here")
    assert command[command.index("-d") + 1] == "C:/a folder/here"
    assert '"C:/a folder/here"' in command_line(command)


def test_a_title_and_a_colour_reach_the_command_line():
    command = window_command(
        Window(label="x", argv=("claude",), window_target="shared-window",
               tab_title="lane-alpha", tab_color="#4169E1"), cwd=REPO)
    assert command[command.index("--title") + 1] == "lane-alpha"
    assert command[command.index("--tabColor") + 1] == "#4169E1"


@pytest.mark.parametrize("bad", ["blue", "#12345", "4169E1", "#GGGGGG", ""])
def test_a_colour_terminal_cannot_read_is_refused_here(bad):
    """Terminal swallows it: the tab opens uncoloured, exit 0, nothing said."""
    with pytest.raises(TerminalError):
        window_command(Window(label="x", argv=("claude",), tab_color=bad), cwd=REPO)


def test_quote_only_quotes_what_needs_it():
    assert quote("plain") == "plain"
    assert quote("two words") == '"two words"'
    assert quote("") == '""'
    assert quote("#4169E1") == '"#4169E1"', (
        "an unquoted colour starts a PowerShell comment in the pasted line")


def test_a_conversation_window_does_not_outlive_its_session():
    kept = window_command(Window(label="x", argv=("claude",)), cwd=REPO)
    assert "-NoExit" in kept
    gone = window_command(
        Window(label="x", argv=("claude",), keep_open=False), cwd=REPO)
    assert "-NoExit" not in gone


# --- the marker that lets a closed window's pane go -------------------------


def test_a_window_with_no_marker_is_the_bare_call():
    assert ps_statement(["claude", "x"]) == "& 'claude' 'x'"


def test_a_marked_window_ends_by_deciding_its_own_exit_code():
    statement = ps_statement(["claude"], close_marker="C:/tmp/it's.closing")
    assert statement.endswith("; exit $code")
    assert "'C:/tmp/it''s.closing'" in statement, "the marker path is not quoted"


@needs_powershell
def test_a_killed_window_exits_zero_and_a_crashed_one_keeps_its_code(tmp_path):
    """Both directions, because a fix that closed BOTH panes would pass an
    assertion about the killed one while taking the crash message away."""
    marker = tmp_path / "panes.closing"
    blob = encode_command(ps_statement(
        [sys.executable, "-c", "raise SystemExit(3)"], close_marker=str(marker)))
    assert _shell_exit_code(blob) == 3, (
        "a window that died on its own must keep its pane, and its error")
    marker.write_text("closed on purpose\n", encoding="utf-8")
    assert _shell_exit_code(blob) == 0, (
        "a window somebody closed must exit 0, or Terminal keeps the pane")
    assert not marker.exists(), (
        "the marker outlived its window and would close the next one's pane")


@needs_powershell
def test_a_program_that_never_ran_keeps_its_pane_too(tmp_path):
    blob = encode_command(ps_statement(
        ["kit-no-such-program-xyz"], close_marker=str(tmp_path / "x.closing")))
    assert _shell_exit_code(blob) != 0


def test_noexit_and_a_close_marker_are_refused_together():
    with pytest.raises(TerminalError):
        window_command(
            Window(label="x", argv=("claude",), keep_open=True,
                   close_marker="C:/tmp/x.closing"), cwd=REPO)


# --- what a window must not inherit -----------------------------------------


def test_the_child_inherits_none_of_this_sessions_identity():
    child = child_environment({
        "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "abc", "claude_pid": "9",
        "PATH": "C:/bin", "USERPROFILE": "C:/Users/x",
    })
    assert child == {"PATH": "C:/bin", "USERPROFILE": "C:/Users/x"}


@pytest.mark.parametrize("marker", sorted(wt.HEADLESS_MARKERS))
def test_every_headless_marker_is_stripped(marker):
    assert marker not in child_environment({marker: "1", "PATH": "x"})


_HEADLESS_SHAPE = re.compile(
    r"COLOR|^TERM$|^CI$|TERMINAL_PROMPT|_INTERACTIVE$|^TTY|NONINTERACTIVE",
    re.IGNORECASE,
)

# A name of this shape that must SURVIVE goes here with its reason.
_KEPT_DESPITE_SHAPE = frozenset()


def test_this_shells_own_headless_markers_are_all_covered():
    """THE ONE THAT FIRES ON THE DAY THE HARNESS ADDS A SIBLING. It reads the
    environment the suite is actually running in -- a harness tool shell, the
    same shell `launch` copies from."""
    uncovered = sorted(
        name for name in os.environ
        if _HEADLESS_SHAPE.search(name)
        and name.upper() not in wt.HEADLESS_MARKERS
        and name not in _KEPT_DESPITE_SHAPE
        and not name.upper().startswith("CLAUDE")
    )
    assert not uncovered, (
        "this shell sets %s, which every window opened from it would inherit. "
        "Add each to wt.HEADLESS_MARKERS, or to _KEPT_DESPITE_SHAPE here with "
        "the reason it must survive" % uncovered)


def test_the_audit_is_looking_at_something():
    assert _HEADLESS_SHAPE.search("NO_COLOR")
    assert not _HEADLESS_SHAPE.search("PATH")
    assert all(_HEADLESS_SHAPE.search(name) for name in wt.HEADLESS_MARKERS)


def test_launch_cleans_the_environment_without_being_asked(monkeypatch):
    seen = {}
    monkeypatch.setattr(wt, "available", lambda: True)
    monkeypatch.setattr(
        wt.subprocess, "run",
        lambda command, check, env: seen.update(command=command, env=env))
    wt.launch(["wt.exe", "x"], env={"CLAUDECODE": "1", "NO_COLOR": "1", "PATH": "p"})
    assert seen["env"] == {"PATH": "p"}


def test_no_terminal_is_a_refusal_not_a_traceback(monkeypatch):
    monkeypatch.setattr(wt, "available", lambda: False)
    with pytest.raises(TerminalError):
        wt.launch(["wt.exe", "x"])


def test_env_is_set_before_the_program_and_quoted_like_any_token():
    """With this project's own variable names, which must be ones PowerShell
    and the check here accept whatever the folder is called."""
    statement = ps_statement(["claude", "x"], env=((pi.ROLE_ENV, "lane"),
                                                   (pi.WINDOW_ENV, "owner's")))
    assert statement == (f"$env:{pi.ROLE_ENV} = 'lane'; $env:{pi.WINDOW_ENV} = 'owner''s'; "
                         "& 'claude' 'x'")


def test_a_bad_env_name_is_refused():
    with pytest.raises(TerminalError):
        ps_statement(["claude"], env=(("BAD NAME; rm", "x"),))



# --- the manual line, where there is no Windows Terminal ------------------------

#: A lane window as `open_terminal.window_for` builds one, with fixed variable
#: names so the expected lines can be written out whole.
LANE_WINDOW = Window(
    label="lane-alpha (lane, opus)",
    argv=("claude", "--model", "opus", "--permission-mode", "acceptEdits",
          "--name", "lane-alpha", "/lane lane-alpha coordination/task_sheets/lane-alpha.md"),
    keep_open=False, close_marker="/tmp/boat-log-terminal-lane-alpha.closing",
    window_target="boat-log", tab_title="lane-alpha", tab_color="#4169E1",
    env=(("BOAT_LOG_ROLE", "lane"), ("BOAT_LOG_WINDOW", "lane-alpha")),
)

needs_sh = pytest.mark.skipif(shutil.which("sh") is None, reason="asks a real POSIX sh")


def test_the_posix_line_is_cd_then_the_variables_then_claude():
    """What a macOS or Linux owner pastes into a new tab: the project folder,
    always quoted; the two variables for the program alone; the same argv the
    Windows Terminal tab would run."""
    line = manual_line(LANE_WINDOW, cwd="/Users/someone/Boat Log", os_name="posix")
    assert line == (
        "cd '/Users/someone/Boat Log' && BOAT_LOG_ROLE=lane BOAT_LOG_WINDOW=lane-alpha "
        "claude --model opus --permission-mode acceptEdits --name lane-alpha "
        "'/lane lane-alpha coordination/task_sheets/lane-alpha.md'")
    words = shlex.split(line)
    assert words[:4] == ["cd", "/Users/someone/Boat Log", "&&", "BOAT_LOG_ROLE=lane"]
    assert tuple(words[5:]) == LANE_WINDOW.argv


def test_the_windows_line_without_wt_is_one_powershell_line():
    line = manual_line(LANE_WINDOW, cwd=r"C:\Users\someone\Boat Log", os_name="nt")
    assert line == (
        r"Set-Location -LiteralPath 'C:\Users\someone\Boat Log'; "
        "$env:BOAT_LOG_ROLE = 'lane'; $env:BOAT_LOG_WINDOW = 'lane-alpha'; "
        "& 'claude' '--model' 'opus' '--permission-mode' 'acceptEdits' '--name' "
        "'lane-alpha' '/lane lane-alpha coordination/task_sheets/lane-alpha.md'")


def test_the_manual_line_carries_no_tab_title_colour_or_marker():
    """They mean something only in a tab this program opened."""
    for os_name in ("nt", "posix"):
        line = manual_line(LANE_WINDOW, cwd="/x", os_name=os_name)
        assert "#4169E1" not in line and ".closing" not in line and "wt.exe" not in line


def test_an_apostrophe_in_the_folder_or_the_task_survives_the_posix_line():
    window = LANE_WINDOW._replace(argv=("claude", "the owner's task"))
    line = posix_line(window.argv, cwd="/Users/o'brien/Boat Log", env=window.env)
    words = shlex.split(line)
    assert words[1] == "/Users/o'brien/Boat Log" and words[-1] == "the owner's task"


def test_a_bad_variable_name_is_refused_on_the_posix_line_too():
    with pytest.raises(TerminalError):
        posix_line(["claude"], cwd="/x", env=(("BAD NAME; rm", "x"),))
    with pytest.raises(TerminalError):
        posix_line([], cwd="/x")


PROBE = "import os, sys; print(os.getcwd() + '|' + os.environ['KIT_PROBE_ROLE'] + '|' + sys.argv[1])"


@needs_sh
def test_a_real_sh_runs_the_posix_line_whole(tmp_path):
    """Asked of a real shell: the folder is entered, the variable reaches the
    program, and a hostile task arrives as one argument."""
    folder = tmp_path / "a b"
    folder.mkdir()
    cwd = folder.as_posix() if os.name != "nt" else str(folder)
    line = posix_line([Path(sys.executable).as_posix(), "-c", PROBE, HOSTILE],
                      cwd=cwd, env=(("KIT_PROBE_ROLE", "lane"),))
    proc = subprocess.run(["sh", "-c", line], capture_output=True, check=False)
    where, role, task = proc.stdout.decode("utf-8", "replace").strip().split("|", 2)
    assert (Path(where).resolve(), role, task) == (folder.resolve(), "lane", HOSTILE), proc.stderr


@needs_powershell
def test_a_real_powershell_runs_the_windows_line_whole(tmp_path):
    folder = tmp_path / "a b"
    folder.mkdir()
    line = powershell_line([sys.executable, "-c", PROBE, "the owner's task"],
                           cwd=str(folder), env=(("KIT_PROBE_ROLE", "lane"),))
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-Command", line],
                          capture_output=True, check=False)
    where, role, task = proc.stdout.decode("utf-8", "replace").strip().split("|", 2)
    assert (Path(where).resolve(), role, task) == (folder.resolve(), "lane", "the owner's task")
