#!/usr/bin/env python3
"""Tests for skf-validate-pins.py.

Pure-function tests for pin validation logic, plus subprocess tests
to verify CLI wiring (argparse, stdout JSON, exit codes).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-validate-pins.py"
)

spec = importlib.util.spec_from_file_location("skf_validate_pins", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REPO_URL = "https://github.com/example/repo"


# --------------------------------------------------------------------------
# assert_result_shape helper
# --------------------------------------------------------------------------

def assert_result_shape(result: Dict[str, Any]) -> None:
    assert set(result.keys()) >= {
        "status", "pin", "resolved_ref", "ref_type", "version", "suggestions",
    }, f"Missing keys in output: {result}"
    assert result["status"] in ("valid", "invalid", "resolved")
    assert result["ref_type"] in ("tag", "branch", None)
    assert isinstance(result["suggestions"], list)


# --------------------------------------------------------------------------
# Mock helpers
# --------------------------------------------------------------------------

SAMPLE_TAGS = [
    "v1.0.0", "v1.1.0", "v1.2.0", "v2.0.0", "v2.0.1",
    "v2.1.0", "v3.0.0-beta.1",
]

SAMPLE_TAGS_WITH_PREFIXES = SAMPLE_TAGS + [
    "repo@1.0.0", "repo/v1.0.0", "repo-v1.0.0",
]


def _make_gh_mock(tags: Optional[List[str]] = None, latest_release: Optional[str] = None):
    """Return a side_effect for subprocess.run that mocks gh/git calls."""
    if tags is None:
        tags = SAMPLE_TAGS

    def side_effect(cmd, **kwargs):
        result = MagicMock()
        if cmd[0] == "gh":
            if cmd[1] == "--version":
                result.returncode = 0
                result.stdout = "gh version 2.0.0"
                return result
            if cmd[1] == "api":
                endpoint = cmd[2]
                if "releases/latest" in endpoint:
                    if latest_release:
                        result.returncode = 0
                        result.stdout = latest_release
                    else:
                        result.returncode = 1
                        result.stdout = ""
                    return result
                if "/tags" in endpoint:
                    result.returncode = 0
                    result.stdout = "\n".join(tags)
                    return result
        if cmd[0] == "git":
            if cmd[1] == "ls-remote":
                if "--heads" in cmd:
                    branch = cmd[-1]
                    if branch == "main":
                        result.returncode = 0
                        result.stdout = f"abc123\trefs/heads/{branch}"
                        return result
                    if branch == "develop":
                        result.returncode = 0
                        result.stdout = f"def456\trefs/heads/{branch}"
                        return result
                    result.returncode = 0
                    result.stdout = ""
                    return result
                if "--tags" in cmd:
                    tag_lines = [f"abc123\trefs/tags/{t}" for t in tags]
                    result.returncode = 0
                    result.stdout = "\n".join(tag_lines)
                    return result
        result.returncode = 1
        result.stdout = ""
        return result
    return side_effect


def _make_unreachable_mock():
    """Mock where all gh/git calls fail."""
    def side_effect(cmd, **kwargs):
        result = MagicMock()
        if cmd[0] == "gh" and cmd[1] == "--version":
            result.returncode = 0
            result.stdout = "gh version 2.0.0"
            return result
        result.returncode = 1
        result.stdout = ""
        result.stderr = "network error"
        return result
    return side_effect


# --------------------------------------------------------------------------
# extract_version tests
# --------------------------------------------------------------------------

class TestExtractVersion:
    def test_semver_tag(self):
        assert mod.extract_version("v2.0.0") == "2.0.0"

    def test_semver_no_prefix(self):
        assert mod.extract_version("1.2.3") == "1.2.3"

    def test_prerelease(self):
        assert mod.extract_version("v3.0.0-beta.1") == "3.0.0-beta.1"

    def test_non_semver(self):
        assert mod.extract_version("main") is None

    def test_non_semver_text(self):
        assert mod.extract_version("release-candidate") is None


# --------------------------------------------------------------------------
# match_tag tests
# --------------------------------------------------------------------------

class TestMatchTag:
    def test_exact_match(self):
        result = mod.match_tag("v2.0.0", SAMPLE_TAGS, "example", "repo")
        assert result == "v2.0.0"

    def test_v_prefix_match(self):
        result = mod.match_tag("2.0.0", SAMPLE_TAGS, "example", "repo")
        assert result == "v2.0.0"

    def test_package_scope_match(self):
        tags = SAMPLE_TAGS + ["repo@2.0.0"]
        result = mod.match_tag("2.0.0", tags, "example", "repo")
        assert result == "v2.0.0"

    def test_package_scope_only(self):
        tags = ["repo@2.0.0"]
        result = mod.match_tag("2.0.0", tags, "example", "repo")
        assert result == "repo@2.0.0"

    def test_crate_prefix_slash_v(self):
        tags = ["repo/v2.0.0"]
        result = mod.match_tag("2.0.0", tags, "example", "repo")
        assert result == "repo/v2.0.0"

    def test_crate_prefix_slash(self):
        tags = ["repo/2.0.0"]
        result = mod.match_tag("2.0.0", tags, "example", "repo")
        assert result == "repo/2.0.0"

    def test_crate_prefix_dash_v(self):
        tags = ["repo-v2.0.0"]
        result = mod.match_tag("2.0.0", tags, "example", "repo")
        assert result == "repo-v2.0.0"

    def test_no_match(self):
        result = mod.match_tag("v99.0.0", SAMPLE_TAGS, "example", "repo")
        assert result is None


# --------------------------------------------------------------------------
# generate_suggestions tests
# --------------------------------------------------------------------------

class TestGenerateSuggestions:
    def test_prefix_match(self):
        suggestions = mod.generate_suggestions("v2", SAMPLE_TAGS)
        assert len(suggestions) <= 5
        assert all(s.startswith("v2") for s in suggestions)

    def test_no_prefix_match_returns_recent(self):
        suggestions = mod.generate_suggestions("v99", SAMPLE_TAGS)
        assert len(suggestions) <= 5
        assert len(suggestions) > 0

    def test_empty_tags(self):
        suggestions = mod.generate_suggestions("v1.0.0", [])
        assert suggestions == []

    def test_max_count(self):
        many_tags = [f"v1.0.{i}" for i in range(20)]
        suggestions = mod.generate_suggestions("v1", many_tags, max_count=5)
        assert len(suggestions) == 5


# --------------------------------------------------------------------------
# validate_pin tests — valid semver tag
# --------------------------------------------------------------------------

class TestValidSemverTag:
    @patch("subprocess.run")
    def test_valid_tag(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="v2.0.0")
        assert_result_shape(result)
        assert result["status"] == "valid"
        assert result["resolved_ref"] == "v2.0.0"
        assert result["ref_type"] == "tag"
        assert result["version"] == "2.0.0"

    @patch("subprocess.run")
    def test_valid_v_prefixed_tag(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="2.0.0")
        assert_result_shape(result)
        assert result["status"] == "valid"
        assert result["resolved_ref"] == "v2.0.0"
        assert result["ref_type"] == "tag"
        assert result["version"] == "2.0.0"


# --------------------------------------------------------------------------
# validate_pin tests — valid branch name
# --------------------------------------------------------------------------

class TestValidBranch:
    @patch("subprocess.run")
    def test_valid_branch(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="main")
        assert_result_shape(result)
        assert result["status"] == "valid"
        assert result["resolved_ref"] == "main"
        assert result["ref_type"] == "branch"
        assert result["version"] is None


# --------------------------------------------------------------------------
# validate_pin tests — invalid pin with suggestions
# --------------------------------------------------------------------------

class TestInvalidPin:
    @patch("subprocess.run")
    def test_invalid_pin(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="v99.0.0")
        assert_result_shape(result)
        assert result["status"] == "invalid"
        assert result["resolved_ref"] is None
        assert len(result["suggestions"]) > 0

    @patch("subprocess.run")
    def test_invalid_pin_with_prefix_suggestions(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="v2.9.9")
        assert_result_shape(result)
        assert result["status"] == "invalid"
        assert any(s.startswith("v2") for s in result["suggestions"])


# --------------------------------------------------------------------------
# validate_pin tests — latest release resolution (no --pin)
# --------------------------------------------------------------------------

class TestLatestRelease:
    @patch("subprocess.run")
    def test_latest_release(self, mock_run):
        mock_run.side_effect = _make_gh_mock(latest_release="v3.0.0")
        result = mod.validate_pin(REPO_URL, pin=None)
        assert_result_shape(result)
        assert result["status"] == "resolved"
        assert result["resolved_ref"] == "v3.0.0"
        assert result["ref_type"] == "tag"
        assert result["version"] == "3.0.0"
        assert result["pin"] is None

    @patch("subprocess.run")
    def test_no_releases_fallback_to_tags(self, mock_run):
        mock_run.side_effect = _make_gh_mock(tags=["v1.0.0"], latest_release=None)
        result = mod.validate_pin(REPO_URL, pin=None)
        assert_result_shape(result)
        assert result["status"] == "resolved"
        assert result["resolved_ref"] == "v1.0.0"

    @patch("subprocess.run")
    def test_no_releases_no_tags(self, mock_run):
        mock_run.side_effect = _make_gh_mock(tags=[], latest_release=None)
        result = mod.validate_pin(REPO_URL, pin=None)
        assert_result_shape(result)
        assert result["status"] == "invalid"
        assert result["pin"] is None


# --------------------------------------------------------------------------
# validate_pin tests — error handling (unreachable repo)
# --------------------------------------------------------------------------

class TestErrorHandling:
    @patch("subprocess.run")
    def test_unreachable_repo(self, mock_run):
        mock_run.side_effect = _make_unreachable_mock()
        result = mod.validate_pin(REPO_URL, pin="v1.0.0")
        assert_result_shape(result)
        assert result["status"] == "invalid"

    def test_invalid_url(self):
        result = mod.validate_pin("not-a-github-url", pin="v1.0.0")
        assert_result_shape(result)
        assert result["status"] == "invalid"


# --------------------------------------------------------------------------
# validate_pin tests — format filter
# --------------------------------------------------------------------------

class TestFormatFilter:
    @patch("subprocess.run")
    def test_tag_only(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="main", format_filter="tag")
        assert result["status"] == "invalid"

    @patch("subprocess.run")
    def test_branch_only(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        result = mod.validate_pin(REPO_URL, pin="v2.0.0", format_filter="branch")
        assert result["status"] == "invalid"


# --------------------------------------------------------------------------
# CLI subprocess tests
# --------------------------------------------------------------------------

class TestCLI:
    @patch("subprocess.run")
    def test_cli_main_valid_pin(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        with patch("sys.argv", ["skf-validate-pins.py", "--repo-url", REPO_URL, "--pin", "v2.0.0"]):
            import io
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                exit_code = mod.main()
        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert_result_shape(output)
        assert output["status"] == "valid"
        assert output["resolved_ref"] == "v2.0.0"

    @patch("subprocess.run")
    def test_cli_main_invalid_pin(self, mock_run):
        mock_run.side_effect = _make_gh_mock()
        with patch("sys.argv", ["skf-validate-pins.py", "--repo-url", REPO_URL, "--pin", "v99.0.0"]):
            import io
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                exit_code = mod.main()
        assert exit_code == 1
        output = json.loads(captured.getvalue())
        assert_result_shape(output)
        assert output["status"] == "invalid"

    def test_cli_missing_repo_url(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
