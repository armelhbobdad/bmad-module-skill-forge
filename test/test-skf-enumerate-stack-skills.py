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
  - Symlink fallback when target unreadable (warning, no crash)
  - CLI subprocess invocation produces valid JSON
  - Empty skills root → empty inventory, exit 0
  - Bad skills root → exit 1
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


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
) -> Path:
    """Create a skill package under `root` with optional artifacts.

    `metadata` is dumped as metadata.json verbatim (None → no file).
    `references` maps file name → markdown content (None → no dir).
    """
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if skill_md is not None:
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
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


def _expected_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


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
        assert result == {"skills": [], "cycles": [], "warnings": []}

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
        _make_skill(
            tmp_path,
            "b-refs",
            metadata=None,
            references={"x.md": "## API\n- r1\n- r2\n"},
        )
        _make_skill(
            tmp_path,
            "c-prose",
            skill_md="# c\n## API Surface\n- p1\n",
            metadata=None,
        )
        _make_skill(
            tmp_path,
            "d-none",
            skill_md="# d\n",
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

    def test_broken_symlink_warns_no_crash(self, tmp_path: Path) -> None:
        # Create a real skill, then point a symlink at a missing dir.
        _make_skill(
            tmp_path,
            "real",
            metadata={"name": "real", "exports": ["x"]},
        )
        missing = tmp_path / "_does_not_exist"
        link = tmp_path / "broken-link"
        try:
            os.symlink(missing, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            import pytest
            pytest.skip("symlinks not supported on this platform")
        result = mod.enumerate_stack_skills(tmp_path)
        names = [s["name"] for s in result["skills"]]
        assert "real" in names
        assert "broken-link" not in names
        assert any("broken-link" in w and "symlink" in w for w in result["warnings"])

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
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
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
        assert payload == {"skills": [], "cycles": [], "warnings": []}

    def test_enumerate_bad_root_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("enumerate", str(tmp_path / "does-not-exist"))
        assert result.returncode == 1
        assert "skills root" in result.stderr

    def test_enumerate_missing_subcommand_exits_2(self) -> None:
        # argparse `required=True` on subparsers → returncode 2 on missing arg.
        result = _run_cli()
        assert result.returncode != 0
