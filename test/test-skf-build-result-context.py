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
- report.md's own commands (build, publish, emit) run as written, the build
  before the publish;
- a scored run's verdict fields must be the ones the scoring output settled:
  `testResult` its `effectiveResult`, else its `result`, with
  `pass-with-drift` for a pass under an overridden workspace drift; `score`
  its `totalScore`; `threshold` 80 after a threshold fallback, else its
  `threshold`; and the fallback fields its override group's. A mis-copied
  one exits 1 before the report takes its public name, and a scored run
  with no --score is a usage error, exit 2 (v4.0.0 quality gate run 1,
  determinism-3);
- an input it cannot read, or a report with no settled verdict, exits 1
  with a JSON error and writes nothing;
- a report, scored or blocked, whose `analysisConfidence` is not a source
  access compute-score.py knows exits 1 before the report takes its public
  name (#823).
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
import yaml
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
              "testMode": "'naive'", "hardGate": "'passed'", "analysisConfidence": "'full'", **front}
    text = "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "stepsCompleted: ['init']\n---\n# R\n"
    path = folder / f"test-report-demo-{RUN_ID}.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def _ledger(folder: Path, records: list[dict] | None = None) -> Path:
    path = folder / f"test-findings-{RUN_ID}.json"
    subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(path), "--stage", "coverage-check"],
                   input=json.dumps(records or []), capture_output=True, text=True, encoding="utf-8", check=True)
    return path


def _score(folder: Path, result: str = "PASS", **fields) -> Path:
    """compute-score.py's output: `result`, `totalScore` 84 and `threshold` 80 unless `fields` says
    otherwise, and the override group when `fields` holds one."""
    path = folder / "score.json"
    path.write_bytes(json.dumps({"result": result, "totalScore": 84, "threshold": 80,
                                 "activeCategories": ["exportCoverage", "externalValidation"],
                                 **fields}).encode("utf-8"))
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")


VERDICTS = [
    ("pass", "PASS", "PASS", 0, "export-skill"),
    ("pass-with-drift", "pass-with-drift", "PASS_WITH_DRIFT", 4, "update-skill"),
    ("fail", "FAIL", "FAIL", 2, "update-skill"),
    ("inconclusive", "INCONCLUSIVE", "INCONCLUSIVE", 3, None),
]
# testResult -> (the scoring output's result, the frontmatter workspaceDrift) that settle it
SETTLED_BY = {"pass": ("PASS", "ok"), "pass-with-drift": ("PASS", "overridden"), "fail": ("FAIL", "ok"),
              "inconclusive": ("INCONCLUSIVE", "ok")}


@pytest.mark.parametrize("test_result, verdict, result, exit_code, next_workflow", VERDICTS,
                         ids=[row[0] for row in VERDICTS])
def test_each_verdict_maps_once(tmp_path, test_result, verdict, result, exit_code, next_workflow):
    scored, drift = SETTLED_BY[test_result]
    report = _report(tmp_path, testResult=f"'{test_result}'", score="'87.5%'", threshold="'80%'",
                     workspaceDrift=f"'{drift}'")
    score = _score(tmp_path, scored, totalScore=87.5, inconclusiveReasons=["active_categories < 2"])
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
    payload = mod.build(str(report), str(ledger), str(_score(tmp_path, totalScore=91, threshold=90)),
                        health_check=False)
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


@pytest.mark.parametrize("front", [
    {"hardGate": "'blocked'", "testResult": "'fail'"},
    {"testResult": "'pass'", "score": "'84%'", "threshold": "'80%'"},
], ids=["blocked", "scored"])
@pytest.mark.parametrize("confidence", ["''", "'degraded'", None], ids=["empty", "degraded", "absent"])
def test_a_report_without_its_source_access_is_refused(tmp_path, front, confidence):
    """#823: a run the hard gate blocks records `analysisConfidence` too (step-hard-gate.md §3), so a report that
    holds no source access compute-score.py knows, blocked or scored, exits 1 and writes no payload."""
    out = tmp_path / "result-context.json"
    report = _report(tmp_path, **front, analysisConfidence=confidence)
    if confidence is None:
        report.write_bytes(report.read_bytes().replace(b"analysisConfidence: None\n", b""))
        assert b"analysisConfidence" not in report.read_bytes()
    proc = _run("--report", str(report), "--ledger", str(_ledger(tmp_path)), "--score", str(_score(tmp_path)),
                "--output", str(out))
    assert proc.returncode == 1, proc.stdout
    error = json.loads(proc.stdout)["error"]
    assert "analysisConfidence" in error and "records no source access" in error, error
    assert not out.exists()
    # each level compute-score.py scores by is one a report may record
    for level in ("full", "provenance-map", "metadata-only", "remote-only", "docs-only"):
        proc = _run("--report", str(_report(tmp_path, **front, analysisConfidence=f"'{level}'")), "--ledger",
                    str(_ledger(tmp_path)), "--score", str(_score(tmp_path)), "--output", str(out))
        assert proc.returncode == 0, proc.stdout


def test_a_missing_ledger_or_report_is_refused(tmp_path):
    report = _report(tmp_path, testResult="'pass'")
    proc = _run("--report", str(report), "--ledger", str(tmp_path / "gone.json"), "--output", str(tmp_path / "o"))
    assert proc.returncode == 1 and "--ledger" in json.loads(proc.stdout)["error"]
    proc = _run("--report", str(tmp_path / "gone.md"), "--ledger", str(_ledger(tmp_path)), "--output",
                str(tmp_path / "o"))
    assert proc.returncode == 1 and "--report" in json.loads(proc.stdout)["error"]


CASES = [
    ("pass", False, {}),
    ("pass", False, {"thresholdFallback": "true", "originalThreshold": "'90%'"}),
    ("inconclusive", False, {}),
    ("fail", True, {}),
]
# The scoring output of each case: the fallback turned the script's FAIL into a PASS at the 80 floor.
SCORED = [
    {"result": "PASS"},
    {"result": "FAIL", "effectiveResult": "PASS", "capReason": None, "thresholdFallback": True,
     "originalThreshold": 90, "threshold": 90},
    {"result": "INCONCLUSIVE"},
    None,
]


