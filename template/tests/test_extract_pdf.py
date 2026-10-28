"""Tests for scripts/extract_pdf.py -- a PDF in, UTF-8 markdown out, one page
marker per page, because the Read tool cannot open a PDF on this machine.

Every PDF here is built in a temp folder from bytes (`build_pdf`), so a test
states exactly what is on each page and the expected text is written out whole.
The two that ask a real subprocess are the ones about the console: what has to be
true is what a cp1252 pipe is handed, and only a separate process can show it.
"""
import io
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import extract_pdf
from extract_pdf import EMPTY_PAGE, build_parser, main, parse_pages

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "extract_pdf.py"

#: Three pages; the middle one has a single line, so a page's text is told apart
#: from its neighbour's by more than a count.
THREE = [["Alpha one", "Alpha two"], ["Bravo"], ["Charlie"]]


def build_pdf(pages, *, arrow=False):
    """A PDF whose page i shows the lines in `pages[i]`; an empty list is a page
    with no text on it. With `arrow`, the character code 65 ("A") is bound to the
    glyph `arrowright`, so the text layer holds U+2192, which cp1252 has no code
    for -- the smallest PDF that reaches a cp1252 console with something it
    cannot print."""
    count = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    encoding = (" /Encoding << /Type /Encoding /Differences [65 /arrowright] >>"
                if arrow else "")
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        3: f"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica{encoding} >>".encode(),
    }
    for i, lines in enumerate(pages):
        page, contents = 4 + 2 * i, 5 + 2 * i
        objects[page] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {contents} 0 R >>"
        ).encode()
        shown = "".join(
            "(%s) Tj 0 -16 Td " % line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            for line in lines)
        stream = f"BT /F1 12 Tf 72 720 Td {shown}ET".encode("latin-1") if lines else b""
        objects[contents] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n" % number + objects[number] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for number in sorted(objects):
        out += b"%010d 00000 n \n" % offsets[number]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref)
    return bytes(out)


def write_pdf(folder, pages, name="doc.pdf", **kwargs):
    path = folder / name
    path.write_bytes(build_pdf(pages, **kwargs))
    return path


def pages_of(markdown):
    """`{page number: that page's text}` read back from a marked-up copy."""
    parts = re.split(r"<!-- page (\d+) -->", markdown)
    return {int(n): text.strip() for n, text in zip(parts[1::2], parts[2::2])}


def run(*argv):
    return main([str(a) for a in argv])


# --- the text and the markers, which are the whole point --------------------


def test_every_page_comes_out_under_its_own_marker(tmp_path):
    pdf = write_pdf(tmp_path, THREE)
    out = tmp_path / "out.md"
    assert run(pdf, "-o", out) == 0
    assert pages_of(out.read_text(encoding="utf-8")) == {
        1: "Alpha one\nAlpha two", 2: "Bravo", 3: "Charlie"}


def test_the_markers_run_in_page_order_and_the_title_names_the_file(tmp_path):
    pdf = write_pdf(tmp_path, THREE, name="Some Manual.pdf")
    out = tmp_path / "out.md"
    run(pdf, "-o", out)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Some Manual.pdf\n")
    assert re.findall(r"<!-- page (\d+) -->", text) == ["1", "2", "3"]
    assert "all 3 pages of 3" in text


def test_a_page_range_reads_only_those_pages_and_says_so(tmp_path):
    pdf = write_pdf(tmp_path, THREE)
    out = tmp_path / "out.md"
    run(pdf, "-o", out, "--pages", "3,1")
    text = out.read_text(encoding="utf-8")
    assert pages_of(text) == {3: "Charlie", 1: "Alpha one\nAlpha two"}
    assert re.findall(r"<!-- page (\d+) -->", text) == ["3", "1"], "asked-for order"
    assert "pages 3,1 of 3" in text


def test_the_summary_counts_the_pages_and_the_words(tmp_path, capsys):
    run(write_pdf(tmp_path, THREE), "-o", tmp_path / "out.md")
    assert capsys.readouterr().out == (
        f"wrote {tmp_path / 'out.md'}\n  pages=3 of 3 empty=0 words=6\n")


