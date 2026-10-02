#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Co-mention Pairs: which loaded skills a document names, and which
pairs of them it names together.

The script reports evidence and the calling step judges it: every pair it
emits is a candidate, never a confirmed integration. Its three subcommands
share one skills input, one matcher and one Markdown reader:

  comention  compose-mode co-mention pairs from an architecture document
             (create-stack-skill detect-integrations.md §2, compose branch)
  mentions   the skills a document names and the pairs it names together
             (refine-architecture gap-analysis.md scope sets and documented
             pairs)
  infer      candidate pairs when there is no architecture document: one
             skill's own docs naming the other, or shared domain keywords,
             never a shared language alone

Skills input (--skills):
  A JSON array. Each entry is a skill name (`"react"`) or an object:
    {"name": "<skill>",            required, non-empty
     "aliases": ["<term>", ...],   other names the skill goes by
     "keywords": ["<kw>", ...],    domain keywords (read by infer only)
     "language": "<language>",     the skill's language, an array of them
                                   (a stack lists its libraries'
                                   languages) or null (infer only)
     "docs": ["<path>", ...]}      the skill's own docs (infer only)
  Other keys are ignored, so an inventory entry, such as a `skills[]` entry
  of skf-enumerate-stack-skills.py, can be passed as it is. Entries with
  the same name merge, languages included. Output names a skill by its
  `name`, never an alias.

Matching:
  A skill is named where one of its terms (its name and each alias)
  appears, case-insensitively, with no word character right before or
  after it: `react` never matches inside `reactive`. For a term that starts
  and ends with a word character, as every skill name does, this is the
  `\\b{term}\\b` rule; a term such as `C++` or `.NET` matches too. The
  words of a multi-word alias may be split by any whitespace, a line break
  included. comention matches each skill on its own, as it always has, so
  `react` also matches the `react` in `react-dom`. mentions and infer read
  each occurrence once, as the longest term that matches there: when the
  skills include both `react` and `react-dom`, the text `react-dom` names
  `react-dom` only. Two skills that share a term are both named by it.

Paragraphs, units and evidence kinds:
  A body paragraph is a run of consecutive non-blank lines that are not
  ATX headers (1-6 `#` then a space or tab); headers of any level end it,
  and the nearest H1/H2 above it governs it. A paragraph splits into
  units: a run of prose, one list item with its continuation lines, one
  table row, or one line of fenced code. A list item or table row inside a
  blockquote (`> - item`) is a unit the same way. Each evidence entry is
  one body paragraph that names both skills of a pair, and its `kind` says
  how:
    co-mention  one unit of the paragraph names both skills
    lead-in     no unit does, but a run of prose names one skill and a list
                item, table row or code line under it (before the next run
                of prose) names the other: "The express server mounts:"
                then "- passport"
    list-only   neither: the two are named only in separate units, such as
                separate list items, table rows or code lines
  A "Tech Stack" table and a "Components" list that each name every
  library give every pair of them two list-only paragraphs. A lead-in
  counts only inside its paragraph: with a blank line before the list, the
  lead-in and the items are two paragraphs. The units are a heuristic, not
  a Markdown parser: consecutive "Label: value" lines with no list marker
  are one run of prose, so they give co-mentions, and a line that starts
  with a number and a period (`2024.`) right after a bullet item is a new
  item, where CommonMark reads a continuation.

  Each entry also shows where the paragraph names the pair: `unit_excerpt`
  is the collapsed text of the first unit that names both (a co-mention),
  or of the lead-in and the item (a lead-in, with `...` for any items
  between them), cut to 240 characters around the two names; when the
  words between the names do not fit, the middle is cut instead, so both
  names stay. `...` marks every cut. `unit_line` is the line (1-based) of
  the first of the two names. Both are null for a list-only entry, while
  `excerpt` and `line` are always the paragraph's start and first line.

