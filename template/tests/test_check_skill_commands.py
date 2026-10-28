"""The skill-command check: a skill without a wrapper fails, a wrapper without a skill fails.

Every defect is planted in a throwaway tree and proved to fail there, and the
real tree is proved to pass -- a gate that has only ever seen a clean tree has
not been shown to catch anything. `test_the_real_tree_is_inspected_not_skipped`
is the other half: a check that walks nothing passes too.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_skill_commands as csc  # noqa: E402

#: The skills the Starter Kit seeds, which every project here carries.
KIT_SKILLS = {"close-session", "desk", "lane", "process-inbox"}


def skill_text(name: str, description: str = "Does a thing.", purpose: str | None = None) -> str:
    meta = {"name": name, "description": description}
    if purpose is not None:
        meta["purpose"] = purpose
    return f"---\n{yaml.safe_dump(meta, allow_unicode=True, width=10**6)}---\n\n# {name}\n"


def wrapper_for(name: str) -> str:
    return (f"---\ndescription: x\n---\n\nExecute the workflow in `skills/{name}/SKILL.md`.\n\n"
            "$ARGUMENTS\n")


def make_tree(root: Path, skills: dict[str, str] | None = None,
              commands: dict[str, str] | None = None, scripts: tuple[str, ...] = ()) -> Path:
    """A tree with these skills (folder -> SKILL.md text), wrappers (stem -> text) and scripts."""
    for name, text in (skills or {}).items():
        (root / "skills" / name).mkdir(parents=True, exist_ok=True)
        (root / "skills" / name / "SKILL.md").write_text(text, encoding="utf-8")
    for stem, text in (commands or {}).items():
        path = root / ".claude" / "commands" / f"{stem}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for script in scripts:
        (root / "scripts").mkdir(exist_ok=True)
        (root / "scripts" / script).write_text("", encoding="utf-8")
    return root


def clean_tree(root: Path) -> Path:
    return make_tree(root, {"alpha": skill_text("alpha")}, {"alpha": wrapper_for("alpha")})


# --- the real tree ---------------------------------------------------------


def test_the_real_tree_passes():
    assert csc.check(root=csc.ROOT) == []
    assert csc.main([]) == 0


def test_the_real_tree_is_inspected_not_skipped():
    """A check that walks nothing passes. Assert it walked the kit's skills."""
    assert KIT_SKILLS <= {skill.name for skill in csc.skills()}
    assert KIT_SKILLS <= set(csc.wrappers())


# --- a skill without a wrapper ---------------------------------------------


def test_a_clean_tree_passes(tmp_path):
    assert csc.check(root=clean_tree(tmp_path)) == []
    assert csc.main([], root=tmp_path) == 0


def test_a_skill_without_a_wrapper_fails(tmp_path, capsys):
    """PLANTED DEFECT. A skill the `/` menu cannot reach."""
    root = make_tree(tmp_path, {"alpha": skill_text("alpha"), "beta": skill_text("beta")},
                     {"alpha": wrapper_for("alpha")})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert "skills/beta/SKILL.md has no slash command" in problems[0]
    assert ".claude/commands/beta.md" in problems[0]
    assert csc.main([], root=root) == 1
    assert "skills/beta/SKILL.md has no slash command" in capsys.readouterr().err


def test_no_commands_folder_at_all_fails_every_skill(tmp_path):
    root = make_tree(tmp_path, {"alpha": skill_text("alpha"), "beta": skill_text("beta")})
    assert len(csc.check(root=root)) == 2


def test_a_wrapper_at_the_skills_name_that_points_elsewhere_fails(tmp_path):
    """PLANTED DEFECT. `/alpha` in the menu would run beta's workflow."""
    root = make_tree(tmp_path, {"alpha": skill_text("alpha"), "beta": skill_text("beta")},
                     {"alpha": wrapper_for("beta"), "beta": wrapper_for("beta")})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert ".claude/commands/alpha.md does not name skills/alpha/SKILL.md" in problems[0]


# --- a wrapper without a skill ---------------------------------------------


def test_a_wrapper_for_a_deleted_skill_fails(tmp_path, capsys):
    """PLANTED DEFECT. The orphan: the skill is gone, its `/` menu entry stayed."""
    root = clean_tree(tmp_path)
    make_tree(root, commands={"ghost": wrapper_for("ghost")})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert (".claude/commands/ghost.md points at skills/ghost/SKILL.md, "
            "which does not exist") in problems[0]
    assert csc.main([], root=root) == 1
    assert "ghost.md" in capsys.readouterr().err


