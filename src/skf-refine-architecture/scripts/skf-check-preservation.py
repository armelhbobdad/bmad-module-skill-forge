#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build, check and promote refine-architecture's refined document.

Compile (references/compile.md) never retypes the architecture document. It
stages an insertion plan, one entry per finding, and this script copies the
original line for line, puts each entry's block where its anchor says,
appends the Refinement Summary, checks that every original line survived and
writes the draft. The review's [C] promotes the draft through this script
too, so the output file is never replaced by a draft that lost a line.

RA's blocks. Every block the script adds sits between two marker lines, so a
later pass can set the whole annotation aside and write a fresh one:

  <!-- RA:BEGIN <kind> <id> -->
  ...
  <!-- RA:END -->

<kind> is gap, issue or improvement (an anchored entry), section (a fallback
section: <id> is the kind it collects) or summary (the Refinement Summary).
Setting RA's blocks aside removes each BEGIN line through the next END line,
outside fenced code. A BEGIN followed by another BEGIN before any END, and an
END with no BEGIN, are malformed: they stay in place as ordinary lines and
are reported, so a marker the user deleted never takes their text with it.
A document refined before the markers existed holds unmarked annotations:
when it has a `Refinement Summary` heading and at least one `RA:` heading or
RA callout (a blockquote whose first line names "Gap Identified by Refine
Architecture", "Issue Detected by Refine Architecture" or "Improvement
Suggested by Refine Architecture"), each `RA:` section and the Refinement
Summary section (to the next heading of the same or a higher level) and
each such callout are set aside too. Nothing marks where an older pass's
text ends, so such a section can hold a paragraph of the user's that follows
it: set_aside names every block set aside, by its lines in the file as
given, so the caller can show them instead of claiming they were checked.

Subcommands:

  inspect --doc PATH [--stripped OUT] [-o JSON]
      Report whether PATH holds an earlier RA pass and, with --stripped,
      write a copy of it with RA's blocks set aside (the analysis input).
      -o also writes the JSON to that file when the command succeeded.
      JSON: {status: "ok", doc, previous_pass, signals[], marked_blocks,
      legacy_blocks, malformed_markers[], lines_set_aside, set_aside[],
      stripped}. set_aside holds {start, end, kind, first_line} per block,
      kind "marked" or "legacy", first_line the text of its start line.
      signals holds "ra-markers" (marked blocks, or malformed markers),
      "legacy-annotations" and "refined-document" (the file name is
      refined-architecture-*.md); previous_pass is true when any is there.

  apply --original PATH --plan PLAN --draft OUT [-o JSON]
      Check the plan, build the draft from PATH with RA's blocks set aside,
      check that it preserves PATH, and write it to OUT. Nothing is written
      when the plan has a problem or the check fails, so an earlier draft at
      OUT stays as it was. -o also writes the JSON to that file, only when
      the draft was written, so the file always describes the draft on disk.
      JSON on success: {status: "ok", draft, counts, evidence, summary,
      unverified_technologies[], placed[], fallback[], closed_fence_line,
      preserved: true, missing: [], altered: [], lines_set_aside,
      set_aside[]}. summary is the Refinement Summary as the draft holds
      it, its placeholders filled.

  check --original PATH --refined PATH
      Set RA's blocks aside in both files and confirm the original's lines
      appear in the refined file, in order and unchanged (a line's
      terminator aside). Lines the refined file adds are allowed.
      JSON: {status: "preserved" | "not-preserved", preserved, missing[],
      missing_count, altered[], altered_count, added_count}. missing holds
      {line, text}, altered {line, original, refined_line, refined}, with
      line numbers in the files as given; each list keeps its first 50.

  promote --original PATH --draft DRAFT --output OUT --timestamp TS [-o JSON]
      Check DRAFT against PATH as check does, then rename an existing OUT to
      <OUT stem>-<TS>.md (-2, -3 ... when that name is taken) and move DRAFT
      to OUT. When the move fails, the earlier OUT is renamed back.
      JSON: {status: "promoted", output, previous, preserved: true,
      draft_removed}. draft_removed is false only when OUT is on another
      file system and the draft, copied there, could not be deleted. -o
      also writes the JSON to that file, only when the draft was promoted;
      when that write fails, the draft and the earlier OUT are put back.
      When a file cannot be put back, the error says where each one is.

  context --inspect JSON --apply JSON --promote JSON -o OUT
      Merge the records of inspect, apply and promote into the payload the
      shared emitter writes the result contract from, and write it to OUT:
      {status: "success", refined_path, previous_refined_path,
      previous_pass, gap_count, issue_count, improvement_count,
      unverified_count, result_contract: {skill, status, outputs, summary}}.
      Prints {status: "ok", context: OUT}. A record that is missing or not
      the JSON its subcommand wrote is an error (exit 2).

The insertion plan (apply --plan) is one JSON object:

  {
    "entries": [
      {"id": "gap-1", "kind": "gap", "anchor": "## Data Layer",
       "skills": ["loro", "yjs"], "block": "#### RA: ...\\n\\n> [!NOTE] ..."},
      {"id": "issue-1", "kind": "issue", "tier": "Critical",
       "anchor": "Sync runs over gRPC.", "occurrence": 2, "block": "> [!WARNING] ..."},
      {"id": "improvement-1", "kind": "improvement", "tier": "High",
       "anchor": null, "block": "#### RA: Enhancement: ..."}
    ],
    "summary": "## Refinement Summary\\n... {gap_count} ...",
    "unverified_technologies": ["Redis"],
    "skill_count": 4,
    "tiers": {"issue": [...], "improvement": [...]},
    "fallback_headings": {"gap": "...", "issue": "...", "improvement": "..."}
  }

  id          unique, letters, digits, '.', '_' or '-' (it goes into the
              BEGIN marker)
  kind        gap, issue or improvement
  tier        an issue's severity or an improvement's value, one of the
              kind's tiers (default Critical, Major, Minor and High, Medium,
              Low; "tiers" replaces them); a gap has none
  anchor      text one line of the document holds, outside its frontmatter,
              or null for the kind's fallback section. It must occur on
              exactly one line, unless "occurrence" (1-based) picks one of
              the lines that hold it. An anchor that is an ATX heading
              (`## API`) matches the headings of that level and title, so
              `### API Gateway` never holds it; only when no heading does is
              it matched as text.
  skills      the skills the finding cites (the Evidence Sources counts)
  block       the Markdown to insert, holding no RA marker and no unclosed
              code fence. A gap or improvement block opens with its ATX
              heading: the script sets that heading one level below the
              heading that governs the anchor.
  summary     the Refinement Summary, holding no RA marker. The script fills
              {gap_count}, {issue_count} and {improvement_count} (all three
              are required, so no count is typed), {<tier>_count} for every
              tier (lower case, spaces as '_': {critical_count}),
              {unverified_count} (the length of unverified_technologies),
              {unverified_technologies} (their names, comma-separated, or
              "none"), {skill_count} (the plan's skill_count, the skills the
              run used as evidence, when the plan gives it) and
              {evidence_rows} (one `| <skill> | <count> |` row per cited
              skill, most cited first). Any other {lower_case} placeholder
              left in it is a problem.

