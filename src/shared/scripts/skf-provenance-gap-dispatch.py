# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""SKF Provenance Gap Dispatch — Major-Version Scope Reconciliation feeder.

`skf-update-skill/references/detect-changes.md §1c` performs three
deterministic operations before the LLM can prompt the user:

  1. **Locate** the latest audit drift report under
     `{forge_data_folder}/{skill_name}/{baseline_version}/drift-report-*.md`
  2. **Parse** the report for an "Out-of-Scope Observations" section
     (either `## Out-of-Scope Observations` at the top level or
     `### Out-of-Scope New Public API` under `## Remediation Suggestions`).
     Extract each candidate's `path` and `evidence`.
  3. **Reconcile** candidates against `brief.scope.amendments[]`:
     - `promoted` for this path → already in scope (skip)
     - `skipped` for this path → user previously declined (skip)
     - `demoted-include` or `demoted-exclude` → pre-decided demotion
     - no matching amendment → unresolved (caller prompts user)

The prose previously asked the LLM to do all three per run. The
markdown parsing in particular is fiddly (heading lookahead, table
vs bullet vs definition list formats); keeping it in prose lets
report-format drift produce silent skips. This helper makes
discovery and classification one bash call.

Subcommand:
  dispatch --skill-name <name> --baseline-version <ver> \\
           --forge-data-folder <path> --brief <brief.yaml-path>

Output JSON (stdout):

  {
    "status": "no-report" | "no-candidates" | "candidates-found",
    "report_path": "<abs path>" | null,
    "candidates_total": N,
    "classified": [
      {
        "path": "<glob or file path>",
        "evidence": "<one-liner from report>",
        "status": "already-in-scope"
                | "pre-decided-skipped"
                | "pre-decided-demoted"
                | "unresolved",
        "prior_action": "promoted" | "skipped"
                      | "demoted-include" | "demoted-exclude"
                      | null
      }, ...
    ],
    "summary": {
      "pre_decided_count": N,
      "unresolved_count":  N
    }
  }

`status` field shortcuts the caller:
  - `no-report`     → no drift report exists; §1c skipped entirely
  - `no-candidates` → report exists but Out-of-Scope section is absent/empty
  - `candidates-found` → classified[] is populated; iterate unresolved entries

Exit codes:
  0  — operation succeeded (any status)
  1  — user error (paths invalid, brief unparseable)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


# --------------------------------------------------------------------------
# Discovery: locate the latest drift report
# --------------------------------------------------------------------------


