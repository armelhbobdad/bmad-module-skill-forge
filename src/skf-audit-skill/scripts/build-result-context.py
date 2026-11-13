#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""SKF audit-skill result context: the emitter payload of a finished audit,
and the route it hands on.

report.md section 1b runs this before the report's Workflow Recommendation:
the Result Contract hands the payload to the shared emitter
(`skf-emit-result-envelope.py emit --workflow skf-audit-skill`), which turns
it into the SKF_AUDIT_RESULT_JSON line and the run's result files, and the
report reads the route it prints. Every value follows from records the run
already wrote, so this script builds them rather than the model retyping
them from memory:

  - the drift report's frontmatter (read with render-drift-tables.py's
    reader, beside this script): skill_name, and audit_ref, upstream_moved
    and upstream_ref, which step 1 sections 5b and 6 wrote;
  - the classification step 5 saved (severity.json): drift_score,
    by_severity and total_findings.

next_workflow() is the one statement of the route rule.

Payload (written to --output, UTF-8 JSON):
  {"status": "success", "skill_name", "drift_score", "report_path" (REPORT
   as given), "next_workflow", "audit_ref", "upstream_moved",
   "upstream_ref",
   "result_contract": {"skill": "skf-audit-skill", "status": "success",
     "outputs": [{"type": "report", "path": REPORT}],
     "summary": {"drift_count" (total_findings), "severity" (drift_score),
                 "next_workflow", "audit_ref", "upstream_moved",
                 "upstream_ref"}},
   "customization_resolver_unavailable" (only when --resolver-unavailable
   is not blank: the emitter turns it into a warning)}

audit_ref is the ref the audit read, as step 1 recorded it: `audit_ref` is
`baseline_ref` when the audit stayed on the baseline, `upstream_ref` when
the operator chose `[C]`. It is null when empty, upstream_ref is null
unless upstream moved, and upstream_moved is true or false when the
frontmatter holds one (a YAML bool, or the word as text), else null.

CLI:
  uv run build-result-context.py --report <drift report>
      --classification <severity.json> [--resolver-unavailable <reason>]
      --output <result-context.json>

stdout (one object): {"status": "ok", "next_workflow", "drift_score",
"output"}.

Exit codes:
  0  the payload was written
  1  REPORT or the classification cannot be read, REPORT has no
     frontmatter or no skill_name, the classification holds no drift_score
     of CLEAN, MINOR, SIGNIFICANT or CRITICAL, no by_severity count or no
     total_findings, upstream_moved is true with no upstream_ref, or
     --output cannot be written ({"status": "error", "error"} on stdout,
     nothing written)
  2  a usage error (argparse, usage on stderr)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

WORKFLOW = "skf-audit-skill"
DRIFT_SCORES = ("CLEAN", "MINOR", "SIGNIFICANT", "CRITICAL")
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


class ContextError(Exception):
    """An input the payload cannot be built from: exit 1."""


