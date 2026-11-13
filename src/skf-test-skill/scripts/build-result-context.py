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
    testResult, workspaceDrift, score, threshold, thresholdFallback,
    originalThreshold and evidenceReportPath (the steps write the verdict
    inputs there, so a compacted context cannot change them), and
    analysisConfidence, which must be one of compute-score.py's
    ANALYSIS_CONFIDENCE for a scored run and a blocked one alike (score.md
    §7 writes it, or step-hard-gate.md §3 on a blocked run);
  - the gap ledger: the gap counts by severity (gap-ledger.py's summary);
  - the scoring script's output, which score.md saves: the verdict, score
    and threshold it settled, activeCategories, inconclusiveReasons and the
    capReason of a cap that fired. A run the hard gate blocked was never
    scored and has none.

A scored run's verdict fields are checked against the scoring output
(`scored_fields`): testResult must be the verdict the output settled,
`effectiveResult` when the output has one, else `result`, in lower case,
with `pass` read as `pass-with-drift` when the frontmatter workspaceDrift
is `overridden`; score its `totalScore`; threshold the one the verdict was
settled against (compute-score.py's FALLBACK_FLOOR after a threshold
fallback, else its `threshold`); and thresholdFallback and
originalThreshold its override group's. A field copied from anything else
(`result` over a cap's FAIL, a bare pass under drift, the target threshold
of a run the fallback accepted) exits 1 and writes no payload, so
report.md halts before it publishes the report or writes a result file.

The derived fields live here, in one place (nextWorkflow is the frontmatter
key `settle` writes):

  testResult       verdict          summary.result   exit_code  next_workflow  nextWorkflow
  pass             PASS             PASS             0          export-skill   export-skill
  pass-with-drift  pass-with-drift  PASS_WITH_DRIFT  4          update-skill   update-skill
  fail             FAIL             FAIL             2          update-skill   update-skill
  inconclusive     INCONCLUSIVE     INCONCLUSIVE     3          null           manual-review

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
                 "capReason" (a cap fired: a non-empty string),
                 "threshold_fallback", "original_threshold",
                 "evidence_report_path" (fallback only), "gapCounts",
                 "hardGate"},
     "runId": <runId>, "healthCheckDispatched": <bool>}}

CLI:
  uv run build-result-context.py --report <report.md> [--report-path <path>]
      --ledger <ledger.json> [--score <scoring output>] [--no-health-check]
      [--warning <text>]... --output <result-context.json>

--score is required unless the frontmatter says the hard gate blocked the
run. --report-path is the path the payload names the report by (default:
--report): report.md builds the payload from the report before it gives
the report its public name, and passes that name here.

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
     settled verdict, an analysisConfidence that names no source access or
     a verdict field the scoring output does not settle, or --output cannot
     be written ({"status": "error", "error"} on stdout)
  2  a usage error: no --score for a run the hard gate did not block (the
     same JSON on stdout), or a flag argparse refuses (its usage on stderr)

Subcommand settle (score.md §6), so the model types no verdict field:
  uv run build-result-context.py settle --report <report.md>
      --score <scoring output> --external <external.json>
      [--evidence-report <path>]

writes the verdict fields `scored_fields` settles into the report
frontmatter, each key replaced where it stands or added before the closing
`---`, every other byte (line endings and a byte order mark included)
kept: testResult, score and threshold (`'{n}%'`, a whole number without
its `.0`), nextWorkflow (the table above) and, only after a threshold
fallback, thresholdFallback: true, originalThreshold and
evidenceReportPath (--evidence-report); without one it removes those
three. It writes neither stepsCompleted nor analysisConfidence. Then it
prints the Completeness Score section on stdout:
  ### Score Breakdown  one row per compute-score.py CATEGORIES entry: the
                       score the weight applied to (state2Deduction's
                       exportCoverage when present, else input.scores; N/A
                       for a skippedCategories entry), the weight and the
                       weighted score, then the Total row
  ### Result           Score, Threshold, Result (summary.result), Cap (a
                       cap fired), Inconclusive Reasons (INCONCLUSIVE),
                       then Threshold Source (frontmatter), Threshold
                       Fallback (a fallback), Weight Distribution
                       (`{mode} (full)`, or `(redistributed)` when a
                       category was skipped), Tier Adjustment, External
                       Validators (--external `toolsUsed`), Analysis
                       Confidence and Tooling Status (frontmatter), and
                       Scoring Notes (scoringNotes, and the drift note on a
                       pass-with-drift) when there is one
