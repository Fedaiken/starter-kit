#!/usr/bin/env python3
"""A lane's predicted peak context, from the bytes its task sheet tells it to read.

Usage (from the workspace root; `<venv python>` is `.venv/Scripts/python.exe`
on Windows and `.venv/bin/python` elsewhere -- `project_identity.venv_python`):
    <venv python> scripts/lane_budget.py coordination/desks/data-model/task_sheets/plan-write.md
    <venv python> scripts/lane_budget.py --calibrate coordination/desks/data-design coordination/desks/data-model

WHY THIS EXISTS
---------------
A lane that compacts has failed its job: it loses what it read, and its report
is no longer a read in full. What a window holds is mostly what it read (Read
results were 78-90% of every heavy lane's content in FACOWORK's Session 55), so
a lane's peak is predicted by the bytes its sheet's `reads:` names, and
`desk_record.sheet_problems` refuses at the stamp a sheet predicted past
BUDGET_TOKENS -- an over-sized unit is split before it opens, never after it
dies. Ported 2026-11-02 from FACOWORK's `scripts/lane_budget.py` (the owner: "just
resolve this for moving forward"); its generic core only. Left behind: every
fit and rule for FACOWORK's campaign trackers (draft checks, final checks,
judging runs, re-cuts, references sweeps, tracker Baselines), which name sheet
kinds this project does not have.

WHAT IS COUNTED
---------------
Every `reads:` path: a file's bytes, a folder's files summed recursively. A
file is counted once, however many paths reach it. A path the sheet names that
is not on disk counts nothing (the stamp refuses such a sheet anyway).

CALIBRATION
-----------
`--calibrate <home> ...` measures the predictor on this project's own lanes.
For every CLOSED lane of each desk home -- its sheets under `<home>/task_sheets/`
and every `<home>/closed/<stamp>/task_sheets/` -- it prints the predicted peak,
the peak `context_meter` measures in that lane's own window, and the residual,
then per reason the least-squares line and the refit the FACOWORK convention
gives (REFIT, below). It changes no coefficient: a refit is a code change made
on that evidence, with the evidence written beside the coefficient. A lane
whose measured peak passed its prediction by more than DRIFT_TOKENS is printed
`DRIFT <lane>`, and the run exits 1 until the lane is cited, as
`calibrate <lane>`, in `kb/lane-context-sizing.md` -- where every calibration
is recorded.

A lane is measured in ITS OWN window, never the latest window of its name
(names recur across desks): a window is the lane's when its `/lane` command
names the path the lane's sheet was stamped at. A closed home's sheets have
moved under `closed/<stamp>/`, so the stamped path is read from the archived
`desk_record.json` beside them, or rebuilt from the move's shape. A read the
save moved (the desk log, a done file) is sized at its copy under the stamp
folder. Lanes still open are listed and not measured: their peak is not final.

Exit codes:
    0 = every sheet under the budget / calibration with every drift cited
    1 = a sheet over the budget / an uncited DRIFT lane
    2 = arguments wrong, or a sheet or desk home not found
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# The Windows console is cp1252 and cannot encode the em dash a METER
# UNREADABLE line carries.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent

#: Where the coefficients come from (`kb/lane-context-sizing.md` holds each
#: calibration's table). A reason in UNTIL_CALIBRATED is still on FACOWORK's
#: fit: no lane of it has closed in this project yet, and `--calibrate` refits it once
#: MIN_REFIT_LANES have.
PROVENANCE = ("the Starter Kit's defaults, UNTIL CALIBRATED in this project: "
              "the whole-read fit measured on Savecraft's 7 closed lanes "
              "(2026-11-02); design-latitude and prescribed on FACOWORK's "
              "217 lanes of 18 plain-desk homes (prep-refit, 2026-10-15)")
UNTIL_CALIBRATED = frozenset({"design-latitude", "prescribed"})

#: (intercept tokens, tokens per byte read), by the sheet's reason.
#:
#: `design-latitude`: FACOWORK's least squares over 142 design lanes was
#: 208,909 + 0.3426 a byte; held so that no lane of the evidence ran past its
#: prediction by more than DRIFT_TOKENS, the intercept rounded up to 250,000 and
#: the rate to 0.36. A design lane's peak barely follows the bytes its sheet
#: names, because its load is its work: the code it writes and tests, and the
#: files it is routed to, which no `reads:` list names before it opens.
#: `prescribed`: least squares over 75 lanes was 111,663 + 0.5167; 125,000 + 0.52.
COEFFICIENTS: dict[str, tuple[int, float]] = {
    "design-latitude": (250_000, 0.36),
    "prescribed": (125_000, 0.52),
}

#: Every reason without a fit of its own: the whole-read fit. The kit ships
#: Savecraft's line, which replaced FACOWORK's Session 55 line (125,000 + 0.52
#: a byte) when `--calibrate` (2026-11-02) measured Savecraft's first 7 closed
#: lanes on it -- bytes read,
#: predicted at 0.52, measured peak:
#:
#:     caravan-type   modding     15,178   132,893    62,007   -70,886
#:     data-shape     research   120,227   187,518   255,030   +67,512
#:     query-census   research   198,123   228,024   233,255    +5,231
#:     plan-check     checking   146,145   200,995   215,007   +14,012
#:     plan-review    checking   189,477   223,528   270,316   +46,788
#:     plan-write     drafting   169,738   213,264   290,077   +76,813
#:     work-shape     research   129,959   192,579   258,928   +66,349
#:
#: Six of seven under-predicted: these lanes load about a token per byte they
#: name, twice FACOWORK's rate, because they read beyond their `reads:` (the
#: game's files, the save, code they are routed to). Least squares is
#: 80,570 + 1.0535 a byte; by REFIT, 100,000 + 1.06. On it three lanes still run
#: past their prediction, none by more than 30,000 (data-shape +27,589,
#: work-shape +21,171, plan-write +10,155), and query-census is over-priced the
#: most (-76,755). It refuses past 471,698 bytes read -- the
#: same line the HAZELHURST measurements in the kb entry drew ("split above
#: about 500 KB"). The evidence spans 15-198 KB, so a sheet past it is priced by
#: extrapolation: the next `--calibrate` with larger lanes moves it.
DEFAULT_COEFFICIENTS: tuple[int, float] = (100_000, 1.06)

#: 60% of the window (`context_meter.WINDOW_TOKENS`, 1,000,000, measured). The
#: largest under-prediction FACOWORK measured on a fit was about +200k, and a
#: lane still writes its report after reading: 600k + 200k leaves ~200k before
#: the ceiling.
BUDGET_TOKENS = 600_000

#: A measured peak this far past its prediction is a DRIFT: the margin
#: BUDGET_TOKENS leaves.
DRIFT_TOKENS = 200_000

#: REFIT, the convention every FACOWORK fit was made by (2026-10-15): the
#: intercept is the least-squares one rounded UP to the next INTERCEPT_STEP; the
#: rate is the larger of the least-squares rate and the least rate at that
#: intercept that leaves no lane past its prediction by more than DRIFT_TOKENS,
#: rounded UP to RATE_STEP. Over-prediction only costs a split; under-prediction
#: costs a lane.
INTERCEPT_STEP = 25_000
RATE_STEP = 0.01
#: Fewer lanes than this place no line: one point has no slope, and two do not
#: make a fit worth trusting over FACOWORK's 217.
MIN_REFIT_LANES = 5

UNREADABLE = "METER UNREADABLE — "

REMEDY = ("split the unit: one sheet per large document or folder, so each lane's "
          "`reads:` stays under the budget; name FILES rather than whole folders "
          "when the lane needs only some of them")

#: Where each calibration is recorded, and a DRIFT lane cited.
SIZING_ENTRY = "kb/lane-context-sizing.md"


@dataclass
class Prediction:
    reason: str
    lane: str
    tokens: int
    total_bytes: int
    breakdown: list[tuple[str, int]]
    intercept: int
    rate: float
    missing: list[str] = field(default_factory=list)

    @property
    def over(self) -> bool:
        return self.tokens > BUDGET_TOKENS


def coefficients(reason: str) -> tuple[int, float]:
    """(intercept, tokens per byte read) a lane of `reason` is priced on."""
    return COEFFICIENTS.get(reason, DEFAULT_COEFFICIENTS)


def tokens_for(reason: str, total_bytes: int) -> int:
    intercept, rate = coefficients(reason)
    return int(round(intercept + rate * total_bytes))


_SHEET_TITLE = re.compile(r"^#\s*Task sheet:\s*(\S+)", re.M)


def sheet_lane(text: str) -> str | None:
    """The lane a sheet is for, from its `# Task sheet: <lane>` title."""
    found = _SHEET_TITLE.search(text)
    return found.group(1) if found else None


def _desk_record():
    import desk_record  # noqa: PLC0415 -- desk_record imports this module lazily too
    return desk_record


def _files_under(repo: Path, rel: str) -> list[tuple[str, int]]:
    """(repo-relative path, bytes) of every file `rel` names: itself, or every
    file under it."""
    path = repo / rel
    if path.is_file():
        return [(rel, path.stat().st_size)]
    if not path.is_dir():
        return []
    return [(child.relative_to(repo).as_posix(), child.stat().st_size)
            for child in sorted(path.rglob("*")) if child.is_file()]


def sheet_reads(text: str) -> tuple[str, list[str]]:
    """(the sheet's reason, its `reads:` paths cleaned), a marker or a path
    outside the project left out -- the stamp refuses those for itself."""
    dr = _desk_record()
    fields, _ = dr.parse_sheet(text)
    reason = (fields.get("reason") or "").split()
    reads = []
    for raw in dr.list_items(fields.get("reads", "") or ""):
        if dr.marker_problem(raw):
            continue
        try:
            reads.append(dr.clean_path(raw))
        except dr.DeskError:
            continue
    return (reason[0] if reason else ""), reads


def estimate(text: str, repo: Path | None = None, lane: str | None = None, *,
             moved_to: tuple[str, str] | None = None) -> Prediction:
    """The prediction for a sheet's text; paths resolve against `repo`.
    `moved_to` is calibration's alone: (a closed home, its stamp folder), so a
    read the home's save moved is sized at its copy there. Without it -- the
    stamp -- the disk is the one the lane is about to open on."""
    repo = REPO if repo is None else Path(repo)
    reason, reads = sheet_reads(text)
    lane = lane or sheet_lane(text) or ""
    seen: set[str] = set()
    entries: dict[str, int] = {}
    missing: list[str] = []
    for rel in reads:
        found = _files_under(repo, rel)
        if not found and moved_to:
            home, closed = moved_to
            if rel.casefold().startswith(home.casefold() + "/"):
                found = _files_under(repo, closed + rel[len(home):])
        if not found:
            missing.append(rel)
            continue
        total = 0
        for path, size in found:
            if path.casefold() in seen:
                continue
            seen.add(path.casefold())
            total += size
        if total:
            entries[rel] = entries.get(rel, 0) + total
    total_bytes = sum(entries.values())
    intercept, rate = coefficients(reason)
    return Prediction(reason=reason, lane=lane, tokens=tokens_for(reason, total_bytes),
                      total_bytes=total_bytes,
                      breakdown=sorted(entries.items(), key=lambda kv: (-kv[1], kv[0])),
                      intercept=intercept, rate=rate, missing=missing)


def breakdown_lines(got: Prediction, indent: str = "      ") -> list[str]:
    return [f"{indent}{size:>12,} bytes  {path}" for path, size in got.breakdown]


def budget_problem(text: str, repo: Path | None = None) -> str | None:
    """Why the stamp refuses this sheet for its size, or None when it fits."""
    got = estimate(text, repo)
    if not got.over:
        return None
    return "\n".join([
        f"the lane is predicted to peak at {got.tokens:,} tokens, past the budget "
        f"of {BUDGET_TOKENS:,} (60% of the window): {got.intercept:,} + {got.rate} x "
        f"{got.total_bytes:,} bytes read, for reason `{got.reason}` ({PROVENANCE}). "
        f"What it reads, largest first:",
        *breakdown_lines(got),
        f"    Remedy: {REMEDY}",
    ])


# --- calibration ----------------------------------------------------------------


#: A sheet in a closed desk home: `<home>/closed/<stamp>/task_sheets/<lane>.md`.
_CLOSED_SHEET = re.compile(
    r"^(?P<home>.+?)/closed/(?P<stamp>[^/]+)/(?P<rest>task_sheets/[^/]+)$", re.IGNORECASE)

#: The sheet path a `/lane <name> <sheet>` role command names: as the opener's
#: slash command records it, or typed plain.
_LANE_SHEET = re.compile(
    r"<command-name>/lane</command-name>.*?<command-args>\s*[^\s<]+[ \t]+([^<\r\n]+?)\s*"
    r"</command-args>", re.S)
_LANE_SHEET_TYPED = re.compile(r"\s*/lane[ \t]+\S+[ \t]+([^\r\n]+?)[ \t]*(?:\r?\n|$)")


def _repo_rel(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> dict:
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


@dataclass
class Lane:
    """One lane of a desk home, as calibration reads it."""
    name: str
    sheet: Path
    stamped: str            # the path its sheet was stamped (and opened) at
    reason: str
    closed: bool
    moved_to: tuple[str, str] | None


def home_lanes(home: Path, repo: Path) -> list[Lane]:
    """Every lane with a sheet in `home`: the live record's sheets under
    `task_sheets/`, then each closed stamp folder's. A lane's state and the
    path it was stamped at come from the record beside its sheets."""
    found: list[Lane] = []
    folders = [(home / "task_sheets", home / "desk_record.json", None)]
    for stamp in sorted((home / "closed").glob("*")):
        if stamp.is_dir():
            folders.append((stamp / "task_sheets", stamp / "desk_record.json",
                            (_repo_rel(repo, home), _repo_rel(repo, stamp))))
    for sheets, record_path, moved_to in folders:
        lanes = _read_json(record_path).get("lanes") or {}
        for sheet in sorted(sheets.glob("*.md")):
            row = lanes.get(sheet.stem) if isinstance(lanes, dict) else None
            row = row if isinstance(row, dict) else {}
            stamped = row.get("sheet")
            if not isinstance(stamped, str) or not stamped.strip():
                rel = _repo_rel(repo, sheet)
                shape = _CLOSED_SHEET.match(rel)
                stamped = f"{shape['home']}/{shape['rest']}" if shape else rel
            text = sheet.read_text(encoding="utf-8")
            reason, _ = sheet_reads(text)
            found.append(Lane(name=sheet.stem, sheet=sheet,
                              stamped=stamped.replace("\\", "/"), reason=reason,
                              closed=moved_to is not None or bool(row.get("closed")),
                              moved_to=moved_to))
    return found


def window_sheets(folder: Path | None = None) -> dict[str, list[Path]]:
    """Every lane window's transcript, keyed by the sheet path its `/lane`
    command names (repo-relative, casefolded). Read-only."""
    import context_meter  # noqa: PLC0415 -- only calibration reads windows

    folder = context_meter.PROJECT_DIR if folder is None else Path(folder)
    found: dict[str, list[Path]] = {}
    try:
        paths = sorted(folder.glob("*.jsonl"))
    except OSError:
        return found
    for path in paths:
        try:
            entry = context_meter.first_user_entry(path)
        except OSError:
            continue
        if entry is None or not context_meter.lane_name(entry):
            continue
        text = context_meter.message_text(entry)
        got = _LANE_SHEET.search(text) or _LANE_SHEET_TYPED.match(text)
        if not got:
            continue
        key = got.group(1).strip().strip("\"'").replace("\\", "/").casefold()
        found.setdefault(key, []).append(path)
    return found


@dataclass
class Point:
    lane: str
    reason: str
    bytes_read: int
    predicted: int
    measured: int

    @property
    def residual(self) -> int:
        return self.measured - self.predicted


def least_squares(points: list[Point]) -> tuple[float, float] | None:
    """(intercept, rate) of the least-squares line through (bytes, measured);
    None for fewer than two points or no spread in bytes."""
    if len(points) < 2:
        return None
    xs = [p.bytes_read for p in points]
    ys = [p.measured for p in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    rate = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - rate * mx, rate


def refit(points: list[Point]) -> tuple[int, float] | None:
    """The REFIT convention's (intercept, rate) for `points`, or None when
    there are too few to place a line (MIN_REFIT_LANES)."""
    if len(points) < MIN_REFIT_LANES:
        return None
    line = least_squares(points)
    if line is None:
        return None
    ls_intercept, ls_rate = line
    intercept = int(math.ceil(max(ls_intercept, 0) / INTERCEPT_STEP) * INTERCEPT_STEP)
    holding = max([0.0] + [(p.measured - DRIFT_TOKENS - intercept) / p.bytes_read
                           for p in points if p.bytes_read > 0])
    rate = max(ls_rate, holding, 0.0)
    rate = math.ceil(round(rate / RATE_STEP, 6)) * RATE_STEP
    return intercept, round(rate, 2)


def is_cited(text: str, lane: str) -> bool:
    return re.search(rf"calibrate {re.escape(lane)}(?![\w-])", text) is not None


def calibrate_lines(homes: list[Path], repo: Path | None = None,
                    folder: Path | None = None
                    ) -> tuple[list[str], list[str], list[str]]:
    """(printed lines, DRIFT lanes, DRIFT lanes not cited)."""
    import context_meter  # noqa: PLC0415

    repo = REPO if repo is None else Path(repo)
    windows = window_sheets(folder)
    cited = ""
    try:
        cited = (repo / SIZING_ENTRY).read_text(encoding="utf-8")
    except OSError:
        pass
    lines = [f"{'lane':<24} {'reason':<16} {'bytes':>9} {'predicted':>10} "
             f"{'measured':>10} {'residual':>10}"]
    points: list[Point] = []
    still_open: list[str] = []
    for home in homes:
        for lane in home_lanes(home, repo):
            if not lane.closed:
                still_open.append(lane.name)
                continue
            text = lane.sheet.read_text(encoding="utf-8")
            got = estimate(text, repo, lane.name, moved_to=lane.moved_to)
            paths = windows.get(lane.stamped.casefold(), [])
            peaks = [p for p in (context_meter.peak_tokens(path) for path in paths)
                     if p is not None]
            if not peaks:
                lines.append(f"{UNREADABLE}{lane.name} (predicted {got.tokens:,}; "
                             f"no window names {lane.stamped})")
                continue
            point = Point(lane.name, lane.reason, got.total_bytes, got.tokens, max(peaks))
            points.append(point)
            lines.append(f"{lane.name:<24} {lane.reason:<16} {point.bytes_read:>9,} "
                         f"{point.predicted:>10,} {point.measured:>10,} "
                         f"{point.residual:>+10,}"
                         + (f"  ({len(paths)} windows, the largest)" if len(paths) > 1 else ""))
    if still_open:
        lines.append(f"still open, not measured (their peak is not final): "
                     f"{', '.join(still_open)}")
    for reason in sorted({p.reason for p in points}):
        mine = [p for p in points if p.reason == reason]
        intercept, rate = coefficients(reason)
        line = least_squares(mine)
        fit = refit(mine)
        said = (f"least squares {line[0]:,.0f} + {line[1]:.4f} a byte" if line
                else "least squares: no line (too few lanes or no spread in bytes)")
        lines.append(f"reason {reason}: {len(mine)} lane(s); priced on {intercept:,} + "
                     f"{rate}; {said}; "
                     + (f"REFIT {fit[0]:,} + {fit[1]}" if fit else
                        f"no refit: fewer than {MIN_REFIT_LANES} lanes"))
    # Every reason without a fit of its own is priced on the one whole-read
    # fit, so their lanes are one body of evidence for it.
    pooled = [p for p in points if p.reason not in COEFFICIENTS]
    if pooled:
        line = least_squares(pooled)
        fit = refit(pooled)
        lines.append(
            f"whole-read fit ({DEFAULT_COEFFICIENTS[0]:,} + {DEFAULT_COEFFICIENTS[1]}, "
            f"every reason without its own): {len(pooled)} lane(s); "
            + (f"least squares {line[0]:,.0f} + {line[1]:.4f} a byte; " if line else "")
            + (f"REFIT {fit[0]:,} + {fit[1]}" if fit
               else f"no refit: fewer than {MIN_REFIT_LANES} lanes"))
    drift = [p.lane for p in points if p.residual > DRIFT_TOKENS]
    uncited = [lane for lane in drift if not is_cited(cited, lane)]
    for lane in drift:
        state = "not cited" if lane in uncited else "cited"
        lines.append(f"DRIFT {lane} -- measured past its prediction by more than "
                     f"{DRIFT_TOKENS:,}; {state} in {SIZING_ENTRY} as `calibrate {lane}`")
    return lines, drift, uncited


def calibrate(home_args: list[str]) -> int:
    homes = []
    for raw in home_args:
        home = Path(raw) if Path(raw).is_absolute() else REPO / raw
        if not home.is_dir():
            print(f"FAIL - no desk home at {raw}", file=sys.stderr)
            return 2
        homes.append(home)
    lines, drift, uncited = calibrate_lines(homes)
    print(f"calibration of {', '.join(home_args)} on "
          f"{datetime.now().astimezone().isoformat(timespec='seconds')}; coefficients "
          f"from {PROVENANCE}; budget {BUDGET_TOKENS:,}, drift past {DRIFT_TOKENS:,}")
    print("each closed lane priced on today's disk (a read its desk's save moved, at "
          "its copy under closed/<stamp>/) and measured at the peak of the window "
          "whose /lane command names the sheet it was stamped at")
    for line in lines:
        print(line)
    if uncited:
        print(f"FAIL - {len(uncited)} DRIFT lane(s) not cited in {SIZING_ENTRY}: "
              f"record each as `calibrate <lane>` with what it read beyond its sheet")
        return 1
    print(f"PASS - {len(drift)} DRIFT lane(s), every one cited" if drift
          else "PASS - no DRIFT lane")
    return 0


# --- the command line ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sheets", nargs="*", help="task sheets to predict")
    parser.add_argument("--calibrate", nargs="+", metavar="HOME",
                        help="predicted against measured peak for every closed lane "
                             "of these desk homes, and the refit per reason")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if bool(args.calibrate) == bool(args.sheets):
        parser.error("give task sheets, or --calibrate <home> ..., not both")
    if args.calibrate:
        return calibrate(args.calibrate)
    over = 0
    for raw in args.sheets:
        path = Path(raw) if Path(raw).is_absolute() else REPO / raw
        try:
            got = estimate(path.read_text(encoding="utf-8"), lane=path.stem)
        except OSError as exc:
            print(f"FAIL - cannot read {raw}: {exc}", file=sys.stderr)
            return 2
        verdict = "OVER BUDGET" if got.over else "fits"
        over += got.over
        print(f"{raw}: {got.tokens:,} tokens predicted ({got.reason}: {got.intercept:,} "
              f"+ {got.rate} x {got.total_bytes:,} bytes) -- {verdict} "
              f"(budget {BUDGET_TOKENS:,}; "
              f"{'UNTIL CALIBRATED: FACOWORK' if got.reason in UNTIL_CALIBRATED else 'the kit default until --calibrate runs here'})")
        for line in breakdown_lines(got, "    "):
            print(line)
        for rel in got.missing:
            print(f"    not on disk, counted 0: {rel}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
