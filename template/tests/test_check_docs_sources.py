"""Tests for the SOURCES check in scripts/check_docs.py -- a search summary is not a page.

Run on small fixture strings, never the live kb/: a kb entry changes whenever
a source is re-read, and a test pinned to one would fail for the wrong reason.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_docs as cd

ROADMAP = "**Roadmap (developer, 2026-10-15 post, via search):** version 7 shipped 2026-06-15."


def hits(*lines):
    return cd.find_search_citations("kb/x.md", "\n".join(lines) + "\n")


def test_via_search_with_no_page_fails_and_names_the_line():
    out = hits("# Title", "", ROADMAP)
    assert len(out) == 1
    assert out[0].startswith("kb/x.md:3:") and "via search" in out[0] and "names no page read" in out[0]


def test_the_same_line_with_a_url_passes():
    assert hits(ROADMAP + " Post: https://example.com/news/123, retrieved: 2026-10-27") == []


def test_a_url_needs_its_retrieved_date():
    assert len(hits(ROADMAP + " Post: https://example.com/news/123")) == 1


def test_a_saved_copy_path_is_not_a_page():
    # saved copies live in gitignored scratch: the path is dead in git and on every other machine
    assert len(hits(ROADMAP + " Read: `Working/sources/news-123.html`, retrieved: 2026-10-27")) == 1


def test_a_search_or_answer_url_is_not_a_page():
    assert len(hits(ROADMAP + " https://www.perplexity.ai/search/roadmap-abc retrieved: 2026-10-27")) == 1
    assert len(hits(ROADMAP + " https://www.google.com/search?q=roadmap retrieved: 2026-10-27")) == 1


def test_perplexity_citation_with_no_url_fails():
    assert len(hits("Version 7 shipped 2026-06-15 (Perplexity, 2026-10-26).")) == 1
    assert len(hits("How this was found: one Perplexity search on 2026-10-26.")) == 1
    assert len(hits("Source: Perplexity.")) == 1


def test_perplexity_citation_with_a_url_passes():
    assert hits("Version 7 shipped 2026-06-15 (Perplexity found it; https://example.com/patch, retrieved: 2026-10-27).") == []


def test_close_variants_fail():
    for line in (
        "Found 2026-10-26 by web search, not yet visited one by one.",
        "| Subreddit | not confirmed by the search | — |",
        "Each row is the search's reading.",
        "The search found three wikis.",
        "Title rules changed (per the WebSearch results).",
        "The post says so, according to WebFetch.",
        "Read through the fetch tool.",
        "The release date is from a Google search result.",
    ):
        assert len(hits(line)) == 1, line


def test_lines_explaining_the_rule_pass():
    for line in (
        "A search result, a Perplexity answer, and the fetch tool's output are a model's summary of pages, not a page; "
        "recorded as a source, they put claims in the record the page never made.",
        "A kb line that cites `via search` or `by web search` as its source fails the gate unless it also names the page.",
        "Use the page loader, not curl or the fetch tool, for any page you cite.",
        "The seeder's permissions lack the Perplexity tools.",
        "keywords:  [web page, URL, fetch tool, git]",
    ):
        assert hits(line) == [], line


def test_a_phrase_only_partly_in_backticks_is_still_a_citation():
    assert len(hits("The roadmap changed (via `WebSearch`).")) == 1


def test_fenced_code_is_skipped():
    assert hits("```", ROADMAP, "```") == []


def test_frontmatter_is_checked():
    out = hits("---", 'topic: "Found 2026-10-26 by web search, not yet visited."', "---")
    assert len(out) == 1 and out[0].startswith("kb/x.md:2:")
