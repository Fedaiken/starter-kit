#!/usr/bin/env python
"""The document gate: budgets, reachability, kb frontmatter, memory caps.

    python scripts/check_docs.py              # run every check; exit 1 on a hit
    python scripts/check_docs.py --report     # every budgeted file at % used, then the checks
    python scripts/check_docs.py --write-kb   # render kb/README.md from frontmatter, then the checks

WHY THIS EXISTS
---------------
Fantasy_Football had two documents reach 63 KB and 94 KB by the same route:
every session appended, and no session was ever the one that had to stop.
Nothing there could name a size at which a document was wrong, so no size ever
was. A budget nobody enforces is a preference, and a preference loses to the
next append. FF's answer is four gates; this file is those four in one script,
sized for a project with no venv and no test suite. Ported to HAZELHURST
2026-09-24 and carried by the Starter Kit from there (`kb/document-budgets.md`).
This file is kit-owned: an improvement made here is offered back to the kit by
`python scripts/kit_sync.py` at close-session.

THE CHECKS
----------
1. BUDGET. Every tracked `.md`/`.html` outside `exempt_dirs` must match exactly
   one row in `doc_budgets.yaml` and weigh no more than its `budget`. Size is
   the CRLF-normalised byte count, so the verdict does not flap between "just
   written with LF" and "just checked out". A file with less than 5% headroom
   is named, non-fatally. Budgets only go down: each row's ceiling is the
   minimum it has held in any committed revision of the YAML, so raising one
   to silence a failure stays red until it is lowered again.
2. ORPHANS. A tier-3 document must be named — by path, or by basename not
   preceded by a path character — by a reader. The root readers are
   `CLAUDE.md`, `kb/README.md` and every `skills/*/SKILL.md`: the files a
   session reads without being told to. A tier-3 file nothing points at is
   unread and looks current. Two row flags extend the roots, both tier 3 only:
   `reader: true` makes each file the row claims a reader once a reader names
   it (a record a session opens to find things, like a trip log), so the
   chain always ends at a root and an orphaned reader reaches nothing;
   `reached_by_folder: true` counts a file as named when a reader names the
   folder it sits in (`Travelers/`), for a folder whose convention is its
   index. Added 2026-09-26: every new traveler profile failed until CLAUDE.md
   was hand-edited to list it, and a trip-folder plan failed although
   `Trips/Trip_Log.md` names its folder.
3. KB. Every `kb/*.md` opens with the frontmatter block (`title`, `topic`,
   `keywords`, `kind`, `retrieved`, `status`), and `kb/README.md` is rendered
   from it. A hand-typed row is drift and fails; `--write-kb` renders it.
4. MEMORY. Every entry in this project's auto-memory folder is at most 2,000 b,
   carries `name`/`description`/`metadata.type`, and has a pointer line in
   `MEMORY.md` under 220 b; no pointer names a missing entry; `MEMORY.md` stays
   under 140 lines (the harness truncates at 200).
5. INTAKE. Every Status cell in `Intake_Checklist.md` starts with a listed
   status word, carries a backticked pointer, and holds no digit outside a
   backticked span, except a `§` section reference (`§3`, `§4F`). Added
   2026-09-24: after one job the checklist stood at 7,688 of 8,000 b because
   its cells restated kb figures and dates, and one had already drifted from
   the kb entry it pointed at. A cell that can only say "which document, who,
   where to read" cannot drift. The first version rejected only `$` amounts and
   ISO dates; `(2025-03)`, `12/15/2023`, `Dec 2024` and `4,400.00` all passed
   a rule that said "no figures". One rule with no format list has no format
   to miss. A lookup identifier the cell needs (an AIN, a form number) goes in
   backticks.
6. SETUP. No document holds a `{{FILL:` or `{{KIT:` marker. The Starter Kit
   seeds a project with these where the setup interview's answers go; one left
   behind is a section nobody wrote that reads as if someone had.

There is no --fix. Deciding which paragraph is rationale that belongs in a
docstring, which fact belongs in kb/, and which narrative git already holds is
the whole job. Each violation prints the row's `rule:` instead.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BUDGETS_FILE = ROOT / "doc_budgets.yaml"
DOCUMENT_SUFFIXES = (".md", ".html")
TIERS = (1, 2, 3)
BAND_DIVISOR = 20  # under 5% headroom is named

# --- kb contract -------------------------------------------------------------
KB_REQUIRED = ("title", "topic", "keywords", "kind", "retrieved", "status")
KB_KINDS = ("probe", "decision", "reference")
KB_STATUSES = ("current", "superseded")
KB_SECTIONS = (("probe", "Probes"), ("decision", "Decisions"), ("reference", "References"))
KB_INDEX = "kb/README.md"

# --- memory contract ---------------------------------------------------------
MEMORY_CAP = 2000
MEMORY_INDEX_LINE_CAP = 220
MEMORY_INDEX_MAX_LINES = 140
MEMORY_INDEX = "MEMORY.md"
MEMORY_TYPES = ("user", "feedback", "project", "reference")

# --- intake contract ---------------------------------------------------------
INTAKE_FILE = "Intake_Checklist.md"
INTAKE_STATUS_WORDS = ("on file", "found", "partly found", "needed", "action needed", "urgent")
_INTAKE_STATUS = re.compile(
    r"^\*{0,2}(?:" + "|".join(re.escape(w) for w in sorted(INTAKE_STATUS_WORDS, key=len, reverse=True)) + r")\*{0,2}(?![\w-])"
)
_BACKTICKED = re.compile(r"`[^`]*`")
_SECTION_REF = re.compile(r"§\s?\d+[A-Za-z]?")
_DIGIT_TOKEN = re.compile(r"\S*\d\S*")

# --- reachability sources ----------------------------------------------------
SOURCE_PATHS = ("CLAUDE.md", KB_INDEX)
SOURCE_GLOBS = ("skills/*/SKILL.md",)
ORPHAN_FLAGS = ("reader", "reached_by_folder")
_PATH_CHARS = r"[\w/\\.-]"

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


class ConfigError(Exception):
    """doc_budgets.yaml is malformed. Exit 2: nothing was checked."""


# --- helpers -----------------------------------------------------------------


def measured_size(text: str) -> int:
    """Bytes as the file checks out under autocrlf: every line ending CRLF."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    return len(normalised.encode("utf-8"))


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def tree_documents() -> list[str]:
    """Every tracked-or-untracked-but-not-ignored document in the working tree."""
    out = git("ls-files", "--cached", "--others", "--exclude-standard")
    return sorted(p for p in out.splitlines() if p.endswith(DOCUMENT_SUFFIXES) and (ROOT / p).is_file())


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`*` never crosses `/`, so `kb/*.md` cannot annex `kb/sub/x.md`."""
    out = []
    for ch in pattern:
        out.append("[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch))
    return re.compile("".join(out) + r"\Z")


def read_frontmatter(text: str) -> tuple[dict | None, str | None]:
    """(block as dict, error). (None, None) when there is no block at all."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return None, None
    for i in range(1, len(lines)):
        if lines[i].strip() in {"---", "..."}:
            block = "\n".join(lines[1:i])
            try:
                loaded = yaml.safe_load(block)
            except (yaml.YAMLError, ValueError) as exc:
                problem = getattr(exc, "problem", None) or str(exc)
                return {}, f"frontmatter is not valid YAML: {str(problem).splitlines()[0]}"
            return (loaded if isinstance(loaded, dict) else {}), None
    return None, None


