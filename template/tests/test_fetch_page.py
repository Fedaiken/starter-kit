"""The rendered-page fetcher: a bot check, a captcha, an access-denied page, an
empty page or a page still showing a loading placeholder is reported as blocked
and never saved, a real page is saved, a page robots.txt disallows is never
loaded, a missing Playwright or browser says how to install it, and each outcome
has its own exit code. A page is measured by the text the browser shows, never
by the text in its HTML, which holds menus CSS hides.

Nothing here opens a browser or the network: every page is a stand-in built
here and handed to `main` through its `load` argument -- its HTML, and the text
a browser would show for it (`shown`, or a string written out) -- and every
robots.txt through its `fetch_robots` argument (or the stand-in `no_network`
puts in place). The missing-Playwright cases and the loader cases swap the
`playwright` modules for stand-ins.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_page as fp  # noqa: E402

URL = "https://www.example.test/page/12"

LISTING = """<html><head><title>Example Widget - Catalog</title>
<script>window.__STATE__ = {"captcha": false, "challenge-platform": null}</script></head>
<body><h1>Example Widget</h1>
<p>$245 / unit. Shipping fee: $75 per order, up to 2 units.</p>
<p>""" + ("Brushed steel body, two handles, a ten-year warranty on the frame. " * 60) + """</p>
<footer>This site is protected by reCAPTCHA and the Google Privacy Policy applies.</footer>
</body></html>"""


def page(body: str, title: str = "", head: str = "") -> str:
    return f"<html><head><title>{title}</title>{head}</head><body>{body}</body></html>"


def shown(html: str) -> str:
    """Stand-in for the text a browser shows (inner_text of <body>) on a page where
    no CSS hides anything: one line per text node, none from scripts or styles."""
    return "\n".join(fp._parsed(html).parts)


def blocked(html: str, status: int | None = 200, rendered: str | None = None) -> str | None:
    """blocked_reason on `html` as shown by `rendered` (default: all of its text, hidden by nothing)."""
    return fp.blocked_reason(html, status, shown(html) if rendered is None else rendered)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Each test starts with an empty robots cache, and a site with no robots.txt."""
    fp._ROBOTS_CACHE.clear()
    monkeypatch.setattr(fp, "fetch_robots_txt", lambda robots_url: (404, ""))


# --- blocked_reason: what counts as blocked ----------------------------------------------

def test_a_rendered_listing_is_not_blocked():
    assert blocked(LISTING, 200) is None


@pytest.mark.parametrize("html,word", [
    (page("<p>Checking your browser before accessing the site.</p>", "Just a moment..."), "just a moment"),
    (page("<p>Sorry, you have been blocked.</p>", "Attention Required! | Cloudflare"), "attention required"),
    (page("<p>Press &amp; Hold to confirm you are a human (and not a bot).</p>",
          "Access to this page has been denied"), "access to this page"),
    (page("<p>As you were browsing something about your browser made us think you were a bot.</p>",
          "Pardon Our Interruption"), "pardon our interruption"),
])
def test_a_block_page_title_is_blocked(html, word):
    why = blocked(html, 200)
    assert why and why.startswith("block page: title") and word in why.casefold()


def test_a_captcha_phrase_on_a_short_page_is_blocked():
    html = page("<p>Please verify you are a human to continue.</p>", "example.test")
    assert "verify you are a human" in blocked(html, 200)


def test_an_access_denied_page_is_blocked():
    html = page("<h1>Access Denied</h1><p>You don't have permission to access "
                "\"http://www.example.test/\" on this server.</p>", "Access Denied")
    assert blocked(html, 200).startswith("block page")


def test_bot_wall_markup_on_a_short_page_is_blocked():
    html = page("<div id='px'></div>", "example.test",
                head="<script src='https://geo.captcha-delivery.com/captcha/?initialCid=x'></script>")
    why = blocked(html + " " * 10, 200)
    assert why and "captcha-delivery.com" in why


def test_the_same_markup_on_a_full_page_is_not_blocked():
    html = LISTING.replace("</head>", "<script src='https://geo.captcha-delivery.com/tags.js'></script></head>")
    assert blocked(html, 200) is None


