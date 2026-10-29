"""Tests for scripts/desk_record.py and scripts/check_ownership.py.

Ported 2026-09-24 from FACOWORK with its fixtures, by way of HAZELHURST into
the Starter Kit: the `records/...` and `sources/...` paths are
arbitrary files in a throwaway repo, not this project's folders. Kit-owned,
so no project's own reason tokens appear: the sheet names `design-latitude`,
which every project carries, and the source rule is tested against a tokens
table written for the test.

FACOWORK's reconciliation build, slice 2. Everything runs in a throwaway git repository
under tmp_path; nothing here reads or writes the project's own record.
"""
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_ownership as co
import desk_record as dr
import open_terminal as ot
import project_identity as pi

#: This machine's project interpreter, as a sheet's `done:` line names it.
VENV = pi.venv_python_rel()

DESK = "the-desk"

SHEET = """# Task sheet: lane-alpha
unit: the first quarter
reason: design-latitude
owns:
- records/2025/January
- records/2025/February/
reads:
- sources/statement_3.md
task:
Compare every entry in the unit against the source statement and draft the fix text.
done:
`python scripts/verify_figures.py report.md` exits 0
"""


def git(repo, *args):
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)


REAL_RUN = dr.run_done_command
REAL_RESOLVE = dr.resolve_program

#: What `report-done` would have run, in the stand-in workspace.
DONE_RUNS: list[list[str]] = []


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A clean git repository standing in for the workspace. `report-done`'s
    runner is a stand-in: every program is found and exits 0 with `ok`, and
    `DONE_RUNS` lists what would have run. A test of the real runner calls
    `real_runner(monkeypatch)`."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    for rel in ("sources/statement_3.md", "records/2025/January/Ledger.md",
                "records/2025/February/Ledger.md", "records/2024/Q1/Summary.md", "kb/some-digest.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "start")
    monkeypatch.setattr(dr, "REPO", tmp_path)
    for attr, where in (("RECORD", "desk_record.json"), ("DONE_DIR", "done"),
                        ("DESK_LOG", "desk_log.md"), ("CLOSED_DIR", "closed")):
        monkeypatch.setattr(dr, attr, tmp_path / "coordination" / where)
    DONE_RUNS.clear()
    monkeypatch.setattr(dr, "resolve_program", lambda program, where: str(where / program))
    monkeypatch.setattr(dr, "run_done_command",
                        lambda argv, cwd: (DONE_RUNS.append(list(argv)), (0, "ok\n"))[1])
    return tmp_path


def real_runner(monkeypatch):
    """The real done shell, with this machine's project interpreter found as
    the one running these tests (the stand-in workspace has no venv)."""
    def resolve(program, where):
        if program == VENV:
            return sys.executable
        return REAL_RESOLVE(program, where)
    monkeypatch.setattr(dr, "resolve_program", resolve)
    monkeypatch.setattr(dr, "run_done_command", REAL_RUN)


def sheet(repo, name="lane-alpha", text=SHEET):
    path = repo / "coordination" / "task_sheets" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return f"coordination/task_sheets/{name}.md"


@pytest.fixture
def desk(repo):
    dr.open_desk(DESK, "a test job", inherit=False)
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    return repo


# --- the sheet a lane could not finish is refused at the stamp ----------------


def problems(text, repo):
    return " | ".join(dr.sheet_problems(text, repo))


def test_a_good_sheet_has_no_problems(repo):
    assert dr.sheet_problems(SHEET, repo) == []


@pytest.mark.parametrize("unit", [
    "the first quarter and the second quarter",
    "January, February",
    "January; February",
    "January + February",
])
def test_a_sheet_naming_more_than_one_unit_is_refused(repo, unit):
    text = SHEET.replace("unit: the first quarter", "unit: " + unit)
    assert "more than one unit" in problems(text, repo)


@pytest.mark.parametrize("unit", [
    "the first quarter (January, February and March)",
    "the scripts-gates family (lift; landed-once + window (all three stages))",
    "the first quarter --- the one the statement names first",
    "the first quarter — January first",
    "the first quarter -- as the module groups it",
])
def test_an_aside_or_a_dash_is_one_unit(repo, unit):
    """S3 build: the stamp refused one-unit sheets over the commas inside an
    aside. What is in parentheses describes the unit; a dash glosses it."""
    text = SHEET.replace("unit: the first quarter", "unit: " + unit)
    assert "more than one unit" not in problems(text, repo)


@pytest.mark.parametrize("unit", [
    "the first quarter (January), February",
    "January (the deposits) and February (the refunds)",
    "the first quarter --- January; February",
    "the first quarter (unclosed, aside",
])
def test_a_joiner_outside_the_parentheses_still_refuses(repo, unit):
    text = SHEET.replace("unit: the first quarter", "unit: " + unit)
    assert "more than one unit" in problems(text, repo)


def with_done(line):
    return SHEET.split("done:")[0] + "done:\n" + line + "\n"


@pytest.mark.parametrize("line", [
    VENV + " -m pytest",
    VENV + " -m pytest -q",
    VENV + " -m pytest tests",
    VENV + " -m pytest tests/ -q -p no:cacheprovider",
    "`pytest -q`",
    "pytest -k landed_once",
])
def test_a_done_that_runs_the_whole_suite_is_refused_and_says_why(repo, line):
    said = problems(with_done(line), repo)
    assert "runs the whole test suite" in said
    assert "every other lane's breakage" in said


@pytest.mark.parametrize("line", [
    VENV + " -m pytest tests/test_lane_guard.py -q",
    VENV + " -m pytest tests/test_a.py tests/test_b.py -q -p no:cacheprovider",
    "`pytest tests\\test_lane_guard.py::test_a_lane_may_look`",
    VENV + " -m pytest tests/fixtures_dir -q",
])
def test_a_done_that_names_its_test_files_passes(repo, line):
    assert "whole test suite" not in problems(with_done(line), repo)


def test_only_the_whole_suite_line_is_named(repo):
    done = (VENV + " -m pytest tests/test_x.py -q\n" + VENV + " -m pytest -q\n")
    said = problems(with_done(done), repo)
    assert said.count("runs the whole test suite") == 1
    assert f"`{VENV} -m pytest -q`" in said


