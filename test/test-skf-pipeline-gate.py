#!/usr/bin/env python3
"""Tests for src/skf-forger/scripts/pipeline-gate.py.

The circuit breaker Pipeline Mode (pipeline-mode.md step 4d) runs after AN,
TS, AS or VS instead of reading the result by hand:
  - every verdict of each gated workflow: TS continues only on PASS routed to
    export (a capped FAIL whose score clears the threshold halts, a fallback
    PASS below the threshold continues, a PASS with an error status halts),
    AN on enough units, AS skips a next US on CLEAN and halts on CRITICAL, VS
    halts on zero coverage and lets NOT_FEASIBLE with coverage on to RA
  - the envelope line and the result record, errored results, and input the
    gate cannot read, UTF-8 with a byte-order mark included (it halts)
  - step 4d gates the envelope the step just printed, never a -latest.json
    record, which may be an earlier run's
  - the gate's fields and value sets match the workflows' own result
    contracts (their envelope schemas once they have them) and the Circuit
    Breakers table, and the documented call runs as written
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCRIPT = SRC / "skf-forger" / "scripts" / "pipeline-gate.py"
PIPELINE_MODE = SRC / "skf-forger" / "references" / "pipeline-mode.md"
CONTRACTS = SRC / "shared" / "references" / "pipeline-contracts.md"
SCHEMAS = SRC / "shared" / "scripts" / "schemas"

spec = importlib.util.spec_from_file_location("skf_pipeline_gate", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def envelope(code: str, **fields) -> str:
    return f"{mod.ENVELOPES[code]}: {json.dumps(fields)}"


def ts_envelope(verdict, next_workflow, **extra) -> str:
    fields = {"status": "success", "skill_name": "demo", "verdict": verdict, "score": 91,
              "threshold": 90, "report_path": "/f/demo/1.0.0/test-report-demo-x.md",
              "next_workflow": next_workflow, "exit_code": 0, "halt_reason": None}
    fields.update(extra)
    return envelope("TS", **fields)


def decide(code: str, text: str, **kwargs) -> dict:
    return mod.gate(code, text, **kwargs)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# TS: only PASS goes on to export
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict,next_workflow,exit_code,reason",
    [
        pytest.param("FAIL", "update-skill", 2, "FAIL", id="fail"),
        pytest.param("INCONCLUSIVE", None, 3, "INCONCLUSIVE", id="inconclusive"),
        pytest.param("pass-with-drift", "update-skill", 4, "pass-with-drift", id="pass-with-drift"),
    ],
)
def test_ts_halts_on_every_verdict_but_pass(verdict, next_workflow, exit_code, reason):
    d = decide("TS", ts_envelope(verdict, next_workflow, exit_code=exit_code))
    assert d["decision"] == "halt"
    assert d["reason"] == reason
    assert "not exported" in d["message"]


def test_ts_continues_on_pass_routed_to_export():
    d = decide("TS", ts_envelope("PASS", "export-skill"))
    assert d == {"code": "TS", "decision": "continue", "reason": None, "skip": None,
                 "message": "TS verdict PASS: the skill goes on to export."}


def test_ts_halts_on_a_capped_fail_whose_score_clears_the_threshold():
    """A post-score cap forces FAIL without lowering the score: the verdict decides."""
    d = decide("TS", ts_envelope("FAIL", "update-skill", score=94, threshold=80, exit_code=2))
    assert (d["decision"], d["reason"]) == ("halt", "FAIL")


def test_ts_continues_on_a_fallback_pass_below_the_threshold():
    """TS's 80% floor settles 85 against 90 as PASS; the gate compares no score."""
    text = ts_envelope("PASS", "export-skill", score=85, threshold=90,
                       threshold_fallback=True, original_threshold=90)
    assert decide("TS", text)["decision"] == "continue"


def test_ts_hard_gate_block_halts_with_the_verdict():
    text = ts_envelope("FAIL", "update-skill", status="error", score=None, threshold=None,
                       exit_code=2, halt_reason="hard-gate-blocked")
    d = decide("TS", text)
    assert (d["decision"], d["reason"]) == ("halt", "FAIL")
    assert "hard-gate-blocked" in d["message"]


