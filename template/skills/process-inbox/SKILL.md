---
name: process-inbox
description: |
  **Inbox Triage Tool**: Processes ONE file from `Inbox/` per run — extracts it, classifies it by kind and staleness, proposes a destination, halts for the owner's verdict, then routes it and records the decision. Routes to the record folders, the markdown KB, a private folder, an archive, or a hold.
  - MANDATORY TRIGGERS: "process the inbox", "process inbox", "/process-inbox"
  - Also trigger when the owner names a specific Inbox file to process.
purpose: Process one file out of the Inbox — sort it, propose where it goes, and wait for your decision before filing it.
---

# Process Inbox — Triage Tool

You are triaging what {{KIT:OWNER}} has dropped into `Inbox/`. **One file per run**, and **the run is not over until that file has left the drop zone.** The point is deliberate, per-file decisions — not a bulk conversion.

## Three folders, and only one of them is the queue

| Folder | What it is | What it costs |
|---|---|---|
| `Inbox/` proper | A document the project has to account for | A row, a verdict, a staleness, a destination, a surviving original |
| **`Inbox/_Scratch/`** | Show-and-tell — a screenshot pasted in to make a point in one conversation | **Nothing.** No row, no verdict, no triage. Delete at will. |
| `Inbox/_Held/` | Judged and parked — an exit from the queue, not a place in it | A HOLD row. Never ages out. |

**`_Scratch/` is never triaged and never ledgered.** Do not propose one, do not write it a row, do not ask about one.

## Why this is triage and not conversion

A drop zone holds different kinds of thing, and a single "convert to markdown" pass damages most of them. A signed document is the truth and must survive byte-identical; its digest is a convenience. A statement is tabular and becomes rows, not prose. Correspondence is appended to a dated log, never summarized away. An identity document is PII and goes to `_private/` unconverted. A letter with a deadline is both a record and a date.

So every file gets two judgments — **what kind of thing it is**, and **whether it is still true** — and a destination follows from those.

## The verdicts

