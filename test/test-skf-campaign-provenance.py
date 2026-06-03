"""Tests for campaign-provenance.py — repo access + commit SHA recording.

The gh calls are exercised through an injected runner so the suite needs
neither network nor an authenticated `gh`. Tests pin the URL parsing (the
fragile string-munge that used to live in step-04 prose), the accessible /
inaccessible aggregation, and the systemic-failure root-cause collapse (E-5).
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


def _ok_runner(args):
    """Every gh call succeeds; default branch = main, sha = deadbeef."""
    if args[1] == "repo" and "defaultBranchRef" in args:
        return 0, "main\n", ""
    if args[1] == "repo":
        return 0, "", ""
    if args[1] == "api":
        return 0, "deadbeef\n", ""
    return 0, "", ""


def _auth_fail_runner(args):
    return 1, "", "gh auth: not logged into any GitHub hosts"


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
            if args[3] == "o/bad" if len(args) > 3 else False:
                return 1, "", "404 not found"
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
        # not systemic — only one failed
        assert out["systemic_hint"] is None

    def test_systemic_auth_failure_collapses(self, tmp_path, capsys):
        sf, bf = _write(
            tmp_path,
            skills=[{"name": "a", "status": "pending", "tier": "A", "pin": "v1"},
                    {"name": "b", "status": "pending", "tier": "A", "pin": "v1"}],
            targets=[{"name": "a", "repo_url": "https://github.com/o/a"},
                     {"name": "b", "repo_url": "https://github.com/o/b"}],
        )
        rc = mod.run(str(sf), str(bf), runner=_auth_fail_runner)
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["inaccessible_count"] == 2
        assert out["systemic_hint"] is not None
        assert "auth" in out["systemic_hint"].lower()

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
