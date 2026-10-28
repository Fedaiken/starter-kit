#!/usr/bin/env python3
"""Save a web page as the browser renders it, or say it was blocked.

    <venv python> scripts/fetch_page.py <url> <out.html> [--settle SECONDS]

WHY THIS EXISTS
---------------
Many pages build themselves in JavaScript. Fetched with curl or a fetch tool,
they come back as an empty shell or a summary, not the page's real text -- and
a figure or a policy that is not in what was fetched reads as "the page does not
say". This loads the page in headless Chromium, lets its scripts run, and saves
what the browser renders, for research that cites a page: a file to read and
grep for the page's own words.

A rendered page splits its words across tags ("$245.23" in one <span>, "/night"
in the next), so a grep of the HTML misses a figure the page shows. Beside the
HTML it writes `<out>.txt`: the title, the final URL and the text the browser
shows (see below) on one line each -- the file to grep. The HTML stays the
record.

WHAT IT NEEDS
-------------
Playwright and its Chromium, installed in the project venv:

    <venv python> -m pip install playwright==1.64.0
    <venv python> -m playwright install chromium

Without them it prints one line giving both commands for this interpreter and
exits 3.

WHAT IT REFUSES TO SAVE
-----------------------
A bot check, a captcha, an access-denied page, an empty page or a page still
showing a loading placeholder is not the page asked for. Saving it would let a
grep come back empty and read as "the page does not say". So nothing is
written; it prints one line naming why and exits 1, and the caller records the
page as blocked.

The page is measured by the text the browser shows (Playwright's inner_text of
<body>, what a person reads), never by the text in its HTML. The HTML holds
menus, modals and cookie panels that CSS hides: parsed as markup they count,
and a page that shows almost nothing can clear the empty line on text no one
sees (a page showing only a loading label held over a thousand characters of
hidden menus in its HTML). The empty test, the length that makes a page short,
the bot-check and access-denied phrases and the loading placeholder are all
read from the shown text; the bot-wall markup and the <title> can only be read
from the HTML. The `.txt` is written from the shown text too, so a grep sees
what the page showed.

A loading placeholder is a shown line that is wholly "Loading...",
"Loading…", "Please wait", "One moment please" or the like (PLACEHOLDER), on a
page shorter than SHORT_TEXT -- the page's own frame can run past the empty
test and still hold nothing, and a longer page may carry such a label in a
lazy widget beside its real text. The test is on whole lines, never on the
word: an article whose prose says "loading a file" or "please wait for the
order to ship" is saved. Waiting longer does not cure it when the site's own data
request fails, so a refused page is a blocked page, not a cue to raise --settle.

No evasion: no stealth plugins, no captcha solving, no faked user agent or
fingerprint. The browser says what it is. A site that blocks it is blocked.
One page per call; it follows no links.

WHAT IT WILL NOT LOAD
---------------------
A page the site's robots.txt disallows. Before the browser opens, it reads
<origin>/robots.txt and tests the URL against each group the site writes for
Claude's user-directed agent (ROBOTS_AGENTS); any of them disallowing it refuses
it, and only a site with none of those groups is read by its `*` group. Matching
follows RFC 9309: `*` and a closing `$` inside a path, and the longest matching
rule wins, Allow on a tie. Python's urllib.robotparser matches neither wildcard,
so a rule such as `Disallow: /search/*/*` would slip past it. Obeying robots.txt
is the owner's ruling for this tool, not a setting: there is no flag to
override it.

A robots.txt that answers 4xx means the site set no rules: allowed. One that
answers 5xx or 429, or does not answer, leaves the rules unknown: refused.

Exit 0 saved, 1 blocked, empty or still loading (nothing written), 2 usage error, 3 the page
did not load (network error, timeout, not HTML, Playwright or its browser not
installed), 4 robots.txt disallows it, 5 robots.txt could not be read. On 4
and 5 nothing is loaded or written.
"""

from __future__ import annotations

import argparse
import http.client
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, NamedTuple, Sequence
from urllib.parse import quote, urlsplit

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

PLAYWRIGHT_REQUIREMENT = "playwright==1.64.0"
EMPTY_TEXT = 200          # shown characters below which a page is empty
SHORT_TEXT = 3000         # a page this short that names a challenge or shows a placeholder is that
NAV_TIMEOUT_MS = 45_000
IDLE_TIMEOUT_MS = 15_000
SCROLL_THROUGH = """async () => {
  for (let i = 0, y = 0; i < 40 && y < document.body.scrollHeight; i++, y += 800) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 300));
  }
  window.scrollTo(0, 0);
}"""

