# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF Find Test Report: locate a skill's newest test report and read its verdict.

skf-export-skill (load-skill.md section 4b) and skf-update-skill (init.md,
the --from-test-report lookup, and in a normal run the check for a failing
report the skill has not been repaired from) both find the test report by
hand: glob, sort, frontmatter read, with a fallback to the stable result
file. The same three lookups run in the prompt for every skill of a batch.
This helper runs them once, the same way for both workflows.

Lookup order (the first one that finds a finished report wins):

  1. versioned-glob  {forge_data_folder}/{skill_name}/{version}/test-report-{skill_name}-*.md
                     (only when --version is given)
  2. flat-glob       {forge_data_folder}/{skill_name}/test-report-{skill_name}-*.md
  3. latest-json     skf-test-skill-result-latest.json in the versioned folder,
                     then the flat folder: the report named in its outputs[]

Within a glob, reports sort newest first by the run id in the file name
(`test-report-{skill_name}-{YYYYMMDDTHHMMSSZ}-...md`; the timestamp is the
first part, so the name order is the time order). A name whose part after
`test-report-{skill_name}-` does not start with a digit belongs to another
skill (`test-report-foo-bar-...` is not a report of `foo`) and is ignored.
A report whose frontmatter `testResult` is empty is unfinished (a run that
stopped before its verdict): it is listed in `skipped[]` and the next older
report is read instead.

Subcommand:

  find --forge-data-folder <dir> --skill-name <name> [--version <version>]
       [--newer-than <time>] [--provenance-map <provenance-map.json>]

Output (stdout):

  {
    "status": "found" | "not-found",
    "skill_name": "<name>",
    "version": "<version>" | null,
    "path": "<report path>" | null,
    "report_exists": true | false | null,
    "source": "versioned-glob" | "flat-glob" | "latest-json" | null,
    "testResult": "pass" | "fail" | "inconclusive" | "pass-with-drift" | null,
    "score": <number> | null,
    "run_id": "<run id>" | null,
    "test_date": "<testDate>" | null,
    "result_path": "<skf-test-skill-result-latest.json>" | null,
    "skipped": [{"path", "reason": "unfinished"}],
    "warnings": ["..."]
  }

`testResult` and `score` come from the report frontmatter. For latest-json,
when the report the result file names is gone, they come from the result
file's `summary` (`result`, `score`), `report_exists` is false (true for
every report the helper read, null when none was found) and a warning says
so. `testResult` is lower case with hyphens (`PASS_WITH_DRIFT` reads as
`pass-with-drift`).

With --newer-than (update-skill passes the skill's metadata.json
`generation_date`), the output also holds `"newer": true | false | null`:
true when the report's time is later than <time>, false when it is not,
null when no report was found or either time cannot be read. The report's
time is the later of the `YYYYMMDDTHHMMSSZ` its run id starts with and its
`test_date`, a time without a zone there read as UTC. <time> is an ISO-8601
date or date-time: with a zone it is that instant, and a date alone or a
time without a zone is the earliest instant it can name, 14 hours before
its UTC reading (the day starts first at UTC+14), so a report from the day
the skill was generated counts as newer rather than hiding.

