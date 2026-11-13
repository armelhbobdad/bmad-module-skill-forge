# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Campaign Status: a deterministic summary of the campaign state.

`campaign status` and step-resume's summary block tallied `skills[]` by status
("N completed / M total, K pending, ...") in the prompt, over a 15+ skill
array. That count is mechanical, with one correct answer, so this script owns
it and identical state always yields identical output.

--export-names gives step-09 the refinement scope: the skill folder of every
completed skill, the name Refine Architecture's inventory knows. It is
campaign-quality-gate.py's `export_name` (the last part of the skill_path
the build recorded, else the campaign name), so a Tier B skill whose folder
quick-skill named after the library is scoped under that folder.

CLI:
  uv run campaign-status.py --state-file <path>
  uv run campaign-status.py --state-file <path> --export-names

Output:
  without --export-names, one JSON object on stdout:
  {
    "campaign_name": "...",
    "current_stage": 0,
    "last_updated": "...",
    "total": 0, "completed": 0, "pending": 0,
    "active": 0, "failed": 0, "skipped": 0
  }
  --export-names: one plain-text line on stdout, the export_name of every
  completed skill of either tier, in skills[] order, each once, joined by
  "," with no space (an empty line when no skill is completed)

Exit codes:
  0  ok
  2  error (state missing / unreadable / not a mapping)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

STATUSES = ("pending", "active", "completed", "failed", "skipped")
GATE_SCRIPT = Path(__file__).resolve().with_name("campaign-quality-gate.py")


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


def export_names(state: Dict[str, Any]) -> List[str]:
    """The export_name of every completed skill, in skills[] order, each once."""
    spec = importlib.util.spec_from_file_location("campaign_quality_gate", GATE_SCRIPT)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    names: List[str] = []
    skills = state.get("skills")
    for skill in skills if isinstance(skills, list) else []:
        if not isinstance(skill, dict) or skill.get("status") != "completed":
            continue
        name = gate.export_name(skill)
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return names


def run(state_file: str, names_only: bool = False) -> int:
    state = _load_state(Path(state_file))
    if state is None:
        return _err(f"State not readable as a mapping: {state_file}", "STATE_UNREADABLE")

    if names_only:
        sys.stdout.write(",".join(export_names(state)) + "\n")
        return 0

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
    parser.add_argument(
        "--export-names",
        action="store_true",
        help="print the comma-joined skill folder (export_name) of every completed skill instead",
    )
    args = parser.parse_args(argv)
    return run(args.state_file, args.export_names)


if __name__ == "__main__":
    raise SystemExit(main())
