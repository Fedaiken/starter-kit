#!/usr/bin/env python3
"""Every skill has a slash command, and every slash command runs something that exists.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere):
    <venv python> scripts/check_skill_commands.py          # exit 1 on any gap, naming each
    <venv python> scripts/check_skill_commands.py --fix    # create the missing wrappers

WHY THIS EXISTS
---------------
The owner drives this project from the `/` menu, so a skill with no command
beside it is invisible, and a command left behind by a deleted skill reads as
current while it sends the next session to a file that is gone. Keeping
`skills/` and `.claude/commands/` in step by hand is the "remember to do it"
discipline the Cardinal Rule rejects (`CLAUDE.md`), so the step is a check.

THE RULE
--------
1. SKILL -> WRAPPER. Every `skills/<name>/SKILL.md` has a thin wrapper at
   `.claude/commands/<name>.md`, and that wrapper names the skill's SKILL.md.
2. WRAPPER -> TARGET (the closed set). Every file under `.claude/commands/` runs
   something that exists. A wrapper that names `skills/<x>/SKILL.md` needs that
   skill on disk. A wrapper that names no skill is a command with no skill
   behind it (`check-docs.md` runs the gate script), and it must name a script
   under `scripts/` that exists -- otherwise it is a `/` menu entry that runs
   nothing, and it is reported as an orphan.
3. A tree with no skill at all is an error (exit 2), never a clean run: a check
   that finds nothing to inspect has proved nothing.

A wrapper is matched to its skill by the SKILL.md path it names, not by its
file name. The convention is `<name>.md` for `skills/<name>/`, and rule 1
holds a skill to it; a wrapper under any other name (an alias, a namespaced
folder) is fine as long as it names a skill that exists.

`--fix` creates a missing wrapper from the skill's frontmatter: the menu line
is the skill's `purpose:` if it has one, else the first sentence of its
`description:`. It only creates. It never overwrites a wrapper (a hand-tuned
one is safe), never deletes an orphan (the report names the file for the
owner), and never touches `.claude/settings.json`.

WHAT THIS DELIBERATELY DOES NOT CHECK
-------------------------------------
That a wrapper's prose is right (`--fix` writes a pointer at the workflow; the
file is hand-tunable afterwards). And whether a slash command a skill names
belongs to the harness (`/loop`, `/schedule`) and needs a `Skill(<name>)` allow
rule in `.claude/settings.json` to run without a permission dialog: no skill
here names one today, and `settings.json` is not this script's to write.

Ported 2026-10-26 from a sibling project's check of the same name, reduced to
this project's layout: no trigger registry, no settings rules.

Exit codes:
    0 = every skill has its wrapper and every wrapper runs something that exists
    1 = at least one gap; each is named, with the fix
    2 = the skills cannot be read at all (none found), or a bad argument
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple, Sequence

import yaml

ROOT = Path(__file__).resolve().parent.parent

#: Where the wrappers live, below the project root.
COMMANDS = (".claude", "commands")

#: A skill's workflow file, as a wrapper writes it. The lookbehind keeps
#: `notskills/x/SKILL.md` and `a/skills/x/SKILL.md` from counting as a pointer
#: at this project's `skills/x/SKILL.md`.
SKILL_REF = re.compile(r"(?<![\w./-])skills/([A-Za-z0-9][A-Za-z0-9_-]*)/SKILL\.md")

#: A script a standalone wrapper runs, written the same way.
SCRIPT_REF = re.compile(r"(?<![\w./-])scripts/([A-Za-z0-9_-]+\.py)")

#: The YAML block between a file's opening and closing `---` lines.
FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)

#: A menu line longer than this is cut; the wrapper is hand-tunable afterwards.
MENU_LINE = 100


class SkillError(Exception):
    """The skills cannot be read at all. Never a silent clean run."""


class Skill(NamedTuple):
    """One skill, as its frontmatter declares itself."""

    name: str      # the folder name -- and the stem its wrapper is expected under
    workflow: str  # repo-relative posix path of its SKILL.md
    summary: str   # the one line the `/` menu shows; "" when the frontmatter is unusable
    broken: str    # why the frontmatter cannot be used; "" when it can


def frontmatter(path: Path) -> dict:
    """The YAML block between the opening `---` fences, as a mapping.

    Raises ValueError, naming what is wrong, when there is no usable block.
    """
    match = FRONTMATTER.match(path.read_text(encoding="utf-8-sig"))
    if not match:
        raise ValueError("it does not open with a closed `---` frontmatter block")
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"its frontmatter is not valid YAML: {' '.join(str(exc).split())}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("its frontmatter is not a mapping")
    return loaded


def menu_line(meta: dict) -> str:
    """The `/` menu line for a skill: `purpose:` if it has one, else the first
    sentence of `description:`; markdown stripped, one line, at most MENU_LINE."""
    purpose = " ".join(str(meta.get("purpose") or "").split())
    if purpose:
        text = purpose
    else:
        lines = str(meta.get("description") or "").strip().splitlines()
        text = lines[0].split(". ")[0] if lines else ""
    text = " ".join(re.sub(r"[*`]", "", text).split()).rstrip(".")
    return text if len(text) <= MENU_LINE else text[:MENU_LINE - 3].rstrip() + "..."


def skills(root: Path = ROOT) -> list[Skill]:
    """Every skill under `skills/`, in folder order.

    A skill whose frontmatter cannot be used is returned with `broken` set, so
    the report can name it beside the other gaps instead of hiding them behind
    one exception. No skill at all raises: that is a check with nothing to look
    at, which passes vacuously.
    """
    found: list[Skill] = []
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        name = path.parent.name
        workflow = path.relative_to(root).as_posix()
        try:
            meta = frontmatter(path)
            if not str(meta.get("description") or "").strip():
                raise ValueError("its frontmatter carries no `description:`")
        except ValueError as exc:
            found.append(Skill(name, workflow, "", str(exc)))
            continue
        found.append(Skill(name, workflow, menu_line(meta), ""))
    if not found:
        raise SkillError(
            f"no skills/*/SKILL.md under {root} -- a check that finds no skills "
            f"passes vacuously, so this is an error, not a clean run")
    return found


def wrappers(root: Path = ROOT) -> dict[str, str]:
    """Every `.md` under `.claude/commands/`: its path below that folder, minus
    `.md`, mapped to its text. Folders are walked, so a namespaced wrapper is seen."""
    folder = root.joinpath(*COMMANDS)
    return {path.relative_to(folder).with_suffix("").as_posix():
            path.read_text(encoding="utf-8-sig", errors="replace")
            for path in sorted(folder.rglob("*.md"))}


def wrapper_text(skill: Skill) -> str:
    """A new wrapper: the menu line in frontmatter, then the pointer at the workflow."""
    line = yaml.safe_dump({"description": skill.summary}, allow_unicode=True,
                          default_flow_style=False, width=10**6)
    return (f"---\n{line}---\n\n"
            f"Execute the workflow in `{skill.workflow}`.\n\n"
            "Read that file now and follow it exactly — it is the authority on "
            "this run. Do not improvise the process from memory.\n\n"
            "$ARGUMENTS\n")


def check(fix: bool = False, root: Path = ROOT) -> list[str]:
    """Every problem, as a line a reader can act on. Empty means the gate passes.

    Raises SkillError when `root` has no skill. With `fix`, creates the missing
    wrappers (printing each) and reports whatever it did not fix.
    """
    found = skills(root)
    present = wrappers(root)
    names = {skill.name for skill in found}
    problems: list[str] = []

    for skill in found:
        if skill.broken:
            problems.append(f"{skill.workflow} cannot be invoked: {skill.broken}")
        stem = skill.name
        target = root.joinpath(*COMMANDS) / f"{stem}.md"
        if stem not in present:
            if fix and not skill.broken and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("w", encoding="utf-8", newline="\n") as handle:
                    handle.write(wrapper_text(skill))
                print(f"created .claude/commands/{stem}.md")
                continue
            problems.append(
                f"{skill.workflow} has no slash command (expected "
                f".claude/commands/{stem}.md)" + ("" if skill.broken else " - run with --fix"))
        elif stem not in SKILL_REF.findall(present[stem]):
            problems.append(
                f".claude/commands/{stem}.md does not name {skill.workflow}, so "
                f"/{stem} does not run the skill; point it there")

    # The closed set: a wrapper nothing stands behind is a `/` menu entry that
    # outlived the skill it fronted.
    for stem, text in present.items():
        path = f".claude/commands/{stem}.md"
        named = list(dict.fromkeys(SKILL_REF.findall(text)))
        for gone in (n for n in named if n not in names):
            problems.append(
                f"{path} points at skills/{gone}/SKILL.md, which does not exist; "
                f"delete the wrapper, or restore the skill")
        if stem in names or named:
            continue
        if not any((root / "scripts" / s).is_file() for s in SCRIPT_REF.findall(text)):
            problems.append(
                f"{path} points at no skill and names no script under scripts/ "
                f"that exists, so it runs nothing; delete it, or point it at "
                f"the skill it fronts")
    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fix", action="store_true",
                        help="create the missing wrappers (never overwrites, never deletes)")
    return parser


def main(argv: Sequence[str] = (), root: Path = ROOT) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        problems = check(fix=args.fix, root=root)
        counted = len(skills(root))
    except SkillError as exc:
        print(f"FAIL - {exc}", file=sys.stderr)
        return 2
    if problems:
        print(f"FAIL - {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"OK - {counted} skill(s), every one with a slash command; "
          f"{len(wrappers(root))} wrapper(s), every one running something that exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
