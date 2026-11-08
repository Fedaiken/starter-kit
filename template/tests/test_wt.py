"""Tests for scripts/wt.py -- the Windows Terminal invocation, and the line
to paste where there is no Windows Terminal.

Adapted from Fantasy Football's tests/test_wt.py with the module, and carried
by way of FACOWORK and HAZELHURST into the Starter Kit (kit-owned). The tests
that start a real PowerShell are the ones that matter most: what has to be true
is what the shell hands the program after parsing, and the only way to know
that is to ask a shell.
"""
import base64
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
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


def test_a_join_builds_a_tab_and_no_join_builds_a_window_of_its_own():
    tab = window_command(Window(label="x", argv=("claude",), join="shared-window"), cwd=REPO)
    assert tab[:4] == ["wt.exe", "-w", "shared-window", "new-tab"]
    own = window_command(Window(label="x", argv=("claude",), tab_title="lane-alpha",
                                tab_color="#4169E1", keep_open=False,
                                close_marker="C:/tmp/x.closing"), cwd=REPO)
    assert own[:3] == ["wt.exe", "-w", "new"]
    assert "new-tab" not in own and own.count("-w") == 1


def test_the_working_directory_with_a_space_is_one_token():
    """This workspace's own path has a space in it."""
    command = window_command(
        Window(label="x", argv=("claude",)), cwd="C:/a folder/here")
    assert command[command.index("-d") + 1] == "C:/a folder/here"
    assert '"C:/a folder/here"' in command_line(command)


def test_a_title_and_a_colour_reach_the_command_line():
    command = window_command(
        Window(label="x", argv=("claude",),
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


@pytest.fixture
def quiet_front(monkeypatch):
    """A launch with no real Terminal, no real front window and no wait.
    Returns the list `front_window` is read from, one entry per read. Window
    500 is a Terminal window that was already open (the owner's desk)."""
    fronts = [wt.Front(101, "the game"), wt.Front(101, "the game")]
    monkeypatch.setattr(wt, "available", lambda: True)
    monkeypatch.setattr(wt, "second_terminal", lambda: None)
    monkeypatch.setattr(wt, "front_window", lambda: fronts.pop(0))
    monkeypatch.setattr(wt, "terminal_windows", lambda: frozenset({500}))
    monkeypatch.setattr(wt.time, "sleep", lambda seconds: None)
    return fronts


def test_launch_cleans_the_environment_without_being_asked(monkeypatch, quiet_front):
    seen = {}
    monkeypatch.setattr(
        wt.subprocess, "run",
        lambda command, check, env, startupinfo: seen.update(command=command, env=env))
    wt.launch(["wt.exe", "x"], env={"CLAUDECODE": "1", "NO_COLOR": "1", "PATH": "p"})
    assert seen["env"] == {"PATH": "p"}


# --- an open never takes the owner's focus ------------------------------------
#
# The owner, 2026-11-07, playing: every lane that opened "pops me out of the
# game". Their ruling: no open ever takes focus, with no if-then. The game
# minimizes itself on losing the front, so the front must never be taken: the
# window starts minimized and not activated (wt.py, AN OPEN NEVER TAKES THE
# OWNER'S FOCUS). No test here launches a real window: test launches landed on
# the owner's play. The proof is the FocusCheck every real open returns.

LANE_OPEN = ["wt.exe", "-w", "new", "--title", "lane-alpha", "-d", "C:/x", "powershell.exe"]


def test_every_launch_starts_minimized_and_not_activated(monkeypatch, quiet_front):
    if os.name != "nt":
        pytest.skip("STARTUPINFO is Windows-only")
    seen = {}
    monkeypatch.setattr(wt.subprocess, "run",
                        lambda command, check, env, startupinfo: seen.update(info=startupinfo))
    wt.launch(LANE_OPEN)
    info = seen["info"]
    assert info.dwFlags & subprocess.STARTF_USESHOWWINDOW, "the show state is ignored without the flag"
    assert info.wShowWindow == 7 == wt.SW_SHOWMINNOACTIVE


def test_off_windows_there_is_no_startup_info_and_no_front(monkeypatch):
    monkeypatch.setattr(wt.os, "name", "posix")
    assert wt.startup_info() is None
    assert wt.front_window() == wt.Front(None)
    assert wt.terminal_windows() == frozenset()


def test_launch_has_no_switch_for_it():
    """No if-then (the owner, 2026-11-07): nothing a caller passes turns it off."""
    import inspect
    assert list(inspect.signature(wt.launch).parameters) == ["command", "env"]


def test_an_open_that_left_the_front_alone_says_so(monkeypatch, quiet_front):
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: None)
    check = wt.launch(LANE_OPEN)
    assert check == wt.FocusCheck("the game", "the game", moved_by_open=False, moved_by_other=False)
    assert check.warning() is None


def test_the_window_the_open_created_taking_the_front_is_flagged(monkeypatch, quiet_front):
    """A Terminal window that was not there before the open is the open's."""
    quiet_front[1] = wt.Front(202, "PowerShell", terminal=True)
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: None)
    check = wt.launch(LANE_OPEN)
    assert check.moved_by_open and not check.moved_by_other
    assert check.warning() == "FOCUS MOVED: the game -> PowerShell"


