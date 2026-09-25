# {{KIT:PROJECT_UPPER}} — Project Instructions

A **pointer index**, not a content store. It loads every session and is gated at 10,000 b (`doc_budgets.yaml`, tier 1). When you learn or decide something:

- **New fact or correction** → a `kb/` entry (`kind: probe` observed, `decision` chosen, `reference` a document's digest). Standing Corrections *only* for what applies on every pass.
- **New procedure** → `skills/<name>/SKILL.md` plus a thin `.claude/commands/<name>.md`; one trigger row here.
- **Anything else** → the relevant folder doc; a pointer here at most.

Back up to `Archive/` before any structural edit. Why this file stays small: `kb/how-this-project-remembers.md`.

---

## Cardinal Rule — Solve Through Structure

Fix a behavior gap by restructuring the skill so the gap cannot occur or surfaces deterministically — a required format, a halt condition, a gate script. Never a Pitfall, a warning, or a memory entry. Test: if the fix is a sentence I have to remember, it is the wrong fix. Full rule and the enforcement ladder: `kb/cardinal-rule-solve-through-structure.md`.

---

## What This Project Is

{{FILL: Two or three sentences. What the project manages, who owns it and their role, and what Claude does here. Name the one thing it exists to get right.}}

The owner is **{{KIT:OWNER}}**. Started {{KIT:DATE}}. **Read `Intake_Checklist.md` first until it says COMPLETE** — its Tier 1 rows are the unknowns that decide how everything else is read.

---

## Source of Truth

When sources conflict, higher wins. Always.

{{FILL: A numbered ladder, highest first, four to six rungs. The top rung is the signed or primary document; the bottom rung is always "Summaries, kb digests, memory — derived. Verify against the rungs above before acting."}}

---

## Standing Corrections

- **Never invent a number or a date.** Not in a document in this repo → "not on file," and stop.
- **The owner's vocabulary wins.** When {{KIT:OWNER}} coins a name, use it verbatim.
- **Every deadline is an absolute date**, computed from its trigger (served, received, filed) with the computation shown.
- **Every figure from outside this repo carries its source** (a URL or a document path) and a `retrieved:` date. A figure without a date is a defect.
{{FILL: Zero to four more lines, each a rule that applies on every pass in this domain (a jurisdiction, a privacy line, a unit of measure). Delete this marker if there are none yet.}}

---

## Where Things Live

| Folder / file | Contains |
|---|---|
| `Intake_Checklist.md` | Documents needed to get current, status per row. |
{{FILL: One row per record folder this project needs, from the setup interview. A `_private/` subfolder is named here when the domain has PII; every `_private/` is gitignored.}}
| `kb/` | One topic per entry with frontmatter. `kb/README.md` is **generated** — never hand-edited. |
| `skills/` · `.claude/commands/` | Skills and their slash-command wrappers, one per trigger. |
| `doc_budgets.yaml` · `scripts/check_docs.py` | Every document's tier and byte ceiling, and the gate. **A new document does not exist until it has a row.** |
| `Inbox/` | Drop zone. `_Manifest.md` is the decision ledger. `_Scratch/` is never triaged. `_Held/` is parked. |
| `Outbox/` | {{KIT:DELIVERABLES}} |
| `Archive/` | Backups and processed originals. Never a place to move a document *to*. |
| `Working/` | Scratchpads for interrupted runs (gitignored). A matching file means resume first. |
| `coordination/` | The desk's record, task sheets, and closed jobs. Written only by the desk scripts. |
| `.kit.json` · `scripts/kit_sync.py` | Which files came from the Starter Kit, and the check that keeps them and the kit in step. |

---

## Triggers & Workflows

Every trigger is also a `/` command; both execute the workflow file directly — read it, never work from a summary.

| Trigger | Action | Workflow file |
|---|---|---|
| `process the inbox` / `/process-inbox` | Triage ONE file: extract, classify, halt for the owner's verdict, route, record, drop gone. | `skills/process-inbox/SKILL.md` |
| `close the session` / `/close-session` | Route this session's findings to `kb/`, a folder doc, memory, the kit, or the bin. | `skills/close-session/SKILL.md` |
| `check docs` / `/check-docs` | Run the document gate and quote the output. | `.claude/commands/check-docs.md` |
| `/desk` | Run this window as the desk: stamp task sheets, open lane windows, route the owner's rulings, make the one save. | `skills/desk/SKILL.md` |
| `/lane <name> <sheet>` | Run this window as a lane on one stamped sheet (the desk's opener types it). | `skills/lane/SKILL.md` |

Desk and lane rules and when to use them: `kb/desk-and-lane-philosophy.md`. This project's reason tokens: `scripts/reason_tokens.json`.

---

## Workspace Rules

- **Platform:** {{KIT:PLATFORM}}. `<venv python>` means `{{KIT:VENV_PYTHON}}` here; the gate, tests and hooks run in it. Tools and the venv rebuild line: `kb/platform-and-tools.md`.
- **Document budgets.** Every tracked `.md`/`.html` has a ceiling in `doc_budgets.yaml`; budgets only go down. A tier-3 document nothing points at is an orphan. Memory entries: 2,000 b, indexed. `<venv python> scripts/check_docs.py` is the gate; every skill runs it. Why: `kb/document-budgets.md`.
- **Generated documents are never hand-edited.** Change the source and re-render.
- **Git:** Claude owns it — stage named paths, commit from a message file, push in the same turn. Say so if a push fails. Full rules: `kb/git-discipline.md`.
- **Secrets and PII never enter git.** `.gitignore` carries the rationale per line.
- **Talking to {{KIT:OWNER}}:** {{KIT:TALK}}