#: SHEET's `owns:` as the stamp records them, and the gate line scoped to them.
OWNS = "records/2025/January records/2025/February"
GATE = f"{VENV} scripts/check_docs.py"


@pytest.mark.parametrize("line", [
    GATE,
    f"{GATE} --report",
    f"`{GATE}` exits 0",
    f"{VENV} scripts/check_docs.py --only",
])
def test_a_done_that_runs_the_document_gate_unscoped_is_refused_and_names_the_remedy(repo, line):
    said = problems(with_done(line), repo)
    assert "runs the document gate on the whole tree" in said
    assert f"`{GATE} --only {OWNS}`" in said
    assert "the whole-tree gate runs at the desk's save" in said


@pytest.mark.parametrize("line, named", [
    (f"{GATE} --only {OWNS} kb/some-digest.md", "kb/some-digest.md"),
    (f"{GATE} --only records/2025 records/2025/January", "records/2025"),
    (f"{GATE} --only=records/2024/Q1 --only {OWNS}", "records/2024/Q1"),
])
def test_an_only_path_the_sheet_does_not_own_is_refused(repo, line, named):
    said = problems(with_done(line), repo)
    assert f"names {named}, which the sheet's `owns:` does not list" in said
    assert f"`{GATE} --only {OWNS}`" in said


def test_an_only_that_leaves_out_an_owned_path_is_refused(repo):
    said = problems(with_done(f"{GATE} --only records/2025/January"), repo)
    assert "leaves out records/2025/February, which the sheet owns" in said


@pytest.mark.parametrize("line", [
    f"{GATE} --only {OWNS}",
    f"{GATE} --only records/2025/February/ ./records/2025/January --report",
    f"{GATE} --only records/2025/January/Ledger.md --only records/2025/January records/2025/February",
    f"{GATE} --only=records/2025/January --only=records/2025/February",
    f"`{GATE} --only {OWNS}` exits 0",
])
def test_a_gate_scoped_to_the_sheets_owns_passes(repo, line):
    assert dr.sheet_problems(with_done(line), repo) == []


def test_a_gate_command_the_done_shell_refuses_is_named_once(repo):
    """A gate run `report-done` refuses on other grounds is named once, not twice."""
    said = problems(with_done(f"{GATE} | tail -3"), repo)
    assert "a pipe" in said and "document gate" not in said


def test_two_unit_lines_are_two_units(repo):
    assert "`unit:` appears more than once" in problems(SHEET + "unit: another\n", repo)


def test_a_sheet_naming_no_files_is_refused(repo):
    text = SHEET.replace("- records/2025/January\n- records/2025/February/\n", "- \n")
    assert "`owns:`" in problems(text, repo)


def test_a_done_that_is_prose_is_refused(repo):
    text = SHEET.split("done:")[0] + "done:\nthe text reads correctly\n"
    assert "names no runnable command" in problems(text, repo)


@pytest.fixture
def source_tokens(tmp_path, monkeypatch):
    """A tokens table written for the test: two jobs that read a source
    document and one that does not, beside the two universal rows."""
    path = tmp_path / "reason_tokens.json"
    rows = {
        "prescribed": ("sonnet", False), "design-latitude": ("opus", False),
        "reading": ("opus", True), "copying": ("sonnet", True),
        "routing": ("sonnet", False),
    }
    path.write_text(json.dumps({"tokens": {
        token: {"model": model, "job": "a job", "reads_source": source}
        for token, (model, source) in rows.items()}}), encoding="utf-8")
    reasons, sources = ot.reason_tables(ot.load_reasons(path))
    monkeypatch.setattr(ot, "REASONS", reasons)
    monkeypatch.setattr(ot, "SOURCE_REASONS", sources)
    return sources


def test_a_source_sheet_that_reads_only_a_digest_is_refused(repo, source_tokens):
    assert source_tokens == ("reading", "copying")
    text = SHEET.replace("- sources/statement_3.md", "- kb/some-digest.md")
    for reason in source_tokens:
        sheet_text = text.replace("reason: design-latitude", "reason: " + reason)
        assert "SOURCE document" in problems(sheet_text, repo)
        with_source = sheet_text.replace(
            "- kb/some-digest.md", "- kb/some-digest.md\n- sources/statement_3.md")
        assert "SOURCE document" not in problems(with_source, repo)
    for reason in ("routing", "design-latitude"):
        other = text.replace("reason: design-latitude", "reason: " + reason)
        assert "SOURCE document" not in problems(other, repo)


def test_the_source_rule_follows_the_projects_file(repo):
    """Whatever this project's file marks `reads_source`, and nothing else."""
    text = SHEET.replace("- sources/statement_3.md", "- kb/some-digest.md")
    for reason, (_, _) in ot.REASONS.items():
        said = problems(text.replace("reason: design-latitude", "reason: " + reason), repo)
        assert ("SOURCE document" in said) == (reason in ot.SOURCE_REASONS), reason


def test_an_opener_that_will_not_load_is_a_desk_refusal(monkeypatch):
    """The stamp reads the tokens through the opener, which refuses a bad
    tokens file at import; that reaches the desk as a DeskError."""
    monkeypatch.setitem(sys.modules, "open_terminal", None)  # the import now fails
    with pytest.raises(dr.DeskError):
        dr.reason_lists()


def test_a_bad_tokens_file_stops_the_stamp_with_exit_2(repo, monkeypatch, capsys):
    def broken():
        raise dr.DeskError("scripts/reason_tokens.json: is not JSON")
    monkeypatch.setattr(dr, "reason_lists", broken)
    dr.open_desk(DESK, "job", inherit=False)
    assert dr.main(["stamp", "lane-alpha", sheet(repo), "--desk", DESK]) == 2
    assert "reason_tokens.json" in capsys.readouterr().err
    assert "lane-alpha" not in dr.read_record()["lanes"]


def test_a_read_that_is_not_on_disk_is_refused(repo):
    text = SHEET.replace("statement_3.md", "statement_99.md")
    assert "statement_99.md does not exist" in problems(text, repo)


