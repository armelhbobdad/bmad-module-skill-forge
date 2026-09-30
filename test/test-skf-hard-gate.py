#!/usr/bin/env python3
"""Tests for src/skf-test-skill/scripts/hard-gate.py.

The hard gate reads the gap ledger (gap-ledger.py) and blocks on any
Critical or High record:
  - a Critical coverage gap and a High coherence finding block, with the
    blocking list and the hard-gate-blocked envelope (exit 2 payload)
  - a run whose only gaps are missing exports (Medium) passes, so the
    coverage score and the threshold decide it
  - Low and Info records and an empty ledger pass
  - a missing or invalid ledger, or a stage that never appended, is an
    error, never a pass
  - the gate and the rendered Gap Report agree on the blocking ids
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "src" / "skf-test-skill" / "scripts"
GATE = SCRIPTS / "hard-gate.py"
LEDGER_SCRIPT = SCRIPTS / "gap-ledger.py"

spec = importlib.util.spec_from_file_location("hard_gate", GATE)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

RUN_ID = "20260930T101010Z-4242-ab12"
REPORT = f"forge-data/demo/1.0.0/test-report-demo-{RUN_ID}.md"


def run(script: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def append(ledger: Path, stage: str, records: list[dict]) -> None:
    proc = run(LEDGER_SCRIPT, "append", "--ledger", str(ledger), "--stage", stage, stdin=json.dumps(records))
    assert proc.returncode == 0, proc.stdout


def gap(severity: str, category: str, title: str, source: str = "SKILL.md:10") -> dict:
    return {
        "severity": severity,
        "category": category,
        "title": title,
        "source": source,
        "remediation": f"Fix {title} at `{source}`.",
    }


def check(ledger: Path, *extra: str) -> subprocess.CompletedProcess:
    return run(
        GATE, "check", "--ledger", str(ledger), "--skill-name", "demo", "--report-path", REPORT, *extra
    )


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    return tmp_path / f"test-findings-{RUN_ID}.json"


def test_critical_coverage_and_high_coherence_block(ledger: Path):
    append(
        ledger,
        "coverage-check",
        [
            gap("Medium", "missing-export", "parseDate undocumented"),
            gap("Critical", "signature-mismatch", "formatDate signature", "src/utils.ts:42"),
        ],
    )
    append(ledger, "coherence-check", [gap("High", "inaccurate-reference", "Type not exported")])
    proc = check(ledger, "--require-stage", "coverage-check", "--require-stage", "coherence-check")
    assert proc.returncode == 0, proc.stdout
    out = json.loads(proc.stdout)
    assert out["status"] == "ok"
    assert out["gate"] == "blocked"
    assert out["blocking_count"] == 2
    assert out["non_blocking_count"] == 1
    assert out["counts"] == {"Critical": 1, "High": 1, "Medium": 1, "Low": 0, "Info": 0}
    assert [(b["id"], b["severity"], b["category"]) for b in out["blocking"]] == [
        ("GAP-002", "Critical", "signature-mismatch"),
        ("GAP-003", "High", "inaccurate-reference"),
    ]
    assert out["blocking"][0]["source"] == "src/utils.ts:42"
    assert out["blocking"][0]["remediation"] == "Fix formatDate signature at `src/utils.ts:42`."
    assert out["envelope"] == {
        "status": "error",
        "skill_name": "demo",
        "verdict": "FAIL",
        "score": None,
        "threshold": None,
        "report_path": REPORT,
        "next_workflow": "update-skill",
        "exit_code": 2,
        "halt_reason": "hard-gate-blocked",
    }


def test_only_missing_exports_do_not_block(ledger: Path):
    append(
        ledger,
        "coverage-check",
        [gap("Medium", "missing-export", f"export{i} undocumented", f"src/m{i}.ts:1") for i in range(5)],
    )
    append(ledger, "coherence-check", [])
    out = json.loads(check(ledger).stdout)
    assert out["gate"] == "passed"
    assert out["blocking"] == []
    assert out["blocking_count"] == 0
    assert out["non_blocking_count"] == 5
    assert out["envelope"] is None


@pytest.mark.parametrize("severity", ["Low", "Info"])
def test_low_and_info_pass(ledger: Path, severity: str):
    append(ledger, "coverage-check", [gap(severity, "provenance-line", "line is not the definition")])
    assert json.loads(check(ledger).stdout)["gate"] == "passed"


def test_empty_ledger_passes(ledger: Path):
    append(ledger, "coverage-check", [])
    append(ledger, "coherence-check", [])
    out = json.loads(check(ledger, "--require-stage", "coverage-check", "--require-stage", "coherence-check").stdout)
    assert out["gate"] == "passed"
    assert out["stages"] == ["coverage-check", "coherence-check"]
    assert out["counts"] == {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}


def test_missing_ledger_is_an_error_not_a_pass(ledger: Path):
    proc = check(ledger)
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["status"] == "error"
    assert out["code"] == "LEDGER_MISSING"


def test_invalid_ledger_is_an_error(ledger: Path):
    ledger.write_text(json.dumps({"schema_version": 1, "stages": [], "records": "none"}), encoding="utf-8")
    proc = check(ledger)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "LEDGER_INVALID"


def test_stage_that_never_appended_is_refused(ledger: Path):
    append(ledger, "coverage-check", [gap("Medium", "missing-export", "a")])
    proc = check(ledger, "--require-stage", "coverage-check", "--require-stage", "coherence-check")
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["code"] == "STAGE_NOT_RECORDED"
    assert out["missing_stages"] == ["coherence-check"]
    assert out["stages"] == ["coverage-check"]


def test_gate_and_gap_report_agree(ledger: Path):
    append(
        ledger,
        "coverage-check",
        [gap("Critical", "fabricated-signature", "ghostFn documented"), gap("Low", "metadata", "no example")],
    )
    append(ledger, "coherence-check", [gap("Critical", "broken-reference", "missing target")])
    blocking = {b["id"] for b in json.loads(check(ledger).stdout)["blocking"]}
    rendered = run(LEDGER_SCRIPT, "render", "--ledger", str(ledger)).stdout
    rendered_ids = {
        line.split(":")[0].removeprefix("### ")
        for line in rendered.splitlines()
        if line.startswith("### GAP-")
    }
    assert blocking == {"GAP-001", "GAP-003"}
    assert blocking <= rendered_ids
    assert "**Blocking (Critical + High):** 2" in rendered


def test_gate_refuses_without_the_ledger_helper(tmp_path: Path, ledger: Path):
    append(ledger, "coverage-check", [gap("High", "structural", "unbalanced fence")])
    alone = tmp_path / "alone"
    alone.mkdir()
    shutil.copy(GATE, alone / "hard-gate.py")
    proc = run(alone / "hard-gate.py", "check", "--ledger", str(ledger), "--skill-name", "demo", "--report-path", REPORT)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "HELPER_MISSING"


def test_required_arguments():
    proc = run(GATE, "check", "--ledger", "x.json")
    assert proc.returncode == 2
    assert "--skill-name" in proc.stderr


def test_blocked_envelope_shape():
    envelope = mod.blocked_envelope("demo", REPORT)
    assert list(envelope) == [
        "status",
        "skill_name",
        "verdict",
        "score",
        "threshold",
        "report_path",
        "next_workflow",
        "exit_code",
        "halt_reason",
    ]
    assert envelope["halt_reason"] == mod.HALT_REASON == "hard-gate-blocked"
    assert envelope["exit_code"] == mod.BLOCKED_EXIT_CODE == 2
