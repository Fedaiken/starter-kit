#!/usr/bin/env python
"""The document gate: budgets, reachability, kb frontmatter, memory caps.

    <venv python> scripts/check_docs.py              # run every check; exit 1 on a hit
    <venv python> scripts/check_docs.py --report     # every budgeted file at % used, then the checks
    <venv python> scripts/check_docs.py --write-kb   # render kb/README.md from frontmatter, then the checks

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
`<venv python> scripts/kit_sync.py` at close-session.

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
7. TRIPS. Each `Trips/<trip>/` folder (not `_private`), on the files it has:
   `itinerary.md` rows under a `## Ddd YYYY-MM-DD` day heading carry a Where
   (start) and a How cell (`TBD` passes, listed as "not ready"; `not on file`
   in Where fails) and a Status of `Plan` or `Booked · record: <section>`,
   optionally ` · checked: <when>`; each day has exactly one `Wear:` line;
   every `Booked · record:` section is a `## ` heading in `record.md`;
   `record.md` holds no `Plan` row and no `Plan (not booked)`; a line in
   record, itinerary or decisions quoting 3+ words carries a speaker or
   source tag; each `Trips/Trip_Log.md` Next deadline cell is at most 300
   characters; a `route: <file>.md` How cell names a file in the folder with a
   `## Google Maps` section of maps/dir links, each carrying every place's id
   (`scripts/maps.py link`), none starting at a stop no earlier leg reached;
   a ride row (What starts `Ride`, `Walk back` or `Back to`) carries its ride
   time as `N min`, so the calendar can end it on arrival. Added 2026-10-03 with the three-file trip layout
   (`Outbox/data-structure-plan.html`): a walk sat on the plan for a week
   with no start point, a quote with no speaker on file was put in a
   companion's mouth, and the Trip Log's deadline cell had grown to 1,009
   characters of history.
8. CLAIMS. A sentence quoting a document's budget matches its row. Each
   `budget_claims:` row in `doc_budgets.yaml` names the document the sentence
   is `in`, the row it is `about` (a `path:` or `glob:` as written) and what it
   `says`, with `{budget}` where the figure goes; the gate renders the live
   figure and requires that exact string. The same sentence with another figure
   is STALE and names both; no such sentence is GONE, because a row that
   matches nothing checks nothing. Then a coverage sweep: a byte figure
   (`10,000 b`) within `CLAIM_WINDOW` characters of a budget word, in a
   document no claim row and no `budget_prose_exempt:` row (`path`, `why`)
   covers, fails "declare it or reword it"; an exemption whose document the
   sweep would not flag is dead config and fails. The kit's own rows are in
   this file (`KIT_BUDGET_CLAIMS`, `KIT_PROSE_EXEMPT`), so a project that pulls
   it with its `doc_budgets.yaml` unchanged passes: a kit claim whose sentence
   is absent checks nothing and leaves its document to the sweep, a kit
   exemption is never dead, and a project row for the same document replaces
   either. Ported 2026-10-26 from
   Fantasy_Football, where a CLAUDE.md quoted a ceiling the config no longer
   held for four days. Recognition is a declaration, not a predicate, on FF's
   measurement: a scan for figures EQUAL to a budget cannot see a stale one by
   construction, and budget-word proximity alone was 57% precise (hypotheticals,
   other caps, dated history), so the sweep only asks for a declaration.
9. SOURCES. A `kb/*.md` line (frontmatter included; fenced code and the
   generated index not) that cites a search or summary tool as where a fact
   came from fails unless the same line also cites the page read: an
   `http(s)://` URL that is not itself a search or answer page, with a
   `retrieved: YYYY-MM-DD` date. A search result, an answer engine's reply and
   a fetch tool's output are a model's summary of pages, not a page; recorded
   as a source, they put claims in the record that no page made. The rule the
   URL stands for: search finds the URL, and a browser reads the page (or the
   source's own raw feed is read). The gate cannot prove a page was read, only
   that one is named. A path to a saved copy does not count: saved copies live
   in gitignored scratch, so the path is dead in git and on every other
   machine. Added 2026-10-27: a
   kb entry cited a developer's news post "via search" for a change the post,
   read raw, never mentions. Recognition
   is by citation grammar, not by the tool's name, because a name list flags
   every line that explains the rule, and a rule nobody can write down without
   failing gets exempted. The name (search, web search, WebSearch, WebFetch,
   the fetch tool, Perplexity, an AI overview, and their result, snippet and
   summary forms) counts only after a sourcing word (via, by, from, per,
   according to, through, source:), alone at the head of a parenthesis
   ("(Perplexity, <date>)"), within a short clause of an ISO date, or as the
   subject of a reporting verb ("the search found", "the search's reading").
   So prose about search, such as "a search result is not a page", passes as
   written; a rule that must name the forbidden words quotes the whole phrase
   in backticks, which marks a mention. A phrase only partly in backticks
   (via `WebSearch`) is still a citation.

Every YAML this gate reads (`doc_budgets.yaml`, kb and memory frontmatter)
goes through `strict_load`, which refuses a repeated mapping key. `safe_load`
keeps the last of two and drops the first without a word, so a second
`budget:` in a row, or a second `entries:` list, would win silently. The one
exception is the committed history `historical_floors` reads: a past revision
cannot be fixed, and refusing it would drop its floors.

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
INTAKE_STATUS_WORDS = ("on file", "found", "partly found", "needed", "action needed", "urgent", "parked")
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


# --- strict yaml -------------------------------------------------------------


class DuplicateKeyError(yaml.YAMLError):
    """A mapping repeats a key. `line` and `first` are 1-based lines in the file."""

    def __init__(self, key: object, line: int, first: int):
        self.key, self.line, self.first = key, line, first
        super().__init__(f"line {line}: key {key!r} repeats the one at line {first}; YAML keeps the last and drops the first without a word. Delete the one that is not the truth.")


class _StrictLoader(yaml.SafeLoader):
    line_offset = 0


def _no_duplicate_keys(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: dict = {}
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        line = key_node.start_mark.line + 1 + loader.line_offset
        if key in seen:
            raise DuplicateKeyError(key, line, seen[key])
        seen[key] = line
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def strict_load(text: str, line_offset: int = 0) -> object:
    """`yaml.safe_load`, refusing a repeated mapping key. `line_offset` is the
    number of file lines before `text`, so a frontmatter error names the file's line."""
    loader = _StrictLoader(text)
    loader.line_offset = line_offset
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


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
                loaded = strict_load(block, line_offset=1)
            except DuplicateKeyError as exc:
                return {}, f"frontmatter {exc}"
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
    validated = [_validate_entry(e, i) for i, e in enumerate(entries)]
    first: dict[str, int] = {}
    for i, entry in enumerate(validated):
        key = _selector(entry)
        if key in first:
            raise ConfigError(f"entries[{i}] ({key}) repeats entries[{first[key]}]; one row per selector, or the two budgets disagree with nobody choosing")
        first[key] = i
    claims = [_validate_claim(c, i, validated) for i, c in enumerate(_optional_list(raw, "budget_claims"))]
    prose_exempt: dict[str, str] = {}
    for i, row in enumerate(_optional_list(raw, "budget_prose_exempt")):
        doc, why = _validate_exemption(row, i)
        if doc in prose_exempt:
            raise ConfigError(f"budget_prose_exempt[{i}] ({doc}) is exempted twice")
        prose_exempt[doc] = why
    return {"exempt_dirs": list(exempt), "entries": validated, "budget_claims": claims, "budget_prose_exempt": prose_exempt}


