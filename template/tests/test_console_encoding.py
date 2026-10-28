"""Every project script that prints must force UTF-8 on stdout and stderr.

Why this exists: the Windows console encodes as cp1252, which has no mapping
for the notation this project writes in -- arrows, check marks, em-dashes
quoted from a game file. A script that echoes such a line to report a finding
dies with UnicodeEncodeError, so a gate meant to halt loudly shows a traceback
instead, and the finding never reaches the reader. `PYTHONUTF8` in
`.claude/settings.json` covers Claude's own windows and nothing else: not a
git hook, not the owner's terminal.

The suite passing is what hides it -- pytest captures output in UTF-8 and
never touches the console path -- so the check is on the source, plus one run
of the guard under a cp1252 stdout to prove the mechanism.

Ported 2026-10-26 from FACOWORK's `tests/test_console_encoding.py`. Adapted:
only a script that prints (a `print(...)` call or a write to `sys.stdout` /
`sys.stderr`) needs the guard -- a module that is only imported prints
through its caller's streams. The guard is any `<stream>.reconfigure(...)`
call with `encoding="utf-8"`, at import or in `main()`.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: cp1252 cannot encode any of these.
UNENCODABLE = "→↔✓≠≤⚠"

GUARD = ('import sys\n'
         'for _s in (sys.stdout, sys.stderr):\n'
         '    if hasattr(_s, "reconfigure"):\n'
         '        _s.reconfigure(encoding="utf-8")\n')


def scripts(root=ROOT):
    paths = sorted((root / "scripts").glob("*.py"))
    paths += sorted(p for p in (root / "skills").rglob("*.py") if "archive" not in p.parts)
    paths = [p for p in paths
             if "__pycache__" not in p.parts and not p.name.startswith("test_")]
    if not paths:
        raise RuntimeError(f"no scripts under {root} -- a scan of nothing passes")
    return paths


def _is_std_stream(node):
    return (isinstance(node, ast.Attribute) and node.attr in ("stdout", "stderr")
            and isinstance(node.value, ast.Name) and node.value.id == "sys")


def prints(tree):
    """Whether the module prints: `print(...)` or `sys.stdout/stderr.write(...)`."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            return True
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "write"
                and _is_std_stream(node.func.value)):
            return True
    return False


def guarded(tree):
    """Whether the module calls `<x>.reconfigure(encoding="utf-8", ...)`."""
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "reconfigure"
                and any(k.arg == "encoding" and isinstance(k.value, ast.Constant)
                        and str(k.value.value).lower().replace("_", "-") in ("utf-8", "utf8")
                        for k in node.keywords)):
            return True
    return False


def unguarded(root=ROOT):
    bad = []
    for path in scripts(root):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if prints(tree) and not guarded(tree):
            bad.append(path.relative_to(root).as_posix())
    return bad


def test_every_printing_script_forces_utf8_output():
    bad = unguarded()
    assert not bad, (
        "these scripts print without forcing UTF-8; on the Windows console "
        "(cp1252) a quoted arrow raises UnicodeEncodeError instead of being "
        "reported. Add the guard after the imports:\n  " + "\n  ".join(bad))


def test_the_scan_reads_this_projects_scripts():
    names = {p.name for p in scripts()}
    assert {"check_docs.py", "desk_record.py", "lane_guard.py"} <= names, names


def test_a_planted_printing_script_without_the_guard_fails(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "loud.py").write_text('print("found")\n', encoding="utf-8")
    (tmp_path / "scripts" / "writes.py").write_text(
        'import sys\nsys.stderr.write("found")\n', encoding="utf-8")
    assert unguarded(tmp_path) == ["scripts/loud.py", "scripts/writes.py"]


def test_a_guarded_script_and_a_silent_module_pass(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "loud.py").write_text(GUARD + 'print("found")\n', encoding="utf-8")
    (tmp_path / "scripts" / "replace.py").write_text(
        GUARD.replace('encoding="utf-8"', 'encoding="utf-8", errors="replace"')
        + 'print("found")\n', encoding="utf-8")
    (tmp_path / "scripts" / "library.py").write_text("X = 1\n", encoding="utf-8")
    assert unguarded(tmp_path) == []


def test_a_guard_naming_another_encoding_is_not_the_guard(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "loud.py").write_text(
        GUARD.replace("utf-8", "cp1252") + 'print("found")\n', encoding="utf-8")
    assert unguarded(tmp_path) == ["scripts/loud.py"]


def test_a_scan_of_nothing_raises(tmp_path):
    with pytest.raises(RuntimeError, match="scan of nothing"):
        scripts(tmp_path)


def test_the_guard_actually_works_on_a_cp1252_console():
    """Not a source check -- run the guard with a cp1252 stdout.

    The bare print is the crash; the guarded one comes through. Bytes out of
    the subprocess, decoded here, so this test is not itself the defect
    `tests/test_subprocess_encoding.py` refuses.
    """
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    bare = subprocess.run([sys.executable, "-c", 'print("%s")' % UNENCODABLE],
                          capture_output=True, env=env, check=False)
    assert bare.returncode != 0 and b"UnicodeEncodeError" in bare.stderr, bare
    proc = subprocess.run([sys.executable, "-c", GUARD + 'print("%s")\n' % UNENCODABLE],
                          capture_output=True, env=env, check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert UNENCODABLE.encode("utf-8") in proc.stdout