# --- budgets -----------------------------------------------------------------


def _validate_entry(entry: object, index: int) -> dict:
    where = f"entries[{index}]"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where} is not a mapping")
    has_path, has_glob = "path" in entry, "glob" in entry
    if has_path == has_glob:
        raise ConfigError(f"{where} must have exactly one of `path:` or `glob:`")
    selector = entry["path"] if has_path else entry["glob"]
    if has_glob and "**" in selector:
        raise ConfigError(f"{where} glob {selector!r} uses `**`, which is refused")
    if not selector.endswith(DOCUMENT_SUFFIXES):
        raise ConfigError(f"{where} ({selector}) names a file kind this gate never scans")
    if entry.get("tier") not in TIERS:
        raise ConfigError(f"{where} ({selector}) tier must be one of {TIERS}")
    generated = entry.get("generated", False) is True
    if generated == ("budget" in entry):
        raise ConfigError(f"{where} ({selector}) must declare exactly one of `budget` or `generated: true`")
    if not generated:
        budget = entry["budget"]
        if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
            raise ConfigError(f"{where} ({selector}) budget must be a positive integer")
        if not isinstance(entry.get("rule"), str) or not entry["rule"].strip():
            raise ConfigError(f"{where} ({selector}) needs a `rule:` saying where the bytes go")
    for flag in ORPHAN_FLAGS:
        if flag in entry and entry[flag] is not True:
            raise ConfigError(f"{where} ({selector}) `{flag}:` is either `true` or absent")
        if entry.get(flag) and entry["tier"] != 3:
            raise ConfigError(f"{where} ({selector}) `{flag}:` is for tier-3 rows; tiers 1 and 2 are never orphan-checked, so an unread reader there would go unnoticed")
    return entry


