"""Desks side by side, each in its own home (scripts/desk_record.py homes,
scripts/check_ownership.py, scripts/desk_save.py, scripts/open_terminal.py,
scripts/desk_home.py, skills/desk/SKILL.md).

Ported 2026-09-26 from FACOWORK's tests/test_desk_homes.py, where the homes
were built for its session-recap desk ("it should only ever be constrained
with its own runs, not other desks' runs"), and carried to the generic /desk:
every new desk opens in a home of its own. Kit-owned; the `records/...` paths
are arbitrary files in a throwaway git repository under tmp_path.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_ownership as co
import desk_home as dh
import desk_record as dr
import desk_save as ds
import open_terminal as ot

from test_desk_record import DESK, SHEET  # noqa: F401  (the same stand-in workspace)
from test_desk_record import repo  # noqa: F401  (pytest fixture)

ROOT = Path(__file__).resolve().parents[1]

ALPHA, BETA = "statements", "letters"
BETA_DESK = "the-letters-desk"
BETA_FILE = "letters/2025/landlord.md"

BETA_SHEET = f"""# Task sheet: draft-landlord
unit: the letter to the landlord
reason: design-latitude
owns:
- {BETA_FILE}
reads:
- sources/statement_3.md
task:
Draft the letter.
done:
`python scripts/check_letter.py {BETA_FILE}` exits 0
"""


def out(repo, *args):  # noqa: F811
    return subprocess.run(["git", *args], cwd=str(repo), check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def homes(repo, monkeypatch):  # noqa: F811
    """The module's home globals are put back after the test, whatever it switched."""
    for attr in ("HOME", "RECORD", "DONE_DIR", "DESK_LOG", "CLOSED_DIR", "DESK_OWNS",
                 "HOME_PROBLEM"):
        monkeypatch.setattr(dr, attr, getattr(dr, attr))
    dr.use_home(None)
    return repo


def at(home):
    dr.use_home(home)


def home_sheet(repo, home, lane, text):  # noqa: F811
    rel = f"{dr.home_path(home)}/task_sheets/{lane}.md"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel


@pytest.fixture
def two(homes):
    """Two desks open at once, each in its own home with one lane."""
    repo = homes
    at(ALPHA)
    dr.open_desk(DESK, "a year of statements", inherit=False)
    dr.stamp(DESK, "lane-alpha", home_sheet(repo, ALPHA, "lane-alpha", SHEET))
    at(BETA)
    dr.open_desk(BETA_DESK, "the landlord letter", inherit=False)
    dr.stamp(BETA_DESK, "draft-landlord", home_sheet(repo, BETA, "draft-landlord", BETA_SHEET))
    return repo


def work(repo):
    """Each desk's lane changes its own file."""
    (repo / "records/2025/January/Ledger.md").write_text("x\nfixed\n", encoding="utf-8")
    (repo / BETA_FILE).parent.mkdir(parents=True, exist_ok=True)
    (repo / BETA_FILE).write_text("Dear landlord\n", encoding="utf-8")


# --- the home ------------------------------------------------------------------


def test_no_name_is_the_old_home_and_a_name_is_its_own_folder():
    assert dr.home_path(None) == dr.home_path("") == "coordination"
    assert dr.home_path(ALPHA) == "coordination/desks/statements"


@pytest.mark.parametrize("bad", ["Nola Sweets", "../x", "a/b", "-x", "SWEETS"])
def test_a_home_name_that_is_not_one_is_refused(bad):
    with pytest.raises(ValueError):
        dr.home_path(bad)


def test_the_home_variable_is_named_for_the_project():
    assert dr.HOME_ENV.endswith("_DESK_HOME") and dr.HOME_ENV != "FACOWORK_DESK_HOME"


def test_the_environment_names_the_home_when_the_module_loads():
    code = ("import desk_record as d; print(d.HOME); "
            "print(d.RECORD.relative_to(d.REPO).as_posix()); print(d.HOME_PROBLEM)")
    said = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT / "scripts"),
                          capture_output=True, text=True,
                          env={**os.environ, dr.HOME_ENV: ALPHA}, check=True)
    assert said.stdout.split() == ["coordination/desks/statements",
                                   "coordination/desks/statements/desk_record.json", "None"]


def test_a_bad_home_in_the_environment_refuses_every_act(homes, monkeypatch):
    monkeypatch.setattr(dr, "HOME_PROBLEM", "X_DESK_HOME='Bad' is not a desk home name")
    with pytest.raises(dr.DeskError, match="not a desk home name"):
        dr.open_desk(DESK, "a job", inherit=False)
    with pytest.raises(dr.DeskError, match="not a desk home name"):
        dr.require_record()


# --- every new desk names a home ---------------------------------------------------