def test_a_wrapper_that_names_nothing_fails(tmp_path):
    """PLANTED DEFECT. A wrapper that runs nothing is an orphan too."""
    root = clean_tree(tmp_path)
    make_tree(root, commands={"stray": "---\ndescription: x\n---\n\nDo the thing.\n"})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert ".claude/commands/stray.md points at no skill" in problems[0]


def test_a_standalone_wrapper_names_a_script_that_exists(tmp_path):
    """The `check-docs.md` shape: no skill behind it, a script it runs."""
    body = "---\ndescription: x\n---\n\nRun `<venv python> scripts/check_docs.py --report`.\n"
    root = clean_tree(tmp_path)
    make_tree(root, commands={"check-docs": body}, scripts=("check_docs.py",))
    assert csc.check(root=root) == []


def test_a_standalone_wrapper_whose_script_is_gone_fails(tmp_path):
    body = "---\ndescription: x\n---\n\nRun `<venv python> scripts/check_docs.py --report`.\n"
    root = make_tree(clean_tree(tmp_path), commands={"check-docs": body})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert ".claude/commands/check-docs.md points at no skill" in problems[0]


def test_an_alias_wrapper_for_a_live_skill_passes(tmp_path):
    root = make_tree(clean_tree(tmp_path), commands={"a": wrapper_for("alpha")})
    assert csc.check(root=root) == []


def test_a_namespaced_orphan_is_seen(tmp_path):
    """PLANTED DEFECT. A wrapper in a subfolder must not slip past the walk."""
    root = make_tree(clean_tree(tmp_path), commands={"team/ghost": wrapper_for("ghost")})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert ".claude/commands/team/ghost.md points at skills/ghost/SKILL.md" in problems[0]


@pytest.mark.parametrize("path", ["notskills/ghost/SKILL.md", "docs/skills/ghost/SKILL.md"])
def test_a_path_that_only_ends_like_a_skill_is_not_a_pointer(tmp_path, path):
    """The pattern must not read another folder's `skills/` as this project's."""
    root = make_tree(clean_tree(tmp_path), commands={
        "stray": f"---\ndescription: x\n---\n\nSee `{path}`.\n"})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert "points at no skill" in problems[0]


def test_a_wrapper_naming_a_live_and_a_dead_skill_is_reported_for_the_dead_one(tmp_path):
    root = make_tree(tmp_path, {"alpha": skill_text("alpha")}, {
        "alpha": wrapper_for("alpha") + "Then `skills/gone/SKILL.md`.\n"})
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert "skills/gone/SKILL.md, which does not exist" in problems[0]


# --- nothing to inspect ----------------------------------------------------


def test_no_skills_is_an_error_not_a_clean_run(tmp_path, capsys):
    """THE VACUOUS PASS. A check that finds no skills has proved nothing."""
    (tmp_path / "skills").mkdir()
    with pytest.raises(csc.SkillError, match="passes vacuously"):
        csc.check(root=tmp_path)
    assert csc.main([], root=tmp_path) == 2
    assert "passes vacuously" in capsys.readouterr().err


def test_no_skills_folder_is_an_error_too(tmp_path):
    assert csc.main([], root=tmp_path) == 2


# --- a skill whose frontmatter cannot be used ------------------------------


@pytest.mark.parametrize("text, why", [
    ("# no frontmatter\n", "does not open with a closed"),
    ("---\nname: alpha\n# never closed\n", "does not open with a closed"),
    ("---\nname: [unclosed\n---\n", "not valid YAML"),
    ("---\n- a\n- b\n---\n", "not a mapping"),
    ("---\nname: alpha\n---\n", "no `description:`"),
])
def test_a_skill_with_unusable_frontmatter_is_reported_beside_the_other_gaps(tmp_path, text, why):
    root = make_tree(tmp_path, {"alpha": text, "beta": skill_text("beta")},
                     {"alpha": wrapper_for("alpha")})
    problems = csc.check(root=root)
    assert len(problems) == 2
    assert "skills/alpha/SKILL.md cannot be invoked" in problems[0] and why in problems[0]
    assert "skills/beta/SKILL.md has no slash command" in problems[1]