| Verdict | Destination | For |
|---|---|---|
{{FILL: One row per record folder in CLAUDE.md's Where Things Live — an UPPERCASE verdict, the folder, and what belongs there. Mark the verdicts whose original IS the record (signed or governing documents) and any whose deadlines must land on a calendar.}}
| `KB` | `kb/<topic>.md` | Prose that stays prose: a decision, a probe finding, a digest that spans folders. Indexed in `kb/README.md`. |
| `PRIVATE` | the matching `_private/` folder | Identity documents, account numbers, screening reports. **Never converted, never digested, never in kb.** Gitignored. |
| `DISCARD` | archived only | Duplicates, superseded versions, material with no forward value. **The verdict and its reason are the record** — a DISCARD is archived, not destroyed. |
| `HOLD` | `Inbox/_Held/` | A decision that genuinely cannot be made yet. Out of the queue, not judged. |

## The staleness axis

Every routed file also gets:

- **`LIVE`** — still true, use as-is.
- **`VERIFY`** — probably true, but must be checked against the top rungs of the Source of Truth ladder before anything depends on it. Summaries and prior-year figures are almost always this.
- **`HISTORICAL`** — a record of a prior period, valuable as history, never as current fact.

## File Routing

| Purpose | Path |
|---|---|
| Work queue (**the program counter**) | `Get-ChildItem Inbox -File` plus `Inbox/*/` excluding `_Scratch`, `_Held`, `_Manifest.md` |
| Decision ledger (append-only) | `Inbox/_Manifest.md` |
| Extraction (.docx) | `pandoc -t markdown --wrap=none IN.docx -o <scratchpad>/OUT.md` |
| Extraction (.pdf) | `pypdf` — a short `python -c` script writing text to the scratchpad, or the `anthropic-skills:pdf` skill. **The Read tool cannot open a PDF on this machine.** |
| Reading copies (transient) | the session scratchpad — never committed |
| Processed originals | `Archive/Inbox_Processed/<YYYY-MM-DD>_<slug>/<filename>` |
| Held files | `Inbox/_Held/<filename>` |
| Never triaged at all | `Inbox/_Scratch/` |
| KB index | `kb/README.md` |

`.png`, `.csv`, `.md`, `.txt` are read directly.

---

## The Run

### Step 0 — Orient

1. List the queue with the command above. Report the count and name each file.
2. Read `Inbox/_Manifest.md`.
3. **An empty queue means stop** — say so. There is nothing to do.

### Step 1 — Select exactly one file

If {{KIT:OWNER}} named a file, take it. Otherwise **propose** the next one and say why, in this order: anything `Intake_Checklist.md` Tier 1 is waiting on, then anything carrying a deadline, then the rest of the record, then everything else. A proposal is not a selection: wait for confirmation.

### Step 2 — Extract and read

Read enough to classify honestly. If the file's title and its contents disagree, **the contents win** — say so. If the file contains PII, stop reading further than needed to classify it as `PRIVATE`.

### Step 3 — Classify and propose

Present exactly this, and nothing more:

```
## <filename>

**Contents:** <2-3 sentences on what is actually in it — not what the title suggests>
**Kind:** <verdict> · **Staleness:** <LIVE|VERIFY|HISTORICAL>
**Proposed destination:** <exact path, or "archive only">
**Where the original ends up:** <exact path under Archive/Inbox_Processed/, Inbox/_Held/, or the destination folder itself if the original IS the record>
**Deadlines found:** <each as an absolute date with what it is — or "none">
**What is lost:** <anything the routing does not preserve — or "nothing">
**Checklist rows it satisfies:** <Intake_Checklist.md row numbers — or "none">
```

Every line is required. A proposal missing one is malformed.

### Step 4 — HALT for the verdict

**Stop here.** {{KIT:OWNER}} confirms, redirects, or overrides. Do not write anything until they have answered. Ask in prose with numbered options, not a picker.

### Step 5 — Route, and END WITH THE DROP GONE

#### 5a — Write the destination

{{FILL: One bullet per record verdict from the table above: what is written where (original moved in beside a .md digest; rows appended to a ledger; a dated line appended to a log; a calendar row for a deadline).}}
- **`KB`** — `kb/<topic>.md` with the full frontmatter; the gate renders its index row in Step 6.
- **`PRIVATE`** — moved to `_private/`; the manifest row records the path and nothing about the contents.
- **`DISCARD` / `HOLD`** — no destination artifact.
- Flip any satisfied `Intake_Checklist.md` rows to ``on file — `<path>` ``, the path in backticks. A Status cell holds a status word, the missing document, and a pointer, with no figures or dates, because the gate rejects them; the figure or date lives in the entry the pointer names.

#### 5b — The original leaves `Inbox/`. This is the run's last write

Three legal endings, and no fourth. The `Archived to` cell records which:

| The original | ends up | `Archived to` reads |
|---|---|---|
| **Is the record** — a signed or governing document, PRIVATE, and any original worth keeping whole | its destination folder | that path |
| **Moved** — every other verdict but HOLD | `Archive/Inbox_Processed/<date>_<slug>/` | that path |
| **Moved** — HOLD | `Inbox/_Held/` | that path |

**This workflow never deletes a drop.** A file is moved, or it stays. If {{KIT:OWNER}} deletes one themselves, the cell reads `DELETED BY {{KIT:OWNER}}, YYYY-MM-DD` and nothing looser.

### Step 6 — Prove the drain, record, stop

1. Append one row to `Inbox/_Manifest.md`.
2. Re-run the queue listing from Step 0. **The file you just processed must not be in it.** If it is, go back to 5b.
3. Run the document gate: `<venv python> scripts/check_docs.py` (add `--write-kb` when a KB entry was written). A new digest needs a `doc_budgets.yaml` row; a new tier-3 file needs a pointer. **Fix the write, never the budget.**
4. Report in exactly this shape:

```
Routed:     <source> → <destination>   (<verdict> · <staleness>)
Original:   <where it went>
Deadlines:  <each row written, or "none">
Checklist:  <rows flipped, or "none">
Gate:       <the OK/FAIL line, verbatim>
Drop zone:  <every file still in the queue, from the listing — or "empty">
Next:       <the name of the next file — named, not processed>
```

**`Drop zone:` is quoted from the listing, not written from memory.** One file per run — the report ends by naming the next file precisely so that continuing on to it is visibly out of shape.

---

## Cardinal Structural Enforcements

Per the CLAUDE.md Cardinal Rule. Tiers: 1 impossible by construction · 2 deterministically caught · 3 format-shaped · 4 prose (residual risk, accepted).

| # | Discipline | Enforcement location | Tier |
|---|---|---|---|
| 1 | PII never reaches kb or a digest | `PRIVATE` verdict has no digest step; Step 2 stops reading on PII; `_private/` is gitignored | 3 — no script checks kb for PII patterns yet |
| 2 | A deadline in a file cannot be filed without being recorded | Step 3's required **Deadlines found** line; Step 6's **Deadlines:** line | 3 |
| 3 | Routing ends with the drop gone | Step 6 re-lists the queue and the report's **Drop zone:** field must quote it | 3 |
| 4 | The original survives | 5b has no deleting row; the only non-survival cell is attributed and dated | 3 |
| 5 | Nothing is written before {{KIT:OWNER}} rules | Step 4 is a hard HALT; Step 5 is keyed to the confirmed verdict | 3 |
| 6 | Lossy routing is disclosed before the decision | Step 3's **What is lost** line is required | 3 |
| 7 | One file per run | Step 6's report names the next file without processing it | 3 — residual risk accepted |
| 8 | The intake checklist cannot silently drift | Step 3 names the rows a file satisfies; 5a flips them; Step 6 reports them | 3 |
| 9 | A new document cannot land unbudgeted, orphaned, or with a hand-typed kb row | Step 6 runs `scripts/check_docs.py`; the report's **Gate:** line quotes its verdict | 2 |
