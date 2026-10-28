"""No subprocess in this project decodes its output by locale.

`text=True` reads as "give me a string" and means something narrower: decode
with `locale.getpreferredencoding(False)`. On this Windows machine that is
**cp1252**, so every byte a tool wrote as UTF-8 -- git's output, a script of
ours printing an arrow -- comes back as a different character, and comes back
silently, because cp1252 has a mapping for almost every byte and raises on
almost none. `universal_newlines=True` is the older spelling and decodes the
same way.

Ported 2026-10-26 from Fantasy_Football's `scripts/check_subprocess_encoding.py`
and its test, where a `git log` through `text=True` mojibake'd an em-dash in
every date it resolved, exited 0, and was found downstream by a gate looking at
something else. The sweep that followed found 25 sites of the same shape, which
makes it a class rather than a defect: the shape is refused here instead of
fixed by hand one site at a time.

A TEST, NOT A GATE SCRIPT. The rule has no command line anybody runs on its
own; the suite is where it is read, so the scan lives in the test module and
nothing else imports it.

WHAT IS DELIBERATELY NOT FLAGGED
--------------------------------
* A bytes call -- no `text=`, no `universal_newlines=`. The caller decodes
  itself, and `bytes.decode()` defaults to UTF-8 everywhere.
* `text=False` (or `None`) spelled out: bytes on purpose.
* A call whose keywords this cannot see (`subprocess.run(**kw)`).
* A function merely NAMED `run`. The callable is resolved back to an
  `import subprocess` in the same module -- an alias, an attribute, or a
  `from subprocess import run` -- so a local helper is not this.

THE FIX IS ALWAYS `encoding="utf-8"`, NEVER `errors=`. `errors="replace"`
substitutes a character instead of decoding one: the same silence under
another name. A byte that is genuinely not UTF-8 should raise and be read.

Every rule is proved by RECALL: the defect is planted in a file under
`tmp_path`, put through the real scan, and the finding read back. A clean scan
of the real tree proves nothing alone -- it is also what a scan of the wrong
folder looks like.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Every tree whose Python this covers.
ROOTS = ("scripts", "tests")

#: The `subprocess` callables that accept the decoding keywords. `call` and
#: `check_call` return an exit code and are here anyway: one edit away from
#: being read for their output.
CALLS = frozenset({"run", "check_output", "check_call", "call", "Popen"})

#: The keywords that turn the pipes into `str`.
DECODING = ("text", "universal_newlines")

DEFECT = (
    "import subprocess\n"
    "proc = subprocess.run(['git', 'log'], capture_output=True, text=True,\n"
    "                      check=False)\n"
)


class Finding(NamedTuple):
    path: str        # root-relative posix path
    lineno: int
    callable_: str   # how the call is spelled, e.g. "subprocess.run"
    keyword: str     # which of DECODING made it a decoding call

    def render(self) -> str:
        return (f"{self.path}:{self.lineno}  {self.callable_}(... "
                f"{self.keyword}=True) with no encoding= -- decodes as cp1252 "
                f'here. FIX: pass encoding="utf-8" beside it (not errors=)')


def subprocess_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """(module aliases of `subprocess`, names imported straight out of it)."""
    aliases: set[str] = set()
    bare: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    aliases.add(alias.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                bare.add(alias.asname or alias.name)
    return aliases, bare


def called_name(node: ast.Call, aliases: set[str], bare: set[str]) -> str | None:
    """`"subprocess.run"` for a call that is one, else None."""
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in CALLS:
        if isinstance(func.value, ast.Name) and func.value.id in aliases:
            return f"{func.value.id}.{func.attr}"
    if isinstance(func, ast.Name) and func.id in bare and func.id in CALLS:
        return func.id
    return None


def decodes(node: ast.Call) -> str | None:
    """The keyword making this call return `str`, or None for bytes. Anything
    but a literal False/None counts: a call that MIGHT decode must say how."""
    for keyword in node.keywords:
        if keyword.arg not in DECODING:
            continue
        if isinstance(keyword.value, ast.Constant) and keyword.value.value in (False, None):
            continue
        return keyword.arg
    return None


def findings_for(source: str, path: str) -> list[Finding]:
    """Every decoding subprocess call in one module source with no encoding."""
    tree = ast.parse(source)
    aliases, bare = subprocess_names(tree)
    if not aliases and not bare:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = called_name(node, aliases, bare)
        keyword = decodes(node) if name else None
        if keyword is None or any(k.arg == "encoding" for k in node.keywords):
            continue
        found.append(Finding(path, node.lineno, name, keyword))
    return found


def modules(root: Path = ROOT) -> list[Path]:
    """Every Python file under ROOTS. Raises on an empty scan: a scan of
    nothing passes in the same words a real pass uses."""
    found = [p for folder in ROOTS for p in sorted((root / folder).glob("*.py"))]
    if not found:
        raise RuntimeError(f"no *.py under {ROOTS} in {root} -- a scan of nothing passes")
    return found


def scan(root: Path = ROOT) -> list[Finding]:
    found = []
    for path in modules(root):
        found += findings_for(path.read_text(encoding="utf-8"),
                              path.relative_to(root).as_posix())
    return found


def plant(root: Path, source: str, folder: str = "scripts") -> list[Finding]:
    """Write `source` as a module under `root/folder` and scan `root`."""
    (root / folder).mkdir(parents=True, exist_ok=True)
    (root / folder / "planted.py").write_text(source, encoding="utf-8")
    return scan(root)


# --- the enforcement -----------------------------------------------------------


def test_no_subprocess_in_this_project_decodes_by_locale():
    findings = scan()
    assert not findings, (
        "subprocess calls decoding with whatever the platform says:\n  "
        + "\n  ".join(f.render() for f in findings))


# --- recall: the rule fires on the real defect ---------------------------------


def test_the_planted_defect_is_found(tmp_path):
    found = plant(tmp_path, DEFECT)
    assert [(f.path, f.callable_, f.keyword) for f in found] == [
        ("scripts/planted.py", "subprocess.run", "text")], found


def test_the_older_spelling_is_the_same_defect(tmp_path):
    found = plant(tmp_path, DEFECT.replace("text=True", "universal_newlines=True"))
    assert [f.keyword for f in found] == ["universal_newlines"], found


@pytest.mark.parametrize("name", sorted(CALLS))
def test_every_decoding_call_in_subprocess_is_covered(tmp_path, name):
    found = plant(tmp_path, DEFECT.replace("subprocess.run", f"subprocess.{name}"))
    assert [f.callable_ for f in found] == [f"subprocess.{name}"], found


def test_an_alias_and_a_bare_import_are_both_reached(tmp_path):
    assert len(plant(tmp_path, "import subprocess as sp\n"
                               "sp.run(['git'], text=True, check=False)\n")) == 1
    assert len(plant(tmp_path, "from subprocess import run\n"
                               "run(['git'], text=True, check=False)\n")) == 1


def test_the_scan_reads_every_root_it_names(tmp_path):
    for folder in ROOTS:
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "planted.py").write_text(DEFECT, encoding="utf-8")
    assert sorted(f.path for f in scan(tmp_path)) == sorted(
        f"{folder}/planted.py" for folder in ROOTS)


def test_a_scan_of_nothing_raises_rather_than_passing(tmp_path):
    for folder in ROOTS:
        (tmp_path / folder).mkdir()
    with pytest.raises(RuntimeError, match="scan of nothing"):
        scan(tmp_path)


# --- the exemptions, each planted and each expected to come back empty --------


def test_the_fix_itself_is_not_a_finding(tmp_path):
    assert not plant(tmp_path, DEFECT.replace("text=True", 'text=True, encoding="utf-8"'))


def test_a_bytes_call_is_not_a_finding(tmp_path):
    assert not plant(tmp_path, "import subprocess\n"
                               "subprocess.run(['git'], capture_output=True, check=False)\n")


def test_text_false_spelled_out_is_not_a_finding(tmp_path):
    assert not plant(tmp_path, DEFECT.replace("text=True", "text=False"))


def test_a_local_function_named_run_is_not_a_finding(tmp_path):
    assert not plant(tmp_path, "def run(argv, text=False):\n"
                               "    return argv\n"
                               "run(['git'], text=True)\n")


def test_a_module_that_never_imports_subprocess_is_not_read(tmp_path):
    assert not plant(tmp_path, "import shutil\nshutil.run(['git'], text=True)\n")