def test_fix_does_not_invent_a_wrapper_for_a_broken_skill(tmp_path):
    root = make_tree(tmp_path, {"alpha": "# no frontmatter\n"})
    problems = csc.check(fix=True, root=root)
    assert not (root / ".claude" / "commands" / "alpha.md").exists()
    assert len(problems) == 2 and not any("--fix" in p for p in problems)


# --- --fix -----------------------------------------------------------------


def test_fix_creates_the_missing_wrapper_and_the_check_then_passes(tmp_path, capsys):
    root = make_tree(tmp_path, {"alpha": skill_text("alpha", purpose="Act on the thing.")})
    assert csc.check(fix=True, root=root) == []
    assert "created .claude/commands/alpha.md" in capsys.readouterr().out
    raw = (root / ".claude" / "commands" / "alpha.md").read_bytes()
    assert raw.decode("utf-8") == (
        "---\ndescription: Act on the thing\n---\n\n"
        "Execute the workflow in `skills/alpha/SKILL.md`.\n\n"
        "Read that file now and follow it exactly — it is the authority on this run. "
        "Do not improvise the process from memory.\n\n$ARGUMENTS\n")
    assert b"\r" not in raw, "the wrapper must be written with LF, like the others"
    assert csc.check(root=root) == []
    assert csc.main([], root=root) == 0


def test_fix_matches_the_wrapper_the_real_close_session_skill_has():
    """The generated wrapper has the shape of the hand-made ones, body for body."""
    real = (csc.ROOT / ".claude" / "commands" / "close-session.md").read_text(encoding="utf-8")
    skill = next(s for s in csc.skills() if s.name == "close-session")
    assert csc.wrapper_text(skill).split("---\n", 2)[2] == real.split("---\n", 2)[2]


def test_fix_is_idempotent(tmp_path, capsys):
    root = make_tree(tmp_path, {"alpha": skill_text("alpha")})
    assert csc.check(fix=True, root=root) == []
    capsys.readouterr()
    assert csc.check(fix=True, root=root) == []
    assert capsys.readouterr().out == ""


def test_fix_never_overwrites_a_wrapper(tmp_path):
    """A hand-tuned wrapper is safe, even one that is wrong: it is reported, not rewritten."""
    tuned = "---\ndescription: hand-tuned\n---\n\nRun beta.\n"
    root = make_tree(tmp_path, {"alpha": skill_text("alpha")}, {"alpha": tuned})
    problems = csc.check(fix=True, root=root)
    assert len(problems) == 1 and "does not name skills/alpha/SKILL.md" in problems[0]
    assert (root / ".claude" / "commands" / "alpha.md").read_text(encoding="utf-8") == tuned


def test_fix_never_overwrites_a_wrapper_the_filesystem_calls_the_same_file(tmp_path):
    """Skill `Alpha` and wrapper `alpha.md` are one file on Windows and macOS.

    The wrapper is not found under the skill's name, so only the guard on the
    target keeps `--fix` from writing over it. Skipped where the filesystem
    tells the two names apart, since there they are two files.
    """
    probe = tmp_path / "Probe"
    probe.write_text("", encoding="utf-8")
    if not (tmp_path / "probe").exists():
        pytest.skip("this filesystem is case-sensitive")
    tuned = "---\ndescription: hand-tuned\n---\n\nRun beta.\n"
    root = make_tree(tmp_path, {"Alpha": skill_text("Alpha")}, {"alpha": tuned})
    assert csc.check(fix=True, root=root) != []
    assert (root / ".claude" / "commands" / "alpha.md").read_text(encoding="utf-8") == tuned


def test_fix_never_deletes_an_orphan(tmp_path):
    root = make_tree(clean_tree(tmp_path), commands={"ghost": wrapper_for("ghost")})
    problems = csc.check(fix=True, root=root)
    assert len(problems) == 1 and "ghost.md" in problems[0]
    assert (root / ".claude" / "commands" / "ghost.md").exists()


