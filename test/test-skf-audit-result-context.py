#!/usr/bin/env python3
"""Tests for src/skf-audit-skill/scripts/build-result-context.py.

#1130 (BMad Builder determinism-5): report.md stated the next_workflow rule in
§4, in its Workflow Recommendation and in its Result Contract,
headless-contract.md stated it again, and the model typed result-context.json
by hand. The script reads the drift report's frontmatter and the
classification step 5 saved, works out the route once and writes the
emitter's payload. These tests:
- check each route, and that each payload passes the emitter and the
  envelope schema;
- run report §1b's command as written, through bash, with a reason that holds
  quotes, backticks and `$( )`, and find it verbatim in the envelope's warning;
- check that each input it refuses exits 1 with a JSON error and writes
  nothing;
- check that the stages read the route the script prints and state no rule
  of their own.
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
AUDIT = SRC / "skf-audit-skill"
SCRIPT = AUDIT / "scripts" / "build-result-context.py"
REPORT = AUDIT / "references" / "report.md"
HEADLESS = AUDIT / "references" / "headless-contract.md"
SKILL = AUDIT / "SKILL.md"
EMITTER = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-audit-result-envelope.v1.json"
TIMESTAMP = "20260101-000000"
HOSTILE_REASON = "No module named 'tomllib' \"x\" $(touch pwned) `touch pwned2`"
POSIX_BASH = os.name != "nt" and shutil.which("bash") is not None
COMMAND = ('uv run {resultContextScript} --report "{outputFile}" --classification "{auditDataFolder}/severity.json" '
           '[--resolver-unavailable "$(cat "{run_dir}/resolver-unavailable.txt")"] '
           '--output "{run_dir}/result-context.json"')

module_spec = importlib.util.spec_from_file_location("skf_audit_build_result_context", SCRIPT)
context = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(context)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _flow(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _fenced(text: str, needle: str) -> str:
    lines = [line.strip() for block in re.findall(r"^```[a-z]*\n(.*?)^```", text, re.M | re.S)
             for line in block.splitlines() if needle in line]
    assert len(lines) == 1, (needle, lines)
    return lines[0]


def _counts(**levels) -> dict:
    return {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, **levels}


class Run:
    """One audit at step 6: the drift report, the saved classification and the run folder."""

    def __init__(self, tmp_path: Path, front: dict | None, severity, report_text: str | None = None):
        self.version = tmp_path / "forge" / "demo" / "1.0.0"
        self.data = self.version / ".skf-audit" / TIMESTAMP
        self.run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-audit-skill-{TIMESTAMP}"
        self.report = self.version / f"drift-report-{TIMESTAMP}.md"
        self.severity = self.data / "severity.json"
        self.output = self.run_dir / "result-context.json"
        for folder in (self.data, self.run_dir):
            folder.mkdir(parents=True, exist_ok=True)
        if report_text is None and front is not None:
            report_text = "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n# Drift Report: demo\n"
        if report_text is not None:
            self.report.write_bytes(report_text.encode("utf-8"))
        if severity is not None:
            self.severity.write_bytes(severity if isinstance(severity, bytes) else json.dumps(severity).encode("utf-8"))

    def build(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--report", str(self.report), "--classification",
                               str(self.severity), *extra, "--output", str(self.output)], capture_output=True,
                              text=True, encoding="utf-8", timeout=60, check=False)

    def emit(self) -> dict:
        proc = subprocess.run([sys.executable, str(EMITTER), "emit", "--workflow", "skf-audit-skill", "--run-dir",
                               str(self.run_dir), "--result-dir", str(self.version)],
                              input=self.output.read_text(encoding="utf-8"), capture_output=True, text=True,
                              encoding="utf-8", timeout=60, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        prefix, _, line = proc.stdout.strip().partition(": ")
        assert prefix == "SKF_AUDIT_RESULT_JSON", proc.stdout
        envelope = json.loads(line)
        Draft202012Validator(json.loads(_read(SCHEMA))).validate(envelope)
        return envelope


def _front(**values) -> dict:
    """A drift report's frontmatter after step 1, the route's values set."""
    return {"workflowType": "audit-skill", "stepsCompleted": ["init", "re-index", "structural-diff", "semantic-diff",
                                                             "severity-classify", "doc-drift"],
            "skill_name": "demo", "audit_ref": "v1.0.0", "upstream_moved": None, "upstream_ref": None,
            "drift_score": "", "nextWorkflow": "", **values}


def _severity(score: str, total: int, **levels) -> dict:
    """What skf-severity-classify.py saves."""
    return {"status": "ok", "drift_score": score, "total_findings": total, "total_items": total,
            "added_export_count": 0, "by_severity": _counts(**levels), "findings": []}


# --------------------------------------------------------------------------
# The route, and the payload the emitter takes
# --------------------------------------------------------------------------


ROUTES = [
    pytest.param(_severity("CRITICAL", 1, CRITICAL=1), {}, "update-skill", None, id="critical"),
    pytest.param(_severity("SIGNIFICANT", 2, HIGH=2), {"upstream_moved": False}, "update-skill", False, id="high"),
    pytest.param(_severity("SIGNIFICANT", 3, MEDIUM=3), {"upstream_moved": True, "upstream_ref": "v1.1.0"},
                 "update-skill", True, id="medium-upstream-moved"),
    pytest.param(_severity("CLEAN", 0), {"upstream_moved": "true", "upstream_ref": "HEAD"}, "update-skill", True,
                 id="clean-moved-as-text"),
    pytest.param(_severity("SIGNIFICANT", 1, MEDIUM=1), {"upstream_moved": None}, None, None, id="medium-unchecked"),
    pytest.param(_severity("MINOR", 2, LOW=2), {"upstream_moved": None}, None, None, id="low-unchecked"),
    pytest.param(_severity("SIGNIFICANT", 1, MEDIUM=1), {"upstream_moved": ""}, None, None, id="medium-moved-empty"),
    pytest.param(_severity("SIGNIFICANT", 1, MEDIUM=1), {"upstream_moved": "false", "upstream_ref": "v9"}, None,
                 False, id="medium-unchanged"),
]


@pytest.mark.parametrize("severity,values,route,moved", ROUTES)
def test_the_route_and_the_payload(tmp_path, severity, values, route, moved):
    run = Run(tmp_path, _front(**values), severity)
    proc = run.build()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    printed = json.loads(proc.stdout)
    assert printed == {"status": "ok", "next_workflow": route, "drift_score": severity["drift_score"],
                       "output": run.output.as_posix()}
    upstream_ref = values.get("upstream_ref") if moved else None
    summary = {"drift_count": severity["total_findings"], "severity": severity["drift_score"], "next_workflow": route,
               "audit_ref": "v1.0.0", "upstream_moved": moved, "upstream_ref": upstream_ref}
    assert json.loads(run.output.read_text(encoding="utf-8")) == {
        "status": "success", "skill_name": "demo", "drift_score": severity["drift_score"],
        "report_path": str(run.report), "next_workflow": route, "audit_ref": "v1.0.0", "upstream_moved": moved,
        "upstream_ref": upstream_ref,
        "result_contract": {"skill": "skf-audit-skill", "status": "success",
                            "outputs": [{"type": "report", "path": str(run.report)}], "summary": summary}}
    envelope = run.emit()
    assert (envelope["next_workflow"], envelope["upstream_moved"], envelope["upstream_ref"]) == (
        route, moved, upstream_ref)
    assert (envelope["status"], envelope["exit_code"], envelope["run_id"]) == ("success", 0, TIMESTAMP)
    assert "warnings" not in envelope
    record = json.loads((run.version / "audit-skill-result-latest.json").read_text(encoding="utf-8"))
    assert record["summary"] == summary


def test_an_empty_audit_ref_is_null(tmp_path):
    run = Run(tmp_path, _front(audit_ref=""), _severity("CLEAN", 0))
    assert run.build().returncode == 0
    payload = json.loads(run.output.read_text(encoding="utf-8"))
    assert payload["audit_ref"] is None and payload["result_contract"]["summary"]["audit_ref"] is None
    assert run.emit()["audit_ref"] is None


def test_a_report_saved_with_crlf_and_a_bom_reads_the_same(tmp_path):
    text = "﻿---\r\nskill_name: demo\r\naudit_ref: v1.0.0\r\nupstream_moved: true\r\nupstream_ref: v2\r\n---\r\n"
    run = Run(tmp_path, None, _severity("CLEAN", 0), report_text=text)
    proc = run.build()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(run.output.read_text(encoding="utf-8"))
    assert (payload["skill_name"], payload["upstream_moved"], payload["upstream_ref"], payload["next_workflow"]) == (
        "demo", True, "v2", "update-skill")


def test_an_unquoted_ref_reaches_the_envelope_as_written(tmp_path):
    """The model writes the frontmatter: an unquoted tag such as 1.10 stays
    1.10, the --target-ref update-skill is handed, never the number 1.1."""
    text = "---\nskill_name: demo\naudit_ref: 1.10\nupstream_moved: true\nupstream_ref: 2.10\n---\n"
    run = Run(tmp_path, None, _severity("CLEAN", 0), report_text=text)
    proc = run.build()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(run.output.read_text(encoding="utf-8"))
    assert (payload["audit_ref"], payload["upstream_ref"]) == ("1.10", "2.10")
    envelope = run.emit()
    assert (envelope["audit_ref"], envelope["upstream_ref"]) == ("1.10", "2.10")


# --------------------------------------------------------------------------
# The resolver warning: report §1b's command as written
# --------------------------------------------------------------------------


def _section_1b() -> str:
    return _slice(_read(REPORT), "### 1b. Build the Result Context", "### 2.")


def _filled(run: Run, keep_reason: bool) -> str:
    command = _fenced(_section_1b(), "{resultContextScript}")
    option = re.search(r" \[(--resolver-unavailable [^\]]+)\]", command)
    assert option, command
    command = command.replace(option.group(0), f" {option.group(1)}" if keep_reason else "")
    command = command.replace("uv run {resultContextScript}", f'"{sys.executable}" "{SCRIPT.as_posix()}"')
    for name, value in (("{outputFile}", run.report), ("{auditDataFolder}", run.data), ("{run_dir}", run.run_dir)):
        command = command.replace(name, value.as_posix())
    assert "{" not in command, command
    return command


@pytest.mark.skipif(not POSIX_BASH, reason="runs report §1b's command in a POSIX bash")
def test_a_hostile_reason_reaches_the_warning_verbatim(tmp_path):
    """§1b writes the reason to a file with a file write and passes the
    file's text: a quote, a backtick or `$( )` in it runs nothing."""
    run = Run(tmp_path, _front(), _severity("CLEAN", 0))
    (run.run_dir / "resolver-unavailable.txt").write_bytes((HOSTILE_REASON + "\n").encode("utf-8"))
    proc = subprocess.run(["bash", "-c", _filled(run, keep_reason=True)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=run.run_dir, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(run.output.read_text(encoding="utf-8"))
    assert payload["customization_resolver_unavailable"] == HOSTILE_REASON
    envelope = run.emit()
    assert envelope["warnings"] == [f"customization_resolver_unavailable: {HOSTILE_REASON}"]
    assert not (run.run_dir / "pwned").exists() and not (run.run_dir / "pwned2").exists()


@pytest.mark.skipif(not POSIX_BASH, reason="runs report §1b's command in a POSIX bash")
def test_no_reason_kept_means_no_warning(tmp_path):
    run = Run(tmp_path, _front(), _severity("CLEAN", 0))
    proc = subprocess.run(["bash", "-c", _filled(run, keep_reason=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "customization_resolver_unavailable" not in json.loads(run.output.read_text(encoding="utf-8"))
    assert "warnings" not in run.emit()


def test_a_blank_reason_is_dropped_and_a_padded_one_stripped(tmp_path):
    run = Run(tmp_path, _front(), _severity("CLEAN", 0))
    assert run.build("--resolver-unavailable", "  \n").returncode == 0
    assert "customization_resolver_unavailable" not in json.loads(run.output.read_text(encoding="utf-8"))
    assert run.build("--resolver-unavailable", "  no JSON\n").returncode == 0
    assert json.loads(run.output.read_text(encoding="utf-8"))["customization_resolver_unavailable"] == "no JSON"


# --------------------------------------------------------------------------
# What it refuses
# --------------------------------------------------------------------------


BAD_INPUTS = [
    pytest.param(None, _severity("CLEAN", 0), "# Drift Report\n", "no frontmatter", id="no-frontmatter"),
    pytest.param({"audit_ref": "v1"}, _severity("CLEAN", 0), None, "names no skill_name", id="no-skill-name"),
    pytest.param({"skill_name": ""}, _severity("CLEAN", 0), None, "names no skill_name", id="empty-skill-name"),
    pytest.param(None, _severity("CLEAN", 0), "", "no frontmatter", id="empty-report"),
    pytest.param(_front(), [], None, "is not a severity classification", id="severity-list"),
    pytest.param(_front(), b"{not json", None, "cannot be read", id="severity-not-json"),
    pytest.param(_front(), {**_severity("CLEAN", 0), "drift_score": None}, None, "holds no drift_score",
                 id="no-drift-score"),
    pytest.param(_front(), {k: v for k, v in _severity("CLEAN", 0).items() if k != "by_severity"}, None,
                 "holds no by_severity count", id="no-by-severity"),
    pytest.param(_front(), {**_severity("CLEAN", 0), "by_severity": {"CRITICAL": 0}}, None,
                 "holds no by_severity count", id="partial-by-severity"),
    pytest.param(_front(), {k: v for k, v in _severity("CLEAN", 0).items() if k != "total_findings"}, None,
                 "holds no total_findings count", id="no-total-findings"),
    pytest.param(_front(upstream_moved=True), _severity("CLEAN", 0), None,
                 "upstream_moved is true but upstream_ref is empty", id="moved-without-ref"),
]


@pytest.mark.parametrize("front,severity,report_text,needle", BAD_INPUTS)
def test_an_input_it_cannot_build_from_exits_1_and_writes_nothing(tmp_path, front, severity, report_text, needle):
    run = Run(tmp_path, front, severity, report_text=report_text)
    proc = run.build()
    assert proc.returncode == 1, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == "error" and needle in out["error"], out
    assert not run.output.exists()


@pytest.mark.parametrize("missing", ["report", "severity"])
def test_a_missing_input_names_its_file(tmp_path, missing):
    run = Run(tmp_path, _front() if missing != "report" else None, _severity("CLEAN", 0) if missing != "severity"
              else None)
    proc = run.build()
    assert proc.returncode == 1
    error = json.loads(proc.stdout)["error"]
    assert error.startswith("--report " if missing == "report" else "--classification "), error
    assert str(run.report if missing == "report" else run.severity) in error
    assert not run.output.exists()


def test_an_output_it_cannot_write_exits_1(tmp_path):
    run = Run(tmp_path, _front(), _severity("CLEAN", 0))
    run.output.mkdir()
    proc = run.build()
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["error"].startswith(f"--output {run.output} cannot be written")


def test_a_usage_error_exits_2_and_help_lists_the_options():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False)
    assert proc.returncode == 2
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, encoding="utf-8",
                          timeout=60, check=False)
    assert proc.returncode == 0
    for option in ("--report", "--classification", "--resolver-unavailable", "--output"):
        assert option in proc.stdout, option


def test_the_header_declares_python_3_11_and_pyyaml():
    head = _read(SCRIPT).split('"""', 1)[0]
    for line in ("# /// script", '# requires-python = ">=3.11"', '# dependencies = ["pyyaml"]'):
        assert line in head, line


def test_the_embedded_examples_hold():
    assert doctest.testmod(context, verbose=False).failed == 0


# --------------------------------------------------------------------------
# The route rule lives in the script, and the stages read its route
# --------------------------------------------------------------------------


def test_the_rule_has_one_statement_the_schema_agrees_with():
    rule = _flow(context.next_workflow.__doc__)
    assert rule.startswith('The route a finished audit hands on: "update-skill" when the saved classification counts '
                           "a CRITICAL or HIGH finding, or when upstream_moved is true")
    described = json.loads(_read(SCHEMA))["properties"]["next_workflow"]["description"]
    assert "a CRITICAL or HIGH finding, or when upstream_moved is true" in described
    # It reads the frontmatter with the renderer's reader, which sits beside it.
    assert '_sibling("render-drift-tables.py"' in _read(SCRIPT)


def test_report_1b_builds_the_payload_and_binds_the_route():
    assert "resultContextScript: 'scripts/build-result-context.py'" in _read(REPORT).split("\n---\n", 1)[0]
    section = _section_1b()
    assert _fenced(section, "{resultContextScript}") == COMMAND
    assert shlex.split(COMMAND)[:3] == ["uv", "run", "{resultContextScript}"]
    flow = _flow(section)
    for token in ("never by hand: `{resultContextScript}` (it resolves relative to the skill root) reads both, works "
                  "out `next_workflow` and writes the payload the Result Contract hands the emitter",
                  "first write it to `{run_dir}/resolver-unavailable.txt` with a file write, never `echo`",
                  "Bind `{next_workflow}` ← its JSON's `next_workflow` (`update-skill`, or null). Exit 2: correct "
                  "the command and run it again.",
                  "fix that value in {outputFile}'s frontmatter, or that file, and run the command once more",
                  'If it exits 1 again, HALT with **exit 4**, `halt_reason: "write-failed"`, phase '
                  "`report:result-contract`"):
        assert token in flow, token
    # §1b runs before the Workflow Recommendation, which reads its route.
    report = _read(REPORT)
    assert report.index("### 1b. Build the Result Context") < report.index("### Workflow Recommendation")


def test_the_stages_read_the_route_and_state_no_rule():
    report = _read(REPORT)
    recommendation = _slice(report, "### Workflow Recommendation", "### 3.")
    assert ("{IF {next_workflow} is update-skill:}\n**Recommended:** Run `[US] Update Skill`{ to apply the Priority "
            "Actions above, when that table has rows}.") in recommendation
    assert "{IF any CRITICAL or HIGH findings:}" not in report
    assert "- Set `nextWorkflow` to `{next_workflow}`, the route §1b bound (empty when it is null)" in report
    for path in sorted((AUDIT / "references").glob("*.md")) + [SKILL]:
        for line in _read(path).splitlines():
            if "next_workflow" in line or "nextWorkflow" in line:
                for rule in ("CRITICAL or HIGH", "by_severity", "`upstream_moved` is true", "upstream_moved` true"):
                    assert rule not in line, (path.name, line)
    contract = _flow(_read(HEADLESS))
    assert ("`next_workflow` is the route step 6's `scripts/build-result-context.py` works out, as the schema "
            "describes the field") in contract
    assert "step 6's result contract (the result payload cannot be built, or the emitter refuses it, twice)" in contract
    assert ("`build-result-context.py`, which step 6 runs to build the result payload and its route"
            in _flow(_read(SKILL)))