# A page whose <title> is one of these is the block page, however long it is.
BLOCK_TITLES = re.compile(
    r"^\s*(just a moment|attention required|access denied|access to this page has been denied"
    r"|pardon our interruption|are you a (?:robot|human)|security check|verify(?:ing)? you are human"
    r"|request unsuccessful|403 forbidden|forbidden|bot check|human verification|captcha)\b",
    re.IGNORECASE)

# Words a challenge page shows. A normal page can carry them too (a login form's
# reCAPTCHA, a footer), so they count only on a short page.
BLOCK_PHRASES = re.compile(
    r"verify you are (?:a )?human|are you a robot|not a robot|press (?:&|and) hold"
    r"|(?:complete|solve) the captcha|unusual traffic|automated (?:access|requests|queries)|access (?:is |has been )?denied"
    r"|you don't have permission to access|checking your browser|enable javascript and cookies"
    r"|pardon our interruption|request unsuccessful|incapsula incident|bot (?:detection|protection)",
    re.IGNORECASE)

# Markup only a bot wall serves (Cloudflare, PerimeterX, DataDome, Imperva, Akamai).
# Also short-page only: a real page may load one of these scripts in the background.
BLOCK_MARKUP = re.compile(
    r"challenge-platform|cf-chl-|cf_chl_|px-captcha|captcha-delivery\.com|_Incapsula_Resource"
    r"|/_sec/cp_challenge|errors\.edgesuite\.net",
    re.IGNORECASE)

# A string that is only a loading placeholder, matched against one whole visible
# string (fullmatch), never found inside prose.
_PLACEHOLDER_WORDS = r"(?:loading|please wait|one moment)(?: page| content| data| results)?(?: please)?"
PLACEHOLDER = re.compile(rf"(?:{_PLACEHOLDER_WORDS}\W*)+", re.IGNORECASE)


