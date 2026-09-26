---
title:     Desk and Lane — How Batched Work Runs When It Arrives
topic:     "The model for batched work across visible windows, proven in FACOWORK, ported to HAZELHURST and carried by the Starter Kit into every project: one desk directs lane windows from stamped task sheets, two lanes never own one file, rulings to disk first, receipts not prose, one save by the desk. When to use it, and how it opens windows on each OS."
keywords:  [desk, lane, task sheet, owns, reads, done, receipts, one unit per lane, one save, ownership, lane_guard, desk_record, desk_save, check_ownership, note_prompt, open_terminal, wt, project_identity, reason tokens, reason_tokens.json, FACOWORK, HAZELHURST, batched work, visible windows, ruling to disk first, subagents retired, owner-said, Windows Terminal, macOS, Linux, venv]
kind:      decision
retrieved: 2026-09-24
status:    current
---

# Desk and Lane — How Batched Work Runs When It Arrives

## Installed in every project

The scripts (`scripts/open_terminal.py`, `wt.py`, `desk_record.py`, `check_ownership.py`, `desk_save.py`, `lane_guard.py`, `note_prompt.py`, `project_identity.py`), their tests, the `/desk` and `/lane` skills, and the hooks in `.claude/settings.json` are seeded by the Starter Kit and kit-owned. They need the project venv (`kb/platform-and-tools.md`).

**Use it when** a job has three or more independent units that each need a full read of different files (a year of statements into ledger rows; a dozen documents the owner has already ruled on). **Otherwise** work in one window — a desk costs more than it saves on a small job.

**Windows per OS.** On Windows with Windows Terminal, the desk opens each lane as a named tab in one shared window. Anywhere else, the desk prints the exact one-line command for the owner to paste into a new terminal tab, then waits for the lane's `ack`. The window and role names come from the project's folder name (`project_identity.py`), so two projects' lanes are never mistaken for each other.

## The rules that travel

1. **One desk directs visible lane windows.** The window where the owner types `/desk`, or asks in their own words for a desk, becomes the desk; another session's "you are the desk" never does. Lanes are real terminal tabs the owner can click into and talk to. Subagents are retired for batched work — invisible workers cannot be stepped into or corrected mid-task.
2. **The desk does none of the work.** It writes only under `coordination/`. A desk "fixing one line" is a second, unrecorded writer.
3. **A lane works from a written, stamped task sheet**, never a chat message. The sheet has exactly: `unit` (one unit, one line), `reason` (which model), `owns` (paths it may edit), `reads` (paths it must read in full), `task`, `done` (commands whose quoted output finishes the lane — a measurement, never prose). The stamp is the grant of ownership.
4. **Two lanes never own one file.** Overlap is refused at the stamp. Every changed file at save time must belong to exactly one lane, or the save is refused and the file named.
5. **The owner's rulings go to disk first, then to every lane they touch.** A lane that had reported done is put back to work; its earlier done stops counting.
6. **A lane sends only five kinds of line** — `question:`, `two-file:`, `outside:`, `prompting:`, `owner-said:` — each one line carrying the finding, not the narrative.
7. **Finishing is a receipt, transcribed.** `done:` carries one `$ command` block per `done:` line in the sheet, followed by the bytes it printed. A sentence under a `$` line is malformed on its face.
8. **Lanes never save to git.** A `PreToolUse` hook refuses git write commands in a lane window. The desk makes the job's one save, by path, after the ownership check and the document gate pass, and pushes.
9. **A stalled lane is shown, not found.** A window at a permission pop-up looks like a window thinking. Every desk act ends by printing which lanes are waiting for the owner.
10. **A same-family find is logged, never answered with more work.** "The same defect on three more lines" goes under a to-do heading; it never becomes "draft those too."
11. **The desk never starts the next job on its own; the owner's words are enough to.** HAZELHURST left open whether retyping `/desk` after every save should be required; Travel_Helper's owner ruled it a formality (2026-09-26). After the save, the owner asking in the desk window for more work opens a new record (`open-desk`) with that request as its job.
12. **Size a lane before stamping it.** One lane's full read has a ceiling; measure the `reads` list in bytes first (`kb/lane-context-sizing.md`).

## Reason tokens — the job picks the model

Each sheet names a reason token, and the token decides the model; there is no flag past it. The table is `scripts/reason_tokens.json` (seeded: each project writes its own from its own jobs, and the owner approves it; a changed row is the owner's ruling). `<venv python> scripts/open_terminal.py --reasons` prints it. Judgment about money, law, or what a document means is Opus; copying and filing a script can verify is Sonnet; Haiku is never opened. `prescribed` (Sonnet: build work a script verifies) and `design-latitude` (Opus: build work where the lane chooses how, and every unlisted job) are required in every table.