Subcommands:
  comention --doc <md-file-or-'-'> --skills <json-file-or-'-'>
      Applies three guards: the matching above; section filtering, where
      paragraphs governed by an H1/H2 header that normalises to one of
      {introduction, overview, glossary, table of contents, references,
      appendix, index} are excluded and heading text is never a source;
      and a two-paragraph minimum, where a pair needs at least two body
      paragraphs that each name both skills. Fenced code is read as body
      text here, as this mode always read it, so its pairs are the ones
      earlier releases emitted: a `#` line inside a fence still counts as
      a header.

      Emit JSON:
        {
          "pairs": [
            {
              "a": "<skill>", "b": "<skill>",
              "paragraph_count": N,
              "comention_count": C,
              "lead_in_count": I,
              "evidence": [{"header": "<governing-header-or-null>",
                            "excerpt": "<collapsed paragraph text>",
                            "line": L,
                            "kind": "co-mention|lead-in|list-only",
                            "unit_line": U-or-null,
                            "unit_excerpt": "<text-naming-both>-or-null"},
                           ...]
            },
            ...
          ],
          "excluded_section_count": M
        }

      Only unordered pairs (a < b lexicographically) with paragraph_count
      >= 2 are emitted, and each is a candidate: comention_count and
      lead_in_count count its co-mention and lead-in entries, so a pair
      with both at 0 was only listed together. `pairs[]` is sorted by
      paragraph_count DESC, then (a, b) ASC, mirroring
      skf-pair-intersect.py. `evidence[]` is in document order.
      `excluded_section_count` is the number of DISTINCT excluded H1/H2
      sections (by normalised header) that governed at least one body
      paragraph: a diagnostic for the caller, not a gate.

  mentions --doc <md-file-or-'-'> --skills <json-file-or-'-'>
      Fenced code blocks are skipped: their lines are neither paragraphs
      nor headings. No section is excluded, and one paragraph is enough.

      Emit JSON:
        {
          "skills": [
            {"name": "<skill>",
             "paragraph_count": N, "heading_count": H, "fenced_count": F,
             "paragraphs": [{"header": "<governing-header-or-null>",
                             "excerpt": "<collapsed paragraph text>",
                             "line": L}, ...]},
            ...
          ],
          "mentioned": ["<skill>", ...],
          "fenced_only": ["<skill>", ...],
          "unmentioned": ["<skill>", ...],
          "candidates": [<a pair shaped as a comention pair>, ...],
          "list_only_pair_count": P,
          "fenced_block_count": B,
          "fenced_blocks": [{"line": L, "info": "<info string>"}, ...]
        }

      `skills[]` has one entry per skill, sorted by name: how many body
      paragraphs, headings (any level) and fenced blocks name it, and each
      such paragraph in document order. `mentioned` lists the skills a
      paragraph or a heading names, `fenced_only` the skills named only
      inside fenced code (a diagram, for example) and `unmentioned` the
      rest; the three are sorted and hold every skill once.

      `candidates[]` holds each pair that a body paragraph names in one
      unit or through a lead-in (comention_count + lead_in_count >= 1),
      with every paragraph that names both as evidence, sorted by
      comention_count DESC, lead_in_count DESC, paragraph_count DESC, then
      (a, b) ASC. `list_only_pair_count` counts the pairs only ever listed
      together, which are not emitted. `fenced_blocks[]` lists the fenced
      blocks skipped, in document order: the line of each opening fence and
      its info string, trimmed (`mermaid` for a Mermaid diagram, "" for
      none).

  infer --skills <json-file-or-'-'> [--top-k N]
      A pair is a candidate on either kind of evidence:
        docs-mention     one skill's docs name the other. Every line of
                         each `docs` file is read, front matter and code
                         included; each occurrence names the skill of the
                         longest term there (see Matching), and an
                         occurrence of the documenting skill's own name or
                         alias names no other skill. A mention is where a
                         documented contract would show, not proof of one:
                         the calling step reads the excerpt and counts a
                         documented contract only when the line says how
                         the two work together, never on a "see also" or
                         "unlike" line.
        shared-keywords  the two skills share a domain keyword. Keywords
                         compare trimmed and lowercased, with runs of
                         whitespace collapsed; a keyword equal to any
                         skill's language does not count.
      A shared language alone never makes a pair: `language` is read only
      to set such keywords aside and to count language_only_pair_count,
      the pairs of skills that share a language and have no evidence.

      Emit JSON:
        {
          "pairs": [
            {
              "a": "<skill>", "b": "<skill>",
              "docs_mention_count": 0-2,
              "shared_keyword_count": K,
              "evidence": [
                {"kind": "docs-mention",
                 "documented_by": "<skill>", "doc": "<path>",
                 "line": L, "line_count": N,
                 "excerpt": "<collapsed line text>"},
                {"kind": "shared-keywords", "keywords": ["<kw>", ...]}
              ]
            },
            ...
          ],
          "truncated": <bool>,
          "total_pairs": T,
          "language_only_pair_count": P
        }

      A docs-mention entry is the first line (docs in the order given)
      where `documented_by` names the other skill, and line_count counts
      every such line. docs_mention_count is how many of the two skills'
      docs name the other. `pairs[]` is sorted by docs_mention_count DESC,
      shared_keyword_count DESC, then (a, b) ASC, and capped at --top-k
      (default 20, the Top-K of detect-integrations.md §1); `truncated` and
      `total_pairs` report the cap as skf-pair-intersect.py does.

CLI examples:
  uv run skf-comention-pairs.py comention --doc arch.md --skills skills.json
  echo '["react","express"]' | uv run skf-comention-pairs.py comention \\
      --doc arch.md --skills -
  uv run skf-comention-pairs.py mentions --doc arch.md --skills skills.json
  uv run skf-comention-pairs.py infer --skills skills.json --top-k 20

Exit codes:
  0  operation succeeded (including: nothing qualifies, so empty lists)
  1  user error (bad JSON, a missing, unreadable or non-UTF-8 file, --doc
     and --skills both on stdin, malformed skills array, negative --top-k)
  2  unexpected internal error
