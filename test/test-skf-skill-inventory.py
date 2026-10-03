#!/usr/bin/env python3
"""Tests for skf-skill-inventory.py."""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
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
        assert derive_name(None, "") == ""

    def test_dotted_repo_name(self):
        assert derive_name("https://github.com/vercel/next.js") == "next-js"
        assert derive_name("git@github.com:mrdoob/three.js.git") == "three-js"

    def test_doc_url_is_named_after_its_host(self):
        # the name auto-docs-only.md writes the brief under
        assert derive_name("https://docs.example.com/guide/intro") == "docs-example-com"
        assert derive_name("http://www.example.org/api/") == "www-example-org"
        assert mod.derive_name_with_basis("https://docs.example.com/x") == ("docs-example-com", "docs-host")

    @pytest.mark.parametrize("url", [
        "https://github.com/foo/bar", "https://www.github.com/foo/bar",
        "https://gitlab.com/group/sub/bar", "https://bitbucket.org/team/bar.git",
    ])
    def test_git_hosts_are_named_after_the_repository(self, url):
        assert mod.derive_name_with_basis(url) == ("bar", "target")

    @pytest.mark.parametrize("manifest_name,expected", [
        ("next", "next"),
        ("@trpc/server", "trpc-server"),
        ("@aws-sdk/client-s3", "aws-sdk-client-s3"),
        ("PyYAML", "pyyaml"),
        ("zope.interface", "zope-interface"),
        ("serde_json", "serde-json"),
        ("github.com/spf13/cobra", "cobra"),
        ("github.com/go-yaml/yaml/v3", "yaml"),
        ("example.com/tool", "tool"),
        ("com.google.guava:guava", "guava"),
        ("org.apache.commons:commons-lang3", "commons-lang3"),
        ("symfony/console", "symfony-console"),
        ("MyLibrary", "mylibrary"),
    ])
    def test_manifest_name_wins_over_the_target(self, manifest_name, expected):
        assert mod.derive_name_with_basis("https://github.com/org/repo", manifest_name) == (expected, "manifest")

    @pytest.mark.parametrize("manifest_name", [None, "", "   ", "@@"])
    def test_empty_manifest_name_falls_back_to_the_target(self, manifest_name):
        assert mod.derive_name_with_basis("packages/auth", manifest_name) == ("auth", "target")

    def test_no_name(self):
        assert mod.derive_name_with_basis("", None) == ("", None)
        assert mod.derive_name_with_basis("///", "") == ("", None)

    @pytest.mark.parametrize("target", [".", "./", ".\\"])
    def test_current_folder_is_named_after_itself(self, target, tmp_path, monkeypatch):
        """`--project-path .` on a repo whose root manifest is private."""
        (tmp_path / "mono").mkdir()
        monkeypatch.chdir(tmp_path / "mono")
        assert mod.derive_name_with_basis(target) == ("mono", "target")
        assert derive_name("..") == derive_name("../") == mod._kebab(tmp_path.name)

    def test_home_paths(self, tmp_path, monkeypatch):
        home = tmp_path / "Me_Home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        assert derive_name("~") == derive_name("~/") == "me-home"
        assert derive_name("~/x") == "x"

    @pytest.mark.parametrize("target", [
        "C:\\Users\\me\\code\\mono", "C:/Users/me/code/mono/", "D:\\mono.git",
        "\\\\server\\share\\mono",
    ])
    def test_windows_paths_split_on_backslashes(self, target):
        assert mod.derive_name_with_basis(target) == ("mono", "target")

    def test_private_manifest_names_nothing(self):
        """A private root (a workspace manifest) is named after the target."""
        assert mod.derive_name_with_basis("apps/web", "@acme/web", private=True) == (
            "web", "target")
        assert mod.derive_name_with_basis("apps/web", "@acme/web", private=False) == (
            "acme-web", "manifest")

    @pytest.mark.parametrize("members,expected", [
        (["@trpc/server", "@trpc/client"], "trpc"),
        (["@aws-sdk/client-s3", "@aws-sdk/core", "@aws-sdk/lib-storage"], "aws-sdk"),
        (["serde", "serde_json", "serde_derive"], "serde"),
        (["next", "@next/font"], "next"),
        (["acme/auth", "acme/core"], "acme"),
        (["com.acme:core", "com.acme:api"], "acme"),
        (["github.com/x/repo/a", "github.com/x/repo/b"], "repo"),
        (["github.com/x/repo/v2/a", "github.com/x/repo/v2/b"], "repo"),
    ], ids=["npm-scope", "aws-sdk", "crates", "unscoped-and-scoped", "composer",
            "maven-group", "go-paths", "go-major-version"])
    def test_members_name_a_merged_unit(self, members, expected):
        assert mod.derive_name_with_basis("org/repo", None, False, members) == (
            expected, "members")

    @pytest.mark.parametrize("members", [
        [], ["@trpc/server"], ["react", "scheduler"], ["com.a:x", "com.b:y"],
        ["github.com/a/x", "gitlab.com/a/x"],
    ], ids=["none", "one", "no-shared-word", "two-groups", "two-domains"])
    def test_members_without_a_shared_name(self, members):
        assert mod.derive_name_with_basis("org/repo", None, False, members) == (
            "repo", "target")

    def test_manifest_name_wins_over_the_members(self):
        """The facade's name, when the umbrella facade trigger merged the unit."""
        result = mod.derive_name_with_basis("org/repo", "animato", False, ["animato-core", "animato-x"])
        assert result == ("animato", "manifest")
        result = mod.derive_name_with_basis("org/repo", "root", True, ["@a/x", "@a/y"])
        assert result == ("a", "members")


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

    def test_doc_url_matches_by_source_repo_and_name(self, skills_dir):
        """A docs-only skill is caught by URL, and by the host name its brief got."""
        make_skill(
            skills_dir, "docs-example-com", "1.0.0",
            source_repo="https://docs.example.com/guide/intro",
        )
        result = scan_inventory(
            str(skills_dir), match_target="https://docs.example.com/guide/intro"
        )
        assert result["match_name"] == "docs-example-com"
        assert len(result["matches"]) == 1
        assert result["matches"][0]["match_reason"] == "both"

    def test_doc_skill_from_another_page_matches_by_name(self, skills_dir):
        make_skill(skills_dir, "docs-example-com", "1.0.0",
                   source_repo="https://docs.example.com/other")
        result = scan_inventory(str(skills_dir), match_target="https://docs.example.com/guide/intro")
        assert [m["match_reason"] for m in result["matches"]] == ["name"]

    def test_match_name_is_the_name_derive_name_gives(self, skills_dir):
        result = scan_inventory(str(skills_dir), match_target="https://github.com/vercel/next.js")
        assert (result["match_name"], result["matches"]) == ("next-js", [])
        assert result["match_name"] == derive_name("https://github.com/vercel/next.js")

    def test_match_name_absent_without_match_target(self, skills_dir):
        assert "match_name" not in scan_inventory(str(skills_dir))

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
VALIDATOR_PY = (Path(__file__).parent.parent / "src" / "skf-rename-skill" / "scripts"
                / "skf-validate-rename-name.py")
ENUMERATE_PY = SCRIPTS / "skf-enumerate-stack-skills.py"
SOURCE_TREE_PY = SCRIPTS / "skf-source-tree.py"
TESSL_PY = SCRIPTS / "skf-tessl-review.py"
LOAD_PROVENANCE_PY = SCRIPTS / "skf-load-provenance.py"

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

    def test_skf_names_are_never_not_skf_output(self, skills):
        """SKF's own staging and batch names are never listed as a skill SKF did not generate."""
        _write(skills / "foo.skf-tmp" / "SKILL.md")
        _write(skills / "_batch" / "SKILL.md")
        _write(skills / "_batch" / "quick-skill-batch-latest.json", "{}")
        _make_flat(skills, "mod")
        assert scan_inventory(str(skills))["not_skf_output"] == ["mod"]

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
        ("_has_forge_evidence", CCC_PY),
        ("FORGE_GROUP_DIRS", CCC_PY),
        ("FORGE_VERSION_ANCHORS", CCC_PY),
        ("FORGE_GROUP_DIRS", VALIDATOR_PY),
        ("_is_link_or_junction", VALIDATOR_PY),
        ("SKF_GENERATORS", ENUMERATE_PY),
        ("_has_skf_metadata", ENUMERATE_PY),
        ("_is_link_or_junction", ENUMERATE_PY),
        ("_is_marked_version", ENUMERATE_PY),
        ("_looks_like_skill", ENUMERATE_PY),
        ("_is_link_or_junction", SOURCE_TREE_PY),
        ("_is_link_or_junction", TESSL_PY),
        ("_parse_iso_utc", LOAD_PROVENANCE_PY),
        ("ISO_TIME_RE", LOAD_PROVENANCE_PY),
    ])
    def test_copy_is_identical(self, name, source):
        assert _top_level_node(INVENTORY_PY, name) == _top_level_node(source, name), (
            f"{name} in skf-skill-inventory.py differs from {source.name}; keep the copies identical")

    @pytest.mark.parametrize("path", [INVENTORY_PY, CCC_PY, ATOMIC_PY, VALIDATOR_PY, ENUMERATE_PY, SOURCE_TREE_PY, TESSL_PY,
                                      LOAD_PROVENANCE_PY])
    def test_copies_carry_keep_identical_notes(self, path):
        text = path.read_text(encoding="utf-8")
        assert "Keep identical to" in text and "test/test-skf-skill-inventory.py pins the copies" in text

    @pytest.mark.parametrize("path", [INVENTORY_PY, ATOMIC_PY, CCC_PY, ENUMERATE_PY, VALIDATOR_PY, SOURCE_TREE_PY, TESSL_PY])
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
        enum = _load(ENUMERATE_PY, "skf_enumerate_for_parity")
        for label, data in list(MARKER_HISTORY.items()) + list(NOT_MARKERS.items()):
            path = tmp_path / label / "metadata.json"
            _write(path, data)
            expected = label in MARKER_HISTORY
            assert mod._has_skf_metadata(path) is expected, label
            assert ccc._has_skf_metadata(path) is expected, label
            assert enum._has_skf_metadata(path) is expected, label

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
            # A linked version folder with a corrupt metadata.json behind it:
            # never SKF output, and never read, so never a roster warning.
            _write(ext / "lv-2.0.0" / "lv" / "SKILL.md")
            _write(ext / "lv-2.0.0" / "lv" / "metadata.json", '{"generated_by":"create-skill", broken')
            (skills / "lv").mkdir()
            (skills / "lv" / "2.0.0").symlink_to(ext / "lv-2.0.0", target_is_directory=True)
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

    def test_enumerate_agrees_with_the_inventory(self, tmp_path):
        """Stack rosters and the inventory name the same folders SKF did not generate."""
        enum = _load(ENUMERATE_PY, "skf_enumerate_for_agreement")
        _root, skills = self._ownership_fixture(tmp_path)
        roster = enum.enumerate_stack_skills(skills)
        inv = scan_inventory(str(skills))
        warned = {w.split(":", 1)[0] for w in roster["warnings"]
                  if "SKF cannot tell whether it generated this skill" in w}
        assert warned == {"bom"}, "an unreadable metadata.json is a warning, not a silent skip"
        assert set(roster["not_skf_output"]) | warned == set(inv["not_skf_output"])
        assert not set(roster["not_skf_output"]) & warned
        skf = {e["name"] for e in inv["skills"] if e["skf_skill"]}
        assert {e["name"] for e in roster["skills"]} <= skf


def test_match_target_reports_skf_skill(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "bar", "1.0.0", source_repo="github.com/foo/bar")
    _make_flat(skills, "legacy-bar", {"name": "legacy-bar", "source_repo": "github.com/foo/bar"})
    result = scan_inventory(str(skills), match_target="https://github.com/foo/bar")
    by_name = {m["name"]: m for m in result["matches"]}
    assert by_name["bar"]["skf_skill"] is True
    assert by_name["legacy-bar"]["skf_skill"] is False


# ---------------------------------------------------------------------------
# Forge folders: {forge_data_folder}/{name} is SKF output only with evidence
# ---------------------------------------------------------------------------

# (ownership, foreign_entries) for each forge folder shape of _forge_fixture.
FORGE_EXPECTED = {
    "cognee": ("skf", []),
    "notes": ("mixed", ["NOTES.md", "my-source-snapshots/"]),
    "vnotes": ("mixed", ["1.0.0/NOTES.md"]),
    "legacybrief": ("skf", []),
    "legacy": ("foreign", ["provenance-map.json"]),
    "other": ("foreign", ["config.toml", "data/"]),
    "deep": ("foreign", ["a/"]),
    "generic": ("foreign", ["test-report.md"]),
    "genericev": ("foreign", ["evidence-report.md"]),
    "tmpfile": ("foreign", ["cache/"]),
    "tslock": ("foreign", ["1.0.0/"]),
    "tsdone": ("skf", []),
    "renamedrep": ("skf", []),
    "resnotes": ("mixed", ["1.0.0/NOTES.md"]),
    "stack-stack": ("skf", []),
    "lockonly": ("empty", []),
    "empty": ("empty", []),
    "clutter": ("empty", []),
    "improvement-queue": ("reserved", []),
    "draft": ("skf", []),
    "filegroup": ("foreign", []),
    "absent": ("absent", []),
    "staged": ("foreign", ["NOTES.md"]),
}
# The linked shapes, added where symlinks can be created. A linked group is
# never SKF output, whatever its name or the files behind the link.
FORGE_EXPECTED_LINKED = {
    "lnk": ("foreign", []),
    "linkver": ("mixed", ["0.9.0"]),
    "_campaign": ("foreign", []),
    "linkbrief": ("foreign", ["NOTES.md", "skill-brief.yaml"]),
    "linkrules": ("mixed", ["1.0.0/extraction-rules.yaml"]),
    "linkanchor": ("foreign", ["1.0.0/", "NOTES.md"]),
    "nestedlink": ("mixed", ["1.0.0/"]),
}
FORGE_FILES = (
    "cognee/skill-brief.yaml", "cognee/0.1.0/provenance-map.json", "cognee/0.1.0/evidence-report.md",
    "notes/skill-brief.yaml", "notes/NOTES.md", "notes/my-source-snapshots/src.tar",
    "vnotes/skill-brief.yaml", "vnotes/1.0.0/provenance-map.json", "vnotes/1.0.0/NOTES.md",
    "legacybrief/skill-brief.yaml", "legacybrief/provenance-map.json",
    "legacybrief/test-report-legacybrief-1.md", "legacybrief/test-findings-r1.json",
    "legacy/provenance-map.json",
    "other/config.toml", "other/data/x.csv",
    "deep/a/b/c/foo-result.json",
    "generic/test-report.md",
    "genericev/evidence-report.md",
    "tmpfile/cache/build-tmp",
    "tslock/1.0.0/.test-skill.lock",
    "tsdone/1.0.0/.test-skill.lock", "tsdone/1.0.0/test-report-tsdone-r1.md",
    "tsdone/1.0.0/skf-test-skill-result-latest.json", "tsdone/1.0.0/test-findings-r1.json",
    "renamedrep/1.0.0/test-report-oldname-r1.md",
    "renamedrep/1.0.0/skf-test-skill-result-latest.json",
    "resnotes/1.0.0/skf-test-skill-result-latest.json", "resnotes/1.0.0/NOTES.md",
    "stack-stack/create-stack-skill-result-latest.json", "stack-stack/1.0.0/lib-tmp/partial.md",
    "lockonly/.skf-update.lock",
    "clutter/.DS_Store",
    "improvement-queue/q.json",
    "draft/.brief-draft.json",
    "filegroup",
    "staged/1.0.0.skf-tmp/provenance-map.json", "staged/NOTES.md",
)


