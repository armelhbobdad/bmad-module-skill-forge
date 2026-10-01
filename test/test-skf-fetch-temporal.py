#!/usr/bin/env python3
"""Tests for skf-fetch-temporal.py: create-skill step 3b's temporal feeder.

No test reaches GitHub or runs the gh a developer has installed:

- The fetch logic runs against a scripted gh: _gh is replaced by a fake
  that answers from a table keyed by the call and fails the test on a call
  the table does not hold.
- _gh itself, and the CLI end to end, run a fake gh placed first on PATH
  (POSIX only: the fake is a script), as test-skf-github-probe.py does.
- repo reads a git repository made for the test.

The last class pins sub/fetch-temporal.md to the helper (#605
determinism-13): the step calls it and holds no formatter of its own.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "src" / "shared" / "scripts" / "skf-fetch-temporal.py"
FETCH_TEMPORAL = REPO / "src" / "skf-create-skill" / "references" / "sub" / "fetch-temporal.md"

_MODULE = None


def _mod():
    """Load the helper lazily, so a missing helper fails each test, not collection."""
    global _MODULE
    if _MODULE is None:
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        spec = importlib.util.spec_from_file_location("skf_fetch_temporal", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


# --------------------------------------------------------------------------
# Upstream data the fake gh serves
# --------------------------------------------------------------------------

ISSUES = [
    {"number": 7, "title": "parse() drops the last line", "state": "OPEN",
     "labels": [{"name": "parser"}, {"name": "bug"}], "createdAt": "2026-09-01T10:00:00Z",
     "closedAt": None, "body": "Steps:\r\n1. call parse()\r\n2. read the output  \r\n"},
    {"number": 12, "title": "Deprecate render() for draw()", "state": "CLOSED", "labels": [],
     "createdAt": "2026-09-02T10:00:00Z", "closedAt": "2026-09-05T10:00:00Z",
     "body": "render() is deprecated: use draw(), café über alles."},
]
PRS = [
    {"number": 13, "title": "Remove render()", "mergedAt": "2026-09-06T10:00:00Z",
     "labels": [{"name": "breaking"}], "body": "BREAKING: render() is removed."},
    {"number": 9, "title": "Add draw()", "mergedAt": "2026-08-01T10:00:00Z", "labels": [], "body": ""},
]
TAGS = [
    {"tagName": "v2.0.0", "name": "Two", "publishedAt": "2026-09-07T10:00:00Z"},
    {"tagName": "v1.0.0", "name": "v1.0.0", "publishedAt": "2026-06-01T10:00:00Z"},
]
RELEASES = {
    "v2.0.0": {"tagName": "v2.0.0", "name": "Two", "publishedAt": "2026-09-07T10:00:00Z",
               "body": "render() was removed.\r\n"},
    "v1.0.0": {"tagName": "v1.0.0", "name": "v1.0.0", "publishedAt": "2026-06-01T10:00:00Z",
               "body": "First release."},
}
CONTENTS = [{"name": "README.md", "type": "file"}, {"name": "changelog.md", "type": "file"},
            {"name": "docs", "type": "dir"}]
CHANGELOG = "# Changelog\r\n\r\n## 2.0.0\r\n\r\n- render() removed\r\n"
SEARCHES = {
    "parse": [{"number": 7, "title": "parse() drops the last line", "state": "OPEN", "body": "Steps."}],
    "draw": [],
}

ISSUES_MD = (
    "# Issues: acme/lib\n"
    "\n"
    "## #12: Deprecate render() for draw()\n"
    "\n"
    "- State: closed\n"
    "- Labels: none\n"
    "- Created: 2026-09-02T10:00:00Z\n"
    "- Closed: 2026-09-05T10:00:00Z\n"
    "\n"
    "render() is deprecated: use draw(), café über alles.\n"
    "\n"
    "## #7: parse() drops the last line\n"
    "\n"
    "- State: open\n"
    "- Labels: bug, parser\n"
    "- Created: 2026-09-01T10:00:00Z\n"
    "\n"
    "Steps:\n"
    "1. call parse()\n"
    "2. read the output\n"
)


def _key(args: list[str]) -> str:
    """The table key of one gh call."""
    if args[:2] == ["auth", "status"]:
        return "auth"
    if args[:2] in (["issue", "list"], ["pr", "list"], ["release", "list"]):
        return {"issue": "issues", "pr": "prs", "release": "releases"}[args[0]]
    if args[:2] == ["release", "view"]:
        return f"release:{args[2]}"
    if args[0] == "api":
        path = args[-1]
        return "contents" if path.endswith("/contents") else f"raw:{path.rsplit('/', 1)[1]}"
    if args[:2] == ["search", "issues"]:
        return f"search:{args[4]}"
    raise AssertionError(f"unexpected gh call: {args}")


def _ok(data) -> tuple[str, str, str]:
    return "ok", data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), ""


class Gh:
    """A scripted gh: the answers for each call, and the calls made, in order."""

    def __init__(self, **overrides):
        self.table: dict[str, tuple[str, str, str]] = {
            "auth": _ok(""),
            "issues": _ok(ISSUES),
            "prs": _ok(PRS),
            "releases": _ok(TAGS),
            "contents": _ok(CONTENTS),
            "raw:changelog.md": _ok(CHANGELOG),
            **{f"release:{tag}": _ok(release) for tag, release in RELEASES.items()},
            **{f"search:{name}": _ok(found) for name, found in SEARCHES.items()},
        }
        self.table.update(overrides)
        self.calls: list[list[str]] = []
        self._lock = threading.Lock()

    def __call__(self, args: list[str], timeout: float) -> tuple[str, str, str]:
        key = _key(args)
        with self._lock:
            self.calls.append(list(args))
        assert key in self.table, f"no answer scripted for {key}: {args}"
        return self.table[key]

    def keys(self) -> list[str]:
        return [_key(args) for args in self.calls]


@pytest.fixture
def gh(monkeypatch):
    def install(**overrides) -> Gh:
        fake = Gh(**overrides)
        monkeypatch.setattr(_mod(), "_gh", fake)
        return fake
    return install


def _feeder(tmp_path: Path, skill: str = "mylib") -> Path:
    return tmp_path / "forge-data" / skill / ".skf-temporal"


def _fetch(feeder: Path, exports: list | None = None) -> tuple[dict, int]:
    return _mod().fetch("acme/lib", feeder, exports, 30.0)


def _files(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


# --------------------------------------------------------------------------
# fetch: the feeder files
# --------------------------------------------------------------------------


class TestFeederFiles:
    def test_writes_the_five_files_and_a_gitignore(self, tmp_path, gh):
        gh()
        feeder = _feeder(tmp_path)
        result, code = _fetch(feeder, ["parse", "draw"])
        assert code == 0 and result["status"] == "replaced"
        assert result["files"] == sorted(_mod().FEEDER_FILES)
        assert sorted(p.name for p in feeder.iterdir()) == sorted((".gitignore", *_mod().FEEDER_FILES))
        assert (feeder / ".gitignore").read_bytes() == b"*\n"
        assert not feeder.with_name(".skf-temporal.new").exists()
        assert result["warnings"] == []

    def test_issue_format(self, tmp_path, gh):
        gh()
        feeder = _feeder(tmp_path)
        _fetch(feeder)
        assert (feeder / "issues.md").read_bytes() == ISSUES_MD.encode("utf-8")

    def test_two_runs_on_the_same_data_are_byte_identical(self, tmp_path, gh):
        """#605 acceptance: the feeder no longer depends on a formatter the model rewrites."""
        gh()
        first, second = _feeder(tmp_path / "one"), _feeder(tmp_path / "two")
        _fetch(first, ["parse", "draw"])
        # GitHub may list the same items in another order: the files do not change.
        gh(issues=_ok(list(reversed(ISSUES))), prs=_ok(list(reversed(PRS))),
           **{"search:parse": _ok(list(reversed(SEARCHES["parse"])))})
        _fetch(second, ["draw", "parse"])
        assert _files(first) == _files(second)
        for name, data in _files(first).items():
            assert b"\r" not in data, name

    def test_every_call_names_github_com(self, tmp_path, gh):
        fake = gh()
        _fetch(_feeder(tmp_path), ["parse"])
        for args in fake.calls:
            if args[0] == "api":
                assert args[1:3] == ["--hostname", "github.com"], args
            elif args[0] in ("issue", "pr", "release"):
                assert args[args.index("-R") + 1] == "github.com/acme/lib", args
            else:
                assert args[:4] == ["search", "issues", "--repo", "acme/lib"], args

    def test_changelog_is_found_in_any_letter_case_and_kept_as_written(self, tmp_path, gh):
        gh()
        feeder = _feeder(tmp_path)
        result, _ = _fetch(feeder)
        assert result["fetches"]["changelog"] == {"status": "ok", "file": "changelog.md", "detail": None}
        assert (feeder / "changelog.md").read_bytes() == b"# Changelog\n\n## 2.0.0\n\n- render() removed\n"

    def test_releases_md_is_the_fallback_changelog(self, tmp_path, gh):
        gh(contents=_ok([{"name": "RELEASES.md", "type": "file"}]), **{"raw:RELEASES.md": _ok("# Releases\n")})
        result, _ = _fetch(_feeder(tmp_path))
        assert result["fetches"]["changelog"]["file"] == "RELEASES.md"

    def test_no_changelog_writes_none(self, tmp_path, gh):
        gh(contents=_ok([{"name": "README.md", "type": "file"}]))
        feeder = _feeder(tmp_path)
        result, code = _fetch(feeder)
        assert code == 0 and result["fetches"]["changelog"]["status"] == "none"
        assert not (feeder / "changelog.md").exists()


