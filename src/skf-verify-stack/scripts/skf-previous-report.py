#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Pick the previous feasibility report for skf-verify-stack (init.md §1).

The delta in synthesize.md §3 compares this run with an earlier report.
Which file that is has one correct answer, so it is decided here rather than in
prose:

  * A given path (--provided) is used when it is a readable file, unless it is
    one of the two files this run writes: this run's timestamped report
    (outputFile) or the -latest copy (outputFileLatest). init.md §4 writes the
    first before synthesize reads the previous report, so a run compared with
    it would be compared with itself and report every finding unchanged.
    report.md §1 copies the finished report over the second, so a report
    compared with it would, from then on, name its own copy as its previous
    report. Files are compared as files (os.path.samefile), not as path
    strings, so a symlink or another spelling of the same file matches.
  * With no given path, the newest finished report of this project in the
    folder is picked: feasibility-report-<slug>-<YYYYMMDD-HHmmss>.md, newest by
    that timestamp, whose frontmatter stepsCompleted lists `synthesize` and
    which passes the feasibility-report check report.md §1 runs before it
    publishes a report. A run that halted before synthesize left a partial
    report, and one that halted at that check left a report no consumer reads:
    neither is the baseline. This run's own file, the -latest copy and any file
    that is one of the two are never picked, and neither is the report of
    another project whose slug starts with this one (the timestamp must follow
    the slug directly) or a report this process cannot read.