def test_recaptcha_footer_on_a_short_real_page_is_not_blocked():
    body = "<p>" + "Our two models ship within a week. Returns accepted for $50 a unit. " * 6 + \
           "</p><footer>This site is protected by reCAPTCHA.</footer>"
    assert blocked(page(body, "Example Shop"), 200) is None


@pytest.mark.parametrize("status", [403, 404, 429, 503])
def test_an_error_status_is_blocked_whatever_the_body(status):
    assert blocked(LISTING, status).startswith(f"HTTP {status}")


def test_a_script_only_shell_is_empty():
    html = page("<div id='root'></div><script>" + "x=1;" * 5000 + "</script>", "Loading")
    assert blocked(html, 200).startswith("empty")


# --- blocked_reason: a page still showing a loading placeholder -----------------------------

# A site's frame: navigation and footer text that clears the empty test by itself,
# with the article's place held by a placeholder.
FRAME = ("<nav>" + " ".join(f"Section{i} Forum{i} Support{i}" for i in range(40)) + "</nav>"
         "<footer>All rights reserved. Privacy Policy | Legal | Cookies</footer>")


def frame_with(placeholder_html: str) -> str:
    return page(FRAME + placeholder_html, "Example - News Hub")


@pytest.mark.parametrize("placeholder_html,shown", [
    ("<div class='x'>Loading...</div>", "Loading..."),
    ("<div>Loading…</div>", "Loading…"),
    ("<div>  LOADING  </div>", "LOADING"),
    ("<div>Please wait</div>", "Please wait"),
    ("<div>Please wait...</div>", "Please wait..."),
    ("<div>Loading page, please wait</div>", "Loading page, please wait"),
    ("<div><img src='spinner.png'><span>Loading</span><span>...</span></div>", "Loading"),
])
def test_a_frame_with_only_a_loading_placeholder_is_refused(placeholder_html, shown):
    html = frame_with(placeholder_html)
    _, text = fp.visible(html)
    assert fp.EMPTY_TEXT < len(text) < fp.SHORT_TEXT      # the frame alone clears the empty test
    why = blocked(html, 200)
    assert why and why.startswith("still loading: ") and f'"{shown}"' in why and str(len(text)) in why


def test_a_page_of_nothing_but_a_placeholder_names_the_placeholder_not_emptiness():
    why = blocked(page("<div>Loading...</div>", "Example"), 200)
    assert why and why.startswith("still loading: ")


def test_an_article_that_mentions_loading_in_its_prose_is_saved():
    body = ("<h1>Opening and loading</h1><p>When loading a file the editor shows \"Loading...\" for a "
            "few seconds; please wait for the document to appear before you click. Loading is faster "
            "from an SSD, and one moment of patience saves a corrupted file. </p>"
            "<p>" + "Keep a backup of every file before you update the editor. " * 6 + "</p>")
    html = frame_with(body)
    _, text = fp.visible(html)
    assert fp.EMPTY_TEXT < len(text) < fp.SHORT_TEXT      # short: only the whole-string test can save it
    assert fp.placeholder_in(shown(html)) is None
    assert blocked(html, 200) is None


@pytest.mark.parametrize("hidden", ["script", "style", "template", "noscript"])
def test_a_placeholder_in_hidden_markup_is_not_shown(hidden):
    assert fp.placeholder_in(shown(frame_with(f"<{hidden}>Loading...</{hidden}>"))) is None


def test_a_long_page_with_a_lazy_widget_label_is_not_refused():
    html = LISTING.replace("</body>", "<div class='comments'>Loading...</div></body>")
    assert len(fp.visible(html)[1]) >= fp.SHORT_TEXT
    assert blocked(html, 200) is None


def test_visible_text_skips_scripts_and_styles():
    title, text = fp.visible(page("<style>.a{}</style><p>Hello</p><script>var b</script>", "T"))
    assert (title, text) == ("T", "Hello")


# --- blocked_reason: a page is measured by the text the browser shows --------------------------

# Navigation a stylesheet hides: it is in the HTML, longer than SHORT_TEXT, and not on screen.
HIDDEN_MENUS = ("<nav style='display:none'>"
                + " ".join(f"Menu{i} Section{i} Support{i}" for i in range(150)) + "</nav>")
STORE_SHOWN = "Store page."


