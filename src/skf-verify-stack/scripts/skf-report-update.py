#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Write one part of a skf-verify-stack feasibility report in place.

The coverage, integrations, requirements and synthesize stages each own a
few frontmatter keys, the rows of a table or a section of the report that
init.md created from the template. Each call edits only the part it names
and writes the report back through the shared skf-atomic-write.py write, so
a stage never rewrites what an earlier one wrote. Every other byte stays:
the report's line endings (a CRLF report stays CRLF, and each line written
takes the report's first line ending), a leading byte order mark, and a
missing newline at the end of the file. Stdin is read as UTF-8 bytes, a
byte order mark and each line's trailing carriage return dropped.

Subcommands:

  set-counts --report R --kind K < <helper JSON>
      Sets the frontmatter keys of one kind from the JSON a helper printed,
      whole numbers bare and tokens double-quoted, and adds the kind's stage
      to stepsCompleted once, rewriting that key as one flow list
      (stepsCompleted: ['init', 'coverage']; the items of a block list go).
      A key the frontmatter lacks is added before its closing `---`. Kinds:

        coverage      skf-coverage-tally.py's coverage tally:
                      coverage_percentage (0..100) -> coveragePercentage,
                      covered_count -> coverageCovered, missing_count ->
                      coverageMissing, replaced_count -> coverageReplaced;
                      stage coverage
        integrations  its integrations tally: pairs_verified,
                      pairs_plausible, pairs_risky, pairs_blocked ->
                      pairsVerified, pairsPlausible, pairsRisky,
                      pairsBlocked; stage integrations
        requirements  its requirements tally: requirements_fulfilled,
                      requirements_partial, requirements_not_addressed ->
                      requirementsFulfilled, requirementsPartial,
                      requirementsNotAddressed, and requirementsPass:
                      "completed"; stage requirements
        requirements-skipped
                      reads no stdin: requirementsPass: "skipped"; stage
                      requirements
        synthesize    skf-verdict-rollup.py's JSON: overallVerdict
                      (FEASIBLE, CONDITIONALLY_FEASIBLE or NOT_FEASIBLE) and
                      recommendationCount, verbatim; stage synthesize
        delta         skf-report-delta.py's JSON: improvedCount,
                      regressedCount, newCount, unchangedCount ->
                      deltaImproved, deltaRegressed, deltaNew,
                      deltaUnchanged; no stage

      A key the input lacks, a value of another type (a count that is not
      a whole number, true and false included), or input that carries an
      `error` (a helper's refusal saved in place of its result) is
      INVALID_INPUT. A stepsCompleted that holds a scalar is INVALID_REPORT.

  fill-table --report R --heading H < <rows>
      Replaces the data rows of the first table under `## H` (a line that
      starts with a pipe, then a delimiter row; fenced code and HTML
      comments are skipped, as the shared report reader skips them) with
      the rows on stdin, such as the rows skf-coverage-tally.py --render
      printed. Blank lines are dropped, and empty stdin leaves the header
      and the delimiter row alone. A line that does not start with a pipe,
      or whose cell count (cells split on unescaped pipes) differs from the
      header's, is INVALID_INPUT.

  replace-section --report R --heading H [--subsection S] < <content>
      Replaces the body of `## H`, up to the next `#` or `##` heading
      outside fenced code and HTML comments or the end of the file, with
      the content, one blank line around it. A closing `---` break and the
      blank lines after it stay. With --subsection S it replaces only the
      `### S` block of that body (up to the next heading of level 1 to 3),
      writing the `### S` line itself, or appends the block at the end of
      the body, before the break, when the body has none, so the same call
      run again changes nothing. Content that is empty, holds a `#` or `##`
      heading (with --subsection, a `###` one too) outside fenced code, or
      leaves a fenced code block or an HTML comment open is INVALID_INPUT.

  For fill-table and replace-section, a report where `## H` is missing or
  appears twice, where fill-table finds no table under it, or where the
  body holds `### S` twice, is INVALID_REPORT.

Output (stdout, one object):
  {"status": "ok", "report": "<R>", "changed": <bool>, ...}
  set-counts adds "kind", "set" (each key with the value written) and
  "stepsCompleted"; fill-table adds "heading" and "rows"; replace-section
  adds "heading", "subsection" (null without it) and "lines". A call that
  changes nothing writes nothing.

Errors (stdout, one object, nothing written): {"error": "<why>", "code": "<code>"}:
  HELPER_MISSING  skf-validate-feasibility-report.py (whose split_frontmatter()
                  and frontmatter_list() read the frontmatter) or
                  skf-atomic-write.py is not in the shared scripts folder
                  beside this skill's folder
  INVALID_INPUT   stdin does not fit the subcommand (see each one above)
  INVALID_REPORT  the report cannot be read as UTF-8, has no frontmatter
                  (set-counts), or does not hold the part the call names
  WRITE_FAILED    skf-atomic-write.py write exited non-zero; its stderr is
                  in `error`, and the report is as it was

Exit codes:
  0  the part was written, or already held what the call writes
  1  HELPER_MISSING
  2  INVALID_INPUT or INVALID_REPORT; also an argparse usage error (usage
     on stderr, no JSON)
  3  WRITE_FAILED

CLI usage:
  uv run skf-report-update.py set-counts --report report.md --kind coverage < coverage-tally.json
  uv run skf-report-update.py set-counts --report report.md --kind requirements-skipped
  uv run skf-report-update.py fill-table --report report.md --heading 'Integration Verdicts' < verdict-table.md
  uv run skf-report-update.py replace-section --report report.md --heading 'Recommendations' \\
      --subsection 'Requirements Coverage' < requirements-section.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# The shared scripts this one runs. Installed (under _bmad/skf/ or an IDE's
# skills folder) and in a dev checkout (src/), shared/ sits beside this
# skill's folder.
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "shared" / "scripts"
SHARED_READER = SHARED_SCRIPTS / "skf-validate-feasibility-report.py"
ATOMIC_WRITER = SHARED_SCRIPTS / "skf-atomic-write.py"
WRITE_TIMEOUT_SEC = 60

HELPER_MISSING = "HELPER_MISSING"
INVALID_INPUT = "INVALID_INPUT"
INVALID_REPORT = "INVALID_REPORT"
WRITE_FAILED = "WRITE_FAILED"

BOM = b"\xef\xbb\xbf"
STEPS_COMPLETED_KEY = "stepsCompleted"
VERDICTS = ("FEASIBLE", "CONDITIONALLY_FEASIBLE", "NOT_FEASIBLE")

# A value set-counts reads: a whole number, a whole number from 0 to 100, or
# an overall verdict token.
COUNT, PERCENTAGE, VERDICT = "count", "percentage", "verdict"


class Kind(NamedTuple):
    fields: tuple  # (input field, frontmatter key, value type)
    fixed: tuple  # (frontmatter key, token) written whatever the input
    stage: str | None  # the step it adds to stepsCompleted
    reads_stdin: bool = True


KINDS = {
    "coverage": Kind(
        (("coverage_percentage", "coveragePercentage", PERCENTAGE),
         ("covered_count", "coverageCovered", COUNT),
         ("missing_count", "coverageMissing", COUNT),
         ("replaced_count", "coverageReplaced", COUNT)),
        (), "coverage"),
    "integrations": Kind(
        (("pairs_verified", "pairsVerified", COUNT),
         ("pairs_plausible", "pairsPlausible", COUNT),
         ("pairs_risky", "pairsRisky", COUNT),
         ("pairs_blocked", "pairsBlocked", COUNT)),
        (), "integrations"),
    "requirements": Kind(
        (("requirements_fulfilled", "requirementsFulfilled", COUNT),
         ("requirements_partial", "requirementsPartial", COUNT),
         ("requirements_not_addressed", "requirementsNotAddressed", COUNT)),
        (("requirementsPass", "completed"),), "requirements"),
    "requirements-skipped": Kind((), (("requirementsPass", "skipped"),), "requirements", reads_stdin=False),
    "synthesize": Kind(
        (("overallVerdict", "overallVerdict", VERDICT),
         ("recommendationCount", "recommendationCount", COUNT)),
        (), "synthesize"),
    "delta": Kind(
        (("improvedCount", "deltaImproved", COUNT),
         ("regressedCount", "deltaRegressed", COUNT),
         ("newCount", "deltaNew", COUNT),
         ("unchangedCount", "deltaUnchanged", COUNT)),
        (), None),
}

# Markdown scanning, the way the shared report reader scans for its table.
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_COMMENT_OPEN_RE = re.compile(r"^\s{0,3}<!--")
_COMMENT_CLOSE = "-->"
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)\s*$")
_LEVEL_1_2_RE = re.compile(r"^#{1,2}\s")
_LEVEL_1_3_RE = re.compile(r"^#{1,3}\s")
_CELL_SEPARATOR_RE = re.compile(r"(?<!\\)\|")
_DELIMITER_CELL_RE = re.compile(r"^:?-+:?$")
_BLOCK_ITEM_RE = re.compile(r"^-(?:\s+.*)?$")


