#!/usr/bin/env python3
"""Tests for skf-scan-skill-md-structure.py.

Covers:
  - required-section presence with canonical headings and synonyms
  - case-insensitive heading match; `##` vs `###` tolerated
  - missing section → satisfied=false + tried[] list
  - fence balance: even → not unbalanced; odd → unbalanced
  - bare opening fence flagged; closing fences never flagged
  - table drift: header has N cols, body row has M ≠ N → flagged
  - escaped pipes (`\\|`) in cells do not inflate column counts
  - separator row ignored
  - empty SKILL.md → graceful empty result for both subcommands
  - subprocess CLI: JSON shape, exit codes, --required-sections flag
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-scan-skill-md-structure.py"

spec = importlib.util.spec_from_file_location("skf_scan_skill_md_structure", SCRIPT_PATH)
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


# --------------------------------------------------------------------------
# Required-section presence
# --------------------------------------------------------------------------


class TestRequiredSections:
    def test_all_canonical_present(self) -> None:
        text = (
            "# Skill\n\n"
            "## Description\nblah\n\n"
            "## Usage\nblah\n\n"
            "## API\nblah\n"
        )
        result = mod.find_required_sections(text)
        assert result["description"]["satisfied"] is True
        assert result["description"]["matched_synonym"] == "Description"
        assert result["usage"]["satisfied"] is True
        assert result["usage"]["matched_synonym"] == "Usage"
        assert result["api_surface"]["satisfied"] is True
        assert result["api_surface"]["matched_synonym"] == "API"

    def test_overview_satisfies_description(self) -> None:
        text = "## Overview\nblah\n## Usage\n## Exports\n"
        result = mod.find_required_sections(text)
        assert result["description"]["satisfied"] is True
        assert result["description"]["matched_synonym"] == "Overview"

    def test_purpose_satisfies_description(self) -> None:
        text = "## Purpose\n## Usage\n## API\n"
        result = mod.find_required_sections(text)
        assert result["description"]["matched_synonym"] == "Purpose"

    def test_examples_satisfies_usage(self) -> None:
        text = "## Description\n## Examples\n## API\n"
        result = mod.find_required_sections(text)
        assert result["usage"]["satisfied"] is True
        assert result["usage"]["matched_synonym"] == "Examples"

    def test_quickstart_satisfies_usage(self) -> None:
        text = "## Description\n## Quickstart\n## API\n"
        result = mod.find_required_sections(text)
        assert result["usage"]["matched_synonym"] == "Quickstart"

    def test_key_api_summary_satisfies_api_surface(self) -> None:
        # SKF-template-specific heading must match as first-class.
        text = "## Description\n## Usage\n## Key API Summary\n"
        result = mod.find_required_sections(text)
        assert result["api_surface"]["satisfied"] is True
        assert result["api_surface"]["matched_synonym"] == "Key API Summary"

    def test_quick_start_satisfies_usage(self) -> None:
        # SKF-template-specific heading (two-word variant).
        text = "## Description\n## Quick Start\n## API\n"
        result = mod.find_required_sections(text)
        assert result["usage"]["matched_synonym"] == "Quick Start"

    def test_common_workflows_satisfies_usage(self) -> None:
        text = "## Description\n## Common Workflows\n## API\n"
        result = mod.find_required_sections(text)
        assert result["usage"]["matched_synonym"] == "Common Workflows"

    def test_usage_patterns_satisfies_usage(self) -> None:
        # quick-skill template heading — full-text match, not a substring of "Usage".
        text = "## Description\n## Usage Patterns\n## API\n"
        result = mod.find_required_sections(text)
        assert result["usage"]["satisfied"] is True
        assert result["usage"]["matched_synonym"] == "Usage Patterns"

    def test_key_exports_satisfies_api_surface(self) -> None:
        # quick-skill template heading — distinct from the bare "Exports" synonym.
        text = "## Description\n## Usage\n## Key Exports\n"
        result = mod.find_required_sections(text)
        assert result["api_surface"]["satisfied"] is True
        assert result["api_surface"]["matched_synonym"] == "Key Exports"

    def test_quick_skill_template_headings_satisfy_all_families(self) -> None:
        # The quick-skill template's literal headings must satisfy every
        # required family so its output passes the structural-scan gate
        # without per-skill heading edits.
        text = (
            "## Overview\nblah\n\n"
            "## Description\nblah\n\n"
            "## Key Exports\nblah\n\n"
            "## Usage Patterns\nblah\n"
        )
        result = mod.find_required_sections(text)
        assert all(
            result[f]["satisfied"] for f in ("description", "usage", "api_surface")
        )

    def test_case_insensitive(self) -> None:
        text = "## description\n## USAGE\n## api\n"
        result = mod.find_required_sections(text)
        # canonical synonym from the constant is reported, not the file's casing
        assert result["description"] == {
            "satisfied": True,
            "matched_synonym": "Description",
            "tried": list(mod.REQUIRED_SYNONYMS["description"]),
        }
        assert result["usage"]["matched_synonym"] == "Usage"
        assert result["api_surface"]["matched_synonym"] == "API"

    def test_h3_tolerated(self) -> None:
        text = "# Top\n### Description\n### Usage\n### API\n"
        result = mod.find_required_sections(text)
        assert all(result[f]["satisfied"] for f in ("description", "usage", "api_surface"))

    def test_h1_tolerated(self) -> None:
        text = "# Description\n# Usage\n# API\n"
        result = mod.find_required_sections(text)
        assert all(result[f]["satisfied"] for f in ("description", "usage", "api_surface"))

    def test_missing_section_returns_tried_list(self) -> None:
        text = "## Description\n## Usage\n"
        result = mod.find_required_sections(text)
        assert result["api_surface"]["satisfied"] is False
        assert result["api_surface"]["matched_synonym"] is None
        # tried list is the full canonical synonyms for the family
        assert result["api_surface"]["tried"] == list(mod.REQUIRED_SYNONYMS["api_surface"])

    def test_all_missing(self) -> None:
        text = "# Just a title\n\nSome prose with no required headings.\n"
        result = mod.find_required_sections(text)
        for family in ("description", "usage", "api_surface"):
            assert result[family]["satisfied"] is False
            assert result[family]["matched_synonym"] is None
            assert result[family]["tried"] == list(mod.REQUIRED_SYNONYMS[family])

    def test_first_match_wins(self) -> None:
        # Two synonyms for the same family — the first encountered wins.
        text = "## Description\n## Overview\n## Usage\n## API\n"
        result = mod.find_required_sections(text)
        assert result["description"]["matched_synonym"] == "Description"

    def test_heading_with_extra_whitespace(self) -> None:
        text = "##    Description   \n##  Usage  \n##  API  \n"
        result = mod.find_required_sections(text)
        assert all(result[f]["satisfied"] for f in ("description", "usage", "api_surface"))

    def test_empty_text(self) -> None:
        result = mod.find_required_sections("")
        for family in ("description", "usage", "api_surface"):
            assert result[family]["satisfied"] is False
            assert result[family]["matched_synonym"] is None

    def test_heading_synonym_not_treated_as_substring(self) -> None:
        # A heading like "## Description of the algorithm" should NOT match
        # the "Description" synonym — the regex anchors on the full heading.
        text = "## Description of the algorithm\n## Usage of foo\n## API for callers\n"
        result = mod.find_required_sections(text)
        for family in ("description", "usage", "api_surface"):
            assert result[family]["satisfied"] is False


# --------------------------------------------------------------------------
# Fence balance and bare opening fences
# --------------------------------------------------------------------------


class TestScanFences:
    def test_balanced_five_pairs(self) -> None:
        # 5 opening + 5 closing = 10 fences, even → not unbalanced
        text = "\n".join(
            ["```bash", "echo 1", "```"] * 5
        )
        fence_count, unbalanced, bare = mod.scan_fences(text)
        assert fence_count == 10
        assert unbalanced is False
        assert bare == []

    def test_odd_count_unbalanced(self) -> None:
        # 5 opening + 4 closing = 9 fences, odd → unbalanced
        text = "```bash\necho 1\n```\n" * 4 + "```bash\necho missing close\n"
        fence_count, unbalanced, bare = mod.scan_fences(text)
        assert fence_count == 9
        assert unbalanced is True

    def test_bare_opening_fence_flagged(self) -> None:
        text = "Intro\n\n```\nsome code\n```\n"
        fence_count, unbalanced, bare = mod.scan_fences(text)
        assert fence_count == 2
        assert unbalanced is False
        assert len(bare) == 1
        assert bare[0]["line"] == 3
        assert bare[0]["text"] == "```"

    def test_closing_fence_never_flagged(self) -> None:
        # Both opening fences carry a language tag; closing fences are
        # bare by convention but must NOT appear in bare_opening_fences.
        text = "```python\nprint(1)\n```\n\n```bash\necho hi\n```\n"
        _, _, bare = mod.scan_fences(text)
        assert bare == []

    def test_multiple_bare_openings(self) -> None:
        text = (
            "```\nblock1\n```\n"
            "\n"
            "```\nblock2\n```\n"
        )
        fence_count, unbalanced, bare = mod.scan_fences(text)
        assert fence_count == 4
        assert unbalanced is False
        # both openings (lines 1 and 5) are bare
        bare_lines = sorted(b["line"] for b in bare)
        assert bare_lines == [1, 5]

    def test_no_fences(self) -> None:
        fence_count, unbalanced, bare = mod.scan_fences("Just prose.\nMore prose.\n")
        assert fence_count == 0
        assert unbalanced is False
        assert bare == []

    def test_mixed_tagged_and_bare(self) -> None:
        text = (
            "```python\nx = 1\n```\n"
            "\n"
            "```\nbare opening\n```\n"
        )
        _, _, bare = mod.scan_fences(text)
        assert [b["line"] for b in bare] == [5]


# --------------------------------------------------------------------------
# Table drift
# --------------------------------------------------------------------------


class TestTableDrift:
    def test_aligned_table_no_drift(self) -> None:
        text = (
            "## Schema\n\n"
            "| col1 | col2 | col3 |\n"
            "| --- | --- | --- |\n"
            "| a | b | c |\n"
            "| d | e | f |\n"
        )
        drift = mod.find_table_drift(text)
        assert drift == []

    def test_drift_flagged(self) -> None:
        # header has 4 cols, last row has 3
        text = (
            "## Schema\n\n"
            "| a | b | c | d |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | 2 | 3 | 4 |\n"
            "| 5 | 6 | 7 |\n"
        )
        drift = mod.find_table_drift(text)
        assert len(drift) == 1
        f = drift[0]
        assert f["expected_cols"] == 4
        assert f["actual_cols"] == 3
        assert f["section"] == "Schema"
        # 1-based line number for the drifting row
        assert f["line"] == 6
        assert "5 | 6 | 7" in f["row"]

    def test_escaped_pipes_not_counted_as_separators(self) -> None:
        # Cell contains `string \| undefined`. Without normalization this
        # would inflate the column count and produce a false drift finding.
        text = (
            "## Types\n\n"
            "| name | type |\n"
            "| --- | --- |\n"
            "| foo | string \\| undefined |\n"
            "| bar | number |\n"
        )
        drift = mod.find_table_drift(text)
        assert drift == []

    def test_separator_row_not_flagged_against_itself(self) -> None:
        # The separator row's column count is the same as the header's, so
        # it would not be flagged anyway, but the test asserts we skip it
        # so the drift count reflects body rows alone.
        text = (
            "## T\n\n"
            "| a | b |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
        )
        drift = mod.find_table_drift(text)
        assert drift == []

    def test_section_tracking(self) -> None:
        text = (
            "## First\n\n"
            "| h1 | h2 |\n"
            "| --- | --- |\n"
            "| a | b |\n"
            "\n"
            "## Second\n\n"
            "| x | y | z |\n"
            "| --- | --- | --- |\n"
            "| 1 | 2 |\n"
        )
        drift = mod.find_table_drift(text)
        assert len(drift) == 1
        assert drift[0]["section"] == "Second"
        assert drift[0]["expected_cols"] == 3
        assert drift[0]["actual_cols"] == 2

    def test_multiple_drift_rows(self) -> None:
        text = (
            "| a | b | c |\n"
            "| --- | --- | --- |\n"
            "| 1 | 2 |\n"        # 2 cols
            "| 3 | 4 | 5 | 6 |\n" # 4 cols
        )
        drift = mod.find_table_drift(text)
        assert len(drift) == 2
        assert {d["actual_cols"] for d in drift} == {2, 4}

    def test_no_tables(self) -> None:
        assert mod.find_table_drift("# Title\n\nSome prose only.\n") == []


# --------------------------------------------------------------------------
# Combined scan + empty-file edge case
# --------------------------------------------------------------------------


class TestScanCombined:
    def test_empty_skill_md_required_sections(self, tmp_path: Path) -> None:
        skill = _write(tmp_path / "SKILL.md", "")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "scan", str(skill), "--required-sections"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        for family in ("description", "usage", "api_surface"):
            assert payload[family]["satisfied"] is False
            assert payload[family]["matched_synonym"] is None

    def test_empty_skill_md_default_scan(self, tmp_path: Path) -> None:
        skill = _write(tmp_path / "SKILL.md", "")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "scan", str(skill)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload == {
            "unbalanced_fences": False,
            "fence_count": 0,
            "bare_opening_fences": [],
            "table_drift": [],
        }


# --------------------------------------------------------------------------
# Subprocess CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_scan_emits_json(self, tmp_path: Path) -> None:
        text = (
            "## Description\nblah\n\n"
            "```bash\necho hi\n```\n\n"
            "## Usage\n## API\n"
        )
        skill = _write(tmp_path / "SKILL.md", text)
        result = _run_cli("scan", str(skill))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["fence_count"] == 2
        assert payload["unbalanced_fences"] is False
        assert payload["bare_opening_fences"] == []
        assert payload["table_drift"] == []

    def test_scan_required_sections_emits_json(self, tmp_path: Path) -> None:
        skill = _write(
            tmp_path / "SKILL.md",
            "## Overview\nx\n## Examples\ny\n## Exports\nz\n",
        )
        result = _run_cli("scan", str(skill), "--required-sections")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["description"]["matched_synonym"] == "Overview"
        assert payload["usage"]["matched_synonym"] == "Examples"
        assert payload["api_surface"]["matched_synonym"] == "Exports"

    def test_scan_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("scan", str(tmp_path / "nope.md"))
        assert result.returncode == 1
        assert "file not found" in result.stderr

    def test_scan_required_sections_unsatisfied(self, tmp_path: Path) -> None:
        skill = _write(tmp_path / "SKILL.md", "## Description\n## Usage\n")
        result = _run_cli("scan", str(skill), "--required-sections")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["api_surface"]["satisfied"] is False
        assert payload["api_surface"]["matched_synonym"] is None
        # tried list is included even when nothing matched
        assert isinstance(payload["api_surface"]["tried"], list)
        assert "API" in payload["api_surface"]["tried"]

    def test_scan_unbalanced_fence_via_cli(self, tmp_path: Path) -> None:
        skill = _write(
            tmp_path / "SKILL.md",
            "```bash\necho hi\n```\n\n```python\nprint(1)\n",
        )
        result = _run_cli("scan", str(skill))
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["unbalanced_fences"] is True
        assert payload["fence_count"] == 3

    def test_scan_bare_opening_fence_via_cli(self, tmp_path: Path) -> None:
        skill = _write(tmp_path / "SKILL.md", "intro\n\n```\nx\n```\n")
        result = _run_cli("scan", str(skill))
        payload = json.loads(result.stdout)
        assert len(payload["bare_opening_fences"]) == 1
        assert payload["bare_opening_fences"][0]["line"] == 3

    def test_scan_table_drift_via_cli(self, tmp_path: Path) -> None:
        skill = _write(
            tmp_path / "SKILL.md",
            (
                "## Schema\n\n"
                "| a | b | c | d |\n"
                "| --- | --- | --- | --- |\n"
                "| 1 | 2 | 3 |\n"
            ),
        )
        result = _run_cli("scan", str(skill))
        payload = json.loads(result.stdout)
        assert len(payload["table_drift"]) == 1
        assert payload["table_drift"][0]["expected_cols"] == 4
        assert payload["table_drift"][0]["actual_cols"] == 3
        assert payload["table_drift"][0]["section"] == "Schema"