def test_ts_error_before_a_verdict_halts_with_its_reason():
    text = ts_envelope(None, None, status="error", score=None, threshold=None,
                       report_path=None, exit_code=1, halt_reason="forge-tier-missing")
    assert decide("TS", text)["reason"] == "forge-tier-missing"


def test_ts_pass_not_routed_to_export_halts():
    d = decide("TS", ts_envelope("PASS", "update-skill"))
    assert (d["decision"], d["reason"]) == ("halt", "not-routed-to-export")


@pytest.mark.parametrize(
    "text,reason",
    [
        pytest.param(json.dumps({"status": "failed", "summary": {"result": "PASS"}}), "failed",
                     id="failed-record"),
        pytest.param(ts_envelope("PASS", "export-skill", status="error", exit_code=1,
                                 halt_reason="report-anchor-missing"), "report-anchor-missing",
                     id="error-envelope"),
    ],
)
def test_ts_pass_with_an_error_status_halts(text, reason):
    """An errored result halts, as the gate's contract says, a PASS included."""
    d = decide("TS", text, next_code="EX")
    assert (d["decision"], d["reason"]) == ("halt", reason)
    assert "not exported" in d["message"]


@pytest.mark.parametrize(
    "result,decision,reason",
    [
        pytest.param("PASS", "continue", None, id="pass"),
        pytest.param("PASS_WITH_DRIFT", "halt", "pass-with-drift", id="pass-with-drift"),
        pytest.param("FAIL", "halt", "FAIL", id="fail"),
        pytest.param("INCONCLUSIVE", "halt", "INCONCLUSIVE", id="inconclusive"),
    ],
)
def test_ts_reads_the_result_record(result, decision, reason):
    """skf-test-skill-result-latest.json spells the verdict in summary.result."""
    record = {"status": "success", "outputs": [{"type": "report", "path": "test-report-demo-x.md"}],
              "summary": {"score": 88, "threshold": 80, "result": result, "testMode": "naive"}}
    d = decide("TS", json.dumps(record, indent=2))
    assert (d["decision"], d["reason"]) == (decision, reason)


@pytest.mark.parametrize(
    "verdict,reason",
    [pytest.param("MAYBE", "unknown-verdict", id="unknown"), pytest.param(None, "no-verdict", id="missing")],
)
def test_ts_halts_without_a_verdict_it_knows(verdict, reason):
    assert decide("TS", ts_envelope(verdict, None))["reason"] == reason


# --------------------------------------------------------------------------
# AN: enough skillable units
# --------------------------------------------------------------------------


def an_envelope(confirmed, **extra) -> str:
    fields = {"status": "success", "report_path": "/f/analysis-report.md",
              "brief_paths": [f"/f/u{i}/skill-brief.yaml" for i in range(confirmed)],
              "unit_counts": {"confirmed": confirmed, "skipped": 0, "maybe": 0},
              "exit_code": 0, "halt_reason": None, "mode": "auto"}
    fields.update(extra)
    return envelope("AN", **fields)


def test_an_halts_on_zero_units():
    d = decide("AN", an_envelope(0))
    assert (d["decision"], d["reason"]) == ("halt", "no-skillable-units")


@pytest.mark.parametrize("confirmed", [1, 3])
def test_an_continues_with_units(confirmed):
    d = decide("AN", an_envelope(confirmed))
    assert d["decision"] == "continue"
    assert f"{confirmed} skillable unit(s)" in d["message"]


def test_an_min_raises_the_bar():
    assert decide("AN", an_envelope(2), minimum=3)["reason"] == "units-below-min"
    assert decide("AN", an_envelope(3), minimum=3)["decision"] == "continue"


def test_an_counts_the_briefs_of_a_record():
    record = {"status": "success", "outputs": [
        {"type": "report", "path": "analysis-report.md"},
        {"type": "config", "path": "/f/a/skill-brief.yaml"},
        {"type": "config", "path": "/f/b/skill-brief.yaml"},
    ], "summary": {}}
    d = decide("AN", json.dumps(record))
    assert d["decision"] == "continue"
    assert "2 skillable unit(s)" in d["message"]


def test_an_counts_brief_paths_without_unit_counts():
    text = envelope("AN", status="success", brief_paths=["/f/a/skill-brief.yaml"])
    assert decide("AN", text)["decision"] == "continue"


