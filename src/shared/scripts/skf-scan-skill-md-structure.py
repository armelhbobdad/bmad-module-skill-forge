# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Scan Skill.md Structure — deterministic structural checks for SKILL.md.

Replaces the synonym-grep loops, bash fence recipes, and inline Python
table-parser in `references/coherence-check.md` §§2.1 / 2.2 / 2.3 / 2.6 with
a single subprocess invocation that emits JSON.

The usage-scope, cross-reference and reference-check subcommands emit the
facts that test-skill's coherence check (§2.4 zero-usage exports, §§3-4
file, script and asset references) and verify-stack's Check 4 (literal
citations between skills) would otherwise count, grep and compare by hand,
so two runs over the same files always agree.

Subcommands:
  scan <skill-md>
      Emit JSON describing fence balance, bare opening fences (no language
      tag), table column-count drift and the Scripts & Assets section (see
      "Scripts & Assets section" below):
        {
          "unbalanced_fences": <bool>,
          "fence_count": N,
          "bare_opening_fences": [{"line": N, "text": "..."}, ...],
          "table_drift": [{"line": N, "section": "<heading>",
                           "expected_cols": N, "actual_cols": N,
                           "row": "..."}],
          "scripts_assets": {"folders": ["assets", "scripts"],
                             "section": {"heading": "...", "line": N} | null,
                             "missing": <bool>}
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

  usage-scope <skill-md> --exports <json-file-or-'-'> [--kinds <k1,k2,...>]
              [--body auto|single|split]
      Emit JSON counting, for each export, the lines that use its name in
      the usage scope (see "Usage scope" and "Export match" below):
        {
          "scope": {
            "body": "single" | "split",
            "sections": [{"heading": "<text>", "line": N,
                          "end_line": N}, ...],
            "reference_files": ["references/<file>.md", ...]
          },
          "exports": [{"name": "...", "kind": "..." | null, "count": N,
                       "first_hit": {"file": "...", "line": N} | null},
                      ...],
          "zero_usage": [{"name": "...", "kind": "..." | null}, ...],
          "warnings": ["references/<file>.md: cannot read: ...", ...]
        }
      --exports holds a JSON array of names or {"name", "kind"} objects,
      an object with an `exports` array (test-skill's step 3 inventory),
      or the validate-inventory.py result (its `inventory.exports`).
      --kinds counts only the exports whose kind it lists; an export
      given without a kind is always counted. --body picks the scope
      (default auto; see "Usage scope"). `exports[]` is sorted by name,
      then kind, with duplicates dropped; `zero_usage[]` lists the
      exports whose count is 0.

  cross-reference --skills <json-file-or-'-'> [--skills-root <dir>]
                  [--pairs <json-file-or-'-'>]
      Emit JSON listing where one skill's SKILL.md literally cites another
      skill (see "Citation match" below):
        {
          "citations": [{"from": "<a>", "to": "<b>",
                         "substring": "<as written>", "line": N,
                         "count": N, "excerpt": "...",
                         "hits": [{"line": N, "substring": "...",
                                   "excerpt": "..."}, ...]}, ...],
          "edges": [["<a>", "<b>"], ...],
          "pairs": [{"library_a": "<a>", "library_b": "<b>",
                     "a_cites_b": <bool>, "b_cites_a": <bool>,
                     "cited": <bool>}, ...],
          "warnings": ["<name>: ...", ...]
        }
      --skills holds a JSON array of {"name", "skill_md" | "path",
      "aliases"} entries (`aliases` optional), or an object with a
      `skills` array: the skf-enumerate-stack-skills.py inventory, whose
      `path` is relative to the skills folder, so pass that folder as
      --skills-root. An entry's `source_repo_basename` and
      `source_root_basename` (the inventory gives both) are aliases too,
      unless another entry has the same term as its name, an alias or a
      source basename, since one word would then cite two skills.
      `path` names the skill folder, `skill_md` the file;
      a relative one resolves against --skills-root, else the working
      directory, and a --skills-root that is not a directory is an
      error. `citations[]` holds one entry per citing direction, sorted
      by (from, to): `hits[]` lists every citing line in line order,
      `count` is their number, and `substring`, `line` and `excerpt`
      repeat the first hit. `edges[]` is the same set in the shape
      skf-find-cycles.py reads ({"edges": [[from, to], ...]}), so this
      output pipes into `find --edges -` as is. --pairs (a JSON array of
      [a, b] or {"library_a", "library_b"} entries, or an object with a
      `pairs` array) keeps only the citations between those pairs and
      adds `pairs[]`, sorted, where `cited` means either direction
      cites. A SKILL.md that cannot be read is a warning (its skill can
      still be cited), and so is a pair that names a skill --skills
      lacks.

  reference-check <skill-md> [--source-root <dir>] [--skills-root <dir>]
      Emit JSON checking every file, script and asset reference in the
      SKILL.md body (see "Reference extraction" below):
        {
          "roots": {"skill": "<dir>", "source": "<dir>" | null,
                    "skills": "<dir>" | null},
          "references": [{"line": N,
                          "type": "file-path" | "script-asset",
                          "form": "link" | "mention",
                          "target": "<as written>",
                          "canonical": "<realpath>",
                          "status": "ok" | "missing" | "escapes",
                          "root": "skill" | "source" | "skills" | null},
                         ...],
          "counts": {"total": N, "ok": N, "missing": N, "escapes": N},
          "scripts_assets": {...},
          "warnings": ["--source-root is not a directory: <dir>", ...]
        }
      A target resolves against the SKILL.md folder and through every
      symlink (os.path.realpath) before the root check. The roots are
      the SKILL.md folder, --source-root (the extraction tree,
      metadata.json `source_root`) and --skills-root (the skills output
      folder, for a stack skill whose references reach its constituent
      skills); `root` names the first one that holds the target.
      `escapes`: outside every root (whether it exists is not checked,
      the escape is the finding); `missing`: inside a root, nothing
      there; `ok`: inside a root and present. `references[]` is in
      document order; the same canonical target twice on one line is one
      reference. A --source-root or --skills-root that is not a
      directory (a stale metadata.json `source_root`, say) is a warning,
      not an error.

Scripts & Assets section:
  `folders` lists the `scripts` and `assets` folders beside SKILL.md,
  sorted; `section` is the first heading outside the frontmatter and
  fenced code whose text starts with `Scripts` (case-insensitive, any
  level: the section the reference extraction below also reads), with its
  text and line, or null; `missing` is true when a folder exists and no
  such section does, the gap test-skill's coherence check records.

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

Line model (usage-scope, cross-reference, reference-check):
  A file is read as UTF-8, a leading byte order mark dropped, and split
  on `\\n` alone (a `\\r\\n` pair loses its `\\r`, a lone `\\r` stays in
  its line), so every `line` matches `grep -n`. The frontmatter is a
  leading `---` ... `---` block. A fence opens on a line of three or more
  backticks or tildes (any indent) and closes on the same character
  repeated at least as often with nothing after it; an unclosed fence
  runs to the end of the file. A heading is an ATX heading outside the
  frontmatter and fenced code: at most three spaces of indent (four make
  indented code), one to six `#`, then a space, a tab or the end of the
  line, with a closing `#` sequence dropped from its text. Its section
  runs to the line before the next heading of the same or a higher level.

Usage scope:
  Single-body (no `*.md` file under `references/`): the section of the
  first heading whose text is a usage synonym (REQUIRED_SYNONYMS["usage"],
  the anchor coherence-check.md §2.1 matches), fenced code inside it
  included. The Key Exports list is outside it, so listing an export
  there does not count as using it. With no such heading the scope is
  empty and every export is zero-usage.
  Split-body (a `*.md` file under `references/`): every usage-family
  section of SKILL.md (the headings in USAGE_FAMILY_HEADINGS: every usage
  synonym plus `Key API Summary`, `Pattern Surface` and `Key Exports`,
  full text, case-insensitive, any level), fenced code inside them
  included, plus every `*.md` file under `references/` at any depth, in
  path order. Overlapping sections count each line once.
  --body auto (the default) decides by the `references/` test alone.
  coherence-check.md §2.4 also calls a package with `references/`
  single-body when its `## Full*` sections carry real content rather than
  stubs: that is the caller's judgment, passed as --body single.

Export match:
  The name as a fixed string, case-sensitive, never inside a longer
  identifier: on a side where the name ends in a letter, digit, `_` or
  `$`, the next character may not be one of those. So `$state` and `a.b`
  match only themselves (no shell expansion, no regex wildcard), `get`
  does not match `getAll`, and `.then` still matches `promise.then`.
  `count` is the number of matching lines (the `grep -c` count).

Citation match:
  A skill's name and aliases, case-insensitive, never inside a longer
  name: on a side where the term ends in a letter, digit, `_` or `-`, the
  next character may not be one of those. So `React` and `react/client`
  cite `react`, while `react-dom`, `preact` and `reactive` do not. The
  whole SKILL.md is searched, frontmatter and code included, and a skill
  never cites itself. A hit's `substring` is the match as written (the
  longest term at the leftmost match of its line) and its `excerpt` that
  line around all of its matches. A match is literal, not a judgment: a
  skill named after a common word (`next`, `requests`) also matches
  prose such as `the next step` or a `sending requests` description, so
  the caller picks from `hits[]` the line it quotes as the citation.

Reference extraction:
  Outside the frontmatter and fenced code, two forms count:
  - link: a markdown link, image or reference definition (`[id]: target`,
    footnotes aside) outside inline code, unless its target is a URL
    (`scheme:` or `//`), a bare `#anchor`, or holds a placeholder or glob
    character (`{}<>*?$`). The target may hold one level of balanced
    parentheses; its backslash escapes and entity references are
    resolved, the `#fragment` and `?query` dropped and `%XX` escapes
    decoded.
  - mention: a `references/`, `scripts/` or `assets/` path, optionally
    `./`-prefixed, in prose or inline code, not preceded by a letter,
    digit, `_`, `-`, `.`, `/`, `@` or `:` (so `src/assets/x`, URLs and
    `[SRC:scripts/x.sh:L1]` provenance citations are not references).
    Trailing punctuation, a `#fragment` and a `:L12` line suffix are
    dropped; a bare folder or a placeholder is not a reference. A
    `scripts/` or `assets/` mention counts only when the package has that
    folder or it sits in a section whose heading starts with `Scripts`
    (the Scripts & Assets section): elsewhere it can name a path in the
    reader's own project, as framework docs do.
  A target under `scripts/` or `assets/` is `script-asset`; any other
  target is `file-path`.
  Known limits: a mention is taken as written (no escape is resolved) and
  ends at whitespace, so `references/my file.md` in inline code reads as
  `references/my`; parentheses nest one level deep in a link target; and
  a one-word line such as `[Note]: see-below` is a reference definition,
  as CommonMark reads it.

Exit codes:
  0: operation succeeded
  1: user error (file not found or unreadable, malformed JSON input, both
     --skills and --pairs on stdin, a cross-reference --skills-root that
     is not a directory)
  2: usage error (argparse: missing or unknown argument or subcommand)
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote


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
# Line model shared by usage-scope, cross-reference and reference-check
# --------------------------------------------------------------------------


_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
# A CommonMark ATX heading. `_HEADING_RE` stays as it is for `scan` and
# skf-shard-body.py, which import it.
_BODY_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_CLOSING_HASHES_RE = re.compile(r"(?:^|[ \t]+)#+$")


def _split_lines(text: str) -> list[str]:
    """Split on newlines only, so line numbers match `grep -n`.

    `str.splitlines()` also breaks on form feeds and U+2028, which would
    shift every later line number away from what an editor or grep shows.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _frontmatter_end(lines: list[str]) -> int:
    """Index of the first body line, past a leading `---` ... `---` block."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def _code_lines(lines: list[str], start: int = 0) -> list[bool]:
    """Flag every fence line and every line between a fence and its close.

    A backtick line whose info string holds a backtick is inline code, not
    a fence (CommonMark), and an unclosed fence runs to the end of the file.
    """
    code = [False] * len(lines)
    fence: tuple[str, int] | None = None
    for i in range(start, len(lines)):
        m = _FENCE_RE.match(lines[i])
        if fence is None:
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = (m.group(1)[0], len(m.group(1)))
                code[i] = True
            continue
        code[i] = True
        if (
            m
            and m.group(1)[0] == fence[0]
            and len(m.group(1)) >= fence[1]
            and not m.group(2).strip()
        ):
            fence = None
    return code


def _body_headings(
    lines: list[str], start: int, code: list[bool]
) -> list[tuple[int, int, str]]:
    """(index, level, text) of each heading outside frontmatter and code.

    A `#` line indented four or more spaces is indented code, and a
    closing sequence (`## Usage ##`) is not part of the text.
    """
    headings: list[tuple[int, int, str]] = []
    for i in range(start, len(lines)):
        if code[i]:
            continue
        m = _BODY_HEADING_RE.match(lines[i])
        if m:
            text = _CLOSING_HASHES_RE.sub("", m.group(2) or "").strip()
            headings.append((i, len(m.group(1)), text))
    return headings


def _section_spans(
    headings: list[tuple[int, int, str]], total: int, wanted
) -> list[tuple[int, int, str]]:
    """(start, end, heading) of each section whose heading `wanted` accepts.

    A section runs from its heading line to the line before the next
    heading of the same or a higher level, or to the end of the file;
    `end` is exclusive.
    """
    spans: list[tuple[int, int, str]] = []
    for pos, (idx, level, text) in enumerate(headings):
        if not wanted(text):
            continue
        end = total
        for next_idx, next_level, _ in headings[pos + 1:]:
            if next_level <= level:
                end = next_idx
                break
        spans.append((idx, end, text))
    return spans


def _bounded(term: str, word_chars: str) -> str:
    """Regex for `term` as a fixed string that is never part of a longer word.

    `word_chars` is a character-class body such as `\\w$`. The guard only
    applies on a side where the term itself ends in such a character, so
    `.then` still matches inside `promise.then`.
    """
    word = re.compile(f"[{word_chars}]")
    body = re.escape(term)
    if word.match(term[0]):
        body = f"(?<![{word_chars}])" + body
    if word.match(term[-1]):
        body += f"(?![{word_chars}])"
    return body


# --------------------------------------------------------------------------
# Usage scope: per-export usage counts
# --------------------------------------------------------------------------


# coherence-check.md §2.4 counts a split-body skill over every usage-family
# heading: the usage synonyms above plus the api-surface headings that carry
# call examples in the SKF templates. A single-body skill counts over its
# first usage-synonym section alone, so an export does not count as used
# because Key Exports lists it. Derived from REQUIRED_SYNONYMS so a usage
# synonym added there joins both scopes.
USAGE_FAMILY_HEADINGS: list[str] = [
    *REQUIRED_SYNONYMS["usage"],
    "Key API Summary",
    "Pattern Surface",
    "Key Exports",
]

# The --body choices after `auto` is resolved.
_BODIES = ("single", "split")

# Characters that continue an identifier in the languages SKF documents
# (`$` for JS/TS names such as `$state`).
_IDENT_CHARS = r"\w$"


def usage_scope(
    skill_text: str,
    reference_texts: list[tuple[str, str]],
    exports: list[dict],
    kinds: set[str] | None = None,
    skill_label: str = "SKILL.md",
    body: str | None = None,
) -> dict:
    """Count the lines that use each export over the usage scope.

    `reference_texts` holds (relative path, text) for each reference file,
    in path order. `exports` holds {"name", "kind"} dicts (kind may be
    None); `kinds`, when given, drops the exports whose kind is known and
    not listed. `body` is "single" or "split"; None picks "split" when
    there is a reference text and "single" otherwise, and a single-body
    scope reads no reference text. Returns the structure described in the
    module docstring, without `warnings` (the caller owns file reading).
    """
    if body is None:
        body = "split" if reference_texts else "single"
    if body not in _BODIES:
        raise ValueError(f"body must be one of {_BODIES}, not {body!r}")
    lines = _split_lines(skill_text)
    start = _frontmatter_end(lines)
    code = _code_lines(lines, start)
    headings = _body_headings(lines, start, code)
    if body == "single":
        usage = {h.lower() for h in REQUIRED_SYNONYMS["usage"]}
        spans = _section_spans(
            headings, len(lines), lambda text: text.lower() in usage
        )[:1]
        reference_texts = []
    else:
        family = {h.lower() for h in USAGE_FAMILY_HEADINGS}
        spans = _section_spans(
            headings, len(lines), lambda text: text.lower() in family
        )
    in_scope = sorted({i for s, e, _ in spans for i in range(s, e)})

    # (file, 1-based line, text) in scope order: SKILL.md first, then the
    # reference files, so `first_hit` is deterministic.
    corpus: list[tuple[str, int, str]] = [
        (skill_label, i + 1, lines[i]) for i in in_scope
    ]
    for rel, text in reference_texts:
        corpus.extend(
            (rel, n, line) for n, line in enumerate(_split_lines(text), start=1)
        )

    selected = {
        (e["name"], e["kind"])
        for e in exports
        if kinds is None or e["kind"] is None or e["kind"] in kinds
    }
    results: list[dict] = []
    for name, kind in sorted(selected, key=lambda k: (k[0], k[1] or "")):
        pattern = re.compile(_bounded(name, _IDENT_CHARS))
        count = 0
        first_hit = None
        for label, lineno, line in corpus:
            # the substring test is a cheap pre-filter; the regex decides
            if name in line and pattern.search(line):
                count += 1
                if first_hit is None:
                    first_hit = {"file": label, "line": lineno}
        results.append({
            "name": name,
            "kind": kind,
            "count": count,
            "first_hit": first_hit,
        })

    return {
        "scope": {
            "body": body,
            "sections": [
                {"heading": text, "line": s + 1, "end_line": e}
                for s, e, text in spans
            ],
            "reference_files": [rel for rel, _ in reference_texts],
        },
        "exports": results,
        "zero_usage": [
            {"name": r["name"], "kind": r["kind"]}
            for r in results
            if r["count"] == 0
        ],
    }


# --------------------------------------------------------------------------
# Cross-reference: literal citations between skills
# --------------------------------------------------------------------------


# Characters that continue a package or skill name (`react-dom` is not
# `react`).
_NAME_CHARS = r"\w-"
_EXCERPT_CONTEXT = 60


def _citation_pattern(terms: list[str]) -> re.Pattern[str]:
    """One case-insensitive regex for a skill's terms, longest term first."""
    ordered = sorted(terms, key=lambda t: (-len(t), t.lower()))
    return re.compile(
        "|".join(_bounded(t, _NAME_CHARS) for t in ordered), re.IGNORECASE
    )


def _excerpt(line: str, start: int, end: int) -> str:
    """The line around [start, end), whitespace collapsed, `...` at a cut.

    [start, end) runs from a line's first match to its last, so every
    match on the line shows.
    """
    lo = max(0, start - _EXCERPT_CONTEXT)
    hi = min(len(line), end + _EXCERPT_CONTEXT)
    text = " ".join(line[lo:hi].split())
    if lo > 0:
        text = "..." + text
    if hi < len(line):
        text += "..."
    return text


def cross_references(
    skills: list[dict], pairs: list[tuple[str, str]] | None = None
) -> dict:
    """Find where each skill's SKILL.md literally cites another skill.

    `skills` holds {"name", "terms", "text"} dicts, `text` None when the
    SKILL.md could not be read (the skill can still be cited). `pairs`,
    when given, keeps only the citations between those unordered pairs and
    adds `pairs[]`. Each citation lists every citing line in `hits`, since
    the first one can be a common word rather than the citation. Returns
    citations, edges, pairs and pair warnings.
    """
    patterns = {s["name"]: _citation_pattern(s["terms"]) for s in skills}
    names = sorted(patterns)
    wanted: set[tuple[str, str]] | None = None
    if pairs is not None:
        wanted = set()
        for a, b in pairs:
            wanted.update({(a, b), (b, a)})

    citations: list[dict] = []
    for source in sorted(skills, key=lambda s: s["name"]):
        if source["text"] is None:
            continue
        lines = _split_lines(source["text"])
        for target in names:
            if target == source["name"]:
                continue
            if wanted is not None and (source["name"], target) not in wanted:
                continue
            pattern = patterns[target]
            hits: list[dict] = []
            for lineno, line in enumerate(lines, start=1):
                matches = list(pattern.finditer(line))
                if not matches:
                    continue
                hits.append({
                    "line": lineno,
                    "substring": matches[0].group(0),
                    "excerpt": _excerpt(
                        line, matches[0].start(), matches[-1].end()
                    ),
                })
            if not hits:
                continue
            citations.append({
                "from": source["name"],
                "to": target,
                "substring": hits[0]["substring"],
                "line": hits[0]["line"],
                "count": len(hits),
                "excerpt": hits[0]["excerpt"],
                "hits": hits,
            })

    result: dict = {
        "citations": citations,
        "edges": [[c["from"], c["to"]] for c in citations],
    }
    warnings: list[str] = []
    if pairs is not None:
        cited = {(c["from"], c["to"]) for c in citations}
        rows: list[dict] = []
        for a, b in sorted(pairs):
            for name in (a, b):
                if name not in patterns:
                    warnings.append(
                        f"{name}: named in --pairs but not in --skills"
                    )
            rows.append({
                "library_a": a,
                "library_b": b,
                "a_cites_b": (a, b) in cited,
                "b_cites_a": (b, a) in cited,
                "cited": (a, b) in cited or (b, a) in cited,
            })
        result["pairs"] = rows
    # dict.fromkeys keeps the first of repeated warnings, in order
    result["warnings"] = list(dict.fromkeys(warnings))
    return result


# --------------------------------------------------------------------------
# Reference check: file, script and asset references
# --------------------------------------------------------------------------


# A link title is "...", '...' or (...); a reference definition must end
# after its title, so a prose line such as `[Note]: see below` is not one.
_LINK_TITLE = r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?"
# A link destination is `<...>`, or a run with no whitespace whose
# parentheses are backslash-escaped or balanced one level deep
# (`references/a_(1).md`). A backslash always takes the next character.
_DEST_CHAR = r"(?:\\\S|[^\s()\\])"
_LINK_RE = re.compile(
    rf"!?\[[^\]\n]*\]\(\s*(<[^>\n]*>|(?:{_DEST_CHAR}|\({_DEST_CHAR}*\))+)"
    + _LINK_TITLE
    + r"\s*\)"
)
_REF_DEFINITION_RE = re.compile(
    r"^\s{0,3}\[([^\]\n]+)\]:\s*(<[^>\n]*>|\S+)" + _LINK_TITLE + r"\s*$"
)
_MENTION_RE = re.compile(
    r"(?<![\w.:/@-])(?:\./)?(references|scripts|assets)/[^\s`'\"()|,;]+"
)
# Backslash-escaped ASCII punctuation, or an entity reference: CommonMark
# resolves both inside a link destination.
_ESCAPE_RE = re.compile(
    r"\\([!-/:-@\[-`{-~])"
    r"|&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]*);"
)
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+:")
_LINE_SUFFIX_RE = re.compile(r":L?\d+(?:-L?\d+)?$")
_PLACEHOLDER_CHARS = frozenset("{}<>*?$")
_MENTION_TRAILING = ".,:;!?*_~>]}"
_PACKAGE_FOLDERS = ("scripts", "assets")


def _inline_code_spans(line: str) -> list[tuple[int, int]]:
    """[start, end) of each inline code span: a backtick run closed by an
    equal run. An unmatched run is literal text."""
    spans: list[tuple[int, int]] = []
    i, n = 0, len(line)
    while i < n:
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run = j - i
        k = j
        close = -1
        while k < n:
            if line[k] != "`":
                k += 1
                continue
            m = k
            while m < n and line[m] == "`":
                m += 1
            if m - k == run:
                close = k
                break
            k = m
        if close == -1:
            i = j
            continue
        spans.append((i, close + run))
        i = close + run
    return spans


def _mask(line: str, spans: list[tuple[int, int]]) -> str:
    """Blank out each span, keeping every offset in place."""
    chars = list(line)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _unescape(text: str) -> str:
    """Resolve backslash escapes and entity references in one pass, so an
    escaped `\\&amp;` stays `&amp;`."""
    return _ESCAPE_RE.sub(
        lambda m: m.group(1) or html.unescape(m.group(0)), text
    )


def _clean_link(dest: str) -> str | None:
    """The local path a link destination names, or None when it names none."""
    if dest.startswith("<") and dest.endswith(">"):
        dest = dest[1:-1].strip()
    dest = _unescape(dest)
    if (
        not dest
        or dest.startswith(("#", "//"))
        or _URL_SCHEME_RE.match(dest)
    ):
        return None
    dest = unquote(dest.split("#", 1)[0].split("?", 1)[0])
    if not dest or any(c in _PLACEHOLDER_CHARS for c in dest):
        return None
    return dest


def _clean_mention(token: str) -> str | None:
    """The path a bare mention names, or None for a folder or placeholder."""
    token = _LINE_SUFFIX_RE.sub("", token.rstrip(_MENTION_TRAILING))
    token = token.split("#", 1)[0].rstrip(_MENTION_TRAILING)
    if token.endswith("/") or any(c in _PLACEHOLDER_CHARS for c in token):
        return None
    return token


def _reference_type(target: str) -> str:
    rel = target
    while rel.startswith("./"):
        rel = rel[2:]
    if rel.startswith(tuple(f"{folder}/" for folder in _PACKAGE_FOLDERS)):
        return "script-asset"
    return "file-path"


def extract_references(
    text: str, package_folders: frozenset[str] = frozenset()
) -> list[dict]:
    """List the file, script and asset references in a SKILL.md body.

    `package_folders` names the folders among `scripts` and `assets` that
    the skill package has; a bare mention of another one counts only
    inside the Scripts & Assets section. Returns [{"line", "form",
    "target"}] in document order (before any existence check).
    """
    lines = _split_lines(text)
    start = _frontmatter_end(lines)
    code = _code_lines(lines, start)
    scripts_section = {
        i
        for s, e, _ in _section_spans(
            _body_headings(lines, start, code),
            len(lines),
            lambda heading: heading.lower().startswith("scripts"),
        )
        for i in range(s, e)
    }

    refs: list[dict] = []
    for idx in range(start, len(lines)):
        if code[idx]:
            continue
        line = lines[idx]
        # links never sit inside inline code; mentions may
        plain = _mask(line, _inline_code_spans(line))
        found: list[tuple[int, str, str | None]] = []
        link_spans: list[tuple[int, int]] = []

        definition = _REF_DEFINITION_RE.match(plain)
        if definition and not definition.group(1).startswith("^"):
            target = _clean_link(definition.group(2))
            found.append((definition.start(2), "link", target))
            link_spans.append((0, definition.end()))
        for m in _LINK_RE.finditer(plain):
            found.append((m.start(1), "link", _clean_link(m.group(1))))
            link_spans.append(m.span())

        for m in _MENTION_RE.finditer(_mask(line, link_spans)):
            folder = m.group(1)
            if (
                folder in _PACKAGE_FOLDERS
                and folder not in package_folders
                and idx not in scripts_section
            ):
                continue
            found.append((m.start(), "mention", _clean_mention(m.group(0))))

        for _, form, target in sorted(found, key=lambda f: f[0]):
            if target is not None:
                refs.append({"line": idx + 1, "form": form, "target": target})
    return refs


def scripts_assets_section(text: str, skill_dir: Path) -> dict:
    """The package's scripts/ and assets/ folders and its Scripts & Assets heading."""
    lines = _split_lines(text)
    start = _frontmatter_end(lines)
    heading = next(
        (
            {"heading": t, "line": idx + 1}
            for idx, _, t in _body_headings(lines, start, _code_lines(lines, start))
            if t.lower().startswith("scripts")
        ),
        None,
    )
    folders = sorted(f for f in _PACKAGE_FOLDERS if (skill_dir / f).is_dir())
    return {
        "folders": folders,
        "section": heading,
        "missing": bool(folders) and heading is None,
    }


def _realpath(path: str) -> str:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        # a name the OS rejects (an embedded NUL, say) resolves nowhere
        return os.path.abspath(path)


def _within(path: str, root: str) -> bool:
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def check_references(
    refs: list[dict],
    skill_dir: str,
    source_root: str | None = None,
    skills_root: str | None = None,
) -> dict:
    """Resolve each reference and check it exists inside an allowed root.

    A source or skills root that is not a directory becomes a warning.
    """
    warnings = [
        f"--{flag} is not a directory: {path}"
        for flag, path in (
            ("source-root", source_root),
            ("skills-root", skills_root),
        )
        if path and not os.path.isdir(path)
    ]
    roots = [("skill", _realpath(skill_dir))]
    if source_root:
        roots.append(("source", _realpath(source_root)))
    if skills_root:
        roots.append(("skills", _realpath(skills_root)))
    base = roots[0][1]

    references: list[dict] = []
    counts = {"total": 0, "ok": 0, "missing": 0, "escapes": 0}
    seen: set[tuple[int, str]] = set()
    for ref in refs:
        canonical = _realpath(os.path.join(base, ref["target"]))
        key = (ref["line"], os.path.normcase(canonical))
        if key in seen:
            continue
        seen.add(key)
        root = next(
            (label for label, path in roots if _within(canonical, path)), None
        )
        if root is None:
            status = "escapes"
        elif os.path.exists(canonical):
            status = "ok"
        else:
            status = "missing"
        counts["total"] += 1
        counts[status] += 1
        references.append({
            "line": ref["line"],
            "type": _reference_type(ref["target"]),
            "form": ref["form"],
            "target": ref["target"],
            "canonical": canonical,
            "status": status,
            "root": root,
        })

    labels = dict(roots)
    return {
        "roots": {
            "skill": labels["skill"],
            "source": labels.get("source"),
            "skills": labels.get("skills"),
        },
        "references": references,
        "counts": counts,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_markdown(path: Path, errors: str = "strict") -> str:
    """The file as UTF-8 for the line model: a leading byte order mark is
    dropped, and every `\\r` is kept, since `read_text` would turn a lone
    `\\r` into a line break that `grep -n` does not count."""
    return path.read_bytes().decode("utf-8-sig", errors=errors)


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
            "scripts_assets": scripts_assets_section(text, skill_md.parent),
        }

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


class UserError(Exception):
    """A caller-facing input error: exit code 1."""


def _load_skill_md(raw: str) -> tuple[Path, str]:
    skill_md = Path(raw)
    if not skill_md.is_file():
        raise UserError(f"file not found: {skill_md}")
    try:
        return skill_md, _read_markdown(skill_md)
    except (OSError, UnicodeDecodeError) as exc:
        raise UserError(f"cannot read {skill_md}: {exc}") from exc


def _read_json(source: str, label: str):
    """Parse JSON from a file path, or from stdin when `source` is '-'."""
    if source == "-":
        try:
            text = sys.stdin.read()
        except OSError as exc:
            raise UserError(
                f"failed to read {label} from stdin: {exc}"
            ) from exc
    else:
        path = Path(source)
        if not path.is_file():
            raise UserError(f"{label} file not found: {path}")
        try:
            text = _read_text(path)
        except (OSError, UnicodeDecodeError) as exc:
            raise UserError(
                f"failed to read {label} file {path}: {exc}"
            ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UserError(f"malformed JSON in {label} input: {exc}") from exc


def parse_exports(payload) -> list[dict]:
    """Normalize the --exports JSON into [{"name", "kind"}] dicts.

    Accepts a list of names or {"name", "kind"} objects, an object with an
    `exports` list, or the validate-inventory.py result (`inventory`).
    """
    items = payload
    if isinstance(payload, dict):
        if "exports" in payload:
            items = payload["exports"]
        elif isinstance(payload.get("inventory"), dict):
            items = payload["inventory"].get("exports")
    if not isinstance(items, list):
        raise UserError(
            "--exports must be a JSON array, an object with an `exports` "
            "array, or a validate-inventory.py result"
        )
    exports: list[dict] = []
    for idx, item in enumerate(items):
        if isinstance(item, str):
            name, kind = item, None
        elif isinstance(item, dict):
            name, kind = item.get("name"), item.get("kind")
        else:
            raise UserError(
                f"--exports[{idx}] must be a name or an object; got {item!r}"
            )
        # surrounding whitespace is never part of a name, and a stray space
        # would make every line miss
        if not isinstance(name, str) or not name.strip():
            raise UserError(f"--exports[{idx}] needs a non-empty `name`")
        if kind is not None and not isinstance(kind, str):
            raise UserError(f"--exports[{idx}] `kind` must be a string")
        kind = (kind or "").strip() or None
        exports.append({"name": name.strip(), "kind": kind})
    return exports


def parse_kinds(raw: str) -> set[str]:
    kinds = {k.strip() for k in raw.split(",") if k.strip()}
    if not kinds:
        raise UserError("--kinds needs at least one kind, e.g. function,method")
    return kinds


# The names an skf-enumerate-stack-skills.py inventory entry gives the
# repository and the folder its skill was built from.
SOURCE_ALIAS_KEYS = ("source_repo_basename", "source_root_basename")


def _source_aliases(item: dict) -> list[str]:
    """The entry's SOURCE_ALIAS_KEYS values that are non-empty strings."""
    found: list[str] = []
    for key in SOURCE_ALIAS_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
    return found


def parse_skill_entries(payload) -> list[dict]:
    """Normalize the --skills JSON into [{"name", "file", "terms"}] dicts.

    `file` is the SKILL.md path as given (`skill_md`, else `path` joined
    with SKILL.md); `terms` is the name plus its aliases, case-insensitive
    duplicates dropped. An entry's source basenames (SOURCE_ALIAS_KEYS)
    are aliases too, unless another entry has the same term as its name,
    an alias or a source basename: one word would then cite two skills.
    """
    items = payload.get("skills") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise UserError(
            "--skills must be a JSON array of skill entries or an object "
            "with a `skills` array"
        )
    parsed: list[tuple[str, str, list[str], list[str]]] = []
    seen: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise UserError(f"--skills[{idx}] must be an object; got {item!r}")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise UserError(f"--skills[{idx}] needs a non-empty `name`")
        name = name.strip()
        if name in seen:
            raise UserError(f"--skills names `{name}` twice")
        seen.add(name)
        skill_md, folder = item.get("skill_md"), item.get("path")
        if isinstance(skill_md, str) and skill_md:
            file = skill_md
        elif isinstance(folder, str) and folder:
            file = os.path.join(folder, "SKILL.md")
        else:
            raise UserError(
                f"--skills[{idx}] ({name}) needs `skill_md` or `path`"
            )
        aliases = item.get("aliases") or []
        if not isinstance(aliases, list) or not all(
            isinstance(a, str) for a in aliases
        ):
            raise UserError(
                f"--skills[{idx}] ({name}) `aliases` must be strings"
            )
        parsed.append((name, file, aliases, _source_aliases(item)))

    # How many entries hold each term, case-insensitively.
    owners: dict[str, int] = {}
    for name, _file, aliases, source in parsed:
        held = {t.strip().lower() for t in (name, *aliases, *source) if t.strip()}
        for term in held:
            owners[term] = owners.get(term, 0) + 1

    entries: list[dict] = []
    for name, file, aliases, source in parsed:
        unique = [term for term in source if owners[term.lower()] == 1]
        terms: dict[str, str] = {}
        for term in (name, *aliases, *unique):
            term = term.strip()
            if term:
                terms.setdefault(term.lower(), term)
        entries.append(
            {"name": name, "file": file, "terms": list(terms.values())}
        )
    return entries


def parse_pairs(payload) -> list[tuple[str, str]]:
    """Normalize the --pairs JSON into unique (a, b) tuples."""
    items = payload.get("pairs") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise UserError(
            "--pairs must be a JSON array of pairs or an object with a "
            "`pairs` array"
        )
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()
    for idx, item in enumerate(items):
        if isinstance(item, list) and len(item) == 2:
            a, b = item
        elif isinstance(item, dict):
            a, b = item.get("library_a"), item.get("library_b")
        else:
            raise UserError(
                f"--pairs[{idx}] must be [a, b] or "
                f"{{\"library_a\", \"library_b\"}}; got {item!r}"
            )
        if not (isinstance(a, str) and a and isinstance(b, str) and b):
            raise UserError(f"--pairs[{idx}] needs two non-empty skill names")
        if a == b:
            raise UserError(f"--pairs[{idx}] pairs `{a}` with itself")
        key = frozenset((a, b))
        if key not in seen:
            seen.add(key)
            pairs.append((a, b))
    return pairs


def _reference_paths(skill_dir: Path) -> list[Path]:
    """Every `references/**/*.md` under the skill folder, in path order."""
    ref_dir = skill_dir / "references"
    if not ref_dir.is_dir():
        return []
    paths = [
        Path(root) / name
        for root, _dirs, files in os.walk(ref_dir)
        for name in files
        if name.lower().endswith(".md")
    ]
    return sorted(paths, key=lambda p: p.relative_to(skill_dir).as_posix())


def _read_reference_files(
    skill_dir: Path, paths: list[Path]
) -> tuple[list[tuple[str, str]], list[str]]:
    """(relative path, text) of each reference file, in the order given.

    A file that cannot be read becomes a warning; undecodable bytes are
    replaced, so one bad byte never hides a whole file from the count.
    """
    texts: list[tuple[str, str]] = []
    warnings: list[str] = []
    for path in paths:
        rel = path.relative_to(skill_dir).as_posix()
        try:
            texts.append((rel, _read_markdown(path, errors="replace")))
        except OSError as exc:
            warnings.append(f"{rel}: cannot read: {exc}")
    return texts, warnings


def _emit(payload: dict) -> int:
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_usage_scope(args: argparse.Namespace) -> int:
    skill_md, text = _load_skill_md(args.skill_md)
    exports = parse_exports(_read_json(args.exports, "--exports"))
    kinds = parse_kinds(args.kinds) if args.kinds is not None else None
    paths = _reference_paths(skill_md.parent)
    body = args.body
    if body == "auto":
        # a reference file that cannot be read still makes the body split
        body = "split" if paths else "single"
    references: list[tuple[str, str]] = []
    warnings: list[str] = []
    if body == "split":
        references, warnings = _read_reference_files(skill_md.parent, paths)
    payload = usage_scope(
        text,
        references,
        exports,
        kinds=kinds,
        skill_label=skill_md.name,
        body=body,
    )
    payload["warnings"] = warnings
    return _emit(payload)


def _cmd_cross_reference(args: argparse.Namespace) -> int:
    if args.skills == "-" and args.pairs == "-":
        raise UserError(
            "--skills and --pairs cannot both read from stdin ('-')"
        )
    # a wrong root would turn every skill into a not-found warning and
    # leave nothing to cite, which reads like a clean result
    if args.skills_root is not None and not Path(args.skills_root).is_dir():
        raise UserError(
            f"--skills-root is not a directory: {args.skills_root}"
        )
    entries = parse_skill_entries(_read_json(args.skills, "--skills"))
    pairs = None
    if args.pairs is not None:
        pairs = parse_pairs(_read_json(args.pairs, "--pairs"))

    skills: list[dict] = []
    warnings: list[str] = []
    for entry in entries:
        skill_md = Path(entry["file"])
        if args.skills_root and not skill_md.is_absolute():
            skill_md = Path(args.skills_root) / skill_md
        text = None
        if not skill_md.is_file():
            warnings.append(f"{entry['name']}: SKILL.md not found: {skill_md}")
        else:
            try:
                text = _read_markdown(skill_md)
            except (OSError, UnicodeDecodeError) as exc:
                warnings.append(
                    f"{entry['name']}: cannot read {skill_md}: {exc}"
                )
        skills.append(
            {"name": entry["name"], "terms": entry["terms"], "text": text}
        )

    payload = cross_references(skills, pairs)
    payload["warnings"] = warnings + payload["warnings"]
    return _emit(payload)


def _cmd_reference_check(args: argparse.Namespace) -> int:
    skill_md, text = _load_skill_md(args.skill_md)
    skill_dir = skill_md.parent
    package_folders = frozenset(
        folder for folder in _PACKAGE_FOLDERS if (skill_dir / folder).is_dir()
    )
    refs = extract_references(text, package_folders)
    payload = check_references(
        refs, str(skill_dir), args.source_root, args.skills_root
    )
    warnings = payload.pop("warnings")
    payload["scripts_assets"] = scripts_assets_section(text, skill_dir)
    payload["warnings"] = warnings
    return _emit(payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-scan-skill-md-structure",
        description=(
            "Deterministic structural scans for SKILL.md: fence balance, "
            "bare opening fences, table column drift, required-section "
            "presence (case-insensitive synonym match), export usage counts "
            "over the usage sections, literal citations between skills, "
            "and file, script and asset reference checks."
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

    p_usage = sub.add_parser(
        "usage-scope",
        help=(
            "count the lines that use each export in the usage sections "
            "(and references/**/*.md for a split-body skill)"
        ),
    )
    p_usage.add_argument("skill_md", help="path to a SKILL.md file")
    p_usage.add_argument(
        "--exports",
        required=True,
        help=(
            "path to the exports JSON, or '-' for stdin. Shape: "
            '["<name>", ...], [{"name": "...", "kind": "..."}, ...], '
            '{"exports": [...]} or {"inventory": {"exports": [...]}}'
        ),
    )
    p_usage.add_argument(
        "--kinds",
        help=(
            "comma-separated kinds to count, e.g. function,method; an "
            "export given without a kind is always counted"
        ),
    )
    p_usage.add_argument(
        "--body",
        choices=("auto", *_BODIES),
        default="auto",
        help=(
            "single: the first usage-synonym section; split: every "
            "usage-family section plus references/**/*.md; auto (the "
            "default): split when the package has a references/**/*.md "
            "file, else single"
        ),
    )
    p_usage.set_defaults(func=_cmd_usage_scope)

    p_xref = sub.add_parser(
        "cross-reference",
        help=(
            "list the literal citations of each skill's name or aliases "
            "in the other skills' SKILL.md"
        ),
    )
    p_xref.add_argument(
        "--skills",
        required=True,
        help=(
            "path to the skills JSON, or '-' for stdin. Shape: "
            '[{"name": "...", "skill_md" | "path": "...", "aliases": [...]}] '
            'or {"skills": [...]} (the skf-enumerate-stack-skills.py output, '
            "whose source basenames a single skill holds count as aliases)"
        ),
    )
    p_xref.add_argument(
        "--skills-root",
        help=(
            "folder that relative `path` and `skill_md` entries resolve "
            "against"
        ),
    )
    p_xref.add_argument(
        "--pairs",
        help=(
            "path to a pairs JSON, or '-' for stdin, that limits the "
            'citations to those pairs. Shape: [["<a>", "<b>"], ...], '
            '[{"library_a": "...", "library_b": "..."}] or {"pairs": [...]}'
        ),
    )
    p_xref.set_defaults(func=_cmd_cross_reference)

    p_refs = sub.add_parser(
        "reference-check",
        help=(
            "check that each file, script and asset reference exists and "
            "resolves inside the allowed roots"
        ),
    )
    p_refs.add_argument("skill_md", help="path to a SKILL.md file")
    p_refs.add_argument(
        "--source-root",
        help=(
            "the skill's extraction tree (metadata.json source_root), a "
            "second allowed root"
        ),
    )
    p_refs.add_argument(
        "--skills-root",
        help=(
            "the skills output folder, an allowed root for a stack skill "
            "whose references reach its constituent skills"
        ),
    )
    p_refs.set_defaults(func=_cmd_reference_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
