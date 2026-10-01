#!/usr/bin/env python3
"""Contract of skf-verify-stack's envelope, halts, run folder, helpers and inputs (#587, #593, #594, #596, #598).

No test runs a stage file, so these run the commands the stage files document
and pin the prose around them:

- skf-verify-stack-result-envelope.v1.json is a valid JSON Schema whose emitter
  settings map each halt_reason to the exit code references/exit-codes.md
  gives, and whose halt_reason list is the one exit-codes.md names;
- every HALT the skill's Markdown names uses a halt_reason of the schema with
  its mapped exit code, and names its phase (an interactive cancel aside);
- every stage that halts binds the emitter in its own frontmatter, and
  exit-codes.md names the emitter's paths and leaves field meanings to the
  schema;
- every halt_reason, emitted through the documented emit-halt command (and the
  run-folder halt's heredoc, before the folder exists), prints a line that
  validates, whose run_id is the run's timestamp;
- the success payload report.md stages, emitted with --result-dir, writes the
  per-run and -latest result files, carries the gate decision init.md records,
  and passes the forger's circuit breaker; report.md creates the forge data
  folder first, or records why it could not, since the emitter writes nothing
  into a folder that is absent;
- the warnings the stages record are fixed codes the schema names, and they
  reach the envelope and the result file, a halt's envelope included;
- stages 1 to 5 write only {outputFile}; report.md copies it to
  {outputFileLatest} once, after the feasibility-report check;
- the documented pipeline runs on a fixture: the enumerate inventory in the run
  folder, --expect-hashes naming a skill changed mid-run, the SKILL.md scanner
  reading that inventory (source basenames as aliases) for Check 4, its
  citations file into the cycle finder as integrations.md calls it (rejected
  directions left out, two skills that cite each other no cycle), and the
  tally counting each cycle as a Risky row;
- a cycle row names `cycle` and its chain, so the delta never merges it into
  the pair row of two of its skills;
- a pair of one skill is dropped before the scanner and the tally, which both
  refuse it, and a pair whose skill changed mid-run is a Risky row;
- coverage finds the skills the document names, by name or source basename,
  through the shared mentions helper, and runs it again with each term the
  model matched to a skill under a common alias, so the integrations stage
  judges the candidate pairs of every Covered skill; the requirements stage
  reads the step 3 summaries, never a SKILL.md;
- the integration rules, the coverage patterns and the report folder are no
  customize.toml settings, the report template's comment names what the
  schema fixes, and a path a flag gave is never asked for again.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SKILL = SRC / "skf-verify-stack"
REFERENCES = SKILL / "references"
SCRIPTS = SRC / "shared" / "scripts"
SCHEMA_PATH = SCRIPTS / "schemas" / "skf-verify-stack-result-envelope.v1.json"
EMITTER = SCRIPTS / "skf-emit-result-envelope.py"
ENUMERATE = SCRIPTS / "skf-enumerate-stack-skills.py"
SCANNER = SCRIPTS / "skf-scan-skill-md-structure.py"
FIND_CYCLES = SCRIPTS / "skf-find-cycles.py"
COMENTION = SCRIPTS / "skf-comention-pairs.py"
REPORT_DELTA = SKILL / "scripts" / "skf-report-delta.py"
TALLY = SKILL / "scripts" / "skf-coverage-tally.py"
PIPELINE_GATE = SRC / "skf-forger" / "scripts" / "pipeline-gate.py"
EXIT_CODES = REFERENCES / "exit-codes.md"

PREFIX = "SKF_VERIFY_STACK_RESULT_JSON: "
RUN_STAMP = "20261001-101500"
EMIT_HALT = (
    'uv run {emitEnvelopeHelper} emit-halt --workflow skf-verify-stack --run-dir "{run_dir}" '
    '--target stderr < "{run_dir}/halt.json"'
)
# The stage files that write the report before the check passes, and the one
# that publishes it.
DRAFTING_STAGES = ("init.md", "coverage.md", "integrations.md", "requirements.md", "synthesize.md")
PHASE_PREFIX = {
    "SKILL.md": "on-activation",
    "init.md": "init",
    "coverage.md": "coverage",
    "integrations.md": "integrations",
    "requirements.md": "requirements",
    "synthesize.md": "synthesize",
    "report.md": "report",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _schema() -> dict:
    return json.loads(_read(SCHEMA_PATH))


def _settings() -> dict:
    return _schema()["$defs"]["skf-envelope"]["const"]


def _markdown() -> list[Path]:
    return [SKILL / "SKILL.md", *sorted(REFERENCES.glob("*.md"))]


def _section(text: str, start: str, end: str) -> str:
    at = text.index(start)
    return text[at:text.index(end, at + len(start))]


def _run(args, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, *[str(a) for a in args]],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _envelope(text: str) -> dict:
    [line] = [line for line in text.splitlines() if line.startswith(PREFIX)]
    return json.loads(line[len(PREFIX):])


def _validate(envelope: dict) -> None:
    jsonschema.Draft202012Validator(_schema()).validate(envelope)


# --- The schema and exit-codes.md agree ----------------------------------------------


def test_the_schema_is_valid_and_names_the_workflow():
    jsonschema.Draft202012Validator.check_schema(_schema())
    settings = _settings()
    assert settings["workflow"] == "skf-verify-stack"
    assert settings["prefix"] == PREFIX.rstrip(": ")
    assert settings["wrapper"] is None and settings["halt_status"] == "error"
    assert settings["result_file"] == "verify-stack-result"


def _exit_code_rows() -> dict[int, str]:
    rows = {}
    for line in _read(EXIT_CODES).splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|(.*)$", line)
        if m:
            rows[int(m.group(1))] = m.group(2)
    return rows


def test_each_halt_reason_sits_in_its_exit_code_row():
    rows = _exit_code_rows()
    assert sorted(rows) == [0, 2, 3, 4, 5, 6, 7]
    for reason, code in _settings()["exit_codes"].items():
        assert reason in rows[code], (reason, code)
    halt_enum = [r for r in _schema()["properties"]["halt_reason"]["enum"] if r is not None]
    assert sorted(halt_enum) == sorted(_settings()["exit_codes"])
    assert sorted(_schema()["properties"]["exit_code"]["enum"]) == [0, *sorted(set(_settings()["exit_codes"].values()))]


def test_exit_codes_md_names_the_fields_and_leaves_their_meaning_to_the_schema():
    text = _read(EXIT_CODES)
    envelope = _section(text, "## Result Envelope", "## Emitting a Halt")
    assert "skf-verify-stack-result-envelope.v1.json" in envelope
    assert set(_schema()["properties"]) <= set(re.findall(r"`([a-z_]+)`", envelope))
    # One field list, no restated meanings: the schema's descriptions hold them.
    assert not re.search(r"^- `[a-z_]+`:", text, re.M)


def _frontmatter(text: str) -> str:
    return text.split("\n---\n", 1)[0]


EMIT_PROBES = (
    "emitEnvelopeProbeOrder:\n"
    "  - '{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py'\n"
    "  - '{project-root}/src/shared/scripts/skf-emit-result-envelope.py'\n"
)


def test_each_stage_that_runs_the_emitter_binds_it_itself():
    # A late halt can run after a compaction dropped SKILL.md's binding.
    stages = [path for path in sorted(REFERENCES.glob("*.md"))
              if "{emitEnvelopeHelper}" in _read(path) and path != EXIT_CODES]
    assert {path.name for path in stages} == {
        "init.md", "coverage.md", "integrations.md", "requirements.md", "synthesize.md", "report.md"}
    for path in stages:
        text = _read(path)
        assert EMIT_PROBES in _frontmatter(text) + "\n", _rel(path)
        assert "resolve `{emitEnvelopeHelper}` from `{emitEnvelopeProbeOrder}` if it is not bound" in text, _rel(path)
    halt = _section(_read(EXIT_CODES), "## Emitting a Halt", "```bash")
    for line in EMIT_PROBES.splitlines()[1:]:
        candidate = line.split("'")[1]
        assert f"`{candidate}`" in halt, line
    assert "resolved at SKILL.md" not in _read(EXIT_CODES)


# --- Every HALT names a known reason, its code and its phase --------------------------

HALT_RE = re.compile(r'HALT(?: per the Workflow Rules)? \(exit code (\d+), `halt_reason: "([^"]+)"`\)([^\n]*)')


def _halts():
    for path in _markdown():
        for m in HALT_RE.finditer(_read(path)):
            yield path, int(m.group(1)), m.group(2), m.group(3)


def test_every_halt_uses_a_schema_reason_and_its_exit_code():
    mapping = _settings()["exit_codes"]
    found = list(_halts())
    assert len(found) >= 25, len(found)
    for path, code, reason, _ in found:
        assert reason in mapping, f"{_rel(path)}: unknown halt_reason {reason}"
        assert mapping[reason] == code, f"{_rel(path)}: {reason} exits {mapping[reason]}, not {code}"


def test_every_halt_names_its_phase():
    for path, _, reason, rest in _halts():
        if reason == "user-cancelled":
            continue  # an interactive cancel emits nothing
        if rest.startswith(" at the stage's phase"):
            assert path.name == "SKILL.md"  # the Workflow Rules helper rule
            continue
        m = re.match(r" at phase `([a-z-]+):([a-z0-9-]+)`", rest)
        assert m, f"{_rel(path)}: a {reason} HALT names no phase: {rest[:60]!r}"
        assert m.group(1) == PHASE_PREFIX[path.name], (_rel(path), m.group(0))


def test_each_halting_stage_carries_the_emit_halt_command():
    for path in _markdown():
        text = _read(path)
        if path.name in ("SKILL.md", "exit-codes.md") or not HALT_RE.search(text):
            continue
        assert "**Halt envelope.**" in text, _rel(path)
        assert EMIT_HALT in text, _rel(path)
    assert EMIT_HALT in _read(EXIT_CODES)


def test_no_stage_types_an_envelope_or_defers_it_to_skill_md():
    for path in [*_markdown(), *sorted((SKILL / "assets").glob("*.md"))]:
        text = _read(path)
        for stale in ("emit the error envelope", 'per SKILL.md "Result Contract (Headless)"',
                      "per **Result Contract (Headless)**", PREFIX + '{"'):
            assert stale not in text, f"{_rel(path)}: {stale!r}"


# --- The emitter builds each documented line ------------------------------------------


def _halt_payload(reason: str) -> dict:
    """The halt.json exit-codes.md documents, filled in."""
    shape = re.search(r'`(\{"phase": "<phase>", [^`]+\})`', _read(EXIT_CODES)).group(1)
    payload = json.loads(
        shape.replace("<phase>", "coverage:report")
        .replace("<the halt message>", "Cannot write the report")
        .replace("<halt_reason>", reason)
    )
    payload["report_path"] = "/forge/feasibility-report-app-20261001-101500.md"
    return payload


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "_bmad-output" / ".skf-run" / f"skf-verify-stack-{RUN_STAMP}"
    run_dir.mkdir(parents=True)
    return run_dir


@pytest.mark.parametrize("reason", sorted(json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["skf-envelope"]["const"]["exit_codes"]))
def test_each_halt_reason_emits_a_valid_line(tmp_path, reason):
    run_dir = _run_dir(tmp_path)
    (run_dir / "halt.json").write_bytes(json.dumps(_halt_payload(reason)).encode("utf-8"))
    proc = _run([EMITTER, "emit-halt", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--target", "stderr"],
                stdin=(run_dir / "halt.json").read_text(encoding="utf-8"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    envelope = _envelope(proc.stderr)
    _validate(envelope)
    assert envelope["status"] == "error" and envelope["halt_reason"] == reason
    assert envelope["exit_code"] == _settings()["exit_codes"][reason]
    assert envelope["run_id"] == RUN_STAMP
    assert envelope["report_latest_path"] is None and envelope["result_path"] is None
    assert envelope["error"]["phase"] == "coverage:report"


def test_the_run_folder_halt_emits_before_the_folder_exists():
    init = _read(REFERENCES / "init.md")
    m = re.search(r"<<'SKF_VS_HALT'\n\s*(\{.*\})\n\s*SKF_VS_HALT", init)
    assert m, "init.md shows the heredoc halt"
    assert '"phase": "init:run-folder"' in m.group(1)
    payload = m.group(1).replace("<the halt message>", "Cannot create the run folder")
    proc = _run([EMITTER, "emit-halt", "--workflow", "skf-verify-stack", "--target", "stderr"], stdin=payload)
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    _validate(envelope)
    assert (envelope["exit_code"], envelope["run_id"], envelope["report_path"]) == (4, None, None)


def _decision() -> str:
    init = _read(REFERENCES / "init.md")
    shape = re.search(r'`(\{"gate": "init\.previous-report", [^`]+\})`', init).group(1)
    return shape.replace("<previousReport>", "/forge/feasibility-report-app-20260930-110000.md")


RECORD_WARNING = 'uv run {emitEnvelopeHelper} record --run-dir "{run_dir}" --warning '


def _documented_warnings() -> list[str]:
    """The warnings the stages record in the run sink, in stage order."""
    coverage = _read(REFERENCES / "coverage.md")
    assert RECORD_WARNING + "'<the warning to record>'" in coverage
    found = re.findall(r"Record `([a-z_]+: [^`]+)`", coverage)
    for name in ("integrations.md", "report.md"):
        found += re.findall(re.escape(RECORD_WARNING) + r"'([a-z_]+: [^']+)'", _read(REFERENCES / name))
    return found


def test_each_documented_warning_is_a_fixed_code():
    warnings = _documented_warnings()
    assert [w.split(":", 1)[0] for w in warnings] == [
        "no_technology_referenced", "no_live_technology", "zero_coverage",
        "skill_modified_mid_run", "all_pairs_blocked", "result_file_write_failed"]
    for warning in warnings:
        # Single-quoted on the command line: no quote, backtick or backslash inside.
        assert not set("'`\\\"") & set(warning), warning
    # The schema names each code in the envelope's warnings field.
    described = _schema()["properties"]["warnings"]["description"]
    for warning in warnings:
        assert warning.split(":", 1)[0] in described, warning


def test_the_zero_coverage_warning_matches_the_tally():
    # Each branch keys on a count of the coverage tally, so an architecture
    # that names no technology never reads as all-Replaced.
    proceed = _section(_read(REFERENCES / "coverage.md"), "### 7. Auto-Proceed", "```bash")
    branches = [line for line in proceed.splitlines() if line.startswith("- when ") or line.startswith("- otherwise")]
    assert [b.split(":", 1)[0] for b in branches] == [
        "- when `total_referenced` is 0", "- when `live_count` is 0 (every referenced technology is Replaced)",
        "- otherwise"]
    assert "no_technology_referenced" in branches[0] and "no_live_technology" in branches[1]


def _success_payload(forge: Path) -> dict:
    report = _read(REFERENCES / "report.md")
    block = re.search(r"Write `\{run_dir\}/result-context\.json`:\n\n```json\n(.*?)\n```", report, re.S).group(1)
    output_file = (forge / f"feasibility-report-app-{RUN_STAMP}.md").as_posix()
    latest = (forge / "feasibility-report-app-latest.md").as_posix()
    text = (block.replace("{outputFileLatest}", latest).replace("{outputFile}", output_file)
            .replace("<overallVerdict>", "CONDITIONALLY_FEASIBLE")
            .replace("<coveragePercentage>", "83").replace("<recommendationCount>", "4"))
    return json.loads(text)


def test_the_documented_success_payload_writes_the_result_files(tmp_path):
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "forge"
    forge.mkdir()
    record = _run([EMITTER, "record", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--decision"],
                  stdin=_decision())
    assert record.returncode == 0, record.stderr
    payload = _success_payload(forge)
    proc = _run([EMITTER, "emit", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--result-dir", forge],
                stdin=json.dumps(payload))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    _validate(envelope)
    assert envelope["status"] == "success" and envelope["exit_code"] == 0 and envelope["halt_reason"] is None
    assert (envelope["overall_verdict"], envelope["coverage_percentage"], envelope["recommendation_count"]) == (
        "CONDITIONALLY_FEASIBLE", 83, 4)
    assert envelope["run_id"] == RUN_STAMP
    assert [d["gate"] for d in envelope["headless_decisions"]] == ["init.previous-report"]
    per_run = [p for p in forge.glob("verify-stack-result-*.json") if not p.name.endswith("-latest.json")]
    assert len(per_run) == 1
    assert Path(envelope["result_path"]).as_posix() == per_run[0].as_posix()
    latest = json.loads((forge / "verify-stack-result-latest.json").read_text(encoding="utf-8"))
    assert latest["skill"] == "skf-verify-stack" and latest["run_id"] == RUN_STAMP
    assert latest["summary"] == {"overallVerdict": "CONDITIONALLY_FEASIBLE", "coveragePercentage": 83,
                                 "recommendationCount": 4}
    assert [o["path"] for o in latest["outputs"]] == [payload["report_path"], payload["report_latest_path"]]
    # The forger's circuit breaker reads the line as a finished VS run.
    gate = _run([PIPELINE_GATE, "--code", "VS"], stdin=proc.stdout)
    assert json.loads(gate.stdout)["decision"] == "continue"


def test_recorded_warnings_reach_the_envelope_and_the_result_file(tmp_path):
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "forge"
    forge.mkdir()
    warnings = _documented_warnings()
    for warning in warnings:
        record = _run([EMITTER, "record", "--run-dir", run_dir, "--warning", warning])
        assert record.returncode == 0, record.stderr
    proc = _run([EMITTER, "emit", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--result-dir", forge],
                stdin=json.dumps(_success_payload(forge)))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stdout)
    _validate(envelope)
    assert envelope["warnings"] == warnings
    latest = json.loads((forge / "verify-stack-result-latest.json").read_text(encoding="utf-8"))
    assert latest["warnings"] == warnings
    # A halt reports the warnings the run recorded before it.
    halt = _run([EMITTER, "emit-halt", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--target", "stderr"],
                stdin=json.dumps(_halt_payload("write-failed")))
    assert halt.returncode == 0, halt.stderr
    assert _envelope(halt.stderr)["warnings"] == warnings


def test_report_creates_the_result_folder_before_the_emitter_writes(tmp_path):
    contract = _section(_read(REFERENCES / "report.md"), "### 4b. Result Contract", "### 5. Finish")
    lines = re.search(r"```bash\n(.*?)\n```", contract, re.S).group(1).splitlines()
    mkdir, record = lines[0].split(" || ")
    assert mkdir == 'mkdir -p "{forge_data_folder}"'
    assert record.startswith(RECORD_WARNING + "'result_file_write_failed: ")
    assert lines[1].startswith("uv run {emitEnvelopeHelper} emit --workflow skf-verify-stack ")
    # Into a folder that does not exist the emitter writes no result file and
    # raises no warning, which is why the folder is created first, and why a
    # folder that cannot be created records the warning itself.
    run_dir = _run_dir(tmp_path)
    forge = tmp_path / "elsewhere" / "forge"
    args = [EMITTER, "emit", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--result-dir", forge]
    absent = _run(args, stdin=json.dumps(_success_payload(forge)))
    assert absent.returncode == 0, absent.stderr
    assert _envelope(absent.stdout)["result_path"] is None and "warnings" not in _envelope(absent.stdout)
    warning = re.search(r"--warning '([^']+)'", record).group(1)
    assert _run([EMITTER, "record", "--run-dir", run_dir, "--warning", warning]).returncode == 0
    recorded = _run(args, stdin=json.dumps(_success_payload(forge)))
    assert recorded.returncode == 0, recorded.stderr
    envelope = _envelope(recorded.stdout)
    assert (envelope["status"], envelope["result_path"], envelope["warnings"]) == ("success", None, [warning])
    forge.mkdir(parents=True)
    created = _run(args, stdin=json.dumps(_success_payload(forge)))
    assert created.returncode == 0, created.stderr
    assert Path(_envelope(created.stdout)["result_path"]).parent.as_posix() == forge.as_posix()
    assert (forge / "verify-stack-result-latest.json").is_file()


def test_the_halt_after_publishing_names_the_latest_copy(tmp_path):
    # Every other halt fires before report.md §1 publishes the -latest copy and
    # leaves it null; the result-contract halt comes after, so it names the copy.
    report = _read(REFERENCES / "report.md")
    contract = _section(report, "### 4b. Result Contract", "### 5. Finish")
    assert ('at phase `report:result-contract`, adding `"report_latest_path": "{outputFileLatest}"` '
            "to the halt payload") in contract
    assert report.index("**Publish the checked report.**") < report.index("### 4b. Result Contract")
    run_dir = _run_dir(tmp_path)
    payload = _halt_payload("write-failed")
    payload.update(phase="report:result-contract", report_latest_path="/forge/feasibility-report-app-latest.md")
    proc = _run([EMITTER, "emit-halt", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--target", "stderr"],
                stdin=json.dumps(payload))
    assert proc.returncode == 0, proc.stderr
    envelope = _envelope(proc.stderr)
    _validate(envelope)
    assert envelope["report_latest_path"] == "/forge/feasibility-report-app-latest.md"
    assert (envelope["status"], envelope["exit_code"]) == ("error", 4)


def test_the_circuit_breaker_halts_on_a_halt_line(tmp_path):
    run_dir = _run_dir(tmp_path)
    proc = _run([EMITTER, "emit-halt", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--target", "stderr"],
                stdin=json.dumps(_halt_payload("schema-violation")))
    gate = _run([PIPELINE_GATE, "--code", "VS"], stdin=proc.stderr)
    out = json.loads(gate.stdout)
    assert (out["decision"], out["reason"]) == ("halt", "schema-violation")


# --- -latest is written once, after the check -----------------------------------------


WRITE_FAILED = re.compile(r'\(exit code 4, `halt_reason: "write-failed"`\) at phase `([a-z]+):report`')


@pytest.mark.parametrize("name", DRAFTING_STAGES)
def test_stages_1_to_5_write_only_the_timestamped_report(name):
    text = _read(REFERENCES / name)
    assert "--target {outputFileLatest}" not in text
    assert '--target "{outputFileLatest}"' not in text
    writes = [m.start() for m in re.finditer(re.escape("write --target {outputFile}`"), text)]
    assert writes
    for at in writes:
        # Every write of the report names the write-failed halt right after it.
        halt = WRITE_FAILED.search(text, at, at + 700)
        assert halt, f"{name}: a report write at offset {at} has no write-failed halt"
        assert halt.group(1) == PHASE_PREFIX[name]
    # A stage that no longer writes the -latest copy keeps no path for it.
    frontmatter = text.split("\n---\n", 1)[0]
    if name != "init.md":
        assert "outputFileLatest:" not in frontmatter


def test_report_publishes_the_latest_copy_after_the_check():
    report = _read(REFERENCES / "report.md")
    copy = 'python3 {atomicWriteHelper} write --target "{outputFileLatest}" < "{outputFile}"'
    assert report.count(copy) == 1
    check = report.index('uv run {validateFeasibilityReportHelper} "{outputFile}" -o "{run_dir}/report-check.json"')
    violation = report.index('(exit code 5, `halt_reason: "schema-violation"`) at phase `report:check`')
    assert check < violation < report.index(copy) < report.index("### 2. Present Summary")
    publish = _section(report, "**Publish the checked report.**", "With the deterministic gate passed")
    assert '(exit code 4, `halt_reason: "write-failed"`) at phase `report:publish`' in publish
    # The result contract comes from the emitter, into the forge data folder.
    contract = _section(report, "### 4b. Result Contract", "### 5. Finish")
    assert ('uv run {emitEnvelopeHelper} emit --workflow skf-verify-stack --run-dir "{run_dir}" '
            '--result-dir "{forge_data_folder}" < "{run_dir}/result-context.json"') in contract
    assert "{YYYYMMDD-HHmmss}.json` (UTC timestamp" not in contract
    assert 'rm -rf "{run_dir}"' in _section(report, "### 5. Finish", "the health-check step is the true terminal step")


def test_skill_md_states_the_latest_timing_and_the_run_folder():
    skill = _read(SKILL / "SKILL.md")
    outputs = next(line for line in skill.splitlines() if line.startswith("| **Outputs** |"))
    assert "written by step 6 once the finished report passes the feasibility-report check" in outputs
    assert "`run_dir` ← `{project-root}/_bmad-output/.skf-run/skf-verify-stack-{timestamp}`" in skill
    assert "`{emitEnvelopeHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-emit-result-envelope.py`" in skill
    # init.md creates the run folder and probes the output folder before its
    # first prompt, so a halt there stages its payload in the folder.
    init = _read(REFERENCES / "init.md")
    preflight = _section(init, "**Pre-flight: run folder and write probe.**", "**Bind `{project_slug}`.**")
    assert 'mkdir -p "{project-root}/_bmad-output/.skf-run" && mkdir "{run_dir}"' in preflight
    assert 'printf \'probe\' > "{outputFolderPath}/.skf-write-probe"' in preflight
    assert init.index("**Pre-flight: run folder and write probe.**") < init.index("### 1. Accept Input Documents")
    assert "mkdir" not in skill


# --- The documented pipeline, on a fixture ----------------------------------------------


def _skill(root: Path, name: str, body: str, source_repo: str | None = None) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_bytes(body.encode("utf-8"))
    metadata = {"generated_by": "create-skill", "exports": [f"{name}Export"], "language": "typescript"}
    if source_repo is not None:
        metadata["source_repo"] = source_repo
    (folder / "metadata.json").write_bytes(json.dumps(metadata).encode("utf-8"))


def _documented_find_args(run_dir: Path) -> list[str]:
    """The cycle finder's arguments as integrations.md calls it, for this run folder."""
    text = _read(REFERENCES / "integrations.md")
    [line] = [line.strip() for line in text.splitlines() if line.strip().startswith("uv run {cycleFinderHelper} find ")]
    command = line.split(" > ", 1)[0].replace("{run_dir}", run_dir.as_posix())
    return shlex.split(command)[3:]