def test_a_new_desk_with_no_home_is_refused_at_the_command_line(homes, capsys):
    at(None)
    assert dr.main(["open-desk", "--desk", DESK, "--job", "a job"]) == 2
    err = capsys.readouterr().err
    assert "desk_home.py <home> desk_record.py open-desk" in err
    assert not dr.RECORD.exists()
    at(ALPHA)
    assert dr.main(["open-desk", "--desk", DESK, "--job", "a job"]) == 0
    assert (homes / "coordination/desks/statements/desk_record.json").exists()


def test_a_record_left_in_coordination_can_still_be_inherited(homes, monkeypatch):
    at(None)
    dr.open_desk("old-desk", "a job from before homes", inherit=False)
    monkeypatch.setattr(dr, "live_desk_problem", lambda record, actor: None)
    assert dr.main(["open-desk", "--desk", DESK, "--inherit"]) == 0
    assert dr.read_record()["desk"] == DESK


def test_a_forgotten_wrapper_is_refused_and_names_the_desks_on_file(two):
    at(None)
    with pytest.raises(dr.DeskError, match=r"desk_home\.py <home>.*coordination/desks/letters"):
        dr.stamp(DESK, "lane-alpha", "coordination/desks/statements/task_sheets/lane-alpha.md")


# --- two desks open at once ------------------------------------------------------


def test_two_desks_open_side_by_side(two):
    at(ALPHA)
    assert dr.require_record()["desk"] == DESK
    at(BETA)
    assert dr.require_record()["desk"] == BETA_DESK


def test_two_desks_in_one_home_still_refuse_each_other(two):
    at(BETA)
    with pytest.raises(dr.DeskError, match="opens under a home name of its own"):
        dr.open_desk("a-second-desk", "another letter", inherit=False)


def live_as(monkeypatch, *rows):
    monkeypatch.setattr(ot, "live_sessions", lambda: list(rows))
    monkeypatch.setattr(ot, "here", lambda rows: list(rows))
    monkeypatch.setattr(ot, "own_ancestry", lambda: {1})


def test_a_live_desk_is_never_inherited_by_another(two, monkeypatch):
    at(BETA)
    record = dr.require_record()
    live_as(monkeypatch, {"name": BETA_DESK, "pid": 99})
    assert "is live in this workspace" in dr.live_desk_problem(record, "a-new-desk")
    assert dr.main(["open-desk", "--desk", "a-new-desk", "--inherit"]) == 2
    assert dr.require_record()["desk"] == BETA_DESK


def test_a_gone_desk_is_inherited_and_a_desk_may_retake_its_own(two, monkeypatch):
    at(BETA)
    record = dr.require_record()
    live_as(monkeypatch)
    assert dr.live_desk_problem(record, "a-new-desk") is None
    live_as(monkeypatch, {"name": BETA_DESK, "pid": 99})
    assert dr.live_desk_problem(record, BETA_DESK) is None


def test_a_lane_reports_done_to_its_own_desk(two):
    at(BETA)
    dr.report_done("draft-landlord")
    assert (two / "coordination/desks/letters/done/draft-landlord.json").exists()
    at(ALPHA)
    with pytest.raises(dr.DeskError, match="no lane 'draft-landlord'"):
        dr.report_done("draft-landlord")


def test_a_desk_cannot_hand_out_a_file_another_desks_lane_holds(two):
    at(BETA)
    stolen = BETA_SHEET.replace(f"- {BETA_FILE}", "- records/2025").replace(
        "draft-landlord", "steal")
    with pytest.raises(dr.DeskError, match="which is lane-alpha's at desk 'the-desk'"):
        dr.stamp(BETA_DESK, "steal", home_sheet(two, BETA, "steal", stolen))
    with pytest.raises(dr.DeskError, match="lane-alpha's at desk"):
        dr.own(BETA_DESK, "draft-landlord", ["records/2025/January"], give=True)
    at(ALPHA)
    with pytest.raises(dr.DeskError, match="draft-landlord's at desk 'the-letters-desk'"):
        dr.own(DESK, "lane-alpha", ["letters"], give=True)


# --- the ownership check and the save ---------------------------------------------


def test_each_ownership_check_reads_the_other_desks_files_as_theirs(two):
    work(two)
    for home, mine, other in ((ALPHA, "records/2025/January/Ledger.md", BETA_FILE),
                              (BETA, BETA_FILE, "records/2025/January/Ledger.md")):
        at(home)
        record = dr.require_record()
        by_owner, failures = co.findings(record, dr.changed_since_baseline(record))
        assert failures == []
        assert mine in " ".join(p for k, v in by_owner.items() if k != co.OUTSIDE for p in v)
        theirs = " ".join(by_owner[co.OUTSIDE])
        assert other in theirs
        assert f"coordination/desks/{BETA if home == ALPHA else ALPHA}/" in theirs


def test_a_stray_is_still_a_stray_to_both_desks(two):
    (two / "records/2024/Q1/Summary.md").write_text("stray\n", encoding="utf-8")
    for home in (ALPHA, BETA):
        at(home)
        record = dr.require_record()
        _, failures = co.findings(record, dr.changed_since_baseline(record))
        assert failures == ["records/2024/Q1/Summary.md: NO lane owns this file"]


