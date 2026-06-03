# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Render Kickoff — fill the mechanical kickoff-template placeholders.

step-05 emits a kickoff message per Tier-A skill. Most of its placeholders are
direct field copies from state + brief (campaign name, stage, quality gate,
skill identity, repo, pin, commit, the dependency-status table, the workaround
list) — mechanical substitution that an LLM should not hand-perform 15× per
campaign. This script renders those deterministically and leaves the three
judgment slots untouched for the LLM to fill in context:

  {{brief_summary}}        — concise summary of the brief target entry
  {{persistent_facts}}     — campaign-wide facts resolved in On Activation
  {{directive_content}}    — raw directive file content

CLI:
  uv run campaign-render-kickoff.py --state-file <p> --brief-file <p> \
      --skill <name> --template <p> [--workarounds '<json-list>']

Output: the rendered kickoff markdown on stdout (judgment slots preserved).

Exit codes:
  0  rendered
  2  error (missing file, bad YAML, skill/target not found, bad --workarounds)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Placeholders this script intentionally leaves for the LLM to fill.
JUDGMENT_SLOTS = ("{{brief_summary}}", "{{persistent_facts}}", "{{directive_content}}")


def _err(message: str, code: str) -> int:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")
    return 2


def _quality_gate_summary(qg: Dict[str, Any]) -> str:
    return (
        f"Hard: {qg.get('hard', 'N/A')} | "
        f"Soft: {qg.get('soft_target', 'N/A')} (fallback: {qg.get('soft_fallback', 'N/A')})"
    )


def _dependency_status_table(skill: Dict[str, Any], skill_map: Dict[str, Dict[str, Any]]) -> str:
    deps = skill.get("depends_on", []) or []
    if not deps:
        return "No dependencies."
    rows = ["| Dependency | Status |", "|------------|--------|"]
    for dep in deps:
        status = skill_map.get(dep, {}).get("status", "unknown")
        rows.append(f"| {dep} | {status} |")
    return "\n".join(rows)


def _workarounds_list(workarounds: List[str]) -> str:
    if not workarounds:
        return "None"
    return "\n".join(f"- {w}" for w in workarounds)


def render_kickoff(
    state: Dict[str, Any],
    brief: Dict[str, Any],
    skill_name: str,
    template: str,
    workarounds: Optional[List[str]] = None,
) -> str:
    campaign = state.get("campaign", {})
    skills = state.get("skills", [])
    skill_map = {s["name"]: s for s in skills}
    if skill_name not in skill_map:
        raise KeyError(f"Skill '{skill_name}' not found in state")
    skill = skill_map[skill_name]

    targets = {t["name"]: t for t in brief.get("targets", [])}
    repo_url = targets.get(skill_name, {}).get("repo_url", "")

    wa = workarounds if workarounds is not None else (skill.get("workarounds_applied", []) or [])

    mechanical = {
        "{{campaign_name}}": str(campaign.get("name", "")),
        "{{current_stage}}": str(campaign.get("current_stage", "")),
        "{{quality_gate_summary}}": _quality_gate_summary(campaign.get("quality_gate", {})),
        "{{skill_name}}": skill_name,
        "{{skill_tier}}": str(skill.get("tier", "")),
        "{{pin}}": skill.get("pin") or "latest",
        "{{commit_sha}}": skill.get("commit_sha") or "unknown",
        "{{repo_url}}": repo_url,
        "{{workarounds_list}}": _workarounds_list(wa),
        "{{dependency_status_table}}": _dependency_status_table(skill, skill_map),
    }

    out = template
    for key, value in mechanical.items():
        out = out.replace(key, value)
    return out


def run(state_file: str, brief_file: str, skill: str, template_file: str, workarounds_json: Optional[str]) -> int:
    for label, p in (("State", state_file), ("Brief", brief_file), ("Template", template_file)):
        if not Path(p).is_file():
            return _err(f"{label} file not found: {p}", f"{label.upper()}_NOT_FOUND")

    try:
        state = yaml.safe_load(Path(state_file).read_text(encoding="utf-8"))
        brief = yaml.safe_load(Path(brief_file).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return _err(f"Failed to parse YAML: {exc}", "PARSE_ERROR")
    template = Path(template_file).read_text(encoding="utf-8")

    workarounds: Optional[List[str]] = None
    if workarounds_json:
        try:
            workarounds = json.loads(workarounds_json)
            if not isinstance(workarounds, list):
                raise ValueError("not a list")
        except ValueError as exc:
            return _err(f"--workarounds must be a JSON list: {exc}", "BAD_WORKAROUNDS")

    try:
        rendered = render_kickoff(state, brief, skill, template, workarounds)
    except KeyError as exc:
        return _err(str(exc), "SKILL_NOT_FOUND")

    sys.stdout.write(rendered)
    if not rendered.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="campaign-render-kickoff",
        description="Render the mechanical placeholders in the campaign kickoff template.",
    )
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--brief-file", required=True)
    parser.add_argument("--skill", required=True, help="skill name (must exist in state)")
    parser.add_argument("--template", required=True, dest="template_file")
    parser.add_argument("--workarounds", dest="workarounds_json", help="JSON list of applied workarounds")
    args = parser.parse_args(argv)
    return run(args.state_file, args.brief_file, args.skill, args.template_file, args.workarounds_json)


if __name__ == "__main__":
    raise SystemExit(main())