def test_the_documented_pipeline_runs_end_to_end(tmp_path):
    skills = tmp_path / "skills"
    # oms-cognee is cited by its repository name, react-query and zod cite each
    # other (Check 4 evidence, no cycle), react-query, oms-cognee and zod cite
    # round in a cycle, and zod's `next step` is only the common word.
    _skill(skills, "oms-cognee", "# Cognee\n\nMemory graph, validated with zod.\n",
           "https://github.com/topoteretes/cognee.git")
    _skill(skills, "react-query", "# React Query\n\nValidate with zod schemas.\nStore results in Cognee.\n")
    _skill(skills, "zod", "# Zod\n\nPairs with react-query.\nThe next step parses.\n")
    run_dir = _run_dir(tmp_path)
    inventory_file = run_dir / "skill-inventory.json"

    enum = _run([ENUMERATE, "enumerate", skills, "--reliability"])
    assert enum.returncode == 0, enum.stderr
    inventory_file.write_bytes(enum.stdout.encode("utf-8"))
    inventory = json.loads(enum.stdout)
    assert inventory["inventory_reliable"] is True
    cognee = next(s for s in inventory["skills"] if s["name"] == "oms-cognee")
    assert cognee["source_repo_basename"] == "cognee"  # the coverage stage's match

    pairs = {"pairs": [["react-query", "zod"], ["oms-cognee", "react-query"], ["oms-cognee", "zod"]]}
    (run_dir / "integration-pairs.json").write_bytes(json.dumps(pairs).encode("utf-8"))
    # The scanner reads the inventory itself: its source basenames are aliases.
    scan = _run([SCANNER, "cross-reference", "--skills", inventory_file,
                 "--skills-root", skills, "--pairs", run_dir / "integration-pairs.json"])
    assert scan.returncode == 0, scan.stderr
    (run_dir / "citations.json").write_bytes(scan.stdout.encode("utf-8"))
    citations = json.loads(scan.stdout)
    by_direction = {(c["from"], c["to"]): c for c in citations["citations"]}
    assert by_direction[("react-query", "oms-cognee")]["substring"] == "Cognee"
    assert by_direction[("react-query", "oms-cognee")]["line"] == 4
    assert ("zod", "react-query") in by_direction and ("react-query", "zod") in by_direction
    assert ("oms-cognee", "react-query") not in by_direction

    assert ("oms-cognee", "zod") in by_direction

    # The finder reads the citations file as it is, as integrations.md calls
    # it: Check 4 rejected no direction, and the mutual citation of
    # react-query and zod is no cycle.
    args = _documented_find_args(run_dir)
    assert args[:3] == ["find", "--edges", (run_dir / "citations.json").as_posix()]
    rejected = run_dir / "rejected-edges.json"
    rejected.write_bytes(json.dumps({"edges": []}).encode("utf-8"))
    found = _run([FIND_CYCLES, *args])
    assert found.returncode == 0, found.stderr
    (run_dir / "cycles.json").write_bytes(found.stdout.encode("utf-8"))
    assert json.loads(found.stdout)["cycles"] == [["oms-cognee", "zod", "react-query", "oms-cognee"]]

    rows = {"rows": [{"lib_a": "react-query", "lib_b": "zod", "verdict": "Verified"},
                     {"lib_a": "oms-cognee", "lib_b": "react-query", "verdict": "Verified"},
                     {"lib_a": "oms-cognee", "lib_b": "zod", "verdict": "Verified"}]}
    tally = _run([TALLY, "--kind", "integrations", "--cycles", run_dir / "cycles.json", "--stdin"],
                 stdin=json.dumps(rows))
    assert tally.returncode == 0, tally.stdout
    counts = json.loads(tally.stdout)
    assert (counts["pairs_verified"], counts["pairs_risky"], counts["row_count"]) == (3, 1, 4)

    # A direction Check 4 rejects as a common word leaves the cycle.
    rejected.write_bytes(json.dumps({"edges": [["oms-cognee", "zod"]]}).encode("utf-8"))
    found = _run([FIND_CYCLES, *args])
    assert found.returncode == 0, found.stderr
    assert json.loads(found.stdout) == {"cycles": [], "cycle_count": 0}

    # A skill changed mid-run is found by its metadata_hash, not a modification time.
    (skills / "zod" / "metadata.json").write_bytes(
        json.dumps({"generated_by": "create-skill", "exports": ["z"], "language": "typescript"}).encode("utf-8"))
    recheck = _run([ENUMERATE, "enumerate", skills, "--expect-hashes", inventory_file])
    assert recheck.returncode == 0, recheck.stderr
    out = json.loads(recheck.stdout)
    assert (out["changed_skills"], out["missing_skills"], out["new_skills"]) == (["zod"], [], [])