With --provenance-map (update-skill passes the map it loaded), the output
also holds `"applied": true | false | null`: true when the map's update
block says a gap-driven update applied this report (top-level `update_type`
`gap-driven` and `test_report_run_id` equal to the report's `run_id`),
false when it does not, null when no report was found or the map cannot be
read as a JSON object.

Exit codes:
  0  a result was printed (found or not-found)
  1  --skill-name or --version is not a single folder name (message on
     stderr)
  2  usage error (argparse: a missing or unknown argument, usage on stderr)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LATEST_RESULT_NAME = "skf-test-skill-result-latest.json"
_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z(?:-[A-Za-z0-9]+)*$")
_RUN_ID_STAMP_RE = re.compile(r"^(\d{8}T\d{6}Z)")
# The easternmost zone (UTC+14): a day there starts 14 hours before UTC's.
_EARLIEST_ZONE_OFFSET = timedelta(hours=14)


# --------------------------------------------------------------------------
# Frontmatter
# --------------------------------------------------------------------------


def read_frontmatter(text: str) -> dict[str, str]:
    """Top-level scalar keys of a `---` frontmatter block, quotes removed.

    Nested blocks and comments are skipped and a flow list comes back as its
    text: the verdict keys are scalars.

    >>> read_frontmatter("---\\ntestResult: 'fail'\\nscore: 72\\nsteps: ['a']\\n---\\n# R")
    {'testResult': 'fail', 'score': '72', 'steps': "['a']"}
    >>> read_frontmatter("# no frontmatter")
    {}
    """
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if not m:
            continue
        value = m.group(2)
        if value.startswith("#"):
            value = ""
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[m.group(1)] = value
    return {}


def normalize_result(value: object) -> str | None:
    """`PASS_WITH_DRIFT` -> `pass-with-drift`; empty -> None.

    >>> normalize_result("PASS_WITH_DRIFT"), normalize_result(" Fail "), normalize_result("")
    ('pass-with-drift', 'fail', None)
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("_", "-")
    return text or None


def normalize_score(value: object) -> int | float | None:
    """A frontmatter or summary score as a number, or None.

    >>> normalize_score("85"), normalize_score("72.5"), normalize_score(""), normalize_score("N/A")
    (85, 72.5, None, None)
    >>> normalize_score("nan"), normalize_score(True)
    (None, None)
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().rstrip("%"))
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def parse_time(value: object, *, earliest: bool = False) -> datetime | None:
    """An ISO-8601 date or date-time, or a run id's leading stamp, as a UTC instant.

    A time with a zone is that instant. A date alone or a time without a
    zone reads as UTC, or with `earliest` as the earliest instant it can
    name, 14 hours before its UTC reading.

    >>> parse_time("2026-09-30T10:10:10Z").isoformat()
    '2026-09-30T10:10:10+00:00'
    >>> parse_time("20260930T101010Z-22-bbbb").isoformat()
    '2026-09-30T10:10:10+00:00'
    >>> parse_time("2026-09-30", earliest=True).isoformat()
    '2026-09-29T10:00:00+00:00'
    >>> parse_time("yesterday") is None, parse_time(None) is None
    (True, True)
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    stamp = _RUN_ID_STAMP_RE.match(text)
    try:
        if stamp:
            return datetime.strptime(stamp.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        moment = datetime.fromisoformat(text)
    except (ValueError, OverflowError):
        return None
    if moment.tzinfo is not None:
        return moment.astimezone(timezone.utc)
    moment = moment.replace(tzinfo=timezone.utc)
    return moment - _EARLIEST_ZONE_OFFSET if earliest else moment


def report_is_newer(result: dict, newer_than: str) -> bool | None:
    """Whether the found report's time is later than `newer_than` (None:
    no report, or a time that cannot be read). The report's time is the
    later of its run id's stamp and its test_date, so a date-only test_date
    (midnight) never hides a report the run id dates later that day."""
    if result["status"] != "found":
        return None
    times = [t for t in (parse_time(result["run_id"]), parse_time(result["test_date"])) if t is not None]
    bound = parse_time(newer_than, earliest=True)
    if not times or bound is None:
        return None
    return max(times) > bound


def report_was_applied(result: dict, provenance_map: Path) -> bool | None:
    """Whether the provenance map's update block names the found report as
    the one a gap-driven update applied (None: no report, or a map that
    cannot be read as a JSON object)."""
    if result["status"] != "found":
        return None
    try:
        data = json.loads(provenance_map.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    applied = data.get("test_report_run_id")
    return bool(
        data.get("update_type") == "gap-driven" and isinstance(applied, str) and applied
        and applied == result["run_id"]
    )


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------


def report_candidates(folder: Path, skill_name: str) -> list[tuple[str, Path]]:
    """(run id, path) for each report of `skill_name` in `folder`, newest first."""
    if not folder.is_dir():
        return []
    prefix = f"test-report-{skill_name}-"
    found: list[tuple[str, Path]] = []
    for path in folder.glob(f"{glob_escape(prefix)}*.md"):
        rest = path.name[len(prefix):-len(".md")]
        if path.is_file() and rest[:1].isdigit():
            found.append((rest, path))
    found.sort(key=lambda item: item[0], reverse=True)
    return found


def glob_escape(text: str) -> str:
    """Escape glob metacharacters in a literal name part."""
    return re.sub(r"([*?\[])", r"[\1]", text)


def read_report(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    return read_frontmatter(text)


def _run_id(frontmatter: dict, path: Path, skill_name: str) -> str | None:
    if frontmatter.get("runId"):
        return frontmatter["runId"]
    prefix = f"test-report-{skill_name}-"
    if path.name.startswith(prefix) and path.name.endswith(".md"):
        rest = path.name[len(prefix):-len(".md")]
        if _RUN_ID_RE.match(rest):
            return rest
    return None


def _found(result: dict, *, path: Path, source: str, frontmatter: dict, skill_name: str) -> dict:
    result.update(
        {
            "status": "found",
            "path": str(path),
            "report_exists": True,
            "source": source,
            "testResult": normalize_result(frontmatter.get("testResult")),
            "score": normalize_score(frontmatter.get("score")),
            "run_id": _run_id(frontmatter, path, skill_name),
            "test_date": frontmatter.get("testDate") or None,
        }
    )
    return result


def _glob_lookup(result: dict, folder: Path, skill_name: str, source: str) -> bool:
    for _, path in report_candidates(folder, skill_name):
        frontmatter = read_report(path)
        if not normalize_result(frontmatter.get("testResult")):
            result["skipped"].append({"path": str(path), "reason": "unfinished"})
            continue
        _found(result, path=path, source=source, frontmatter=frontmatter, skill_name=skill_name)
        return True
    return False


def _report_from_outputs(outputs: object) -> str | None:
    if not isinstance(outputs, list):
        return None
    paths = [o.get("path") for o in outputs if isinstance(o, dict) and isinstance(o.get("path"), str)]
    for entry in outputs:
        if isinstance(entry, dict) and entry.get("type") == "report" and isinstance(entry.get("path"), str):
            return entry["path"]
    for path in paths:
        if Path(path).name.startswith("test-report-") and path.endswith(".md"):
            return path
    return None


def resolve_output_path(recorded: str, result_file: Path) -> Path | None:
    """Where a path from outputs[] points: absolute as written; a relative one
    beside the result file (the report is written in the same folder), then as
    written from the working directory."""
    path = Path(recorded)
    if path.is_absolute():
        return path if path.is_file() else None
    for candidate in (result_file.parent / path, result_file.parent / path.name, Path.cwd() / path):
        if candidate.is_file():
            return candidate
    return None


def _latest_json_lookup(result: dict, folder: Path, skill_name: str) -> bool:
    result_file = folder / LATEST_RESULT_NAME
    if not result_file.is_file():
        return False
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result["warnings"].append(f"cannot read {result_file}: {exc}")
        return False
    if not isinstance(data, dict):
        result["warnings"].append(f"{result_file} is not a JSON object")
        return False
    recorded = _report_from_outputs(data.get("outputs"))
    if recorded is None:
        result["warnings"].append(f"{result_file} names no report in outputs[]")
        return False
    result["result_path"] = str(result_file)
    report = resolve_output_path(recorded, result_file)
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    if report is not None:
        frontmatter = read_report(report)
        _found(result, path=report, source="latest-json", frontmatter=frontmatter, skill_name=skill_name)
        if result["testResult"] is None:
            result["testResult"] = normalize_result(summary.get("result"))
        if result["score"] is None:
            result["score"] = normalize_score(summary.get("score"))
        return True
    result["warnings"].append(
        f"the report {recorded} named in {result_file} is missing; the verdict comes from its summary"
    )
    result.update(
        {
            "status": "found",
            "path": recorded,
            "report_exists": False,
            "source": "latest-json",
            "testResult": normalize_result(summary.get("result")),
            "score": normalize_score(summary.get("score")),
            "run_id": data.get("runId") if isinstance(data.get("runId"), str) else None,
            "test_date": data.get("timestamp") if isinstance(data.get("timestamp"), str) else None,
        }
    )
    return True


def find_test_report(forge_data_folder: Path, skill_name: str, version: str | None) -> dict:
    """Run the three lookups in order and return the result object."""
    result: dict = {
        "status": "not-found",
        "skill_name": skill_name,
        "version": version,
        "path": None,
        "report_exists": None,
        "source": None,
        "testResult": None,
        "score": None,
        "run_id": None,
        "test_date": None,
        "result_path": None,
        "skipped": [],
        "warnings": [],
    }
    flat = forge_data_folder / skill_name
    versioned = flat / version if version else None
    if versioned is not None and _glob_lookup(result, versioned, skill_name, "versioned-glob"):
        return result
    if _glob_lookup(result, flat, skill_name, "flat-glob"):
        return result
    for folder in (versioned, flat):
        if folder is not None and _latest_json_lookup(result, folder, skill_name):
            return result
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _valid_segment(value: str) -> bool:
    return bool(value) and value not in (".", "..") and "/" not in value and "\\" not in value


def _cmd_find(args: argparse.Namespace) -> int:
    for flag, value in (("--skill-name", args.skill_name), ("--version", args.version)):
        if value is not None and not _valid_segment(value):
            print(f"error: {flag} must be a single folder name, got {value!r}", file=sys.stderr)
            return 1
    result = find_test_report(Path(args.forge_data_folder), args.skill_name, args.version)
    if args.newer_than is not None:
        result["newer"] = report_is_newer(result, args.newer_than)
    if args.provenance_map is not None:
        result["applied"] = report_was_applied(result, Path(args.provenance_map))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-find-test-report",
        description="Locate a skill's newest finished test report and read its verdict.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("find", help="run the versioned, flat and latest-json lookups")
    p.add_argument("--forge-data-folder", required=True)
    p.add_argument("--skill-name", required=True)
    p.add_argument("--version", help="the version folder to search first (the active version)")
    p.add_argument(
        "--newer-than",
        metavar="TIME",
        help="also say whether the report is newer than this ISO-8601 time (the skill's generation_date)",
    )
    p.add_argument(
        "--provenance-map",
        metavar="FILE",
        help="also say whether this map's update block names the report as applied",
    )
    p.set_defaults(func=_cmd_find)

    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdout)
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