def with_hidden_menus(body: str, title: str = "Example Store") -> str:
    html = page(HIDDEN_MENUS + body, title)
    assert len(fp.visible(html)[1]) >= fp.SHORT_TEXT      # the markup alone is a long page
    return html


def test_hidden_menus_do_not_save_a_page_that_shows_almost_nothing():
    html = with_hidden_menus(f"<p>{STORE_SHOWN}</p>")
    assert blocked(html, 200, rendered=STORE_SHOWN) == f"empty: {len(STORE_SHOWN)} shown characters"


@pytest.mark.parametrize("length,refused", [(fp.EMPTY_TEXT - 1, True), (fp.EMPTY_TEXT, False)])
def test_the_empty_line_is_on_the_shown_characters(length, refused):
    html = with_hidden_menus("<p>text</p>")
    assert (blocked(html, 200, rendered="a" * length) is not None) is refused


def test_shown_whitespace_is_not_counted():
    html = with_hidden_menus("<p>text</p>")
    assert blocked(html, 200, rendered="\n\n  " + "a" * (fp.EMPTY_TEXT - 1) + "  \n\t\n").startswith("empty")


def test_a_captcha_phrase_shown_on_a_page_with_long_hidden_markup_is_blocked():
    html = with_hidden_menus("<p>Please verify you are a human to continue.</p>")
    why = blocked(html, 200, rendered="Please verify you are a human to continue.")
    assert why and why.startswith("block page: \"verify you are a human\"")


def test_a_placeholder_shown_on_a_page_with_long_hidden_markup_is_still_loading():
    html = with_hidden_menus("<div>Loading...</div>")
    why = blocked(html, 200, rendered="Example Store\nLoading...")
    assert why and why.startswith("still loading: \"Loading...\"")


def test_a_block_phrase_only_in_hidden_text_does_not_refuse_a_page_that_shows_real_text():
    shown_text = "Our two models ship within a week. " * 10
    html = page("<div hidden>Access denied. Automated access is not allowed.</div>"
                f"<p>{shown_text}</p>", "Example Shop")
    assert fp.BLOCK_PHRASES.search(fp.visible(html)[1])        # the markup does hold the phrase
    assert fp.EMPTY_TEXT < len(shown_text) < fp.SHORT_TEXT
    assert blocked(html, 200, rendered=shown_text) is None


def test_bot_wall_markup_is_still_read_from_the_html():
    html = page("<div id='px'></div>", "example.test",
                head="<script src='https://geo.captcha-delivery.com/captcha/?initialCid=x'></script>")
    why = blocked(html, 200, rendered="x" * fp.EMPTY_TEXT)
    assert why and "captcha-delivery.com" in why


def test_a_placeholder_is_a_whole_shown_line():
    assert fp.placeholder_in("Home\n  Loading …  \nFooter") == "Loading …"
    assert fp.placeholder_in("Loading\n...") == "Loading"
    assert fp.placeholder_in("While loading a file, please wait.\nDone") is None
    assert fp.placeholder_in("") is None


def test_inline_pieces_the_browser_joins_into_one_line_are_one_placeholder():
    html = frame_with("<div><img src='spinner.png'><span>Loading</span><span>...</span></div>")
    why = blocked(html, 200, rendered=shown(frame_with("")) + "\nLoading...")
    assert why and why.startswith("still loading: \"Loading...\"")


# --- main: exit codes and what is written ------------------------------------------------

def loader(status, html, final=URL, rendered=None):
    text = shown(html) if rendered is None else rendered
    return lambda url, settle: fp.Loaded(status, html, final, text)


def test_a_real_page_is_saved_and_exits_0(tmp_path, capsys):
    out = tmp_path / "sub" / "page.html"
    assert fp.main([URL, str(out)], load=loader(200, LISTING)) == 0
    assert out.read_text(encoding="utf-8") == LISTING
    assert capsys.readouterr().out.startswith("saved ")


def test_the_visible_text_is_saved_beside_it_for_grep(tmp_path):
    out = tmp_path / "page.html"
    html = LISTING.replace("$245 / unit", "<span>$245</span><span> / unit</span>")
    assert fp.main([URL, str(out)], load=loader(200, html)) == 0
    title, final, _, text = out.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
    assert (title, final) == ("Example Widget - Catalog", URL)
    assert "$245 / unit" in text and "__STATE__" not in text