def test_a_page_with_no_text_is_marked_and_counted_not_dropped(tmp_path, capsys):
    pdf = write_pdf(tmp_path, [["Alpha"], [], ["Charlie"]])
    out = tmp_path / "out.md"
    run(pdf, "-o", out)
    assert pages_of(out.read_text(encoding="utf-8")) == {
        1: "Alpha", 2: EMPTY_PAGE, 3: "Charlie"}
    printed = capsys.readouterr().out
    assert "empty=1" in printed
    assert "NOTE: 1 page(s) yielded no text" in printed


def test_parentheses_and_backslashes_in_the_text_come_back_whole(tmp_path):
    line = r"cost (base) \ 5)"
    out = tmp_path / "out.md"
    run(write_pdf(tmp_path, [[line]]), "-o", out)
    assert pages_of(out.read_text(encoding="utf-8")) == {1: line}


# --- the page spec ------------------------------------------------------------


@pytest.mark.parametrize("spec, expected", [
    (None, [0, 1, 2, 3, 4, 5]),
    ("", [0, 1, 2, 3, 4, 5]),
    ("2", [1]),
    ("2-4", [1, 2, 3]),
    ("1-2, 5-6", [0, 1, 4, 5]),
    ("6,1", [5, 0]),
])
def test_a_page_spec_becomes_zero_based_indices(spec, expected):
    assert parse_pages(spec, 6) == expected


@pytest.mark.parametrize("spec", ["0", "7", "3-9", "4-2", "1,99", "1--3"])
def test_a_range_outside_the_document_is_refused_by_name(spec):
    with pytest.raises(SystemExit) as refusal:
        parse_pages(spec, 6)
    assert "outside 1-6" in str(refusal.value)


@pytest.mark.parametrize("spec", ["two", "1-x", "a-3", "1.5"])
def test_a_range_that_is_not_numbers_is_a_message_not_a_traceback(spec):
    with pytest.raises(SystemExit) as refusal:
        parse_pages(spec, 6)
    assert "not a number" in str(refusal.value)


def test_a_bad_range_writes_nothing(tmp_path):
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit):
        run(write_pdf(tmp_path, THREE), "-o", out, "--pages", "9")
    assert not out.exists()


# --- the table of contents ------------------------------------------------------


def test_toc_prints_each_pages_first_line_and_writes_nothing(tmp_path, capsys):
    pdf = write_pdf(tmp_path, THREE, name="Guide.pdf")
    assert run(pdf, "--toc") == 0
    assert capsys.readouterr().out == (
        "Guide.pdf: 3 pages\n"
        "  p  1  Alpha one\n"
        "  p  2  Bravo\n"
        "  p  3  Charlie\n")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["Guide.pdf"]


def test_toc_takes_a_page_range_too(tmp_path, capsys):
    run(write_pdf(tmp_path, THREE), "--toc", "--pages", "2-3")
    lines = capsys.readouterr().out.splitlines()
    assert lines[1:] == ["  p  2  Bravo", "  p  3  Charlie"]


def test_toc_of_a_page_with_no_text_is_a_blank_not_a_crash(tmp_path, capsys):
    run(write_pdf(tmp_path, [["Alpha"], []]), "--toc")
    assert capsys.readouterr().out.splitlines()[2] == "  p  2  "


# --- where the copy goes -------------------------------------------------------


def test_with_no_output_the_copy_goes_beside_a_pdf_inside_the_project(
        tmp_path, monkeypatch):
    monkeypatch.setattr(extract_pdf, "PROJECT_ROOT", tmp_path)
    folder = tmp_path / "Inbox"
    folder.mkdir()
    pdf = write_pdf(folder, THREE, name="Manual.pdf")
    assert run(pdf) == 0
    assert pages_of((folder / "Manual.md").read_text(encoding="utf-8"))[2] == "Bravo"