@pytest.mark.parametrize(
    "fields,reason",
    [
        pytest.param({"status": "redirect", "redirect_to": "US", "skill_name": "hono"}, "redirect", id="redirect"),
        pytest.param({"status": "skipped", "brief_paths": [], "unit_counts": {"confirmed": 0},
                      "skipped_reason": "Existing skill for hono"}, "skipped", id="skipped"),
        pytest.param({"status": "error", "exit_code": 3, "halt_reason": "pin-invalid"}, "pin-invalid", id="error"),
        pytest.param({"status": "success"}, "units-unknown", id="no-count"),
    ],
)
def test_an_halts_without_a_brief_to_go_on_with(fields, reason):
    d = decide("AN", envelope("AN", **fields))
    assert (d["decision"], d["reason"]) == ("halt", reason)


# --------------------------------------------------------------------------
# AS: CLEAN skips a next US, CRITICAL halts
# --------------------------------------------------------------------------


def as_envelope(drift_score, **extra) -> str:
    fields = {"status": "success", "skill_name": "demo", "drift_score": drift_score,
              "report_path": "/f/drift-report.md", "next_workflow": None, "exit_code": 0,
              "halt_reason": None}
    fields.update(extra)
    return envelope("AS", **fields)


@pytest.mark.parametrize(
    "severity,next_code,decision,skip",
    [
        pytest.param("CLEAN", "US", "skip", "US", id="clean-before-us"),
        pytest.param("CLEAN", "TS", "continue", None, id="clean-before-ts"),
        pytest.param("CLEAN", None, "continue", None, id="clean-last"),
        pytest.param("MINOR", "US", "continue", None, id="minor"),
        pytest.param("SIGNIFICANT", "US", "continue", None, id="significant"),
        pytest.param("CRITICAL", "US", "halt", None, id="critical"),
    ],
)
def test_as_severities(severity, next_code, decision, skip):
    d = decide("AS", as_envelope(severity), next_code=next_code)
    assert (d["decision"], d["skip"]) == (decision, skip)
    if decision == "skip":
        assert d["reason"] == "CLEAN"
        assert d["message"] == "No drift detected: skipping update."
    if decision == "halt":
        assert d["reason"] == "CRITICAL"


def test_as_reads_the_record_severity():
    record = {"status": "success", "outputs": [], "summary": {"drift_count": 0, "severity": "CLEAN"}}
    assert decide("AS", json.dumps(record), next_code="us")["decision"] == "skip"


@pytest.mark.parametrize(
    "fields,decision",
    [
        pytest.param({"next_workflow": "update-skill", "upstream_moved": True, "upstream_ref": "v1.3.0"},
                     "continue", id="upstream-moved"),
        pytest.param({"next_workflow": None, "upstream_moved": False, "upstream_ref": None}, "skip",
                     id="upstream-unchanged"),
    ],
)
def test_a_clean_audit_reaches_us_when_upstream_moved(fields, decision):
    """#588: a headless `maintain` after an upstream release reaches US. The
    audited tree can read CLEAN while the skill is pinned to an older ref;
    AS then routes to update-skill, and the gate follows the route."""
    d = decide("AS", as_envelope("CLEAN", **fields), next_code="US")
    assert d["decision"] == decision
    if decision == "continue":
        assert d["skip"] is None and "v1.3.0" in d["message"]
    record = {"status": "success", "summary": {"severity": "CLEAN", "next_workflow": fields["next_workflow"]}}
    assert decide("AS", json.dumps(record), next_code="US")["decision"] == decision


@pytest.mark.parametrize(
    "text,reason",
    [
        pytest.param(as_envelope(None, status="error", exit_code=3, halt_reason="skill-not-found"),
                     "skill-not-found", id="error"),
        pytest.param(as_envelope("HIGH"), "unknown-severity", id="unknown"),
        pytest.param(as_envelope(None), "no-severity", id="missing"),
    ],
)
def test_as_halts_without_a_severity_it_knows(text, reason):
    assert decide("AS", text, next_code="US")["reason"] == reason


