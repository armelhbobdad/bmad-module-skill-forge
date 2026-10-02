# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Campaign Report: generate a markdown report from campaign state + template.

CLI:
  uv run campaign-report.py \
      --state-file <path> --template-file <path> --output-file <path> \
      [--context-file <path> [--decision-log <path>]]

Output (JSON on stdout):
  {"status":"success","report_path":"...","skills_completed":N,"skills_failed":N,
   "quality_scores":{"skill":score,...},"duration":"...",
   "export_verdicts":{"skill":"pass|fallback|fail",...},"skills_excluded":["skill",...],
   "skills_exported":["skill",...],
   "export_failures":[{"skill","halt_reason","exit_code"},...]}

`export_verdicts` holds each completed skill's quality-gate verdict at Export
and `skills_excluded` the completed skills the gate kept from export, both
from campaign-quality-gate.py classify (the rule step-10 applies, the state's
directive included), so a headless caller sees which completed skills were
not exported. Both are null when the gate cannot be applied (an invalid gate
or an unreadable directive), and the report says so.

`skills_exported` and `export_failures` are what Export did: the `export`
outcome campaign-state.py recorded for each skill after its skf-export-skill
call, an exported skill by name and a failed one with that call's
halt_reason and exit code. Both are null when the Export stage did not run
(`campaign.current_stage` below 9). The report's Export Gate table shows the
same outcome per skill in its Export column.

--context-file also writes the payload skf-emit-result-envelope.py turns into
the campaign's SKF_CAMPAIGN_RESULT_JSON line (schemas/
skf-campaign-result-envelope.v1.json): the result above, with the report as
`campaign_report_path` and --decision-log as `decision_log`. When the report
cannot be written it still writes one, the degraded finish: `status` error,
`halt_reason` report-failure, no report path, and the counts and scores the
state gives (none when it cannot be read). So step 11 stages nothing by hand
on either path. It first removes the payload an earlier run left, so a
payload that cannot be written leaves no file and step 11 takes its fallback
instead of an earlier run's envelope.

Exit codes:
  0  success
  2  error (missing file, bad YAML, template error)
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

GATE_SCRIPT = Path(__file__).resolve().with_name("campaign-quality-gate.py")


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


