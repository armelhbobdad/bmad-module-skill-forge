# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""SKF Scan Skill.md Structure — deterministic structural checks for SKILL.md.

Replaces the synonym-grep loops, bash fence recipes, and inline Python
table-parser in `references/coherence-check.md` §§2.1 / 2.2 / 2.3 / 2.6 with
a single subprocess invocation that emits JSON.

Subcommands:
  scan <skill-md>
      Emit JSON describing fence balance, bare opening fences (no language
      tag), and table column-count drift:
        {
          "unbalanced_fences": <bool>,
          "fence_count": N,
          "bare_opening_fences": [{"line": N, "text": "..."}, ...],
          "table_drift": [{"line": N, "section": "<heading>",
                           "expected_cols": N, "actual_cols": N,
                           "row": "..."}]
        }

  scan <skill-md> --required-sections
      Emit JSON describing which of the three required section families
      (description / usage / api_surface) are present, and which synonym
      satisfied the requirement (case-insensitive, `##`/`###` tolerated):
        {
          "description":  {"satisfied": <bool>,
                           "matched_synonym": "<heading>" | null,
                           "tried": ["Description", "Overview", ...]},
          "usage":        {"satisfied": <bool>,
                           "matched_synonym": "..." | null,
                           "tried": [...]},
          "api_surface":  {"satisfied": <bool>,
                           "matched_synonym": "..." | null,
                           "tried": [...]}
        }

Heading match rule:
  Match the first `^#+\\s+<heading>$` (any number of `#`, case-insensitive,
  surrounding whitespace trimmed) that matches any synonym in a family.
  The reported `matched_synonym` is the canonical synonym from the list,
  not the heading text as it appears in the file.

Fence balance:
  Count triple-backtick (```) fence lines (`^```` at start of line, ignoring
  leading whitespace). `unbalanced_fences=true` iff the count is odd.

Bare opening fence:
  A stateful open/close scan toggles `in_code` on each fence line. A bare
  opening fence is one where `in_code` transitions 0→1 and the line, with
  the leading ``` stripped, has no language tag (empty or whitespace-only
  remainder). Closing fences are never flagged — they are bare by markdown
  convention. This mirrors the Python recipe in coherence-check.md §2.3.

Table drift:
  Walks markdown table blocks. A block starts when a `^\\|.*\\|$` line is
  found; subsequent contiguous `^\\|.*\\|$` lines are part of the same
  block. The first row is the header. The second row, if it matches the
  separator pattern (cells made of `-`, `:`, and whitespace), is ignored
  in the drift count. For every other row, normalize escaped pipes (`\\|`)
  to a sentinel before splitting on `|`, then drop the empty leading and
  trailing fields produced by the bracketing pipes; flag rows whose column
  count differs from the header's. Each flag includes the line number,
  the most-recently-seen `^#+\\s+` heading, expected/actual column counts,
  and the raw row text.

  Escaped pipes appear inside TypeScript union types (e.g.
  `string \\| undefined`). Normalizing prevents one false drift finding
  per union-typed cell.

Empty SKILL.md:
  An empty file yields `fence_count: 0`, `unbalanced_fences: false`,
  empty `bare_opening_fences`, empty `table_drift`; for
  `--required-sections`, all three families have `satisfied: false`,
  `matched_synonym: null`.

