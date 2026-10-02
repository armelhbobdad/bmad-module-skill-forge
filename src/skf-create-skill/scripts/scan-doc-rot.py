#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""Doc-rot correction-candidate scan (step-doc-rot.md §2).

Step 5c writes a `## CORRECTION` block for each live upstream correction to an
export the compiled skill documents. This helper finds the candidates: it
walks the resolved feeder artifacts, matches every line against the fixed
13-row keyword table with case-insensitive substring containment (no regex,
no semantics), and emits each hit with the kind of change its keyword
suggests (`candidate_category`), a ranking hint. A keyword is not a
correction: "No breaking changes in this release" holds one, and so do a pull
request template checkbox and a bug fix that mentions a deprecation warning.
Nor is every correction worded with one: a Keep a Changelog "### Removed"
bullet that names `Client.close_all`, or "Renamed `load` to `read`", holds
none. So with --provenance (the staged provenance map), a line of the
project's own announcements (the temporal feeder's changelog.md,
releases.md and prs.md) that names an export the map lists is a candidate
too. Every candidate carries the nearest headings above it: `release`, the
nearest one naming a version (`## [2.3.0] - 2024-05-01`, `## v2.3.0`), and
`section`, the nearest one under that (`### Removed`). The step's judgment
pass decides which candidates are live corrections, then caps the blocks at
10. Running the scan here (instead of in-prompt) keeps the candidate list
identical for identical feeders: the model never hand-greps multi-KB
artifacts.

Before it returns, the script drops matches that land inside the compiled
SKILL.md's own YAML frontmatter or its own `## Migration & Deprecation
Warnings` section (both are self-authored: compile §2 wrote the frontmatter
`description` and compile §4b wrote the migration bullets, so re-emitting
either would be circular), and then bounds what survives.

Bounding matters because the temporal feeder is a verbatim upstream dump
(changelog, release notes, issue and pull request bodies), so an unbounded
run can hand the judgment pass hundreds of "breaking" and "deprecated" lines.
Two deterministic bounds run after the exclusions: duplicate collapse (same
candidate category + same normalized line text) and a cap on the candidate
pool. Keyword hits, and export mentions under a change section, come first;
a plain export mention (an "### Added" bullet) gets only the places left. A
change section is a heading whose whole text is a change name (Keep a
Changelog's `### Deprecated`, `### Removed` and `### Changed`, `## Breaking
Changes`, `## Migration Guide`), never one with such a word inside it:
GitHub's generated `## What's Changed` and a pull request template's
`## Type of change` head every line of their feeder. Within each of those two
ranks the feeders share the cap in turns, so a years-deep changelog cannot
crowd out the release notes, and the compiled SKILL.md's own lines of a rank
come after every other feeder's lines of that rank, so the skill's own text
never outranks an upstream line of the same rank.
Nothing is silently destroyed: a collapsed record carries `occurrences` and
`duplicate_of`, and the counts of what was collapsed and capped are reported
so the step can log them.