def test_a_pair_of_one_skill_is_dropped_before_the_helpers(tmp_path):
    # Two technologies can match one skill (by alias or source basename); the
    # scanner and the tally both refuse such a pair, so integrations.md drops it.
    text = _read(REFERENCES / "integrations.md")
    claims = _section(text, "### 2. Extract Integration Claims", "### 3.")
    assert "Drop a pair whose two technologies step 2 matched to the same skill" in claims
    assert "{IF §2 dropped a pair whose technologies are one skill:}" in _section(text, "### 5.", "### 6.")
    pairs = tmp_path / "pairs.json"
    pairs.write_bytes(json.dumps({"pairs": [["surrealql", "surrealql"]]}).encode("utf-8"))
    skills = tmp_path / "skills.json"
    skills.write_bytes(json.dumps([{"name": "surrealql", "path": "surrealql"}]).encode("utf-8"))
    scan = _run([SCANNER, "cross-reference", "--skills", skills, "--pairs", pairs])
    assert scan.returncode == 1 and "with itself" in scan.stderr
    rows = {"rows": [{"lib_a": "surrealql", "lib_b": "surrealql", "verdict": "Verified"}]}
    tally = _run([TALLY, "--kind", "integrations", "--stdin"], stdin=json.dumps(rows))
    assert tally.returncode == 2 and "with itself" in json.loads(tally.stdout)["error"]