def _export_classification(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """campaign-quality-gate.py classify for the state, or None when the gate cannot be applied."""
    spec = importlib.util.spec_from_file_location("campaign_quality_gate", GATE_SCRIPT)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    campaign = state.get("campaign") or {}
    try:
        return gate.classify(state, gate.read_directive(campaign.get("directive_path")))
    except (gate.GateError, KeyError, TypeError, AttributeError):
        return None


def _export_record(skill: Any) -> Optional[Dict[str, Any]]:
    """The `export` outcome campaign-state.py recorded for a skill, or None."""
    record = skill.get("export") if isinstance(skill, dict) else None
    return record if isinstance(record, dict) and record.get("status") in ("exported", "failed") else None


def _export_cell(record: Optional[Dict[str, Any]], verdict: str) -> str:
    if record is None:
        return "not exported" if verdict == "fail" else "N/A"
    if record["status"] == "exported":
        return "exported"
    why = record.get("halt_reason") or (
        f"exit {record['exit_code']}" if record.get("exit_code") is not None else "no exit code")
    return f"failed ({why})"


def _export_outcomes(state: Any) -> Dict[str, Any]:
    """What Export did, from each skill's recorded `export`; both null before stage 9 ran."""
    campaign = state.get("campaign") if isinstance(state, dict) else None
    stage = campaign.get("current_stage") if isinstance(campaign, dict) else None
    if not isinstance(stage, int) or isinstance(stage, bool) or stage < 9:
        return {"skills_exported": None, "export_failures": None}
    skills = state.get("skills")
    exported, failures = [], []
    for skill in skills if isinstance(skills, list) else []:
        record = _export_record(skill)
        if record is None or not skill.get("name"):
            continue
        if record["status"] == "exported":
            exported.append(skill["name"])
        else:
            failures.append({"skill": skill["name"], "halt_reason": record.get("halt_reason"),
                             "exit_code": record.get("exit_code")})
    return {"skills_exported": exported, "export_failures": failures}


def _export_gate_section(
    classification: Optional[Dict[str, Any]], state: Optional[Dict[str, Any]] = None
) -> str:
    if classification is None:
        return "The quality gate could not be applied to the completed skills (see the decision log)."
    rows = classification["skills"]
    if not rows:
        return "No completed skills."
    records = {s.get("name"): _export_record(s) for s in (state or {}).get("skills") or [] if isinstance(s, dict)}
    lines = ["| Skill | Quality Score | Gate | Export |", "|-------|---------------|------|--------|"]
    for row in rows:
        score = row["quality_score"] if row["quality_score"] is not None else "N/A"
        export = _export_cell(records.get(row["name"]), row["verdict"])
        lines.append(f"| {row['name']} | {score} | {row['verdict']} | {export} |")
    excluded = classification["excluded"]
    if excluded:
        listed = ", ".join(
            f"{e['name']} ({e['quality_score'] if e['quality_score'] is not None else 'N/A'}: {e['reason']})"
            for e in excluded
        )
        lines += ["", f"**Not exported (below the quality gate):** {listed}"]
    return "\n".join(lines)


def _compute_aggregates(
    state: Dict[str, Any], classification: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
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
    if classification is None:
        classification = _export_classification(state)

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
        "export_gate_section": _export_gate_section(classification, state),
    }


def _counts(state: Any) -> Dict[str, Any]:
    """The completed and failed counts and the completed skills' scores."""
    skills = state.get("skills", []) if isinstance(state, dict) else []
    skills = [s for s in skills if isinstance(s, dict)] if isinstance(skills, list) else []
    return {
        "skills_completed": sum(1 for s in skills if s.get("status") == "completed"),
        "skills_failed": sum(1 for s in skills if s.get("status") == "failed"),
        "quality_scores": {
            s["name"]: s["quality_score"]
            for s in skills
            if s.get("status") == "completed" and s.get("quality_score") is not None and s.get("name")
        },
    }


def _write_context(path: Optional[str], payload: Dict[str, Any]) -> None:
    """Write the emitter payload; a failed write leaves step 11 its fallback."""
    if not path:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        _emit_error(f"Failed to write the envelope context: {exc}", "CONTEXT_WRITE_ERROR")


def run(
    state_file: str,
    template_file: str,
    output_file: str,
    context_file: Optional[str] = None,
    decision_log: Optional[str] = None,
) -> int:
    state_path = Path(state_file)
    template_path = Path(template_file)
    output_path = Path(output_file)
    state: Any = None
    if context_file:
        with contextlib.suppress(OSError):
            Path(context_file).unlink(missing_ok=True)

    def fail(message: str, code: str) -> int:
        _emit_error(message, code)
        _write_context(context_file, {
            "status": "error",
            "halt_reason": "report-failure",
            **_counts(state),
            **_export_outcomes(state),
            "campaign_report_path": None,
            "decision_log": decision_log,
        })
        return 2

    if not state_path.is_file():
        return fail(f"State file not found: {state_file}", "STATE_NOT_FOUND")

    try:
        state = _load_yaml(state_path)
    except Exception as exc:
        return fail(f"Failed to parse state file: {exc}", "STATE_PARSE_ERROR")

    if not isinstance(state, dict):
        return fail("State file root is not a mapping", "INVALID_STATE")

    # Read after the state, so a degraded payload still carries its counts.
    if not template_path.is_file():
        return fail(f"Template file not found: {template_file}", "TEMPLATE_NOT_FOUND")

    try:
        template = template_path.read_text(encoding="utf-8")
    except Exception as exc:
        return fail(f"Failed to read template file: {exc}", "TEMPLATE_READ_ERROR")

    try:
        classification = _export_classification(state)
        aggregates = _compute_aggregates(state, classification)
    except Exception as exc:
        return fail(f"Failed to compute report aggregates: {exc}", "AGGREGATE_ERROR")

    report = template
    for key, value in aggregates.items():
        report = report.replace("{{" + key + "}}", value)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    except Exception as exc:
        return fail(f"Failed to write report: {exc}", "WRITE_ERROR")

    result = {
        "status": "success",
        "report_path": output_path.as_posix(),
        **_counts(state),
        "duration": aggregates["duration"],
        "export_verdicts": (
            None if classification is None else {r["name"]: r["verdict"] for r in classification["skills"]}
        ),
        "skills_excluded": (
            None if classification is None else [e["name"] for e in classification["excluded"]]
        ),
        **_export_outcomes(state),
    }
    _write_context(context_file, {
        "status": "success",
        "skills_completed": result["skills_completed"],
        "skills_failed": result["skills_failed"],
        "quality_scores": result["quality_scores"],
        "export_verdicts": result["export_verdicts"],
        "skills_excluded": result["skills_excluded"],
        "skills_exported": result["skills_exported"],
        "export_failures": result["export_failures"],
        "campaign_report_path": result["report_path"],
        "decision_log": decision_log,
        "duration": result["duration"],
    })
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
    parser.add_argument(
        "--context-file",
        help="Also write the SKF_CAMPAIGN_RESULT_JSON payload for skf-emit-result-envelope.py here",
    )
    parser.add_argument("--decision-log", help="Path to _campaign-decision-log.md, for the payload")
    args = parser.parse_args()
    return run(args.state_file, args.template_file, args.output_file, args.context_file, args.decision_log)


if __name__ == "__main__":
    raise SystemExit(main())