@pytest.mark.parametrize("bad", ["C:/Users/x", "/etc", "../elsewhere", ".", ".git/config"])
def test_a_path_outside_the_project_is_refused(bad):
    with pytest.raises(dr.DeskError):
        dr.clean_path(bad)


def test_a_lane_cannot_be_given_the_desks_folder(repo):
    text = SHEET.replace("- records/2025/January\n", "- coordination/task_sheets\n")
    assert "desk's own folder" in problems(text, repo)


def test_an_unknown_reason_is_refused(repo):
    assert "not on the launcher's list" in problems(
        SHEET.replace("reason: design-latitude", "reason: cheap"), repo)


def test_a_refused_stamp_writes_nothing(repo):
    dr.open_desk(DESK, "job", inherit=False)
    with pytest.raises(dr.DeskError, match="Nothing was stamped"):
        dr.stamp(DESK, "lane-alpha", sheet(repo, text=SHEET.replace("done:", "finish:")))
    assert "lane-alpha" not in dr.read_record()["lanes"]


# --- a template marker left in a path is refused ------------------------------

#: The line that reached the record in the measured incident: a template's note
#: to the desk, still on an `owns:` line, recorded as part of the path -- so the
#: lane's real file was owned by nobody until the end-of-job ownership check.
MARKER_LINE = ("work/2025/reports/january-apply.md (only when a block edits an "
               "Arc shard; the desk deletes this line when no block does)")
MARKER_SAID = "a template placeholder or marker was left in"
MARKER_REMEDY = "Fill it in with the real path, or delete the line"


def sheet_with(field, line):
    """SHEET with one more `- line` under `owns:` or `reads:`."""
    anchor = {"owns": "- records/2025/January\n",
              "reads": "- sources/statement_3.md\n"}[field]
    return SHEET.replace(anchor, f"{anchor}- {line}\n")


@pytest.mark.parametrize("field", ["owns", "reads"])
def test_a_marker_left_on_a_line_is_refused_and_the_line_is_named(repo, field):
    line = MARKER_LINE if field == "owns" else (
        "skills/reconciliation/shard_backfill.md (only when a block edits an Arc "
        "shard; the desk deletes this line when no block does)")
    said = problems(sheet_with(field, line), repo)
    assert f"{field}: `- {line}`" in said
    assert MARKER_SAID in said and MARKER_REMEDY in said


def test_a_marker_on_a_reads_line_is_not_refused_as_a_missing_file(repo):
    """The `reads:` marker used to be refused only because its text was not on
    disk. Refused for what it IS, the message says so and not "does not exist"."""
    said = problems(sheet_with("reads", "notes/<the unit's own folder> (only when x)"), repo)
    assert MARKER_SAID in said
    assert "does not exist" not in said


def test_a_marker_on_a_file_that_exists_is_refused_all_the_same(repo):
    """Not refused by accident: the file is there, and the marker still is not a path."""
    (repo / "notes (old).md").write_text("x\n", encoding="utf-8")
    said = problems(sheet_with("reads", "notes (old).md"), repo)
    assert "reads: `- notes (old).md`" in said and MARKER_SAID in said


@pytest.mark.parametrize("field", ["owns", "reads"])
@pytest.mark.parametrize("line", [
    "<run>/<year>/reports/<lane>.md",      # an unfilled template placeholder
    "records/<year>/January",          # half of one filled
    "records/2025/January (a note)",
    "records/2025/January(",
    "records/2025/January)",
    "records/2025/January<",
    "records/2025/January>",
])
def test_every_marker_character_is_refused_on_both_lists(repo, field, line):
    said = problems(sheet_with(field, line), repo)
    assert f"{field}: `- {line}`" in said and MARKER_SAID in said
    assert "does not exist" not in said


def test_a_refused_marker_names_each_character_it_found(repo):
    said = problems(sheet_with("owns", "<run>/<year>/reports/<lane>.md (only when)"), repo)
    assert "carries `(`, `)`, `<`, `>`:" in said


def test_a_marker_on_an_owns_line_is_never_recorded_as_a_path(repo):
    dr.open_desk(DESK, "job", inherit=False)
    with pytest.raises(dr.DeskError, match=MARKER_SAID) as caught:
        dr.stamp(DESK, "lane-alpha", sheet(repo, text=sheet_with("owns", MARKER_LINE)))
    assert "Nothing was stamped" in str(caught.value)
    assert "lane-alpha" not in dr.read_record()["lanes"]


def test_a_sheet_with_the_marker_deleted_and_the_paths_real_still_stamps(repo):
    """The corrected form of the incident's sheet: the note gone, the path real."""
    (repo / "skills/reconciliation").mkdir(parents=True)
    (repo / "skills/reconciliation/shard_backfill.md").write_text("x\n", encoding="utf-8")
    text = sheet_with("owns", "work/2025/reports/january-apply.md").replace(
        "- sources/statement_3.md\n",
        "- sources/statement_3.md\n- skills/reconciliation/shard_backfill.md\n")
    assert dr.sheet_problems(text, repo) == []
    dr.open_desk(DESK, "job", inherit=False)
    dr.stamp(DESK, "lane-alpha", sheet(repo, text=text))
    assert dr.read_record()["lanes"]["lane-alpha"]["owns"] == [
        "records/2025/January", "work/2025/reports/january-apply.md",
        "records/2025/February"]


@pytest.mark.parametrize("path", [MARKER_LINE, "work/2025/reports/<lane>.md", "a).md"])
def test_own_refuses_a_marker_and_records_nothing(desk, path):
    before = dr.read_record()["lanes"]["lane-alpha"]["owns"]
    with pytest.raises(dr.DeskError, match=MARKER_SAID) as caught:
        dr.own(DESK, "lane-alpha", ["records/2024/Q1", path], give=True)
    assert "Give the real path" in str(caught.value)
    assert "Nothing was changed" in str(caught.value)
    assert dr.read_record()["lanes"]["lane-alpha"]["owns"] == before  # the clean path too


def test_own_still_gives_a_clean_path(desk):
    dr.own(DESK, "lane-alpha", ["work/2025/reports/january-apply.md"], give=True)
    assert "work/2025/reports/january-apply.md" in dr.read_record()["lanes"]["lane-alpha"]["owns"]


