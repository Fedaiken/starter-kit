#!/usr/bin/env python
"""Refuse a kit commit that carries the owner's personal details.

    python scripts/check_private.py            # exit 1 on any hit

The kit is public and shared, so nothing personal may enter it — but the kit
cannot list what "personal" is without publishing it. This reads the details
from the owner's own profile (~/.starter-kit/profile.json, outside the kit) at
check time: name, email, GitHub account, and home folder. It scans every file
git would commit (tracked or untracked, not ignored) and the identity git
would stamp on the commit. Run it before every commit to the kit.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
PROFILE = Path.home() / ".starter-kit" / "profile.json"
SELF = Path(__file__).resolve()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(KIT), *args], capture_output=True, text=True, encoding="utf-8").stdout


def main() -> int:
    if not PROFILE.is_file():
        print(f"FAIL - no profile at {PROFILE}; nothing to check against. This is not a pass.", file=sys.stderr)
        return 2
    prof = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    needles = {
        "name": prof.get("name"),
        "email": prof.get("email"),
        "GitHub account": prof.get("github_owner"),
        "home folder": str(Path.home()),
        "home folder (posix)": Path.home().as_posix(),
    }
    patterns = {label: re.compile(rf"(?<![\w]){re.escape(v)}(?![\w])", re.I) for label, v in needles.items() if v}
    hits: list[str] = []
    for rel in git("ls-files", "--cached", "--others", "--exclude-standard").splitlines():
        path = KIT / rel
        if not path.is_file() or path.resolve() == SELF:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            for label, pat in patterns.items():
                if pat.search(line):
                    hits.append(f"{rel}:{n}: the owner's {label}")
    email = git("config", "user.email").strip()
    if prof.get("email") and email.lower() == prof["email"].lower():
        hits.append("git config user.email: commits would carry the owner's email; use a GitHub noreply address in this repo")
    if hits:
        print(f"FAIL - {len(hits)} personal detail(s) would be published:", file=sys.stderr)
        for h in hits:
            print(f"  {h}", file=sys.stderr)
        return 1
    print("OK - nothing from the owner's profile appears in the kit or its commit identity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