CLI usage:
  uv run scan-doc-rot.py --skill-md <staged SKILL.md> [--provenance <map>] [FEEDER ...]
  uv run scan-doc-rot.py --feeder evidence-report.md --feeder provenance-map.json

  --skill-md         the compiled/staged SKILL.md feeder (feeder #4); matches
                     inside its YAML frontmatter or its `## Migration &
                     Deprecation Warnings` section are excluded, and its other
                     candidates come last when the pool is capped. It is also
                     scanned like any other feeder.
  FEEDER             any other feeder artifact (evidence-report.md,
                     provenance-map.json, temporal-context files). Repeatable
                     positionally or via --feeder.
  --provenance       the staged provenance-map.json: its entries[].export_name
                     values are the exports a changelog.md, releases.md or
                     prs.md line may name (`default` aside). Missing, empty or
                     unreadable: no export is known, as without the flag.
  --max-candidates   cap on emitted candidates (default 50). 0 or negative
                     means unlimited.

  Missing or empty files are skipped silently (not an error), matching §1's
  "attempt to load; if it does not exist or is empty, skip it."

Output (stdout, one object):
  {
    "scanned": ["<path>", ...],        # feeders that existed and were non-empty
    "matches": [                        # the candidates step 5c's judgment pass reviews
      {"source": "<path>", "pattern": "deprecated" | null,  # null: an export mention
       "candidate_category": "Deprecation" | null,
       "context_line": "<line text>", "line_number": <1-indexed int>,
       "exports": ["<export_name>", ...],  # the known exports the line names
       "release": "<heading>" | null,     # nearest heading above naming a version
       "section": "<heading>" | null,     # nearest heading below that one
       "occurrences": <int>,            # 1 unless duplicates collapsed into this record
       "duplicate_of": [{"source": "<path>", "line_number": <int>}, ...]},
      ...
    ],
    "match_count": <int>,               # len(matches), after exclusions/collapse/cap
    "excluded_count": <int>,            # SKILL.md matches dropped (frontmatter + §4b)
    "deduped_count": <int>,             # matches collapsed into a surviving record
    "capped_count": <int>,              # candidates dropped because the cap was reached
    "cap": <int>,                       # effective cap (0 = unlimited)
    "exports_known": <int>              # export names --provenance gave
  }

Exit codes:
  0  — scan emitted successfully (including the zero-match case)
  1  — invalid arguments (no feeders supplied)
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

# Fixed keyword table: (pattern, candidate_category). A hit makes the line a
# candidate for step-doc-rot.md §2's judgment pass, never a correction by itself.
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

# The temporal feeder files that carry the project's own announcements: a line
# of one that names a known export is a candidate (issues.md and
# targeted-issues.md hold reports anyone can open, which §2 drops anyway).
EXPORT_FEEDERS = frozenset({"changelog.md", "releases.md", "prs.md"})
# An export name too common to mean the export when a line says it.
IGNORED_EXPORT_NAMES = frozenset({"default"})
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
# A heading that names a release: a version (`[2.3.0]`, `v2.3.0`, `2.3`) or Unreleased.
_RELEASE_HEADING = re.compile(r"\bv?\d+\.\d+|\bunreleased\b", re.IGNORECASE)
# A change section: a heading whose whole text, its marks stripped, is one of
# these names. Its export mentions rank with the keyword hits.
_CHANGE_SECTION = re.compile(
    r"deprecated|deprecations?|removed|removals?|changed|breaking(?: changes?)?|migrations?(?: guide)?",
    re.IGNORECASE,
)
# The marks around a heading's words: `[Removed]`, `Removed:`, `⚠ BREAKING CHANGES`.
_HEADING_MARKS = re.compile(r"^[\W_]+|[\W_]+$")
_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")

# Cap on the candidate pool one run hands the judgment pass (step-doc-rot.md §2).
# The pass keeps at most 10 corrections (step 5b budgets the compiled body at 400
# lines and each block is ~7 lines), so 50 candidates leaves room for the many
# keyword lines that are no correction at all.
DEFAULT_MAX_CANDIDATES = 50


def named_exports(line: str, exports: frozenset[str]) -> list[str]:
    """The known export names `line` names: each dotted identifier on it
    (`Client.close_all`) and each of its parts (`close_all`), checked
    against the set. Sorted, each once."""
    found: set[str] = set()
    for token in _IDENTIFIER.findall(line):
        for name in (token, *token.split(".")):
            if name in exports:
                found.add(name)
    return sorted(found)


def scan_text(
    text: str, source: str, exports: frozenset[str] = frozenset(), export_feeder: bool = False
) -> list[dict]:
    """Case-insensitive substring scan of `text` against PATTERN_TABLE.

    Returns one record per (line, pattern) hit, in file order then table
    order, and, when `export_feeder`, one record for a line with no hit that
    names an export of `exports` (pattern and candidate_category null).
    Every record carries the line's `exports` and the nearest `release` and
    `section` headings above it (headings inside a code fence do not count).
    line_number is 1-indexed. Pure: no I/O.
    """
    matches: list[dict] = []
    release: str | None = None
    section: str | None = None
    fenced = False
    for idx, line in enumerate(text.splitlines(), start=1):
        if _FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else _HEADING.match(line)
        if heading:
            title = line.strip()
            if _RELEASE_HEADING.search(heading.group(2)):
                release, section = title, None
            else:
                section = title
        named = named_exports(line, exports) if exports else []
        lowered = line.lower()
        context = {"context_line": line.strip(), "line_number": idx, "exports": named,
                   "release": release, "section": None if heading else section}
        hit = False
        for pattern, candidate_category in PATTERN_TABLE:
            if pattern.lower() in lowered:
                hit = True
                matches.append({"source": source, "pattern": pattern,
                                "candidate_category": candidate_category, **context})
        if not hit and export_feeder and named:
            matches.append({"source": source, "pattern": None, "candidate_category": None, **context})
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
    """Collapse matches that repeat the same text under the same candidate category.

    Returns (kept, collapsed). The dedup key is
    `(candidate_category, whitespace-normalized lowercased context_line)`: a
    temporal changelog restates the same deprecation across many releases, and
    a pull request template repeats the same checkbox in every pull request, so
    each restatement would otherwise be its own candidate saying the same thing.

    The first occurrence in scan order survives and gains two fields:
    `occurrences` (how many keyword hits collapsed into it, itself included)
    and `duplicate_of` (the `{source, line_number}` of every later hit), so
    nothing is silently destroyed. Two keywords of one candidate category on
    one line count twice, and the second hit points back at the same line.
    Records are copies: the inputs are untouched.
    """
    seen: dict[tuple[str, str], dict] = {}
    kept: list[dict] = []
    for m in matches:
        key = (m["candidate_category"], " ".join(m["context_line"].split()).lower())
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


def change_section(section: str | None) -> bool:
    """True when `section` (a heading line) is a change section: its text,
    without its `#`s and the marks around its words, is a change name as a
    whole. `### Removed` and `## Breaking Changes` are; `## What's Changed`
    and `## Type of change` are not."""
    title = _HEADING_MARKS.sub("", (section or "").strip().lstrip("#"))
    return bool(_CHANGE_SECTION.fullmatch(title))


def rank(match: dict) -> int:
    """0 for a keyword hit or a line under a change section, 1 for a plain
    export mention (an "### Added" bullet)."""
    if match.get("pattern") is not None:
        return 0
    return 0 if change_section(match.get("section")) else 1


def apply_cap(
    matches: list[dict], cap: int, skill_md_source: str | None
) -> tuple[list[dict], int]:
    """Keep at most `cap` candidates. Returns (kept, dropped).

    A cap of 0 or less means unlimited. Rank 0 (keyword hits, and export
    mentions under a change section) fills the cap before rank 1 (plain
    export mentions). Within a rank the feeders share the cap in turns: each
    turn takes the next candidate of every feeder, in scan order, so one long
    feeder (a years-deep changelog) cannot crowd out the rest. The compiled
    SKILL.md's own candidates take only the places of their rank left after
    every other feeder's, because its body restates what compile wrote: the
    skill's own text never outranks an upstream line of its rank. The kept records are
    returned in scan order, so a run that does not hit the cap is ordered
    exactly as the scan.
    """
    if cap <= 0 or len(matches) <= cap:
        return matches, 0
    order: list[int] = []
    for level in (0, 1):
        by_feeder: dict[str, list[int]] = {}
        for i, m in enumerate(matches):
            if m["source"] != skill_md_source and rank(m) == level:
                by_feeder.setdefault(m["source"], []).append(i)
        order += [i for turn in itertools.zip_longest(*by_feeder.values()) for i in turn if i is not None]
        order += [i for i, m in enumerate(matches) if m["source"] == skill_md_source and rank(m) == level]
    keep = sorted(order[:cap])
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


def load_exports(path: str | None) -> frozenset[str]:
    """The entries[].export_name values of a provenance map; empty when the
    path is None, missing, empty or not a provenance map."""
    text = _load(path) if path else None
    if text is None:
        return frozenset()
    try:
        data = json.loads(text)
    except ValueError:
        return frozenset()
    entries = data.get("entries") if isinstance(data, dict) else None
    names = {e.get("export_name") for e in entries or [] if isinstance(e, dict)}
    return frozenset(n for n in names if isinstance(n, str) and n and n not in IGNORED_EXPORT_NAMES)


def scan_files(
    feeders: list[str],
    skill_md: str | None,
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    provenance: str | None = None,
) -> dict:
    """Scan every feeder + the skill-md feeder, apply the self-authorship
    exclusions, collapse duplicates, cap the candidate pool, and return the
    result object. Deterministic: feeders scanned in the given order."""
    scanned: list[str] = []
    matches: list[dict] = []
    skill_md_text = None
    exports = load_exports(provenance)

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
        export_feeder = path != skill_md and Path(path).name in EXPORT_FEEDERS
        matches.extend(scan_text(text, path, exports, export_feeder))

    # Frontmatter first, then the §4b section — the two windows are disjoint, so
    # the total is order-independent, but running them in file order keeps the
    # attribution obvious when debugging a run.
    matches, front_excluded = apply_frontmatter_exclusion(matches, skill_md, skill_md_text)
    matches, section_excluded = apply_migration_exclusion(matches, skill_md, skill_md_text)
    matches, deduped = collapse_duplicates(matches)
    matches, capped = apply_cap(matches, max_candidates, skill_md)
    return {
        "scanned": scanned,
        "matches": matches,
        "match_count": len(matches),
        "excluded_count": front_excluded + section_excluded,
        "deduped_count": deduped,
        "capped_count": capped,
        "cap": max(max_candidates, 0),
        "exports_known": len(exports),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan-doc-rot",
        description=(
            "Doc-rot correction-candidate scan (step-doc-rot.md §2): "
            "case-insensitive substring match of feeder artifacts against the fixed "
            "keyword table, with the compiled SKILL.md's frontmatter and "
            "Migration & Deprecation Warnings section excluded, duplicates collapsed, "
            "and the candidate pool capped. The step's judgment pass decides which "
            "candidates are corrections."
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
        "Deprecation Warnings section are excluded from matches, and its other "
        "candidates come last when the pool is capped.",
    )
    parser.add_argument(
        "--provenance",
        dest="provenance",
        default=None,
        help="The staged provenance-map.json: a changelog.md, releases.md or prs.md line "
        "that names one of its entries[].export_name values is a candidate too.",
    )
    parser.add_argument(
        "--max-candidates",
        dest="max_candidates",
        type=int,
        default=DEFAULT_MAX_CANDIDATES,
        help=(
            f"Maximum candidates to emit (default {DEFAULT_MAX_CANDIDATES}). "
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
    result = scan_files(feeders, args.skill_md, max_candidates=args.max_candidates, provenance=args.provenance)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
