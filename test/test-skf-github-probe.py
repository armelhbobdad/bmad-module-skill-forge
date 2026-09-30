#!/usr/bin/env python3
"""Tests for skf-github-probe.py: can a GitHub repository be read, and why not.

No test reaches GitHub or runs the gh a developer has installed:

- The command logic (which probe runs next, which cause is named) runs
  against scripted probes: _gh, _api and _git are replaced by fakes that
  answer from a table and fail the test on a probe the table does not
  expect.
- _gh runs a fake gh placed first on PATH (POSIX only: the fake is a
  script), which answers the way gh 2.x does: exit 4 when logged out,
  `gh: <message> (HTTP <code>)` on stderr for an HTTP error.
- _api calls a local HTTP server standing in for api.github.com.
- _git runs the real git against a scratch bare repository served as
  https://github.com/acme/lib through a url.<file uri>.insteadOf entry in a
  per-test global git config, as test-skf-source-tree.py does.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "shared" / "scripts"
HELPER = SCRIPTS / "skf-github-probe.py"
SOURCE_TREE = SCRIPTS / "skf-source-tree.py"
SHA_A, SHA_B, SHA_C = "a" * 40, "b" * 40, "c" * 40

_MODULE = None


def _mod():
    """Load the helper lazily, so a missing helper fails each test, not collection."""
    global _MODULE
    if _MODULE is None:
        assert HELPER.is_file(), f"missing helper: {HELPER}"
        spec = importlib.util.spec_from_file_location("skf_github_probe", HELPER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE = module
    return _MODULE


# --------------------------------------------------------------------------
# Scripted probes
# --------------------------------------------------------------------------


class Script:
    """Answers for _gh (keyed by the API path), _api (by path) and _git
    (`repo` for the --symref HEAD probe, `tags` for the tag listing)."""

    def __init__(self):
        self.gh: dict[str, tuple] = {}
        self.api: dict[str, tuple] = {}
        self.git: dict[str, tuple] = {}
        self.calls: list[tuple[str, str]] = []

    def _answer(self, table: dict, probe: str, key: str) -> tuple[str, str, str]:
        self.calls.append((probe, key))
        assert key in table, f"unexpected {probe} probe: {key}"
        answer = table[key]
        result = answer[0]
        out = answer[1] if len(answer) > 1 else ""
        detail = answer[2] if len(answer) > 2 else ("" if result == "ok" else f"{probe} said {result}")
        return result, out, detail

    def fake_gh(self, *args: str):
        return self._answer(self.gh, "gh", args[-1])

    def fake_api(self, path: str):
        return self._answer(self.api, "api", path)

    def fake_git(self, *args: str):
        return self._answer(self.git, "git", "tags" if "--tags" in args else "repo")


@pytest.fixture
def script(monkeypatch) -> Script:
    s = Script()
    mod = _mod()
    monkeypatch.setattr(mod, "_gh", s.fake_gh)
    monkeypatch.setattr(mod, "_api", s.fake_api)
    monkeypatch.setattr(mod, "_git", s.fake_git)
    mod._start_clock(None)
    return s


REPO = "repos/acme/lib"
OWNER = "users/acme"
TAGS = "repos/acme/lib/tags?per_page=100"


def _tree_path(ref: str = "HEAD") -> str:
    from urllib.parse import quote
    return f"repos/acme/lib/git/trees/{quote(ref, safe='')}?recursive=1"


# --------------------------------------------------------------------------
# Repository names
# --------------------------------------------------------------------------


class TestParseRepo:
    @pytest.mark.parametrize("value", [
        "acme/lib",
        " acme/lib ",
        "github.com/acme/lib",
        "www.github.com/acme/lib",
        "https://github.com/acme/lib",
        "https://github.com/acme/lib.git",
        "https://github.com/acme/lib/",
        "HTTPS://GitHub.com/acme/lib",
        "http://github.com/acme/lib",
        "https://github.com/acme/lib/tree/main/packages/x",
        "https://github.com/acme/lib?tab=readme",
        "https://github.com/acme/lib#readme",
        "git@github.com:acme/lib.git",
        "ssh://git@github.com/acme/lib.git",
        "git://github.com/acme/lib",
        # skf-resolve-package.py's grammar, which the probe reads --repo with.
        "github:acme/lib",
        "git+https://github.com/acme/lib.git",
        "git+ssh://git@github.com:acme/lib.git",
        "ssh://git@github.com:acme/lib.git",
        "ssh://git@github.com:22/acme/lib.git",
    ])
    def test_github_forms(self, value):
        assert _mod().parse_repo(value) == ("acme", "lib")

    def test_one_grammar_with_the_resolver(self):
        resolver = _mod()._load("skf-resolve-package.py")
        assert Path(resolver.__file__).resolve() == (SCRIPTS / "skf-resolve-package.py").resolve()
        for value in ("vercel/next.js", "https://github.com/org/repo/tree/main/pkg", "git@github.com:a/b.git"):
            loc = resolver.github_target(value)
            assert _mod().parse_repo(value) == (loc["owner"], loc["repo"])

    def test_names_with_dots_dashes_and_underscores(self):
        assert _mod().parse_repo("my-org/next.js") == ("my-org", "next.js")
        assert _mod().parse_repo("a_b/.github") == ("a_b", ".github")

    @pytest.mark.parametrize("value", [
        "", "acme", "acme/lib/extra", "https://gitlab.com/acme/lib", "https://github.com/acme",
        "acme/..", "../lib", "-x/lib", "acme/li b", "@scope/pkg", "C:/acme/lib", "file:///acme/lib",
        "https://github.com.evil.example/acme/lib",
    ])
    def test_not_a_github_repository(self, value):
        assert _mod().parse_repo(value) is None


# --------------------------------------------------------------------------
# repo
# --------------------------------------------------------------------------


class TestRepo:
    def test_gh_reads_it(self, script):
        script.gh[REPO] = ("ok", json.dumps({"private": True, "default_branch": "trunk"}))
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["via"], out["gh"], out["private"], out["default_branch"]) == (
            "ok", "gh", "ok", True, "trunk")
        assert (out["cause"], out["message"], out["account"]) == (None, None, None)
        assert script.calls == [("gh", REPO)]

    @pytest.mark.parametrize("gh", ["missing", "unauthenticated", "network", "timeout", "rate-limited"])
    def test_public_repo_without_gh(self, script, gh):
        script.gh[REPO] = (gh,)
        script.api[REPO] = ("ok", json.dumps({"private": False, "default_branch": "main"}))
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["via"], out["private"], out["default_branch"]) == ("ok", "api", False, "main")
        assert out["gh"] == {"missing": "missing", "unauthenticated": "unauthenticated"}.get(gh, "failed")

    def test_private_repo_through_git_credentials(self, script):
        script.gh[REPO] = ("missing",)
        script.api[REPO] = ("not-found",)
        script.git["repo"] = ("ok", f"ref: refs/heads/develop\tHEAD\n{SHA_A}\tHEAD\n")
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["via"], out["private"], out["default_branch"]) == ("ok", "git", True, "develop")

    @pytest.mark.parametrize("gh, cause", [("missing", "gh-missing"), ("unauthenticated", "gh-unauthenticated")])
    def test_private_or_missing_without_a_gh_login(self, script, gh, cause):
        script.gh[REPO] = (gh,)
        script.api[REPO] = ("not-found",)
        script.git["repo"] = ("auth-required",)
        script.api[OWNER] = ("ok", "{}")
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["cause"], out["gh"], out["via"]) == ("unavailable", cause, gh, None)
        assert "private or does not exist" in out["message"]
        assert "gh auth login" in out["message"]
        assert [(r["probe"], r["target"], r["result"]) for r in out["probes"]] == [
            ("gh", "repo", gh), ("api", "repo", "not-found"), ("git", "repo", "auth-required"),
            ("api", "owner", "ok")]

    def test_missing_owner_is_repo_not_found(self, script):
        script.gh[REPO] = ("missing",)
        script.api[REPO] = ("not-found",)
        script.git["repo"] = ("auth-required",)
        script.api[OWNER] = ("not-found",)
        out = _mod().probe_repo("acme", "lib")
        assert out["cause"] == "repo-not-found"
        assert out["message"] == "GitHub has no user or organization named acme; check the URL."
        assert out["account"] is None

    def test_authenticated_404_names_the_account(self, script):
        script.gh[REPO] = ("not-found",)
        script.git["repo"] = ("not-found",)
        script.gh[OWNER] = ("ok", "{}")
        script.gh["user"] = ("ok", json.dumps({"login": "octo"}))
        out = _mod().probe_repo("acme", "lib")
        assert (out["cause"], out["account"], out["gh"]) == ("repo-not-found", "octo", "ok")
        assert "the GitHub account octo" in out["message"] and "private" in out["message"]
        assert ("api", REPO) not in script.calls, "an authenticated 404 already says what anonymous access would"

    def test_refused_access_is_no_access(self, script):
        saml = "gh: Resource protected by organization SAML enforcement. (HTTP 403)"
        script.gh[REPO] = ("forbidden", "", saml)
        script.api[REPO] = ("not-found",)
        script.git["repo"] = ("auth-required",)
        out = _mod().probe_repo("acme", "lib")
        assert out["cause"] == "no-access"
        assert "SAML" in out["message"] and "gh auth refresh" in out["message"]
        assert all(r["target"] != "owner" for r in out["probes"])

    def test_refused_token_still_reads_a_public_repo(self, script):
        """A token an organization refuses (SAML) does not make its public repositories private."""
        script.gh[REPO] = ("forbidden",)
        script.api[REPO] = ("ok", json.dumps({"private": False, "default_branch": "main"}))
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["via"], out["gh"]) == ("ok", "api", "ok")

    def test_git_refused_is_no_access(self, script):
        script.gh[REPO] = ("missing",)
        script.api[REPO] = ("not-found",)
        script.git["repo"] = ("forbidden",)
        assert _mod().probe_repo("acme", "lib")["cause"] == "no-access"

    @pytest.mark.parametrize("gh", ["missing", "unauthenticated", "network"])
    def test_network_failures_are_unreachable(self, script, gh):
        script.gh[REPO] = (gh,)
        script.api[REPO] = ("network", "", "api.github.com: [Errno -2] Name or service not known")
        script.git["repo"] = ("network", "", "fatal: unable to access: Could not resolve host: github.com")
        out = _mod().probe_repo("acme", "lib")
        assert out["cause"] == "unreachable"
        assert "Could not resolve host" in out["message"]
        assert all(r["target"] != "owner" for r in out["probes"]), "no owner lookup without a 404"


# --------------------------------------------------------------------------
# tags
# --------------------------------------------------------------------------


def _gh_tags(*pages) -> str:
    """What `gh api --paginate` prints: one JSON array per page."""
    return "".join(json.dumps([{"name": n, "commit": {"sha": s}} for n, s in page]) for page in pages)


class TestTags:
    def test_gh_listing_with_pages(self, script):
        script.gh[TAGS] = ("ok", _gh_tags([("v1.0.0", SHA_A), ("latest", SHA_C)], [("v1.10.0", SHA_B)]))
        out = _mod().probe_tags("acme", "lib", ["1.10.0", "v1.10.0"], 20)
        assert (out["status"], out["via"]) == ("ok", "gh")
        assert out["tags"] == ["v1.10.0", "v1.0.0", "latest"] and out["count"] == 3
        assert (out["match"], out["found"], out["missing"]) == ("v1.10.0", {"v1.10.0": SHA_B}, ["1.10.0"])
        assert script.calls == [("gh", TAGS)]

    def test_one_page_is_one_array(self, script):
        script.gh[TAGS] = ("ok", _gh_tags([("v2", SHA_A)]))
        assert _mod().probe_tags("acme", "lib", [], 20)["tags"] == ["v2"]

    @pytest.mark.parametrize("gh", ["missing", "unauthenticated", "network", "not-found"])
    def test_git_lists_when_gh_cannot(self, script, gh):
        script.gh[TAGS] = (gh,)
        script.git["tags"] = ("ok", f"{SHA_A}\trefs/tags/v1\n{SHA_B}\trefs/tags/v2\n{SHA_C}\trefs/tags/v2^{{}}\n")
        out = _mod().probe_tags("acme", "lib", ["2", "v2"], 20)
        assert (out["status"], out["via"], out["match"], out["found"]) == ("ok", "git", "v2", {"v2": SHA_C})
        assert out["missing"] == ["2"]

    def test_unparsable_gh_output_falls_back_to_git(self, script):
        script.gh[TAGS] = ("ok", "not json")
        script.git["tags"] = ("ok", f"{SHA_A}\trefs/tags/v1\n")
        assert _mod().probe_tags("acme", "lib", [], 20)["via"] == "git"

    def test_unreadable_listing_says_no_tag_is_missing(self, script):
        """quick-skill reports a missing tag only when a listing lacks it."""
        script.gh[TAGS] = ("unauthenticated",)
        script.git["tags"] = ("auth-required",)
        script.api[OWNER] = ("ok", "{}")
        out = _mod().probe_tags("acme", "lib", ["1.0", "v1.0"], 20)
        assert (out["status"], out["cause"]) == ("unavailable", "gh-unauthenticated")
        assert (out["tags"], out["count"], out["match"], out["found"], out["missing"]) == ([], 0, None, {}, [])

    def test_logged_out_gh_and_no_git_is_the_gh_cause(self, script):
        script.gh[TAGS] = ("unauthenticated",)
        script.git["tags"] = ("missing",)
        assert _mod().probe_tags("acme", "lib", [], 20)["cause"] == "gh-unauthenticated"

    def test_limit(self, script):
        script.gh[TAGS] = ("ok", _gh_tags([(f"v1.{i}.0", SHA_A) for i in range(30)]))
        assert len(_mod().probe_tags("acme", "lib", [], 20)["tags"]) == 20
        assert _mod().probe_tags("acme", "lib", [], 2)["tags"] == ["v1.29.0", "v1.28.0"]
        full = _mod().probe_tags("acme", "lib", [], 0)
        assert len(full["tags"]) == full["count"] == 30

    # withastro/astro's changesets tags (trimmed): one tag per package and version.
    ASTRO = [("astro@4.16.2", SHA_A), ("astro@4.16.1", SHA_A), ("astro@4.16.0", SHA_B), ("astro@4.15.11", SHA_A),
             ("@astrojs/cloudflare@14.3.3", SHA_C), ("@astrojs/react@4.16.0", SHA_C), ("latest", SHA_A)]

    def test_a_version_matches_a_monorepo_package_tag(self, script):
        script.gh[TAGS] = ("ok", _gh_tags(self.ASTRO))
        out = _mod().probe_tags("acme", "lib", [], 5, "4.16.0", "astro")
        assert (out["status"], out["match"], out["found"], out["missing"]) == ("ok", "astro@4.16.0", {}, [])

    @pytest.mark.parametrize("gh", ["missing", "timeout"])
    def test_the_git_listing_matches_by_name_too(self, script, gh):
        # The git listing's loop must not clobber --name: its last line here is `latest`.
        script.gh[TAGS] = (gh,)
        script.git["tags"] = ("ok", "".join(f"{SHA_A}\trefs/tags/{name}\n" for name, _sha in self.ASTRO))
        out = _mod().probe_tags("acme", "lib", [], 5, "4.16.0", "astro")
        assert (out["via"], out["match"]) == ("git", "astro@4.16.0")

    def test_a_scoped_package_tag_matches_by_name(self, script):
        script.gh[TAGS] = ("ok", _gh_tags(self.ASTRO))
        assert _mod().probe_tags("acme", "lib", [], 5, "14.3.3", "cloudflare")["match"] == \
            "@astrojs/cloudflare@14.3.3"
        assert _mod().probe_tags("acme", "lib", [], 5, "14.3.3", "@astrojs/cloudflare")["match"] == \
            "@astrojs/cloudflare@14.3.3"

    def test_without_a_name_only_the_bare_and_v_forms_match(self, script):
        script.gh[TAGS] = ("ok", _gh_tags(self.ASTRO + [("v2.0.0", SHA_A)]))
        assert _mod().probe_tags("acme", "lib", [], 5, "4.16.0")["match"] is None
        assert _mod().probe_tags("acme", "lib", [], 5, "2.0.0")["match"] == "v2.0.0"
        assert _mod().probe_tags("acme", "lib", [], 5, "v2.0.0", "astro")["match"] == "v2.0.0"

    def test_a_missing_version_lists_the_nearest_tags(self, script):
        script.gh[TAGS] = ("ok", _gh_tags(self.ASTRO))
        out = _mod().probe_tags("acme", "lib", [], 5, "4.16.5", "astro")
        assert out["match"] is None
        assert out["nearest"] == _mod()._sibling().nearest_tags([name for name, _sha in self.ASTRO], "4.16.5")
        assert out["nearest"] and all(_mod()._sibling().split_version(t) for t in out["nearest"])

    def test_a_wanted_tag_comes_before_the_version(self, script):
        script.gh[TAGS] = ("ok", _gh_tags(self.ASTRO))
        out = _mod().probe_tags("acme", "lib", ["latest"], 5, "4.16.0", "astro")
        assert (out["match"], out["found"]) == ("latest", {"latest": SHA_A})

    def test_no_version_no_nearest(self, script):
        script.gh[TAGS] = ("ok", _gh_tags(self.ASTRO))
        assert _mod().probe_tags("acme", "lib", [], 5)["nearest"] == []

    def test_sorted_tags(self):
        names = ["v1.2.0", "latest", "v1.10.0", "v1.2.0-rc.1", "nightly", "pkg@3.0.0", "v1.9.0"]
        assert _mod()._sorted_tags(names) == ["pkg@3.0.0", "v1.10.0", "v1.9.0", "v1.2.0", "v1.2.0-rc.1",
                                              "latest", "nightly"]


# --------------------------------------------------------------------------
# tree
# --------------------------------------------------------------------------


def _tree_json(truncated: bool = False) -> str:
    return json.dumps({"sha": SHA_A, "truncated": truncated, "tree": [
        {"path": "package.json", "type": "blob"}, {"path": "src", "type": "tree"},
        {"path": "src/a.ts", "type": "blob"}, {"path": "vendor/sub", "type": "commit"}]})


class TestTree:
    def test_gh_lists_files_only(self, script):
        script.gh[_tree_path()] = ("ok", _tree_json(truncated=True))
        out = _mod().probe_tree("acme", "lib", "")
        assert (out["status"], out["via"], out["ref"], out["tree"], out["count"], out["truncated"]) == (
            "ok", "gh", "HEAD", ["package.json", "src/a.ts"], 2, True)

    @pytest.mark.parametrize("ref", ["", "null", "None", "NONE", "head", "Head"])
    def test_null_or_head_ref_reads_the_default_branch(self, script, ref):
        """A written-out null (quick-skill's auto-detect path has no source_ref) is no ref name."""
        script.gh[_tree_path()] = ("ok", _tree_json())
        out = _mod().probe_tree("acme", "lib", ref)
        assert (out["status"], out["ref"]) == ("ok", "HEAD")
        assert script.calls == [("gh", _tree_path())]

    def test_refs_with_a_slash_are_encoded(self, script):
        script.gh[_tree_path("tokio/v1.0.0")] = ("ok", _tree_json())
        out = _mod().probe_tree("acme", "lib", "tokio/v1.0.0")
        assert out["status"] == "ok" and "tokio%2Fv1.0.0" in script.calls[0][1]

    def test_refused_token_falls_back_to_the_api(self, script):
        script.gh[_tree_path()] = ("forbidden",)
        script.api[_tree_path()] = ("ok", _tree_json())
        assert _mod().probe_tree("acme", "lib", "HEAD")["via"] == "api"

    def test_missing_ref_in_a_readable_repo(self, script):
        script.gh[_tree_path("v9")] = ("not-found",)
        script.gh[REPO] = ("ok", "{}")
        out = _mod().probe_tree("acme", "lib", "v9")
        assert (out["status"], out["cause"], out["ref"]) == ("unavailable", "ref-not-found", "v9")
        assert out["message"] == "acme/lib has no branch, tag or commit named v9."
        assert not any(probe == "api" for probe, _key in script.calls)

    def test_gh_404_for_the_repository_skips_the_api(self, script):
        script.gh[_tree_path("v9")] = ("not-found",)
        script.gh[REPO] = ("not-found",)
        script.gh[OWNER] = ("ok", "{}")
        script.gh["user"] = ("ok", json.dumps({"login": "octo"}))
        out = _mod().probe_tree("acme", "lib", "v9")
        assert (out["cause"], out["account"]) == ("repo-not-found", "octo")
        assert not any(probe == "api" for probe, _key in script.calls)

    @pytest.mark.parametrize("lookup", ["network", "timeout", "forbidden"])
    def test_gh_repo_lookup_without_an_answer_falls_back_to_the_api(self, script, lookup):
        """gh answered 404 for the tree but not for the repository: the anonymous API still decides."""
        script.gh[_tree_path("v9")] = ("not-found",)
        script.gh[REPO] = (lookup,)
        script.api[_tree_path("v9")] = ("not-found",)
        script.api[REPO] = ("ok", "{}")
        out = _mod().probe_tree("acme", "lib", "v9")
        assert (out["status"], out["cause"]) == ("unavailable", "ref-not-found")
        assert [(probe, key) for probe, key in script.calls if probe == "api"] == [
            ("api", _tree_path("v9")), ("api", REPO)]

    def test_a_tree_404_alone_is_no_missing_repository(self, script):
        """A 404 for a tree may be a missing ref: with nothing else answering, it is unreachable."""
        script.gh[_tree_path("v9")] = ("not-found",)
        script.gh[REPO] = ("timeout",)
        script.api[_tree_path("v9")] = ("network",)
        out = _mod().probe_tree("acme", "lib", "v9")
        assert (out["status"], out["cause"]) == ("unavailable", "unreachable")
        assert all(r["target"] != "owner" for r in out["probes"])

    @pytest.mark.parametrize("gh", ["missing", "unauthenticated"])
    def test_unauthenticated_tree_api_fallback(self, script, gh):
        script.gh[_tree_path()] = (gh,)
        script.api[_tree_path()] = ("ok", _tree_json())
        out = _mod().probe_tree("acme", "lib", "HEAD")
        assert (out["status"], out["via"], out["gh"]) == ("ok", "api", gh)

    def test_missing_ref_through_the_api(self, script):
        script.gh[_tree_path("v9")] = ("missing",)
        script.api[_tree_path("v9")] = ("not-found",)
        script.api[REPO] = ("ok", "{}")
        assert _mod().probe_tree("acme", "lib", "v9")["cause"] == "ref-not-found"

    def test_private_repo_without_gh(self, script):
        script.gh[_tree_path()] = ("missing",)
        script.api[_tree_path()] = ("not-found",)
        script.api[REPO] = ("not-found",)
        script.api[OWNER] = ("ok", "{}")
        out = _mod().probe_tree("acme", "lib", "HEAD")
        assert (out["status"], out["cause"], out["tree"], out["count"]) == ("unavailable", "gh-missing", [], 0)

    def test_invalid_ref_runs_no_probe(self, script):
        out = _mod().probe_tree("acme", "lib", "-x")
        assert (out["status"], out["cause"], script.calls) == ("unavailable", "ref-not-found", [])

    def test_output_pipes_into_detect_language(self, script):
        script.gh[_tree_path()] = ("ok", _tree_json())
        out = _mod().probe_tree("acme", "lib", "HEAD")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "skf-detect-language.py")], input=json.dumps(out),
                              capture_output=True, text=True, check=True)
        assert json.loads(proc.stdout)["language"] == "javascript"