@pytest.mark.parametrize("test_result, blocked, extra, scored", [(*case, s) for case, s in zip(CASES, SCORED)],
                         ids=["pass", "fallback", "inconclusive", "blocked"])
def test_every_payload_passes_the_emitter_and_writes_the_result_files(tmp_path, test_result, blocked, extra, scored):
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-test-skill-{RUN_ID}"
    forge_version.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    report = _report(forge_version, testResult=f"'{test_result}'", hardGate="'blocked'" if blocked else "'passed'",
                     score="'84%'" if not blocked else "''", threshold="'80%'", **extra)
    args = ["--report", str(report), "--ledger", str(_ledger(forge_version)), "--output",
            str(run_dir / "result-context.json")]
    if not blocked:
        args += ["--score", str(_score(run_dir, **scored))]
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


# Cap 1 (tooling not ok) forced the script's PASS into FAIL; a report that copied `result` says pass.
CAPPED = {"result": "PASS", "effectiveResult": "FAIL", "capReason": "Cap 1: toolingStatus frontmatter-validator-timeout",
          "thresholdFallback": False, "originalThreshold": None, "totalScore": 84, "threshold": 80}


@pytest.mark.parametrize("test_result, scored", [("fail", {"result": "FAIL", "totalScore": 71}), ("pass", CAPPED)],
                         ids=["settled", "mis-copied"])
def test_the_report_steps_commands_run_as_written(tmp_path, test_result, scored):
    """report.md §4c: build the payload from the hidden report, publish the report, emit the payload.
    The build comes first, so a mis-copied verdict halts while the report keeps its in-progress name."""
    text = REPORT_STEP.read_text(encoding="utf-8")
    contract = text[text.index("### 4c. Result Contract"):text.index("### 6. Present Final Report")]
    assert (contract.index("uv run {resultContextScript}") < contract.index('mv "{report_file}"')
            < contract.index("emit --workflow skf-test-skill --run-dir"))
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-test-skill-{RUN_ID}"
    forge_version.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    hidden = forge_version / f".skf-test-report-demo-{RUN_ID}.md"
    published = forge_version / f"test-report-demo-{RUN_ID}.md"
    _report(forge_version, testResult=f"'{test_result}'", score=f"'{scored['totalScore']}%'", threshold="'80%'",
            toolingStatus="'frontmatter-validator-timeout'").rename(hidden)
    values = {"{report_file}": hidden.as_posix(), "{publishedReportFile}": published.as_posix(),
              "{ledgerFile}": _ledger(forge_version).as_posix(), "{run_dir}": run_dir.as_posix(),
              "{forge_version}": forge_version.as_posix(), "{emit_target}": "stdout"}
    _score(run_dir, **scored)

    def fill(command: str) -> list[str]:
        # `uv run {script}` stands for this Python running the script; the rest is filled in.
        command = re.sub(r"^uv run \{\w+\}", "uv run script", command)
        for key, value in values.items():
            command = command.replace(key, value)
        assert not re.search(r"\{\w+\}", command), command
        return shlex.split(command)

    build = _fenced(text, "uv run {resultContextScript}")
    build = re.sub(r" \[(--score [^\]]+)\]", r" \1", build).replace(" [--no-health-check]", "")
    # SKILL.md On Activation kept the resolver's failure: report.md writes it to a file, whose text the
    # command substitution passes as one argument; it reaches the line.
    build = re.sub(r" \[(--warning [^\]]+)\]", r" \1", build)
    build = build.replace('"$(cat "{run_dir}/resolver-warning.txt")"',
                          shlex.quote("customization_resolver_unavailable: resolve_customization.py not found"))
    built = subprocess.run([sys.executable, str(SCRIPT), *fill(build)[3:]], capture_output=True, text=True,
                           encoding="utf-8")
    if test_result == "pass":
        # The HALT comes before the move: export-skill never finds the report, nor a result file.
        error = json.loads(built.stdout)["error"]
        assert built.returncode == 1 and "testResult 'pass' where it settles 'fail'" in error
        assert hidden.is_file() and not published.exists() and not (run_dir / "result-context.json").exists()
        assert not list(forge_version.glob("skf-test-skill-result-*.json"))
        return
    assert built.returncode == 0, built.stdout
    assert json.loads(built.stdout)["exit_code"] == 2
    move = fill(_fenced(text, 'mv "{report_file}"'))
    Path(move[1]).rename(move[2])
    values["{report_file}"] = values["{publishedReportFile}"]
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


@pytest.mark.parametrize("front, scored, copied, settled, verdict", [
    # Cap 1 fired on degraded tooling: the settled verdict is effectiveResult, never result.
    ({"toolingStatus": "'frontmatter-validator-timeout'"}, CAPPED, "pass", "fail", ("FAIL", 2)),
    # --allow-workspace-drift on a drifted tree: a PASS is conditional, an INCONCLUSIVE stays one.
    ({"workspaceDrift": "'overridden'"}, {"result": "PASS"}, "pass", "pass-with-drift", ("pass-with-drift", 4)),
    ({"workspaceDrift": "'overridden'"}, {"result": "INCONCLUSIVE"}, "pass-with-drift", "inconclusive",
     ("INCONCLUSIVE", 3)),
    # The threshold fallback accepted the run at the 80 floor.
    ({"thresholdFallback": "true", "originalThreshold": "'90%'"},
     {"result": "FAIL", "effectiveResult": "PASS", "capReason": None, "thresholdFallback": True,
      "originalThreshold": 90, "threshold": 90}, "fail", "pass", ("PASS", 0)),
], ids=["capped-pass", "drift-pass", "drift-inconclusive", "fallback-fail"])
def test_only_the_verdict_the_scoring_output_settled_is_built(tmp_path, front, scored, copied, settled, verdict):
    """determinism-3: the verdict the pipeline branches on is checked against compute-score.py's output.
    A mis-copied testResult exits 1 and writes nothing; the settled one builds."""
    out = tmp_path / "result-context.json"
    score = _score(tmp_path, **scored)
    report = _report(tmp_path, testResult=f"'{copied}'", score="'84%'", threshold="'80%'", **front)
    proc = _run("--report", str(report), "--ledger", str(_ledger(tmp_path)), "--score", str(score),
                "--output", str(out))
    assert proc.returncode == 1, proc.stdout
    error = json.loads(proc.stdout)["error"]
    assert "disagrees with the scoring output" in error
    assert f"testResult {copied!r} where it settles {settled!r}" in error
    assert not out.exists()
    report = _report(tmp_path, testResult=f"'{settled}'", score="'84%'", threshold="'80%'", **front)
    payload = mod.build(str(report), str(_ledger(tmp_path)), str(score))
    assert (payload["verdict"], payload["exit_code"]) == verdict


