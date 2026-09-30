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
    (outputFile) or the -latest copy (outputFileLatest). init.md §4
    overwrites both before synthesize reads the previous report, so a run
    compared with either would be compared with itself and report every
    finding unchanged. Files are compared as files (os.path.samefile), not as
    path strings, so a symlink or another spelling of the same file matches.
  * With no given path, the newest timestamped report of this project in the
    folder is picked: feasibility-report-<slug>-<YYYYMMDD-HHmmss>.md, newest by
    that timestamp. This run's own file, the -latest copy and any file that is
    one of the two are never picked, and neither is the report of another
    project whose slug starts with this one (the timestamp must follow the
    slug directly) or a report this process cannot read.

The slug is the producer's `projectSlug`, as `skf-validate-feasibility-report.py
--locate` returns it: this script applies no slug rule of its own.

CLI usage:
  uv run skf-previous-report.py --folder <dir> --slug <slug> --timestamp <YYYYMMDD-HHmmss>
  uv run skf-previous-report.py --folder <dir> --slug <slug> --timestamp <ts> --provided <path>

Output (stdout, one object):
  {
    "status": "provided" | "discovered" | "none" | "not-found" | "collision",
    "previousReport": "<path>" | null,     # the report to compare against
    "previousTimestamp": "<YYYYMMDD-HHmmss>" | null,
    "provided": "<path as given>" | null,
    "collidesWith": "<outputFile or outputFileLatest>" | null,
    "outputFile": "<folder>/feasibility-report-<slug>-<timestamp>.md",
    "outputFileLatest": "<folder>/feasibility-report-<slug>-latest.md"
  }

  provided    the given path is a readable file and neither file this run writes
  discovered  no path was given; previousReport is the newest earlier report
  none        no path was given and the folder holds no earlier report
  not-found   the given path is not a readable file (no previous report)
  collision   the given path is outputFile or outputFileLatest

previousTimestamp is the timestamp in the previous report's file name, null
when there is no previous report or its name carries none.

Exit codes:
  0  status provided, discovered, none or not-found
  1  status collision: the caller halts (previous-report-collision)
  2  usage error: a missing flag, a --timestamp not shaped YYYYMMDD-HHmmss, or
     a --slug that is not a project slug (argparse prints the reason; no JSON)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPORT_NAME = "feasibility-report-{slug}-{suffix}.md"
LATEST_SUFFIX = "latest"

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


def _earlier_reports(folder: Path, slug: str, timestamp: str) -> list[tuple[str, Path]]:
    """(timestamp, path) of this project's timestamped reports, this run's excluded."""
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []  # a missing or unreadable folder holds no earlier report
    found = []
    for entry in entries:
        stamp = _timestamp_of(entry, slug)
        if stamp is not None and stamp != timestamp and _readable_file(entry):
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

    # A report name that is a link to a file this run writes is no earlier run.
    candidates = [
        (stamp, path)
        for stamp, path in _earlier_reports(base, slug, timestamp)
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
            "timestamped report of this project in --folder. Prints JSON; exit 0 "
            "otherwise, 2 on a usage error."
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


if __name__ == "__main__":
    sys.exit(main())
