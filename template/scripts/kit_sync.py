#!/usr/bin/env python
"""Keep this project's kit-owned files and the Starter Kit in step.

    <venv python> scripts/kit_sync.py status          # every kit-owned file; exit 1 on any UNDECIDED
    <venv python> scripts/kit_sync.py push <path>     # project -> kit, commit in the kit, push the kit
    <venv python> scripts/kit_sync.py push --new <path>  # a project file the kit does not own yet: same, and kit_owned.txt gains it
    <venv python> scripts/kit_sync.py pull <path>     # kit -> project
    <venv python> scripts/kit_sync.py keep <path>     # this difference is local; stop asking
    <venv python> scripts/kit_sync.py commit <kit paths> -F <msg>  # hand edits to the kit's seeder or seeded files
    add --merged to push/pull when BOTH sides changed and you merged them by hand

WHY THIS EXISTS
---------------
The Starter Kit seeds every new project.
A kit copied once is stale by the next project: the gate, the method kb
entries and the command wrappers improve inside whichever project is busy, and
that improvement never reaches the kit unless someone remembers to carry it.
"Remember to carry it" is the fix the Cardinal Rule forbids. So close-session
runs `status`, which exits 1 while any kit-owned file has moved on either side
without a decision, and each one gets exactly one of push, pull or keep.

HOW IT DECIDES
--------------
`.kit.json` records, per kit-owned file, the hash of the project's copy and of
the kit's copy (`template/<path>`) as of the last decision. Hashes are taken
with line endings normalised to LF, so an autocrlf checkout is not a change.
Now vs. record:

    project == kit                      in sync      (the record is refreshed)
    (project, kit) == record            kept local   (decided earlier)
    anything else                       UNDECIDED    (says which side moved)

The kit-owned list is the kit's `kit_owned.txt`, read live, so a file the kit
starts owning later shows up here as `new in kit`. This file is itself
kit-owned (`kb/starter-kit-and-kit-sync.md`).

WHAT A PUSH CHECKS
------------------
The kit is public, and its rules require `scripts/check_private.py` to print
OK before every commit. A rule a person must remember is skipped on the day it
matters, so every push runs the kit's check itself, after the copy and before
the commit. Not OK, or no check in the kit, and the kit is put back as it was:
nothing is copied, listed or committed. `--new` lists a file the kit does not
own yet; it refuses a path the kit already seeds, because turning a seeded
file into a kit-owned one overwrites every project's own copy, and that is a
change to make in a session opened in the kit. `commit` is that change's
save, and the same check gates it: it commits only the kit paths it is named,
from a message file, and refuses a kit-owned template file, which travels by
`push` so the project's record of it stays true.

WHERE THE KIT IS
----------------
Never stored in the project: the project and the kit each live wherever a
given machine put them. Looked up in order: the STARTER_KIT environment
variable, then `kit` in ~/.starter-kit/profile.json (written by the kit's
new_project.py). `.kit.json` keeps only the kit's URL, so a machine without a
copy can be told what to clone.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / ".kit.json"
OWNED_LIST = "kit_owned.txt"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()[:16]


def load_record() -> dict:
    if not RECORD.is_file():
        raise SystemExit(f"FAIL - no {RECORD.name} here; this project was not seeded from the Starter Kit. Adopt it: python <kit>/scripts/new_project.py --adopt {ROOT}")
    return json.loads(RECORD.read_text(encoding="utf-8-sig"))  # -sig: PowerShell's utf8 writes a BOM


def save_record(rec: dict) -> None:
    RECORD.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


PROFILE = Path.home() / ".starter-kit" / "profile.json"


def kit_root(rec: dict) -> Path:
    where, kit = "", None
    if os.environ.get("STARTER_KIT"):
        where, kit = "STARTER_KIT", Path(os.environ["STARTER_KIT"])
    elif PROFILE.is_file():
        found = json.loads(PROFILE.read_text(encoding="utf-8-sig")).get("kit")
        if found:
            where, kit = str(PROFILE), Path(found)
    if kit is None or not (kit / OWNED_LIST).is_file():
        url = rec.get("kit_url") or "the Starter Kit's repository"
        said = f"{where} points at {kit}, which has no {OWNED_LIST}" if kit else "no copy of the Starter Kit is known on this machine"
        raise SystemExit(f"FAIL - {said}. Clone {url} and run its START_HERE.md profile step once (`<python> scripts/new_project.py profile --show`), or set STARTER_KIT to the clone. Nothing was checked; this is not a pass.")
    return kit


def owned(kit: Path, rec: dict) -> list[str]:
    listed = [ln.strip() for ln in (kit / OWNED_LIST).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return sorted(set(listed) | set(rec.get("files", {})))


def classify(rel: str, kit: Path, rec: dict) -> tuple[str, str, str | None, str | None]:
    """(verdict, reason, project hash, kit hash)."""
    p, k = digest(ROOT / rel), digest(kit / "template" / rel)
    if p is None and k is None:
        return "gone", "absent on both sides", p, k
    if p == k:
        return "in sync", "", p, k
    prior = rec.get("files", {}).get(rel)
    if prior and prior.get("project") == p and prior.get("kit") == k:
        return "kept local", "", p, k
    if not prior:
        reason = "new in kit" if p is None else "not in the kit any more" if k is None else "differs, never decided"
    else:
        moved = [side for side, now in (("project", p), ("kit", k)) if prior.get(side) != now]
        reason = " and ".join(moved) + " changed" if moved else "differs"
    return "UNDECIDED", reason, p, k


def status(args) -> int:
    rec = load_record()
    kit = kit_root(rec)
    undecided = 0
    refreshed = False
    for rel in owned(kit, rec):
        verdict, reason, p, k = classify(rel, kit, rec)
        if verdict == "in sync" and rec.get("files", {}).get(rel) != {"project": p, "kit": k}:
            rec.setdefault("files", {})[rel] = {"project": p, "kit": k}
            refreshed = True
        if verdict == "UNDECIDED":
            undecided += 1
        print(f"  {verdict:<10}  {rel}" + (f"  ({reason})" if reason else ""))
    if refreshed:
        save_record(rec)
    if undecided:
        print(f"FAIL - {undecided} kit-owned file(s) UNDECIDED. Each takes one of: push (every project should get it), pull (take the kit's), keep (local on purpose).", file=sys.stderr)
        return 1
    print(f"OK - every kit-owned file is in sync with {kit} or kept local on purpose.")
    return 0


def _git_kit(kit: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(kit), *argv], capture_output=True, text=True, encoding="utf-8")


PRIVACY_CHECK = "scripts/check_private.py"


def listed_with(text: str, rel: str) -> str:
    """kit_owned.txt's text with rel added after the last path in its top folder, else at the end."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    top = rel.split("/")[0] if "/" in rel else None
    at = None
    for i, ln in enumerate(lines):
        entry = ln.strip()
        if top and entry and not entry.startswith("#") and "/" in entry and entry.split("/")[0] == top:
            at = i
    if at is None:
        lines.append(rel)
    else:
        lines.insert(at + 1, rel)
    return nl.join(lines) + nl


