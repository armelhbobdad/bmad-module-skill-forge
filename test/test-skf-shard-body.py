#!/usr/bin/env python3
"""Tests for skf-shard-body.py.

Covers the deterministic auto-shard mechanic that replaces the in-prompt
line-counting / boundary-detection / size-sort / file-write / blockquote
surgery in skf-create-skill's step-auto-shard.md §1–§5 and validate.md §4:

  - largest-first extraction stops the moment the body fits under budget,
    reference files carry kebab names + preserved headings, SKILL.md gains
    blockquote xrefs, and the JSON reports correct before/after counts with
    tier1_preserved / xref_ok true
  - a body already under budget -> action:"skip", zero files written
  - a body whose Tier-2 sections cannot fit under budget -> under_budget:false
  - --dry-run reports the same plan with no filesystem mutation
  - the Tier-1 preservation guard flags a pulled Tier-1 heading
  - frontmatter is never modified; writes route through skf-atomic-write.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-shard-body.py"

spec = importlib.util.spec_from_file_location("skf_shard_body", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------


FRONTMATTER = "---\nname: demo-skill\ndescription: A demo skill for tests.\n---\n"


def _section(heading: str, body_lines: int) -> str:
    """A markdown section: `## <heading>` plus `body_lines` filler lines."""
    filler = "\n".join(f"line {i} of {heading}" for i in range(body_lines))
    return f"## {heading}\n{filler}\n"


def _tier1(heading: str, body_lines: int = 3) -> str:
    return _section(heading, body_lines)


def _run(skill_md: Path, *extra: str) -> dict:
    """Invoke the script as a subprocess, return parsed JSON."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(skill_md), *extra],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"exit {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# (1) Largest-first extraction stops the moment the body fits
# --------------------------------------------------------------------------


class TestSelectiveExtraction:
    def _build(self, tmp_path: Path) -> Path:
        # Tier-1 sections (small, must stay inline) + three Tier-2 `## Full`
        # sections of known, distinct sizes. Total body ~450 lines > 400.
        body = (
            _tier1("Overview", 4)
            + _tier1("Quick Start", 4)
            + _tier1("Key API Summary", 4)
            + _section("Full API Reference", 200)  # largest
            + _section("Full Type Definitions", 120)  # middle
            + _section("Full Integration Patterns", 90)  # smallest
        )
        return _write(tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body)

    def test_extracts_largest_first_until_under_budget(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "shard"
        assert result["body_lines_before"] > 400
        assert result["body_lines_after"] <= 400
        assert result["under_budget"] is True
        assert result["tier1_preserved"] is True
        assert result["tier1_missing"] == []
        assert result["xref_ok"] is True

        headings = [s["heading"] for s in result["sections_extracted"]]
        # Largest first, and it should stop before pulling every section:
        # 450 - 200 = 250-ish after just the first extraction is already < 400.
        assert headings[0] == "Full API Reference"
        assert "Full Integration Patterns" not in headings

    def test_reference_files_written_with_kebab_names(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "400")

        for entry in result["sections_extracted"]:
            ref = skill_md.parent / entry["file"]
            assert ref.is_file(), f"{entry['file']} should exist"
            content = ref.read_text(encoding="utf-8")
            assert content.startswith(f"## {entry['heading']}\n")
        # Full API Reference -> references/full-api-reference.md
        assert (skill_md.parent / "references" / "full-api-reference.md").is_file()

    def test_skill_md_carries_blockquote_xrefs(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        result = _run(skill_md, "--budget", "400")

        rewritten = skill_md.read_text(encoding="utf-8")
        for entry in result["sections_extracted"]:
            assert (
                f"> See [{entry['heading']}]({entry['file']})" in rewritten
            ), f"blockquote for {entry['heading']} missing"
        # The extracted section body must no longer be inline.
        assert "line 199 of Full API Reference" not in rewritten

    def test_frontmatter_unmodified(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        _run(skill_md, "--budget", "400")
        rewritten = skill_md.read_text(encoding="utf-8")
        assert rewritten.startswith(FRONTMATTER)

    def test_tier1_sections_remain_inline(self, tmp_path: Path) -> None:
        skill_md = self._build(tmp_path)
        _run(skill_md, "--budget", "400")
        rewritten = skill_md.read_text(encoding="utf-8")
        for name in ("Overview", "Quick Start", "Key API Summary"):
            assert f"## {name}\n" in rewritten


# --------------------------------------------------------------------------
# (2) Already under budget -> skip, zero files written
# --------------------------------------------------------------------------


class TestSkipUnderBudget:
    def test_skip_writes_nothing(self, tmp_path: Path) -> None:
        body = _tier1("Overview", 20) + _section("Full API Reference", 40)
        skill_md = _write(
            tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body
        )
        before = skill_md.read_text(encoding="utf-8")

        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "skip"
        assert result["sections_extracted"] == []
        assert result["body_lines_before"] == result["body_lines_after"]
        assert result["under_budget"] is True
        assert result["tier1_preserved"] is True
        assert result["xref_ok"] is True
        # No mutation, no references/ directory created.
        assert skill_md.read_text(encoding="utf-8") == before
        assert not (skill_md.parent / "references").exists()


# --------------------------------------------------------------------------
# (3) Tier-2 sections cannot fit the body under budget -> under_budget:false
# --------------------------------------------------------------------------


class TestCannotFit:
    def test_under_budget_false_when_tier1_too_large(self, tmp_path: Path) -> None:
        # Tier-1 alone is ~430 lines; extracting every Tier-2 section still
        # leaves the body over budget -> under_budget:false signals the caller
        # to fall to the editing-judgment trim.
        body = (
            _tier1("Overview", 210)
            + _tier1("Architecture at a Glance", 210)
            + _section("Full API Reference", 60)
            + _section("Full Type Definitions", 60)
        )
        skill_md = _write(
            tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body
        )

        result = _run(skill_md, "--budget", "400")

        assert result["action"] == "shard"
        assert result["under_budget"] is False
        # Every Tier-2 section was extracted (maximum possible reduction).
        headings = {s["heading"] for s in result["sections_extracted"]}
        assert headings == {"Full API Reference", "Full Type Definitions"}
        assert result["body_lines_after"] > 400
        # Tier-1 was never pulled despite the overflow.
        assert result["tier1_preserved"] is True


# --------------------------------------------------------------------------
# (4a) --dry-run reports the same plan with no filesystem mutation
# --------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_mutation(self, tmp_path: Path) -> None:
        body = (
            _tier1("Overview", 4)
            + _section("Full API Reference", 300)
            + _section("Full Type Definitions", 150)
        )
        skill_md = _write(
            tmp_path / "demo-skill" / "SKILL.md", FRONTMATTER + "\n" + body
        )
        before = skill_md.read_text(encoding="utf-8")

        result = _run(skill_md, "--budget", "400", "--dry-run")

        assert result["action"] == "shard"
        assert result["dry_run"] is True
        assert result["body_lines_after"] <= 400
        assert result["sections_extracted"][0]["heading"] == "Full API Reference"
        assert result["tier1_preserved"] is True
        assert result["xref_ok"] is True
        # Nothing on disk changed.
        assert skill_md.read_text(encoding="utf-8") == before
        assert not (skill_md.parent / "references").exists()

    def test_dry_run_matches_write_plan(self, tmp_path: Path) -> None:
        body = (
            _tier1("Overview", 4)
            + _section("Full API Reference", 300)
            + _section("Full Type Definitions", 150)
        )
        dry = _write(tmp_path / "a" / "SKILL.md", FRONTMATTER + "\n" + body)
        wet = _write(tmp_path / "b" / "SKILL.md", FRONTMATTER + "\n" + body)

        dry_res = _run(dry, "--budget", "400", "--dry-run")
        wet_res = _run(wet, "--budget", "400")

        # The plan (counts + sections) is identical; only dry_run differs.
        for key in (
            "action",
            "body_lines_before",
            "body_lines_after",
            "sections_extracted",
            "tier1_preserved",
            "under_budget",
        ):
            assert dry_res[key] == wet_res[key], key


# --------------------------------------------------------------------------
# (4b) Tier-1 preservation guard flags a pulled heading
# --------------------------------------------------------------------------


class TestTier1Guard:
    def test_guard_flags_missing_tier1(self) -> None:
        # Direct unit test of the guard: a Tier-1 heading present before but
        # absent after (a hypothetical bad extraction) must be reported.
        before = ["## Overview", "text", "## Full API Reference", "x"]
        after = ["## Full API Reference", "x"]
        tier1_before = mod.present_tier1(before)
        tier1_after = mod.present_tier1(after)
        missing = [
            h
            for h in mod.TIER1_HEADINGS
            if h in tier1_before and h not in tier1_after
        ]
        assert missing == ["Overview"]
        assert bool(missing) is True  # tier1_preserved would be False

    def test_guard_passes_when_only_full_sections_pulled(self) -> None:
        before = ["## Overview", "t", "## Full API Reference", "x"]
        after = ["## Overview", "t", "> See [Full API Reference](references/x.md)"]
        tier1_before = mod.present_tier1(before)
        tier1_after = mod.present_tier1(after)
        missing = [
            h
            for h in mod.TIER1_HEADINGS
            if h in tier1_before and h not in tier1_after
        ]
        assert missing == []


# --------------------------------------------------------------------------
# Unit-level helpers: kebab, section boundaries, counting
# --------------------------------------------------------------------------


class TestHelpers:
    def test_kebab_case(self) -> None:
        assert mod.kebab_case("Full API Reference") == "full-api-reference"
        assert mod.kebab_case("Full Type Definitions") == "full-type-definitions"
        assert (
            mod.kebab_case("Full Integration & Patterns")
            == "full-integration-patterns"
        )

    def test_count_body_excludes_trailing_blanks(self) -> None:
        assert mod.count_body_lines(["a", "b", "", "  ", ""]) == 2
        assert mod.count_body_lines([]) == 0
        assert mod.count_body_lines(["", ""]) == 0

    def test_full_section_boundary_stops_at_next_h2(self) -> None:
        body = [
            "## Full API Reference",
            "a",
            "### nested",
            "b",
            "## Overview",
            "c",
        ]
        secs = mod.find_full_sections(body)
        assert len(secs) == 1
        assert secs[0].heading == "Full API Reference"
        assert secs[0].start == 0
        assert secs[0].end == 4  # nested ### stays inside; stops at ## Overview
        assert secs[0].kebab == "full-api-reference"

    def test_non_full_h2_not_extracted(self) -> None:
        body = ["## Overview", "x", "## Fully Loaded", "y"]
        # "Fully Loaded" does not start with the "Full " token boundary word.
        secs = mod.find_full_sections(body)
        assert secs == []

    def test_split_frontmatter(self) -> None:
        fm, body = mod.split_frontmatter(FRONTMATTER + "\nbody line\n")
        assert fm[0] == "---"
        assert fm[-1] == "---"
        assert "body line" in body
