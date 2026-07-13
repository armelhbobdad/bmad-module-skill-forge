#!/usr/bin/env python3
"""Tests for skf-skill-inventory.py."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import importlib.util
import pytest

spec = importlib.util.spec_from_file_location(
    "skf_skill_inventory",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-skill-inventory.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
scan_inventory = mod.scan_inventory
normalize_url = mod.normalize_url
derive_name = mod.derive_name
compute_matches = mod.compute_matches


def _link_active(active_link: Path, version: str) -> None:
    """Create active->version link with Windows junction fallback.

    Mirrors src/shared/scripts/skf-atomic-write.py — symlink first, junction
    via `mklink /J` when the symlink privilege isn't held. Junctions need an
    existing absolute target directory.
    """
    try:
        active_link.symlink_to(version)
        return
    except OSError as e:
        if os.name != "nt" or getattr(e, "winerror", None) not in (1314, 5):
            raise
        abs_target = (active_link.parent / version).resolve()
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(active_link), str(abs_target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise OSError(
                f"junction fallback failed: {result.stderr.strip() or result.stdout.strip()}"
            ) from e


def make_skill(skills_dir, name, version="1.0.0", with_metadata=True, with_provenance=False,
               source_repo=None):
    """Create a mock skill with versioned directory structure."""
    skill_group = skills_dir / name
    version_dir = skill_group / version / name
    version_dir.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md
    (version_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n# {name}\n", encoding="utf-8")

    if with_metadata:
        meta = {
            "name": name,
            "version": version,
            "language": "TypeScript",
            "source_authority": "community",
            "source_repo": source_repo if source_repo is not None else f"https://github.com/test/{name}",
            "generated_by": "create-skill",
            "confidence_tier": "Forge",
            "stats": {"exports_total": 10},
        }
        (version_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    if with_provenance:
        (version_dir / "provenance-map.json").write_text("{}", encoding="utf-8")

    # Create active symlink (junction on Windows w/o Dev Mode)
    active_link = skill_group / "active"
    if active_link.is_symlink():
        active_link.unlink()
    elif active_link.is_dir():
        active_link.rmdir()
    elif active_link.exists():
        active_link.unlink()
    _link_active(active_link, version)

    return skill_group


class TestSkfSkillInventory:
    """Tests for the skf-skill-inventory scan_inventory function."""

    @pytest.fixture()
    def skills_dir(self):
        """Provide a temporary skills directory."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "skills"
            d.mkdir()
            yield d

    def test_empty_directory(self, skills_dir):
        result = scan_inventory(str(skills_dir))
        assert result["status"] == "ok"
        assert result["summary"]["total_skills"] == 0

    def test_single_versioned_skill(self, skills_dir):
        make_skill(skills_dir, "cocoindex", "2.1.0", with_provenance=True)
        result = scan_inventory(str(skills_dir))
        assert result["status"] == "ok"
        assert result["summary"]["total_skills"] == 1
        s = result["skills"][0]
        assert s["name"] == "cocoindex"
        assert s["active_version"] == "2.1.0"
        assert s["has_skill_md"] is True
        assert s["has_provenance_map"] is True
        assert s["metadata"]["language"] == "TypeScript"
        assert s["metadata"]["exports_total"] == 10

    def test_multiple_skills(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0")
        make_skill(skills_dir, "vue", "3.0.0")
        make_skill(skills_dir, "svelte", "4.0.0", with_metadata=False)
        result = scan_inventory(str(skills_dir))
        assert result["summary"]["total_skills"] == 3
        assert result["summary"]["with_metadata"] == 2

    def test_filter_by_name(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0")
        make_skill(skills_dir, "vue", "3.0.0")
        result = scan_inventory(str(skills_dir), skill_filter="vue")
        assert result["summary"]["total_skills"] == 1
        assert result["skills"][0]["name"] == "vue"

    def test_filter_nonexistent(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0")
        result = scan_inventory(str(skills_dir), skill_filter="angular")
        assert result["status"] == "error"
        assert result["code"] == "SKILL_NOT_FOUND"
        assert "react" in result["available"]

    def test_nonexistent_directory(self):
        result = scan_inventory("/tmp/nonexistent-skf-dir-12345")
        assert result["status"] == "error"
        assert result["code"] == "DIR_NOT_FOUND"

    def test_with_export_manifest(self, skills_dir):
        make_skill(skills_dir, "cocoindex", "2.0.0")
        manifest = {"exports": {"cocoindex": {"active_version": "2.0.0"}}}
        (skills_dir / ".export-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        result = scan_inventory(str(skills_dir))
        assert result["manifest"] is not None
        assert "cocoindex" in result["manifest"]["exports"]

    def test_no_matches_key_without_flag(self, skills_dir):
        """The additive matches[] key is absent unless --match-target is used."""
        make_skill(skills_dir, "react", "18.0.0")
        result = scan_inventory(str(skills_dir))
        assert "matches" not in result


class TestNormalizeUrl:
    """Unit tests for the URL/path normalization helper."""

    def test_strips_scheme_git_and_trailing_slash(self):
        assert normalize_url("https://github.com/Foo/Bar.git/") == "github.com/foo/bar"

    def test_idempotent(self):
        once = normalize_url("HTTP://GitHub.com/Foo/Bar.git")
        assert once == "github.com/foo/bar"
        assert normalize_url(once) == once

    def test_bare_repo_unchanged(self):
        assert normalize_url("github.com/foo/bar") == "github.com/foo/bar"

    def test_empty_and_none(self):
        assert normalize_url("") == ""
        assert normalize_url(None) == ""


class TestDeriveName:
    """Unit tests for the expected-skill-name derivation."""

    def test_last_path_segment(self):
        assert derive_name("github.com/x/bar-baz") == "bar-baz"

    def test_url_scheme_and_git_and_case(self):
        assert derive_name("https://github.com/Foo/Bar.git/") == "bar"

    def test_bare_doc_hostname_dots_to_hyphens(self):
        assert derive_name("docs.example.com") == "docs-example-com"

    def test_local_path(self):
        assert derive_name("/srv/code/my_project") == "my-project"

    def test_empty(self):
        assert derive_name("") == ""


class TestCoexistenceMatch:
    """Tests for the --match-target coexistence match set (matches[])."""

    @pytest.fixture()
    def skills_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "skills"
            d.mkdir()
            yield d

    def test_url_match_normalizes(self, skills_dir):
        """source_repo github.com/foo/bar matches a scheme/.git/slash/case-varied target.

        The skill is named ``legacy-bar`` (not the ``bar`` the target derives) so
        the hit fires on URL normalization alone, isolating the url reason.
        """
        make_skill(skills_dir, "legacy-bar", "1.0.0", source_repo="github.com/foo/bar")
        result = scan_inventory(str(skills_dir), match_target="https://github.com/Foo/Bar.git/")
        assert result["status"] == "ok"
        assert len(result["matches"]) == 1
        m = result["matches"][0]
        assert m["match_reason"] == "url"
        assert m["name"] == "legacy-bar"
        assert m["active_version"] == "1.0.0"
        assert m["active_path"] is not None

    def test_name_match_derives_from_target(self, skills_dir):
        """A skill named bar-baz matches by derived name even when the URL differs."""
        make_skill(skills_dir, "bar-baz", "2.0.0", source_repo="github.com/unrelated/thing")
        result = scan_inventory(str(skills_dir), match_target="github.com/x/bar-baz")
        assert len(result["matches"]) == 1
        m = result["matches"][0]
        assert m["match_reason"] == "name"
        assert m["name"] == "bar-baz"

    def test_both_reason(self, skills_dir):
        """URL and name both hit -> match_reason 'both'."""
        make_skill(skills_dir, "bar", "1.0.0", source_repo="github.com/foo/bar")
        result = scan_inventory(str(skills_dir), match_target="https://github.com/foo/bar")
        assert len(result["matches"]) == 1
        assert result["matches"][0]["match_reason"] == "both"

    def test_no_match_is_empty(self, skills_dir):
        make_skill(skills_dir, "react", "18.0.0", source_repo="github.com/facebook/react")
        result = scan_inventory(str(skills_dir), match_target="github.com/vuejs/core")
        assert result["matches"] == []

    def test_doc_url_matches_by_source_repo(self, skills_dir):
        """A docs-only skill (source_repo = full doc URL) is caught by URL match."""
        make_skill(
            skills_dir, "docs-example-com", "1.0.0",
            source_repo="https://docs.example.com/guide/intro",
        )
        result = scan_inventory(
            str(skills_dir), match_target="https://docs.example.com/guide/intro"
        )
        assert len(result["matches"]) == 1
        assert result["matches"][0]["match_reason"] == "url"

    def test_skill_without_metadata_only_name_matches(self, skills_dir):
        """No metadata -> no source_repo -> URL match cannot fire, name match still can."""
        make_skill(skills_dir, "bar", "1.0.0", with_metadata=False)
        result = scan_inventory(str(skills_dir), match_target="github.com/foo/bar")
        assert len(result["matches"]) == 1
        m = result["matches"][0]
        assert m["match_reason"] == "name"
        assert m["source_repo"] is None
