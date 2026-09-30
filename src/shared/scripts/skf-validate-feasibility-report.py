#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""SKF Validate Feasibility Report: deterministic structure/schema gate and locator.

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
quotes stripped. This is sufficient for the `schemaVersion` and
`overallVerdict` scalars and keeps the script stdlib-only.

Locate mode (--locate <folder> --project-name <name>) finds and reads the
report for a consumer, so no workflow builds the file name or parses the
verdict table in prose:

  1. The project name becomes the producer's `{project_slug}` (slugify()):
     NFKD-decomposed with combining marks dropped, so `Café` gives `cafe`;
     letters and digits with no ASCII form dropped; lowercased; every run of
     other characters (spaces, punctuation, symbols) turned into one hyphen;
     hyphens trimmed from both ends; `project` when nothing is left, which
     includes an empty name.
  2. Only <folder>/feasibility-report-<slug>-latest.md is read, the stable
     copy: a timestamped report can be a halted run's partial report.
  3. A report whose schemaVersion is not "1.0" is not interpreted: no verdict
     is read from it. Otherwise overallVerdict comes from the frontmatter and
     pairVerdicts from the canonical `| lib_a | lib_b | verdict | rationale |`
     table under `## Integration Verdicts`, and only that table (the display
     table with more columns below it is not read). Fenced code and HTML
     comments are skipped, so an example table in either is not read. The
     report holds the canonical table once: a second one is a schema
     violation (duplicateVerdictTableLine), since reading only the first,
     say the template's empty table left above the filled one, would drop
     every pair. Verdict tokens are case-sensitive: a token outside the
     schema's set is listed in unknownTokens, never dropped or mapped, and
     its row stays in pairVerdicts as written.

  {
    "status": "ok" | "not-found" | "error",
    "projectName": "<name>",
    "projectSlug": "<slug>",
    "latestPath": "<folder>/feasibility-report-<slug>-latest.md",
    "path": "<latestPath>" | null,        # null when the report does not exist
    "schemaVersion": "<value>" | null,
    "schemaVersionOk": bool | null,       # null when the report was not read
    "overallVerdict": "<token>" | null,
    "verdictTableFound": bool | null,     # null when the report was not interpreted
    "duplicateVerdictTableLine": int | null,
    "pairVerdicts": [{"lib_a", "lib_b", "verdict", "rationale"}, ...],
    "unknownTokens": [{"field": "overallVerdict", "token"},
                      {"field": "verdict", "line", "lib_a", "lib_b", "token"}],
    "violation": "schema-violation" | "io-error" | null,
    "error": "<message>"                  # on io-error only
  }

`line` is the 1-based line of the table row in the report file, and
duplicateVerdictTableLine the 1-based line of the second canonical table's
header row (null when there is none). The producer can take `projectSlug`
from any locate result, whatever the status.

Exit codes, validate mode (per script-standards):
  0  valid          — all sections present + in order AND schemaVersion == "1.0"
  1  schema-violation — missing/mis-ordered section, or schemaVersion mismatch
                        (the JSON `violation` field + detail lists carry why)
  2  IO/parse error  — report file could not be read

Exit codes, locate mode:
  0  status "ok": the report exists, its schemaVersion is "1.0", the canonical
     table is there once and every token is known. Also status "not-found":
     there is no -latest report for this project, and the caller goes on
     without one
  1  schema-violation: the report's schemaVersion is not "1.0", the canonical
     table is missing or there twice, or a verdict token is unknown
  2  the report exists but could not be read (violation "io-error"). Also a
     usage error, which prints no JSON: --locate without --project-name,
     --project-name without --locate, or an empty folder

CLI:
  python3 skf-validate-feasibility-report.py <report.md>
  python3 skf-validate-feasibility-report.py <report.md> -o result.json
  python3 skf-validate-feasibility-report.py --locate <folder> --project-name <name>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
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

# Verdict tokens per the shared schema; both sets are case-sensitive.
OVERALL_VERDICTS = ("FEASIBLE", "CONDITIONALLY_FEASIBLE", "NOT_FEASIBLE")
PAIR_VERDICTS = ("Verified", "Plausible", "Risky", "Blocked")

# The section that holds the pair table, and the table's fixed header row.
VERDICTS_HEADING = "Integration Verdicts"
VERDICT_TABLE_HEADER = ["lib_a", "lib_b", "verdict", "rationale"]

# The stable copy the producer writes next to each timestamped report. --locate
# reads only this file: a timestamped report can be a halted run's partial one.
LATEST_REPORT_NAME = "feasibility-report-{slug}-latest.md"

# The slug of a project name that leaves no ASCII letter or digit (a name
# written only in a script with no ASCII form, such as Japanese).
FALLBACK_SLUG = "project"

# A level-2 markdown heading: exactly two '#', then whitespace, then the text.
# `### Foo` does not match (the 3rd char is '#', not whitespace).
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")

# A level 1 or 2 heading: it ends the section before it, and starts an
# Integration Verdicts section when its text is VERDICTS_HEADING.
_SECTION_END_RE = re.compile(r"^#{1,2}\s")

