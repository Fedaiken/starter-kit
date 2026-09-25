---
name: close-session
description: |
  Route this session's findings to the place a future session would look for them — a kb/ entry, a folder doc, a memory, the intake checklist, the Starter Kit, or the bin. Appends nothing to any tracker.
  - MANDATORY TRIGGERS: "close the session", "/close-session"
purpose: Route what this session found to where it gets read next.
---

# Close Session — Route, Don't Append

You are ending a working session. Everything it learned, decided, or noticed is about to be lost or filed. **The failure this skill exists to prevent is filing it all in one place.** The Fantasy_Football backlog went from 18 KB to 95 KB in three days because "capture before the conversation ends" had one destination and no reader. This skill is a routing decision per finding: a filled-cell matrix — prose is not a value the matrix accepts. Why: `kb/how-this-project-remembers.md`.

**`delete` is the most common destination.** Most of what a session notices has no forward value. If you cannot name the question a future session would ask that a finding answers, the finding is deleted.

## File Routing

| Purpose | Path |
|---|---|
| kb entry (external fact, document digest, or project decision) | `kb/<slug>.md` with the frontmatter block; the index is rendered by the gate in Step 4, never typed |
| Folder doc (a fact that belongs to the record) | the owning file under the record folders in `CLAUDE.md`, Where Things Live. Cite the source path beside the fact |
| Intake checklist (a document now on file, or newly needed) | `Intake_Checklist.md` — flip a row or add one |
| Kit (a change to a kit-owned file every project should get) | `<venv python> scripts/kit_sync.py push <path>` — copies it into the Starter Kit and commits it there |
| Memory entry (cross-cutting working feedback that no skill owns) | the auto-memory folder, with frontmatter (`name`, `description`, `metadata.type`) and a body with **Why** and **How to apply**, plus its `MEMORY.md` line. **At most 2,000 b; one fact per file** |
| Standing Correction (applies on every pass) | `CLAUDE.md` — one line, only after a `kb/` entry holds the reasoning |
{{FILL: Zero or more rows for this project's own destinations (a dated-obligations calendar, an append-only ledger, a log), each with its path. Delete this marker if there are none.}}

## The Run

### Step 0 — Enumerate

List every finding from this session as a one-line candidate: facts learned, decisions {{KIT:OWNER}} made and why, deadlines surfaced, documents now on file, corrections to how you should work here, improvements to a kit-owned file, work identified but not done. Draw from the whole session. **If there are no findings, say "no findings" and go to Step 4** — do not manufacture one so the matrix has a row.

### Step 1 — Route each finding

For each candidate: *what question would a future session ask that this answers, and where would it look?* Pick exactly one destination:

| Finding is… | Destination | Test |
|---|---|---|
| A fact about the outside world that cost a probe (a published figure, a vendor's price, a portal's behavior) | `kb/` `kind: probe` | Would a session working that surface be wrong without it? |
| A decision {{KIT:OWNER}} made, with a why | `kb/` `kind: decision` | Would a session re-derive or reverse it without knowing? |
| A digest of a document on file | `kb/` `kind: reference`, or the folder doc | Does it span folders (kb) or belong to one record (folder doc)? |
| A fact about the record | `folder doc` | Would the next session look in that folder first? |
| A document that arrived or is newly needed | `checklist` | Does a row flip or need adding? |
| An improvement to a kit-owned file (`kit_sync.py status` lists them) | `kit` | Would every other project want it? If not, `keep` it local in Step 4. |
| A correction to how Claude should work here that no single skill owns | `memory` | Would you make the same mistake in an unrelated task? If a *specific skill* owns it, fix that skill's structure instead — the Cardinal Rule. |
| A rule that applies on every pass | `standing correction` | Only after a `kb/` entry holds the full reasoning |
{{FILL: One row per project destination added to File Routing above, with its test. Delete this marker if there are none.}}
| Anything else — narrative, effort, "what happened" | `delete` | The default. |

### Step 2 — Write every destination now

A destination that is not written in this run is a nomination, not a destination.

### Step 3 — Print the matrix

```
| # | Finding (one line) | Destination | Written to | Why here |
|---|---|---|---|---|
| 1 | … | kb/ | kb/<slug>.md | a session on that topic would repeat the probe |
| 2 | … | kit | Starter_Kit scripts/check_docs.py (kit commit abc1234) | every project's gate has the same gap |
| 3 | … | delete | — | narrative; nothing asks for it |
```

Every cell filled. `Destination` is one of the values in the Step 1 table, exactly. `Written to` is a path or a row that exists in the tree right now, a kit commit, or `—` for `delete` only.

### Step 4 — Gate, commit, stop

1. Run `<venv python> scripts/kit_sync.py status` and quote its verdict line. Every `UNDECIDED` file takes `push`, `pull`, or `keep` now; re-run until it exits 0. A `pull` changes a file here — it is staged with this run's paths.
2. Run `<venv python> scripts/check_docs.py --write-kb` and quote its verdict line. It renders the kb index, and fails on a document over budget, a new file with no `doc_budgets.yaml` row, a tier-3 orphan, a memory entry over cap or unindexed, or a setup marker left behind. **Fix the write, never the budget.**
3. Stage every path in the `Written to` column by name (plus `kb/README.md` and `.kit.json` if they changed), commit from a message file, and push in the same turn. Say what landed to {{KIT:OWNER}} in plain words, and stop.

## Cardinal Structural Enforcements

| # | Discipline | Enforcement location | Tier |
|---|---|---|---|
| 1 | A finding cannot be "captured" in prose | The output is a matrix whose `Destination` column takes a fixed set of values; prose is not one of them | 3 |
| 2 | A destination cannot be nominated without being written | `Written to` must hold a path that exists at print time | 3 |
| 3 | A kb entry cannot be left out of the index, land malformed, or push a file over budget | Step 4 runs `scripts/check_docs.py --write-kb`: it renders the index from frontmatter and exits 1 on any budget, orphan, kb, memory, intake, or setup defect | 2 |
| 4 | A portable improvement cannot be silently stranded in one project | Step 4 runs `scripts/kit_sync.py status`, which exits 1 while any kit-owned file changed on either side without a decision | 2 |
| 5 | `delete` is chosen often enough | Prose: the skill says it is the default. Residual risk accepted | 4 |
| 6 | Zero findings does not produce a fake row | Prose: "say no findings." Residual risk accepted; an invented row is visible in the matrix | 4 |