# --------------------------------------------------------------------------
# Every cause is reachable
# --------------------------------------------------------------------------


def test_every_cause_is_reported_somewhere(script):
    mod = _mod()
    seen = set()
    script.gh.update({REPO: ("forbidden",), OWNER: ("ok", "{}"), "user": ("ok", "{}")})
    script.api[REPO] = ("not-found",)
    script.git["repo"] = ("not-found",)
    seen.add(mod.probe_repo("acme", "lib")["cause"])
    script.gh[REPO] = ("not-found",)
    seen.add(mod.probe_repo("acme", "lib")["cause"])
    for gh in ("missing", "unauthenticated"):
        script.gh[REPO] = (gh,)
        script.api.update({REPO: ("not-found",), OWNER: ("ok", "{}")})
        script.git["repo"] = ("auth-required",)
        seen.add(mod.probe_repo("acme", "lib")["cause"])
    script.api[REPO] = ("network",)
    script.git["repo"] = ("network",)
    seen.add(mod.probe_repo("acme", "lib")["cause"])
    script.gh.update({_tree_path("v9"): ("not-found",), REPO: ("ok", "{}")})
    seen.add(mod.probe_tree("acme", "lib", "v9")["cause"])
    assert mod.main(["repo", "--repo", "not a repo"]) == 3
    seen.add("invalid-repo")
    assert seen == set(mod.CAUSES)