# A field score.md §7 copied by hand that the scoring output does not settle, beside the one it settles.
FALLBACK = {"result": "FAIL", "effectiveResult": "PASS", "capReason": None, "thresholdFallback": True,
            "originalThreshold": 90, "totalScore": 85, "threshold": 90}
FALLBACK_FRONT = {"thresholdFallback": "true", "originalThreshold": "'90%'", "threshold": "'80%'"}


@pytest.mark.parametrize("scored, front, wrong, envelope", [
    # The fallback accepted 85 against a 90 target at the 80 floor; the report kept the target and lost the flag.
    (FALLBACK, {"threshold": "'90%'"},
     ["threshold 90 where it settles 80", "thresholdFallback False where it settles True"],
     {"threshold": 80, "threshold_fallback": True, "original_threshold": 90}),
    (FALLBACK, {**FALLBACK_FRONT, "originalThreshold": "'95%'"}, ["originalThreshold 95 where it settles 90"],
     {"threshold": 80, "threshold_fallback": True, "original_threshold": 90}),
    ({"result": "PASS", "threshold": 80}, FALLBACK_FRONT, ["thresholdFallback True where it settles False"],
     {"threshold": 80}),
    ({"result": "PASS", "totalScore": 91.5}, {"score": "'95%'"}, ["score 95 where it settles 91.5"],
     {"score": 91.5}),
], ids=["fallback-target-threshold", "fallback-original-threshold", "fallback-claimed", "score"])
def test_the_score_threshold_and_fallback_the_scoring_output_settled_are_built(tmp_path, scored, front, wrong,
                                                                              envelope):
    """determinism-3: score.md §7 copies score, threshold and the fallback fields by hand too, and the envelope
    and campaign-quality-gate.py read them: a field the scoring output did not settle exits 1 and writes nothing."""
    out = tmp_path / "result-context.json"
    score = _score(tmp_path, **scored)
    fields = {"testResult": "'pass'", "score": f"'{scored.get('totalScore', 84)}%'", "threshold": "'80%'"}
    proc = _run("--report", str(_report(tmp_path, **{**fields, **front})), "--ledger", str(_ledger(tmp_path)),
                "--score", str(score), "--output", str(out))
    assert proc.returncode == 1, proc.stdout
    error = json.loads(proc.stdout)["error"]
    assert "disagrees with the scoring output" in error and all(w in error for w in wrong), error
    assert not out.exists()
    settled = {**fields, **(FALLBACK_FRONT if scored.get("thresholdFallback") else {})}
    payload = mod.build(str(_report(tmp_path, **settled)), str(_ledger(tmp_path)), str(score))
    assert {key: payload.get(key) for key in envelope} == envelope
    assert ("threshold_fallback" in payload) == ("threshold_fallback" in envelope)


def test_a_scored_run_needs_its_scoring_output(tmp_path):
    """Without --score there is nothing to check the verdict against: only a blocked run goes without.
    Leaving it out is a usage error (exit 2), which report.md has the caller correct and run again."""
    out = tmp_path / "result-context.json"
    report = _report(tmp_path, testResult="'pass'", score="'90%'", threshold="'80%'")
    proc = _run("--report", str(report), "--ledger", str(_ledger(tmp_path)), "--output", str(out))
    assert proc.returncode == 2 and "--score is required" in json.loads(proc.stdout)["error"]
    assert not out.exists()
    contract = " ".join(REPORT_STEP.read_text(encoding="utf-8").split())
    assert "Exit 2: correct the command and run it again. Exit 1: HALT with its `error`" in contract
    proc = _run("--report", str(report), "--ledger", str(_ledger(tmp_path)), "--score",
                str(_score(tmp_path, error="bad flag", code="INVALID_INPUT", result=None)), "--output", str(out))
    assert proc.returncode == 1 and "holds no verdict" in json.loads(proc.stdout)["error"]


def test_the_report_path_names_the_public_report(tmp_path):
    """report.md builds the payload from the in-progress report and names it by its public name."""
    hidden = _report(tmp_path, testResult="'pass'", score="'90%'", threshold="'80%'")
    public = (tmp_path / "public.md").as_posix()
    payload = mod.build(str(hidden), str(_ledger(tmp_path)), str(_score(tmp_path, totalScore=90)), report_path=public)
    assert payload["report_path"] == public
    assert payload["result_contract"]["outputs"] == [{"type": "report", "path": public}]
    blocked = _report(tmp_path, hardGate="'blocked'", testResult="'fail'")
    assert mod.build(str(blocked), str(_ledger(tmp_path)), report_path=public)["report_path"] == public


def test_kept_warnings_reach_the_envelope(tmp_path):
    """A warning the run kept (the customization resolver fallback, say) reaches the line and the files."""
    report = _report(tmp_path, testResult="'pass'", score="'90%'", threshold="'80%'")
    score = _score(tmp_path, totalScore=90)
    payload = mod.build(str(report), str(_ledger(tmp_path)), str(score),
                        warnings=["customization_resolver_unavailable: no python3", " "])
    assert payload["warnings"] == ["customization_resolver_unavailable: no python3"]
    assert "warnings" not in mod.build(str(report), str(_ledger(tmp_path)), str(score))


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