def test_a_marker_that_already_reached_the_record_can_still_be_taken_back_out(desk):
    """Why the refusal is not in `clean_path`: `disown` runs paths through it, and
    the desk must be able to remove the very line this refusal exists to stop."""
    record = dr.read_record()
    record["lanes"]["lane-alpha"]["owns"].append(MARKER_LINE)
    dr.write_record(record)
    dr.own(DESK, "lane-alpha", [MARKER_LINE], give=False)
    assert MARKER_LINE not in dr.read_record()["lanes"]["lane-alpha"]["owns"]


def test_the_command_line_refuses_a_marker_with_exit_2(repo, capsys):
    dr.open_desk(DESK, "job", inherit=False)
    text = sheet_with("owns", MARKER_LINE)
    sheet(repo, text=text)
    assert dr.main(["stamp", "lane-alpha", "coordination/task_sheets/lane-alpha.md",
                    "--desk", DESK]) == 2
    err = capsys.readouterr().err
    assert MARKER_SAID in err and MARKER_REMEDY in err and "Nothing was stamped" in err
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    assert dr.main(["own", "lane-alpha", "scripts/<x>.py", "--desk", DESK]) == 2
    assert MARKER_SAID in capsys.readouterr().err


# --- the stamp gives the lane its files ---------------------------------------


def test_the_stamp_is_the_grant(desk):
    row = dr.read_record()["lanes"]["lane-alpha"]
    assert row["owns"] == ["records/2025/January", "records/2025/February"]
    assert (row["unit"], row["reason"]) == ("the first quarter", "design-latitude")
    assert dr.stamped_sheet_problem(dr.read_record(), "lane-alpha") is None


def test_only_the_desk_on_file_writes_the_record(desk):
    with pytest.raises(dr.DeskError, match="is not the desk"):
        dr.stamp("lane-alpha", "lane-alpha", "coordination/task_sheets/lane-alpha.md")
    with pytest.raises(dr.DeskError, match="is not the desk"):
        dr.own("some-lane", "lane-alpha", ["scripts/x.py"], give=True)


def test_two_lanes_cannot_own_one_file_nor_one_inside_the_other(desk):
    inside = SHEET.replace("- records/2025/February/\n", "").replace(
        "2025/January", "2025/January/Ledger.md")
    with pytest.raises(dr.DeskError, match="overlaps records/2025/January"):
        dr.stamp(DESK, "other", sheet(desk, "other", inside))
    above = inside.replace("2025/January/Ledger.md", "2025")
    with pytest.raises(dr.DeskError, match="two lanes cannot own one file"):
        dr.stamp(DESK, "other", sheet(desk, "other", above))
    with pytest.raises(dr.DeskError, match="two lanes"):
        dr.own(DESK, "desk", ["records/2025/January/Ledger.md"], give=True)


def test_own_and_disown_change_the_file_and_print_the_line_to_send(desk):
    said = dr.own(DESK, "lane-alpha", ["records/2024/Q1"], give=True)
    assert "[desk] ownership:" in said[-1]
    assert "records/2024/Q1" in dr.read_record()["lanes"]["lane-alpha"]["owns"]
    dr.own(DESK, "lane-alpha", ["records/2024/Q1"], give=False)
    assert "records/2024/Q1" not in dr.read_record()["lanes"]["lane-alpha"]["owns"]
    with pytest.raises(dr.DeskError, match="does not own"):
        dr.own(DESK, "lane-alpha", ["records/2024/Q1"], give=False)


def test_a_second_desk_is_refused_and_a_replacement_inherits(desk):
    with pytest.raises(dr.DeskError, match="already on file"):
        dr.open_desk("new-desk", "job", inherit=False)
    dr.open_desk("new-desk", "", inherit=True)
    record = dr.read_record()
    assert record["desk"] == "new-desk" and "lane-alpha" in record["lanes"]
    assert record["inherited"][0]["from"] == DESK


# --- a ruling is on disk before it is routed ----------------------------------


def test_route_writes_the_ruling_then_names_every_lane_it_affects(desk):
    dr.stamp(DESK, "lane-beta", sheet(desk, "lane-beta", SHEET.replace(
        "- records/2025/January\n- records/2025/February/\n",
        "- records/2024/Q1\n").replace("the first quarter", "the 2024 summary")))
    said = dr.route(DESK, ["records/2025/January/Ledger.md", "records/2024"],
                    "the January deposit was a refund → strike it", None)
    assert "the January deposit was a refund → strike it" in dr.DESK_LOG.read_text(encoding="utf-8")
    sends = [line for line in said if "send to" in line]
    assert [line.split()[2].rstrip(":") for line in sends] == ["lane-alpha", "lane-beta"]
    assert all("[desk] correction: the January deposit" in line for line in sends)


def test_a_route_with_no_ruling_is_refused_and_nothing_is_written(desk):
    with pytest.raises(dr.DeskError):
        dr.route(DESK, ["records/2025/January"], "  ", None)
    assert not dr.DESK_LOG.exists()


def test_a_ruling_carries_the_question_it_answers_to_the_log_and_the_lane(desk):
    """A bare "1" means nothing to a lane without the question it answered."""
    said = dr.route(DESK, ["records/2025/January"], "1", None,
                    asked="keep the deposit line — 1 yes, 2 no?")
    assert "Answering: keep the deposit line" in dr.DESK_LOG.read_text(encoding="utf-8")
    sends = [line for line in said if "send to" in line]
    assert sends and all("correction: 1 (answering: keep the deposit line" in line
                         for line in sends)


def test_an_unprompted_ruling_adds_no_question_to_the_lane_line(desk):
    said = dr.route(DESK, ["records/2025/January"], "strike it", None, asked="unprompted")
    assert all("(answering:" not in line for line in said)


def test_an_empty_question_is_refused_and_nothing_is_written(desk):
    with pytest.raises(dr.DeskError):
        dr.route(DESK, ["records/2025/January"], "1", None, asked="  ")
    assert not dr.DESK_LOG.exists()


def test_the_route_act_requires_asked_on_the_command_line():
    with pytest.raises(SystemExit):
        dr.build_parser().parse_args(["route", "records/2025", "--ruling", "1", "--desk", DESK])


