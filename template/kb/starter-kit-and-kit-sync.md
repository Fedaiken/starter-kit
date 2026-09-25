---
title:     The Starter Kit and Kit Sync — How Portable Improvements Travel
topic:     "This project was seeded from the Starter Kit. Kit-owned files are shared with every project; kit_sync.py flags any that changed on either side, and close-session makes a decision on each: push to the kit, pull from it, or keep the local version."
keywords:  [Starter Kit, kit_sync.py, .kit.json, kit-owned, seeded, push, pull, keep, adopt, drift, portable improvement, START_HERE, close-session, template, profile, STARTER_KIT, pull request, kit_url]
kind:      decision
retrieved: 2026-09-24
status:    current
---

# The Starter Kit and Kit Sync

## Why the kit exists

The project the kit was drawn from spent its first hour on Claude reading sibling projects' CLAUDE.md files, porting a document gate, copying a permission policy, and re-deriving the Cardinal Rule, the git rules and the kb conventions — before its owner could talk about the subject. The kit holds those, so a project starts at "what is this project for."

## Two kinds of file

- **Seeded** files are copied once and belong to the project from then on: `CLAUDE.md`, `doc_budgets.yaml`, the inbox and close-session skills, `.gitignore`, the intake checklist, `scripts/reason_tokens.json`, `kb/platform-and-tools.md`, and the settings written for this machine. They are filled at setup and diverge by design.
- **Kit-owned** files are the same in every project: the gate, this sync script, the desk-and-lane scripts, their tests, the desk and lane skills, the method kb entries, `.gitattributes`, the command wrappers. The list is `kit_owned.txt` in the kit.

## Finding the kit

The project never stores where the kit is on disk — a project moves between machines and the kit is cloned wherever each owner likes. `kit_sync.py` looks, in order, at the `STARTER_KIT` environment variable and at the `kit` path in `~/.starter-kit/profile.json` (which the kit's seeder writes). `.kit.json` records only the kit's URL, so a machine without a copy can be told where to clone it.

## The loop — `<venv python> scripts/kit_sync.py`

`.kit.json` records, per kit-owned file, the hash of the project's copy and of the kit's copy as of the last decision. `status` compares both to now:

| Verdict | Meaning | Exit |
|---|---|---|
| `in sync` | project and kit are identical | 0 |
| `kept local` | they differ, and that difference was already decided | 0 |
| `UNDECIDED` | one side moved since the last decision (it says which) | 1 |

Each UNDECIDED file takes one decision:

- `push <path>` — the project's version is better for every project. Copies it into this machine's kit, commits it there, and pushes the kit. If the kit is someone else's (a clone of a shared kit), the push to its origin fails; the commit stays in your copy and the script says to offer it as a pull request.
- `pull <path>` — the kit improved. Copies the kit's version here.
- `keep <path>` — this project's difference is local. Records the current state so the file stops asking.

`/close-session` runs `status` in its gate step, and a finding about a kit-owned file routes to the `kit` destination. A portable fix therefore reaches the kit the same session it is made, or is kept local on purpose. It is never forgotten.

## What is not synced

Seeded files never are; a better skill shape or CLAUDE.md section found in one project is carried back by editing the kit's `template/` by hand, in a session opened in the kit.
