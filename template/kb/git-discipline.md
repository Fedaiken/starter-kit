---
title:     Git Discipline — Claude Owns Version Control
topic:     "How every Starter Kit project uses git: Claude stages named paths, commits from a message file and pushes in the same turn; a private remote from day one when the owner has one; secrets and PII never enter git; destructive commands ask and force-push is denied; Archive/ backups before structural edits."
keywords:  [git, GitHub, gh, private repo, remote, local only, git add named paths, never git add ., commit -F, message file, heredoc, PowerShell, push same turn, force push, stash, reset, settings.json deny ask, gitignore rationale, gitattributes, autocrlf, index.lock, Archive backup, PII, secrets, lanes never commit, owner identity, profile]
kind:      decision
retrieved: 2026-09-24
status:    current
---

# Git Discipline — Claude Owns Version Control

The owner does not run git. Claude does, every time, without being asked — and says so plainly when something did not land.

## The rules

1. **A private remote from day one, when there is one.** `git init -b main`; the identity is the owner's, from their Starter Kit profile. On GitHub: `gh repo create <owner>/<name> --private --source . --push`. On another host, add the URL the owner gives as `origin`. With no remote (a work machine that allows none), the repository is local and every "push" below is skipped and said so.
2. **Stage named paths.** Never `git add .` or `git add -A`. The paths staged are the paths this turn wrote; anything else in `git status` is someone else's or a mistake, and gets named, not swept in.
3. **Commit from a message file.** Write the message to the scratchpad, then `git commit -F <path>`. It works in every shell; a heredoc does not (PowerShell has none).
4. **Push in the same turn.** A commit that is not pushed is a backup nobody has. If the push fails, say so in the reply — do not leave it for the owner to discover.
5. **The subject line says what changed, in plain words.** The owner reads `git log` as the project's diary.

## What the permission policy enforces

`.claude/settings.json`, written at setup for this machine, makes the dangerous commands structural, not a matter of care:

| Rule | Commands |
|---|---|
| **deny** | `git push --force` / `-f`, `git stash`, `rm -rf /` |
| **ask** | `git reset`, `clean`, `checkout`, `restore`, `rebase`, `merge`, `branch -D` |
| **allow** | `git add`, `git commit`, `git push origin main` |

`git stash` is denied because a stash is invisible work: it hides changes from the next session's `git status`, and a forgotten stash is lost work.

## What never enters git

- **Secrets:** `.env`, credentials, API keys. One committed is burned — rotate it, don't just delete the line.
- **PII:** identity documents, account numbers, screening reports. They live in gitignored `_private/` folders; the tracked prose refers to them by path only. **File names leak too:** an exported statement or email attachment can carry a full account number in its name, so tracked text keys a private document on an id you assign (`E017`, `stmt-2025-03`), never on its original file name.
- **Raw dumps** too large or too PII-heavy for a remote. They are sources to mine; what matters gets a kb digest and its original filed through the inbox.
- **Machine-local state:** `.claude/settings.local.json`, `.venv/`, `Working/`.

**Every `.gitignore` line carries its rationale.** An unexplained exclusion becomes an unexplained missing file six months later.

## Line endings

`.gitattributes` normalizes text to LF in the index and declares PDFs, Office files, and images binary, so git never rewrites a signed PDF. On Windows `core.autocrlf` is on and the "LF will be replaced by CRLF" warnings are noise. The document gate measures bytes as checked out with CRLF endings on every OS, so its verdict is the same everywhere.

## Archive before a structural edit

Before restructuring `CLAUDE.md`, `doc_budgets.yaml`, `.gitignore`, or `settings.json`, copy the file to `Archive/<name>_<YYYY-MM-DD>_pre-<change>.<ext>`. Git has the history, but the owner can open a file in `Archive/`; a commit takes git to read.

## When there is more than one writer

A transient `.git/index.lock` can appear when two git calls overlap (the gate runs several). Check no git process is running, then retry; remove the lock only if it persists.

**Lanes never commit.** A hook refuses git write commands in a lane window, and the desk makes the job's one save by path after an ownership check. See `kb/desk-and-lane-philosophy.md`.