def _optional_list(raw: dict, key: str) -> list:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"`{key}` must be a list")
    return value


def load_budgets() -> dict:
    try:
        raw = strict_load(BUDGETS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"{BUDGETS_FILE.name} does not exist") from exc
    except DuplicateKeyError as exc:
        raise ConfigError(f"{BUDGETS_FILE.name} {exc}") from exc
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
            # safe_load, not strict_load: a committed revision cannot be fixed,
            # and refusing one would drop its floors. Its last key is what the
            # gate read at the time.
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


# --- budget claims -----------------------------------------------------------

# A byte figure as these documents write one: `10,000 b`, `8000 b`, `234 b`.
# Three digits minimum, so a short sha (`88da27b`) is not a figure.
_FIGURE = r"\d{1,3}(?:,\d{3})+|\d{3,}"
_BYTE_FIGURE = re.compile(rf"(?<![\w,.])({_FIGURE})\s?b\b", re.IGNORECASE)
# Used by both halves: the sweep looks for these, and a declared `says:` must
# hold one outside its slot, so no row declares a sentence the sweep never sees.
_BUDGET_WORDS = re.compile(r"budget|capped|cap\b|gated|ceiling", re.IGNORECASE)
CLAIM_WINDOW = 25  # FF measured 12 and 25 flagging the same documents; 40 pulled in measurements
# Rows every kit project carries, kept here rather than in each project's YAML.
# The CLAUDE.md template quotes its own ceiling in this phrasing; the two kb
# entries are kit-owned and their figures are history, not budgets.
KIT_BUDGET_CLAIMS = ({"in": "CLAUDE.md", "about": "CLAUDE.md", "says": "is gated at {budget} b"},)
KIT_PROSE_EXEMPT = {
    "kb/document-budgets.md": "HAZELHURST's ceiling and size on its first day: dated history of another project",
    "kb/git-discipline.md": "a route file's measured overage in an incident, not a budget",
}