class UpdateError(Exception):
    """A call this script refuses: `code` is INVALID_INPUT or INVALID_REPORT."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def make_error(message, code):
    return {"error": message, "code": code}


# --- Lines ---------------------------------------------------------------------


class Report(NamedTuple):
    lines: list  # [content, ending] pairs; ending "\r\n", "\n", or "" for an open last line
    bom: bool
    newline: str  # the ending each written line takes


def split_lines(text):
    """[content, ending] for each line; only the last line can have the ending ""."""
    pieces = text.split("\n")
    lines = []
    for index, piece in enumerate(pieces):
        if index == len(pieces) - 1:
            if piece:
                lines.append([piece, ""])
        elif piece.endswith("\r"):
            lines.append([piece[:-1], "\r\n"])
        else:
            lines.append([piece, "\n"])
    return lines


def join_lines(lines):
    return "".join(content + ending for content, ending in lines)


def parse_report(data):
    """A Report from the report file's bytes; raises UpdateError when they are not UTF-8."""
    bom = data.startswith(BOM)
    try:
        text = data[len(BOM):].decode("utf-8") if bom else data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UpdateError(INVALID_REPORT, f"the report is not UTF-8: {exc}") from exc
    lines = split_lines(text)
    first = next((ending for _, ending in lines if ending), "\n")
    return Report(lines, bom, first)