def _forge_fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    """A project whose forge folder holds every forge ownership shape.

    Returns (root, skills, forge, expected verdicts by name).
    """
    root = tmp_path / "project"
    skills = root / "skills"
    forge = root / "forge-data"
    skills.mkdir(parents=True)
    for rel in FORGE_FILES:
        _write(forge / rel)
    (forge / "empty").mkdir()
    expected = dict(FORGE_EXPECTED)
    if _symlinks_supported(tmp_path):
        ext = tmp_path / "elsewhere"
        _write(ext / "lnk" / "skill-brief.yaml")
        (forge / "lnk").symlink_to(ext / "lnk", target_is_directory=True)
        _write(forge / "linkver" / "skill-brief.yaml")
        _write(ext / "v" / "provenance-map.json")
        (forge / "linkver" / "0.9.0").symlink_to(ext / "v", target_is_directory=True)
        _write(ext / "campaign" / "state.yaml")
        (forge / "_campaign").symlink_to(ext / "campaign", target_is_directory=True)
        _write(ext / "brief.yaml")
        _write(forge / "linkbrief" / "NOTES.md")
        (forge / "linkbrief" / "skill-brief.yaml").symlink_to(ext / "brief.yaml")
        _write(ext / "rules.yaml")
        _write(forge / "linkrules" / "skill-brief.yaml")
        _write(forge / "linkrules" / "1.0.0" / "provenance-map.json")
        (forge / "linkrules" / "1.0.0" / "extraction-rules.yaml").symlink_to(ext / "rules.yaml")
        _write(ext / "pm.json")
        _write(forge / "linkanchor" / "NOTES.md")
        (forge / "linkanchor" / "1.0.0").mkdir()
        (forge / "linkanchor" / "1.0.0" / "provenance-map.json").symlink_to(ext / "pm.json")
        (ext / "nothing").mkdir()
        _write(forge / "nestedlink" / "skill-brief.yaml")
        (forge / "nestedlink" / "1.0.0" / "sub").mkdir(parents=True)
        (forge / "nestedlink" / "1.0.0" / "sub" / "ref").symlink_to(ext / "nothing",
                                                                   target_is_directory=True)
        expected.update(FORGE_EXPECTED_LINKED)
    return root, skills, forge, expected


def _same_folder_skill(out: Path, name: str = "cognee") -> Path:
    """A marked skill in a folder both settings name, with its forge files beside it."""
    _make_version(out, name, "0.1.0", MARKED)
    _link_active(out / name / "active", "0.1.0")
    for rel in ("skill-brief.yaml", "0.1.0/provenance-map.json", "0.1.0/evidence-report.md"):
        _write(out / name / rel)
    return out / name


class TestForgeOwnership:
    """classify_forge_group, forge_groups[] and same_folder."""

    def test_forge_verdicts(self, tmp_path):
        _root, _skills, forge, expected = _forge_fixture(tmp_path)
        for name, verdict in expected.items():
            group = mod.classify_forge_group(forge / name, name)
            assert (group["ownership"], group["foreign_entries"]) == verdict, name
            assert (group["name"], group["path"]) == (name, str(forge / name))
        assert mod.classify_forge_group(forge / "improvement-queue", "improvement-queue")["errors"] == []
        assert mod.classify_forge_group(forge / "cognee", "cognee")["errors"] == []
        assert mod.classify_forge_group(forge / "filegroup", "filegroup")["errors"]
        for linked in ("lnk", "_campaign"):
            if linked in expected:
                [error] = mod.classify_forge_group(forge / linked, linked)["errors"]
                assert "link" in error, linked

    @pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                        reason="needs POSIX permissions and a non-root user")
    def test_unreadable_forge_folder_names_the_error(self, tmp_path):
        """A forge folder SKF cannot list is not SKF output, and `errors` says why."""
        forge = tmp_path / "forge-data"
        _write(forge / "locked" / "skill-brief.yaml")
        (forge / "locked").chmod(0)
        try:
            group = mod.classify_forge_group(forge / "locked", "locked")
        finally:
            (forge / "locked").chmod(0o755)
        assert (group["ownership"], group["foreign_entries"]) == ("foreign", [])
        [error] = group["errors"]
        assert "Cannot list" in error

    def test_scan_reports_forge_groups(self, tmp_path):
        _root, skills, forge, _expected = _forge_fixture(tmp_path)
        make_skill(skills, "cognee", "0.1.0")
        make_skill(skills, "notes", "1.0.0")
        _write(skills / ".export-manifest.json", {"exports": {"cognee": {}, "legacy": {}}})
        result = scan_inventory(str(skills), forge_data_folder=str(forge))
        assert result["status"] == "ok"
        assert (result["same_folder"], result["forge_data_folder"]) == (False, str(forge))
        by_name = {g["name"]: g["ownership"] for g in result["forge_groups"]}
        # The manifest keys and the skill folders, a manifest-only key included.
        assert by_name == {"cognee": "skf", "notes": "mixed", "legacy": "foreign"}
        missing = scan_inventory(str(skills), forge_data_folder=str(tmp_path / "no-forge"))
        assert {g["name"]: g["ownership"] for g in missing["forge_groups"]} == {
            "cognee": "absent", "notes": "absent", "legacy": "absent"}
        one = scan_inventory(str(skills), skill_filter="notes", forge_data_folder=str(forge))
        assert [g["name"] for g in one["forge_groups"]] == ["notes"]
        plain = scan_inventory(str(skills))
        assert "forge_groups" not in plain and "same_folder" not in plain

    def test_same_folder_uses_the_union_rule(self, tmp_path):
        out = tmp_path / "out"
        group = _same_folder_skill(out)

        def verdict(forge_folder=out):
            result = scan_inventory(str(out), forge_data_folder=str(forge_folder))
            assert (result["same_folder"], result["forge_groups"]) == (True, [])
            [entry] = result["skills"]
            return entry["ownership"], entry["foreign_entries"]

        assert verdict() == ("skf", [])
        assert verdict(tmp_path / "sub" / ".." / "out") == ("skf", [])
        _write(group / "0.1.0" / "NOTES.md")
        assert verdict() == ("mixed", ["0.1.0/NOTES.md"])
        (group / "0.1.0" / "NOTES.md").unlink()
        _write(group / "0.2.0" / "test-report-cognee-r.md")
        assert verdict() == ("skf", [])
        if _symlinks_supported(tmp_path):
            # A linked forge file is never SKF output, even in a marked version folder.
            _write(tmp_path / "pm.json")
            linked = group / "0.1.0" / "provenance-map.json"
            linked.unlink()
            linked.symlink_to(tmp_path / "pm.json")
            assert verdict() == ("mixed", ["0.1.0/provenance-map.json"])
            linked.unlink()
            _write(linked)
        # Read as a skills folder alone, the forge files are not SKF output.
        alone = _entry(out, "cognee")
        assert alone["ownership"] == "mixed" and "skill-brief.yaml" in alone["foreign_entries"]

    def test_inventory_never_owns_a_forge_folder_ccc_calls_foreign(self, tmp_path):
        ccc = _load(CCC_PY, "skf_ccc_for_forge_owned")
        root, _skills, forge, expected = _forge_fixture(tmp_path)
        scan = ccc.classify_folder(root, "forge-data", "forge", _listing(forge))
        owned = [name for name in expected if mod.classify_forge_group(forge / name, name)[
            "ownership"] in ("skf", "mixed", "reserved")]
        assert "cognee" in owned and "improvement-queue" in owned
        for name in owned:
            assert name in scan.owned_groups, f"inventory owns forge folder {name} but ccc calls it foreign"

    def test_ccc_never_excludes_a_forge_folder_the_inventory_calls_foreign(self, tmp_path):
        ccc = _load(CCC_PY, "skf_ccc_for_forge_foreign")
        root, _skills, forge, expected = _forge_fixture(tmp_path)
        scan = ccc.classify_folder(root, "forge-data", "forge", _listing(forge))
        verdicts = {name: mod.classify_forge_group(forge / name, name)["ownership"] for name in expected}
        for name, verdict in verdicts.items():
            if verdict in ("foreign", "empty", "absent"):
                assert name not in scan.owned_groups, (
                    f"ccc excludes forge folder {name} but the inventory calls it {verdict}")
        assert "deep" not in scan.owned_groups
        assert sorted(scan.owned_groups) == sorted(
            name for name, verdict in verdicts.items() if verdict in ("skf", "mixed", "reserved"))

    def test_same_folder_parity_with_ccc(self, tmp_path):
        ccc = _load(CCC_PY, "skf_ccc_for_same_folder")
        out = tmp_path / "out"
        _same_folder_skill(out)
        _write(out / "briefonly" / "skill-brief.yaml")
        _write(out / "briefnotes" / "skill-brief.yaml")
        _write(out / "briefnotes" / "NOTES.md")
        _make_flat(out, "module", subdirs=("references",))
        _write(out / "deep" / "a" / "b" / "x-result-latest.json")
        scan = ccc.classify_folder(tmp_path, "out", ("skills", "forge"), _listing(out))
        result = scan_inventory(str(out), forge_data_folder=str(out))
        verdicts = {e["name"]: e["ownership"] for e in result["skills"]}
        assert verdicts == {"cognee": "skf", "briefonly": "skf", "briefnotes": "mixed",
                            "module": "foreign", "deep": "foreign"}
        for name, verdict in verdicts.items():
            assert (name in scan.owned_groups) is (verdict in ("skf", "mixed")), name


class TestStagingFolders:
    """What an interrupted SKF run leaves before metadata.json is never foreign."""

    def test_folder_holding_no_file_is_not_foreign(self, skills):
        _write(skills / "x" / "1.0.0" / "x.skf-tmp" / "SKILL.md")
        (skills / "y" / "1.0.0" / "y" / "references").mkdir(parents=True)
        _make_version(skills, "z", "1.0.0")
        _make_version(skills, "m", "1.0.0", MARKED)
        (skills / "m" / "2.0.0" / "m.skf-tmp").mkdir(parents=True)
        assert _entry(skills, "x")["foreign_entries"] == []
        assert _entry(skills, "y")["foreign_entries"] == []
        assert _entry(skills, "z")["foreign_entries"] == ["1.0.0/"]
        m = _entry(skills, "m")
        assert (m["ownership"], m["foreign_entries"]) == ("skf", [])
        if _symlinks_supported(skills.parent):
            (skills.parent / "nothing").mkdir()
            (skills / "w" / "1.0.0" / "w").mkdir(parents=True)
            (skills / "w" / "1.0.0" / "w" / "ref").symlink_to(skills.parent / "nothing",
                                                              target_is_directory=True)
            # A link is content, even to an empty folder.
            assert _entry(skills, "w")["foreign_entries"] == ["1.0.0/"]

    def test_create_skill_staging_folder_is_never_a_skill(self, tmp_path):
        """create-skill stages into `_bmad-output/.skf-stage/{name}/`. When a folder setting
        names `_bmad-output`, that staging folder is never a skill folder or a forge folder."""
        out = tmp_path / "_bmad-output"
        _write(out / ".skf-stage" / "mylib" / "SKILL.md", "---\nname: mylib\n---\n")
        _write(out / ".skf-stage" / "mylib" / "metadata.json", {"generated_by": "create-skill"})
        for forge in (None, out, tmp_path / "forge-data"):
            result = scan_inventory(str(out), forge_data_folder=str(forge) if forge else None)
            assert result["status"] == "ok"
            assert (result["skills"], result["not_skf_output"]) == ([], []), forge
            assert result.get("forge_groups", []) == [], forge
            check = mod.write_check(out, "mylib", "0.1.0", forge)
            assert (check["verdict"], check["reason"]) == ("ok", None), check
        skills = tmp_path / "skills"
        _make_version(skills, "mylib", "0.1.0", MARKED)
        result = scan_inventory(str(skills), forge_data_folder=str(out))
        assert [(g["name"], g["ownership"]) for g in result["forge_groups"]] == [("mylib", "absent")]
        # Staged at `_bmad-output/{name}/`, the files would be the skill folder itself.
        _write(out / "mylib" / "SKILL.md", "---\nname: mylib\n---\n")
        _write(out / "mylib" / "metadata.json", {"generated_by": "create-skill"})
        assert mod.write_check(out, "mylib", "0.1.0", None)["verdict"] == "flat-layout"


# (name, version, verdict, reason) for the shapes of _write_check_fixture.
WRITE_CHECK_CASES = [
    ("absent", "1.0.0", "ok", None),
    ("module", "1.0.0", "not-skf-output", "not-skf-output"),
    ("moved", "1.0.0", "not-skf-output", "not-skf-output"),
    ("empty", "1.0.0", "ok", None),
    ("clutter", "1.0.0", "ok", None),
    ("dangling", "1.0.0", "ok", None),
    ("staging", "1.0.0", "ok", None),
    ("crash", "1.0.0", "ok", None),
    ("mixedclean", "2.0.0", "ok", None),
    ("mixedclean", "0.9.0", "not-skf-output", "version"),
    ("rc", "1.0.0", "ok", None),
    ("rc", "1.0.0-rc.1", "not-skf-output", "version"),
    ("flat", "1.0.0", "flat-layout", "flat-layout"),
    ("flatv", "2.0.0", "ok", None),
    ("lk", "1.0.0", "not-skf-output", "link"),
    ("file", "1.0.0", "not-skf-output", "not-a-folder"),
    ("danglinggroup", "1.0.0", "not-skf-output", "link"),
    ("improvement-queue", "1.0.0", "not-skf-output", "reserved-name"),
    ("vnotes", "1.0.0", "not-skf-output", "version"),
    ("linkedver", "2.0.0", "not-skf-output", "version"),
]
LINKED_WRITE_CHECK_SHAPES = frozenset({"dangling", "lk", "danglinggroup", "linkedver"})