def new_problem(rel: str, kit: Path, rec: dict) -> str | None:
    """Why `push --new rel` must refuse, or None."""
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        return f"{rel} is not a path inside this project."
    if rel in owned(kit, rec):
        return f"{rel} is already kit-owned; push it without --new."
    if not (ROOT / rel).is_file():
        return f"{rel} does not exist in this project; nothing to push."
    if (kit / "template" / rel).exists():
        return (f"the kit already seeds template/{rel}. Making a seeded file kit-owned overwrites every project's own copy; "
                "do that in a session opened in the kit.")
    return None


def push_into_kit(rel: str, kit: Path, new: bool) -> int:
    """Copy rel into the kit, list it when new, run the kit's privacy check, commit, push.

    The check runs on the kit as it would be committed. Anything short of OK puts
    every touched file back, so a refused push leaves the kit as it was found.
    """
    src_proj, src_kit, listing = ROOT / rel, kit / "template" / rel, kit / OWNED_LIST
    touched = [src_kit, listing] if new else [src_kit]
    before = {path: path.read_bytes() if path.is_file() else None for path in touched}
    made = [d for d in [src_kit.parent, *src_kit.parent.parents] if d != kit and kit in d.parents and not d.exists()]
    paths_in_kit = [f"template/{rel}"] + ([OWNED_LIST] if new else [])

    def put_back(why: str) -> int:
        _git_kit(kit, "reset", "-q", "--", *paths_in_kit)
        for path, data in before.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        for d in made:  # deepest first: made lists src_kit.parent before its parents
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        print(f"FAIL - {why}\n  Nothing was committed; the kit is as it was.", file=sys.stderr)
        return 1

    src_kit.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_proj, src_kit)
    if new:
        listing.write_bytes(listed_with(before[listing].decode("utf-8"), rel).encode("utf-8"))
    refused = privacy_refusal(kit)
    if refused:
        return put_back(refused)
    message = f"From {ROOT.name}: {rel}" + (" (new kit-owned file)" if new else "")
    for step in (("add", "--", *paths_in_kit), ("commit", "-m", message, "--", *paths_in_kit)):
        done = _git_kit(kit, *step)
        if done.returncode != 0:
            return put_back(f"kit git {step[0]}: {(done.stderr or done.stdout).strip()}")
    head = _git_kit(kit, "rev-parse", "--short", "HEAD").stdout.strip()
    print(f"pushed {rel} into the kit{' as a new kit-owned file' if new else ''} (kit commit {head})")
    send_kit(kit)
    return 0