Exit 0 when it wrote and printed; 1 (one `error:` line on stderr, the
report untouched) when an input is missing, unreadable or not its script's
result (--score an INVALID_INPUT envelope or without input, weights and
weightedScores; --external without a toolsUsed list), the report has no
frontmatter or the hard gate blocked it, or the write fails; 2 a usage
error, a threshold fallback without --evidence-report included.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
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
# testResult -> the report frontmatter's nextWorkflow, which settle writes
NEXT_WORKFLOW = {"pass": "export-skill", "pass-with-drift": "update-skill", "fail": "update-skill",
                 "inconclusive": "manual-review"}
# The keys settle writes only after a threshold fallback, and removes otherwise.
FALLBACK_KEYS = ("thresholdFallback", "originalThreshold", "evidenceReportPath")
# compute-score.py CATEGORIES -> the Score Breakdown row label
CATEGORY_LABELS = {"exportCoverage": "Export Coverage", "signatureAccuracy": "Signature Accuracy",
                   "typeCoverage": "Type Coverage", "coherence": "Coherence",
                   "externalValidation": "External Validation"}
# combine-external-scores.py toolsUsed -> the External Validators line
EXTERNAL_VALIDATORS = {
    frozenset({"skill-check", "tessl"}): "skill-check and Tessl Review",
    frozenset({"skill-check"}): "skill-check only",
    frozenset({"tessl"}): "Tessl Review only",
    frozenset(): "none: weight redistributed",
}
DRIFT_NOTE = "workspace drift overridden: the PASS is conditional; re-run against the pinned commit before export"
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$")


class ContextError(Exception):
    """An input the payload cannot be built from: exit 1."""


class UsageError(ContextError):
    """A command the caller can correct and run again: exit 2."""


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
    """Top-level scalar keys of the leading `---` block, quotes removed (a single-quoted one's `''` read as `'`).

    >>> read_frontmatter("---\\ntestResult: 'pass'\\nscore: 91.5%\\nsteps: ['a']\\n---\\n# R")
    {'testResult': 'pass', 'score': '91.5%', 'steps': "['a']"}
    >>> read_frontmatter("---\\nevidenceReportPath: '/home/o''neil/e.md'\\n---\\n")
    {'evidenceReportPath': "/home/o'neil/e.md"}
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
            value = value[1:-1].replace("''", "'") if value[0] == "'" else value[1:-1]
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


def _fallback_floor() -> int:
    """The threshold a fallback accepts a run at: compute-score.py's, which applies the fallback."""
    return _sibling("compute-score.py", "skf_compute_score_floor").FALLBACK_FLOOR


def _analysis_confidence() -> tuple[str, ...]:
    """The source access levels a report may record: compute-score.py's, which scores by them."""
    return tuple(_sibling("compute-score.py", "skf_compute_score_confidence").ANALYSIS_CONFIDENCE)


