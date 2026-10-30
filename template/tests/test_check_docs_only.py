"""Tests for `scripts/check_docs.py --only` -- a lane's gate measures its own files.

Desk rules-check, 2026-10-27: every sheet's `done:` ran the whole-tree gate, so
one lane's digest over budget failed three finished lanes' report-done
(`kb/desk-done-gate-blocks-on-other-lanes.md`). Each test builds a throwaway
git repository under tmp_path and points the gate at it; nothing here reads
the project's own documents.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_docs as cd

BUDGETS = """exempt_dirs: [Archive]
entries:
  - path: CLAUDE.md
    tier: 1
    budget: 2000
    rule: "the index"
  - glob: "mine/*.md"
    tier: 2
    budget: 60
    rule: "mine, trimmed"
  - glob: "theirs/*.md"
    tier: 2
    budget: 60
    rule: "theirs, trimmed"
  - glob: "notes/*.md"
    tier: 3
    budget: 500
    rule: "a note a reader names"
  - glob: "kb/*.md"
    tier: 2
    budget: 4000
    rule: "one topic"
  - path: kb/README.md
    tier: 2
    generated: true
"""

ENTRY = """---
title: "A {name}"
topic: "What {name} found."
keywords: [{name}]
kind: probe
retrieved: 2026-10-27
status: current
---

# A {name}
"""


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A project with one lane's folder (`mine/`) in form and another lane's
    (`theirs/`) mid-edit: a document over budget, one with no budget row, a
    tier-3 note nothing names and a kb entry with broken frontmatter."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    write(tmp_path, "doc_budgets.yaml", BUDGETS)
    write(tmp_path, "CLAUDE.md", "# Index\n\nSee mine/a.md and notes/named.md.\n")
    write(tmp_path, "mine/a.md", "short\n")
    write(tmp_path, "theirs/b.md", "far too long for a sixty-byte ceiling, mid-edit by another lane\n")
    write(tmp_path, "unrowed/c.md", "no row claims this\n")
    write(tmp_path, "notes/named.md", "named by CLAUDE.md\n")
    write(tmp_path, "notes/unnamed.md", "nothing points here\n")
    write(tmp_path, "kb/good.md", ENTRY.format(name="good"))
    write(tmp_path, "kb/broken.md", "no frontmatter\n")
    monkeypatch.setattr(cd, "ROOT", tmp_path)
    monkeypatch.setattr(cd, "BUDGETS_FILE", tmp_path / "doc_budgets.yaml")
    meta, _ = cd.read_frontmatter(ENTRY.format(name="good"))
    write(tmp_path, "kb/README.md", "# Knowledge Base\n\n" + cd.kb_row(tmp_path / "kb" / "good.md", meta) + "\n")
    return tmp_path


def run(capsys, *argv):
    code = cd.main(list(argv))
    out = capsys.readouterr()
    return code, out.out + out.err


def test_the_whole_tree_run_fails_on_every_unfinished_file(tree, capsys):
    code, said = run(capsys)
    assert code == 1
    for rel in ("theirs/b.md", "unrowed/c.md", "notes/unnamed.md", "kb/broken.md"):
        assert rel in said


def test_a_document_over_budget_outside_the_only_paths_does_not_fail_the_run(tree, capsys):
    code, said = run(capsys, "--only", "mine")
    assert code == 0, said
    assert "theirs/b.md" not in said
    assert "1 document(s) under --only mine" in said


def test_a_document_over_budget_inside_the_only_paths_fails(tree, capsys):
    code, said = run(capsys, "--only", "theirs")
    assert code == 1
    assert "[BUDGET] theirs/b.md" in said and "over by" in said


def test_a_file_named_exactly_is_in_scope_and_its_neighbour_is_not(tree, capsys):
    write(tree, "mine/big.md", "x" * 100 + "\n")
    assert run(capsys, "--only", "mine/a.md")[0] == 0
    code, said = run(capsys, "--only", "mine/big.md")
    assert code == 1 and "mine/big.md" in said


def test_each_per_document_check_is_scoped(tree, capsys):
    """No row, orphan and kb frontmatter: each fails inside the paths, never outside."""
    for path, label in (("unrowed", "[BUDGET] unrowed/c.md"), ("notes", "[ORPHANS] notes/unnamed.md"),
                        ("kb/broken.md", "[KB] kb/broken.md")):
        code, said = run(capsys, "--only", path)
        assert code == 1 and label in said, path
    assert run(capsys, "--only", "mine", "notes/named.md", "kb/good.md")[0] == 0


def kb_tier_3(tree):
    """The kb rows as this project has them: tier 3, so a new entry is orphaned
    until the index names it."""
    write(tree, "doc_budgets.yaml", BUDGETS.replace('glob: "kb/*.md"\n    tier: 2', 'glob: "kb/*.md"\n    tier: 3'))


def test_a_new_kb_entry_with_no_row_passes_only_with_a_note(tree, capsys):
    """Desk trade-import, 2026-10-29: four lanes' new entries failed their own
    done: until the README's owner re-rendered. The save renders it now."""
    kb_tier_3(tree)
    write(tree, "kb/new.md", ENTRY.format(name="new"))
    code, said = run(capsys, "--only", "kb/new.md")
    assert code == 0, said
    assert "rendered at the save: kb/README.md has no row as kb/new.md's frontmatter renders it" in said
    assert "rendered at the save: kb/new.md is named only by a kb/README.md row" in said
    assert "[KB]" not in said and "[ORPHANS]" not in said
    assert "new.md" not in (tree / "kb/README.md").read_text(encoding="utf-8")