def test_a_blocked_page_exits_1_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "page.html"
    html = page("<p>Checking your browser.</p>", "Just a moment...")
    assert fp.main([URL, str(out)], load=loader(200, html)) == 1
    assert list(tmp_path.iterdir()) == []
    printed = capsys.readouterr().out.strip()
    assert printed.startswith(f"BLOCKED {URL}: ") and len(printed.splitlines()) == 1


def test_a_page_still_loading_exits_1_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "page.html"
    assert fp.main([URL, str(out)], load=loader(200, frame_with("<div>Loading...</div>"))) == 1
    assert list(tmp_path.iterdir()) == []
    printed = capsys.readouterr().out.strip()
    assert printed.startswith(f"BLOCKED {URL}: still loading: \"Loading...\"")
    assert printed.endswith("-- nothing saved") and len(printed.splitlines()) == 1


def test_an_article_that_mentions_loading_is_saved_and_exits_0(tmp_path):
    out = tmp_path / "page.html"
    body = frame_with("<p>When loading a file, please wait: the editor shows Loading... first. " * 6 + "</p>")
    assert fp.main([URL, str(out)], load=loader(200, body)) == 0
    assert out.exists() and "please wait: the editor shows" in out.with_suffix(".txt").read_text(encoding="utf-8")


def test_an_empty_page_exits_1(tmp_path):
    out = tmp_path / "page.html"
    assert fp.main([URL, str(out)], load=loader(200, page("", ""))) == 1
    assert not out.exists()


def test_a_page_that_shows_almost_nothing_exits_1_whatever_its_hidden_markup(tmp_path, capsys):
    html = with_hidden_menus(f"<p>{STORE_SHOWN}</p>")
    assert fp.main([URL, str(tmp_path / "page.html")], load=loader(200, html, rendered=STORE_SHOWN)) == 1
    assert list(tmp_path.iterdir()) == []
    printed = capsys.readouterr().out.strip()
    assert printed == f"BLOCKED {URL}: empty: {len(STORE_SHOWN)} shown characters -- nothing saved"


def test_the_text_file_is_the_shown_text_not_the_hidden_markup(tmp_path, capsys):
    out = tmp_path / "page.html"
    html = LISTING.replace("</body>", HIDDEN_MENUS + "</body>")
    assert "Menu7 " in fp.visible(html)[1]
    assert fp.main([URL, str(out)], load=loader(200, html, rendered=shown(LISTING))) == 0
    assert out.read_text(encoding="utf-8") == html                     # the HTML stays the record
    title, final, blank, text = out.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
    assert (title, final, blank) == ("Example Widget - Catalog", URL, "")
    assert text.startswith("Example Widget $245 / unit. Shipping fee") and "Menu7 " not in text
    assert f"{len(text)} shown (in page.txt)" in capsys.readouterr().out


def test_a_page_that_does_not_load_exits_3(tmp_path, capsys):
    def fail(url, settle):
        raise fp.LoadError("net::ERR_NAME_NOT_RESOLVED")
    assert fp.main([URL, str(tmp_path / "x.html")], load=fail) == 3
    assert capsys.readouterr().out.startswith("FAILED ")


@pytest.mark.parametrize("argv", [[], [URL], ["www.no-scheme.test", "x.html"]])
def test_bad_arguments_exit_2(argv, tmp_path):
    called = []
    assert fp.main(argv, load=lambda u, s: called.append(u)) == 2
    assert called == []


# --- Playwright or its browser is not there ----------------------------------------------

class Error(Exception):          # stands in for playwright.sync_api.Error
    pass


class Timeout(Error):            # ... and for its TimeoutError
    pass


def install_playwright(monkeypatch, chromium):
    """Stand-ins for the `playwright` modules whose `chromium` is the one given."""
    class Playwright:
        def __init__(self):
            self.chromium = chromium

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    api = types.ModuleType("playwright.sync_api")
    api.Error, api.TimeoutError, api.sync_playwright = Error, Timeout, Playwright
    pkg = types.ModuleType("playwright")
    pkg.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)