# The opening or closing line of a fenced code block.
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

# The first line of an HTML comment block (CommonMark HTML block type 2). The
# block ends on the first line that holds _COMMENT_CLOSE, which can be this one.
_COMMENT_OPEN_RE = re.compile(r"^\s{0,3}<!--")
_COMMENT_CLOSE = "-->"

# A pipe that separates table cells; `\|` is a pipe inside a cell (GFM).
_CELL_SEPARATOR_RE = re.compile(r"(?<!\\)\|")

# One cell of a table's delimiter row: `---`, `:--`, `--:` or `:-:`.
_DELIMITER_CELL_RE = re.compile(r"^:?-+:?$")

_HYPHEN_RUN_RE = re.compile(r"-+")


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
        # utf-8-sig drops the byte order mark some editors add, which would
        # otherwise hide the frontmatter's opening `---`.
        content = p.read_text(encoding="utf-8-sig")
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


def slugify(project_name):
    """Return the `{project_slug}` of a project name (the producer's rule).

    NFKD-decompose the name and drop its combining marks, so an accented Latin
    letter keeps its base letter (`Café` -> `cafe`) and compatibility forms
    fold to ASCII (full-width letters, ligatures, superscripts). A letter or
    digit that still has no ASCII form is dropped (`Straße` -> `strae`).
    Lowercase the rest, turn every run of other characters (spaces,
    punctuation and symbols of any script) into one hyphen, and trim hyphens
    from both ends. A name that leaves nothing gets FALLBACK_SLUG.

    Deterministic and idempotent: slugify(slugify(name)) == slugify(name).
    """
    kept = []
    for ch in unicodedata.normalize("NFKD", project_name):
        if unicodedata.category(ch).startswith("M"):
            continue  # a combining mark; the letter it sat on stays
        if ch.isascii() and ch.isalnum():
            kept.append(ch.lower())
        elif ch.isalnum():
            continue  # a letter or digit with no ASCII form
        else:
            kept.append("-")
    return _HYPHEN_RUN_RE.sub("-", "".join(kept)).strip("-") or FALLBACK_SLUG


def _table_cells(line):
    """Split one markdown table row into its trimmed cells.

    The leading pipe is stripped and so is a trailing one; `\\|` is a pipe
    inside a cell (GFM) and comes back as `|`.
    """
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SEPARATOR_RE.split(row)]


def read_verdict_table(body, first_line=1):
    """Read the canonical pair table under `## Integration Verdicts`.

    Returns (found, rows, duplicate_line). `found` is True when that section
    holds a table whose header row is exactly VERDICT_TABLE_HEADER, followed
    by a delimiter row. `rows` lists each data row of the first such table as
    (line_number, [lib_a, lib_b, verdict, rationale]), counting lines from
    `first_line`, the file line of the body's first line. Table lines start
    with a pipe, and a table ends at the first line that does not. Fenced
    code and HTML comments (from a line that starts with `<!--` to the first
    line that holds `-->`) are skipped, so an example table in either is not
    read. The display table the producer writes below the canonical one has
    more columns, so its header never matches.

    The report holds the canonical table once. `duplicate_line` is the file
    line of the header row of a second one, in the same section or in a
    repeated `## Integration Verdicts` section, and None when there is none:
    a producer that appends its table below the template's empty one leaves
    two, and reading only the first would drop every pair.

    A row with fewer than four cells gets empty ones; a row with more keeps
    the extra cells in its rationale (an unescaped `|` in the text).

    Deterministic: same body, same result.
    """
    width = len(VERDICT_TABLE_HEADER)
    lines = body.split("\n")
    found, rows = False, []
    fence = None
    in_comment = False
    in_section = False
    resume = 0  # the line after the first canonical table's last row
    for idx, line in enumerate(lines):
        if idx < resume:
            continue
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
        if _SECTION_END_RE.match(line):
            heading = _H2_RE.match(line)
            in_section = heading is not None and heading.group(1).strip() == VERDICTS_HEADING
            continue
        if not in_section or not line.lstrip().startswith("|"):
            continue
        if _table_cells(line) != VERDICT_TABLE_HEADER:
            continue
        delimiter = lines[idx + 1] if idx + 1 < len(lines) else ""
        delimiter_cells = _table_cells(delimiter)
        if not (
            delimiter.lstrip().startswith("|")
            and len(delimiter_cells) == width
            and all(_DELIMITER_CELL_RE.match(cell) for cell in delimiter_cells)
        ):
            continue
        if found:
            return True, rows, first_line + idx
        found = True
        resume = idx + 2
        while resume < len(lines) and lines[resume].lstrip().startswith("|"):
            cells = _table_cells(lines[resume])
            if len(cells) > width:
                cells = cells[: width - 1] + [" | ".join(cells[width - 1:])]
            cells += [""] * (width - len(cells))
            rows.append((first_line + resume, cells))
            resume += 1
    return found, rows, None


