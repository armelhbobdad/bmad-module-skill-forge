#!/usr/bin/env python3
"""Tests for skf-detect-docs.py.

Pure-function tests for each detection method, plus subprocess tests
to verify CLI wiring (argparse, stdout JSON, exit codes).
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-detect-docs.py"
)

spec = importlib.util.spec_from_file_location("skf_detect_docs", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REPO_URL = "https://github.com/example/repo"

_VALID_DETECTED_VIA = {"homepageUrl", "readme_link", "pages_api", "docs_folder"}


# --------------------------------------------------------------------------
# assert_result_shape helper (subtask 2.2)
# --------------------------------------------------------------------------

def assert_result_shape(entry: Dict[str, Any]) -> None:
    assert set(entry.keys()) >= {
        "url", "detected_via", "content_hash", "content_type",
    }, f"Missing keys in output entry: {entry}"
    assert isinstance(entry["url"], str) and entry["url"]
    assert entry["detected_via"] in _VALID_DETECTED_VIA, (
        f"Invalid detected_via: {entry['detected_via']}"
    )
    assert entry["content_hash"] is None or (
        isinstance(entry["content_hash"], str)
        and entry["content_hash"].startswith("sha256:")
    ), f"Invalid content_hash: {entry['content_hash']}"
    assert entry["content_type"] in {"api-docs", "guide", "reference"}, (
        f"Invalid content_type: {entry['content_type']}"
    )


# --------------------------------------------------------------------------
# Mock helpers
# --------------------------------------------------------------------------

def _make_gh_mock(responses: Dict[str, str]):
    """Return a side_effect for subprocess.run that mocks gh api calls."""
    def side_effect(cmd, **kwargs):
        result = MagicMock()
        if cmd[0] == "gh":
            if cmd[1] == "--version":
                result.returncode = 0
                result.stdout = "gh version 2.0.0"
                return result
            if cmd[1] == "api":
                endpoint = cmd[2]
                jq_arg = None
                if "--jq" in cmd:
                    jq_idx = cmd.index("--jq")
                    jq_arg = cmd[jq_idx + 1]
                key = endpoint
                if key in responses:
                    result.returncode = 0
                    result.stdout = responses[key]
                    return result
                result.returncode = 1
                result.stdout = ""
                return result
        result.returncode = 1
        result.stdout = ""
        return result
    return side_effect


def _make_readme_content(markdown_text: str) -> str:
    """Build a JSON response matching GitHub's readme API."""
    encoded = base64.b64encode(markdown_text.encode("utf-8")).decode("ascii")
    return json.dumps({"content": encoded, "encoding": "base64"})


def _null_hash(url: str):
    return None


# --------------------------------------------------------------------------
# Tests: homepageUrl detection (subtask 2.4)
# --------------------------------------------------------------------------

class TestDetectHomepageUrl:
    def test_homepage_url_detected(self):
        responses = {
            "repos/example/repo": "https://docs.example.com",
            "repos/example/repo/readme": "",
            "repos/example/repo/contents/docs": "",
        }
        with patch.object(mod, "_run_gh", side_effect=lambda args: responses.get(args[1], None)):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)
        assert len(results) >= 1
        homepage_entries = [r for r in results if r["detected_via"] == "homepageUrl"]
        assert len(homepage_entries) == 1
        assert homepage_entries[0]["url"] == "https://docs.example.com"
        assert_result_shape(homepage_entries[0])

    def test_homepage_url_empty_skipped(self):
        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)
        assert not any(r["detected_via"] == "homepageUrl" for r in results)

    def test_homepage_url_self_referencing_skipped(self):
        with patch.object(mod, "_run_gh", side_effect=lambda args: (
            "https://github.com/example/repo" if "readme" not in args[1] and "contents" not in args[1] and "pages" not in args[1]
            else None
        )):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)
        assert not any(r["detected_via"] == "homepageUrl" for r in results)


# --------------------------------------------------------------------------
# Tests: README link scanning (subtask 2.4)
# --------------------------------------------------------------------------

