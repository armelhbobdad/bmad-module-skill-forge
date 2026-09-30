#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deterministic circuit-breaker decision for one finished pipeline step.

Pipeline Mode (references/pipeline-mode.md step 4d) runs this after AN, TS, AS
or VS finishes, instead of reading the step's result and comparing it by
hand. Which field carries the verdict, and which verdicts go on, skip or stop,
has one correct answer per result, so it runs here, not in the prompt. The
gate never compares a TS score with a threshold: the forger hands a `[min:N]`
to TS as `--threshold=N`, and TS settles its own verdict, caps and 80% floor
fallback included.

The rules mirror the Circuit Breakers table in
`src/shared/references/pipeline-contracts.md`:

  TS  continue only on the settled verdict PASS, which TS routes to export
      (`next_workflow` is `export-skill`). FAIL, INCONCLUSIVE and
      pass-with-drift halt with the verdict as the reason; so does a FAIL
      that a post-score cap forced while the score clears the threshold.
  AN  continue when it confirmed at least `--min` skillable units (default 1).
      A redirect or a skipped target halts: there is no brief to go on with.
  AS  CRITICAL drift halts; CLEAN skips an update that comes next
      (`--next US`); MINOR and SIGNIFICANT continue.
  VS  zero coverage halts (`zero-coverage`): VS verified none of the
      architecture's technologies, so nothing after it has evidence to use.
      Every verdict with coverage continues, NOT_FEASIBLE included: RA, which
      usually follows VS, takes each Blocked integration as a critical issue.

A result with `status` `error` or `failed` halts with its `halt_reason`, or
its status when it names none, a TS PASS included. A TS result with any other
verdict keeps the verdict as the reason, so a hard-gate block halts as FAIL. A
result the gate cannot read, or a value outside its rule's set, halts too: a
gate that cannot decide never lets a step through.

Input, on stdin (or in the file `--result` names, for tests and CI): the
step's result envelope line (`SKF_TEST_RESULT_JSON: {...}` and the like; the
last line of the code's own envelope wins, and one from another workflow is
refused) or a result record. Pipeline Mode gates only the envelope line the
step just printed, and an empty input when it printed none (`no-result`):
a `-latest.json` record may not describe this run, because a workflow can
halt after writing it (TS writes its record before its last halts) or abort
before writing one. The envelope and the record name the fields differently,
and both are read:

  TS  verdict `verdict` | `summary.result` (PASS_WITH_DRIFT reads as
      pass-with-drift), route `next_workflow` (checked when present)
  AN  units `unit_counts.confirmed`, else the `brief_paths`, else the
      `skill-brief.yaml` paths in `outputs[]`
  AS  severity `drift_score` | `summary.severity`
  VS  verdict `overall_verdict` | `summary.overallVerdict`, coverage
      `coverage_percentage` | `summary.coveragePercentage`

The input is read as UTF-8 and a byte-order mark is dropped; input that is
not UTF-8 halts as `result-unreadable`.

CLI usage:
  uv run scripts/pipeline-gate.py --code TS --next EX <<'SKF_RESULT'
  SKF_TEST_RESULT_JSON: {"status":"success","verdict":"FAIL",...}
  SKF_RESULT
  uv run scripts/pipeline-gate.py --code AN --min 2 <<'SKF_RESULT'
  SKF_RESULT
  uv run scripts/pipeline-gate.py --code AS --next US --result <saved-envelope.txt>

  (The AN call has an empty heredoc: the step printed no envelope, so the
  gate halts with `no-result`.)

Output (stdout, one object):
  {
    "code": "TS",
    "decision": "continue" | "skip" | "halt",
    "reason": null | "<why it skips or halts>",  # TS: FAIL, INCONCLUSIVE, pass-with-drift
    "skip": null | "US",                         # the next workflow a skip passes over
    "message": "<one line for the pipeline report>"
  }

Exit codes:
  0  a decision was printed (continue, skip or halt: read `decision`)
  2  usage error (argparse: a missing or unknown argument, usage on stderr,
     no JSON)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# The envelope each gated workflow prints in headless mode.
ENVELOPES = {
    "AN": "SKF_ANALYZE_RESULT_JSON",
    "TS": "SKF_TEST_RESULT_JSON",
    "AS": "SKF_AUDIT_RESULT_JSON",
    "VS": "SKF_VERIFY_STACK_RESULT_JSON",
}
GATED_CODES = tuple(ENVELOPES)

# Settled test-skill verdicts, keyed by their normalized spelling; the value
# is the envelope's spelling, which a halt reports as its reason.
TS_VERDICTS = {
    "PASS": "PASS",
    "FAIL": "FAIL",
    "INCONCLUSIVE": "INCONCLUSIVE",
    "PASS_WITH_DRIFT": "pass-with-drift",
}
AS_SEVERITIES = ("CLEAN", "MINOR", "SIGNIFICANT", "CRITICAL")
VS_VERDICTS = ("FEASIBLE", "CONDITIONALLY_FEASIBLE", "NOT_FEASIBLE")
ERROR_STATUSES = frozenset({"error", "failed"})
EXPORT_ROUTE = "export-skill"