def test_a_pair_whose_skill_changed_mid_run_is_a_risky_row():
    # Its row needs a token the canonical table and the tally accept.
    text = _read(REFERENCES / "integrations.md")
    check = _section(text, "**Mid-run change check.**", "### 4.")
    assert 'carries the verdict `Risky` and the rationale "skill modified mid-run: re-run [VS]"' in check
    assert "in every table and in `verdict-rows.json`" in check
    assert RECORD_WARNING + "'skill_modified_mid_run: <skill>'" in check
    risky = _section(_read(REFERENCES / "synthesize.md"), "**Risky integration (from Step 03):**", "**Plausible integration")
    assert "If a skill changed mid-run" in risky and "re-run **[VS]**" in risky


def test_synthesize_reads_this_runs_tiers_from_the_inventory():
    delta = _section(_read(REFERENCES / "synthesize.md"), "### 3. Check for Previous Report", "### 4.")
    assert ('uv run {reportDeltaScript} --previous-report "{previousReport}" --current-report "{outputFile}" '
            '--inventory "{inventoryFile}"') in delta
    assert "<tiers JSON>" not in delta and "echo " not in delta


# --- The stages read helpers and files, not SKILL.md or mtimes --------------------------


def test_integrations_takes_check_4_and_the_edges_from_the_scanner():
    text = _read(REFERENCES / "integrations.md")
    frontmatter = text.split("\n---\n", 1)[0]
    for probe in ("scanSkillMdStructureProbeOrder:", "enumerateStackSkillsProbeOrder:", "cycleFinderProbeOrder:"):
        assert probe in frontmatter, probe
    # The scanner reads the inventory itself, so no stage copies it by hand.
    assert ('uv run {scanSkillMdStructureHelper} cross-reference --skills "{inventoryFile}" '
            '--skills-root "{skills_output_folder}" --pairs "{run_dir}/integration-pairs.json"') in text
    assert "citation-skills.json" not in text and "aliases" not in text
    assert ('uv run {cycleFinderHelper} find --edges "{run_dir}/citations.json" '
            '--exclude-edges "{run_dir}/rejected-edges.json" --skip-mutual > "{run_dir}/cycles.json"') in text
    assert "cycle-edges.json" not in text and "form a cycle too" not in text
    assert "a Check-4 judgment" not in text and "Build the directed pair graph in the prompt" not in text
    # The matching rule lives in the scanner and the rules file, not here.
    check4 = _section(text, "### 4. Cross-Reference Each Integration Pair", "**Each verdict includes:**")
    assert "react-dom" not in check4 and "common word" not in check4
    assert 'uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --expect-hashes "{inventoryFile}"' in text
    assert "`changed_skills` and `missing_skills`" in text
    surfaces = _section(text, "### 3. Load Skill API Surfaces", "### 4.")
    assert "For every skill step 2 matched to a Covered technology" in surfaces
    assert '"capabilities":' in surfaces and "`capabilities`" in surfaces
    assert "{run_dir}/skill-summaries.json" in surfaces


