#!/usr/bin/env python3
"""Tests for skf-skill-inventory.py."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
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


# ---------------------------------------------------------------------------
# Ownership: only a marked metadata.json proves that SKF generated a skill
# ---------------------------------------------------------------------------

SCRIPTS = Path(__file__).parent.parent / "src" / "shared" / "scripts"
INVENTORY_PY = SCRIPTS / "skf-skill-inventory.py"
CCC_PY = SCRIPTS / "skf-merge-ccc-exclusions.py"
ATOMIC_PY = SCRIPTS / "skf-atomic-write.py"

# One metadata.json shape per SKF release that wrote the flat layout.
MARKER_HISTORY = {
    "create-npm-0.1": {"skill_type": "individual", "forge_tier": "forge", "spec_version": "1.3",
                       "tool_versions": {"skf": "1.0.0"}},
    "create-0.3": {"skill_type": "single", "confidence_tier": "Forge", "tool_versions": {"skf": "1.0.0"}},
    "create-0.7": {"skill_type": "single", "confidence_tier": "Forge+", "generated_by": "create-skill",
                   "tool_versions": {"skf": "0.7.0"}},
    "quick-npm-0.1": {"generated_by": "quick-skill"},
    "quick-0.3": {"generated_by": "quick-skill", "skill_type": "single", "confidence_tier": "Quick"},
    "stack-npm-0.1": {"skill_type": "stack", "forge_tier": "deep"},
    "stack-0.3": {"skill_type": "stack", "confidence_tier": "Deep"},
    "stack-0.7": {"skill_type": "stack", "generated_by": "create-stack-skill", "confidence_tier": "Deep",
                  "tool_versions": {"skf": "0.7.0"}},
}

NOT_MARKERS = {
    "module-own": {"name": "x", "version": "1.0.0"},
    "other-generator": {"generated_by": "bmad-builder"},
    "type-without-tier": {"skill_type": "single"},
    "tool-versions-string": {"tool_versions": "skf"},
    "generated-by-list": {"generated_by": ["quick-skill"]},
}

MARKED = MARKER_HISTORY["create-0.7"]


def _write(path: Path, content=b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        content = json.dumps(content)
    if isinstance(content, str):
        content = content.encode("utf-8")
    path.write_bytes(content)


def _make_flat(skills_dir: Path, name: str, metadata=None, subdirs=(), extra=()) -> Path:
    """A flat skill: SKILL.md at the group root, optional metadata.json and extras.

    `metadata` can be a dict, a list, text or bytes (written as given).
    """
    group = skills_dir / name
    _write(group / "SKILL.md", f"---\nname: {name}\n---\n")
    if metadata is not None:
        _write(group / "metadata.json", metadata)
    for sub in subdirs:
        _write(group / sub / "file.md")
    for rel in extra:
        _write(group / rel)
    return group


def _make_version(skills_dir: Path, name: str, version: str, metadata=None) -> Path:
    pkg = skills_dir / name / version / name
    _write(pkg / "SKILL.md", f"---\nname: {name}\n---\n")
    if metadata is not None:
        _write(pkg / "metadata.json", metadata)
    return pkg


def _symlinks_supported(tmp: Path) -> bool:
    probe = tmp / "symlink-probe"
    try:
        probe.symlink_to(tmp)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


def _entry(skills_dir: Path, name: str) -> dict:
    result = scan_inventory(str(skills_dir), skill_filter=name)
    assert result["status"] == "ok", result
    assert [s["name"] for s in result["skills"]] == [name]
    return result["skills"][0]


@pytest.fixture()
def skills(tmp_path):
    d = tmp_path / "skills"
    d.mkdir()
    return d


class TestOwnership:
    """ownership / skf_skill / flat_skf / foreign_entries / not_skf_output."""

    def test_versioned_marked_skill_is_skf(self, skills):
        make_skill(skills, "cognee", "0.6.0")
        e = _entry(skills, "cognee")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"], e["foreign_entries"]) == (
            "skf", True, False, [])
        assert scan_inventory(str(skills))["not_skf_output"] == []

    def test_versioned_unmarked_skill_is_foreign(self, skills):
        """The versioned layout alone is not proof (an earlier SKF moved module skills there)."""
        make_skill(skills, "moved", "1.0.0", with_metadata=False)
        e = _entry(skills, "moved")
        assert (e["ownership"], e["skf_skill"]) == ("foreign", False)
        assert e["foreign_entries"] == ["1.0.0/"]
        assert scan_inventory(str(skills))["not_skf_output"] == ["moved"]

    def test_flat_module_skill_is_foreign_and_structure_unchanged(self, skills):
        _make_flat(skills, "foo", subdirs=("references", "scripts"))
        e = _entry(skills, "foo")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("foreign", False, False)
        assert e["foreign_entries"] == ["SKILL.md", "references/", "scripts/"]
        assert e["versions"] == ["flat"]
        assert e["active_version"] == "flat"
        assert e["active_path"] == str(skills / "foo")
        assert scan_inventory(str(skills))["not_skf_output"] == ["foo"]

    def test_skill_md_alone_is_foreign(self, skills):
        _make_flat(skills, "bar")
        e = _entry(skills, "bar")
        assert (e["ownership"], e["foreign_entries"]) == ("foreign", ["SKILL.md"])

    def test_shared_folder_is_foreign_and_not_listed(self, skills):
        _write(skills / "_shared" / "README.md")
        result = scan_inventory(str(skills))
        e = result["skills"][0]
        assert (e["name"], e["ownership"], e["skf_skill"]) == ("_shared", "foreign", False)
        assert result["not_skf_output"] == []

    def test_batch_folder_is_skf_but_not_a_skill(self, skills):
        _write(skills / "_batch" / "quick-skill-batch-latest.json", "{}")
        _write(skills / "_batch" / "notes.txt")
        result = scan_inventory(str(skills))
        e = result["skills"][0]
        assert (e["ownership"], e["skf_skill"], e["foreign_entries"]) == ("skf", False, [])
        assert result["not_skf_output"] == []

    def test_nested_module_sub_skill_is_foreign(self, skills):
        _make_flat(skills, "nested")
        _write(skills / "nested" / "sub" / "SKILL.md")
        e = _entry(skills, "nested")
        assert e["ownership"] == "foreign"
        assert e["versions"] == ["sub"]
        assert e["foreign_entries"] == ["SKILL.md", "sub/"]

    @pytest.mark.parametrize("era", sorted(MARKER_HISTORY))
    def test_legacy_flat_skf_skill_is_skf(self, skills, era):
        _make_flat(skills, "legacy", MARKER_HISTORY[era], subdirs=("references", "scripts", "assets"),
                   extra=("context-snippet.md",))
        e = _entry(skills, "legacy")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"], e["foreign_entries"]) == (
            "skf", True, True, [])
        assert scan_inventory(str(skills))["not_skf_output"] == []

    @pytest.mark.parametrize("shape", sorted(NOT_MARKERS))
    def test_flat_metadata_without_marker_is_foreign(self, skills, shape):
        _make_flat(skills, "mod", NOT_MARKERS[shape])
        e = _entry(skills, "mod")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("foreign", False, False)
        assert "metadata.json" in e["foreign_entries"]
        assert scan_inventory(str(skills))["not_skf_output"] == ["mod"]

    def test_marked_versions_beside_foreign_root_skill_md_are_mixed(self, skills):
        _make_flat(skills, "mix", subdirs=("references",))
        _make_version(skills, "mix", "2.0.0", MARKED)
        _link_active(skills / "mix" / "active", "2.0.0")
        e = _entry(skills, "mix")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("mixed", True, False)
        assert e["foreign_entries"] == ["SKILL.md", "references/"]
        assert scan_inventory(str(skills))["not_skf_output"] == []

    def test_same_named_subfolder_in_module_skill_is_foreign(self, skills):
        _make_flat(skills, "react")
        _write(skills / "react" / "references" / "react" / "hooks.md")
        e = _entry(skills, "react")
        assert (e["ownership"], e["foreign_entries"]) == ("foreign", ["SKILL.md", "references/"])

    def test_same_named_subfolder_in_marked_flat_skill_stays_skf(self, skills):
        """references/{name}/ beside a marked root is package content, not a version."""
        _make_flat(skills, "react", MARKED)
        _write(skills / "react" / "references" / "react" / "hooks.md")
        e = _entry(skills, "react")
        assert (e["ownership"], e["flat_skf"], e["foreign_entries"]) == ("skf", True, [])

    def test_marked_flat_skill_package_folders_are_not_versions(self, skills):
        """Export discovery reads active_version: a flat SKF skill must resolve to "flat"."""
        _make_flat(skills, "react", MARKED, subdirs=("scripts",))
        _write(skills / "react" / "references" / "react" / "hooks.md")
        e = _entry(skills, "react")
        assert (e["skf_skill"], e["flat_skf"]) == (True, True)
        assert (e["versions"], e["active_version"], e["active_path"]) == (
            ["flat"], "flat", str(skills / "react"))
        assert e["has_skill_md"] is True
        assert scan_inventory(str(skills))["not_skf_output"] == []

    def test_marked_root_without_skill_md_is_not_flat_skf(self, skills):
        """flat_skf needs the root SKILL.md: a marker alone is not a skill to migrate."""
        _write(skills / "half" / "metadata.json", MARKED)
        _write(skills / "half" / "references" / "notes.md")
        e = _entry(skills, "half")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"], e["foreign_entries"]) == (
            "skf", False, False, [])
        assert scan_inventory(str(skills))["not_skf_output"] == []

    def test_marked_flat_package_plus_user_file_is_mixed(self, skills):
        _make_flat(skills, "flatnote", MARKED, extra=("NOTES.md",))
        e = _entry(skills, "flatnote")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("mixed", True, True)
        assert e["foreign_entries"] == ["NOTES.md"]

    def test_result_staging_and_neutral_entries_keep_skf(self, skills):
        make_skill(skills, "tidy", "1.0.0")
        group = skills / "tidy"
        for rel in ("rename-skill-result-latest.json", "rename-skill-result-20260101-000000.json",
                    "active.skf-lock", ".skf-write-probe", "1.1.0.skf-tmp/tidy/SKILL.md",
                    ".DS_Store", "Thumbs.db", "desktop.ini", ".gitkeep", ".gitignore",
                    ".gitattributes"):
            _write(group / rel)
        e = _entry(skills, "tidy")
        assert (e["ownership"], e["foreign_entries"]) == ("skf", [])

    def test_nested_git_repository_makes_group_mixed(self, skills):
        make_skill(skills, "vgit", "1.0.0")
        _write(skills / "vgit" / ".git" / "HEAD", "ref: refs/heads/main\n")
        e = _entry(skills, "vgit")
        assert (e["ownership"], e["foreign_entries"]) == ("mixed", [".git/"])

    def test_unmarked_version_inside_marked_group_is_mixed(self, skills):
        make_skill(skills, "half", "1.0.0")
        _make_version(skills, "half", "0.9.0")
        e = _entry(skills, "half")
        assert (e["ownership"], e["skf_skill"]) == ("mixed", True)
        assert e["foreign_entries"] == ["0.9.0/"]

    def test_real_active_dir_counts_only_when_marked(self, skills):
        _make_version(skills, "copied", "active", MARKED)
        assert _entry(skills, "copied")["ownership"] == "skf"
        _make_version(skills, "plain", "1.0.0", MARKED)
        _make_version(skills, "plain", "active")
        e = _entry(skills, "plain")
        assert (e["ownership"], e["foreign_entries"]) == ("mixed", ["active/"])
        _make_flat(skills, "act")
        _write(skills / "act" / "active" / "readme.md")
        e = _entry(skills, "act")
        assert (e["ownership"], e["foreign_entries"]) == ("foreign", ["SKILL.md", "active/"])

    def test_linked_group_is_foreign(self, skills, tmp_path):
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        target = tmp_path / "elsewhere" / "linked"
        _make_flat(target.parent, "linked", MARKED)
        (skills / "linked").symlink_to(target, target_is_directory=True)
        e = _entry(skills, "linked")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("foreign", False, False)
        assert any("link" in err for err in e["errors"])
        assert e["versions"] == ["flat"]  # structure is still read through the link

    def test_linked_version_folder_is_foreign(self, skills, tmp_path):
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        make_skill(skills, "lv", "1.0.0")
        elsewhere = tmp_path / "elsewhere"
        _make_version(elsewhere, "lv", "0.9.0", MARKED)
        (skills / "lv" / "0.9.0").symlink_to(elsewhere / "lv" / "0.9.0", target_is_directory=True)
        e = _entry(skills, "lv")
        assert (e["ownership"], e["foreign_entries"]) == ("mixed", ["0.9.0"])

    def test_linked_package_inside_version_folder_is_foreign(self, skills, tmp_path):
        """A marked package reached through a link is not SKF output: a purge would follow it."""
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        make_skill(skills, "lp", "1.0.0")
        elsewhere = tmp_path / "elsewhere"
        pkg = _make_version(elsewhere, "lp", "0.9.0", MARKED)
        (skills / "lp" / "0.9.0").mkdir()
        (skills / "lp" / "0.9.0" / "lp").symlink_to(pkg, target_is_directory=True)
        e = _entry(skills, "lp")
        assert (e["ownership"], e["skf_skill"], e["foreign_entries"]) == ("mixed", True, ["0.9.0/"])

    def test_entries_inside_a_marked_version_folder_are_foreign(self, skills):
        """A marked version folder holds only the package and .skf- staging names."""
        make_skill(skills, "mylib", "1.0.0")
        _write(skills / "mylib" / "1.0.0" / "NOTES.md")
        _write(skills / "mylib" / "1.0.0" / "other" / "SKILL.md")
        e = _entry(skills, "mylib")
        assert (e["ownership"], e["skf_skill"]) == ("mixed", True)
        assert e["foreign_entries"] == ["1.0.0/NOTES.md", "1.0.0/other/"]

    def test_staging_and_clutter_inside_a_marked_version_keep_skf(self, skills):
        make_skill(skills, "tidy", "1.0.0")
        version = skills / "tidy" / "1.0.0"
        for rel in ("tidy.skf-tmp/SKILL.md", "tidy.skf-rollback-123/SKILL.md", ".DS_Store",
                    ".gitkeep"):
            _write(version / rel)
        e = _entry(skills, "tidy")
        assert (e["ownership"], e["foreign_entries"]) == ("skf", [])

    def test_linked_entry_inside_a_marked_version_is_listed_bare(self, skills, tmp_path):
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        make_skill(skills, "lk", "1.0.0")
        (tmp_path / "elsewhere").mkdir()
        (skills / "lk" / "1.0.0" / "ext").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
        e = _entry(skills, "lk")
        assert (e["ownership"], e["foreign_entries"]) == ("mixed", ["1.0.0/ext"])

    @pytest.mark.parametrize("layout", ["flat", "versioned"])
    def test_metadata_with_a_utf8_bom_is_not_a_marker(self, skills, layout):
        """A BOM metadata.json is refused up front, naming the decode error.

        The rename and metadata helpers read metadata.json as plain UTF-8 and
        reject a BOM, so the ownership gates must too: a refusal before any
        change, not a rollback halfway through a rename.
        """
        bom = b"\xef\xbb\xbf" + json.dumps(dict(MARKED, name="b", version="1.0.0")).encode("utf-8")
        if layout == "flat":
            _make_flat(skills, "b", bom)
        else:
            _make_version(skills, "b", "1.0.0", bom)
            _link_active(skills / "b" / "active", "1.0.0")
        e = _entry(skills, "b")
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("foreign", False, False)
        assert e["metadata"] is None
        assert any("BOM" in err and "metadata.json" in err for err in e["errors"]), e["errors"]
        ccc = _load(CCC_PY, "skf_ccc_for_bom")
        meta = skills / "b" / ("metadata.json" if layout == "flat" else "1.0.0/b/metadata.json")
        assert not mod._has_skf_metadata(meta)
        assert not ccc._has_skf_metadata(meta)

    def test_manifest_with_a_utf8_bom_is_reported(self, skills):
        make_skill(skills, "cognee", "0.6.0")
        _write(skills / ".export-manifest.json",
               b"\xef\xbb\xbf" + json.dumps({"exports": {"cognee": {}}}).encode("utf-8"))
        result = scan_inventory(str(skills))
        assert result["manifest"] is None
        assert "BOM" in result["manifest_error"]

    def test_manifest_key_alone_is_not_ownership(self, skills):
        _make_flat(skills, "foo", subdirs=("references",))
        manifest = {"schema_version": "2", "exports": {"foo": {"active_version": "flat"}}}
        _write(skills / ".export-manifest.json", manifest)
        e = _entry(skills, "foo")
        assert (e["ownership"], e["skf_skill"]) == ("foreign", False)

    def test_skill_filter_reports_ownership_fields(self, skills):
        _make_flat(skills, "foo")
        make_skill(skills, "cognee", "0.6.0")
        result = scan_inventory(str(skills), skill_filter="foo")
        e = result["skills"][0]
        for key in ("ownership", "skf_skill", "flat_skf", "foreign_entries"):
            assert key in e
        assert result["not_skf_output"] == ["foo"]

    def test_cli_reports_ownership(self, skills):
        _make_flat(skills, "foo", subdirs=("references",))
        proc = subprocess.run([sys.executable, str(INVENTORY_PY), str(skills), "--skill", "foo"],
                              capture_output=True, timeout=60)
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout.decode("utf-8"))
        e = data["skills"][0]
        assert (e["ownership"], e["skf_skill"], e["flat_skf"]) == ("foreign", False, False)
        assert data["not_skf_output"] == ["foo"]
        missing = subprocess.run([sys.executable, str(INVENTORY_PY), str(skills), "--skill", "nope"],
                                 capture_output=True, timeout=60)
        assert missing.returncode == 1
        assert json.loads(missing.stdout.decode("utf-8"))["code"] == "SKILL_NOT_FOUND"

    def test_manifest_export_without_folder_gives_no_entry(self, skills):
        """The four migrate sites halt when --skill returns no entry."""
        _write(skills / ".export-manifest.json", {"exports": {"gone": {"active_version": "1.0.0"}}})
        result = scan_inventory(str(skills), skill_filter="gone")
        assert (result["status"], result["skills"]) == ("ok", [])

    @pytest.mark.parametrize("manifest", ['"exports"', "[1, 2]", '{"exports": [1]}'])
    def test_malformed_manifest_does_not_crash(self, skills, manifest):
        _write(skills / ".export-manifest.json", manifest)
        _make_flat(skills, "foo")
        result = scan_inventory(str(skills))
        assert result["status"] == "ok"
        assert [s["name"] for s in result["skills"]] == ["foo"]


class TestForeignMetadataRobustness:
    """Foreign metadata.json files are an expected input: never crash the scan."""

    @pytest.mark.parametrize("content, error", [
        ("[1]", "not a JSON object"),
        ("null", "not a JSON object"),
        (b"\xff\xfe\x00", "Cannot read"),
        ('{"stats": 5}', None),
    ])
    def test_unreadable_or_odd_metadata(self, skills, content, error):
        _make_flat(skills, "odd", content)
        e = _entry(skills, "odd")
        assert e["ownership"] == "foreign"
        if error:
            assert any(error in err for err in e["errors"]), e["errors"]
            assert e["metadata"] is None
        else:
            assert e["metadata"]["exports_total"] is None

    def test_directory_named_metadata_json(self, skills):
        _write(skills / "odd" / "SKILL.md")
        (skills / "odd" / "metadata.json").mkdir()
        _write(skills / "odd" / "metadata.json" / "x.txt")
        e = _entry(skills, "odd")
        assert e["ownership"] == "foreign"
        assert any("Cannot read" in err for err in e["errors"]), e["errors"]

    def test_versioned_stats_not_an_object(self, skills):
        pkg = _make_version(skills, "vs", "1.0.0", dict(MARKED, stats=5))
        _link_active(skills / "vs" / "active", "1.0.0")
        e = _entry(skills, "vs")
        assert e["ownership"] == "skf"
        assert e["metadata"]["exports_total"] is None
        assert pkg.is_dir()


def _load(path: Path, name: str):
    spec_ = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    return module


def _top_level_node(path: Path, name: str) -> str:
    """ast.dump of the top-level def or assignment named `name` (comments ignored)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node)
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.dump(node)
    raise AssertionError(f"{name} not found at the top level of {path.name}")


