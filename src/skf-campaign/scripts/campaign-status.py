# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Status — deterministic state summary + optional backup-drift verdict.

Collapses two in-prompt determinism leaks into one helper the LLM calls instead
of hand-deriving:

  - `campaign status` and the resume summary block tallied `skills[]` by status
    ("N completed / M total, K pending, ...") in-prompt over a 15+ skill array.
  - the `.bak` recovery path compared `primary` vs `backup` timestamps and stage
    numbers by hand (an ISO-8601 + int compare across two YAML files).

Both are mechanical, one-correct-answer computations. This script owns them so
identical state always yields identical output.

CLI:
  uv run campaign-status.py --state-file <path>
  uv run campaign-status.py --state-file <path> --backup-file <path>

Output (JSON on stdout):
  {
    "campaign_name": "...",
    "current_stage": 0,
    "last_updated": "...",
    "total": 0, "completed": 0, "pending": 0,
    "active": 0, "failed": 0, "skipped": 0,
    "backup_comparison": null | {
      "primary_behind": bool,
      "primary_last_updated": "...", "backup_last_updated": "...",
      "primary_stage": 0, "backup_stage": 0
    }
  }

Exit codes:
  0  ok
  2  error (state missing / unreadable / not a mapping)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

STATUSES = ("pending", "active", "completed", "failed", "skipped")


def _err(message: str, code: str) -> int:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")
    return 2


def _load_state(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


def _counts(state: Dict[str, Any]) -> Dict[str, int]:
    skills = state.get("skills", []) or []
    tally = {s: 0 for s in STATUSES}
    for skill in skills:
        status = skill.get("status")
        if status in tally:
            tally[status] += 1
    tally["total"] = len(skills)
    return tally


def _compare_backup(primary: Dict[str, Any], backup: Dict[str, Any]) -> Dict[str, Any]:
    p_c = primary.get("campaign", {}) or {}
    b_c = backup.get("campaign", {}) or {}
    p_updated = p_c.get("last_updated")
    b_updated = b_c.get("last_updated")
    p_stage = p_c.get("current_stage")
    b_stage = b_c.get("current_stage")

    stage_behind = (
        isinstance(p_stage, int) and isinstance(b_stage, int) and p_stage < b_stage
    )

    ts_behind = False
    p_ts = _parse_iso(p_updated)
    b_ts = _parse_iso(b_updated)
    if p_ts is not None and b_ts is not None:
        try:
            ts_behind = p_ts < b_ts
        except TypeError:
            # naive vs aware datetime — cannot order; defer to stage compare.
            ts_behind = False

    return {
        "primary_behind": bool(stage_behind or ts_behind),
        "primary_last_updated": p_updated,
        "backup_last_updated": b_updated,
        "primary_stage": p_stage,
        "backup_stage": b_stage,
    }


def run(state_file: str, backup_file: Optional[str]) -> int:
    state = _load_state(Path(state_file))
    if state is None:
        return _err(f"State not readable as a mapping: {state_file}", "STATE_UNREADABLE")

    campaign = state.get("campaign", {}) or {}
    result: Dict[str, Any] = {
        "campaign_name": campaign.get("name", ""),
        "current_stage": campaign.get("current_stage"),
        "last_updated": campaign.get("last_updated"),
        **_counts(state),
        "backup_comparison": None,
    }

    if backup_file:
        backup = _load_state(Path(backup_file))
        if backup is not None:
            result["backup_comparison"] = _compare_backup(state, backup)

    json.dump(result, sys.stdout, separators=(",", ":"), default=str)
    sys.stdout.write("\n")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-status",
        description="Summarize campaign state and (optionally) compare it to its backup.",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    parser.add_argument(
        "--backup-file",
        help="Path to _campaign-state.yaml.bak; when given, emit backup_comparison",
    )
    args = parser.parse_args(argv)
    return run(args.state_file, args.backup_file)


if __name__ == "__main__":
    raise SystemExit(main())