def fake_playwright(monkeypatch, launch_message):
    """Stand-ins for the `playwright` modules whose browser launch fails with `launch_message`."""
    class Chromium:
        def launch(self, headless):
            raise Error(launch_message)

    install_playwright(monkeypatch, Chromium())


def fake_browser(monkeypatch, html, body_text, status=200, content_type="text/html"):
    """Stand-ins for a Chromium that loads `html` and shows `body_text`. Returns the
    list of selectors the page's inner_text was asked for."""
    asked = []

    class Response:
        headers = {"content-type": content_type}

    Response.status = status

    class Page:
        url = URL

        def goto(self, url, wait_until, timeout):
            return Response()

        def wait_for_load_state(self, state, timeout):
            pass

        def evaluate(self, script):
            pass

        def wait_for_timeout(self, ms):
            pass

        def content(self):
            return html

        def inner_text(self, selector):
            asked.append(selector)
            return body_text

    class Browser:
        def new_page(self, **options):
            return Page()

        def close(self):
            pass

    class Chromium:
        def launch(self, headless):
            return Browser()

    install_playwright(monkeypatch, Chromium())
    return asked


def test_a_missing_playwright_exits_3_with_both_install_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    assert fp.main([URL, str(tmp_path / "x.html")]) == 3
    printed = capsys.readouterr().out.strip()
    assert printed.startswith(f"FAILED {URL}: playwright is not installed") and len(printed.splitlines()) == 1
    assert f"{sys.executable} -m pip install playwright==1.64.0" in printed
    assert f"{sys.executable} -m playwright install chromium" in printed
    assert list(tmp_path.iterdir()) == []


def test_a_missing_browser_exits_3_with_the_install_command(tmp_path, monkeypatch, capsys):
    fake_playwright(monkeypatch, "BrowserType.launch: Executable doesn't exist at /nowhere/chrome\n"
                                 "Looks like Playwright was just installed or updated.")
    assert fp.main([URL, str(tmp_path / "x.html")]) == 3
    printed = capsys.readouterr().out.strip()
    assert printed.startswith(f"FAILED {URL}: playwright's Chromium is not installed")
    assert len(printed.splitlines()) == 1 and f"{sys.executable} -m playwright install chromium" in printed
    assert list(tmp_path.iterdir()) == []


def test_any_other_browser_error_reports_its_first_line(tmp_path, monkeypatch, capsys):
    fake_playwright(monkeypatch, "BrowserType.launch: Target closed\nCall log: ...")
    assert fp.main([URL, str(tmp_path / "x.html")]) == 3
    assert capsys.readouterr().out.strip() == f"FAILED {URL}: BrowserType.launch: Target closed"


def test_a_browser_error_with_no_message_still_reports(tmp_path, monkeypatch, capsys):
    fake_playwright(monkeypatch, "")
    assert fp.main([URL, str(tmp_path / "x.html")]) == 3
    assert capsys.readouterr().out.strip() == f"FAILED {URL}: Error"


# --- the browser's loader returns the text the browser shows ------------------------------

def test_load_page_returns_the_html_and_the_text_the_browser_shows(monkeypatch):
    html = with_hidden_menus(f"<p>{STORE_SHOWN}</p>")
    asked = fake_browser(monkeypatch, html, STORE_SHOWN)
    assert fp.load_page(URL, 0) == fp.Loaded(200, html, URL, STORE_SHOWN)
    assert asked == ["body"]


def test_through_the_real_loader_a_page_showing_almost_nothing_exits_1(tmp_path, monkeypatch, capsys):
    fake_browser(monkeypatch, with_hidden_menus(f"<p>{STORE_SHOWN}</p>"), STORE_SHOWN)
    assert fp.main([URL, str(tmp_path / "page.html")]) == 1
    assert list(tmp_path.iterdir()) == []
    assert f"empty: {len(STORE_SHOWN)} shown characters" in capsys.readouterr().out


def test_through_the_real_loader_a_page_with_real_shown_text_is_saved(tmp_path, monkeypatch):
    fake_browser(monkeypatch, LISTING, shown(LISTING))
    out = tmp_path / "page.html"
    assert fp.main([URL, str(out)]) == 0
    assert "Shipping fee: $75 per order" in out.with_suffix(".txt").read_text(encoding="utf-8")


