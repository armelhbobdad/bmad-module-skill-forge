#!/usr/bin/env python3
"""Tests for skf-enumerate-stack-skills.py.

Covers the exports resolution cascade documented in
`src/skf-create-stack-skill/references/parallel-extract.md` §0:

  1. metadata.json — exports[] populated, hash captured, confidence=T1
  2. references/   — heuristic `## API` / `## Exports` parse, hash=null, T2
  3. SKILL.md      — heuristic `## Exports` / `## API Surface` parse, T2
  4. None          — empty exports, T1-low, warning emitted

Plus:
  - Cycle detection on `composes: [...]` (direct + transitive)
  - Ownership: only packages whose metadata.json carries an SKF marker are
    enumerated; other skill folders and top-level links go to
    `not_skf_output`, and unreadable metadata counts as a warning
  - evidence_tier: the dominant confidence_distribution bin, ties to the
    weaker tier, beside the exports-source `confidence`
  - The metadata.json fields each entry carries (skill_type, language,
    confidence_tier on its skill_type's scale, exports_documented,
    metadata_schema_version, source_repo and source_root with basenames)
  - --expect-hashes: changed, missing and new skills against a recorded run
  - candidates: explicit, manifest and active-link candidates, the
    exclusion reasons, stale manifest keys and manifest parse errors
  - CLI subprocess invocation produces valid JSON
  - Empty skills root → empty inventory, exit 0
  - Bad skills root → exit 1
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-enumerate-stack-skills.py"

spec = importlib.util.spec_from_file_location("skf_enumerate_stack_skills", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _make_skill(
    root: Path,
    name: str,
    *,
    skill_md: str | None = "# placeholder\n",
    metadata: dict | None = None,
    references: dict[str, str] | None = None,
    marked: bool = True,
) -> Path:
    """Create a skill package under `root` with optional artifacts.

    `metadata` is dumped as metadata.json (None → no file); with `marked`
    (the default) it carries the SKF marker `generated_by: create-skill`, so
    the package counts as one SKF generated. `references` maps file name →
    markdown content (None → no dir).
    """
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if skill_md is not None:
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if metadata is not None and marked:
        metadata = {**metadata, "generated_by": metadata.get("generated_by", "create-skill")}
    if metadata is not None:
        (skill_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
    if references is not None:
        refs = skill_dir / "references"
        refs.mkdir(exist_ok=True)
        for fname, body in references.items():
            (refs / fname).write_text(body, encoding="utf-8")
    return skill_dir


def _make_nested_skill(
    root: Path,
    name: str,
    version: str,
    *,
    skill_md: str | None = "# placeholder\n",
    metadata: dict | None = None,
    references: dict[str, str] | None = None,
    active: bool = True,
    marked: bool = True,
) -> Path:
    """Create a version-nested skill package and return the inner package dir.

    Layout (knowledge/version-paths.md):
        {root}/{name}/{version}/{name}/SKILL.md
        {root}/{name}/active -> {version}      (when `active` is True)
    """
    pkg = _make_skill(
        root / name / version,
        name,
        skill_md=skill_md,
        metadata=metadata,
        references=references,
        marked=marked,
    )
    if active:
        import pytest

        link = root / name / "active"
        try:
            os.symlink(version, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
    return pkg


def _expected_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _symlink(target: Path, link: Path) -> None:
    """Create a directory link at `link`, skipping where links are unsupported."""
    import pytest

    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")


def _write_bytes(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# --------------------------------------------------------------------------
# resolve_skill — metadata.json path
# --------------------------------------------------------------------------


class TestResolveFromMetadata:
    def test_metadata_with_exports_list_of_strings(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-a",
            metadata={"name": "skill-a", "exports": ["fn_one", "Klass", "CONST"]},
        )
        meta_bytes = (skill_dir / "metadata.json").read_bytes()
        entry, composes, warnings = mod.resolve_skill(skill_dir, "skill-a")
        assert entry["exports"] == ["fn_one", "Klass", "CONST"]
        assert entry["exports_source"] == "metadata"
        assert entry["confidence"] == "T1"
        assert entry["metadata_hash"] == _expected_hash(meta_bytes)
        assert composes == []
        assert warnings == []

    def test_metadata_with_exports_list_of_dicts(self, tmp_path: Path) -> None:
        # render-quick-metadata.py emits {name, type, source_file} dicts —
        # the enumerator must accept that shape too.
        skill_dir = _make_skill(
            tmp_path,
            "skill-a",
            metadata={
                "name": "skill-a",
                "exports": [
                    {"name": "fn_one", "type": "def"},
                    {"name": "Klass", "type": "class"},
                ],
            },
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-a")
        assert entry["exports"] == ["fn_one", "Klass"]
        assert entry["exports_source"] == "metadata"

    def test_metadata_with_empty_exports(self, tmp_path: Path) -> None:
        # Empty exports[] is still authoritative — don't fall through.
        skill_dir = _make_skill(
            tmp_path,
            "skill-empty",
            metadata={"name": "skill-empty", "exports": []},
            references={"a.md": "## Exports\n- ghost\n"},
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-empty")
        assert entry["exports"] == []
        assert entry["exports_source"] == "metadata"
        assert entry["metadata_hash"] is not None

    def test_metadata_without_exports_field_falls_through(self, tmp_path: Path) -> None:
        # metadata.json exists, valid JSON, but no exports[] — fall to references.
        skill_dir = _make_skill(
            tmp_path,
            "skill-x",
            metadata={"name": "skill-x", "description": "no exports field"},
            references={"a.md": "## Exports\n- fallback_fn\n"},
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-x")
        assert entry["exports"] == ["fallback_fn"]
        assert entry["exports_source"] == "references"
        # Hash from metadata.json is preserved even though exports came
        # from references — callers may want it for provenance.
        assert entry["metadata_hash"] is not None

    def test_malformed_metadata_falls_through_with_warning(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-bad",
            metadata=None,  # write a custom bad blob below
            references={"a.md": "## Exports\n- recovered\n"},
        )
        (skill_dir / "metadata.json").write_text("{not json", encoding="utf-8")
        entry, _, warnings = mod.resolve_skill(skill_dir, "skill-bad")
        assert entry["exports"] == ["recovered"]
        assert entry["exports_source"] == "references"
        # The hash is still recorded — malformed JSON is still hashable bytes.
        assert entry["metadata_hash"] is not None
        assert any("not valid JSON" in w for w in warnings)

    def test_metadata_with_composes_records_graph_input(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-stack",
            metadata={
                "name": "skill-stack",
                "exports": ["combined"],
                "composes": ["skill-a", "skill-b"],
            },
        )
        _, composes, _ = mod.resolve_skill(skill_dir, "skill-stack")
        assert composes == ["skill-a", "skill-b"]


# --------------------------------------------------------------------------
# resolve_skill — references/ path
# --------------------------------------------------------------------------


class TestResolveFromReferences:
    def test_references_api_section(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-r",
            metadata=None,
            references={
                "exports.md": (
                    "# Exports overview\n\n"
                    "Some intro prose.\n\n"
                    "## API\n\n"
                    "- compute_score\n"
                    "- `serialize`\n"
                    "- normalize_path\n\n"
                    "## Other section\n"
                    "- ignored_after_boundary\n"
                ),
            },
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-r")
        assert entry["exports"] == ["compute_score", "serialize", "normalize_path"]
        assert entry["exports_source"] == "references"
        assert entry["confidence"] == "T2"
        assert entry["metadata_hash"] is None

    def test_references_exports_section(self, tmp_path: Path) -> None:
        # `## Exports` heading should also match.
        skill_dir = _make_skill(
            tmp_path,
            "skill-r2",
            metadata=None,
            references={"api.md": "## Exports\n- foo\n- bar\n"},
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-r2")
        assert entry["exports"] == ["foo", "bar"]
        assert entry["exports_source"] == "references"

    def test_references_dedup_across_files(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-r3",
            metadata=None,
            references={
                "a.md": "## API\n- shared_name\n- only_in_a\n",
                "b.md": "## Exports\n- shared_name\n- only_in_b\n",
            },
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-r3")
        # Files visited in sorted order (a then b); shared_name not duplicated.
        assert entry["exports"] == ["shared_name", "only_in_a", "only_in_b"]

    def test_references_dir_missing_falls_through(self, tmp_path: Path) -> None:
        # No metadata, no references/, but a SKILL.md with Exports section.
        skill_dir = _make_skill(
            tmp_path,
            "skill-s",
            skill_md="# header\n\n## Exports\n- from_prose\n",
            metadata=None,
            references=None,
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-s")
        assert entry["exports"] == ["from_prose"]
        assert entry["exports_source"] == "skill-md"


# --------------------------------------------------------------------------
# resolve_skill — SKILL.md path
# --------------------------------------------------------------------------


class TestResolveFromSkillMd:
    def test_skill_md_exports_section(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-m",
            skill_md=(
                "# Skill M\n\n"
                "## Exports\n\n"
                "- handle_request\n"
                "- `cleanup`\n\n"
                "## Conventions\n"
                "- ignored\n"
            ),
            metadata=None,
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-m")
        assert entry["exports"] == ["handle_request", "cleanup"]
        assert entry["exports_source"] == "skill-md"
        assert entry["confidence"] == "T2"
        assert entry["metadata_hash"] is None

    def test_skill_md_api_surface_section(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-m2",
            skill_md="# x\n\n## API Surface\n- surfaced_fn\n",
            metadata=None,
        )
        entry, _, _ = mod.resolve_skill(skill_dir, "skill-m2")
        assert entry["exports"] == ["surfaced_fn"]
        assert entry["exports_source"] == "skill-md"

    def test_skill_md_with_nothing_yields_unknown(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(
            tmp_path,
            "skill-nothing",
            skill_md="# title only\n\nno exports here\n",
            metadata=None,
        )
        entry, _, warnings = mod.resolve_skill(skill_dir, "skill-nothing")
        assert entry["exports"] == []
        assert entry["exports_source"] == "unknown"
        assert entry["confidence"] == "T1-low"
        assert entry["metadata_hash"] is None
        assert any("no exports found" in w for w in warnings)


# --------------------------------------------------------------------------
# Section parsing edge cases
# --------------------------------------------------------------------------


class TestParseListSection:
    def test_heading_not_present(self) -> None:
        assert mod._parse_list_section("# header\n- a\n", ("## Exports",)) == []

    def test_only_first_matching_section_used_by_h2_boundary(self) -> None:
        # First `## Exports` matches; the second `##` heading ends the section,
        # so items after it are not collected by THAT section.
        content = (
            "## Exports\n"
            "- one\n"
            "## Other\n"
            "- not_an_export\n"
            "## Exports\n"
            "- two\n"
        )
        # Implementation takes the FIRST matching section only.
        assert mod._parse_list_section(content, ("## Exports",)) == ["one"]

    def test_bullet_variants(self) -> None:
        content = "## Exports\n- a\n* b\n+ c\n"
        assert mod._parse_list_section(content, ("## Exports",)) == ["a", "b", "c"]

    def test_non_list_lines_ignored(self) -> None:
        content = (
            "## Exports\n"
            "\n"
            "Some prose intro.\n"
            "\n"
            "- real_one\n"
            "  - nested_indented\n"
            "- real_two\n"
        )
        names = mod._parse_list_section(content, ("## Exports",))
        # Nested bullet still parses (starts with `-`); that's acceptable.
        assert "real_one" in names
        assert "real_two" in names
        assert "nested_indented" in names


# --------------------------------------------------------------------------
# Cycle detection
# --------------------------------------------------------------------------


class TestDetectCycles:
    def test_no_cycle_empty_graph(self) -> None:
        assert mod.detect_cycles({}) == []

    def test_no_cycle_linear(self) -> None:
        assert mod.detect_cycles({"a": ["b"], "b": ["c"], "c": []}) == []

    def test_direct_cycle(self) -> None:
        # a → b → a
        assert mod.detect_cycles({"a": ["b"], "b": ["a"]}) == ["a"]

    def test_self_cycle(self) -> None:
        assert mod.detect_cycles({"a": ["a"]}) == ["a"]

    def test_transitive_cycle(self) -> None:
        # a → b → c → a
        assert mod.detect_cycles({"a": ["b"], "b": ["c"], "c": ["a"]}) == ["a"]

    def test_external_reference_no_cycle(self) -> None:
        # composes targets that are not in graph (out-of-root) are ignored.
        assert mod.detect_cycles({"a": ["external", "b"], "b": []}) == []


# --------------------------------------------------------------------------
# enumerate_stack_skills — end-to-end
# --------------------------------------------------------------------------


class TestEnumerateStackSkills:
    def test_empty_skills_root(self, tmp_path: Path) -> None:
        result = mod.enumerate_stack_skills(tmp_path)
        assert result == {"skills": [], "cycles": [], "warnings": [], "not_skf_output": []}

    def test_single_skill_with_metadata(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "alpha",
            metadata={"name": "alpha", "exports": ["a", "b"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert len(result["skills"]) == 1
        s = result["skills"][0]
        assert s["name"] == "alpha"
        assert s["path"] == "alpha"
        assert s["exports"] == ["a", "b"]
        assert s["exports_source"] == "metadata"
        assert s["confidence"] == "T1"
        assert s["metadata_hash"] is not None
        assert result["cycles"] == []
        assert result["warnings"] == []

    def test_cascade_mix(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "a-meta",
            metadata={"name": "a-meta", "exports": ["m1"]},
        )
        # Marked metadata without an `exports` key falls through the cascade.
        _make_skill(
            tmp_path,
            "b-refs",
            metadata={"name": "b-refs"},
            references={"x.md": "## API\n- r1\n- r2\n"},
        )
        _make_skill(
            tmp_path,
            "c-prose",
            skill_md="# c\n## API Surface\n- p1\n",
            metadata={"name": "c-prose"},
        )
        _make_skill(
            tmp_path,
            "d-none",
            skill_md="# d\n",
            metadata={"name": "d-none"},
        )
        # A module's own skill: no metadata.json, so not SKF output.
        _make_skill(
            tmp_path,
            "e-module",
            skill_md="# e\n## API Surface\n- m1\n",
            metadata=None,
        )
        result = mod.enumerate_stack_skills(tmp_path)
        by_name = {s["name"]: s for s in result["skills"]}
        assert by_name["a-meta"]["exports_source"] == "metadata"
        assert by_name["b-refs"]["exports_source"] == "references"
        assert by_name["c-prose"]["exports_source"] == "skill-md"
        assert by_name["d-none"]["exports_source"] == "unknown"
        assert by_name["d-none"]["confidence"] == "T1-low"
        assert any("d-none: no exports found" in w for w in result["warnings"])
        assert "e-module" not in by_name
        assert result["not_skf_output"] == ["e-module"]

    def test_cycle_in_composes(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "alpha",
            metadata={"name": "alpha", "exports": [], "composes": ["beta"]},
        )
        _make_skill(
            tmp_path,
            "beta",
            metadata={"name": "beta", "exports": [], "composes": ["alpha"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert "alpha" in result["cycles"]
        assert any("composes cycle detected" in w for w in result["warnings"])

    def test_external_compose_target_no_cycle(self, tmp_path: Path) -> None:
        # alpha composes "not-in-root" → not a cycle, no warning.
        _make_skill(
            tmp_path,
            "alpha",
            metadata={
                "name": "alpha",
                "exports": ["x"],
                "composes": ["not-in-root"],
            },
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["cycles"] == []

    def test_hidden_dirs_ignored(self, tmp_path: Path) -> None:
        # Dotfiles/hidden dirs (`.git`, `.analysis`, etc.) must not appear.
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "SKILL.md").write_text("# hidden\n")
        _make_skill(
            tmp_path,
            "visible",
            metadata={"name": "visible", "exports": ["v"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        names = [s["name"] for s in result["skills"]]
        assert names == ["visible"]

    def test_subdir_without_skill_md_silently_skipped(self, tmp_path: Path) -> None:
        # A subdir like `shared/` or `knowledge/` without SKILL.md is NOT a skill.
        (tmp_path / "knowledge").mkdir()
        (tmp_path / "knowledge" / "notes.md").write_text("# notes\n")
        _make_skill(
            tmp_path,
            "real-skill",
            metadata={"name": "real-skill", "exports": ["x"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["name"] for s in result["skills"]] == ["real-skill"]
        # No warning emitted for the non-skill subdir.
        assert all("knowledge" not in w for w in result["warnings"])

    def test_top_level_links_are_never_skf_output(self, tmp_path: Path) -> None:
        # SKF never links a skill folder: a live link to a marked skill is
        # listed as not SKF output, and a broken link holds nothing to list.
        root = tmp_path / "skills"
        _make_skill(root, "real", metadata={"name": "real", "exports": ["x"]})
        _make_skill(tmp_path / "elsewhere", "linked",
                    metadata={"name": "linked", "exports": ["y"]})
        _symlink(tmp_path / "elsewhere" / "linked", root / "linked")
        _symlink(tmp_path / "_does_not_exist", root / "broken-link")
        result = mod.enumerate_stack_skills(root)
        names = [s["name"] for s in result["skills"]]
        assert names == ["real"]
        assert result["not_skf_output"] == ["linked"]
        assert result["warnings"] == []

    def test_skills_emitted_in_sorted_order(self, tmp_path: Path) -> None:
        for n in ("zeta", "alpha", "mu"):
            _make_skill(
                tmp_path,
                n,
                metadata={"name": n, "exports": [n[0]]},
            )
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["name"] for s in result["skills"]] == ["alpha", "mu", "zeta"]

    def test_path_uses_forward_slash(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "p",
            metadata={"name": "p", "exports": []},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        # `path` is relative to skills-root; for a single-level package
        # that's just the name. No backslashes regardless of platform.
        assert "\\" not in result["skills"][0]["path"]


# --------------------------------------------------------------------------
# Version-nested layout resolution
# --------------------------------------------------------------------------


class TestVersionSortKey:
    def test_numeric_ordering(self) -> None:
        assert mod._version_sort_key("1.10.0") > mod._version_sort_key("1.2.0")

    def test_major_dominates(self) -> None:
        assert mod._version_sort_key("2.0.0") > mod._version_sort_key("1.12.0")

    def test_release_ranks_above_prerelease(self) -> None:
        assert mod._version_sort_key("1.0.0") > mod._version_sort_key("1.0.0-rc1")

    def test_non_numeric_ranks_lowest(self) -> None:
        assert mod._version_sort_key("active") < mod._version_sort_key("0.0.1")


class TestVersionNestedLayout:
    """`{name}/{version}/{name}/SKILL.md` with an `active` symlink — the
    canonical layout from knowledge/version-paths.md that the flat-only walk
    used to skip entirely (empty inventory for every constituent)."""

    def test_active_symlink_resolves(self, tmp_path: Path) -> None:
        _make_nested_skill(
            tmp_path,
            "surreal",
            "3.0.5",
            metadata={"name": "surreal", "exports": ["query", "connect"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert len(result["skills"]) == 1
        s = result["skills"][0]
        assert s["name"] == "surreal"
        assert s["path"] == "surreal/active/surreal"
        assert s["exports"] == ["query", "connect"]
        assert s["exports_source"] == "metadata"
        assert s["confidence"] == "T1"
        assert s["metadata_hash"] is not None
        assert result["warnings"] == []

    def test_highest_version_when_no_active(self, tmp_path: Path) -> None:
        _make_nested_skill(
            tmp_path, "lib", "1.2.0",
            metadata={"name": "lib", "exports": ["old"]}, active=False,
        )
        _make_nested_skill(
            tmp_path, "lib", "1.10.0",
            metadata={"name": "lib", "exports": ["new"]}, active=False,
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert len(result["skills"]) == 1
        s = result["skills"][0]
        assert s["exports"] == ["new"]
        assert s["path"] == "lib/1.10.0/lib"

    def test_prerelease_loses_to_release_fallback(self, tmp_path: Path) -> None:
        _make_nested_skill(
            tmp_path, "lib", "1.0.0-rc1",
            metadata={"name": "lib", "exports": ["pre"]}, active=False,
        )
        _make_nested_skill(
            tmp_path, "lib", "1.0.0",
            metadata={"name": "lib", "exports": ["rel"]}, active=False,
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"][0]["exports"] == ["rel"]

    def test_active_symlink_wins_over_higher_version(self, tmp_path: Path) -> None:
        # The stable `active` pointer is authoritative even if a higher
        # version directory exists alongside it.
        _make_nested_skill(
            tmp_path, "lib", "1.0.0",
            metadata={"name": "lib", "exports": ["pinned"]}, active=True,
        )
        _make_nested_skill(
            tmp_path, "lib", "2.0.0",
            metadata={"name": "lib", "exports": ["newer"]}, active=False,
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert len(result["skills"]) == 1
        assert result["skills"][0]["exports"] == ["pinned"]
        assert result["skills"][0]["path"] == "lib/active/lib"

    def test_nested_composes_cycle_detected(self, tmp_path: Path) -> None:
        # Cycle detection keys on the top-level dir name, unaffected by nesting.
        _make_nested_skill(
            tmp_path, "alpha", "1.0.0",
            metadata={"name": "alpha", "exports": [], "composes": ["beta"]},
        )
        _make_nested_skill(
            tmp_path, "beta", "1.0.0",
            metadata={"name": "beta", "exports": [], "composes": ["alpha"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert "alpha" in result["cycles"]
        assert any("composes cycle detected" in w for w in result["warnings"])

    def test_mixed_flat_and_nested(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path, "flatlib", metadata={"name": "flatlib", "exports": ["f"]},
        )
        _make_nested_skill(
            tmp_path, "nestlib", "0.1.0",
            metadata={"name": "nestlib", "exports": ["n"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        by_name = {s["name"]: s for s in result["skills"]}
        assert by_name["flatlib"]["path"] == "flatlib"
        assert by_name["nestlib"]["path"] == "nestlib/active/nestlib"

    def test_version_dir_without_inner_skill_md_skipped(self, tmp_path: Path) -> None:
        # A version dir whose inner package lacks SKILL.md is not a package.
        inner = tmp_path / "broken" / "1.0.0" / "broken"
        inner.mkdir(parents=True)
        (inner / "metadata.json").write_text('{"name":"broken","exports":[]}')
        _make_skill(
            tmp_path, "real", metadata={"name": "real", "exports": ["x"]},
        )
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["name"] for s in result["skills"]] == ["real"]


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
        input=stdin,
    )


class TestCli:
    def test_enumerate_emits_valid_json(self, tmp_path: Path) -> None:
        _make_skill(
            tmp_path,
            "alpha",
            metadata={"name": "alpha", "exports": ["a", "b"]},
        )
        result = _run_cli("enumerate", str(tmp_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert "skills" in payload
        assert "cycles" in payload
        assert "warnings" in payload
        assert len(payload["skills"]) == 1
        assert payload["skills"][0]["name"] == "alpha"
        assert payload["skills"][0]["exports"] == ["a", "b"]
        assert payload["skills"][0]["confidence"] == "T1"

    def test_enumerate_empty_root_exits_0(self, tmp_path: Path) -> None:
        result = _run_cli("enumerate", str(tmp_path))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload == {"skills": [], "cycles": [], "warnings": [], "not_skf_output": []}

    def test_enumerate_bad_root_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("enumerate", str(tmp_path / "does-not-exist"))
        assert result.returncode == 1
        assert "skills root" in result.stderr

    def test_enumerate_missing_subcommand_exits_2(self) -> None:
        # argparse `required=True` on subparsers → returncode 2 on missing arg.
        result = _run_cli()
        assert result.returncode != 0

    def test_default_output_has_no_derived_keys(self, tmp_path: Path) -> None:
        # The additive flags must stay off by default: no --pairs/--reliability
        # means the top-level shape is exactly {skills, cycles, warnings,
        # not_skf_output}, the shape skf-create-stack-skill/parallel-extract.md
        # documents.
        _make_skill(tmp_path, "alpha", metadata={"name": "alpha", "exports": ["a"]})
        result = _run_cli("enumerate", str(tmp_path))
        payload = json.loads(result.stdout)
        assert set(payload) == {"skills", "cycles", "warnings", "not_skf_output"}


# --------------------------------------------------------------------------
# --pairs — deterministic unique library pairs (refine-architecture §3)
# --------------------------------------------------------------------------


class TestComputePairs:
    def test_pure_fn_three_names_sorted(self) -> None:
        # Names supplied out of order → pairs come back in sorted-name order.
        skills = [{"name": "gamma"}, {"name": "alpha"}, {"name": "beta"}]
        assert mod.compute_pairs(skills) == [
            {"library_a": "alpha", "library_b": "beta"},
            {"library_a": "alpha", "library_b": "gamma"},
            {"library_a": "beta", "library_b": "gamma"},
        ]

    def test_pure_fn_single_name_empty(self) -> None:
        assert mod.compute_pairs([{"name": "solo"}]) == []

    def test_pure_fn_empty_inventory(self) -> None:
        assert mod.compute_pairs([]) == []

    def test_pure_fn_dedupes_repeated_name(self) -> None:
        # A pathological duplicate name must not yield a duplicate pair.
        skills = [{"name": "a"}, {"name": "a"}, {"name": "b"}]
        assert mod.compute_pairs(skills) == [{"library_a": "a", "library_b": "b"}]

    def test_pure_fn_count_is_n_choose_2(self) -> None:
        skills = [{"name": n} for n in ("e", "a", "d", "b", "c")]
        pairs = mod.compute_pairs(skills)
        n = 5
        assert len(pairs) == n * (n - 1) // 2 == 10

    def test_cli_pairs_three_skills_exact(self, tmp_path: Path) -> None:
        # Create in non-sorted order to prove ordering is independent of scan.
        for name in ("skill-c", "skill-a", "skill-b"):
            _make_skill(tmp_path, name, metadata={"name": name, "exports": ["x"]})
        result = _run_cli("enumerate", str(tmp_path), "--pairs")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["pairs"] == [
            {"library_a": "skill-a", "library_b": "skill-b"},
            {"library_a": "skill-a", "library_b": "skill-c"},
            {"library_a": "skill-b", "library_b": "skill-c"},
        ]
        assert payload["pair_count"] == 3

    def test_cli_pairs_single_skill_empty(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "only", metadata={"name": "only", "exports": []})
        payload = json.loads(_run_cli("enumerate", str(tmp_path), "--pairs").stdout)
        assert payload["pairs"] == []
        assert payload["pair_count"] == 0

    def test_cli_pairs_count_matches_formula_n5(self, tmp_path: Path) -> None:
        for name in ("a", "b", "c", "d", "e"):
            _make_skill(tmp_path, name, metadata={"name": name, "exports": ["x"]})
        payload = json.loads(_run_cli("enumerate", str(tmp_path), "--pairs").stdout)
        n = 5
        assert payload["pair_count"] == n * (n - 1) // 2 == 10
        assert len(payload["pairs"]) == 10

    def test_cli_pairs_byte_identical_across_runs(self, tmp_path: Path) -> None:
        for name in ("zeta", "alpha", "mu", "beta"):
            _make_skill(tmp_path, name, metadata={"name": name, "exports": ["x"]})
        first = _run_cli("enumerate", str(tmp_path), "--pairs").stdout
        second = _run_cli("enumerate", str(tmp_path), "--pairs").stdout
        assert first == second
        # No duplicate pairs.
        pairs = json.loads(first)["pairs"]
        seen = {(p["library_a"], p["library_b"]) for p in pairs}
        assert len(seen) == len(pairs)


# --------------------------------------------------------------------------
# --reliability — inventory reliability verdict (verify-stack §2 guard)
# --------------------------------------------------------------------------


class TestComputeReliability:
    def test_all_clean_is_reliable(self) -> None:
        v = mod.compute_reliability(3, 0)
        assert v["inventory_reliable"] is True
        assert v["unreliable_ratio"] == 0.0
        assert v["skill_count"] == 3
        assert v["warning_count"] == 0

    def test_boundary_ratio_020_is_reliable(self) -> None:
        # 4 skills + 1 warning => 1/5 = 0.20 exactly. Gate is `<= 0.20`, so
        # the boundary is reliable (matches the prose `> 0.20` halt).
        v = mod.compute_reliability(4, 1)
        assert v["unreliable_ratio"] == 0.20
        assert v["inventory_reliable"] is True

    def test_just_over_boundary_is_unreliable(self) -> None:
        # 3 skills + 2 warnings => 2/5 = 0.40 > 0.20 => unreliable.
        v = mod.compute_reliability(3, 2)
        assert v["unreliable_ratio"] == 0.40
        assert v["inventory_reliable"] is False

    def test_empty_inventory_no_zero_division(self) -> None:
        v = mod.compute_reliability(0, 0)
        assert v["unreliable_ratio"] == 0.0
        assert v["inventory_reliable"] is True

    def test_boundary_flips_exactly_at_threshold(self) -> None:
        # Just below and just above the 0.20 boundary flip the boolean.
        # 1 warning / 5 total (0.20) reliable; 3 warnings / 12 total (0.25)
        # not; 2 warnings / 10 total (0.20) reliable.
        assert mod.compute_reliability(4, 1)["inventory_reliable"] is True
        assert mod.compute_reliability(8, 2)["inventory_reliable"] is True
        assert mod.compute_reliability(9, 3)["inventory_reliable"] is False

    def test_cli_reliability_keys_present(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "alpha", metadata={"name": "alpha", "exports": ["a"]})
        payload = json.loads(
            _run_cli("enumerate", str(tmp_path), "--reliability").stdout
        )
        assert payload["inventory_reliable"] is True
        assert payload["skill_count"] == 1
        assert payload["warning_count"] == 0
        assert payload["unreliable_ratio"] == 0.0

    def test_cli_reliability_unreliable_when_many_warnings(self, tmp_path: Path) -> None:
        # 1 skill with exports + 2 SKF skills that resolve to zero exports
        # emit "no exports found" warnings => 2 warnings / 5 total = 0.40 >
        # 0.20. A module's own skill beside them counts on neither side.
        _make_skill(tmp_path, "good", metadata={"name": "good", "exports": ["x"]})
        _make_skill(tmp_path, "bare1", skill_md="# bare1\n", metadata={"name": "bare1"})
        _make_skill(tmp_path, "bare2", skill_md="# bare2\n", metadata={"name": "bare2"})
        _make_skill(tmp_path, "module", skill_md="# module\n", metadata=None)
        payload = json.loads(
            _run_cli("enumerate", str(tmp_path), "--reliability").stdout
        )
        assert payload["skill_count"] == 3
        assert payload["warning_count"] == 2
        assert payload["inventory_reliable"] is False
        assert payload["not_skf_output"] == ["module"]


# --------------------------------------------------------------------------
# Ownership — a stack roster reads only the skills SKF generated
# --------------------------------------------------------------------------


class TestOwnership:
    """Only a package whose metadata.json carries an SKF marker is a skill.

    The marker functions are pinned copies of skf-skill-inventory.py's
    (test-skf-skill-inventory.py checks the copies and the parity)."""

    def test_module_skills_are_listed_not_counted(self, tmp_path: Path) -> None:
        # A module's own skills in a shared skills folder: SKILL.md only.
        for name in ("lib-a", "lib-b", "lib-c"):
            _make_nested_skill(tmp_path, name, "1.0.0",
                               metadata={"name": name, "exports": [name]})
        _make_skill(tmp_path, "skf-setup", skill_md="# setup\n")
        _make_skill(tmp_path, "skf-drop-skill", skill_md="# drop\n")
        result = _run_cli("enumerate", str(tmp_path), "--pairs", "--reliability")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [s["name"] for s in payload["skills"]] == ["lib-a", "lib-b", "lib-c"]
        assert payload["not_skf_output"] == ["skf-drop-skill", "skf-setup"]
        assert payload["warnings"] == []
        assert payload["inventory_reliable"] is True
        assert (payload["skill_count"], payload["warning_count"]) == (3, 0)
        assert payload["pair_count"] == 3

    def test_unmarked_metadata_is_not_skf_output(self, tmp_path: Path) -> None:
        # A module skill an earlier SKF moved into the versioned layout, and a
        # flat skill whose metadata.json carries exports but no marker.
        _make_nested_skill(tmp_path, "vmod", "1.0.0", metadata=None)
        _make_skill(tmp_path, "metamod", metadata={"name": "metamod", "exports": ["q"]},
                    marked=False)
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"] == []
        assert result["not_skf_output"] == ["metamod", "vmod"]
        assert result["warnings"] == []

    def test_mixed_group_reads_the_marked_version(self, tmp_path: Path) -> None:
        # A module's root SKILL.md beside a marked version: read the version.
        _make_skill(tmp_path, "mix", skill_md="# module\n")
        _make_nested_skill(tmp_path, "mix", "2.0.0", metadata={"name": "mix", "exports": ["m"]})
        result = mod.enumerate_stack_skills(tmp_path)
        assert [(s["name"], s["path"]) for s in result["skills"]] == [("mix", "mix/active/mix")]
        assert result["skills"][0]["exports"] == ["m"]
        assert result["not_skf_output"] == []

    def test_unmarked_active_falls_back_to_the_highest_marked_version(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "half", "1.0.0", metadata={"name": "half"}, marked=False)
        _make_nested_skill(tmp_path, "half", "0.9.0", metadata={"name": "half", "exports": ["h"]},
                           active=False)
        _make_nested_skill(tmp_path, "half", "0.5.0", metadata={"name": "half", "exports": ["old"]},
                           active=False)
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["path"] for s in result["skills"]] == ["half/0.9.0/half"]
        assert result["skills"][0]["exports"] == ["h"]
        assert result["warnings"] == []

    def test_active_outside_the_group_is_ignored(self, tmp_path: Path) -> None:
        # The folder outside shares its name with the marked version inside,
        # so only the check that `active` stays in the group keeps the
        # roster from reading the package behind the link.
        root = tmp_path / "skills"
        _make_nested_skill(root, "out", "1.0.0", metadata={"name": "out", "exports": ["o"]},
                           active=False)
        _make_skill(tmp_path / "elsewhere" / "1.0.0", "out",
                    metadata={"name": "out", "exports": ["foreign"]})
        _symlink(tmp_path / "elsewhere" / "1.0.0", root / "out" / "active")
        result = mod.enumerate_stack_skills(root)
        assert [s["path"] for s in result["skills"]] == ["out/1.0.0/out"]
        assert result["skills"][0]["exports"] == ["o"]

    def test_active_naming_a_staging_version_is_ignored(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "st", "1.0.0", metadata={"name": "st", "exports": ["done"]},
                           active=False)
        _make_nested_skill(tmp_path, "st", "2.0.0.skf-tmp",
                           metadata={"name": "st", "exports": ["partial"]})
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["path"] for s in result["skills"]] == ["st/1.0.0/st"]
        assert result["skills"][0]["exports"] == ["done"]

    def test_real_active_folder_is_read(self, tmp_path: Path) -> None:
        # A real `active/` folder (no link support) holding a marked package.
        _make_skill(tmp_path / "ra" / "active", "ra", metadata={"name": "ra", "exports": ["a"]})
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["path"] for s in result["skills"]] == ["ra/active/ra"]
        assert result["not_skf_output"] == [] and result["warnings"] == []

    def test_linked_package_is_not_skf_output_whatever_its_metadata(self, tmp_path: Path) -> None:
        # SKF never links the package inside a version folder, so a corrupt
        # metadata.json behind such a link is not a warning: the folder is
        # listed as not SKF output, as the inventory lists it.
        root = tmp_path / "skills"
        ext = tmp_path / "ext"
        _write(ext / "lnk" / "SKILL.md", "# l\n")
        _write(ext / "lnk" / "metadata.json", '{"generated_by":"create-skill", broken')
        _symlink(ext / "lnk", root / "lnk" / "1.0.0" / "lnk")
        _write(ext / "act" / "SKILL.md", "# a\n")
        _write(ext / "act" / "metadata.json", "{broken")
        _symlink(ext / "act", root / "act" / "1.0.0" / "act")
        _symlink(Path("1.0.0"), root / "act" / "active")
        result = mod.enumerate_stack_skills(root)
        assert result["skills"] == []
        assert result["not_skf_output"] == ["act", "lnk"]
        assert result["warnings"] == []

    def test_linked_version_folder_is_passed_over_without_a_warning(self, tmp_path: Path) -> None:
        # SKF never links a version folder, so a corrupt metadata.json behind
        # one is never read: the marked real version beside it is read, and a
        # group holding only the linked version is not SKF output.
        root = tmp_path / "skills"
        ext = tmp_path / "ext"
        for group in ("lv", "only"):
            _write(ext / group / group / "SKILL.md", "# linked\n")
            _write(ext / group / group / "metadata.json", '{"generated_by":"create-skill", broken')
            _symlink(ext / group, root / group / "2.0.0")
        _make_nested_skill(root, "lv", "1.0.0", metadata={"name": "lv", "exports": ["lv"]},
                           active=False)
        result = mod.enumerate_stack_skills(root)
        assert [s["path"] for s in result["skills"]] == ["lv/1.0.0/lv"]
        assert result["not_skf_output"] == ["only"]
        assert result["warnings"] == []

    def test_marked_flat_root_yields_to_a_marked_version(self, tmp_path: Path) -> None:
        # Candidates: the version `active` names, then the versions from
        # highest to lowest, and only then a flat root.
        _make_skill(tmp_path, "fv", metadata={"name": "fv", "exports": ["flat"]})
        _make_nested_skill(tmp_path, "fv", "1.0.0", metadata={"name": "fv", "exports": ["ver"]},
                           active=False)
        result = mod.enumerate_stack_skills(tmp_path)
        assert [(s["path"], s["exports"]) for s in result["skills"]] == [("fv/1.0.0/fv", ["ver"])]

    def test_corrupt_metadata_is_one_counted_warning(self, tmp_path: Path) -> None:
        pkg = _make_nested_skill(tmp_path, "corrupt", "1.0.0", metadata=None)
        _write(pkg / "metadata.json", '{"generated_by":"create-skill", broken')
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"] == [] and result["not_skf_output"] == []
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith("corrupt: SKF cannot tell whether it generated")

    def test_bom_metadata_is_one_counted_warning(self, tmp_path: Path) -> None:
        pkg = _make_skill(tmp_path, "bom")
        marked = json.dumps({"generated_by": "create-skill", "exports": ["b"]}).encode("utf-8")
        _write_bytes(pkg / "metadata.json", b"\xef\xbb\xbf" + marked)
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"] == [] and result["not_skf_output"] == []
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith("bom: SKF cannot tell whether it generated")
        assert "bom/metadata.json" in result["warnings"][0]

    def test_non_object_metadata_is_one_counted_warning(self, tmp_path: Path) -> None:
        pkg = _make_nested_skill(tmp_path, "arr", "1.0.0", metadata=None)
        _write(pkg / "metadata.json", '["generated_by", "create-skill"]')
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"] == [] and result["not_skf_output"] == []
        assert result["warnings"] == [
            "arr: SKF cannot tell whether it generated this skill: "
            "arr/1.0.0/arr/metadata.json root is not an object"]

    def test_unreadable_active_version_warns_and_reads_the_older_one(self, tmp_path: Path) -> None:
        # 2.0.0 is both `active` and the highest version: it is named once.
        pkg = _make_nested_skill(tmp_path, "act", "2.0.0", metadata=None)
        _write(pkg / "metadata.json", "{bad")
        _make_nested_skill(tmp_path, "act", "1.0.0", metadata={"name": "act", "exports": ["a"]},
                           active=False)
        result = mod.enumerate_stack_skills(tmp_path)
        assert [s["path"] for s in result["skills"]] == ["act/1.0.0/act"]
        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning.startswith("act: act/2.0.0/act/metadata.json is not valid JSON")
        assert warning.count("act/2.0.0/act/metadata.json") == 1
        assert "read the SKF package at act/1.0.0/act" in warning

    def test_too_deeply_nested_metadata_is_one_warning_not_a_crash(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "good", metadata={"name": "good", "exports": ["g"]})
        _write(tmp_path / "deep" / "SKILL.md", "# deep\n")
        _write(tmp_path / "deep" / "metadata.json", "[" * 200000)
        result = _run_cli("enumerate", str(tmp_path))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [s["name"] for s in payload["skills"]] == ["good"]
        assert payload["not_skf_output"] == []
        assert len(payload["warnings"]) == 1
        assert payload["warnings"][0].startswith("deep: failed to resolve package dir")

    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="needs POSIX permissions that deny this user")
    def test_link_to_an_unreadable_folder_is_skipped_not_a_crash(self, tmp_path: Path) -> None:
        root = tmp_path / "skills"
        _make_skill(root, "good", metadata={"name": "good", "exports": ["g"]})
        locked = tmp_path / "locked"
        _write(locked / "mod" / "SKILL.md", "# mod\n")
        _symlink(locked / "mod", root / "mod")
        locked.chmod(0)
        try:
            result = _run_cli("enumerate", str(root))
        finally:
            locked.chmod(0o755)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert [s["name"] for s in payload["skills"]] == ["good"]
        assert payload["not_skf_output"] == [] and payload["warnings"] == []

    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="needs POSIX permissions that deny this user")
    @pytest.mark.parametrize("locked_rel, prefix", [
        ("zzz", None),
        ("2.0.0", "x: x/2.0.0 cannot be read ("),
        ("2.0.0/x", "x: x/2.0.0/x/metadata.json failed to read ("),
    ])
    def test_unreadable_folder_in_a_group_keeps_its_marked_version(
            self, tmp_path: Path, locked_rel: str, prefix: str | None) -> None:
        # One folder SKF cannot search never drops the marked version beside
        # it; when it sorts above that version it is named in one warning.
        _make_nested_skill(tmp_path, "x", "1.0.0", metadata={"name": "x", "exports": ["x"]},
                           active=False)
        _make_nested_skill(tmp_path, "y", "1.0.0", metadata={"name": "y", "exports": ["y"]},
                           active=False)
        (tmp_path / "x" / locked_rel.split("/")[0] / "x").mkdir(parents=True)
        locked = tmp_path / "x" / locked_rel
        locked.chmod(0)
        try:
            result = mod.enumerate_stack_skills(tmp_path)
        finally:
            locked.chmod(0o755)
        assert [(s["name"], s["path"]) for s in result["skills"]] == [
            ("x", "x/1.0.0/x"), ("y", "y/1.0.0/y")]
        assert result["not_skf_output"] == []
        if prefix is None:
            assert result["warnings"] == []
        else:
            assert len(result["warnings"]) == 1
            warning = result["warnings"][0]
            assert warning.startswith(prefix), warning
            assert warning.endswith("; read the SKF package at x/1.0.0/x instead")

    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="needs POSIX permissions that deny this user")
    def test_group_that_cannot_be_listed_is_one_warning(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "x", "1.0.0", metadata={"name": "x", "exports": ["x"]},
                           active=False)
        group = tmp_path / "x"
        group.chmod(0o311)  # searchable, not listable
        try:
            result = mod.enumerate_stack_skills(tmp_path)
        finally:
            group.chmod(0o755)
        assert result["skills"] == [] and result["not_skf_output"] == []
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith(
            "x: SKF cannot tell whether it generated this skill: x cannot be listed (")

    def test_marked_package_without_skill_md_warns(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "nosk", "1.0.0", skill_md=None,
                           metadata={"name": "nosk", "exports": []})
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"] == [] and result["not_skf_output"] == []
        assert result["warnings"] == ["nosk: the SKF package at nosk/active/nosk has no SKILL.md"]

    def test_staging_and_batch_names_are_skipped(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "foo.skf-tmp", metadata={"name": "foo", "exports": ["f"]})
        _make_skill(tmp_path, "_batch", skill_md="# batch\n")
        _write(tmp_path / "_batch" / "quick-skill-batch-latest.json", "{}")
        _make_nested_skill(tmp_path, "stage", "1.0.0", metadata={"name": "stage", "exports": ["s"]},
                           active=False)
        _make_nested_skill(tmp_path, "stage", "2.0.0.skf-tmp",
                           metadata={"name": "stage", "exports": ["partial"]}, active=False)
        result = mod.enumerate_stack_skills(tmp_path)
        assert [(s["name"], s["path"]) for s in result["skills"]] == [("stage", "stage/1.0.0/stage")]
        assert result["not_skf_output"] == []
        assert result["warnings"] == []

    def test_package_must_be_named_after_its_folder(self, tmp_path: Path) -> None:
        _make_skill(tmp_path / "pack" / "1.0.0", "other",
                    metadata={"name": "other", "exports": ["x"]})
        result = mod.enumerate_stack_skills(tmp_path)
        assert result["skills"] == [] and result["not_skf_output"] == []
        assert result["warnings"] == []

    def test_enumerated_skills_always_have_a_metadata_hash(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "flat", metadata={"name": "flat", "exports": ["f"]})
        _make_nested_skill(tmp_path, "refs", "1.0.0", metadata={"name": "refs"},
                           references={"api.md": "## API\n- r\n"})
        _make_skill(tmp_path, "prose", skill_md="# p\n## Exports\n- p\n", metadata={"name": "prose"})
        _make_skill(tmp_path, "module", skill_md="# m\n## Exports\n- m\n")
        result = mod.enumerate_stack_skills(tmp_path)
        by_name = {s["name"]: s for s in result["skills"]}
        assert sorted(by_name) == ["flat", "prose", "refs"]
        assert [by_name[n]["exports_source"] for n in ("flat", "refs", "prose")] == [
            "metadata", "references", "skill-md"]
        for entry in result["skills"]:
            assert entry["metadata_hash"] and entry["metadata_hash"].startswith("sha256:"), entry


# --------------------------------------------------------------------------
# evidence_tier: the dominant bin of metadata.json confidence_distribution
# --------------------------------------------------------------------------


class TestDominantTier:
    @pytest.mark.parametrize("distribution, tier", [
        ({"t1": 5}, "T1"),
        ({"t1": 1, "t1_low": 4}, "T1-low"),
        ({"t1": 1, "t2": 4, "t3": 2}, "T2"),
        ({"t3": 7}, "T3"),
        ({"t1": 9, "t1_low": 2, "t2": 3, "t3": 1}, "T1"),
        ({"t1": 2.5, "t2": 2}, "T1"),
    ])
    def test_the_largest_bin_wins(self, distribution: dict, tier: str) -> None:
        assert mod.dominant_tier(distribution) == tier

    @pytest.mark.parametrize("distribution, tier", [
        ({"t1": 3, "t1_low": 3}, "T1-low"),
        ({"t1_low": 3, "t2": 3}, "T2"),
        ({"t2": 3, "t3": 3}, "T3"),
        ({"t1": 3, "t3": 3}, "T3"),
        ({"t1": 2, "t1_low": 2, "t2": 2, "t3": 2}, "T3"),
        ({"t1": 4, "t1_low": 4, "t2": 1}, "T1-low"),
    ])
    def test_a_tie_goes_to_the_weaker_tier(self, distribution: dict, tier: str) -> None:
        assert mod.dominant_tier(distribution) == tier

    @pytest.mark.parametrize("distribution", [
        None, {}, [], "T1", {"t1": 0, "t1_low": 0, "t2": 0, "t3": 0},
    ])
    def test_no_recorded_evidence_reads_t1_low(self, distribution) -> None:
        assert mod.dominant_tier(distribution) == "T1-low"

    @pytest.mark.parametrize("value", [
        True, "9", -9, None, [9], {"n": 9}, float("nan"), float("inf"),
    ])
    def test_a_bin_without_a_positive_number_does_not_count(self, value) -> None:
        assert mod.dominant_tier({"t1": value, "t3": 1}) == "T3"

    def test_only_the_canonical_bin_names_count(self) -> None:
        assert mod.dominant_tier({"T1": 9, "t1-low": 9, "t3": 1}) == "T3"


class TestEvidenceTier:
    def test_docs_only_skill_reads_t3_while_its_confidence_reads_t1(self, tmp_path: Path) -> None:
        # SKF's generators always write an exports array, so the exports
        # source of a docs-only skill is metadata (T1) while all of its
        # recorded evidence is T3.
        _make_skill(tmp_path, "docs", metadata={
            "name": "docs", "exports": [],
            "confidence_distribution": {"t1": 0, "t1_low": 0, "t2": 0, "t3": 12}})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert (entry["confidence"], entry["evidence_tier"]) == ("T1", "T3")

    def test_largest_bin_t1_low_is_not_read_as_t1(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "src-read", "1.0.0", active=False, metadata={
            "name": "src-read", "exports": ["a", "b", "c"],
            "confidence_distribution": {"t1": 1, "t1_low": 2, "t2": 0, "t3": 0}})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert (entry["confidence"], entry["evidence_tier"]) == ("T1", "T1-low")

    def test_evidence_tier_does_not_follow_the_exports_source(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "refs", metadata={
            "name": "refs", "confidence_distribution": {"t1": 8, "t2": 1}},
            references={"api.md": "## API\n- r\n"})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert (entry["confidence"], entry["evidence_tier"]) == ("T2", "T1")

    def test_no_distribution_reads_t1_low(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "bare", metadata={"name": "bare", "exports": ["b"]})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert entry["evidence_tier"] == "T1-low"


# --------------------------------------------------------------------------
# metadata.json fields on each skills[] entry
# --------------------------------------------------------------------------


ENTRY_KEYS = [
    "name", "path", "exports", "exports_source", "confidence", "evidence_tier",
    "metadata_hash", "skill_type", "language", "confidence_tier", "exports_documented",
    "metadata_schema_version", "source_repo", "source_repo_basename", "source_root",
    "source_root_basename",
]

METADATA_FIELD_KEYS = ENTRY_KEYS[ENTRY_KEYS.index("skill_type"):]


class TestMetadataFields:
    def test_an_entry_carries_every_field(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "cognee", "0.6.0", active=False, metadata={
            "name": "cognee", "version": "0.6.0", "skill_type": "single",
            "source_repo": "https://github.com/topoteretes/Cognee.git",
            "source_root": "/work/repos/github.com/topoteretes/cognee/",
            "confidence_tier": "Forge+", "spec_version": "1.3", "language": "python",
            "exports": ["add", "cognify", "search"],
            "confidence_distribution": {"t1": 3, "t1_low": 0, "t2": 0, "t3": 0},
            "stats": {"exports_documented": 3, "exports_total": 9}})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert list(entry) == ENTRY_KEYS
        assert {key: entry[key] for key in METADATA_FIELD_KEYS} == {
            "skill_type": "single",
            "language": "python",
            "confidence_tier": "Forge+",
            "exports_documented": 3,
            "metadata_schema_version": "1.3",
            "source_repo": "https://github.com/topoteretes/Cognee.git",
            "source_repo_basename": "cognee",
            "source_root": "/work/repos/github.com/topoteretes/cognee/",
            "source_root_basename": "cognee",
        }
        assert (entry["confidence"], entry["evidence_tier"]) == ("T1", "T1")

    def test_fields_are_null_when_metadata_lacks_them(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "bare", metadata={"name": "bare", "exports": ["b"]})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert list(entry) == ENTRY_KEYS
        assert all(entry[key] is None for key in METADATA_FIELD_KEYS), entry

    def test_resolve_skill_without_metadata_has_every_field(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "nometa", skill_md="# n\n## Exports\n- n\n", metadata=None)
        entry, _, _ = mod.resolve_skill(skill_dir, "nometa")
        assert list(entry) == ENTRY_KEYS
        assert entry["evidence_tier"] == "T1-low"
        assert all(entry[key] is None for key in METADATA_FIELD_KEYS), entry

    def test_quick_skill_metadata(self, tmp_path: Path) -> None:
        # The shape skf-render-quick-metadata.py writes: an empty source_root.
        _make_skill(tmp_path, "quick", metadata={
            "name": "quick", "skill_type": "single", "generated_by": "quick-skill",
            "source_repo": "https://github.com/x/Quick", "source_root": "",
            "language": "typescript", "confidence_tier": "Quick", "spec_version": "1.3",
            "exports": ["q"], "confidence_distribution": {"t1": 0, "t1_low": 1, "t2": 0, "t3": 0},
            "stats": {"exports_documented": 1}})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert (entry["source_repo_basename"], entry["source_root"], entry["source_root_basename"]) == (
            "quick", None, None)
        assert (entry["confidence_tier"], entry["evidence_tier"]) == ("Quick", "T1-low")

    @pytest.mark.parametrize("skill_type, tier, expected", [
        ("single", "Forge+", "Forge+"),
        ("single", "T1", None),
        ("single", "forge", None),
        ("single", 3, None),
        ("individual", "Deep", "Deep"),
        (None, "Quick", "Quick"),
        (None, "T2", None),
        ("stack", "T1-low", "T1-low"),
        ("stack", "T3", "T3"),
        ("stack", "Deep", None),  # a stack written before its tier was a T-code
        ("pipeline", "Forge", "Forge"),
        ("pipeline", "T2", "T2"),
        (7, "Deep", "Deep"),  # a skill_type that is not a string counts as none
    ])
    def test_confidence_tier_follows_its_skill_type_scale(self, skill_type, tier, expected) -> None:
        metadata = {"confidence_tier": tier}
        if skill_type is not None:
            metadata["skill_type"] = skill_type
        fields = mod.metadata_fields(metadata)
        assert fields["confidence_tier"] == expected
        assert fields["skill_type"] == (skill_type if isinstance(skill_type, str) else None)

    @pytest.mark.parametrize("language, expected", [
        ("python", "python"),
        ("  TypeScript ", "TypeScript"),
        (["python", " rust ", "", 3], ["python", "rust"]),
        ([], None),
        ([""], None),
        ("", None),
        ("   ", None),
        (7, None),
        ({"primary": "go"}, None),
    ])
    def test_language(self, language, expected) -> None:
        assert mod.metadata_fields({"language": language})["language"] == expected

    @pytest.mark.parametrize("stats, expected", [
        ({"exports_documented": 12}, 12),
        ({"exports_documented": 0}, 0),
        ({"exports_documented": 12.0}, 12),
        ({"exports_documented": 12.5}, None),
        ({"exports_documented": -1}, None),
        ({"exports_documented": True}, None),
        ({"exports_documented": "12"}, None),
        ({}, None),
        ("12", None),
        (None, None),
    ])
    def test_exports_documented(self, stats, expected) -> None:
        assert mod.metadata_fields({"stats": stats})["exports_documented"] == expected

    @pytest.mark.parametrize("spec_version, expected", [
        ("1.3", "1.3"),
        (" 1.3 ", "1.3"),
        ("", None),
        (1.3, None),
    ])
    def test_metadata_schema_version_is_spec_version(self, spec_version, expected) -> None:
        assert mod.metadata_fields({"spec_version": spec_version})["metadata_schema_version"] == expected

    @pytest.mark.parametrize("source_repo, basename", [
        ("https://github.com/Org/Repo", "repo"),
        ("https://github.com/Org/Repo.git", "repo"),
        ("https://github.com/Org/Repo.GIT/", "repo"),
        ("github.com/foo/bar", "bar"),
        ("vercel/next.js", "next.js"),
        ("git@github.com:org/repo.git", "repo"),
        ("/work/src/My-Lib/", "my-lib"),
        ("C:\\work\\MyLib", "mylib"),
        (" https://github.com/org/spaced ", "spaced"),
        ("react", None),  # no separator: no URL, owner/repo pair or path
        ("https://github.com/org/.git", None),
        ("https://github.com/org/..", None),
        ("///", None),
        ("", None),
        ("   ", None),
        (42, None),
    ])
    def test_source_repo_basename(self, source_repo, basename) -> None:
        assert mod.metadata_fields({"source_repo": source_repo})["source_repo_basename"] == basename

    @pytest.mark.parametrize("source_root, basename", [
        ("packages/Core", "core"),
        ("packages/core/", "core"),
        ("src\\Win\\Pkg", "pkg"),
        ("/work/repos/Repo", "repo"),
        ("mylib", "mylib"),
        ("app.git", "app.git"),  # only source_repo drops .git
        (".", None),
        ("..", None),
        ("/", None),
        ("", None),
    ])
    def test_source_root_basename(self, source_root, basename) -> None:
        assert mod.metadata_fields({"source_root": source_root})["source_root_basename"] == basename

    def test_source_fields_are_trimmed(self) -> None:
        fields = mod.metadata_fields({"source_repo": " https://github.com/a/b ", "source_root": " src/b "})
        assert (fields["source_repo"], fields["source_root"]) == ("https://github.com/a/b", "src/b")

    def test_a_stack_lists_its_languages(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "app-stack", metadata={
            "name": "app-stack", "skill_type": "stack", "generated_by": "create-stack-skill",
            "confidence_tier": "T1-low", "forge_tier": "Deep", "language": ["python", "typescript"],
            "exports": [], "confidence_distribution": {"t1": 1, "t1_low": 2, "t2": 0, "t3": 0},
            "stats": {"exports_documented": 14}})
        [entry] = mod.enumerate_stack_skills(tmp_path)["skills"]
        assert (entry["skill_type"], entry["confidence_tier"], entry["evidence_tier"]) == (
            "stack", "T1-low", "T1-low")
        assert entry["language"] == ["python", "typescript"]
        assert entry["exports_documented"] == 14
        assert entry["source_repo"] is None and entry["source_repo_basename"] is None


# --------------------------------------------------------------------------
# --expect-hashes: which skills changed against a recorded run
# --------------------------------------------------------------------------


class TestExpectHashes:
    def test_compare_hashes(self) -> None:
        skills = [{"name": "a", "metadata_hash": "h1"}, {"name": "b", "metadata_hash": "h2-new"},
                  {"name": "d", "metadata_hash": "h4"}]
        expected = {"c": "h3", "b": "h2", "a": "h1"}
        assert mod.compare_hashes(skills, expected) == {
            "changed_skills": ["b"], "missing_skills": ["c"], "new_skills": ["d"]}

    def test_a_null_recorded_hash_never_matches(self) -> None:
        skills = [{"name": "a", "metadata_hash": "sha256:1"}]
        assert mod.compare_hashes(skills, {"a": None})["changed_skills"] == ["a"]

    def test_hashes_compare_as_written(self) -> None:
        skills = [{"name": "a", "metadata_hash": "sha256:abc"}]
        assert mod.compare_hashes(skills, {"a": "abc"})["changed_skills"] == ["a"]

    def test_load_takes_an_enumerate_result(self) -> None:
        text = json.dumps({"skills": [{"name": "a", "metadata_hash": "h1", "exports": []},
                                      {"name": "b", "metadata_hash": "h2"}],
                           "cycles": [], "warnings": [], "not_skf_output": ["m"]})
        assert mod.load_expected_hashes(text) == {"a": "h1", "b": "h2"}

    def test_load_takes_a_name_to_hash_object(self) -> None:
        assert mod.load_expected_hashes('{"a": "h1", "skills": "h2", "c": null}') == {
            "a": "h1", "skills": "h2", "c": None}
        assert mod.load_expected_hashes("{}") == {}

    @pytest.mark.parametrize("text", [
        "[]",
        '"sha256:1"',
        '{"a": 1}',
        '{"a": {"metadata_hash": "h"}}',
        '{"skills": ["a"]}',
        '{"skills": [{"metadata_hash": "h"}]}',
        '{"skills": [{"name": "a", "metadata_hash": 5}]}',
        '{"skills": [{"name": "a", "metadata_hash": "h"}, {"name": "a", "metadata_hash": "h"}]}',
        "{not json",
    ])
    def test_load_refuses_any_other_shape(self, text: str) -> None:
        with pytest.raises(ValueError):
            mod.load_expected_hashes(text)

    def test_cli_names_the_skills_that_changed_since_the_recorded_run(self, tmp_path: Path) -> None:
        root = tmp_path / "skills"
        for name in ("keep", "edit", "gone"):
            _make_nested_skill(root, name, "1.0.0", metadata={"name": name, "exports": [name]},
                               active=False)
        first = _run_cli("enumerate", str(root))
        assert first.returncode == 0, first.stderr
        recorded = _write(tmp_path / "inventory.json", first.stdout)

        meta = root / "edit" / "1.0.0" / "edit" / "metadata.json"
        meta.write_text(json.dumps({**json.loads(meta.read_text()), "description": "edited"}))
        shutil.rmtree(root / "gone")
        _make_nested_skill(root, "added", "1.0.0", metadata={"name": "added", "exports": ["n"]},
                           active=False)

        result = _run_cli("enumerate", str(root), "--expect-hashes", str(recorded))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["changed_skills"], payload["missing_skills"], payload["new_skills"]) == (
            ["edit"], ["gone"], ["added"])
        assert [s["name"] for s in payload["skills"]] == ["added", "edit", "keep"]

    def test_cli_unchanged_run_reports_empty_lists(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            _make_skill(tmp_path / "skills", name, metadata={"name": name, "exports": [name]})
        recorded = _write(tmp_path / "inventory.json", _run_cli("enumerate", str(tmp_path / "skills")).stdout)
        payload = json.loads(
            _run_cli("enumerate", str(tmp_path / "skills"), "--expect-hashes", str(recorded)).stdout)
        assert (payload["changed_skills"], payload["missing_skills"], payload["new_skills"]) == ([], [], [])

    def test_cli_reads_a_name_to_hash_object_from_stdin(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "a", metadata={"name": "a", "exports": ["a"]})
        _make_skill(tmp_path, "b", metadata={"name": "b", "exports": ["b"]})
        [a, _b] = mod.enumerate_stack_skills(tmp_path)["skills"]
        stdin = json.dumps({"a": a["metadata_hash"], "b": "sha256:stale", "z": "sha256:gone"})
        result = _run_cli("enumerate", str(tmp_path), "--expect-hashes", "-", stdin=stdin)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert (payload["changed_skills"], payload["missing_skills"], payload["new_skills"]) == (
            ["b"], ["z"], [])

    def test_cli_combines_with_the_other_flags(self, tmp_path: Path) -> None:
        for name in ("a", "b"):
            _make_skill(tmp_path, name, metadata={"name": name, "exports": [name]})
        result = _run_cli("enumerate", str(tmp_path), "--pairs", "--reliability",
                          "--expect-hashes", "-", stdin="{}")
        payload = json.loads(result.stdout)
        assert payload["pair_count"] == 1 and payload["inventory_reliable"] is True
        assert payload["new_skills"] == ["a", "b"]

    @pytest.mark.parametrize("content", [None, "{not json", '["a"]', '{"a": 1}'])
    def test_cli_bad_expect_hashes_file_exits_1(self, tmp_path: Path, content: str | None) -> None:
        _make_skill(tmp_path / "skills", "a", metadata={"name": "a", "exports": ["a"]})
        recorded = tmp_path / "inventory.json"
        if content is not None:
            recorded.write_text(content, encoding="utf-8")
        result = _run_cli("enumerate", str(tmp_path / "skills"), "--expect-hashes", str(recorded))
        assert result.returncode == 1
        assert result.stderr.startswith("error: --expect-hashes "), result.stderr
        assert result.stdout == ""


# --------------------------------------------------------------------------
# candidates: pick the compose-mode candidates and gate them
# --------------------------------------------------------------------------


CANDIDATE_KEYS = {"candidate_source", "kept", "excluded", "stale_manifest_keys",
                  "manifest_parse_error", "cycles", "warnings", "not_skf_output"}


def _write_manifest(root: Path, content) -> None:
    """Write `.export-manifest.json`: a dict of exports, or raw text or bytes."""
    if isinstance(content, dict):
        content = json.dumps({"schema_version": "2", "exports": content})
    if isinstance(content, str):
        content = content.encode("utf-8")
    _write_bytes(root / ".export-manifest.json", content)


def _gate(result: dict) -> tuple[list[str], list[tuple[str, str]]]:
    """(kept names, [(skill_dir, reason)]) of a candidates result."""
    return ([e["name"] for e in result["kept"]],
            [(x["skill_dir"], x["reason"]) for x in result["excluded"]])


def _stack_folder(root: Path) -> None:
    """A skills folder holding each shape a candidate can take."""
    for name in ("alpha", "beta"):
        _make_nested_skill(root, name, "1.0.0", metadata={"name": name, "exports": [name]},
                           active=False)
    _make_nested_skill(root, "app-stack", "1.0.0", active=False, metadata={
        "name": "app-stack", "skill_type": "stack", "generated_by": "create-stack-skill",
        "exports": []})
    _make_skill(root, "module", skill_md="# module\n")  # a module's own skill
    pkg = _make_nested_skill(root, "corrupt", "1.0.0", metadata=None, active=False)
    _write(pkg / "metadata.json", '{"generated_by":"create-skill", broken')
    _write(root / "notes" / "README.md", "# notes\n")  # a folder that holds no skill


class TestCandidates:
    def test_manifest_keys_are_gated_against_the_roster(self, tmp_path: Path) -> None:
        _stack_folder(tmp_path)
        _write_manifest(tmp_path, {name: {} for name in (
            "alpha", "app-stack", "module", "corrupt", "notes", "gone")})
        result = mod.compute_candidates(tmp_path)
        assert set(result) == CANDIDATE_KEYS
        assert result["candidate_source"] == "manifest"
        assert result["manifest_parse_error"] is None
        assert _gate(result) == (["alpha"], [
            ("app-stack", "not-a-skill"), ("corrupt", "roster-warning"),
            ("module", "not-skf-output"), ("notes", "no-skf-package")])
        assert result["stale_manifest_keys"] == ["gone"]

    def test_each_exclusion_carries_its_log_line(self, tmp_path: Path) -> None:
        _stack_folder(tmp_path)
        result = mod.compute_candidates(
            tmp_path, ["app-stack", "corrupt", "module", "notes", "gone"])
        messages = {x["skill_dir"]: x["message"] for x in result["excluded"]}
        assert messages["app-stack"] == "app-stack: not a skill (skill_type stack), excluding"
        assert messages["module"] == "module: not SKF output, excluding"
        assert messages["notes"] == "notes: no SKF skill package, excluding"
        assert messages["gone"] == "gone: no such skill folder, excluding"
        assert messages["corrupt"].startswith(
            "corrupt: SKF cannot tell whether it generated this skill: "
            "corrupt/1.0.0/corrupt/metadata.json is not valid JSON")
        for excluded in result["excluded"]:
            assert excluded["message"].startswith(excluded["skill_dir"] + ": ")
            assert "\u2014" not in excluded["message"]

    def test_explicit_names_replace_the_manifest(self, tmp_path: Path) -> None:
        _stack_folder(tmp_path)
        _write_manifest(tmp_path, "{broken")
        result = mod.compute_candidates(tmp_path, ["beta", "gone", "module", "beta"])
        assert result["candidate_source"] == "explicit"
        assert result["manifest_parse_error"] is None  # the manifest is not read
        assert _gate(result) == (["beta"], [("gone", "no-such-folder"), ("module", "not-skf-output")])
        assert result["stale_manifest_keys"] == []

    def test_kept_entries_are_the_roster_entries(self, tmp_path: Path) -> None:
        _stack_folder(tmp_path)
        roster = mod.enumerate_stack_skills(tmp_path)
        result = mod.compute_candidates(tmp_path, ["beta", "alpha"])
        assert result["kept"] == [s for s in roster["skills"] if s["name"] in ("alpha", "beta")]
        assert [e["path"] for e in result["kept"]] == ["alpha/1.0.0/alpha", "beta/1.0.0/beta"]
        for key in ("cycles", "warnings", "not_skf_output"):
            assert result[key] == roster[key]

    def test_single_individual_and_untyped_skills_are_kept(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "one", metadata={"skill_type": "single", "exports": ["o"]})
        _make_skill(tmp_path, "old", metadata={"skill_type": "individual", "confidence_tier": "Forge",
                                               "exports": ["i"]})
        _make_skill(tmp_path, "quick", metadata={"generated_by": "quick-skill", "exports": ["q"]})
        _make_skill(tmp_path, "pipe", metadata={"skill_type": "pipeline", "exports": ["p"]})
        _make_skill(tmp_path, "stk", metadata={"skill_type": "stack", "exports": []})
        result = mod.compute_candidates(tmp_path, ["one", "old", "quick", "pipe", "stk"])
        assert _gate(result) == (["old", "one", "quick"], [
            ("pipe", "not-a-skill"), ("stk", "not-a-skill")])
        assert result["excluded"][0]["message"] == "pipe: not a skill (skill_type pipeline), excluding"

    def test_unreadable_manifest_falls_back_to_the_active_folders(self, tmp_path: Path) -> None:
        _make_skill(tmp_path / "ra" / "active", "ra", metadata={"name": "ra", "exports": ["r"]})
        _make_nested_skill(tmp_path, "alpha", "1.0.0", metadata={"name": "alpha", "exports": ["a"]},
                           active=False)  # no `active`: not a candidate
        _make_skill(tmp_path, "flat", metadata={"name": "flat", "exports": ["f"]})
        _write(tmp_path / "mod" / "active" / "mod" / "SKILL.md", "# a module skill\n")
        _write(tmp_path / "other" / "active" / "diff" / "SKILL.md", "# named elsewhere\n")
        _write(tmp_path / "noskill" / "active" / "x" / "README.md", "# no SKILL.md\n")
        _write(tmp_path / "dotted" / "active" / ".hidden" / "SKILL.md", "# dot name\n")
        for skipped in (".hidden", "_batch", "st.skf-tmp"):
            _write(tmp_path / skipped / "active" / "x" / "SKILL.md", "# skipped\n")
        _write_manifest(tmp_path, "{broken")
        result = mod.compute_candidates(tmp_path)
        assert result["candidate_source"] == "active-links"
        assert result["manifest_parse_error"].startswith(".export-manifest.json is not valid JSON (")
        assert _gate(result) == (["ra"], [("mod", "not-skf-output"), ("other", "no-skf-package")])
        assert result["kept"][0]["path"] == "ra/active/ra"

    def test_an_active_link_is_a_candidate(self, tmp_path: Path) -> None:
        _make_nested_skill(tmp_path, "linked", "2.0.0", metadata={"name": "linked", "exports": ["l"]})
        result = mod.compute_candidates(tmp_path)
        assert result["candidate_source"] == "active-links"
        assert _gate(result) == (["linked"], [])
        assert result["kept"][0]["path"] == "linked/active/linked"

    @pytest.mark.parametrize("manifest", [
        None,
        {},
        '{"schema_version": "2"}',
        '{"schema_version": "2", "exports": null}',
    ])
    def test_a_manifest_that_lists_nothing_falls_back_without_an_error(
            self, tmp_path: Path, manifest) -> None:
        _make_skill(tmp_path / "ra" / "active", "ra", metadata={"name": "ra", "exports": ["r"]})
        if manifest is not None:
            _write_manifest(tmp_path, manifest)
        result = mod.compute_candidates(tmp_path)
        assert (result["candidate_source"], result["manifest_parse_error"]) == ("active-links", None)
        assert _gate(result) == (["ra"], [])

    @pytest.mark.parametrize("manifest, error", [
        ("[]", ".export-manifest.json root is not an object"),
        ('{"exports": ["alpha"]}', ".export-manifest.json exports is not an object"),
        ("", ".export-manifest.json is not valid JSON ("),
        (b"\xff\xfe{}", ".export-manifest.json is not valid JSON ("),
        ("[" * 200000, ".export-manifest.json is not valid JSON ("),
    ])
    def test_a_manifest_of_another_shape_is_a_parse_error(self, tmp_path: Path, manifest, error) -> None:
        _make_skill(tmp_path / "ra" / "active", "ra", metadata={"name": "ra", "exports": ["r"]})
        _write_manifest(tmp_path, manifest)
        result = mod.compute_candidates(tmp_path)
        assert result["candidate_source"] == "active-links"
        assert result["manifest_parse_error"].startswith(error), result["manifest_parse_error"]
        assert _gate(result) == (["ra"], [])

    def test_a_manifest_folder_is_an_unreadable_manifest(self, tmp_path: Path) -> None:
        (tmp_path / ".export-manifest.json").mkdir()
        result = mod.compute_candidates(tmp_path)
        assert result["manifest_parse_error"].startswith(".export-manifest.json cannot be read (")

    def test_a_manifest_key_that_names_no_folder_is_stale(self, tmp_path: Path) -> None:
        root = tmp_path / "skills"
        _make_skill(root, "alpha", metadata={"name": "alpha", "exports": ["a"]})
        _write(root / "file.txt", "not a folder")
        _write(tmp_path / "escape" / "SKILL.md", "# outside the skills folder\n")
        _write_manifest(root, {name: {} for name in ("alpha", "../escape", "", "a/b", "file.txt", "gone")})
        result = mod.compute_candidates(root)
        assert _gate(result) == (["alpha"], [])
        assert result["stale_manifest_keys"] == ["", "../escape", "a/b", "file.txt", "gone"]

    def test_an_explicit_name_that_is_a_path_is_no_such_folder(self, tmp_path: Path) -> None:
        root = tmp_path / "skills"
        _make_skill(root, "alpha", metadata={"name": "alpha", "exports": ["a"]})
        _make_skill(tmp_path, "outside", metadata={"name": "outside", "exports": ["o"]})
        result = mod.compute_candidates(root, ["../outside", "alpha/.."])
        assert _gate(result) == ([], [("../outside", "no-such-folder"), ("alpha/..", "no-such-folder")])

    def test_candidates_sort_by_name_on_every_platform(self, tmp_path: Path) -> None:
        # A Path sorts without case on Windows; the gate orders names as
        # strings everywhere, so upper case comes first.
        for name in ("alpha", "Zed"):
            _write(tmp_path / name / "active" / name / "SKILL.md", "# a module skill\n")
        result = mod.compute_candidates(tmp_path)
        assert [x["skill_dir"] for x in result["excluded"]] == ["Zed", "alpha"]
        explicit = mod.compute_candidates(tmp_path, ["gamma", "Beta", "gamma"])
        assert [x["skill_dir"] for x in explicit["excluded"]] == ["Beta", "gamma"]

    def test_a_composes_cycle_is_not_an_exclusion(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "a", metadata={"name": "a", "exports": ["a"], "composes": ["b"]})
        _make_skill(tmp_path, "b", metadata={"name": "b", "exports": ["b"], "composes": ["a"]})
        result = mod.compute_candidates(tmp_path, ["a", "b"])
        assert _gate(result) == (["a", "b"], [])
        assert result["cycles"] == ["a"]

    def test_a_top_level_link_is_not_skf_output(self, tmp_path: Path) -> None:
        root = tmp_path / "skills"
        _make_skill(tmp_path / "elsewhere", "linked", metadata={"name": "linked", "exports": ["l"]})
        _symlink(tmp_path / "elsewhere" / "linked", root / "linked")
        result = mod.compute_candidates(root, ["linked"])
        assert _gate(result) == ([], [("linked", "not-skf-output")])

    @pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="needs POSIX permissions that deny this user")
    def test_a_folder_skf_cannot_read_is_not_a_stale_key(self, tmp_path: Path) -> None:
        root = tmp_path / "skills"
        _make_skill(root, "alpha", metadata={"name": "alpha", "exports": ["a"]})
        locked = tmp_path / "locked"
        _write(locked / "hidden" / "SKILL.md", "# behind a folder SKF cannot search\n")
        _symlink(locked / "hidden", root / "hidden")
        _write_manifest(root, {"alpha": {}, "hidden": {}})
        locked.chmod(0)
        try:
            result = mod.compute_candidates(root)
        finally:
            locked.chmod(0o755)
        assert result["stale_manifest_keys"] == []
        assert _gate(result) == (["alpha"], [("hidden", "no-skf-package")])

    def test_cli_candidates(self, tmp_path: Path) -> None:
        _stack_folder(tmp_path)
        result = _run_cli("candidates", str(tmp_path), "--explicit", " beta , beta,alpha,,app-stack ")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert set(payload) == CANDIDATE_KEYS
        assert payload["candidate_source"] == "explicit"
        assert _gate(payload) == (["alpha", "beta"], [("app-stack", "not-a-skill")])

    def test_cli_candidates_reads_the_manifest(self, tmp_path: Path) -> None:
        _stack_folder(tmp_path)
        _write_manifest(tmp_path, {"beta": {}, "gone": {}})
        payload = json.loads(_run_cli("candidates", str(tmp_path)).stdout)
        assert payload["candidate_source"] == "manifest"
        assert _gate(payload) == (["beta"], [])
        assert payload["stale_manifest_keys"] == ["gone"]

    def test_cli_explicit_list_naming_no_skill_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("candidates", str(tmp_path), "--explicit", " , ")
        assert result.returncode == 1
        assert "--explicit names no skill" in result.stderr
        assert result.stdout == ""

    def test_cli_candidates_bad_root_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("candidates", str(tmp_path / "does-not-exist"))
        assert result.returncode == 1
        assert "skills root" in result.stderr

    def test_docstring_says_which_subcommand_reads_the_export_manifest(self) -> None:
        doc = mod.__doc__
        assert "The export manifest is never read." not in doc
        assert "`enumerate` never reads the export manifest" in doc
        assert "candidates <skills-root> [--explicit a,b]" in doc
