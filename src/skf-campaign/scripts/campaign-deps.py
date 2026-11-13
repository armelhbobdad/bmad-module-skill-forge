# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Campaign Deps — dependency computation and enforcement for campaign skills.

Three modes:
  --compute: topological sort of all skills from depends_on edges
  --check:   verify a single skill's dependencies are satisfied
  --render:  the strategy view step-02 shows, in the order --compute gives

A Tier A skill may not depend on a Tier B skill: Tier B skills are built in
the batch stage, after the skill loop that builds Tier A skills, so the Tier A
skill could never pass its dependency gate. --compute reports each such edge
in `tier_inversions` and exits 1, so the strategy stage rejects the plan
before any skill is built. That rule and the dangling-reference rule come
from campaign-parse-manifest.py's dependency_problems, the one statement of
both, so Setup and Strategy report the same entries.

At a blocked skill, --check names the status of each unmet dependency and the
headless default: `skip` when every unmet dependency failed or was skipped
(it can never complete in this run), `halt` when one is still pending or
active (an order the loop cannot follow).

On a cycle, `cycle_participants` are the skills the sort could not place and
`cycle_edges` every depends_on edge between two of them, so the cycle is
named without reading the state by hand.

--render orders the skills with the same code as --compute and prints the
strategy view as text with ASCII marks: each skill in execution order with
its tier, its pin (or `latest`) and what it depends on, then the campaign's
quality gate and the tier counts. On a plan --compute rejects it exits as
--compute does and prints no view; a cycle is then a CIRCULAR_DEPENDENCY
error on stderr that names the participants and edges, since --render
prints no JSON. A dependency named twice is listed once, in the view and in
`cycle_edges`. Text goes out as UTF-8, so a campaign name in any script
prints on a Windows console too.

CLI:
  uv run campaign-deps.py --compute --state-file <path>
  uv run campaign-deps.py --render --state-file <path>
  uv run campaign-deps.py --check --state-file <path> --skill <name>
  uv run campaign-deps.py --check --state-file <path> --skill <name> --force

Output (on stdout):
  --compute (JSON):
    {"execution_order": [...], "circular_deps_detected": bool,
     "cycle_participants": [...] | null,
     "cycle_edges": [{"skill", "depends_on"}] | null,
     "tier_counts": {"A": int, "B": int},
     "tier_inversions": [{"skill": "<Tier A>", "depends_on": "<Tier B>"}]}

  --render (text):
    CAMPAIGN STRATEGY: <campaign name>

    EXECUTION ORDER:
      1. <skill> [Tier <A|B>] <pin|latest>
      2. <skill> [Tier <A|B>] <pin|latest>, depends on: <dep>, <dep>

    QUALITY GATE: <hard>, soft target <N>%, soft fallback <N>%
    TIERS: <n> Tier A (full pipeline), <m> Tier B (QS batch)

  --check (JSON):
    {"skill": "name", "ready": bool, "unmet_deps": [...], "forced": bool,
     "unmet_status": {"<dep>": "<status>"}, "default_action": "skip" | "halt" | null}

Exit codes:
  0  success / ready / force-override
  1  circular deps / tier inversion / unmet deps / dangling reference
  2  error (missing file, bad YAML)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import heapq
from pathlib import Path
from typing import Any, Dict, List

import yaml

MANIFEST_SCRIPT = Path(__file__).resolve().with_name("campaign-parse-manifest.py")


def _dependency_problems(skills: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """campaign-parse-manifest.py's dependency_problems (one rule for Setup and Strategy)."""
    spec = importlib.util.spec_from_file_location("campaign_parse_manifest", MANIFEST_SCRIPT)
    manifest = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manifest)
    return manifest.dependency_problems(skills)


def _emit_error(message: str, code: str) -> None:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_skill_map(skills: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s["name"]: s for s in skills}


