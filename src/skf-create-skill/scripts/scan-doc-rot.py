#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic doc-rot correction-indicator scan (step-doc-rot.md §2).

step 5c self-declares its correction scan "grep-based and deterministic — no AI
judgment is used for detection." This helper *is* that grep: it walks the
resolved feeder artifacts, matches every line against the fixed 13-row
correction-pattern table with case-insensitive substring containment (no regex,
no semantics), and emits the matches as JSON. It applies the one positional
filter the step documents — dropping matches that land inside the compiled
SKILL.md's own `## Migration & Deprecation Warnings` section (compile §4b
already authored those, so re-emitting them would be circular) — before it
returns. Running the scan here (instead of in-prompt) makes the "deterministic,
identical input → identical output" promise actually hold: the model no longer
hand-greps multi-KB artifacts.

The genuine judgment the step keeps in-prompt is untouched by this script:
enriching each match's `affected` symbol from surrounding context (§2) and
choosing where the `## CORRECTION` block goes (§3). The script emits every
deterministic field (`source`, `pattern`, `category`, `context_line`,
`line_number`); the prompt adds `affected`.

The pattern table and category labels are the contract in step-doc-rot.md §2 —
keep the two in lockstep.

CLI usage:
  uv run scan-doc-rot.py --skill-md <staged SKILL.md> [FEEDER ...]
  uv run scan-doc-rot.py --feeder evidence-report.md --feeder provenance-map.json

  --skill-md  the compiled/staged SKILL.md feeder (feeder #4); matches inside its
              `## Migration & Deprecation Warnings` section are excluded. It is
              also scanned like any other feeder.
  FEEDER      any other feeder artifact (evidence-report.md, provenance-map.json,
              temporal-context files). Repeatable positionally or via --feeder.

  Missing or empty files are skipped silently (not an error), matching §1's
  "attempt to load; if it does not exist or is empty, skip it."

Output (stdout, one object):
  {
    "scanned": ["<path>", ...],        # feeders that existed and were non-empty
    "matches": [                        # correction_matches[] (affected added in-prompt)
      {"source": "<path>", "pattern": "deprecated", "category": "Deprecation",
       "context_line": "<line text>", "line_number": <1-indexed int>},
      ...
    ],
    "match_count": <int>,
    "excluded_count": <int>             # SKILL.md matches dropped by the §4b filter
  }

Exit codes:
  0  — scan emitted successfully (including the zero-match case)
  1  — invalid arguments (no feeders supplied)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Fixed correction-pattern table — mirrors step-doc-rot.md §2. (pattern, category)
# Order is the table order; scanning is per-pattern so overlapping patterns
# (e.g. "deprecated" ⊂ "@deprecated") each record their own hit, exactly as the
# 13-row table enumerates them.
PATTERN_TABLE: list[tuple[str, str]] = [
    ("deprecated", "Deprecation"),
    ("@deprecated", "Deprecation"),
    ("breaking change", "Breaking change"),
    ("BREAKING", "Breaking change"),
    ("removed in", "Removal"),
    ("was removed", "Removal"),
    ("renamed to", "Rename"),
    ("renamed from", "Rename"),
    ("superseded by", "Supersession"),
    ("replaced by", "Supersession"),
    ("no longer supported", "End of life"),
    ("migration required", "Migration"),
    ("signature changed", "Signature change"),
]

_MIGRATION_HEADING = re.compile(r"^\s*##\s+Migration\s*&\s*Deprecation Warnings", re.IGNORECASE)


def scan_text(text: str, source: str) -> list[dict]:
    """Case-insensitive substring scan of `text` against PATTERN_TABLE.

    Returns one record per (line, pattern) hit, in file order then table order.
    line_number is 1-indexed. Pure — no I/O.
    """
    matches: list[dict] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        for pattern, category in PATTERN_TABLE:
            if pattern.lower() in lowered:
                matches.append(
                    {
                        "source": source,
                        "pattern": pattern,
                        "category": category,
                        "context_line": line.strip(),
                        "line_number": idx,
                    }
                )
    return matches


def migration_section_range(skill_md_text: str) -> tuple[int, int] | None:
    """1-indexed [start, end) line window of the `## Migration & Deprecation
    Warnings` section, or None if the section is absent.

    start = the heading line; end = the next level-2 (`## `) heading, or EOF.
    A `### ` subsection inside the section does NOT close it (only a sibling
    `## ` heading does), matching §2's "before the next `##` heading".
    """
    lines = skill_md_text.splitlines()
    start = None
    for idx, line in enumerate(lines, start=1):
        if _MIGRATION_HEADING.match(line):
            start = idx
            break
    if start is None:
        return None
    end = len(lines) + 1
    for idx in range(start + 1, len(lines) + 1):
        if lines[idx - 1].lstrip().startswith("## "):
            end = idx
            break
    return (start, end)


def apply_migration_exclusion(
    matches: list[dict], skill_md_source: str | None, skill_md_text: str | None
) -> tuple[list[dict], int]:
    """Drop matches whose source is the compiled SKILL.md and whose line sits
    inside its Migration & Deprecation Warnings section. Returns (kept, dropped)."""
    if skill_md_source is None or skill_md_text is None:
        return matches, 0
    window = migration_section_range(skill_md_text)
    if window is None:
        return matches, 0
    start, end = window
    kept, dropped = [], 0
    for m in matches:
        if m["source"] == skill_md_source and start <= m["line_number"] < end:
            dropped += 1
            continue
        kept.append(m)
    return kept, dropped


def _load(path: str) -> str | None:
    """Read a feeder file as UTF-8. Returns None for missing/empty (skip, not
    an error). UTF-8 avoids cp1252 mojibake on Windows."""
    p = Path(path)
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return None
    return text


def scan_files(feeders: list[str], skill_md: str | None) -> dict:
    """Scan every feeder + the skill-md feeder, apply the §4b exclusion, return
    the result object. Deterministic: feeders scanned in the given order."""
    scanned: list[str] = []
    matches: list[dict] = []
    skill_md_text = None

    ordered = list(feeders)
    if skill_md is not None:
        ordered.append(skill_md)

    for path in ordered:
        text = _load(path)
        if text is None:
            continue
        scanned.append(path)
        if path == skill_md:
            skill_md_text = text
        matches.extend(scan_text(text, path))

    matches, excluded = apply_migration_exclusion(matches, skill_md, skill_md_text)
    return {
        "scanned": scanned,
        "matches": matches,
        "match_count": len(matches),
        "excluded_count": excluded,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan-doc-rot",
        description=(
            "Deterministic doc-rot correction-indicator scan (step-doc-rot.md §2): "
            "case-insensitive substring match of feeder artifacts against the fixed "
            "correction-pattern table, with the compiled SKILL.md's Migration & "
            "Deprecation Warnings section excluded."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "positional_feeders",
        nargs="*",
        metavar="FEEDER",
        help="Feeder artifact paths (evidence-report.md, provenance-map.json, temporal files).",
    )
    parser.add_argument(
        "--feeder",
        action="append",
        default=[],
        dest="feeders",
        help="Feeder artifact path (repeatable). Equivalent to a positional FEEDER.",
    )
    parser.add_argument(
        "--skill-md",
        dest="skill_md",
        default=None,
        help="Compiled/staged SKILL.md feeder; its Migration & Deprecation Warnings "
        "section is excluded from matches.",
    )
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    feeders = list(args.positional_feeders) + list(args.feeders)
    if not feeders and args.skill_md is None:
        parser.print_usage(file=sys.stderr)
        print("error: supply at least one feeder path or --skill-md", file=sys.stderr)
        return 1
    result = scan_files(feeders, args.skill_md)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
