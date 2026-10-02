# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Status: a deterministic summary of the campaign state.

`campaign status` and step-resume's summary block tallied `skills[]` by status
("N completed / M total, K pending, ...") in the prompt, over a 15+ skill
array. That count is mechanical, with one correct answer, so this script owns
it and identical state always yields identical output.

CLI:
  uv run campaign-status.py --state-file <path>

Output (JSON on stdout):
  {
    "campaign_name": "...",
    "current_stage": 0,
    "last_updated": "...",
    "total": 0, "completed": 0, "pending": 0,
    "active": 0, "failed": 0, "skipped": 0
  }

Exit codes:
  0  ok
  2  error (state missing / unreadable / not a mapping)
"""

from __future__ import annotations

import argparse
import json
import sys
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


def _counts(state: Dict[str, Any]) -> Dict[str, int]:
    skills = state.get("skills", []) or []
    tally = {s: 0 for s in STATUSES}
    for skill in skills:
        status = skill.get("status")
        if status in tally:
            tally[status] += 1
    tally["total"] = len(skills)
    return tally


def run(state_file: str) -> int:
    state = _load_state(Path(state_file))
    if state is None:
        return _err(f"State not readable as a mapping: {state_file}", "STATE_UNREADABLE")

    campaign = state.get("campaign", {}) or {}
    result: Dict[str, Any] = {
        "campaign_name": campaign.get("name", ""),
        "current_stage": campaign.get("current_stage"),
        "last_updated": campaign.get("last_updated"),
        **_counts(state),
    }

    json.dump(result, sys.stdout, separators=(",", ":"), default=str)
    sys.stdout.write("\n")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-status",
        description="Summarize the campaign state.",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    args = parser.parse_args(argv)
    return run(args.state_file)


if __name__ == "__main__":
    raise SystemExit(main())
