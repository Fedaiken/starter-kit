"""No live file may invoke a bare `python3` or `python`.

Why this exists: on this machine `python3` is the Microsoft Store's
app-execution-alias stub -- it prints "Python was not found" and exits 9009
without running anything -- and a bare `python` is the system install, which
does not carry this project's packages. Every project script runs as
`<venv python> scripts/<name>.py` from the project root (`.venv/Scripts/python.exe`
here, `kb/platform-and-tools.md`). A skill or docstring that says `python`
hands the next window a command that fails or runs the wrong interpreter.

Ported 2026-10-26 from FACOWORK's `tests/test_interpreter_references.py`: a
one-time sweep protects nothing against the next skill edit, so the rule lives
here, where a bare invocation fails the suite.

Out of scope, as there: records of commands that really were run (`Archive/`,
`Working/`, `coordination/`, the untriaged `Inbox/`) -- rewriting them would
falsify the record -- and `tests/`, which name the stub on purpose. Allowed in
a live file: a `#!` line, prose explaining the stub, `<venv python>` (the
project interpreter), `<python>` (the Starter Kit's own name for a machine with
no venv yet) and the explicit `python.exe` / `.venv/...` forms.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Folders whose contents are a historical record or untriaged, not live
#: instructions -- or not this project's at all.
EXCLUDED_PARTS = {"Archive", "Working", "coordination", "Inbox", "tests",
                  "__pycache__", ".venv", ".git", "node_modules"}

SUFFIXES = {".md", ".py", ".txt"}

#: A command line, not a shebang and not prose about the stub itself.
BARE_PYTHON = re.compile(r"(?<![\w./\\-])python3?(?=\s+[-\w\"'./])")


def live_files(root=ROOT):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        rel = path.relative_to(root)
        if EXCLUDED_PARTS & set(rel.parts):
            continue
        yield rel.as_posix(), path


def offending_lines(rel, path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    bad = []
    for n, line in enumerate(text.split("\n"), 1):
        if path.suffix == ".py" and n == 1 and line.startswith("#!"):
            continue          # shebangs are documentation, never executed here
        if "python3" in line and "not found" in line:
            continue          # prose explaining the stub
        if BARE_PYTHON.search(line):
            bad.append("%s:%d: %s" % (rel, n, line.strip()[:110]))
    return bad


def findings(root=ROOT):
    found = []
    for rel, path in live_files(root):
        found += offending_lines(rel, path)
    return found


def test_no_bare_python_invocations():
    found = findings()
    assert not found, (
        "bare python/python3 invocation in a live file -- write <venv python> "
        "(.venv/Scripts/python.exe here):\n  " + "\n  ".join(found))


def test_the_scan_reads_this_project():
    """A guard on the guard: an exclusion that swallowed the tree would pass."""
    rels = {rel for rel, _ in live_files()}
    assert {"CLAUDE.md", "scripts/check_docs.py", "skills/lane/SKILL.md"} <= rels, rels


def test_a_planted_bare_invocation_is_found(tmp_path):
    (tmp_path / "skills" / "x").mkdir(parents=True)
    (tmp_path / "skills" / "x" / "SKILL.md").write_text(
        "Run `python scripts/check_docs.py` first.\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "tool.py").write_text(
        '"""Usage: python3 -m tool"""\n', encoding="utf-8")
    assert findings(tmp_path) == [
        "scripts/tool.py:1: \"\"\"Usage: python3 -m tool\"\"\"",
        "skills/x/SKILL.md:1: Run `python scripts/check_docs.py` first.",
    ]


def test_the_allowed_forms_are_not_findings(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "ok.py").write_text(
        "#!/usr/bin/env python3\n"
        '"""<venv python> scripts/ok.py\n'
        ".venv/Scripts/python.exe scripts/ok.py\n"
        "python.exe -m venv .venv\n"
        "<python> KIT/scripts/new_project.py profile --show\n"
        "python3 is the Store stub; run it and you get Python was not found.\n"
        'A bare `python` is the system install."""\n', encoding="utf-8")
    assert findings(tmp_path) == []


def test_records_and_tests_are_out_of_scope(tmp_path):
    for folder in ("Archive", "Working/x", "coordination", "Inbox", "tests"):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / "note.md").write_text("python scripts/a.py\n", encoding="utf-8")
    assert findings(tmp_path) == []