class TestReleaseLoop:
    """The loop the prose wrote gave its inner jq no input: the helper reads
    each `gh release view` it runs, one tag after another."""

    def test_one_view_per_tag_in_listing_order(self, tmp_path, gh):
        fake = gh()
        feeder = _feeder(tmp_path)
        result, _ = _fetch(feeder)
        views = [key for key in fake.keys() if key.startswith("release:")]
        assert views == ["release:v2.0.0", "release:v1.0.0"]
        assert fake.keys().index("release:v2.0.0") > fake.keys().index("releases")
        text = (feeder / "releases.md").read_text(encoding="utf-8")
        assert text == (
            "# Releases: acme/lib\n\n"
            "## v2.0.0: Two\n\n- Published: 2026-09-07T10:00:00Z\n\nrender() was removed.\n\n"
            "## v1.0.0\n\n- Published: 2026-06-01T10:00:00Z\n\nFirst release.\n"
        )
        assert result["fetches"]["releases"] == {"status": "ok", "count": 2, "fetched": 2, "failed": 0,
                                                 "stopped_at": None, "detail": None}

    def test_a_failed_tag_gets_a_placeholder(self, tmp_path, gh):
        gh(**{"release:v1.0.0": ("not-found", "", "release not found")})
        feeder = _feeder(tmp_path)
        result, _ = _fetch(feeder)
        assert "## v1.0.0 (fetch failed: release not found)" in (feeder / "releases.md").read_text(encoding="utf-8")
        assert result["fetches"]["releases"]["failed"] == 1

    def test_a_rate_limit_stops_the_loop_and_keeps_what_it_has(self, tmp_path, gh):
        fake = gh(**{"release:v1.0.0": ("rate-limited", "", "API rate limit exceeded")})
        feeder = _feeder(tmp_path)
        result, code = _fetch(feeder)
        assert code == 0
        record = result["fetches"]["releases"]
        assert (record["status"], record["stopped_at"], record["fetched"]) == ("stopped", 2, 1)
        assert "## v2.0.0: Two" in (feeder / "releases.md").read_text(encoding="utf-8")
        assert "Release fetch stopped at tag 2/2 due to rate limiting: partial releases.md kept." in result["warnings"]
        assert fake.keys().count("release:v1.0.0") == 1

    def test_no_release_writes_no_file(self, tmp_path, gh):
        gh(releases=_ok([]))
        feeder = _feeder(tmp_path)
        result, _ = _fetch(feeder)
        assert result["fetches"]["releases"]["status"] == "empty"
        assert not (feeder / "releases.md").exists()


