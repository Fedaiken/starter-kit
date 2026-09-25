# START HERE — Set Up a New Project From the Starter Kit

**For Claude.** The owner has pointed you at this file to start a new project. Follow it exactly; it is the authority on this run. Say "the kit" for the folder this file is in, and `KIT` for its path.

**The shape: propose, don't interrogate.** The owner gives a sentence. You draft the whole setup from it, and they approve or correct it once. Every question and every permission prompt is a stall.

**Requirements:** Claude Code, git, and Python 3.9+ on this machine. Nothing else is assumed: any OS, any git host or none.

## Step 0 — The owner's profile (once per machine)

Run `python KIT/scripts/new_project.py profile --show` (use `python3` or `py -3` if `python` is not found; that command is `<python>` below).

- **Exit 0:** the profile is complete; quote its lines and go to Step 1.
- **Otherwise:** it prints what is missing. Ask for all of it **in one message**, with a proposed answer beside each where you can infer one (the name from `git config user.name`; the email from `git config user.email`; `gh auth status` for a GitHub account). Fields: name, email, git host (`github`, `other`, `none`), GitHub account (github only), permissions (`broad`: few prompts, the kit author's policy; `default`: Claude Code's own), deliverables (`html`, `docx`, or `md` — how they read what Claude writes for them), and one line on how they want Claude to talk to them. Then write it with `<python> KIT/scripts/new_project.py profile --name … --email … --git … [--github-owner …] --permissions … --deliverables … --talk "…"` and re-run `--show` until it exits 0.

The profile lives at `~/.starter-kit/profile.json`, outside the kit, because the kit is shared and nothing personal may enter it.

## Step 1 — The one sentence

If the owner has said what the project is for and what to call it, go on. Otherwise ask exactly one question: *"What's it for, and what should I call it?"* A name they coin is used verbatim.

## Step 2 — Draft the setup, and HALT

Research what the domain needs first (the governing documents, the rulebook or jurisdiction, what "getting current" means), then present this, every line filled:

```
**Project:** <Name> → <parent folder>/<Name>; repository: <per the profile's git host>
**What it is:** <two or three sentences — what it manages, the owner's role, what Claude does>
**Source of truth, highest first:** 1. … 2. … … N. Summaries, kb digests, memory — derived.
**Standing corrections:** <zero to four every-pass rules for this domain, or "none yet">
**Record folders:** <Folder/ — what goes in it>, … (+ which get a gitignored _private/)
**Inbox verdicts:** <VERDICT → Folder/>, … plus KB, PRIVATE, DISCARD, HOLD
**Close-session destinations:** <any calendar / ledger / log, with path, or "none">
**Intake, Tier 1 (decides the rest):** <# — document — who (Claude or owner)>, …
**Intake, Tier 2 (the record):** <# — document — who>, …
**Reason tokens for batched work:** the eight defaults, plus <any domain job, token → model>, or "defaults"
```

The parent folder defaults to the folder the kit sits in; propose another if the owner's projects live elsewhere. Then stop and ask: *"Go, or what should change?"* **Nothing is written before they answer.** A correction revises the draft and asks again. Their "go" also approves creating the private remote.

## Step 3 — Seed

```
<python> KIT/scripts/new_project.py <Name> --parent <parent folder> [--repo <repo>] [--remote <url>]
```

Quote its `seeded`, `machine`, `remote`, `venv` and `tests` lines. It builds `.venv` and runs the test suite there; **a failed venv or a failing test stops the run** — fix it (a missing tool, a proxy, a Python too old) before going on. The gate output it ends with **fails on purpose**: each `[SETUP]` line is a `{{FILL: …}}` marker Step 4 must write.

## Step 4 — Fill every marker from the approved draft

Work in the new folder. For each `[SETUP]` line, replace the marker with the approved content, following the marker's own instruction:

- `CLAUDE.md` — What This Project Is, the Source of Truth ladder, Standing Corrections, a Where Things Live row per record folder.
- `Intake_Checklist.md` — the Tier 1 and Tier 2 rows. Every Status cell is ``**needed** — <document> — `<pointer>` `` with no digit outside backticks.
- `skills/process-inbox/SKILL.md` — a verdict row per record folder, and a 5a bullet per verdict.
- `skills/close-session/SKILL.md` — the project's own destinations, or delete both markers.
- `scripts/reason_tokens.json` — add any approved domain token (`model` sonnet or opus, `job`, `reads_source`).

Create each record folder with a `.gitkeep`. A new document not covered by an existing `doc_budgets.yaml` glob — a calendar, a ledger, a log — gets its row now, with a `rule:` and a dated comment.

## Step 5 — Gate

```
<venv python> scripts/check_docs.py --write-kb
<venv python> scripts/kit_sync.py status
<venv python> -m pytest tests -q
```

`<venv python>` is named in the new `CLAUDE.md`. All three must pass; quote each verdict line. **Fix the write, never the budget.**

## Step 6 — Save and publish

1. Stage the seeded tree by name: every path `git ls-files --others --exclude-standard` prints, passed explicitly to `git add`. Commit from a message file: `Seed <Name> from the Starter Kit (kit <commit>)`.
2. By the profile's git host — `github`: `gh repo create <account>/<repo> --private --source . --push`; `other`: `git remote add origin <url>` then `git push -u origin main`; `none`: nothing, and say the repository is local only. A failure is reported with its error; the local commit stands.

## Step 7 — The owner's to-do list, in the Outbox

From the checklist, write the owner's rows (only theirs) as a to-do list, each with why it matters, into `Outbox/` in the profile's deliverables format (`html`: a plain page readable on a phone, light and dark; `docx`: via pandoc or python-docx; `md`: a short markdown file). Commit, push, and open it for them (`start` on Windows, `open` on macOS, `xdg-open` on Linux).

## Step 8 — Hand over

Tell the owner, in three short lines:

1. The project is at `<path>` and its remote is `<url>` (or local only, or the push failed).
2. **Open a new Claude session in that folder** — `CLAUDE.md` loads from the folder a session starts in, so this session is not the project's.
3. The first thing to do there: the Outbox list, then `process the inbox`.

## Cardinal Structural Enforcements

| # | Discipline | Enforcement location | Tier |
|---|---|---|---|
| 1 | Nothing is created before the owner approves the setup | Step 2 is a hard HALT on a fixed-field draft; Step 3 is keyed to their "go" | 3 |
| 2 | Nothing personal enters the kit | The profile is written to `~/.starter-kit/`, outside the kit; the seeder reads it from there | 1 |
| 3 | No section of the new project is left as a placeholder | The gate's SETUP check fails on any `{{FILL:` / `{{KIT:` marker; Step 5 requires its OK line | 2 |
| 4 | The project starts inside budget, with a generated kb index and in-form intake cells | Step 5 runs `check_docs.py --write-kb` | 2 |
| 5 | The hooks work on this machine from the first shell call | The seeder writes `settings.json` for this OS, builds `.venv`, runs the tests, and exits non-zero on a failure | 2 |
| 6 | The project starts in step with the kit | The seeder writes `.kit.json` from the copied files; Step 5 runs `kit_sync.py status` | 2 |
| 7 | The owner never has to read a format they don't read | Step 7 writes the Outbox file in the profile's format and opens it | 3 |
| 8 | The owner's session actually loads the new CLAUDE.md | Step 8's second line | 4 — residual risk accepted |