"""

from __future__ import annotations

import argparse
import bisect
import functools
import itertools
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple


# Closed exclusion set — governing H1/H2 headers that normalise to one of
# these drop their paragraphs from co-mention analysis (they typically
# enumerate all libraries without describing an integration).
EXCLUDED_HEADERS = frozenset({
    "introduction",
    "overview",
    "glossary",
    "table of contents",
    "references",
    "appendix",
    "index",
})

# ATX header line: 1-6 leading hashes followed by at least one space/tab.
# A line like `#foo` (no space) is NOT a header per CommonMark and is treated
# as body text. Capture group 1 = hashes (level), group 2 = header text.
_HEADER_RE = re.compile(r"^(#{1,6})[ \t]+(.*)$")

# A fence line: three or more backticks or tildes after any indentation
# (the rule the other SKF Markdown scanners use), then the info string.
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")

# The indentation and blockquote markers (`>`) that can precede a list
# marker or a table row.
_QUOTE_RE = re.compile(r"\s*(?:>\s*)*")

# List item markers, at any indentation so that a nested item is a unit of
# its own, and inside a blockquote: a bullet, or a number with `.` or `)`,
# then whitespace and text.
_BULLET_RE = re.compile(r"^\s*(?:>\s*)*[-*+]\s+\S")
_ORDERED_RE = re.compile(r"^\s*(?:>\s*)*(\d{1,9})[.)]\s+\S")

# A GFM table delimiter row, such as `| --- | :-: |` or `--- | ---`, matched
# whole against the row with its blockquote markers and outer whitespace
# removed: leading and trailing `\s*` here would backtrack quadratically on
# a long run of spaces.
_TABLE_DELIM_RE = re.compile(r"\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?")

_WORD_RE = re.compile(r"\S+")

_EXCERPT_LIMIT = 240

# infer's Top-K cap: the cap detect-integrations.md §1 applies to pairs.
DEFAULT_TOP_K = 20

CO_MENTION = "co-mention"
LEAD_IN = "lead-in"
LIST_ONLY = "list-only"
DOCS_MENTION = "docs-mention"
SHARED_KEYWORDS = "shared-keywords"


class UserError(Exception):
    """A caller-facing input error → exit code 1."""


class Skill(NamedTuple):
    """One loaded skill: the terms that name it (its name first, then its
    aliases) and the inputs only infer reads."""

    name: str
    terms: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    docs: tuple[str, ...] = ()


class Unit(NamedTuple):
    """A part of a paragraph that a pair can share: its first line
    (1-based), its text, and whether it is a run of prose (the others are
    list items, table rows and code lines)."""

    line: int
    text: str
    prose: bool


class Paragraph(NamedTuple):
    """A body paragraph: its governing H1/H2 header (or None), its first
    line (1-based), its text and its units."""

    header: str | None
    line: int
    text: str
    units: tuple[Unit, ...]


class Fence(NamedTuple):
    """A fenced code block: the line of its opening fence (1-based), its
    info string, trimmed, and its content without the fence lines."""

    line: int
    info: str
    text: str


class MarkdownDoc(NamedTuple):
    """What read_markdown finds: body paragraphs, the text of every header
    line, and each fenced block it set apart."""

    paragraphs: list[Paragraph]
    headings: list[str]
    fenced: list[Fence]


# --------------------------------------------------------------------------
# Markdown parsing
# --------------------------------------------------------------------------


def _strip_closing_hashes(text: str) -> str:
    """Remove a closed-ATX trailing run of hashes (e.g. `Overview ##`).

    String methods rather than a `[ \\t]*#+[ \\t]*$` search, which
    backtracks quadratically on a long run of spaces.
    """
    body = text.rstrip(" \t")
    if not body.endswith("#"):
        return text
    return body.rstrip("#").rstrip(" \t")


def normalize_header(text: str) -> str:
    """Normalise a header for exclusion-set comparison: lowercase, collapse
    internal whitespace, strip trailing punctuation."""
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = t.rstrip(".,:;!?").strip()
    return t


def _fence_roles(lines: list[str]) -> list[str | None]:
    """Mark each line of a fenced code block `open`, `body` or `close`, and
    every other line None. A fence closes on a line of the same character,
    at least as long, with nothing after it; an unclosed fence runs to the
    end of the document."""
    roles: list[str | None] = []
    fence: str | None = None
    for line in lines:
        m = _FENCE_RE.match(line)
        if fence is None:
            # A backtick fence's info string cannot hold a backtick.
            if m is not None and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = m.group(1)
                roles.append("open")
            else:
                roles.append(None)
        elif (
            m is not None
            and m.group(1)[0] == fence[0]
            and len(m.group(1)) >= len(fence)
            and not m.group(2).strip()
        ):
            fence = None
            roles.append("close")
        else:
            roles.append("body")
    return roles


def _fenced_blocks(lines: list[str], roles: list[str | None]) -> list[Fence]:
    """Each fenced code block, with its opening line and info string."""
    blocks: list[tuple[int, str, list[str]]] = []
    for idx, (line, role) in enumerate(zip(lines, roles)):
        if role == "open":
            info = _FENCE_RE.match(line).group(2).strip()
            blocks.append((idx + 1, info, []))
        elif role == "body":
            blocks[-1][2].append(line)
    return [Fence(line, info, "\n".join(body)) for line, info, body in blocks]


def _unquote(line: str) -> str:
    """The line without its indentation and blockquote markers."""
    return line[_QUOTE_RE.match(line).end():]


def _is_list_item(line: str) -> bool:
    return bool(_BULLET_RE.match(line) or _ORDERED_RE.match(line))


def _table_rows(lines: list[str], code: list[bool]) -> set[int]:
    """Indexes of a paragraph's table rows: every line that starts with `|`,
    and each GFM table (a header row, its delimiter row, then each line up
    to a list item or code) even when its rows have no leading pipe."""
    rows = {
        i for i, line in enumerate(lines)
        if not code[i] and _unquote(line).startswith("|")
    }
    for i in range(1, len(lines)):
        if (
            code[i] or code[i - 1]
            or "|" not in lines[i] or "|" not in lines[i - 1]
            or not _TABLE_DELIM_RE.fullmatch(_unquote(lines[i]).rstrip())
        ):
            continue
        rows.update((i - 1, i))
        j = i + 1
        while j < len(lines) and not code[j] and not _is_list_item(lines[j]):
            rows.add(j)
            j += 1
    return rows


def _units(lines: list[str], code: list[bool], first: int) -> tuple[Unit, ...]:
    """Split a paragraph's lines, the first of which is line `first` of the
    document, into the units a pair can share: a run of prose, one list item
    with its continuation lines, one table row, or one line of fenced
    code."""
    rows = _table_rows(lines, code)
    units: list[Unit] = []
    start = 0  # index of the open unit's first line
    # What the open unit holds: "prose", "item" (a list item) or None.
    current: str | None = None

    def close(end: int) -> None:
        if current is not None:
            units.append(Unit(
                first + start, "\n".join(lines[start:end]), current == "prose"
            ))

    for i, line in enumerate(lines):
        if code[i] or i in rows:
            close(i)
            current = None
            units.append(Unit(first + i, line, False))
            continue
        ordered = _ORDERED_RE.match(line)
        # A bullet can interrupt running prose; an ordered marker only when
        # it is 1 (CommonMark), so `2024. Then ...` inside prose stays text.
        if _BULLET_RE.match(line) or (
            ordered is not None
            and (current != "prose" or int(ordered.group(1)) == 1)
        ):
            close(i)
            start, current = i, "item"
        elif current is None:
            # Any other line opens a run of prose, or continues the open
            # run or list item.
            start, current = i, "prose"
    close(len(lines))
    return tuple(units)


def read_markdown(doc_text: str, *, skip_fenced: bool) -> MarkdownDoc:
    """Split the document into body paragraphs, headings and fenced blocks.

    Paragraphs are maximal runs of consecutive non-blank, non-header lines,
    separated by blank lines. Header lines of ANY level are never emitted
    as paragraphs (headings are not a co-mention source). Only H1/H2
    headers update the governing header; H3-H6 leave it unchanged.

    With skip_fenced (mentions), fenced code blocks are set apart first:
    their lines end a paragraph, are never headers, and each block lands in
    `fenced`. Without it (comention), fence lines are body text and a `#`
    line inside a fence is a header, as that mode has always read them; the
    units still know which lines are code.
    """
    lines = doc_text.splitlines()
    roles = _fence_roles(lines)
    doc = MarkdownDoc(
        paragraphs=[],
        headings=[],
        fenced=_fenced_blocks(lines, roles) if skip_fenced else [],
    )
    governing: str | None = None
    buf: list[int] = []  # line indexes of the open paragraph

    def _flush() -> None:
        if buf:
            text = "\n".join(lines[i] for i in buf).strip()
            if text:
                doc.paragraphs.append(Paragraph(
                    header=governing,
                    line=buf[0] + 1,
                    text=text,
                    units=_units(
                        [lines[i] for i in buf],
                        [roles[i] is not None for i in buf],
                        buf[0] + 1,
                    ),
                ))
            buf.clear()

    for idx, raw_line in enumerate(lines):
        if skip_fenced and roles[idx] is not None:
            _flush()
            continue
        m = _HEADER_RE.match(raw_line)
        if m is not None:
            # A header terminates the current paragraph; the header line
            # itself is not body content.
            _flush()
            level = len(m.group(1))
            header_text = _strip_closing_hashes(m.group(2)).strip()
            doc.headings.append(header_text)
            if level <= 2:
                governing = header_text if header_text else None
            continue
        if raw_line.strip() == "":
            _flush()
            continue
        buf.append(idx)
    _flush()
    return doc


def parse_body_paragraphs(doc_text: str) -> list[tuple[str | None, str]]:
    """Body paragraphs as (governing header text or None, paragraph text),
    read the way comention reads them (fenced code is body text)."""
    return [
        (p.header, p.text)
        for p in read_markdown(doc_text, skip_fenced=False).paragraphs
    ]


# --------------------------------------------------------------------------
# Skills and matching
# --------------------------------------------------------------------------


def _norm(text: str) -> str:
    """Lowercase, trimmed, with each run of whitespace collapsed."""
    return " ".join(text.lower().split())


def _dedupe(items: tuple[str, ...], key=lambda s: s) -> tuple[str, ...]:
    """Drop repeats (by key), keeping the first of each in order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return tuple(out)