def settled_test_result(scored: dict, workspace_drift: str | None) -> str | None:
    """The testResult the scoring output settles, or None when it holds no verdict.

    >>> settled_test_result({"result": "PASS"}, "ok")
    'pass'
    >>> settled_test_result({"result": "PASS", "effectiveResult": "FAIL", "capReason": "Cap 1"}, "ok")
    'fail'
    >>> settled_test_result({"result": "FAIL", "effectiveResult": "PASS"}, "overridden")
    'pass-with-drift'
    >>> settled_test_result({"result": "INCONCLUSIVE"}, "overridden")
    'inconclusive'
    >>> settled_test_result({"error": "bad flag", "code": "INVALID_INPUT"}, "ok") is None
    True
    """
    verdict = scored.get("effectiveResult") or scored.get("result")
    settled = verdict.lower() if isinstance(verdict, str) else None
    if settled not in ("pass", "fail", "inconclusive"):
        return None
    return "pass-with-drift" if settled == "pass" and workspace_drift == "overridden" else settled


def scored_fields(scored: dict, workspace_drift: str | None) -> dict | None:
    """The frontmatter verdict fields the scoring output settles, or None when it holds no verdict.

    >>> scored_fields({"result": "PASS", "totalScore": 91.5, "threshold": 80}, "ok")
    {'testResult': 'pass', 'score': 91.5, 'threshold': 80, 'thresholdFallback': False, 'originalThreshold': None}
    >>> fell_back = {"result": "FAIL", "effectiveResult": "PASS", "capReason": None, "thresholdFallback": True,
    ...              "originalThreshold": 90, "totalScore": 85, "threshold": 90}
    >>> scored_fields(fell_back, "ok")
    {'testResult': 'pass', 'score': 85, 'threshold': 80, 'thresholdFallback': True, 'originalThreshold': 90}
    """
    test_result = settled_test_result(scored, workspace_drift)
    if test_result is None:
        return None
    fallback = scored.get("thresholdFallback") is True
    return {
        "testResult": test_result,
        "score": scored.get("totalScore"),
        "threshold": _fallback_floor() if fallback else scored.get("threshold"),
        "thresholdFallback": fallback,
        "originalThreshold": scored.get("originalThreshold") if fallback else None,
    }


def build(report: str, ledger: str, score: str | None = None, health_check: bool = True,
          warnings: list[str] | None = None, report_path: str | None = None) -> dict:
    """The emitter payload for the run whose report and ledger are given; `report_path`
    (default `report`) is the path the payload names the report by."""
    report_path = report_path or report
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

    # Every run records its source access, a blocked one included (step-hard-gate.md §3): a report missing it
    # halts here, before report.md publishes it.
    confidence = front.get("analysisConfidence")
    levels = _analysis_confidence()
    if confidence not in levels:
        raise ContextError(f"--report {report} records no source access (analysisConfidence {confidence!r}, "
                           f"not one of: {', '.join(levels)})")

    skill = front.get("skillName") or None
    blocked = front.get("hardGate") == "blocked"
    if blocked:
        envelope = dict(_sibling("hard-gate.py", "skf_hard_gate").blocked_envelope(skill, report_path))
        result, active, inconclusive, cap = "FAIL", [], None, None
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
            "report_path": report_path,
            "next_workflow": next_workflow,
            "exit_code": exit_code,
            "halt_reason": None,
        }
        if not score:
            raise UsageError("--score is required for a run the hard gate did not block: its verdict "
                             "fields are checked against the scoring output")
        scored = _read_json(score, "--score")
        if not isinstance(scored, dict):
            raise ContextError(f"--score {score} is not a JSON object")
        settled = scored_fields(scored, front.get("workspaceDrift"))
        if settled is None:
            raise ContextError(f"--score {score} holds no verdict (no effectiveResult or result)")
        fell_back = front.get("thresholdFallback", "").lower() == "true"
        written = {"testResult": test_result, "score": envelope["score"], "threshold": envelope["threshold"],
                   "thresholdFallback": fell_back,
                   "originalThreshold": percent(front.get("originalThreshold")) if fell_back else None}
        wrong = [f"{key} {written[key]!r} where it settles {settled[key]!r}"
                 for key in settled if written[key] != settled[key]]
        if wrong:
            raise ContextError(f"--report {report} disagrees with the scoring output {score}: "
                               + "; ".join(wrong))
        active = scored.get("activeCategories", [])
        inconclusive = scored.get("inconclusiveReasons") if verdict == "INCONCLUSIVE" else None
        # The cap that fired, which no skill edit lifts: a caller restores the tooling it names, then tests again.
        cap = scored.get("capReason") if isinstance(scored.get("capReason"), str) else None

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
    if cap and cap.strip():
        summary["capReason"] = cap
    if fallback:
        summary["threshold_fallback"] = True
        summary["original_threshold"] = envelope["original_threshold"]
        summary["evidence_report_path"] = front.get("evidenceReportPath") or None
    summary["gapCounts"] = counts
    summary["hardGate"] = front.get("hardGate") or None

    contract = {"skill": WORKFLOW, **envelope,
                "outputs": [{"type": "report", "path": report_path}],
                "summary": summary,
                "runId": front.get("runId") or None,
                "healthCheckDispatched": health_check}
    payload = {**envelope, "result_contract": contract}
    kept = [w.strip() for w in warnings or [] if w and w.strip()]
    if kept:
        payload["warnings"] = kept
    return payload