class _Text(HTMLParser):
    """The visible text and the <title>, without scripts, styles or templates."""

    HIDDEN = {"script", "style", "noscript", "template", "svg", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self._hidden = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        elif tag in self.HIDDEN:
            self._hidden += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in self.HIDDEN and self._hidden:
            self._hidden -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        elif not self._hidden:
            self.parts.append(data)


def _parsed(html: str) -> _Text:
    p = _Text()
    p.feed(html)
    p.close()
    return p


def _squash(parts: Sequence[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def page_title(html: str) -> str:
    """The page's <title>, whitespace collapsed."""
    return _squash(_parsed(html).title)


def visible(html: str) -> tuple[str, str]:
    """(title, the HTML's own text), whitespace collapsed. This is the text in the
    markup, CSS-hidden menus and all -- not what the page shows. A page is
    measured by the browser's rendered text (`Loaded.rendered`), never by this."""
    p = _parsed(html)
    return _squash(p.title), _squash(p.parts)


def placeholder_in(rendered: str) -> str | None:
    """The first line of the shown text that is wholly a loading placeholder, or None."""
    for line in rendered.splitlines():
        line = _squash([line])
        if line and PLACEHOLDER.fullmatch(line):
            return line
    return None


def blocked_reason(html: str, status: int | None, rendered: str) -> str | None:
    """Why this page is not the page asked for, or None when it is. `rendered` is
    the text the browser shows; the length and phrase tests read it, and only the
    title and the bot-wall markup are read from the `html`."""
    title = page_title(html)
    if status is not None and status >= 400:
        return f"HTTP {status}" + (f" ({title})" if title else "")
    if BLOCK_TITLES.search(title):
        return f"block page: title \"{title}\""
    text = _squash([rendered])
    short = len(text) < SHORT_TEXT
    if short:
        m = BLOCK_PHRASES.search(text)
        if m:
            return f"block page: \"{m.group(0)}\" on a page of {len(text)} shown characters"
        m = BLOCK_MARKUP.search(html)
        if m:
            return f"block page: bot-wall markup \"{m.group(0)}\" on a page of {len(text)} shown characters"
        waiting = placeholder_in(rendered)
        if waiting:
            return f"still loading: \"{waiting}\" on a page of {len(text)} shown characters"
    if len(text) < EMPTY_TEXT:
        return f"empty: {len(text)} shown characters"
    return None


# --- robots.txt ----------------------------------------------------------------------------

# The groups that bind this fetcher: Claude drives it, so a rule a site writes for
# Claude's user-directed agent applies, whatever token the browser sends (Chromium
# says HeadlessChrome; matching only that would slip past a rule written for us).
# ClaudeBot is left out: it is Anthropic's training crawler, and this fetches one
# page a person asked for and trains nothing.
ROBOTS_AGENTS = ("Claude-User", "anthropic-ai")
ROBOTS_TIMEOUT_S = 20
ROBOTS_MAX_BYTES = 500 * 1024     # RFC 9309 2.5: at least the first 500 KiB is parsed


class Rule(NamedTuple):
    allow: bool
    path: str

    def __str__(self) -> str:
        return f"{'Allow' if self.allow else 'Disallow'}: {self.path}"

    def matches(self, target: str) -> bool:
        anchored = self.path.endswith("$")
        body = self.path[:-1] if anchored else self.path
        rx = ".*".join(re.escape(_encoded(part)) for part in body.split("*"))
        return re.match(rx + (r"\Z" if anchored else ""), target) is not None


def _encoded(s: str) -> str:
    """One spelling for a path: non-ASCII percent-encoded, escapes in upper case."""
    s = quote(s, safe="!#$%&'()*+,/:;=?@[]~")
    return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group(0).upper(), s)


class RobotsUnavailable(Exception):
    """robots.txt gave no rules to go by (5xx, 429, or no answer)."""


def parse_robots(text: str) -> list[tuple[list[str], list[Rule]]]:
    """[(user-agent tokens, rules)] per group, in file order."""
    groups: list[tuple[list[str], list[Rule]]] = []
    in_rules = True
    for raw in text.splitlines():
        key, sep, value = raw.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:                 # a user-agent line after rules starts a new group
                groups.append(([], []))
                in_rules = False
            groups[-1][0].append(value.split("/")[0].strip().lower())
        elif key in ("allow", "disallow") and groups:
            in_rules = True
            if value:                    # an empty Disallow: matches nothing
                groups[-1][1].append(Rule(key == "allow", value))
    return groups


def rules_for(groups: list[tuple[list[str], list[Rule]]],
              agents: Sequence[str] = ROBOTS_AGENTS) -> list[tuple[str, list[Rule]]]:
    """[(user-agent, its rules)] for each of `agents` the file has a group for
    (same-named groups merged), or only `*` when it has none of them."""
    found = []
    for agent in agents:
        named = [names for names, _ in groups if agent.lower() in names]
        if named:
            found.append((agent, [r for names, rules in groups if agent.lower() in names for r in rules]))
    return found or [("*", [r for names, rules in groups if "*" in names for r in rules])]


def deciding_rule(rules: list[Rule], url: str) -> Rule | None:
    """The rule that decides `url`: the longest match, Allow on a tie. None when no rule matches."""
    parts = urlsplit(url)
    target = _encoded((parts.path or "/") + (f"?{parts.query}" if parts.query else ""))
    best = None
    for rule in rules:
        if rule.matches(target) and (best is None or len(rule.path) > len(best.path)
                                     or (len(rule.path) == len(best.path) and rule.allow)):
            best = rule
    return best


def fetch_robots_txt(robots_url: str) -> tuple[int, str]:
    """(HTTP status, text). An error status comes back as its status with no text;
    no answer at all raises RobotsUnavailable."""
    try:
        with urllib.request.urlopen(robots_url, timeout=ROBOTS_TIMEOUT_S) as resp:
            return resp.status, resp.read(ROBOTS_MAX_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        raise RobotsUnavailable(f"{robots_url} did not answer ({getattr(exc, 'reason', exc)})") from exc


# One read of robots.txt per host per run.
_ROBOTS_CACHE: dict[str, list[tuple[str, list[Rule]]] | RobotsUnavailable] = {}


def robots_disallows(url: str, fetch: Callable[[str], tuple[int, str]]) -> str | None:
    """Why robots.txt refuses `url` (any group of ours that disallows it), or None
    when it may be loaded. Raises RobotsUnavailable when the rules cannot be read."""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    robots_url = f"{origin}/robots.txt"
    if origin not in _ROBOTS_CACHE:
        try:
            status, text = fetch(robots_url)
            if status >= 500 or status == 429:   # 429 is "slow down", not "no rules" (as Google reads it)
                raise RobotsUnavailable(f"{robots_url} answered HTTP {status}")
            _ROBOTS_CACHE[origin] = rules_for(parse_robots(text)) if 200 <= status < 300 else []
        except RobotsUnavailable as exc:
            _ROBOTS_CACHE[origin] = exc
    hit = _ROBOTS_CACHE[origin]
    if isinstance(hit, RobotsUnavailable):
        raise hit
    for agent, rules in hit:
        rule = deciding_rule(rules, url)
        if rule is not None and not rule.allow:
            return f"\"{rule}\" for User-agent: {agent} in {robots_url}"
    return None


# --- the page --------------------------------------------------------------------------------

class Loaded(NamedTuple):
    status: int | None
    html: str
    final_url: str
    rendered: str       # the text the browser shows: inner_text of <body>, no CSS-hidden text


class LoadError(Exception):
    """The page did not load at all."""


def _python() -> str:
    """This interpreter as a shell word, for the install commands a message prints."""
    py = sys.executable or "python"
    return f'"{py}"' if " " in py else py


def load_page(url: str, settle_s: float) -> Loaded:
    """Open `url` in headless Chromium, let it render, and return its HTML and the
    text it shows."""
    try:
        from playwright.sync_api import Error as PwError, TimeoutError as PwTimeout, sync_playwright
    except ImportError as exc:
        raise LoadError(f"playwright is not installed -- run, in order: {_python()} -m pip install "
                        f"{PLAYWRIGHT_REQUIREMENT} ; {_python()} -m playwright install chromium") from exc
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(locale="en-US", viewport={"width": 1366, "height": 900})
                resp = page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                for _ in range(2):
                    try:
                        page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT_MS)
                    except PwTimeout:
                        pass  # pages that poll forever never go idle; the settle wait covers them
                    # Scroll once through the page, as a reader would: a price box or a
                    # policy section often loads only when it comes into view.
                    page.evaluate(SCROLL_THROUGH)
                page.wait_for_timeout(int(settle_s * 1000))
                ctype = (resp.headers.get("content-type", "") if resp else "")
                if ctype and "html" not in ctype.lower():
                    raise LoadError(f"not an HTML page: {ctype}")
                rendered = page.inner_text("body")
                return Loaded(resp.status if resp else None, page.content(), page.url, rendered)
            finally:
                browser.close()
    except PwError as exc:
        message = str(exc).strip()
        if "Executable doesn't exist" in message:
            raise LoadError(f"playwright's Chromium is not installed -- run: "
                            f"{_python()} -m playwright install chromium") from exc
        raise LoadError((message.splitlines() or [type(exc).__name__])[0]) from exc


def main(argv: Sequence[str], load: Callable[[str, float], Loaded] = load_page,
         fetch_robots: Callable[[str], tuple[int, str]] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fetch_page.py", description=__doc__.strip().splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("out", type=Path)
    ap.add_argument("--settle", type=float, default=4.0,
                    help="seconds to let late scripts run after the page goes idle (default 4)")
    try:
        args = ap.parse_args(list(argv))
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    if not re.match(r"https?://", args.url):
        print(f"usage: the URL must start http:// or https://, not {args.url!r}")
        return 2
    try:
        why = robots_disallows(args.url, fetch_robots or fetch_robots_txt)
    except RobotsUnavailable as exc:
        print(f"ROBOTS-UNREADABLE {args.url}: {exc} -- refused, nothing loaded")
        return 5
    if why:
        print(f"DISALLOWED {args.url}: robots.txt {why} -- nothing loaded")
        return 4
    try:
        page = load(args.url, args.settle)
    except LoadError as exc:
        print(f"FAILED {args.url}: {exc}")
        return 3
    why = blocked_reason(page.html, page.status, page.rendered)
    if why:
        print(f"BLOCKED {args.url}: {why} -- nothing saved")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page.html, encoding="utf-8")
    text = _squash([page.rendered])
    txt = args.out.with_suffix(".txt")
    txt.write_text(f"{page_title(page.html)}\n{page.final_url}\n\n{text}\n", encoding="utf-8")
    print(f"saved {args.out.as_posix()}: HTTP {page.status}, {len(page.html)} characters of HTML, "
          f"{len(text)} shown (in {txt.name}), from {page.final_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