def _term_body(term: str) -> str:
    """Regex source for a term's words, with any whitespace between them."""
    return r"\s+".join(re.escape(word) for word in term.split())


def _skill_pattern(skill: Skill) -> re.Pattern[str]:
    """One case-insensitive pattern that matches any of the skill's terms
    with no word character on either side."""
    terms = sorted(skill.terms, key=lambda t: (-len(t), t))
    return re.compile(
        "|".join(rf"(?:(?<!\w){_term_body(t)}(?!\w))" for t in terms),
        re.IGNORECASE,
    )


class _Occurrence(NamedTuple):
    """A match of a term in a text, and the skills it names there."""

    start: int
    end: int
    names: frozenset[str]


class _EachSkill:
    """comention's matcher: each skill's terms on their own, so `react`
    also matches the `react` in `react-dom`."""

    def __init__(self, specs: dict[str, Skill]) -> None:
        self.patterns = {n: _skill_pattern(specs[n]) for n in sorted(specs)}

    def names(self, text: str) -> set[str]:
        return {n for n, pattern in self.patterns.items() if pattern.search(text)}

    def find(self, text: str, among: frozenset[str]) -> list[_Occurrence]:
        """Every match in the text of a term of a skill in `among`."""
        return [
            _Occurrence(m.start(), m.end(), frozenset((n,)))
            for n in sorted(among)
            for m in self.patterns[n].finditer(text)
        ]


