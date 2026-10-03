"""Tests for campaign-provenance.py: repo access and commit SHA recording.

The gh calls are exercised through an injected runner so the suite needs
neither network nor an authenticated `gh`. Tests pin the URL parsing (the
fragile string-munge that used to live in step-04 prose), the accessible /
inaccessible aggregation, the systemic-failure root-cause hint (E-5), and the
error classes, each from the stderr and exit code gh 2.101.0 really prints
for that failure (GH_STDERR below).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-provenance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("campaign_provenance", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


class TestParseOwnerRepo:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/octocat/Hello-World", ("octocat", "Hello-World")),
            ("https://github.com/octocat/Hello-World.git", ("octocat", "Hello-World")),
            ("https://github.com/octocat/Hello-World/", ("octocat", "Hello-World")),
            ("git@github.com:octocat/Hello-World.git", ("octocat", "Hello-World")),
            ("octocat/Hello-World", ("octocat", "Hello-World")),
            ("http://gitlab.example.com/grp/proj", ("grp", "proj")),
        ],
    )
    def test_parses(self, url, expected):
        assert mod.parse_owner_repo(url) == expected

    @pytest.mark.parametrize("bad", ["", "justonename", None, "   "])
    def test_unparseable_returns_none(self, bad):
        assert mod.parse_owner_repo(bad) is None


def _write(tmp_path, skills, targets):
    state = {
        "campaign": {
            "name": "c",
            "started_at": "2026-05-27T00:00:00Z",
            "last_updated": "2026-05-27T00:00:00Z",
            "current_stage": 3,
            "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80},
            "health_findings_queue": "local",
        },
        "skills": skills,
        "dependency_graph": {"execution_order": [], "circular_deps_detected": False},
    }
    brief = {"targets": targets}
    sf = tmp_path / "_campaign-state.yaml"
    bf = tmp_path / "campaign-brief.yaml"
    sf.write_text(yaml.dump(state), encoding="utf-8")
    bf.write_text(yaml.dump(brief), encoding="utf-8")
    return sf, bf


# What gh 2.101.0 prints on stderr, with its exit code, for each failure class
# of a `gh api repos/...` call (captured from real runs; the request ids of the
# rate-limit and SAML messages trimmed).
GH_STDERR = {
    "unauthenticated": (4, "To get started with GitHub CLI, please run:  gh auth login\n"
                           "Alternatively, populate the GH_TOKEN environment variable with a GitHub API "
                           "authentication token.\n"),
    "bad-credentials": (1, "gh: Bad credentials (HTTP 401)\n"),
    "not-found": (1, "gh: Not Found (HTTP 404)\n"),
    "no-such-ref": (1, "gh: No commit found for SHA: nope (HTTP 422)\n"),
    "rate-limited": (1, "gh: API rate limit exceeded for user ID 1234567. If you reach out to GitHub Support "
                        "for help, please include the request ID 0000:0000:0000000:0000000:00000000. (HTTP 403)\n"),
    "secondary-rate-limit": (1, "gh: You have exceeded a secondary rate limit. Please wait a few minutes "
                                "before you try again. (HTTP 429)\n"),
    "forbidden": (1, "gh: Resource protected by organization SAML enforcement. You must grant your "
                     "Personal Access token access to this organization. (HTTP 403)\n"),
    "network": (1, "error connecting to api.github.com\ncheck your internet connection or "
                   "https://githubstatus.com\n"),
}
EXPECTED_CLASS = {
    "unauthenticated": "unauthenticated",
    "bad-credentials": "unauthenticated",
    "not-found": "not-found",
    "no-such-ref": "not-found",
    "rate-limited": "rate-limited",
    "secondary-rate-limit": "rate-limited",
    "forbidden": "forbidden",
    "network": "network",
}


def _ok_runner(args):
    """Every gh call succeeds; default branch = main, sha = deadbeef."""
    assert args[:2] == ["gh", "api"], args
    if "/commits/" in args[2]:
        return 0, "deadbeef\n", ""
    return 0, "main\n", ""


def _failing_runner(case):
    rc, err = GH_STDERR[case]
    return lambda args: (rc, "", err)


class TestClassifyError:
    @pytest.mark.parametrize("case", sorted(GH_STDERR))
    def test_real_gh_stderr_lands_in_its_class(self, case):
        rc, err = GH_STDERR[case]
        assert mod._classify_error(rc, err) == EXPECTED_CLASS[case]

    def test_repository_that_does_not_exist_is_not_a_network_failure(self):
        # gh repo view's GraphQL message; the script asks REST, which says 404.
        assert mod._classify_error(1, GH_STDERR["not-found"][1]) == "not-found"

    def test_every_systemic_class_has_a_hint(self):
        assert set(mod._SYSTEMIC_HINTS) == {"unauthenticated", "rate-limited", "forbidden", "network"}
        for hint in mod._SYSTEMIC_HINTS.values():
            assert "campaign resume" in hint
            assert "\u2014" not in hint


class TestRun:
    def test_all_accessible_exit_0(self, tmp_path, capsys):
        sf, bf = _write(
            tmp_path,
            skills=[{"name": "a", "status": "pending", "tier": "A", "pin": None},
                    {"name": "b", "status": "pending", "tier": "A", "pin": "v1.0.0"}],
            targets=[{"name": "a", "repo_url": "https://github.com/o/a"},
                     {"name": "b", "repo_url": "https://github.com/o/b.git"}],
        )
        rc = mod.run(str(sf), str(bf), runner=_ok_runner)
        assert rc == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["all_accessible"] is True
        assert out["inaccessible_count"] == 0
        by_name = {r["name"]: r for r in out["results"]}
        assert by_name["a"]["commit_sha"] == "deadbeef"
        assert by_name["a"]["ref"] == "main"          # resolved default branch
        assert by_name["b"]["ref"] == "v1.0.0"         # pin used directly
        assert by_name["a"]["owner"] == "o"

    def test_one_inaccessible_exit_1(self, tmp_path, capsys):
        def runner(args):
            if args[2].startswith("repos/o/bad"):
                return GH_STDERR["not-found"][0], "", GH_STDERR["not-found"][1]
            return _ok_runner(args)

        sf, bf = _write(
            tmp_path,
            skills=[{"name": "good", "status": "pending", "tier": "A", "pin": "v1"},
                    {"name": "bad", "status": "pending", "tier": "A", "pin": "v1"}],
            targets=[{"name": "good", "repo_url": "https://github.com/o/good"},
                     {"name": "bad", "repo_url": "https://github.com/o/bad"}],
        )
        rc = mod.run(str(sf), str(bf), runner=runner)
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["all_accessible"] is False
        assert out["inaccessible_count"] == 1
        # not systemic: only one failed
        assert out["systemic_hint"] is None
        bad = next(r for r in out["results"] if r["name"] == "bad")
        assert bad["error"] == "gh: Not Found (HTTP 404)"
        assert bad["error_class"] == "not-found"

    @pytest.mark.parametrize("case", ["unauthenticated", "rate-limited", "forbidden", "network"])
    def test_systemic_failure_adds_one_hint_and_keeps_each_error(self, tmp_path, capsys, case):
        sf, bf = _write(
            tmp_path,
            skills=[{"name": "a", "status": "pending", "tier": "A", "pin": "v1"},
                    {"name": "b", "status": "pending", "tier": "A", "pin": "v1"}],
            targets=[{"name": "a", "repo_url": "https://github.com/o/a"},
                     {"name": "b", "repo_url": "https://github.com/o/b"}],
        )
        rc = mod.run(str(sf), str(bf), runner=_failing_runner(case))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["inaccessible_count"] == 2
        assert out["systemic_hint"] == mod._SYSTEMIC_HINTS[case]
        for result in out["results"]:
            assert result["error"] == GH_STDERR[case][1].strip()
            assert result["error_class"] == case

    def test_every_repo_missing_gives_no_hint(self, tmp_path, capsys):
        # Two missing repositories share a class, but no single fix covers them.
        sf, bf = _write(
            tmp_path,
            skills=[{"name": "a", "status": "pending", "tier": "A", "pin": "v1"},
                    {"name": "b", "status": "pending", "tier": "A", "pin": "v1"}],
            targets=[{"name": "a", "repo_url": "https://github.com/o/a"},
                     {"name": "b", "repo_url": "https://github.com/o/b"}],
        )
        rc = mod.run(str(sf), str(bf), runner=_failing_runner("not-found"))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["systemic_hint"] is None
        assert {r["error_class"] for r in out["results"]} == {"not-found"}

    def test_one_rest_call_reads_access_and_default_branch(self, tmp_path, capsys):
        calls = []

        def runner(args):
            calls.append(args)
            return _ok_runner(args)

        sf, bf = _write(
            tmp_path,
            skills=[{"name": "a", "status": "pending", "tier": "A", "pin": None}],
            targets=[{"name": "a", "repo_url": "https://github.com/o/a"}],
        )
        assert mod.run(str(sf), str(bf), runner=runner) == 0
        assert calls == [
            ["gh", "api", "repos/o/a", "--jq", ".default_branch"],
            ["gh", "api", "repos/o/a/commits/main", "--jq", ".sha"],
        ]

    def test_missing_repo_url_in_brief(self, tmp_path, capsys):
        sf, bf = _write(
            tmp_path,
            skills=[{"name": "orphan", "status": "pending", "tier": "A", "pin": None}],
            targets=[],
        )
        rc = mod.run(str(sf), str(bf), runner=_ok_runner)
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["results"][0]["status"] == "inaccessible"
        assert "repo_url" in out["results"][0]["error"]

    def test_missing_state_file_exit_2(self, tmp_path, capsys):
        _, bf = _write(tmp_path, skills=[], targets=[])
        rc = mod.run(str(tmp_path / "missing.yaml"), str(bf), runner=_ok_runner)
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "STATE_NOT_FOUND"

    def test_missing_brief_file_exit_2(self, tmp_path, capsys):
        sf, _ = _write(tmp_path, skills=[], targets=[])
        rc = mod.run(str(sf), str(tmp_path / "missing.yaml"), runner=_ok_runner)
        assert rc == 2
        err = json.loads(capsys.readouterr().err.strip())
        assert err["code"] == "BRIEF_NOT_FOUND"


class TestMalformedBrief:
    """A brief target with no name or no repo_url is invalid input, not an inaccessible repository."""

    @pytest.mark.parametrize(
        ("targets", "error"),
        [
            ([{"repo_url": "https://github.com/o/a"}], "Brief target 1 has no name"),
            ([{"name": "a"}], "Brief target 1 (a) has no repo_url"),
            ([{"name": "a", "repo_url": None}], "Brief target 1 (a) has no repo_url"),
            ([{"name": "a", "repo_url": "https://github.com/o/a"}, {"name": " "}],
             "Brief target 2 has no name and no repo_url"),
            ([None], "Brief target 1 is not a mapping"),
        ],
        ids=["no-name", "no-repo-url", "null-repo-url", "second-target-blank", "not-a-mapping"],
    )
    def test_target_without_name_or_repo_url_exit_2(self, tmp_path, capsys, targets, error):
        sf, bf = _write(tmp_path, skills=[{"name": "a", "status": "pending", "tier": "A", "pin": None}],
                        targets=targets)
        rc = mod.run(str(sf), str(bf), runner=_ok_runner)
        assert rc == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err.strip()) == {"error": error, "code": "INVALID_BRIEF"}

    def test_brief_that_is_no_mapping_exit_2(self, tmp_path, capsys):
        sf, bf = _write(tmp_path, skills=[], targets=[])
        bf.write_bytes(b"")
        rc = mod.run(str(sf), str(bf), runner=_ok_runner)
        assert rc == 2
        assert json.loads(capsys.readouterr().err.strip())["code"] == "INVALID_BRIEF"