The slug is the producer's `projectSlug`, as `skf-validate-feasibility-report.py
--locate` returns it: this script applies no slug rule of its own. It reads
stepsCompleted with the frontmatter reader of that shared script, and checks a
report with its read_report(), the check report.md §1 runs. The script sits in
the shared scripts folder beside this skill's folder, so the rules that read the
list and check the report are the ones the report's consumers use.

CLI usage:
  uv run skf-previous-report.py --folder <dir> --slug <slug> --timestamp <YYYYMMDD-HHmmss>
  uv run skf-previous-report.py --folder <dir> --slug <slug> --timestamp <ts> --provided <path>

Output (stdout, one object):
  {
    "status": "provided" | "discovered" | "none" | "not-found" | "collision"
              | "reader-missing",
    "previousReport": "<path>" | null,     # the report to compare against
    "previousTimestamp": "<YYYYMMDD-HHmmss>" | null,
    "provided": "<path as given>" | null,
    "collidesWith": "<outputFile or outputFileLatest>" | null,
    "outputFile": "<folder>/feasibility-report-<slug>-<timestamp>.md",
    "outputFileLatest": "<folder>/feasibility-report-<slug>-latest.md"
  }

  provided        the given path is a readable file and neither file this run
                  writes (it is used as given, finished or not: the delta names
                  a report it cannot compare)
  discovered      no path was given; previousReport is the newest finished
                  earlier report (it lists synthesize and passes the check)
  none            no path was given and the folder holds no finished earlier
                  report
  not-found       the given path is not a readable file (no previous report)
  collision       the given path is outputFile or outputFileLatest
  reader-missing  no path was given and the shared skf-validate-feasibility-report.py
                  is not in the shared scripts folder beside this skill's folder,
                  so no report can be read or checked; the output also carries
                  "error", naming the missing file

previousTimestamp is the timestamp in the previous report's file name, null
when there is no previous report or its name carries none.

Exit codes:
  0  status provided, discovered, none or not-found
  1  status collision: the caller halts (previous-report-collision)
  2  usage error: a missing flag, a --timestamp not shaped YYYYMMDD-HHmmss, or
     a --slug that is not a project slug (argparse prints the reason; no JSON)
  3  status reader-missing: the caller halts (resolution-failure)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

REPORT_NAME = "feasibility-report-{slug}-{suffix}.md"
LATEST_SUFFIX = "latest"

# A report is finished once synthesize.md §5 appended its step to this list.
STEPS_KEY = "stepsCompleted"
FINISHED_STEP = "synthesize"

# The shared feasibility-report reader. Installed (under _bmad/skf/ or an
# IDE's skills folder) and in a dev checkout (src/), shared/ sits beside
# this skill's folder.
SHARED_READER = (
    Path(__file__).resolve().parent.parent.parent
    / "shared"
    / "scripts"
    / "skf-validate-feasibility-report.py"
)

# A run timestamp: UTC, to the second (SKILL.md On Activation §2).
_TIMESTAMP_RE = re.compile(r"^\d{8}-\d{6}$")

# What skf-validate-feasibility-report.py's slugify() can return: lowercase
# ASCII letters and digits in runs joined by single hyphens.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _same_file(a: Path, b: Path) -> bool:
    """True when both paths exist and are one file."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False  # either path is missing or cannot be read


def _readable_file(path: Path) -> bool:
    """True when path is a file this process can read.

    Before Python 3.14, Path.is_file() raises for most OSErrors, such as a
    PermissionError under a folder the user cannot search or an unreachable
    network path; from 3.14 on it returns False. Either way the path is no
    readable file.
    """
    try:
        return path.is_file() and os.access(path, os.R_OK)
    except OSError:
        return False


def _timestamp_of(path: Path, slug: str) -> str | None:
    """The run timestamp in a report file name of this project, or None."""
    m = re.fullmatch(rf"feasibility-report-{re.escape(slug)}-(\d{{8}}-\d{{6}})\.md", path.name)
    return m.group(1) if m else None


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


def _finished(path: Path, reader) -> bool:
    """True when the report's frontmatter stepsCompleted lists synthesize and
    the report passes the shared reader's check (read_report), as report.md §1
    requires before it publishes a report.

    A report this process cannot read, whose frontmatter holds no such list,
    or that fails the check is not finished.
    """
    try:
        # utf-8-sig drops a byte order mark, as the shared reader does.
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    steps = reader.frontmatter_list(content, STEPS_KEY)
    if steps is None or FINISHED_STEP not in steps:
        return False
    _fields, ok = reader.read_report(content)
    return ok


def _earlier_reports(folder: Path, slug: str, timestamp: str, reader) -> list[tuple[str, Path]]:
    """(timestamp, path) of this project's finished timestamped reports, this run's excluded.

    A report counts only when it is finished (_finished): a run that halted
    earlier left a partial or unchecked report behind.
    """
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []  # a missing or unreadable folder holds no earlier report
    found = []
    for entry in entries:
        stamp = _timestamp_of(entry, slug)
        if stamp is not None and stamp != timestamp and _readable_file(entry) and _finished(entry, reader):
            found.append((stamp, entry))
    return found


def resolve(folder: str, slug: str, timestamp: str, provided: str | None = None) -> tuple[dict, int]:
    """Pick the previous report. Returns (result_dict, exit_code)."""
    base = Path(folder)
    output_file = base / REPORT_NAME.format(slug=slug, suffix=timestamp)
    output_latest = base / REPORT_NAME.format(slug=slug, suffix=LATEST_SUFFIX)
    written = (output_latest, output_file)
    result = {
        "status": "none",
        "previousReport": None,
        "previousTimestamp": None,
        "provided": provided,
        "collidesWith": None,
        "outputFile": str(output_file),
        "outputFileLatest": str(output_latest),
    }

    if provided is not None:
        path = Path(provided)
        if not _readable_file(path):
            result["status"] = "not-found"
            return result, 0
        for target in written:
            if _same_file(path, target):
                result.update(status="collision", collidesWith=str(target))
                return result, 1
        result.update(
            status="provided",
            previousReport=provided,
            previousTimestamp=_timestamp_of(path, slug),
        )
        return result, 0

    reader = load_reader()
    if reader is None:
        result.update(status="reader-missing", error=f"the shared report reader is missing: {SHARED_READER}")
        return result, 3
    # A report name that is a link to a file this run writes is no earlier run.
    candidates = [
        (stamp, path)
        for stamp, path in _earlier_reports(base, slug, timestamp, reader)
        if not any(_same_file(path, target) for target in written)
    ]
    if candidates:
        stamp, path = max(candidates)
        result.update(status="discovered", previousReport=str(path), previousTimestamp=stamp)
    return result, 0


def _timestamp(value: str) -> str:
    if not _TIMESTAMP_RE.match(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a run timestamp (YYYYMMDD-HHmmss)")
    return value


def _slug(value: str) -> str:
    if not _SLUG_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a project slug (lowercase letters and digits joined by "
            "single hyphens): pass the projectSlug skf-validate-feasibility-report.py "
            "--locate returns"
        )
    return value


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="skf-previous-report",
        description=(
            "Pick the feasibility report this verify-stack run compares against "
            "(init.md §1). With --provided: use that file unless it is one of "
            "the two files this run writes (the timestamped report or the -latest "
            "copy), which is a collision (exit 1). Without it: pick the newest "
            "finished timestamped report of this project in --folder (its "
            "stepsCompleted lists synthesize and it passes the feasibility-report "
            "check); exit 3 when the shared report reader that reads and checks "
            "it is missing. Prints JSON; exit 0 otherwise, 2 on a usage error."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example:\n"
            "  uv run skf-previous-report.py --folder forge-data --slug my-app "
            "--timestamp 20260930-120000 --provided forge-data/feasibility-report-my-app-latest.md"
        ),
    )
    parser.add_argument(
        "--folder",
        required=True,
        help="the folder the reports are written to ({outputFolderPath})",
    )
    parser.add_argument(
        "--slug",
        required=True,
        type=_slug,
        help="the run's project slug ({project_slug})",
    )
    parser.add_argument(
        "--timestamp",
        required=True,
        type=_timestamp,
        help="the run's timestamp, YYYYMMDD-HHmmss ({timestamp})",
    )
    parser.add_argument(
        "--provided",
        metavar="PATH",
        help="the previous report the user gave; omit to pick the newest earlier one",
    )
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    provided = args.provided if args.provided and args.provided.strip() else None
    result, code = resolve(args.folder, args.slug, args.timestamp, provided)
    print(json.dumps(result, indent=2))
    return code


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a --help text or a path may hold.
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
