"""Tests for scripts/open_terminal.py -- the window opener.

FACOWORK's reconciliation build, slice 1. No test here opens a window, ends a process or
asks the CLI what is live: `launch`, the kill and `live_sessions` are all
stood in for, and the record and the close markers live under tmp_path.

Kit-owned, like the script: nothing here names the project or pins a
project's own reason tokens. Only the two tokens every project carries are
pinned (`prescribed` on Sonnet, `design-latitude` on Opus); a test that needs
a Sonnet job and an Opus job uses those two, and the rest are parametrized
over whatever `scripts/reason_tokens.json` holds.
"""
import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import desk_record as dr
import open_terminal as ot
import project_identity as pi
import wt
from wt import TerminalError

REPO = Path(__file__).resolve().parents[1]

#: Another project's folder, for "live, but not in this workspace".
ELSEWHERE = str(REPO.parent / "Some_Other_Project")

#: A job every project's file opens on Sonnet, and one it opens on Opus.
SONNET_JOB = "prescribed"
OPUS_JOB = "design-latitude"


def session(name, cwd=None, status="idle", pid=4242):
    return {"name": name, "pid": pid, "sessionId": "s-" + name,
            "cwd": str(REPO if cwd is None else cwd), "status": status}


@pytest.fixture
def room(tmp_path, monkeypatch):
    """A workspace with nothing live, nothing recorded, and no real terminal."""
    state = {"live": [], "launched": [], "killed": [], "kill_code": 0}
    monkeypatch.setattr(ot, "RECORD", tmp_path / "coordination" / "launch_record.jsonl")
    monkeypatch.setattr(ot, "CLOSE_MARKERS", tmp_path)
    monkeypatch.setattr(ot, "session_cwd", lambda: str(REPO))
    monkeypatch.setattr(ot, "live_sessions", lambda: list(state["live"]))
    monkeypatch.setattr(ot, "own_ancestry", lambda: set())
    monkeypatch.setattr(ot, "launch", lambda command: state["launched"].append(command))
    # A Windows Terminal machine unless a test says otherwise, so the open's
    # output does not depend on which machine runs the suite.
    monkeypatch.setattr(ot, "launch_mode", lambda: ot.OPENED_BY_WT)
    # The desk record lives under tmp_path too, and is EMPTY: the stamped-sheet
    # refusal has its own tests below, which put it back.
    state["require_sheet"] = ot.require_a_stamped_sheet
    monkeypatch.setattr(ot, "require_a_stamped_sheet", lambda *a: None)
    for attr, where in (("RECORD", "desk_record.json"), ("DONE_DIR", "done"),
                        ("DESK_LOG", "desk_log.md"), ("CLOSED_DIR", "closed")):
        monkeypatch.setattr(dr, attr, tmp_path / "coordination" / where)

    def fake_run(command, **kwargs):
        assert command == ot.kill_command(command[2]), (
            "only the kill may reach subprocess here")
        state["killed"].append(command)
        state["markers_at_kill"] = sorted(p.name for p in tmp_path.glob("*.closing"))
        if state["kill_code"] == 0:
            state["live"] = [r for r in state["live"] if str(r["pid"]) != command[2]]

        class Done:
            returncode = state["kill_code"]
            stdout = b""
            stderr = b"ERROR: a child refused"
        return Done()

    monkeypatch.setattr(ot.subprocess, "run", fake_run)
    return state


def record():
    return ot.read_record()


LANE = ["--role", "lane", "--name", "lane-alpha", "--task", "coordination/task_sheets/lane-alpha.md"]


# --- the job decides the model (R16) ----------------------------------------


def test_the_two_universal_rows_are_in_every_projects_list():
    """FACOWORK's two build rows travel unchanged; every other row is the
    project's own ruling, in its own `scripts/reason_tokens.json`."""
    assert ot.UNIVERSAL_REASONS == {"prescribed": "sonnet", "design-latitude": "opus"}
    for token, model in ot.UNIVERSAL_REASONS.items():
        assert ot.REASONS[token][0] == model
    assert ot.CATCH_ALL_REASON == "design-latitude"
    assert ot.REASONS[ot.CATCH_ALL_REASON][0] == "opus", (
        "the job that fits nothing must be the expensive one")


def test_no_reason_opens_haiku_or_fable():
    models = {model for model, _ in ot.REASONS.values()}
    assert models <= set(ot.ALLOWED_MODELS) == {"opus", "sonnet"}
    assert "haiku" not in models and ot.GATED_MODEL not in models


def test_the_projects_file_loads_and_is_what_the_launcher_uses():
    table = ot.load_reasons()
    assert (ot.REASONS, ot.SOURCE_REASONS) == ot.reason_tables(table)
    assert set(ot.SOURCE_REASONS) <= set(ot.REASONS)
    assert not set(ot.NOT_REASONS) & set(ot.REASONS)


@pytest.mark.parametrize("token", sorted(ot.REASON_TABLE))
def test_every_row_of_the_file_keeps_its_contract(token):
    row = ot.REASON_TABLE[token]
    assert ot._TOKEN.match(token), "%r is not one lower-case word" % token
    assert row.model in ("sonnet", "opus")
    assert row.job.strip() and "\n" not in row.job
    assert isinstance(row.reads_source, bool)


# --- the tokens file is refused loudly when it is wrong ------------------------


GOOD = {
    "prescribed": {"model": "sonnet", "job": "a named change", "reads_source": False},
    "design-latitude": {"model": "opus", "job": "anything else", "reads_source": False},
}


def tokens_file(tmp_path, tokens=None, **top):
    path = tmp_path / "reason_tokens.json"
    body = {"tokens": GOOD if tokens is None else tokens, **top}
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_a_file_with_only_the_two_universal_rows_loads(tmp_path):
    table = ot.load_reasons(tokens_file(tmp_path, about="a note"))
    assert list(table) == ["prescribed", "design-latitude"]
    assert table["prescribed"] == ot.Reason("sonnet", "a named change", False)


def with_row(token, **row):
    return {**GOOD, token: {"model": "opus", "job": "a job", "reads_source": True, **row}}