class TestDetectReadmeLinks:
    def test_readme_doc_links_detected(self):
        readme_md = (
            "# My Project\n\n"
            "Check out the [Documentation](https://docs.example.com/guide)\n"
            "And the [API Reference](https://docs.example.com/api/v1)\n"
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        assert len(readme_entries) >= 1
        for entry in readme_entries:
            assert_result_shape(entry)

    def test_readme_rejects_badge_and_ci_links(self):
        readme_md = (
            "# Project\n\n"
            "[![Build](https://img.shields.io/badge/build-passing.svg)](https://github.com/example/repo/actions)\n"
            "[Docs](https://docs.example.com)\n"
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        urls = [r["url"] for r in readme_entries]
        assert "https://docs.example.com" in urls
        assert not any("shields.io" in u for u in urls)
        assert not any("/actions" in u for u in urls)

    def test_readme_rejects_package_registry_links(self):
        readme_md = (
            "[npm](https://www.npmjs.com/package/foo)\n"
            "[PyPI](https://pypi.org/project/foo)\n"
            "[Docs](https://docs.foo.dev)\n"
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        urls = [r["url"] for r in readme_entries]
        assert not any("npmjs.com" in u for u in urls)
        assert not any("pypi.org" in u for u in urls)
        assert "https://docs.foo.dev" in urls


# --------------------------------------------------------------------------
# Tests: Pages API detection (subtask 2.4)
# --------------------------------------------------------------------------

class TestDetectPagesApi:
    def test_pages_detected(self):
        def gh_side(args):
            if "pages" in args[1]:
                return "https://example.github.io/repo"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL)

        pages_entries = [r for r in results if r["detected_via"] == "pages_api"]
        assert len(pages_entries) == 1
        assert pages_entries[0]["url"] == "https://example.github.io/repo"
        assert_result_shape(pages_entries[0])

    def test_pages_404_returns_empty(self):
        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL)
        pages_entries = [r for r in results if r["detected_via"] == "pages_api"]
        assert len(pages_entries) == 0


# --------------------------------------------------------------------------
# Tests: docs/ folder detection (subtask 2.4)
# --------------------------------------------------------------------------

class TestDetectDocsFolder:
    def test_docs_folder_via_api(self):
        docs_response = json.dumps([
            {"name": "getting-started.md", "download_url": "https://raw.githubusercontent.com/example/repo/main/docs/getting-started.md"},
            {"name": "api.md", "download_url": "https://raw.githubusercontent.com/example/repo/main/docs/api.md"},
            {"name": "image.png", "download_url": "https://raw.githubusercontent.com/example/repo/main/docs/image.png"},
        ])

        def gh_side(args):
            if "contents/docs" in args[1]:
                return docs_response
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 2
        urls = [r["url"] for r in docs_entries]
        assert any("getting-started.md" in u for u in urls)
        assert any("api.md" in u for u in urls)
        assert not any("image.png" in u for u in urls)
        for entry in docs_entries:
            assert_result_shape(entry)

    def test_docs_folder_local_path(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "intro.md").write_text("# Intro", encoding="utf-8")
        (docs_dir / "guide.md").write_text("# Guide", encoding="utf-8")
        (docs_dir / "notes.txt").write_text("not md", encoding="utf-8")

        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, local_path=str(tmp_path), skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 2
        urls = [r["url"] for r in docs_entries]
        assert all(u.startswith("file://") for u in urls)
        for entry in docs_entries:
            assert_result_shape(entry)


# --------------------------------------------------------------------------
# Tests: changelog/migration exclusion (subtask 2.5)
# --------------------------------------------------------------------------

class TestLanguageDocRecall:
    """Widened recall (issue #427): a `doc.` subdomain and language
    reference/guide path segments are doc URLs, so a language repo's canonical
    corpora (the Book, std/library docs) are detected from its README."""

    def test_doc_subdomain_accepted(self):
        # `doc.rust-lang.org` (singular) was missed by the old `docs\.` rule.
        assert mod._is_doc_url("https://doc.rust-lang.org/book/")
        assert mod._is_doc_url("https://doc.rust-lang.org/std/")
        assert mod._is_doc_url("https://doc.rust-lang.org/reference/")

    def test_language_path_segments_accepted(self):
        assert mod._is_doc_url("https://docs.python.org/3/tutorial/")
        assert mod._is_doc_url("https://docs.python.org/3/library/")
        assert mod._is_doc_url("https://example.org/book/")

    def test_near_miss_still_rejected(self):
        # Widening must not start accepting arbitrary product/marketing URLs.
        assert not mod._is_doc_url("https://rust-lang.org/")
        assert not mod._is_doc_url("https://example.com/blog/2026/new-release")
        assert not mod._is_doc_url("https://github.com/rust-lang/rust")

    def test_widening_does_not_break_rejects(self):
        # A badge/CI URL that happens to contain a doc-ish word stays rejected.
        assert not mod._is_doc_url("https://img.shields.io/badge/docs-passing.svg")


class TestExclusionFilter:
    def test_changelog_excluded(self):
        readme_md = (
            "[Docs](https://docs.example.com)\n"
            "[Changelog](https://docs.example.com/CHANGELOG.md)\n"
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        urls = [r["url"] for r in results]
        assert "https://docs.example.com" in urls
        assert not any("CHANGELOG" in u for u in urls)

    def test_migration_guide_excluded(self):
        readme_md = (
            "[Docs](https://docs.example.com)\n"
            "[Migration](https://docs.example.com/MIGRATION.md)\n"
            "[Upgrade](https://docs.example.com/UPGRADE.md)\n"
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        urls = [r["url"] for r in results]
        assert not any("MIGRATION" in u for u in urls)
        assert not any("UPGRADE" in u for u in urls)

    def test_non_corpus_segments_not_excluded_by_detector(self):
        # The detector is shape-agnostic: /whatsnew/, /contribute, /wiki/ are
        # NOT in _EXCLUSION_PATTERNS, so they stay detected here. Suppressing
        # them for whole-language references is the brief-layer merge's job
        # (skf-merge-doc-urls.py, issue #431) — pushing it down to the detector
        # would wrongly strip those pages for ordinary skills. This guard pins
        # that layering decision.
        for url in (
            "https://docs.example.com/whatsnew/",
            "https://docs.example.com/contribute",
            "https://docs.example.com/wiki/Questions",
        ):
            assert not mod._is_excluded(url), url
        assert mod._is_doc_url("https://docs.example.com/wiki/Questions")


# --------------------------------------------------------------------------
# Tests: empty results → exit 1 (subtask 2.6)
# --------------------------------------------------------------------------

class TestEmptyResults:
    def test_all_methods_find_nothing(self):
        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL)
        assert results == []


# --------------------------------------------------------------------------
# Tests: --local-path for docs/ folder (subtask 2.7)
# --------------------------------------------------------------------------

class TestLocalPath:
    def test_local_path_uses_filesystem(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "readme.md").write_text("# Hello", encoding="utf-8")

        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, local_path=str(tmp_path), skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 1
        assert docs_entries[0]["url"].startswith("file://")

    def test_local_path_no_docs_dir(self, tmp_path):
        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, local_path=str(tmp_path), skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 0


# --------------------------------------------------------------------------
# Tests: --skip-pages-api (subtask 2.8)
# --------------------------------------------------------------------------

class TestSkipPagesApi:
    def test_skip_pages_api_flag(self):
        def gh_side(args):
            if "pages" in args[1]:
                return "https://example.github.io/repo"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        pages_entries = [r for r in results if r["detected_via"] == "pages_api"]
        assert len(pages_entries) == 0


# --------------------------------------------------------------------------
# Tests: URL deduplication (subtask 2.9)
# --------------------------------------------------------------------------

class TestDeduplication:
    def test_same_url_from_multiple_methods_deduped(self):
        readme_md = "[Docs](https://docs.example.com)\n"
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            endpoint = args[1]
            if endpoint == f"repos/example/repo":
                return "https://docs.example.com"
            if "readme" in endpoint:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        urls = [r["url"] for r in results]
        assert urls.count("https://docs.example.com") == 1
        winner = [r for r in results if r["url"] == "https://docs.example.com"][0]
        assert winner["detected_via"] == "homepageUrl"


# --------------------------------------------------------------------------
# Tests: network error graceful degradation (subtask 2.10)
# --------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_one_method_fails_others_continue(self):
        readme_md = "[Docs](https://docs.example.com)\n"
        readme_json = _make_readme_content(readme_md)

        call_count = {"n": 0}

        def gh_side(args):
            endpoint = args[1]
            if endpoint == f"repos/example/repo":
                return None
            if "readme" in endpoint:
                return readme_json
            if "pages" in endpoint:
                return None
            if "contents/docs" in endpoint:
                return None
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL)

        assert len(results) >= 1
        assert any(r["detected_via"] == "readme_link" for r in results)


# --------------------------------------------------------------------------
# Tests: subprocess CLI wiring (subtask 2.11)
# --------------------------------------------------------------------------

class TestSubprocessCli:
    def test_missing_repo_url_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_invalid_repo_url_exits_2(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", "not-a-github-url"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        err = json.loads(result.stderr.strip())
        assert err["code"] == "INVALID_URL"

    def test_valid_url_produces_json_stdout(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv = ['test', '--repo-url', 'https://github.com/example/repo', '--skip-pages-api']; "
             f"import importlib.util; "
             f"spec = importlib.util.spec_from_file_location('m', '{SCRIPT_PATH.as_posix()}'); "
             f"m = importlib.util.module_from_spec(spec); "
             f"spec.loader.exec_module(m); "
             f"m._run_gh = lambda args: 'https://docs.example.com' if args[1] == 'repos/example/repo' else None; "
             f"m._fetch_and_hash = lambda url: None; "
             f"raise SystemExit(m.main())"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        assert parsed[0]["url"] == "https://docs.example.com"


# --------------------------------------------------------------------------
# Tests: error handling (subtask 2.12)
# --------------------------------------------------------------------------

class TestErrorHandling:
    def test_invalid_url_format(self):
        with patch.object(mod, "_run_gh", return_value=None):
            results = mod.detect("https://gitlab.com/foo/bar")
        assert results == []

    def test_missing_owner_repo(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", "https://github.com/"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2


# --------------------------------------------------------------------------
# Tests: content type classification
# --------------------------------------------------------------------------

class TestContentTypeClassification:
    def test_api_docs_classification(self):
        assert mod._classify_content_type("https://example.com/api/v1") == "api-docs"
        assert mod._classify_content_type("https://api.example.com/docs") == "api-docs"

    def test_guide_classification(self):
        assert mod._classify_content_type("https://example.com/guide/intro") == "guide"
        assert mod._classify_content_type("https://example.com/getting-started") == "guide"
        assert mod._classify_content_type("https://example.com/tutorial/first") == "guide"

    def test_reference_fallback(self):
        assert mod._classify_content_type("https://docs.example.com") == "reference"
        assert mod._classify_content_type("https://example.com/docs/overview") == "reference"


# --------------------------------------------------------------------------
# Tests: content hashing
# --------------------------------------------------------------------------

class TestContentHashing:
    def test_local_file_hash(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_bytes(b"hello world")
        import hashlib
        expected = "sha256:" + hashlib.sha256(b"hello world").hexdigest()
        result = mod._fetch_and_hash("file://" + f.as_posix())
        assert result == expected

    def test_unreachable_url_returns_none(self):
        result = mod._fetch_and_hash("http://192.0.2.1/nonexistent")
        assert result is None


# --------------------------------------------------------------------------
# Tests: exclusion filter patterns
# --------------------------------------------------------------------------

class TestExclusionPatterns:
    @pytest.mark.parametrize("url", [
        "https://example.com/CHANGELOG.md",
        "https://example.com/changelog",
        "https://example.com/CHANGES.md",
        "https://example.com/MIGRATION.md",
        "https://example.com/UPGRADE.md",
        "https://example.com/CONTRIBUTING.md",
        "https://example.com/LICENSE",
        "https://example.com/SECURITY.md",
        "https://example.com/release-notes/v1",
        "https://example.com/releases",
    ])
    def test_excluded_urls(self, url):
        assert mod._is_excluded(url), f"Expected {url} to be excluded"

    @pytest.mark.parametrize("url", [
        "https://docs.example.com",
        "https://example.com/api/reference",
        "https://example.com/guide/intro",
    ])
    def test_non_excluded_urls(self, url):
        assert not mod._is_excluded(url), f"Expected {url} to NOT be excluded"


# --------------------------------------------------------------------------
# Gap: content hash integration through detect() pipeline
# --------------------------------------------------------------------------

class TestContentHashIntegration:
    def test_hash_flows_into_detect_results(self, tmp_path):
        """Verify _fetch_and_hash results propagate into detect() output."""
        import hashlib
        fake_content = b"documentation content"
        expected_hash = "sha256:" + hashlib.sha256(fake_content).hexdigest()

        def gh_side(args):
            if args[1] == "repos/example/repo":
                return "https://docs.example.com"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", return_value=expected_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        assert len(results) >= 1
        entry = results[0]
        assert entry["content_hash"] == expected_hash
        assert entry["content_hash"].startswith("sha256:")
        assert_result_shape(entry)

    def test_hash_null_on_fetch_failure(self):
        """Content hash is None when URL is unreachable, entry still present."""
        def gh_side(args):
            if args[1] == "repos/example/repo":
                return "https://docs.example.com"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", return_value=None):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        assert len(results) >= 1
        assert results[0]["content_hash"] is None
        assert_result_shape(results[0])


# --------------------------------------------------------------------------
# Gap: README HTML anchor tag detection
# --------------------------------------------------------------------------

class TestReadmeHtmlLinks:
    def test_html_anchor_doc_links_detected(self):
        readme_md = (
            '<p>See our <a href="https://docs.example.com/api/v2">API docs</a></p>\n'
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        assert len(readme_entries) >= 1
        assert any("docs.example.com/api/v2" in r["url"] for r in readme_entries)
        for entry in readme_entries:
            assert_result_shape(entry)


# --------------------------------------------------------------------------
# Gap: README bare URL detection
# --------------------------------------------------------------------------

class TestReadmeBareUrls:
    def test_bare_url_on_own_line_detected(self):
        readme_md = (
            "# My Project\n\n"
            "https://docs.example.com/reference/overview\n\n"
            "Some other text.\n"
        )
        readme_json = _make_readme_content(readme_md)

        def gh_side(args):
            if "readme" in args[1]:
                return readme_json
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        assert len(readme_entries) >= 1
        assert any("docs.example.com/reference/overview" in r["url"] for r in readme_entries)
        for entry in readme_entries:
            assert_result_shape(entry)


# --------------------------------------------------------------------------
# Gap: CLI exit code 0 (results found) and exit code 1 (none found)
# --------------------------------------------------------------------------

class TestCliExitCodes:
    def test_exit_code_1_when_no_results(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv = ['test', '--repo-url', 'https://github.com/example/repo', '--skip-pages-api']; "
             f"import importlib.util; "
             f"spec = importlib.util.spec_from_file_location('m', '{SCRIPT_PATH.as_posix()}'); "
             f"m = importlib.util.module_from_spec(spec); "
             f"spec.loader.exec_module(m); "
             f"m._run_gh = lambda args: None; "
             f"m._fetch_and_hash = lambda url: None; "
             f"raise SystemExit(m.main())"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        parsed = json.loads(result.stdout.strip())
        assert parsed == []

    def test_exit_code_2_on_invalid_url(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--repo-url", "https://not-github.com/x/y"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        err = json.loads(result.stderr.strip())
        assert err["code"] == "INVALID_URL"


# --------------------------------------------------------------------------
# Gap: multi-method aggregation (all 4 methods return results)
# --------------------------------------------------------------------------

class TestMultiMethodAggregation:
    def test_all_four_methods_contribute(self):
        readme_md = "[Guide](https://docs.example.com/guide/start)\n"
        readme_json = _make_readme_content(readme_md)
        docs_response = json.dumps([
            {"name": "usage.md", "download_url": "https://raw.githubusercontent.com/example/repo/main/docs/usage.md"},
        ])

        def gh_side(args):
            endpoint = args[1]
            if endpoint == "repos/example/repo":
                return "https://homepage.example.com"
            if "readme" in endpoint:
                return readme_json
            if "pages" in endpoint:
                return "https://example.github.io/repo"
            if "contents/docs" in endpoint:
                return docs_response
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL)

        detected_methods = {r["detected_via"] for r in results}
        assert "homepageUrl" in detected_methods
        assert "readme_link" in detected_methods
        assert "pages_api" in detected_methods
        assert "docs_folder" in detected_methods
        for entry in results:
            assert_result_shape(entry)


# --------------------------------------------------------------------------
# Gap: nested docs/ subdirectories via local path (rglob behavior)
# --------------------------------------------------------------------------

class TestNestedDocsFolder:
    def test_local_path_recurses_subdirectories(self, tmp_path):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "overview.md").write_text("# Overview", encoding="utf-8")
        nested = docs_dir / "api"
        nested.mkdir()
        (nested / "endpoints.md").write_text("# Endpoints", encoding="utf-8")
        deep = nested / "v2"
        deep.mkdir()
        (deep / "schema.md").write_text("# Schema", encoding="utf-8")

        with patch.object(mod, "_run_gh", return_value=None):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, local_path=str(tmp_path), skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 3
        urls = [r["url"] for r in docs_entries]
        assert any("overview.md" in u for u in urls)
        assert any("endpoints.md" in u for u in urls)
        assert any("schema.md" in u for u in urls)
        for entry in docs_entries:
            assert_result_shape(entry)


# --------------------------------------------------------------------------
# Gap: gh CLI not found → exit 2 with structured error
# --------------------------------------------------------------------------

class TestGhCliNotFound:
    def test_gh_not_found_exits_2(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv = ['test', '--repo-url', 'https://github.com/a/b']; "
             f"import importlib.util; "
             f"spec = importlib.util.spec_from_file_location('m', '{SCRIPT_PATH.as_posix()}'); "
             f"m = importlib.util.module_from_spec(spec); "
             f"spec.loader.exec_module(m); "
             f"m._check_gh_available = lambda: False; "
             f"raise SystemExit(m.main())"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        err = json.loads(result.stderr.strip())
        assert err["code"] == "GH_NOT_FOUND"


# --------------------------------------------------------------------------
# Gap: README API with missing content field
# --------------------------------------------------------------------------

class TestReadmeEdgeCases:
    def test_readme_missing_content_field(self):
        def gh_side(args):
            if "readme" in args[1]:
                return json.dumps({"encoding": "base64"})
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        assert len(readme_entries) == 0

    def test_readme_invalid_json_response(self):
        def gh_side(args):
            if "readme" in args[1]:
                return "not-json{"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        readme_entries = [r for r in results if r["detected_via"] == "readme_link"]
        assert len(readme_entries) == 0


# --------------------------------------------------------------------------
# Gap: docs/ API returning non-list JSON (file, not directory)
# --------------------------------------------------------------------------

class TestDocsFolderEdgeCases:
    def test_docs_api_non_list_response(self):
        """GitHub returns a single object when docs/ is a file, not a directory."""
        def gh_side(args):
            if "contents/docs" in args[1]:
                return json.dumps({"name": "docs", "type": "file"})
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 0

    def test_docs_api_invalid_json(self):
        def gh_side(args):
            if "contents/docs" in args[1]:
                return "not-json{"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        docs_entries = [r for r in results if r["detected_via"] == "docs_folder"]
        assert len(docs_entries) == 0


# --------------------------------------------------------------------------
# Gap: _is_doc_url with doc text on non-doc domain
# --------------------------------------------------------------------------

class TestDocUrlTextClassification:
    def test_link_text_triggers_doc_detection(self):
        assert mod._is_doc_url("https://example.com/foo", "Read the documentation")
        assert mod._is_doc_url("https://example.com/bar", "API reference")

    def test_link_text_alone_not_enough_if_rejected_domain(self):
        assert not mod._is_doc_url("https://img.shields.io/badge/docs-passing", "documentation")


# --------------------------------------------------------------------------
# Gap: homepage "null" string explicitly handled
# --------------------------------------------------------------------------

class TestHomepageNullString:
    def test_homepage_null_string_skipped(self):
        def gh_side(args):
            if args[1] == "repos/example/repo":
                return "null"
            return None

        with patch.object(mod, "_run_gh", side_effect=gh_side):
            with patch.object(mod, "_fetch_and_hash", side_effect=_null_hash):
                results = mod.detect(REPO_URL, skip_pages_api=True)

        assert not any(r["detected_via"] == "homepageUrl" for r in results)
