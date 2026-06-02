# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Validate Pins — validate all version pins in a campaign state file.

Campaign-specific wrapper around the shared skf-validate-pins.py module.
Reads the campaign state and brief, validates every skill's pin against
real GitHub releases/tags, and outputs consolidated JSON.

CLI:
  uv run src/skf-campaign/scripts/campaign-validate-pins.py \
      --state-file <path> --brief-file <path>

Input:
  --state-file   Path to _campaign-state.yaml
  --brief-file   Path to campaign-brief.yaml

Output (JSON on stdout):
  {
    "results": [
      {
        "name": "skill-name",
        "status": "valid|invalid|resolved",
        "pin": "input-pin-or-null",
        "resolved_ref": "actual-tag-or-branch",
        "ref_type": "tag|branch|null",
        "version": "semver-or-null",
        "suggestions": []
      }
    ],
    "all_valid": true,
    "invalid_count": 0,
    "resolved_count": 0
  }

Exit codes:
  0  all valid/resolved
  1  one or more invalid pins
  2  error (missing files, bad YAML, gh unavailable)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

SHARED_SCRIPTS = Path(__file__).parent.parent.parent / "shared" / "scripts"
VALIDATE_PINS_PATH = SHARED_SCRIPTS / "skf-validate-pins.py"


def _load_validate_pin():
    spec = importlib.util.spec_from_file_location("skf_validate_pins", VALIDATE_PINS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate_pin


def _emit_error(message: str, code: str) -> None:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(state_file: str, brief_file: str) -> int:
    state_path = Path(state_file)
    brief_path = Path(brief_file)

    if not state_path.is_file():
        _emit_error(f"State file not found: {state_file}", "STATE_NOT_FOUND")
        return 2

    if not brief_path.is_file():
        _emit_error(f"Brief file not found: {brief_file}", "BRIEF_NOT_FOUND")
        return 2

    try:
        state = _load_yaml(state_path)
    except Exception as exc:
        _emit_error(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR")
        return 2

    try:
        brief = _load_yaml(brief_path)
    except Exception as exc:
        _emit_error(f"Failed to parse brief file: {exc}", "BRIEF_PARSE_ERROR")
        return 2

    skills = state.get("skills", [])
    if not isinstance(skills, list):
        _emit_error("State file 'skills' is not an array", "INVALID_STATE")
        return 2

    targets = brief.get("targets", [])
    if not isinstance(targets, list):
        _emit_error("Brief file 'targets' is not an array", "INVALID_BRIEF")
        return 2

    name_to_repo: Dict[str, str] = {}
    for target in targets:
        name_to_repo[target["name"]] = target["repo_url"]

    if not VALIDATE_PINS_PATH.is_file():
        _emit_error(
            f"Shared module not found: {VALIDATE_PINS_PATH.as_posix()}",
            "SHARED_MODULE_NOT_FOUND",
        )
        return 2

    validate_pin = _load_validate_pin()

    results: List[Dict[str, Any]] = []
    invalid_count = 0
    resolved_count = 0

    for skill in skills:
        skill_name = skill["name"]
        repo_url = name_to_repo.get(skill_name)
        if repo_url is None:
            _emit_error(
                f"Skill '{skill_name}' not found in brief targets",
                "SKILL_NOT_IN_BRIEF",
            )
            return 2

        pin = skill.get("pin")
        result = validate_pin(repo_url, pin=pin)
        result["name"] = skill_name

        if result["status"] == "invalid":
            invalid_count += 1
        elif result["status"] == "resolved":
            resolved_count += 1

        results.append(result)

    all_valid = invalid_count == 0
    output = {
        "results": results,
        "all_valid": all_valid,
        "invalid_count": invalid_count,
        "resolved_count": resolved_count,
    }

    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")

    if not all_valid:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate all version pins in a campaign state file.",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    parser.add_argument("--brief-file", required=True, help="Path to campaign-brief.yaml")
    args = parser.parse_args()
    return run(args.state_file, args.brief_file)


if __name__ == "__main__":
    raise SystemExit(main())