@pytest.mark.parametrize("tokens, said", [
    ({"prescribed": GOOD["prescribed"]}, "'design-latitude' is missing"),
    ({"design-latitude": GOOD["design-latitude"]}, "'prescribed' is missing"),
    ({**GOOD, "prescribed": {**GOOD["prescribed"], "model": "opus"}},
     "'prescribed' opens on opus"),
    ({**GOOD, "design-latitude": {**GOOD["design-latitude"], "model": "sonnet"}},
     "'design-latitude' opens on sonnet"),
    (with_row("cheap", model="haiku"), "names model 'haiku'"),
    (with_row("grand", model="fable"), "names model 'fable'"),
    (with_row("owners-call"), "cannot be a reason"),
    (with_row("not-a-decision"), "cannot be a reason"),
    (with_row("Two Words"), "is not a token"),
    (with_row("vague", job="  "), "no one-line `job`"),
    (with_row("vague", job="two\nlines"), "no one-line `job`"),
    (with_row("maybe", reads_source="yes"), "`reads_source` 'yes'"),
    ({**GOOD, "short": {"model": "opus", "job": "x"}}, "must have exactly"),
    ({**GOOD, "typo": {"model": "opus", "job": "x", "reads-source": True}}, "must have exactly"),
    ({**GOOD, "flat": "opus"}, "must have exactly"),
])
def test_a_file_that_breaks_a_rule_is_refused_and_says_which(tmp_path, tokens, said):
    with pytest.raises(ot.ReasonTokensError) as refusal:
        ot.load_reasons(tokens_file(tmp_path, tokens))
    assert said in str(refusal.value)
    assert "No lane opens until it is fixed" in str(refusal.value)


@pytest.mark.parametrize("text, said", [
    (None, "cannot be read"),
    ("{not json", "is not JSON"),
    ("[]", "has no `tokens` object"),
    ('{"reasons": {}}', "has no `tokens` object"),
    ('{"tokens": {}, "extra": 1}', "beside `tokens`"),
])
def test_a_missing_or_malformed_file_is_refused(tmp_path, text, said):
    path = tmp_path / "reason_tokens.json"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    with pytest.raises(ot.ReasonTokensError, match=said):
        ot.load_reasons(path)


def test_the_launcher_refuses_to_run_on_a_bad_file_with_exit_2(tmp_path):
    """Run as a program, a bad tokens file is one FAIL line and exit 2 -- not a
    traceback, and never a lane opened on a guess."""
    scripts = tmp_path / "Boat Log" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("open_terminal.py", "wt.py", "project_identity.py"):
        shutil.copyfile(REPO / "scripts" / name, scripts / name)
    (scripts / "reason_tokens.json").write_text(
        json.dumps({"tokens": {"prescribed": GOOD["prescribed"]}}), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(scripts / "open_terminal.py"), "--reasons"],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode == 2, proc.stderr
    assert proc.stderr.startswith("FAIL - scripts/reason_tokens.json: ")
    assert "'design-latitude' is missing" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_reasons_prints_the_whole_table(room, capsys):
    assert ot.main(["--reasons"]) == 0
    out = capsys.readouterr().out
    for token, (model, job) in ot.REASONS.items():
        assert token in out and job in out
    assert "scripts/reason_tokens.json" in out and "the owner's ruling" in out
    assert room["launched"] == [] and not ot.RECORD.exists()


@pytest.mark.parametrize("reason", sorted(ot.REASONS))
def test_the_reason_decides_the_model_and_nothing_else_does(reason):
    tier = ot.tier_choice("lane", None, reason)
    assert (tier.model, tier.reason) == (ot.REASONS[reason][0], reason)
    assert tier.why == ot.REASONS[reason][1]


def test_a_lane_that_names_no_reason_is_refused_and_told_the_whole_list():
    with pytest.raises(TerminalError) as refusal:
        ot.tier_choice("lane", None, None)
    said = str(refusal.value)
    for token in ot.REASONS:
        assert token in said, "the refusal hides the reason %r" % token
    assert "'design-latitude', on opus" in said, (
        "the refusal never says where a job that fits nothing goes")


def test_a_reason_nobody_ruled_on_is_refused_and_no_flag_gets_past_it():
    with pytest.raises(TerminalError) as refusal:
        ot.tier_choice("lane", None, "cheap-and-cheerful")
    assert "design-latitude" in str(refusal.value)
    actions = {a: action for action in ot.build_parser()._actions
               for a in action.option_strings}
    assert not [f for f in actions if "reason" in f and f not in ("--reason", "--reasons")], (
        "an escape flag past the reason list has appeared")
    # `--reasons` prints the list and takes nothing: it cannot name a job.
    assert actions["--reasons"].nargs == 0


def test_a_cheap_model_beside_an_expensive_reason_is_refused_both_ways():
    with pytest.raises(TerminalError):
        ot.tier_choice("lane", "sonnet", OPUS_JOB)
    with pytest.raises(TerminalError):
        ot.tier_choice("lane", "opus", SONNET_JOB)
    assert ot.tier_choice("lane", "opus", OPUS_JOB).model == "opus"


@pytest.mark.parametrize("reason", sorted(ot.REASONS))
def test_every_token_refuses_the_other_model(reason):
    model = ot.REASONS[reason][0]
    other = "sonnet" if model == "opus" else "opus"
    with pytest.raises(TerminalError):
        ot.tier_choice("lane", other, reason)


def test_fable_is_refused_without_the_owners_own_flag():
    with pytest.raises(TerminalError) as refusal:
        ot.chosen_model("lane", "fable", fable_approved=False)
    assert ot.FABLE_FLAG in str(refusal.value)


def test_fable_on_a_lane_is_the_owners_call_and_outside_the_list():
    model = ot.chosen_model("lane", "fable", fable_approved=True)
    assert ot.tier_choice("lane", model, None).reason == "owners-call"
    assert "owners-call" not in ot.REASONS and "owners-call" in ot.NOT_REASONS


@pytest.mark.parametrize("model", ["haiku", "gpt", "claude-fable-5-1"])
def test_a_model_outside_the_list_is_refused(model):
    with pytest.raises(TerminalError):
        ot.chosen_model("lane", model, fable_approved=True)


def test_a_desk_is_on_fable_and_so_needs_the_owners_flag():
    with pytest.raises(TerminalError) as refusal:
        ot.chosen_model("desk", None, fable_approved=False)
    assert "/desk" in str(refusal.value), "the refusal does not name the usual way"
    model = ot.chosen_model("desk", None, fable_approved=True)
    assert ot.tier_choice("desk", model, None) == ot.Tier(
        "fable", "not-a-decision", ot.DESK_WHY)


