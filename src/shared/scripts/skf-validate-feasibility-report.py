#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Validate Feasibility Report — deterministic structure/schema gate.

Validates a skf-verify-stack feasibility report (.md) against the two
producer↔consumer contract invariants the report.md §1 prompt previously
eyeballed by re-reading the file each run:

  1. The five required body sections are all present and appear in the
     canonical order defined by the shared feasibility-report schema:
       ## Executive Summary
       ## Coverage Analysis
       ## Integration Verdicts
       ## Recommendations
       ## Evidence Sources
  2. Frontmatter `schemaVersion` equals the literal producer version "1.0".

Both are pure structure/schema checks — identical input always yields
identical pass/fail — so this belongs in a deterministic script, not an LLM
re-read. The verdict is emitted as JSON on stdout:

  {
    "status": "ok" | "error",
    "path": "<report path>",
    "schemaVersionOk": bool,
    "schemaVersionFound": "<value>" | null,
    "headingsOk": bool,
    "missingHeadings": [...],
    "orderViolations": [...],
    "violation": "schema-violation" | null
  }

Frontmatter is parsed with the standard library only (no pyyaml dep) using the
same delimiter handling as skf-validate-output.py: a `---`-delimited block at
the top of the file, parsed as simple `key: value` scalars with surrounding
quotes stripped. This is sufficient for the single `schemaVersion` scalar and
keeps the script stdlib-only.

Exit codes (per script-standards):
  0  valid          — all sections present + in order AND schemaVersion == "1.0"
  1  schema-violation — missing/mis-ordered section, or schemaVersion mismatch
                        (the JSON `violation` field + detail lists carry why)
  2  IO/parse error  — report file could not be read

CLI:
  python3 skf-validate-feasibility-report.py <report.md>
  python3 skf-validate-feasibility-report.py <report.md> -o result.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Canonical body-section order per the shared feasibility-report schema
# (src/shared/references/feasibility-report-schema.md → "Body section headings").
# Case-sensitive, exact heading text.
CANONICAL_HEADINGS = [
    "Executive Summary",
    "Coverage Analysis",
    "Integration Verdicts",
    "Recommendations",
    "Evidence Sources",
]

# Producer schema version the consumer/producer both pin to.
EXPECTED_SCHEMA_VERSION = "1.0"

# A level-2 markdown heading: exactly two '#', then whitespace, then the text.
# `### Foo` does not match (the 3rd char is '#', not whitespace).
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")


def split_frontmatter(content):
    """Return (frontmatter_dict, body_text).

    Stdlib-only, no YAML dependency — mirrors skf-validate-output.py's delimiter
    handling. The opening delimiter must be a line that is exactly `---`; the
    closing delimiter is the next line that is exactly `---`. The block between
    them is parsed as simple `key: value` scalars with surrounding quotes
    stripped. If no valid frontmatter block is present, returns ({}, content).
    """
    lines = content.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return {}, content

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, content

    fm = {}
    for line in lines[1:end_idx]:
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip("'\"")

    body = "\n".join(lines[end_idx + 1:])
    return fm, body


def scan_headings(body):
    """Scan the body for the canonical level-2 sections.

    Returns (missing, order_violations):
      - missing: canonical headings not found at all (in canonical order).
      - order_violations: human-readable strings describing each inversion,
        detected by walking the canonical order and flagging any present
        heading whose first occurrence is earlier than the previous present
        canonical heading's first occurrence.

    Deterministic: same body → same lists.
    """
    lines = body.split("\n")
    first_line = {}  # heading text -> 0-based body line index of first occurrence
    for idx, line in enumerate(lines):
        m = _H2_RE.match(line)
        if not m:
            continue
        text = m.group(1).strip()
        if text in CANONICAL_HEADINGS and text not in first_line:
            first_line[text] = idx

    missing = [h for h in CANONICAL_HEADINGS if h not in first_line]

    order_violations = []
    prev_name = None
    prev_idx = -1
    for h in CANONICAL_HEADINGS:
        if h not in first_line:
            continue
        cur_idx = first_line[h]
        if prev_name is not None and cur_idx < prev_idx:
            order_violations.append(
                f"'## {h}' appears at body line {cur_idx + 1}, before "
                f"'## {prev_name}' at body line {prev_idx + 1} "
                f"(expected '{prev_name}' to precede '{h}')"
            )
        prev_name = h
        prev_idx = cur_idx

    return missing, order_violations


def validate_report(path):
    """Validate one feasibility report. Returns (result_dict, exit_code)."""
    p = Path(path)
    try:
        content = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return (
            {
                "status": "error",
                "path": str(p),
                "error": f"could not read report file: {e}",
                "schemaVersionOk": False,
                "schemaVersionFound": None,
                "headingsOk": False,
                "missingHeadings": [],
                "orderViolations": [],
                "violation": "io-error",
            },
            2,
        )

    fm, body = split_frontmatter(content)
    schema_version = fm.get("schemaVersion")  # None if the key is absent
    schema_version_ok = schema_version == EXPECTED_SCHEMA_VERSION

    missing, order_violations = scan_headings(body)
    headings_ok = not missing and not order_violations

    ok = schema_version_ok and headings_ok
    result = {
        "status": "ok" if ok else "error",
        "path": str(p),
        "schemaVersionOk": schema_version_ok,
        "schemaVersionFound": schema_version,
        "headingsOk": headings_ok,
        "missingHeadings": missing,
        "orderViolations": order_violations,
        "violation": None if ok else "schema-violation",
    }
    return result, (0 if ok else 1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate a feasibility report's section order and schemaVersion. "
            "Confirms the five required body sections (Executive Summary, "
            "Coverage Analysis, Integration Verdicts, Recommendations, "
            "Evidence Sources) are present and in canonical order, and that "
            "frontmatter schemaVersion == \"1.0\". Exit 0 valid, 1 "
            "schema-violation, 2 IO/parse error."
        )
    )
    parser.add_argument("report", help="path to the feasibility report .md file")
    parser.add_argument(
        "-o",
        "--output",
        help="write the JSON verdict to this file instead of stdout",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print the resolved exit code to stderr",
    )
    args = parser.parse_args(argv)

    result, exit_code = validate_report(args.report)
    text = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    if args.verbose:
        print(f"exit_code={exit_code} violation={result.get('violation')}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
