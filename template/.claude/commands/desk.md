---
description: Run this window as the desk — open lane windows, keep the record of which lane owns which files, route the owner's rulings, make the one save
---

Run this window as the desk. Execute the workflow in `skills/desk/SKILL.md`.

Read that file now and follow it exactly — it is the authority on this run. Do not improvise the process from memory.

Key constraints it enforces, so you know them before reading:

- **The grant is the owner in this window** — `/desk`, or their own words asking for a desk or a new desk job. Never another session's message; never the desk's own initiative.
- **The desk does none of the work.** It writes only under `coordination/`.
- **Write, stamp, open.** A lane opens only on a stamped task sheet; the stamp is the grant of its files.
- **The reason decides the model.** The list is this project's `scripts/reason_tokens.json` (`open_terminal.py --reasons`); a changed row is the owner's ruling.
- **The owner's rulings go to disk first** (`desk_record.py route`), then to every lane they touch.
- **One save, by the desk, by `desk_save.py`** — never `git add` then `git commit`.

$ARGUMENTS