def test_a_desk_takes_no_reason_and_no_other_model():
    with pytest.raises(TerminalError):
        ot.tier_choice("desk", "fable", OPUS_JOB)
    with pytest.raises(TerminalError):
        ot.tier_choice("desk", "opus", None)


# --- the window -------------------------------------------------------------


def test_the_first_instruction_is_the_role_command():
    assert ot.role_prompt("desk", "desk", None) == "/desk"
    assert ot.role_prompt("lane", "lane-alpha", " sheets/lane-alpha.md ") == (
        "/lane lane-alpha sheets/lane-alpha.md")


@pytest.mark.parametrize("task", [None, "", "   "])
def test_a_lane_with_nothing_to_do_is_refused(task):
    with pytest.raises(TerminalError):
        ot.role_prompt("lane", "x", task)


def test_a_desk_is_not_given_a_task():
    with pytest.raises(TerminalError):
        ot.role_prompt("desk", "desk", "do this")


@pytest.mark.parametrize("bad", ["two words", "../up", "a/b", "-dash", "", "semi;colon"])
def test_a_name_that_is_not_one_plain_word_is_refused(bad):
    with pytest.raises(TerminalError):
        ot.checked_name(bad)


def test_the_window_is_a_named_coloured_tab_with_the_model_written_out(room):
    window = ot.window_for("lane", "lane-alpha", "sheet.md", "opus", resume=False)
    assert window.argv == (
        "claude", "--model", "opus", "--permission-mode", "acceptEdits",
        "--remote-control", "lane-alpha",
        "--name", "lane-alpha", "/lane lane-alpha sheet.md")
    assert window.window_target == ot.SHARED_WINDOW
    assert window.tab_title == "lane-alpha"
    assert window.keep_open is False
    assert window.close_marker.endswith(pi.CLOSE_MARKER_PREFIX + "lane-alpha.closing")


def test_a_resumed_window_carries_no_role_prompt(room):
    window = ot.window_for("lane", "lane-alpha", None, "opus", resume=True)
    assert window.argv[-2:] == ("--resume", "lane-alpha")


def test_the_colour_says_the_model(room):
    """What the slice 3 rehearsal reads off the tab bar."""
    assert ot.tab_color("desk", "fable") == "#DC143C"
    assert ot.tab_color("lane", "opus") != ot.tab_color("lane", "sonnet")
    colours = [ot.DESK_TAB_COLOR, *ot.LANE_TAB_COLORS.values()]
    assert len(set(colours)) == len(colours), "two kinds of window share a colour"
    assert set(ot.LANE_TAB_COLORS) == {*ot.ALLOWED_MODELS, ot.GATED_MODEL}


# --- the open, end to end ---------------------------------------------------


def test_a_dry_run_names_opus_and_sonnet_for_the_two_universal_jobs(room, capsys):
    """The build plan's Done-means line for this slice."""
    assert ot.main([*LANE, "--reason", OPUS_JOB, "--dry-run"]) == 0
    opus = capsys.readouterr().out
    assert f"model: opus - {OPUS_JOB}" in opus and "(lane, opus)" in opus
    assert ot.main([*LANE, "--reason", SONNET_JOB, "--dry-run"]) == 0
    sonnet = capsys.readouterr().out
    assert f"model: sonnet - {SONNET_JOB}" in sonnet and "(lane, sonnet)" in sonnet