# --------------------------------------------------------------------------
# _gh against a fake gh
# --------------------------------------------------------------------------


FAKE_GH = """#!{python}
import json, os, sys, time
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
mode = os.environ["FAKE_GH_MODE"]
if mode == "ok":
    print(json.dumps({{"private": False, "default_branch": "main"}}))
    sys.exit(0)
if mode == "logged-out":
    print("To get started with GitHub CLI, please run:  gh auth login", file=sys.stderr)
    print("Alternatively, populate the GH_TOKEN environment variable.", file=sys.stderr)
    sys.exit(4)
if mode == "hang":
    time.sleep(30)
    sys.exit(0)
if mode == "offline":
    print("error connecting to api.github.com", file=sys.stderr)
    sys.exit(1)
code, message = mode.split(":", 1)
print(json.dumps({{"message": message}}))
print(f"gh: {{message}} (HTTP {{code}})", file=sys.stderr)
sys.exit(1)
"""


@pytest.fixture
def fake_gh(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("the fake gh is a POSIX script")
    folder = tmp_path / "bin"
    folder.mkdir()
    gh = folder / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
    gh.chmod(0o755)
    log = tmp_path / "gh.log"
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    _mod()._start_clock(None)

    def run(mode: str, *args: str):
        monkeypatch.setenv("FAKE_GH_MODE", mode)
        return _mod()._gh(*args)

    return SimpleNamespace(run=run, log=log)


class TestGhCall:
    def test_ok_and_argv(self, fake_gh):
        result, out, detail = fake_gh.run("ok", "repos/acme/lib")
        assert (result, json.loads(out)["default_branch"], detail) == ("ok", "main", "")
        argv = json.loads(fake_gh.log.read_text(encoding="utf-8").splitlines()[-1])
        assert argv == ["api", "--hostname", "github.com", "repos/acme/lib"]

    @pytest.mark.parametrize("mode, result", [
        ("logged-out", "unauthenticated"),
        ("401:Bad credentials", "unauthenticated"),
        ("404:Not Found", "not-found"),
        ("403:Resource protected by organization SAML enforcement.", "forbidden"),
        ("403:API rate limit exceeded for user ID 1.", "rate-limited"),
        ("429:Too Many Requests", "rate-limited"),
        ("502:Bad Gateway", "network"),
        ("offline", "network"),
    ])
    def test_failures(self, fake_gh, mode, result):
        got, out, detail = fake_gh.run(mode, "repos/acme/lib")
        assert (got, out) == (result, "")
        assert detail

    def test_logged_out_detail(self, fake_gh):
        assert fake_gh.run("logged-out", "user")[2] == "gh is not logged in"

    def test_a_hanging_gh_is_stopped(self, fake_gh, monkeypatch):
        monkeypatch.setattr(_mod(), "PROBE_TIMEOUT_SEC", 1.0)
        result, _out, detail = fake_gh.run("hang", "repos/acme/lib")
        assert result == "timeout" and "1 seconds" in detail

    def test_no_time_left(self, fake_gh):
        _mod()._start_clock(0)
        assert fake_gh.run("ok", "user")[0] == "timeout"
        assert not fake_gh.log.exists()

    def test_missing_gh(self, monkeypatch):
        monkeypatch.setattr(_mod()._sibling(), "_resolve_outside_cwd", lambda _name: None)
        assert _mod()._gh("user") == ("missing", "", "gh is not installed")


# --------------------------------------------------------------------------
# _api against a local server
# --------------------------------------------------------------------------


class _Handler(http.server.BaseHTTPRequestHandler):
    routes: dict = {}

    def do_GET(self):  # noqa: N802 - http.server's name
        code, headers, body = self.routes.get(self.path, (404, {}, '{"message": "Not Found"}'))
        self.send_response(code)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *_args):
        pass