@pytest.mark.parametrize("case", ["capped", "capped-fail", "uncapped", "fallback", "blocked", "blank"])
def test_the_cap_reaches_the_summary_only_when_one_fired(tmp_path, case):
    """#1185: a capped FAIL names its cap in `summary.capReason`, so a caller restores the tooling instead of
    editing the skill; the exit code and next_workflow stay the FAIL's, and the envelope gains no field."""
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-test-skill-{RUN_ID}"
    forge_version.mkdir(parents=True)
    run_dir.mkdir(parents=True)
    front = {"testResult": "'fail'", "score": "'84%'", "threshold": "'80%'"}
    scored = {
        "capped": CAPPED,
        # a cap fired on a run that failed its threshold anyway: the cap is still named
        "capped-fail": {**CAPPED, "result": "FAIL", "totalScore": 71},
        "uncapped": {"result": "FAIL", "totalScore": 71},
        "fallback": FALLBACK,
        "blocked": None,
        "blank": {**CAPPED, "capReason": "  "},
    }[case]
    if case in ("capped-fail", "uncapped"):
        front["score"] = "'71%'"
    if case == "fallback":
        front = {"testResult": "'pass'", "score": "'85%'", **FALLBACK_FRONT}
    if case == "blocked":
        front = {"hardGate": "'blocked'", "testResult": "'fail'"}
    report = _report(forge_version, **front)
    score = str(_score(run_dir, **scored)) if scored else None
    payload = mod.build(str(report), str(_ledger(forge_version)), score)
    summary = payload["result_contract"]["summary"]
    if case in ("capped", "capped-fail"):
        assert summary["capReason"] == CAPPED["capReason"]
    else:
        assert "capReason" not in summary
    assert "capReason" not in payload and "capReason" not in payload["result_contract"]
    if case != "fallback":
        assert (payload["exit_code"], payload["next_workflow"]) == (2, "update-skill")
    (run_dir / "result-context.json").write_bytes(json.dumps(payload).encode("utf-8"))
    target = "stderr" if case == "blocked" else "stdout"
    emitted = subprocess.run(
        [sys.executable, str(EMITTER), "emit", "--workflow", "skf-test-skill", "--run-dir", str(run_dir),
         "--result-dir", str(forge_version), "--target", target],
        input=(run_dir / "result-context.json").read_text(encoding="utf-8"),
        capture_output=True, text=True, encoding="utf-8")
    assert emitted.returncode == 0, emitted.stderr
    line = (emitted.stderr if case == "blocked" else emitted.stdout).strip()
    envelope = json.loads(line.split(": ", 1)[1])
    assert not list(Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).iter_errors(envelope))
    latest = json.loads((forge_version / "skf-test-skill-result-latest.json").read_text(encoding="utf-8"))
    assert latest["summary"].get("capReason") == summary.get("capReason")


# ---------------------------------------------------------------------------
# settle (#1186): score.md §6 writes the verdict fields and the Completeness
# Score section by script, so the model types no verdict field.
# ---------------------------------------------------------------------------

SCORE_STEP = TS / "references" / "score.md"
TEMPLATE = TS / "templates" / "test-report-template.md"
COMPUTE_SCORE = TS / "scripts" / "compute-score.py"
compute = _load("skf_compute_score_for_settle_test", COMPUTE_SCORE)
CATEGORIES = ("exportCoverage", "signatureAccuracy", "typeCoverage", "coherence", "externalValidation")
VERDICT_KEYS = ("testResult", "score", "threshold", "nextWorkflow")
FALLBACK_KEYS = ("thresholdFallback", "originalThreshold")


def _settle_report(folder: Path, crlf: bool = False, **front: str) -> Path:
    """The report init.md §6c creates from the template, filled as the stages before score.md leave it."""
    fields = {"skillName": "'demo'", "runId": f"'{RUN_ID}'", "testMode": "'contextual'", "forgeTier": "'Deep'",
              "hardGate": "'passed'", "threshold": "'80%'", "thresholdSource": "'bundled default (80%)'",
              "analysisConfidence": "'full'", "docsOnly": "false", "toolingStatus": "'ok'",
              "workspaceDrift": "'ok'", **front}
    text = TEMPLATE.read_text(encoding="utf-8")
    for key, value in fields.items():
        text, n = re.subn(rf"(?m)^{key}: .*$", f"{key}: {value}", text, count=1)
        if not n:
            text = text.replace("\n---\n", f"\n{key}: {value}\n---\n", 1)
    if crlf:
        text = text.replace("\n", "\r\n")
    path = folder / f".skf-test-report-demo-{RUN_ID}.md"
    path.write_bytes(text.encode("utf-8"))
    return path


def _scored(folder: Path, threshold: float = 80, tooling: str = "ok", **inp) -> Path:
    """compute-score.py's own output for a contextual Deep run whose every category scores `inp['all']`, else the
    input `inp` gives."""
    every = inp.pop("all", 91.5)
    data = {"mode": "contextual", "tier": "Deep", "threshold": threshold, "toolingStatus": tooling,
            "scores": dict.fromkeys(CATEGORIES, every), **inp}
    path = folder / "score.json"
    path.write_bytes(json.dumps(compute.compute_score(data)).encode("utf-8"))
    return path


def _external(folder: Path, tools: list[str] | None = None) -> Path:
    path = folder / "external.json"
    path.write_bytes(json.dumps({"externalScore": 88.0, "toolsUsed": ["skill-check"] if tools is None else tools,
                                 "available": True}).encode("utf-8"))
    return path


def _settle(report: Path, score: Path, external: Path, *extra: str):
    return _run("settle", "--report", str(report), "--score", str(score), "--external", str(external), *extra)


def _front_lines(report: Path) -> dict[str, str]:
    """Each top-level key line of the report's frontmatter, as written."""
    head = report.read_bytes().decode("utf-8").lstrip("\ufeff").split("---", 2)[1]
    return {line.split(":", 1)[0]: line.rstrip("\r") for line in head.split("\n") if re.match(r"^\w+:", line)}