def discover_drift_report(
    forge_data_folder: Path, skill_name: str, baseline_version: str
) -> Path | None:
    """Return the most recent drift-report-*.md under
    {forge_data_folder}/{skill_name}/{baseline_version}/, or None.

    Reports are sorted by filename DESC — the convention is timestamped
    filenames so lexicographic order == chronological order.
    """
    search_dir = forge_data_folder / skill_name / baseline_version
    if not search_dir.is_dir():
        return None
    candidates = sorted(
        search_dir.glob("drift-report-*.md"),
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


# --------------------------------------------------------------------------
# Parse: extract Out-of-Scope candidates from a drift report
# --------------------------------------------------------------------------


_TOP_LEVEL_HEADING = re.compile(r"^##\s+Out-of-Scope Observations\s*$")
_NESTED_HEADING = re.compile(r"^###\s+Out-of-Scope New Public API\s*$")
_REMEDIATION_HEADING = re.compile(r"^##\s+Remediation Suggestions\s*$")
_ANY_TOP_LEVEL_HEADING = re.compile(r"^##\s+\S")
_ANY_SUB_LEVEL_HEADING = re.compile(r"^###\s+\S")


def extract_out_of_scope_section(text: str) -> str | None:
    """Pull the Out-of-Scope block from a drift report. Returns the block
    text (without the heading), or None if no matching section exists.

    Supports two report shapes:
      - top-level `## Out-of-Scope Observations` heading
      - `### Out-of-Scope New Public API` under `## Remediation Suggestions`
    """
    lines = text.splitlines()
    n = len(lines)

    # Pass 1: top-level heading
    for i, line in enumerate(lines):
        if _TOP_LEVEL_HEADING.match(line):
            return _gather_until_next_heading(lines, i + 1, _ANY_TOP_LEVEL_HEADING)

    # Pass 2: nested heading under Remediation Suggestions
    in_remediation = False
    for i, line in enumerate(lines):
        if _REMEDIATION_HEADING.match(line):
            in_remediation = True
            continue
        if in_remediation and _ANY_TOP_LEVEL_HEADING.match(line):
            in_remediation = False
            continue
        if in_remediation and _NESTED_HEADING.match(line):
            return _gather_until_next_heading(lines, i + 1, _ANY_SUB_LEVEL_HEADING)

    return None


def _gather_until_next_heading(
    lines: list[str], start: int, stop_pattern: re.Pattern[str]
) -> str:
    """Collect lines from `start` until the next heading matching stop_pattern."""
    out: list[str] = []
    for i in range(start, len(lines)):
        if stop_pattern.match(lines[i]):
            break
        out.append(lines[i])
    return "\n".join(out).strip()


# --------------------------------------------------------------------------
# Parse candidates from the section text
# --------------------------------------------------------------------------


# Bullet-list shape: "- `path/to/thing` — evidence text"
# (em-dash, en-dash, or plain hyphen as separator)
_BULLET = re.compile(
    r"^\s*[-*]\s+`(?P<path>[^`]+)`\s*[—–-]\s*(?P<evidence>.+?)\s*$"
)

# Table shape: "| path | evidence |"
_TABLE_ROW = re.compile(
    r"^\|\s*`?(?P<path>[^|`]+?)`?\s*\|\s*(?P<evidence>[^|]+?)\s*\|"
)
_TABLE_SEPARATOR = re.compile(r"^\|\s*[-:]+\s*\|")


def parse_candidates(section_text: str) -> list[dict]:
    r"""Extract (path, evidence) candidates from an Out-of-Scope section.

    Recognized formats:
      - Bullet lines: ``- `path/to` — evidence``
      - Markdown table: ``| path | evidence |`` (skip header/separator rows)
    """
    if not section_text:
        return []
    candidates: list[dict] = []
    in_table = False
    table_header_seen = False
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped:
            in_table = False
            table_header_seen = False
            continue

        if _TABLE_SEPARATOR.match(stripped):
            in_table = True
            table_header_seen = True
            continue

        if stripped.startswith("|"):
            if not table_header_seen:
                # First table-shaped line is the header — skip
                table_header_seen = True
                continue
            m = _TABLE_ROW.match(stripped)
            if m:
                path = m.group("path").strip()
                evidence = m.group("evidence").strip()
                if path and not _looks_like_table_header(path):
                    candidates.append({"path": path, "evidence": evidence})
            continue

        m = _BULLET.match(line)
        if m:
            candidates.append(
                {
                    "path": m.group("path").strip(),
                    "evidence": m.group("evidence").strip(),
                }
            )
    return candidates


def _looks_like_table_header(text: str) -> bool:
    """True if `text` looks like a table-header cell label (e.g. 'path',
    'evidence'). Headers slip past `_TABLE_SEPARATOR` only when the report
    uses a header row without the canonical `|---|---|` separator."""
    return text.lower() in {"path", "evidence", "file", "files", "candidate", "rationale"}


# --------------------------------------------------------------------------
# Reconcile candidates against brief.scope.amendments[]
# --------------------------------------------------------------------------


_ALREADY_IN_SCOPE = "already-in-scope"
_PRE_DECIDED_SKIPPED = "pre-decided-skipped"
_PRE_DECIDED_DEMOTED = "pre-decided-demoted"
_UNRESOLVED = "unresolved"


def load_brief(brief_path: Path) -> dict:
    """Parse a skill-brief.yaml file. Raises ValueError on load failure."""
    try:
        text = brief_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read brief at {brief_path}: {exc}") from exc
    try:
        brief = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"brief at {brief_path} is not valid YAML: {exc}") from exc
    if not isinstance(brief, dict):
        raise ValueError(
            f"brief at {brief_path} must be a YAML mapping, got "
            f"{type(brief).__name__}"
        )
    return brief


