#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""SKF test-skill hard gate: block on any Critical or High gap in the ledger.

step-hard-gate.md stops a run before scoring when coverage or coherence found
a Critical or High gap. It used to look for `**Severity:**` lines under
`### GAP-{NNN}` headings that no stage before it writes, so the gate never
fired. This script reads the gap ledger that the stages append to
(gap-ledger.py, `{forge_version}/test-findings-{run_id}.json`) and counts the
blocking records there, so the verdict comes from the same records the Gap
Report is rendered from.

Subcommand:

  check --ledger <path> --skill-name <name> --report-path <path>
        [--require-stage <stage> ...]

    Output (stdout):
      {
        "status": "ok",
        "gate": "blocked" | "passed",
        "ledger": "<path>",
        "stages": [...],                 # the stages that appended
        "counts": {"Critical": n, "High": n, "Medium": n, "Low": n, "Info": n},
        "blocking_count": n,             # Critical + High
        "non_blocking_count": n,         # Medium + Low + Info
        "blocking": [                    # Critical first, then by id
          {"id", "severity", "category", "title", "source", "remediation"}
        ],
        "envelope": {...} | null         # headless payload, null when passed
      }

    The envelope is the payload of the headless `SKF_TEST_RESULT_JSON` line
    for a blocked run. The run keeps status error, verdict FAIL and exit 2:

      {"status": "error", "skill_name": "<name>", "verdict": "FAIL",
       "score": null, "threshold": null, "report_path": "<path>",
       "next_workflow": "update-skill", "exit_code": 2,
       "halt_reason": "hard-gate-blocked"}

    --require-stage names a stage that must have appended to the ledger,
    with or without records. When one has not, the gate refuses to decide
    (code STAGE_NOT_RECORDED): a stage that never wrote its findings would
    otherwise pass the gate with nothing to block on.

Exit codes:
  0  the gate decided (blocked or passed; read `gate`)
  1  the ledger is missing or invalid, or a required stage is not recorded
  2  usage error (argparse: a missing or unknown argument, usage on stderr,
     no JSON). The exit 2 in the envelope is the blocked run's, not this.

Errors print {"status": "error", "code", "error", ...} on stdout, with the
codes LEDGER_MISSING, LEDGER_INVALID, STAGE_NOT_RECORDED and HELPER_MISSING.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HALT_REASON = "hard-gate-blocked"
BLOCKED_EXIT_CODE = 2
NEXT_WORKFLOW = "update-skill"


def _load_gap_ledger():
    """Import gap-ledger.py from this folder: the ledger format lives there.

    There is no fallback: a gate that cannot read the ledger must not pass.
    """
    sibling = Path(__file__).resolve().parent / "gap-ledger.py"
    spec = importlib.util.spec_from_file_location("skf_gap_ledger", sibling)
    if spec is None or spec.loader is None or not sibling.is_file():
        raise ImportError(f"gap-ledger.py not found beside {Path(__file__).name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blocked_envelope(skill_name: str, report_path: str) -> dict:
    """The headless result payload for a run the gate blocks."""
    return {
        "status": "error",
        "skill_name": skill_name,
        "verdict": "FAIL",
        "score": None,
        "threshold": None,
        "report_path": report_path,
        "next_workflow": NEXT_WORKFLOW,
        "exit_code": BLOCKED_EXIT_CODE,
        "halt_reason": HALT_REASON,
    }


def evaluate(gl, ledger: dict, *, skill_name: str, report_path: str, ledger_path: str) -> dict:
    """Decide the gate from a loaded ledger. `gl` is the gap-ledger module."""
    records = gl.ordered(ledger["records"])
    counts = gl.count_by_severity(records)
    blocking = [r for r in records if r["severity"] in gl.BLOCKING]
    gate = "blocked" if blocking else "passed"
    return {
        "status": "ok",
        "gate": gate,
        "ledger": ledger_path,
        "stages": list(ledger["stages"]),
        "counts": counts,
        "blocking_count": len(blocking),
        "non_blocking_count": len(records) - len(blocking),
        "blocking": [
            {key: r[key] for key in ("id", "severity", "category", "title", "source", "remediation")}
            for r in blocking
        ],
        "envelope": blocked_envelope(skill_name, report_path) if blocking else None,
    }


def _emit(payload: dict) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        gl = _load_gap_ledger()
    except ImportError as exc:
        _emit({"status": "error", "code": "HELPER_MISSING", "error": str(exc)})
        return 1
    path = Path(args.ledger)
    try:
        ledger = gl.load_ledger(path)
    except gl.LedgerError as exc:
        _emit({"status": "error", "code": exc.code, "error": str(exc)})
        return 1
    missing = [s for s in args.require_stage if s not in ledger["stages"]]
    if missing:
        _emit(
            {
                "status": "error",
                "code": "STAGE_NOT_RECORDED",
                "error": f"no findings recorded by: {', '.join(missing)}",
                "missing_stages": missing,
                "stages": list(ledger["stages"]),
            }
        )
        return 1
    _emit(
        evaluate(
            gl,
            ledger,
            skill_name=args.skill_name,
            report_path=args.report_path,
            ledger_path=str(path),
        )
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hard-gate",
        description="Block a test-skill run on any Critical or High gap in the ledger.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="count the blocking gaps and decide the gate")
    p.add_argument("--ledger", required=True, help="{forge_version}/test-findings-{run_id}.json")
    p.add_argument("--skill-name", required=True)
    p.add_argument("--report-path", required=True, help="the test report, for the envelope")
    p.add_argument(
        "--require-stage",
        action="append",
        default=[],
        help="a stage that must have appended to the ledger (repeatable)",
    )
    p.set_defaults(func=_cmd_check)

    return parser


def _force_utf8(*streams) -> None:
    """Reconfigure the JSON streams to UTF-8 (a Windows console uses cp1252)."""
    for stream in streams:
        if hasattr(stream, "reconfigure"):
            errors = getattr(stream, "errors", None)
            if errors is None:
                stream.reconfigure(encoding="utf-8")
            else:
                stream.reconfigure(encoding="utf-8", errors=errors)


def main(argv: list[str] | None = None) -> int:
    _force_utf8(sys.stdout)
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