Exit codes:
  0 — operation succeeded
  1 — user error (file not found, can't read)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------
# Required-section synonym constants
# --------------------------------------------------------------------------


# These mirror the canonical synonyms documented in
# `src/skf-test-skill/references/coherence-check.md` §2.1, with the
# SKF-template-specific headings folded in so they are first-class
# matches rather than literal-name misses (per the §2.1 "Note"
# paragraph). The set covers the Deep/create-skill template
# (`Quick Start`, `Common Workflows`, `Key API Summary`, `Key Types`),
# the quick-skill template (`Usage Patterns`, `Key Exports`), and the
# reference-app assembly overrides (`Adoption Steps` replaces Common
# Workflows for usage; `Pattern Surface` replaces Key API Summary for
# api_surface), since headings are matched on the full heading text,
# not a substring.
REQUIRED_SYNONYMS: dict[str, list[str]] = {
    "description": ["Description", "Overview", "Purpose", "Summary"],
    "usage": [
        "Usage",
        "Usage Patterns",
        "Examples",
        "How to use",
        "Quickstart",
        "Quick Start",
        "Getting Started",
        "Common Workflows",
        "Adoption Steps",
    ],
    "api_surface": [
        "API",
        "API Surface",
        "Exports",
        "Key Exports",
        "Public API",
        "Interface",
        "Reference",
        "Key API Summary",
        "Pattern Surface",
    ],
}


# --------------------------------------------------------------------------
# Required-section presence
# --------------------------------------------------------------------------


_HEADING_RE = re.compile(r"^\s*(#+)\s+(.*?)\s*$")


def find_required_sections(text: str) -> dict[str, dict]:
    """For each family, find the first matching heading.

    Walks every line once, lower-cases the heading text, and looks it up
    against pre-lowered synonym sets. Returns the structure described in
    the module docstring.
    """
    # Build a lookup: lowered-heading → (family, canonical_synonym)
    # Multiple families can never share a synonym, so a flat dict is fine.
    lookup: dict[str, tuple[str, str]] = {}
    for family, synonyms in REQUIRED_SYNONYMS.items():
        for syn in synonyms:
            lookup[syn.lower()] = (family, syn)

    matched: dict[str, str] = {}
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if not m:
            continue
        heading_text = m.group(2).strip().lower()
        hit = lookup.get(heading_text)
        if hit is None:
            continue
        family, canonical = hit
        if family in matched:
            # first match wins
            continue
        matched[family] = canonical

    result: dict[str, dict] = {}
    for family, synonyms in REQUIRED_SYNONYMS.items():
        if family in matched:
            result[family] = {
                "satisfied": True,
                "matched_synonym": matched[family],
                "tried": list(synonyms),
            }
        else:
            result[family] = {
                "satisfied": False,
                "matched_synonym": None,
                "tried": list(synonyms),
            }
    return result


# --------------------------------------------------------------------------
# Fence balance + bare opening fences
# --------------------------------------------------------------------------


def scan_fences(text: str) -> tuple[int, bool, list[dict]]:
    """Count fences, decide balance, collect bare opening fences.

    Uses a stateful toggle so closing fences are never flagged.
    Returns (fence_count, unbalanced, bare_opening_fences[]).
    """
    fence_count = 0
    bare: list[dict] = []
    in_code = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        # match lines that start with ``` (allow leading whitespace,
        # which markdown tolerates in some renderers)
        stripped = raw.lstrip()
        if not stripped.startswith("```"):
            continue
        fence_count += 1
        # the part of the fence line after the opening ```
        tail = stripped[3:].strip()
        if not in_code:
            # opening fence: a bare opening fence has empty tail
            if tail == "":
                bare.append({"line": lineno, "text": raw})
            in_code = True
        else:
            # closing fence — never flagged
            in_code = False
    return fence_count, (fence_count % 2 == 1), bare


# --------------------------------------------------------------------------
# Table column drift
# --------------------------------------------------------------------------


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")
_PIPE_SENTINEL = "\x00"


def _split_row_cells(row_text: str) -> list[str]:
    """Split a markdown table row into cells.

    Normalizes escaped pipes to a sentinel before splitting, then drops
    the empty leading/trailing fields produced by the bracketing pipes.
    """
    normalized = row_text.strip().replace("\\|", _PIPE_SENTINEL)
    parts = normalized.split("|")
    # parts looks like ["", "cell1", "cell2", ..., ""] for `|a|b|`;
    # drop bracketing empties.
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [p.replace(_PIPE_SENTINEL, "|") for p in parts]


def _is_separator_row(cells: list[str]) -> bool:
    """True if every cell looks like a table separator (`---`, `:---:`, etc.)."""
    if not cells:
        return False
    return all(_TABLE_SEP_CELL_RE.match(c) is not None for c in cells)


def find_table_drift(text: str) -> list[dict]:
    """Walk table blocks, flag rows whose column count differs from the header.

    Tracks the most-recently-seen heading text so each finding can name the
    section it's in. The heading text reported is the raw text after the `#`
    characters, with surrounding whitespace stripped.
    """
    findings: list[dict] = []
    lines = text.splitlines()
    current_section = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        heading = _HEADING_RE.match(line)
        if heading is not None:
            current_section = heading.group(2).strip()
            i += 1
            continue
        if not _TABLE_ROW_RE.match(line):
            i += 1
            continue

        # Start of a table block. Collect contiguous rows.
        block_start = i
        block_rows: list[tuple[int, str]] = []
        while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
            block_rows.append((i + 1, lines[i]))  # 1-based line numbers
            i += 1

        if not block_rows:
            continue

        header_lineno, header_text = block_rows[0]
        header_cells = _split_row_cells(header_text)
        expected = len(header_cells)

        # If the second row is a separator, skip it from drift checking.
        body_rows = block_rows[1:]
        if body_rows:
            _, second_text = body_rows[0]
            if _is_separator_row(_split_row_cells(second_text)):
                body_rows = body_rows[1:]

        for row_lineno, row_text in body_rows:
            cells = _split_row_cells(row_text)
            actual = len(cells)
            if actual != expected:
                findings.append({
                    "line": row_lineno,
                    "section": current_section,
                    "expected_cols": expected,
                    "actual_cols": actual,
                    "row": row_text,
                })

        # if the block ended at a non-row line, fall through to advance i;
        # i already points past the block.
        _ = block_start  # explicitly unused, kept for readability
    return findings


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _cmd_scan(args: argparse.Namespace) -> int:
    skill_md = Path(args.skill_md)
    if not skill_md.is_file():
        print(f"error: file not found: {skill_md}", file=sys.stderr)
        return 1
    try:
        text = _read_text(skill_md)
    except OSError as exc:
        print(f"error: cannot read {skill_md}: {exc}", file=sys.stderr)
        return 1

    if args.required_sections:
        payload = find_required_sections(text)
    else:
        fence_count, unbalanced, bare = scan_fences(text)
        payload = {
            "unbalanced_fences": unbalanced,
            "fence_count": fence_count,
            "bare_opening_fences": bare,
            "table_drift": find_table_drift(text),
        }

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-scan-skill-md-structure",
        description=(
            "Deterministic structural scans for SKILL.md: fence balance, "
            "bare opening fences, table column drift, and required-section "
            "presence (case-insensitive synonym match)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="emit structural scan JSON")
    p_scan.add_argument("skill_md", help="path to a SKILL.md file")
    p_scan.add_argument(
        "--required-sections",
        action="store_true",
        help="emit required-section presence JSON instead of fence/table data",
    )
    p_scan.set_defaults(func=_cmd_scan)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
