#!/usr/bin/env python3
"""Unit tests for src/skf-create-skill/scripts/scan-doc-rot.py (step-doc-rot.md §2).

Covers the case-insensitive substring scan against the 13-row pattern table,
the per-(line, pattern) record shape, the `## Migration & Deprecation Warnings`
positional exclusion, missing/empty-feeder skipping, and the subprocess CLI
(exit codes + JSON-on-stdout).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-create-skill"
    / "scripts"
    / "scan-doc-rot.py"
)

spec = importlib.util.spec_from_file_location("scan_doc_rot", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

scan_text = mod.scan_text
migration_section_range = mod.migration_section_range
apply_migration_exclusion = mod.apply_migration_exclusion
scan_files = mod.scan_files
PATTERN_TABLE = mod.PATTERN_TABLE


# --------------------------------------------------------------------------
# Pattern table contract
# --------------------------------------------------------------------------


def test_pattern_table_has_13_rows():
    assert len(PATTERN_TABLE) == 13


def test_pattern_table_matches_step_doc_prose():
    """Every pattern + category in the script must be documented in step-doc-rot.md."""
    step = (SCRIPT_PATH.parent.parent / "references" / "step-doc-rot.md").read_text(
        encoding="utf-8"
    )
    for pattern, category in PATTERN_TABLE:
        assert pattern in step, f"pattern '{pattern}' missing from step-doc-rot.md"
        assert category in step, f"category '{category}' missing from step-doc-rot.md"


# --------------------------------------------------------------------------
# scan_text — case-insensitive substring, per-(line, pattern) records
# --------------------------------------------------------------------------


def test_case_insensitive_match():
    matches = scan_text("This API was DEPRECATED last year.", "f.md")
    patterns = {m["pattern"] for m in matches}
    assert "deprecated" in patterns


def test_records_full_field_shape():
    matches = scan_text("foo removed in v2", "f.md")
    m = next(x for x in matches if x["pattern"] == "removed in")
    assert m == {
        "source": "f.md",
        "pattern": "removed in",
        "category": "Removal",
        "context_line": "foo removed in v2",
        "line_number": 1,
    }


def test_line_numbers_are_1_indexed():
    text = "clean\nclean\nrenamed to bar\n"
    m = next(x for x in scan_text(text, "f.md") if x["pattern"] == "renamed to")
    assert m["line_number"] == 3


def test_at_deprecated_and_deprecated_both_fire_on_same_line():
    """Overlapping table patterns each record their own hit (13-row contract)."""
    matches = scan_text("`@deprecated` marks it", "f.md")
    patterns = [m["pattern"] for m in matches]
    assert "deprecated" in patterns
    assert "@deprecated" in patterns


def test_no_false_positive_on_clean_text():
    assert scan_text("A perfectly current stable API.\nNothing to see.", "f.md") == []


def test_context_line_is_stripped():
    m = scan_text("   breaking change ahead   ", "f.md")[0]
    assert m["context_line"] == "breaking change ahead"


# --------------------------------------------------------------------------
# Migration & Deprecation Warnings exclusion (§4b guard)
# --------------------------------------------------------------------------


SKILL_MD = (
    "# Skill\n"
    "\n"
    "## API\n"
    "foo was removed in v2\n"  # line 4 — OUTSIDE migration section → kept
    "\n"
    "## Migration & Deprecation Warnings\n"  # line 6 — heading
    "- bar deprecated since v3\n"  # line 7 — INSIDE → excluded
    "- baz superseded by qux\n"  # line 8 — INSIDE → excluded
    "\n"
    "## Footer\n"  # line 10 — closes the section
    "old note renamed to new\n"  # line 11 — OUTSIDE → kept
)


def test_migration_section_range():
    assert migration_section_range(SKILL_MD) == (6, 10)


def test_migration_range_none_when_absent():
    assert migration_section_range("# Skill\n## API\nfoo deprecated\n") is None


def test_exclusion_drops_only_in_section_matches():
    matches = scan_text(SKILL_MD, "SKILL.md")
    kept, dropped = apply_migration_exclusion(matches, "SKILL.md", SKILL_MD)
    kept_lines = {m["line_number"] for m in kept}
    assert 4 in kept_lines  # "removed in" before the section
    assert 11 in kept_lines  # "renamed to" after the section
    assert 7 not in kept_lines  # "deprecated" inside → dropped
    assert 8 not in kept_lines  # "superseded by" inside → dropped
    assert dropped == 2


def test_exclusion_only_applies_to_skill_md_source():
    """An identical line from a NON-skill-md feeder is never excluded."""
    other = scan_text("bar deprecated since v3", "evidence-report.md")
    kept, dropped = apply_migration_exclusion(other, "SKILL.md", SKILL_MD)
    assert dropped == 0
    assert len(kept) == len(other)


def test_subsection_does_not_close_migration_window():
    text = (
        "## Migration & Deprecation Warnings\n"  # 1
        "### Details\n"  # 2 — ### must NOT close the section
        "old renamed to new\n"  # 3 — still inside
        "## Next\n"  # 4 — closes
    )
    assert migration_section_range(text) == (1, 4)


# --------------------------------------------------------------------------
# scan_files — missing/empty skip + scanned list
# --------------------------------------------------------------------------


def test_scan_files_skips_missing_and_empty(tmp_path):
    good = tmp_path / "evidence-report.md"
    good.write_text("thing removed in v9\n", encoding="utf-8")
    empty = tmp_path / "empty.md"
    empty.write_text("   \n", encoding="utf-8")
    missing = tmp_path / "nope.md"
    out = scan_files([str(good), str(empty), str(missing)], None)
    assert out["scanned"] == [str(good)]
    assert out["match_count"] == 1
    assert out["matches"][0]["pattern"] == "removed in"


def test_scan_files_applies_exclusion_end_to_end(tmp_path):
    skill = tmp_path / "SKILL.md"
    skill.write_text(SKILL_MD, encoding="utf-8")
    out = scan_files([], str(skill))
    lines = {m["line_number"] for m in out["matches"]}
    assert out["excluded_count"] == 2
    assert 4 in lines and 11 in lines
    assert 7 not in lines and 8 not in lines
    assert out["scanned"] == [str(skill)]


# --------------------------------------------------------------------------
# CLI (subprocess) — exit codes + JSON on stdout
# --------------------------------------------------------------------------


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
    )


def test_cli_emits_json(tmp_path):
    feeder = tmp_path / "provenance-map.json"
    feeder.write_text('{"note": "api migration required now"}\n', encoding="utf-8")
    proc = _run([str(feeder)])
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["match_count"] == 1
    assert data["matches"][0]["category"] == "Migration"


def test_cli_zero_matches_is_success(tmp_path):
    feeder = tmp_path / "clean.md"
    feeder.write_text("all current, nothing to correct\n", encoding="utf-8")
    proc = _run([str(feeder)])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["match_count"] == 0


def test_cli_no_args_exits_1():
    proc = _run([])
    assert proc.returncode == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