@pytest.fixture
def api_server(monkeypatch):
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    routes: dict = {}
    handler = type("Handler", (_Handler,), {"routes": routes})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(_mod(), "API_ROOT", f"http://127.0.0.1:{server.server_address[1]}")
    _mod()._start_clock(None)
    yield routes
    server.shutdown()
    server.server_close()


class TestApiCall:
    def test_ok(self, api_server):
        api_server["/repos/acme/lib"] = (200, {"Content-Type": "application/json"}, '{"private": false}')
        result, body, detail = _mod()._api("repos/acme/lib")
        assert (result, json.loads(body), detail) == ("ok", {"private": False}, "")

    @pytest.mark.parametrize("code, headers, body, result", [
        (404, {}, '{"message": "Not Found"}', "not-found"),
        (403, {}, '{"message": "API rate limit exceeded for 1.2.3.4."}', "rate-limited"),
        (403, {"X-RateLimit-Remaining": "0"}, "{}", "rate-limited"),
        (429, {}, "{}", "rate-limited"),
        (403, {}, '{"message": "Forbidden"}', "forbidden"),
        (451, {}, '{"message": "Repository access blocked"}', "forbidden"),
        (500, {}, "{}", "network"),
    ])
    def test_errors(self, api_server, code, headers, body, result):
        api_server["/repos/acme/lib"] = (code, headers, body)
        got, out, detail = _mod()._api("repos/acme/lib")
        assert (got, out) == (result, "")
        assert f"HTTP {code}" in detail

    def test_closed_port_is_network(self, monkeypatch):
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        monkeypatch.setattr(_mod(), "API_ROOT", f"http://127.0.0.1:{port}")
        _mod()._start_clock(None)
        assert _mod()._api("repos/acme/lib")[0] == "network"

    def test_repo_probe_end_to_end(self, api_server, monkeypatch):
        """gh missing, the API reads a public repository."""
        api_server["/repos/acme/lib"] = (200, {}, '{"private": false, "default_branch": "main"}')
        _no_gh(monkeypatch)
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["via"], out["gh"]) == ("ok", "api", "missing")