# --------------------------------------------------------------------------
# settle: the verdict fields and the Completeness Score section (score.md §6)
# --------------------------------------------------------------------------


def pct(value) -> str:
    """A score as the report writes it, reconcile-coverage.py `_pct`'s form.

    >>> pct(87.37), pct(80), pct(85.0), pct(None)
    ('87.37%', '80%', '85%', 'N/A')
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "N/A"
    return f"{int(value)}%" if float(value).is_integer() else f"{value}%"


def write_frontmatter(text: str, values: dict[str, str], remove: tuple[str, ...] = ()) -> str:
    """`text` with each key of `values` set (replaced where it stands, else added before the closing `---`) and each
    key of `remove` dropped; every other byte, line endings and a byte order mark included, is kept.

    >>> write_frontmatter("---\\r\\nscore: ''\\r\\nold: 1\\r\\n---\\r\\n# R\\r\\n", {"score": "'91.5%'", "add": "true"},
    ...                   remove=("old",))
    "---\\r\\nscore: '91.5%'\\r\\nadd: true\\r\\n---\\r\\n# R\\r\\n"
    """
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    lines = text[len(bom):].splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ContextError("has no frontmatter")
    close = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if close is None:
        raise ContextError("has no frontmatter (no closing ---)")
    eol = lines[0][len(lines[0].rstrip("\r\n")):] or "\n"
    head, body = lines[1:close], lines[close:]
    kept, placed = [], set()
    for line in head:
        m = _KEY_RE.match(line.rstrip("\r\n"))
        key = m.group(1) if m else None
        if key in remove:
            continue
        if key in values:
            ending = line[len(line.rstrip("\r\n")):] or eol
            kept.append(f"{key}: {values[key]}{ending}")
            placed.add(key)
            continue
        kept.append(line)
    kept += [f"{key}: {value}{eol}" for key, value in values.items() if key not in placed]
    return bom + lines[0] + "".join(kept) + "".join(body)


def _scoring_output(path: str) -> dict:
    scored = _read_json(path, "--score")
    if not isinstance(scored, dict) or scored.get("code") == "INVALID_INPUT" or "error" in scored:
        raise ContextError(f"--score {path} is compute-score.py's refusal, not a score: correct the input and run "
                           "it again (score.md §3c)")
    shapes = {"input": dict, "weights": dict, "weightedScores": dict}
    wrong = [key for key, kind in shapes.items() if not isinstance(scored.get(key), kind)]
    if wrong:
        raise ContextError(f"--score {path} is not compute-score.py's output: no {', '.join(wrong)}")
    if not isinstance(scored.get("totalScore"), (int, float)) or isinstance(scored.get("totalScore"), bool):
        raise ContextError(f"--score {path} is not compute-score.py's output: no numeric totalScore")
    return scored


def _tools_used(path: str) -> str:
    external = _read_json(path, "--external")
    tools = external.get("toolsUsed") if isinstance(external, dict) else None
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise ContextError(f"--external {path} is not combine-external-scores.py's result: no toolsUsed list")
    label = EXTERNAL_VALIDATORS.get(frozenset(tools))
    if label is None:
        raise ContextError(f"--external {path} names a tool combine-external-scores.py never uses: {tools}")
    return label


def settle(report: str, score: str, external: str, evidence_report: str | None = None) -> tuple[str, str]:
    """(the report text with its verdict fields written, the Completeness Score section). Raises ContextError
    (exit 1) or UsageError (exit 2); writes nothing."""
    try:
        raw = Path(report).read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ContextError(f"--report {report} cannot be read: {exc}") from exc
    front = read_frontmatter(text)
    if not front:
        raise ContextError(f"--report {report} has no frontmatter")
    if front.get("hardGate") == "blocked":
        raise ContextError(f"--report {report} records a run the hard gate blocked: it has no score to settle "
                           "(step-hard-gate.md writes its Completeness Score section)")
    scored = _scoring_output(score)
    validators = _tools_used(external)
    fields = scored_fields(scored, front.get("workspaceDrift"))
    if fields is None:
        raise ContextError(f"--score {score} holds no verdict (no effectiveResult or result)")
    fell_back = fields["thresholdFallback"]
    if fell_back and not evidence_report:
        raise UsageError("the threshold fallback fired: pass --evidence-report with the evidence report's path")
    test_result = fields["testResult"]
    values = {"testResult": f"'{test_result}'", "score": f"'{pct(fields['score'])}'",
              "threshold": f"'{pct(fields['threshold'])}'", "nextWorkflow": f"'{NEXT_WORKFLOW[test_result]}'"}
    if fell_back:
        values |= {"thresholdFallback": "true", "originalThreshold": f"'{pct(fields['originalThreshold'])}'",
                   "evidenceReportPath": "'" + evidence_report.replace("'", "''") + "'"}
    try:
        written = write_frontmatter(text, values, remove=() if fell_back else FALLBACK_KEYS)
    except ContextError as exc:
        raise ContextError(f"--report {report} {exc}") from exc
    return written, completeness_section(scored, fields, front, validators, evidence_report)


def completeness_section(scored: dict, fields: dict, front: dict[str, str], validators: str,
                         evidence_report: str | None) -> str:
    """The Completeness Score section score.md §6 writes, from the scoring output, the settled fields, the report
    frontmatter and the External Validators label."""
    inputs = scored["input"]
    given = inputs.get("scores") if isinstance(inputs.get("scores"), dict) else {}
    deduction = scored.get("state2Deduction") if isinstance(scored.get("state2Deduction"), dict) else {}
    skipped = scored.get("skippedCategories") if isinstance(scored.get("skippedCategories"), list) else []
    categories = _sibling("compute-score.py", "skf_compute_score_categories").CATEGORIES
    lines = ["## Completeness Score", "", "### Score Breakdown", "",
             "| Category | Score | Weight | Weighted |", "|----------|-------|--------|----------|"]
    for cat in categories:
        if cat in skipped:
            value = None
        elif cat == "exportCoverage" and "exportCoverage" in deduction:
            value = deduction["exportCoverage"]
        else:
            value = given.get(cat)
        lines.append(f"| {CATEGORY_LABELS.get(cat, cat)} | {pct(value)} | {pct(scored['weights'].get(cat))} "
                     f"| {pct(scored['weightedScores'].get(cat))} |")
    total = pct(scored["totalScore"])
    lines += [f"| **Total** | | **100%** | **{total}** |", "", "### Result", "",
              f"**Score:** {total}", f"**Threshold:** {pct(fields['threshold'])}",
              f"**Result:** **{VERDICTS[fields['testResult']][1]}**"]
    cap = scored.get("capReason")
    if isinstance(cap, str) and cap.strip():
        lines.append(f"**Cap:** {cap}")
    if fields["testResult"] == "inconclusive":
        reasons = scored.get("inconclusiveReasons") if isinstance(scored.get("inconclusiveReasons"), list) else []
        lines.append("**Inconclusive Reasons:**")
        lines += [f"- {reason}" for reason in reasons]
    lines += ["", f"**Threshold Source:** {front.get('thresholdSource', '')}"]
    if fields["thresholdFallback"]:
        lines.append(f"**Threshold Fallback:** scored {total} against {pct(fields['originalThreshold'])} target: "
                     f"accepted at {pct(fields['threshold'])} floor. Evidence report: {evidence_report}")
    mode = inputs.get("mode")
    lines += [f"**Weight Distribution:** {mode} ({'redistributed' if skipped else 'full'})",
              "**Tier Adjustment:** " + ("Quick tier: signature and type coverage not scored"
                                         if inputs.get("tier") == "Quick" else "none"),
              f"**External Validators:** {validators}",
              f"**Analysis Confidence:** {front.get('analysisConfidence', '')}",
              f"**Tooling Status:** {front.get('toolingStatus', '')}"]
    notes = [n for n in scored.get("scoringNotes") or [] if isinstance(n, str) and n.strip()]
    if fields["testResult"] == "pass-with-drift":
        notes.append(DRIFT_NOTE)
    if notes:
        lines.append(f"**Scoring Notes:** {'; '.join(notes)}")
    return "\n".join(lines) + "\n"


def _write_atomic(path: Path, data: bytes) -> None:
    """Write `data` over `path` through a temp file beside it, so a failed write leaves the report as it was."""
    tmp = path.with_name(f".{path.name}.settle-{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _settle_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="build-result-context settle",
        description=("Write the verdict fields the scoring output settles into the report frontmatter and print "
                     "the Completeness Score section (score.md §6)."),
    )
    parser.add_argument("--report", required=True, help="the test report whose frontmatter takes the verdict")
    parser.add_argument("--score", required=True, help="compute-score.py's output (score.json)")
    parser.add_argument("--external", required=True, help="combine-external-scores.py's result (external.json)")
    parser.add_argument("--evidence-report",
                        help="the evidence report's path, written as evidenceReportPath after a threshold fallback")
    args = parser.parse_args(argv)
    try:
        written, section = settle(args.report, args.score, args.external, args.evidence_report)
        # The report keeps its own line endings, so it is written back as bytes.
        _write_atomic(Path(args.report), written.encode("utf-8"))
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ContextError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(section)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build-result-context",
        description=("Build the shared emitter's payload for a finished test-skill run from its "
                     "report frontmatter, its gap ledger and the scoring output."),
    )
    parser.add_argument("--report", required=True, help="the test report to read")
    parser.add_argument("--report-path",
                        help="the path the payload names the report by: its public name (default: --report)")
    parser.add_argument("--ledger", required=True, help="the run's gap ledger")
    parser.add_argument("--score", help="the scoring script's output (required unless the hard gate blocked "
                                        "the run)")
    parser.add_argument("--no-health-check", action="store_true",
                        help="the run was given --no-health-check (healthCheckDispatched false)")
    parser.add_argument("--warning", action="append", default=[],
                        help="a warning the run kept for its result (repeatable)")
    parser.add_argument("--output", required=True, help="where to write the payload")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["settle"]:
        return _settle_main(argv[1:])
    args = _build_parser().parse_args(argv)
    try:
        payload = build(args.report, args.ledger, args.score, not args.no_health_check, args.warning,
                        args.report_path)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    except (ContextError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2 if isinstance(exc, UsageError) else 1
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
