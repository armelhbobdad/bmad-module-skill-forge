#!/usr/bin/env python3
"""Tests for skf-validate-feasibility-report.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "shared"
    / "scripts"
    / "skf-validate-feasibility-report.py"
)

spec = importlib.util.spec_from_file_location(
    "skf_validate_feasibility_report", SCRIPT_PATH
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_report = mod.validate_report
split_frontmatter = mod.split_frontmatter
scan_headings = mod.scan_headings


def _report(schema_version='"1.0"', sections=None):
    """Build a feasibility-report string.

    `sections` is the ordered list of body headings to emit; defaults to the
    canonical order. Each section gets a line of filler body.
    """
    if sections is None:
        sections = [
            "Executive Summary",
            "Coverage Analysis",
            "Integration Verdicts",
            "Recommendations",
            "Evidence Sources",
        ]
    fm_lines = ["---"]
    if schema_version is not None:
        fm_lines.append(f"schemaVersion: {schema_version}")
    fm_lines.append("reportType: feasibility")
    fm_lines.append('overallVerdict: "FEASIBLE"')
    fm_lines.append("---")
    body_lines = ["", "# Feasibility Report", ""]
    for s in sections:
        body_lines.append(f"## {s}")
        body_lines.append("")
        body_lines.append(f"Body text for {s}.")
        body_lines.append("")
    return "\n".join(fm_lines + body_lines) + "\n"


def _write(tmp_path, content, name="report.md"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# --- (1) valid report -------------------------------------------------------


def test_valid_report_passes(tmp_path):
    p = _write(tmp_path, _report())
    result, code = validate_report(str(p))
    assert code == 0
    assert result["status"] == "ok"
    assert result["headingsOk"] is True
    assert result["schemaVersionOk"] is True
    assert result["schemaVersionFound"] == "1.0"
    assert result["missingHeadings"] == []
    assert result["orderViolations"] == []
    assert result["violation"] is None


# --- (2) out-of-order sections ---------------------------------------------


def test_out_of_order_sections_fail(tmp_path):
    # Recommendations placed before Integration Verdicts.
    p = _write(
        tmp_path,
        _report(
            sections=[
                "Executive Summary",
                "Coverage Analysis",
                "Recommendations",
                "Integration Verdicts",
                "Evidence Sources",
            ]
        ),
    )
    result, code = validate_report(str(p))
    assert code == 1
    assert result["status"] == "error"
    assert result["violation"] == "schema-violation"
    assert result["headingsOk"] is False
    assert result["missingHeadings"] == []
    assert result["orderViolations"], "expected a non-empty orderViolations list"
    # schemaVersion itself is fine here.
    assert result["schemaVersionOk"] is True


# --- (3) missing section ----------------------------------------------------


def test_missing_section_fail(tmp_path):
    p = _write(
        tmp_path,
        _report(
            sections=[
                "Executive Summary",
                "Coverage Analysis",
                "Integration Verdicts",
                "Recommendations",
                # Evidence Sources omitted
            ]
        ),
    )
    result, code = validate_report(str(p))
    assert code == 1
    assert result["violation"] == "schema-violation"
    assert "Evidence Sources" in result["missingHeadings"]
    assert result["headingsOk"] is False


# --- (4) schemaVersion mismatch --------------------------------------------


def test_schema_version_mismatch_fail(tmp_path):
    p = _write(tmp_path, _report(schema_version='"2.0"'))
    result, code = validate_report(str(p))
    assert code == 1
    assert result["schemaVersionOk"] is False
    assert result["schemaVersionFound"] == "2.0"
    assert result["violation"] == "schema-violation"
    # Headings are correct — only the version is wrong.
    assert result["headingsOk"] is True


# --- (5) schemaVersion absent ----------------------------------------------


def test_schema_version_absent_fail(tmp_path):
    p = _write(tmp_path, _report(schema_version=None))
    result, code = validate_report(str(p))
    assert code == 1
    assert result["schemaVersionOk"] is False
    assert result["schemaVersionFound"] is None
    assert result["violation"] == "schema-violation"


# --- IO error ---------------------------------------------------------------


def test_missing_file_io_error(tmp_path):
    result, code = validate_report(str(tmp_path / "does-not-exist.md"))
    assert code == 2
    assert result["status"] == "error"
    assert result["violation"] == "io-error"


# --- helper-level unit checks ----------------------------------------------


def test_split_frontmatter_quotes_stripped(tmp_path):
    fm, body = split_frontmatter(_report())
    assert fm["schemaVersion"] == "1.0"
    assert "## Executive Summary" in body


def test_split_frontmatter_no_frontmatter():
    content = "# Just a body\n\n## Executive Summary\n"
    fm, body = split_frontmatter(content)
    assert fm == {}
    assert body == content


def test_scan_headings_ignores_level_three():
    # A '### Executive Summary' must NOT satisfy the level-2 requirement.
    body = "### Executive Summary\n## Coverage Analysis\n"
    missing, _ = scan_headings(body)
    assert "Executive Summary" in missing


def test_scan_headings_first_occurrence_used():
    body = "\n".join(
        [
            "## Executive Summary",
            "## Coverage Analysis",
            "## Integration Verdicts",
            "## Recommendations",
            "## Evidence Sources",
        ]
    )
    missing, violations = scan_headings(body)
    assert missing == []
    assert violations == []


# --- CLI exit-code smoke test ----------------------------------------------


def test_cli_exit_codes(tmp_path):
    valid = _write(tmp_path, _report(), name="valid.md")
    bad = _write(tmp_path, _report(schema_version='"9.9"'), name="bad.md")

    ok = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(valid)],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0
    payload = json.loads(ok.stdout)
    assert payload["status"] == "ok"

    fail = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(bad)],
        capture_output=True,
        text=True,
    )
    assert fail.returncode == 1
    payload = json.loads(fail.stdout)
    assert payload["schemaVersionFound"] == "9.9"

    err = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(tmp_path / "nope.md")],
        capture_output=True,
        text=True,
    )
    assert err.returncode == 2
