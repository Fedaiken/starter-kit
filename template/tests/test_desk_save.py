"""Tests for scripts/desk_save.py -- the desk's one save as one act.

Ported 2026-09-24 from FACOWORK (its slice 5), plus the document gate.
Everything runs in a throwaway git repository
under tmp_path; nothing here touches the project's own record or history.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import desk_record as dr
import desk_save as ds

from test_desk_record import DESK, SHEET, git, sheet  # noqa: F401  (the same stand-in workspace)
from test_desk_record import repo  # noqa: F401  (pytest fixture)


def out(repo, *args):  # noqa: F811
    return subprocess.run(["git", *args], cwd=str(repo), check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def job(repo):  # noqa: F811
    """A desk with one lane that has edited its file, written a new one, and closed."""
    git(repo, "add", "-A")
    dr.open_desk(DESK, "a test job", inherit=False)
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    (repo / "records/2025/January/Ledger.md").write_text("x\nSession 3\n", encoding="utf-8")
    (repo / "records/2025/January/New Note.md").write_text("born\n", encoding="utf-8")
    dr.record_close("lane-alpha")
    return repo


def test_the_save_is_one_commit_of_the_owned_paths_and_the_desks_record(job):
    assert ds.save(DESK, "the job", push=False) == 0
    files = out(job, "show", "--name-only", "--format=", "HEAD").split("\n")
    assert "records/2025/January/Ledger.md" in files
    assert "records/2025/January/New Note.md" in files
    assert any(f.startswith("coordination/closed/") for f in files)
    assert out(job, "status", "--porcelain") == ""


def test_another_windows_staged_file_does_not_ride_in_the_desks_commit(job):
    other = job / "records/2024/Q1/Summary.md"
    other.write_text("x\nanother window's work\n", encoding="utf-8")
    dr.outside(DESK, ["records/2024/Q1/Summary.md"], "another window")
    git(job, "add", "records/2024/Q1/Summary.md")     # that window staged it
    assert ds.save(DESK, "the job", push=False) == 0
    assert "Summary.md" not in out(job, "show", "--name-only", "--format=", "HEAD")
    assert out(job, "status", "--porcelain").strip() == "M  records/2024/Q1/Summary.md"


def test_a_stray_edit_refuses_the_save_and_leaves_the_desk_open(job, capsys):
    (job / "records/2024/Q1/Summary.md").write_text("stray\n", encoding="utf-8")
    head = out(job, "rev-parse", "HEAD")
    assert ds.save(DESK, "the job", push=False) == 1
    assert "NO lane owns this file" in capsys.readouterr().err
    assert out(job, "rev-parse", "HEAD") == head
    assert dr.RECORD.exists()


def test_a_lane_still_open_refuses_the_save(repo, capsys):  # noqa: F811
    dr.open_desk(DESK, "a test job", inherit=False)
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    assert ds.save(DESK, "the job", push=False) == 1
    assert "not yet closed" in capsys.readouterr().err
    assert dr.RECORD.exists()


def test_a_dry_run_lists_and_changes_nothing(job, capsys):
    head = out(job, "rev-parse", "HEAD")
    assert ds.save(DESK, "the job", dry_run=True, push=False) == 0
    said = capsys.readouterr().out
    assert "would save: records/2025/January/Ledger.md" in said
    assert out(job, "rev-parse", "HEAD") == head and dr.RECORD.exists()


def test_a_renamed_file_is_saved_as_a_rename(job):
    old = job / "records/2025/February/Ledger.md"
    old.rename(old.with_name("Ledger_old-.md"))
    assert ds.save(DESK, "the job", push=False) == 0
    assert out(job, "status", "--porcelain") == ""
    assert "Ledger_old-.md" in out(job, "show", "--name-only", "--format=", "HEAD")


def test_only_the_desk_may_save(job):
    with pytest.raises(dr.DeskError):
        ds.save("someone-else", "the job", push=False)


def test_a_failing_document_gate_refuses_the_save_and_leaves_the_desk_open(job, capsys):
    gate = job / "scripts" / "check_docs.py"
    gate.parent.mkdir()
    gate.write_text("import sys\nprint('FAIL - notes.md has no budget row')\nsys.exit(1)\n",
                    encoding="utf-8")
    dr.outside(DESK, ["scripts"], "the stand-in gate")
    head = out(job, "rev-parse", "HEAD")
    assert ds.save(DESK, "the job", push=False) == 1
    err = capsys.readouterr().err
    assert "notes.md has no budget row" in err and "document gate" in err
    assert out(job, "rev-parse", "HEAD") == head
    assert dr.RECORD.exists()


def test_a_passing_document_gate_lets_the_save_through(job):
    gate = job / "scripts" / "check_docs.py"
    gate.parent.mkdir()
    gate.write_text("print('OK')\n", encoding="utf-8")
    dr.outside(DESK, ["scripts"], "the stand-in gate")
    assert ds.save(DESK, "the job", push=False) == 0
