# Inbox Processing Manifest

Append-only decision ledger. One row per file processed. The work queue is
the set of files still sitting in `Inbox/` — this file is the record of
what happened to everything that left it.

**`Inbox/_Scratch/` is outside all of it** — drop anything there to show it in
a conversation: no row, no verdict, no clock, delete at will. Scratch files
are ephemeral by contract; anything durable moves OUT to `Inbox/` proper.

**`Inbox/_Held/`** is judged-and-parked: a file whose routing genuinely cannot
be decided yet. It carries a HOLD row and never ages out.

Columns are positional. Don't reorder or add columns.

| # | Source | Verdict | Staleness | Destination | Archived to | Notes |
|---|---|---|---|---|---|---|
