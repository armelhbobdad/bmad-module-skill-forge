#!/usr/bin/env python3
"""Tests for skf-resolve-package.py.

Network is mocked at the _http_get_json layer so the tests stay offline
and deterministic. The script's own _http_get_json error-classification
is not exercised here (it is thin glue around urllib + json); tests
focus on the GitHub-URL parser, registry-payload parsers, and the
overall resolve-package fallback behaviour.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_resolve_package",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-resolve-package.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestParseGithubUrl:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("https://github.com/lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("http://github.com/lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("github.com/lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            (
                "git+https://github.com/lodash/lodash.git",
                ("https://github.com/lodash/lodash", "lodash", "lodash"),
            ),
            (
                "git@github.com:lodash/lodash.git",
                ("https://github.com/lodash/lodash", "lodash", "lodash"),
            ),
            ("github:lodash/lodash", ("https://github.com/lodash/lodash", "lodash", "lodash")),
            ("https://github.com/scope-name/pkg.git", ("https://github.com/scope-name/pkg", "scope-name", "pkg")),
            ("https://github.com/owner/repo/", ("https://github.com/owner/repo", "owner", "repo")),
        ],
    )
    def test_recognized_variants(self, raw, expected):
        assert mod.parse_github_url(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not-a-url",
            "https://example.com/foo",
            "https://gitlab.com/owner/repo",
            "https://bitbucket.org/owner/repo",
            "ftp://github.com/owner/repo",  # only http/https
        ],
    )
    def test_rejects_non_github(self, raw):
        assert mod.parse_github_url(raw) is None

    def test_handles_none_and_non_string(self):
        assert mod.parse_github_url(None) is None  # type: ignore[arg-type]
        assert mod.parse_github_url(42) is None  # type: ignore[arg-type]


class TestRegistryPayloadParsers:
    """Each try_* function calls _http_get_json then extracts a GitHub URL.
    Tests monkeypatch the HTTP fetch and assert the correct candidate-field
    priority and outcome reporting.
    """

    def _patch_http(self, monkeypatch, payload, outcome="ok"):
        monkeypatch.setattr(mod, "_http_get_json", lambda url, timeout: (payload, outcome))

    def test_npm_repository_object(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": {"url": "git+https://github.com/lodash/lodash.git"}})
        result, outcome = mod.try_npm("lodash", 5)
        assert result == ("https://github.com/lodash/lodash", "lodash", "lodash")
        assert outcome == "ok"

    def test_npm_repository_string_shortcut(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": "github:lodash/lodash"})
        result, outcome = mod.try_npm("lodash", 5)
        assert result == ("https://github.com/lodash/lodash", "lodash", "lodash")
        assert outcome == "ok"

    def test_npm_falls_back_to_homepage(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {"repository": "https://example.com/not-github", "homepage": "https://github.com/owner/repo"},
        )
        result, _ = mod.try_npm("foo", 5)
        assert result == ("https://github.com/owner/repo", "owner", "repo")

    def test_npm_no_github_link(self, monkeypatch):
        self._patch_http(monkeypatch, {"repository": "https://example.com/x", "homepage": "https://example.com/y"})
        result, outcome = mod.try_npm("foo", 5)
        assert result is None
        assert outcome == "no-github-link"

    def test_npm_404(self, monkeypatch):
        self._patch_http(monkeypatch, None, outcome="404")
        result, outcome = mod.try_npm("foo", 5)
        assert result is None
        assert outcome == "404"

    def test_pypi_project_urls_priority(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {
                "info": {
                    "project_urls": {
                        "Homepage": "https://example.com/docs",
                        "Source": "https://github.com/psf/requests",
                        "Repository": "https://github.com/psf/requests-mirror",
                    },
                    "home_page": "https://example.com/old",
                },
            },
        )
        result, _ = mod.try_pypi("requests", 5)
        assert result == ("https://github.com/psf/requests", "psf", "requests")

    def test_pypi_falls_back_to_home_page(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {
                "info": {
                    "project_urls": {"Documentation": "https://example.com/docs"},
                    "home_page": "https://github.com/owner/repo",
                },
            },
        )
        result, _ = mod.try_pypi("foo", 5)
        assert result == ("https://github.com/owner/repo", "owner", "repo")

    def test_pypi_no_github_link(self, monkeypatch):
        self._patch_http(
            monkeypatch,
            {"info": {"project_urls": {"Homepage": "https://example.com/x"}, "home_page": "https://example.com/y"}},
        )
        result, outcome = mod.try_pypi("foo", 5)
        assert result is None
        assert outcome == "no-github-link"

    def test_crates_repository(self, monkeypatch):
        self._patch_http(monkeypatch, {"crate": {"repository": "https://github.com/serde-rs/serde"}})
        result, _ = mod.try_crates("serde", 5)
        assert result == ("https://github.com/serde-rs/serde", "serde-rs", "serde")

    def test_crates_falls_back_to_homepage(self, monkeypatch):
        self._patch_http(monkeypatch, {"crate": {"homepage": "https://github.com/owner/repo"}})
        result, _ = mod.try_crates("foo", 5)
        assert result == ("https://github.com/owner/repo", "owner", "repo")


class TestResolvePackage:
    def test_first_registry_wins(self, monkeypatch):
        def fake_npm(name, t):
            return ("https://github.com/lodash/lodash", "lodash", "lodash"), "ok"

        def fake_pypi(name, t):
            raise AssertionError("pypi must not be called once npm resolved")

        monkeypatch.setattr(mod, "try_npm", fake_npm)
        monkeypatch.setattr(mod, "try_pypi", fake_pypi)
        result = mod.resolve_package("lodash")
        assert result["status"] == "ok"
        assert result["registry_used"] == "npm"
        assert result["registries_tried"] == ["npm"]
        assert result["registry_outcomes"] == {"npm": "ok"}

    def test_falls_through_to_pypi(self, monkeypatch):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "404"))
        monkeypatch.setattr(
            mod, "try_pypi", lambda n, t: (("https://github.com/psf/requests", "psf", "requests"), "ok")
        )
        result = mod.resolve_package("requests")
        assert result["status"] == "ok"
        assert result["registry_used"] == "pypi"
        assert result["registries_tried"] == ["npm", "pypi"]
        assert result["registry_outcomes"] == {"npm": "404", "pypi": "ok"}

    def test_falls_through_all_registries(self, monkeypatch):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "404"))
        monkeypatch.setattr(mod, "try_pypi", lambda n, t: (None, "404"))
        monkeypatch.setattr(mod, "try_crates", lambda n, t: (None, "404"))
        result = mod.resolve_package("nonexistent")
        assert result["status"] == "fallthrough"
        assert "resolved_url" not in result
        assert result["registries_tried"] == ["npm", "pypi", "crates"]
        assert result["registry_outcomes"] == {"npm": "404", "pypi": "404", "crates": "404"}

    def test_records_timeouts_in_outcomes(self, monkeypatch):
        monkeypatch.setattr(mod, "try_npm", lambda n, t: (None, "timeout"))
        monkeypatch.setattr(mod, "try_pypi", lambda n, t: (None, "no-github-link"))
        monkeypatch.setattr(
            mod, "try_crates", lambda n, t: (("https://github.com/serde-rs/serde", "serde-rs", "serde"), "ok")
        )
        result = mod.resolve_package("serde")
        assert result["status"] == "ok"
        assert result["registry_used"] == "crates"
        assert result["registry_outcomes"] == {"npm": "timeout", "pypi": "no-github-link", "crates": "ok"}


class TestCli:
    def test_cli_ok_exit_zero(self, monkeypatch, capsys):
        monkeypatch.setattr(
            mod,
            "resolve_package",
            lambda name, timeout: {
                "status": "ok",
                "package_name": name,
                "resolved_url": "https://github.com/o/r",
                "repo_owner": "o",
                "repo_name": "r",
                "registry_used": "npm",
                "registries_tried": ["npm"],
                "registry_outcomes": {"npm": "ok"},
            },
        )
        rc = mod.main(["lodash"])
        assert rc == 0
        out = capsys.readouterr().out
        assert '"status": "ok"' in out

    def test_cli_fallthrough_exit_one(self, monkeypatch, capsys):
        monkeypatch.setattr(
            mod,
            "resolve_package",
            lambda name, timeout: {
                "status": "fallthrough",
                "package_name": name,
                "registries_tried": ["npm", "pypi", "crates"],
                "registry_outcomes": {"npm": "404", "pypi": "404", "crates": "404"},
            },
        )
        rc = mod.main(["nonexistent"])
        assert rc == 1
        out = capsys.readouterr().out
        assert '"status": "fallthrough"' in out