class TestTargetedSearches:
    def test_names_are_sanitized_and_sorted(self, tmp_path, gh):
        fake = gh(**{"search:Mapstring": _ok([]), "search:use_thing": _ok([])})
        feeder = _feeder(tmp_path)
        result, _ = _fetch(feeder, ["parse", "Map<string>", "use_thing", "<>", "draw", "parse()"])
        searched = sorted(key for key in fake.keys() if key.startswith("search:"))
        assert searched == ["search:Mapstring", "search:draw", "search:parse", "search:use_thing"]
        text = (feeder / "targeted-issues.md").read_text(encoding="utf-8")
        headings = re.findall(r"^## (\S+)", text, re.M)
        assert headings == ["Mapstring", "draw", "parse", "use_thing"]
        assert "## draw (no issues found)" in text
        assert "### #7: parse() drops the last line (open)" in text
        assert result["fetches"]["targeted"]["skipped"] == ["<>"]
        assert "Targeted search skipped '<>': no letter, digit or underscore to search for." in result["warnings"]

    def test_at_most_ten_names(self, tmp_path, gh):
        names = [f"fn{i}" for i in range(14)]
        fake = gh(**{f"search:{name}": _ok([]) for name in names})
        result, _ = _fetch(_feeder(tmp_path), names)
        searched = {key for key in fake.keys() if key.startswith("search:")}
        assert searched == {f"search:fn{i}" for i in range(_mod().TARGETED_NAMES)}
        assert result["fetches"]["targeted"]["names"] == 10

    def test_no_exports_runs_no_search(self, tmp_path, gh):
        fake = gh()
        feeder = _feeder(tmp_path)
        result, _ = _fetch(feeder, [])
        assert not any(key.startswith("search:") for key in fake.keys())
        assert result["fetches"]["targeted"]["status"] == "none"
        assert not (feeder / "targeted-issues.md").exists()

    def test_an_old_gh_without_search_skips_the_searches(self, tmp_path, gh):
        gh(**{"search:parse": ("unsupported", "", 'unknown command "search" for "gh"')})
        feeder = _feeder(tmp_path)
        result, code = _fetch(feeder, ["parse"])
        assert code == 0 and result["fetches"]["targeted"]["status"] == "unsupported"
        assert not (feeder / "targeted-issues.md").exists()

    def test_a_rate_limit_stops_the_searches(self, tmp_path, gh):
        gh(**{"search:parse": ("rate-limited", "", "API rate limit exceeded")})
        result, _ = _fetch(_feeder(tmp_path), ["parse"])
        record = result["fetches"]["targeted"]
        assert (record["status"], record["stopped_at"]) == ("stopped", 1)
        assert "Targeted search stopped at function 1/1 due to rate limiting." in result["warnings"]