def reconcile(candidates: list[dict], brief: dict) -> list[dict]:
    """Classify each candidate against brief.scope.amendments[]."""
    scope = brief.get("scope")
    amendments = []
    if isinstance(scope, dict):
        amendments = scope.get("amendments") or []
    if not isinstance(amendments, list):
        amendments = []

    # index amendments by path → list of actions (most recent first preserved)
    by_path: dict[str, list[str]] = {}
    for amend in amendments:
        if not isinstance(amend, dict):
            continue
        path = amend.get("path")
        action = amend.get("action")
        if isinstance(path, str) and isinstance(action, str):
            by_path.setdefault(path, []).append(action)

    classified: list[dict] = []
    for candidate in candidates:
        path = candidate["path"]
        evidence = candidate.get("evidence", "")
        prior_actions = by_path.get(path, [])
        status, prior_action = _classify(prior_actions)
        classified.append(
            {
                "path": path,
                "evidence": evidence,
                "status": status,
                "prior_action": prior_action,
            }
        )
    return classified


def _classify(prior_actions: list[str]) -> tuple[str, str | None]:
    """Pick the dominant amendment action for a single candidate path.

    A path may have multiple amendments (e.g. promoted then later
    demoted-exclude). Most recent action wins — the list is in
    amendment-record-insertion order, so iterate from the end.
    """
    for action in reversed(prior_actions):
        if action == "promoted":
            return _ALREADY_IN_SCOPE, "promoted"
        if action == "skipped":
            return _PRE_DECIDED_SKIPPED, "skipped"
        if action in ("demoted-include", "demoted-exclude"):
            return _PRE_DECIDED_DEMOTED, action
    return _UNRESOLVED, None


# --------------------------------------------------------------------------
# Dispatch: orchestrate all three steps
# --------------------------------------------------------------------------


def dispatch(
    *,
    forge_data_folder: Path,
    skill_name: str,
    baseline_version: str,
    brief_path: Path,
) -> dict:
    """Run the full §1c discovery + parse + reconcile pipeline."""
    report = discover_drift_report(forge_data_folder, skill_name, baseline_version)
    if report is None:
        return {
            "status": "no-report",
            "report_path": None,
            "candidates_total": 0,
            "classified": [],
            "summary": {"pre_decided_count": 0, "unresolved_count": 0},
        }

    text = report.read_text(encoding="utf-8")
    section = extract_out_of_scope_section(text)
    if section is None:
        return {
            "status": "no-candidates",
            "report_path": str(report),
            "candidates_total": 0,
            "classified": [],
            "summary": {"pre_decided_count": 0, "unresolved_count": 0},
        }

    candidates = parse_candidates(section)
    if not candidates:
        return {
            "status": "no-candidates",
            "report_path": str(report),
            "candidates_total": 0,
            "classified": [],
            "summary": {"pre_decided_count": 0, "unresolved_count": 0},
        }

    brief = load_brief(brief_path)
    classified = reconcile(candidates, brief)

    pre_decided = sum(1 for c in classified if c["status"] != _UNRESOLVED)
    unresolved = sum(1 for c in classified if c["status"] == _UNRESOLVED)

    return {
        "status": "candidates-found",
        "report_path": str(report),
        "candidates_total": len(classified),
        "classified": classified,
        "summary": {
            "pre_decided_count": pre_decided,
            "unresolved_count": unresolved,
        },
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _cmd_dispatch(args: argparse.Namespace) -> int:
    forge = Path(args.forge_data_folder)
    if not forge.is_dir():
        print(
            f"error: forge-data-folder not a directory: {forge}", file=sys.stderr
        )
        return 1
    brief_path = Path(args.brief)
    if not brief_path.is_file():
        print(f"error: brief not found: {brief_path}", file=sys.stderr)
        return 1
    try:
        result = dispatch(
            forge_data_folder=forge,
            skill_name=args.skill_name,
            baseline_version=args.baseline_version,
            brief_path=brief_path,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skf-provenance-gap-dispatch",
        description=(
            "Locate the latest drift report, extract Out-of-Scope candidates, "
            "and classify them against brief.scope.amendments[]."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dispatch", help="run the full §1c pipeline")
    p.add_argument("--skill-name", required=True)
    p.add_argument("--baseline-version", required=True)
    p.add_argument("--forge-data-folder", required=True)
    p.add_argument("--brief", required=True, help="path to skill-brief.yaml")
    p.set_defaults(func=_cmd_dispatch)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
