---
title:     Cardinal Rule — Solve Through Structure, Never Through Reminders
topic:     "The standing rule for fixing a behavior gap: restructure the skill so the gap cannot occur or surfaces deterministically, never add a Pitfall, a warning, or a memory. Carried verbatim across the projects the Starter Kit was drawn from, and by the kit into every project it seeds."
keywords:  [cardinal rule, structural enforcement, pitfalls, warnings, memory entries, format-shaped, halt conditions, deterministic checks, enforcement ladder, skill design, remember to check, enforcement table]
kind:      decision
retrieved: 2026-09-24
status:    current
---

# Cardinal Rule — Solve Through Structure, Never Through Reminders

**Always solve behavior gaps and skill failures through structural skill design — never through Pitfalls, warnings, or memories.**

When a skill produces wrong output, when guidance gets ignored, when discipline lapses, the fix lives in the skill's structure. Not in another "remember to check" note.

This text is carried verbatim from project to project. It is not trimming stock when a budget gets tight; take the bytes from prose the project wrote.

## What "structural" means

- **Mandatory format outputs.** A filled-cell matrix where an empty cell visibly fails; a required citation pattern where omission is malformed.
- **Hard halt conditions.** REFUSE language; deterministic verification scans before proceeding.
- **Tool-level enforcement.** A gate script that exits non-zero; a hook that refuses the command; a format the tool boundary enforces.
- **Generative discipline.** The format shape forces the check; the only things that can happen are derivable from a populated source.

The enforcement ladder, highest first: tool/harness-enforced > deterministic-scan-gated > format-shaped > prose. Climb as high as the gap allows. When structure genuinely cannot reach (irreducible judgment, or too rare to gate proportionately), name the residual risk explicitly in the skill's enforcement table. Do not paper it with a Pitfall.

## What does NOT count as a fix

- Adding a Pitfall ("don't do X")
- Adding a memory entry ("always remember Y")
- Adding a cardinal-rule warning in prose
- "I'll be more careful next time"

These all rely on Claude remembering to check. They are not solutions; they restate the problem instead of removing it.

## The test

If the proposed fix is a sentence I have to remember to follow, it is the wrong fix. If the proposed fix is a format my output must conform to, or a state the workflow cannot leave without resolving, it is the right fix.

## Where it is applied

Every `skills/*/SKILL.md` ends with a Cardinal Structural Enforcements table: one row per discipline, the enforcement location, and an honest tier (1 impossible by construction, 2 deterministically caught, 3 format-shaped, 4 prose with residual risk accepted). A row with an empty enforcement column is malformed. `scripts/check_docs.py` is the first tier-2 enforcement a new project has; `scripts/kit_sync.py` is the second.
