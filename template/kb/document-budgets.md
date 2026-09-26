---
title:     Document Budgets — Why Every Document Has a Ceiling From Day One
topic:     "Why a new project budgets its documents before it has any: the tiers, the gate's six checks, budgets only go down, headroom is the deliverable, and the test for whether a sentence may be cut. Distilled from Fantasy_Football and the HAZELHURST scaffold."
keywords:  [doc_budgets.yaml, check_docs.py, byte budget, tier 1, tier 2, tier 3, orphan, headroom, 5% band, budgets only go down, ratchet, trim not raise, CLAUDE.md bloat, pointer index, rationale routing, memory cap, kb frontmatter, generated index, setup marker]
kind:      decision
retrieved: 2026-09-24
status:    current
---

# Document Budgets — Why Every Document Has a Ceiling From Day One

## The failure it prevents

In Fantasy_Football two documents reached 63 KB and 94 KB by the same route: every session appended, and no session was ever the one that had to stop. Its backlog went from 18 KB to 95 KB in three days. Nothing could name a size at which a document was wrong, so no size ever was. **A budget nobody enforces is a preference, and a preference loses to the next append.**

HAZELHURST proved it happens on day one, not month three. Its CLAUDE.md was scaffolded at 9.5 KB under a 12,000 b ceiling and passed 10,697 b the same day with zero documents on file. Claude argued budgets could wait until there was something to budget. The owner overruled it: *"if we don't budget now you see what happens with our claude.md its already super bloated? I wanted us to just start out right."* The owner was right. That ruling is why the kit ships the gate.

## Tiers — what a document costs

| Tier | Loaded | Cost | Example |
|---|---|---|---|
| 1 | every session | paid every turn of every session | `CLAUDE.md`, the memory index |
| 2 | when a trigger fires | paid per use | skills, commands, the intake checklist |
| 3 | when a session opens it | paid only on demand | kb entries, folder docs |
| 4 | never | a tier-3 file nothing points at | unread and indistinguishable from deleted |

Tier 4 is why the orphan check exists. A document nobody points at looks current and is read by nobody.

## The gate — `<venv python> scripts/check_docs.py`

1. **BUDGET.** Every tracked `.md`/`.html` outside `exempt_dirs` matches exactly one row and weighs no more than its budget. Bytes are measured as checked out under autocrlf, so the verdict does not flap. Under 5% headroom is named, non-fatally.
2. **ORPHANS.** A tier-3 document must be named, by path or basename, by a reader. The root readers are `CLAUDE.md`, `kb/README.md` and every `skills/*/SKILL.md`. Two tier-3 row flags extend them: `reader: true` makes a file a reader once a reader names it, so the chain always ends at a root. `reached_by_folder: true` counts a file as named when a reader names its folder (`Travelers/`).
3. **KB.** Every entry has its frontmatter; `kb/README.md` is rendered from it (`--write-kb`) and a hand-typed row fails.
4. **MEMORY.** Each auto-memory entry is at most 2,000 b, has its frontmatter, and has a pointer line in `MEMORY.md` of at most 220 b; the index stays under 140 lines.
5. **INTAKE.** Every Status cell in `Intake_Checklist.md` is a status word, a backticked pointer, and no figure. A cell that can only say "which document, who, where to read" cannot drift from the kb entry it points at.
6. **SETUP.** No Starter Kit marker survives in any document.

There is no `--fix`. Each failure prints the row's `rule:`, which says where the bytes go.

## Budgets only go down

The gate reads every committed revision of `doc_budgets.yaml` and takes each row's lowest value as its floor. Raising a budget to silence a failure stays red until it is lowered again. FF found a HEAD-only comparison loophole used twice in one commit; reading all history closes it.

**Lowering after a trim: set the ceiling above the trimmed size, not at it.** A ceiling just above a fresh trim is the zero-headroom state that caused the trim, and since budgets never rise, a number chosen too tight today cannot be walked back. The headroom is the deliverable.

## A new document's first ceiling

Size it from how it grows, and write the arithmetic in the row's comment, so the next session can tell a ceiling that was chosen from one that was guessed. A ledger first written at 4,537 b whose rows are about 80 b each gets 6,000 b — about a year more of rows plus the notes under the table — and the comment says so. A closed record (a finished job, a signed document's digest) gets its size plus modest headroom, and the comment names the one event that would make it grow.

## When a file hits its ceiling — trim, never raise

**The test for cutting a sentence:** is the thing it says enforced somewhere, or written down where a session would already be reading? If yes, the sentence is a second copy that can drift. Remove the copy, not the rule.

- **Grep before you cut.** A script docstring or test may quote the sentence.
- **Moving text within a file is break-even.** Consolidation is not a trim; a file shrinks only when bytes leave it. Dated narrative goes to a `kb/` entry the file points at; rationale goes to the docstring of the script that enforces it.
- **A row comment in `doc_budgets.yaml` is not the measurement.** It records what was true at a trim. Read the bytes (`--report`).

## Where each kind of text goes

| Text | Destination |
|---|---|
| A rule that applies on every pass | `CLAUDE.md` Standing Corrections, one line, after a kb entry holds the reasoning |
| Why a script works the way it does | that script's docstring (scripts/ is exempt) |
| A fact, a decision, a digest | `kb/`, one topic per entry |
| A procedure | `skills/<name>/SKILL.md` |
| Narrative, "what happened" | git history — not a document |

See `kb/how-this-project-remembers.md` for the full routing.