# --- robots.txt --------------------------------------------------------------------------
# A made-up robots.txt in the shapes real sites write: a `*` group and a group for
# `anthropic-ai` that repeats it and adds two prefixes, a crawler group that bans
# everything, and wildcard rules (`/search/*/*`, `/events/*?*modal`).

STAR_RULES = """Allow: /calendar/ical/
Disallow: /account
Disallow: /book/
Disallow: /calendar/
Disallow: /events/*?*modal
Disallow: /events/*/book
Disallow: /items/*/reviews
Disallow: /search/*/*
"""

SITE_ROBOTS = (
    "User-agent: anthropic-ai\n" + STAR_RULES + "Disallow: /items/\nDisallow: /events/\n"
    "\n\n\nUser-agent: ClaudeBot\nDisallow: /\n\n\n"
    "User-agent: *\n" + STAR_RULES + "\nSitemap: https://shop.example.test/sitemap.xml\n")

# The same file with no group for Claude: only `*` applies.
STAR_ONLY = "User-agent: *\n" + STAR_RULES

SEARCH = "https://shop.example.test/search/blue-widgets/results?qty=2&color=red"
ITEM_URL = "https://shop.example.test/items/5657102?qty=2&color=red"
REVIEWS = "https://shop.example.test/items/5657102/reviews"


def robots(text, status=200):
    """A robots.txt stand-in that counts its calls."""
    def fetch(robots_url):
        fetch.calls.append(robots_url)
        return status, text
    fetch.calls = []
    return fetch


def verdict(text, url):
    """robots_disallows on a fresh read of `text` (the cache would keep the last one)."""
    fp._ROBOTS_CACHE.clear()
    return fp.robots_disallows(url, robots(text))


def test_the_search_page_is_refused_by_search_star_star():
    assert verdict(STAR_ONLY, SEARCH) == \
        '"Disallow: /search/*/*" for User-agent: * in https://shop.example.test/robots.txt'
    assert '"Disallow: /search/*/*" for User-agent: anthropic-ai' in verdict(SITE_ROBOTS, SEARCH)


def test_under_star_alone_an_item_page_with_a_query_is_allowed():
    assert verdict(STAR_ONLY, ITEM_URL) is None


def test_the_anthropic_ai_group_refuses_every_item_page():
    assert verdict(SITE_ROBOTS, ITEM_URL) == \
        '"Disallow: /items/" for User-agent: anthropic-ai in https://shop.example.test/robots.txt'


def test_an_item_reviews_page_is_refused():
    assert '"Disallow: /items/*/reviews"' in verdict(STAR_ONLY, REVIEWS)


def test_claudebot_does_not_bind_the_fetcher():
    text = "User-agent: ClaudeBot\nDisallow: /\n\nUser-agent: *\nDisallow: /private\n"
    assert verdict(text, URL) is None
    assert "for User-agent: *" in verdict(text, "https://www.example.test/private/1")


def test_a_claude_group_replaces_star():
    text = "User-agent: Claude-User\nDisallow: /mine\n\nUser-agent: *\nDisallow: /\n"
    assert verdict(text, URL) is None
    assert "for User-agent: Claude-User" in verdict(text, "https://www.example.test/mine/1")


def test_either_claude_group_disallowing_refuses():
    text = "User-agent: Claude-User\nAllow: /\n\nUser-agent: anthropic-ai\nDisallow: /page/\n"
    assert "for User-agent: anthropic-ai" in verdict(text, URL)


def test_user_agent_lines_match_without_case_or_version():
    assert verdict("User-agent: CLAUDE-USER/1.0\nDisallow: /\n", URL) is not None


def test_consecutive_user_agent_lines_share_one_group():
    text = "User-agent: Googlebot\nUser-agent: anthropic-ai\nDisallow: /a\n\nUser-agent: Googlebot\nDisallow: /b\n"
    assert verdict(text, "https://www.example.test/a") is not None
    assert verdict(text, "https://www.example.test/b") is None


@pytest.mark.parametrize("path,refused", [
    ("/calendar/ical/123.ics", False),     # Allow: /calendar/ical/ outruns Disallow: /calendar/
    ("/calendar/abc", True),               # only Disallow: /calendar/ matches
])
def test_the_longest_match_wins(path, refused):
    assert (verdict(STAR_ONLY, "https://shop.example.test" + path) is not None) is refused