def test_the_launch_record_is_saved_by_whichever_desk_holds_it(homes):
    at(BETA)
    dr.open_desk(BETA_DESK, "the landlord letter", inherit=False)
    (homes / "coordination/launch_record.jsonl").write_text("{}\n", encoding="utf-8")
    record = dr.require_record()
    by_owner, failures = co.findings(record, dr.changed_since_baseline(record))
    assert failures == [] and "coordination/launch_record.jsonl" in by_owner["desk"]


def test_each_desk_saves_its_own_and_leaves_the_other_alone(two):
    work(two)
    at(BETA)
    dr.record_close("draft-landlord")
    assert ds.save(BETA_DESK, "the landlord letter", push=False) == 0
    files = out(two, "show", "--name-only", "--format=", "HEAD").split("\n")
    assert BETA_FILE in files
    assert any(f.startswith("coordination/desks/letters/closed/") for f in files)
    assert "records/2025/January/Ledger.md" not in files
    assert not any(f.startswith("coordination/desks/statements/") for f in files)
    assert (two / "coordination/desks/statements/desk_record.json").exists()
    at(ALPHA)
    dr.record_close("lane-alpha")
    assert ds.save(DESK, "a year of statements", push=False) == 0
    files = out(two, "show", "--name-only", "--format=", "HEAD").split("\n")
    assert "records/2025/January/Ledger.md" in files
    assert not any("desks/letters" in f for f in files)
    assert out(two, "status", "--porcelain") == ""


def test_a_save_whose_commit_fails_puts_the_desk_back(two, capsys):
    """Another desk committing in the same moment holds git's index.lock."""
    work(two)
    at(BETA)
    dr.record_close("draft-landlord")
    lock = two / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    try:
        assert ds.save(BETA_DESK, "the landlord letter", push=False) == 2
    finally:
        lock.unlink()
    assert "record restored" in capsys.readouterr().err
    assert dr.require_record()["desk"] == BETA_DESK
    assert not list((two / "coordination/desks/letters/closed").iterdir())
    assert ds.save(BETA_DESK, "the landlord letter", push=False) == 0


# --- the opener -------------------------------------------------------------------


def test_the_opener_hands_its_home_to_the_lane_window(monkeypatch):
    monkeypatch.setenv(dr.HOME_ENV, BETA)
    window = ot.window_for("lane", "draft-landlord",
                           "coordination/desks/letters/task_sheets/draft-landlord.md",
                           "opus", resume=False)
    assert (dr.HOME_ENV, BETA) in window.env
    monkeypatch.delenv(dr.HOME_ENV)
    window = ot.window_for("lane", "lane-alpha", "x.md", "opus", resume=False)
    assert all(name != dr.HOME_ENV for name, _ in window.env)


def test_a_desk_cannot_close_another_desks_lane(two):
    at(ALPHA)
    for abandoned in (None, "gone quiet"):
        with pytest.raises(ot.TerminalError, match="lane of desk 'the-letters-desk'"):
            ot.require_a_safe_close("draft-landlord", {"status": "idle"}, abandoned)
    at(BETA)
    ot.require_a_safe_close("draft-landlord", {"status": "idle"}, "gone quiet")


# --- the wrapper, and the skill that uses it ----------------------------------------


def test_the_wrapper_runs_a_desk_tool_under_the_home():
    cmd, env = dh.command(BETA, "desk_record.py", ["show"])
    assert env[dr.HOME_ENV] == BETA
    assert Path(cmd[1]).name == "desk_record.py" and cmd[2:] == ["show"]


@pytest.mark.parametrize("home, tool", [
    ("Nola Sweets", "desk_record.py"),
    ("", "desk_record.py"),
    (BETA, "check_docs.py"),
])
def test_the_wrapper_refuses_a_bad_home_or_a_tool_that_is_not_a_desk_tool(home, tool):
    with pytest.raises(ValueError):
        dh.command(home, tool, [])


def test_the_wrapper_really_runs_the_tool_there():
    """End to end in a fresh process: the tool reads the home from the environment."""
    said = subprocess.run([sys.executable, str(Path(dh.__file__)), "nobody-home-here",
                           "desk_record.py", "show"], capture_output=True, text=True,
                          check=False)
    assert said.returncode == 2
    assert "no desk record in coordination/desks/nobody-home-here/" in said.stderr


def test_the_desk_skill_names_no_bare_desk_command():
    """Every desk command in the desk's workflow runs through its home: a bare
    one would read `coordination/`, where no new desk opens."""
    text = (ROOT / "skills/desk/SKILL.md").read_text(encoding="utf-8")
    tools = "|".join(re.escape(t) for t in dh.DESK_TOOLS)
    bare = re.findall(rf"<venv python> scripts/(?:{tools})", text)
    assert bare == [], bare
    assert "<home run>" in text and "scripts/desk_home.py <home>" in text