def test_no_verify_stack_file_restats_modification_times():
    for path in [*_markdown(), *sorted((SKILL / "assets").glob("*.md"))]:
        text = _read(path)
        for stale in ("mtime", "Re-stat", "modification time of"):
            assert stale not in text, f"{_rel(path)}: {stale!r}"


def test_init_persists_the_inventory_in_the_run_folder():
    init = _read(REFERENCES / "init.md")
    assert "inventoryFile: '{run_dir}/skill-inventory.json'" in init.split("\n---\n", 1)[0]
    assert 'uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --reliability > "{inventoryFile}"' in init
    assert "Capture mtime" not in init


MENTIONS_CALL = 'uv run {comentionHelper} mentions --doc "<architectureDoc>" --skills - > "{docMentionsFile}"'


def _mentions_skills(inventory: dict) -> list[dict]:
    """The --skills array coverage.md pipes: each name, its source basenames as aliases."""
    return [{"name": s["name"],
             "aliases": [s[k] for k in ("source_repo_basename", "source_root_basename") if s.get(k)]}
            for s in inventory["skills"]]


def test_coverage_names_skills_through_the_mentions_helper(tmp_path):
    coverage = _read(REFERENCES / "coverage.md")
    frontmatter = _frontmatter(coverage)
    assert ("comentionProbeOrder:\n"
            "  - '{project-root}/_bmad/skf/shared/scripts/skf-comention-pairs.py'\n"
            "  - '{project-root}/src/shared/scripts/skf-comention-pairs.py'\n") in frontmatter
    assert "docMentionsFile: '{run_dir}/doc-mentions.json'" in frontmatter
    extract = _section(coverage, "### 2. Extract Technology References", "### 3.")
    assert MENTIONS_CALL in extract
    assert "`source_repo_basename` and `source_root_basename` that are not null" in extract
    assert "each other name a persistent fact gives the skill" in extract
    assert '(exit code 3, `halt_reason: "resolution-failure"`) at phase `coverage:mentions`' in extract
    # No hand scan for skill names and no hand equality on the source basenames.
    match = _section(coverage, "### 3. Cross-Reference Against Skills", "**Detect a deliberate-removal signal")
    assert "A `mentioned` skill matches its own row" in match
    for stale in ("Direct name matching", "for equality with", "extract the basename",
                  "strip any trailing `.git` suffix"):
        assert stale not in coverage, stale
    extras = _section(coverage, "### 4. Detect Extra Skills", "### 5.")
    assert "`unmentioned` or `fenced_only`" in extras and "`source_repo_basename` is null" in extras
    note = _section(coverage, "{IF a skill of the helper's `fenced_only` list is Extra:}", "### 6.")
    assert "has the `info` string `mermaid`" in note

    # The call runs as documented, on the inventory step 1 writes.
    skills = tmp_path / "skills"
    _skill(skills, "oms-cognee", "# Cognee\n", "https://github.com/topoteretes/cognee.git")
    _skill(skills, "react-query", "# React Query\n")
    _skill(skills, "zod", "# Zod\n")
    enum = _run([ENUMERATE, "enumerate", skills, "--reliability"])
    assert enum.returncode == 0, enum.stderr
    doc = tmp_path / "architecture.md"
    doc.write_bytes(("# App\n\n## Data\n\nReact Query caches what Cognee returns.\n\n"
                     "```mermaid\ngraph LR\n  zod --> app\n```\n").encode("utf-8"))
    proc = _run([COMENTION, "mentions", "--doc", doc, "--skills", "-"],
                stdin=json.dumps(_mentions_skills(json.loads(enum.stdout))))
    assert proc.returncode == 0, proc.stderr
    mentions = json.loads(proc.stdout)
    # "Cognee" names oms-cognee by its repository; "React Query" is no skill
    # name or alias, so the model's own detection reads it under an alias.
    assert mentions["mentioned"] == ["oms-cognee"]
    assert mentions["fenced_only"] == ["zod"] and mentions["unmentioned"] == ["react-query"]
    assert [b["info"] for b in mentions["fenced_blocks"]] == ["mermaid"]
    assert mentions["candidates"] == []

    # The second run §3 documents: the document's "React Query" is now an
    # alias of react-query, so the skill is named and its pair is a candidate.
    rerun = _with_alias(_mentions_skills(json.loads(enum.stdout)), "react-query", "React Query")
    proc = _run([COMENTION, "mentions", "--doc", doc, "--skills", "-"], stdin=json.dumps(rerun))
    assert proc.returncode == 0, proc.stderr
    mentions = json.loads(proc.stdout)
    assert mentions["mentioned"] == ["oms-cognee", "react-query"]
    assert [(c["a"], c["b"]) for c in mentions["candidates"]] == [("oms-cognee", "react-query")]


