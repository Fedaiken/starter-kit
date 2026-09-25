---
title:     How This Project Remembers — CLAUDE.md, kb, Memory, Skills, Folder Docs
topic:     "Where each kind of knowledge lives and why: CLAUDE.md is a pointer index, kb/ holds one topic per entry with frontmatter, memory is for cross-cutting feedback only, skills hold procedure, folder docs hold the record, and close-session routes a session's findings with delete as the default. Carried by the Starter Kit."
keywords:  [CLAUDE.md, pointer index, kb, knowledge base, frontmatter, probe, decision, reference, retrieved date, superseded, generated index, auto-memory, MEMORY.md, one fact per file, skills, slash commands, thin wrapper, folder docs, source of truth, close-session, routing, delete default, standing corrections, what the owner reads, Outbox]
kind:      decision
retrieved: 2026-09-24
status:    current
---

# How This Project Remembers

Every session starts with no memory of the last one. What it knows is what it loads. So the question for every fact is: **where would a future session look for this, and will it find it without being told?**

## The five homes

| Home | Holds | Loaded | Rule |
|---|---|---|---|
| `CLAUDE.md` | Pointers and rules that apply on every pass | every session (tier 1) | A pointer index, not a content store. Rationale lives where the pointer points. |
| `kb/<topic>.md` | Facts, decisions, digests — prose that stays prose | on demand (tier 3) | One topic per entry. Frontmatter required. Split before 16,000 b. Supersede rather than append. |
| `skills/<name>/SKILL.md` | Procedure — how a repeated job is done | when its trigger fires | One skill per trigger, with a thin `.claude/commands/<name>.md` wrapper that says "read the skill and follow it." |
| Folder docs | The record itself — what the documents say | on demand | The owning folder, with the source path cited beside each fact. |
| Auto-memory | Cross-cutting working feedback no skill owns | its index every session | One fact per file, at most 2,000 b, with **Why** and **How to apply**. |

## kb entries

Every entry opens with this frontmatter, and the gate refuses one without it:

```
---
title:     <one line>
topic:     "<one line: what a session would search for>"
keywords:  [<the words a future session would grep>]
kind:      probe | decision | reference
retrieved: YYYY-MM-DD
status:    current | superseded
---
```

- **probe** — what an outside surface was observed to say (a published figure, a portal's behavior). `retrieved:` is when it was seen and after when to doubt it.
- **decision** — a call the owner made and why. `retrieved:` is the date of the call. Quote their words.
- **reference** — a digest of a document on file. `retrieved:` is when it was digested.

`kb/README.md` is **generated** from the frontmatter by `<venv python> scripts/check_docs.py --write-kb`. Never hand-edit it. A superseded entry stays listed with its status visible, because a stale note that reads as current is worse than an absent one.

## Memory is the last resort

A memory entry is a sentence Claude has to remember to apply — exactly what the Cardinal Rule forbids as a fix. If a *specific skill* owns the behavior, fix that skill's structure instead. Memory is only for feedback that cuts across unrelated tasks (how the owner wants replies shaped, for example).

## Closing a session

`/close-session` enumerates what the session found and routes each finding to exactly one home, printed as a matrix where every cell is filled and every "written to" path exists. **`delete` is the default.** If you cannot name the question a future session would ask that a finding answers, it goes nowhere. This is what stopped FF's backlog, which grew from 18 KB to 95 KB in three days because "capture before the conversation ends" had one destination and no reader.

## What the owner reads

The `.md` files in the record are Claude's working memory. Anything for the owner — a checklist to gather documents, a summary, a draft — goes to `Outbox/` in the format the owner reads, which `CLAUDE.md`'s Outbox row names (set from the owner's profile at setup). The kit's first owner reads no `.md` at all (*"i don't read md files, those are for you"*), which is why the Outbox exists.

## Source of truth

`CLAUDE.md` carries a numbered ladder of which source wins when two disagree. The bottom rung is always the derived material — summaries, kb digests, memory. A kb digest is a convenience; the document it digests wins.
