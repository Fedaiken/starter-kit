---
description: Triage ONE file from Inbox/ — classify, halt for verdict, route, record
---

Execute the inbox triage workflow in `skills/process-inbox/SKILL.md`.

Read that file now and follow it exactly. It is the authority on this run — do not improvise a triage process from memory.

Key constraints it enforces, so you know them before reading:

- **One file per run.** Process a single file, then stop and name the next one without touching it.
- **Halt before writing.** Step 4 is a hard stop for the owner's verdict. Nothing is written until they rule.
- **PII goes to `_private/` unconverted.** No digest, no kb entry.
- **Every deadline found is recorded.**
- **The run ends with the drop gone from `Inbox/`.** Step 6 re-lists the queue and quotes it.

$ARGUMENTS