def test_done_counts_only_if_said_after_the_lane_was_last_put_to_work(desk):
    row = lambda: dr.read_record()["lanes"]["lane-alpha"]  # noqa: E731
    assert dr.lane_state(row(), "lane-alpha") == "working"
    assert "report-done lane-alpha" in dr.close_problem("lane-alpha")
    dr.report_done("lane-alpha")
    assert dr.lane_state(row(), "lane-alpha") == "reported done"
    assert dr.close_problem("lane-alpha") is None
    dr.route(DESK, ["records/2025/January"], "a correction", None)
    assert dr.lane_state(row(), "lane-alpha") == "working"


def test_reported_done_reads_the_folder_it_is_given_and_not_done_dir(desk):
    """The stage checks read done files from beside the record they were handed,
    so the one rule takes that folder as an argument."""
    row = dr.read_record()["lanes"]["lane-alpha"]
    elsewhere = desk / "elsewhere" / "done"
    elsewhere.mkdir(parents=True)
    said = row["working_since"] + 1
    (elsewhere / "lane-alpha.json").write_text(
        json.dumps({"lane": "lane-alpha", "at": said}), encoding="utf-8")
    # A done only in the given folder: it counts there, and DONE_DIR has none.
    assert dr.reported_done(row, "lane-alpha", done_dir=elsewhere)
    assert not dr.reported_done(row, "lane-alpha")
    assert dr.done_at("lane-alpha", done_dir=elsewhere) == said
    assert dr.done_at("lane-alpha") is None
    assert dr.done_path("lane-alpha", done_dir=elsewhere) == elsewhere / "lane-alpha.json"
    assert dr.done_path("lane-alpha") == dr.DONE_DIR / "lane-alpha.json"
    # A done only in DONE_DIR: it counts by default, and the given folder does not see it.
    (elsewhere / "lane-alpha.json").unlink()
    dr.report_done("lane-alpha")
    assert dr.reported_done(row, "lane-alpha")
    assert not dr.reported_done(row, "lane-alpha", done_dir=elsewhere)


# --- a done and a correction in one clock tick are still in order --------------

#: A clock that never moves, so every act below lands in "the same tick" the way
#: two acts a few milliseconds apart do on Windows, whose clock advances about
#: every 15 ms. Long before now, so a value leaking in from the real clock
#: could not pass for it.
STOPPED_AT = 1_000_000_000.0


@pytest.fixture
def stopped(repo, monkeypatch):
    """A desk whose clock stopped before it opened, so the stamp is in the same
    tick as everything after it."""
    monkeypatch.setattr(dr, "time", types.SimpleNamespace(time=lambda: STOPPED_AT))
    dr.open_desk(DESK, "a test job", inherit=False)
    dr.stamp(DESK, "lane-alpha", sheet(repo))
    return repo


def state():
    return dr.lane_state(dr.read_record()["lanes"]["lane-alpha"], "lane-alpha")


def correct():
    dr.route(DESK, ["records/2025/January"], "a correction", None)


def test_a_done_then_a_correction_in_one_tick_is_not_done(stopped):
    dr.report_done("lane-alpha")
    correct()
    assert state() == "working"
    assert "report-done lane-alpha" in dr.close_problem("lane-alpha")


def test_a_correction_then_a_done_in_one_tick_is_done(stopped):
    correct()
    dr.report_done("lane-alpha")
    assert state() == "reported done"
    assert dr.close_problem("lane-alpha") is None


def test_a_done_a_correction_and_a_second_done_in_one_tick_is_done(stopped):
    dr.report_done("lane-alpha")
    correct()
    dr.report_done("lane-alpha")
    assert state() == "reported done"


def test_a_stamp_then_a_done_in_one_tick_is_done(stopped):
    dr.report_done("lane-alpha")
    assert state() == "reported done"


def test_a_done_then_a_restamp_in_one_tick_is_not_done(stopped):
    dr.report_done("lane-alpha")
    dr.stamp(DESK, "lane-alpha", "coordination/task_sheets/lane-alpha.md")
    assert state() == "working"


def test_the_nudge_is_a_millisecond_and_the_iso_time_stays_real(stopped):
    dr.report_done("lane-alpha")
    said = json.loads(dr.done_path("lane-alpha").read_text(encoding="utf-8"))
    assert 0 < said["at"] - STOPPED_AT <= 0.01
    assert not said["at_iso"].startswith("2001")


def test_a_lane_whose_sheet_changed_cannot_report_done(desk):
    (desk / "coordination" / "task_sheets" / "lane-alpha.md").write_text(
        SHEET + "one more thing", encoding="utf-8")
    with pytest.raises(dr.DeskError, match="changed since the desk stamped it"):
        dr.report_done("lane-alpha")


def test_a_carriage_return_is_not_a_changed_sheet(desk):
    (desk / "coordination" / "task_sheets" / "lane-alpha.md").write_bytes(
        SHEET.replace("\n", "\r\n").encode("utf-8"))
    assert dr.stamped_sheet_problem(dr.read_record(), "lane-alpha") is None


# --- report-done runs the `done:` commands itself -------------------------------


def done_sheet(repo, name, *commands):
    """A sheet whose `done:` is `commands`, one a line, owning a file of its own."""
    text = (with_done("\n".join(commands)).replace("lane-alpha", name)
            .replace("- records/2025/January\n- records/2025/February/\n", "- records/2024/Q1\n"))
    return sheet(repo, name, text)


def test_report_done_runs_each_command_and_writes_the_receipts(desk, monkeypatch):
    real_runner(monkeypatch)
    first = f"{VENV} -c \"print('first line')\""
    second = f"{VENV} -c \"import sys;print('second');print('two', file=sys.stderr)\""
    dr.stamp(DESK, "lane-beta", done_sheet(desk, "lane-beta", first, second))
    said = dr.report_done("lane-beta")
    digest = dr.read_record()["lanes"]["lane-beta"]["sha256"]
    text = dr.receipts_path("lane-beta").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Receipts: lane-beta"
    assert lines[1] == f"sheet: {digest[:12]}"
    assert lines[2].startswith("ran: 20")
    assert text.split("\n", 3)[3] == (f"\n$ {first}\nexit: 0\nfirst line\n"
                                      f"\n$ {second}\nexit: 0\nsecond\ntwo\n")
    assert dr.lane_state(dr.read_record()["lanes"]["lane-beta"], "lane-beta") == "reported done"
    assert said[0] == text.rstrip("\n")                 # printed, not only written
    assert "receipts: coordination/done/lane-beta.receipts.md" in said[-1]
    done = json.loads(dr.done_path("lane-beta").read_text(encoding="utf-8"))
    assert done["receipts"] == "coordination/done/lane-beta.receipts.md"
    assert done["sheet"] == digest[:12]