_ENVELOPE_RE = re.compile(r"(SKF_[A-Z0-9_]+_RESULT_JSON):\s*(\{.*\})\s*$")
_MISSING = object()


# --------------------------------------------------------------------------
# Reading the result
# --------------------------------------------------------------------------


def read_result(code: str, text: str | None) -> tuple[dict | None, str | None]:
    """Return (result, problem) for the text a step produced.

    The last envelope line of `code`'s own workflow wins. Envelope lines of
    other workflows alone are refused (`wrong-result`); with no envelope line
    at all, the whole text must be one JSON object (a result record).
    """
    if text is None:
        return None, "result-unreadable"
    if not text.strip():
        return None, "no-result"
    found = [m for m in map(_ENVELOPE_RE.search, text.splitlines()) if m]
    own = [m.group(2) for m in found if m.group(1) == ENVELOPES[code]]
    if found and not own:
        return None, "wrong-result"
    try:
        value = json.loads(own[-1] if own else text)
    except json.JSONDecodeError:
        return None, "result-unreadable"
    if not isinstance(value, dict):
        return None, "result-unreadable"
    return value, None


def _field(result: dict, key: str, summary_key: str):
    """The envelope's `key`, else the record's `summary.<summary_key>`."""
    value = result.get(key)
    if value is None:
        summary = result.get("summary")
        if isinstance(summary, dict):
            value = summary.get(summary_key)
    return value


def _token(value) -> str | None:
    """A verdict or severity as one upper-case token: `pass-with-drift` -> PASS_WITH_DRIFT."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper().replace("-", "_")


def _is_error(result: dict) -> bool:
    status = result.get("status")
    return isinstance(status, str) and status.strip().lower() in ERROR_STATUSES


def _halt_reason(result: dict) -> str:
    """The reason an errored result names, or its status."""
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    for value in (result.get("halt_reason"), summary.get("halt_reason")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(result.get("status")).strip().lower()


def _count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _percentage(value) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if 0 <= value <= 100 else None


def _units(result: dict) -> int | None:
    """Confirmed skillable units: the envelope count, else the briefs listed."""
    counts = result.get("unit_counts")
    if isinstance(counts, dict) and _count(counts.get("confirmed")) is not None:
        return counts["confirmed"]
    briefs = result.get("brief_paths")
    if isinstance(briefs, list):
        return len(briefs)
    outputs = result.get("outputs")
    if isinstance(outputs, list):
        paths = [o.get("path") if isinstance(o, dict) else o for o in outputs]
        return sum(isinstance(p, str) and p.endswith("skill-brief.yaml") for p in paths)
    return None


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------


def _decision(code, decision, reason=None, message="", skip=None):
    return {"code": code, "decision": decision, "reason": reason, "skip": skip, "message": message}


def _halt(code, reason, message):
    return _decision(code, "halt", reason, message)


def _go(code, message):
    return _decision(code, "continue", message=message)


def _off_the_rule(code, what, raw, allowed):
    """Halt on a missing value, or one outside the rule's set."""
    if raw is None:
        return _halt(code, f"no-{what}", f"{code} reported no {what}.")
    return _halt(code, f"unknown-{what}", f"{code} reported the {what} {raw!r}, which is not {allowed}.")


def _gate_ts(result: dict) -> dict:
    raw = _field(result, "verdict", "result")
    verdict = TS_VERDICTS.get(_token(raw) or "")
    if verdict is None:
        if raw is None and _is_error(result):
            reason = _halt_reason(result)
            return _halt("TS", reason, f"TS halted before a verdict ({reason}).")
        return _off_the_rule("TS", "verdict", raw, "PASS, FAIL, INCONCLUSIVE or pass-with-drift")
    if verdict != "PASS":
        detail = f" ({_halt_reason(result)})" if _is_error(result) else ""
        return _halt("TS", verdict, f"TS verdict {verdict}{detail}: the skill is not exported.")
    if _is_error(result):
        reason = _halt_reason(result)
        return _halt("TS", reason, f"TS reported PASS but ended in an error ({reason}): the skill is not exported.")
    route = result.get("next_workflow", _MISSING)
    if route not in (_MISSING, EXPORT_ROUTE):
        message = f"TS verdict PASS, but next_workflow is {route!r}, not {EXPORT_ROUTE!r}."
        return _halt("TS", "not-routed-to-export", message)
    return _go("TS", "TS verdict PASS: the skill goes on to export.")