Placement. An issue goes right after the block that holds its anchor: a
heading line, the enclosing paragraph, table or blockquote, the whole list
(a loose list's later items included, and a code fence indented under one
of its items, which belongs to the item) or the code fence. A gap or
improvement goes at the end of the section its anchor sits in (the anchor
heading's own section, or the nearest heading above the anchor line), before
the next heading of the same or a higher level. Entries placed at one point
keep this order: issues, gaps, improvements, each by tier and then by plan
order. Entries with a null anchor, or with no heading above the anchor, go
to the fallback sections appended at the end of the document (gaps, then
issues by severity, then improvements by value), and the Refinement Summary
comes last. A document that ends inside an unclosed code fence gets a
closing fence line first (closed_fence_line), so nothing RA adds lands in
the code. Original lines keep their bytes and terminators; added lines use
the document's own line ending.

apply's problems. When the plan cannot be applied, apply prints
{status: "problems", problems[]} and exits 1. Each problem has an id (null
for the plan itself), a reason and a detail: plan-invalid, entry-invalid,
tier-unknown, block-has-marker, block-unclosed-fence, block-no-heading,
anchor-not-found (with closest: the line that holds the longest part of the
anchor, its heading), anchor-ambiguous (with matches: each line and its
heading), occurrence-out-of-range, summary-has-marker,
summary-unclosed-fence, summary-count-typed and summary-placeholder.

Exit codes:
  0  inspect, apply, check, promote or context succeeded (check: preserved)
  1  apply: the plan has problems, or the draft would not preserve the
     original (status "not-preserved"); check: not preserved; promote: the
     draft does not preserve the original, and nothing was moved
  2  a usage error (argparse prints it, no JSON), or a file that cannot be
     read or is not UTF-8 text, or a context record that is not its
     subcommand's JSON ({status: "error", error})
  3  a write failed ({status: "error", error}): the shared atomic writer is
     missing or failed, or promote could not rename or move a file or write
     its -o record (it puts the earlier output back first, and the error
     names where each file is when it cannot)

Writes go through the shared skf-atomic-write.py, which sits in the shared
scripts folder beside this skill's folder, installed and in a dev checkout.
"""

from __future__ import annotations

import argparse
import difflib
import errno
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ATOMIC_WRITER = (
    Path(__file__).resolve().parent.parent.parent / "shared" / "scripts" / "skf-atomic-write.py"
)

KINDS = ("gap", "issue", "improvement")
# Entries placed at one point, and the fallback sections, keep this order.
KIND_RANK = {"issue": 0, "gap": 1, "improvement": 2}
FALLBACK_ORDER = ("gap", "issue", "improvement")
DEFAULT_TIERS = {"issue": ["Critical", "Major", "Minor"], "improvement": ["High", "Medium", "Low"]}
DEFAULT_FALLBACK_HEADINGS = {
    "gap": "RA: Additional Integration Paths",
    "issue": "RA: Additional Issues Detected",
    "improvement": "RA: Additional Improvements Suggested",
}
REQUIRED_PLACEHOLDERS = ("gap_count", "issue_count", "improvement_count")
LIST_CAP = 50

BEGIN_RE = re.compile(r"^\s{0,3}<!--\s*RA:BEGIN\b.*-->\s*$")
END_RE = re.compile(r"^\s{0,3}<!--\s*RA:END\s*-->\s*$")
MARKER_TEXT_RE = re.compile(r"<!--\s*RA:(?:BEGIN|END)\b")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
LIST_RE = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,9}[.)])(?:\s|$)")
INDENT_RE = re.compile(r"^(?: {2,}|\t)\S")
QUOTE_RE = re.compile(r"^ {0,3}>")
PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TIMESTAMP_RE = re.compile(r"^\d{8}-\d{6}$")
REFINED_NAME_RE = re.compile(r"^refined-architecture-.+\.md$")
LEGACY_CALLOUTS = (
    "Gap Identified by Refine Architecture",
    "Issue Detected by Refine Architecture",
    "Improvement Suggested by Refine Architecture",
)
SUMMARY_TITLE = "refinement summary"


class DocError(Exception):
    """A file that cannot be read as UTF-8 text (exit 2)."""


class WriteError(Exception):
    """A write that failed (exit 3)."""


class Line(NamedTuple):
    number: int  # 1-based, in the file the line was read from
    text: str  # without its terminator
    end: str  # "\n", "\r\n", or "" for a last line without one


class Structure(NamedTuple):
    """What each line of a document is, outside and inside its code fences."""

    front: list[bool]
    fence: list[bool]  # a fence's opening, content and closing lines
    fence_close: list[int]  # for a fence line: the index of its closing line
    level: list[int]  # ATX heading level, 0 for any other line
    open_fence: tuple[str, int] | None  # (char, length) of a fence left open at the end


class Stripped:
    """A document with RA's blocks set aside, and what was set aside."""

    def __init__(self) -> None:
        self.kept: list[Line] = []
        self.marked = 0
        self.legacy = 0
        self.malformed: list[int] = []  # 1-based line numbers
        self.spans: list[dict] = []  # each block set aside: {start, end, kind, first_line}


# --------------------------------------------------------------------------
# Reading and writing
# --------------------------------------------------------------------------


def split_lines(text: str) -> list[Line]:
    """Split on \\n alone (a \\r before it belongs to the terminator)."""
    lines = []
    for number, piece in enumerate(re.findall(r"[^\n]*\n|[^\n]+\Z", text), start=1):
        if piece.endswith("\r\n"):
            lines.append(Line(number, piece[:-2], "\r\n"))
        elif piece.endswith("\n"):
            lines.append(Line(number, piece[:-1], "\n"))
        else:
            lines.append(Line(number, piece, ""))
    return lines


def read_lines(path: str) -> list[Line]:
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise DocError(f"{path}: {e.strerror or e}") from e
    try:
        return split_lines(data.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise DocError(f"{path}: not UTF-8 text ({e.reason} at byte {e.start})") from e


def render(lines: list[Line]) -> str:
    return "".join(line.text + line.end for line in lines)


def write_atomic(path: Path, data: bytes) -> None:
    """Write through the shared skf-atomic-write.py (temp file, fsync, rename)."""
    if not ATOMIC_WRITER.is_file():
        raise WriteError(f"the shared atomic writer is not installed: {ATOMIC_WRITER.as_posix()}")
    proc = subprocess.run(
        [sys.executable, str(ATOMIC_WRITER), "write", "--target", str(path)],
        input=data,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", "replace").strip()
        try:
            message = json.loads(message).get("message", message)
        except (ValueError, AttributeError):
            message = message.splitlines()[-1] if message else f"exit {proc.returncode}"
        raise WriteError(f"{path.as_posix()}: {message}")


# --------------------------------------------------------------------------
# Markdown structure
# --------------------------------------------------------------------------


def scan(texts: list[str]) -> Structure:
    n = len(texts)
    front = [False] * n
    if n and texts[0].strip() == "---":
        for i in range(1, n):
            if texts[i].strip() in ("---", "..."):
                for j in range(i + 1):
                    front[j] = True
                break
    fence = [False] * n
    fence_close = [-1] * n
    level = [0] * n
    open_fence = None
    i = 0
    while i < n:
        if front[i]:
            i += 1
            continue
        m = FENCE_OPEN_RE.match(texts[i])
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            char, length = m.group(1)[0], len(m.group(1))
            close_re = re.compile(r"^ {0,3}" + re.escape(char) + "{" + str(length) + r",}\s*$")
            j = i + 1
            while j < n and not close_re.match(texts[j]):
                j += 1
            last = min(j, n - 1)
            if j >= n:
                open_fence = (char, length)
            for k in range(i, last + 1):
                fence[k] = True
                fence_close[k] = last
            i = last + 1
            continue
        h = HEADING_RE.match(texts[i])
        if h:
            level[i] = len(h.group(1))
        i += 1
    return Structure(front, fence, fence_close, level, open_fence)


def heading_text(text: str) -> str:
    h = HEADING_RE.match(text)
    title = (h.group(2) or "") if h else ""
    return re.sub(r"(?:^|[ \t]+)#+$", "", title).strip()


def nearest_heading(texts: list[str], st: Structure, index: int) -> int | None:
    for i in range(index, -1, -1):
        if st.level[i] and not st.fence[i]:
            return i
    return None


def section_end(st: Structure, start: int) -> int:
    """The index of the next heading of the same or a higher level, else the end."""
    lvl = st.level[start]
    for i in range(start + 1, len(st.level)):
        if st.level[i] and not st.fence[i] and st.level[i] <= lvl:
            return i
    return len(st.level)


def _block_line(texts: list[str], st: Structure, i: int) -> bool:
    return bool(texts[i].strip()) and not st.front[i] and not st.fence[i] and not st.level[i]


def _run_of(texts: list[str], st: Structure, i: int) -> tuple[int, int]:
    """The first and last index of the run of block lines that holds line i."""
    start = end = i
    while start > 0 and _block_line(texts, st, start - 1):
        start -= 1
    while end + 1 < len(texts) and _block_line(texts, st, end + 1):
        end += 1
    return start, end


def _fence_start(st: Structure, i: int) -> int:
    """The opening line of the code fence that holds line i."""
    while i > 0 and st.fence[i - 1] and st.fence_close[i - 1] == st.fence_close[i]:
        i -= 1
    return i


def _indented_fence(texts: list[str], st: Structure, i: int) -> bool:
    """Line i is in a code fence whose opening line is indented, as under a list item."""
    return st.fence[i] and INDENT_RE.match(texts[_fence_start(st, i)]) is not None


def _content_above(texts: list[str], st: Structure, i: int) -> int:
    """The nearest line above i that is not blank, hopping over indented fences."""
    j = i - 1
    while j >= 0:
        if not texts[j].strip() and not st.fence[j]:
            j -= 1
        elif _indented_fence(texts, st, j):
            j = _fence_start(st, j) - 1
        else:
            break
    return j


def block_end(texts: list[str], st: Structure, a: int) -> int:
    """The last index of the paragraph, table, blockquote, list or fence that holds line a."""
    n = len(texts)
    if st.fence[a]:
        close = st.fence_close[a]
        if not _indented_fence(texts, st, a):
            return close
        # A fence indented under a list item belongs to that item's list.
        j = _fence_start(st, a) - 1
        while j >= 0 and not texts[j].strip() and not st.fence[j]:
            j -= 1
        if j >= 0 and (_block_line(texts, st, j) or _indented_fence(texts, st, j)):
            return max(close, block_end(texts, st, j))
        return close
    start, end = _run_of(texts, st, a)
    in_list = any(LIST_RE.match(texts[i]) for i in range(start, end + 1))
    if not in_list and INDENT_RE.match(texts[start]):
        # An indented paragraph after a blank line, or after a fence indented
        # under an item, continues the list item above it.
        j = _content_above(texts, st, start)
        if j >= 0 and _block_line(texts, st, j):
            above, _ = _run_of(texts, st, j)
            in_list = INDENT_RE.match(texts[j]) is not None or any(
                LIST_RE.match(texts[i]) for i in range(above, j + 1))
    if in_list:
        # A loose list goes on past a blank line while the next line is an
        # item, indented under one, or opens a fence indented under one.
        while True:
            j = end + 1
            while j < n and not texts[j].strip() and not st.fence[j]:
                j += 1
            if j < n and _indented_fence(texts, st, j):
                end = st.fence_close[j]
                continue
            if j < n and _block_line(texts, st, j) and (LIST_RE.match(texts[j]) or INDENT_RE.match(texts[j])):
                end = j
                while end + 1 < n and _block_line(texts, st, end + 1):
                    end += 1
                continue
            break
    return end


# --------------------------------------------------------------------------
# Setting RA's blocks aside
# --------------------------------------------------------------------------


def strip_ra(lines: list[Line]) -> Stripped:
    texts = [line.text for line in lines]
    st = scan(texts)
    keep = [True] * len(lines)
    result = Stripped()
    open_at = None
    for i, text in enumerate(texts):
        if st.front[i] or st.fence[i]:
            continue
        if BEGIN_RE.match(text):
            if open_at is not None:
                result.malformed.append(lines[open_at].number)
            open_at = i
        elif END_RE.match(text):
            if open_at is None:
                result.malformed.append(lines[i].number)
            else:
                for j in range(open_at, i + 1):
                    keep[j] = False
                result.marked += 1
                result.spans.append(_span(lines[open_at], lines[i], "marked"))
                open_at = None
    if open_at is not None:
        result.malformed.append(lines[open_at].number)
    result.malformed.sort()
    rest = [line for line, k in zip(lines, keep) if k]
    spans = legacy_spans(rest)
    result.legacy = len(spans)
    result.spans += [_span(rest[start], rest[end - 1], "legacy") for start, end in spans]
    result.spans.sort(key=lambda span: span["start"])
    drop = {i for start, end in spans for i in range(start, end)}
    result.kept = [line for i, line in enumerate(rest) if i not in drop]
    return result


def _span(first: Line, last: Line, kind: str) -> dict:
    return {"start": first.number, "end": last.number, "kind": kind, "first_line": first.text.strip()}


def legacy_spans(lines: list[Line]) -> list[tuple[int, int]]:
    """The unmarked annotations of a pass made before the markers existed."""
    texts = [line.text for line in lines]
    st = scan(texts)
    summaries, heads, callouts = [], [], []
    for i, text in enumerate(texts):
        if st.front[i] or st.fence[i]:
            continue
        if st.level[i]:
            title = heading_text(text)
            if title.casefold() == SUMMARY_TITLE:
                summaries.append(i)
            elif title.startswith("RA:"):
                heads.append(i)
        elif QUOTE_RE.match(text) and any(name in text for name in LEGACY_CALLOUTS):
            if i == 0 or not QUOTE_RE.match(texts[i - 1]):
                callouts.append(i)
    if not summaries or not (heads or callouts):
        return []
    spans = [(i, section_end(st, i)) for i in heads + summaries]
    for i in callouts:
        end = i
        while end + 1 < len(texts) and QUOTE_RE.match(texts[end + 1]) and not st.fence[end + 1]:
            end += 1
        spans.append((i, end + 1))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
            continue
        merged.append((start, end))
    return merged


# --------------------------------------------------------------------------
# The preservation check
# --------------------------------------------------------------------------


def check_preservation(original: list[Line], refined: list[Line]) -> dict:
    a = strip_ra(original).kept
    b = strip_ra(refined).kept
    matcher = difflib.SequenceMatcher(None, [x.text for x in a], [y.text for y in b], autojunk=False)
    missing, altered, added = [], [], 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            missing.extend(a[i1:i2])
        elif tag == "insert":
            added += j2 - j1
        elif tag == "replace":
            pairs = min(i2 - i1, j2 - j1)
            altered.extend(zip(a[i1:i1 + pairs], b[j1:j1 + pairs]))
            missing.extend(a[i1 + pairs:i2])
            added += (j2 - j1) - pairs
    missing.sort(key=lambda line: line.number)
    preserved = not missing and not altered
    return {
        "status": "preserved" if preserved else "not-preserved",
        "preserved": preserved,
        "missing": [{"line": x.number, "text": x.text} for x in missing[:LIST_CAP]],
        "missing_count": len(missing),
        "altered": [
            {"line": x.number, "original": x.text, "refined_line": y.number, "refined": y.text}
            for x, y in altered[:LIST_CAP]
        ],
        "altered_count": len(altered),
        "added_count": added,
    }


# --------------------------------------------------------------------------
# The insertion plan
# --------------------------------------------------------------------------


def _problem(entry_id, reason: str, detail: str, **extra) -> dict:
    return {"id": entry_id, "reason": reason, "detail": detail, **extra}


def _fence_open(texts: list[str]) -> bool:
    return scan(texts).open_fence is not None


def _placeholder(tier: str) -> str:
    return re.sub(r"\s+", "_", tier.strip().lower()) + "_count"


def read_plan(path: str) -> dict:
    try:
        raw = Path(path).read_bytes().decode("utf-8")
    except OSError as e:
        raise DocError(f"{path}: {e.strerror or e}") from e
    except UnicodeDecodeError as e:
        raise DocError(f"{path}: not UTF-8 text ({e.reason} at byte {e.start})") from e
    try:
        return json.loads(raw)
    except ValueError as e:
        return {"__invalid__": f"{path}: not JSON ({e})"}


def check_plan(plan, base: list[Line]) -> tuple[list[dict], dict]:
    """Return (problems, resolved): the plan's problems and, when none, what apply needs."""
    if not isinstance(plan, dict) or "__invalid__" in plan:
        detail = plan.get("__invalid__") if isinstance(plan, dict) else "the plan must be a JSON object"
        return [_problem(None, "plan-invalid", detail or "the plan must be a JSON object")], {}
    problems: list[dict] = []
    tiers = {kind: list(names) for kind, names in DEFAULT_TIERS.items()}
    given = plan.get("tiers")
    if given is not None:
        if not isinstance(given, dict):
            problems.append(_problem(None, "plan-invalid", "tiers must be an object"))
        else:
            for kind, names in given.items():
                ok = (kind in tiers and isinstance(names, list) and names
                      and all(isinstance(t, str) and t.strip() for t in names)
                      and len({t.casefold() for t in names}) == len(names))
                if not ok:
                    problems.append(_problem(None, "plan-invalid",
                                             f"tiers.{kind} must be issue or improvement, with distinct names"))
                else:
                    tiers[kind] = [t.strip() for t in names]
    placeholders = [_placeholder(t) for kind in ("issue", "improvement") for t in tiers[kind]]
    if len(set(placeholders)) != len(placeholders):
        problems.append(_problem(None, "plan-invalid", "an issue tier and an improvement tier share a name"))
    headings = dict(DEFAULT_FALLBACK_HEADINGS)
    given = plan.get("fallback_headings")
    if given is not None:
        if not isinstance(given, dict) or not all(
                k in headings and isinstance(v, str) and v.strip() and "\n" not in v for k, v in given.items()):
            problems.append(_problem(None, "plan-invalid",
                                     "fallback_headings maps gap, issue or improvement to one line of text"))
        else:
            headings.update({k: v.strip().lstrip("#").strip() for k, v in given.items()})
    unverified = plan.get("unverified_technologies", [])
    if not isinstance(unverified, list) or not all(isinstance(t, str) for t in unverified):
        problems.append(_problem(None, "plan-invalid", "unverified_technologies must be a list of strings"))
        unverified = []
    skill_count = plan.get("skill_count")
    if skill_count is not None and (not isinstance(skill_count, int) or isinstance(skill_count, bool)
                                    or skill_count < 0):
        problems.append(_problem(None, "plan-invalid", "skill_count must be a whole number from 0"))
        skill_count = None
    summary = plan.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append(_problem(None, "plan-invalid", "summary must be the Refinement Summary's Markdown"))
        summary = ""
    entries = plan.get("entries")
    if not isinstance(entries, list):
        problems.append(_problem(None, "plan-invalid", "entries must be a list"))
        entries = []

    texts = [line.text for line in base]
    st = scan(texts)
    searchable = [i for i in range(len(texts)) if not st.front[i]]
    seen: set[str] = set()
    resolved_entries = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            problems.append(_problem(None, "entry-invalid", f"entries[{index}] is not an object"))
            continue
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not ID_RE.match(entry_id):
            problems.append(_problem(None, "entry-invalid",
                                     f"entries[{index}]: id must be letters, digits, '.', '_' or '-'"))
            continue
        if entry_id in seen:
            problems.append(_problem(entry_id, "entry-invalid", "the id is used twice"))
            continue
        seen.add(entry_id)
        kind = entry.get("kind")
        if kind not in KINDS:
            problems.append(_problem(entry_id, "entry-invalid", "kind must be gap, issue or improvement"))
            continue
        tier = None
        if kind in tiers:
            given_tier = entry.get("tier")
            match = [t for t in tiers[kind] if isinstance(given_tier, str) and t.casefold() == given_tier.strip().casefold()]
            if not match:
                problems.append(_problem(entry_id, "tier-unknown", f"tier must be one of {', '.join(tiers[kind])}"))
                continue
            tier = match[0]
        skills = entry.get("skills", [])
        if not isinstance(skills, list) or not all(isinstance(s, str) and s.strip() for s in skills):
            problems.append(_problem(entry_id, "entry-invalid", "skills must be a list of skill names"))
            continue
        block = entry.get("block")
        if not isinstance(block, str) or not block.strip():
            problems.append(_problem(entry_id, "entry-invalid", "block must be the Markdown to insert"))
            continue
        block_lines = block.replace("\r\n", "\n").strip("\n").split("\n")
        if MARKER_TEXT_RE.search(block):
            problems.append(_problem(entry_id, "block-has-marker", "a block holds no RA:BEGIN or RA:END marker"))
            continue
        if _fence_open(block_lines):
            problems.append(_problem(entry_id, "block-unclosed-fence", "the block opens a code fence it never closes"))
            continue
        if kind != "issue" and not HEADING_RE.match(next(t for t in block_lines if t.strip())):
            problems.append(_problem(entry_id, "block-no-heading", "a gap or improvement block opens with its heading"))
            continue
        anchor_line = None
        anchor = entry.get("anchor")
        if anchor is not None:
            if not isinstance(anchor, str) or not anchor.strip() or "\n" in anchor.strip():
                problems.append(_problem(entry_id, "entry-invalid", "anchor must be one line of text, or null"))
                continue
            anchor = anchor.strip()
            hits = _heading_hits(anchor, texts, st) or [i for i in searchable if anchor in texts[i]]
            occurrence = entry.get("occurrence")
            if occurrence is not None and (not isinstance(occurrence, int) or isinstance(occurrence, bool)
                                           or occurrence < 1):
                problems.append(_problem(entry_id, "entry-invalid", "occurrence must be a whole number from 1"))
                continue
            if not hits:
                problems.append(_problem(entry_id, "anchor-not-found", "no line of the document holds the anchor",
                                         anchor=anchor, closest=_closest(anchor, base, texts, st, searchable)))
                continue
            if occurrence is None and len(hits) > 1:
                problems.append(_problem(entry_id, "anchor-ambiguous",
                                         f"{len(hits)} lines hold the anchor: quote one that only one line holds, "
                                         "or add occurrence", anchor=anchor,
                                         matches=[_where(i, base, texts, st) for i in hits[:LIST_CAP]]))
                continue
            if occurrence is not None and occurrence > len(hits):
                problems.append(_problem(entry_id, "occurrence-out-of-range",
                                         f"occurrence {occurrence}, but {len(hits)} line(s) hold the anchor",
                                         anchor=anchor))
                continue
            anchor_line = hits[(occurrence or 1) - 1]
        resolved_entries.append({"index": index, "id": entry_id, "kind": kind, "tier": tier,
                                 "skills": [s.strip() for s in skills], "lines": block_lines,
                                 "anchor": anchor_line})

    if summary:
        summary_lines = summary.replace("\r\n", "\n").strip("\n").split("\n")
        if MARKER_TEXT_RE.search(summary):
            problems.append(_problem(None, "summary-has-marker", "the summary holds no RA:BEGIN or RA:END marker"))
        if _fence_open(summary_lines):
            problems.append(_problem(None, "summary-unclosed-fence", "the summary opens a code fence it never closes"))
        found = set(PLACEHOLDER_RE.findall(summary))
        typed = [name for name in REQUIRED_PLACEHOLDERS if name not in found]
        if typed:
            problems.append(_problem(None, "summary-count-typed",
                                     "the summary must leave these counts to the script: "
                                     + ", ".join("{" + name + "}" for name in typed)))
        known = set(REQUIRED_PLACEHOLDERS) | set(placeholders) | {"unverified_count", "unverified_technologies",
                                                                   "evidence_rows"}
        if skill_count is not None:
            known.add("skill_count")
        unknown = sorted(found - known)
        if unknown:
            problems.append(_problem(None, "summary-placeholder",
                                     "fill these yourself or remove them: "
                                     + ", ".join("{" + name + "}" for name in unknown)))
    resolved = {"entries": resolved_entries, "summary": summary, "tiers": tiers, "headings": headings,
                "unverified": unverified, "skill_count": skill_count}
    return problems, resolved


def _heading_hits(anchor: str, texts: list[str], st: Structure) -> list[int]:
    """The headings an ATX heading anchor names: same level, same title."""
    h = HEADING_RE.match(anchor)
    if not h:
        return []
    level, title = len(h.group(1)), heading_text(anchor)
    return [i for i, lvl in enumerate(st.level)
            if lvl == level and not st.fence[i] and not st.front[i] and heading_text(texts[i]) == title]


def _where(i: int, base: list[Line], texts: list[str], st: Structure) -> dict:
    h = nearest_heading(texts, st, i)
    return {"line": base[i].number, "text": texts[i], "heading": texts[h].strip() if h is not None else None}


def _closest(anchor: str, base: list[Line], texts: list[str], st: Structure, searchable: list[int]) -> dict | None:
    best, best_size = None, 0
    for i in searchable:
        if not texts[i].strip():
            continue
        m = difflib.SequenceMatcher(None, anchor, texts[i], autojunk=False)
        size = m.find_longest_match(0, len(anchor), 0, len(texts[i])).size
        if size > best_size:
            best, best_size = i, size
    if best is None or best_size * 2 < len(anchor):
        return None
    return _where(best, base, texts, st)


# --------------------------------------------------------------------------
# Building the draft
# --------------------------------------------------------------------------


def _set_level(block: list[str], level: int) -> list[str]:
    out = list(block)
    for i, text in enumerate(out):
        if text.strip():
            m = HEADING_RE.match(text)
            out[i] = "#" * level + " " + (m.group(2) or "").strip()
            break
    return out


def _region(kind: str, region_id: str, body: list[str]) -> list[str]:
    return [f"<!-- RA:BEGIN {kind} {region_id} -->", "", *body, "", "<!-- RA:END -->"]


def compose(base: list[Line], resolved: dict) -> tuple[list[Line], dict]:
    texts = [line.text for line in base]
    st = scan(texts)
    n = len(base)
    newline = next((line.end for line in base if line.end), "\n")
    rank = {kind: {t: r for r, t in enumerate(resolved["tiers"].get(kind, []))} for kind in KINDS}
    at: dict[int, list[tuple[tuple, list[str], dict]]] = {}
    fallback: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    for entry in resolved["entries"]:
        a = entry["anchor"]
        key = (KIND_RANK[entry["kind"]], rank[entry["kind"]].get(entry["tier"], 0), entry["index"])
        if a is None:
            fallback[entry["kind"]].append(entry)
            continue
        if entry["kind"] == "issue":
            if st.level[a] and not st.fence[a]:
                k = a + 1
            else:
                k = block_end(texts, st, a) + 1
            body = entry["lines"]
        else:
            g = a if (st.level[a] and not st.fence[a]) else nearest_heading(texts, st, a)
            if g is None:
                fallback[entry["kind"]].append(entry)
                continue
            k = section_end(st, g)
            body = _set_level(entry["lines"], min(st.level[g] + 1, 6))
        at.setdefault(k, []).append((key, _region(entry["kind"], entry["id"], body), entry))

    tail: list[list[str]] = []
    fallback_ids: list[str] = []
    for kind in FALLBACK_ORDER:
        items = sorted(fallback[kind], key=lambda e: (rank[kind].get(e["tier"], 0), e["index"]))
        if not items:
            continue
        fallback_ids += [e["id"] for e in items]
        body = ["## " + resolved["headings"][kind]]
        for e in items:
            lines = e["lines"] if kind == "issue" else _set_level(e["lines"], 3)
            body += ["", *lines]
        tail.append(_region("section", kind, body))
    tail.append(_region("summary", "refinement-summary", fill_summary(resolved)))

    out: list[Line] = []
    placed = []

    def add(text: str) -> None:
        if out and not out[-1].end:
            out[-1] = Line(out[-1].number, out[-1].text, newline)
        out.append(Line(len(out) + 1, text, newline))

    def insert(k: int) -> None:
        for _, region, entry in sorted(at.get(k, []), key=lambda item: item[0]):
            placed.append({"id": entry["id"], "kind": entry["kind"], "line": len(out) + 1})
            for text in region:
                add(text)

    for i, line in enumerate(base):
        insert(i)
        out.append(Line(len(out) + 1, line.text, line.end))
    closed_fence_line = None
    if st.open_fence is not None:
        char, length = st.open_fence
        add(char * length)
        closed_fence_line = len(out)
    insert(n)
    for region in tail:
        for text in region:
            add(text)
    # The last line keeps the document's own ending: none when it had none.
    if out and base and not base[-1].end and out[-1].text == "<!-- RA:END -->":
        out[-1] = Line(out[-1].number, out[-1].text, "")
    info = {
        "placed": placed,
        "fallback": fallback_ids,
        "closed_fence_line": closed_fence_line,
    }
    return out, info


def tally(resolved: dict) -> tuple[dict, dict]:
    entries = resolved["entries"]
    counts = {kind: sum(1 for e in entries if e["kind"] == kind) for kind in KINDS}
    for kind in ("issue", "improvement"):
        counts[f"{kind}_tiers"] = {t: sum(1 for e in entries if e["kind"] == kind and e["tier"] == t)
                                   for t in resolved["tiers"][kind]}
    counts["unverified"] = len(resolved["unverified"])
    counts["skills"] = resolved["skill_count"]
    evidence: dict[str, int] = {}
    for e in entries:
        for skill in dict.fromkeys(e["skills"]):
            evidence[skill] = evidence.get(skill, 0) + 1
    evidence = dict(sorted(evidence.items(), key=lambda item: (-item[1], item[0])))
    return counts, evidence


def fill_summary(resolved: dict) -> list[str]:
    counts, evidence = tally(resolved)
    values = {"gap_count": counts["gap"], "issue_count": counts["issue"],
              "improvement_count": counts["improvement"], "unverified_count": counts["unverified"],
              "unverified_technologies": ", ".join(resolved["unverified"]) or "none",
              "evidence_rows": "\n".join(f"| {skill} | {count} |" for skill, count in evidence.items())}
    if counts["skills"] is not None:
        values["skill_count"] = counts["skills"]
    for kind in ("issue", "improvement"):
        for tier, count in counts[f"{kind}_tiers"].items():
            values[_placeholder(tier)] = count
    text = PLACEHOLDER_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), resolved["summary"])
    return text.replace("\r\n", "\n").strip("\n").split("\n")


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------


def cmd_inspect(args) -> tuple[dict, int]:
    lines = read_lines(args.doc)
    stripped = strip_ra(lines)
    signals = []
    if stripped.marked or stripped.malformed:
        signals.append("ra-markers")
    if stripped.legacy:
        signals.append("legacy-annotations")
    if REFINED_NAME_RE.match(Path(args.doc).name):
        signals.append("refined-document")
    out = None
    if args.stripped:
        out = Path(args.stripped)
        write_atomic(out, render(stripped.kept).encode("utf-8"))
    return {
        "status": "ok",
        "doc": args.doc,
        "previous_pass": bool(signals),
        "signals": signals,
        "marked_blocks": stripped.marked,
        "legacy_blocks": stripped.legacy,
        "malformed_markers": stripped.malformed,
        "lines_set_aside": len(lines) - len(stripped.kept),
        "set_aside": stripped.spans,
        "stripped": out.as_posix() if out else None,
    }, 0


def cmd_apply(args) -> tuple[dict, int]:
    original = read_lines(args.original)
    plan = read_plan(args.plan)
    stripped = strip_ra(original)
    problems, resolved = check_plan(plan, stripped.kept)
    if problems:
        return {"status": "problems", "problems": problems}, 1
    draft, info = compose(stripped.kept, resolved)
    check = check_preservation(original, draft)
    if not check["preserved"]:
        return {"status": "not-preserved", **{k: v for k, v in check.items() if k != "status"}}, 1
    out = Path(args.draft)
    write_atomic(out, render(draft).encode("utf-8"))
    counts, evidence = tally(resolved)
    return {
        "status": "ok",
        "draft": out.as_posix(),
        "counts": counts,
        "evidence": evidence,
        "summary": "\n".join(fill_summary(resolved)),
        "unverified_technologies": resolved["unverified"],
        **info,
        "preserved": True,
        "missing": [],
        "altered": [],
        "lines_set_aside": len(original) - len(stripped.kept),
        "set_aside": stripped.spans,
    }, 0


def cmd_check(args) -> tuple[dict, int]:
    result = check_preservation(read_lines(args.original), read_lines(args.refined))
    return result, 0 if result["preserved"] else 1


def _free_name(output: Path, timestamp: str) -> Path:
    candidate = output.with_name(f"{output.stem}-{timestamp}{output.suffix}")
    n = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = output.with_name(f"{output.stem}-{timestamp}-{n}{output.suffix}")
        n += 1
    return candidate


def cmd_promote(args) -> tuple[dict, int]:
    draft_path, output = Path(args.draft), Path(args.output)
    draft = read_lines(args.draft)
    check = check_preservation(read_lines(args.original), draft)
    if not check["preserved"]:
        return {"status": "not-preserved", **{k: v for k, v in check.items() if k != "status"}}, 1
    if output.exists() and not output.is_file():
        raise WriteError(f"{output.as_posix()}: not a file")
    previous = None
    draft_removed = True
    if output.exists():
        previous = _free_name(output, args.timestamp)
        try:
            os.rename(output, previous)
        except OSError as e:
            raise WriteError(f"cannot rename {output.as_posix()}: {e.strerror or e}") from e
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(draft_path, output)
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise
            # Another file system: copy through the atomic writer, then drop the draft.
            write_atomic(output, draft_path.read_bytes())
            try:
                draft_path.unlink()
            except OSError:
                draft_removed = False
    except (OSError, WriteError) as e:
        reason = e.strerror if isinstance(e, OSError) and e.strerror else str(e)
        message = f"cannot move {draft_path.as_posix()} to {output.as_posix()}: {reason}"
        if previous is not None:
            try:
                os.rename(previous, output)
            except OSError as back:
                message += (f"; the earlier output could not be renamed back ({back.strerror or back}), so it "
                            f"stays at {previous.as_posix()}, and the draft is at {draft_path.as_posix()}")
        raise WriteError(message) from e
    return {
        "status": "promoted",
        "output": output.as_posix(),
        "previous": previous.as_posix() if previous else None,
        "preserved": True,
        "draft_removed": draft_removed,
    }, 0


def _undo_promote(args, result: dict) -> str:
    """Put the draft and the earlier output back: the promotion's record could not be written.

    Returns "" when both are back, else where each file was left.
    """
    output, previous = Path(args.output).as_posix(), result.get("previous")
    try:
        shutil.move(output, args.draft)
    except OSError as e:
        left = f"the draft could not be moved back ({e.strerror or e}), so it stays at {output} as the refined document"
        return left + (f", and the earlier output is at {previous}" if previous else "")
    if previous:
        try:
            os.rename(previous, output)
        except OSError as e:
            return (f"the earlier output could not be renamed back ({e.strerror or e}), so it stays at {previous}, "
                    f"and the draft is back at {Path(args.draft).as_posix()}")
    return ""


def _record(path: str, command: str, status: str, keys: tuple[str, ...]) -> dict:
    """A JSON record one of the other subcommands wrote with -o."""
    try:
        record = json.loads(Path(path).read_bytes().decode("utf-8"))
    except OSError as e:
        raise DocError(f"{path}: {e.strerror or e}") from e
    except (UnicodeDecodeError, ValueError) as e:
        raise DocError(f"{path}: not the JSON record {command} writes ({e})") from e
    if not isinstance(record, dict) or record.get("status") != status or any(k not in record for k in keys):
        raise DocError(f"{path}: not the record of a successful {command}")
    return record


def cmd_context(args) -> tuple[dict, int]:
    inspected = _record(args.inspect, "inspect", "ok", ("previous_pass",))
    applied = _record(args.apply, "apply", "ok", ("counts",))
    promoted = _record(args.promote, "promote", "promoted", ("output", "previous"))
    counts = applied["counts"]
    names = ("gap", "issue", "improvement", "unverified")
    if not isinstance(counts, dict) or not all(isinstance(counts.get(k), int) for k in names):
        raise DocError(f"{args.apply}: its counts lack {', '.join(names)}")
    totals = {f"{k}_count": counts[k] for k in names}
    payload = {
        "status": "success",
        "refined_path": promoted["output"],
        "previous_refined_path": promoted["previous"],
        "previous_pass": bool(inspected["previous_pass"]),
        **totals,
        "result_contract": {
            "skill": "skf-refine-architecture",
            "status": "success",
            "outputs": [{"type": "report", "path": promoted["output"]}],
            "summary": {**totals, "previous_refined_path": promoted["previous"]},
        },
    }
    out = Path(args.out)
    write_atomic(out, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return {"status": "ok", "context": out.as_posix()}, 0


def _timestamp(value: str) -> str:
    if not TIMESTAMP_RE.match(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not YYYYMMDD-HHmmss")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-check-preservation",
        description=(
            "Build refine-architecture's draft from an insertion plan, check that a refined "
            "document keeps every line of the original, promote the draft to the output file, "
            "and stage the result contract's payload from the run's records. RA's marked "
            "blocks (and the unmarked annotations of an older pass) are set aside in both "
            "documents first. Prints JSON."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run skf-check-preservation.py inspect --doc arch.md --stripped run/analysis-doc.md\n"
            "  uv run skf-check-preservation.py apply --original arch.md --plan run/insertion-plan.json "
            "--draft forge/.skf-ra-draft-app.md -o run/apply.json\n"
            "  uv run skf-check-preservation.py check --original arch.md --refined refined.md\n"
            "  uv run skf-check-preservation.py promote --original arch.md --draft forge/.skf-ra-draft-app.md "
            "--output docs/refined-architecture-app.md --timestamp 20261001-120000\n"
            "  uv run skf-check-preservation.py context --inspect run/inspect.json --apply run/apply.json "
            "--promote run/promote.json --out run/result-context.json"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect", help="Detect an earlier RA pass and write the analysis copy.")
    p.add_argument("--doc", required=True, help="the architecture document")
    p.add_argument("--stripped", help="write the document with RA's blocks set aside here")
    p.add_argument("-o", "--output-json", help="also write the JSON result here")
    p.set_defaults(func=cmd_inspect)
    p = sub.add_parser("apply", help="Build the draft from the insertion plan.")
    p.add_argument("--original", required=True, help="the architecture document")
    p.add_argument("--plan", required=True, help="the insertion plan (JSON)")
    p.add_argument("--draft", required=True, help="where to write the draft")
    p.add_argument("-o", "--output-json", help="also write the JSON result here")
    p.set_defaults(func=cmd_apply)
    p = sub.add_parser("check", help="Check that a refined document preserves the original.")
    p.add_argument("--original", required=True, help="the architecture document")
    p.add_argument("--refined", required=True, help="the refined document or draft")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("promote", help="Replace the output with the draft, keeping the earlier output.")
    p.add_argument("--original", required=True, help="the architecture document")
    p.add_argument("--draft", required=True, help="the draft to promote")
    p.add_argument("--output", required=True, help="the refined document's path")
    p.add_argument("--timestamp", required=True, type=_timestamp,
                   help="the run's timestamp, YYYYMMDD-HHmmss, for the earlier output's new name")
    p.add_argument("-o", "--output-json", help="also write the JSON result here")
    p.set_defaults(func=cmd_promote)
    p = sub.add_parser("context", help="Merge the run's records into the result contract's payload.")
    p.add_argument("--inspect", required=True, help="inspect's -o record")
    p.add_argument("--apply", required=True, help="apply's -o record")
    p.add_argument("--promote", required=True, help="promote's -o record")
    p.add_argument("--out", required=True, help="where to write the payload")
    p.set_defaults(func=cmd_context)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result, code = args.func(args)
    except DocError as e:
        result, code = {"status": "error", "error": str(e)}, 2
    except WriteError as e:
        result, code = {"status": "error", "error": str(e)}, 3
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if getattr(args, "output_json", None) and code == 0:
        try:
            write_atomic(Path(args.output_json), (text + "\n").encode("utf-8"))
        except WriteError as e:
            message = str(e)
            if args.command == "promote":
                left = _undo_promote(args, result)
                message += f"; {left}" if left else ""
            result, code = {"status": "error", "error": message}, 3
            text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a document line or a path may hold.
    """
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


if __name__ == "__main__":
    _force_utf8(sys.stdout, sys.stderr)
    sys.exit(main())