def parse_budgets(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ConfigError("the budget declaration must be a mapping")
    exempt = raw.get("exempt_dirs")
    if not isinstance(exempt, list) or not exempt:
        raise ConfigError("`exempt_dirs` must be a non-empty list")
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ConfigError("`entries` must be a non-empty list")
    return {"exempt_dirs": list(exempt), "entries": [_validate_entry(e, i) for i, e in enumerate(entries)]}


def load_budgets() -> dict:
    try:
        raw = yaml.safe_load(BUDGETS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"{BUDGETS_FILE.name} does not exist") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{BUDGETS_FILE.name} is not valid YAML: {exc}") from exc
    return parse_budgets(raw)


def _selector(entry: dict) -> str:
    return entry["path"] if "path" in entry else entry["glob"]


def historical_floors() -> dict[str, int]:
    """The lowest budget each selector has held in any committed revision.

    Read from every revision rather than HEAD alone: a HEAD comparison
    re-floors the moment a raise is committed, which is the loophole FF found
    already used twice in one commit.
    """
    floors: dict[str, int] = {}
    try:
        revs = git("log", "--format=%H", "--", BUDGETS_FILE.name).split()
    except RuntimeError:
        return floors
    for rev in revs:
        try:
            raw = yaml.safe_load(git("show", f"{rev}:{BUDGETS_FILE.name}"))
        except (RuntimeError, yaml.YAMLError):
            continue
        for entry in (raw or {}).get("entries", []) or []:
            if not isinstance(entry, dict) or "budget" not in entry:
                continue
            key = entry.get("path") or entry.get("glob")
            budget = entry["budget"]
            if isinstance(key, str) and isinstance(budget, int) and not isinstance(budget, bool):
                floors[key] = min(floors.get(key, budget), budget)
    return floors


def assign(files: list[str], budgets: dict) -> dict[str, list[dict]]:
    exempt = set(budgets["exempt_dirs"])
    out: dict[str, list[dict]] = {}
    for rel in files:
        matched = [e for e in budgets["entries"] if ("path" in e and e["path"] == rel) or ("glob" in e and glob_to_regex(e["glob"]).match(rel))]
        exact = [e for e in matched if "path" in e]
        if exact:
            out[rel] = exact
            continue
        if rel.split("/", 1)[0] in exempt:
            continue
        out[rel] = matched
    return out


def check_budgets(files: list[str], budgets: dict, report: bool) -> tuple[list[str], list[str]]:
    """(failures, notes). Notes are the headroom band and the optional report."""
    failures: list[str] = []
    notes: list[str] = []
    rows: list[tuple[str, int, int, int]] = []
    floors = historical_floors()
    for entry in budgets["entries"]:
        key = _selector(entry)
        if "budget" in entry and key in floors and entry["budget"] > floors[key]:
            failures.append(f"{key}: budget raised to {entry['budget']} b, but it once held {floors[key]} b. Budgets only go down; lower it and trim the file.")
    for rel, matched in sorted(assign(files, budgets).items()):
        if not matched:
            failures.append(f"{rel}: no doc_budgets.yaml row. A document does not exist until someone decides its tier and budget.")
            continue
        if len(matched) > 1:
            failures.append(f"{rel}: claimed by {len(matched)} rows ({', '.join(_selector(e) for e in matched)}); narrow them.")
            continue
        entry = matched[0]
        if entry.get("generated"):
            continue
        size = measured_size((ROOT / rel).read_text(encoding="utf-8"))
        rows.append((rel, size, entry["budget"], entry["tier"]))
        if size > entry["budget"]:
            failures.append(f"{rel}: {size:,} b vs budget {entry['budget']:,} b, over by {size - entry['budget']:,} b (tier {entry['tier']}).\n      {entry['rule']}")
        elif entry["budget"] - size < entry["budget"] // BAND_DIVISOR:
            notes.append(f"near budget: {rel} {size:,} b of {entry['budget']:,} b, {entry['budget'] - size:,} b left")
    if report:
        rows.sort(key=lambda r: -(r[1] * 100 / r[2]))
        notes.insert(0, f"{'% used':>6}  {'bytes':>7}  {'budget':>7}  {'left':>7}  tier  document")
        for i, (rel, size, budget, tier) in enumerate(rows, start=1):
            notes.insert(i, f"{int(size * 100 / budget):>5}%  {size:>7,}  {budget:>7,}  {budget - size:>7,}  {tier:>4}  {rel}")
    return failures, notes


# --- orphans -----------------------------------------------------------------


def _is_named(rel: str, entry: dict, corpus: dict[str, str]) -> bool:
    """Named by path or basename in some reader other than itself — or, on a
    `reached_by_folder` row, its folder named with the trailing slash."""
    alternatives = [re.escape(rel), re.escape(Path(rel).name)]
    folder = Path(rel).parent.as_posix()
    if entry.get("reached_by_folder") and folder != ".":
        alternatives.append(re.escape(folder + "/"))
    needle = re.compile(rf"(?<!{_PATH_CHARS})(?:{'|'.join(alternatives)})(?!\w)")
    return any(needle.search(text) for src, text in corpus.items() if src != rel)


def find_orphans(files: list[str], budgets: dict, roots: dict[str, str], read) -> list[str]:
    """Tier-3 files no reader names. `roots` maps each root reader to its text;
    `read(rel)` returns a file's text. A `reader: true` file joins the corpus
    only once the corpus already names it, repeated until nothing joins, so a
    chain of readers counts only if it starts at a root."""
    claimed = {rel: m[0] for rel, m in assign(files, budgets).items() if len(m) == 1}
    corpus = dict(roots)
    waiting = sorted(rel for rel, e in claimed.items() if e.get("reader") and rel not in corpus)
    joined = True
    while joined:
        joined = False
        for rel in list(waiting):
            if _is_named(rel, claimed[rel], corpus):
                corpus[rel] = read(rel)
                waiting.remove(rel)
                joined = True
    failures: list[str] = []
    for rel, entry in sorted(claimed.items()):
        if entry["tier"] == 3 and not _is_named(rel, entry, corpus):
            failures.append(
                f"{rel}: tier-3 document named by nothing a session reads (CLAUDE.md, kb/README.md, a SKILL.md, or a `reader: true` file one of them names). "
                "Point at it, set `reached_by_folder: true` on its row if a reader names its folder, or delete it; Archive/ is not a destination."
            )
    return failures


def check_orphans(files: list[str], budgets: dict) -> list[str]:
    sources = [ROOT / p for p in SOURCE_PATHS]
    for pattern in SOURCE_GLOBS:
        sources += sorted(ROOT.glob(pattern))
    roots = {s.relative_to(ROOT).as_posix(): s.read_text(encoding="utf-8") for s in sources if s.is_file()}
    return find_orphans(files, budgets, roots, lambda rel: (ROOT / rel).read_text(encoding="utf-8"))


# --- kb ----------------------------------------------------------------------

KB_HEADER = """# Knowledge Base

One markdown file per topic. Prose that stays prose — a digest of what a
document says, what a probe of an outside surface found (a published figure,
a vendor's quote, a portal's behavior), or a decision the owner made and why.

**Not** for the record itself — the record lives in its folder (see
`CLAUDE.md`, Where Things Live). A kb entry points at the record; it does not
replace it. No PII in any entry.

Every entry opens with the frontmatter block — `title`, `topic`, `keywords`,
`kind` (probe | decision | reference), `retrieved` (YYYY-MM-DD), `status`
(current | superseded) — and **this index is rendered from that frontmatter by
`python scripts/check_docs.py --write-kb` and is never hand-edited.** A row
typed in here is overwritten; write the frontmatter instead.

`retrieved:` on a **probe** is the date the outside surface was observed and
the date after which the entry should be doubted; on a **decision** the date
the call was made; on a **reference** the date the source document was
digested. A `status: superseded` entry stays listed, with its status visible,
because a stale note that reads as current is worse than an absent one.
"""


def kb_entries() -> list[tuple[Path, dict | None, str | None]]:
    found = []
    for path in sorted((ROOT / "kb").glob("*.md"), key=lambda p: p.name):
        if path.name == "README.md":
            continue
        meta, err = read_frontmatter(path.read_text(encoding="utf-8"))
        found.append((path, meta, err))
    return found


def validate_kb(path: Path, meta: dict | None, err: str | None) -> list[str]:
    tag = f"kb/{path.name}"
    if err:
        return [f"{tag}: {err}"]
    if meta is None:
        return [f"{tag}: no frontmatter block (the file must open with a '---' line)"]
    problems = []
    for field in ("title", "topic"):
        value = meta.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{tag}: '{field}' is missing or empty")
        elif "\n" in value or "|" in value:
            problems.append(f"{tag}: '{field}' must be one line with no '|'")
    kw = meta.get("keywords")
    if not isinstance(kw, list) or not kw or not all(isinstance(k, str) and k.strip() and "|" not in k for k in kw):
        problems.append(f"{tag}: 'keywords' must be a non-empty list of strings")
    if meta.get("kind") not in KB_KINDS:
        problems.append(f"{tag}: 'kind' must be one of {' | '.join(KB_KINDS)}")
    if meta.get("status") not in KB_STATUSES:
        problems.append(f"{tag}: 'status' must be one of {' | '.join(KB_STATUSES)}")
    r = meta.get("retrieved")
    if isinstance(r, dt.datetime) or not (isinstance(r, dt.date) or (isinstance(r, str) and DATE.match(r.strip()))):
        problems.append(f"{tag}: 'retrieved' must be a YYYY-MM-DD date")
    return problems


def render_kb(found) -> str:
    lines = [KB_HEADER.rstrip("\n"), ""]
    for kind, heading in KB_SECTIONS:
        rows = [(p, m) for p, m, _ in found if (m or {}).get("kind") == kind]
        lines += [f"## {heading}", "", "| Entry | Title | Topic | Retrieved | Status |", "|---|---|---|---|---|"]
        for path, meta in rows:
            r = meta["retrieved"]
            r = r.isoformat() if isinstance(r, dt.date) else str(r).strip()
            lines.append(f"| [{path.name}]({path.name}) | {meta['title'].strip()} | {meta['topic'].strip()} | {r} | {meta['status']} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def check_kb(write: bool) -> list[str]:
    found = kb_entries()
    problems = [p for path, meta, err in found for p in validate_kb(path, meta, err)]
    if problems:
        return problems
    rendered = render_kb(found)
    index = ROOT / KB_INDEX
    current = index.read_text(encoding="utf-8").replace("\r\n", "\n") if index.exists() else None
    if current == rendered:
        return []
    if write:
        index.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"wrote {KB_INDEX} ({len(found)} entries)")
        return []
    diff = list(difflib.unified_diff((current or "").splitlines(), rendered.splitlines(), "README.md (on disk)", "README.md (from frontmatter)", lineterm="", n=1))
    return [f"{KB_INDEX} disagrees with the entry frontmatter; run `python scripts/check_docs.py --write-kb`.\n      " + "\n      ".join(diff[:40])]


# --- memory ------------------------------------------------------------------


def memory_dir() -> Path:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
    return Path.home() / ".claude" / "projects" / slug / "memory"


def check_memory() -> list[str]:
    folder = memory_dir()
    if not folder.is_dir():
        return []
    failures: list[str] = []
    index_path = folder / MEMORY_INDEX
    index_text = index_path.read_text(encoding="utf-8").replace("\r\n", "\n") if index_path.is_file() else ""
    index_lines = [ln for ln in index_text.splitlines() if ln.strip()]
    if len(index_lines) > MEMORY_INDEX_MAX_LINES:
        failures.append(f"memory/{MEMORY_INDEX}: {len(index_lines)} lines, over {MEMORY_INDEX_MAX_LINES}. Consolidate entries into a kb/ file and keep one pointer.")
    targets = {Path(m.group(1).strip()).name for m in re.finditer(r"\]\(([^)]+)\)", index_text)}
    for n, line in enumerate(index_lines, start=1):
        if line.startswith("- ") and len(line.encode("utf-8")) > MEMORY_INDEX_LINE_CAP:
            failures.append(f"memory/{MEMORY_INDEX}:{n}: pointer line is {len(line.encode('utf-8'))} b, over {MEMORY_INDEX_LINE_CAP} b. A pointer is a title and a hook.")
    names = set()
    for path in sorted(folder.glob("*.md")):
        if path.name == MEMORY_INDEX:
            continue
        names.add(path.name)
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        size = len(text.encode("utf-8"))
        if size > MEMORY_CAP:
            failures.append(f"memory/{path.name}: {size} b, over the {MEMORY_CAP} b cap. One fact per file; split it.")
        meta, err = read_frontmatter(text)
        if err or meta is None:
            failures.append(f"memory/{path.name}: {err or 'no frontmatter block'}")
        else:
            for field in ("name", "description"):
                if not isinstance(meta.get(field), str) or not meta[field].strip():
                    failures.append(f"memory/{path.name}: '{field}' is missing")
            mtype = (meta.get("metadata") or {}).get("type") if isinstance(meta.get("metadata"), dict) else None
            if mtype not in MEMORY_TYPES:
                failures.append(f"memory/{path.name}: metadata.type must be one of {' | '.join(MEMORY_TYPES)}")
        if path.name not in targets:
            failures.append(f"memory/{path.name}: no pointer line in {MEMORY_INDEX}. Recall opens what the index points at; an unindexed entry is read by nobody.")
    for target in sorted(targets - names):
        failures.append(f"memory/{MEMORY_INDEX}: pointer names {target}, which does not exist.")
    return failures


# --- intake ------------------------------------------------------------------


def _table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def check_intake_text(text: str) -> list[str]:
    """Every Status cell: a status word, a backticked pointer, no digit outside backticks.

    A table is any run of `|` lines; its first line is the header, and only a
    table whose header has a `Status` column is checked. Backticked spans and
    `§` section references are removed before the digit scan, so a dated path
    stays legal and `§4F` points at a section rather than stating a figure.
    """
    failures: list[str] = []
    checked = 0
    header: list[str] | None = None
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = _table_cells(line)
        if header is None:
            header = cells
            continue
        if all(set(c) <= set("-: ") for c in cells) or "Status" not in header:
            continue
        status = cells[header.index("Status")] if len(cells) == len(header) else None
        row = cells[header.index("#")] if "#" in header and len(cells) == len(header) else "?"
        checked += 1
        if status is None:
            failures.append(f"{INTAKE_FILE} row {row}: has {len(cells)} cells, the header has {len(header)}.")
            continue
        bare = _SECTION_REF.sub("", _BACKTICKED.sub("", status))
        problems = []
        if not _INTAKE_STATUS.match(status):
            problems.append(f"does not start with a status word ({', '.join(INTAKE_STATUS_WORDS)})")
        if not _BACKTICKED.search(status):
            problems.append("has no backticked pointer to the kb entry or file")
        figures = [tok.strip("*,;.()") or tok for tok in _DIGIT_TOKEN.findall(bare)]
        if figures:
            problems.append(f"holds a digit outside backticks ({', '.join(figures)}): move the figure to the kb entry the cell points to")
        if problems:
            failures.append(
                f"{INTAKE_FILE} row {row}: Status cell {'; '.join(problems)}.\n"
                f"      A cell is `<status word> — <missing document(s), no figures> — <`pointer`>`; an identifier the cell needs goes in backticks, a `§` reference is allowed."
            )
    if not checked:
        failures.append(f"{INTAKE_FILE}: no table with a `Status` column found, so no cell was checked.")
    return failures


def check_intake() -> list[str]:
    path = ROOT / INTAKE_FILE
    return check_intake_text(path.read_text(encoding="utf-8")) if path.is_file() else []


# --- setup -------------------------------------------------------------------

_SETUP_MARKER = re.compile(r"\{\{(?:FILL|KIT):[^}]*\}\}")


def check_setup(files: list[str]) -> list[str]:
    """No Starter Kit marker survives in any document, exempt folders included."""
    failures: list[str] = []
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), start=1):
            for m in _SETUP_MARKER.finditer(line):
                failures.append(f"{rel}:{n}: setup marker left unfilled: {m.group(0)[:90]}")
    return failures