def test_a_longer_disallow_beats_a_shorter_allow():
    text = "User-agent: *\nAllow: /page\nDisallow: /page/12\n"
    assert verdict(text, URL) is not None
    assert verdict(text, "https://www.example.test/page/13") is None


@pytest.mark.parametrize("text", [
    "User-agent: *\nDisallow: /page\nAllow: /page\n",
    "User-agent: *\nAllow: /page\nDisallow: /page\n",
    "User-agent: *\nDisallow: /p*\nAllow: /pa\n",
])
def test_allow_wins_a_tie(text):
    assert verdict(text, URL) is None


def test_a_wildcard_reaches_into_the_query():
    assert '"Disallow: /events/*?*modal"' in verdict(
        STAR_ONLY, "https://shop.example.test/events/123?x=1&modal=photos")
    assert verdict(STAR_ONLY, "https://shop.example.test/events/123?x=1") is None


def test_a_closing_dollar_anchors_the_end():
    text = "User-agent: *\nDisallow: /*.json$\n"
    assert verdict(text, "https://www.example.test/a.json") is not None
    assert verdict(text, "https://www.example.test/a.json?v=2") is None


def test_an_empty_disallow_allows_everything():
    assert verdict("User-agent: *\nDisallow:\n", URL) is None


def test_robots_txt_is_read_once_per_host():
    fetch = robots(STAR_ONLY)
    fp.robots_disallows(SEARCH, fetch)
    fp.robots_disallows(ITEM_URL, fetch)
    fp.robots_disallows(URL, fetch)
    assert fetch.calls == ["https://shop.example.test/robots.txt", "https://www.example.test/robots.txt"]


# --- main: what a robots refusal does ----------------------------------------------------

def never_load(url, settle):
    raise AssertionError("the page was loaded")


def test_a_disallowed_page_exits_4_and_loads_nothing(tmp_path, capsys):
    out = tmp_path / "search.html"
    assert fp.main([SEARCH, str(out)], load=never_load, fetch_robots=robots(SITE_ROBOTS)) == 4
    assert list(tmp_path.iterdir()) == []
    printed = capsys.readouterr().out.strip()
    assert printed.startswith(f"DISALLOWED {SEARCH}: robots.txt \"Disallow: /search/*/*\"")
    assert printed.endswith("-- nothing loaded") and len(printed.splitlines()) == 1


def test_an_item_page_the_anthropic_ai_group_bans_exits_4(tmp_path):
    assert fp.main([ITEM_URL, str(tmp_path / "i.html")], load=never_load,
                   fetch_robots=robots(SITE_ROBOTS)) == 4


@pytest.mark.parametrize("status", [401, 403, 404, 410])
def test_a_4xx_robots_txt_means_allowed(status, tmp_path):
    out = tmp_path / "page.html"
    assert fp.main([URL, str(out)], load=loader(200, LISTING), fetch_robots=robots("", status)) == 0
    assert out.exists()


@pytest.mark.parametrize("status", [500, 503, 429])
def test_a_5xx_or_429_robots_txt_exits_5_and_loads_nothing(status, tmp_path, capsys):
    assert fp.main([URL, str(tmp_path / "x.html")], load=never_load,
                   fetch_robots=robots("", status)) == 5
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr().out.startswith(
        f"ROBOTS-UNREADABLE {URL}: https://www.example.test/robots.txt answered HTTP {status}")


def test_a_robots_txt_that_does_not_answer_exits_5(tmp_path, capsys):
    def silent(robots_url):
        raise fp.RobotsUnavailable(f"{robots_url} did not answer (timed out)")
    assert fp.main([URL, str(tmp_path / "x.html")], load=never_load, fetch_robots=silent) == 5
    assert "did not answer" in capsys.readouterr().out


def test_an_allowed_page_still_loads_and_saves(tmp_path):
    out = tmp_path / "page.html"
    assert fp.main([URL, str(out)], load=loader(200, LISTING),
                   fetch_robots=robots("User-agent: *\nDisallow: /private\n")) == 0
    assert out.exists()