# --------------------------------------------------------------------------
# fetch: the feeder's lifetime
# --------------------------------------------------------------------------


FAILED = ("failed", "", "error connecting to api.github.com")


def _all_failing() -> dict:
    return {"issues": FAILED, "prs": FAILED, "releases": FAILED, "contents": FAILED}


def _old_feeder(feeder: Path) -> dict[str, bytes]:
    feeder.mkdir(parents=True)
    (feeder / ".gitignore").write_bytes(b"*\n")
    (feeder / "changelog.md").write_bytes(b"# old changelog\n")
    (feeder / "stale.md").write_bytes(b"# a search for an export the skill no longer has\n")
    return _files(feeder)


class TestFeederLifetime:
    def test_a_failed_refresh_keeps_the_last_good_feeder(self, tmp_path, gh):
        gh(**_all_failing())
        feeder = _feeder(tmp_path)
        before = _old_feeder(feeder)
        result, code = _fetch(feeder)
        assert (code, result["status"]) == (3, "kept")
        assert _files(feeder) == before
        assert result["files"] == ["changelog.md", "stale.md"]
        assert not feeder.with_name(".skf-temporal.new").exists()
        assert any("last good fetch" in warning for warning in result["warnings"])

    @pytest.mark.parametrize("search", [FAILED, _ok([])], ids=["searches-fail", "searches-find-nothing"])
    def test_searches_that_found_no_issue_keep_the_last_good_feeder(self, tmp_path, gh, search):
        """A Deep run passes --exports: "(fetch failed)" or "(no issues
        found)" sections are no fetched content, so with the network down
        the feeder stays as the last good fetch left it."""
        gh(**_all_failing(), **{"search:parse": search, "search:draw": search})
        feeder = _feeder(tmp_path)
        before = _old_feeder(feeder)
        result, code = _fetch(feeder, ["parse", "draw"])
        assert (code, result["status"]) == (3, "kept")
        assert _files(feeder) == before
        assert result["fetches"]["targeted"]["searched"] == 2

    def test_release_placeholders_alone_keep_the_last_good_feeder(self, tmp_path, gh):
        """A release list, one failed view and then a rate limit fetch no release notes."""
        gh(**{**_all_failing(), "releases": _ok(TAGS), "release:v2.0.0": FAILED,
              "release:v1.0.0": ("rate-limited", "", "API rate limit exceeded")})
        feeder = _feeder(tmp_path)
        before = _old_feeder(feeder)
        result, code = _fetch(feeder)
        assert (code, result["status"]) == (3, "kept")
        assert _files(feeder) == before
        record = result["fetches"]["releases"]
        assert (record["status"], record["fetched"], record["failed"], record["stopped_at"]) == ("stopped", 0, 1, 2)
        assert "Release fetch stopped at tag 2/2 due to rate limiting: no release notes fetched." in result["warnings"]

    def test_every_release_view_failing_writes_no_releases_md(self, tmp_path, gh):
        gh(**{f"release:{tag}": FAILED for tag in RELEASES})
        feeder = _feeder(tmp_path)
        result, code = _fetch(feeder)
        assert code == 0 and not (feeder / "releases.md").exists()
        assert result["fetches"]["releases"]["status"] == "failed"

    def test_a_fetch_that_wrote_a_file_replaces_the_feeder(self, tmp_path, gh):
        gh(**{**_all_failing(), "issues": _ok(ISSUES)})
        feeder = _feeder(tmp_path)
        _old_feeder(feeder)
        result, code = _fetch(feeder)
        assert (code, result["status"]) == (0, "replaced")
        assert sorted(p.name for p in feeder.iterdir()) == [".gitignore", "issues.md"]

    def test_a_fetch_folder_an_interrupted_fetch_left_is_replaced(self, tmp_path, gh):
        gh()
        feeder = _feeder(tmp_path)
        leftover = feeder.with_name(".skf-temporal.new")
        leftover.mkdir(parents=True)
        (leftover / "partial.md").write_bytes(b"# half a fetch\n")
        _fetch(feeder)
        assert not leftover.exists()
        assert not (feeder / "partial.md").exists()

    def test_first_fetch_makes_the_skill_folder(self, tmp_path, gh):
        gh()
        feeder = _feeder(tmp_path, "brand-new")
        assert not feeder.parent.exists()
        assert _fetch(feeder)[1] == 0 and (feeder / "issues.md").is_file()

    def test_the_feeder_keeps_itself_out_of_git(self, tmp_path, gh):
        if shutil.which("git") is None:
            pytest.skip("git is not installed")
        gh()
        project = tmp_path / "project"
        feeder = _feeder(project)
        _fetch(feeder)
        (feeder.parent / "skill-brief.yaml").write_bytes(b"name: mylib\n")
        leftover = feeder.with_name(".skf-temporal.new")
        leftover.mkdir()
        (leftover / ".gitignore").write_bytes(b"*\n")
        (leftover / "issues.md").write_bytes(b"# half a fetch\n")
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        status = subprocess.run(["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all"],
                                check=True, capture_output=True, text=True).stdout
        assert status.splitlines() == ["?? forge-data/mylib/skill-brief.yaml"], status