# --------------------------------------------------------------------------
# VS: zero coverage halts, NOT_FEASIBLE with coverage goes on to RA
# --------------------------------------------------------------------------


def vs_envelope(verdict, **extra) -> str:
    fields = {"status": "success", "report_path": "/f/feasibility-report-p-x.md",
              "report_latest_path": "/f/feasibility-report-p-latest.md", "overall_verdict": verdict,
              "coverage_percentage": 100, "recommendation_count": 0, "exit_code": 0, "halt_reason": None}
    fields.update(extra)
    return envelope("VS", **fields)


@pytest.mark.parametrize(
    "verdict,coverage,decision,reason",
    [
        pytest.param("FEASIBLE", 100, "continue", None, id="feasible"),
        pytest.param("CONDITIONALLY_FEASIBLE", 75, "continue", None, id="conditionally-feasible"),
        pytest.param("NOT_FEASIBLE", 60, "continue", None, id="not-feasible-blocked-pair"),
        pytest.param("NOT_FEASIBLE", 0, "halt", "zero-coverage", id="not-feasible-zero-coverage"),
    ],
)
def test_vs_verdicts(verdict, coverage, decision, reason):
    """RA takes a Blocked integration as a critical issue, so only a VS that
    verified nothing (zero coverage, the rollup's first rung) stops it."""
    d = decide("VS", vs_envelope(verdict, coverage_percentage=coverage), next_code="RA")
    assert (d["decision"], d["reason"]) == (decision, reason)


@pytest.mark.parametrize(
    "coverage,decision",
    [pytest.param(0, "halt", id="zero-coverage"), pytest.param(50, "continue", id="blocked-pair")],
)
def test_vs_reads_the_record_verdict_and_coverage(coverage, decision):
    record = {"status": "success", "summary": {"overallVerdict": "NOT_FEASIBLE", "coveragePercentage": coverage}}
    assert decide("VS", json.dumps(record))["decision"] == decision


@pytest.mark.parametrize(
    "text,reason",
    [
        pytest.param(vs_envelope(None, status="error", exit_code=4, halt_reason="write-failed"),
                     "write-failed", id="error"),
        pytest.param(vs_envelope("BLOCKED"), "unknown-verdict", id="unknown"),
        pytest.param(vs_envelope(None), "no-verdict", id="missing"),
        pytest.param(vs_envelope("FEASIBLE", coverage_percentage=None), "no-coverage", id="no-coverage"),
        pytest.param(vs_envelope("FEASIBLE", coverage_percentage=150), "unknown-coverage", id="coverage-over-100"),
        pytest.param(vs_envelope("FEASIBLE", coverage_percentage=True), "unknown-coverage", id="coverage-not-a-number"),
    ],
)
def test_vs_halts_without_a_verdict_it_knows(text, reason):
    assert decide("VS", text)["reason"] == reason


# --------------------------------------------------------------------------
# Reading the input
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,reason",
    [
        pytest.param("", "no-result", id="empty"),
        pytest.param("  \n", "no-result", id="blank"),
        pytest.param("the workflow crashed", "result-unreadable", id="prose"),
        pytest.param("[1, 2]", "result-unreadable", id="not-an-object"),
        pytest.param("SKF_TEST_RESULT_JSON: {not json}", "result-unreadable", id="bad-envelope"),
        pytest.param(envelope("AS", status="success", drift_score="CLEAN"), "wrong-result", id="other-workflow"),
    ],
)
def test_a_result_the_gate_cannot_read_halts(text, reason):
    d = decide("TS", text)
    assert (d["decision"], d["reason"]) == ("halt", reason)


def test_the_last_envelope_of_the_code_wins_among_other_lines():
    text = "\n".join([
        "Pipeline [4/5]: Starting TS (Test Skill)...",
        ts_envelope("FAIL", "update-skill"),
        envelope("AN", status="success", unit_counts={"confirmed": 1}),
        "  " + ts_envelope("PASS", "export-skill") + "  ",
        "Pipeline [4/5]: TS complete.",
    ])
    assert decide("TS", text)["decision"] == "continue"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _run(*args, stdin=""):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )


def test_cli_reads_stdin():
    p = _run("--code", "ts", stdin=ts_envelope("INCONCLUSIVE", None) + "\n")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert (out["code"], out["decision"], out["reason"]) == ("TS", "halt", "INCONCLUSIVE")


