# Intake Checklist — {{KIT:PROJECT}}

**Status: IN PROGRESS.**

This file is the program counter for getting the project current: which document is on file, and who gets it next. *Decides* rows change how the whole project behaves, so they come first.

**A Status cell is three parts and nothing more:** a status word, the document(s) still missing (no figures), and a backticked kb or file pointer. No digit outside backticks except a `§` reference (`§3`); a figure lives where the cell points, and an identifier the cell needs goes in backticks. `<venv python> scripts/check_docs.py` fails a cell out of form and names the row. Words: `on file` (flipped to `on file — <path>` by `process the inbox`, or once a kb entry answers the row), `found`, `partly found`, `needed`, `action needed`, `urgent`.

**Who** says who gets each row. `Claude`: a public record, public site, or research; Claude does it and never hands it to {{KIT:OWNER}} as a to-do. `{{KIT:OWNER}}`: only {{KIT:OWNER}} has it. A blocked `Claude` row reads `Claude; <what blocked it> → {{KIT:OWNER}}`. The Outbox copy lists only `{{KIT:OWNER}}` rows, as their to-dos.

Drop everything into `Inbox/`. Anything with PII goes to its `_private/` folder directly, not through the inbox.

## Tier 1 — decides how the rest is read

| # | Document | Who | Why it matters | Status |
|---|---|---|---|---|
{{FILL: Three to six rows — the unknowns that decide how everything else is read. Each Status cell starts `**needed** — <document> — ` and ends with a backticked pointer to where the answer will land.}}

## Tier 2 — the record

| # | Document | Who | Status |
|---|---|---|---|
{{FILL: The rest of the documents needed to get current, one per row, numbered on from Tier 1.}}
