# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Campaign Report — generate a markdown report from campaign state + template.

CLI:
  uv run campaign-report.py \
      --state-file <path> --template-file <path> --output-file <path>

Output (JSON on stdout):
  {"status":"success","report_path":"...","skills_completed":N,"skills_failed":N,
   "quality_scores":{"skill":score,...},"duration":"..."}

Exit codes:
  0  success
  2  error (missing file, bad YAML, template error)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def _emit_error(message: str, code: str) -> None:
    json.dump({"error": message, "code": code}, sys.stderr)
    sys.stderr.write("\n")


def _load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _format_duration(start: Optional[datetime], end: Optional[datetime]) -> str:
    if not start or not end:
        return "N/A"
    delta = end - start
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "N/A"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _compute_aggregates(state: Dict[str, Any]) -> Dict[str, Any]:
    campaign = state.get("campaign", {})
    skills: List[Dict[str, Any]] = state.get("skills", [])

    started_at_str = campaign.get("started_at", "")
    last_updated_str = campaign.get("last_updated", "")
    started_at = _parse_iso(started_at_str)
    last_updated = _parse_iso(last_updated_str)

    completed = [s for s in skills if s.get("status") == "completed"]
    failed = [s for s in skills if s.get("status") == "failed"]
    skipped = [s for s in skills if s.get("status") == "skipped"]

    scores = [s["quality_score"] for s in completed if s.get("quality_score") is not None]
    quality_min = min(scores) if scores else 0
    quality_max = max(scores) if scores else 0
    quality_avg = round(sum(scores) / len(scores), 1) if scores else 0

    all_workarounds: List[str] = []
    skills_with_wa = 0
    for s in skills:
        wa = s.get("workarounds_applied", []) or []
        if wa:
            skills_with_wa += 1
            all_workarounds.extend(wa)

    skills_table_rows = []
    for s in skills:
        wa = s.get("workarounds_applied", []) or []
        skills_table_rows.append(
            f"| {s.get('name', '')} "
            f"| {s.get('tier', '')} "
            f"| {s.get('status', '')} "
            f"| {s.get('quality_score', 'N/A')} "
            f"| {s.get('pin', 'N/A')} "
            f"| {len(wa)} |"
        )

    quality_breakdown_rows = []
    for s in completed:
        qs = s.get("quality_score")
        quality_breakdown_rows.append(f"- **{s['name']}**: {qs if qs is not None else 'N/A'}")

    if not quality_breakdown_rows:
        quality_breakdown_rows.append("No completed skills with quality scores.")

    if all_workarounds:
        workarounds_list_items = [f"- `{fp}`" for fp in all_workarounds]
    else:
        workarounds_list_items = ["No workarounds applied."]

    duration_table_rows = []
    for s in skills:
        s_start = _parse_iso(s.get("started_at"))
        s_end = _parse_iso(s.get("completed_at"))
        s_start_str = s.get("started_at", "N/A") or "N/A"
        s_end_str = s.get("completed_at", "N/A") or "N/A"
        dur = _format_duration(s_start, s_end)
        duration_table_rows.append(f"| {s.get('name', '')} | {s_start_str} | {s_end_str} | {dur} |")

    failed_skipped_lines = []
    if failed:
        failed_skipped_lines.append("### Failed Skills\n")
        for s in failed:
            failed_skipped_lines.append(f"- **{s['name']}** (Tier {s.get('tier', '?')})")
    if skipped:
        failed_skipped_lines.append("\n### Skipped Skills\n")
        for s in skipped:
            failed_skipped_lines.append(f"- **{s['name']}** (Tier {s.get('tier', '?')})")
    if not failed and not skipped:
        if skills:
            failed_skipped_lines.append("All skills completed successfully.")
        else:
            failed_skipped_lines.append("No skills in campaign.")

    quality_gate = campaign.get("quality_gate", {})

    return {
        "campaign_name": campaign.get("name", ""),
        "started_at": started_at_str or "N/A",
        "completed_at": last_updated_str or "N/A",
        "duration": _format_duration(started_at, last_updated),
        "quality_gate_hard": quality_gate.get("hard", "N/A"),
        "quality_gate_soft_target": str(quality_gate.get("soft_target", "N/A")),
        "quality_gate_soft_fallback": str(quality_gate.get("soft_fallback", "N/A")),
        "skills_completed": str(len(completed)),
        "skills_failed": str(len(failed)),
        "skills_skipped": str(len(skipped)),
        "skills_table": "\n".join(skills_table_rows),
        "quality_min": str(quality_min),
        "quality_max": str(quality_max),
        "quality_avg": str(quality_avg),
        "quality_breakdown": "\n".join(quality_breakdown_rows),
        "total_workarounds": str(len(all_workarounds)),
        "skills_with_workarounds": str(skills_with_wa),
        "workarounds_list": "\n".join(workarounds_list_items),
        "duration_table": "\n".join(duration_table_rows),
        "failed_skipped_section": "\n".join(failed_skipped_lines),
    }


def run(state_file: str, template_file: str, output_file: str) -> int:
    state_path = Path(state_file)
    template_path = Path(template_file)
    output_path = Path(output_file)

    if not state_path.is_file():
        _emit_error(f"State file not found: {state_file}", "STATE_NOT_FOUND")
        return 2

    if not template_path.is_file():
        _emit_error(f"Template file not found: {template_file}", "TEMPLATE_NOT_FOUND")
        return 2

    try:
        state = _load_yaml(state_path)
    except Exception as exc:
        _emit_error(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR")
        return 2

    if not isinstance(state, dict):
        _emit_error("State file root is not a mapping", "INVALID_STATE")
        return 2

    try:
        template = template_path.read_text(encoding="utf-8")
    except Exception as exc:
        _emit_error(f"Failed to read template file: {exc}", "TEMPLATE_READ_ERROR")
        return 2

    try:
        aggregates = _compute_aggregates(state)
    except Exception as exc:
        _emit_error(f"Failed to compute report aggregates: {exc}", "AGGREGATE_ERROR")
        return 2

    report = template
    for key, value in aggregates.items():
        report = report.replace("{{" + key + "}}", value)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        output_path.write_text(report, encoding="utf-8")
    except Exception as exc:
        _emit_error(f"Failed to write report: {exc}", "WRITE_ERROR")
        return 2

    skills = state.get("skills", [])
    completed_count = sum(1 for s in skills if s.get("status") == "completed")
    failed_count = sum(1 for s in skills if s.get("status") == "failed")
    quality_scores = {
        s["name"]: s["quality_score"]
        for s in skills
        if s.get("status") == "completed" and s.get("quality_score") is not None
    }

    result = {
        "status": "success",
        "report_path": output_path.as_posix(),
        "skills_completed": completed_count,
        "skills_failed": failed_count,
        "quality_scores": quality_scores,
        "duration": aggregates["duration"],
    }
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a campaign report from state and template.",
    )
    parser.add_argument("--state-file", required=True, help="Path to _campaign-state.yaml")
    parser.add_argument("--template-file", required=True, help="Path to campaign-report-template.md")
    parser.add_argument("--output-file", required=True, help="Path to write the generated report")
    args = parser.parse_args()
    return run(args.state_file, args.template_file, args.output_file)


if __name__ == "__main__":
    raise SystemExit(main())