class _LongestTerm:
    """The matcher of mentions and infer: one pattern over every skill's
    terms, longest first, so each occurrence is the longest term that
    matches there, and names the skills of that term."""

    def __init__(self, specs: dict[str, Skill]) -> None:
        owners: dict[str, set[str]] = {}
        for skill in specs.values():
            for term in skill.terms:
                owners.setdefault(_norm(term), set()).add(skill.name)
        self.owners = {t: frozenset(n) for t, n in owners.items()}
        self.terms = sorted(self.owners, key=lambda t: (-len(t), t))
        # Plain alternatives (no groups) keep the regex engine's fast path.
        alternatives = "|".join(_term_body(t) for t in self.terms)
        self.pattern = re.compile(
            rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE
        ) if self.terms else None

    def names(self, text: str) -> set[str]:
        return set().union(*(o.names for o in self.find(text)))

    def find(
        self, text: str, among: frozenset[str] | None = None
    ) -> list[_Occurrence]:
        """Each occurrence in the text, in order, with the skills it names
        (only those in `among`, when given; an occurrence naming none of
        them is left out)."""
        found: list[_Occurrence] = []
        for m in self.pattern.finditer(text) if self.pattern else ():
            names = self._owners(m.group(0))
            if among is not None:
                names &= among
            if names:
                found.append(_Occurrence(m.start(), m.end(), names))
        return found

    def _owners(self, text: str) -> frozenset[str]:
        found = self.owners.get(_norm(text))
        if found is not None:
            return found
        # A case-insensitive match that lowercasing does not map back to its
        # term (the long s matches `s`): the first term, longest first, that
        # matches the text whole is the one the pattern chose.
        for term in self.terms:
            if re.fullmatch(_term_body(term), text, re.IGNORECASE):
                return self.owners[term]
        return frozenset()


def _coerce(skills: list[Skill | str]) -> dict[str, Skill]:
    """Index skills by name, merging entries that share a name. A plain
    string is a skill with no alias."""
    merged: dict[str, Skill] = {}
    for item in skills:
        skill = item if isinstance(item, Skill) else Skill(item, (item,))
        prev = merged.get(skill.name)
        if prev is not None:
            skill = Skill(
                name=skill.name,
                terms=_dedupe(prev.terms + skill.terms, key=_norm),
                keywords=tuple(sorted(set(prev.keywords + skill.keywords))),
                languages=tuple(sorted(set(prev.languages + skill.languages))),
                docs=_dedupe(prev.docs + skill.docs),
            )
        merged[skill.name] = skill
    return merged


def _string_list(entry: dict, key: str, where: str) -> tuple[str, ...]:
    """The entry's optional `key`: an array of non-empty strings."""
    value = entry.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise UserError(
            f"{where}.{key} must be an array of non-empty strings; "
            f"got {type(value).__name__}"
        )
    out: list[str] = []
    for j, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise UserError(
                f"{where}.{key}[{j}] must be a non-empty string; got {item!r}"
            )
        out.append(item.strip())
    return tuple(out)


def _languages(entry: dict, where: str) -> tuple[str, ...]:
    """The entry's optional `language`: a string, or an array of strings (a
    stack lists its libraries' languages), normalised and sorted."""
    value = entry.get("language")
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not all(
        isinstance(item, str) and item.strip() for item in items
    ):
        raise UserError(
            f"{where}.language must be a non-empty string or an array of "
            f"non-empty strings; got {value!r}"
        )
    return tuple(sorted({_norm(item) for item in items}))


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


