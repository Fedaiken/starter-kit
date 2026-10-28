"""Tests for scripts/kit_sync.py -- push, push --new, and commit into the kit.

Every test builds a throwaway kit (a git repository with a bare remote) and a
throwaway project under tmp_path, and points kit_sync at them. Nothing here
touches the network, this project's .kit.json, or the real Starter Kit.

The kit's privacy check is a stand-in with the real one's contract: exit 0 and
print OK, or exit 1 naming the hit. It refuses any file carrying PLANTED, so a
test plants the word to make the check fail.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import kit_sync as ks

STAND_IN_CHECK = '''\
import sys
from pathlib import Path
kit = Path(__file__).resolve().parent.parent
hits = [p for p in kit.rglob("*") if p.is_file() and ".git" not in p.parts and p.name != "check_private.py"
        and "PLANTED" in p.read_text(encoding="utf-8", errors="replace")]
if hits:
    print("FAIL - personal detail in " + ", ".join(p.name for p in hits), file=sys.stderr)
    sys.exit(1)
print("OK - nothing personal")
'''

OWNED = "# Kit-owned\n\n# The gate\nscripts/check_docs.py\n\n# Tests\ntests/test_one.py\n"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """(project, kit, remote): a kit with one commit pushed to its bare remote, and a project in sync with it."""
    remote, kit, project = tmp_path / "remote.git", tmp_path / "kit", tmp_path / "Project"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    kit.mkdir()
    git(kit, "init", "-q", "-b", "main")
    for key, value in (("user.name", "Kit Test"), ("user.email", "kit@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        git(kit, "config", key, value)
    write(kit / "kit_owned.txt", OWNED)
    write(kit / "scripts/check_private.py", STAND_IN_CHECK)
    write(kit / "scripts/new_project.py", "# the seeder\n")
    write(kit / "template/scripts/check_docs.py", "gate v1\n")
    write(kit / "template/tests/test_one.py", "def test(): pass\n")
    write(kit / "template/kb/seeded.md", "seeded once\n")
    git(kit, "add", "-A")
    git(kit, "commit", "-q", "-m", "kit")
    git(kit, "remote", "add", "origin", str(remote))
    git(kit, "push", "-q", "origin", "main")

    write(project / "scripts/check_docs.py", "gate v1\n")
    write(project / "tests/test_one.py", "def test(): pass\n")
    files = {rel: {"project": ks.digest(project / rel), "kit": ks.digest(kit / "template" / rel)}
             for rel in ("scripts/check_docs.py", "tests/test_one.py")}
    write(project / ".kit.json", json.dumps({"kit_url": str(remote), "files": files}, indent=2) + "\n")

    monkeypatch.setattr(ks, "ROOT", project)
    monkeypatch.setattr(ks, "RECORD", project / ".kit.json")
    monkeypatch.setenv("STARTER_KIT", str(kit))
    return project, kit, remote


def heads(kit, remote):
    return git(kit, "rev-parse", "HEAD"), git(remote, "rev-parse", "main")


def record(project) -> dict:
    return json.loads((project / ".kit.json").read_text(encoding="utf-8"))


# --- push --new -----------------------------------------------------------------


def test_push_new_copies_lists_records_commits_and_pushes(setup, capsys):
    project, kit, remote = setup
    write(project / "tests/test_two.py", "def test_two(): pass\n")
    assert ks.main(["push", "--new", "tests/test_two.py"]) == 0
    assert (kit / "template/tests/test_two.py").read_text(encoding="utf-8") == "def test_two(): pass\n"
    listed = (kit / "kit_owned.txt").read_text(encoding="utf-8").splitlines()
    assert listed.index("tests/test_two.py") == listed.index("tests/test_one.py") + 1
    assert set(git(kit, "show", "--name-only", "--format=", "HEAD").splitlines()) == {"template/tests/test_two.py", "kit_owned.txt"}
    assert git(kit, "status", "--porcelain") == ""
    kit_head, remote_head = heads(kit, remote)
    assert kit_head == remote_head
    assert record(project)["files"]["tests/test_two.py"]["kit"] == ks.digest(project / "tests/test_two.py")
    out = capsys.readouterr().out
    assert "OK - nothing personal" in out and "kit pushed to origin" in out


def test_push_new_lists_a_file_with_no_folder_match_at_the_end(setup):
    project, kit, _ = setup
    write(project / "skills/x/SKILL.md", "a skill\n")
    assert ks.main(["push", "--new", "skills/x/SKILL.md"]) == 0
    assert (kit / "kit_owned.txt").read_text(encoding="utf-8").splitlines()[-1] == "skills/x/SKILL.md"


def test_push_new_refuses_a_file_the_kit_already_owns(setup, capsys):
    _, kit, remote = setup
    before = heads(kit, remote)
    assert ks.main(["push", "--new", "scripts/check_docs.py"]) == 1
    assert "already kit-owned" in capsys.readouterr().err
    assert heads(kit, remote) == before


def test_push_new_refuses_a_file_the_kit_seeds(setup, capsys):
    project, kit, remote = setup
    write(project / "kb/seeded.md", "this project's own version\n")
    before = heads(kit, remote)
    assert ks.main(["push", "--new", "kb/seeded.md"]) == 1
    assert "already seeds" in capsys.readouterr().err
    assert (kit / "template/kb/seeded.md").read_text(encoding="utf-8") == "seeded once\n"
    assert heads(kit, remote) == before


def test_push_new_refuses_a_file_missing_from_the_project(setup, capsys):
    assert ks.main(["push", "--new", "tests/test_absent.py"]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_a_failed_privacy_check_leaves_the_kit_as_it_was_on_push_new(setup, capsys):
    project, kit, remote = setup
    owned_before = (kit / "kit_owned.txt").read_bytes()
    rec_before = (project / ".kit.json").read_bytes()
    write(project / "scripts/deep/new_tool.py", "owner = 'PLANTED'\n")
    before = heads(kit, remote)
    assert ks.main(["push", "--new", "scripts/deep/new_tool.py"]) == 1
    err = capsys.readouterr().err
    assert "privacy check refused" in err and "Nothing was committed" in err
    assert not (kit / "template/scripts/deep").exists()
    assert (kit / "kit_owned.txt").read_bytes() == owned_before
    assert (project / ".kit.json").read_bytes() == rec_before
    assert git(kit, "status", "--porcelain") == ""
    assert heads(kit, remote) == before


# --- plain push -----------------------------------------------------------------


def test_plain_push_runs_the_privacy_check_and_restores_on_refusal(setup, capsys):
    project, kit, remote = setup
    write(project / "scripts/check_docs.py", "gate v2 PLANTED\n")
    before = heads(kit, remote)
    assert ks.main(["push", "scripts/check_docs.py"]) == 1
    assert "privacy check refused" in capsys.readouterr().err
    assert (kit / "template/scripts/check_docs.py").read_text(encoding="utf-8") == "gate v1\n"
    assert git(kit, "status", "--porcelain") == ""
    assert heads(kit, remote) == before


def test_plain_push_refuses_when_the_kit_has_no_privacy_check(setup, capsys):
    project, kit, remote = setup
    (kit / "scripts/check_private.py").unlink()
    write(project / "scripts/check_docs.py", "gate v2\n")
    before = heads(kit, remote)
    assert ks.main(["push", "scripts/check_docs.py"]) == 1
    assert "has no scripts/check_private.py" in capsys.readouterr().err
    assert (kit / "template/scripts/check_docs.py").read_text(encoding="utf-8") == "gate v1\n"
    assert heads(kit, remote) == before


def test_plain_push_that_passes_commits_and_pushes(setup):
    project, kit, remote = setup
    write(project / "scripts/check_docs.py", "gate v2\n")
    assert ks.main(["push", "scripts/check_docs.py"]) == 0
    assert (kit / "template/scripts/check_docs.py").read_text(encoding="utf-8") == "gate v2\n"
    kit_head, remote_head = heads(kit, remote)
    assert kit_head == remote_head
    assert git(kit, "show", "--name-only", "--format=", "HEAD") == "template/scripts/check_docs.py"


def test_plain_push_of_a_file_the_kit_does_not_own_points_at_new(setup, capsys):
    project, _, _ = setup
    write(project / "tests/test_two.py", "x\n")
    assert ks.main(["push", "tests/test_two.py"]) == 1
    assert "push --new tests/test_two.py" in capsys.readouterr().err


# --- commit ---------------------------------------------------------------------


def test_commit_saves_only_the_named_kit_paths_and_pushes(setup, tmp_path):
    _, kit, remote = setup
    write(kit / "scripts/new_project.py", "# the seeder, improved\n")
    write(kit / "template/kb/seeded.md", "seeded, improved\n")
    write(kit / "README.md", "an unrelated edit\n")
    message = write(tmp_path / "msg.txt", "Seeder: improve it\n")
    assert ks.main(["commit", "scripts/new_project.py", "template/kb/seeded.md", "-F", str(message)]) == 0
    assert set(git(kit, "show", "--name-only", "--format=", "HEAD").splitlines()) == {"scripts/new_project.py", "template/kb/seeded.md"}
    assert git(kit, "log", "-1", "--format=%s") == "Seeder: improve it"
    assert git(kit, "status", "--porcelain") == "?? README.md"
    kit_head, remote_head = heads(kit, remote)
    assert kit_head == remote_head


def test_commit_refuses_a_kit_owned_template_file(setup, tmp_path, capsys):
    _, kit, remote = setup
    write(kit / "template/scripts/check_docs.py", "edited in the kit\n")
    message = write(tmp_path / "msg.txt", "m\n")
    before = heads(kit, remote)
    assert ks.main(["commit", "template/scripts/check_docs.py", "-F", str(message)]) == 1
    assert "goes by `push scripts/check_docs.py`" in capsys.readouterr().err
    assert heads(kit, remote) == before


def test_commit_refused_by_the_privacy_check_commits_nothing(setup, tmp_path, capsys):
    _, kit, remote = setup
    write(kit / "scripts/new_project.py", "owner = 'PLANTED'\n")
    message = write(tmp_path / "msg.txt", "m\n")
    before = heads(kit, remote)
    assert ks.main(["commit", "scripts/new_project.py", "-F", str(message)]) == 1
    assert "privacy check refused" in capsys.readouterr().err
    assert heads(kit, remote) == before
    assert git(kit, "diff", "--cached", "--name-only") == ""


def test_commit_refuses_an_empty_or_missing_message_file(setup, tmp_path, capsys):
    _, kit, _ = setup
    write(kit / "scripts/new_project.py", "# changed\n")
    assert ks.main(["commit", "scripts/new_project.py", "-F", str(tmp_path / "absent.txt")]) == 1
    assert ks.main(["commit", "scripts/new_project.py", "-F", str(write(tmp_path / "empty.txt", "\n"))]) == 1
    assert "missing or empty" in capsys.readouterr().err


def test_commit_refuses_a_path_outside_the_kit(setup, tmp_path, capsys):
    message = write(tmp_path / "msg.txt", "m\n")
    assert ks.main(["commit", "../elsewhere.txt", "-F", str(message)]) == 1
    assert "not a path inside the kit" in capsys.readouterr().err


def test_a_failed_kit_push_is_reported_and_exits_nonzero(setup, tmp_path, capsys):
    _, kit, _ = setup
    git(kit, "remote", "set-url", "origin", str(tmp_path / "no-such-remote.git"))
    write(kit / "scripts/new_project.py", "# changed\n")
    message = write(tmp_path / "msg.txt", "m\n")
    assert ks.main(["commit", "scripts/new_project.py", "-F", str(message)]) == 1
    assert "KIT PUSH FAILED" in capsys.readouterr().out


# --- the listing ----------------------------------------------------------------


def test_listed_with_keeps_crlf_line_endings():
    text = "# head\r\nscripts/a.py\r\n\r\n# Tests\r\ntests/t.py\r\n"
    assert ks.listed_with(text, "scripts/b.py") == "# head\r\nscripts/a.py\r\nscripts/b.py\r\n\r\n# Tests\r\ntests/t.py\r\n"