def test_a_command_that_fails_is_in_the_receipts_and_the_lane_is_not_done(desk, monkeypatch):
    real_runner(monkeypatch)
    good = f"{VENV} -c \"print('fine')\""
    bad = f"{VENV} -c \"import sys;print('broke');sys.exit(3)\""
    dr.stamp(DESK, "lane-beta", done_sheet(desk, "lane-beta", good, bad))
    with pytest.raises(dr.DeskError) as refused:
        dr.report_done("lane-beta")
    said = str(refused.value)
    assert f"$ {bad}\nexit: 3\nbroke\n" in said
    assert "1 of 2 `done:` command(s) did not exit 0" in said and "NOT recorded as done" in said
    assert "exit: 3" in dr.receipts_path("lane-beta").read_text(encoding="utf-8")
    assert not dr.done_path("lane-beta").exists()
    assert "report-done lane-beta" in dr.close_problem("lane-beta")


def test_a_failure_after_an_earlier_done_leaves_the_lane_working(desk, monkeypatch):
    dr.report_done("lane-alpha")
    dr.route(DESK, ["records/2025/January"], "a correction", None)
    monkeypatch.setattr(dr, "run_done_command", lambda argv, cwd: (1, "still wrong\n"))
    with pytest.raises(dr.DeskError, match="NOT recorded as done"):
        dr.report_done("lane-alpha")
    assert state() == "working"


def test_a_program_that_is_not_there_is_not_run_and_fails(desk, monkeypatch):
    real_runner(monkeypatch)
    missing = "C:/nowhere/at/all/python.exe -c \"print(1)\""
    dr.stamp(DESK, "lane-beta", done_sheet(desk, "lane-beta", missing))
    with pytest.raises(dr.DeskError, match="NOT recorded as done"):
        dr.report_done("lane-beta")
    text = dr.receipts_path("lane-beta").read_text(encoding="utf-8")
    assert f"$ {missing}\nexit: 127\n[report-done: not run: no program" in text


def test_the_commands_run_from_the_project_root_unpiped(desk, monkeypatch):
    real_runner(monkeypatch)
    where = f"{VENV} -c \"import os;print(os.getcwd());print('a|b')\""
    dr.stamp(DESK, "lane-beta", done_sheet(desk, "lane-beta", where))
    dr.report_done("lane-beta")
    printed = dr.receipts_path("lane-beta").read_text(encoding="utf-8").splitlines()
    assert Path(printed[-2]).resolve() == desk.resolve()
    assert printed[-1] == "a|b"   # quoted, so an argument: no shell ran


def test_a_correction_after_done_needs_the_commands_to_pass_again(desk):
    dr.report_done("lane-alpha")
    dr.route(DESK, ["records/2025/January"], "a correction", None)
    assert state() == "working"
    runs = len(DONE_RUNS)
    dr.report_done("lane-alpha")
    assert state() == "reported done" and len(DONE_RUNS) == runs + 1


def test_the_dry_run_finds_every_command_and_runs_and_records_nothing(desk):
    said = dr.report_done("lane-alpha", dry=True)
    assert said[0] == "$ python scripts/verify_figures.py report.md"
    assert said[1].startswith("  would run: [") and "verify_figures.py" in said[1]
    assert "nothing was run or recorded" in said[-1]
    assert DONE_RUNS == [] and not dr.receipts_path("lane-alpha").exists()
    assert state() == "working"


def test_a_dry_run_names_a_command_that_would_not_start(desk, monkeypatch):
    real_runner(monkeypatch)
    dr.stamp(DESK, "lane-beta", done_sheet(desk, "lane-beta", "C:/nowhere/python.exe -V"))
    with pytest.raises(dr.DeskError, match="would not run: no program"):
        dr.report_done("lane-beta", dry=True)
    assert dr.main(["report-done", "lane-beta", "--dry-run"]) == 2


def test_the_receipts_are_archived_with_the_desk(desk):
    dr.report_done("lane-alpha")
    dr.record_close("lane-alpha")
    dr.close_desk(DESK)
    assert list(dr.CLOSED_DIR.glob("*/done/lane-alpha.receipts.md"))


@pytest.mark.parametrize("line, said", [
    (f"{VENV} scripts/x.py | tail -3", "a pipe"),
    (f"{VENV} scripts/x.py > out.txt", "a redirect"),
    (f"{VENV} scripts/x.py < in.txt", "a redirect"),
    (f"{VENV} scripts/x.py && {VENV} scripts/y.py", "`&` or `&&`"),
    (f"{VENV} scripts/x.py; git status", "`;`"),
    (f"{VENV} scripts/x.py $HOME", "shell variable"),
    (f"{VENV} scripts/x.py `date`", "a backtick substitution"),
    (".venv\\Scripts\\python.exe scripts/x.py", "backslash outside quotes"),
    (f"{VENV} -c \"print(1)", "quotes do not close"),
    ("git commit -m done", "which a lane never runs"),
    ("git stash", "which a lane never runs"),
])
def test_the_stamp_refuses_a_done_command_the_done_shell_cannot_run(repo, line, said):
    found = problems(with_done(line), repo)
    assert "cannot be run by `report-done` as written" in found and said in found


@pytest.mark.parametrize("line", [
    f"{VENV} -c \"print('a|b; c > d && e')\"",
    f"{VENV} -c \"import re;print(re.findall(r'\\d+ passed', 'x'))\"",
    "git status --short scripts/desk_record.py",
    "git diff --stat -- scripts/",
    f"`{VENV} scripts/check_ownership.py` exits 0 and lists a file",
    f"- {VENV} scripts/check_ownership.py",
])
def test_quoted_shell_characters_and_read_only_git_run(repo, line):
    assert "cannot be run by `report-done`" not in problems(with_done(line), repo)


