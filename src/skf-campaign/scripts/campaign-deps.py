# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Deps — dependency computation and enforcement for campaign skills.

Two modes:
  --compute: topological sort of all skills from depends_on edges
  --check:   verify a single skill's dependencies are satisfied

CLI:
  uv run campaign-deps.py --compute --state-file <path>
  uv run campaign-deps.py --check --state-file <path> --skill <name>
  uv run campaign-deps.py --check --state-file <path> --skill <name> --force

Output (JSON on stdout):
  --compute:
    {"execution_order": [...], "circular_deps_detected": bool, "cycle_participants": [...] | null}

  --check:
    {"skill": "name", "ready": bool, "unmet_deps": [...], "forced": bool}

Exit codes:
  0  success / ready / force-override
  1  circular deps / unmet deps / dangling reference
  2  error (missing file, bad YAML)
"""

from __future__ import annotations

import argparse
import json
import sys
import heapq
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def _emit_error(message: str, code: str) -> None:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_skill_map(skills: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s["name"]: s for s in skills}


def _validate_deps(
    skill_map: Dict[str, Dict[str, Any]],
) -> Optional[List[str]]:
    dangling: List[str] = []
    for name, skill in skill_map.items():
        for dep in skill.get("depends_on", []) or []:
            if dep not in skill_map:
                dangling.append(f"{name} depends on unknown skill '{dep}'")
    return dangling if dangling else None


def compute(state_file: str) -> int:
    path = Path(state_file)
    if not path.is_file():
        _emit_error(f"State file not found: {state_file}", "STATE_NOT_FOUND")
        return 2

    try:
        state = _load_yaml(path)
    except Exception as exc:
        _emit_error(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR")
        return 2

    skills = state.get("skills", [])
    if not isinstance(skills, list):
        _emit_error("State file 'skills' is not an array", "INVALID_STATE")
        return 2

    skill_map = _build_skill_map(skills)

    dangling = _validate_deps(skill_map)
    if dangling:
        _emit_error(
            f"Dangling dependency references: {'; '.join(dangling)}",
            "DANGLING_DEPENDENCY",
        )
        return 1

    in_degree: Dict[str, int] = {name: 0 for name in skill_map}
    adjacency: Dict[str, List[str]] = {name: [] for name in skill_map}

    for name, skill in skill_map.items():
        for dep in skill.get("depends_on", []) or []:
            adjacency[dep].append(name)
            in_degree[name] += 1

    def _tier_key(n: str) -> tuple[int, str]:
        return (0 if skill_map[n].get("tier") == "A" else 1, n)

    heap: List[tuple[int, str]] = []
    for n in skill_map:
        if in_degree[n] == 0:
            heapq.heappush(heap, _tier_key(n))

    execution_order: List[str] = []

    while heap:
        _, current = heapq.heappop(heap)
        execution_order.append(current)

        for dependent in adjacency[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                heapq.heappush(heap, _tier_key(dependent))

    if len(execution_order) < len(skill_map):
        cycle_participants = sorted(
            n for n in skill_map if n not in set(execution_order)
        )
        output = {
            "execution_order": execution_order,
            "circular_deps_detected": True,
            "cycle_participants": cycle_participants,
        }
        json.dump(output, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        return 1

    output = {
        "execution_order": execution_order,
        "circular_deps_detected": False,
        "cycle_participants": None,
    }
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


def check(state_file: str, skill_name: str, force: bool = False) -> int:
    path = Path(state_file)
    if not path.is_file():
        _emit_error(f"State file not found: {state_file}", "STATE_NOT_FOUND")
        return 2

    try:
        state = _load_yaml(path)
    except Exception as exc:
        _emit_error(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR")
        return 2

    skills = state.get("skills", [])
    if not isinstance(skills, list):
        _emit_error("State file 'skills' is not an array", "INVALID_STATE")
        return 2

    skill_map = _build_skill_map(skills)

    if skill_name not in skill_map:
        _emit_error(f"Skill '{skill_name}' not found in state", "SKILL_NOT_FOUND")
        return 2

    deps = skill_map[skill_name].get("depends_on", []) or []
    unmet: List[str] = []
    for dep in deps:
        if dep not in skill_map:
            _emit_error(
                f"Skill '{skill_name}' depends on unknown skill '{dep}'",
                "DANGLING_DEPENDENCY",
            )
            return 1
        if skill_map[dep].get("status") != "completed":
            unmet.append(dep)

    ready = len(unmet) == 0
    forced = force and not ready

    if forced:
        json.dump(
            {"warning": f"Forcing past unmet dependencies for '{skill_name}'", "unmet": unmet},
            sys.stderr,
        )
        sys.stderr.write("\n")

    output = {
        "skill": skill_name,
        "ready": ready,
        "unmet_deps": unmet,
        "forced": forced,
    }
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")

    if not ready and not force:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Campaign dependency computation and enforcement.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--compute",
        action="store_true",
        help="Compute execution order via topological sort",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check if a skill's dependencies are satisfied",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    parser.add_argument("--skill", help="Skill name (required for --check)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force past dependency check (--check only)",
    )
    args = parser.parse_args()

    if args.check and not args.skill:
        parser.error("--skill is required when using --check")

    if args.compute:
        return compute(args.state_file)
    return check(args.state_file, args.skill, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