def _builds(tmp_path: Path, report: Path, score: Path) -> dict:
    """report.md §4c's build over the settled report: it checks every verdict field against the scoring output."""
    out = tmp_path / "result-context.json"
    proc = _run("--report", str(report), "--ledger", str(_ledger(tmp_path)), "--score", str(score),
                "--output", str(out))
    assert proc.returncode == 0, proc.stdout
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case, front, score_args, expected, envelope", [
    ("plain-pass", {}, {"all": 91.5},
     {"testResult": "'pass'", "score": "'91.5%'", "threshold": "'80%'", "nextWorkflow": "'export-skill'"},
     ("PASS", 0, "export-skill")),
    # 87.37 was the copying slip that halted report.md §4c as `87.4%`
    ("two-decimals", {}, {"all": 87.37},
     {"testResult": "'pass'", "score": "'87.37%'", "threshold": "'80%'", "nextWorkflow": "'export-skill'"},
     ("PASS", 0, "export-skill")),
    ("capped-fail", {"toolingStatus": "'frontmatter-validator-timeout'"},
     {"all": 91.5, "tooling": "frontmatter-validator-timeout"},
     {"testResult": "'fail'", "score": "'91.5%'", "threshold": "'80%'", "nextWorkflow": "'update-skill'"},
     ("FAIL", 2, "update-skill")),
    ("fallback", {"threshold": "'90%'"}, {"all": 85, "threshold": 90},
     {"testResult": "'pass'", "score": "'85%'", "threshold": "'80%'", "nextWorkflow": "'export-skill'",
      "thresholdFallback": "true", "originalThreshold": "'90%'"},
     ("PASS", 0, "export-skill")),
    ("drift", {"workspaceDrift": "'overridden'"}, {"all": 91.5},
     {"testResult": "'pass-with-drift'", "score": "'91.5%'", "threshold": "'80%'", "nextWorkflow": "'update-skill'"},
     ("pass-with-drift", 4, "update-skill")),
    ("inconclusive", {"testMode": "'naive'", "forgeTier": "'Quick'"},
     {"mode": "naive", "tier": "Quick", "scores": {**dict.fromkeys(CATEGORIES), "exportCoverage": 95}},
     {"testResult": "'inconclusive'", "score": "'95%'", "threshold": "'80%'", "nextWorkflow": "'manual-review'"},
     ("INCONCLUSIVE", 3, None)),
])
def test_settle_writes_the_verdict_fields_the_build_then_accepts(tmp_path, case, front, score_args, expected,
                                                                  envelope):
    """Each verdict field comes from the scoring output: settle writes it in place, and the no-subcommand build
    that report.md §4c runs exits 0 on what it wrote."""
    report = _settle_report(tmp_path, **front)
    before = report.read_bytes()
    score = _scored(tmp_path, **score_args)
    proc = _settle(report, score, _external(tmp_path))
    assert proc.returncode == 0, proc.stderr
    lines = _front_lines(report)
    for key, value in expected.items():
        assert lines[key] == f"{key}: {value}", (key, lines[key])
    if "thresholdFallback" not in expected:
        assert not set(lines) & set(FALLBACK_KEYS)
    # #1190: settle records no evidence report path, so the report names none
    assert "evidenceReportPath" not in lines
    # every line but the verdict fields is kept, in its place; the fallback keys come before the closing ---.
    # Keys compare whole: `thresholdSource` is no `threshold` line, and settle keeps it.
    kept = [line for line in before.decode("utf-8").split("\n") if line.split(":", 1)[0] not in VERDICT_KEYS]
    now = report.read_bytes().decode("utf-8").split("\n")
    assert [line for line in now if line.split(":", 1)[0] not in VERDICT_KEYS + FALLBACK_KEYS] == kept
    assert "stepsCompleted: []" in now and "analysisConfidence: 'full'" in now
    assert lines["thresholdSource"] == "thresholdSource: 'bundled default (80%)'"
    section = proc.stdout
    assert section.startswith("## Completeness Score\n\n### Score Breakdown\n")
    result = {"PASS": "PASS", "FAIL": "FAIL", "pass-with-drift": "PASS_WITH_DRIFT",
              "INCONCLUSIVE": "INCONCLUSIVE"}[envelope[0]]
    assert f"**Result:** **{result}**\n" in section
    payload = _builds(tmp_path, report, score)
    assert (payload["verdict"], payload["exit_code"], payload["next_workflow"]) == envelope
    if case == "capped-fail":
        cap = json.loads(score.read_text(encoding="utf-8"))["capReason"]
        assert f"**Result:** **FAIL**\n**Cap:** {cap}\n" in section
    # #1190: the Result block carries no fallback line; after a fallback, settle's output ends with the subsection
    # (score.md §6 adds its Access Degradation Notice after that output on a degraded run)
    assert "**Threshold Fallback:**" not in section and "Evidence report" not in section
    if case == "fallback":
        assert payload["threshold_fallback"] is True and payload["original_threshold"] == 90
        assert "evidence_report_path" not in json.dumps(payload)
        result_block = section[section.index("### Result\n"):section.index("### Threshold Fallback\n")]
        assert result_block.endswith("**Tooling Status:** ok\n\n")
        assert section.endswith("### Threshold Fallback\n\n**Attempted Threshold:** 90%\n**Achieved Score:** 85%\n"
                                "**Accepted At:** 80% floor\n**Threshold Source:** bundled default (80%)\n"
                                "**Prior Test Report:** none found beside this report\n"
                                "**Findings:** the Gap Report lists this run's gaps; address them to reach the 90% "
                                "target\n")
    else:
        assert "### Threshold Fallback" not in section
    if case == "plain-pass":
        # a contextual run in which every category scored keeps its full weights
        assert "\n**Weight Distribution:** contextual (full)\n" in section
    if case == "drift":
        assert f"**Scoring Notes:** {mod.DRIFT_NOTE}\n" in section
    if case == "inconclusive":
        assert ("**Result:** **INCONCLUSIVE**\n**Inconclusive Reasons:**\n"
                "- insufficient evidence: only 1 active category\n\n") in section