def _with_alias(skills: list[dict], name: str, term: str) -> list[dict]:
    """The --skills array of coverage.md's second run: the model's term added to the skill's aliases."""
    return [{**s, "aliases": [*s["aliases"], term]} if s["name"] == name else s for s in skills]


def test_a_skill_the_model_matches_under_a_common_alias_reaches_the_pairs(tmp_path):
    coverage = _read(REFERENCES / "coverage.md")
    match = _section(coverage, "### 3. Cross-Reference Against Skills", "**Detect a deliberate-removal signal")
    rerun = _section(match, "**Run the mentions helper again when the model matched a skill.**", "\n\n")
    assert "add the technology's term, as the document writes it, to that skill's `aliases`" in rerun
    assert "run the §2 `mentions` command once more with the extended array, overwriting `{docMentionsFile}`" in rerun
    assert "take §2's skill rows from the new file" in rerun
    assert "labelled with its `name`, replaces the technology's" in rerun
    extras = _section(coverage, "### 4. Detect Extra Skills", "**Subdivide")
    assert "as §3 left it" in extras and "matched by no technology" not in extras
    # The integrations stage reads the same file, so the pair reaches it.
    claims = _section(_read(REFERENCES / "integrations.md"), "### 2. Extract Integration Claims", "### 3.")
    assert "`candidates[]` in `{docMentionsFile}`" in claims

    doc = tmp_path / "architecture.md"
    doc.write_bytes("# App\n\n## Data\n\nPrisma connects to PostgreSQL over TCP.\n".encode("utf-8"))
    skills = [{"name": "postgres", "aliases": []}, {"name": "prisma", "aliases": []}]
    first = _run([COMENTION, "mentions", "--doc", doc, "--skills", "-"], stdin=json.dumps(skills))
    assert first.returncode == 0, first.stderr
    first_out = json.loads(first.stdout)
    # "PostgreSQL" is no skill name: only the model's common-alias match finds it.
    assert first_out["mentioned"] == ["prisma"] and first_out["unmentioned"] == ["postgres"]
    assert first_out["candidates"] == []
    second = _run([COMENTION, "mentions", "--doc", doc, "--skills", "-"],
                  stdin=json.dumps(_with_alias(skills, "postgres", "PostgreSQL")))
    assert second.returncode == 0, second.stderr
    second_out = json.loads(second.stdout)
    assert second_out["mentioned"] == ["postgres", "prisma"] and second_out["unmentioned"] == []
    [candidate] = second_out["candidates"]
    assert (candidate["a"], candidate["b"]) == ("postgres", "prisma")
    assert "Prisma connects to PostgreSQL" in candidate["evidence"][0]["unit_excerpt"]