def _sibling(name: str, module: str):
    """Import a script that sits beside this one (render-drift-tables.py)."""
    path = Path(__file__).resolve().parent / name
    spec = importlib.util.spec_from_file_location(module, path)
    if spec is None or spec.loader is None or not path.is_file():
        raise ContextError(f"{name} not found beside {Path(__file__).name}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def next_workflow(by_severity: dict, upstream_moved) -> str | None:
    """The route a finished audit hands on: "update-skill" when the saved
    classification counts a CRITICAL or HIGH finding, or when upstream_moved
    is true (the skill is built from an older ref than the remote now names,
    so the update compares the ref upstream moved to); None otherwise.

    >>> next_workflow({"CRITICAL": 0, "HIGH": 2, "MEDIUM": 0, "LOW": 0}, None)
    'update-skill'
    >>> next_workflow({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 3, "LOW": 1}, True)
    'update-skill'
    >>> next_workflow({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 3, "LOW": 1}, False) is None
    True
    """
    counts = by_severity if isinstance(by_severity, dict) else {}
    serious = any(_is_count(counts.get(level)) and counts[level] > 0 for level in ("CRITICAL", "HIGH"))
    return "update-skill" if serious or upstream_moved is True else None


def _text(value) -> str | None:
    """A frontmatter scalar as text, None when null or empty."""
    if value is None or isinstance(value, (dict, list)):
        return None
    value = str(value)
    return value if value.strip() else None


def _read_json(path: str, label: str):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContextError(f"{label} {path} cannot be read: {exc}") from None


def build(report: str, classification: str, resolver_unavailable: str | None = None) -> dict:
    """The emitter payload for the audit whose drift report and saved
    classification are given."""
    render = _sibling("render-drift-tables.py", "skf_audit_render_drift_tables")
    try:
        text = render.load_text(Path(report), "the drift report")
    except render.RenderError as exc:
        raise ContextError(f"--report {exc}") from None
    try:
        front = render.read_frontmatter(text)
    except render.RenderError as exc:
        raise ContextError(f"--report {report}: {exc}") from None
    skill = _text(front.get("skill_name"))
    if skill is None:
        raise ContextError(f"--report {report} names no skill_name in its frontmatter")

    severity = _read_json(classification, "--classification")
    if not isinstance(severity, dict):
        raise ContextError(f"--classification {classification} is not a severity classification: expected an "
                           "object (the output of skf-severity-classify.py)")
    score = severity.get("drift_score")
    if score not in DRIFT_SCORES:
        raise ContextError(f"--classification {classification} holds no drift_score of {', '.join(DRIFT_SCORES)} "
                           f"(drift_score {score!r})")
    by_severity = severity.get("by_severity")
    if not isinstance(by_severity, dict) or not all(_is_count(by_severity.get(level)) for level in SEVERITIES):
        raise ContextError(f"--classification {classification} holds no by_severity count for each of "
                           f"{', '.join(SEVERITIES)}")
    total = severity.get("total_findings")
    if not _is_count(total):
        raise ContextError(f"--classification {classification} holds no total_findings count")

    moved = render.flag(front.get("upstream_moved"))
    upstream_ref = _text(front.get("upstream_ref")) if moved else None
    if moved and upstream_ref is None:
        raise ContextError(f"--report {report}: upstream_moved is true but upstream_ref is empty: set it to the ref "
                           "upstream moved to")
    audit_ref = _text(front.get("audit_ref"))
    route = next_workflow(by_severity, moved)

    payload = {
        "status": "success",
        "skill_name": skill,
        "drift_score": score,
        "report_path": report,
        "next_workflow": route,
        "audit_ref": audit_ref,
        "upstream_moved": moved,
        "upstream_ref": upstream_ref,
        "result_contract": {
            "skill": WORKFLOW,
            "status": "success",
            "outputs": [{"type": "report", "path": report}],
            "summary": {"drift_count": total, "severity": score, "next_workflow": route, "audit_ref": audit_ref,
                        "upstream_moved": moved, "upstream_ref": upstream_ref},
        },
    }
    reason = (resolver_unavailable or "").strip()
    if reason:
        payload["customization_resolver_unavailable"] = reason
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build-result-context.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--report", required=True, help="the drift report, whose frontmatter holds the run context")
    parser.add_argument("--classification", required=True,
                        help="severity.json, the skf-severity-classify.py result step 5 saved")
    parser.add_argument("--resolver-unavailable", default=None,
                        help="the reason On Activation step 3 kept when the customization resolver could not run")
    parser.add_argument("--output", required=True, help="where to write the payload (result-context.json)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = build(args.report, args.classification, args.resolver_unavailable)
        out = Path(args.output)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError as exc:
            raise ContextError(f"--output {args.output} cannot be written: {exc}") from None
    except ContextError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    print(json.dumps({"status": "ok", "next_workflow": payload["next_workflow"], "drift_score": payload["drift_score"],
                      "output": out.as_posix()}, indent=2))
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    a reason or a path may hold.
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
    sys.exit(main())