def locate_report(folder, project_name):
    """Find a project's -latest feasibility report and read its verdicts.

    Returns (result_dict, exit_code): see "Locate mode" in the module
    docstring for the keys and the exit codes.
    """
    slug = slugify(project_name)
    latest = Path(folder) / LATEST_REPORT_NAME.format(slug=slug)
    result = {
        "status": "not-found",
        "projectName": project_name,
        "projectSlug": slug,
        "latestPath": str(latest),
        "path": None,
        "schemaVersion": None,
        "schemaVersionOk": None,
        "overallVerdict": None,
        "verdictTableFound": None,
        "duplicateVerdictTableLine": None,
        "pairVerdicts": [],
        "unknownTokens": [],
        "violation": None,
    }
    try:
        if not latest.is_file():
            return result, 0
        content = latest.read_text(encoding="utf-8-sig")  # see validate_report
    except (OSError, UnicodeDecodeError) as e:
        result.update(
            status="error",
            path=str(latest),
            violation="io-error",
            error=f"could not read report file: {e}",
        )
        return result, 2

    fm, body = split_frontmatter(content)
    schema_version = fm.get("schemaVersion")  # None if the key is absent
    result["path"] = str(latest)
    result["schemaVersion"] = schema_version
    result["schemaVersionOk"] = schema_version == EXPECTED_SCHEMA_VERSION
    if not result["schemaVersionOk"]:
        # An unknown version is never interpreted: no verdict is read from it.
        result.update(status="error", violation="schema-violation")
        return result, 1

    overall = fm.get("overallVerdict")
    unknown = []
    if overall not in OVERALL_VERDICTS:
        unknown.append({"field": "overallVerdict", "token": overall})

    # The body starts on the file line after the frontmatter's closing `---`.
    first_line = len(content.split("\n")) - len(body.split("\n")) + 1
    found, rows, duplicate_line = read_verdict_table(body, first_line)
    pairs = []
    for line_number, cells in rows:
        pair = dict(zip(VERDICT_TABLE_HEADER, cells))
        pairs.append(pair)
        if pair["verdict"] not in PAIR_VERDICTS:
            unknown.append(
                {
                    "field": "verdict",
                    "line": line_number,
                    "lib_a": pair["lib_a"],
                    "lib_b": pair["lib_b"],
                    "token": pair["verdict"],
                }
            )

    ok = found and duplicate_line is None and not unknown
    result.update(
        status="ok" if ok else "error",
        overallVerdict=overall,
        verdictTableFound=found,
        duplicateVerdictTableLine=duplicate_line,
        pairVerdicts=pairs,
        unknownTokens=unknown,
        violation=None if ok else "schema-violation",
    )
    return result, (0 if ok else 1)


class _PairedFlagsParser(argparse.ArgumentParser):
    """Check the flags that only work together as part of parsing.

    The checks run in parse_known_args, which parse_args calls, so a caller
    that only parses with the parser _build_parser() returns (the helper-call
    contract test does) refuses `--locate` without `--project-name` as main()
    does.
    """

    def parse_known_args(self, args=None, namespace=None):
        parsed, extras = super().parse_known_args(args, namespace)
        if parsed.locate is not None:
            if parsed.project_name is None:
                self.error("--project-name is required with --locate")
            if not parsed.locate.strip():
                self.error("--locate needs a folder path")
        elif parsed.project_name is not None:
            self.error("--project-name only applies with --locate")
        return parsed, extras


def _build_parser():
    parser = _PairedFlagsParser(
        description=(
            "Validate a feasibility report's section order and schemaVersion, "
            "or locate a project's report and read its verdicts. Given a "
            "report path: confirms the five required body sections (Executive "
            "Summary, Coverage Analysis, Integration Verdicts, Recommendations, "
            "Evidence Sources) are present and in canonical order, and that "
            "frontmatter schemaVersion == \"1.0\"; exit 0 valid, 1 "
            "schema-violation, 2 IO/parse error. Given --locate FOLDER "
            "--project-name NAME: reads FOLDER/feasibility-report-<slug>-latest.md, "
            "the slug made from NAME by the producer's rule, and returns its "
            "schemaVersion, overallVerdict, pairVerdicts (from the one canonical "
            "Integration Verdicts table) and unknownTokens; exit 0 ok or "
            "not-found, 1 schema-violation, 2 IO or usage error."
        )
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "report", nargs="?", help="path to the feasibility report .md file to validate"
    )
    target.add_argument(
        "--locate",
        metavar="FOLDER",
        help=(
            "find and read the project's feasibility-report-<slug>-latest.md in "
            "FOLDER (the forge data folder); needs --project-name"
        ),
    )
    parser.add_argument(
        "--project-name",
        metavar="NAME",
        help=(
            "the project_name the report was written for (with --locate); a "
            "name that leaves no slug, an empty one included, gets the slug "
            "'project'"
        ),
    )
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
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if args.locate is not None:
        result, exit_code = locate_report(args.locate, args.project_name)
    else:
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