def _validate_claim(row: object, index: int, entries: list[dict]) -> dict:
    where = f"budget_claims[{index}]"
    if not isinstance(row, dict):
        raise ConfigError(f"{where} is not a mapping")
    for key in ("in", "about", "says"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ConfigError(f"{where} needs a non-empty `{key}:`")
    if "{budget}" not in row["says"]:
        raise ConfigError(f"{where} ({row['in']}) `says:` has no {{budget}} slot, so it could never disagree with the config")
    # The slot is removed first: `{budget}` holds the word "budget" and would satisfy this on its own.
    if not _BUDGET_WORDS.search(row["says"].replace("{budget}", " ")):
        raise ConfigError(f"{where} ({row['in']}) `says:` has no budget word ({_BUDGET_WORDS.pattern}), so the sweep that keeps this list honest would never find it")
    about = [e for e in entries if _selector(e) == row["about"]]
    if not about:
        raise ConfigError(f"{where} ({row['in']}) `about: {row['about']}` names no entry; write a `path:` or `glob:` exactly as its row does")
    if "budget" not in about[0]:
        raise ConfigError(f"{where} ({row['in']}) `about: {row['about']}` is generated and has no budget to quote")
    return {"in": row["in"], "about": row["about"], "says": row["says"], "budget": about[0]["budget"], "kit": False}


def _kit_claims(budgets: dict) -> list[dict]:
    """The kit's claims this project has not replaced and can resolve to a budget."""
    own = {c["in"] for c in budgets["budget_claims"]}
    out = []
    for claim in KIT_BUDGET_CLAIMS:
        rows = [e for e in budgets["entries"] if _selector(e) == claim["about"] and "budget" in e]
        if claim["in"] not in own and rows:
            out.append({**claim, "budget": rows[0]["budget"], "kit": True})
    return out


def _validate_exemption(row: object, index: int) -> tuple[str, str]:
    where = f"budget_prose_exempt[{index}]"
    if not isinstance(row, dict):
        raise ConfigError(f"{where} is not a mapping")
    if not isinstance(row.get("path"), str) or not row["path"].strip():
        raise ConfigError(f"{where} needs a non-empty `path:`")
    if not isinstance(row.get("why"), str) or not row["why"].strip():
        raise ConfigError(f"{where} ({row['path']}) needs a `why:`; an unexplained exemption reads as an oversight")
    return row["path"], row["why"]


def flagged_figures(text: str) -> list[str]:
    """Every byte figure with a budget word within `CLAIM_WINDOW` characters."""
    return [m.group(1) for m in _BYTE_FIGURE.finditer(text)
            if _BUDGET_WORDS.search(text[max(0, m.start() - CLAIM_WINDOW):m.start()]) or _BUDGET_WORDS.search(text[m.end():m.end() + CLAIM_WINDOW])]


def find_budget_claim_problems(documents: list[str], budgets: dict, read) -> list[str]:
    """`documents` is the swept population; `read(rel)` returns a file's text,
    or None when the file is not there. A declared document is checked whether
    or not the population holds it, so a declaration cannot pass by naming a
    file the sweep skips. A kit claim (`KIT_BUDGET_CLAIMS`) whose document or
    sentence is absent checks nothing and leaves the document to the sweep."""
    failures: list[str] = []
    declared = set(KIT_PROSE_EXEMPT) | set(budgets["budget_prose_exempt"])
    for claim in budgets["budget_claims"] + _kit_claims(budgets):
        doc, budget = claim["in"], claim["budget"]
        text = read(doc)
        if text is None:
            if not claim["kit"]:
                failures.append(f"{doc}: a budget_claims row names it, and this working tree has no such file.")
            continue
        rendered = claim["says"].replace("{budget}", f"{budget:,}")
        skeleton = rf"({_FIGURE})".join(re.escape(part) for part in claim["says"].split("{budget}"))
        hit = None if rendered in text else re.search(skeleton, text, re.IGNORECASE)
        if rendered in text:
            declared.add(doc)
        elif hit:
            declared.add(doc)
            failures.append(f"{doc}: quotes {hit.group(1)} b for {claim['about']}; doc_budgets.yaml says {budget:,} b. Fix the document; budgets only go down.")
        elif not claim["kit"]:
            declared.add(doc)
            failures.append(f"{doc}: no sentence reads {rendered!r}. It was reworded or deleted, so its budget_claims row checks nothing: restore it, update `says:`, or drop the row.")
    for rel in sorted(set(documents) - declared):
        figures = flagged_figures(read(rel) or "")
        if figures:
            failures.append(
                f"{rel}: states {', '.join(f + ' b' for f in figures)} beside a budget word, and no budget_claims row covers it. "
                "Declare the claim in doc_budgets.yaml, reword it, or exempt the document with a `why:` if its figures are not budget claims."
            )
    for rel, why in sorted(budgets["budget_prose_exempt"].items()):
        text = read(rel)
        if text is None:
            failures.append(f"{rel}: exempted in budget_prose_exempt, and this working tree has no such file. Drop the row.")
        elif not flagged_figures(text):
            failures.append(f"{rel}: exempted in budget_prose_exempt, and the sweep would not flag it. An exemption covering nothing is dead config; drop the row.")
    return failures


def check_budget_claims(files: list[str], budgets: dict) -> list[str]:
    def read(rel: str) -> str | None:
        path = ROOT / rel
        return path.read_text(encoding="utf-8") if path.is_file() else None

    return find_budget_claim_problems(sorted(assign(files, budgets)), budgets, read)


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
`<venv python> scripts/check_docs.py --write-kb` and is never hand-edited.** A row
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
    return [f"{KB_INDEX} disagrees with the entry frontmatter; run `<venv python> scripts/check_docs.py --write-kb`.\n      " + "\n      ".join(diff[:40])]


# --- sources -----------------------------------------------------------------

# Longer names first, so `web search results` is read whole rather than as `web`.
_SEARCH_TOOL = (
    r"(?:web[ _-]?search(?:es)?|WebFetch|web_fetch|fetch[ _-]tool|Perplexity|AI (?:overview|summary|answer)s?"
    r"|search(?:es)?(?: (?:results?|snippets?|summar(?:y|ies)|engines?))?)"
)
_SEARCH_MODIFIERS = r"(?:(?:a|an|the|one|my|our|some|this|that|several|quick|online|web|Google|Bing|DuckDuckGo|Perplexity)\s+){0,3}"
_SEARCH_CITATIONS = tuple(re.compile(p, re.IGNORECASE) for p in (
    rf"\b(?:via|by|from|per|according to|through|sources?:|cited:)\s+{_SEARCH_MODIFIERS}{_SEARCH_TOOL}\b",
    rf"\(\s*{_SEARCH_TOOL}\s*[,;)]",
    rf"\b{_SEARCH_TOOL}\b[^.;()\n]{{0,25}}?\b\d{{4}}-\d{{2}}-\d{{2}}",
    rf"\b{_SEARCH_TOOL}(?:\s+(?:says|said|shows|showed|reports|reported|found|returned|states|stated|confirms|confirmed)\b|(?:'s|’s)\s+(?:reading|summary|answer)\b)",
))
_PAGE_URL = re.compile(r"https?://[^\s`)>\]]+", re.IGNORECASE)
_SEARCH_URL = re.compile(r"perplexity\.ai|google\.[a-z.]+/search|bing\.com/search|duckduckgo\.com/\?", re.IGNORECASE)
_RETRIEVED = re.compile(r"\bretrieved:\s*\d{4}-\d{2}-\d{2}\b", re.IGNORECASE)


def _cites_page(line: str) -> bool:
    """A URL that is not a search or answer page, and a `retrieved:` date beside it."""
    return bool(_RETRIEVED.search(line)) and any(not _SEARCH_URL.search(u) for u in _PAGE_URL.findall(line))


def find_search_citations(rel: str, text: str) -> list[str]:
    """Each line citing a search or summary tool as a source with no page on it.
    A match lying wholly inside one backticked span is a mention and passes."""
    failures: list[str] = []
    fenced = False
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or _cites_page(line):
            continue
        quoted = [(m.start(), m.end()) for m in _BACKTICKED.finditer(line)]
        scan = line.replace("`", " ")  # same offsets, so `quoted` still lines up
        hits = [m for p in _SEARCH_CITATIONS for m in p.finditer(scan)
                if not any(s <= m.start() and m.end() <= e for s, e in quoted)]
        if hits:
            phrase = min(hits, key=lambda m: m.start()).group(0).strip()
            failures.append(
                f"{rel}:{n}: cites {phrase!r} as a source, and the line names no page read. A search or summary is not a page: "
                "read the page itself and cite its URL with `retrieved: <date>` on this line. If the line is about search rather than citing it, put the phrase in backticks."
            )
    return failures


def check_sources() -> list[str]:
    return [f for path, _, _ in kb_entries() for f in find_search_citations(f"kb/{path.name}", path.read_text(encoding="utf-8"))]


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


# --- trips -------------------------------------------------------------------

TRIPS_DIR = "Trips"
TRIP_LOG = "Trips/Trip_Log.md"
TRIP_LOG_DEADLINE_CAP = 300
QUOTE_TAGS = ("said by", "reported by", "speaker not on file", "http", "source:")
QUOTED_FILES = ("record.md", "itinerary.md", "decisions.md")
_DAY_HEADING = re.compile(r"^## (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{4}-\d{2}-\d{2}\s*$")
_ITIN_STATUS = re.compile(
    r"^(?:Plan|Booked · record: (?P<section>.+?))"
    r"(?: · checked: (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{4}-\d{2}-\d{2} \d{1,2}:\d{2} [ap]m)?$"
)
_QUOTE_SPAN = re.compile(r'"([^"]*)"|“([^”]*)”')
_TBD = re.compile(r"\bTBD\b")
_RIDE = re.compile(r"(?:Ride|Walk back|Back to)\b")
_MINUTES = re.compile(r"\b\d+ min\b")


def _tables(lines: list[str]):
    """(line number, header cells, row cells) for every body row of every `|` table."""
    header: list[str] | None = None
    for n, line in enumerate(lines, start=1):
        if not line.lstrip().startswith("|"):
            header = None
            continue
        cells = _table_cells(line)
        if header is None:
            header = cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        yield n, header, cells


def check_itinerary_text(rel: str, text: str) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    """(failures, not-ready notes, (line, section) for every Booked row)."""
    failures: list[str] = []
    notes: list[str] = []
    booked: list[tuple[int, str]] = []
    lines = text.replace("\r\n", "\n").split("\n")
    days: list[tuple[int, int, int]] = []  # (heading line, first line, last line), 1-based inclusive
    start = None
    for n, line in enumerate(lines, start=1):
        if re.match(r"#{1,2} ", line):
            if start is not None:
                days.append((start, start + 1, n - 1))
                start = None
            if _DAY_HEADING.match(line):
                start = n
    if start is not None:
        days.append((start, start + 1, len(lines)))
    for head, first, last in days:
        day = lines[head - 1][3:].strip()
        wear = sum(1 for ln in lines[first - 1:last] if ln.lstrip().startswith("Wear:"))
        if wear != 1:
            failures.append(f"{rel}:{head}: {day} has {wear} `Wear:` lines; a day has exactly one (`Wear: not set` passes).")
        bad_header = None
        for offset, header, cells in _tables(lines[first - 1:last]):
            n = first - 1 + offset
            missing = [c for c in ("Where (start)", "How", "Status") if c not in header]
            if missing:
                if header is not bad_header:
                    failures.append(f"{rel}:{n}: {day} table has no {', '.join(missing)} column; the header is `| Time | What | Where (start) | How | Status |`.")
                bad_header = header
                continue
            if len(cells) != len(header):
                failures.append(f"{rel}:{n}: row has {len(cells)} cells, the header has {len(header)}.")
                continue
            where, how, status = (cells[header.index(c)] for c in ("Where (start)", "How", "Status"))
            what = cells[header.index("What")] if "What" in header else "row"
            problems = []
            if not where:
                problems.append("Where (start) is empty")
            elif where.lower() == "not on file":
                problems.append("Where (start) says `not on file`; an item with no start point is `TBD`")
            if not how:
                problems.append("How is empty")
            elif _RIDE.match(what) and not _MINUTES.search(f"{what} {how}") and not _TBD.search(how):
                problems.append("a ride row carries its ride time as `N min` in What or How (`TBD` in How passes, not ready); the calendar ends the ride on arrival from it")
            m = _ITIN_STATUS.match(status)
            if not m:
                problems.append(f"Status `{status}` is neither `Plan` nor `Booked · record: <record.md section>` (a ` · checked: Ddd YYYY-MM-DD h:mm am` may follow)")
            elif m.group("section"):
                booked.append((n, m.group("section").strip()))
            if problems:
                failures.append(f"{rel}:{n}: {what}: {'; '.join(problems)}.")
            elif _TBD.search(where) or _TBD.search(how):
                notes.append(f"not ready: {rel}:{n}: {day} {what} (TBD in {' and '.join(c for c, v in (('Where', where), ('How', how)) if _TBD.search(v))})")
    return failures, notes, booked


def check_record_text(rel: str, text: str) -> list[str]:
    """A record holds booked facts only: no `Plan` Status row, no `Plan (not booked)`."""
    failures: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    for n, line in enumerate(lines, start=1):
        if "Plan (not booked)" in line:
            failures.append(f"{rel}:{n}: `Plan (not booked)` in the record; a plan line goes to itinerary.md.")
    for n, header, cells in _tables(lines):
        if "Status" in header and len(cells) == len(header):
            status = cells[header.index("Status")]
            if re.match(r"^\*{0,2}Plan\b(?! \(not booked\))", status):
                failures.append(f"{rel}:{n}: row with Status `{status}` in the record; a plan line goes to itinerary.md.")
    return failures


def record_sections(text: str) -> set[str]:
    return {ln[3:].strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.startswith("## ")}


def check_booked_sections(itin_rel: str, booked: list[tuple[int, str]], record_rel: str, record_text: str | None) -> list[str]:
    """Each `Booked · record: <section>` names a `## <section>` heading in the trip's record.md."""
    sections = record_sections(record_text) if record_text is not None else set()
    out = []
    for n, section in booked:
        if record_text is None:
            out.append(f"{itin_rel}:{n}: `Booked · record: {section}`, but {record_rel} does not exist.")
        elif section not in sections:
            out.append(f"{itin_rel}:{n}: `Booked · record: {section}` names no `## {section}` heading in {record_rel}.")
    return out


def check_quotes_text(rel: str, text: str) -> list[str]:
    """A line quoting 3+ words carries a speaker or a source (`QUOTE_TAGS`). Fenced code is skipped."""
    failures: list[str] = []
    fenced = False
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        spans = [a or b for a, b in _QUOTE_SPAN.findall(line)]
        long = [s for s in spans if len(s.split()) >= 3]
        if long and not any(tag in line.lower() for tag in QUOTE_TAGS):
            failures.append(f"{rel}:{n}: quotes \"{long[0][:60]}\" with no speaker or source; add (said by <name>, <date>), (reported by …), (speaker not on file), source: or the URL.")
    return failures


def check_trip_log_text(text: str) -> list[str]:
    """Each Next deadline cell is one deadline: at most `TRIP_LOG_DEADLINE_CAP` characters."""
    failures: list[str] = []
    checked = 0
    for n, header, cells in _tables(text.replace("\r\n", "\n").split("\n")):
        if "Next deadline" not in header:
            continue
        checked += 1
        if len(cells) != len(header):
            failures.append(f"{TRIP_LOG}:{n}: row has {len(cells)} cells, the header has {len(header)}.")
            continue
        cell = cells[header.index("Next deadline")]
        if len(cell) > TRIP_LOG_DEADLINE_CAP:
            trip = cells[header.index("Trip")] if "Trip" in header else f"line {n}"
            failures.append(f"{TRIP_LOG}:{n}: {trip}: Next deadline cell is {len(cell):,} characters, over {TRIP_LOG_DEADLINE_CAP}. One deadline here; the history goes to the trip's decisions.md.")
    if not checked:
        failures.append(f"{TRIP_LOG}: no table with a `Next deadline` column found, so no cell was checked.")
    return failures


_ROUTE_CELL = re.compile(r"route:\s*`?([\w.-]+\.md)`?")
_MAPS_DIR = re.compile(r"https://www\.google\.com/maps/dir/\?\S+")
_STOP_ADDR = re.compile(r"([\d\s·,]*\d)\s+([A-Za-z]+)")


def _place_key(text: str, anywhere: bool = False) -> set[tuple[str, str]]:
    """(house number, street word) pairs in an address: `3017 · 3029 Magazine St` gives two.
    `anywhere` finds the address after a business name (`Empire Antiques, 3617 Magazine St`)."""
    m = (_STOP_ADDR.search if anywhere else _STOP_ADDR.match)(text.strip())
    return {(n, m.group(2).lower()) for n in re.findall(r"\d+", m.group(1))} if m else set()


def check_route_text(rel: str, text: str) -> list[str]:
    """A walk's route file holds its Google Maps links, and no leg starts at a stop it never reached.

    Sat 2026-10-03: the Magazine St link went only into the calendar and began at
    stop 1, the book shop, so Maps walked past it."""
    from urllib.parse import parse_qs, urlparse
    links = _MAPS_DIR.findall(text)
    if "## Google Maps" not in text or not links:
        return [f"{rel}: a walk's route file has a `## Google Maps` section with its google.com/maps/dir links; the calendar copies them from here."]
    stops: set[tuple[str, str]] = set()
    for _, header, cells in _tables(text.replace("\r\n", "\n").split("\n")):
        if "Address" in header and len(cells) == len(header):
            stops |= _place_key(cells[header.index("Address")])
    failures, reached = [], set()
    for link in links:
        q = parse_qs(urlparse(link).query)
        stops_in = q.get("waypoints", [""])[0].split("|") if q.get("waypoints") else []
        ids_in = q.get("waypoint_place_ids", [""])[0].split("|") if q.get("waypoint_place_ids") else []
        if not (q.get("origin_place_id") and q.get("destination_place_id")) or len(ids_in) != len(stops_in):
            failures.append(f"{rel}: a Maps leg without every place's id pins street addresses, not the businesses; build it with `scripts/maps.py link` ({link[:90]}…).")
        start = _place_key(q.get("origin", [""])[0], anywhere=True)
        if start & stops and not start & reached:
            failures.append(f"{rel}: a Maps leg starts at a stop no earlier leg reached ({q['origin'][0]}); Maps never stops at an origin. Start where the travelers are and make the stop a waypoint.")
        for p in stops_in + q.get("destination", [""]):
            reached |= _place_key(p, anywhere=True)
    return failures


def check_trip_folder(folder: Path, rel_folder: str) -> tuple[list[str], list[str]]:
    """(failures, notes) for one trip folder; each check runs only on the files it has."""
    def read(name: str) -> str | None:
        p = folder / name
        return p.read_text(encoding="utf-8") if p.is_file() else None

    failures: list[str] = []
    notes: list[str] = []
    record = read("record.md")
    itinerary = read("itinerary.md")
    if itinerary is not None:
        f, notes, booked = check_itinerary_text(f"{rel_folder}/itinerary.md", itinerary)
        failures += f + check_booked_sections(f"{rel_folder}/itinerary.md", booked, f"{rel_folder}/record.md", record)
        for name in sorted(set(_ROUTE_CELL.findall(itinerary))):
            text = read(name)
            failures += check_route_text(f"{rel_folder}/{name}", text) if text is not None else [f"{rel_folder}/itinerary.md: a How cell names `route: {name}`, which is not in the folder."]
    if record is not None:
        failures += check_record_text(f"{rel_folder}/record.md", record)
    for name in QUOTED_FILES:
        text = read(name)
        if text is not None:
            failures += check_quotes_text(f"{rel_folder}/{name}", text)
    return failures, notes


def check_trips(root: Path = ROOT) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    trips = root / TRIPS_DIR
    if trips.is_dir():
        for folder in sorted(p for p in trips.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            f, n = check_trip_folder(folder, f"{TRIPS_DIR}/{folder.name}")
            failures += f
            notes += n
    log = root / TRIP_LOG
    if log.is_file():
        failures += check_trip_log_text(log.read_text(encoding="utf-8"))
    return failures, notes


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
    trip_failures, trip_notes = check_trips()
    notes += trip_notes
    claim_failures = check_budget_claims(files, budgets)
    source_failures = check_sources()

    sections = (("BUDGET", budget_failures), ("ORPHANS", orphan_failures), ("KB", kb_problems), ("MEMORY", memory_failures), ("INTAKE", intake_failures), ("SETUP", setup_failures), ("TRIPS", trip_failures), ("CLAIMS", claim_failures), ("SOURCES", source_failures))
    total = sum(len(f) for _, f in sections)
    for line in notes:
        print(line)
    if total:
        print(f"FAIL - {total} problem(s) across {len(assign(files, budgets))} document(s):", file=sys.stderr)
        for label, failures in sections:
            for f in failures:
                print(f"  [{label}] {f}", file=sys.stderr)
        return 1
    print(f"OK - {len(assign(files, budgets))} document(s) classified and within budget; kb index current; memory folder clean; intake cells in form; no setup marker left; trip files in form; budget claims current; no search cited as a source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