def test_a_command_named_only_inside_prose_is_refused(repo):
    said = problems(with_done("the lane then runs scripts/check_ownership.py for the desk"), repo)
    assert "names a command only inside prose" in said


def test_prose_lines_are_not_commands_and_a_parenthesized_note_is_prose_throughout():
    done = (f"{VENV} scripts/a.py\n"
            "`the report` names scripts/b.py\n"
            "(a note that opens here, names `make_sheets.py --second`, and runs on\n"
            f"{VENV} scripts/not_a_command.py --in-a-note\n"
            "to the line that closes it. The desk deletes this note)\n"
            f"- {VENV} scripts/c.py\n")
    assert dr.done_commands(done) == [f"{VENV} scripts/a.py", f"{VENV} scripts/c.py"]


@pytest.mark.parametrize("line, token", [
    (f"{VENV} scripts/check_x.py --lane <lane>", "<lane>"),
    (f"{VENV} scripts/check_x.py coordination/desks/<home>/done", "<home>"),
    (f"{VENV} scripts/check_x.py records/S<N>", "<N>"),
    ("<venv python> scripts/check_docs.py", "<venv python>"),
    (f"{VENV} scripts/check_x.py \"records/2025/Report <N>.md\"", "<N>"),
    (f"{VENV} -c \"print(open('records/<YYYY-MM-DD>.md').read())\"", "<YYYY-MM-DD>"),
    ("git diff --stat -- records/<month>/", "<month>"),
])
def test_a_placeholder_left_in_done_is_refused_and_named(repo, line, token):
    said = problems(with_done(line), repo)
    assert "`done:` still carries the template placeholder" in said
    assert token in said


@pytest.mark.parametrize("line", [
    f"{VENV} -c \"import sys;t='abc';sys.exit(0 if len(t)<5 and len(t)>2 else 1)\"",
    f"{VENV} -c \"n=3;m=1;print(n<m and m>0)\"",
    f"{VENV} -c \"t=open('site/index.html',encoding='utf-8').read();"
    "print('<title>' in t and '<b>' in t and '</b>' in t)\"",
    f"{VENV} -c \"t=open('skills/lane/SKILL.md',encoding='utf-8').read();"
    "print('report-done <name>' in t)\"",
])
def test_a_comparison_or_a_tested_string_is_not_a_placeholder(repo, line):
    assert dr.placeholders_left(line) == []
    assert "placeholder" not in problems(with_done(line), repo)


def test_prose_in_a_done_block_is_not_read_for_placeholders(repo):
    done = (f"`{VENV} scripts/verify_figures.py report.md` exits 0\n"
            "(the <home> folder check is the desk's, not a line here)\n")
    assert dr.placeholders_left(done) == []


PROJECT = Path(__file__).resolve().parents[1]

#: Where desks write task sheets, live or archived: `coordination/desks/<home>/task_sheets/`,
#: as the usage lines of desk_record.py and open_terminal.py spell it.
SHEET_GLOB = "coordination/**/task_sheets/*.md"


def test_every_sheet_on_file_would_run_under_the_done_shell(tmp_path):
    """Every task sheet any desk here has written, live or archived, run
    through `report-done`'s dry mode against this project: each command
    splits under the done shell, is not one the stamp refuses, and finds its
    program.

    A project no desk has run in yet (a freshly seeded one) has no sheet on
    file. Then one is planted where a desk writes them, so the glob is still
    proved to reach that layout and its `done:` line still runs against this
    project; wherever a sheet is on file, only the real ones are read."""
    sheets, where = sorted(PROJECT.glob(SHEET_GLOB)), PROJECT
    if not sheets:
        planted = tmp_path / "coordination" / "desks" / "first-job" / "task_sheets" / "lane-alpha.md"
        planted.parent.mkdir(parents=True)
        planted.write_text(SHEET.split("done:\n")[0] + f"done:\n{GATE} --only {OWNS}\n", encoding="utf-8")
        sheets, where = sorted(tmp_path.glob(SHEET_GLOB)), tmp_path
    failures, ran = [], 0
    for path in sheets:
        done = dr.parse_sheet(path.read_text(encoding="utf-8"))[0].get("done", "")
        for command in dr.done_commands(done):
            ran += 1
            argv, why = dr.dry_run(command, PROJECT)
            if why or not Path(argv[0]).is_file():
                failures.append(f"{path.relative_to(where).as_posix()}: {command[:80]} -- {why}")
    assert sheets, "no task sheet on file: the glob, not the sheets, is wrong"
    assert ran, "no done: command read from any sheet: the parse, not the sheets, is wrong"
    assert failures == []


def test_the_desk_closes_only_when_every_lane_has_and_archives_not_deletes(desk):
    with pytest.raises(dr.DeskError, match="lanes not yet closed"):
        dr.close_desk(DESK)
    dr.record_close("lane-alpha")
    dr.close_desk(DESK)
    assert not dr.RECORD.exists()
    kept = list(dr.CLOSED_DIR.glob("*/desk_record.json"))
    assert len(kept) == 1 and list(dr.CLOSED_DIR.glob("*/task_sheets/lane-alpha.md"))


def test_the_command_line_refuses_with_exit_2_and_acts_with_exit_0(desk, capsys):
    assert dr.main(["show"]) == 0
    assert "lane-alpha" in capsys.readouterr().out
    assert dr.main(["own", "lane-alpha", "scripts/x.py"]) == 2
    assert "pass --desk" in capsys.readouterr().err


def test_every_documented_line_parses():
    usage = dr.__doc__.split("Usage", 1)[1].split("WHY THIS EXISTS", 1)[0]
    lines = [l.strip() for l in usage.splitlines() if "scripts/desk_record.py " in l]
    assert len(lines) >= 8
    import shlex
    for line in lines:
        assert line.startswith("<venv python> scripts/"), (
            "a Usage line names one machine's interpreter: " + line)
        dr.build_parser().parse_args(shlex.split(line)[3:])


# --- the ownership check (R22) ------------------------------------------------


