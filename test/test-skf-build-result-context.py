#!/usr/bin/env python3
"""Tests for src/skf-test-skill/scripts/build-result-context.py.

report.md §4c hands the shared emitter the payload this script builds from
the run's own records (#593, #587): the report frontmatter, the gap ledger
and the scoring output. These tests pin:

- the one table that maps `testResult` to the envelope's verdict, exit code
  and next workflow, and the result file's `summary.result` spelling;
- a run the hard gate blocked takes hard-gate.py's own payload;
- the fallback fields are present only when the threshold fallback fired;
- each payload the script writes passes through the shared emitter as
  `skf-test-skill`, validates against skf-test-result-envelope.v1.json, and
  writes the per-run record and its -latest copy in the version folder;
- report.md's own commands (publish, build, emit) run as written;
- an input it cannot read, or a report with no settled verdict, exits 1
  with a JSON error and writes nothing.
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
TS = ROOT / "src" / "skf-test-skill"
SCRIPT = TS / "scripts" / "build-result-context.py"
GAP_LEDGER = TS / "scripts" / "gap-ledger.py"
HARD_GATE = TS / "scripts" / "hard-gate.py"
EMITTER = ROOT / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
SCHEMA = ROOT / "src" / "shared" / "scripts" / "schemas" / "skf-test-result-envelope.v1.json"
REPORT_STEP = TS / "references" / "report.md"
RUN_ID = "20260601T120000Z-ab12cd34"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = _load("skf_build_result_context", SCRIPT)
hard_gate = _load("skf_hard_gate_for_context_test", HARD_GATE)


def test_embedded_doctests_pass():
    assert doctest.testmod(mod, verbose=False).failed == 0


def _report(folder: Path, **front: str) -> Path:
    fields = {"workflowType": "'test-skill'", "skillName": "'demo'", "runId": f"'{RUN_ID}'",
              "testMode": "'naive'", "hardGate": "'passed'", **front}
    text = "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "stepsCompleted: ['init']\n---\n# R\n"
    path = folder / f"test-report-demo-{RUN_ID}.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def _ledger(folder: Path, records: list[dict] | None = None) -> Path:
    path = folder / f"test-findings-{RUN_ID}.json"
    subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(path), "--stage", "coverage-check"],
                   input=json.dumps(records or []), capture_output=True, text=True, encoding="utf-8", check=True)
    return path


def _score(folder: Path, **fields) -> Path:
    path = folder / "score.json"
    path.write_bytes(json.dumps({"activeCategories": ["exportCoverage", "externalValidation"], **fields})
                     .encode("utf-8"))
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")


VERDICTS = [
    ("pass", "PASS", "PASS", 0, "export-skill"),
    ("pass-with-drift", "pass-with-drift", "PASS_WITH_DRIFT", 4, "update-skill"),
    ("fail", "FAIL", "FAIL", 2, "update-skill"),
    ("inconclusive", "INCONCLUSIVE", "INCONCLUSIVE", 3, None),
]


@pytest.mark.parametrize("test_result, verdict, result, exit_code, next_workflow", VERDICTS,
                         ids=[row[0] for row in VERDICTS])
def test_each_verdict_maps_once(tmp_path, test_result, verdict, result, exit_code, next_workflow):
    report = _report(tmp_path, testResult=f"'{test_result}'", score="'87.5%'", threshold="'80%'")
    score = _score(tmp_path, inconclusiveReasons=["active_categories < 2"])
    payload = mod.build(str(report), str(_ledger(tmp_path)), str(score))
    assert (payload["status"], payload["verdict"], payload["exit_code"], payload["next_workflow"],
            payload["halt_reason"]) == ("success", verdict, exit_code, next_workflow, None)
    assert (payload["score"], payload["threshold"]) == (87.5, 80)
    summary = payload["result_contract"]["summary"]
    assert summary["result"] == result and summary["hardGate"] == "passed"
    assert ("inconclusiveReasons" in summary) == (verdict == "INCONCLUSIVE")


def test_the_contract_carries_the_reports_records(tmp_path):
    report = _report(tmp_path, testResult="'pass'", score="'91%'", threshold="'90%'")
    ledger = _ledger(tmp_path, [{"severity": "Medium", "category": "structural", "title": "t", "source": "SKILL.md",
                                 "remediation": "Fix it."}])
    payload = mod.build(str(report), str(ledger), str(_score(tmp_path)), health_check=False)
    contract = payload["result_contract"]
    assert contract["skill"] == "skf-test-skill" and contract["runId"] == RUN_ID
    assert contract["outputs"] == [{"type": "report", "path": str(report)}]
    assert contract["healthCheckDispatched"] is False
    assert contract["summary"]["gapCounts"] == {"Critical": 0, "High": 0, "Medium": 1, "Low": 0, "Info": 0}
    assert contract["summary"]["activeCategories"] == ["exportCoverage", "externalValidation"]
    assert "threshold_fallback" not in payload and "threshold_fallback" not in contract["summary"]


def test_a_blocked_run_takes_the_hard_gates_payload(tmp_path):
    report = _report(tmp_path, hardGate="'blocked'", testResult="'fail'", thresholdFallback="true")
    payload = mod.build(str(report), str(_ledger(tmp_path)))
    contract = payload.pop("result_contract")
    assert payload == hard_gate.blocked_envelope("demo", str(report))
    assert contract["summary"]["result"] == "FAIL" and contract["summary"]["activeCategories"] == []
    assert contract["summary"]["score"] is None and "threshold_fallback" not in contract["summary"]


@pytest.mark.parametrize("front, error", [
    ({"testResult": "''"}, "holds no settled verdict"),
    ({"testResult": "'pass'", "score": "'high'"}, "not a percentage"),
], ids=["unscored", "bad-score"])
def test_a_report_without_a_settled_verdict_is_refused(tmp_path, front, error):
    out = tmp_path / "result-context.json"
    proc = _run("--report", str(_report(tmp_path, **front)), "--ledger", str(_ledger(tmp_path)),
                "--output", str(out))
    assert proc.returncode == 1 and error in json.loads(proc.stdout)["error"]
    assert not out.exists()


def test_a_missing_ledger_or_report_is_refused(tmp_path):
    report = _report(tmp_path, testResult="'pass'")
    proc = _run("--report", str(report), "--ledger", str(tmp_path / "gone.json"), "--output", str(tmp_path / "o"))
    assert proc.returncode == 1 and "--ledger" in json.loads(proc.stdout)["error"]
    proc = _run("--report", str(tmp_path / "gone.md"), "--ledger", str(_ledger(tmp_path)), "--output",
                str(tmp_path / "o"))
    assert proc.returncode == 1 and "--report" in json.loads(proc.stdout)["error"]


CASES = [
    ("pass", False, {}),
    ("pass", False, {"thresholdFallback": "true", "originalThreshold": "'90%'",
                     "evidenceReportPath": "'f/evidence-report-fallback.md'"}),
    ("inconclusive", False, {}),
    ("fail", True, {}),
]


@pytest.mark.parametrize("test_result, blocked, extra", CASES, ids=["pass", "fallback", "inconclusive", "blocked"])
def test_every_payload_passes_the_emitter_and_writes_the_result_files(tmp_path, test_result, blocked, extra):
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-test-skill-{RUN_ID}"
    forge_version.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    report = _report(forge_version, testResult=f"'{test_result}'", hardGate="'blocked'" if blocked else "'passed'",
                     score="'84%'" if not blocked else "''", threshold="'80%'", **extra)
    args = ["--report", str(report), "--ledger", str(_ledger(forge_version)), "--output",
            str(run_dir / "result-context.json")]
    if not blocked:
        args += ["--score", str(_score(run_dir))]
    built = _run(*args)
    assert built.returncode == 0, built.stdout
    target = json.loads(built.stdout)["target"]
    assert target == ("stderr" if blocked else "stdout")
    emitted = subprocess.run(
        [sys.executable, str(EMITTER), "emit", "--workflow", "skf-test-skill", "--run-dir", str(run_dir),
         "--result-dir", str(forge_version), "--target", target],
        input=(run_dir / "result-context.json").read_text(encoding="utf-8"),
        capture_output=True, text=True, encoding="utf-8")
    assert emitted.returncode == 0, emitted.stderr
    line = (emitted.stderr if blocked else emitted.stdout).strip()
    assert line.startswith("SKF_TEST_RESULT_JSON: ")
    envelope = json.loads(line.split(": ", 1)[1])
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert not list(Draft202012Validator(schema).iter_errors(envelope))
    assert envelope["run_id"] == RUN_ID
    names = sorted(p.name for p in forge_version.glob("skf-test-skill-result-*.json"))
    assert len(names) == 2 and "skf-test-skill-result-latest.json" in names
    assert re.fullmatch(r"skf-test-skill-result-\d{8}-\d{6}\.json", names[0]), names
    latest = json.loads((forge_version / "skf-test-skill-result-latest.json").read_text(encoding="utf-8"))
    assert latest["summary"]["result"] == ("FAIL" if blocked else {"pass": "PASS", "inconclusive": "INCONCLUSIVE"}
                                           [test_result])
    assert latest["run_id"] == RUN_ID and latest["runId"] == RUN_ID and "timestamp" in latest
    assert ("threshold_fallback" in envelope) == bool(extra)


def _fenced(text: str, needle: str) -> str:
    """The one line of a fenced block that holds `needle`."""
    for block in re.findall(r"```(?:bash)?\n(.*?)```", text, re.S):
        for line in block.splitlines():
            if needle in line:
                return line.strip()
    raise AssertionError(f"no fenced line holds {needle!r}")


def test_the_report_steps_commands_run_as_written(tmp_path):
    """report.md §4c: publish the hidden report, build the payload, emit it."""
    text = REPORT_STEP.read_text(encoding="utf-8")
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-test-skill-{RUN_ID}"
    forge_version.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    hidden = forge_version / f".skf-test-report-demo-{RUN_ID}.md"
    _report(forge_version, testResult="'fail'", score="'71%'", threshold="'80%'").rename(hidden)
    values = {"{report_file}": hidden.as_posix(),
              "{publishedReportFile}": (forge_version / f"test-report-demo-{RUN_ID}.md").as_posix(),
              "{ledgerFile}": _ledger(forge_version).as_posix(), "{run_dir}": run_dir.as_posix(),
              "{forge_version}": forge_version.as_posix(), "{emit_target}": "stdout"}
    _score(run_dir)

    def fill(command: str) -> list[str]:
        # `uv run {script}` stands for this Python running the script; the rest is filled in.
        command = re.sub(r"^uv run \{\w+\}", "uv run script", command)
        for key, value in values.items():
            command = command.replace(key, value)
        assert not re.search(r"\{\w+\}", command), command
        return shlex.split(command)

    move = fill(_fenced(text, 'mv "{report_file}"'))
    Path(move[1]).rename(move[2])
    values["{report_file}"] = values["{publishedReportFile}"]
    build = _fenced(text, "uv run {resultContextScript}")
    build = re.sub(r" \[(--score [^\]]+)\]", r" \1", build).replace(" [--no-health-check]", "")
    # SKILL.md On Activation kept the resolver's failure: report.md writes it to a file, whose text the
    # command substitution passes as one argument; it reaches the line.
    build = re.sub(r" \[(--warning [^\]]+)\]", r" \1", build)
    build = build.replace('"$(cat "{run_dir}/resolver-warning.txt")"',
                          shlex.quote("customization_resolver_unavailable: resolve_customization.py not found"))
    built = subprocess.run([sys.executable, str(SCRIPT), *fill(build)[3:]], capture_output=True, text=True,
                           encoding="utf-8")
    assert built.returncode == 0, built.stdout
    assert json.loads(built.stdout)["exit_code"] == 2
    emit = fill(_fenced(text, "emit --workflow skf-test-skill --run-dir"))
    source = emit.index("<")
    emitted = subprocess.run([sys.executable, str(EMITTER), *emit[3:source]],
                             input=Path(emit[source + 1]).read_text(encoding="utf-8"),
                             capture_output=True, text=True, encoding="utf-8")
    assert emitted.returncode == 0, emitted.stderr
    envelope = json.loads(emitted.stdout.split(": ", 1)[1])
    assert (envelope["verdict"], envelope["exit_code"], envelope["next_workflow"]) == ("FAIL", 2, "update-skill")
    assert envelope["report_path"] == values["{publishedReportFile}"]
    assert envelope["warnings"] == ["customization_resolver_unavailable: resolve_customization.py not found"]
    assert not hidden.exists() and Path(values["{publishedReportFile}"]).is_file()


def test_kept_warnings_reach_the_envelope(tmp_path):
    """A warning the run kept (the customization resolver fallback, say) reaches the line and the files."""
    report = _report(tmp_path, testResult="'pass'", score="'90%'", threshold="'80%'")
    payload = mod.build(str(report), str(_ledger(tmp_path)), str(_score(tmp_path)),
                        warnings=["customization_resolver_unavailable: no python3", " "])
    assert payload["warnings"] == ["customization_resolver_unavailable: no python3"]
    assert "warnings" not in mod.build(str(report), str(_ledger(tmp_path)), str(_score(tmp_path)))


def test_the_resolver_warning_has_a_producer():
    """SKILL.md On Activation keeps the resolver's failure, and report.md §4c hands that one warning on."""
    skill_md = (TS / "SKILL.md").read_text(encoding="utf-8")
    activation = re.sub(r"\s+", " ", skill_md[skill_md.index("3. **Resolve workflow customization.**"):])
    assert "keep the reason as `{customization_resolver_unavailable}`: report.md §4c hands it to the result" in activation
    text = REPORT_STEP.read_text(encoding="utf-8")
    command = _fenced(text, "uv run {resultContextScript}")
    # The reason reaches the command as a file's text, so a quote, a backtick or `$( )` in it runs nothing.
    assert '[--warning "$(cat "{run_dir}/resolver-warning.txt")"]' in command
    assert ("write `customization_resolver_unavailable: {customization_resolver_unavailable}` to "
            "`{run_dir}/resolver-warning.txt` with a file write, never `echo`") in text
    assert "<warning>" not in text
