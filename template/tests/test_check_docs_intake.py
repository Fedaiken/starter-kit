"""Tests for the INTAKE check in scripts/check_docs.py -- a Status cell is a pointer, not a fact.

Run on small fixture strings, never the live Intake_Checklist.md: the live
file changes every time a document arrives, and a test pinned to it would
fail for the wrong reason.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_docs as cd


def table(*status_cells):
    lines = ["| # | Document | Who | Status |", "|---|---|---|---|"]
    lines += [f"| {n} | Doc {n} | the agent | {cell} |" for n, cell in enumerate(status_cells, 1)]
    return "# Checklist\n\n" + "\n".join(lines) + "\n"


def test_good_cell_passes():
    assert cd.check_intake_text(table("**partly found** — the executed agreement — `kb/agreement.md`")) == []


def test_dollar_figure_fails_and_names_the_row():
    out = cd.check_intake_text(table(
        "**found** — `kb/a.md`",
        "**partly found** — $4,500 from February — `kb/agreement.md`",
    ))
    assert len(out) == 1
    assert "row 2" in out[0] and "digit outside backticks" in out[0] and "$4,500" in out[0]


def test_date_fails():
    out = cd.check_intake_text(table("**found** — agreement ends 2025-12-31 — `kb/agreement.md`"))
    assert len(out) == 1
    assert "row 1" in out[0] and "digit outside backticks" in out[0] and "2025-12-31" in out[0]


def test_figures_the_old_pattern_list_missed_all_fail():
    # the first gate rejected only `$` amounts and ISO dates; each of these passed it
    for cell in (
        "**partly found** — the statement (2025-03) — `kb/a.md`",
        "**partly found** — moved out 12/15/2023 — `kb/a.md`",
        "**partly found** — statements for Dec 2024, Jan 2025 — `kb/a.md`",
        "**partly found** — deposit of 4,400.00 — `kb/a.md`",
    ):
        out = cd.check_intake_text(table(cell))
        assert len(out) == 1, cell
        assert "row 1" in out[0] and "digit outside backticks" in out[0], cell
        assert "move the figure to the kb entry the cell points to" in out[0], cell


def test_failure_names_the_row_and_the_offending_figure():
    out = cd.check_intake_text(table("**found** — `kb/a.md`", "**needed** — see 4,400.00 — `kb/a.md`"))
    assert len(out) == 1
    assert "row 2" in out[0] and "4,400.00" in out[0]


def test_backticked_identifier_passes():
    assert cd.check_intake_text(table("**needed** — look it up with `2338-007-067` — `kb/public-record.md`")) == []


def test_section_reference_passes():
    assert cd.check_intake_text(table("**on file** — `kb/which-rules-apply.md` §3")) == []
    assert cd.check_intake_text(table("**on file** — `kb/management-agreement.md` §4F")) == []
    assert cd.check_intake_text(table("**on file** — `kb/which-rules-apply.md` §1, §6")) == []


def test_section_reference_does_not_excuse_a_figure_beside_it():
    out = cd.check_intake_text(table("**on file** — $4,500 per §3 — `kb/a.md`"))
    assert len(out) == 1
    assert "$4,500" in out[0] and "§3" not in out[0]


def test_unknown_status_word_fails():
    out = cd.check_intake_text(table("**received** — `kb/agreement.md`"))
    assert len(out) == 1
    assert "status word" in out[0]


def test_status_word_must_be_whole():
    # "foundation" starts with "found" but is not the word
    assert len(cd.check_intake_text(table("foundation — `kb/a.md`"))) == 1


def test_missing_pointer_fails():
    out = cd.check_intake_text(table("needed"))
    assert len(out) == 1
    assert "pointer" in out[0]


def test_process_inbox_on_file_form_passes_with_a_dated_path():
    # process-inbox flips a row to `on file — <path>`; a date inside the backticked path is legal
    assert cd.check_intake_text(table("on file — `Archive/Inbox_Processed/2026-09-25_agreement/agreement.pdf`")) == []


def test_every_listed_word_passes():
    assert cd.check_intake_text(table(*(f"{w} — `kb/a.md`" for w in cd.INTAKE_STATUS_WORDS))) == []


def test_table_without_status_column_is_ignored_but_none_at_all_fails():
    other = "| Folder | Contains |\n|---|---|\n| kb | $5 on 2026-01-01 |\n"
    assert cd.check_intake_text(other + "\n" + table("found — `kb/a.md`")) == []
    assert len(cd.check_intake_text(other)) == 1