def test_cli_reads_a_result_file(tmp_path):
    saved = tmp_path / "audit-record.json"
    saved.write_text(json.dumps({"status": "success", "summary": {"severity": "CLEAN"}}), encoding="utf-8")
    p = _run("--code", "AS", "--next", "US", "--result", str(saved))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["skip"] == "US"


def _run_bytes(*args, stdin: bytes):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, timeout=60)


def test_cli_halts_on_input_that_is_not_utf8(tmp_path):
    raw = b'SKF_TEST_RESULT_JSON: {"status":"success","verdict":"PASS\xff"}\n'
    p = _run_bytes("--code", "TS", stdin=raw)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.decode("utf-8"))["reason"] == "result-unreadable"
    saved = tmp_path / "envelope.txt"
    saved.write_bytes(raw)
    assert json.loads(_run("--code", "TS", "--result", str(saved)).stdout)["reason"] == "result-unreadable"


def test_cli_drops_a_byte_order_mark(tmp_path):
    record = b"\xef\xbb\xbf" + json.dumps({"status": "success", "summary": {"severity": "CLEAN"}}).encode("utf-8")
    p = _run_bytes("--code", "AS", "--next", "US", stdin=record)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout.decode("utf-8"))["skip"] == "US"
    saved = tmp_path / "audit-record.json"
    saved.write_bytes(record)
    assert json.loads(_run("--code", "AS", "--next", "US", "--result", str(saved)).stdout)["skip"] == "US"


def test_cli_passes_the_an_minimum():
    p = _run("--code", "AN", "--min", "4", stdin=an_envelope(3))
    assert json.loads(p.stdout)["reason"] == "units-below-min"


def test_cli_reads_non_ascii_as_utf8():
    p = _run("--code", "AN", stdin=an_envelope(1, report_path="/f/Proyecto café → report.md"))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["decision"] == "continue"


def test_cli_halts_on_an_unreadable_result_file(tmp_path):
    p = _run("--code", "VS", "--result", str(tmp_path / "missing.json"))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["reason"] == "result-unreadable"


@pytest.mark.parametrize(
    "args",
    [pytest.param(["--code", "EX"], id="ungated-code"), pytest.param([], id="no-code"),
     pytest.param(["--code", "TS", "--min", "many"], id="bad-min")],
)
def test_cli_usage_errors_exit_two(args):
    p = _run(*args)
    assert p.returncode == 2
    assert p.stdout == ""


# --------------------------------------------------------------------------
# The gate matches the contracts it enforces
# --------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"section {heading!r} not found"
    return m.group(1)


def _workflow_text(skill: str) -> str:
    """Every Markdown file of a workflow: its result contract may live in any."""
    return "\n".join(_read(p) for p in sorted((SRC / skill).rglob("*.md")))


def _envelope_schema(stem: str) -> dict | None:
    """A workflow's envelope schema, once a later package adds it (W3 to W5)."""
    path = SCHEMAS / f"skf-{stem}-result-envelope.v1.json"
    return json.loads(_read(path)) if path.exists() else None


def _schema_fields(schema: dict) -> dict:
    """The envelope's properties, inside the wrapper the schema names, if any."""
    meta = schema.get("$defs", {}).get("skf-envelope", {}).get("const", {})
    props = schema.get("properties", {})
    return props[meta["wrapper"]].get("properties", {}) if meta.get("wrapper") else props


def _schema_values(node: dict) -> set[str]:
    """The strings a schema property allows, through anyOf and oneOf."""
    values = {v for v in node.get("enum", []) if isinstance(v, str)}
    for key in ("anyOf", "oneOf"):
        for sub in node.get(key, []):
            values |= _schema_values(sub)
    return values


# Each gated workflow: its envelope schema's stem, its skill folder, the
# envelope fields the gate reads, and the field whose values the rule knows.
GATED = {
    "TS": ("test", "skf-test-skill", ("verdict", "next_workflow"), "verdict"),
    "AN": ("analyze", "skf-analyze-source", ("unit_counts", "brief_paths"), None),
    "AS": ("audit", "skf-audit-skill", ("drift_score", "next_workflow", "upstream_ref"), "drift_score"),
    "VS": ("verify-stack", "skf-verify-stack", ("overall_verdict", "coverage_percentage"), "overall_verdict"),
}
RULE_VALUES = {
    "TS": set(mod.TS_VERDICTS.values()),
    "AS": set(mod.AS_SEVERITIES),
    "VS": set(mod.VS_VERDICTS),
}