def _write_check_fixture(tmp_path: Path, links: bool) -> Path:
    """A skills folder holding one shape per write-check rule."""
    skills = tmp_path / "skills"
    skills.mkdir()
    _make_flat(skills, "module", extra=("references/guide.md",))
    _make_version(skills, "moved", "1.0.0")
    _link_active(skills / "moved" / "active", "1.0.0")
    (skills / "empty").mkdir()
    _write(skills / "clutter" / ".DS_Store")
    _write(skills / "staging" / "1.0.0" / "staging.skf-tmp" / "SKILL.md")
    (skills / "crash" / "1.0.0" / "crash" / "references").mkdir(parents=True)
    _make_version(skills, "mixedclean", "1.0.0", MARKED)
    _write(skills / "mixedclean" / "README.md")
    _make_version(skills, "mixedclean", "0.9.0")
    _make_version(skills, "rc", "1.0.0", MARKED)
    _make_version(skills, "rc", "1.0.0-rc.1")
    _make_flat(skills, "flat", MARKED)
    _make_flat(skills, "flatv", MARKED)
    _make_version(skills, "flatv", "1.0.0", MARKED)
    _link_active(skills / "flatv" / "active", "1.0.0")
    _write(skills / "file")
    _make_version(skills, "improvement-queue", "1.0.0", MARKED)
    _make_version(skills, "vnotes", "1.0.0", MARKED)
    _write(skills / "vnotes" / "1.0.0" / "NOTES.md")
    if links:
        ext = tmp_path / "ext"
        (skills / "dangling").mkdir()
        (skills / "dangling" / "active").symlink_to("9.9.9", target_is_directory=True)
        _make_flat(ext, "lk", MARKED)
        (skills / "lk").symlink_to(ext / "lk", target_is_directory=True)
        (skills / "danglinggroup").symlink_to(tmp_path / "nowhere", target_is_directory=True)
        _make_version(skills, "linkedver", "1.0.0", MARKED)
        _make_version(ext, "linkedver", "2.0.0", MARKED)
        (skills / "linkedver" / "2.0.0").symlink_to(ext / "linkedver" / "2.0.0",
                                                    target_is_directory=True)
    return skills


class TestWriteCheck:
    """write_check: may a writer add {name}/{version}/{name}/ and flip active?"""

    @pytest.mark.parametrize("name, version, verdict, reason", WRITE_CHECK_CASES)
    def test_write_check(self, tmp_path, name, version, verdict, reason):
        links = _symlinks_supported(tmp_path)
        if name in LINKED_WRITE_CHECK_SHAPES and not links:
            pytest.skip("symlinks are not available")
        skills = _write_check_fixture(tmp_path, links)
        out = mod.write_check(skills, name, version, tmp_path / "forge-data")
        assert (out["verdict"], out["reason"]) == (verdict, reason), out
        assert (out["name"], out["version"]) == (name, version)
        if verdict == "ok":
            assert (out["folder"], out["detail"]) == (str(skills / name), None)
        else:
            assert out["detail"]
        if reason == "version":
            assert out["folder"] == str(skills / name / version)
            assert version in out["detail"]
        if reason == "reserved-name":
            assert out["folder"] == str(tmp_path / "forge-data" / name)
        assert out["marked_active_version"] == ("1.0.0" if name == "flatv" else None)

    @pytest.mark.parametrize("name", ["_batch", "cognee.skf-tmp", "_campaign", "improvement-queue"])
    def test_reserved_names_are_refused(self, tmp_path, name):
        out = mod.write_check(tmp_path / "skills", name, "1.0.0", tmp_path / "forge-data")
        assert (out["verdict"], out["reason"]) == ("not-skf-output", "reserved-name")
        side = "forge-data" if name in ("_campaign", "improvement-queue") else "skills"
        assert out["folder"] == str(tmp_path / side / name)

    def test_marked_active_version(self, skills):
        for name, active in (("st", "1.0.0"), ("su", "2.0.0")):
            _make_version(skills, name, "1.0.0", MARKED)
            _make_version(skills, name, "2.0.0")
            _link_active(skills / name / "active", active)
        _make_version(skills, "real", "active", MARKED)
        st = mod.write_check(skills, "st", None, None)
        assert (st["verdict"], st["marked_active_version"]) == ("ok", "1.0.0")
        assert mod.write_check(skills, "su", None, None)["marked_active_version"] is None
        assert mod.write_check(skills, "real", None, None)["marked_active_version"] == "active"

    def test_the_version_it_would_replace_names_its_generator(self, skills):
        """step 5b enhancement-2: quick-skill names the build at the version before it overwrites it."""
        pkg = _make_version(skills, "cognee", "1.0.0", {"generated_by": "create-skill", "confidence_tier": "Forge",
                                                         "skill_type": "single"})
        _write(pkg / "references" / "api.md")
        _write(pkg / "extraction-rules.yaml")
        _make_version(skills, "quick", "2.0.0", {"generated_by": "quick-skill", "confidence_tier": "Quick"})
        _make_version(skills, "marked", "1.0.0", {"tool_versions": {"skf": "3.0.0"}, "generated_by": 7})
        out = mod.write_check(skills, "cognee", "1.0.0", None)
        assert (out["verdict"], out["version_generated_by"], out["version_confidence_tier"]) == (
            "ok", "create-skill", "Forge")
        assert (mod.write_check(skills, "quick", "2.0.0", None)["version_generated_by"],
                mod.write_check(skills, "quick", "2.0.0", None)["version_confidence_tier"]) == ("quick-skill", "Quick")
        # A marker without a generator name, a new version, no version and a new skill name nothing.
        for name, version in (("marked", "1.0.0"), ("cognee", "2.0.0"), ("cognee", None), ("fresh", "1.0.0")):
            out = mod.write_check(skills, name, version, None)
            assert (out["verdict"], out["version_generated_by"], out["version_confidence_tier"]) == (
                "ok", None, None), (name, version)

    def test_the_cli_write_check_names_the_generator(self, skills):
        _make_version(skills, "cognee", "1.0.0", {"generated_by": "create-skill", "confidence_tier": "Forge"})
        code, out, _ = _run_inventory(str(skills), "--skill", "cognee", "--write-check", "--write-version", "1.0.0")
        assert code == 0
        check = out["write_check"]
        assert (check["verdict"], check["version_generated_by"], check["version_confidence_tier"]) == (
            "ok", "create-skill", "Forge")

    def test_same_folder_write_check(self, tmp_path):
        out = tmp_path / "out"
        _write(out / "cg" / "skill-brief.yaml")
        _write(out / "cg" / "0.1.0" / "provenance-map.json")
        same = mod.write_check(out, "cg", "0.1.0", out)
        assert (same["verdict"], same["foreign_entries"]) == ("ok", []), same
        other = mod.write_check(out, "cg", "0.1.0", tmp_path / "forge")
        assert (other["verdict"], other["reason"]) == ("not-skf-output", "not-skf-output")
        assert other["foreign_entries"] == ["0.1.0/", "skill-brief.yaml"]

    def test_missing_skills_folder_is_a_new_skill(self, tmp_path):
        out = mod.write_check(tmp_path / "nope", "x", "1.0.0", None)
        assert (out["verdict"], out["reason"], out["folder"]) == (
            "ok", None, str(tmp_path / "nope" / "x"))

    @pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                        reason="needs POSIX permissions and a non-root user")
    def test_unreadable_skill_folder_is_refused(self, skills):
        """A skill folder, or a marked version folder, SKF cannot list is never written into."""
        _make_version(skills, "grp", "1.0.0", MARKED)
        _make_version(skills, "ver", "1.0.0", MARKED)
        locked = [(skills / "grp", 0), (skills / "ver" / "1.0.0", 0o100)]  # 0o100: traversable only
        for path, mode in locked:
            path.chmod(mode)
        try:
            for name, (path, _mode) in zip(("grp", "ver"), locked):
                out = mod.write_check(skills, name, "2.0.0", None)
                assert (out["verdict"], out["reason"]) == ("not-skf-output", "unreadable"), out
                assert str(path) in out["detail"], out
        finally:
            for path, _mode in locked:
                path.chmod(0o755)

    @pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                        reason="needs POSIX permissions and a non-root user")
    @pytest.mark.parametrize("locked, mode, active", [
        ("0junk", 0, "0.1.0"),  # listed before the marked version
        ("zjunk", 0, "0.1.0"),  # listed after it
        ("0.2.0", 0, "0.2.0"),  # a marked version, the one `active` names
        ("0.2.0", 0o644, "0.1.0"),  # listable but not searchable
    ])
    def test_unreadable_folder_in_the_skill_folder_is_refused(self, skills, locked, mode, active):
        """A folder SKF cannot list or search is refused on every Python version.

        pathlib raises inside such a folder before Python 3.14 and returns False
        from 3.14 on: neither may crash the helper or let a writer in.
        """
        _make_version(skills, "a", "0.1.0", MARKED)
        if locked == "0.2.0":
            _make_version(skills, "a", locked, MARKED)
        else:
            _write(skills / "a" / locked / "notes.md")
        _link_active(skills / "a" / "active", active)
        path = skills / "a" / locked
        path.chmod(mode)
        try:
            out = mod.write_check(skills, "a", "0.3.0", None)
            code, cli, _err = _run_inventory(str(skills), "--skill", "a", "--write-check",
                                             "--write-version", "0.3.0")
            scan = scan_inventory(str(skills))
        finally:
            path.chmod(0o755)
        assert (out["verdict"], out["reason"]) == ("not-skf-output", "unreadable"), out
        assert str(path) in out["detail"], out
        assert out["foreign_entries"] == [locked + "/"]
        assert (code, cli["write_check"]["reason"]) == (0, "unreadable")
        assert scan["status"] == "ok"
        [entry] = scan["skills"]
        assert (entry["ownership"], entry["foreign_entries"]) == ("mixed", [locked + "/"])
        assert any(str(path) in error for error in entry["errors"]), entry["errors"]

    @pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                        reason="needs POSIX permissions and a non-root user")
    def test_unreadable_folder_in_a_same_folder_skill_is_refused(self, tmp_path):
        """Where both settings name one folder, forge files SKF cannot reach are refused too."""
        out = tmp_path / "out"
        _make_version(out, "a", "0.1.0", MARKED)
        _write(out / "a" / "0.2.0" / "provenance-map.json")
        locked = out / "a" / "0.2.0"
        locked.chmod(0o644)  # listable but not searchable
        try:
            check = mod.write_check(out, "a", "0.3.0", out)
            [entry] = scan_inventory(str(out), forge_data_folder=str(out))["skills"]
        finally:
            locked.chmod(0o755)
        assert (check["verdict"], check["reason"]) == ("not-skf-output", "unreadable"), check
        assert str(locked) in check["detail"], check
        assert (entry["ownership"], entry["foreign_entries"]) == ("mixed", ["0.2.0/"])
        assert any(str(locked) in error for error in entry["errors"]), entry["errors"]

    @pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                        reason="needs POSIX permissions and a non-root user")
    def test_folder_it_cannot_search_deeper_down_is_content(self, skills):
        """Deeper in a folder SKF did not write, a folder it cannot search is content."""
        _make_version(skills, "a", "0.1.0", MARKED)
        _write(skills / "a" / "junk" / "sub" / "notes.md")
        sub = skills / "a" / "junk" / "sub"
        sub.chmod(0o644)
        try:
            out = mod.write_check(skills, "a", "0.3.0", None)
            entry = _entry(skills, "a")
        finally:
            sub.chmod(0o755)
        assert (out["verdict"], out["foreign_entries"]) == ("ok", ["junk/"]), out
        assert (entry["ownership"], entry["foreign_entries"], entry["errors"]) == (
            "mixed", ["junk/"], [])

    def test_marked_active_version_stays_in_the_group(self, skills):
        """`active` names a version only as a link to a marked folder of its own group."""
        _make_version(skills, "out", "1.0.0", MARKED)
        _make_version(skills, "other", "1.0.0", MARKED)
        _link_active(skills / "out" / "active", "../other/1.0.0")
        assert mod.write_check(skills, "out", None, None)["marked_active_version"] is None
        _make_version(skills, "stg", "1.0.0", MARKED)
        _make_version(skills, "stg", "2.0.0.skf-tmp", MARKED)
        _link_active(skills / "stg" / "active", "2.0.0.skf-tmp")
        stg = mod.write_check(skills, "stg", None, None)
        assert (stg["verdict"], stg["marked_active_version"]) == ("ok", None)

    def test_same_folder_through_an_alias(self, tmp_path):
        """A forge setting that reaches the skills folder through a link names the same folder."""
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        out = tmp_path / "out"
        _write(out / "cg" / "skill-brief.yaml")
        _write(out / "cg" / "0.1.0" / "provenance-map.json")
        alias = tmp_path / "alias"
        alias.symlink_to(out, target_is_directory=True)
        check = mod.write_check(out, "cg", "0.1.0", alias)
        assert (check["verdict"], check["foreign_entries"]) == ("ok", []), check
        result = scan_inventory(str(out), forge_data_folder=str(alias))
        assert (result["same_folder"], result["forge_groups"]) == (True, [])

    def test_same_folder_package_named_like_staging(self, tmp_path):
        """A skill named `*-tmp` keeps its own package: unmarked, it is not SKF output."""
        out = tmp_path / "out"
        _write(out / "data-tmp" / "skill-brief.yaml")
        _make_version(out, "data-tmp", "1.0.0")
        _write(out / "data-tmp" / "1.0.0" / "data-tmp" / "references" / "guide.md")
        [entry] = scan_inventory(str(out), forge_data_folder=str(out))["skills"]
        assert (entry["ownership"], entry["foreign_entries"]) == ("mixed", ["1.0.0/"])
        check = mod.write_check(out, "data-tmp", "1.0.0", out)
        assert (check["verdict"], check["reason"]) == ("not-skf-output", "not-skf-output"), check
        # Marked, it is SKF's own, and a stack's `*-tmp` staging folder beside it still is.
        _write(out / "data-tmp" / "1.0.0" / "data-tmp" / "metadata.json", MARKED)
        _write(out / "data-tmp" / "1.0.0" / "lib-tmp" / "partial.md")
        [entry] = scan_inventory(str(out), forge_data_folder=str(out))["skills"]
        assert (entry["ownership"], entry["foreign_entries"]) == ("skf", [])
        assert mod.write_check(out, "data-tmp", "1.0.0", out)["verdict"] == "ok"


def _run_inventory(*args: str) -> tuple[int, dict | None, str]:
    proc = subprocess.run([sys.executable, str(INVENTORY_PY), *args], capture_output=True, timeout=60)
    stdout = proc.stdout.decode("utf-8")
    return (proc.returncode, json.loads(stdout) if stdout.strip() else None,
            proc.stderr.decode("utf-8", errors="replace"))