def _listing(folder: Path) -> list:
    """First-level-relative paths as `git ls-files` would list them (links not followed)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        rel = Path(dirpath).relative_to(folder).parts
        for d in dirnames:
            if (Path(dirpath) / d).is_symlink():
                out.append(rel + (d,))
        out.extend(rel + (f,) for f in filenames)
    return sorted(out)


class TestSkfMarkerParity:
    """The copied marker check must stay identical to its sources."""

    @pytest.mark.parametrize("name, source", [
        ("_has_skf_metadata", CCC_PY),
        ("_is_marked_version", CCC_PY),
        ("_has_skf_evidence", CCC_PY),
        ("SKF_GENERATORS", CCC_PY),
        ("RESULT_JSON_RE", CCC_PY),
        ("_is_link_or_junction", ATOMIC_PY),
        ("_is_link_or_junction", CCC_PY),
    ])
    def test_copy_is_identical(self, name, source):
        assert _top_level_node(INVENTORY_PY, name) == _top_level_node(source, name), (
            f"{name} in skf-skill-inventory.py differs from {source.name}; keep the copies identical")

    @pytest.mark.parametrize("path", [INVENTORY_PY, CCC_PY, ATOMIC_PY])
    def test_copies_carry_keep_identical_notes(self, path):
        text = path.read_text(encoding="utf-8")
        assert "Keep identical to" in text and "test/test-skf-skill-inventory.py pins the copies" in text

    @pytest.mark.parametrize("path", [INVENTORY_PY, ATOMIC_PY, CCC_PY])
    def test_link_check_treats_other_reparse_points_as_not_links(self, tmp_path, monkeypatch, path):
        """On Windows, os.readlink raises ValueError for a reparse point that is
        neither a symlink nor a junction (cloud placeholder, dedup file)."""
        module = _load(path, "skf_link_check_" + path.stem.replace("-", "_"))
        folder = tmp_path / "placeholder"
        folder.mkdir()

        def not_a_symbolic_link(_p):
            raise ValueError("not a symbolic link")

        monkeypatch.setattr(module.os, "readlink", not_a_symbolic_link)
        assert module._is_link_or_junction(folder) is False

    def test_scan_survives_reparse_points_that_are_not_links(self, skills, monkeypatch):
        make_skill(skills, "cognee", "0.6.0")
        _make_flat(skills, "foo")
        real_readlink = os.readlink

        def readlink(p, *args, **kwargs):
            if Path(p).is_symlink():
                return real_readlink(p, *args, **kwargs)
            raise ValueError("not a symbolic link")

        monkeypatch.setattr(mod.os, "readlink", readlink)
        result = scan_inventory(str(skills))
        assert result["status"] == "ok"
        by_name = {e["name"]: e["ownership"] for e in result["skills"]}
        assert by_name == {"cognee": "skf", "foo": "foreign"}

    def test_both_copies_accept_marker_history_and_reject_non_markers(self, tmp_path):
        ccc = _load(CCC_PY, "skf_ccc_for_parity")
        for label, data in list(MARKER_HISTORY.items()) + list(NOT_MARKERS.items()):
            path = tmp_path / label / "metadata.json"
            _write(path, data)
            expected = label in MARKER_HISTORY
            assert mod._has_skf_metadata(path) is expected, label
            assert ccc._has_skf_metadata(path) is expected, label

    @staticmethod
    def _ownership_fixture(tmp_path: Path) -> tuple[Path, Path]:
        """One skills folder holding every ownership shape, SKF evidence or not."""
        root = tmp_path / "project"
        skills = root / "skills"
        skills.mkdir(parents=True)
        links = _symlinks_supported(tmp_path)
        for era, data in MARKER_HISTORY.items():
            _make_flat(skills, era, data, subdirs=("references",), extra=("context-snippet.md",))
        for shape, data in NOT_MARKERS.items():
            _make_flat(skills, "not-" + shape, data)
        _make_flat(skills, "foo", subdirs=("references", "scripts"))
        _make_flat(skills, "nested")
        _write(skills / "nested" / "sub" / "SKILL.md")
        _write(skills / "_shared" / "README.md")
        _write(skills / "_batch" / "quick-skill-batch-latest.json", "{}")
        make_skill(skills, "vskf", "1.0.0")
        _write(skills / "vskf" / "rename-skill-result-latest.json", "{}")
        # Unmarked versioned groups: a module skill an earlier SKF moved.
        make_skill(skills, "vnometa", "1.0.0", with_metadata=False)
        _make_version(skills, "vunmarked", "1.0.0", {"name": "vunmarked", "version": "1.0.0"})
        # Structure alone: an active pointer, a result file, a manifest key.
        _write(skills / "activeonly" / "1.0.0" / "SKILL.md")
        _write(skills / "resultonly" / "rename-skill-result-latest.json", "{}")
        _write(skills / "resultonly" / "SKILL.md")
        _make_flat(skills, "manifestonly", subdirs=("references",))
        _write(skills / ".export-manifest.json",
               {"exports": {"manifestonly": {}, "vnometa": {}, "gone": {}}})
        _make_flat(skills, "mix", subdirs=("references",))
        _make_version(skills, "mix", "2.0.0", MARKED)
        _make_flat(skills, "flatnote", MARKED, extra=("NOTES.md",))
        make_skill(skills, "vgit", "1.0.0")
        _write(skills / "vgit" / ".git" / "HEAD")
        _make_version(skills, "half", "1.0.0", MARKED)
        _make_version(skills, "half", "0.9.0")
        make_skill(skills, "vnotes", "1.0.0")
        _write(skills / "vnotes" / "1.0.0" / "NOTES.md")
        _make_flat(skills, "bom", b"\xef\xbb\xbf" + json.dumps(MARKED).encode("utf-8"))
        if links:
            _link_active(skills / "mix" / "active", "2.0.0")
            _link_active(skills / "activeonly" / "active", "1.0.0")
            ext = tmp_path / "elsewhere"
            _make_flat(ext, "linked", MARKED)
            (skills / "linked").symlink_to(ext / "linked", target_is_directory=True)
        return root, skills

    def test_inventory_never_owns_what_ccc_calls_foreign(self, tmp_path):
        """Whatever the inventory owns (skf or mixed), ccc excludes too."""
        ccc = _load(CCC_PY, "skf_ccc_for_ownership")
        root, skills = self._ownership_fixture(tmp_path)
        scan = ccc.classify_folder(root, "skills", "skills", _listing(skills))
        result = scan_inventory(str(skills))
        owned = [e["name"] for e in result["skills"] if e["ownership"] in ("skf", "mixed")]
        assert owned, "fixture must hold SKF output"
        for name in owned:
            assert name in scan.owned_groups, f"inventory owns {name} but ccc calls it foreign"
            assert name + "/" not in scan.foreign

    def test_ccc_never_excludes_what_the_inventory_calls_foreign(self, tmp_path):
        """One definition of SKF output: ccc excludes no group a workflow refuses to touch."""
        ccc = _load(CCC_PY, "skf_ccc_for_foreign")
        root, skills = self._ownership_fixture(tmp_path)
        scan = ccc.classify_folder(root, "skills", "skills", _listing(skills))
        result = scan_inventory(str(skills))
        foreign = [e["name"] for e in result["skills"] if e["ownership"] == "foreign"]
        for expected in ("vnometa", "vunmarked", "activeonly", "resultonly", "manifestonly",
                         "bom"):
            assert expected in foreign, expected
        for name in foreign:
            assert name not in scan.owned_groups, f"ccc excludes {name} but the inventory calls it foreign"
        assert sorted(scan.owned_groups) == sorted(
            e["name"] for e in result["skills"] if e["ownership"] != "foreign")


def test_match_target_reports_skf_skill(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "bar", "1.0.0", source_repo="github.com/foo/bar")
    _make_flat(skills, "legacy-bar", {"name": "legacy-bar", "source_repo": "github.com/foo/bar"})
    result = scan_inventory(str(skills), match_target="https://github.com/foo/bar")
    by_name = {m["name"]: m for m in result["matches"]}
    assert by_name["bar"]["skf_skill"] is True
    assert by_name["legacy-bar"]["skf_skill"] is False