# --------------------------------------------------------------------------
# fetch: the CLI
# --------------------------------------------------------------------------


class TestFetchCli:
    def test_exports_from_a_file_or_stdin(self, tmp_path, gh, monkeypatch, capsys):
        fake = gh()
        listing = tmp_path / "inventory.json"
        listing.write_bytes(json.dumps({"top_exports": ["parse"]}).encode("utf-8"))
        feeder = _feeder(tmp_path)
        assert _mod().main(["fetch", "--repo", "acme/lib", "--feeder", str(feeder), "--exports", str(listing)]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "replaced"
        assert "search:parse" in fake.keys()
        monkeypatch.setattr(sys, "stdin", io.StringIO('["draw"]'))
        assert _mod().main(["fetch", "--repo", "acme/lib", "--feeder", str(feeder), "--exports", "-"]) == 0
        assert "search:draw" in fake.keys()

    def test_nothing_fetched_exits_3(self, tmp_path, gh, capsys):
        gh(**_all_failing())
        assert _mod().main(["fetch", "--repo", "acme/lib", "--feeder", str(_feeder(tmp_path))]) == 3
        assert json.loads(capsys.readouterr().out)["status"] == "kept"

    @pytest.mark.parametrize("args, message", [
        (["--repo", "https://github.com/acme/lib"], "--repo must be owner/repo"),
        (["--repo", "acme/lib", "--feeder", "FOLDER/temporal"], "--feeder must be a folder named .skf-temporal"),
        (["--repo", "acme/lib", "--timeout", "0"], "--timeout must be more than 0"),
        (["--repo", "acme/lib", "--exports", "FOLDER/missing.json"], "cannot read --exports"),
    ], ids=["url-repo", "feeder-name", "timeout", "exports-file"])
    def test_usage_errors_touch_nothing(self, tmp_path, gh, capsys, args, message):
        fake = gh()
        folder = tmp_path / "forge-data" / "mylib"
        keep = folder / "temporal"
        keep.mkdir(parents=True)
        (keep / "notes.md").write_bytes(b"# a user's file\n")
        argv = ["fetch", "--feeder", str(folder / ".skf-temporal"), *args]
        argv = [a.replace("FOLDER", str(folder)) for a in argv]
        assert _mod().main(argv) == 2
        assert message in capsys.readouterr().err
        assert fake.calls == []
        assert (keep / "notes.md").read_bytes() == b"# a user's file\n"

    def test_exports_shapes(self, tmp_path):
        mod = _mod()
        listing = tmp_path / "x.json"
        for data, names in (([], []), ({"top_exports": None}, []), (["a", "b"], ["a", "b"])):
            listing.write_bytes(json.dumps(data).encode("utf-8"))
            assert mod.read_exports(str(listing)) == names
        listing.write_bytes(b'{"top_exports": "parse"}')
        with pytest.raises(mod.UsageError):
            mod.read_exports(str(listing))


# --------------------------------------------------------------------------
# repo
# --------------------------------------------------------------------------


class TestRepo:
    @pytest.mark.parametrize("value", [
        "acme/lib",
        "https://github.com/acme/lib",
        "https://github.com/acme/lib.git",
        "git@github.com:acme/lib.git",
        "ssh://git@github.com/acme/lib",
    ])
    def test_github_forms(self, gh, value):
        gh()
        assert _mod().resolve_repo(value) == {"repo": "acme/lib", "via": "url", "gh": "ok", "skip_reason": None}

    def test_the_url_is_read_by_parse_remote(self, gh, monkeypatch):
        """#605: the owner/repo parse reuses skf-source-tree.py's parse_remote."""
        gh()
        tree = _mod()._sibling()
        seen = []
        real = tree.parse_remote
        monkeypatch.setattr(tree, "parse_remote", lambda value: seen.append(value) or real(value))
        assert _mod().resolve_repo("https://github.com/acme/lib.git")["repo"] == "acme/lib"
        assert "https://github.com/acme/lib.git" in seen

    @pytest.mark.parametrize("value", ["https://gitlab.com/acme/lib", "https://github.com/acme/group/lib"])
    def test_other_hosts_and_paths_are_skipped(self, gh, value):
        fake = gh()
        result = _mod().resolve_repo(value)
        assert (result["repo"], result["skip_reason"], result["gh"]) == (None, "not-github", "not-run")
        assert fake.calls == []

    @pytest.mark.parametrize("status, gh_state", [
        (("missing", "", "gh is not installed"), "missing"),
        (("failed", "", "You are not logged into any GitHub hosts."), "unauthenticated"),
        (("unauthenticated", "", "gh is not logged in"), "unauthenticated"),
        (("timeout", "", "gh did not answer within 10 seconds"), "failed"),
    ], ids=["missing", "logged-out", "token-rejected", "timeout"])
    def test_gh_states(self, gh, status, gh_state):
        fake = gh(auth=status)
        result = _mod().resolve_repo("acme/lib")
        assert (result["gh"], result["skip_reason"]) == (gh_state, f"gh-{gh_state}")
        assert fake.calls == [["auth", "status", "--hostname", "github.com"]]

    def test_a_local_clone_reads_its_origin(self, tmp_path, gh):
        if shutil.which("git") is None:
            pytest.skip("git is not installed")
        gh()
        clone = tmp_path / "lib"
        subprocess.run(["git", "init", "-q", str(clone)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(clone), "remote", "add", "origin", "git@github.com:acme/lib.git"],
                       check=True, capture_output=True)
        assert _mod().resolve_repo(str(clone)) == {"repo": "acme/lib", "via": "origin", "gh": "ok",
                                                   "skip_reason": None}

    def test_local_paths_without_a_github_origin(self, tmp_path, gh):
        if shutil.which("git") is None:
            pytest.skip("git is not installed")
        fake = gh()
        plain = tmp_path / "plain"
        plain.mkdir()
        assert _mod().resolve_repo(str(plain))["skip_reason"] == "not-a-git-repo"
        assert _mod().resolve_repo(str(tmp_path / "missing"))["skip_reason"] == "not-a-git-repo"
        clone = tmp_path / "clone"
        subprocess.run(["git", "init", "-q", str(clone)], check=True, capture_output=True)
        assert _mod().resolve_repo(str(clone))["skip_reason"] == "no-origin"
        subprocess.run(["git", "-C", str(clone), "remote", "add", "origin", "https://gitlab.com/acme/lib.git"],
                       check=True, capture_output=True)
        assert _mod().resolve_repo(str(clone))["skip_reason"] == "not-github"
        assert fake.calls == []


# --------------------------------------------------------------------------
# _gh and the CLI against a fake gh on PATH
# --------------------------------------------------------------------------

FAKE_GH = """#!{python}
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
mode = os.environ.get("FAKE_GH_MODE", "data")
if mode == "logged-out":
    print("To get started with GitHub CLI, please run:  gh auth login", file=sys.stderr)
    sys.exit(4)
if mode == "hang":
    time.sleep(30)
    sys.exit(0)
if mode == "unknown":
    print('unknown command "search" for "gh"', file=sys.stderr)
    sys.exit(1)
if mode != "data":
    code, message = mode.split(":", 1)
    print(f"gh: {{message}} (HTTP {{code}})", file=sys.stderr)
    sys.exit(1)
with open(os.environ["FAKE_GH_DATA"], encoding="utf-8") as fh:
    data = json.load(fh)
if args[:2] == ["auth", "status"]:
    sys.exit(0)
if args[:2] == ["release", "view"]:
    key = "release:" + args[2]
elif args[0] == "api":
    key = "contents" if args[-1].endswith("/contents") else "raw:" + args[-1].rsplit("/", 1)[1]
elif args[:2] == ["search", "issues"]:
    key = "search:" + args[4]
else:
    key = {{"issue": "issues", "pr": "prs", "release": "releases"}}[args[0]]
value = data[key]
sys.stdout.buffer.write((value if isinstance(value, str) else json.dumps(value)).encode("utf-8"))
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the fake gh is a POSIX script")
    folder = tmp_path / "bin"
    folder.mkdir()
    script = folder / "gh"
    script.write_bytes(FAKE_GH.format(python=sys.executable).encode("utf-8"))
    script.chmod(0o755)
    data = {"issues": ISSUES, "prs": PRS, "releases": TAGS, "contents": CONTENTS, "raw:changelog.md": CHANGELOG,
            **{f"release:{tag}": release for tag, release in RELEASES.items()},
            **{f"search:{name}": found for name, found in SEARCHES.items()}}
    (tmp_path / "gh-data.json").write_bytes(json.dumps(data).encode("utf-8"))
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_GH_DATA", str(tmp_path / "gh-data.json"))
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.delenv("FAKE_GH_MODE", raising=False)
    return log


class TestGhCall:
    @pytest.mark.parametrize("mode, result", [
        ("logged-out", "unauthenticated"),
        ("404:Not Found", "not-found"),
        ("403:API rate limit exceeded for user ID 1.", "rate-limited"),
        ("429:Too Many Requests", "rate-limited"),
        ("unknown", "unsupported"),
        ("502:Bad Gateway", "failed"),
    ])
    def test_failures(self, fake_gh, monkeypatch, mode, result):
        monkeypatch.setenv("FAKE_GH_MODE", mode)
        status, out, detail = _mod()._gh(["search", "issues", "--repo", "acme/lib", "parse"], 30.0)
        assert (status, out) == (result, "") and detail

    def test_a_hanging_gh_is_stopped(self, fake_gh, monkeypatch):
        monkeypatch.setenv("FAKE_GH_MODE", "hang")
        status, _out, detail = _mod()._gh(["issue", "list"], 1.0)
        assert status == "timeout" and "1 seconds" in detail

    def test_a_missing_gh(self, monkeypatch):
        monkeypatch.setattr(_mod()._sibling(), "_resolve_outside_cwd", lambda _name: None)
        assert _mod()._gh(["issue", "list"], 1.0) == ("missing", "", "gh is not installed")

    def test_cli_runs_are_byte_identical(self, tmp_path, fake_gh):
        """#605 acceptance, end to end: two runs of the command step 3b runs
        write the same bytes from the same upstream data."""
        feeders = []
        for run in ("one", "two"):
            feeder = _feeder(tmp_path / run)
            proc = subprocess.run(
                [sys.executable, str(HELPER), "fetch", "--repo", "acme/lib", "--feeder", str(feeder),
                 "--exports", "-"],
                input=b'["parse", "draw"]', capture_output=True, timeout=120,
            )
            assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
            assert json.loads(proc.stdout)["status"] == "replaced"
            feeders.append(feeder)
        assert _files(feeders[0]) == _files(feeders[1])
        assert sorted(_files(feeders[0])) == sorted((".gitignore", *_mod().FEEDER_FILES))
        logged = [json.loads(line) for line in fake_gh.read_text(encoding="utf-8").splitlines()]
        assert ["release", "view", "v2.0.0", "-R", "github.com/acme/lib", "--json",
                "tagName,name,publishedAt,body"] in logged

    def test_cli_repo(self, fake_gh):
        proc = subprocess.run([sys.executable, str(HELPER), "repo", "--source-repo", "https://github.com/acme/lib"],
                              capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout) == {"repo": "acme/lib", "via": "url", "gh": "ok", "skip_reason": None}


# --------------------------------------------------------------------------
# sub/fetch-temporal.md: the step calls the helper
# --------------------------------------------------------------------------


def _step() -> str:
    return FETCH_TEMPORAL.read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    text = _step()
    head = text.index(start)
    return text[head:text.index(end, head + len(start))]


class TestFetchTemporalProse:
    def test_no_formatter_or_fetch_is_left_to_the_model(self):
        text = _step()
        assert "jq -r '...'" not in text
        for command in ("gh issue list", "gh pr list", "gh release list", "gh release view", "gh search issues",
                        "gh api repos/"):
            assert command not in text, command

    def test_eligibility_asks_the_helper_for_the_repository(self):
        eligibility = " ".join(_section("### 1. Check Eligibility", "### 2.").split())
        assert 'uv run {fetchTemporalHelper} repo --source-repo "{source_repo}"' in eligibility
        assert ("Skip silently when the command exits non-zero, when its `skip_reason` is not null, and when no "
                "candidate resolves.") in eligibility
        assert "strip `.git`" not in _step()
        # The reasons are the helper's to list, not the step's.
        for reason in ("not-github", "not-a-git-repo", "no-origin", "gh-missing", "gh-unauthenticated", "gh-failed"):
            assert f"`{reason}`" not in eligibility, reason
            assert reason in HELPER.read_text(encoding="utf-8"), reason

    def test_fetch_runs_the_helper_on_the_feeder(self):
        fetch = _section("### 3. Fetch Temporal Context", "### 4.")
        assert 'uv run {fetchTemporalHelper} fetch --repo "{temporal_repo}" --feeder "{temporal_feeder}"' in fetch
        assert "**Exit 0** (`status: \"replaced\"`)" in fetch
        assert "**Exit 3** (`status: \"kept\"`" in fetch

    def test_the_limits_and_files_stay_in_the_helper(self):
        """The step acts on status, files, warnings and the exit code; the
        limits, the file names and the swap are the helper's (its --help)."""
        mod = _mod()
        fetch = " ".join(_section("### 3. Fetch Temporal Context", "### 4.").split())
        assert "`uv run {fetchTemporalHelper} --help`" in fetch
        for limit in (mod.ISSUE_LIMIT, mod.RELEASE_LIMIT, mod.ISSUE_SEARCH_LIMIT):
            assert f"last {limit} " not in fetch and f"up to {limit} " not in fetch, limit
        for name in mod.FEEDER_FILES:
            assert f"`{name}`" not in fetch, name
        for phrase in (".gitignore", "project's history", "network down"):
            assert phrase not in fetch, phrase
        help_text = subprocess.run([sys.executable, str(HELPER), "--help"], capture_output=True, text=True,
                                   encoding="utf-8", timeout=60)
        assert help_text.returncode == 0, help_text.stderr
        for name in mod.FEEDER_FILES:
            assert name in help_text.stdout, name
        assert "ISSUE_LIMIT" in help_text.stdout and "the fetch folder replaces the feeder" in help_text.stdout


# --------------------------------------------------------------------------
# enrich.md: step 4 searches only this skill's collections
# --------------------------------------------------------------------------

REFERENCES = REPO / "src" / "skf-create-skill" / "references"


class TestEnrichSearchesThisSkillOnly:
    """Step 4 annotates from the temporal and docs collections step 3b and step
    3c register for this skill, never from another skill's collections."""

    @staticmethod
    def _enrich() -> str:
        return (REFERENCES / "enrich.md").read_text(encoding="utf-8")

    def test_the_inventory_keeps_this_skills_entries(self):
        text = self._enrich()
        pre_check = text[text.index("### 2. Collection Inventory"):text.index("### 3. QMD Enrichment")]
        assert 'uv run {forgeTierRwHelper} read --target "{forgeTierConfig}"' in pre_check
        assert "whose `skill_name` is `{skill-name}`" in pre_check
        assert "Another skill's collections never count" in pre_check
        # A docs collection alone is enough to search: the branch is not temporal-only.
        assert "a temporal collection, a docs collection, or both" in pre_check

    def test_every_query_passes_the_collections(self):
        text = self._enrich()
        searches = text[text.index("### 3. QMD Enrichment"):text.index("### 4. Annotate")]
        queries = re.findall(r"`qmd_bridge\.query\([^`]*\)`", searches)
        assert len(queries) == 4
        for query in queries:
            assert "collections={enrichment_collections}" in query, query
        assert "drop a result from any other collection" in searches

    def test_the_collections_are_the_ones_steps_3b_and_3c_register(self):
        pre_check = " ".join(self._enrich().split())
        assert "at most `{skill-name}-temporal` and `{skill-name}-docs`" in pre_check
        for step, name, kind in (("fetch-temporal.md", "temporal", "temporal"), ("fetch-docs.md", "docs", "docs")):
            text = (REFERENCES / "sub" / step).read_text(encoding="utf-8")
            entry = (f'{{"name": "{{skill-name}}-{name}", "type": "{kind}", "source_workflow": "create-skill", '
                     f'"skill_name": "{{skill-name}}"')
            assert entry in text, step