def privacy_refusal(kit: Path) -> str | None:
    """Run the kit's privacy check; None when it prints OK, else why the commit must not happen."""
    check = kit / PRIVACY_CHECK
    if not check.is_file():
        return f"the kit has no {PRIVACY_CHECK}, and its rules allow no commit without it."
    verdict = subprocess.run([sys.executable, str(check)], cwd=str(kit), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if verdict.returncode != 0:
        return f"the kit's privacy check refused this commit:\n{(verdict.stderr + verdict.stdout).strip()}"
    print(verdict.stdout.strip())
    return None


def send_kit(kit: Path) -> bool:
    """Push the kit's HEAD to its origin; False only when a push was tried and failed."""
    if not _git_kit(kit, "remote").stdout.strip():
        return True
    sent = _git_kit(kit, "push", "origin", "HEAD")
    if sent.returncode == 0:
        print("kit pushed to origin")
        return True
    print(f"KIT PUSH FAILED - {(sent.stderr or sent.stdout).strip()}\n  The commit is in this machine's copy of the kit. If the kit is someone else's, offer it to them as a pull request; say so either way.")
    return False


def commit(args) -> int:
    """Commit hand edits to the kit's own files (its seeder, a seeded template file), then push.

    Kit-owned template files refuse: they travel by `push`, so the project's
    record of them stays true. Only the named paths are staged and committed.
    """
    rec = load_record()
    kit = kit_root(rec)
    listed = set(owned(kit, rec))
    message = Path(args.message_file)
    if not message.is_file() or not message.read_text(encoding="utf-8-sig").strip():
        print(f"FAIL - the message file {message} is missing or empty.", file=sys.stderr)
        return 1
    paths = [Path(p).as_posix() for p in args.paths]
    for rel in paths:
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            print(f"FAIL - {rel} is not a path inside the kit; give it relative to {kit}.", file=sys.stderr)
            return 1
        if rel.startswith("template/") and rel[len("template/"):] in listed:
            print(f"FAIL - {rel} is kit-owned; it goes by `push {rel[len('template/'):]}` from a project, never a hand commit.", file=sys.stderr)
            return 1
        if not (kit / rel).exists() and _git_kit(kit, "ls-files", "--error-unmatch", "--", rel).returncode != 0:
            print(f"FAIL - {rel} is neither in the kit nor tracked by it.", file=sys.stderr)
            return 1
    refused = privacy_refusal(kit)
    if refused:
        print(f"FAIL - {refused}\n  Nothing was committed.", file=sys.stderr)
        return 1
    for step in (("add", "--", *paths), ("commit", "-F", str(message.resolve()), "--", *paths)):
        done = _git_kit(kit, *step)
        if done.returncode != 0:
            _git_kit(kit, "reset", "-q", "--", *paths)
            print(f"FAIL - kit git {step[0]}: {(done.stderr or done.stdout).strip()}\n  Nothing was committed.", file=sys.stderr)
            return 1
    head = _git_kit(kit, "rev-parse", "--short", "HEAD").stdout.strip()
    print(f"committed {', '.join(paths)} in the kit (kit commit {head})")
    return 0 if send_kit(kit) else 1


def act(args) -> int:
    rec = load_record()
    kit = kit_root(rec)
    rel = Path(args.path).as_posix()
    new = getattr(args, "new", False)
    if new:
        problem = new_problem(rel, kit, rec)
        if problem:
            print(f"FAIL - {problem}", file=sys.stderr)
            return 1
    elif rel not in owned(kit, rec):
        print(f"FAIL - {rel} is not kit-owned (see {kit / OWNED_LIST}). If every project should get it: push --new {rel}", file=sys.stderr)
        return 1
    verdict, reason, p, k = classify(rel, kit, rec)
    prior = rec.get("files", {}).get(rel) or {}
    both = prior and prior.get("project") != p and prior.get("kit") != k
    if args.action in ("push", "pull") and both and not args.merged:
        print(f"FAIL - {rel}: both sides changed since the last decision. Merge the two by hand into the side you are keeping, then re-run with --merged.", file=sys.stderr)
        return 1
    src_proj, src_kit = ROOT / rel, kit / "template" / rel
    if args.action == "push":
        if p is None:
            print(f"FAIL - {rel} does not exist in this project; nothing to push.", file=sys.stderr)
            return 1
        if push_into_kit(rel, kit, new) != 0:
            return 1
    elif args.action == "pull":
        if k is None:
            print(f"FAIL - the kit no longer has {rel}; `keep` it or delete it here.", file=sys.stderr)
            return 1
        src_proj.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_kit, src_proj)
        print(f"pulled {rel} from the kit; stage it with this run's paths")
    else:
        print(f"kept {rel} local ({reason or verdict})")
    rec.setdefault("files", {})[rel] = {"project": digest(src_proj), "kit": digest(src_kit)}
    rec["last_decision"] = dt.date.today().isoformat()
    save_record(rec)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status").set_defaults(run=status)
    for name in ("push", "pull", "keep"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--merged", action="store_true")
        if name == "push":
            p.add_argument("--new", action="store_true", help="the kit does not own this file yet: list it in kit_owned.txt too")
        p.set_defaults(run=act)
    c = sub.add_parser("commit", help="commit hand edits to the kit's own (not kit-owned) files, then push the kit")
    c.add_argument("paths", nargs="+", help="paths relative to the kit's root")
    c.add_argument("-F", dest="message_file", required=True, help="the commit message, from a file")
    c.set_defaults(run=commit)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