def test_cli_write_check_and_forge_flags(tmp_path):
    skills = tmp_path / "skills"
    _make_flat(skills, "module", extra=("references/guide.md",))
    code, out, _ = _run_inventory(str(skills), "--skill", "module", "--write-check",
                                  "--write-version", "1.0.0")
    assert (code, out["status"]) == (0, "ok")
    assert (out["same_folder"], out["forge_data_folder"]) == (False, None)
    assert (out["write_check"]["verdict"], out["write_check"]["version"]) == ("not-skf-output", "1.0.0")
    code, out, _ = _run_inventory(str(tmp_path / "missing"), "--skill", "a", "--write-check")
    assert (code, out["write_check"]["verdict"]) == (0, "ok")
    code, out, _ = _run_inventory(str(skills), "--skill", "module", "--write-check",
                                  "--forge-data-folder", str(skills))
    assert (code, out["same_folder"]) == (0, True)
    for argv in (
        [str(skills), "--write-check"],
        [str(skills), "--skill", "a", "--write-version", "1"],
        [str(skills), "--skill", "a/b", "--write-check"],
        [str(skills), "--skill", "a\\b", "--write-check"],
        [str(skills), "--skill", "..", "--write-check"],
        [str(skills), "--skill", "a", "--write-check", "--write-version", "."],
        [str(skills), "--skill", "a", "--write-check", "--write-version"],
        [str(skills), "--skill", "--write-check"],
        ["--skill", "a", "--write-check"],
        [str(skills), "--forge-data-folder"],
        [str(skills), "--forge-data-folder", "--manifest-only"],
    ):
        code, out, err = _run_inventory(*argv)
        assert (code, out["status"], out["code"]) == (1, "error", "USAGE"), argv
        assert "Usage:" in err, argv
    code, out, _ = _run_inventory(str(skills), "--forge-data-folder", str(tmp_path / "no-forge"))
    assert code == 0
    assert [(g["name"], g["ownership"]) for g in out["forge_groups"]] == [("module", "absent")]
    _write(tmp_path / "afile")
    code, out, _ = _run_inventory(str(tmp_path / "afile"), "--skill", "a", "--write-check")
    assert (code, out["code"]) == (1, "DIR_NOT_FOUND")


# --------------------------------------------------------------------------
# version: normalize, order, next patch, compose bump, primary library
# --------------------------------------------------------------------------


class TestVersionNormalize:
    @pytest.mark.parametrize("text, normalized, rule", [
        ("1.0.0", "1.0.0", "version"),
        ("0.5.0-beta.1", "0.5.0-beta.1", "version"),
        # Build metadata stripped (the Version Sanitization table).
        ("1.0.0-rc.2+build.456", "1.0.0-rc.2", "version"),
        ("2.0.0+20260404", "2.0.0", "version"),
        ("2.0", "2.0.0", "version"),
        ("18", "18.0.0", "version"),
        ("v1.2.3", "1.2.3", "version"),
        ("1.02.3", "1.2.3", "version"),
        ("1.2.3.4", "1.2.3.4", "version"),
        ("2.0.0rc1", "2.0.0rc1", "version"),
        ("1.0.0.dev0", "1.0.0.dev0", "version"),
        (" 1.2.3 ", "1.2.3", "version"),
        # A range reduces to its lower bound.
        ("^18.2.0", "18.2.0", "range"),
        ("~1.2.3", "1.2.3", "range"),
        ("~=1.4", "1.4.0", "range"),
        ("~> 1.2", "1.2.0", "range"),
        (">=1.0, <2.0", "1.0.0", "range"),
        (">=1.0 <2.0", "1.0.0", "range"),
        (">1.2.3", "1.2.3", "range"),
        ("==2.31.0", "2.31.0", "range"),
        ("=1.2.3", "1.2.3", "range"),
        (">=1.2, >=1.4, <2", "1.4.0", "range"),
        ("1.2.x", "1.2.0", "range"),
        ("1.x", "1.0.0", "range"),
        ("==1.2.*", "1.2.0", "range"),
        ("1.2.3 - 2.0.0", "1.2.3", "range"),
        ("^2.0.0 || ^1.2.3", "1.2.3", "range"),
        ("npm:react@^18.2.0", "18.2.0", "range"),
        ("workspace:^1.0.0", "1.0.0", "range"),
        ("^1.0.0-rc.1+build", "1.0.0-rc.1", "range"),
    ])
    def test_normalizes(self, text, normalized, rule):
        out = mod.normalize_version(text)
        assert (out["normalized"], out["rule"], out["reason"]) == (normalized, rule, None), out
        # Idempotent: a normalized version normalizes to itself.
        assert mod.normalize_version(normalized)["normalized"] == normalized

    def test_reports_build_metadata(self):
        assert mod.normalize_version("1.0.0-rc.2+build.456")["build_metadata"] == "build.456"
        assert mod.normalize_version("1.0.0")["build_metadata"] is None

    @pytest.mark.parametrize("text", [
        "", "   ", "*", "x", "latest", "<2.0.0", "<=2, !=1.5", "1.2.3-", "1.0.0+", "1.0.0+a+b",
        "file:../lib", "git+https://github.com/o/r.git#v1.0.0", "workspace:*", "^banana",
        ">=1.0 <two", "1.x.3", "^1.0 || latest",
    ])
    def test_names_no_version(self, text):
        out = mod.normalize_version(text)
        assert out["normalized"] is None and out["rule"] is None, out
        assert out["reason"], out


class TestVersionOrder:
    def test_numbers_compare_as_numbers(self):
        out = mod.order_versions("1.9.0", "1.10.0")
        assert (out["order"], out["major_minor"], out["higher"]) == ("lower", "lower", "1.10.0")
        assert mod.order_versions("1.10.0", "1.9.0")["order"] == "higher"
        assert mod.order_versions("0.10.0", "0.9.9")["order"] == "higher"

    @pytest.mark.parametrize("a, b", [
        ("1.0", "1.0.0"),
        ("1.0.0+build.1", "1.0.0+build.2"),
        ("v2.1.0", "2.1.0"),
        ("^18.2.0", "18.2.0"),
        ("1.2.3.0", "1.2.3"),
    ])
    def test_equal(self, a, b):
        out = mod.order_versions(a, b)
        assert (out["order"], out["higher"]) == ("equal", None), out

    def test_semver_precedence_chain(self):
        chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
                 "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]
        for lower, higher in zip(chain, chain[1:]):
            assert mod.order_versions(lower, higher)["order"] == "lower", (lower, higher)
            assert mod.order_versions(higher, lower)["order"] == "higher", (lower, higher)

    def test_pre_release_digit_runs_compare_as_numbers(self):
        assert mod.order_versions("2.0.0rc2", "2.0.0rc10")["order"] == "lower"
        assert mod.order_versions("1.0.0-1", "1.0.0-alpha")["order"] == "lower"

    def test_major_minor(self):
        out = mod.order_versions("1.2.9", "1.2.0")
        assert (out["order"], out["major_minor"]) == ("higher", "equal")
        out = mod.order_versions("1.9.5", "2.0.1")
        assert (out["order"], out["major_minor"]) == ("lower", "lower")

    def test_raises_on_a_non_version(self):
        with pytest.raises(ValueError, match="latest"):
            mod.order_versions("latest", "1.0.0")


class TestNextPatch:
    @pytest.mark.parametrize("text, expected", [
        ("1.2.3", "1.2.4"),
        ("1.9.9", "1.9.10"),
        ("2.0", "2.0.1"),
        ("v0.5.0", "0.5.1"),
        ("1.2.3+build.7", "1.2.4"),
        ("1.2.3.4", "1.2.4"),
        # The release of a pre-release, as semver's patch increment gives.
        ("1.2.3-rc.1", "1.2.3"),
        ("2.0.0rc1", "2.0.0"),
    ])
    def test_next_patch(self, text, expected):
        out = mod.next_patch(text)
        assert out["next_patch"] == expected, out
        assert mod.order_versions(expected, text)["order"] == "higher"

    def test_raises_on_a_non_version(self):
        with pytest.raises(ValueError):
            mod.next_patch("latest")


class TestComposeBump:
    def test_removed_library_is_major(self):
        out = mod.compose_bump("3.0.5", ["react", "zod"], ["react"])
        assert (out["bump"], out["version"], out["removed"], out["added"]) == ("major", "4.0.0", ["zod"], [])

    def test_replaced_library_is_major(self):
        out = mod.compose_bump("1.4.2", ["react", "zod"], ["react", "valibot"])
        assert (out["bump"], out["version"], out["removed"], out["added"]) == (
            "major", "2.0.0", ["zod"], ["valibot"])

    def test_added_library_is_minor(self):
        out = mod.compose_bump("1.4.2", ["react"], ["react", "zod"])
        assert (out["bump"], out["version"], out["added"]) == ("minor", "1.5.0", ["zod"])

    def test_same_libraries_is_minor(self):
        assert mod.compose_bump("1.9.0", ["a"], ["a"])["version"] == "1.10.0"

    def test_prior_is_normalized(self):
        out = mod.compose_bump("v2.0.0-rc.1+b", ["a"], ["a"])
        assert (out["prior_normalized"], out["version"]) == ("2.0.0-rc.1", "2.1.0")

    def test_prior_that_is_no_version_raises(self):
        with pytest.raises(ValueError, match="latest"):
            mod.compose_bump("latest", ["a"], ["a"])

    def test_refuses_a_result_not_above_the_prior(self, monkeypatch):
        monkeypatch.setattr(mod, "_order_key", lambda parsed: ())
        with pytest.raises(mod.NotIncreasingError, match="not above"):
            mod.compose_bump("1.0.0", ["a"], ["a"])
        with pytest.raises(mod.NotIncreasingError, match="not above"):
            mod.next_patch("1.0.0")


class TestPrimaryLibrary:
    def test_highest_import_count(self):
        out = mod.primary_library([
            {"name": "zod", "import_count": 3, "version": "3.22.0"},
            {"name": "react", "import_count": 40, "version": "^18.2.0"},
        ])
        assert (out["primary"], out["version"], out["reason"], out["fallback"]) == (
            "react", "18.2.0", "highest-import-count", False)
        assert out["tied"] == ["react"]

    def test_tie_goes_to_the_lowest_name(self):
        rows = [{"name": "react", "import_count": 12, "version": "18.2.0"},
                {"name": "Axios", "import_count": 12, "version": "1.6.0"},
                {"name": "zod", "import_count": 1, "version": "3.0.0"}]
        out = mod.primary_library(rows)
        assert (out["primary"], out["version"], out["reason"], out["tied"]) == (
            "Axios", "1.6.0", "tie-name-order", ["Axios", "react"])
        assert mod.primary_library(list(reversed(rows))) == out

    def test_tie_prefers_a_usable_version(self):
        out = mod.primary_library([
            {"name": "alpha", "import_count": 5, "version": "workspace:*"},
            {"name": "beta", "import_count": 5, "version": "~2.1.0"},
        ])
        assert (out["primary"], out["version"], out["reason"]) == ("beta", "2.1.0", "tie-usable-version")

    def test_no_usable_version_falls_back_to_1_0_0(self):
        out = mod.primary_library([{"name": "lib", "import_count": 2, "version": "latest"},
                                   {"name": "other", "import_count": 1}])
        assert (out["primary"], out["version"], out["fallback"], out["version_input"]) == (
            "lib", "1.0.0", True, "latest")

    def test_no_candidates(self):
        out = mod.primary_library([])
        assert (out["primary"], out["version"], out["reason"]) == (None, "1.0.0", "no-candidates")

    @pytest.mark.parametrize("row", [
        {"import_count": 1}, {"name": "", "import_count": 1}, {"name": "a", "import_count": -1},
        {"name": "a", "import_count": True}, {"name": "a", "import_count": 1.5},
        {"name": "a", "import_count": 1, "version": 2}, "a",
    ])
    def test_malformed_candidate_raises(self, row):
        with pytest.raises(ValueError):
            mod.primary_library([row])


class TestIsoTime:
    @pytest.mark.parametrize("text, expected", [
        ("2026-04-04T10:00:00Z", "2026-04-04T10:00:00Z"),
        ("2026-04-04T10:00:00+02:00", "2026-04-04T08:00:00Z"),
        ("2026-04-04T01:30:00-0230", "2026-04-04T04:00:00Z"),
        ("2026-04-04T10:00:00.123456789+00:00", "2026-04-04T10:00:00Z"),
        ("2026-04-04 10:00", "2026-04-04T10:00:00Z"),
        ("2026-04-04", "2026-04-04T00:00:00Z"),
    ])
    def test_parses_to_utc(self, text, expected):
        assert mod._utc_text(mod._parse_iso_utc(text)) == expected

    @pytest.mark.parametrize("value", [None, 5, "", "yesterday", "2026-13-01", "2026-04-04T25:00:00Z",
                                       "04/04/2026", "0001-01-01T00:00:00+05:00"])
    def test_rejects(self, value):
        assert mod._parse_iso_utc(value) is None


# --------------------------------------------------------------------------
# resolve: the version a reading workflow uses, and its paths
# --------------------------------------------------------------------------