@pytest.mark.parametrize("reason", sorted(ot.REASONS))
def test_a_dry_run_names_each_tokens_model_and_reason(room, capsys, reason):
    model = ot.REASONS[reason][0]
    assert ot.main([*LANE, "--reason", reason, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"model: {model} - {reason}" in out and f"(lane, {model})" in out
    # The printed command line carries the window's argv as an encoded blob, so
    # the model on it is read from the window the same open builds.
    tier = ot.tier_choice("lane", None, reason)
    argv = ot.window_for("lane", "lane-alpha", LANE[-1], tier.model, resume=False).argv
    assert argv[argv.index("--model") + 1] == model
    assert room["launched"] == [] and not ot.RECORD.exists()


def test_a_dry_run_opens_nothing_and_records_nothing(room, capsys):
    assert ot.main([*LANE, "--reason", OPUS_JOB, "--dry-run"]) == 0
    assert room["launched"] == []
    assert not ot.RECORD.exists()
    assert f"wt.exe -w {pi.SHARED_WINDOW} new-tab" in capsys.readouterr().out


def test_a_dry_run_refuses_exactly_what_a_real_open_refuses(room, capsys):
    for extra in ([], ["--dry-run"]):
        assert ot.main([*LANE, *extra]) == 2
        assert "needs --reason" in capsys.readouterr().err
    assert room["launched"] == []


def test_an_open_launches_and_writes_the_record(room):
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    assert len(room["launched"]) == 1
    (entry,) = record()
    assert {k: entry[k] for k in ("event", "name", "role", "reason", "model", "task")} == {
        "event": "open", "name": "lane-alpha", "role": "lane", "reason": OPUS_JOB,
        "model": "opus", "task": "coordination/task_sheets/lane-alpha.md"}
    assert entry["at"], "the record does not say when"


def test_a_launch_that_failed_is_not_recorded(room, monkeypatch, capsys):
    def boom(command):
        raise TerminalError("wt.exe is not on PATH")
    monkeypatch.setattr(ot, "launch", boom)
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 2
    assert record() == []
    assert "/lane lane-alpha" in capsys.readouterr().out, (
        "the manual path is not left on screen")


def test_a_stale_marker_is_cleared_when_a_window_of_that_name_opens(room):
    marker = ot.close_marker_path("lane-alpha")
    marker.write_text("left by a window whose shell never read it\n", encoding="utf-8")
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    assert not marker.exists()


def test_a_name_already_live_here_is_refused_but_not_one_live_elsewhere(room, capsys):
    room["live"] = [session("lane-alpha", cwd=ELSEWHERE)]
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    room["live"] = [session("lane-alpha")]
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 2
    assert "already answers to" in capsys.readouterr().err


def test_the_cap_counts_only_lanes_this_opened_in_this_workspace(room, capsys):
    """R23's cap of 15 -- and the session list is account-wide, so a hundred
    other projects' windows and the owner's own must not count."""
    for n in range(ot.MAX_OPEN_LANES - 1):
        ot.append_record({"event": "open", "name": "lane%d" % n, "role": "lane"})
    room["live"] = (
        [session("lane%d" % n, pid=n) for n in range(ot.MAX_OPEN_LANES - 1)]
        + [session("owners-own"), session("desk")]
        + [session("other%d" % n, cwd=ELSEWHERE)
           for n in range(100)])
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    room["live"].append(session("lane-alpha"))
    late = ["--role", "lane", "--name", "one-more", "--task", "x", "--reason", SONNET_JOB]
    assert ot.main(late) == 2
    assert "the cap is 15" in capsys.readouterr().err
    # A closed lane frees its place even while the list still shows it.
    ot.append_record({"event": "close", "name": "lane0"})
    assert ot.main(late) == 0


# --- --list -----------------------------------------------------------------


def test_the_list_shows_reason_and_model_and_marks_what_it_did_not_open(room, capsys):
    ot.append_record({"at": "2026-09-19T10:00:00-06:00", "event": "open",
                      "name": "lane-alpha", "role": "lane", "reason": OPUS_JOB,
                      "model": "opus"})
    room["live"] = [session("lane-alpha", status="busy"), session("owners-own"),
                    session("other-seat", cwd=ELSEWHERE)]
    assert ot.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert f"lane, opus - {OPUS_JOB}" in out
    assert "owners-own" in out and "not opened by this launcher" in out
    assert "other-seat" not in out, "another project's window was listed as ours"


# --- --close ----------------------------------------------------------------


def opened(room, name="lane-alpha", **kwargs):
    ot.append_record({"event": "open", "name": name, "role": "lane",
                      "reason": OPUS_JOB, "model": "opus"})
    room["live"] = [session(name, **kwargs)]


def test_it_ends_only_windows_it_opened(room, capsys):
    room["live"] = [session("owners-own")]
    assert ot.main(["--close", "--name", "owners-own"]) == 2
    assert "no record of opening" in capsys.readouterr().err
    assert room["killed"] == []


def test_a_name_live_only_in_another_project_is_refused(room, capsys):
    opened(room, cwd=ELSEWHERE)
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert "not this workspace" in capsys.readouterr().err
    assert room["killed"] == []


def test_closing_a_window_that_is_already_gone_says_so_with_its_own_code(room):
    opened(room)
    room["live"] = []
    assert ot.main(["--close", "--name", "lane-alpha"]) == ot.CLOSED_NOTHING


def test_the_session_running_the_command_cannot_end_itself(room, monkeypatch, capsys):
    opened(room, pid=777)
    monkeypatch.setattr(ot, "own_ancestry", lambda: {777, 1})
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert room["killed"] == []


def test_the_marker_is_planted_before_the_kill_and_the_close_is_recorded(room):
    opened(room)
    assert ot.main(["--close", "--name", "lane-alpha"]) == 0
    assert room["killed"] == [ot.kill_command(4242)]
    assert room["markers_at_kill"] == [pi.CLOSE_MARKER_PREFIX + "lane-alpha.closing"]
    assert record()[-1]["event"] == "close"


def test_a_close_dry_run_names_the_process_and_touches_nothing(room, capsys):
    opened(room)
    assert ot.main(["--close", "--name", "lane-alpha", "--dry-run"]) == 0
    assert "pid 4242" in capsys.readouterr().out
    assert room["killed"] == [] and not list(ot.CLOSE_MARKERS.glob("*.closing"))
    assert record()[-1]["event"] == "open"


def test_a_failed_kill_takes_its_marker_back(room, capsys):
    opened(room)
    room["kill_code"] = 1
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert not ot.close_marker_path("lane-alpha").exists(), (
        "a marker left behind would close that pane over its next error")
    assert record()[-1]["event"] == "open"


def test_a_kill_that_landed_but_reported_a_child_is_still_a_close(room, monkeypatch):
    """`taskkill /T` exits non-zero when any child refuses, even though the
    session named is gone. The end state is what is read."""
    opened(room)
    room["kill_code"] = 1
    calls = {"n": 0}

    def live():
        calls["n"] += 1
        return [session("lane-alpha")] if calls["n"] == 1 else []
    monkeypatch.setattr(ot, "live_sessions", live)
    assert ot.main(["--close", "--name", "lane-alpha"]) == 0
    assert ot.close_marker_path("lane-alpha").exists()


def test_a_record_line_that_is_not_json_is_refused_not_skipped(room):
    ot.RECORD.parent.mkdir(parents=True)
    ot.RECORD.write_text('{"event": "open", "name": "a"}\nnot json\n', encoding="utf-8")
    with pytest.raises(TerminalError):
        ot.read_record()


# --- the lines somebody actually runs ---------------------------------------


def launch_lines():
    """Every written line, in a live skill or command file, that opens a lane."""
    roots = [REPO / "skills", REPO / ".claude" / "commands"]
    for root in roots:
        for path in sorted(root.rglob("*.md")):
            if {"archive", "retired"} & set(path.relative_to(REPO).parts):
                continue
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if "open_terminal.py" in line and "--role lane" in line:
                    yield "%s:%d" % (path.relative_to(REPO).as_posix(), number), line


def test_every_written_launch_line_names_its_reason():
    """A refusal fires on the line somebody actually runs, and those lines are
    the ones written in the skills. One that leaves out the reason is an open
    the launcher refuses, taught by the file that teaches the command."""
    for where, line in launch_lines():
        assert "--reason" in line, "%s opens a lane with no --reason: %s" % (
            where, line.strip())
        token = line.split("--reason", 1)[1].split()[0].strip("`\"'")
        assert token in ot.REASONS or token.startswith("<"), (
            "%s names a reason the launcher refuses: %s" % (where, token))


def test_the_scan_finds_a_launch_line_when_there_is_one(tmp_path, monkeypatch):
    """A scan that matched nothing would pass in silence."""
    (tmp_path / "skills" / "desk").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / "skills" / "desk" / "SKILL.md").write_text(
        "<venv python> scripts/open_terminal.py --role lane --name x "
        "--task y\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO", tmp_path)
    assert len(list(launch_lines())) == 1
    with pytest.raises(AssertionError):
        test_every_written_launch_line_names_its_reason()


def test_every_documented_open_is_one_the_launcher_accepts(room, capsys):
    """The Usage block is what anybody copies."""
    usage = ot.__doc__.split("Usage", 1)[1].split("WHY THIS EXISTS", 1)[0]
    lines = [l.strip() for l in usage.splitlines() if "--role" in l]
    assert len(lines) >= 3, "the Usage block documents no opens"
    for line in lines:
        argv = shlex.split(line)[3:]
        if "--dry-run" not in argv:
            argv.append("--dry-run")
        assert ot.main(argv) == 0, "documented open is refused: %s\n%s" % (
            line, capsys.readouterr().err)


def test_the_documented_interpreter_is_the_projects_own():
    usage = ot.__doc__.split("Usage", 1)[1].split("WHY THIS EXISTS", 1)[0]
    for line in usage.splitlines():
        if "open_terminal.py" in line:
            assert line.strip().startswith("<venv python> scripts/"), (
                "a Usage line names one machine's interpreter: " + line)


def test_the_record_is_valid_json_lines(room):
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    for line in ot.RECORD.read_text(encoding="utf-8").splitlines():
        json.loads(line)


# --- slice 2: a lane opens on a stamped sheet, and closes only when done ------


SHEET = """# Task sheet
unit: the first quarter
reason: design-latitude
owns:
- records/2025/January
reads:
- sources
task: compare the unit against the statement and draft the fixes
done: `python scripts/verify_figures.py` passes on the report
"""


@pytest.fixture
def desk(room, tmp_path, monkeypatch):
    """A desk record with one stamped lane, its sheet on disk under tmp_path."""
    monkeypatch.setattr(ot, "require_a_stamped_sheet", room["require_sheet"])
    monkeypatch.setattr(dr, "REPO", tmp_path)
    (tmp_path / "sources").mkdir()
    (tmp_path / "sheets").mkdir()
    (tmp_path / "sheets" / "lane-alpha.md").write_text(SHEET, encoding="utf-8")
    monkeypatch.setattr(dr, "take_baseline", lambda repo=None: {})
    dr.open_desk("the-desk", "a test job", inherit=False)
    dr.stamp("the-desk", "lane-alpha", "sheets/lane-alpha.md")
    return room


STAMPED = ["--role", "lane", "--name", "lane-alpha", "--task", "sheets/lane-alpha.md"]


def test_a_lane_with_no_stamped_sheet_does_not_open(room, monkeypatch, capsys):
    monkeypatch.setattr(ot, "require_a_stamped_sheet", room["require_sheet"])
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 2
    assert "desk_record.py stamp lane-alpha" in capsys.readouterr().err
    assert room["launched"] == []


def test_a_stamped_lane_opens(desk):
    assert ot.main([*STAMPED, "--reason", OPUS_JOB]) == 0
    assert len(desk["launched"]) == 1


def test_a_sheet_edited_after_its_stamp_does_not_open(desk, tmp_path, capsys):
    (tmp_path / "sheets" / "lane-alpha.md").write_text(SHEET + "also do this", encoding="utf-8")
    assert ot.main([*STAMPED, "--reason", OPUS_JOB]) == 2
    assert "changed since the desk stamped it" in capsys.readouterr().err


def test_the_open_and_the_sheet_must_name_the_same_job(desk, capsys):
    assert ot.main([*STAMPED, "--reason", SONNET_JOB]) == 2
    assert f"reason: {OPUS_JOB}" in capsys.readouterr().err


def test_a_lane_that_has_not_reported_done_is_not_closed(desk, capsys):
    opened(desk)
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert "report-done lane-alpha" in capsys.readouterr().err
    assert desk["killed"] == []


def test_a_lane_that_reported_done_closes_and_keeps_its_row(desk):
    opened(desk)
    dr.report_done("lane-alpha")
    assert ot.main(["--close", "--name", "lane-alpha"]) == 0
    row = dr.read_record()["lanes"]["lane-alpha"]
    assert row["closed"] and row["owns"] == ["records/2025/January"]


def test_a_done_lane_that_is_mid_turn_is_not_closed(desk, capsys):
    opened(desk, status="busy")
    dr.report_done("lane-alpha")
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert "mid-turn" in capsys.readouterr().err
    assert desk["killed"] == []


def test_the_mid_turn_refusal_names_the_wait(desk, capsys):
    opened(desk, status="busy")
    dr.report_done("lane-alpha")
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert "--close --wait --name lane-alpha" in capsys.readouterr().err


# --- --close --wait: a lane that sent done: is still finishing its turn --------


@pytest.fixture
def waiting(desk, monkeypatch):
    """A stamped lane that has reported done, a fake clock, and a live list
    that reads the statuses in `desk["statuses"]` one call at a time (the
    last one sticks). A status of None means the session has ended."""
    desk["statuses"] = []
    desk["sleeps"] = []
    clock = {"t": 0.0}
    opened(desk)
    dr.report_done("lane-alpha")

    def live():
        status = (desk["statuses"].pop(0) if len(desk["statuses"]) > 1
                  else desk["statuses"][0])
        return [] if status is None else [session("lane-alpha", status=status)]

    def fake_sleep(seconds):
        desk["sleeps"].append(seconds)
        clock["t"] += seconds

    monkeypatch.setattr(ot, "live_sessions", live)
    monkeypatch.setattr(ot, "sleep", fake_sleep)
    monkeypatch.setattr(ot, "monotonic", lambda: clock["t"])
    return desk


def test_close_wait_closes_a_done_lane_once_its_turn_ends(waiting, capsys):
    """S3: the desk tried eleven times to close a lane that had sent done: and
    was still finishing its turn. One `--close --wait` does it."""
    waiting["statuses"] = ["busy", "busy", "busy", "idle"]
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == 0
    assert waiting["killed"] == [ot.kill_command(4242)]
    assert waiting["sleeps"] == [ot.WAIT_POLL_SECONDS] * 3
    assert "waiting up to 600s" in capsys.readouterr().out
    assert dr.read_record()["lanes"]["lane-alpha"]["closed"]


def test_close_wait_on_an_idle_lane_does_not_wait(waiting):
    waiting["statuses"] = ["idle"]
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == 0
    assert waiting["sleeps"] == [] and len(waiting["killed"]) == 1


def test_close_wait_refuses_plainly_at_the_timeout(waiting, capsys):
    waiting["statuses"] = ["busy"]
    assert ot.main(["--close", "--wait", "--timeout", "12", "--name", "lane-alpha"]) == 2
    assert "still BUSY after 12s of --wait; nothing was closed" in capsys.readouterr().err
    assert waiting["sleeps"] == [5, 5, 2]
    assert waiting["killed"] == [] and not list(ot.CLOSE_MARKERS.glob("*.closing"))
    assert record()[-1]["event"] == "open"


def test_close_wait_defaults_to_ten_minutes(waiting):
    waiting["statuses"] = ["busy"]
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == 2
    assert sum(waiting["sleeps"]) == ot.WAIT_TIMEOUT_SECONDS == 600


def test_close_wait_refuses_at_once_a_lane_stopped_for_the_owner(waiting, capsys):
    waiting["statuses"] = ["busy", "waiting"]
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == 2
    assert "WAITING" in capsys.readouterr().err
    assert waiting["sleeps"] == [5] and waiting["killed"] == []


def test_close_wait_still_refuses_a_lane_that_has_not_reported_done(waiting, capsys):
    """The wait replaces nothing: after it, the close checks what it always does."""
    dr.route("the-desk", ["records/2025/January"], "the January deposit was a refund", None)
    waiting["statuses"] = ["busy", "idle"]
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == 2
    assert "report-done lane-alpha" in capsys.readouterr().err
    assert waiting["killed"] == []


def test_close_wait_on_a_session_that_ended_meanwhile_closes_nothing(waiting):
    waiting["statuses"] = ["busy", None]
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == ot.CLOSED_NOTHING
    assert waiting["killed"] == []


def test_close_wait_refuses_when_another_process_takes_the_name(waiting, monkeypatch, capsys):
    calls = {"n": 0}

    def live():
        calls["n"] += 1
        return [session("lane-alpha", status="busy", pid=4242 if calls["n"] == 1 else 999)]
    monkeypatch.setattr(ot, "live_sessions", live)
    assert ot.main(["--close", "--wait", "--name", "lane-alpha"]) == 2
    assert "changed" in capsys.readouterr().err and waiting["killed"] == []


@pytest.mark.parametrize("argv, said", [
    (["--wait", "--name", "lane-alpha", *LANE[:2]], "are for --close"),
    (["--close", "--timeout", "30", "--name", "lane-alpha"], "pass --wait with it"),
    (["--close", "--wait", "--abandoned", "stuck", "--name", "lane-alpha"], "pass one of them"),
    (["--close", "--wait", "--timeout", "0", "--name", "lane-alpha"], "not a positive number"),
])
def test_a_wait_that_would_mean_nothing_is_refused(waiting, capsys, argv, said):
    waiting["statuses"] = ["idle"]
    assert ot.main(argv) == 2
    assert said in capsys.readouterr().err
    assert waiting["killed"] == [] and waiting["launched"] == []


def test_the_list_is_unchanged_by_the_wait(waiting, capsys):
    waiting["statuses"] = ["busy"]
    assert ot.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "lane-alpha" in out and f"lane, opus - {OPUS_JOB}" in out
    assert "waiting up to" not in out and waiting["sleeps"] == []


def test_a_correction_routed_to_a_done_lane_puts_it_back_to_work(desk, capsys):
    opened(desk)
    dr.report_done("lane-alpha")
    dr.route("the-desk", ["records/2025/January/2025_January_Ledger.md"],
             "the January deposit was a refund", None)
    assert ot.main(["--close", "--name", "lane-alpha"]) == 2
    assert desk["killed"] == []


def test_an_abandoned_lane_closes_and_the_why_is_recorded_twice(desk):
    opened(desk, status="busy")
    assert ot.main(["--close", "--name", "lane-alpha", "--abandoned", "looping"]) == 0
    assert record()[-1]["abandoned"] == "looping"
    assert dr.read_record()["lanes"]["lane-alpha"]["closed"]["abandoned"] == "looping"


def test_a_window_the_desk_record_never_heard_of_still_closes_plainly(room):
    opened(room, status="busy")
    assert ot.main(["--close", "--name", "lane-alpha"]) == 0


# --- the desk is SHOWN a stalled lane by the commands it runs anyway -----------


def stalls(monkeypatch, tmp_path, rows):
    import note_prompt
    log = tmp_path / "prompts.jsonl"
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(note_prompt, "LOG", log)


def test_list_names_a_lane_stopped_at_a_pop_up(room, monkeypatch, tmp_path, capsys):
    opened(room, status="waiting")
    sid = room["live"][0]["sessionId"]
    stalls(monkeypatch, tmp_path, [
        {"session": sid, "tool": "PowerShell", "what": "an older command"},
        {"session": sid, "tool": "Bash", "what": "rm -rf $TEMP/recon_smoke"}])
    assert ot.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "NEEDS THE OWNER -- the `lane-alpha` tab" in out
    assert "Bash: rm -rf $TEMP/recon_smoke" in out and "an older command" not in out
    assert out.count("NEEDS THE OWNER") == 1


def test_a_waiting_lane_with_no_pop_up_on_record_is_still_named(room, monkeypatch, tmp_path, capsys):
    opened(room, status="waiting")
    stalls(monkeypatch, tmp_path, [])
    ot.main(["--list"])
    assert "may be asking the owner a question" in capsys.readouterr().out


def test_busy_and_idle_lanes_raise_no_banner(room, monkeypatch, tmp_path, capsys):
    for status in ("busy", "idle"):
        opened(room, status=status)
        stalls(monkeypatch, tmp_path, [])
        ot.main(["--list"])
        assert "NEEDS THE OWNER" not in capsys.readouterr().out


def test_a_close_also_ends_with_the_banner(room, monkeypatch, tmp_path, capsys):
    opened(room, status="idle")
    room["live"].append(session("other-lane", status="waiting", pid=5151))
    stalls(monkeypatch, tmp_path, [])
    ot.main(["--close", "--name", "lane-alpha"])
    assert "NEEDS THE OWNER -- the `other-lane` tab" in capsys.readouterr().out


def test_the_banner_never_breaks_the_act_it_rides_on(room, monkeypatch):
    def boom():
        raise RuntimeError("the CLI is gone")
    monkeypatch.setattr(ot, "live_sessions", boom)
    assert ot.stalled_lines() == []


def test_a_lane_window_carries_its_role_in_its_environment(room):
    window = ot.window_for("lane", "lane-alpha", "sheets/lane-alpha.md", "opus", resume=False)
    assert dict(window.env) == {pi.ROLE_ENV: "lane", pi.WINDOW_ENV: "lane-alpha"}


def test_ancestry_walk_stops_at_a_recycled_parent_pid():
    # 30 is this process; its parent 20 died and pid 20 now belongs to a
    # younger, unrelated process whose own parent is a lane (10).
    table = [
        {"ProcessId": 30, "ParentProcessId": 20, "Created": 100},
        {"ProcessId": 20, "ParentProcessId": 10, "Created": 500},
        {"ProcessId": 10, "ParentProcessId": 1, "Created": 400},
    ]
    assert ot.ancestry_from(table, 30) == {30}


def test_ancestry_walk_climbs_a_real_tree():
    table = [
        {"ProcessId": 30, "ParentProcessId": 20, "Created": 300},
        {"ProcessId": 20, "ParentProcessId": 10, "Created": 200},
        {"ProcessId": 10, "ParentProcessId": 1, "Created": None},
    ]
    assert ot.ancestry_from(table, 30) == {30, 20, 10}


# --- where there is no Windows Terminal: the owner pastes one line ------------


@pytest.mark.parametrize("os_name, has_wt, mode", [
    ("nt", True, ot.OPENED_BY_WT),
    ("nt", False, ot.OPENED_BY_MANUAL),
    ("posix", True, ot.OPENED_BY_MANUAL),
    ("posix", False, ot.OPENED_BY_MANUAL),
])
def test_only_windows_with_wt_opens_a_tab_itself(os_name, has_wt, mode):
    assert ot.launch_mode(os_name, has_wt) == mode


def test_a_posix_machine_never_asks_for_wt(monkeypatch):
    monkeypatch.setattr(ot, "wt_available", lambda: pytest.fail("wt was looked for"))
    assert ot.launch_mode("posix") == ot.OPENED_BY_MANUAL


@pytest.fixture
def by_hand(room, monkeypatch):
    """A macOS or Linux machine: the open is manual and prints the POSIX line."""
    monkeypatch.setattr(ot, "launch_mode", lambda: ot.OPENED_BY_MANUAL)
    monkeypatch.setattr(ot, "manual_line",
                        lambda window, cwd: wt.manual_line(window, cwd=cwd, os_name="posix"))
    real_reason = ot.manual_reason
    monkeypatch.setattr(ot, "manual_reason", lambda: real_reason("posix"))
    return room


def expected_posix_line(name, task, model="opus"):
    return (f"cd '{REPO}' && {pi.ROLE_ENV}=lane {pi.WINDOW_ENV}={name} "
            f"claude --model {model} --permission-mode acceptEdits "
            f"--remote-control {name} --name {name} '/lane {name} {task}'")


def test_a_manual_open_prints_the_line_and_records_it_as_manual(by_hand, capsys):
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    out = capsys.readouterr().out
    assert "OPEN BY HAND - this is not Windows" in out
    assert "open a new terminal tab, name it lane-alpha" in out
    assert expected_posix_line("lane-alpha", LANE[-1]) in out
    assert "Wait for its ack" in out
    assert "wt.exe" not in out and by_hand["launched"] == []
    (entry,) = record()
    assert (entry["event"], entry["name"], entry["model"], entry["opened_by"]) == (
        "open", "lane-alpha", "opus", "manual")


def test_the_printed_line_is_what_the_owner_pastes(by_hand, capsys):
    """Word for word what a bash or zsh tab would run: the folder, the two
    variables the lane guard reads, and the same argv a Terminal tab runs."""
    ot.main([*LANE, "--reason", SONNET_JOB])
    line = next(l.strip() for l in capsys.readouterr().out.splitlines()
                if l.strip().startswith("cd '"))
    words = shlex.split(line)
    assert words[:3] == ["cd", str(REPO), "&&"]
    assert words[3:5] == [f"{pi.ROLE_ENV}=lane", f"{pi.WINDOW_ENV}=lane-alpha"]
    tier = ot.tier_choice("lane", None, SONNET_JOB)
    assert tuple(words[5:]) == ot.window_for(
        "lane", "lane-alpha", LANE[-1], tier.model, resume=False).argv


def test_a_manual_dry_run_prints_the_line_and_records_nothing(by_hand, capsys):
    assert ot.main([*LANE, "--reason", OPUS_JOB, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert expected_posix_line("lane-alpha", LANE[-1]) in out
    assert "OPEN BY HAND" not in out and not ot.RECORD.exists()


def test_a_manual_open_refuses_exactly_what_a_tab_open_refuses(by_hand, capsys):
    assert ot.main(LANE) == 2
    assert "needs --reason" in capsys.readouterr().err
    assert not ot.RECORD.exists()


def test_a_tab_open_is_recorded_as_opened_by_wt(room):
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    assert record()[-1]["opened_by"] == "wt"


def test_windows_without_wt_prints_a_powershell_line(room, monkeypatch, capsys):
    monkeypatch.setattr(ot, "launch_mode", lambda: ot.OPENED_BY_MANUAL)
    monkeypatch.setattr(ot, "manual_line",
                        lambda window, cwd: wt.manual_line(window, cwd=cwd, os_name="nt"))
    monkeypatch.setattr(ot, "manual_reason", lambda: "wt.exe is not on PATH")
    assert ot.main([*LANE, "--reason", OPUS_JOB]) == 0
    out = capsys.readouterr().out
    assert "OPEN BY HAND - wt.exe is not on PATH" in out
    assert f"Set-Location -LiteralPath '{REPO}'; $env:{pi.ROLE_ENV} = 'lane';" in out
    assert record()[-1]["opened_by"] == "manual"


@pytest.mark.parametrize("os_name, said", [
    ("nt", "wt.exe is not on PATH"),
    ("posix", "this is not Windows"),
])
def test_the_manual_reason_says_which_case_it_is(os_name, said):
    assert said in ot.manual_reason(os_name)


# --- every window starts with Remote Control on (owner's ruling, 2026-09-26) ----


DESK = ["--role", "desk", "--name", "desk", "--model", "fable", "--fable-approved-by-owner"]


def rc(name):
    """The name the phone lists a window under: exactly its `--name`, until a
    visible-tab measurement shows whether `--remote-control` renames it."""
    return name


def launched_statement(room):
    """The PowerShell statement inside the last `wt.exe` line this launched:
    the argv rides in it as a base64 `-EncodedCommand` blob."""
    blob = room["launched"][-1][-1]
    return base64.b64decode(blob).decode("utf-16-le")


def printed_manual_line(out, os_name):
    start = "cd '" if os_name == "posix" else "Set-Location"
    return next(l.strip() for l in out.splitlines() if l.strip().startswith(start))


@pytest.mark.parametrize("argv, name", [
    ([*LANE, "--reason", OPUS_JOB], "lane-alpha"),
    (DESK, "desk"),
])
def test_a_tab_open_carries_remote_control_named_for_the_window(room, argv, name):
    assert ot.main(argv) == 0
    assert "& 'claude' " in launched_statement(room)
    assert f"'--remote-control' '{rc(name)}' '--name' '{name}'" in launched_statement(room)
    assert record()[-1]["remote_control"] is True


@pytest.mark.parametrize("os_name", ["posix", "nt"])
@pytest.mark.parametrize("argv, name", [
    ([*LANE, "--reason", OPUS_JOB], "lane-alpha"),
    (DESK, "desk"),
])
def test_the_open_by_hand_line_carries_remote_control(room, monkeypatch, capsys,
                                                      os_name, argv, name):
    monkeypatch.setattr(ot, "launch_mode", lambda: ot.OPENED_BY_MANUAL)
    monkeypatch.setattr(ot, "manual_line",
                        lambda window, cwd: wt.manual_line(window, cwd=cwd, os_name=os_name))
    assert ot.main(argv) == 0
    out = capsys.readouterr().out
    assert "OPEN BY HAND" in out
    line = printed_manual_line(out, os_name)
    said = (f"--remote-control {rc(name)} --name {name}" if os_name == "posix"
            else f"'--remote-control' '{rc(name)}' '--name' '{name}'")
    assert said in line
    assert record()[-1]["remote_control"] is True


def test_the_name_always_follows_the_flag_so_nothing_else_is_taken_for_it(room):
    """The CLI's value is optional: a bare flag would take the next word."""
    for role, task in (("lane", "sheet.md"), ("desk", None)):
        argv = ot.window_for(role, "w1", task, "opus", resume=False).argv
        assert argv[argv.index("--remote-control") + 1] == rc("w1")


def test_the_remote_control_name_is_exactly_the_messaging_name(room):
    """Whether `--remote-control <name>` also renames the session is
    unmeasured. With the two strings identical, whichever sets the name, the
    desk and its lanes still message, close and refuse by the window name."""
    for role, task in (("lane", "sheet.md"), ("desk", None)):
        argv = ot.window_for(role, "w1", task, "opus", resume=False).argv
        assert argv[argv.index("--name") + 1] == "w1"
        assert argv[argv.index("--remote-control") + 1] == "w1"
    argv = ot.window_for("lane", "w1", None, "opus", resume=True).argv
    assert argv[argv.index("--remote-control") + 1] == argv[argv.index("--resume") + 1]
    assert dict(ot.window_for("lane", "w1", "s.md", "opus", resume=False).env)[
        pi.WINDOW_ENV] == "w1"


def test_a_resumed_window_keeps_remote_control(room):
    argv = ot.window_for("lane", "lane-alpha", None, "opus", resume=True).argv
    assert argv[argv.index("--remote-control") + 1] == rc("lane-alpha")
    assert argv[-2:] == ("--resume", "lane-alpha")


def test_no_remote_control_turns_it_off_on_both_paths(room, monkeypatch, capsys):
    assert ot.main([*LANE, "--reason", OPUS_JOB, "--no-remote-control"]) == 0
    assert "--remote-control" not in launched_statement(room)
    assert record()[-1]["remote_control"] is False
    monkeypatch.setattr(ot, "launch_mode", lambda: ot.OPENED_BY_MANUAL)
    monkeypatch.setattr(ot, "manual_line",
                        lambda window, cwd: wt.manual_line(window, cwd=cwd, os_name="posix"))
    assert ot.main(["--role", "lane", "--name", "lane-beta", "--task", "x",
                    "--reason", OPUS_JOB, "--no-remote-control"]) == 0
    assert "--remote-control" not in printed_manual_line(capsys.readouterr().out, "posix")
    assert record()[-1]["remote_control"] is False


def test_a_dry_run_says_whether_remote_control_is_on(room, capsys):
    """The `wt.exe` line hides the argv in an encoded blob, so it is said."""
    assert ot.main([*LANE, "--reason", OPUS_JOB, "--dry-run"]) == 0
    assert f"remote control: {rc('lane-alpha')}" in capsys.readouterr().out
    assert ot.main([*LANE, "--reason", OPUS_JOB, "--dry-run", "--no-remote-control"]) == 0
    assert "remote control: off (--no-remote-control)" in capsys.readouterr().out


def test_the_docstring_documents_the_off_switch():
    assert ot.NO_REMOTE_CONTROL_FLAG in ot.__doc__
    assert "REMOTE CONTROL" in ot.__doc__


# --- closing, per machine -------------------------------------------------------


@pytest.mark.parametrize("os_name, command", [
    ("nt", ["taskkill", "/PID", "4242", "/T", "/F"]),
    ("posix", ["kill", "-TERM", "4242"]),
])
def test_the_kill_is_the_machines_own(os_name, command):
    assert ot.kill_command(4242, os_name) == command


def test_ps_output_becomes_the_table_the_ancestry_walk_reads():
    text = "    1     0\n  200     1\n  300   200\n garbage line\n"
    table = ot.parse_ps(text)
    assert table == [
        {"ProcessId": 1, "ParentProcessId": 0, "Created": None},
        {"ProcessId": 200, "ParentProcessId": 1, "Created": None},
        {"ProcessId": 300, "ParentProcessId": 200, "Created": None},
    ]
    assert ot.ancestry_from(table, 300) == {300, 200, 1}


@pytest.mark.skipif(os.name == "nt", reason="asks a real `ps`, which Windows lacks")
def test_this_process_finds_itself_in_the_real_process_table():
    assert os.getpid() in ot.own_ancestry()


@pytest.mark.skipif(os.name != "nt", reason="asks a real PowerShell for the process table")
def test_this_process_finds_itself_in_the_real_windows_table():
    assert os.getpid() in ot.own_ancestry()