def _prose_values(code: str, text: str) -> list[set[str]]:
    """The value sets a workflow's prose lists for the field its rule reads."""
    if code == "TS":
        return [set(m.split("|")) for m in re.findall(r'"verdict":"([A-Za-z-]+(?:\|[A-Za-z-]+)+)"', text)]
    if code == "AS":
        return [set(m.split("|")) for m in re.findall(r'"drift_score":"([A-Z]+(?:\|[A-Z]+)+)\|null"', text)]
    return [set(re.findall(r"`(FEASIBLE|CONDITIONALLY_FEASIBLE|NOT_FEASIBLE)`", text))]


def test_every_gated_code_is_described():
    assert set(GATED) == set(mod.GATED_CODES) == set(mod.ENVELOPES)


@pytest.mark.parametrize("code", sorted(GATED))
def test_each_workflow_prints_the_envelope_fields_the_gate_reads(code):
    """The envelope prefix and fields come from the workflow's envelope schema
    once it has one, else from the envelope lines its prose shows."""
    stem, skill, fields, _ = GATED[code]
    schema = _envelope_schema(stem)
    if schema is not None:
        assert schema["$defs"]["skf-envelope"]["const"]["prefix"] == mod.ENVELOPES[code]
        missing = [f for f in fields if f not in _schema_fields(schema)]
    else:
        lines = [line for line in _workflow_text(skill).splitlines() if f"{mod.ENVELOPES[code]}: {{" in line]
        assert lines, f"{skill} prints no {mod.ENVELOPES[code]} line"
        missing = [f for f in fields if not any(f'"{f}"' in line for line in lines)]
    assert not missing, (code, missing)


@pytest.mark.parametrize("code", sorted(RULE_VALUES))
def test_the_value_sets_match_the_workflow_contracts(code):
    """The values each rule knows are the ones the workflow's own contract lists."""
    stem, skill, _, field = GATED[code]
    schema = _envelope_schema(stem)
    if schema is not None:
        assert _schema_values(_schema_fields(schema).get(field, {})) == RULE_VALUES[code]
    else:
        found = _prose_values(code, _workflow_text(skill))
        assert RULE_VALUES[code] in found, found


def test_ts_routes_only_pass_to_export():
    """The TS rule rests on TS naming export-skill as the route of PASS."""
    lines = _workflow_text("skf-test-skill").splitlines()
    schema = _envelope_schema("test")
    if schema is not None:
        lines.append("next_workflow " + json.dumps(_schema_fields(schema).get("next_workflow", {})))
    assert any(re.search(r"next_workflow.*export-skill.*\bPASS\b", line) for line in lines)


def test_the_circuit_breaker_table_names_what_the_gate_decides():
    rows = {}
    for line in _section(_read(CONTRACTS), "## Circuit Breakers").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"[A-Z]{2}", cells[0]):
            rows[cells[0]] = " ".join(cells[1:])
    assert set(rows) - {"CS"} == set(mod.GATED_CODES)
    for code, tokens in {"TS": ("PASS", "FAIL", "INCONCLUSIVE", "pass-with-drift", "`verdict`",
                                "`summary.result`", "next_workflow"),
                         "AN": ("unit_counts.confirmed", "min: 1"),
                         "AS": ("CRITICAL", "CLEAN", "`drift_score`", "`summary.severity`"),
                         "VS": ("`zero-coverage`", "NOT_FEASIBLE", "`coverage_percentage`",
                                "`summary.coveragePercentage`", "`overall_verdict`",
                                "`summary.overallVerdict`")}.items():
        for token in tokens:
            assert token in rows[code], (code, token)
    assert "score below" not in rows["TS"].lower()
    assert "All integrations blocked" not in rows["VS"]
    assert "pipeline-gate.py" in _section(_read(CONTRACTS), "## Circuit Breakers")


