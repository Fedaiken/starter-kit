"""The WebFetch tool must be denied in this project's `.claude/settings.json`.

Why this exists: the fetch tool returns a model's summary of a page, not the
page, so a figure or a policy it leaves out reads as "the page does not say".
`scripts/fetch_page.py` saves what the browser renders, and a file you can grep
is the evidence; the tool must not stay available as the easy wrong path.
"""
import json
from pathlib import Path

SETTINGS = Path(__file__).resolve().parents[1] / ".claude" / "settings.json"
TOOL = "WebFetch"


def _entries(settings, key):
    permissions = settings.get("permissions") or {}
    entries = permissions.get(key) or []
    return [e.strip() for e in entries if isinstance(e, str)]


def _names(entry):
    """`WebFetch` and `WebFetch(domain:example.com)` both name the tool."""
    return entry == TOOL or entry.startswith(TOOL + "(")


def problems(settings):
    """What is wrong with `settings` (a parsed settings.json), one line each."""
    found = []
    allowed = [e for e in _entries(settings, "allow") if _names(e)]
    if allowed:
        found.append("permissions.allow has %s -- remove %s"
                     % (", ".join(repr(e) for e in allowed),
                        "it" if len(allowed) == 1 else "them"))
    if TOOL not in _entries(settings, "deny"):
        found.append('permissions.deny lacks "%s" -- add it' % TOOL)
    return found


def test_webfetch_is_denied_in_the_project_settings():
    assert SETTINGS.is_file(), "%s is missing -- create it with %s in permissions.deny" % (SETTINGS, TOOL)
    found = problems(json.loads(SETTINGS.read_text(encoding="utf-8")))
    assert not found, (
        "%s: %s. The fetch tool returns a summary of a page, not the page; "
        "use scripts/fetch_page.py." % (SETTINGS, "; ".join(found)))


def test_a_denied_tool_passes():
    assert problems({"permissions": {"allow": ["Read"], "deny": ["WebFetch"]}}) == []


def test_a_tool_missing_from_deny_is_named():
    found = problems({"permissions": {"allow": ["Read"], "deny": ["Bash(rm -rf /*)"]}})
    assert found == ['permissions.deny lacks "WebFetch" -- add it']


def test_a_bare_allow_is_found():
    found = problems({"permissions": {"allow": ["Read", "WebFetch"], "deny": ["WebFetch"]}})
    assert found == ["permissions.allow has 'WebFetch' -- remove it"]


def test_an_allow_with_a_pattern_is_found():
    found = problems({"permissions": {"allow": ["WebFetch(domain:example.com)"], "deny": ["WebFetch"]}})
    assert found == ["permissions.allow has 'WebFetch(domain:example.com)' -- remove it"]


def test_an_allow_and_a_missing_deny_are_both_reported():
    assert len(problems({"permissions": {"allow": ["WebFetch"]}})) == 2


def test_a_patterned_deny_does_not_deny_the_tool():
    assert problems({"permissions": {"deny": ["WebFetch(domain:example.com)"]}}) \
        == ['permissions.deny lacks "WebFetch" -- add it']


def test_a_tool_with_a_longer_name_is_not_the_tool():
    assert problems({"permissions": {"allow": ["WebFetcher"], "deny": ["WebFetch"]}}) == []


def test_settings_with_no_permissions_fail():
    assert problems({}) == ['permissions.deny lacks "WebFetch" -- add it']