# --------------------------------------------------------------------------
# _git against a scratch upstream
# --------------------------------------------------------------------------


def _no_gh(monkeypatch) -> None:
    """gh is not installed; git still resolves."""
    tree = _mod()._sibling()
    real = tree._resolve_outside_cwd
    monkeypatch.setattr(tree, "_resolve_outside_cwd", lambda name: None if name == "gh" else real(name))


def _g(cwd, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in _mod()._sibling().GIT_LOCATION_VARS}
    proc = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          capture_output=True, text=True, env=env, check=True)
    return proc.stdout.strip()


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    """https://github.com/acme/lib served from a local bare repository; gh missing."""
    work, bare = tmp_path / "work", tmp_path / "up.git"
    work.mkdir()
    _g(work, "init", "-q", "-b", "trunk")
    (work / "a.txt").write_text("a\n", encoding="utf-8")
    _g(work, "add", "a.txt")
    _g(work, "commit", "-q", "-m", "one")
    _g(work, "tag", "v1.0.0")
    _g(work, "tag", "-a", "v1.1.0", "-m", "v1.1.0")
    _g(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    config = tmp_path / "gitconfig"
    session = os.environ.get("GIT_CONFIG_GLOBAL")
    text = f'[include]\n\tpath = "{Path(session).as_posix()}"\n' if session else ""
    text += f'[url "{bare.as_uri()}"]\n\tinsteadOf = https://github.com/acme/lib\n'
    config.write_text(text, encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    _no_gh(monkeypatch)
    monkeypatch.setattr(_mod(), "_api", lambda path: ("not-found", "", f"HTTP 404 from {path}"))
    _mod()._start_clock(None)
    return SimpleNamespace(work=work, bare=bare, commit=_g(work, "rev-parse", "HEAD"))


class TestGitCall:
    def test_tags_through_git_when_gh_is_missing(self, upstream):
        out = _mod().probe_tags("acme", "lib", ["1.1.0", "v1.1.0"], 20)
        assert (out["status"], out["via"], out["gh"]) == ("ok", "git", "missing")
        assert out["tags"] == ["v1.1.0", "v1.0.0"]
        assert (out["match"], out["found"]) == ("v1.1.0", {"v1.1.0": upstream.commit})

    def test_repo_through_git(self, upstream):
        out = _mod().probe_repo("acme", "lib")
        assert (out["status"], out["via"], out["default_branch"], out["private"]) == ("ok", "git", "trunk", True)

    def test_git_ignores_an_exported_git_dir(self, upstream, monkeypatch, tmp_path):
        decoy = tmp_path / "decoy"
        decoy.mkdir()
        _g(decoy, "init", "-q")
        monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
        assert _mod().probe_tags("acme", "lib", [], 20)["count"] == 2

    @pytest.mark.parametrize("stderr, result", [
        ("remote: Repository not found.\nfatal: repository 'https://github.com/a/b/' not found", "not-found"),
        ("fatal: could not read Username for 'https://github.com': terminal prompts disabled", "auth-required"),
        ("fatal: Authentication failed for 'https://github.com/a/b/'", "auth-required"),
        ("fatal: unable to access 'https://github.com/a/b/': The requested URL returned error: 401",
         "auth-required"),
        ("remote: Permission to a/b.git denied to octo.\nfatal: unable to access 'https://github.com/a/b/': "
         "The requested URL returned error: 403", "forbidden"),
        ("remote: The 'a' organization has enabled or enforced SAML SSO.\nfatal: unable to access", "forbidden"),
        ("fatal: unable to access 'https://github.com/a/b/': Could not resolve host: github.com", "network"),
        ("fatal: unable to access 'https://github.com/a/b/': Failed to connect to github.com port 443", "network"),
    ])
    def test_classify_git(self, stderr, result):
        assert _mod()._classify_git(stderr) == result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class TestCli:
    COMMON = {"status", "cause", "message", "repo", "gh", "account", "via", "probes"}

    @pytest.mark.parametrize("argv, extra", [
        (["repo"], {"private", "default_branch"}),
        (["tags", "--want", "v1"], {"tags", "count", "match", "found", "missing", "nearest"}),
        (["tree", "--ref", "v1"], {"ref", "tree", "count", "truncated"}),
    ])
    def test_invalid_repo(self, argv, extra):
        proc = subprocess.run([sys.executable, str(HELPER), *argv, "--repo", "https://gitlab.com/a/b"],
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 3, proc.stderr
        assert proc.stdout.count("\n") == 1 and proc.stdout.isascii()
        out = json.loads(proc.stdout)
        assert set(out) == self.COMMON | extra
        assert (out["status"], out["cause"], out["repo"], out["gh"], out["probes"]) == (
            "unavailable", "invalid-repo", None, "not-run", [])
        if argv[0] == "tree":
            assert out["ref"] == "v1"
        if argv[0] == "tags":
            assert out["missing"] == []

    def test_invalid_repo_reports_a_null_ref_as_head(self):
        argv = ["tree", "--ref", "null", "--repo", "gitlab.com/a/b"]
        proc = subprocess.run([sys.executable, str(HELPER), *argv], capture_output=True, text=True, check=False)
        assert proc.returncode == 3, proc.stderr
        assert json.loads(proc.stdout)["ref"] == "HEAD"

    def test_every_command_prints_every_key(self, script, capsys):
        script.gh.update({REPO: ("ok", '{"private": false, "default_branch": "main"}'),
                          TAGS: ("ok", _gh_tags([("v1", SHA_A)])), _tree_path(): ("ok", _tree_json())})
        mod = _mod()
        for argv, extra in (("repo", {"private", "default_branch"}),
                            ("tags", {"tags", "count", "match", "found", "missing", "nearest"}),
                            ("tree", {"ref", "tree", "count", "truncated"})):
            assert mod.main([argv, "--repo", "acme/lib"]) == 0
            line = capsys.readouterr().out
            assert line.count("\n") == 1
            assert set(json.loads(line)) == self.COMMON | extra

    def test_tags_takes_a_version_and_a_name(self, script, capsys):
        script.gh[TAGS] = ("ok", _gh_tags([("pkg@1.2.0", SHA_A), ("pkg@1.1.0", SHA_B)]))
        assert _mod().main(["tags", "--repo", "acme/lib", "--version", "1.2.0", "--name", "pkg", "--limit", "5"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert (out["match"], out["nearest"]) == ("pkg@1.2.0", ["pkg@1.2.0", "pkg@1.1.0"])

    def test_unavailable_exits_3(self, script, capsys):
        script.gh[REPO] = ("forbidden",)
        script.api[REPO] = ("not-found",)
        script.git["repo"] = ("forbidden",)
        assert _mod().main(["repo", "--repo", "acme/lib"]) == 3
        assert json.loads(capsys.readouterr().out)["cause"] == "no-access"

    def test_usage_errors_exit_2(self):
        for argv in ([], ["repo"], ["bogus", "--repo", "a/b"], ["tags", "--repo", "a/b", "--limit", "x"]):
            proc = subprocess.run([sys.executable, str(HELPER), *argv], capture_output=True, text=True, check=False)
            assert proc.returncode == 2, argv

    def test_unexpected_error_is_one_json_line(self, monkeypatch, capsys):
        def boom(*_args):
            raise RuntimeError("boom")

        monkeypatch.setattr(_mod(), "probe_repo", boom)
        assert _mod().main(["repo", "--repo", "acme/lib"]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err) == {"status": "error", "message": "RuntimeError: boom"}

    def test_vocabularies_match_the_docstring(self):
        mod = _mod()
        doc = mod.__doc__
        for name, label in (("CAUSES", "cause    null |"), ("GH_STATES", "gh       "),
                            ("PROBE_RESULTS", "result is")):
            end = doc.index(f"({name})")
            start = doc.rindex(label, 0, end)
            assert tuple(re.findall(r'"([a-z-]+)"', doc[start + len(label):end])) == getattr(mod, name), name


# --------------------------------------------------------------------------
# The sibling skf-source-tree.py and the script itself
# --------------------------------------------------------------------------


class TestScript:
    def test_loads_the_source_tree_beside_it(self):
        sibling = _mod()._sibling()
        assert Path(sibling.__file__).resolve() == SOURCE_TREE.resolve()
        assert _mod()._sibling() is sibling

    def test_without_its_sibling_a_probe_is_an_error(self, tmp_path):
        lone = tmp_path / "skf-github-probe.py"
        lone.write_bytes(HELPER.read_bytes())
        proc = subprocess.run([sys.executable, str(lone), "repo", "--repo", "acme/lib", "--timeout", "5"],
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 1 and proc.stdout == ""
        assert json.loads(proc.stderr)["status"] == "error"

    def test_without_the_resolver_beside_it_a_probe_is_an_error(self, tmp_path):
        """--repo is read with skf-resolve-package.py's grammar, so the probe needs it too."""
        for script in (HELPER, SOURCE_TREE):
            (tmp_path / script.name).write_bytes(script.read_bytes())
        proc = subprocess.run([sys.executable, str(tmp_path / HELPER.name), "repo", "--repo", "acme/lib",
                               "--timeout", "5"], capture_output=True, text=True, check=False)
        assert proc.returncode == 1 and proc.stdout == ""
        assert "skf-resolve-package.py" in json.loads(proc.stderr)["message"]

    def test_script_header(self):
        head = HELPER.read_text(encoding="utf-8").splitlines()[:4]
        assert head == ["# /// script", '# requires-python = ">=3.11"', "# dependencies = []", "# ///"]

    def test_git_runs_from_the_temp_folder_without_hooks(self, tmp_path, monkeypatch):
        """git never runs in the caller's repository, whose config it would read."""
        calls = []

        def record(argv, timeout):
            calls.append(argv)
            return 0, b"", b"", False

        monkeypatch.setattr(_mod()._sibling(), "_run", record)
        monkeypatch.chdir(tmp_path)
        _mod()._start_clock(None)
        _mod()._git("ls-remote", "--tags", "--", "https://github.com/acme/lib")
        assert calls and calls[0][calls[0].index("-C") + 1] == tempfile.gettempdir()
        assert f"core.hooksPath={os.devnull}" in calls[0]