def test_settle_removes_the_fallback_keys_a_run_without_one_left(tmp_path):
    """A rerun whose earlier score fell back: the two keys go, so build finds no fallback the output never settled.
    #1190: an `evidenceReportPath` an older run wrote is neither settle's to remove nor build's to read."""
    old = "evidenceReportPath: 'f/evidence-report-fallback.md'"
    report = _settle_report(tmp_path, thresholdFallback="true", originalThreshold="'90%'",
                            evidenceReportPath="'f/evidence-report-fallback.md'")
    assert set(FALLBACK_KEYS) <= set(_front_lines(report))
    score = _scored(tmp_path)
    proc = _settle(report, score, _external(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert not set(FALLBACK_KEYS) & set(_front_lines(report))
    assert _front_lines(report)["evidenceReportPath"] == old
    assert "### Threshold Fallback" not in proc.stdout
    payload = _builds(tmp_path, report, score)
    assert "threshold_fallback" not in payload and "evidence_report_path" not in json.dumps(payload)


def test_settle_keeps_a_crlf_report_crlf(tmp_path):
    report = _settle_report(tmp_path, crlf=True)
    report.write_bytes(b"\xef\xbb\xbf" + report.read_bytes())
    score = _scored(tmp_path, all=85, threshold=90)
    proc = _settle(report, score, _external(tmp_path))
    assert proc.returncode == 0, proc.stderr
    raw = report.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf---\r\n")
    assert b"\n" not in raw.replace(b"\r\n", b"")
    assert b"score: '85%'\r\n" in raw
    assert b"thresholdFallback: true\r\noriginalThreshold: '90%'\r\n---\r\n" in raw
    assert _builds(tmp_path, report, score)["threshold"] == 80


@pytest.mark.parametrize("case, code, error", [
    ("refused-score", 1, "compute-score.py's refusal"),
    ("not-a-score", 1, "not compute-score.py's output: no input, weights, weightedScores"),
    ("no-tools", 1, "no toolsUsed list"),
    ("unknown-tool", 1, "names a tool combine-external-scores.py never uses"),
    ("missing-external", 1, "--external"),
    ("blocked", 1, "the hard gate blocked"),
    ("no-frontmatter", 1, "has no frontmatter"),
    ("unclosed-frontmatter", 1, "has no frontmatter"),
])
def test_settle_refuses_and_leaves_the_report_as_it_was(tmp_path, case, code, error):
    report = _settle_report(tmp_path, hardGate="'blocked'" if case == "blocked" else "'passed'")
    if case == "no-frontmatter":
        report.write_bytes(b"# Test Report: demo\n")
    if case == "unclosed-frontmatter":
        report.write_bytes(b"---\ntestResult: ''\nscore: ''\n# Test Report: demo\n")
    before = report.read_bytes()
    score = _scored(tmp_path)
    if case == "refused-score":
        score.write_bytes(json.dumps({"error": "threshold must be a number", "code": "INVALID_INPUT"}).encode())
    if case == "not-a-score":
        score.write_bytes(json.dumps({"result": "PASS", "totalScore": 91.5}).encode())
    external = _external(tmp_path)
    if case == "no-tools":
        external.write_bytes(json.dumps({"externalScore": None}).encode())
    if case == "unknown-tool":
        external = _external(tmp_path, ["skill-check", "linter"])
    if case == "missing-external":
        external = tmp_path / "gone.json"
    proc = _settle(report, score, external)
    assert proc.returncode == code, proc.stdout + proc.stderr
    assert proc.stdout == "" and len(proc.stderr.strip().splitlines()) == 1
    assert proc.stderr.startswith("error: ") and error in proc.stderr, proc.stderr
    assert report.read_bytes() == before


def test_a_failed_write_leaves_the_report_as_it_was(tmp_path, monkeypatch, capsys):
    """settle writes the report through a temp file beside it: a write that fails exits 1 with one error line, and
    leaves the report and no temp file behind."""
    report = _settle_report(tmp_path)
    before = report.read_bytes()
    score, external = _scored(tmp_path), _external(tmp_path)

    def refuse(src, dst):
        raise PermissionError(13, "Permission denied", str(dst))

    monkeypatch.setattr(mod.os, "replace", refuse)
    code = mod.main(["settle", "--report", str(report), "--score", str(score), "--external", str(external)])
    out, err = capsys.readouterr()
    assert code == 1 and out == "", out
    assert err.startswith("error: ") and len(err.strip().splitlines()) == 1, err
    assert report.read_bytes() == before
    assert not list(tmp_path.glob(".*.settle-*.tmp"))


def test_a_usage_error_is_exit_2():
    proc = _run("settle", "--report", "r.md")
    assert proc.returncode == 2 and "--score" in proc.stderr


def test_an_old_caller_passing_evidence_report_writes_nothing(tmp_path):
    """#1190: settle takes no --evidence-report, so a score.md that still passes it gets argparse's usage error (exit
    2), and the report keeps every byte, the fallback that would have fired included."""
    report = _settle_report(tmp_path, threshold="'90%'")
    before = report.read_bytes()
    proc = _settle(report, _scored(tmp_path, all=85, threshold=90), _external(tmp_path),
                   "--evidence-report", "f/evidence-report-fallback.md")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert proc.stdout == "" and "unrecognized arguments: --evidence-report" in proc.stderr
    assert report.read_bytes() == before


GOLDEN_SECTION = """## Completeness Score

### Score Breakdown

| Category | Score | Weight | Weighted |
|----------|-------|--------|----------|
| Export Coverage | 85% | 81.82% | 69.55% |
| Signature Accuracy | N/A | 0% | 0% |
| Type Coverage | N/A | 0% | 0% |
| Coherence | N/A | 0% | 0% |
| External Validation | 88% | 18.18% | 16% |
| **Total** | | **100%** | **85.55%** |

### Result

**Score:** 85.55%
**Threshold:** 80%
**Result:** **PASS_WITH_DRIFT**

**Threshold Source:** pipeline default (forge-auto → 80%)
**Weight Distribution:** naive (redistributed)
**Tier Adjustment:** none
**External Validators:** skill-check and Tessl Review
**Analysis Confidence:** provenance-map
**Tooling Status:** ok
**Scoring Notes:** State 2 undercount risk acknowledged: 10-point deduction applied to Export Coverage (raw: 95%, \
adjusted: 85%; provenance and metadata diverge by 40.0%); workspace drift overridden: the PASS is conditional; re-run \
against the pinned commit before export
"""


def test_settle_prints_the_golden_completeness_score_section(tmp_path):
    """A naive State 2 run under a drift override: the deducted Export Coverage, the skipped categories, both
    validators, the State 2 note and the drift note, every line from a file."""
    report = _settle_report(tmp_path, testMode="'naive'", forgeTier="'Forge'", workspaceDrift="'overridden'",
                            analysisConfidence="'provenance-map'", thresholdSource="'pipeline default (forge-auto → 80%)'")
    score = _scored(tmp_path, mode="naive", tier="Forge", state2=True, analysisConfidence="provenance-map",
                    scores={**dict.fromkeys(CATEGORIES), "exportCoverage": 95, "externalValidation": 88},
                    state2Counts={"provenance": 10, "metadata": 10, "union": 14})
    proc = _settle(report, score, _external(tmp_path, ["skill-check", "tessl"]))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == GOLDEN_SECTION
    assert _builds(tmp_path, report, score)["verdict"] == "pass-with-drift"


# #1190: the Design Notes golden, 85 against a CLI 90% target with one earlier report of the version.
GOLDEN_FALLBACK = """### Threshold Fallback

**Attempted Threshold:** 90%
**Achieved Score:** 85%
**Accepted At:** 80% floor
**Threshold Source:** CLI override (90%)
**Prior Test Report:** `test-report-demo-20260101T000000Z-ab12cd34.md`: an earlier test report of this version
**Findings:** the Gap Report lists this run's gaps; address them to reach the 90% target
"""
GOLDEN_PRIOR = "`test-report-demo-20260101T000000Z-ab12cd34.md`: an earlier test report of this version"


@pytest.mark.parametrize("earlier, prior", [
    # this run's own report keeps its hidden `.skf-` name, so a folder with no published report names none
    ([], None),
    (["test-report-demo-20260101T000000Z-ab12cd34.md"], "test-report-demo-20260101T000000Z-ab12cd34.md"),
    # each run id starts with its UTC time: the latest stamp wins, whatever order the folder lists
    (["test-report-demo-20260102T000000Z-bb.md", "test-report-demo-20260101T000000Z-aa.md"],
     "test-report-demo-20260102T000000Z-bb.md"),
    # an SKF 2.x name holds no stamp, so it ranks older than every stamped one, and a report kept under the
    # skill's name before a rename ranks by its stamp, not by that name
    (["test-report-demo.md", "test-report-zeta-20260103T000000Z-cc.md", "test-report-demo-20260102T000000Z-bb.md"],
     "test-report-zeta-20260103T000000Z-cc.md"),
    (["test-report-demo.md"], "test-report-demo.md"),
    # the same, with names whose plain order would put the 2.x one last
    (["test-report-demo.md", "test-report-alpha-20260103T000000Z-cc.md", "test-report-demo-20260102T000000Z-bb.md"],
     "test-report-alpha-20260103T000000Z-cc.md"),
], ids=["first-run", "one-earlier", "two-earlier", "legacy-and-renamed", "legacy-only", "legacy-and-renamed-from-a"])
def test_settle_records_the_fallback_in_its_own_subsection(tmp_path, earlier, prior):
    """#1190: a threshold fallback is recorded in the Completeness Score section, after the Result block's last
    line, and in no file of its own: the target, the raw score, the floor, the threshold source, the latest
    earlier test report beside this one and a pointer to the Gap Report."""
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    run_dir = tmp_path / "run"
    forge_version.mkdir(parents=True)
    run_dir.mkdir()
    for name in earlier:
        (forge_version / name).write_bytes(b"---\ntestResult: 'fail'\n---\n# R\n")
    # neither a drift report nor a folder holding a report's name, whose stamp would rank last, is a test report
    (forge_version / "drift-report-20260103T000000Z.md").write_bytes(b"# D\n")
    (forge_version / "test-report-demo-20991231T000000Z-zz.md").mkdir()
    report = _settle_report(forge_version, threshold="'90%'", thresholdSource="'CLI override (90%)'")
    score = _scored(run_dir, all=85, threshold=90)
    proc = _settle(report, score, _external(run_dir))
    assert proc.returncode == 0, proc.stderr
    line = f"`{prior}`: an earlier test report of this version" if prior else "none found beside this report"
    golden = GOLDEN_FALLBACK.replace(GOLDEN_PRIOR, line)
    assert proc.stdout.endswith("**Tooling Status:** ok\n\n" + golden), proc.stdout
    assert proc.stdout.count("### Threshold Fallback") == 1
    if earlier == ["test-report-demo-20260101T000000Z-ab12cd34.md"]:
        assert proc.stdout.endswith(GOLDEN_FALLBACK)
    assert not list(forge_version.glob("evidence-report*"))
    payload = _builds(tmp_path, report, score)
    assert (payload["threshold_fallback"], payload["original_threshold"], payload["threshold"]) == (True, 90, 80)
    summary = payload["result_contract"]["summary"]
    assert (summary["threshold_fallback"], summary["original_threshold"]) == (True, 90)
    assert "evidence_report_path" not in summary and "evidence_report_path" not in json.dumps(payload)


def test_the_fallback_subsection_follows_the_scoring_notes(tmp_path):
    """#1190: on a fallback run that also has Scoring Notes (the golden State 2 run under a drift override, against
    a 90% target), the notes stay the Result block's last line and the subsection follows them."""
    source = "'pipeline default (forge-auto → 90%)'"
    report = _settle_report(tmp_path, testMode="'naive'", forgeTier="'Forge'", workspaceDrift="'overridden'",
                            analysisConfidence="'provenance-map'", threshold="'90%'", thresholdSource=source)
    score = _scored(tmp_path, threshold=90, mode="naive", tier="Forge", state2=True,
                    analysisConfidence="provenance-map",
                    scores={**dict.fromkeys(CATEGORIES), "exportCoverage": 95, "externalValidation": 88},
                    state2Counts={"provenance": 10, "metadata": 10, "union": 14})
    proc = _settle(report, score, _external(tmp_path, ["skill-check", "tessl"]))
    assert proc.returncode == 0, proc.stderr
    subsection = ("\n### Threshold Fallback\n\n**Attempted Threshold:** 90%\n**Achieved Score:** 85.55%\n"
                  "**Accepted At:** 80% floor\n**Threshold Source:** pipeline default (forge-auto → 90%)\n"
                  "**Prior Test Report:** none found beside this report\n"
                  "**Findings:** the Gap Report lists this run's gaps; address them to reach the 90% target\n")
    assert proc.stdout == GOLDEN_SECTION.replace("forge-auto → 80%", "forge-auto → 90%") + subsection
    payload = _builds(tmp_path, report, score)
    assert (payload["verdict"], payload["threshold_fallback"], payload["original_threshold"]) == \
        ("pass-with-drift", True, 90)


def test_the_prior_report_is_never_the_report_settle_writes(tmp_path):
    """A report settle is given under its public name is never its own prior report."""
    report = tmp_path / f"test-report-demo-{RUN_ID}.md"
    report.write_bytes(b"---\n---\n")
    assert mod.prior_test_report(report) is None
    (tmp_path / "test-report-demo-20260101T000000Z-aa.md").write_bytes(b"---\n---\n")
    assert mod.prior_test_report(report) == "test-report-demo-20260101T000000Z-aa.md"


@pytest.mark.parametrize("names, latest", [
    # equal stamps rank by name
    (["test-report-zeta-20260101T000000Z-aa.md", "test-report-alpha-20260101T000000Z-aa.md"],
     "test-report-zeta-20260101T000000Z-aa.md"),
    # names without a stamp rank by name, below every stamped one
    (["test-report-demo.md", "test-report-alpha.md"], "test-report-demo.md"),
    (["test-report-zz.md", "test-report-aa-20200101T000000Z.md"], "test-report-aa-20200101T000000Z.md"),
    # a stamp followed by anything but `-`-joined letters and digits is no run id
    (["test-report-demo-20270101T000000Z-x_y.md", "test-report-demo-20260101T000000Z-aa.md"],
     "test-report-demo-20260101T000000Z-aa.md"),
    # review loop 1's probes: a pre-rename name and an SKF 2.x name rank by their stamps, not their names
    (["test-report-zeta-20250101T000000Z-aa.md", "test-report-alpha-20260101T000000Z-bb.md"],
     "test-report-alpha-20260101T000000Z-bb.md"),
    (["test-report-demo.md", "test-report-demo-20261101T000000Z-bb.md"], "test-report-demo-20261101T000000Z-bb.md"),
], ids=["equal-stamps", "no-stamps", "stamp-over-name", "not-a-run-id", "renamed", "legacy"])
def test_the_prior_report_ranks_by_its_run_id_stamp(tmp_path, names, latest):
    """#1190: the run-id stamp in a published report's name ranks it, not the name's plain order."""
    report = tmp_path / f".skf-test-report-demo-{RUN_ID}.md"
    report.write_bytes(b"---\n---\n")
    for name in names:
        (tmp_path / name).write_bytes(b"---\n---\n")
    assert mod.prior_test_report(report) == latest


@pytest.mark.parametrize("tools, label", [(["skill-check", "tessl"], "skill-check and Tessl Review"),
                                          (["skill-check"], "skill-check only"), (["tessl"], "Tessl Review only"),
                                          ([], "none: weight redistributed")])
def test_the_external_validators_line_names_the_tools_used(tmp_path, tools, label):
    report = _settle_report(tmp_path, forgeTier="'Quick'")
    score = _scored(tmp_path, tier="Quick")
    proc = _settle(report, score, _external(tmp_path, tools))
    assert proc.returncode == 0, proc.stderr
    assert f"\n**External Validators:** {label}\n" in proc.stdout
    assert "\n**Tier Adjustment:** Quick tier: signature and type coverage not scored\n" in proc.stdout


def test_score_md_settles_through_its_command_as_written(tmp_path):
    """score.md §6 runs settle as written and writes its output unchanged; §5 to §8 type no verdict field."""
    text = SCORE_STEP.read_text(encoding="utf-8")
    section6 = text[text.index("### 6. Write the Completeness Score Section"):text.index("### 7.")]
    command = _fenced(section6, "uv run {resultContextScript} settle")
    assert command.startswith("uv run {resultContextScript} settle ")
    assert "resultContextScript: 'scripts/build-result-context.py'" in text
    forge_version, run_dir = tmp_path / "forge" / "demo" / "1.0.0", tmp_path / "run"
    forge_version.mkdir(parents=True)
    run_dir.mkdir()
    report = _settle_report(forge_version, threshold="'90%'")
    score = _scored(run_dir, all=85, threshold=90)
    _external(run_dir)
    values = {"{outputFile}": report.as_posix(), "{run_dir}": run_dir.as_posix(),
              "{forge_version}": forge_version.as_posix()}
    command = command.removeprefix("uv run {resultContextScript} ")
    for key, value in values.items():
        command = command.replace(key, value)
    assert not re.search(r"\{\w+\}", command), command
    proc = subprocess.run([sys.executable, str(SCRIPT), *shlex.split(command)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("## Completeness Score\n")
    lines = _front_lines(report)
    assert lines["threshold"] == "threshold: '80%'" and lines["thresholdFallback"] == "thresholdFallback: true"
    assert "evidenceReportPath" not in lines
    # #1190: settle's output ends with the fallback subsection, and nothing else in the folder records it
    fallback = proc.stdout[proc.stdout.index("\n### Threshold Fallback\n"):]
    assert fallback.count("\n### ") == 1 and "**Prior Test Report:** none found beside this report\n" in fallback
    assert sorted(p.name for p in forge_version.iterdir()) == [report.name]
    payload = _builds(tmp_path, report, score)
    assert (payload["threshold_fallback"], payload["original_threshold"]) == (True, 90)
    assert "evidence_report_path" not in json.dumps(payload)
    flow = " ".join(section6.split())
    assert "write its output unchanged as the **Completeness Score** section" in flow
    assert '(`halt_reason: "helper-failed"`, phase `score:settle`)' in flow
    assert "Exit 2 is a usage error: correct the command and run it again." in flow
    assert "{N}%" not in section6 and "{total}" not in section6
    # The verdict fields are settle's alone: §5 to §8 name them, and type no value for any of them.
    after = text[text.index("### 5. Determine Next Workflow Recommendation"):]
    typed = re.findall(r"`(?:testResult|score|threshold|nextWorkflow|thresholdFallback|originalThreshold): [^`]*`",
                       after)
    assert typed == [], typed