def _make_excerpt(text: str, limit: int = _EXCERPT_LIMIT) -> str:
    """Collapse whitespace and truncate for a stable, compact evidence quote."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) > limit:
        return collapsed[: limit - 3].rstrip() + "..."
    return collapsed


@functools.lru_cache(maxsize=256)
def _words(text: str) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """The text's words, found once per text: where each starts and ends,
    and the running total of their lengths."""
    spans = [m.span() for m in _WORD_RE.finditer(text)]
    return (
        tuple(s for s, _ in spans),
        tuple(e for _, e in spans),
        tuple(itertools.accumulate((e - s for s, e in spans), initial=0)),
    )


def _excerpt_around(
    text: str,
    first: tuple[int, int],
    second: tuple[int, int],
    limit: int = _EXCERPT_LIMIT,
) -> str:
    """Collapse `text` like an excerpt and cut it to `limit` characters
    around two names, at the spans `first` and `second` (first starting
    first): the words around both, or, when the words between them do not
    fit, the words around each with the middle cut. `...` marks each cut."""
    starts, ends, pre = _words(text)
    last = len(starts) - 1

    def join(i: int, j: int) -> str:
        return " ".join(text[starts[k]:ends[k]] for k in range(i, j + 1))

    if pre[-1] + last <= limit:  # the whole text fits
        return join(0, last)

    def word(pos: int) -> int:
        """The index of the word that holds text[pos]."""
        return bisect.bisect_right(ends, pos)

    def width(i: int, j: int) -> int:
        """Words i..j joined, with a `...` for each side cut."""
        return pre[j + 1] - pre[i] + (j - i) + 3 * (i > 0) + 3 * (j < last)

    def grow(i: int, j: int, room: int) -> tuple[int, int]:
        """Add words on both sides of i..j, in turn, while they fit."""
        grown = True
        while grown:
            grown = False
            if i > 0 and width(i - 1, j) <= room:
                i, grown = i - 1, True
            if j < last and width(i, j + 1) <= room:
                j, grown = j + 1, True
        return i, j

    i, j = word(first[0]), word(max(first[1], second[1]) - 1)
    first_end, second_start = word(first[1] - 1), word(second[0])
    if width(i, j) <= limit or second_start <= first_end:
        windows = [grow(i, j, limit)]
    else:
        # The words between the names do not fit: keep each name with the
        # words around it, and cut the middle.
        windows = [
            grow(i, first_end, limit // 2), grow(second_start, j, limit // 2),
        ]
    quote = " ... ".join(join(a, b) for a, b in windows)
    if windows[0][0] > 0:
        quote = "..." + quote
    if windows[-1][1] < last:
        quote += "..."
    # Only a name inside a word too long for its window overflows the limit.
    return _make_excerpt(quote, limit)


def _pair_quote(
    text: str,
    line: int,
    found_a: list[_Occurrence],
    found_b: list[_Occurrence],
) -> tuple[int, str]:
    """Where `text`, whose first line is `line`, names two skills nearest
    each other, given where it names each: the line of the first of the
    two names, and the excerpt around them."""
    # One pass in text order: each occurrence pairs with the latest one
    # before it of the other skill (an occurrence of both, with itself).
    marked = sorted(
        [(o.start, o.end, 0, o) for o in found_a]
        + [(o.start, o.end, 1, o) for o in found_b],
        key=lambda m: m[:3],
    )
    latest: list[_Occurrence | None] = [None, None]
    best: tuple[tuple[int, int], _Occurrence, _Occurrence] | None = None
    for _, _, side, o in marked:
        p = latest[1 - side]
        if p is not None:
            key = (max(p.end, o.end) - p.start, p.start)
            if best is None or key < best[0]:
                best = (key, p, o)
        latest[side] = o
    _, first, second = best  # the text names both skills
    return (
        line + text.count("\n", 0, first.start),
        _excerpt_around(
            text, (first.start, first.end), (second.start, second.end)
        ),
    )


def _paragraph_evidence(
    para: Paragraph, present: list[str], matcher: _EachSkill | _LongestTerm
) -> list[tuple[tuple[str, str], dict]]:
    """One evidence entry per pair of the skills a paragraph names, with
    its kind and where the paragraph names the pair. `present` is sorted,
    so every pair is (a, b) with a < b."""
    if len(present) < 2:
        return []
    among = frozenset(present)
    # Each unit, with where it names each skill.
    units: list[tuple[Unit, dict[str, list[_Occurrence]]]] = []
    for unit in para.units:
        named: dict[str, list[_Occurrence]] = {}
        for o in matcher.find(unit.text, among):
            for n in o.names:
                named.setdefault(n, []).append(o)
        units.append((unit, named))
    # pair -> (kind, unit_line, unit_excerpt); a co-mention wins over a
    # lead-in, and the first unit (or lead-in and item) over later ones.
    where: dict[tuple[str, str], tuple[str, int, str]] = {}
    for unit, named in units:
        for a, b in itertools.combinations(sorted(named), 2):
            if (a, b) not in where:
                where[a, b] = (CO_MENTION, *_pair_quote(
                    unit.text, unit.line, named[a], named[b]
                ))
    lead: int | None = None  # the run of prose the next units sit under
    for k, (unit, named) in enumerate(units):
        if unit.prose:
            lead = k
            continue
        if lead is None:
            continue
        lead_unit, lead_named = units[lead]
        # Each skill of such a pair is named in one of the two units only:
        # a unit that named both would have made it a co-mention.
        pairs = [
            (min(x, y), max(x, y))
            for x, y in itertools.product(sorted(lead_named), sorted(named))
            if (min(x, y), max(x, y)) not in where and x != y
        ]
        if not pairs:
            continue
        # The lead-in, then the item, with `...` for any items between.
        gap = "\n" if k == lead + 1 else "\n...\n"
        text = lead_unit.text + gap + unit.text
        shift = len(lead_unit.text) + len(gap)
        for a, b in pairs:
            found = [
                lead_named[n] if n in lead_named else [
                    o._replace(start=o.start + shift, end=o.end + shift)
                    for o in named[n]
                ]
                for n in (a, b)
            ]
            where[a, b] = (LEAD_IN, *_pair_quote(text, lead_unit.line, *found))
    excerpt = _make_excerpt(para.text)
    evidence = []
    for pair in itertools.combinations(present, 2):
        kind, unit_line, unit_excerpt = where.get(pair, (LIST_ONLY, None, None))
        evidence.append((pair, {
            "header": para.header,
            "excerpt": excerpt,
            "line": para.line,
            "kind": kind,
            "unit_line": unit_line,
            "unit_excerpt": unit_excerpt,
        }))
    return evidence


def _pair_entry(a: str, b: str, evidence: list[dict]) -> dict:
    return {
        "a": a,
        "b": b,
        "paragraph_count": len(evidence),
        "comention_count": sum(1 for e in evidence if e["kind"] == CO_MENTION),
        "lead_in_count": sum(1 for e in evidence if e["kind"] == LEAD_IN),
        "evidence": evidence,
    }


# --------------------------------------------------------------------------
# Subcommand logic
# --------------------------------------------------------------------------


def analyze(doc_text: str, skills: list[Skill | str]) -> dict:
    """comention: candidate pairs that at least two body paragraphs name,
    with their evidence.

    Deterministic: same (doc_text, skills) → identical output.
    """
    matcher = _EachSkill(_coerce(skills))

    excluded_sections: set[str] = set()
    # (a, b) -> list of evidence dicts, one per paragraph naming both
    pair_evidence: dict[tuple[str, str], list[dict]] = {}

    for para in read_markdown(doc_text, skip_fenced=False).paragraphs:
        if para.header is not None:
            norm = normalize_header(para.header)
            if norm in EXCLUDED_HEADERS:
                excluded_sections.add(norm)
                continue
        # `present` is sorted → pairs are (a < b)
        present = sorted(matcher.names(para.text))
        for pair, entry in _paragraph_evidence(para, present, matcher):
            pair_evidence.setdefault(pair, []).append(entry)

    pairs = [
        _pair_entry(a, b, evidence)
        for (a, b), evidence in pair_evidence.items()
        if len(evidence) >= 2
    ]
    pairs.sort(key=lambda p: (-p["paragraph_count"], p["a"], p["b"]))

    return {
        "pairs": pairs,
        "excluded_section_count": len(excluded_sections),
    }


def mentions(doc_text: str, skills: list[Skill | str]) -> dict:
    """mentions: which skills the document names outside fenced code, and
    the candidate pairs a body paragraph names in one unit or through a
    lead-in."""
    specs = _coerce(skills)
    names = sorted(specs)
    matcher = _LongestTerm(specs)
    doc = read_markdown(doc_text, skip_fenced=True)

    hits: dict[str, list[dict]] = {n: [] for n in names}
    pair_evidence: dict[tuple[str, str], list[dict]] = {}
    for para in doc.paragraphs:
        present = sorted(matcher.names(para.text))
        if not present:
            continue
        excerpt = _make_excerpt(para.text)
        for n in present:
            hits[n].append(
                {"header": para.header, "excerpt": excerpt, "line": para.line}
            )
        for pair, entry in _paragraph_evidence(para, present, matcher):
            pair_evidence.setdefault(pair, []).append(entry)

    in_headings = [matcher.names(h) for h in doc.headings]
    in_fenced = [matcher.names(f.text) for f in doc.fenced]
    skills_out: list[dict] = []
    mentioned: list[str] = []
    fenced_only: list[str] = []
    unmentioned: list[str] = []
    for n in names:
        heading_count = sum(1 for found in in_headings if n in found)
        fenced_count = sum(1 for found in in_fenced if n in found)
        skills_out.append({
            "name": n,
            "paragraph_count": len(hits[n]),
            "heading_count": heading_count,
            "fenced_count": fenced_count,
            "paragraphs": hits[n],
        })
        if hits[n] or heading_count:
            mentioned.append(n)
        elif fenced_count:
            fenced_only.append(n)
        else:
            unmentioned.append(n)

    candidates: list[dict] = []
    list_only_pairs = 0
    for (a, b), evidence in pair_evidence.items():
        entry = _pair_entry(a, b, evidence)
        if entry["comention_count"] or entry["lead_in_count"]:
            candidates.append(entry)
        else:
            list_only_pairs += 1
    candidates.sort(key=lambda p: (
        -p["comention_count"], -p["lead_in_count"], -p["paragraph_count"],
        p["a"], p["b"],
    ))

    return {
        "skills": skills_out,
        "mentioned": mentioned,
        "fenced_only": fenced_only,
        "unmentioned": unmentioned,
        "candidates": candidates,
        "list_only_pair_count": list_only_pairs,
        "fenced_block_count": len(doc.fenced),
        "fenced_blocks": [{"line": f.line, "info": f.info} for f in doc.fenced],
    }


def _read_doc(path_text: str, owner: str) -> str:
    """Read one of a skill's `docs` files (infer)."""
    path = Path(path_text)
    if not path.is_file():
        raise UserError(f"docs file of skill {owner!r} not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UserError(
            f"failed to read docs file of skill {owner!r} ({path}): {exc}"
        ) from exc


