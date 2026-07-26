#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic doc-rot correction-indicator scan (step-doc-rot.md §2).

step 5c self-declares its correction scan "grep-based and deterministic — no AI
judgment is used for detection." This helper *is* that grep: it walks the
resolved feeder artifacts, matches every line against the fixed 13-row
correction-pattern table with case-insensitive substring containment (no regex,
no semantics), and emits the matches as JSON. It applies the positional filters
the step documents — dropping matches that land inside the compiled SKILL.md's
own YAML frontmatter or its own `## Migration & Deprecation Warnings` section
(both are self-authored: compile §2 wrote the frontmatter `description` and
compile §4b wrote the migration bullets, so re-emitting either would be
circular) — and then bounds what survives, before it returns. Running the scan
here (instead of in-prompt) makes the "deterministic, identical input →
identical output" promise actually hold: the model no longer hand-greps
multi-KB artifacts.

Bounding matters because §2's own example command passes the raw temporal
changelog as a feeder. That artifact is a verbatim upstream dump (thousands of
lines of release history), so an unbounded run turns years of "breaking" /
"deprecated" lines into hundreds of `## CORRECTION` blocks and blows the
compiled body's line budget. Two deterministic bounds run after the exclusions:
duplicate collapse (same category + same normalized line text) and a hard cap
on how many blocks a single run may propose. Nothing is silently destroyed —
a collapsed record carries `occurrences` and `duplicate_of`, and the counts of
what was collapsed and capped are reported so the step can log them.

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

  --skill-md         the compiled/staged SKILL.md feeder (feeder #4); matches
                     inside its YAML frontmatter or its `## Migration &
                     Deprecation Warnings` section are excluded. It is also
                     scanned like any other feeder.
  FEEDER             any other feeder artifact (evidence-report.md,
                     provenance-map.json, temporal-context files). Repeatable
                     positionally or via --feeder.
  --max-corrections  cap on emitted matches (default 10). 0 or negative means
                     unlimited.

  Missing or empty files are skipped silently (not an error), matching §1's
  "attempt to load; if it does not exist or is empty, skip it."

Output (stdout, one object):
  {
    "scanned": ["<path>", ...],        # feeders that existed and were non-empty
    "matches": [                        # correction_matches[] (affected added in-prompt)
      {"source": "<path>", "pattern": "deprecated", "category": "Deprecation",
       "context_line": "<line text>", "line_number": <1-indexed int>,
       "occurrences": <int>,            # 1 unless duplicates collapsed into this record
       "duplicate_of": [{"source": "<path>", "line_number": <int>}, ...]},
      ...
    ],
    "match_count": <int>,               # len(matches), after exclusions/collapse/cap
    "excluded_count": <int>,            # SKILL.md matches dropped (frontmatter + §4b)
    "deduped_count": <int>,             # matches collapsed into a surviving record
    "capped_count": <int>,              # matches dropped because the cap was reached
    "cap": <int>                        # effective cap (0 = unlimited)
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

# Cap on how many `## CORRECTION` blocks one run may propose (step-doc-rot.md §3).
# Step 5b budgets the compiled body at 400 lines and each block is ~7 lines, so
# 10 blocks stays inside the budget with headroom.
DEFAULT_MAX_CORRECTIONS = 10


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


def frontmatter_range(text: str) -> tuple[int, int] | None:
    """1-indexed [start, end] inclusive window of the leading YAML frontmatter
    block (both `---` fences included), or None when the file has no frontmatter.

    Delimiter handling mirrors the established SKF convention (see
    `skf-shard-body.py` `split_frontmatter` and
    `skf-validate-feasibility-report.py` `split_frontmatter`): the opening fence
    must be the FIRST line and the closing fence is the next line that is
    exactly `---` once surrounding whitespace is stripped. A `---` horizontal
    rule further down the body therefore cannot open a block, and an unterminated
    opening fence yields None rather than swallowing the file.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(2, len(lines) + 1):
        if lines[idx - 1].strip() == "---":
            return (1, idx)
    return None


def migration_section_range(skill_md_text: str) -> tuple[int, int] | None:
    """1-indexed [start, end) line window of the `## Migration & Deprecation
    Warnings` section, or None if the section is absent.

    start = the heading line; end = the next level-2 (`## `) heading, or EOF.
    A `### ` subsection inside the section does NOT close it (only a sibling
    `## ` heading does), matching §2's "before the next `##` heading".

    The search starts after any YAML frontmatter. `_MIGRATION_HEADING` tolerates
    leading whitespace, so an indented restatement of the heading inside a folded
    `description:` would otherwise anchor the window in the frontmatter and leave
    the real body section unexcluded.
    """
    lines = skill_md_text.splitlines()
    front = frontmatter_range(skill_md_text)
    first_body_line = front[1] + 1 if front else 1
    start = None
    for idx in range(first_body_line, len(lines) + 1):
        if _MIGRATION_HEADING.match(lines[idx - 1]):
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


def apply_frontmatter_exclusion(
    matches: list[dict], skill_md_source: str | None, skill_md_text: str | None
) -> tuple[list[dict], int]:
    """Drop matches whose source is the compiled SKILL.md and whose line sits
    inside its YAML frontmatter. Returns (kept, dropped).

    Same circularity argument as the §4b exclusion below: compile (step 5 §2)
    authors the frontmatter `description` from the very annotations this scan
    looks for, so a `breaking change` / `deprecated` phrase there is already
    surfaced, not a new correction. The frontmatter is also a closed key set of
    pipeline scalars (`name`, `description`), so a match in it can never be an
    upstream correction the body has missed.

    Scoped to the compiled SKILL.md deliberately. evidence-report.md also carries
    frontmatter, but its frontmatter holds pinned counts rather than authored
    prose, so it cannot restate an upstream correction and is left in scope.
    """
    if skill_md_source is None or skill_md_text is None:
        return matches, 0
    window = frontmatter_range(skill_md_text)
    if window is None:
        return matches, 0
    start, end = window
    kept, dropped = [], 0
    for m in matches:
        if m["source"] == skill_md_source and start <= m["line_number"] <= end:
            dropped += 1
            continue
        kept.append(m)
    return kept, dropped


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


def collapse_duplicates(matches: list[dict]) -> tuple[list[dict], int]:
    """Collapse matches that repeat the same text under the same category.

    Returns (kept, collapsed). The dedup key is
    `(category, whitespace-normalized lowercased context_line)` — a temporal
    changelog restates the same deprecation across many releases, and each
    restatement would otherwise become its own `## CORRECTION` block saying the
    same thing.

    The first occurrence in scan order survives and gains two fields:
    `occurrences` (how many lines collapsed into it, including itself) and
    `duplicate_of` (the `{source, line_number}` of every later occurrence), so
    nothing is silently destroyed. Records are copies — the inputs are untouched.
    """
    seen: dict[tuple[str, str], dict] = {}
    kept: list[dict] = []
    for m in matches:
        key = (m["category"], " ".join(m["context_line"].split()).lower())
        survivor = seen.get(key)
        if survivor is not None:
            survivor["occurrences"] += 1
            survivor["duplicate_of"].append(
                {"source": m["source"], "line_number": m["line_number"]}
            )
            continue
        record = dict(m, occurrences=1, duplicate_of=[])
        seen[key] = record
        kept.append(record)
    return kept, len(matches) - len(kept)


def apply_cap(
    matches: list[dict], cap: int, skill_md_source: str | None
) -> tuple[list[dict], int]:
    """Keep at most `cap` matches. Returns (kept, dropped).

    A cap of 0 or less means unlimited. Selection prefers the compiled SKILL.md's
    own annotations over other feeders — a naive head-slice would drop them first,
    because scan order puts the skill-md feeder last — and falls back to scan
    order within each group. The kept records are returned in scan order, so a
    run that does not hit the cap is ordered exactly as it is today.
    """
    if cap <= 0 or len(matches) <= cap:
        return matches, 0
    priority = sorted(
        range(len(matches)),
        key=lambda i: (0 if matches[i]["source"] == skill_md_source else 1, i),
    )
    keep = sorted(priority[:cap])
    return [matches[i] for i in keep], len(matches) - cap


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


def scan_files(
    feeders: list[str],
    skill_md: str | None,
    *,
    max_corrections: int = DEFAULT_MAX_CORRECTIONS,
) -> dict:
    """Scan every feeder + the skill-md feeder, apply the self-authorship
    exclusions, collapse duplicates, cap the survivors, and return the result
    object. Deterministic: feeders scanned in the given order."""
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

    # Frontmatter first, then the §4b section — the two windows are disjoint, so
    # the total is order-independent, but running them in file order keeps the
    # attribution obvious when debugging a run.
    matches, front_excluded = apply_frontmatter_exclusion(matches, skill_md, skill_md_text)
    matches, section_excluded = apply_migration_exclusion(matches, skill_md, skill_md_text)
    matches, deduped = collapse_duplicates(matches)
    matches, capped = apply_cap(matches, max_corrections, skill_md)
    return {
        "scanned": scanned,
        "matches": matches,
        "match_count": len(matches),
        "excluded_count": front_excluded + section_excluded,
        "deduped_count": deduped,
        "capped_count": capped,
        "cap": max(max_corrections, 0),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan-doc-rot",
        description=(
            "Deterministic doc-rot correction-indicator scan (step-doc-rot.md §2): "
            "case-insensitive substring match of feeder artifacts against the fixed "
            "correction-pattern table, with the compiled SKILL.md's frontmatter and "
            "Migration & Deprecation Warnings section excluded, duplicates collapsed, "
            "and the survivors capped."
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
        help="Compiled/staged SKILL.md feeder; its frontmatter and its Migration & "
        "Deprecation Warnings section are excluded from matches.",
    )
    parser.add_argument(
        "--max-corrections",
        dest="max_corrections",
        type=int,
        default=DEFAULT_MAX_CORRECTIONS,
        help=(
            f"Maximum matches to emit (default {DEFAULT_MAX_CORRECTIONS}). "
            "0 or negative means unlimited."
        ),
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
    result = scan_files(feeders, args.skill_md, max_corrections=args.max_corrections)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
