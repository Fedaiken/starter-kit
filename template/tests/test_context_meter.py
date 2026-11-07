"""Tests for scripts/context_meter.py: a window's context is read from its own
transcript, never guessed.

Every transcript here is written under tmp_path in the shape the CLI writes
(one JSON entry a line, `message.usage` on each assistant turn), and the meter
is pointed at that folder; nothing reads the owner's real transcripts.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import context_meter as cm
import desk_record as dr
import open_terminal as ot
from wt import TerminalError

REPO = Path(__file__).resolve().parents[1]


def turn(tokens, *, cached=0, created=0, stop="end_turn", at="2026-11-02T20:00:00Z",
         text="", sidechain=False, send=None):
    content = [{"type": "text", "text": text}] if text else []
    if send:
        content.append({"type": "tool_use", "name": "SendMessage",
                        "input": {"to": "the-desk", "message": send}})
    return {"type": "assistant", "isSidechain": sidechain, "timestamp": at,
            "message": {"model": "claude-opus-5-5", "stop_reason": stop,
                        "content": content,
                        "usage": {"input_tokens": tokens,
                                  "cache_read_input_tokens": cached,
                                  "cache_creation_input_tokens": created,
                                  "output_tokens": 999}}}


def api_error(text="Prompt is too long", error="invalid_request"):
    return {"type": "assistant", "isApiErrorMessage": True, "error": error,
            "timestamp": "2026-11-02T21:00:00Z",
            "message": {"model": "<synthetic>", "content": [{"type": "text", "text": text}],
                        "usage": {"input_tokens": 0, "cache_read_input_tokens": 0,
                                  "cache_creation_input_tokens": 0}}}


def typed(text, at="2026-11-02T19:59:00Z"):
    return {"type": "user", "timestamp": at, "message": {"role": "user", "content": text}}


def tool_result():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}


def lane_command(name, sheet, at="2026-11-02T19:00:00Z"):
    return typed("<command-message>lane</command-message>\n<command-name>/lane</command-name>\n"
                 f"<command-args>{name} {sheet}</command-args>", at)


def write(folder, session_id, entries, tail=""):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session_id}.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries) + tail, encoding="utf-8")
    return path


@pytest.fixture
def folder(tmp_path, monkeypatch):
    here = tmp_path / "projects" / "key"
    here.mkdir(parents=True)
    monkeypatch.setattr(cm, "PROJECT_DIR", here)
    return here


# --- one transcript -------------------------------------------------------------


def test_the_project_key_is_the_folder_claude_writes():
    assert cm.project_key(Path(r"C:\Users\someone\Claude\Project")) == "C--Users-someone-Claude-Project"


def test_tokens_now_is_the_three_input_fields_of_the_last_real_turn(folder):
    path = write(folder, "s1", [typed("go"), turn(10, cached=20_000, created=5),
                                tool_result(), turn(3, cached=40_000, created=7)])
    assert cm.tokens_now(path) == 40_010, "output tokens are not context"
    assert cm.peak_tokens(path) == 40_010


def test_the_peak_is_the_largest_turn_not_the_last(folder):
    path = write(folder, "s1", [turn(1, cached=90_000), turn(1, cached=30_000)])
    assert cm.tokens_now(path) == 30_001 and cm.peak_tokens(path) == 90_001


def test_an_api_error_entry_is_never_a_reading_and_a_sidechain_is_another_context(folder):
    path = write(folder, "s1", [turn(1, cached=500_000), turn(1, cached=900_000, sidechain=True),
                                api_error()])
    assert cm.tokens_now(path) == 500_001
    assert cm.peak_tokens(path) == 500_001
    err = cm.last_error(path)
    assert err["error"] == "invalid_request" and cm.is_dead_at_ceiling(err)


def test_a_resumable_error_is_not_dead_and_a_resumed_window_has_no_error(folder):
    path = write(folder, "s1", [turn(5), api_error("API Error: Server error", "server_error")])
    assert not cm.is_dead_at_ceiling(cm.last_error(path))
    path = write(folder, "s2", [turn(5), api_error(), typed("go on"), turn(6)])
    assert cm.last_error(path) is None


def test_a_half_written_last_line_is_skipped(folder):
    path = write(folder, "s1", [turn(1, cached=1_000)], tail='{"type": "assist')
    assert cm.tokens_now(path) == 1_001


def test_a_turn_far_behind_a_huge_line_is_still_found(folder, monkeypatch):
    monkeypatch.setattr(cm, "TAIL_BYTES", 64)
    path = write(folder, "s1", [turn(1, cached=7_000), tool_result() | {"pad": "x" * 5_000}])
    assert cm.tokens_now(path) == 7_001


def test_an_unreadable_transcript_is_none_never_a_number(folder):
    assert cm.tokens_now(folder / "nope.jsonl") is None
    assert cm.peak_tokens(folder / "nope.jsonl") is None
    assert cm.transcript_path("../escape") is None
    assert cm.transcript_path("missing") is None


# --- the last turn ----------------------------------------------------------------


def test_the_last_turn_reads_its_reports_back_to_its_prompt(folder):
    path = write(folder, "s1", [typed("first"), turn(1, send="done: lane-alpha, x.md"),
                                typed("next"), turn(1, text="Next: the router."),
                                tool_result(), turn(1, text="still working")])
    got = cm.last_turn(path)
    assert got["stop_reason"] == "end_turn" and got["reports"] == set(), \
        "the done: was an earlier turn's"


def test_a_question_sent_by_sendmessage_is_a_report(folder):
    path = write(folder, "s1", [typed("go"), turn(1, send="question: which file?")])
    assert cm.last_turn(path)["reports"] == {"question"}


def test_a_peer_message_starts_a_turn_and_a_heading_is_not_a_report(folder):
    peer = {"type": "user", "isMeta": True, "origin": {"kind": "peer"},
            "message": {"content": "[desk] answer: yes"}}
    path = write(folder, "s1", [typed("go"), turn(1, send="done: x"), peer,
                                turn(1, text="Done: a heading, not the line")])
    assert cm.last_turn(path)["reports"] == set()


def test_a_window_whose_last_entry_is_an_error_has_no_last_turn(folder):
    assert cm.last_turn(write(folder, "s1", [typed("go"), turn(1), api_error()])) is None


# --- lane transcripts -------------------------------------------------------------


def test_lane_transcripts_are_found_by_their_role_command(folder):
    write(folder, "a", [lane_command("lane-alpha", "sheets/a.md"), turn(1)])
    write(folder, "b", [typed("/lane lane-beta sheets/b.md"), turn(1)])
    write(folder, "c", [typed("/desk"), turn(1)])
    assert sorted(cm.lane_transcripts()) == ["lane-alpha", "lane-beta"]


def test_a_lane_name_used_twice_keeps_the_later_window(folder):
    write(folder, "old", [lane_command("lane-alpha", "x.md", at="2026-11-01T10:00:00Z")])
    write(folder, "new", [lane_command("lane-alpha", "y.md", at="2026-11-02T10:00:00Z")])
    assert cm.lane_transcripts()["lane-alpha"].stem == "new"


# --- live windows and THIS WINDOW ---------------------------------------------------


def row(name, sid, pid):
    return {"name": name, "sessionId": sid, "pid": pid, "cwd": str(REPO), "status": "idle"}


def test_this_window_is_the_live_session_in_this_process_s_ancestry(monkeypatch):
    rows = [row("desk", "d", 10), row("lane", "l", 20)]
    monkeypatch.setattr(ot, "own_ancestry", lambda: {99, 20, 5})
    assert cm.this_window(rows)["name"] == "lane"


def test_no_match_and_no_environment_is_no_window(monkeypatch):
    monkeypatch.setattr(ot, "own_ancestry", lambda: {99})
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    assert cm.this_window([row("desk", "d", 10)]) is None


def test_the_environment_is_believed_only_when_the_process_table_agrees(monkeypatch):
    rows = [row("desk", "d", 10)]
    monkeypatch.setattr(ot, "own_ancestry", lambda: set())
    monkeypatch.setenv("CLAUDE_PID", "10")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "d")
    me = cm.os.getpid()
    # The walk from this process stops at a parent born AFTER claude.exe: a child.
    table = [{"ProcessId": me, "ParentProcessId": 77, "Created": 300},
             {"ProcessId": 10, "ParentProcessId": 1, "Created": 100}]
    monkeypatch.setattr(ot, "process_table", lambda: table)
    assert cm.this_window(rows)["name"] == "desk"
    # A shell older than claude.exe is not its child, whatever its environment says.
    table[0]["Created"] = 50
    assert cm.this_window(rows) is None
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "another")
    table[0]["Created"] = 300
    assert cm.this_window(rows) is None


def test_the_report_marks_this_window_and_names_the_unreadable(folder, monkeypatch):
    write(folder, "d", [turn(1, cached=250_000), turn(1, cached=244_858)])
    rows = [row("savecraft-e2", "d", 10), row("lane-x", "gone", 20)]
    lines = cm.report_lines(rows, mine=rows[0])
    assert lines[0].startswith(f"{cm.UNREADABLE}lane-x")
    assert "savecraft-e2" in lines[1] and "244,859 tokens" in lines[1]
    assert " 24.5%" in lines[1] and "peak   250,001" in lines[1]
    assert lines[1].endswith(cm.THIS_WINDOW)


def test_the_report_exits_2_when_the_live_list_cannot_be_read(monkeypatch, capsys):
    def boom():
        raise TerminalError("no CLI")
    monkeypatch.setattr(ot, "live_sessions", boom)
    assert cm.main(["--report"]) == 2
    assert cm.UNREADABLE in capsys.readouterr().err


def test_the_report_says_when_this_window_is_not_found(folder, monkeypatch, capsys):
    write(folder, "d", [turn(1, cached=1_000)])
    monkeypatch.setattr(ot, "live_sessions", lambda: [row("desk", "d", 10)])
    monkeypatch.setattr(ot, "own_ancestry", lambda: set())
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    assert cm.main(["--report"]) == 0
    out = capsys.readouterr().out
    assert "desk" in out and f"{cm.UNREADABLE}this window" in out


def test_the_window_is_the_measured_million_and_the_desk_uses_the_same():
    assert cm.WINDOW_TOKENS == 1_000_000 == dr.WINDOW_TOKENS
    assert cm.percent_of_window(244_859) == 24.5, "the owner's 24% on 2026-11-02"


def test_since_is_for_peaks_and_must_be_a_date(capsys):
    with pytest.raises(SystemExit):
        cm.main(["--report", "--since", "2026-11-02"])
    with pytest.raises(SystemExit):
        cm.main(["--peaks", "--since", "not-a-date"])