class _StateError(Exception):
    """A state the modes cannot read: reported on stderr with exit 2."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def _read_state(state_file: str) -> Dict[str, Any]:
    path = Path(state_file)
    if not path.is_file():
        raise _StateError(f"State file not found: {state_file}", "STATE_NOT_FOUND")
    try:
        state = _load_yaml(path)
    except Exception as exc:
        raise _StateError(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR") from exc
    if not isinstance(state, dict) or not isinstance(state.get("skills", []), list):
        raise _StateError("State file 'skills' is not an array", "INVALID_STATE")
    return state


def plan(skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The execution order of the skills, and why the stages cannot follow it, if they cannot.

    --compute and --render both order the skills here. `dangling` lists
    each depends_on name no skill has; the order is not computed then.
    """
    skill_map = _build_skill_map(skills)

    tier_counts = {"A": 0, "B": 0}
    for skill in skill_map.values():
        tier = skill.get("tier")
        if tier in tier_counts:
            tier_counts[tier] += 1

    problems = _dependency_problems(list(skill_map.values()))
    result: Dict[str, Any] = {
        "execution_order": [],
        "circular_deps_detected": False,
        "cycle_participants": None,
        "cycle_edges": None,
        "tier_counts": tier_counts,
        "tier_inversions": problems["tier_inversions"],
        "dangling": problems["dangling_depends_on"],
    }
    if result["dangling"]:
        return result

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

    result["execution_order"] = execution_order
    if len(execution_order) < len(skill_map):
        placed = set(execution_order)
        participants = sorted(n for n in skill_map if n not in placed)
        unplaced = set(participants)
        result["circular_deps_detected"] = True
        result["cycle_participants"] = participants
        result["cycle_edges"] = [
            {"skill": name, "depends_on": dep}
            for name, dep in sorted(
                (name, dep)
                for name in participants
                for dep in dict.fromkeys(skill_map[name].get("depends_on", []) or [])
                if dep in unplaced
            )
        ]
    return result


def _dangling_error(result: Dict[str, Any]) -> None:
    dangling = [f"{d['skill']} depends on unknown skill '{d['depends_on']}'" for d in result["dangling"]]
    _emit_error(f"Dangling dependency references: {'; '.join(dangling)}", "DANGLING_DEPENDENCY")


def _inversion_error(result: Dict[str, Any]) -> None:
    _emit_error(
        "Tier A skills depend on Tier B skills, which are built after them: "
        + "; ".join(f"{i['skill']} depends on {i['depends_on']}" for i in result["tier_inversions"]),
        "TIER_INVERSION",
    )


def compute(state_file: str) -> int:
    try:
        state = _read_state(state_file)
    except _StateError as exc:
        _emit_error(str(exc), exc.code)
        return 2

    result = plan(state.get("skills", []))
    if result["dangling"]:
        _dangling_error(result)
        return 1

    output = {key: value for key, value in result.items() if key != "dangling"}
    if result["circular_deps_detected"]:
        json.dump(output, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        return 1

    if result["tier_inversions"]:
        _inversion_error(result)

    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 1 if result["tier_inversions"] else 0


def _percent(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}%"


def render(state_file: str) -> int:
    """Print the strategy view, or exit as --compute does on a plan it rejects."""
    try:
        state = _read_state(state_file)
    except _StateError as exc:
        _emit_error(str(exc), exc.code)
        return 2

    skills = state.get("skills", [])
    result = plan(skills)
    if result["dangling"]:
        _dangling_error(result)
        return 1
    if result["circular_deps_detected"]:
        edges = "; ".join(f"{e['skill']} depends on {e['depends_on']}" for e in result["cycle_edges"])
        _emit_error(
            f"Circular dependencies among {', '.join(result['cycle_participants'])}: {edges}",
            "CIRCULAR_DEPENDENCY",
        )
        return 1
    if result["tier_inversions"]:
        _inversion_error(result)
        return 1

    skill_map = _build_skill_map(skills)
    campaign = state.get("campaign") if isinstance(state.get("campaign"), dict) else {}
    gate = campaign.get("quality_gate") if isinstance(campaign.get("quality_gate"), dict) else {}
    lines = [f"CAMPAIGN STRATEGY: {campaign.get('name', '')}", "", "EXECUTION ORDER:"]
    for number, name in enumerate(result["execution_order"], start=1):
        skill = skill_map[name]
        pin = skill.get("pin")
        row = f"  {number}. {name} [Tier {skill.get('tier')}] {pin if pin not in (None, '') else 'latest'}"
        deps = list(dict.fromkeys(skill.get("depends_on", []) or []))
        if deps:
            row += f", depends on: {', '.join(deps)}"
        lines.append(row)
    counts = result["tier_counts"]
    lines += [
        "",
        f"QUALITY GATE: {gate.get('hard')}, soft target {_percent(gate.get('soft_target'))}, "
        f"soft fallback {_percent(gate.get('soft_fallback'))}",
        f"TIERS: {counts['A']} Tier A (full pipeline), {counts['B']} Tier B (QS batch)",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
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
    unmet_status = {dep: skill_map[dep].get("status") for dep in unmet}
    if ready:
        default_action = None
    elif all(status in ("failed", "skipped") for status in unmet_status.values()):
        default_action = "skip"
    else:
        default_action = "halt"

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
        "unmet_status": unmet_status,
        "default_action": default_action,
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
    mode.add_argument(
        "--render",
        action="store_true",
        help="Print the strategy view, in the order --compute gives",
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
    if args.render:
        return render(args.state_file)
    return check(args.state_file, args.skill, force=args.force)


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every
    character a campaign name may hold.
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