def test_fix_never_touches_the_settings(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not even json", encoding="utf-8")
    root = make_tree(tmp_path, {"alpha": skill_text("alpha", "Left running under `/loop /alpha`.")})
    assert csc.check(fix=True, root=root) == []
    assert settings.read_text(encoding="utf-8") == "{not even json"


# --- the menu line ---------------------------------------------------------


def test_the_menu_line_prefers_purpose():
    meta = {"description": "Long. Description.", "purpose": "The   short\npurpose."}
    assert csc.menu_line(meta) == "The short purpose"


def test_the_menu_line_falls_back_to_the_first_sentence_of_the_description():
    meta = {"description": "**Inbox Tool**: Does `one` thing. Then another.\n- MANDATORY TRIGGERS: x"}
    assert csc.menu_line(meta) == "Inbox Tool: Does one thing"


def test_a_long_menu_line_is_cut_to_the_limit():
    line = csc.menu_line({"description": "word " * 60})
    assert len(line) == csc.MENU_LINE and line.endswith("...")


@pytest.mark.parametrize("purpose", [
    "Route: what it found, and \"where\" it goes",
    "Use #1 - it's the 'first'",
    "- starts like a list item",
    "@at and `tick` and {braces} [brackets]",
    "Ünïcode — with a dash",
    "yes",
])
def test_a_menu_line_with_yaml_punctuation_survives_the_round_trip(tmp_path, purpose):
    """The wrapper's frontmatter must parse back to exactly the line it was written from."""
    root = make_tree(tmp_path, {"alpha": skill_text("alpha", purpose=purpose)})
    assert csc.check(fix=True, root=root) == []
    wrote = csc.frontmatter(root / ".claude" / "commands" / "alpha.md")
    assert wrote == {"description": csc.menu_line({"purpose": purpose})}


# --- the real tree, with a defect planted in a copy of it ------------------


def copy_of_the_real_tree(dest: Path) -> Path:
    shutil.copytree(csc.ROOT / "skills", dest / "skills")
    shutil.copytree(csc.ROOT / ".claude" / "commands", dest / ".claude" / "commands")
    (dest / "scripts").mkdir()
    shutil.copy(csc.ROOT / "scripts" / "check_docs.py", dest / "scripts" / "check_docs.py")
    return dest


def test_a_copy_of_the_real_tree_passes(tmp_path):
    assert csc.check(root=copy_of_the_real_tree(tmp_path)) == []


@pytest.mark.parametrize("name", sorted(KIT_SKILLS))
def test_removing_a_real_wrapper_is_caught(tmp_path, name):
    root = copy_of_the_real_tree(tmp_path)
    (root / ".claude" / "commands" / f"{name}.md").unlink()
    problems = csc.check(root=root)
    assert len(problems) == 1 and f"skills/{name}/SKILL.md has no slash command" in problems[0]


@pytest.mark.parametrize("name", sorted(KIT_SKILLS))
def test_removing_a_real_skill_orphans_its_wrapper(tmp_path, name):
    root = copy_of_the_real_tree(tmp_path)
    shutil.rmtree(root / "skills" / name)
    problems = csc.check(root=root)
    assert len(problems) == 1
    assert f".claude/commands/{name}.md points at skills/{name}/SKILL.md" in problems[0]


def test_removing_the_gate_script_orphans_check_docs(tmp_path):
    root = copy_of_the_real_tree(tmp_path)
    (root / "scripts" / "check_docs.py").unlink()
    problems = csc.check(root=root)
    assert len(problems) == 1 and ".claude/commands/check-docs.md points at no skill" in problems[0]


# --- the command line, end to end ------------------------------------------


def run_script(copy: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(copy), *args], capture_output=True,
                          encoding="utf-8", errors="replace", timeout=60)


def test_the_command_line_fails_names_the_gap_and_fix_clears_it(tmp_path):
    """The script copied into a throwaway tree takes that tree as its root."""
    root = make_tree(tmp_path, {"alpha": skill_text("alpha")})
    (root / "scripts").mkdir()
    copy = root / "scripts" / "check_skill_commands.py"
    shutil.copy(SCRIPTS / "check_skill_commands.py", copy)

    failed = run_script(copy)
    assert failed.returncode == 1
    assert "skills/alpha/SKILL.md has no slash command" in failed.stderr

    fixed = run_script(copy, "--fix")
    assert fixed.returncode == 0, fixed.stderr
    assert "created .claude/commands/alpha.md" in fixed.stdout

    assert run_script(copy).returncode == 0


def test_the_command_line_rejects_an_unknown_argument(tmp_path):
    result = run_script(SCRIPTS / "check_skill_commands.py", "--bogus")
    assert result.returncode == 2