def test_it_passes_on_a_clean_tree(desk, capsys):
    assert co.main([]) == 0
    assert "PASS" in capsys.readouterr().out


def test_it_passes_when_each_lane_edited_only_its_own(desk, capsys):
    (desk / "records/2025/January/Ledger.md").write_text("fixed\n", encoding="utf-8")
    (desk / "records/2025/February/New_Entry.md").write_text("new\n", encoding="utf-8")
    assert co.main([]) == 0
    out = capsys.readouterr().out
    assert "lane-alpha: 2 changed file(s)" in out and "desk:" in out


def test_a_planted_stray_edit_fails_and_is_named(desk, capsys):
    (desk / "records/2024/Q1/Summary.md").write_text("stray\n", encoding="utf-8")
    assert co.main([]) == 1
    assert "records/2024/Q1/Summary.md: NO lane owns this file" in capsys.readouterr().err


def test_a_stray_new_file_and_a_stray_deletion_fail_too(desk, capsys):
    (desk / "records/2024/Q1/Planted.md").write_text("new\n", encoding="utf-8")
    (desk / "sources/statement_3.md").unlink()
    assert co.main([]) == 1
    err = capsys.readouterr().err
    assert "Planted.md" in err and "statement_3.md" in err


def test_a_file_owned_twice_in_a_hand_edited_record_fails(desk, capsys):
    record = dr.read_record()
    record["lanes"]["other"] = {"owns": ["records/2025"], "closed": None}
    dr.write_record(record)
    (desk / "records/2025/January/Ledger.md").write_text("fixed\n", encoding="utf-8")
    assert co.main([]) == 1
    assert "owned by 2 lanes: lane-alpha, other" in capsys.readouterr().err


def test_what_was_already_dirty_is_nobodys_until_it_changes_again(repo, capsys):
    inbox = repo / "Inbox" / "drop.md"
    inbox.parent.mkdir()
    inbox.write_text("the owner's own drop\n", encoding="utf-8")
    dr.open_desk(DESK, "job", inherit=False)
    assert co.main([]) == 0
    inbox.write_text("and now a lane has been in here, at more length\n", encoding="utf-8")
    assert co.main([]) == 1
    assert "Inbox/drop.md" in capsys.readouterr().err


def test_a_closed_lanes_files_are_still_attributed_to_it(desk):
    (desk / "records/2025/January/Ledger.md").write_text("fixed\n", encoding="utf-8")
    dr.record_close("lane-alpha")
    assert co.main([]) == 0


def test_a_closed_lanes_files_pass_to_its_successor_so_one_owner_remains(desk):
    """The applying lane after the drafting lane; `<lane>-2` after an abandoned one."""
    (desk / "records/2025/January/Ledger.md").write_text("fixed\n", encoding="utf-8")
    dr.record_close("lane-alpha", abandoned="looping")
    said = dr.stamp(DESK, "lane-alpha-2", sheet(desk, "lane-alpha-2"))
    assert any("passes from lane-alpha (closed) to lane-alpha-2" in line for line in said)
    assert dr.read_record()["lanes"]["lane-alpha"]["owns"] == []
    assert co.main([]) == 0


def test_a_closed_lane_holding_the_folder_above_is_the_desks_call(desk):
    dr.record_close("lane-alpha")
    inside = SHEET.replace("- records/2025/February/\n", "").replace(
        "2025/January", "2025/January/Ledger.md")
    with pytest.raises(dr.DeskError, match="ABOVE"):
        dr.stamp(DESK, "apply", sheet(desk, "apply", inside))


def test_no_record_is_its_own_exit_code(repo, capsys):
    assert co.main([]) == 2
    assert "no desk record" in capsys.readouterr().err


def test_a_rename_counts_both_names(desk):
    git(desk, "mv", "records/2024/Q1/Summary.md", "records/2025/January/Summary.md")
    changed = dr.git_changed(desk)
    assert "records/2024/Q1/Summary.md" in changed
    assert "records/2025/January/Summary.md" in changed


def test_the_record_is_json_a_person_can_read(desk):
    text = dr.RECORD.read_text(encoding="utf-8")
    assert json.loads(text)["desk"] == DESK and "\n" in text.strip()


# --- another window's work is not a stray, and is not this desk's to save ------


def test_a_file_another_window_changed_passes_under_its_own_heading(desk, capsys):
    (desk / "records/2025/January/Ledger.md").write_text("judged\n", encoding="utf-8")
    (desk / "sources/statement_3.md").write_text("another window's edit\n", encoding="utf-8")
    assert co.main() == 1
    assert "sources/statement_3.md: NO lane owns this file" in capsys.readouterr().err
    said = dr.outside(DESK, ["sources/statement_3.md"], "the owner's other window")
    assert "does not stage" in said[-1]
    assert co.main() == 0
    out = capsys.readouterr().out
    assert "NOT staged by the save" in out
    assert "sources/statement_3.md  -- the owner's other window" in out
    assert "PASS - " in out and "1 more are another window's" in out
    assert "lane-alpha: 1 changed file(s)" in out


def test_a_path_a_lane_owns_is_never_another_windows_work(desk):
    for path in ("records/2025/January/Ledger.md", "records/2025", "records"):
        with pytest.raises(dr.DeskError, match="cannot be another window's work"):
            dr.outside(DESK, [path], "somebody else")
    assert "outside" not in dr.read_record()


def test_outside_needs_a_reason_and_the_desk(desk):
    with pytest.raises(dr.DeskError, match="--why is empty"):
        dr.outside(DESK, ["sources/statement_3.md"], "  ")
    with pytest.raises(dr.DeskError):
        dr.outside("lane-alpha", ["sources/statement_3.md"], "a lane may not say so")


def test_every_desk_act_ends_with_the_stall_banner(desk, monkeypatch, capsys):
    monkeypatch.setattr(dr, "stall_banner", lambda: ["NEEDS THE OWNER -- the `x` tab"])
    assert dr.main(["own", "desk", "CLAUDE.md", "--desk", DESK]) == 0
    assert "NEEDS THE OWNER" in capsys.readouterr().out
    assert dr.main(["show"]) == 0  # a lane runs this one; it carries no banner
    assert "NEEDS THE OWNER" not in capsys.readouterr().out
