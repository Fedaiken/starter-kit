#!/usr/bin/env python
"""Seed a new project from the Starter Kit, keep the owner's profile, or adopt a project.

    python scripts/new_project.py profile --show
    python scripts/new_project.py profile --name "Ada" --email ada@example.com --git github \\
        --github-owner ada --permissions broad --deliverables html --talk "short, decision first"
    python scripts/new_project.py <Name> [--repo <name>] [--parent <dir>] [--remote <url>]
    python scripts/new_project.py adopt <existing project folder>

Runs on Windows, macOS and Linux with Python 3.9+. The procedure around it is
START_HERE.md; this script does only what a script can verify.

THE PROFILE
-----------
Who the owner is, where their code goes, how they want to be talked to, and how
they read what Claude writes for them. It is asked once per machine and kept
OUTSIDE the kit, at ~/.starter-kit/profile.json, because the kit is public and
shared: nothing personal may live in it. The profile also records where this
copy of the kit is, which is how scripts/kit_sync.py in a project finds it.

SEEDING
-------
Copies template/ into <parent>/<Name>, fills every {{KIT:...}} marker from the
profile and this machine, writes .claude/settings.json for this OS (hook paths
differ: .venv/Scripts/python.exe on Windows, .venv/bin/python elsewhere),
builds .venv and runs the test suite in it, runs `git init` with the profile's
identity, writes .kit.json, and runs the gate. The gate FAILS on purpose: every
{{FILL:...}} marker is a section the setup interview still owes. It does not
commit or create a remote; START_HERE.md does both once the gate passes.

ADOPTING
--------
Gives a project that predates the kit scripts/kit_sync.py and an empty
.kit.json, so its next close-session asks, file by file, which version wins.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
TEMPLATE = KIT / "template"
OWNED_LIST = KIT / "kit_owned.txt"
PROFILE = Path.home() / ".starter-kit" / "profile.json"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = ".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python"
VENV_PACKAGES = ("pytest", "pyyaml", "pypdf", "pypdfium2", "pillow")
# Stored under another name so git in the kit repo tracks it: the template's
# .gitignore would otherwise apply to the kit itself.
RENAMES = {"_gitignore": ".gitignore"}
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".py", ".txt", ".html", ""}
_KIT_MARKER = re.compile(r"\{\{KIT:([A-Z_]+)\}\}")
PROFILE_FIELDS = {
    "name": "the owner's name, as Claude should use it",
    "email": "the email for git commits (a GitHub noreply address is fine)",
    "git": "github | other | none — where the project's repository lives",
    "github_owner": "the GitHub account or organisation (git = github only)",
    "permissions": "broad (few permission prompts) | default (Claude Code's own)",
    "deliverables": "html | docx | md — how the owner reads what Claude writes for them",
    "talk": "one line: how the owner wants Claude to talk to them",
}

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# --- profile -------------------------------------------------------------------


def load_profile() -> dict:
    if not PROFILE.is_file():
        return {}
    return json.loads(PROFILE.read_text(encoding="utf-8-sig"))


def profile_problems(prof: dict) -> list[str]:
    problems = [f"{k}: missing ({why})" for k, why in PROFILE_FIELDS.items() if k != "github_owner" and not prof.get(k)]
    if prof.get("git") not in (None, "github", "other", "none"):
        problems.append("git: must be github, other or none")
    if prof.get("git") == "github" and not prof.get("github_owner"):
        problems.append(f"github_owner: missing ({PROFILE_FIELDS['github_owner']})")
    if prof.get("permissions") not in (None, "broad", "default"):
        problems.append("permissions: must be broad or default")
    if prof.get("deliverables") not in (None, "html", "docx", "md"):
        problems.append("deliverables: must be html, docx or md")
    return problems


def cmd_profile(args) -> int:
    prof = load_profile()
    changed = {k: getattr(args, k) for k in PROFILE_FIELDS if getattr(args, k, None)}
    if changed:
        prof.update(changed)
        prof["kit"] = KIT.as_posix()
        PROFILE.parent.mkdir(parents=True, exist_ok=True)
        PROFILE.write_text(json.dumps(prof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {PROFILE}")
    if not prof:
        print(f"NO PROFILE on this machine ({PROFILE}). Ask the owner for:")
        for k, why in PROFILE_FIELDS.items():
            print(f"  --{k.replace('_', '-')}: {why}")
        return 1
    for k in PROFILE_FIELDS:
        print(f"  {k:<13} {prof.get(k, '-')}")
    problems = profile_problems(prof)
    for p in problems:
        print(f"  MISSING  {p}")
    return 1 if problems else 0


# --- machine -------------------------------------------------------------------


def machine_facts(prof: dict) -> dict:
    exes = ["git", "pandoc", "pdftoppm"] + (["gh"] if prof.get("git") == "github" else []) + (["wt"] if IS_WINDOWS else [])
    found = {e: bool(shutil.which(e)) for e in exes}
    return {
        "os": f"{platform.system()} {platform.release()}",
        "shell": "PowerShell (the Bash tool is Git Bash)" if IS_WINDOWS else os.path.basename(os.environ.get("SHELL", "sh")),
        "python": f"{platform.python_version()} at {sys.executable}",
        "found": found,
    }


def platform_line(facts: dict) -> str:
    pdf = "the Read tool cannot open a PDF here (no poppler)" if not facts["found"].get("pdftoppm") else "the Read tool can open PDFs"
    return f"{facts['os']}, {facts['shell']}; {pdf}"


def platform_block(facts: dict, prof: dict, remote: str) -> str:
    found = facts["found"]
    have = ", ".join(e for e, ok in found.items() if ok) or "none"
    missing = ", ".join(e for e, ok in found.items() if not ok)
    build = (f"{Path(sys.executable).name} -m venv .venv; {VENV_PYTHON} -m pip install {' '.join(VENV_PACKAGES)}"
             if IS_WINDOWS else f"python3 -m venv .venv && {VENV_PYTHON} -m pip install {' '.join(VENV_PACKAGES)}")
    pdf_row = ("**The Read tool cannot open a PDF on this machine** (it needs poppler, which is not installed). "
               "Use `pypdf` from a short script writing text to the scratchpad, or the `anthropic-skills:pdf` skill."
               if not found.get("pdftoppm") else "Read directly, or `pypdf` for text extraction.")
    docx_row = "`pandoc -t markdown --wrap=none IN.docx -o OUT.md`" if found.get("pandoc") else "pandoc is not installed; install it, or `python-docx` in the venv"
    lines = [
        "## Platform",
        "",
        f"- **{facts['os']}**, shell: {facts['shell']}."
        + (" Bash-isms (`<<<`, `<<EOF` into stdin) fail in PowerShell; paths use backslashes in prose, forward slashes inside git calls." if IS_WINDOWS else ""),
        f"- **Python** {facts['python']}. Scripts and the gate run in the project venv: `<venv python>` is `{VENV_PYTHON}`.",
        f"- **Tools found at setup:** {have}." + (f" **Missing:** {missing}." if missing else ""),
        "",
        "## The venv",
        "",
        f"The gate, the tests and the desk-and-lane hooks run under `.venv` (gitignored, machine-local). **On a machine without it, every shell call shows a hook error and `/desk` stops at its first line.** Rebuild it from the project root:",
        "",
        "```",
        build,
        "```",
        "",
        f"Tests: `{VENV_PYTHON} -m pytest tests -q`.",
        "",
        "## Reading documents",
        "",
        "| Format | How |",
        "|---|---|",
        f"| `.docx` | {docx_row} |",
        f"| `.pdf` | {pdf_row} |",
        "| PDF checkboxes and scans | **Text extraction drops checkbox state.** Render the page with `pypdfium2`: `pdfium.PdfDocument(path)[i].render(scale=1.6).to_pil().save(png)`, then Read the PNG. A scan with no text layer needs OCR. |",
        "| `.png`, `.jpg`, `.csv`, `.md`, `.txt` | Read directly. |",
        "",
        "Reading copies go to the session scratchpad, never into the repo.",
        "",
        "## Git",
        "",
        f"- Repository on `main`; remote: {remote}. Identity is set per repo from the owner's Starter Kit profile.",
        "- Commit messages go through a file (`git commit -F <path>`). The full rules: `kb/git-discipline.md`.",
    ]
    return "\n".join(lines)


def deliverables_rule(prof: dict) -> str:
    owner, fmt = prof["name"], prof["deliverables"]
    if fmt == "md":
        return f"**Anything for {owner} to read or use.** Markdown is fine; say the path in the reply."
    kind = "`.html` or `.docx`" if fmt == "html" else "`.docx`"
    return f"**Anything for {owner} to read or use**, as {kind}. {owner} does not read `.md`; those are Claude's. Open the file after writing it."


# --- settings ------------------------------------------------------------------


def settings(prof: dict) -> tuple[dict, dict | None]:
    """(settings.json, settings.local.json or None) for this OS and permission choice."""
    shells = ("Bash", "PowerShell") if IS_WINDOWS else ("Bash",)
    venv_cmd = "${CLAUDE_PROJECT_DIR}/" + VENV_PYTHON

    def hook(script: str) -> dict:
        return {"type": "command", "command": venv_cmd, "args": ["${CLAUDE_PROJECT_DIR}/scripts/" + script], "timeout": 10}

    git_writes = [f"{s}(git {c})" for s in shells for c in ("add *", "commit *", "push origin main", "push origin HEAD*")]
    venv_runs = [f"{s}({p} *)" for s in shells for p in (VENV_PYTHON, "./" + VENV_PYTHON)]
    deny = [f"{s}({c})" for s in shells for c in ("git push --force*", "git push -f*", "git stash*")] + ["Bash(rm -rf /*)", "Bash(sudo rm:*)"]
    ask = [f"{s}(git {c}*)" for s in shells for c in ("reset", "clean", "checkout", "restore", "rebase", "merge", "branch -D")]
    if prof["permissions"] == "broad":
        allow = [*shells, "Read", "Glob", "Grep", "Edit", "Write", "NotebookEdit", "WebSearch", "WebFetch",
                 "Artifact", "SendMessage", "ListAgents", "Monitor", "Skill(loop)", "Skill(schedule)",
                 "Skill(schedule:*)", "Skill(update-config)", "Skill(artifact-design)", *venv_runs, *git_writes]
    else:
        # The desk talks to its lanes through these two; without them every
        # message is a prompt, and a desk waiting on a prompt looks like a desk thinking.
        allow = ["SendMessage", "ListAgents", *venv_runs, *git_writes]
    main = {
        "env": {"PYTHONUTF8": "1"},
        "permissions": {"allow": allow, "deny": deny, "ask": ask},
        "hooks": {
            "PermissionRequest": [{"matcher": "*", "hooks": [hook("note_prompt.py")]}],
            "PermissionDenied": [{"matcher": "*", "hooks": [hook("note_prompt.py")]}],
            "PreToolUse": [{"matcher": "|".join(shells), "hooks": [hook("lane_guard.py")]}],
        },
    }
    if prof["permissions"] != "broad":
        return main, None
    local = {"permissions": {
        "allow": [f"{s}(*)" for s in shells] + ["Read(*)", "Write(*)", "Edit(*)", "NotebookEdit(*)", "WebSearch", "WebFetch(*)", "Artifact", "Skill(update-config)", "Skill(loop)"],
        "deny": ["Bash(rm -rf /*)", "Bash(sudo rm:*)"],
        "additionalDirectories": [str(Path.home() / ".claude")],
    }}
    return main, local


# --- seeding -------------------------------------------------------------------


def owned() -> list[str]:
    return [ln.strip() for ln in OWNED_LIST.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def kit_origin() -> str:
    done = subprocess.run(["git", "-C", str(KIT), "remote", "get-url", "origin"], capture_output=True, text=True)
    return done.stdout.strip()


def kit_head() -> str:
    done = subprocess.run(["git", "-C", str(KIT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return done.stdout.strip() or "uncommitted"


def run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def import_sync_module(target: Path):
    spec = importlib.util.spec_from_file_location("kit_sync", target / "scripts" / "kit_sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmd_seed(args) -> int:
    prof = load_profile()
    problems = profile_problems(prof)
    if problems:
        print("FAIL - the owner's profile is incomplete; run `new_project.py profile` first:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    name = args.name
    target = Path(args.parent or KIT.parent) / name
    if target.exists() and any(target.iterdir()):
        print(f"FAIL - {target} exists and is not empty. Pick another name, or adopt it.", file=sys.stderr)
        return 1
    repo = args.repo or re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-")
    if prof["git"] == "github":
        remote = f"`https://github.com/{prof['github_owner']}/{repo}.git` (private)"
    elif prof["git"] == "other":
        remote = f"`{args.remote}`" if args.remote else "the URL the owner gives at setup"
    else:
        remote = "none — this repository is local only"
    facts = machine_facts(prof)
    values = {
        "PROJECT": name,
        "PROJECT_UPPER": name.upper(),
        "DATE": dt.date.today().isoformat(),
        "OWNER": prof["name"],
        "TALK": prof["talk"],
        "DELIVERABLES": deliverables_rule(prof),
        "PLATFORM": platform_line(facts),
        "PLATFORM_BLOCK": platform_block(facts, prof, remote),
        "VENV_PYTHON": VENV_PYTHON,
    }

    for src in sorted(TEMPLATE.rglob("*")):
        if not src.is_file() or "__pycache__" in src.parts or ".pytest_cache" in src.parts:
            continue
        rel = src.relative_to(TEMPLATE)
        dest = target / rel.parent / RENAMES.get(rel.name, rel.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in TEXT_SUFFIXES:
            text = src.read_text(encoding="utf-8")
            unknown = {m for m in _KIT_MARKER.findall(text) if m not in values}
            if unknown:
                print(f"FAIL - {rel} uses unknown kit marker(s) {sorted(unknown)}; the kit is broken, fix the template.", file=sys.stderr)
                return 1
            dest.write_text(_KIT_MARKER.sub(lambda m: values[m.group(1)], text), encoding="utf-8", newline="")
        else:
            shutil.copyfile(src, dest)
    (target / "Working").mkdir(exist_ok=True)

    main_settings, local_settings = settings(prof)
    (target / ".claude").mkdir(exist_ok=True)
    (target / ".claude" / "settings.json").write_text(json.dumps(main_settings, indent=2) + "\n", encoding="utf-8")
    if local_settings:
        (target / ".claude" / "settings.local.json").write_text(json.dumps(local_settings, indent=2) + "\n", encoding="utf-8")

    for argv in (["init", "-b", "main"], ["config", "user.name", prof["name"]], ["config", "user.email", prof["email"]]):
        run(["git", *argv], target).check_returncode()
    if IS_WINDOWS:
        run(["git", "config", "core.autocrlf", "true"], target)

    sync = import_sync_module(target)
    record = {
        "kit_url": kit_origin(),
        "kit_commit": kit_head(),
        "seeded": values["DATE"],
        "files": {rel: {"project": sync.digest(target / rel), "kit": sync.digest(TEMPLATE / rel)} for rel in owned()},
    }
    (target / ".kit.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    print(f"seeded {target} from the Starter Kit (kit {record['kit_commit']})")
    print(f"machine: {platform_line(facts)}")
    missing = [e for e, ok in facts["found"].items() if not ok]
    if missing:
        print(f"  missing tools: {', '.join(missing)}")
    print(f"remote: {remote}")

    venv_ok = True
    if args.no_venv:
        print("venv: SKIPPED (--no-venv). The hooks in .claude/settings.json fail on every shell call until it exists.")
        venv_ok = False
    else:
        steps = [[sys.executable, "-m", "venv", ".venv"], [VENV_PYTHON, "-m", "pip", "install", "-q", *VENV_PACKAGES]]
        for step in steps:
            done = run([str(target / step[0]) if step[0] == VENV_PYTHON else step[0], *step[1:]], target)
            if done.returncode != 0:
                print(f"venv: FAILED at `{' '.join(step)}`:\n{(done.stderr or done.stdout).strip()[-1500:]}", file=sys.stderr)
                venv_ok = False
                break
        if venv_ok:
            tests = run([str(target / VENV_PYTHON), "-m", "pytest", "tests", "-q"], target)
            summary = (tests.stdout.strip().splitlines() or ["(no output)"])[-1]
            print(f"venv: built; tests: {summary}")
            venv_ok = tests.returncode == 0

    gate_python = str(target / VENV_PYTHON) if venv_ok or (target / VENV_PYTHON).exists() else sys.executable
    print("--- gate (the SETUP lines are the interview's to-do) ---")
    gate = run([gate_python, "scripts/check_docs.py", "--write-kb"], target)
    print(gate.stdout.rstrip())
    print(gate.stderr.rstrip())
    if not venv_ok:
        print("FAIL - the venv or its tests did not pass; fix that before filling the markers.", file=sys.stderr)
        return 1
    return 0


def cmd_adopt(args) -> int:
    target = Path(args.path).resolve()
    if not (target / ".git").is_dir():
        print(f"FAIL - {target} is not a git repository.", file=sys.stderr)
        return 1
    if (target / ".kit.json").exists():
        print(f"FAIL - {target} already has a .kit.json; run its scripts/kit_sync.py status.", file=sys.stderr)
        return 1
    script = target / "scripts" / "kit_sync.py"
    script.parent.mkdir(exist_ok=True)
    if not script.exists():
        shutil.copyfile(TEMPLATE / "scripts" / "kit_sync.py", script)
    record = {"kit_url": kit_origin(), "kit_commit": kit_head(), "adopted": dt.date.today().isoformat(), "files": {}}
    (target / ".kit.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"adopted {target}: wrote .kit.json and scripts/kit_sync.py. Every differing kit-owned file is now UNDECIDED:")
    return subprocess.run([sys.executable, "scripts/kit_sync.py", "status"], cwd=target).returncode


def main(argv: list[str]) -> int:
    if argv and argv[0] not in ("profile", "adopt", "seed", "-h", "--help"):
        argv = ["seed", *argv]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("profile", help="show or set the owner's profile on this machine")
    p.add_argument("--show", action="store_true")
    for k, why in PROFILE_FIELDS.items():
        p.add_argument("--" + k.replace("_", "-"), dest=k, help=why)
    p.set_defaults(run=cmd_profile)
    s = sub.add_parser("seed", help="seed a new project")
    s.add_argument("name")
    s.add_argument("--repo", help="repository name (default: the name, lowercased)")
    s.add_argument("--parent", help="where the project folder goes (default: beside the kit)")
    s.add_argument("--remote", help="the remote URL when the profile's git is `other`")
    s.add_argument("--no-venv", action="store_true", help="skip building .venv (the hooks will fail until it exists)")
    s.set_defaults(run=cmd_seed)
    a = sub.add_parser("adopt", help="bring an existing project under kit sync")
    a.add_argument("path")
    a.set_defaults(run=cmd_adopt)
    args = parser.parse_args(argv)
    if sys.version_info < (3, 9):
        print("FAIL - the Starter Kit needs Python 3.9 or newer.", file=sys.stderr)
        return 1
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