def test_a_window_titled_as_the_open_taking_the_front_is_flagged(monkeypatch, quiet_front):
    """Claude retitles its window `✳ <name>`: the open's own --title, at the end."""
    quiet_front[1] = wt.Front(202, "\u2733 lane-alpha")
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: None)
    assert wt.launch(LANE_OPEN).moved_by_open


def test_the_owners_own_alt_tab_is_recorded_never_flagged(monkeypatch, quiet_front):
    """Measured 2026-11-07 at the desk: FOCUS MOVED: Task Switching -> ✳ syxplay
    was the owner's own Alt+Tab to a window that was already open."""
    quiet_front[:] = [wt.Front(77, "Task Switching"), wt.Front(500, "\u2733 syxplay", terminal=True)]
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: None)
    check = wt.launch(LANE_OPEN)
    assert check.moved_by_other and not check.moved_by_open
    assert check.warning() is None


def test_a_name_inside_another_name_is_not_the_open(monkeypatch, quiet_front):
    quiet_front[1] = wt.Front(600, "\u2733 lane-alpha-2")
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: None)
    check = wt.launch(LANE_OPEN)
    assert check.moved_by_other and not check.moved_by_open


def test_the_front_is_compared_by_window_not_by_title(monkeypatch, quiet_front):
    """A Claude tab retitles itself with a working glyph every second: the same
    window under a new title has not moved."""
    quiet_front[:] = [wt.Front(500, "\u25d0 lane-alpha", True), wt.Front(500, "\u25d1 lane-alpha", True)]
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: None)
    check = wt.launch(LANE_OPEN)
    assert not check.moved_by_open and not check.moved_by_other


def test_nothing_in_front_reads_as_nothing():
    check = wt.FocusCheck("", "lane-alpha", moved_by_open=True, moved_by_other=False)
    assert check.warning() == "FOCUS MOVED: (nothing) -> lane-alpha"


def test_the_window_title_is_read_off_the_invocation():
    assert wt.window_title(LANE_OPEN) == "lane-alpha"
    assert wt.window_title(["wt.exe", "-w", "new"]) is None
    assert wt.window_title(["wt.exe", "--title"]) is None


def test_the_front_is_read_after_the_wait_and_the_windows_before_the_open(monkeypatch, quiet_front):
    order = []
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: order.append("open"))
    monkeypatch.setattr(wt.time, "sleep", lambda seconds: order.append(("wait", seconds)))
    reads = list(quiet_front)
    monkeypatch.setattr(wt, "front_window", lambda: order.append("read") or reads.pop(0))
    monkeypatch.setattr(wt, "terminal_windows", lambda: order.append("windows") or frozenset())
    wt.launch(LANE_OPEN)
    assert order == ["read", "windows", "open", ("wait", wt.FOCUS_CHECK_DELAY), "read"]


@needs_powershell
def test_the_real_readers_answer_on_this_machine():
    front = wt.front_window()
    assert front.handle is None or (isinstance(front.handle, int) and isinstance(front.title, str))
    windows = wt.terminal_windows()
    assert all(isinstance(handle, int) for handle in windows)
    if front.terminal:
        assert front.handle in windows


