"""Tests for scripts/lane_budget.py: a lane is sized before it opens, and the
predictor is measured on this project's own closed lanes.

Every sheet, read and transcript is written under tmp_path; nothing reads the
project's real desks or the owner's real transcripts.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import context_meter as cm
import desk_record as dr
import lane_budget as lb

from test_desk_record import repo  # noqa: F401  (pytest fixture)


def sheet_text(lane="lane-alpha", reason="research", reads=("sources/a.md",)):
    return (f"# Task sheet: {lane}\nunit: one question\nreason: {reason}\nowns:\n"
            f"- Working/{lane}\nreads:\n" + "".join(f"- {r}\n" for r in reads)
            + "task:\nAnswer it.\ndone:\n`python scripts/check.py` exits 0\n")


def put(root, rel, size):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


# --- the prediction ---------------------------------------------------------------


def test_a_prediction_is_the_reasons_line_over_the_bytes_named(tmp_path):
    put(tmp_path, "sources/a.md", 1_000)
    got = lb.estimate(sheet_text(), tmp_path)
    intercept, rate = lb.DEFAULT_COEFFICIENTS
    assert got.total_bytes == 1_000 and got.tokens == round(intercept + rate * 1_000)


def test_a_folder_counts_every_file_under_it_and_a_file_counts_once(tmp_path):
    put(tmp_path, "sources/a.md", 100)
    put(tmp_path, "sources/deep/b.md", 50)
    got = lb.estimate(sheet_text(reads=("sources", "sources/a.md", "sources/deep/b.md")), tmp_path)
    assert got.total_bytes == 150


def test_design_latitude_and_prescribed_keep_their_own_fit_until_calibrated():
    assert lb.coefficients("design-latitude") == (250_000, 0.36)
    assert lb.coefficients("prescribed") == (125_000, 0.52)
    assert lb.coefficients("research") == lb.DEFAULT_COEFFICIENTS
    assert lb.UNTIL_CALIBRATED == {"design-latitude", "prescribed"}


def test_the_refit_whole_read_line_is_the_one_measured_here():
    # `--calibrate` of data-design and data-model, 2026-11-02 (kb/lane-context-sizing.md).
    assert lb.DEFAULT_COEFFICIENTS == (100_000, 1.06)
    assert lb.tokens_for("drafting", 169_738) == 279_922, "plan-write, measured 290,077"


def test_a_sheet_under_the_budget_has_no_problem_and_one_over_is_refused(tmp_path):
    put(tmp_path, "sources/a.md", 400_000)
    assert lb.budget_problem(sheet_text(), tmp_path) is None
    put(tmp_path, "sources/a.md", 500_000)
    said = lb.budget_problem(sheet_text(), tmp_path)
    assert "600,000" in said and "500,000 bytes" in said and "Remedy: split the unit" in said
    assert "sources/a.md" in said, "it names what the lane reads, largest first"


def test_the_stamp_refuses_a_lane_predicted_past_the_budget(repo):  # noqa: F811
    # SHEET is design-latitude: 250,000 + 0.36 x 1,000,000 = 610,000.
    put(repo, "sources/statement_3.md", 1_000_000)
    from test_desk_record import SHEET
    problems = " | ".join(dr.sheet_problems(SHEET, repo))
    assert "predicted to peak at" in problems and "split the unit" in problems
    put(repo, "sources/statement_3.md", 10)
    assert dr.sheet_problems(SHEET, repo) == []


def test_the_command_line_exits_1_over_the_budget_and_names_each_read(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lb, "REPO", tmp_path)
    put(tmp_path, "sources/a.md", 700_000)
    (tmp_path / "s.md").write_text(sheet_text(reads=("sources/a.md", "sources/gone.md")),
                                   encoding="utf-8")
    assert lb.main(["s.md"]) == 1
    out = capsys.readouterr().out
    assert "OVER BUDGET" in out and "the kit default until --calibrate runs here" in out
    assert "not on disk, counted 0: sources/gone.md" in out


def test_sheets_or_calibrate_never_both_nor_neither():
    with pytest.raises(SystemExit):
        lb.main([])
    with pytest.raises(SystemExit):
        lb.main(["a.md", "--calibrate", "home"])


# --- the refit convention ------------------------------------------------------------


def points(*rows):
    return [lb.Point(f"l{n}", "research", b, 0, m) for n, (b, m) in enumerate(rows)]


def test_least_squares_on_a_straight_line_is_that_line():
    line = lb.least_squares(points((0, 100_000), (100_000, 200_000), (200_000, 300_000)))
    assert line == pytest.approx((100_000, 1.0))


def test_too_few_lanes_place_no_refit():
    assert lb.refit(points(*[(n * 1_000, 100_000) for n in range(lb.MIN_REFIT_LANES - 1)])) is None


def test_the_refit_rounds_up_and_holds_the_drift_line():
    pts = points((10_000, 110_000), (20_000, 120_000), (30_000, 130_000),
                 (40_000, 140_000), (50_000, 150_000), (60_000, 500_000))
    intercept, rate = lb.refit(pts)
    assert intercept % lb.INTERCEPT_STEP == 0
    assert all(p.measured - (intercept + rate * p.bytes_read) <= lb.DRIFT_TOKENS for p in pts)


def test_the_refit_reproduces_the_recorded_calibration():
    measured = [(15_178, 62_007), (120_227, 255_030), (198_123, 233_255), (146_145, 215_007),
                (189_477, 270_316), (169_738, 290_077), (129_959, 258_928)]
    assert lb.refit(points(*measured)) == (100_000, 1.06)


# --- calibration on a desk home --------------------------------------------------------


def transcript(folder, sid, lane, sheet, peak):
    folder.mkdir(parents=True, exist_ok=True)
    entries = [{"type": "user", "timestamp": "2026-11-02T19:00:00Z",
                "message": {"content": "<command-name>/lane</command-name>\n"
                                       f"<command-args>{lane} {sheet}</command-args>"}},
               {"type": "assistant", "message": {"usage": {
                   "input_tokens": 1, "cache_read_input_tokens": peak - 1,
                   "cache_creation_input_tokens": 0}}}]
    (folder / f"{sid}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in entries),
                                         encoding="utf-8")


@pytest.fixture
def homes(tmp_path, monkeypatch):
    """A closed home (its sheets moved under closed/<stamp>/) and a live one."""
    folder = tmp_path / "transcripts"
    monkeypatch.setattr(cm, "PROJECT_DIR", folder)
    put(tmp_path, "sources/a.md", 10_000)
    closed = tmp_path / "coordination/desks/old/closed/2026-11-02_114854"
    (closed / "task_sheets").mkdir(parents=True)
    (closed / "task_sheets/lane-a.md").write_text(
        sheet_text("lane-a", reads=("sources/a.md", "coordination/desks/old/desk_log.md")),
        encoding="utf-8")
    put(closed, "desk_log.md", 2_000)   # moved by the save; priced at its copy
    (closed / "desk_record.json").write_text(json.dumps({"lanes": {"lane-a": {
        "sheet": "coordination/desks/old/task_sheets/lane-a.md"}}}), encoding="utf-8")
    transcript(folder, "s-a", "lane-a", "coordination/desks/old/task_sheets/lane-a.md", 150_000)
    # Another desk's window of the same lane name is never this lane's.
    transcript(folder, "s-other", "lane-a", "coordination/desks/elsewhere/task_sheets/lane-a.md",
               900_000)
    live = tmp_path / "coordination/desks/new"
    (live / "task_sheets").mkdir(parents=True)
    for name, closed_at in (("lane-b", {"at": "x"}), ("lane-c", None)):
        (live / f"task_sheets/{name}.md").write_text(sheet_text(name), encoding="utf-8")
    (live / "desk_record.json").write_text(json.dumps({"lanes": {
        "lane-b": {"sheet": "coordination/desks/new/task_sheets/lane-b.md", "closed": {"at": "x"}},
        "lane-c": {"sheet": "coordination/desks/new/task_sheets/lane-c.md", "closed": None}}}),
        encoding="utf-8")
    transcript(folder, "s-b", "lane-b", "coordination/desks/new/task_sheets/lane-b.md", 400_000)
    return tmp_path


def test_each_closed_lane_is_measured_in_its_own_window(homes):
    lines, drift, uncited = lb.calibrate_lines(
        [homes / "coordination/desks/old", homes / "coordination/desks/new"], homes)
    text = "\n".join(lines)
    a = next(line for line in lines if line.startswith("lane-a"))
    assert "12,000" in a, "the moved desk log is sized at its copy under closed/"
    assert "150,000" in a and "900,000" not in a
    assert "still open, not measured" in text and "lane-c" in text
    assert drift == ["lane-b"] and uncited == ["lane-b"]
    assert "DRIFT lane-b" in text and "not cited" in text


def test_a_drift_cited_in_the_sizing_entry_passes(homes, monkeypatch, capsys):
    monkeypatch.setattr(lb, "REPO", homes)
    put(homes, "kb/lane-context-sizing.md", 0)
    assert lb.main(["--calibrate", "coordination/desks/old", "coordination/desks/new"]) == 1
    (homes / "kb/lane-context-sizing.md").write_text("calibrate lane-b: it read the save",
                                                     encoding="utf-8")
    assert lb.main(["--calibrate", "coordination/desks/old", "coordination/desks/new"]) == 0
    assert "PASS - 1 DRIFT lane(s), every one cited" in capsys.readouterr().out


def test_a_closed_lane_with_no_window_is_unreadable_not_a_number(homes):
    (homes / "transcripts/s-a.jsonl").unlink()
    lines, _, _ = lb.calibrate_lines([homes / "coordination/desks/old"], homes)
    assert any(line.startswith(f"{lb.UNREADABLE}lane-a") for line in lines)


def test_a_home_that_is_not_there_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "REPO", tmp_path)
    assert lb.main(["--calibrate", "coordination/desks/none"]) == 2