def test_a_stale_row_for_a_named_entry_is_a_note(tree, capsys):
    write(tree, "kb/good.md", ENTRY.format(name="good").replace("What good found.", "What good found, revised."))
    code, said = run(capsys, "--only", "kb/good.md")
    assert code == 0 and "rendered at the save" in said and "kb/good.md" in said


def test_every_other_failure_of_an_unrendered_entry_still_fails(tree, capsys):
    kb_tier_3(tree)
    write(tree, "kb/new.md", ENTRY.format(name="new") + "x" * 4000 + "\n")
    code, said = run(capsys, "--only", "kb/new.md")
    assert code == 1 and "[BUDGET] kb/new.md" in said
    assert "[KB]" not in said and "[ORPHANS]" not in said


def test_a_missing_row_for_an_entry_outside_only_is_not_checked(tree, capsys):
    write(tree, "kb/new.md", ENTRY.format(name="new"))
    code, said = run(capsys, "--only", "mine")
    assert code == 0, said
    assert "kb/new.md" not in said


def test_the_whole_tree_run_still_fails_a_missing_or_hand_typed_row(tree, capsys):
    (tree / "kb/broken.md").unlink()
    run(capsys, "--write-kb")
    write(tree, "kb/new.md", ENTRY.format(name="new"))
    code, said = run(capsys)
    assert code == 1 and "[KB] kb/README.md disagrees with the entry frontmatter" in said and "[new.md](new.md)" in said
    run(capsys, "--write-kb")
    index = tree / "kb/README.md"
    index.write_text(index.read_text(encoding="utf-8") + "| [x.md](x.md) | Hand | Typed | 2026-10-27 | current |\n", encoding="utf-8")
    code, said = run(capsys)
    assert code == 1 and "[KB] kb/README.md disagrees with the entry frontmatter" in said and "Hand" in said


def test_as_rendered_reads_the_index_the_save_will_write_and_writes_nothing(tree, capsys):
    kb_tier_3(tree)
    (tree / "kb/broken.md").unlink()
    write(tree, "kb/new.md", ENTRY.format(name="new"))
    before = (tree / "kb/README.md").read_text(encoding="utf-8")
    code, said = run(capsys, "--as-rendered")
    assert "would write kb/README.md" in said
    assert "[KB]" not in said and "[ORPHANS] kb/" not in said
    assert (tree / "kb/README.md").read_text(encoding="utf-8") == before
    assert code == 1 and "theirs/b.md" in said  # the rest of the tree is still gated


def test_as_rendered_and_write_kb_are_refused_together(tree, capsys):
    with pytest.raises(SystemExit) as stop:
        cd.main(["--as-rendered", "--write-kb"])
    assert stop.value.code == 2


def test_naming_the_index_runs_the_whole_index_check(tree, capsys):
    code, said = run(capsys, "--only", "kb/README.md")
    assert code == 1 and "kb/broken.md" in said


def test_write_kb_is_refused_when_the_index_is_not_named(tree, capsys):
    code, said = run(capsys, "--only", "mine", "--write-kb")
    assert code == 2 and "writes nothing outside its paths" in said


@pytest.mark.parametrize("bad", ["../elsewhere", "/abs/path", "C:/abs", "."])
def test_a_path_outside_the_project_is_refused_with_exit_2(tree, capsys, bad):
    code, said = run(capsys, "--only", bad)
    assert code == 2 and "not a path inside this project" in said


def test_a_path_with_no_document_is_named_and_does_not_fail(tree, capsys):
    code, said = run(capsys, "--only", "mine", "scripts/check_docs.py")
    assert code == 0 and "--only scripts/check_docs.py: no document at or under it" in said


def test_only_takes_paths_across_repeated_flags_and_backslashes(tree, capsys):
    code, said = run(capsys, "--only", "mine\\", "--only", "./notes/named.md")
    assert code == 0, said
    assert "--only mine notes/named.md" in said


def test_the_help_text_names_what_only_skips(capsys):
    with pytest.raises(SystemExit):
        cd.main(["--help"])
    said = " ".join(capsys.readouterr().out.split())
    assert "Skipped under --only: MEMORY" in said and "doc_budgets.yaml" in said