def _step_4d() -> str:
    text = _read(PIPELINE_MODE)
    start = text.index("   - d. **Check the circuit breaker.**")
    return text[start:text.index("   - e. **", start)]


def _documented_gate_call() -> tuple[list[str], str]:
    """The call step 4d documents: its arguments and its heredoc delimiter."""
    m = re.search(r"```bash\n\s*uv run scripts/pipeline-gate\.py (.+?) <<'(\w+)'\n.*?\n\s*\2\n\s*```",
                  _step_4d(), re.S)
    assert m, "step 4d must show the gate call with a quoted heredoc"
    return m.group(1), m.group(2)


@pytest.mark.parametrize("keep_optional", [True, False], ids=["with-options", "required-only"])
def test_step_4d_gate_call_runs_as_written(keep_optional):
    synopsis, _ = _documented_gate_call()
    if keep_optional:
        synopsis = re.sub(r"\[(--[^\]]+)\]", r"\1", synopsis)
    else:
        synopsis = re.sub(r"\s*\[--[^\]]+\]", "", synopsis)
    values = {"<code>": "AS", "<next-code>": "US", "<N>": "1"}
    argv = [values.get(word, word) for word in shlex.split(synopsis)]
    assert not [w for w in argv if w.startswith("<")], argv
    p = _run(*argv, stdin=as_envelope("CLEAN"))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["decision"] == ("skip" if keep_optional else "continue")


def test_step_4d_gates_the_envelope_the_step_just_printed():
    """A -latest.json record may not describe this run: TS writes its record
    before its health-check halt, whose envelope carries no verdict, and its
    coverage and coherence aborts and its step-completeness and report-anchor
    halts write none, leaving an earlier run's record in place. Gated on this
    run's envelope, the pipeline halts; the earlier PASS record would export."""
    this_run = ts_envelope(None, None, status="error", score=None, threshold=None, exit_code=1,
                           halt_reason="step-completeness-violation")
    earlier_record = json.dumps({"status": "success", "summary": {"result": "PASS", "score": 92}})
    assert decide("TS", this_run, next_code="EX")["decision"] == "halt"
    assert decide("TS", earlier_record, next_code="EX")["decision"] == "continue"
    step = _step_4d()
    assert "--result" not in step
    assert "never a `-latest.json` result file" in step
    # A step that printed no envelope: the empty heredoc halts.
    assert "leave the heredoc empty" in step and "`no-result`" in step
    assert (decide("TS", "", next_code="EX")["decision"], decide("TS", "")["reason"]) == ("halt", "no-result")


def test_step_4d_passes_an_min_only_when_the_plan_has_one():
    """forge-auto's AN entry has min null, and `--min null` is a usage error."""
    assert "for AN with a `min` in its plan entry, `--min` that value" in _step_4d()
    assert _run("--code", "AN", "--min", "null", stdin=an_envelope(1)).returncode == 2


def test_step_4d_acts_on_the_decision_and_compares_no_score():
    step = _step_4d()
    for word in ("`continue`", "`skip`", "`halt`", "`reason`", "`message`", "--threshold",
                 "`FAIL`", "`INCONCLUSIVE`", "`pass-with-drift`"):
        assert word in step, word
    assert "Compare no score with a threshold here" in step
    assert "validate it against the threshold" not in _read(PIPELINE_MODE)


def test_the_ts_to_ex_rule_has_one_home_in_the_contracts():
    """Step 4d runs the gate; the contracts state when EX runs after TS, and
    the run procedure keeps no copy of that rule."""
    assert "`TS` followed by `EX`" not in _section(_read(PIPELINE_MODE), "## Special behaviors")
    contracts = _read(CONTRACTS)
    ts_ex = next(line for line in _section(contracts, "## Data Flow").splitlines() if line.startswith("| TS | EX |"))
    assert "below the circuit-breaker threshold" not in ts_ex
    assert "`next_workflow` is `export-skill`" in ts_ex
    ts_row = next(line for line in _section(contracts, "## Circuit Breakers").splitlines() if line.startswith("| TS |"))
    for verdict in ("FAIL", "INCONCLUSIVE", "pass-with-drift", "post-score cap"):
        assert verdict in ts_ex + ts_row, verdict