def report_bytes(report):
    return (BOM if report.bom else b"") + join_lines(report.lines).encode("utf-8")


def splice(report, start, stop, contents):
    """Replace lines [start, stop) with `contents`, each taking the report's newline.

    A file that ended without a newline still does, and every other line keeps
    its own ending.
    """
    lines = report.lines
    open_end = bool(lines) and lines[-1][1] == ""
    lines[start:stop] = [[content, report.newline] for content in contents]
    for line in lines[:-1]:
        if line[1] == "":
            line[1] = report.newline
    if open_end and lines:
        lines[-1][1] = ""


def stdin_lines(data):
    """The lines of stdin's bytes, decoded as UTF-8, each trailing carriage return dropped."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UpdateError(INVALID_INPUT, f"stdin is not UTF-8: {exc}") from exc
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def visible_lines(contents, start=0):
    """(visible, still_open): visible[i] is True when line i (from `start`) is
    outside fenced code and HTML comments; still_open is True when a fence or a
    comment never closes."""
    visible = [False] * len(contents)
    fence = None
    in_comment = False
    for index in range(start, len(contents)):
        line = contents[index]
        fence_match = _FENCE_RE.match(line)
        if fence is not None:
            marker = fence_match.group(1) if fence_match else ""
            if marker[:1] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if in_comment:
            in_comment = _COMMENT_CLOSE not in line
            continue
        if fence_match:
            fence = fence_match.group(1)
            continue
        if _COMMENT_OPEN_RE.match(line):
            in_comment = _COMMENT_CLOSE not in line
            continue
        visible[index] = True
    return visible, fence is not None or in_comment


def _cells(line):
    """Split one table row into its trimmed cells; `\\|` is a pipe inside a cell."""
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SEPARATOR_RE.split(row)]


def _shown(line, limit=80):
    return line if len(line) <= limit else line[: limit - 3] + "..."


# --- The frontmatter -------------------------------------------------------------


def frontmatter_end(report, reader):
    """The index of the frontmatter's closing `---` line, or None when the report has none.

    The frontmatter is the lines before split_frontmatter()'s body, as
    skf-report-delta.py derives the body's first line. The newline added at
    the end counts a closing `---` that ends the file without one.
    """
    text = join_lines(report.lines) + "\n"
    _, body = reader.split_frontmatter(text)
    count = len(text.split("\n")) - len(body.split("\n"))
    return count - 1 if count > 0 else None


def _key_index(contents, end, key):
    """The last top-level `key:` line of the frontmatter, or None."""
    found = None
    for index in range(1, end):
        name, sep, _ = contents[index].partition(":")
        if sep and not contents[index][:1].isspace() and name.strip() == key:
            found = index
    return found


def _list_tail(contents, end, index):
    """The index after the last line that belongs to the list starting on line `index`."""
    value = contents[index].partition(":")[2].strip()
    if value.startswith("["):
        if "]" in value:
            return index + 1
        for nxt in range(index + 1, end):
            if "]" in contents[nxt]:
                return nxt + 1
        return index + 1
    tail = index + 1
    for nxt in range(index + 1, end):
        stripped = contents[nxt].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not _BLOCK_ITEM_RE.match(stripped):
            break
        tail = nxt + 1
    return tail


def _value(value, kind_of_value, field):
    """The frontmatter text of one input value, or raise INVALID_INPUT naming the field."""
    if kind_of_value == VERDICT:
        if value not in VERDICTS:
            raise UpdateError(INVALID_INPUT, f"{field} is {value!r}, not one of: {', '.join(VERDICTS)}")
        return f'"{value}"'
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UpdateError(INVALID_INPUT, f"{field} is {value!r}, not a whole number")
    if kind_of_value == PERCENTAGE and value > 100:
        raise UpdateError(INVALID_INPUT, f"{field} is {value}, not a percentage from 0 to 100")
    return str(value)


def counts_to_set(kind, data):
    """The {frontmatter key: text} a set-counts call writes, from the parsed input."""
    spec = KINDS[kind]
    values = {}
    if spec.fields:
        if not isinstance(data, dict):
            raise UpdateError(INVALID_INPUT, f"the {kind} input must be a JSON object")
        if "error" in data:
            raise UpdateError(INVALID_INPUT, f"the {kind} input carries an error: {data['error']}")
        for field, key, kind_of_value in spec.fields:
            if field not in data:
                raise UpdateError(INVALID_INPUT, f"the {kind} input has no {field}")
            values[key] = _value(data[field], kind_of_value, field)
    for key, token in spec.fixed:
        values[key] = f'"{token}"'
    return values


def set_counts(report, reader, kind, data):
    """Set one kind's keys in the report's frontmatter; returns the summary fields."""
    end = frontmatter_end(report, reader)
    if end is None:
        raise UpdateError(INVALID_REPORT, "the report has no frontmatter block")
    values = counts_to_set(kind, data)
    stage = KINDS[kind].stage
    contents = [content for content, _ in report.lines]

    steps = None
    steps_at = _key_index(contents, end, STEPS_COMPLETED_KEY)
    if stage is not None:
        if steps_at is not None:
            value = contents[steps_at].partition(":")[2].strip()
            if value and not value.startswith(("[", "#")):
                raise UpdateError(INVALID_REPORT, f"the report frontmatter's {STEPS_COMPLETED_KEY} is "
                                                  f"{value!r}, not a list")
        text = join_lines(report.lines)
        steps = list(reader.frontmatter_list(text, STEPS_COMPLETED_KEY) or [])
        if stage not in steps:
            steps.append(stage)

    # Each edit: (start, stop, new lines), applied from the bottom up.
    edits = []
    added = []
    for key, text_value in values.items():
        at = _key_index(contents, end, key)
        if at is None:
            added.append(f"{key}: {text_value}")
        else:
            edits.append((at, at + 1, [f"{key}: {text_value}"]))
    if steps is not None:
        flow = f"{STEPS_COMPLETED_KEY}: [" + ", ".join(f"'{step}'" for step in steps) + "]"
        if steps_at is None:
            added.append(flow)
        else:
            edits.append((steps_at, _list_tail(contents, end, steps_at), [flow]))
    if added:
        edits.append((end, end, added))
    for start, stop, new in sorted(edits, key=lambda edit: edit[0], reverse=True):
        splice(report, start, stop, new)
    return {"kind": kind, "set": {key: _plain(text_value) for key, text_value in values.items()},
            STEPS_COMPLETED_KEY: steps}


def _plain(text_value):
    """A value as set-counts wrote it, back as JSON: a number, or a token without its quotes."""
    return text_value[1:-1] if text_value.startswith('"') else int(text_value)


# --- Sections and tables ---------------------------------------------------------


def _body_start(report, reader):
    end = frontmatter_end(report, reader)
    return 0 if end is None else end + 1


def find_section(contents, visible, start, heading):
    """(heading line, end) of the one `## heading` section; end is the next `#`
    or `##` heading, or the line count."""
    found = [index for index in range(start, len(contents))
             if visible[index] and (match := _H2_RE.match(contents[index])) and match.group(1).strip() == heading]
    if not found:
        raise UpdateError(INVALID_REPORT, f"the report has no `## {heading}` heading")
    if len(found) > 1:
        lines = " and ".join(str(index + 1) for index in found[:2])
        raise UpdateError(INVALID_REPORT, f"the report holds `## {heading}` twice (lines {lines})")
    at = found[0]
    end = next((index for index in range(at + 1, len(contents))
                if visible[index] and _LEVEL_1_2_RE.match(contents[index])), len(contents))
    return at, end


def fill_table(report, reader, heading, rows_data):
    """Replace the data rows of the first table under `## heading` with the stdin rows."""
    contents = [content for content, _ in report.lines]
    start = _body_start(report, reader)
    visible, _ = visible_lines(contents, start)
    at, end = find_section(contents, visible, start, heading)
    header = None
    for index in range(at + 1, end - 1):
        if not visible[index] or not contents[index].lstrip().startswith("|"):
            continue
        delimiter = contents[index + 1]
        if delimiter.lstrip().startswith("|") and all(_DELIMITER_CELL_RE.match(cell) for cell in _cells(delimiter)):
            header = index
            break
    if header is None:
        raise UpdateError(INVALID_REPORT, f"the report has no table under `## {heading}`")
    width = len(_cells(contents[header]))
    first = stop = header + 2
    while stop < end and contents[stop].lstrip().startswith("|"):
        stop += 1

    rows = []
    for number, line in enumerate(stdin_lines(rows_data), start=1):
        if not line.strip():
            continue
        if not line.lstrip().startswith("|"):
            raise UpdateError(INVALID_INPUT, f"stdin line {number} is not a table row: {_shown(line)!r}")
        cells = len(_cells(line))
        if cells != width:
            raise UpdateError(INVALID_INPUT, f"stdin line {number} has {cells} cells but the `## {heading}` "
                                             f"table has {width}: {_shown(line)!r}")
        rows.append(line)
    splice(report, first, stop, rows)
    return {"heading": heading, "rows": len(rows)}


def section_content(content_data, subsection):
    """The content lines of a replace-section call, blank lines around them dropped."""
    lines = stdin_lines(content_data)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise UpdateError(INVALID_INPUT, "stdin holds no content")
    visible, still_open = visible_lines(lines)
    if still_open:
        raise UpdateError(INVALID_INPUT, "the content leaves a fenced code block or an HTML comment open")
    heading = _LEVEL_1_3_RE if subsection else _LEVEL_1_2_RE
    for index, line in enumerate(lines):
        if visible[index] and heading.match(line):
            levels = "`#`, `##` or `###`" if subsection else "`#` or `##`"
            raise UpdateError(INVALID_INPUT, f"content line {index + 1} is a {levels} heading, which would end "
                                             f"the section: {_shown(line)!r}")
    return lines


def _break_at(contents, visible, low, high):
    """Where the closing `---` break of lines [low, high) starts, or high when there is none."""
    index = high
    while index > low and not contents[index - 1].strip():
        index -= 1
    if index > low and visible[index - 1] and contents[index - 1].strip() == "---":
        return index - 1
    return high


def replace_section(report, reader, heading, subsection, content_data):
    """Replace the body of `## heading`, or its `### subsection` block, with the content."""
    content = section_content(content_data, subsection)
    contents = [line for line, _ in report.lines]
    start = _body_start(report, reader)
    visible, _ = visible_lines(contents, start)
    at, end = find_section(contents, visible, start, heading)
    brk = _break_at(contents, visible, at + 1, end)
    total = len(contents)

    if subsection is None:
        splice(report, at + 1, brk, ["", *content, *([""] if brk < total else [])])
        return {"heading": heading, "subsection": None, "lines": len(content)}

    blocks = [index for index in range(at + 1, brk)
              if visible[index] and (match := _H3_RE.match(contents[index]))
              and match.group(1).strip() == subsection]
    if len(blocks) > 1:
        lines = " and ".join(str(index + 1) for index in blocks[:2])
        raise UpdateError(INVALID_REPORT, f"`## {heading}` holds `### {subsection}` twice (lines {lines})")
    block = [f"### {subsection}", "", *content]
    if blocks:
        first = blocks[0]
        stop = next((index for index in range(first + 1, brk)
                     if visible[index] and _LEVEL_1_3_RE.match(contents[index])), brk)
        splice(report, first, stop, [*block, *([""] if stop < total else [])])
    else:
        tail = brk
        while tail > at + 1 and not contents[tail - 1].strip():
            tail -= 1
        splice(report, tail, brk, ["", *block, *([""] if brk < total else [])])
    return {"heading": heading, "subsection": subsection, "lines": len(content)}


# --- Running a call --------------------------------------------------------------


def load_reader():
    """Import the shared feasibility-report reader, or None when it is missing."""
    try:
        if not SHARED_READER.is_file():
            return None
    except OSError:
        return None  # a folder on the way that cannot be searched
    spec = importlib.util.spec_from_file_location("skf_validate_feasibility_report", SHARED_READER)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _present(script):
    """True when a shared script is a file; False too when a folder on the way cannot be searched."""
    try:
        return script.is_file()
    except OSError:
        return False


def atomic_write(target, data, writer=ATOMIC_WRITER):
    """Write `data` to `target` with `skf-atomic-write.py write`; None, or why it failed."""
    try:
        result = subprocess.run(
            [sys.executable, str(writer), "write", "--target", str(target)],
            input=data,
            capture_output=True,
            timeout=WRITE_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{writer.name} could not run: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        return f"{writer.name} write exited {result.returncode}: {detail or 'no message'}"
    return None


def parse_json_input(kind, data):
    """The parsed stdin of a set-counts call (None for a kind that reads none)."""
    if not KINDS[kind].reads_stdin:
        return None
    lines = stdin_lines(data)
    text = "\n".join(lines)
    if not text.strip():
        raise UpdateError(INVALID_INPUT, f"stdin holds no {kind} JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise UpdateError(INVALID_INPUT, f"stdin is not JSON: {exc.msg}") from exc


def run(args, stdin_data, reader, writer=ATOMIC_WRITER):
    """(result, exit code) of one call: `args` as _build_parser() parses them,
    `stdin_data` the bytes on stdin (ignored by a kind that reads none)."""
    path = Path(args.report)
    try:
        original = path.read_bytes()
        report = parse_report(original)
        if args.command == "set-counts":
            summary = set_counts(report, reader, args.kind, parse_json_input(args.kind, stdin_data))
        elif args.command == "fill-table":
            summary = fill_table(report, reader, args.heading, stdin_data)
        else:
            summary = replace_section(report, reader, args.heading, args.subsection, stdin_data)
    except OSError as exc:
        return make_error(f"cannot read the report {args.report}: {exc}", INVALID_REPORT), 2
    except UpdateError as exc:
        return make_error(exc.message, exc.code), 2
    updated = report_bytes(report)
    changed = updated != original
    if changed:
        failure = atomic_write(path, updated, writer)
        if failure:
            return make_error(failure, WRITE_FAILED), 3
    return {"status": "ok", "report": args.report, "changed": changed, **summary}, 0


# --- CLI ----------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-report-update",
        # The module docstring is the contract the stages point --help at:
        # each kind's keys, what a table fill and a section replace touch,
        # and the exit codes.
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{set-counts,fill-table,replace-section}")

    counts = sub.add_parser("set-counts", help="set one kind's frontmatter keys from a helper's JSON on stdin")
    counts.add_argument("--report", required=True, metavar="REPORT", help="the feasibility report to edit")
    counts.add_argument("--kind", required=True, choices=tuple(KINDS),
                        help="whose JSON stdin holds (requirements-skipped reads none)")

    table = sub.add_parser("fill-table", help="replace the data rows of the first table under a heading")
    table.add_argument("--report", required=True, metavar="REPORT", help="the feasibility report to edit")
    table.add_argument("--heading", required=True, metavar="H", help="the `## H` heading the table sits under")

    section = sub.add_parser("replace-section", help="replace the body of a section, or one subsection of it")
    section.add_argument("--report", required=True, metavar="REPORT", help="the feasibility report to edit")
    section.add_argument("--heading", required=True, metavar="H", help="the `## H` heading of the section")
    section.add_argument("--subsection", metavar="S",
                         help="replace, or append, only the `### S` block of that section")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    missing = [script.name for script in (SHARED_READER, ATOMIC_WRITER) if not _present(script)]
    reader = load_reader() if not missing else None
    if reader is None:
        names = ", ".join(missing) or SHARED_READER.name
        message = f"the shared {names} is not installed beside this skill; nothing written"
        print(json.dumps(make_error(message, HELPER_MISSING), indent=2))
        return 1
    reads_stdin = args.command != "set-counts" or KINDS[args.kind].reads_stdin
    stdin_data = sys.stdin.buffer.read() if reads_stdin else b""
    result, code = run(args, stdin_data, reader)
    print(json.dumps(result, indent=2))
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure the given streams to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a report line in an error message may hold.
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
    raise SystemExit(main())