# --- main --------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], epilog="There is no --fix; trimming a document is a judgment call.")
    parser.add_argument("--report", action="store_true", help="print every budgeted document at its percentage of budget, then run the checks")
    parser.add_argument("--write-kb", action="store_true", help="render kb/README.md from frontmatter, then run the checks")
    args = parser.parse_args(argv)

    try:
        budgets = load_budgets()
        files = tree_documents()
    except ConfigError as exc:
        print(f"FAIL - {BUDGETS_FILE.name} is invalid: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"FAIL - cannot list documents: {exc}. Nothing was checked; this is not a pass.", file=sys.stderr)
        return 2

    kb_problems = check_kb(args.write_kb)
    budget_failures, notes = check_budgets(files, budgets, args.report)
    orphan_failures = check_orphans(files, budgets)
    memory_failures = check_memory()
    intake_failures = check_intake()
    setup_failures = check_setup(files)

    sections = (("BUDGET", budget_failures), ("ORPHANS", orphan_failures), ("KB", kb_problems), ("MEMORY", memory_failures), ("INTAKE", intake_failures), ("SETUP", setup_failures))
    total = sum(len(f) for _, f in sections)
    for line in notes:
        print(line)
    if total:
        print(f"FAIL - {total} problem(s) across {len(assign(files, budgets))} document(s):", file=sys.stderr)
        for label, failures in sections:
            for f in failures:
                print(f"  [{label}] {f}", file=sys.stderr)
        return 1
    print(f"OK - {len(assign(files, budgets))} document(s) classified and within budget; kb index current; memory folder clean; intake cells in form; no setup marker left.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