def test_nothing_here_can_move_the_front():
    """A hand-back -- giving the front back after Terminal took it -- was built
    and shipped on 2026-11-07. The game had minimized itself by then, and the
    hand-back pushed the owner back to the game from whatever else they were
    doing. The reader reads; nothing in this module may move the front."""
    source = Path(wt.__file__).read_text(encoding="utf-8")
    for call in ("SetForegroundWindow", "AttachThreadInput", "keybd_event",
                 "SendInput", "BringWindowToTop", "SwitchToThisWindow"):
        # Whole words: `wShowWindow`, the start-up show state, is not the call.
        assert not re.search(rf"\b{call}\b", source), f"{call} moves the front"
    # The one window change allowed is `tuck`'s: minimize, never activating.
    shows = re.findall(r"\bShowWindow\(([^)]*)\)", source)
    assert shows == ["handle, SW_SHOWMINNOACTIVE"], shows


# --- tabs in one window: the shared window is minimized before a join ---------


def test_a_title_is_a_name_with_or_without_its_glyph():
    assert wt.titled_as("lane-alpha", "lane-alpha")
    assert wt.titled_as("✳ lane-alpha", "lane-alpha")
    assert not wt.titled_as("✳ lane-alpha-2", "lane-alpha")
    assert not wt.titled_as("xlane-alpha", "lane-alpha")
    assert not wt.titled_as("anything", "")


def test_tuck_and_the_title_reader_do_nothing_off_windows(monkeypatch):
    monkeypatch.setattr(wt.os, "name", "posix")
    assert wt.tuck([1, 2]) == []
    assert wt.terminal_windows_titled(["desk"]) == []


@needs_powershell
def test_tuck_never_touches_the_window_in_front():
    """Asked to tuck the window in front, it does nothing -- the one case in
    which minimizing could change what the owner sees in front of them."""
    front = wt.front_window()
    if front.handle is None:
        pytest.skip("nothing in front to ask about")
    assert wt.tuck([front.handle]) == []
    assert wt.front_window().handle == front.handle


@needs_powershell
def test_the_title_reader_finds_only_terminal_windows():
    windows = wt.terminal_windows()
    names = []
    for handle in sorted(windows)[:3]:
        ctypes, _, user = wt._user32()
        title = wt._text(ctypes, user.GetWindowTextW, handle)
        if title:
            names.append(title.split()[-1])
    assert set(wt.terminal_windows_titled(names)) <= windows


# --- with a Terminal window in front: the second copy --------------------------
#
# wt.py, WITH A TERMINAL WINDOW IN FRONT. Nothing here downloads, installs or
# opens anything: the second copy is the owner's to install.

SECOND = r"C:\second\wt.exe"
INSTALLED_IMAGE = r"C:\Program Files\WindowsApps\Terminal\WindowsTerminal.exe"
SECOND_IMAGE = r"C:\second\WindowsTerminal.exe"
JOIN_OPEN = ["wt.exe", "-w", "shared", "new-tab", "--title", "lane-alpha", "powershell.exe"]


