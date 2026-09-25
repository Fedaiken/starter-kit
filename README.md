# Starter Kit

Start a new [Claude Code](https://claude.com/claude-code) project with a working method already in place, so the first session is about what the project is *for* rather than how Claude should work.

## Start a project

1. Get the kit onto your machine, anywhere you like: `git clone <this repository's URL>`.
2. Open Claude Code in any folder and say:

   > Read `<path to the kit>/START_HERE.md` and follow it. I want a project for <what it's for>, called <Name>.

3. The first time on a machine, Claude asks who you are, where your code lives, and how you like to work. It saves that on your machine only, never in the kit.
4. Claude drafts the whole setup — what the project is, which documents win, the folders, a list of documents to gather — and you approve or correct it once.
5. Claude builds it, checks it, saves it to git, and hands you your to-do list. Open a new Claude session in the new folder and start.

**You need:** Claude Code, git, and Python 3.9 or newer. Windows, macOS and Linux. GitHub is optional; so is any remote at all.

## What every project gets

| | |
|---|---|
| **A short CLAUDE.md** | A pointer index held to 10,000 bytes. Instructions files bloat by default; this one can't. |
| **Document budgets** | Every document has a size ceiling and a gate script that fails when one goes over. Ceilings only go down. |
| **The Cardinal Rule** | Behavior problems get fixed by changing a skill's structure — a required format, a halt, a gate — never with a "remember to" note. |
| **A knowledge base** | One topic per entry, with frontmatter. The index builds itself. |
| **Git discipline** | Claude commits named paths and pushes every change. Force-push and stash are blocked. |
| **Permissions** | Your choice at setup: few prompts, or Claude Code's defaults. |
| **Skills** | `process the inbox` (one file at a time, halts for your verdict), `close the session` (routes what a session learned; most of it to the bin), `check docs`. |
| **Desk and lane** | For batched work: one "desk" window hands stamped task sheets to visible "lane" windows, each owning its own files, with one save at the end. Lanes open as Windows Terminal tabs on Windows; elsewhere the desk gives you the command to paste into a new tab. |
| **An Outbox** | Anything written for you arrives in the format you read — HTML, Word, or Markdown. |

## How it stays current

Some files are shared by every project: the gate, the desk-and-lane scripts, the method notes. When one is improved inside a project, `close the session` won't finish until it's decided: send it back to your copy of the kit, take the kit's newer version, or keep it local on purpose. Improvements to someone else's kit go back as a pull request.

## Honest assumptions

- It is opinionated. The budgets and gates are the point; they will say no.
- Desk and lane need a Python virtual environment in each project; setup builds it and runs the test suite before you start.
- Tested on Windows. macOS and Linux are supported by design; the first run there may find a bug — please open an issue.

## Layout

| Path | What |
|---|---|
| `START_HERE.md` | The setup procedure Claude follows. |
| `template/` | What a new project is made from. |
| `kit_owned.txt` | The files kept identical across projects. |
| `scripts/new_project.py` | Profile, seed, and adopt (bring an existing project under sync). |
