"""Tests for scripts/backlog.py -- the backlog ledger -- and the desk save's move of
a closing desk's Logged-for-later bullets onto it (scripts/desk_save.py)."""
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

import backlog as bl
import desk_record as dr
import desk_save as ds

from test_desk_record import DESK, git, sheet  # noqa: F401  (the same stand-in workspace)
from test_desk_record import repo  # noqa: F401  (pytest fixture)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TODAY = date(2026, 1, 15)


def run(tmp_path, *args):
    return bl.main(list(args), path=tmp_path / bl.LEDGER_REL, today=TODAY)


@pytest.fixture
def ledger_dir(tmp_path):
    (tmp_path / "notes.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    return tmp_path


# --- the ledger -----------------------------------------------------------------


def test_add_park_and_close_round_trip_and_check_passes(ledger_dir, capsys):
    assert run(ledger_dir, "add", "a short line", "--pointer", "notes.md:2", "--from", "desk x") == 0
    assert run(ledger_dir, "check") == 1          # unrouted
    assert run(ledger_dir, "park", "B1", "--until", "the next release") == 0
    assert run(ledger_dir, "check") == 0
    text = (ledger_dir / bl.LEDGER_REL).read_text(encoding="utf-8")
    assert "parked until the next release · a short line → notes.md:2" in text
    assert run(ledger_dir, "close", "B1", "--done", "abc1234") == 0
    ledger = bl.read(ledger_dir / bl.LEDGER_REL)
    assert ledger.open == [] and ledger.closed[0].startswith("B1 · logged 2026-01-15 · closed 2026-01-15 · done")


def test_an_entry_without_a_pointer_or_with_a_missing_file_is_refused(ledger_dir, capsys):
    assert run(ledger_dir, "add", "no pointer", "--from", "desk x") == 2
    assert "no pointer" in capsys.readouterr().err
    assert run(ledger_dir, "add", "gone", "--pointer", "nowhere.md", "--from", "desk x") == 2
    assert "names no file" in capsys.readouterr().err
    assert run(ledger_dir, "add", "past the end", "--pointer", "notes.md:40", "--from", "desk x") == 2
    assert not (ledger_dir / bl.LEDGER_REL).exists()


def test_a_line_over_the_cap_is_refused_and_says_what_to_shorten(ledger_dir, capsys):
    assert run(ledger_dir, "add", "w" * bl.ENTRY_CAP, "--pointer", "notes.md", "--from", "desk x") == 2
    assert "over the" in capsys.readouterr().err
    assert run(ledger_dir, "add", "short", "--pointer", "notes.md", "--from", "desk x") == 0
    assert run(ledger_dir, "park", "B1", "--until", "u" * bl.ENTRY_CAP) == 2
    assert "the park text" in capsys.readouterr().err
    assert bl.read(ledger_dir / bl.LEDGER_REL).open[0].route == bl.OPEN


def test_a_closing_note_too_long_for_the_closed_cap_is_refused(ledger_dir, capsys):
    run(ledger_dir, "add", "short", "--pointer", "notes.md", "--from", "desk x")
    assert run(ledger_dir, "close", "B1", "--done", "n" * bl.CLOSED_CAP) == 2
    assert "closed line is capped" in capsys.readouterr().err


def test_a_hand_edit_fails_check_and_refuses_every_write(ledger_dir, capsys):
    run(ledger_dir, "add", "short", "--pointer", "notes.md", "--from", "desk x")
    path = ledger_dir / bl.LEDGER_REL
    path.write_text(path.read_text(encoding="utf-8").replace("short", "edited"), encoding="utf-8")
    assert run(ledger_dir, "check") == 1
    assert run(ledger_dir, "desk", "B1") == 2
    assert "edited by hand" in capsys.readouterr().err


def test_reword_keeps_id_date_from_and_route(ledger_dir):
    run(ledger_dir, "add", "a long first wording", "--pointer", "notes.md", "--from", "desk x")
    run(ledger_dir, "park", "B1", "--until", "an event")
    assert run(ledger_dir, "reword", "B1", "shorter", "--pointer", "notes.md:1") == 0
    entry = bl.read(ledger_dir / bl.LEDGER_REL).open[0]
    assert (entry.id, entry.logged, entry.source, entry.route, entry.text, entry.pointer) == (
        "B1", "2026-01-15", "desk x", "parked until an event", "shorter", "notes.md:1")


def test_the_budget_holds_25_entries_at_the_cap_beside_five_closings():
    """backlog.md's doc_budgets.yaml row (8,000 b) holds about 25 open entries at
    ENTRY_CAP: the caps are derived from it, so a change that breaks it fails here."""
    ledger = bl.empty()
    ledger.next_id = 1000
    for i in range(25):
        e = bl.Entry(f"B{1000 + i}", "2026-01-15", "desk some-desk", bl.PARKED + "x", "", "p.md:1")
        e.text = "s" * (bl.ENTRY_CAP - bl.size(e.line()))
        assert bl.size(e.line()) == bl.ENTRY_CAP
        ledger.open.append(e)
    ledger.next_id = 1025
    ledger.closed = ["c" * (bl.CLOSED_CAP - 2)] * bl.CLOSED_KEPT
    rendered = ledger.render().replace("\n", "\r\n")   # as a Windows checkout measures it
    assert bl.size(rendered) <= 8000


# --- logged for later ----------------------------------------------------------------

LOG = """# Desk log

## Logged for later

- lane-alpha, 2026-01-15, until the vendor's next release: the export drops a field — "their words, at length"
"""


def test_a_bullet_in_shape_is_moved_parked_until_its_blocker_pointing_at_its_line(ledger_dir):
    (ledger_dir / "log.md").write_text(LOG, encoding="utf-8")
    ledger = bl.empty()
    added = bl.move_logged(ledger, LOG, "log.md", "desk d", "2026-01-15", ledger_dir)
    assert [(e.route, e.text, e.pointer) for e in added] == [
        ("parked until the vendor's next release", "the export drops a field", "log.md:5")]


def test_a_bullet_with_no_blocker_is_refused_as_work_for_the_job():
    log = LOG.replace(", until the vendor's next release", "")
    problems = bl.logged_problems(log, "log.md")
    assert len(problems) == 1 and "names no blocker" in problems[0] and "done in the job" in problems[0]


def test_a_bullet_out_of_shape_is_refused():
    problems = bl.logged_problems(LOG.replace(" — ", " - "), "log.md")
    assert len(problems) == 1 and "is not `" in problems[0]


# --- the desk save ----------------------------------------------------------------


def out(repo, *args):  # noqa: F811
    return subprocess.run(["git", *args], cwd=str(repo), check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout


@pytest.fixture
def job(repo):  # noqa: F811
    """A desk with one closed lane, in a project that has the backlog ledger."""
    (repo / "scripts").mkdir(exist_ok=True)
    shutil.copy(SCRIPTS / "backlog.py", repo / "scripts" / "backlog.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "the ledger script")
    dr.open_desk(DESK, "a test job", inherit=False)
    dr.plan_desk(DESK, 10)
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    (repo / "records/2025/January/Ledger.md").write_text("x\nSession 3\n", encoding="utf-8")
    dr.record_close("lane-alpha")
    return repo


def test_the_save_parks_each_logged_bullet_on_the_ledger_in_its_commit(job, capsys):
    with dr.DESK_LOG.open("a", encoding="utf-8") as handle:
        handle.write(LOG)
    assert ds.save(DESK, "the job", push=False) == 0
    files = out(job, "show", "--name-only", "--format=", "HEAD").split("\n")
    assert bl.LEDGER_REL in files
    entry = bl.read(job / bl.LEDGER_REL).open[0]
    assert entry.route == "parked until the vendor's next release"
    assert entry.pointer.startswith("coordination/closed/") and entry.pointer.endswith("desk_log.md:" + str(
        next(n for n, line in enumerate((job / entry.pointer.split(":")[0]).read_text(
            encoding="utf-8").split("\n"), 1) if line.startswith("- lane-alpha"))))
    assert bl.check(job / bl.LEDGER_REL)[0] == 0


def test_a_bullet_with_no_blocker_refuses_the_save_and_leaves_the_desk_open(job, capsys):
    with dr.DESK_LOG.open("a", encoding="utf-8") as handle:
        handle.write(LOG.replace(", until the vendor's next release", ""))
    assert ds.save(DESK, "the job", push=False) == 1
    assert "names no blocker" in capsys.readouterr().err
    assert dr.RECORD.exists() and not (job / bl.LEDGER_REL).exists()


def test_without_the_ledger_script_the_save_ignores_the_logged_bullets(repo, capsys):  # noqa: F811
    git(repo, "add", "-A")
    dr.open_desk(DESK, "a test job", inherit=False)
    dr.plan_desk(DESK, 10)
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    (repo / "records/2025/January/Ledger.md").write_text("x\nSession 3\n", encoding="utf-8")
    dr.record_close("lane-alpha")
    with dr.DESK_LOG.open("a", encoding="utf-8") as handle:
        handle.write(LOG.replace(", until the vendor's next release", ""))
    assert ds.save(DESK, "the job", push=False) == 0
    assert not (repo / bl.LEDGER_REL).exists()