def infer(skills: list[Skill | str], top_k: int = DEFAULT_TOP_K) -> dict:
    """infer: candidate pairs without an architecture document, from one
    skill's docs naming the other or shared domain keywords, never a shared
    language alone. Top-K capped."""
    specs = _coerce(skills)
    names = sorted(specs)
    languages = {lang for s in specs.values() for lang in s.languages}
    matcher = _LongestTerm(specs)

    # (documenting skill, named skill) -> its docs-mention entry
    mentioned: dict[tuple[str, str], dict] = {}
    for a in names:
        for doc in specs[a].docs:
            for lineno, line in enumerate(_read_doc(doc, a).splitlines(), start=1):
                named: set[str] = set()
                for occurrence in matcher.find(line):
                    # An occurrence of the documenting skill's own term
                    # names that skill, never another one.
                    if a not in occurrence.names:
                        named |= occurrence.names
                for b in sorted(named):
                    found = mentioned.get((a, b))
                    if found is None:
                        mentioned[(a, b)] = {
                            "kind": DOCS_MENTION,
                            "documented_by": a,
                            "doc": doc.replace("\\", "/"),
                            "line": lineno,
                            "line_count": 1,
                            "excerpt": _make_excerpt(line),
                        }
                    else:
                        found["line_count"] += 1

    pairs: list[dict] = []
    language_only_pairs = 0
    for a, b in itertools.combinations(names, 2):
        evidence = [mentioned[k] for k in ((a, b), (b, a)) if k in mentioned]
        docs_mention_count = len(evidence)
        shared = sorted(
            (set(specs[a].keywords) & set(specs[b].keywords)) - languages
        )
        if shared:
            evidence.append({"kind": SHARED_KEYWORDS, "keywords": shared})
        if evidence:
            pairs.append({
                "a": a,
                "b": b,
                "docs_mention_count": docs_mention_count,
                "shared_keyword_count": len(shared),
                "evidence": evidence,
            })
        elif set(specs[a].languages) & set(specs[b].languages):
            language_only_pairs += 1
    pairs.sort(key=lambda p: (
        -p["docs_mention_count"], -p["shared_keyword_count"], p["a"], p["b"],
    ))

    return {
        "pairs": pairs[:top_k],
        "truncated": len(pairs) > top_k,
        "total_pairs": len(pairs),
        "language_only_pair_count": language_only_pairs,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_source(source: str, label: str) -> str:
    """Read text from a file path or stdin (if source == '-')."""
    if source == "-":
        try:
            return sys.stdin.read()
        except (OSError, UnicodeDecodeError) as exc:
            raise UserError(f"failed to read {label} from stdin: {exc}") from exc
    path = Path(source)
    if not path.is_file():
        raise UserError(f"{label} file not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise UserError(f"failed to read {label} file {path}: {exc}") from exc


def parse_skills(raw_text: str) -> list[Skill]:
    """Parse and validate the --skills JSON array of skill names or objects."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise UserError(f"malformed JSON in --skills input: {exc}") from exc
    if not isinstance(data, list):
        raise UserError(
            "--skills input must be a JSON array of skill names or objects; "
            f"got {type(data).__name__}"
        )
    skills: list[Skill] = []
    for idx, item in enumerate(data):
        where = f"--skills[{idx}]"
        if isinstance(item, str) and item.strip():
            skills.append(Skill(item, (item,)))
            continue
        if not isinstance(item, dict):
            raise UserError(
                f"{where} must be a non-empty string or an object with a "
                f"non-empty `name`; got {item!r}"
            )
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise UserError(
                f"{where}.name must be a non-empty string; got {name!r}"
            )
        skills.append(Skill(
            name=name,
            terms=_dedupe((name, *_string_list(item, "aliases", where)), key=_norm),
            keywords=tuple(sorted({
                _norm(k) for k in _string_list(item, "keywords", where)
            })),
            languages=_languages(item, where),
            docs=_dedupe(_string_list(item, "docs", where)),
        ))
    return skills


def _read_doc_and_skills(args: argparse.Namespace) -> tuple[str, list[Skill]]:
    if args.doc == "-" and args.skills == "-":
        raise UserError(
            "--doc and --skills cannot both read from stdin ('-')"
        )
    # Read the file-backed input first so a single stdin source stays intact.
    if args.doc == "-":
        skills_text = _read_source(args.skills, "--skills")
        doc_text = _read_source(args.doc, "--doc")
    else:
        doc_text = _read_source(args.doc, "--doc")
        skills_text = _read_source(args.skills, "--skills")
    return doc_text, parse_skills(skills_text)


def _emit(result: dict) -> int:
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_comention(args: argparse.Namespace) -> int:
    doc_text, skills = _read_doc_and_skills(args)
    result = analyze(doc_text, skills)
    if args.verbose:
        print(
            f"analyzed {len({s.name for s in skills})} distinct skill names; "
            f"{len(result['pairs'])} qualifying pairs; "
            f"{result['excluded_section_count']} excluded sections",
            file=sys.stderr,
        )
    return _emit(result)


def _cmd_mentions(args: argparse.Namespace) -> int:
    doc_text, skills = _read_doc_and_skills(args)
    result = mentions(doc_text, skills)
    if args.verbose:
        print(
            f"analyzed {len(result['skills'])} distinct skill names; "
            f"{len(result['mentioned'])} mentioned, "
            f"{len(result['fenced_only'])} only in fenced code, "
            f"{len(result['unmentioned'])} unmentioned; "
            f"{len(result['candidates'])} candidate pairs; "
            f"{result['list_only_pair_count']} list-only pairs",
            file=sys.stderr,
        )
    return _emit(result)


def _cmd_infer(args: argparse.Namespace) -> int:
    if args.top_k < 0:
        raise UserError(f"--top-k must be >= 0; got {args.top_k}")
    skills = parse_skills(_read_source(args.skills, "--skills"))
    result = infer(skills, top_k=args.top_k)
    if args.verbose:
        print(
            f"analyzed {len({s.name for s in skills})} distinct skill names; "
            f"{result['total_pairs']} candidate pairs, "
            f"{len(result['pairs'])} emitted; "
            f"{result['language_only_pair_count']} language-only pairs",
            file=sys.stderr,
        )
    return _emit(result)


def _add_doc_and_skills(p: argparse.ArgumentParser, doc_help: str) -> None:
    p.add_argument("--doc", required=True, help=doc_help)
    p.add_argument(
        "--skills",
        required=True,
        help=(
            "path to a JSON array of loaded skills, or '-' for stdin. "
            "Shape: [\"<skill>\" | {\"name\": \"<skill>\", "
            "\"aliases\": [\"<term>\", ...]}, ...]"
        ),
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="print a one-line summary to stderr",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-comention-pairs",
        description=(
            "Report which loaded skills a document names and the pairs it "
            "names together (comention: detect-integrations.md §2 compose "
            "branch; mentions: refine-architecture scope sets), or candidate "
            "pairs from the skills' own docs and keywords (infer)."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cm = sub.add_parser(
        "comention",
        help=(
            "emit candidate co-mention pairs (>=2 body paragraphs, "
            "word-boundary, section-filtered) with evidence kinds as JSON"
        ),
    )
    _add_doc_and_skills(
        p_cm, "path to the architecture markdown document, or '-' for stdin"
    )
    p_cm.set_defaults(func=_cmd_comention)

    p_mn = sub.add_parser(
        "mentions",
        help=(
            "emit which skills a document names (fenced code skipped) and "
            "the pairs a paragraph names together, as JSON"
        ),
    )
    _add_doc_and_skills(
        p_mn, "path to the markdown document, or '-' for stdin"
    )
    p_mn.set_defaults(func=_cmd_mentions)

    p_in = sub.add_parser(
        "infer",
        help=(
            "emit candidate pairs with no architecture document: one "
            "skill's docs naming the other or shared domain keywords, never "
            "a shared language alone, Top-K capped, as JSON"
        ),
    )
    p_in.add_argument(
        "--skills",
        required=True,
        help=(
            "path to a JSON array of loaded skills, or '-' for stdin. "
            "Shape: [{\"name\": \"<skill>\", \"aliases\": [...], "
            "\"keywords\": [...], \"language\": \"<language>\" | [...], "
            "\"docs\": [\"<path>\", ...]}, ...]"
        ),
    )
    p_in.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"cap the output at the top N pairs (default {DEFAULT_TOP_K})",
    )
    p_in.add_argument(
        "--verbose",
        action="store_true",
        help="print a one-line summary to stderr",
    )
    p_in.set_defaults(func=_cmd_infer)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 — last-resort guard → exit 2
        print(f"internal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
