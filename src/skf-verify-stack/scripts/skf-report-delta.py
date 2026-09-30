#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Deterministic previous-vs-current delta for skf-verify-stack (synthesize.md §3).

Deciding each finding's verdict is judgment, made by the run that wrote the
report; classifying how two runs differ is not. "improved / regressed / new /
unchanged" is a set-diff plus a fixed verdict ranking, one correct answer per
input. Doing it in prose lets the counts drift (mismatched pair keys,
inconsistent ranking), so it lives here. So does reading the finding sets out
of the two reports (--previous-report, --current-report): each one sits in a
table with a pinned header, so reading it has one correct answer too.

Verdict ranking (higher = healthier):
  * coverage    — Missing(0) < Covered(1). Replaced is intentional removal, not a
    gap; Replaced findings are bucketed separately and never scored improved/
    regressed (mirrors their exclusion from the coverage denominator).
  * integration — Blocked(0) < Risky(1) < Plausible(2) < Verified(3).
  * evidence tier: T3(0) < T2(1) < T1-low(2) < T1(3); a drop is a regression.

Tiers use one scale, the confidence tiers T1, T1-low, T2 and T3 (case-sensitive),
for every skill: the caller maps each skill to it before calling (verify-stack
passes skf-enumerate-stack-skills.py's evidence_tier). metadata.json
`confidence_tier` is no input here: a single skill records its forge tier there
(Quick, Forge, Forge+ or Deep) and a stack its confidence tier, so its values sit
on two scales that do not compare. Any other token, a forge tier included, is
rejected (exit 2, code UNKNOWN_TIER), never skipped: a skipped token would hide
a regression.

Matching keys are normalized so identity is stable across runs:
  * coverage findings match on technology.lower()
  * integration findings match on the unordered pair {libA, libB} (lowercased),
    so "A↔B" in one run equals "B↔A" in the other.

Reading a report (--previous-report, --current-report):
  * A report whose frontmatter schemaVersion is not "1.0" is not read.
  * coverage: the Technology and Verdict columns of the first table under
    `## Coverage Analysis` whose header row has both (coverage.md §6 writes
    `| Technology | Source Section | Skill Match | Verdict |`).
  * integration: the lib_a, lib_b and verdict columns of the canonical
    `| lib_a | lib_b | verdict | rationale |` table under
    `## Integration Verdicts`, read by read_verdict_table() of the shared
    skf-validate-feasibility-report.py, the reader the report's consumers use.
    A report with no such table, or with two, is not read.
  * tiers, from the previous report only: the skill and evidence_tier columns
    of the first table under `## Evidence Sources` whose header row has both
    (synthesize.md §5 writes `| skill | evidence_tier | confidence_tier |
    metadata_schema_version | skill_md |`). A report written before tiers were
    recorded has no such table, or one with no row: previousTiersRecorded is
    then false and no tier is compared.
  Tables in fenced code or in an HTML comment are skipped. A verdict or tier
  cell holds the token alone (case-sensitive), and every row names its
  technology, its two libraries or its skill.

CLI usage:
  uv run skf-report-delta.py '<JSON>'                  # JSON literal positional
  uv run skf-report-delta.py --json-input '<JSON>'     # explicit flag form
  cat input.json | uv run skf-report-delta.py --stdin  # piped input
  echo '{"currentTiers": {...}}' | uv run skf-report-delta.py \\
      --previous-report <earlier.md> --current-report <this-run.md> --stdin

  --previous-report fills `previous` and `previousTiers` from that report and
  --current-report fills `current` from its report, so the JSON leaves them
  out; with both flags the JSON may be left out too. --no-tiers compares no
  tier: both tier maps and the previous report's tier table are ignored.

Input schema (one object):
  {
    "previous": {
      "coverage":    [{"technology": "react", "verdict": "Covered"}, ...],
      "integration": [{"libA": "react", "libB": "express", "verdict": "Verified"}, ...]
    },
    "current":  { ... same shape ... },
    "previousTiers": {"react": "T1", ...},   # optional, skill_name -> T1|T1-low|T2|T3
    "currentTiers":  {"react": "T2", ...}     # optional, same scale
  }

Output (stdout, one object):
  {
    "improved": [labels], "improvedCount": <int>,
    "regressed": [labels], "regressedCount": <int>,
    "unchanged": [labels], "unchangedCount": <int>,
    "new": [labels], "newCount": <int>,
    "dropped": [labels], "droppedCount": <int>,
    "replaced": [labels], "replacedCount": <int>,
    "tierDowngrades": [{"skill": "...", "from": "T1", "to": "T2"}],
    "tierDowngradeCount": <int>,
    "tiersCompared": <bool>,                # both tier maps were there to compare
    "previousTiersRecorded": <bool> | null  # --previous-report: the report records
                                            # tiers; null without it or with --no-tiers
  }

Errors (stdout, one object): {"error": "<why>", "code": "<code>"}, plus "report"
("previous" or "current") and "path" when the error comes from a report:
  INVALID_INPUT   the JSON does not fit the input schema above
  UNKNOWN_TIER    a tier token outside T1, T1-low, T2 and T3
  INVALID_REPORT  a report that cannot be read, or is not read (see above)
  HELPER_MISSING  the shared skf-validate-feasibility-report.py is not in the
                  shared scripts folder beside this skill's folder

Exit codes:
  0  delta emitted successfully
  1  no input, input that is not JSON, or HELPER_MISSING
  2  input rejected: INVALID_INPUT, UNKNOWN_TIER or INVALID_REPORT
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

COVERAGE_RANK = {"Missing": 0, "Covered": 1}
COVERAGE_VERDICTS = ("Covered", "Missing", "Replaced")
INTEGRATION_RANK = {"Blocked": 0, "Risky": 1, "Plausible": 2, "Verified": 3}
INTEGRATION_VERDICTS = tuple(INTEGRATION_RANK)
TIER_RANK = {"T3": 0, "T2": 1, "T1-low": 2, "T1": 3}
TIERS = tuple(sorted(TIER_RANK, key=TIER_RANK.get, reverse=True))  # strongest first

INVALID_INPUT = "INVALID_INPUT"
UNKNOWN_TIER = "UNKNOWN_TIER"
INVALID_REPORT = "INVALID_REPORT"
HELPER_MISSING = "HELPER_MISSING"

# The shared feasibility-report reader. Installed (under _bmad/skf/ or an
# IDE's skills folder) and in a dev checkout (src/), shared/ sits beside
# this skill's folder.
SHARED_READER = (
    Path(__file__).resolve().parent.parent.parent
    / "shared"
    / "scripts"
    / "skf-validate-feasibility-report.py"
)
SCHEMA_VERSION = "1.0"

# The two tables read here besides the canonical verdict table: the section
# each sits under and the columns read from it (see "Reading a report").
COVERAGE_SECTION = "Coverage Analysis"
COVERAGE_COLUMNS = ("Technology", "Verdict")
TIERS_SECTION = "Evidence Sources"
TIER_COLUMNS = ("skill", "evidence_tier")

# Table scanning, the way the shared reader scans for the verdict table.
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_COMMENT_OPEN_RE = re.compile(r"^\s{0,3}<!--")
_COMMENT_CLOSE = "-->"
_SECTION_END_RE = re.compile(r"^#{1,2}\s")
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_CELL_SEPARATOR_RE = re.compile(r"(?<!\\)\|")
_DELIMITER_CELL_RE = re.compile(r"^:?-+:?$")


class ReportError(Exception):
    """A report the delta does not read; `code` is INVALID_REPORT or UNKNOWN_TIER."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def make_error(message, code=INVALID_INPUT):
    return {"error": message, "code": code}


def _validate_side(side, name):
    if not isinstance(side, dict):
        return f"`{name}` must be an object with `coverage`/`integration` lists"
    cov = side.get("coverage", [])
    integ = side.get("integration", [])
    if not isinstance(cov, list) or not isinstance(integ, list):
        return f"`{name}.coverage` and `{name}.integration` must be lists"
    for i, row in enumerate(cov):
        if not isinstance(row, dict) or not isinstance(row.get("technology"), str):
            return f"`{name}.coverage[{i}]` requires a string `technology`"
        if row.get("verdict") not in COVERAGE_VERDICTS:
            return (
                f"`{name}.coverage[{i}]` verdict {row.get('verdict')!r} not one of: "
                f"{', '.join(COVERAGE_VERDICTS)}"
            )
    for i, row in enumerate(integ):
        if not isinstance(row, dict) or not isinstance(row.get("libA"), str) or not isinstance(row.get("libB"), str):
            return f"`{name}.integration[{i}]` requires string `libA` and `libB`"
        if row.get("verdict") not in INTEGRATION_VERDICTS:
            return (
                f"`{name}.integration[{i}]` verdict {row.get('verdict')!r} not one of: "
                f"{', '.join(INTEGRATION_VERDICTS)}"
            )
    return None


def _validate(inp):
    """Return (message, code) for an input compute() rejects, else None."""
    if inp is None or not isinstance(inp, dict):
        return "Input must be a JSON object", INVALID_INPUT
    if "previous" not in inp or "current" not in inp:
        return "Input requires `previous` and `current` objects", INVALID_INPUT
    for name in ("previous", "current"):
        err = _validate_side(inp[name], name)
        if err:
            return err, INVALID_INPUT
    for key in ("previousTiers", "currentTiers"):
        tiers = inp.get(key)
        if tiers is None:
            continue
        if not isinstance(tiers, dict):
            return f"`{key}` must be an object mapping skill_name -> tier", INVALID_INPUT
        for skill, tier in tiers.items():
            if tier not in TIERS:
                return (
                    f"`{key}.{skill}` tier {tier!r} not one of: {', '.join(TIERS)} "
                    "(map each skill to its evidence tier before calling; a forge tier "
                    "such as Deep is on another scale)",
                    UNKNOWN_TIER,
                )
    return None


def _index(side):
    """Return {normalized_key: (label, domain, verdict)} for one report side."""
    out = {}
    for row in side.get("coverage", []):
        tech = row["technology"].strip()
        out[("cov", tech.lower())] = (tech, "coverage", row["verdict"])
    for row in side.get("integration", []):
        a, b = row["libA"].strip(), row["libB"].strip()
        pair = tuple(sorted([a.lower(), b.lower()]))
        out[("int", pair)] = (f"{a} ↔ {b}", "integration", row["verdict"])
    return out


def _rank(domain, verdict):
    return COVERAGE_RANK.get(verdict) if domain == "coverage" else INTEGRATION_RANK.get(verdict)


def compute(inp):
    """Pure delta over the two finding sets."""
    err = _validate(inp)
    if err:
        return make_error(*err)

    prev = _index(inp["previous"])
    curr = _index(inp["current"])

    buckets = {k: [] for k in ("improved", "regressed", "unchanged", "new", "dropped", "replaced")}

    for key, (label, domain, verdict) in curr.items():
        if key not in prev:
            # Replaced-on-arrival is informational, not a regression/new gap.
            if verdict == "Replaced":
                buckets["replaced"].append(label)
            else:
                buckets["new"].append(label)
            continue
        _, _, prev_verdict = prev[key]
        if verdict == "Replaced" or prev_verdict == "Replaced":
            buckets["replaced"].append(label)
            continue
        pr, cr = _rank(domain, prev_verdict), _rank(domain, verdict)
        if cr > pr:
            buckets["improved"].append(label)
        elif cr < pr:
            buckets["regressed"].append(label)
        else:
            buckets["unchanged"].append(label)

    for key, (label, _domain, verdict) in prev.items():
        if key not in curr:
            if verdict == "Replaced":
                buckets["replaced"].append(label)
            else:
                buckets["dropped"].append(label)

    prev_tiers = inp.get("previousTiers")
    curr_tiers = inp.get("currentTiers")
    compared = prev_tiers is not None and curr_tiers is not None
    tier_downgrades = []
    for skill in sorted(set(prev_tiers or {}) & set(curr_tiers or {})):
        pr = TIER_RANK[prev_tiers[skill]]
        cr = TIER_RANK[curr_tiers[skill]]
        if cr < pr:
            tier_downgrades.append({"skill": skill, "from": prev_tiers[skill], "to": curr_tiers[skill]})

    result = {}
    for name, items in buckets.items():
        result[name] = sorted(items)
        result[name + "Count"] = len(items)
    result["tierDowngrades"] = tier_downgrades
    result["tierDowngradeCount"] = len(tier_downgrades)
    result["tiersCompared"] = compared
    return result


# --- Reading a report ---------------------------------------------------------


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


def _cells(line):
    """Split one table row into its trimmed cells; `\\|` is a pipe inside a cell."""
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SEPARATOR_RE.split(row)]


def _section_tables(body, section, first_line):
    """Yield (header, rows) for each table under `## {section}`.

    `header` holds the header row's cells, and `rows` each data row as
    (file_line, cells), counting from `first_line`, the file line of the
    body's first line. A table is a line that starts with a pipe, then a
    delimiter row, then every following line that starts with a pipe.
    Fenced code and HTML comments are skipped.
    """
    lines = body.split("\n")
    fence = None
    in_comment = in_section = False
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        idx += 1
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
            in_section = heading is not None and heading.group(1).strip() == section
            continue
        if not in_section or not line.lstrip().startswith("|") or idx >= len(lines):
            continue
        delimiter = lines[idx]
        if not delimiter.lstrip().startswith("|") or not all(
            _DELIMITER_CELL_RE.match(cell) for cell in _cells(delimiter)
        ):
            continue
        header, rows = _cells(line), []
        idx += 1
        while idx < len(lines) and lines[idx].lstrip().startswith("|"):
            rows.append((first_line + idx, _cells(lines[idx])))
            idx += 1
        yield header, rows


def _columns(tables, wanted):
    """The first table whose header has every wanted column, as (indexes, rows), else None."""
    for header, rows in tables:
        if all(name in header for name in wanted):
            return [header.index(name) for name in wanted], rows
    return None


def _cell(cells, index):
    return cells[index] if index < len(cells) else ""


def read_report(path, reader, with_tiers):
    """Read one report's finding sets (see "Reading a report").

    Returns (side, tiers): `side` is {"coverage": [...], "integration": [...]}
    in compute()'s input shape, and `tiers` maps each skill to its evidence
    tier, or is None when `with_tiers` is false or the report records no
    tier. Raises ReportError for a report that is not read.
    """
    shown = f"`{path}`"
    try:
        # utf-8-sig drops the byte order mark some editors add, as the shared
        # reader does.
        content = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReportError(INVALID_REPORT, f"{shown} cannot be read: {exc}") from exc
    frontmatter, body = reader.split_frontmatter(content)
    version = frontmatter.get("schemaVersion")
    if version != SCHEMA_VERSION:
        found = "no schemaVersion" if version is None else f"schemaVersion {version!r}"
        raise ReportError(INVALID_REPORT, f"{shown} has {found}, not {SCHEMA_VERSION!r}")
    # The body starts on the file line after the frontmatter's closing `---`.
    first_line = len(content.split("\n")) - len(body.split("\n")) + 1

    table = _columns(_section_tables(body, COVERAGE_SECTION, first_line), COVERAGE_COLUMNS)
    if table is None:
        raise ReportError(
            INVALID_REPORT,
            f"{shown} has no table with Technology and Verdict columns under `## {COVERAGE_SECTION}`",
        )
    (tech_at, verdict_at), rows = table
    coverage = []
    for line, cells in rows:
        tech, verdict = _cell(cells, tech_at), _cell(cells, verdict_at)
        if not tech:
            raise ReportError(INVALID_REPORT, f"{shown} line {line}: a coverage row names no technology")
        if verdict not in COVERAGE_VERDICTS:
            raise ReportError(
                INVALID_REPORT,
                f"{shown} line {line}: coverage verdict {verdict!r} for `{tech}` is not one of: "
                f"{', '.join(COVERAGE_VERDICTS)}",
            )
        coverage.append({"technology": tech, "verdict": verdict})

    verdict_header = "| " + " | ".join(reader.VERDICT_TABLE_HEADER) + " |"
    found, rows, duplicate_line = reader.read_verdict_table(body, first_line)
    if not found:
        raise ReportError(INVALID_REPORT, f"{shown} has no `{verdict_header}` table under `## Integration Verdicts`")
    if duplicate_line is not None:
        raise ReportError(
            INVALID_REPORT, f"{shown} holds the `{verdict_header}` table twice (again at line {duplicate_line})"
        )
    integration = []
    for line, (lib_a, lib_b, verdict, _rationale) in rows:
        if not lib_a or not lib_b:
            raise ReportError(INVALID_REPORT, f"{shown} line {line}: a verdict row names fewer than two libraries")
        if verdict not in INTEGRATION_VERDICTS:
            raise ReportError(
                INVALID_REPORT,
                f"{shown} line {line}: verdict {verdict!r} for `{lib_a}` and `{lib_b}` is not one of: "
                f"{', '.join(INTEGRATION_VERDICTS)}",
            )
        integration.append({"libA": lib_a, "libB": lib_b, "verdict": verdict})

    tiers = None
    table = _columns(_section_tables(body, TIERS_SECTION, first_line), TIER_COLUMNS) if with_tiers else None
    if table is not None and table[1]:
        (skill_at, tier_at), rows = table
        tiers = {}
        for line, cells in rows:
            skill, tier = _cell(cells, skill_at), _cell(cells, tier_at)
            if not skill:
                raise ReportError(INVALID_REPORT, f"{shown} line {line}: an `## {TIERS_SECTION}` row names no skill")
            if tier not in TIERS:
                raise ReportError(
                    UNKNOWN_TIER,
                    f"{shown} line {line}: skill `{skill}` has evidence_tier {tier!r}, not one of: "
                    f"{', '.join(TIERS)}",
                )
            tiers[skill] = tier
    return {"coverage": coverage, "integration": integration}, tiers


def run(data, previous_report=None, current_report=None, no_tiers=False, reader=None):
    """The delta for one call: the JSON input, each side a report flag names read from that report.

    `reader` is the shared report reader (load_reader()), needed only with a
    report path.
    """
    if not isinstance(data, dict):
        return make_error("Input must be a JSON object")
    inp = dict(data)
    recorded = None
    for side, path in (("previous", previous_report), ("current", current_report)):
        if path is None:
            continue
        taken = ("previous", "previousTiers") if side == "previous" else ("current",)
        clash = [key for key in taken if key in inp]
        if clash:
            return make_error(f"`{clash[0]}` comes from --{side}-report: leave it out of the JSON")
        with_tiers = side == "previous" and not no_tiers
        try:
            inp[side], tiers = read_report(path, reader, with_tiers)
        except ReportError as exc:
            return {**make_error(str(exc), exc.code), "report": side, "path": path}
        if with_tiers:
            recorded = tiers is not None
            if tiers is not None:
                inp["previousTiers"] = tiers
    if no_tiers:
        inp.pop("previousTiers", None)
        inp.pop("currentTiers", None)
    result = compute(inp)
    if "code" not in result:
        result["previousTiersRecorded"] = recorded
    return result


# --- CLI --------------------------------------------------------------------


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-report-delta",
        # The module docstring is the contract synthesize.md points --help at:
        # the rankings, the one tier scale, how a report is read, and the input,
        # output and error schemas.
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  uv run skf-report-delta.py "
            "'{\"previous\":{\"coverage\":[{\"technology\":\"react\",\"verdict\":\"Missing\"}]},"
            "\"current\":{\"coverage\":[{\"technology\":\"react\",\"verdict\":\"Covered\"}]}}'\n"
            "  echo '{\"currentTiers\":{\"react\":\"T1\"}}' | uv run skf-report-delta.py "
            "--previous-report forge-data/feasibility-report-my-app-20260101-080000.md "
            "--current-report forge-data/feasibility-report-my-app-20260930-120000.md --stdin"
        ),
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("json_input", nargs="?", help="JSON object as a positional argument.")
    src.add_argument("--json-input", dest="json_input_flag", help="JSON object passed via flag.")
    src.add_argument("--stdin", action="store_true", help="Read the JSON object from stdin.")
    parser.add_argument(
        "--previous-report",
        metavar="PATH",
        help="read `previous` and `previousTiers` from this earlier feasibility report",
    )
    parser.add_argument(
        "--current-report",
        metavar="PATH",
        help="read `current` from this run's feasibility report",
    )
    parser.add_argument(
        "--no-tiers",
        action="store_true",
        help="compare no tier: ignore both tier maps and the previous report's tier table",
    )
    return parser


def _resolve_input(args):
    if args.stdin:
        return sys.stdin.read()
    if args.json_input_flag is not None:
        return args.json_input_flag
    if args.json_input is not None:
        return args.json_input
    return ""


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw = _resolve_input(args)
    if not raw.strip():
        if args.previous_report is None or args.current_report is None:
            parser.print_usage(file=sys.stderr)
            print(
                "error: no input provided (positional arg, --json-input, or --stdin; "
                "it may be left out only with both --previous-report and --current-report)",
                file=sys.stderr,
            )
            return 1
        raw = "{}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(make_error(f"Invalid JSON: {exc.msg}"), indent=2))
        return 1

    reader = None
    if args.previous_report is not None or args.current_report is not None:
        reader = load_reader()
        if reader is None:
            message = f"the shared report reader is missing: {SHARED_READER}"
            print(json.dumps(make_error(message, HELPER_MISSING), indent=2))
            return 1

    result = run(data, args.previous_report, args.current_report, args.no_tiers, reader)
    print(json.dumps(result, indent=2))
    return 2 if "code" in result else 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
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
