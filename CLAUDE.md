# Starter Kit — Project Instructions

The kit that starts every new Claude Code project with the method already in place. It is **public and shared**: friends and other machines clone it. A session opened here is maintaining the kit, not a project. Setting up a project from it: `START_HERE.md`.

## What is here

| Path | What |
|---|---|
| `START_HERE.md` | The setup procedure any Claude follows, on any machine. |
| `README.md` | The public front page. `Outbox/Starter_Kit.html` is rendered from it (below) and never hand-edited. |
| `template/` | Copied into a new project by `scripts/new_project.py`. `{{KIT:…}}` markers are filled by the script from the owner's profile and the machine; `{{FILL:…}}` markers by the setup interview. `_gitignore` becomes `.gitignore` (so it does not apply to this repo). `.claude/settings.json` is not in the template: the seeder writes it per OS and per permission choice. |
| `kit_owned.txt` | The template files that stay identical in every project, kept in step by `template/scripts/kit_sync.py`. Everything else in `template/` is seeded. |
| `scripts/new_project.py` | `profile` (the owner's details, kept at `~/.starter-kit/profile.json`, never here), seed, `adopt`. |
| `scripts/check_private.py` | The pre-commit privacy check (Rules). |

## Rules

- **Nothing personal in this repo.** No name, email, account, machine path, or project detail of any owner — in files or in commit metadata. Owner details come from the profile at seed time. Before every commit, `python scripts/check_private.py` must print OK: it checks every file and the commit identity against the owner's profile without the kit ever naming them.
- **A kit-owned file carries no marker and no owner's name.** It must be byte-identical across projects.
- **Every OS.** Scripts are Python 3.9+ stdlib (plus PyYAML for the gate); anything OS-specific is chosen at run time or written by the seeder.
- **The method lives in the template's kb** (Cardinal Rule, budgets, git, memory routing, desk and lane, kit sync). Do not restate it here.
- **Changes arrive two ways:** `kit_sync.py push` from a project commits here automatically; a seeded-file improvement is edited into `template/` by hand in a session opened here.
- **Test before committing a template or script change:** seed a throwaway project into the scratchpad (`--parent <scratchpad>`), fill its markers, and confirm `check_docs.py`, `kit_sync.py status` and the test suite all pass in it.
- **Git:** Claude owns it — stage named paths, commit from a message file, push in the same turn (`template/kb/git-discipline.md`).
- **The Outbox page:** after changing `README.md`, re-render with `pandoc README.md -s --metadata title="Starter Kit" -o Outbox/Starter_Kit.html` and commit both.
