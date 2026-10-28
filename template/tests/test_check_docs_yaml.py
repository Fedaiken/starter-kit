"""Tests for scripts/check_docs.py's strict YAML loader and its CLAIMS check.

Each failure is planted in a throwaway tree, never the live doc_budgets.yaml:
the live file changes as documents arrive, and a test pinned to it would fail
for the wrong reason. Each plant is shown to fail, and its clean twin to pass,
so neither half can pass by checking nothing.
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_docs as cd

BUDGETS = """\
exempt_dirs:
  - Archive
entries:
  - path: CLAUDE.md
    tier: 1
    budget: 10000
    rule: Pointers only.
  - glob: kb/*.md
    tier: 3
    budget: 16000
    rule: One topic per entry.
  - path: kb/README.md
    tier: 3
    generated: true
"""

CLAIM = """\
budget_claims:
  - in: CLAUDE.md
    about: CLAUDE.md
    says: "is gated at {budget} b"
"""


def parsed(text):
    return cd.parse_budgets(cd.strict_load(text))


def problems(budgets, docs):
    return cd.find_budget_claim_problems(sorted(docs), budgets, docs.get)


# --- strict yaml -------------------------------------------------------------


def test_safe_load_drops_a_duplicate_key_silently():
    # the defect the loader exists for: no error, and the first value is gone
    assert yaml.safe_load("budget: 10000\nbudget: 99999\n") == {"budget": 99999}


def test_strict_load_refuses_a_duplicate_key_naming_line_and_key():
    with pytest.raises(cd.DuplicateKeyError) as exc:
        cd.strict_load("budget: 10000\nrule: x\nbudget: 99999\n")
    assert (exc.value.key, exc.value.line, exc.value.first) == ("budget", 3, 1)
    assert "line 3" in str(exc.value) and "'budget'" in str(exc.value) and "line 1" in str(exc.value)


def test_strict_load_reads_a_clean_file_like_safe_load():
    assert cd.strict_load(BUDGETS) == yaml.safe_load(BUDGETS)


def test_duplicate_key_in_a_nested_row_is_refused():
    text = BUDGETS.replace("    budget: 10000\n", "    budget: 10000\n    budget: 12000\n", 1)
    with pytest.raises(cd.DuplicateKeyError) as exc:
        cd.strict_load(text)
    assert exc.value.key == "budget" and exc.value.line == 7


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setattr(cd, "ROOT", tmp_path)
    monkeypatch.setattr(cd, "BUDGETS_FILE", tmp_path / "doc_budgets.yaml")
    return tmp_path


def test_gate_fails_on_a_duplicated_budget_naming_file_line_and_key(tree, capsys):
    (tree / "doc_budgets.yaml").write_text(BUDGETS.replace("    budget: 10000\n", "    budget: 10000\n    budget: 12000\n", 1), encoding="utf-8")
    with pytest.raises(cd.ConfigError) as exc:
        cd.load_budgets()
    assert "doc_budgets.yaml" in str(exc.value) and "line 7" in str(exc.value) and "'budget'" in str(exc.value)
    assert cd.main([]) == 2
    err = capsys.readouterr().err
    assert "doc_budgets.yaml" in err and "line 7" in err and "'budget'" in err


def test_a_second_entries_list_is_refused(tree):
    (tree / "doc_budgets.yaml").write_text(BUDGETS + "entries:\n  - path: x.md\n    tier: 3\n    budget: 1\n    rule: r\n", encoding="utf-8")
    with pytest.raises(cd.ConfigError) as exc:
        cd.load_budgets()
    assert "'entries'" in str(exc.value) and "line 15" in str(exc.value) and "line 3" in str(exc.value)


def test_two_rows_for_one_selector_are_refused():
    with pytest.raises(cd.ConfigError) as exc:
        parsed(BUDGETS + "  - path: CLAUDE.md\n    tier: 1\n    budget: 12000\n    rule: again\n")
    assert "CLAUDE.md" in str(exc.value) and "repeats entries[0]" in str(exc.value)


def test_frontmatter_duplicate_key_names_the_file_line():
    text = "---\ntitle: A\ntopic: b\ntitle: C\n---\nbody\n"
    meta, err = cd.read_frontmatter(text)
    assert meta == {} and "line 4" in err and "'title'" in err and "line 2" in err


def test_kb_entry_with_duplicate_key_fails_naming_the_entry(tmp_path):
    entry = tmp_path / "topic.md"
    entry.write_text("---\ntitle: A\ntopic: b\nkeywords: [k]\nkind: probe\nretrieved: 2026-10-26\nstatus: current\nstatus: superseded\n---\n", encoding="utf-8")
    meta, err = cd.read_frontmatter(entry.read_text(encoding="utf-8"))
    out = cd.validate_kb(entry, meta, err)
    assert len(out) == 1 and out[0].startswith("kb/topic.md:") and "'status'" in out[0] and "line 8" in out[0]


# --- budget claims: config ---------------------------------------------------


def test_no_claim_rows_is_a_valid_config():
    b = parsed(BUDGETS)
    assert b["budget_claims"] == [] and b["budget_prose_exempt"] == {}


@pytest.mark.parametrize("says, words", [
    ("is gated at 10,000 b", "no {budget} slot"),
    ("weighs {budget} b", "no budget word"),
    ("{budget}", "no budget word"),  # the slot's own word must not count
])
def test_a_says_that_cannot_be_checked_is_refused(says, words):
    with pytest.raises(cd.ConfigError) as exc:
        parsed(BUDGETS + f'budget_claims:\n  - in: CLAUDE.md\n    about: CLAUDE.md\n    says: "{says}"\n')
    assert words in str(exc.value)


def test_about_must_name_a_budgeted_row():
    with pytest.raises(cd.ConfigError, match="names no entry"):
        parsed(BUDGETS + CLAIM.replace("about: CLAUDE.md", "about: README.md"))
    with pytest.raises(cd.ConfigError, match="generated"):
        parsed(BUDGETS + CLAIM.replace("about: CLAUDE.md", "about: kb/README.md"))


def test_an_exemption_needs_a_why():
    with pytest.raises(cd.ConfigError, match="why"):
        parsed(BUDGETS + "budget_prose_exempt:\n  - path: kb/a.md\n")


# --- budget claims: the check ------------------------------------------------


def test_current_claim_passes():
    assert problems(parsed(BUDGETS + CLAIM), {"CLAUDE.md": "It is gated at 10,000 b (tier 1)."}) == []


def test_wrong_claim_fails_naming_document_and_both_figures():
    out = problems(parsed(BUDGETS + CLAIM), {"CLAUDE.md": "It is gated at 12,000 b (tier 1)."})
    assert len(out) == 1
    assert out[0].startswith("CLAUDE.md:") and "12,000 b" in out[0] and "10,000 b" in out[0] and "doc_budgets.yaml" in out[0]


def test_reworded_claim_fails_as_gone():
    out = problems(parsed(BUDGETS + CLAIM), {"CLAUDE.md": "It must stay small."})
    assert len(out) == 1 and "checks nothing" in out[0]


def test_claim_in_a_missing_document_fails():
    out = problems(parsed(BUDGETS + CLAIM), {})
    assert len(out) == 1 and "no such file" in out[0]


def test_undeclared_budget_sentence_fails():
    out = problems(parsed(BUDGETS), {"kb/a.md": "This entry is capped at 16,000 b."})
    assert len(out) == 1 and out[0].startswith("kb/a.md:") and "16,000 b" in out[0] and "budget_claims" in out[0]


@pytest.mark.parametrize("text", [
    "The file measured 4,321 b on disk after the trim.",          # no budget word near it
    "The budget rule is simple.\n\n" + "x" * 40 + " it was 4,321 b.",  # word too far away
    "Commit 88da27b set the budget.",                               # a sha, not a figure
    "A budget of 12 b is not a figure anyone declares.",            # under three digits
])
def test_a_figure_that_is_not_a_budget_claim_passes(text):
    assert problems(parsed(BUDGETS), {"kb/a.md": text}) == []


def test_exempted_document_passes_and_a_dead_exemption_fails():
    exempt = BUDGETS + "budget_prose_exempt:\n  - path: kb/history.md\n    why: dated history of another project\n"
    assert problems(parsed(exempt), {"kb/history.md": "It sat under a 12,000 b ceiling."}) == []
    out = problems(parsed(exempt), {"kb/history.md": "Nothing to see."})
    assert len(out) == 1 and "dead config" in out[0]
    out = problems(parsed(exempt), {})
    assert len(out) == 1 and "no such file" in out[0]


# --- end to end: the gate itself, in a throwaway repository ------------------


def test_kit_claim_checks_claude_md_with_no_row_in_the_project():
    assert problems(parsed(BUDGETS), {"CLAUDE.md": "It is gated at 10,000 b."}) == []
    out = problems(parsed(BUDGETS), {"CLAUDE.md": "It is gated at 12,000 b."})
    assert len(out) == 1 and "12,000 b" in out[0] and "10,000 b" in out[0]


def test_kit_claim_with_no_sentence_checks_nothing_and_leaves_the_sweep():
    assert problems(parsed(BUDGETS), {"CLAUDE.md": "It must stay small."}) == []
    out = problems(parsed(BUDGETS), {"CLAUDE.md": "It is capped at 12,000 b."})
    assert len(out) == 1 and "no budget_claims row covers it" in out[0]


def test_kit_exemption_covers_its_entry_and_is_never_dead():
    assert problems(parsed(BUDGETS), {"kb/document-budgets.md": "It sat under a 12,000 b ceiling."}) == []
    assert problems(parsed(BUDGETS), {"kb/document-budgets.md": "Nothing to see."}) == []


def test_project_row_replaces_the_kit_claim():
    own = BUDGETS + CLAIM.replace("is gated at {budget} b", "stays under its {budget} b budget")
    assert problems(parsed(own), {"CLAUDE.md": "It stays under its 10,000 b budget."}) == []
    out = problems(parsed(own), {"CLAUDE.md": "It is gated at 10,000 b."})
    assert len(out) == 1 and "checks nothing" in out[0]


# --- end to end: the gate itself, in a throwaway repository ------------------

KIT_KB = {
    # the kit-owned entries' figures, as Savecraft carries them on 2026-10-26
    "document-budgets.md": "Its CLAUDE.md was scaffolded at 9.5 KB under a 12,000 b ceiling and passed 10,697 b the same day.",
    "git-discipline.md": "`check_docs.py | tail -2` committed and pushed a route file 102 b over budget.",
}


def plant(root, claude_md, budgets=BUDGETS):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "doc_budgets.yaml").write_text(budgets, encoding="utf-8")
    (root / "CLAUDE.md").write_text(claude_md + "\nIndex: `kb/README.md`.\n", encoding="utf-8")
    (root / "kb").mkdir()
    for name, body in KIT_KB.items():
        (root / "kb" / name).write_text(
            f"---\ntitle: {name}\ntopic: t\nkeywords: [k]\nkind: decision\nretrieved: 2026-10-26\nstatus: current\n---\n\n{body}\n", encoding="utf-8")


def test_unchanged_kit_project_passes_and_a_real_mismatch_still_fails(tree, capsys):
    # a doc_budgets.yaml with neither new key, as Travel_Helper and HAZELHURST have it
    plant(tree, "A pointer index. It loads every session and is gated at 10,000 b (`doc_budgets.yaml`, tier 1).")
    assert "budget_claims" not in BUDGETS and "budget_prose_exempt" not in BUDGETS
    assert cd.main(["--write-kb"]) == 0, capsys.readouterr().err
    assert "budget claims current" in capsys.readouterr().out

    (tree / "CLAUDE.md").write_text("It is gated at 12,000 b (`doc_budgets.yaml`, tier 1).\nIndex: `kb/README.md`.\n", encoding="utf-8")
    assert cd.main([]) == 1
    err = capsys.readouterr().err
    assert "[CLAIMS] CLAUDE.md:" in err and "12,000 b" in err and "10,000 b" in err


def test_gate_fails_on_a_wrong_declared_claim_and_passes_on_the_right_one(tree, capsys):
    plant(tree, "It is gated at 12,000 b.", BUDGETS + CLAIM)
    assert cd.main(["--write-kb"]) == 1
    err = capsys.readouterr().err
    assert "[CLAIMS] CLAUDE.md:" in err and "12,000 b" in err and "10,000 b" in err

    (tree / "CLAUDE.md").write_text("It is gated at 10,000 b.\nIndex: `kb/README.md`.\n", encoding="utf-8")
    assert cd.main([]) == 0
    assert "budget claims current" in capsys.readouterr().out