def test_integrations_judges_the_mentions_candidates(tmp_path):
    text = _read(REFERENCES / "integrations.md")
    assert "docMentionsFile: '{run_dir}/doc-mentions.json'" in _frontmatter(text)
    claims = _section(text, "### 2. Extract Integration Claims", "### 3.")
    assert "`candidates[]` in `{docMentionsFile}`" in claims
    assert "`unit_excerpt`, with its `header` and `unit_line`" in claims
    assert "the quoted `unit_excerpt` of the evidence entry" in claims
    # The stage reads no document and keeps no verb list or Mermaid pointer.
    for stale in ('"connects to"', "Look for data flow descriptions", "Mermaid Diagram Handling",
                  "{coveragePatternsData}", "Parse the architecture document"):
        assert stale not in text, stale
    # A candidate carries the unit that names both skills, as the stage quotes it.
    doc = tmp_path / "architecture.md"
    doc.write_bytes("# App\n\n## Data\n\nThe api service validates every payload with zod.\n".encode("utf-8"))
    skills = [{"name": "api", "aliases": []}, {"name": "zod", "aliases": []}]
    proc = _run([COMENTION, "mentions", "--doc", doc, "--skills", "-"], stdin=json.dumps(skills))
    assert proc.returncode == 0, proc.stderr
    [candidate] = json.loads(proc.stdout)["candidates"]
    assert (candidate["a"], candidate["b"]) == ("api", "zod")
    [evidence] = candidate["evidence"]
    assert evidence["header"] == "Data" and evidence["unit_line"] == 5
    assert "validates every payload with zod" in evidence["unit_excerpt"]


def test_a_cycle_row_never_merges_into_a_pair_row():
    text = _read(REFERENCES / "integrations.md")
    rows = _section(text, "**For each cycle**", "**Count the verdicts deterministically.**")
    assert "`lib_a` is `cycle`, `lib_b` the arrow chain rendered from the cycle's node path" in rows
    risky = _section(_read(REFERENCES / "synthesize.md"), "**Risky integration (from Step 03):**", "**Plausible integration")
    assert "`cycle` in its `lib_a`, the chain in its `lib_b`" in risky
    # The delta keys rows on their two libraries: the cycle row stays its own row.
    spec = importlib.util.spec_from_file_location("skf_report_delta_contract", REPORT_DELTA)
    delta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(delta)
    pair = {"libA": "react-query", "libB": "zod", "verdict": "Verified"}
    cycle = {"libA": "cycle", "libB": "oms-cognee → zod → react-query → oms-cognee", "verdict": "Risky"}
    out = delta.compute({"previous": {"coverage": [], "integration": [pair]},
                         "current": {"coverage": [], "integration": [pair, cycle]}})
    assert out["unchanged"] == ["react-query ↔ zod"]
    assert out["new"] == ["cycle ↔ oms-cognee → zod → react-query → oms-cognee"]
    assert out["regressedCount"] == 0


def test_requirements_reads_the_step_3_summaries_not_skill_md():
    requirements = _read(REFERENCES / "requirements.md")
    assess = _section(requirements, "### 3. Assess Stack Coverage", "### 4.")
    assert "{skillSummariesFile}" in assess
    assert "never from a SKILL.md read in this context" in assess
    assert "Read each skill's SKILL.md" not in requirements
    assert "skillSummariesFile: '{run_dir}/skill-summaries.json'" in requirements.split("\n---\n", 1)[0]


def test_the_rules_file_says_the_scanner_runs_check_4():
    rules = _read(REFERENCES / "integration-verification-rules.md")
    check4 = _section(rules, "### 4. Documentation Cross-Reference", "---")
    assert "skf-scan-skill-md-structure.py cross-reference" in check4
    assert "a citation is a hit it lists, never a line read from a SKILL.md" in check4
    assert "the next step" in check4
    # What a hit matches is the scanner's rule (its docstring), not restated here.
    assert "never inside a longer name" not in check4 and "`source_repo`" not in check4
    assert "`{project-root}/_bmad/skf/shared/references/feasibility-report-schema.md`" in rules


