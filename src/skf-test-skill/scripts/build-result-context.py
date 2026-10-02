#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF test-skill result context: the emitter payload of a finished run.

report.md §4c hands the shared emitter (`skf-emit-result-envelope.py emit
--workflow skf-test-skill`) one payload, which the emitter turns into the
SKF_TEST_RESULT_JSON line and the run's result files. Every value in it
follows from records the run already wrote, so this script builds it rather
than the model retyping them from memory:

  - the report frontmatter: skillName, runId, testMode, hardGate,
    testResult, score, threshold, thresholdFallback, originalThreshold and
    evidenceReportPath (the steps write the verdict inputs there, so a
    compacted context cannot change them);
  - the gap ledger: the gap counts by severity (gap-ledger.py's summary);
  - the scoring script's output, which score.md saves: activeCategories and
    inconclusiveReasons. A run the hard gate blocked was never scored and
    has none.

The derived fields live here, in one place:

  testResult       verdict          summary.result   exit_code  next_workflow
  pass             PASS             PASS             0          export-skill
  pass-with-drift  pass-with-drift  PASS_WITH_DRIFT  4          update-skill
  fail             FAIL             FAIL             2          update-skill
  inconclusive     INCONCLUSIVE     INCONCLUSIVE     3          null

A run the hard gate blocked (frontmatter hardGate: 'blocked') takes the
hard gate's own payload (hard-gate.py `blocked_envelope`): status error,
halt_reason hard-gate-blocked, verdict FAIL, exit 2, score and threshold
null. threshold_fallback and original_threshold appear only when the
threshold fallback fired: absent, never false or null, otherwise.

Payload (written to --output, UTF-8 JSON):
  {<the envelope fields: status, skill_name, verdict, score, threshold,
    report_path, next_workflow, exit_code, halt_reason, and
    threshold_fallback and original_threshold when the fallback fired>,
   "warnings": [<each --warning, in order>] (only when one is given),
   "result_contract": {"skill": "skf-test-skill", <the envelope fields>,
     "outputs": [{"type": "report", "path": <report>}],
     "summary": {"score", "threshold", "result", "testMode",
                 "activeCategories", "inconclusiveReasons" (INCONCLUSIVE),
                 "threshold_fallback", "original_threshold",
                 "evidence_report_path" (fallback only), "gapCounts",
                 "hardGate"},
     "runId": <runId>, "healthCheckDispatched": <bool>}}

CLI:
  uv run build-result-context.py --report <report.md> --ledger <ledger.json>
      [--score <scoring output>] [--no-health-check] [--warning <text>]...
      --output <result-context.json>

--warning hands the emitter a warning the run kept for its result (such as
`customization_resolver_unavailable: <reason>`); the emitter adds the ones
the run recorded in its sink, and stamps all of them into the envelope and
the result files.

stdout (one object): {"status", "verdict", "exit_code", "next_workflow",
"halt_reason", "target", "output"}; `target` is the --target the emit call
takes: "stderr" for a blocked run, else "stdout".

Exit codes:
  0  the payload was written
  1  an input is missing or unreadable, the report's frontmatter holds no
     settled verdict, or --output cannot be written ({"status": "error",
     "error"} on stdout)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

WORKFLOW = "skf-test-skill"
# testResult -> (verdict, summary.result, exit_code, next_workflow)
VERDICTS = {
    "pass": ("PASS", "PASS", 0, "export-skill"),
    "pass-with-drift": ("pass-with-drift", "PASS_WITH_DRIFT", 4, "update-skill"),
    "fail": ("FAIL", "FAIL", 2, "update-skill"),
    "inconclusive": ("INCONCLUSIVE", "INCONCLUSIVE", 3, None),
}
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$")


class ContextError(Exception):
    """An input the payload cannot be built from: exit 1."""


def _sibling(name: str, module: str):
    """Import a script that sits beside this one (gap-ledger.py, hard-gate.py)."""
    path = Path(__file__).resolve().parent / name
    spec = importlib.util.spec_from_file_location(module, path)
    if spec is None or spec.loader is None or not path.is_file():
        raise ContextError(f"{name} not found beside {Path(__file__).name}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def read_frontmatter(text: str) -> dict[str, str]:
    """Top-level scalar keys of the leading `---` block, quotes removed.

    >>> read_frontmatter("---\\ntestResult: 'pass'\\nscore: 91.5%\\nsteps: ['a']\\n---\\n# R")
    {'testResult': 'pass', 'score': '91.5%', 'steps': "['a']"}
    >>> read_frontmatter("# no frontmatter")
    {}
    """
    lines = text.lstrip("﻿").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        m = _KEY_RE.match(line.rstrip("\r"))
        if not m:
            continue
        value = m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[m.group(1)] = value
    return {}


def percent(value: str | None):
    """'87.5%' -> 87.5, '90%' or '90' -> 90, '' or None -> None.

    >>> percent("87.5%"), percent("90"), percent(""), percent(None)
    (87.5, 90, None, None)
    """
    text = (value or "").strip().rstrip("%").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        raise ContextError(f"not a percentage: {value!r}") from None
    return int(number) if number.is_integer() else number


def _read_json(path: str, label: str):
    try:
        return json.loads(Path(path).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContextError(f"{label} {path} cannot be read: {exc}") from exc


def build(report: str, ledger: str, score: str | None = None, health_check: bool = True,
          warnings: list[str] | None = None) -> dict:
    """The emitter payload for the run whose report and ledger are given."""
    try:
        front = read_frontmatter(Path(report).read_bytes().decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ContextError(f"--report {report} cannot be read: {exc}") from exc
    if not front:
        raise ContextError(f"--report {report} has no frontmatter")
    gl = _sibling("gap-ledger.py", "skf_gap_ledger")
    try:
        counts = gl.summarize(Path(ledger), gl.load_ledger(Path(ledger)))["counts"]
    except gl.LedgerError as exc:
        raise ContextError(f"--ledger {ledger}: {exc}") from exc

    skill = front.get("skillName") or None
    blocked = front.get("hardGate") == "blocked"
    if blocked:
        envelope = dict(_sibling("hard-gate.py", "skf_hard_gate").blocked_envelope(skill, report))
        result, active, inconclusive = "FAIL", [], None
    else:
        test_result = front.get("testResult", "")
        if test_result not in VERDICTS:
            raise ContextError(f"--report {report} holds no settled verdict (testResult {test_result!r})")
        verdict, result, exit_code, next_workflow = VERDICTS[test_result]
        envelope = {
            "status": "success",
            "skill_name": skill,
            "verdict": verdict,
            "score": percent(front.get("score")),
            "threshold": percent(front.get("threshold")),
            "report_path": report,
            "next_workflow": next_workflow,
            "exit_code": exit_code,
            "halt_reason": None,
        }
        scored = _read_json(score, "--score") if score else {}
        if not isinstance(scored, dict):
            raise ContextError(f"--score {score} is not a JSON object")
        active = scored.get("activeCategories", [])
        inconclusive = scored.get("inconclusiveReasons") if verdict == "INCONCLUSIVE" else None

    fallback = front.get("thresholdFallback", "").lower() == "true" and not blocked
    if fallback:
        envelope["threshold_fallback"] = True
        envelope["original_threshold"] = percent(front.get("originalThreshold"))

    summary = {
        "score": envelope["score"],
        "threshold": envelope["threshold"],
        "result": result,
        "testMode": front.get("testMode") or None,
        "activeCategories": active,
    }
    if inconclusive is not None:
        summary["inconclusiveReasons"] = inconclusive
    if fallback:
        summary["threshold_fallback"] = True
        summary["original_threshold"] = envelope["original_threshold"]
        summary["evidence_report_path"] = front.get("evidenceReportPath") or None
    summary["gapCounts"] = counts
    summary["hardGate"] = front.get("hardGate") or None

    contract = {"skill": WORKFLOW, **envelope,
                "outputs": [{"type": "report", "path": report}],
                "summary": summary,
                "runId": front.get("runId") or None,
                "healthCheckDispatched": health_check}
    payload = {**envelope, "result_contract": contract}
    kept = [w.strip() for w in warnings or [] if w and w.strip()]
    if kept:
        payload["warnings"] = kept
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build-result-context",
        description=("Build the shared emitter's payload for a finished test-skill run from its "
                     "report frontmatter, its gap ledger and the scoring output."),
    )
    parser.add_argument("--report", required=True, help="the test report, at its published name")
    parser.add_argument("--ledger", required=True, help="the run's gap ledger")
    parser.add_argument("--score", help="the scoring script's output (absent for a blocked run)")
    parser.add_argument("--no-health-check", action="store_true",
                        help="the run was given --no-health-check (healthCheckDispatched false)")
    parser.add_argument("--warning", action="append", default=[],
                        help="a warning the run kept for its result (repeatable)")
    parser.add_argument("--output", required=True, help="where to write the payload")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        payload = build(args.report, args.ledger, args.score, not args.no_health_check, args.warning)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    except (ContextError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1
    blocked = payload["halt_reason"] is not None
    print(json.dumps({
        "status": payload["status"],
        "verdict": payload["verdict"],
        "exit_code": payload["exit_code"],
        "next_workflow": payload["next_workflow"],
        "halt_reason": payload["halt_reason"],
        "target": "stderr" if blocked else "stdout",
        "output": out.as_posix(),
    }, indent=2))
    return 0


def _force_utf8(*streams) -> None:
    """Reconfigure stdout and stderr to UTF-8, keeping each stream's error handler.

    A Windows console pipes them as cp1252, which cannot print every character
    of the --help text, so --help would stop with UnicodeEncodeError.
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