def _gate_an(result: dict, minimum: int) -> dict:
    if _is_error(result):
        reason = _halt_reason(result)
        return _halt("AN", reason, f"AN halted ({reason}).")
    status = str(result.get("status", "")).strip().lower()
    if status == "redirect":
        name = result.get("skill_name") or "the existing skill"
        return _halt("AN", "redirect", f"AN routed the target to an update of {name}: run US {name}.")
    if status == "skipped":
        why = result.get("skipped_reason") or "AN skipped the target"
        return _halt("AN", "skipped", f"{why}: there is no brief to go on with.")
    units = _units(result)
    if units is None:
        return _halt("AN", "units-unknown", "AN reported no unit count and no brief paths.")
    if units < minimum:
        reason = "no-skillable-units" if units == 0 else "units-below-min"
        message = f"AN confirmed {units} skillable unit(s); the pipeline needs at least {minimum}."
        return _halt("AN", reason, message)
    return _go("AN", f"AN confirmed {units} skillable unit(s).")


def _gate_as(result: dict, next_code: str | None) -> dict:
    if _is_error(result):
        reason = _halt_reason(result)
        return _halt("AS", reason, f"AS halted ({reason}).")
    raw = _field(result, "drift_score", "severity")
    severity = _token(raw)
    if severity not in AS_SEVERITIES:
        return _off_the_rule("AS", "severity", raw, "CLEAN, MINOR, SIGNIFICANT or CRITICAL")
    if severity == "CRITICAL":
        message = "AS found CRITICAL drift: review the drift report, then run US on the skill."
        return _halt("AS", "CRITICAL", message)
    if severity == "CLEAN" and next_code == "US":
        return _decision("AS", "skip", "CLEAN", "No drift detected: skipping update.", skip="US")
    return _go("AS", f"AS drift severity {severity}.")


def _gate_vs(result: dict) -> dict:
    if _is_error(result):
        reason = _halt_reason(result)
        return _halt("VS", reason, f"VS halted ({reason}).")
    raw = _field(result, "overall_verdict", "overallVerdict")
    verdict = _token(raw)
    if verdict not in VS_VERDICTS:
        return _off_the_rule("VS", "verdict", raw, "FEASIBLE, CONDITIONALLY_FEASIBLE or NOT_FEASIBLE")
    raw_coverage = _field(result, "coverage_percentage", "coveragePercentage")
    coverage = _percentage(raw_coverage)
    if coverage is None:
        return _off_the_rule("VS", "coverage", raw_coverage, "a percentage from 0 to 100")
    if coverage == 0:
        message = ("VS covered none of the architecture's technologies (coverage 0%), so it "
                   "verified nothing to go on with: create their skills, then re-run VS.")
        return _halt("VS", "zero-coverage", message)
    return _go("VS", f"VS verdict {verdict} at {coverage}% coverage.")


_UNREADABLE = {
    "no-result": "{code} left no result envelope to read.",
    "result-unreadable": "The result given for {code} is not one JSON object, or it cannot be read as UTF-8.",
    "wrong-result": "The result given for {code} is another workflow's envelope.",
}


def gate(code: str, text: str | None, *, next_code: str | None = None, minimum: int = 1) -> dict:
    """Decide continue, skip or halt for `code` from the text its step produced."""
    code = code.upper()
    result, problem = read_result(code, text)
    if problem:
        return _halt(code, problem, _UNREADABLE[problem].format(code=code))
    if code == "TS":
        return _gate_ts(result)
    if code == "AN":
        return _gate_an(result, minimum)
    if code == "AS":
        return _gate_as(result, next_code.upper() if next_code else None)
    return _gate_vs(result)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline-gate",
        description=(
            "Circuit-breaker decision for one finished pipeline step "
            "(pipeline-mode.md step 4d): read the step's result envelope line "
            "or result record and print continue, skip or halt with a reason."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--code",
        required=True,
        type=str.upper,
        choices=GATED_CODES,
        help="The code of the step that finished.",
    )
    parser.add_argument(
        "--next",
        type=str.upper,
        help="The code of the next workflow in the plan, if any (a CLEAN AS skips a next US).",
    )
    parser.add_argument(
        "--min",
        type=int,
        default=1,
        help="The fewest units AN must confirm (AN's [min:N]; default 1). Read for AN only.",
    )
    parser.add_argument(
        "--result",
        help=(
            "A file holding the envelope line or a result record, for tests and CI "
            "(stdin when omitted or '-'). Pipeline Mode gates the envelope line the "
            "step just printed: a -latest.json record may be an earlier run's."
        ),
    )
    return parser


def _force_utf8(stream) -> None:
    """Reconfigure the JSON output to UTF-8 (a Windows console uses cp1252)."""
    if hasattr(stream, "reconfigure"):
        errors = getattr(stream, "errors", None)
        if errors is None:
            stream.reconfigure(encoding="utf-8")
        else:
            stream.reconfigure(encoding="utf-8", errors=errors)


def _read_input(path: str | None) -> str | None:
    """The text to gate, or None when it cannot be read as UTF-8.

    A byte-order mark is dropped: a Windows editor or shell may write one.
    """
    try:
        if path in (None, "-"):
            if hasattr(sys.stdin, "reconfigure"):
                sys.stdin.reconfigure(encoding="utf-8-sig", errors="strict")
            return sys.stdin.read()
        return Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdout)
    args = _build_parser().parse_args(argv)
    decision = gate(args.code, _read_input(args.result), next_code=args.next, minimum=args.min)
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
