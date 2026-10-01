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
  - line model: grep-compatible line numbers (a lone `\\r` and a byte
    order mark included), backtick and tilde fences, CommonMark ATX
    headings outside the frontmatter and fenced code
  - usage-scope: the single-body scope (the first usage section, so a
    quick skill's Key Exports list does not count as use) and the
    split-body scope (usage-family sections plus references/**/*.md),
    --body, exports named `$state` and `a.b` counted as fixed strings,
    identifier boundaries, --kinds, the accepted --exports shapes
  - cross-reference: case-insensitive name and alias citations that
    `react-dom` and `preact` do not satisfy, every citing line with a
    count, a common-word first hit ahead of the real citation, --pairs,
    the enumerate inventory as input (its source basenames as aliases,
    unless two skills hold one), edges piped into skf-find-cycles.py, a
    --skills-root that is not a directory
  - reference-check: links (balanced parentheses, escapes and entities
    resolved), reference definitions and folder mentions; fenced code,
    URLs, provenance citations and placeholders skipped; ok / missing /
    escapes against the skill, source and skills roots, symlink escapes,
    the Scripts & Assets section rule, roots that are not directories
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-scan-skill-md-structure.py"
FIND_CYCLES_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-find-cycles.py"
ENUMERATE_PATH = (
    REPO_ROOT / "src" / "shared" / "scripts" / "skf-enumerate-stack-skills.py"
)

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

    def test_pattern_surface_satisfies_api_surface(self) -> None:
        # reference-app assembly override — "Pattern Surface" replaces
        # "Key API Summary" for Section 4 and must satisfy api_surface.
        text = "## Description\n## Adoption Steps\n## Pattern Surface\n"
        result = mod.find_required_sections(text)
        assert result["api_surface"]["satisfied"] is True
        assert result["api_surface"]["matched_synonym"] == "Pattern Surface"

    def test_adoption_steps_satisfies_usage(self) -> None:
        # reference-app assembly override — "Adoption Steps" replaces
        # "Common Workflows" for Section 3 and must satisfy usage.
        text = "## Description\n## Adoption Steps\n## Pattern Surface\n"
        result = mod.find_required_sections(text)
        assert result["usage"]["satisfied"] is True
        assert result["usage"]["matched_synonym"] == "Adoption Steps"

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


def _run_cli_input(stdin: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _line_of(text: str, needle: str) -> int:
    """1-based number of the only line holding `needle`."""
    hits = [n for n, line in enumerate(text.split("\n"), start=1) if needle in line]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def _symlinks_supported(tmp: Path) -> bool:
    probe = tmp / "symlink-probe"
    try:
        probe.symlink_to(tmp)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


# --------------------------------------------------------------------------
# Line model shared by usage-scope, cross-reference and reference-check
# --------------------------------------------------------------------------


class TestLineModel:
    def test_split_lines_breaks_on_newlines_only(self) -> None:
        # A U+2028, a form feed or a lone `\r` stays inside its line, as
        # `grep -n` counts; `\r\n` ends a line.
        text = "a\u2028b\r\nc\x0cd\ne\rf\n"
        assert mod._split_lines(text) == ["a\u2028b", "c\x0cd", "e\rf"]

    def test_split_lines_empty(self) -> None:
        assert mod._split_lines("") == []

    def test_frontmatter_end(self) -> None:
        lines = ["---", "name: x", "---", "# Title"]
        assert mod._frontmatter_end(lines) == 3
        assert mod._frontmatter_end(["# Title", "---"]) == 0
        # an unclosed block is not frontmatter
        assert mod._frontmatter_end(["---", "name: x"]) == 0

    def test_code_lines_tilde_and_longer_fences(self) -> None:
        lines = [
            "~~~",      # opens a tilde fence
            "```",      # inside: another character does not close it
            "code",
            "~~~",      # closes
            "text",
            "````md",   # opens a four-backtick fence
            "```",      # shorter: does not close
            "````",     # closes
            "```x``` is inline code",  # a backtick in the info string
        ]
        assert mod._code_lines(lines) == [
            True, True, True, True, False, True, True, True, False,
        ]

    def test_unclosed_fence_runs_to_end(self) -> None:
        assert mod._code_lines(["a", "```py", "b", "c"]) == [
            False, True, True, True,
        ]

    def test_section_spans_stop_at_same_or_higher_level(self) -> None:
        lines = [
            "# Top",        # 0
            "## Usage",     # 1
            "### Sub",      # 2
            "text",         # 3
            "## Next",      # 4
            "### Usage",    # 5
            "#### Deeper",  # 6
            "### Sibling",  # 7
        ]
        headings = mod._body_headings(lines, 0, [False] * len(lines))
        spans = mod._section_spans(
            headings, len(lines), lambda t: t == "Usage"
        )
        assert spans == [(1, 4, "Usage"), (5, 7, "Usage")]

    def test_body_headings_follow_commonmark_atx(self) -> None:
        lines = [
            "   ## Usage ##",       # 0: three spaces, closing sequence
            "    ## indented code",  # four spaces: not a heading
            "\t# tab indent",       # a tab is four columns: not a heading
            "####### seven",        # more than six `#`: not a heading
            "#hashtag",             # no space after `#`: not a heading
            "## C#",                # 5: a `#` glued to the text stays
            "##",                   # 6: an empty heading
            "### ###",              # 7: an empty heading, closing only
            "## Usage ## more ##",  # 8: only the last run closes
        ]
        headings = mod._body_headings(lines, 0, [False] * len(lines))
        assert headings == [
            (0, 2, "Usage"),
            (5, 2, "C#"),
            (6, 2, ""),
            (7, 3, ""),
            (8, 2, "Usage ## more"),
        ]


# --------------------------------------------------------------------------
# usage-scope
# --------------------------------------------------------------------------


# Exports named `$state` and `a.b`: a double-quoted `grep -c "$state"` sees
# an empty pattern, and `a.b` as a regex matches `aXb`.
USAGE_SKILL = """\
---
# Usage
description: Uses $state and a.b
---

# demo

## Overview

`$state` and `a.b` in the overview sit outside the usage scope.

## Quick Start

```js
## a code comment, not a heading
let count = $state(0);
const x = a.b(1) + a.b(2);
```

## Key Types

`a.b` in Key Types sits outside the usage scope.

## Common Workflows

x$state, $stated, aXb, a.bc, ca.b, getAll and target are other names.
Call ($state) and read x.a.b once.

### Examples

$state again.
"""

USAGE_REFERENCE = "# API\n\n`$state()` returns a signal.\n"

# The quick-skill template: every export listed under Key Exports, the
# usage patterns after it, and no references/ folder.
QUICK_SKILL = """\
---
name: datefmt
description: Parse and format dates.
---

# datefmt

## Overview

A date library.

## Key Exports

- `parse(text)`: reads a date.
- `format(date)`: writes a date.

## Usage Patterns

```js
const d = parse("2024-01-01");
```
"""


class TestUsageScope:
    def test_scope_sections(self) -> None:
        exports = [{"name": "x", "kind": None}]
        split = mod.usage_scope(USAGE_SKILL, [], exports, body="split")
        # `# Usage` in the frontmatter and `##` inside the fence are not
        # headings, so Quick Start runs to Key Types.
        assert split["scope"] == {
            "body": "split",
            "sections": [
                {"heading": "Quick Start", "line": 12, "end_line": 19},
                {"heading": "Common Workflows", "line": 24, "end_line": 31},
                {"heading": "Examples", "line": 29, "end_line": 31},
            ],
            "reference_files": [],
        }
        # no reference file: single-body, the first usage section alone
        single = mod.usage_scope(USAGE_SKILL, [], exports)
        assert single["scope"] == {
            "body": "single",
            "sections": [
                {"heading": "Quick Start", "line": 12, "end_line": 19},
            ],
            "reference_files": [],
        }

    def test_state_and_dotted_names_count_as_fixed_strings(self) -> None:
        exports = [
            {"name": "$state", "kind": "function"},
            {"name": "a.b", "kind": "method"},
            {"name": "get", "kind": "function"},
        ]
        result = mod.usage_scope(USAGE_SKILL, [], exports, body="split")
        by_name = {e["name"]: e for e in result["exports"]}
        # lines 16, 27 and 31; never x$state or $stated, never the overview
        assert by_name["$state"]["count"] == 3
        assert by_name["$state"]["first_hit"] == {"file": "SKILL.md", "line": 16}
        # line 17 (twice on the line, one count) and x.a.b on line 27;
        # aXb, a.bc and ca.b are other names
        assert by_name["a.b"]["count"] == 2
        assert by_name["a.b"]["first_hit"] == {"file": "SKILL.md", "line": 17}
        # getAll and target do not use `get`
        assert by_name["get"]["count"] == 0
        assert by_name["get"]["first_hit"] is None
        assert result["zero_usage"] == [{"name": "get", "kind": "function"}]

    def test_reference_files_join_the_scope(self) -> None:
        refs = [
            ("references/api.md", USAGE_REFERENCE),
            ("references/nested/deep.md", "Use get() here.\n"),
        ]
        exports = [{"name": "$state", "kind": None}, {"name": "get", "kind": None}]
        result = mod.usage_scope(USAGE_SKILL, refs, exports)
        # a reference file makes the body split
        assert result["scope"]["body"] == "split"
        by_name = {e["name"]: e for e in result["exports"]}
        assert by_name["$state"]["count"] == 4
        assert by_name["get"]["count"] == 1
        assert by_name["get"]["first_hit"] == {
            "file": "references/nested/deep.md",
            "line": 1,
        }
        assert result["zero_usage"] == []
        assert result["scope"]["reference_files"] == [
            "references/api.md",
            "references/nested/deep.md",
        ]

    def test_api_surface_headings_are_in_the_family(self) -> None:
        text = (
            "## Key API Summary\nfetchData\n"
            "## Pattern Surface\nwire()\n"
            "## Key Exports\nuseThing\n"
            "## Key Types\nNotCounted\n"
        )
        exports = [{"name": n, "kind": None} for n in (
            "fetchData", "wire", "useThing", "NotCounted",
        )]
        result = mod.usage_scope(text, [], exports, body="split")
        counts = {e["name"]: e["count"] for e in result["exports"]}
        assert counts == {
            "NotCounted": 0, "fetchData": 1, "useThing": 1, "wire": 1,
        }

    def test_quick_skill_key_exports_list_is_not_use(self) -> None:
        # A quick skill ships no references/, so its body is single and an
        # export that only Key Exports lists is zero-usage.
        exports = [
            {"name": "parse", "kind": "function"},
            {"name": "format", "kind": "function"},
        ]
        result = mod.usage_scope(QUICK_SKILL, [], exports)
        assert result["scope"]["body"] == "single"
        assert result["scope"]["sections"] == [
            {"heading": "Usage Patterns", "line": 17, "end_line": 21},
        ]
        counts = {e["name"]: e["count"] for e in result["exports"]}
        assert counts == {"format": 0, "parse": 1}
        assert result["zero_usage"] == [{"name": "format", "kind": "function"}]
        # split-body counts the Key Exports list as well
        split = mod.usage_scope(QUICK_SKILL, [], exports, body="split")
        assert split["zero_usage"] == []

    def test_single_body_counts_the_first_usage_section_only(self) -> None:
        text = (
            "## Key API Summary\nlisted()\n"
            "## Quick Start\nstart()\n"
            "## Common Workflows\nlater()\n"
        )
        exports = [
            {"name": n, "kind": None} for n in ("listed", "start", "later")
        ]
        refs = [("references/api.md", "later()\n")]
        result = mod.usage_scope(text, refs, exports, body="single")
        assert result["scope"] == {
            "body": "single",
            "sections": [{"heading": "Quick Start", "line": 3, "end_line": 4}],
            "reference_files": [],
        }
        assert result["zero_usage"] == [
            {"name": "later", "kind": None},
            {"name": "listed", "kind": None},
        ]

    def test_single_body_without_a_usage_heading_is_empty(self) -> None:
        result = mod.usage_scope(
            "## Key Exports\nlisted()\n", [], [{"name": "listed", "kind": None}]
        )
        assert result["scope"]["sections"] == []
        assert result["zero_usage"] == [{"name": "listed", "kind": None}]

    def test_unknown_body_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            mod.usage_scope("", [], [], body="both")

    def test_heading_rules_shape_the_section(self) -> None:
        # a closing sequence is not part of the heading text, and a `#`
        # line indented four spaces is code, so it does not end the section
        text = "## Usage ##\n    ## not a heading\nfoo()\n"
        result = mod.usage_scope(text, [], [{"name": "foo", "kind": None}])
        assert result["scope"]["sections"] == [
            {"heading": "Usage", "line": 1, "end_line": 3},
        ]
        assert result["exports"][0]["count"] == 1

    def test_family_matches_heading_text_case_insensitively(self) -> None:
        text = "### USAGE PATTERNS\ncallMe()\n"
        result = mod.usage_scope(text, [], [{"name": "callMe", "kind": None}])
        assert result["exports"][0]["count"] == 1
        assert result["scope"]["sections"][0]["heading"] == "USAGE PATTERNS"

    def test_family_list(self) -> None:
        assert mod.USAGE_FAMILY_HEADINGS == [
            *mod.REQUIRED_SYNONYMS["usage"],
            "Key API Summary",
            "Pattern Surface",
            "Key Exports",
        ]

    def test_case_sensitive_and_leading_symbol_names(self) -> None:
        text = "## Usage\npromise.then(cb)\nfoo()\n"
        exports = [
            {"name": ".then", "kind": "method"},
            {"name": "Foo", "kind": "function"},
        ]
        result = mod.usage_scope(text, [], exports)
        counts = {e["name"]: e["count"] for e in result["exports"]}
        # a name starting with `.` needs no guard on its left
        assert counts == {".then": 1, "Foo": 0}

    def test_kinds_filter_keeps_exports_without_a_kind(self) -> None:
        exports = [
            {"name": "$state", "kind": "function"},
            {"name": "a.b", "kind": "method"},
            {"name": "Signal", "kind": "type"},
            {"name": "untyped", "kind": None},
        ]
        result = mod.usage_scope(
            USAGE_SKILL, [], exports, kinds={"function", "method"}
        )
        assert [e["name"] for e in result["exports"]] == [
            "$state", "a.b", "untyped",
        ]
        assert result["zero_usage"] == [{"name": "untyped", "kind": None}]

    def test_exports_sorted_and_deduplicated(self) -> None:
        exports = [
            {"name": "b", "kind": None},
            {"name": "a", "kind": "function"},
            {"name": "b", "kind": None},
            {"name": "a", "kind": None},
        ]
        result = mod.usage_scope("", [], exports)
        assert [(e["name"], e["kind"]) for e in result["exports"]] == [
            ("a", None), ("a", "function"), ("b", None),
        ]

    def test_empty_skill_md(self) -> None:
        result = mod.usage_scope("", [], [{"name": "x", "kind": None}])
        assert result["scope"]["sections"] == []
        assert result["zero_usage"] == [{"name": "x", "kind": None}]


class TestParseExports:
    def test_accepted_shapes(self) -> None:
        expected = [
            {"name": "a", "kind": None},
            {"name": "b", "kind": "function"},
        ]
        items = ["a", {"name": "b", "kind": "function", "signature": "b()"}]
        assert mod.parse_exports(items) == expected
        assert mod.parse_exports({"exports": items}) == expected
        assert mod.parse_exports(
            {"valid": True, "inventory": {"exports": items}}
        ) == expected

    def test_empty_kind_is_no_kind(self) -> None:
        assert mod.parse_exports([{"name": "a", "kind": ""}]) == [
            {"name": "a", "kind": None}
        ]

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        assert mod.parse_exports([{"name": " a.b ", "kind": " method"}]) == [
            {"name": "a.b", "kind": "method"}
        ]

    @pytest.mark.parametrize(
        "payload",
        [
            {"other": []},
            {"inventory": None},
            [1],
            [{"kind": "function"}],
            [{"name": ""}],
            [{"name": "  "}],
            [{"name": "a", "kind": 3}],
        ],
    )
    def test_rejected_shapes(self, payload) -> None:
        with pytest.raises(mod.UserError):
            mod.parse_exports(payload)


class TestUsageScopeCli:
    def _package(self, tmp_path: Path) -> Path:
        skill = _write(tmp_path / "SKILL.md", USAGE_SKILL)
        _write(tmp_path / "references" / "api.md", USAGE_REFERENCE)
        _write(tmp_path / "references" / "notes.txt", "$state\n")
        return skill

    def test_counts_from_files(self, tmp_path: Path) -> None:
        skill = self._package(tmp_path)
        exports = _write(
            tmp_path / "exports.json",
            json.dumps({"exports": [
                {"name": "$state", "kind": "function"},
                {"name": "a.b", "kind": "method"},
                {"name": "State", "kind": "type"},
            ]}),
        )
        result = _run_cli(
            "usage-scope", str(skill), "--exports", str(exports),
            "--kinds", "function,method",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        # references/notes.txt is not markdown and does not count
        assert [(e["name"], e["count"]) for e in payload["exports"]] == [
            ("$state", 4), ("a.b", 2),
        ]
        assert payload["zero_usage"] == []
        assert payload["scope"]["body"] == "split"
        assert payload["scope"]["reference_files"] == ["references/api.md"]
        assert payload["warnings"] == []

    def test_quick_skill_package_is_single_body(self, tmp_path: Path) -> None:
        skill = _write(tmp_path / "SKILL.md", QUICK_SKILL)
        exports = _write(tmp_path / "exports.json", '["parse", "format"]')
        result = _run_cli("usage-scope", str(skill), "--exports", str(exports))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["scope"]["body"] == "single"
        assert payload["zero_usage"] == [{"name": "format", "kind": None}]
        # --body split counts the Key Exports list too
        result = _run_cli(
            "usage-scope", str(skill), "--exports", str(exports),
            "--body", "split",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["scope"]["body"] == "split"
        assert payload["zero_usage"] == []

    def test_body_single_reads_no_reference_file(self, tmp_path: Path) -> None:
        # the caller's judgment that the `## Full*` sections carry real
        # content makes a package with references/ single-body
        skill = self._package(tmp_path)
        exports = _write(tmp_path / "e.json", '["$state"]')
        result = _run_cli(
            "usage-scope", str(skill), "--exports", str(exports),
            "--body", "single",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["scope"]["body"] == "single"
        assert payload["scope"]["reference_files"] == []
        # line 16 in Quick Start; references/api.md is not read
        assert payload["exports"][0]["count"] == 1

    def test_unknown_body_exits_2(self, tmp_path: Path) -> None:
        skill = self._package(tmp_path)
        exports = _write(tmp_path / "e.json", "[]")
        result = _run_cli(
            "usage-scope", str(skill), "--exports", str(exports),
            "--body", "both",
        )
        assert result.returncode == 2
        assert "--body" in result.stderr

    def test_lone_carriage_return_keeps_grep_line_numbers(
        self, tmp_path: Path
    ) -> None:
        # `grep -n` ends a line at `\n` alone; read as universal newlines,
        # `old\rstyle` would be two lines and `foo()` line 4
        skill = tmp_path / "SKILL.md"
        skill.write_bytes(b"## Usage\r\nold\rstyle\nfoo()\n")
        exports = _write(tmp_path / "e.json", '["foo"]')
        result = _run_cli("usage-scope", str(skill), "--exports", str(exports))
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["exports"][0]["first_hit"] == {
            "file": "SKILL.md", "line": 3,
        }

    def test_exports_from_stdin(self, tmp_path: Path) -> None:
        skill = self._package(tmp_path)
        result = _run_cli_input(
            '["$state", "missingFn"]',
            "usage-scope", str(skill), "--exports", "-",
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["zero_usage"] == [{"name": "missingFn", "kind": None}]

    def test_missing_skill_md_exits_1(self, tmp_path: Path) -> None:
        exports = _write(tmp_path / "e.json", "[]")
        result = _run_cli(
            "usage-scope", str(tmp_path / "nope.md"), "--exports", str(exports)
        )
        assert result.returncode == 1
        assert "file not found" in result.stderr

    def test_malformed_exports_exit_1(self, tmp_path: Path) -> None:
        skill = self._package(tmp_path)
        bad = _write(tmp_path / "e.json", "{not json")
        result = _run_cli("usage-scope", str(skill), "--exports", str(bad))
        assert result.returncode == 1
        assert "malformed JSON" in result.stderr

    def test_empty_kinds_exit_1(self, tmp_path: Path) -> None:
        skill = self._package(tmp_path)
        exports = _write(tmp_path / "e.json", "[]")
        result = _run_cli(
            "usage-scope", str(skill), "--exports", str(exports), "--kinds", ","
        )
        assert result.returncode == 1
        assert "--kinds" in result.stderr


# --------------------------------------------------------------------------
# cross-reference
# --------------------------------------------------------------------------


REACT_SKILL = """\
---
name: react
description: Components and hooks.
---
# react

Build a UI from components.
"""

REACT_DOM_SKILL = """\
---
name: react-dom
description: DOM renderer.
---
# react-dom

Render with `createRoot` from 'react-dom/client'.
Needs React 18 or later.
Peer dependency: react.
"""

REDUX_SKILL = """\
---
name: redux
description: A reactive store that preact apps use too.
---
# redux

Pairs with the react-dom bindings.
"""

APP_SKILL = """\
---
name: app
description: The app shell.
---
# app

```ts
import { useQuery } from '@tanstack/react-query';
```
"""


def _skill(name: str, text: str | None, *aliases: str) -> dict:
    return {"name": name, "terms": [name, *aliases], "text": text}


class TestCrossReferences:
    def _skills(self) -> list[dict]:
        return [
            _skill("react", REACT_SKILL),
            _skill("react-dom", REACT_DOM_SKILL),
            _skill("redux", REDUX_SKILL),
            _skill("app", APP_SKILL),
            _skill("tanstack-query", "# tanstack-query\n", "@tanstack/react-query"),
        ]

    def test_citations_edges_and_boundaries(self) -> None:
        result = mod.cross_references(self._skills())
        tanstack = {
            "line": 8,
            "substring": "@tanstack/react-query",
            "excerpt": "import { useQuery } from '@tanstack/react-query';",
        }
        needs_react = {
            "line": 8,
            "substring": "React",
            "excerpt": "Needs React 18 or later.",
        }
        peer_react = {
            "line": 9,
            "substring": "react",
            "excerpt": "Peer dependency: react.",
        }
        bindings = {
            "line": 7,
            "substring": "react-dom",
            "excerpt": "Pairs with the react-dom bindings.",
        }
        assert result["citations"] == [
            {
                "from": "app",
                "to": "tanstack-query",
                **tanstack,
                "count": 1,
                "hits": [tanstack],
            },
            {
                # `react-dom` on lines 2, 5 and 7 is not `react`
                "from": "react-dom",
                "to": "react",
                **needs_react,
                "count": 2,
                "hits": [needs_react, peer_react],
            },
            {
                # `reactive` and `preact` are not `react`; `react-dom` is
                # a name of its own
                "from": "redux",
                "to": "react-dom",
                **bindings,
                "count": 1,
                "hits": [bindings],
            },
        ]
        assert result["edges"] == [
            ["app", "tanstack-query"],
            ["react-dom", "react"],
            ["redux", "react-dom"],
        ]
        assert "pairs" not in result
        assert result["warnings"] == []

    def test_a_skill_never_cites_itself(self) -> None:
        result = mod.cross_references([_skill("react", REACT_SKILL)])
        assert result["citations"] == []

    def test_longest_term_wins_at_the_same_place(self) -> None:
        skills = [
            _skill("next", None, "next.js"),
            _skill("site", "Built on Next.js 14.\n"),
        ]
        citation = mod.cross_references(skills)["citations"][0]
        assert citation["substring"] == "Next.js"

    def test_unreadable_skill_can_still_be_cited(self) -> None:
        skills = [_skill("react", None), _skill("react-dom", REACT_DOM_SKILL)]
        result = mod.cross_references(skills)
        assert result["edges"] == [["react-dom", "react"]]

    def test_excerpt_is_cut_around_the_match(self) -> None:
        line = "x" * 100 + " react " + "y" * 100
        skills = [_skill("react", None), _skill("doc", line + "\n")]
        excerpt = mod.cross_references(skills)["citations"][0]["excerpt"]
        assert excerpt.startswith("...")
        assert excerpt.endswith("...")
        assert " react " in excerpt
        assert len(excerpt) < len(line)

    def test_excerpt_spans_every_match_on_the_line(self) -> None:
        line = "react " + "x" * 100 + " react " + "y" * 100
        skills = [_skill("react", None), _skill("doc", line + "\n")]
        excerpt = mod.cross_references(skills)["citations"][0]["excerpt"]
        assert excerpt.startswith("react x")
        # the second match, 100 characters past the first, still shows
        assert " react y" in excerpt
        assert excerpt.endswith("...")

    def test_a_common_word_first_hit_keeps_the_later_citation(self) -> None:
        # The first hits are prose, not citations: `the next step` and a
        # frontmatter `sending requests`. The citations come later, and
        # `hits` carries them so the caller can quote them.
        app = (
            "---\n"
            "name: app\n"
            "description: An HTTP client for sending requests.\n"
            "---\n"
            "In the next step, wire the store.\n"
            "\n"
            "Next.js 14 (App Router) replaces the `requests` library.\n"
        )
        skills = [
            _skill("app", app),
            _skill("next", None, "next.js"),
            _skill("requests", None),
        ]
        citations = mod.cross_references(skills)["citations"]
        by_target = {c["to"]: c for c in citations}
        assert by_target["next"]["hits"] == [
            {
                "line": 5,
                "substring": "next",
                "excerpt": "In the next step, wire the store.",
            },
            {
                "line": 7,
                "substring": "Next.js",
                "excerpt": (
                    "Next.js 14 (App Router) replaces the `requests` library."
                ),
            },
        ]
        assert [(h["line"], h["substring"])
                for h in by_target["requests"]["hits"]] == [
            (3, "requests"), (7, "requests"),
        ]
        # the top-level fields repeat the first hit
        assert (by_target["next"]["line"], by_target["next"]["count"]) == (5, 2)

    def test_pairs_limit_the_citations(self) -> None:
        pairs = [("react", "react-dom"), ("redux", "react")]
        result = mod.cross_references(self._skills(), pairs)
        # redux -> react-dom is not one of the pairs
        assert result["edges"] == [["react-dom", "react"]]
        assert result["pairs"] == [
            {
                "library_a": "react",
                "library_b": "react-dom",
                "a_cites_b": False,
                "b_cites_a": True,
                "cited": True,
            },
            {
                "library_a": "redux",
                "library_b": "react",
                "a_cites_b": False,
                "b_cites_a": False,
                "cited": False,
            },
        ]

    def test_pair_naming_an_unknown_skill_warns(self) -> None:
        result = mod.cross_references(self._skills(), [("react", "vue")])
        assert result["pairs"][0]["cited"] is False
        assert result["warnings"] == ["vue: named in --pairs but not in --skills"]


class TestParseCrossReferenceInputs:
    def test_skill_entries(self) -> None:
        entries = mod.parse_skill_entries({"skills": [
            {"name": "react", "path": "react/active/react", "exports": []},
            {"name": "tq", "skill_md": "/abs/SKILL.md",
             "aliases": ["TQ", "@tanstack/react-query"]},
        ]})
        assert entries[0]["file"] == os.path.join("react/active/react", "SKILL.md")
        assert entries[0]["terms"] == ["react"]
        # `TQ` repeats the name in another case
        assert entries[1] == {
            "name": "tq",
            "file": "/abs/SKILL.md",
            "terms": ["tq", "@tanstack/react-query"],
        }

    def test_source_basenames_are_aliases_unless_shared(self) -> None:
        # An inventory entry names the repository and the folder its skill
        # was built from. A basename only one skill holds is an alias; one
        # another skill also holds, as its name or a basename, is not.
        entries = mod.parse_skill_entries({"skills": [
            {"name": "oms-cognee", "path": "oms-cognee",
             "source_repo_basename": "cognee", "source_root_basename": "cognee"},
            {"name": "surrealdb", "path": "surrealdb",
             "source_repo_basename": "surrealdb",
             "source_root_basename": "surrealdb-v3.0.5"},
            {"name": "surrealql", "path": "surrealql",
             "source_repo_basename": "surrealdb", "source_root_basename": None},
            {"name": "tauri-updater", "path": "tauri-updater",
             "source_repo_basename": "plugins-workspace",
             "source_root_basename": "updater"},
            {"name": "tauri-auth-plugins", "path": "tauri-auth-plugins",
             "source_repo_basename": "plugins-workspace",
             "source_root_basename": 7},
            {"name": "zod", "path": "zod", "aliases": ["Zod"],
             "source_repo_basename": "zod", "source_root_basename": "zod"},
        ]})
        assert {e["name"]: e["terms"] for e in entries} == {
            "oms-cognee": ["oms-cognee", "cognee"],
            "surrealdb": ["surrealdb", "surrealdb-v3.0.5"],
            "surrealql": ["surrealql"],
            "tauri-updater": ["tauri-updater", "updater"],
            "tauri-auth-plugins": ["tauri-auth-plugins"],
            "zod": ["zod"],
        }

    @pytest.mark.parametrize(
        "payload",
        [
            {"other": []},
            ["react"],
            [{"path": "x"}],
            [{"name": "x"}],
            [{"name": "x", "path": "x", "aliases": "X"}],
            [{"name": "x", "path": "x"}, {"name": "x", "path": "y"}],
        ],
    )
    def test_rejected_skill_entries(self, payload) -> None:
        with pytest.raises(mod.UserError):
            mod.parse_skill_entries(payload)

    def test_pairs_shapes_and_duplicates(self) -> None:
        pairs = mod.parse_pairs({"pairs": [
            ["a", "b"],
            {"library_a": "b", "library_b": "a", "architectural_context": "x"},
            {"library_a": "a", "library_b": "c"},
        ]})
        assert pairs == [("a", "b"), ("a", "c")]

    @pytest.mark.parametrize(
        "payload",
        [{"other": []}, [["a"]], [["a", "a"]], [{"library_a": "a"}], ["a-b"]],
    )
    def test_rejected_pairs(self, payload) -> None:
        with pytest.raises(mod.UserError):
            mod.parse_pairs(payload)


class TestCrossReferenceCli:
    def _skills_root(self, tmp_path: Path) -> Path:
        root = tmp_path / "skills"
        _write(root / "alpha" / "SKILL.md", "# alpha\n\nWraps beta.\n")
        _write(root / "beta" / "SKILL.md", "# beta\n\nUsed by alpha.\n")
        _write(root / "gamma" / "SKILL.md", "# gamma\n\nStands alone.\n")
        return root

    def test_relative_paths_resolve_against_skills_root(self, tmp_path: Path) -> None:
        root = self._skills_root(tmp_path)
        skills = _write(tmp_path / "skills.json", json.dumps([
            {"name": "alpha", "path": "alpha"},
            {"name": "beta", "skill_md": "beta/SKILL.md"},
            {"name": "gamma", "path": "gamma"},
            {"name": "delta", "path": "delta"},
        ]))
        result = _run_cli(
            "cross-reference", "--skills", str(skills),
            "--skills-root", str(root),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["edges"] == [["alpha", "beta"], ["beta", "alpha"]]
        assert len(payload["warnings"]) == 1
        assert payload["warnings"][0].startswith("delta: SKILL.md not found: ")

    def test_edges_pipe_into_find_cycles(self, tmp_path: Path) -> None:
        root = self._skills_root(tmp_path)
        skills = json.dumps([
            {"name": n, "path": n} for n in ("alpha", "beta", "gamma")
        ])
        xref = _run_cli_input(
            skills, "cross-reference", "--skills", "-", "--skills-root", str(root)
        )
        assert xref.returncode == 0, xref.stderr
        cycles = subprocess.run(
            [sys.executable, str(FIND_CYCLES_PATH), "find", "--edges", "-"],
            input=xref.stdout,
            capture_output=True,
            text=True,
            check=False,
        )
        assert cycles.returncode == 0, cycles.stderr
        assert json.loads(cycles.stdout) == {
            "cycles": [["alpha", "beta", "alpha"]],
            "cycle_count": 1,
        }

    def test_enumerate_inventory_as_input(self, tmp_path: Path) -> None:
        root = self._skills_root(tmp_path)
        for name in ("alpha", "beta", "gamma"):
            _write(
                root / name / "metadata.json",
                json.dumps({"generated_by": "create-skill", "exports": []}),
            )
        inventory = subprocess.run(
            [sys.executable, str(ENUMERATE_PATH), "enumerate", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert inventory.returncode == 0, inventory.stderr
        inventory_file = _write(tmp_path / "inventory.json", inventory.stdout)
        pairs = _write(tmp_path / "pairs.json", json.dumps([
            {"library_a": "gamma", "library_b": "alpha"},
            {"library_a": "alpha", "library_b": "beta"},
        ]))
        result = _run_cli(
            "cross-reference", "--skills", str(inventory_file),
            "--skills-root", str(root), "--pairs", str(pairs),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["edges"] == [["alpha", "beta"], ["beta", "alpha"]]
        assert [(p["library_a"], p["library_b"], p["cited"])
                for p in payload["pairs"]] == [
            ("alpha", "beta", True), ("gamma", "alpha", False),
        ]
        assert payload["warnings"] == []

    def test_inventory_source_basenames_cite_a_skill(self, tmp_path: Path) -> None:
        # app names oms-cognee's repository, so it cites oms-cognee; the
        # two tauri plugins share theirs, so naming it cites neither.
        root = tmp_path / "skills"
        repos = {
            "oms-cognee": "https://github.com/topoteretes/cognee.git",
            "tauri-updater": "https://github.com/tauri-apps/plugins-workspace",
            "tauri-auth": "https://github.com/tauri-apps/plugins-workspace",
            "app": None,
        }
        for name, repo in repos.items():
            _write(root / name / "SKILL.md", f"# {name}\n")
            metadata = {"generated_by": "create-skill", "exports": []}
            if repo is not None:
                metadata["source_repo"] = repo
            _write(root / name / "metadata.json", json.dumps(metadata))
        _write(
            root / "app" / "SKILL.md",
            "# app\n\nStores memories in Cognee.\nShips plugins-workspace builds.\n",
        )
        inventory = subprocess.run(
            [sys.executable, str(ENUMERATE_PATH), "enumerate", str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert inventory.returncode == 0, inventory.stderr
        inventory_file = _write(tmp_path / "inventory.json", inventory.stdout)
        result = _run_cli(
            "cross-reference", "--skills", str(inventory_file),
            "--skills-root", str(root),
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["edges"] == [["app", "oms-cognee"]]
        assert (payload["citations"][0]["substring"], payload["citations"][0]["line"]) == ("Cognee", 3)

    def test_both_inputs_on_stdin_exit_1(self) -> None:
        result = _run_cli("cross-reference", "--skills", "-", "--pairs", "-")
        assert result.returncode == 1
        assert "both read from stdin" in result.stderr

    def test_skills_root_not_a_directory_exits_1(self, tmp_path: Path) -> None:
        # a wrong root must not pass as a stack whose skills cite nothing
        skills = _write(
            tmp_path / "s.json", json.dumps([{"name": "a", "path": "a"}])
        )
        result = _run_cli(
            "cross-reference", "--skills", str(skills),
            "--skills-root", str(tmp_path / "nope"),
        )
        assert result.returncode == 1
        assert "--skills-root is not a directory" in result.stderr

    def test_duplicate_skill_names_exit_1(self, tmp_path: Path) -> None:
        skills = _write(tmp_path / "s.json", json.dumps([
            {"name": "a", "path": "a"}, {"name": "a", "path": "b"},
        ]))
        result = _run_cli("cross-reference", "--skills", str(skills))
        assert result.returncode == 1
        assert "twice" in result.stderr


# --------------------------------------------------------------------------
# reference-check
# --------------------------------------------------------------------------


REFERENCE_SKILL = """\
---
name: demo
description: See references/frontmatter.md (frontmatter is not scanned).
---

# demo

## Overview

See [API](references/api.md#usage) and [gone](references/gone.md "Title").
Read `references/api.md` then **references/api.md**, or references/api.md:L12.
[spaced](<references/my file.md>) and [encoded](references/my%20file.md).
[api][api-ref] uses a reference definition.

[api-ref]: references/api.md
[^1]: A footnote is not a path.
[Note]: this prose line is not a definition.

Run `scripts/run.py` or `scripts/absent.sh`; the schema is `assets/schema.json`.
[SRC:scripts/build.sh:L1], src/assets/logo.png and ../assets/x.png are not references.
[web](https://example.com/assets/x.png), [mail](mailto:a@b.c), [top](#overview).
Placeholders: `references/{name}.md`, `scripts/*.py`, `references/<file>.md`, `scripts/`.

```js
import { Button } from './Button';
// node scripts/build.js and see [x](references/in-code.md)
```

[escape](../../../../../etc/passwd) climbs out.
[absolute](/etc/passwd) is outside too.
[source](../../src/index.ts) and [stack](../react/SKILL.md).
Twice: [a](references/api.md) and [b](./references/api.md).
"""


class TestExtractReferences:
    def test_forms_and_skips(self) -> None:
        refs = mod.extract_references(
            REFERENCE_SKILL, frozenset({"scripts", "assets"})
        )
        text = REFERENCE_SKILL
        assert refs == [
            {"line": _line_of(text, "See [API]"), "form": "link",
             "target": "references/api.md"},
            {"line": _line_of(text, "See [API]"), "form": "link",
             "target": "references/gone.md"},
            {"line": _line_of(text, "Read `references"), "form": "mention",
             "target": "references/api.md"},
            {"line": _line_of(text, "Read `references"), "form": "mention",
             "target": "references/api.md"},
            {"line": _line_of(text, "Read `references"), "form": "mention",
             "target": "references/api.md"},
            {"line": _line_of(text, "[spaced]"), "form": "link",
             "target": "references/my file.md"},
            {"line": _line_of(text, "[spaced]"), "form": "link",
             "target": "references/my file.md"},
            {"line": _line_of(text, "[api-ref]: "), "form": "link",
             "target": "references/api.md"},
            {"line": _line_of(text, "Run `scripts"), "form": "mention",
             "target": "scripts/run.py"},
            {"line": _line_of(text, "Run `scripts"), "form": "mention",
             "target": "scripts/absent.sh"},
            {"line": _line_of(text, "Run `scripts"), "form": "mention",
             "target": "assets/schema.json"},
            {"line": _line_of(text, "[escape]"), "form": "link",
             "target": "../../../../../etc/passwd"},
            {"line": _line_of(text, "[absolute]"), "form": "link",
             "target": "/etc/passwd"},
            {"line": _line_of(text, "[source]"), "form": "link",
             "target": "../../src/index.ts"},
            {"line": _line_of(text, "[source]"), "form": "link",
             "target": "../react/SKILL.md"},
            {"line": _line_of(text, "Twice:"), "form": "link",
             "target": "references/api.md"},
            {"line": _line_of(text, "Twice:"), "form": "link",
             "target": "./references/api.md"},
        ]

    def test_folder_mentions_need_the_folder_or_the_scripts_section(self) -> None:
        text = (
            "## Quick Start\n\n"
            'Set `"icon": "./assets/icon.png"` and run `scripts/setup.sh` in '
            "your app.\n\n"
            "## Scripts & Assets\n\n"
            "| `scripts/check.py` | Checks the config |\n"
            "\n## Key Types\n\n`scripts/after.py` again.\n"
        )
        refs = mod.extract_references(text)
        assert refs == [{"line": 7, "form": "mention", "target": "scripts/check.py"}]
        # with the folder in the package, every mention counts
        shipped = mod.extract_references(text, frozenset({"scripts"}))
        assert [r["target"] for r in shipped] == [
            "scripts/setup.sh", "scripts/check.py", "scripts/after.py",
        ]

    def test_links_count_without_the_folder(self) -> None:
        refs = mod.extract_references("![logo](assets/logo.png)\n")
        assert refs == [{"line": 1, "form": "link", "target": "assets/logo.png"}]

    def test_link_targets_follow_commonmark(self) -> None:
        text = (
            "[a](references/a_(1).md) and [b](references/b\\_c.md).\n"
            "[c](references/c&amp;d.md), [d](references/d%20e.md#x).\n"
            "[e](references/&lt;name&gt;.md) is a placeholder.\n"
        )
        refs = mod.extract_references(text)
        assert [(r["line"], r["target"]) for r in refs] == [
            # one level of balanced parentheses stays in the target
            (1, "references/a_(1).md"),
            # a backslash escape and an entity reference are resolved
            (1, "references/b_c.md"),
            (2, "references/c&d.md"),
            (2, "references/d e.md"),
        ]

    def test_reference_type(self) -> None:
        assert mod._reference_type("./scripts/x.py") == "script-asset"
        assert mod._reference_type("assets/a.json") == "script-asset"
        assert mod._reference_type("references/a.md") == "file-path"
        assert mod._reference_type("../other/scripts/x.py") == "file-path"

    def test_inline_code_spans(self) -> None:
        line = "a `b` and ``c ` d`` and `unclosed"
        assert mod._inline_code_spans(line) == [(2, 5), (10, 19)]


class TestReferenceCheck:
    def _package(self, tmp_path: Path) -> Path:
        project = tmp_path / "project"
        skill_dir = project / "skills" / "demo"
        _write(skill_dir / "SKILL.md", REFERENCE_SKILL)
        _write(skill_dir / "references" / "api.md", "# API\n")
        _write(skill_dir / "references" / "my file.md", "# Spaced\n")
        _write(skill_dir / "scripts" / "run.py", "print(1)\n")
        _write(skill_dir / "assets" / "schema.json", "{}\n")
        _write(project / "src" / "index.ts", "export {}\n")
        _write(project / "skills" / "react" / "SKILL.md", "# react\n")
        return skill_dir

    def _check(self, skill_dir: Path, *flags: str) -> dict:
        result = _run_cli("reference-check", str(skill_dir / "SKILL.md"), *flags)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def test_statuses_without_extra_roots(self, tmp_path: Path) -> None:
        skill_dir = self._package(tmp_path)
        payload = self._check(skill_dir)
        rows = [
            (r["target"], r["type"], r["form"], r["status"], r["root"])
            for r in payload["references"]
        ]
        assert rows == [
            ("references/api.md", "file-path", "link", "ok", "skill"),
            ("references/gone.md", "file-path", "link", "missing", "skill"),
            ("references/api.md", "file-path", "mention", "ok", "skill"),
            ("references/my file.md", "file-path", "link", "ok", "skill"),
            ("references/api.md", "file-path", "link", "ok", "skill"),
            ("scripts/run.py", "script-asset", "mention", "ok", "skill"),
            ("scripts/absent.sh", "script-asset", "mention", "missing", "skill"),
            ("assets/schema.json", "script-asset", "mention", "ok", "skill"),
            ("../../../../../etc/passwd", "file-path", "link", "escapes", None),
            ("/etc/passwd", "file-path", "link", "escapes", None),
            ("../../src/index.ts", "file-path", "link", "escapes", None),
            ("../react/SKILL.md", "file-path", "link", "escapes", None),
            ("references/api.md", "file-path", "link", "ok", "skill"),
        ]
        assert payload["counts"] == {
            "total": 13, "ok": 7, "missing": 2, "escapes": 4,
        }
        assert payload["warnings"] == []
        assert payload["roots"] == {
            "skill": os.path.realpath(str(skill_dir)),
            "source": None,
            "skills": None,
        }
        first = payload["references"][0]
        assert first["canonical"] == os.path.realpath(
            str(skill_dir / "references" / "api.md")
        )
        assert first["line"] == _line_of(REFERENCE_SKILL, "See [API]")

    def test_source_and_skills_roots(self, tmp_path: Path) -> None:
        skill_dir = self._package(tmp_path)
        project = skill_dir.parent.parent
        payload = self._check(
            skill_dir,
            "--source-root", str(project / "src"),
            "--skills-root", str(project / "skills"),
        )
        by_target = {r["target"]: r for r in payload["references"]}
        assert by_target["../../src/index.ts"]["status"] == "ok"
        assert by_target["../../src/index.ts"]["root"] == "source"
        assert by_target["../react/SKILL.md"]["status"] == "ok"
        assert by_target["../react/SKILL.md"]["root"] == "skills"
        # the skill folder sits inside the skills root; the first root wins
        assert by_target["references/api.md"]["root"] == "skill"
        assert by_target["/etc/passwd"]["status"] == "escapes"
        assert payload["roots"]["source"] == os.path.realpath(str(project / "src"))

    def test_symlink_out_of_the_package_escapes(self, tmp_path: Path) -> None:
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks unavailable")
        skill_dir = tmp_path / "skill"
        secret = _write(tmp_path / "outside" / "secret.md", "secret\n")
        _write(skill_dir / "SKILL.md", "See `references/link.md`.\n")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "link.md").symlink_to(secret)
        ref = self._check(skill_dir)["references"][0]
        assert ref["status"] == "escapes"
        assert ref["canonical"] == os.path.realpath(str(secret))

    def test_symlink_inside_the_package_is_ok(self, tmp_path: Path) -> None:
        if not _symlinks_supported(tmp_path):
            pytest.skip("symlinks unavailable")
        skill_dir = tmp_path / "skill"
        target = _write(skill_dir / "references" / "real.md", "# Real\n")
        _write(skill_dir / "SKILL.md", "See [alias](references/alias.md).\n")
        (skill_dir / "references" / "alias.md").symlink_to(target)
        ref = self._check(skill_dir)["references"][0]
        assert (ref["status"], ref["root"]) == ("ok", "skill")

    def test_package_without_folders_skips_their_mentions(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        _write(
            skill_dir / "SKILL.md",
            "Put `assets/icon.png` in your app.\n\n"
            "## Scripts & Assets\n\n`scripts/check.py` ships here.\n",
        )
        payload = self._check(skill_dir)
        assert [(r["target"], r["status"]) for r in payload["references"]] == [
            ("scripts/check.py", "missing"),
        ]

    def test_no_references(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skill"
        _write(skill_dir / "SKILL.md", "# Title\n\nPlain prose.\n")
        payload = self._check(skill_dir)
        assert payload["references"] == []
        assert payload["counts"] == {"total": 0, "ok": 0, "missing": 0, "escapes": 0}

    def test_byte_order_mark_keeps_the_frontmatter(self, tmp_path: Path) -> None:
        # read as plain UTF-8, the mark would hide the frontmatter and its
        # description would read as a missing reference
        skill_dir = tmp_path / "skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_bytes(
            b"\xef\xbb\xbf---\ndescription: see references/fm.md\n---\n"
            b"# Title\n\nPlain prose.\n"
        )
        assert self._check(skill_dir)["references"] == []

    def test_roots_that_are_not_directories_warn(self, tmp_path: Path) -> None:
        skill_dir = self._package(tmp_path)
        gone = tmp_path / "gone"
        a_file = skill_dir / "SKILL.md"
        payload = self._check(
            skill_dir, "--source-root", str(gone), "--skills-root", str(a_file)
        )
        assert payload["warnings"] == [
            f"--source-root is not a directory: {gone}",
            f"--skills-root is not a directory: {a_file}",
        ]

    def test_missing_skill_md_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli("reference-check", str(tmp_path / "nope.md"))
        assert result.returncode == 1
        assert "file not found" in result.stderr