# --- The customization surface keeps only settings that take effect (#596) -------------


def test_customize_toml_keeps_only_settings_that_take_effect():
    raw = _read(SKILL / "customize.toml")
    workflow = tomllib.loads(raw)["workflow"]
    assert sorted(workflow) == ["activation_steps_append", "activation_steps_prepend", "on_complete",
                                "persistent_facts", "report_template_path"]
    for removed in ("integration_rules_path", "coverage_patterns_path", "output_folder_path"):
        assert f"{removed} =" not in raw, removed
    # Extra aliases go through persistent_facts, and the comment says how the
    # bundled project-context.md entry is kept from steering a run.
    facts = _section(raw, "# Persistent facts", "persistent_facts = [")
    assert "Extra aliases go here" in facts and "as aliases of that skill" in facts
    assert "cannot remove it" in facts
    # The report folder is the forge data folder, and the comment says so.
    assert "the report always lands in {forge_data_folder}" in raw


def test_the_report_template_comment_names_what_the_schema_fixes():
    raw = _read(SKILL / "customize.toml")
    comment = _section(raw, "# The template step 1", "report_template_path =")
    assert "Default: assets/feasibility-report-template.md" in comment
    assert '`schemaVersion: "1.0"`' in comment
    template = _read(SKILL / "assets" / "feasibility-report-template.md")
    headings = [line for line in template.splitlines() if line.startswith("## ")]
    assert headings == ["## Executive Summary", "## Coverage Analysis", "## Integration Verdicts",
                        "## Recommendations", "## Evidence Sources"]
    flat = " ".join(line.lstrip("#").strip() for line in comment.splitlines())
    for heading in headings:
        assert f"`{heading}`" in flat, heading
    for table in ("| lib_a | lib_b | verdict | rationale |",
                  "| skill | evidence_tier | confidence_tier | metadata_schema_version | skill_md |"):
        assert table in template and f"`{table}`" in flat, table
    assert "(`schema-violation`)" in comment


def test_no_stage_reads_a_removed_setting():
    for path in [SKILL / "SKILL.md", *sorted(REFERENCES.glob("*.md"))]:
        text = _read(path)
        for stale in ("{integrationRulesPath}", "{coveragePatternsPath}", "integration_rules_path",
                      "coverage_patterns_path", "output_folder_path"):
            assert stale not in text, f"{_rel(path)}: {stale}"
    # Each stage loads the bundled file by its path from the skill root.
    assert "coveragePatternsData: 'references/coverage-patterns.md'" in _frontmatter(_read(REFERENCES / "coverage.md"))
    integrations = _frontmatter(_read(REFERENCES / "integrations.md"))
    assert "integrationRulesData: 'references/integration-verification-rules.md'" in integrations
    assert "coveragePatternsData" not in integrations
    for name in ("coverage-patterns.md", "integration-verification-rules.md"):
        assert (REFERENCES / name).is_file(), name
    # The report folder is the forge data folder, always.
    skill = _read(SKILL / "SKILL.md")
    assert "Bind `{outputFolderPath}` ← `{forge_data_folder}`, always (no setting moves it)" in skill
    assert "`{reportTemplatePath}` ← `workflow.report_template_path` if non-empty" in skill
    assert "four scalars" not in skill and "Stash all four" not in skill


def test_init_checks_the_forge_data_folder_before_probing_it():
    init = _read(REFERENCES / "init.md")
    preflight = _section(init, "**Pre-flight: run folder and write probe.**", "**Bind `{project_slug}`.**")
    check = preflight.index('(exit code 3, `halt_reason: "forge-folder-unconfigured"`) at phase `init:forge-data-folder`')
    assert check < preflight.index('printf \'probe\' > "{outputFolderPath}/.skf-write-probe"')
    assert init.count("forge-folder-unconfigured") == 1
    assert "step 1 pre-flight (forge_data_folder unconfigured" in _read(EXIT_CODES)


# --- A path the invocation gave is never asked for again (#594) ------------------------


def test_activation_binds_the_inputs_in_every_mode():
    skill = _read(SKILL / "SKILL.md")
    bind = next(line for line in skill.splitlines() if "**Bind the inputs**" in line)
    assert "in every mode" in bind
    for variable, flag in (("{architecture_doc_path}", "--architecture-doc"), ("{prd_path}", "--prd"),
                           ("{previous_report_path}", "--previous-report")):
        assert f"`{variable}` ← " in bind and f"`{flag}`" in bind, variable
        flags = next(line for line in skill.splitlines() if line.startswith("| **Flags** |"))
        assert f"`{flag} <path>`" in flags, flag
    inputs = next(line for line in skill.splitlines() if line.startswith("| **Inputs** |"))
    for name in ("architecture_doc_path", "prd_path", "previous_report_path"):
        assert name in inputs, name


def test_step_1_asks_only_for_what_no_flag_answered():
    init = _read(REFERENCES / "init.md")
    accept = _section(init, "### 1. Accept Input Documents", "**Validate the architecture document**")
    assert "**Ask only for what no flag answered.**" in accept
    assert "is used in every mode and never asked for again" in accept
    assert "only the numbered lines whose input is null" in accept
    gate = next(line for line in accept.splitlines() if "**GATE [default: use args]**" in line)
    assert '(exit code 2, `halt_reason: "input-missing"`) at phase `init:input-documents`' in gate
    # A run every flag answered shows no prompt, so there is nothing to wait for.
    assert gate.startswith("When the prompt shows, wait for user input")
    # The old gate read the flags in headless only.
    assert "if `{headless_mode}` and `--architecture-doc` was provided" not in init
    previous = _section(init, "**Resolve the previous report.**", "```bash")
    assert "`--provided` set to `{previous_report_path}` when it is set" in previous
    bookkeeping = next(line for line in init.splitlines() if line.startswith("- `architectureDoc` ← "))
    assert "`{architecture_doc_path}`" in bookkeeping and "`prdDoc` ← `{prd_path}`" in bookkeeping
    # The summary table reads the variables activation and step 1 bind.
    summary = _section(init, "### 5. Display Initialization Summary", "**Skill Inventory:**")
    assert "| **Architecture Doc** | {architecture_doc_path} |" in summary
    assert "| **PRD Document** | {prd_path or 'Not provided: requirements pass will be skipped'} |" in summary
    assert "{prd_doc" not in init and "{architecture_doc}" not in init
