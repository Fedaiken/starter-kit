#!/usr/bin/env python
"""Extract a .pdf to UTF-8 markdown, with a page marker for every page.

It exists because **the Read tool cannot open a PDF on this machine**: Read
renders pages with `pdftoppm`, poppler is not installed, and
`kb/platform-and-tools.md` records that. `pypdf` is already in the project venv,
so this reads the PDF's text layer instead and adds nothing to install.

    .venv/Scripts/python.exe scripts/extract_pdf.py INPUT.pdf -o OUTPUT.md
    .venv/Scripts/python.exe scripts/extract_pdf.py INPUT.pdf -o OUTPUT.md --pages 90-98
    .venv/Scripts/python.exe scripts/extract_pdf.py INPUT.pdf --toc          # structure only
    .venv/Scripts/python.exe scripts/extract_pdf.py INPUT.pdf                # INPUT.md beside it

PAGE MARKERS ARE THE POINT. Every page is fenced with `<!-- page N -->`, so a
claim taken from the text can be cited back to a page number and a partial read
says which part it read. A long PDF summarised without page anchors is
unverifiable prose about a document nobody can re-find.

WITHOUT `-o` THE COPY GOES BESIDE THE PDF, AND ONLY FOR A PDF INSIDE THIS
PROJECT. A PDF anywhere else -- the game's install folder above all, which
`CLAUDE.md` makes read-only -- needs `-o`, so the default cannot write a file
into a place this project must not touch.

WHAT IT CANNOT READ. Only the text layer. A scanned page has none: it comes out
as `_(no extractable text)_`, the run says how many pages did, and they need OCR.
Form checkboxes are not text either; `kb/platform-and-tools.md` has the render
recipe for those. Some fonts need `fontTools` to decode (not in the venv, and not
added): pypdf then warns on stderr, and that text may come out wrong -- check it
against the rendered page.

The file is written as UTF-8 with `\\n` line ends whatever the machine's
defaults are, and stdout and stderr are switched to UTF-8 too: the console here
is cp1252, and `--toc` prints page text, which would otherwise die on the first
character cp1252 has no code for.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

try:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
except ImportError:  # pragma: no cover - environment guard
    sys.exit("pypdf is not installed. Rebuild the venv: see kb/platform-and-tools.md")

#: The folder holding `scripts/`. A default output is allowed only beneath it.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

EMPTY_PAGE = "_(no extractable text)_"


def parse_pages(spec: str | None, total: int) -> list[int]:
    """`"5"`, `"5-12"`, `"5-12,90-98"` -> zero-based page indices, in the order
    asked for. No spec is every page."""
    if not spec:
        return list(range(total))
    wanted: list[int] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                first, last = (part.strip() for part in chunk.split("-", 1))
                start, end = int(first), int(last)
            else:
                start = end = int(chunk)
        except ValueError:
            sys.exit(f"Page range {chunk!r} is not a number or a first-last pair.")
        if start < 1 or end > total or start > end:
            sys.exit(f"Page range {chunk!r} is outside 1-{total}.")
        wanted.extend(range(start - 1, end))
    return wanted


def page_text(reader: PdfReader, index: int) -> str:
    return (reader.pages[index].extract_text() or "").strip()


def extract(path: Path, spec: str | None) -> tuple[str, dict[str, int]]:
    """The markdown for `path` (the pages `spec` names, or all) and its counts."""
    reader = PdfReader(str(path))
    total = len(reader.pages)
    indices = parse_pages(spec, total)

    scope = f"pages {spec}" if spec else f"all {total} pages"
    body = [
        f"# {path.name}",
        "",
        (f"> Extracted by `scripts/extract_pdf.py` ({scope} of {total}). "
         f"Original preserved; this is a reading copy. Page markers are the "
         f"citation anchors -- quote them."),
        "",
    ]

    empty = words = 0
    for index in indices:
        text = page_text(reader, index)
        if text:
            words += len(text.split())
        else:
            empty += 1
        body.extend([f"<!-- page {index + 1} -->", "", text or EMPTY_PAGE, ""])

    stats = {"total_pages": total, "read": len(indices), "empty": empty, "words": words}
    return "\n".join(body) + "\n", stats


def print_toc(path: Path, spec: str | None) -> None:
    """First non-empty line of each page: a cheap map of a long document."""
    reader = PdfReader(str(path))
    print(f"{path.name}: {len(reader.pages)} pages")
    for index in parse_pages(spec, len(reader.pages)):
        text = page_text(reader, index)
        head = next((line.strip() for line in text.splitlines() if line.strip()), "")
        print(f"  p{index + 1:>3}  {head[:78]}")


def default_output(path: Path, root: Path | None = None) -> Path:
    """`path` with `.md`, beside it -- or a refusal, if `path` is outside `root`
    (the project, unless a test names another)."""
    root = PROJECT_ROOT if root is None else root
    if not path.resolve().is_relative_to(root.resolve()):
        sys.exit(f"{path} is outside this project, so no copy is written beside it. "
                 f"Name one with -o (the session scratchpad, or Working/).")
    return path.with_suffix(".md")


def build_parser() -> argparse.ArgumentParser:
    """The CLI surface, built apart from `main` so a test can hold the usage
    lines in this docstring and in the kb to it."""
    parser = argparse.ArgumentParser(description="Extract a .pdf to markdown.")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path,
                        help="where to write; default INPUT.md beside the PDF, "
                             "for a PDF inside this project only")
    parser.add_argument("--pages", help='e.g. "5", "5-12", "1-4,90-98"')
    parser.add_argument("--toc", action="store_true",
                        help="print each page's first line and exit; writes nothing")
    return parser


def main(argv: Sequence[str] = ()) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    args = build_parser().parse_args(argv)
    if not args.input.exists():
        sys.exit(f"No such file: {args.input}")

    try:
        if args.toc:
            print_toc(args.input, args.pages)
            return 0
        output = args.output or default_output(args.input)
        if output.resolve() == args.input.resolve():
            sys.exit(f"Refusing to write over the PDF itself: {output}")
        text, stats = extract(args.input, args.pages)
    except PyPdfError as err:
        # Not a PDF, damaged, or password-protected: pypdf raises on the first
        # page read, not on open. One line naming the file, not a traceback.
        sys.exit(f"{args.input} could not be read as a PDF: {err}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")

    print(f"wrote {output}")
    print(f"  pages={stats['read']} of {stats['total_pages']} "
          f"empty={stats['empty']} words={stats['words']}")
    if stats["empty"]:
        print(f"  NOTE: {stats['empty']} page(s) yielded no text -- scanned images "
              f"or pure layout. Their content is NOT in this copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