def _resolve_fixture(tmp_path: Path, manifest=None, link=None, versions=("0.5.0", "0.6.0")):
    """skills/cognee with a package per version, forge/cognee, an optional manifest and link."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for v in versions:
        _make_version(skills, "cognee", v, metadata={**MARKED, "version": v})
        (forge / "cognee" / v).mkdir(parents=True, exist_ok=True)
    (forge / "cognee").mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        _write(skills / ".export-manifest.json", manifest)
    if link is not None:
        _link_active(skills / "cognee" / "active", link)
    return skills, forge


def _manifest(active, statuses=None):
    statuses = statuses or {active: "active"}
    return {"schema_version": "2", "exports": {"cognee": {
        "active_version": active,
        "versions": {v: {"status": s, "ides": [], "last_exported": "2026-03-15"}
                     for v, s in statuses.items()}}}}


def _resolve(skills, forge, version=None) -> dict:
    out = mod.resolve_skill(skills, "cognee", forge, version)
    assert out is not None
    return out


@pytest.fixture()
def links_ok(tmp_path):
    if not _symlinks_supported(tmp_path):
        pytest.skip("symlinks unavailable")


class TestResolve:
    def test_manifest_and_link_agree(self, tmp_path, links_ok):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.6.0"), link="0.6.0")
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["layout"]) == ("0.6.0", "manifest-and-link", "versioned")
        assert (out["active_version"], out["symlink_target"]) == ("0.6.0", "0.6.0")
        assert out["skill_package"] == str(skills / "cognee" / "0.6.0" / "cognee")
        assert out["forge_version"] == str(forge / "cognee" / "0.6.0")
        assert out["skill_package_exists"] is True
        assert out["manifest_last_exported"] == "2026-03-15"

    def test_manifest_lags_link(self, tmp_path, links_ok):
        """The [N] case: the link wins, and provenance comes from its version folder."""
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"), link="0.6.0")
        _write(forge / "cognee" / "0.5.0" / "provenance-map.json", {"generated_at": "2026-03-01T00:00:00Z"})
        _write(forge / "cognee" / "0.6.0" / "provenance-map.json",
               {"generated_at": "2026-04-04T10:00:00+02:00"})
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"]) == ("0.6.0", "manifest-lags-link")
        assert "export-skill" in out["detail"]
        assert out["forge_version"] == str(forge / "cognee" / "0.6.0")
        assert out["paths"]["provenance_map"] == {
            "path": str(forge / "cognee" / "0.6.0" / "provenance-map.json"), "source": "versioned",
            "versioned": str(forge / "cognee" / "0.6.0" / "provenance-map.json"),
            "flat": str(forge / "cognee" / "provenance-map.json")}
        cands = out["candidates"]
        assert (cands["manifest"]["version"], cands["manifest"]["generated_at"],
                cands["manifest"]["generated_at_source"]) == ("0.5.0", "2026-03-01T00:00:00Z", "provenance-map")
        assert (cands["symlink"]["version"], cands["symlink"]["generated_at"]) == ("0.6.0", "2026-04-04T08:00:00Z")

    def test_link_to_a_version_without_package_keeps_the_manifest(self, tmp_path, links_ok):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"), versions=("0.5.0",))
        (skills / "cognee" / "0.7.0").mkdir()
        _link_active(skills / "cognee" / "active", "0.7.0")
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["symlink_target"]) == ("0.5.0", "manifest", "0.7.0")
        assert out["candidates"]["symlink"]["skill_package_exists"] is False

    def test_manifest_only(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"))
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["symlink_target"]) == ("0.5.0", "manifest", None)
        assert out["candidates"]["symlink"] is None

    def test_link_only(self, tmp_path, links_ok):
        skills, forge = _resolve_fixture(tmp_path, link="0.5.0")
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["active_version"]) == ("0.5.0", "link", None)
        assert out["candidates"]["manifest"] is None

    def test_newest_on_disk(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, versions=("1.9.0", "1.10.0", "1.2.0"))
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"]) == ("1.10.0", "newest-on-disk")
        assert [v["version"] for v in out["versions"]] == ["1.10.0", "1.9.0", "1.2.0"]

    def test_flat_layout(self, tmp_path):
        skills, forge = tmp_path / "skills", tmp_path / "forge"
        _make_flat(skills, "cognee", metadata=MARKED)
        _write(forge / "cognee" / "provenance-map.json", {"generated_at": "2026-01-01T00:00:00Z"})
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["layout"]) == (None, "flat-layout", "flat")
        assert (out["skill_package"], out["forge_version"]) == (str(skills / "cognee"), None)
        assert out["paths"]["metadata"]["source"] == "flat"
        assert out["paths"]["metadata"]["versioned"] is None
        assert out["paths"]["provenance_map"]["path"] == str(forge / "cognee" / "provenance-map.json")
        assert out["versions"] == []

    def test_flat_package_folders_are_not_versions(self, tmp_path):
        skills, forge = tmp_path / "skills", tmp_path / "forge"
        _make_flat(skills, "cognee", metadata=MARKED, extra=("references/cognee/guide.md",))
        out = _resolve(skills, forge)
        assert (out["reason"], out["versions"]) == ("flat-layout", [])

    def test_missing_on_disk(self, tmp_path):
        skills, forge = tmp_path / "skills", tmp_path / "forge"
        _write(skills / ".export-manifest.json", _manifest("0.5.0"))
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["skill_package_exists"]) == ("0.5.0", "missing", False)
        assert out["paths"]["metadata"]["path"] is None
        out_none = mod.resolve_skill(skills, "absent", forge)
        assert out_none is None
        (skills / "empty").mkdir()
        out = mod.resolve_skill(skills, "empty", forge)
        assert (out["chosen_version"], out["reason"], out["layout"]) == (None, "missing", "none")

    def test_requested_version(self, tmp_path, links_ok):
        """The [M] case: the operator picks the manifest version over the link."""
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"), link="0.6.0")
        out = _resolve(skills, forge, version="0.5.0")
        assert (out["chosen_version"], out["reason"]) == ("0.5.0", "requested")
        assert out["forge_version"] == str(forge / "cognee" / "0.5.0")

    def test_versioned_first_then_flat(self, tmp_path):
        """test-skill's read sites: provenance and evidence from {forge_version}, flat only as the fallback."""
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.6.0"))
        _write(forge / "cognee" / "provenance-map.json", {})
        _write(forge / "cognee" / "evidence-report.md", "# old flat report\n")
        out = _resolve(skills, forge)
        assert out["paths"]["provenance_map"]["source"] == "flat"
        assert out["paths"]["evidence_report"]["path"] == str(forge / "cognee" / "evidence-report.md")
        _write(forge / "cognee" / "0.6.0" / "provenance-map.json", {})
        _write(forge / "cognee" / "0.6.0" / "evidence-report.md", "# report\n")
        out = _resolve(skills, forge)
        assert out["paths"]["provenance_map"]["path"] == str(forge / "cognee" / "0.6.0" / "provenance-map.json")
        assert out["paths"]["evidence_report"]["source"] == "versioned"
        assert out["paths"]["metadata"] == {
            "path": str(skills / "cognee" / "0.6.0" / "cognee" / "metadata.json"), "source": "versioned",
            "versioned": str(skills / "cognee" / "0.6.0" / "cognee" / "metadata.json"),
            "flat": str(skills / "cognee" / "metadata.json")}

    def test_provenance_time_falls_back_to_mtime(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"))
        prov = forge / "cognee" / "0.5.0" / "provenance-map.json"
        _write(prov, {"generated_at": "not a date"})
        os.utime(prov, (1767225600, 1767225600))  # 2026-01-01T00:00:00Z
        cand = _resolve(skills, forge)["candidates"]["manifest"]
        assert (cand["generated_at"], cand["generated_at_source"]) == ("2026-01-01T00:00:00Z", "mtime")
        prov.unlink()
        cand = _resolve(skills, forge)["candidates"]["manifest"]
        assert (cand["provenance_map"], cand["generated_at"], cand["generated_at_source"]) == (None, None, None)

    def test_versions_counts_and_newest_non_deprecated(self, tmp_path, links_ok):
        """drop-skill's active-version guard and repoint, rename-skill's version count."""
        statuses = {"1.10.0": "deprecated", "1.9.0": "archived", "1.2.0": "active", "0.1.0": "deprecated"}
        skills, forge = _resolve_fixture(tmp_path, _manifest("1.2.0", statuses),
                                         link="1.2.0", versions=("1.10.0", "1.9.0", "1.2.0", "2.0.0"))
        out = _resolve(skills, forge)
        assert out["versions"] == [
            {"version": "2.0.0", "status": None, "in_manifest": False, "on_disk": True},
            {"version": "1.10.0", "status": "deprecated", "in_manifest": True, "on_disk": True},
            {"version": "1.9.0", "status": "archived", "in_manifest": True, "on_disk": True},
            {"version": "1.2.0", "status": "active", "in_manifest": True, "on_disk": True},
            {"version": "0.1.0", "status": "deprecated", "in_manifest": True, "on_disk": False},
        ]
        assert out["newest_non_deprecated"] == "1.9.0"
        assert out["newest_on_disk"] == "2.0.0"
        assert out["counts"] == {"total": 5, "manifest": 4, "on_disk": 4, "non_deprecated": 2,
                                 "by_status": {"deprecated": 2, "archived": 1, "active": 1}}

    def test_staging_and_dot_folders_are_not_versions(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"), versions=("0.5.0",))
        (skills / "cognee" / "0.6.0.skf-tmp" / "cognee").mkdir(parents=True)
        (skills / "cognee" / ".hidden" / "cognee").mkdir(parents=True)
        (skills / "cognee" / "notes").mkdir()
        assert [v["version"] for v in _resolve(skills, forge)["versions"]] == ["0.5.0"]

    def test_v1_manifest(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, {"exports": {"cognee": {
            "active_version": "0.6.0", "versions": ["0.5.0", "0.6.0"]}}, "updated_at": "2026-02-02"})
        out = _resolve(skills, forge)
        assert (out["chosen_version"], out["reason"], out["manifest_last_exported"]) == (
            "0.6.0", "manifest", "2026-02-02")
        assert {v["version"]: v["status"] for v in out["versions"]} == {"0.6.0": "active", "0.5.0": "archived"}

    def test_manifest_version_that_is_not_a_folder_name(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, _manifest("../../etc"), versions=("0.5.0",))
        out = _resolve(skills, forge)
        assert out["active_version"] is None
        assert (out["chosen_version"], out["reason"]) == ("0.5.0", "newest-on-disk")
        assert any("not a folder name" in e for e in out["errors"])

    def test_malformed_manifest(self, tmp_path):
        skills, forge = _resolve_fixture(tmp_path, versions=("0.5.0",))
        _write(skills / ".export-manifest.json", "{not json")
        out = _resolve(skills, forge)
        assert out["manifest_error"] and "JSON" in out["manifest_error"]
        assert out["chosen_version"] == "0.5.0"
        _write(skills / ".export-manifest.json", [])
        assert _resolve(skills, forge)["manifest_error"] == "the export manifest is not a JSON object"

    def test_link_that_leaves_the_skill_folder_is_ignored(self, tmp_path, links_ok):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"), versions=("0.5.0",))
        elsewhere = tmp_path / "elsewhere" / "9.9.9"
        (elsewhere / "cognee").mkdir(parents=True)
        (skills / "cognee" / "active").symlink_to(elsewhere)
        out = _resolve(skills, forge)
        assert (out["symlink_target"], out["chosen_version"]) == (None, "0.5.0")
        assert any("does not lead to a version folder" in e for e in out["errors"])

    def test_broken_link_and_real_active_folder(self, tmp_path, links_ok):
        skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"), versions=("0.5.0",))
        (skills / "cognee" / "active").symlink_to("gone")
        out = _resolve(skills, forge)
        assert out["symlink_target"] is None and any("broken" in e for e in out["errors"])
        (skills / "cognee" / "active").unlink()
        (skills / "cognee" / "active" / "cognee").mkdir(parents=True)
        out = _resolve(skills, forge)
        assert out["symlink_target"] is None and any("not a link" in e for e in out["errors"])
        assert "active" not in [v["version"] for v in out["versions"]]


def test_cli_resolve(tmp_path):
    skills, forge = _resolve_fixture(tmp_path, _manifest("0.5.0"))
    code, out, _ = _run_inventory("resolve", str(skills), "--skill", "cognee", "--forge-data-folder", str(forge))
    assert (code, out["status"], out["resolve"]["chosen_version"]) == (0, "ok", "0.5.0")
    assert (out["skills_folder"], out["forge_data_folder"]) == (str(skills), str(forge))
    code, out, _ = _run_inventory("resolve", str(skills), "--skill", "cognee", "--forge-data-folder", str(forge),
                                  "--version", "0.6.0")
    assert (code, out["resolve"]["chosen_version"], out["resolve"]["reason"]) == (0, "0.6.0", "requested")
    code, out, _ = _run_inventory("resolve", str(skills), "--skill", "absent", "--forge-data-folder", str(forge))
    assert (code, out["code"]) == (1, "SKILL_NOT_FOUND")
    code, out, _ = _run_inventory("resolve", str(tmp_path / "nope"), "--skill", "cognee",
                                  "--forge-data-folder", str(forge))
    assert (code, out["code"]) == (1, "DIR_NOT_FOUND")
    for argv in (
        ["resolve"],
        ["resolve", "--skill", "cognee", "--forge-data-folder", str(forge)],
        ["resolve", str(skills), "--forge-data-folder", str(forge)],
        ["resolve", str(skills), "--skill", "cognee"],
        ["resolve", str(skills), "--skill", "cognee", "--forge-data-folder"],
        ["resolve", str(skills), "--skill", "../x", "--forge-data-folder", str(forge)],
        ["resolve", str(skills), "--skill", "cognee", "--forge-data-folder", str(forge), "--version", "a/b"],
        ["resolve", str(skills), "--skill", "cognee", "--forge-data-folder", str(forge), "--versions", "1"],
        ["resolve", str(skills), "--skill", "cognee", "--forge-data-folder", str(forge), "extra"],
    ):
        code, out, err = _run_inventory(*argv)
        assert (code, out["status"], out["code"]) == (1, "error", "USAGE"), argv
        assert "Usage:" in err, argv


def test_cli_version(tmp_path):
    code, out, _ = _run_inventory("version", "normalize", "^18.2.0")
    assert (code, out["status"], out["command"], out["normalized"], out["rule"]) == (
        0, "ok", "normalize", "18.2.0", "range")
    code, out, _ = _run_inventory("version", "normalize", "latest")
    assert (code, out["status"], out["code"], out["normalized"]) == (1, "error", "NOT_A_VERSION", None)
    code, out, _ = _run_inventory("version", "order", "1.9.0", "1.10.0")
    assert (code, out["order"], out["higher"]) == (0, "lower", "1.10.0")
    code, out, _ = _run_inventory("version", "order", "1.9.0", "*")
    assert (code, out["code"]) == (1, "NOT_A_VERSION")
    code, out, _ = _run_inventory("version", "next-patch", "1.2.3+build.9")
    assert (code, out["next_patch"]) == (0, "1.2.4")
    code, out, _ = _run_inventory("version", "bump", "--prior", "3.0.5", "--prior-libraries", "react, zod",
                                  "--libraries", "react")
    assert (code, out["bump"], out["version"], out["removed"]) == (0, "major", "4.0.0", ["zod"])
    code, out, _ = _run_inventory("version", "bump", "--prior", "3.0.5", "--prior-libraries", "",
                                  "--libraries", "react")
    assert (code, out["bump"], out["version"], out["added"]) == (0, "minor", "3.1.0", ["react"])
    code, out, _ = _run_inventory("version", "bump", "--prior", "nope", "--prior-libraries", "a",
                                  "--libraries", "a")
    assert (code, out["code"]) == (1, "NOT_A_VERSION")
    candidates = tmp_path / "candidates.json"
    _write(candidates, [{"name": "react", "import_count": 9, "version": "^18.2.0"},
                        {"name": "next", "import_count": 9, "version": "14.1.0"}])
    code, out, _ = _run_inventory("version", "primary", str(candidates))
    assert (code, out["primary"], out["version"], out["reason"]) == (0, "next", "14.1.0", "tie-name-order")
    proc = subprocess.run([sys.executable, str(INVENTORY_PY), "version", "primary", "-"],
                          input=b'[{"name": "zod", "import_count": 1, "version": "3.0.0"}]',
                          capture_output=True, timeout=60)
    assert (proc.returncode, json.loads(proc.stdout)["primary"]) == (0, "zod")
    for bad in ("{not json", '{"name": "a"}', '[{"import_count": 1}]'):
        _write(candidates, bad)
        code, out, _ = _run_inventory("version", "primary", str(candidates))
        assert (code, out["code"]) == (1, "BAD_INPUT"), bad
    code, out, _ = _run_inventory("version", "primary", str(tmp_path / "missing.json"))
    assert (code, out["code"]) == (1, "BAD_INPUT")
    for argv in (
        ["version"],
        ["version", "normalize"],
        ["version", "normalize", "1", "2"],
        ["version", "order", "1.0.0"],
        ["version", "compare", "1", "2"],
        ["version", "bump", "--prior", "1.0.0", "--libraries", "a"],
        ["version", "bump", "--prior", "1.0.0", "--prior-libraries", "a", "--libraries"],
        ["version", "bump", "--prior", "1.0.0", "--prior-libraries", "a", "--libraries", "a", "--major", "x"],
    ):
        code, out, err = _run_inventory(*argv)
        assert (code, out["status"], out["code"]) == (1, "error", "USAGE"), argv
        assert "Usage:" in err, argv


# --------------------------------------------------------------------------
# purge check: may drop-skill purge the skill, or one version of it?
# --------------------------------------------------------------------------


def _purge_fixture(tmp_path: Path, links: bool) -> tuple[Path, Path]:
    """A skills folder and a forge folder holding one shape per purge rule."""
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    skills.mkdir()
    forge.mkdir()
    for name in ("clean", "rc", "vnotes", "mixedroot", "forgemixed", "forgevmixed", "forgevfolder",
                 "forgeforeign", "forgeempty", "forgelink", "improvement-queue"):
        _make_version(skills, name, "1.0.0", MARKED)
        _link_active(skills / name / "active", "1.0.0")
    _make_version(skills, "clean", "0.9.0", MARKED)
    # test-skill leaves its gap ledger in each version folder it tested.
    for rel in ("clean/skill-brief.yaml", "clean/1.0.0/provenance-map.json",
                "clean/1.0.0/test-findings-r1.json", "clean/0.9.0/provenance-map.json"):
        _write(forge / rel)
    _make_version(skills, "rc", "1.0.0-rc")  # no marker: a foreign `1.0.0-rc/`
    _write(skills / "vnotes" / "1.0.0" / "NOTES.md")  # a foreign `1.0.0/NOTES.md`
    _write(skills / "mixedroot" / "README.md")  # a foreign entry beside the versions
    for rel in ("forgemixed/skill-brief.yaml", "forgemixed/NOTES.md",
                "forgevmixed/skill-brief.yaml", "forgevmixed/1.0.0/provenance-map.json",
                "forgevmixed/1.0.0/NOTES.md",
                "forgevfolder/skill-brief.yaml", "forgevfolder/1.0.0/data.csv",
                "forgeforeign/config.toml", "improvement-queue/q.json"):
        _write(forge / rel)
    (forge / "forgeempty").mkdir()
    _make_flat(skills, "module", extra=("references/guide.md",))
    _write(skills / "afile")
    if links:
        ext = tmp_path / "ext"
        _make_version(ext, "lk", "1.0.0", MARKED)
        (skills / "lk").symlink_to(ext / "lk", target_is_directory=True)
        _make_version(skills, "linkedver", "1.0.0", MARKED)
        _make_version(ext, "linkedver", "2.0.0", MARKED)
        (skills / "linkedver" / "2.0.0").symlink_to(ext / "linkedver" / "2.0.0", target_is_directory=True)
        _write(ext / "forgelink" / "skill-brief.yaml")
        (forge / "forgelink").symlink_to(ext / "forgelink", target_is_directory=True)
    return skills, forge


# (id, name, version, verdict, reason, offending entries). Each refusal cell of the purge rule, and
# the cells beside it that must stay allowed.
PURGE_CASES = [
    ("clean-whole", "clean", None, "ok", None, []),
    ("clean-version", "clean", "0.9.0", "ok", None, []),
    ("absent", "nothing", None, "ok", None, []),
    ("reserved-batch", "_batch", None, "not-skf-output", "reserved-name", []),
    ("reserved-staging", "clean.skf-tmp", "1.0.0", "not-skf-output", "reserved-name", []),
    ("foreign-whole", "module", None, "not-skf-output", "skill-foreign", []),
    ("foreign-version", "module", "1.0.0", "not-skf-output", "skill-foreign", []),
    ("not-a-folder", "afile", None, "not-skf-output", "skill-foreign", []),
    ("mixed-whole", "mixedroot", None, "not-skf-output", "skill-mixed-whole", ["README.md"]),
    ("mixed-other-version", "mixedroot", "1.0.0", "ok", None, []),
    ("rc-folder-is-not-the-version", "rc", "1.0.0", "ok", None, []),
    ("rc-folder-itself", "rc", "1.0.0-rc", "not-skf-output", "skill-version-not-skf", ["1.0.0-rc/"]),
    ("rc-whole", "rc", None, "not-skf-output", "skill-mixed-whole", ["1.0.0-rc/"]),
    ("entry-inside-the-version", "vnotes", "1.0.0", "not-skf-output", "skill-version-mixed", ["1.0.0/NOTES.md"]),
    ("forge-mixed-whole", "forgemixed", None, "not-skf-output", "forge-mixed-whole", ["NOTES.md"]),
    ("forge-mixed-other-version", "forgemixed", "1.0.0", "ok", None, []),
    ("forge-entry-inside-the-version", "forgevmixed", "1.0.0", "not-skf-output", "forge-version-mixed",
     ["1.0.0/NOTES.md"]),
    ("forge-version-folder-left", "forgevfolder", "1.0.0", "ok", None, []),
    ("forge-foreign-left", "forgeforeign", None, "ok", None, []),
    ("forge-empty-deleted", "forgeempty", None, "ok", None, []),
    ("forge-reserved-left", "improvement-queue", None, "ok", None, []),
    ("link", "lk", None, "not-skf-output", "skill-foreign", []),
    ("linked-version", "linkedver", "2.0.0", "not-skf-output", "skill-version-not-skf", ["2.0.0"]),
    ("forge-link-left", "forgelink", None, "ok", None, []),
]
LINKED_PURGE_CASES = frozenset({"link", "linked-version", "forge-link-left"})


class TestPurgeCheck:
    """purge_check: the purge verdict drop-skill §8b reads, one test per cell."""

    @pytest.mark.parametrize("case_id, name, version, verdict, reason, entries", PURGE_CASES,
                             ids=[c[0] for c in PURGE_CASES])
    def test_purge_verdict(self, tmp_path, case_id, name, version, verdict, reason, entries):
        links = _symlinks_supported(tmp_path)
        if case_id in LINKED_PURGE_CASES and not links:
            pytest.skip("symlinks are not available")
        skills, forge = _purge_fixture(tmp_path, links)
        out = mod.purge_check(skills, name, forge, version)
        assert (out["verdict"], out["reason"], out["offending_entries"]) == (verdict, reason, entries), out
        assert (out["name"], out["version"], out["scope"]) == (name, version, "skill" if version is None else "version")
        assert (out["detail"] is None) == (verdict == "ok")
        if reason == "skill-foreign" and name in ("lk", "afile"):
            assert out["errors"] and out["detail"] == "; ".join(out["errors"])
        if reason == "skill-foreign" and name == "module":
            assert out["detail"] == "has no SKF marker in its `metadata.json`"

    def test_the_folders_a_purge_deletes(self, tmp_path):
        skills, forge = _purge_fixture(tmp_path, links=False)
        whole = mod.purge_check(skills, "clean", forge)
        assert whole["affected_directories"] == [str(skills / "clean"), str(forge / "clean")]
        version = mod.purge_check(skills, "clean", forge, "0.9.0")
        assert version["affected_directories"] == [str(skills / "clean" / "0.9.0"), str(forge / "clean" / "0.9.0")]
        # Nothing on disk, nothing to delete; an empty forge folder is deleted with the skill.
        assert mod.purge_check(skills, "nothing", forge)["affected_directories"] == []
        empty = mod.purge_check(skills, "forgeempty", forge)
        assert empty["affected_directories"] == [str(skills / "forgeempty"), str(forge / "forgeempty")]
        assert empty["forge_left_in_place"] is None
        for path in whole["affected_directories"] + version["affected_directories"]:
            assert not path.endswith(("/", "\\")), "a trailing separator makes a delete follow a link"

    @pytest.mark.parametrize("name, version, left", [
        ("forgeforeign", None, "forgeforeign"),
        ("improvement-queue", None, "improvement-queue"),
        ("forgevfolder", "1.0.0", "forgevfolder/1.0.0"),
    ])
    def test_a_forge_folder_skf_did_not_generate_stays(self, tmp_path, name, version, left):
        skills, forge = _purge_fixture(tmp_path, links=False)
        out = mod.purge_check(skills, name, forge, version)
        assert out["verdict"] == "ok"
        assert Path(out["forge_left_in_place"]).as_posix() == (forge / left).as_posix()
        assert all(not Path(p).as_posix().startswith(forge.as_posix()) for p in out["affected_directories"])

    def test_a_linked_forge_folder_stays_and_names_the_link(self, tmp_path):
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        skills, forge = _purge_fixture(tmp_path, links=True)
        out = mod.purge_check(skills, "forgelink", forge)
        assert out["forge_left_in_place"] == str(forge / "forgelink")
        assert out["affected_directories"] == [str(skills / "forgelink")]
        assert any("link" in e for e in out["forge_errors"])

    def test_a_refused_purge_still_lists_its_folders(self, tmp_path):
        """A deprecate keeps them, so the drop gate shows their size whatever the verdict."""
        skills, forge = _purge_fixture(tmp_path, links=False)
        out = mod.purge_check(skills, "mixedroot", forge)
        assert out["verdict"] == "not-skf-output"
        assert out["affected_directories"] == [str(skills / "mixedroot")]

    def test_one_folder_for_both_settings(self, tmp_path):
        out_dir = tmp_path / "out"
        _same_folder_skill(out_dir)
        result = mod.purge_check(out_dir, "cognee", out_dir)
        assert (result["verdict"], result["same_folder"], result["forge_ownership"]) == ("ok", True, None)
        assert result["affected_directories"] == [str(out_dir / "cognee")]
        _write(out_dir / "cognee" / "0.1.0" / "NOTES.md")
        refused = mod.purge_check(out_dir, "cognee", out_dir, "0.1.0")
        assert (refused["reason"], refused["offending_entries"]) == ("skill-version-mixed", ["0.1.0/NOTES.md"])

    def test_the_skill_folder_refusal_comes_first(self, tmp_path):
        skills, forge = _purge_fixture(tmp_path, links=False)
        _write(skills / "forgemixed" / "README.md")
        out = mod.purge_check(skills, "forgemixed", forge)
        assert out["reason"] == "skill-mixed-whole" and out["folder"] == str(skills / "forgemixed")

    def test_write_check_uses_the_same_version_rule(self, tmp_path):
        skills, forge = _purge_fixture(tmp_path, links=False)
        assert mod._version_entries(["1.0.0-rc/", "1.0.0/x", "1.0.0", "10.0.0/"], "1.0.0") == ["1.0.0/x", "1.0.0"]
        assert mod.write_check(skills, "rc", "1.0.0-rc", forge)["reason"] == "version"
        assert mod.write_check(skills, "rc", "2.0.0", forge)["verdict"] == "ok"


# --------------------------------------------------------------------------
# rename check: may rename-skill move the skill, and its forge folder?
# --------------------------------------------------------------------------


def _rename_fixture(tmp_path: Path, links: bool) -> tuple[Path, Path]:
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    skills.mkdir()
    forge.mkdir()
    for name in ("clean", "vnotes", "forgemixed", "forgeempty", "forgeforeign", "noforge",
                 "forgefile", "forgelink", "improvement-queue"):
        _make_version(skills, name, "1.0.0", MARKED)
        _link_active(skills / name / "active", "1.0.0")
    _write(skills / "vnotes" / "1.0.0" / "NOTES.md")
    _make_flat(skills, "flat", MARKED)
    _make_flat(skills, "module", extra=("references/guide.md",))
    _write(skills / "afile")
    for rel in ("clean/skill-brief.yaml", "clean/1.0.0/provenance-map.json",
                "clean/1.0.0/test-findings-r1.json",
                "forgemixed/skill-brief.yaml", "forgemixed/NOTES.md",
                "forgeforeign/config.toml", "improvement-queue/q.json"):
        _write(forge / rel)
    (forge / "forgeempty").mkdir()
    _write(forge / "forgefile")
    if links:
        ext = tmp_path / "ext"
        _make_version(ext, "lk", "1.0.0", MARKED)
        (skills / "lk").symlink_to(ext / "lk", target_is_directory=True)
        _write(ext / "forgelink" / "skill-brief.yaml")
        (forge / "forgelink").symlink_to(ext / "forgelink", target_is_directory=True)
    return skills, forge


# (id, name, verdict, reason, forge_move, forge left in place under the forge folder)
RENAME_CASES = [
    ("clean", "clean", "ok", None, True, None),
    ("forge-empty-moves", "forgeempty", "ok", None, True, None),
    ("no-forge-folder", "noforge", "ok", None, False, None),
    ("forge-foreign-stays", "forgeforeign", "ok", None, False, "forgeforeign"),
    ("forge-reserved-stays", "improvement-queue", "ok", None, False, "improvement-queue"),
    ("reserved-name", "_batch", "not-skf-output", "reserved-name", False, None),
    ("absent", "nothing", "not-skf-output", "absent", False, None),
    ("foreign", "module", "not-skf-output", "foreign", False, None),
    ("not-a-folder", "afile", "not-skf-output", "foreign", False, None),
    ("mixed", "vnotes", "not-skf-output", "mixed", False, None),
    ("flat-layout", "flat", "flat-layout", "flat-layout", False, None),
    ("forge-mixed", "forgemixed", "not-skf-output", "forge-mixed", False, None),
    ("forge-not-a-folder", "forgefile", "not-skf-output", "forge-not-a-folder", False, None),
    ("link", "lk", "not-skf-output", "foreign", False, None),
    ("forge-link", "forgelink", "not-skf-output", "forge-link", False, None),
]
LINKED_RENAME_CASES = frozenset({"link", "forge-link"})


class TestRenameCheck:
    """rename_check: the rename verdict rename-skill §4a reads, one test per rule."""

    @pytest.mark.parametrize("case_id, name, verdict, reason, forge_move, left", RENAME_CASES,
                             ids=[c[0] for c in RENAME_CASES])
    def test_rename_verdict(self, tmp_path, case_id, name, verdict, reason, forge_move, left):
        links = _symlinks_supported(tmp_path)
        if case_id in LINKED_RENAME_CASES and not links:
            pytest.skip("symlinks are not available")
        skills, forge = _rename_fixture(tmp_path, links)
        out = mod.rename_check(skills, name, forge)
        assert (out["verdict"], out["reason"], out["forge_move"]) == (verdict, reason, forge_move), out
        assert out["forge_left_in_place"] == (str(forge / left) if left else None)
        assert (out["detail"] is None) == (verdict == "ok")
        if reason == "mixed":
            assert out["offending_entries"] == ["1.0.0/NOTES.md"]
        if reason == "forge-mixed":
            assert out["offending_entries"] == ["NOTES.md"] and out["folder"] == str(forge / name)
        if reason in ("forge-link", "forge-not-a-folder"):
            assert out["detail"] == "; ".join(out["forge_errors"]) and out["folder"] == str(forge / name)
        if case_id in ("link", "not-a-folder"):
            assert out["errors"] and out["detail"] == "; ".join(out["errors"])

    @pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
                        reason="needs POSIX permissions and a non-root user")
    def test_a_forge_folder_skf_cannot_list_is_refused(self, tmp_path):
        skills, forge = _rename_fixture(tmp_path, links=False)
        _make_version(skills, "locked", "1.0.0", MARKED)
        _write(forge / "locked" / "skill-brief.yaml")
        (forge / "locked").chmod(0)
        try:
            out = mod.rename_check(skills, "locked", forge)
        finally:
            (forge / "locked").chmod(0o755)
        assert (out["verdict"], out["reason"]) == ("not-skf-output", "forge-unreadable")
        assert "Cannot list" in out["detail"]

    def test_one_folder_for_both_settings(self, tmp_path):
        out_dir = tmp_path / "out"
        _same_folder_skill(out_dir)
        result = mod.rename_check(out_dir, "cognee", out_dir)
        assert (result["verdict"], result["same_folder"], result["forge_move"], result["forge_left_in_place"]) == (
            "ok", True, False, None)
        # Where both settings name one folder, a brief alone is SKF's, but no skill to rename.
        _write(out_dir / "briefonly" / "skill-brief.yaml")
        assert mod.rename_check(out_dir, "briefonly", out_dir)["reason"] == "foreign"


# --------------------------------------------------------------------------
# guarded delete: drop-skill's purge deletes only plain folders inside its roots
# --------------------------------------------------------------------------


class TestGuardedDelete:
    """guarded_delete: containment, link and junction checks, rmtree and the existence check."""

    @pytest.fixture()
    def roots(self, tmp_path):
        skills, forge = tmp_path / "skills", tmp_path / "forge-data"
        _write(skills / "a" / "1.0.0" / "a" / "SKILL.md", b"12345")
        _write(skills / "a" / "0.9.0" / "a" / "SKILL.md", b"123")
        _write(forge / "a" / "1.0.0" / "provenance-map.json", b"1234567")
        return skills, forge

    def test_it_deletes_folders_inside_the_roots(self, roots):
        skills, forge = roots
        out = mod.guarded_delete([str(skills), str(forge)], [str(skills / "a" / "1.0.0"), str(forge / "a")])
        assert out["files_deleted"] == [str(skills / "a" / "1.0.0"), str(forge / "a")]
        assert (out["delete_failures"], out["already_absent"], out["attempted"]) == ([], [], 2)
        assert (out["bytes_freed"], out["purge_status"]) == (12, "success")
        assert not (skills / "a" / "1.0.0").exists() and (skills / "a" / "0.9.0").is_dir()

    def test_a_trailing_separator_is_dropped(self, roots):
        skills, forge = roots
        out = mod.guarded_delete([str(skills)], [str(skills / "a" / "1.0.0") + os.sep])
        assert out["files_deleted"] == [str(skills / "a" / "1.0.0")]

    @pytest.mark.parametrize("where, says", [
        ("outside", "is not inside"),
        ("the-root", "is not inside"),
        ("dot-dot", "has a `..` part"),
        ("empty", "names no folder"),
        ("a-file", "is not a folder"),
    ])
    def test_it_refuses_what_is_not_a_plain_folder_inside_a_root(self, roots, tmp_path, where, says):
        skills, forge = roots
        _write(tmp_path / "elsewhere" / "keep.md")
        path = {"outside": str(tmp_path / "elsewhere"), "the-root": str(skills),
                "dot-dot": str(skills / "a" / ".." / "a"), "empty": "",
                "a-file": str(skills / "a" / "1.0.0" / "a" / "SKILL.md")}[where]
        out = mod.guarded_delete([str(skills), str(forge)], [path])
        [failure] = out["delete_failures"]
        assert says in failure["error"], failure
        assert (out["files_deleted"], out["purge_status"]) == ([], "failed")
        assert (tmp_path / "elsewhere" / "keep.md").is_file() and (skills / "a" / "1.0.0").is_dir()

    def test_nothing_there_is_not_a_failure(self, roots):
        skills, _forge = roots
        out = mod.guarded_delete([str(skills)], [str(skills / "gone")])
        assert (out["already_absent"], out["attempted"], out["purge_status"]) == ([str(skills / "gone")], 0, "success")

    def test_no_path_deletes_nothing_and_succeeds(self, roots):
        """A drop of a manifest entry whose folders are gone: the purge check lists no folder."""
        skills, forge = roots
        out = mod.guarded_delete([str(skills), str(forge)], [])
        assert (out["files_deleted"], out["delete_failures"], out["attempted"]) == ([], [], 0)
        assert (out["bytes_freed"], out["purge_status"]) == (0, "success")
        assert (skills / "a" / "1.0.0").is_dir() and (forge / "a" / "1.0.0").is_dir()

    def test_one_failure_among_deletes_is_partial(self, roots, tmp_path):
        skills, forge = roots
        out = mod.guarded_delete([str(skills)], [str(skills / "a" / "0.9.0"), str(tmp_path / "elsewhere")])
        assert (out["attempted"], out["purge_status"]) == (2, "partial")
        assert out["files_deleted"] == [str(skills / "a" / "0.9.0")]

    def test_it_never_deletes_through_a_link(self, roots, tmp_path):
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        skills, forge = roots
        outside = tmp_path / "outside"
        _write(outside / "v" / "keep.md")
        (skills / "linked").symlink_to(outside, target_is_directory=True)
        (skills / "a" / "2.0.0").symlink_to(outside / "v", target_is_directory=True)
        out = mod.guarded_delete([str(skills)], [str(skills / "linked" / "v"), str(skills / "a" / "2.0.0"),
                                                 str(skills / "a" / "2.0.0") + os.sep])
        errors = [f["error"] for f in out["delete_failures"]]
        assert errors[0] == f"{skills / 'linked'} is a link; SKF never deletes through a link"
        assert errors[1:] == ["a link; SKF never deletes through a link"] * 2
        assert (out["files_deleted"], out["purge_status"]) == ([], "failed")
        assert (outside / "v" / "keep.md").is_file()

    def test_a_link_inside_a_deleted_folder_is_removed_not_followed(self, roots, tmp_path):
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        skills, forge = roots
        outside = tmp_path / "outside"
        _write(outside / "keep.md")
        _link_active(skills / "a" / "active", "1.0.0")
        (skills / "a" / "1.0.0" / "a" / "ref").symlink_to(outside, target_is_directory=True)
        out = mod.guarded_delete([str(skills)], [str(skills / "a")])
        assert out["files_deleted"] == [str(skills / "a")] and not (skills / "a").exists()
        assert (outside / "keep.md").is_file()

    def test_a_read_only_file_is_deleted(self, roots):
        skills, _forge = roots
        target = skills / "a" / "0.9.0" / "a" / "SKILL.md"
        target.chmod(0o444)
        out = mod.guarded_delete([str(skills)], [str(skills / "a" / "0.9.0")])
        assert out["purge_status"] == "success" and not target.exists()

    def test_the_closest_root_decides_which_folders_are_checked(self, tmp_path):
        """A forge folder inside the skills folder: the link check starts below the forge root."""
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        skills = tmp_path / "skills"
        real_forge = tmp_path / "real-forge"
        _write(real_forge / "a" / "1.0.0" / "provenance-map.json")
        skills.mkdir()
        (skills / "forge").symlink_to(real_forge, target_is_directory=True)  # the user's configuration
        out = mod.guarded_delete([str(skills), str(skills / "forge")], [str(skills / "forge" / "a" / "1.0.0")])
        assert out["purge_status"] == "success" and not (real_forge / "a" / "1.0.0").exists()


def test_cli_purge_rename_and_guarded_delete(tmp_path):
    skills, forge = _purge_fixture(tmp_path, links=False)
    code, out, _ = _run_inventory(str(skills), "--skill", "rc", "--purge-check", "--purge-version", "1.0.0-rc",
                                  "--forge-data-folder", str(forge))
    assert (code, out["status"], out["same_folder"]) == (0, "ok", False)
    assert (out["purge_check"]["verdict"], out["purge_check"]["reason"]) == ("not-skf-output", "skill-version-not-skf")
    code, out, _ = _run_inventory(str(skills), "--skill", "clean", "--purge-check", "--forge-data-folder", str(forge))
    assert (code, out["purge_check"]["verdict"], out["purge_check"]["scope"]) == (0, "ok", "skill")
    code, out, _ = _run_inventory(str(skills), "--skill", "clean", "--rename-check", "--forge-data-folder", str(forge))
    assert (code, out["rename_check"]["verdict"], out["rename_check"]["forge_move"]) == (0, "ok", True)
    assert "purge_check" not in out and "write_check" not in out
    for argv in (
        [str(skills), "--skill", "clean", "--purge-check"],
        [str(skills), "--skill", "clean", "--rename-check"],
        [str(skills), "--skill", "clean", "--purge-check", "--forge-data-folder"],
        [str(skills), "--skill", "clean", "--purge-version", "1.0.0", "--forge-data-folder", str(forge)],
        [str(skills), "--skill", "clean", "--rename-check", "--purge-version", "1.0.0", "--forge-data-folder", str(forge)],
        [str(skills), "--skill", "clean", "--purge-check", "--rename-check", "--forge-data-folder", str(forge)],
        [str(skills), "--skill", "clean", "--purge-check", "--write-check", "--forge-data-folder", str(forge)],
        [str(skills), "--purge-check", "--forge-data-folder", str(forge)],
        [str(skills), "--skill", "a/b", "--rename-check", "--forge-data-folder", str(forge)],
        [str(skills), "--skill", "clean", "--purge-check", "--purge-version", "..", "--forge-data-folder", str(forge)],
        ["--skill", "clean", "--rename-check", "--forge-data-folder", str(forge)],
        ["guarded-delete", str(skills / "clean")],
        ["guarded-delete"],
        ["guarded-delete", "--root"],
        ["guarded-delete", "--root", str(skills), "--force", str(skills / "clean")],
    ):
        code, out, err = _run_inventory(*argv)
        assert (code, out["status"], out["code"]) == (1, "error", "USAGE"), argv
        assert "Usage:" in err, argv
    code, out, _ = _run_inventory("guarded-delete", "--root", str(skills), "--root", str(forge),
                                  str(skills / "clean" / "0.9.0"), str(tmp_path / "elsewhere"))
    assert (code, out["status"], out["command"], out["purge_status"]) == (0, "ok", "guarded-delete", "partial")
    assert out["files_deleted"] == [str(skills / "clean" / "0.9.0")]
    code, out, _ = _run_inventory("guarded-delete", "--root", str(skills), str(tmp_path))
    assert (code, out["purge_status"]) == (0, "failed")
    # drop-skill runs it with every path of an empty `affected_directories`: nothing to delete succeeds.
    code, out, _ = _run_inventory("guarded-delete", "--root", str(skills), "--root", str(forge))
    assert (code, out["status"], out["attempted"], out["files_deleted"]) == (0, "ok", 0, [])
    assert (out["bytes_freed"], out["purge_status"]) == (0, "success")
    _write(tmp_path / "afile")
    code, out, _ = _run_inventory(str(tmp_path / "afile"), "--skill", "a", "--purge-check",
                                  "--forge-data-folder", str(forge))
    assert (code, out["code"]) == (1, "DIR_NOT_FOUND")


# ---------------------------------------------------------------------------
# derive-name: the one skill-name rule (#582)
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
ANALYZE_REFS = REPO / "src" / "skf-analyze-source" / "references"


def test_cli_derive_name(tmp_path):
    code, out, _ = _run_inventory("derive-name", "--target", "https://github.com/vercel/next.js")
    assert (code, out) == (0, {"status": "ok", "command": "derive-name", "name": "next-js", "basis": "target",
                               "kind": "remote", "clone_url": "https://github.com/vercel/next.js"})
    code, out, _ = _run_inventory("derive-name", "--target", "https://github.com/vercel/next.js",
                                  "--manifest-name", "next")
    assert (code, out["name"], out["basis"]) == (0, "next", "manifest")
    code, out, _ = _run_inventory("derive-name", "--target", "libs/x", "--manifest-name", "")
    assert (code, out["name"], out["basis"]) == (0, "x", "target")
    code, out, _ = _run_inventory("derive-name", "--manifest-name", "@trpc/server")
    assert (code, out["name"], out["kind"], out["clone_url"]) == (0, "trpc-server", None, None)
    names = tmp_path / "names.json"
    names.write_bytes(json.dumps([
        {"target": "packages/server", "manifest_name": "@trpc/server"},
        {"target": "libs/util"},
        {"target": "https://docs.example.com/a", "manifest_name": None},
    ]).encode("utf-8"))
    code, out, _ = _run_inventory("derive-name", "--from", str(names))
    assert (code, out["status"], out["command"]) == (0, "ok", "derive-name")
    assert [(n["name"], n["basis"]) for n in out["names"]] == [
        ("trpc-server", "manifest"), ("util", "target"), ("docs-example-com", "docs-host")]
    assert out["names"][1] == {"target": "libs/util", "manifest_name": None, "name": "util", "basis": "target"}
    assert (out["unnamed"], out["duplicates"]) == ([], [])


@pytest.mark.parametrize(
    ("target", "kind", "url"),
    [pytest.param("/srv/code/mono", "local", None, id="absolute"),
     pytest.param("./mono", "local", None, id="dot-relative"),
     pytest.param("../mono", "local", None, id="parent-relative"),
     pytest.param("~/code/mono", "local", None, id="home"),
     pytest.param(".", "local", None, id="dot"),
     pytest.param("C:\\code\\mono", "local", None, id="windows-drive"),
     pytest.param("https://docs.example.com/guide", "docs", None, id="docs-url"),
     pytest.param("https://github.com/acme/mono", "remote", "https://github.com/acme/mono", id="https"),
     pytest.param("git@github.com:acme/mono.git", "remote", "git@github.com:acme/mono.git", id="ssh"),
     pytest.param("ssh://git@host.example/acme/mono", "remote", "ssh://git@host.example/acme/mono", id="ssh-url"),
     pytest.param("github.com/acme/mono", "remote", "https://github.com/acme/mono", id="host-path"),
     pytest.param("gitlab.com/group/repo/", "remote", "https://gitlab.com/group/repo", id="gitlab-host-path"),
     pytest.param("acme/mono", "remote", "https://github.com/acme/mono", id="shorthand")],
)
def test_derive_name_classifies_the_target_and_gives_the_clone_url(target, kind, url):
    """step 5b determinism-4: one {kind, clone_url} per target, which the [auto] path and
    scan-root.md both read, so a host path or a shorthand is never cloned as a local folder."""
    assert (mod.target_kind(target), mod.clone_url(target)) == (kind, url)
    code, out, _ = _run_inventory("derive-name", "--target", target)
    assert (code, out["kind"], out["clone_url"]) == (0, kind, url)


def test_derive_name_reads_an_existing_folder_as_local(tmp_path, monkeypatch):
    """A relative path with no ./ prefix is local when it names a folder, else a shorthand."""
    (tmp_path / "acme" / "mono").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert (mod.target_kind("acme/mono"), mod.clone_url("acme/mono")) == ("local", None)
    assert (mod.target_kind("acme/other"), mod.clone_url("acme/other")) == (
        "remote", "https://github.com/acme/other")
    assert (mod.target_kind(""), mod.clone_url("")) == (None, None)


def test_cli_derive_name_batch_private_and_members(tmp_path):
    """identify-units passes the disqualify record's manifest; a merged unit its members."""
    names = tmp_path / "names.json"
    names.write_bytes(json.dumps([
        {"target": "apps/web", "manifest_name": "@acme/web", "private": True},
        {"target": "packages/core", "manifest_name": "@acme/core", "private": False},
        {"target": "/src/aws-sdk-js-v3", "manifest_name": "aws-sdk-js-v3", "private": True,
         "members": ["@aws-sdk/client-s3", "@aws-sdk/core"]},
        {"target": "libs/x", "manifest_name": None, "private": None, "members": None},
    ]).encode("utf-8"))
    code, out, _ = _run_inventory("derive-name", "--from", str(names))
    assert code == 0
    assert [(n["name"], n["basis"]) for n in out["names"]] == [
        ("web", "target"), ("acme-core", "manifest"), ("aws-sdk", "members"), ("x", "target")]


def test_cli_derive_name_tells_clashing_names_apart(tmp_path):
    """Two folders named api would make skf-count-imports.py refuse the units."""
    names = tmp_path / "names.json"
    names.write_bytes(json.dumps([
        {"target": "src/server/api"},
        {"target": "src/client/api"},
        {"target": "a/core", "manifest_name": "com.a:core"},
        {"target": "b/core", "manifest_name": "com.b:core"},
        {"target": "web"},
        {"target": "same"},
        {"target": "same"},
        {"target": "///"},
    ]).encode("utf-8"))
    code, out, _ = _run_inventory("derive-name", "--from", str(names))
    assert (code, out["status"]) == (0, "ok")
    assert [n["name"] for n in out["names"]] == [
        "server-api", "client-api", "a-core", "b-core", "web", "same", "same", None]
    assert [n.get("clash") for n in out["names"][:5]] == ["api", "api", "core", "core", None]
    assert (out["unnamed"], out["duplicates"]) == ([7], [[5, 6]])


def test_cli_derive_name_from_stdin():
    proc = subprocess.run([sys.executable, str(INVENTORY_PY), "derive-name", "--from", "-"],
                          input=b'[{"target": "a/b"}, {"target": "", "manifest_name": "PyYAML"}]',
                          capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    names = json.loads(proc.stdout.decode("utf-8"))["names"]
    assert [n["name"] for n in names] == ["b", "pyyaml"]


def test_cli_derive_name_errors(tmp_path):
    code, out, _ = _run_inventory("derive-name", "--target", "")
    assert (code, out["status"], out["code"]) == (1, "error", "NO_NAME")
    bad = tmp_path / "bad.json"
    for content in (
        b'{"target": "x"}',
        b"[1]",
        b'[{"target": 3}]',
        b"not json",
        b'[{"target": "x", "private": "yes"}]',
        b'[{"target": "x", "members": "@a/b"}]',
        b'[{"target": "x", "members": [1]}]',
    ):
        bad.write_bytes(content)
        code, out, _ = _run_inventory("derive-name", "--from", str(bad))
        assert (code, out["code"]) == (1, "BAD_INPUT"), content
    # A batch names what it can: a nameless entry does not fail the others.
    bad.write_bytes(b'[{"target": "ok"}, {"target": ""}]')
    code, out, _ = _run_inventory("derive-name", "--from", str(bad))
    assert (code, [n["name"] for n in out["names"]], out["unnamed"]) == (0, ["ok", None], [1])
    code, out, _ = _run_inventory("derive-name", "--from", str(tmp_path / "missing.json"))
    assert (code, out["code"]) == (1, "BAD_INPUT")
    for argv in (
        ["derive-name"],
        ["derive-name", "--target"],
        ["derive-name", "--target", "x", "--bogus", "y"],
        ["derive-name", "--from", str(bad), "--target", "x"],
        ["derive-name", "--manifest-name", "--target", "x"],
        ["derive-name", "--target", "x", "--skills-folder"],
    ):
        code, out, err = _run_inventory(*argv)
        assert (code, out["status"], out["code"]) == (1, "error", "USAGE"), argv
        assert "Usage:" in err, argv


def test_cli_derive_name_reports_the_existing_skill(tmp_path):
    """#582: the brief takes the manifest's name, so that is the name to look up."""
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "next", "15.0.0", source_repo="https://nextjs.org/docs")
    code, out, _ = _run_inventory(str(skills), "--match-target", "https://github.com/vercel/next.js")
    assert (code, out["match_name"], out["matches"]) == (0, "next-js", [])
    code, out, _ = _run_inventory("derive-name", "--target", "https://github.com/vercel/next.js",
                                  "--manifest-name", "next", "--skills-folder", str(skills))
    assert (code, out["name"]) == (0, "next")
    assert out["existing"] == {
        "name": "next", "active_version": "15.0.0", "source_repo": "https://nextjs.org/docs",
        "active_path": out["existing"]["active_path"], "match_reason": "name", "skf_skill": True,
    }
    assert out["existing"]["active_path"]
    names = tmp_path / "names.json"
    names.write_bytes(json.dumps([
        {"target": "packages/next", "manifest_name": "next"},
        {"target": "packages/font", "manifest_name": "@next/font"},
    ]).encode("utf-8"))
    code, out, _ = _run_inventory("derive-name", "--from", str(names), "--skills-folder", str(skills))
    assert code == 0
    assert [(n["name"], (n["existing"] or {}).get("name")) for n in out["names"]] == [
        ("next", "next"), ("next-font", None)]
    # Without --skills-folder there is no `existing` key; a missing folder holds no skill.
    code, out, _ = _run_inventory("derive-name", "--target", "x")
    assert "existing" not in out
    code, out, _ = _run_inventory("derive-name", "--target", "x", "--skills-folder", str(tmp_path / "none"))
    assert (code, out["existing"]) == (0, None)


_PLACEHOLDER = re.compile(r"\{[^{}\n]*\}")
_DERIVE_CALL = re.compile(r"\{skillInventoryHelper\} derive-name\b([^`\n]*)")


def _derive_name_calls() -> list[tuple[str, str]]:
    calls = []
    for md in sorted((REPO / "src").rglob("*.md")):
        for m in _DERIVE_CALL.finditer(md.read_text(encoding="utf-8")):
            calls.append((md.relative_to(REPO).as_posix(), m.group(1)))
    return calls


def _call_words(rest: str) -> list[str]:
    lex = shlex.shlex(_PLACEHOLDER.sub("X", rest), posix=True, punctuation_chars="|&;<>()")
    lex.whitespace_split = True
    words = []
    for word in lex:
        if set(word) <= set("|&;<>()"):
            break
        words.append(word)
    return words


def test_prose_derive_name_calls_fit_the_cli(capsys):
    """A derive-name call in a step file must parse (the helper reads argv by hand)."""
    calls = _derive_name_calls()
    assert {rel for rel, _ in calls} >= {
        "src/skf-analyze-source/references/step-auto-scope.md",
        "src/skf-analyze-source/references/scan-root.md",
        "src/skf-analyze-source/references/auto-docs-only.md",
        "src/skf-analyze-source/references/identify-units.md",
        "src/skf-analyze-source/references/map-and-detect.md",
    }
    for rel, rest in calls:
        mod._main_derive_name(_call_words(rest))
        out = json.loads(capsys.readouterr().out)
        assert out.get("code") != "USAGE", (rel, rest, out)


def test_analyze_source_names_through_the_helper():
    auto = (ANALYZE_REFS / "step-auto-scope.md").read_text(encoding="utf-8")
    docs = (ANALYZE_REFS / "auto-docs-only.md").read_text(encoding="utf-8")
    assert "Use the manifest `name` field if available" not in auto
    assert "{project_name}-{package_name}" not in auto
    assert "replace `.` with `-`" not in docs, "the host rule lives in derive_name"
    # The name the brief gets is the name the coexistence check looks up.
    assert '--skills-folder "{skills_output_folder}"' in auto
    # One classification of the target, in the script: section 0 routes on its kind.
    assert "| `docs` | Documentation URL |" in auto and "`basis` is `docs-host`" not in auto
    for row in ("| GitHub repo |", "| Git hosting |", "Any other `https://` or `http://` URL"):
        assert row not in auto, row


def test_one_name_rule_on_both_paths():
    """identify-units, map-and-detect and auto section 6 pass the same inputs."""
    auto = (ANALYZE_REFS / "step-auto-scope.md").read_text(encoding="utf-8")
    identify = (ANALYZE_REFS / "identify-units.md").read_text(encoding="utf-8")
    mapping = (ANALYZE_REFS / "map-and-detect.md").read_text(encoding="utf-8")
    heuristics = (ANALYZE_REFS / "unit-detection-heuristics.md").read_text(encoding="utf-8")
    assert "## Unit Names" in heuristics
    for text in (auto, identify, mapping):
        assert "Unit Names" in text
    assert '"private": <manifest.private>' in identify
    assert '"private": <private>, "members": [<member names>]' in auto
    assert '"members": ["<constituent manifest name>", ...]' in mapping
    for text in (auto, identify, mapping):
        assert "`unnamed`" in text and "`duplicates`" in text
    # Section 6 takes the coexistence decision itself: [A] does not restart at section 1.
    assert "sets `{coexistence_suffix}` to `-wiki` and continues here" in auto


# ---------------------------------------------------------------------------
# test-skill's in-progress report (#587) and the near names test-skill shows
# ---------------------------------------------------------------------------

IN_PROGRESS_REPORT = ".skf-test-report-demo-20260601T120000Z-ab12.md"


@pytest.mark.parametrize("with_anchor", [True, False], ids=["marked", "halted-before-anchors"])
def test_an_in_progress_test_report_leaves_the_forge_version_skfs(tmp_path, with_anchor):
    """A run that halts leaves its hidden report beside the lock: never a foreign entry,
    so drop and rename can still purge or move the version."""
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    make_skill(skills, "demo")
    _write(forge / "demo" / "skill-brief.yaml")
    version = forge / "demo" / "1.0.0"
    _write(version / ".test-skill.lock")
    _write(version / IN_PROGRESS_REPORT, "---\ntestResult: ''\n---\n")
    if with_anchor:
        _write(version / "provenance-map.json", "{}")
    group = mod.classify_forge_group(forge / "demo", "demo")
    assert group["foreign_entries"] == []
    assert group["ownership"] == "skf"
    for version_arg in (None, "1.0.0"):
        purge = mod.purge_check(skills, "demo", forge, version_arg)
        assert purge["verdict"] == "ok", purge
        assert purge["forge_foreign_entries"] == []
    assert mod.rename_check(skills, "demo", forge)["verdict"] == "ok"


def test_an_in_progress_test_report_in_a_shared_folder_is_skfs(tmp_path):
    """With one folder for skills and forge data, the report sits beside the package."""
    skills = tmp_path / "skills"
    make_skill(skills, "demo", with_provenance=True)
    version = skills / "demo" / "1.0.0"
    _write(version / "provenance-map.json", "{}")
    _write(version / ".test-skill.lock")
    _write(version / IN_PROGRESS_REPORT)
    result = scan_inventory(str(skills), forge_data_folder=str(skills))
    [entry] = result["skills"]
    assert result["same_folder"] is True
    assert entry["ownership"] == "skf"
    assert entry["foreign_entries"] == []
    assert result["not_skf_output"] == []


def test_near_lists_the_testable_skills_closest_first(tmp_path):
    skills = tmp_path / "skills"
    for name in ("zod", "cocoindex-code", "cocoindx"):
        make_skill(skills, name)
    make_skill(skills, "cocoindex-notes", with_metadata=False)  # no SKF marker: not testable
    code, out, err = _run_inventory(str(skills), "--near", "cocoindex")
    assert code == 0, err
    assert out["near"] == [
        {"name": "cocoindx", "active_version": "1.0.0", "close": True},
        {"name": "cocoindex-code", "active_version": "1.0.0", "close": True},
        {"name": "zod", "active_version": "1.0.0", "close": False},
    ]
    code, out, _ = _run_inventory(str(skills))
    assert code == 0 and "near" not in out


def test_near_needs_a_name(tmp_path):
    skills = tmp_path / "skills"
    skills.mkdir()
    code, out, _ = _run_inventory(str(skills), "--near")
    assert code == 1 and out["code"] == "USAGE"


def test_test_skill_reads_a_failed_near_list_as_no_list(tmp_path):
    """A skills folder that does not exist exits 1 with no `near[]`; test-skill's init.md then
    shows only the create-skill line, at the skill-name prompt and at the not-found branch."""
    code, out, _ = _run_inventory(str(tmp_path / "missing"), "--near", "")
    assert code == 1 and out["code"] == "DIR_NOT_FOUND" and "near" not in out
    init = re.sub(r"\s+", " ", (REPO / "src" / "skf-test-skill" / "references" / "init.md").read_text(encoding="utf-8"))
    prompt = init[init.index("### 1. Receive the Skill Name"):init.index("### 1b.")]
    assert "when the helper exits non-zero, or `near[]` is absent or empty, show the create-skill line below instead" in prompt
    not_found = init[init.index("**Not found** (step 4)"):init.index("**If SKILL.md missing**")]
    assert "When the helper exits non-zero, or `near[]` is absent or empty" in not_found
    assert "show no list, only that create-skill line" in not_found