def test_with_no_output_a_pdf_outside_the_project_is_refused_and_nothing_is_written(
        tmp_path):
    """The default would otherwise write into whatever folder the PDF is in --
    the game install, which CLAUDE.md makes read-only. `tmp_path` is outside the
    project, so this is that case."""
    pdf = write_pdf(tmp_path, THREE)
    with pytest.raises(SystemExit) as refusal:
        run(pdf)
    assert "outside this project" in str(refusal.value) and "-o" in str(refusal.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["doc.pdf"]


def test_an_output_in_a_folder_that_does_not_exist_yet_is_made(tmp_path):
    out = tmp_path / "a" / "b" / "out.md"
    run(write_pdf(tmp_path, THREE), "-o", out)
    assert out.is_file()


def test_the_pdf_itself_is_never_the_output(tmp_path):
    pdf = write_pdf(tmp_path, THREE)
    before = pdf.read_bytes()
    with pytest.raises(SystemExit) as refusal:
        run(pdf, "-o", pdf)
    assert "over the PDF itself" in str(refusal.value)
    assert pdf.read_bytes() == before


# --- what it refuses to read ------------------------------------------------------


def test_a_missing_file_is_named(tmp_path):
    with pytest.raises(SystemExit) as refusal:
        run(tmp_path / "nope.pdf", "-o", tmp_path / "out.md")
    assert "No such file" in str(refusal.value)


def test_a_file_that_is_not_a_pdf_is_one_line_naming_it_and_writes_nothing(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_text("this is not a pdf at all", encoding="utf-8")
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit) as refusal:
        run(fake, "-o", out)
    assert str(fake) in str(refusal.value) and "could not be read as a PDF" in str(refusal.value)
    assert not out.exists()


def test_a_password_protected_pdf_is_refused_not_read_as_blank(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt(user_password="secret", owner_password="owner", algorithm="RC4-128")
    locked = tmp_path / "locked.pdf"
    buffer = io.BytesIO()
    writer.write(buffer)
    locked.write_bytes(buffer.getvalue())
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit) as refusal:
        run(locked, "-o", out)
    assert "could not be read as a PDF" in str(refusal.value)
    assert not out.exists()


# --- the encoding, which the cp1252 console makes a real hazard ------------------


def test_the_copy_is_utf_8_with_unix_line_ends(tmp_path):
    out = tmp_path / "out.md"
    run(write_pdf(tmp_path, [["A", "plain"]], arrow=True), "-o", out)
    raw = out.read_bytes()
    assert "→".encode("utf-8") in raw, "the arrow was not written as UTF-8"
    assert b"\r" not in raw, "line ends are LF whatever the platform"
    assert not raw.startswith(b"\xef\xbb\xbf"), "no byte-order mark"


def _run_script_on_a_cp1252_console(*argv):
    """The script as `python scripts/extract_pdf.py`, with its streams forced to
    cp1252 the way this machine's console is, and the bytes it wrote returned."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, argv)],
        capture_output=True, check=False, env=env)


def test_toc_prints_a_character_cp1252_has_no_code_for(tmp_path):
    pdf = write_pdf(tmp_path, [["A start"]], arrow=True)
    proc = _run_script_on_a_cp1252_console(pdf, "--toc")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "→ start" in proc.stdout.decode("utf-8")


def test_run_as_a_script_it_extracts_and_exits_zero(tmp_path):
    out = tmp_path / "out.md"
    proc = _run_script_on_a_cp1252_console(write_pdf(tmp_path, THREE), "-o", out)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert pages_of(out.read_text(encoding="utf-8")) == {
        1: "Alpha one\nAlpha two", 2: "Bravo", 3: "Charlie"}


def test_run_as_a_script_a_refusal_is_a_nonzero_exit(tmp_path):
    proc = _run_script_on_a_cp1252_console(tmp_path / "nope.pdf", "-o", tmp_path / "out.md")
    assert proc.returncode != 0
    assert b"No such file" in proc.stderr


# --- the usage written down is the usage that parses -------------------------------

INVOCATION = re.compile(r"scripts/extract_pdf\.py ([^`\n]+)")


def _documented_invocations(text):
    return [shlex.split(args, comments=True) for args in INVOCATION.findall(text)]


def test_every_usage_line_in_the_docstring_parses():
    found = _documented_invocations(extract_pdf.__doc__)
    assert len(found) >= 4, "the docstring's usage block is not being read"
    for argv in found:
        build_parser().parse_args(argv)


def test_the_invocation_in_the_kb_parses():
    kb = (REPO / "kb" / "platform-and-tools.md").read_text(encoding="utf-8")
    found = _documented_invocations(kb)
    assert found, "kb/platform-and-tools.md does not say how to call the script"
    for argv in found:
        build_parser().parse_args(argv)