def test_with_no_second_copy_a_new_window_opens_exactly_as_before(monkeypatch, quiet_front):
    """Both desks open through this file. Until the owner installs the second
    copy, nothing about an open may change: one direct start of `wt.exe`,
    minimized and not activated, no WMI and no download."""
    if os.name != "nt":
        pytest.skip("STARTUPINFO is Windows-only")
    calls = []
    monkeypatch.setattr(wt.subprocess, "run",
                        lambda command, check, env, startupinfo: calls.append((command, check, env, startupinfo)))

    def refuse(*args, **kwargs):
        raise AssertionError("an open with no second copy went another way")

    monkeypatch.setattr(wt, "_start_detached", refuse)
    monkeypatch.setattr(wt.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(wt, "install_second_terminal", refuse)
    wt.launch(LANE_OPEN, env={"CLAUDECODE": "1", "PATH": "p"})
    assert len(calls) == 1
    command, check, env, info = calls[0]
    assert (command, check, env) == (LANE_OPEN, True, {"PATH": "p"})
    assert info.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert info.wShowWindow == wt.SW_SHOWMINNOACTIVE


@pytest.fixture
def second_installed(monkeypatch, quiet_front):
    """A launch with the second copy installed. Returns the detached starts."""
    started = []
    monkeypatch.setattr(wt, "second_terminal", lambda: SECOND)
    monkeypatch.setattr(wt, "_start_detached", lambda command, env: started.append((command, env)))
    return started


def _no_direct_start(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a new window was started from this process")

    monkeypatch.setattr(wt.subprocess, "run", refuse)


def test_with_the_installed_terminal_in_front_the_second_copy_opens_it(monkeypatch, quiet_front, second_installed):
    quiet_front[0] = wt.Front(500, "\u2733 syxplay", terminal=True)
    monkeypatch.setattr(wt, "image_of", lambda handle: INSTALLED_IMAGE)
    _no_direct_start(monkeypatch)
    wt.launch(LANE_OPEN, env={"CLAUDECODE": "1", "PATH": "p"})
    assert second_installed == [([SECOND, *LANE_OPEN[1:]], {"PATH": "p"})]


def test_with_the_second_copy_in_front_the_installed_terminal_opens_it(monkeypatch, quiet_front, second_installed):
    quiet_front[0] = wt.Front(700, "\u2733 lane-beta", terminal=True)
    monkeypatch.setattr(wt, "image_of", lambda handle: SECOND_IMAGE)
    _no_direct_start(monkeypatch)
    wt.launch(LANE_OPEN)
    assert second_installed[0][0] == LANE_OPEN


def test_with_anything_else_in_front_the_installed_terminal_opens_it(monkeypatch, quiet_front, second_installed):
    _no_direct_start(monkeypatch)
    wt.launch(LANE_OPEN)
    assert second_installed[0][0] == LANE_OPEN


def test_a_terminal_window_whose_program_cannot_be_read_goes_to_the_second_copy(monkeypatch):
    monkeypatch.setattr(wt, "image_of", lambda handle: "")
    assert wt.terminal_for(wt.Front(500, "x", terminal=True), second=SECOND) == SECOND


def test_a_join_is_never_detached(monkeypatch, quiet_front, second_installed):
    """The named window lives in one copy of Terminal; only it can take the tab."""
    calls = []
    monkeypatch.setattr(wt.subprocess, "run", lambda command, **kw: calls.append(command))
    wt.launch(JOIN_OPEN)
    assert calls == [JOIN_OPEN] and second_installed == []


def test_only_dash_w_new_is_a_new_window():
    assert wt.is_new_window(LANE_OPEN)
    assert not wt.is_new_window(JOIN_OPEN)
    assert not wt.is_new_window(["wt.exe", "x"])


@pytest.fixture
def detached(monkeypatch, tmp_path):
    """`_start_detached` with no real WMI: `started` is what it ran, and
    `answer` is what the windowless launcher reports."""
    (tmp_path / "pythonw.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr(wt.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(wt.tempfile, "tempdir", str(tmp_path))
    state = {"started": [], "payload": None, "answer": "0", "exit": 0}

    def fake_run(command, capture_output, check):
        state["started"].append(command)
        payload = next(tmp_path.glob("wt-open-*.json"))
        state["payload"] = json.loads(payload.read_text(encoding="utf-8"))
        if state["answer"] is not None:
            Path(str(payload) + ".rc").write_text(state["answer"], encoding="utf-8")
        return subprocess.CompletedProcess(command, state["exit"])

    monkeypatch.setattr(wt.subprocess, "run", fake_run)
    state["tmp"] = tmp_path
    return state


def _left_behind(state):
    return sorted(p.name for p in state["tmp"].iterdir() if p.name != "pythonw.exe")


def test_the_detached_start_goes_through_wmi_to_the_windowless_launcher(detached):
    wt._start_detached(LANE_OPEN, {"PATH": "p"})
    command = detached["started"][0]
    assert command[:3] == ["powershell.exe", "-NoProfile", "-EncodedCommand"]
    script = base64.b64decode(command[3]).decode("utf-16-le")
    assert "Win32_Process -MethodName Create" in script
    assert "pythonw.exe" in script and wt.BRIDGE_FLAG in script and "wt.py" in script
    assert detached["payload"] == {"command": LANE_OPEN, "env": {"PATH": "p"},
                                   "show": wt.SW_SHOWNOACTIVATE}
    assert _left_behind(detached) == [], "the environment stayed on disk"


def test_a_window_that_did_not_open_is_a_refusal_and_leaves_nothing(detached):
    detached["answer"] = "1"
    with pytest.raises(TerminalError):
        wt._start_detached(LANE_OPEN, {})
    assert _left_behind(detached) == []


def test_wmi_refusing_the_launcher_is_a_refusal(detached):
    detached["exit"], detached["answer"] = 8, None
    with pytest.raises(TerminalError, match="8"):
        wt._start_detached(LANE_OPEN, {})
    assert _left_behind(detached) == []


def test_a_launcher_that_never_reports_is_a_refusal(detached, monkeypatch):
    detached["answer"] = None
    monkeypatch.setattr(wt, "BRIDGE_WAIT", -1.0)
    with pytest.raises(TerminalError, match="report back"):
        wt._start_detached(LANE_OPEN, {})
    assert _left_behind(detached) == []


def test_no_windowless_python_is_a_refusal(monkeypatch, tmp_path):
    monkeypatch.setattr(wt.sys, "executable", str(tmp_path / "python.exe"))
    with pytest.raises(TerminalError, match="pythonw"):
        wt._start_detached(LANE_OPEN, {})


@needs_powershell
def test_the_real_launcher_reports_the_exit_code(tmp_path):
    payload = tmp_path / "open.json"
    payload.write_text(json.dumps({"command": [sys.executable, "-c", "raise SystemExit(3)"],
                                   "env": dict(os.environ), "show": wt.SW_SHOWNOACTIVATE}),
                       encoding="utf-8")
    wt.run_bridge(str(payload))
    assert Path(str(payload) + ".rc").read_text(encoding="utf-8") == "3"


@needs_powershell
def test_the_real_launcher_reports_why_it_could_not_start(tmp_path):
    payload = tmp_path / "open.json"
    payload.write_text(json.dumps({"command": ["kit-no-such-program-xyz"], "env": dict(os.environ),
                                   "show": wt.SW_SHOWNOACTIVATE}), encoding="utf-8")
    wt.run_bridge(str(payload))
    assert "FileNotFoundError" in Path(str(payload) + ".rc").read_text(encoding="utf-8")


@needs_powershell
def test_the_program_behind_the_front_window_can_be_read():
    front = wt.front_window()
    if front.handle is None:
        pytest.skip("nothing in front to ask about")
    assert isinstance(wt.image_of(front.handle), str)
    assert wt.image_of(None) == ""


class _Download:
    def __init__(self, blob):
        self.blob = blob

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.blob


def _portable_zip():
    home = f"terminal-{wt.SECOND_TERMINAL_VERSION}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{home}/wt.exe", "stub")
    return buffer.getvalue()


def test_the_install_refuses_a_download_with_the_wrong_hash(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(wt.urllib.request, "urlopen", lambda url, timeout: _Download(b"not it"))
    with pytest.raises(TerminalError, match="nothing was installed"):
        wt.install_second_terminal()
    assert wt.second_terminal() is None and list(tmp_path.iterdir()) == []


def test_the_install_unpacks_marks_portable_and_carries_the_settings(monkeypatch, tmp_path):
    blob = _portable_zip()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(wt, "SECOND_TERMINAL_SHA256", hashlib.sha256(blob).hexdigest())
    monkeypatch.setattr(wt.urllib.request, "urlopen", lambda url, timeout: _Download(blob))
    settings = tmp_path / wt.INSTALLED_SETTINGS
    settings.parent.mkdir(parents=True)
    settings.write_text('{"theme": "the owner\'s"}', encoding="utf-8")
    home = wt.install_second_terminal()
    assert wt.second_terminal() == str(home / "wt.exe")
    assert (home / ".portable").is_file()
    assert (home / "settings" / "settings.json").read_text(encoding="utf-8") == settings.read_text(encoding="utf-8")


def test_the_install_does_nothing_when_it_is_already_there(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    home = wt.second_terminal_home()
    home.mkdir(parents=True)
    (home / "wt.exe").write_text("stub", encoding="utf-8")

    def refuse(*args, **kwargs):
        raise AssertionError("downloaded over an installed copy")

    monkeypatch.setattr(wt.urllib.request, "urlopen", refuse)
    assert wt.install_second_terminal() == home


def test_no_local_app_data_means_no_second_copy(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert wt.second_terminal_home() is None and wt.second_terminal() is None
    with pytest.raises(TerminalError):
        wt.install_second_terminal()


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
    tab_title="lane-alpha", tab_color="#4169E1",
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
