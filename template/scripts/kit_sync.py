#!/usr/bin/env python
"""Keep this project's kit-owned files and the Starter Kit in step.

    python scripts/kit_sync.py status          # every kit-owned file; exit 1 on any UNDECIDED
    python scripts/kit_sync.py push <path>     # project -> kit, commit in the kit, push the kit
    python scripts/kit_sync.py pull <path>     # kit -> project
    python scripts/kit_sync.py keep <path>     # this difference is local; stop asking
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
        raise SystemExit(f"FAIL - {said}. Clone {url} and run its `python scripts/new_project.py profile --show` once (or set STARTER_KIT to the clone). Nothing was checked; this is not a pass.")
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


def act(args) -> int:
    rec = load_record()
    kit = kit_root(rec)
    rel = Path(args.path).as_posix()
    if rel not in owned(kit, rec):
        print(f"FAIL - {rel} is not kit-owned (see {kit / OWNED_LIST}).", file=sys.stderr)
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
        src_kit.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_proj, src_kit)
        path_in_kit = f"template/{rel}"
        steps = [("add", "--", path_in_kit), ("commit", "-m", f"From {ROOT.name}: {rel}", "--", path_in_kit)]
        for step in steps:
            done = _git_kit(kit, *step)
            if done.returncode != 0:
                print(f"FAIL - kit git {step[0]}: {(done.stderr or done.stdout).strip()}", file=sys.stderr)
                return 1
        head = _git_kit(kit, "rev-parse", "--short", "HEAD").stdout.strip()
        print(f"pushed {rel} into the kit (kit commit {head})")
        if _git_kit(kit, "remote").stdout.strip():
            sent = _git_kit(kit, "push", "origin", "HEAD")
            if sent.returncode == 0:
                print("kit pushed to origin")
            else:
                print(f"KIT PUSH FAILED - {sent.stderr.strip()}\n  The commit is in this machine's copy of the kit. If the kit is someone else's, offer it to them as a pull request; say so either way.")
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
        p.set_defaults(run=act)
    args = parser.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
