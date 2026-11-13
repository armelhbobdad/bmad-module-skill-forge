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
- stages 1 to 5 write only {outputFile}, stages 2 to 5 through the
  report-update helper, each block of its calls followed by the
  resolution-failure and write-failed halts; report.md copies it to
  {outputFileLatest} once, after the feasibility-report check;
- the documented pipeline runs on a fixture: the enumerate inventory in the run
  folder, --expect-hashes naming a skill changed mid-run, the SKILL.md scanner
  reading that inventory (source basenames as aliases) for Check 4, its
  citations file into the cycle finder as integrations.md calls it (rejected
  directions left out, two skills that cite each other no cycle), the
  tally counting each cycle as a Risky row, and the canonical rows rendered
  from the same rows file, each pair with its rationale and each cycle as a
  row of its own;
- a cycle row names `cycle` and its chain, so the delta never merges it into
  the pair row of two of its skills;
- the API-surface reads fall back to one SKILL.md at a time when subagents
  are unavailable, each summary written to disk before the next read, and a
  Blocked recommendation states synthesize's Named-candidate requirement in
  place;
- a pair of one skill is dropped before the scanner and the tally, which both
  refuse it, and a pair whose skill changed mid-run is a Risky row;
- coverage finds the skills the document names, by name or source basename,
  through the shared mentions helper, hands it the other technologies
  (`--technologies`) so the helper settles every name and alias match and
  the model judges only the names it leaves unverified, and runs it again
  with each term matched to a skill the document did not name, so the
  integrations stage judges the candidate pairs of every Covered skill; the
  requirements stage reads the step 3 summaries, never a SKILL.md (#1199);
- coverage.md states each rule once, with no coverage-patterns.md beside it,
  and the integration rules file ends after Check 4, integrations.md §4
  being the one home of verdict evidence (#1199);
- the integration rules and the report folder are no customize.toml
  settings, the report template's comment names what the schema fixes, and
  a path a flag gave is never asked for again;
- report.md §5 deletes the run folder, then carries out the on_complete
  instruction, shows its failure on one line and goes on, then chains to
  the health check even when the instruction started another workflow,
  and SKILL.md and customize.toml say it runs at the end of step 6, before
  the health check (#1109);
- init.md §4 halts (`resolution-failure`) before the Load when the report
  template names no readable file, and runs the feasibility-report check on
  the report it creates from it, halting (`schema-violation`) on a copy that
  breaks it, both at phase `init:report-template`, long before step 6 (#1110);
- step 1 checks the skills before its prompt, asks once more for a PRD or
  previous-report path that was not found and records it when headless, from
  a file the record command reads, and fills only the per-run frontmatter
  keys; SKILL.md points to references/invocation-contract.md (#1200);
- synthesize alone writes the `## Recommendations` list, one item per finding the
  rollup counts, each Risky or Blocked item naming its bridge or replacement;
  report.md presents that list once, after the verdict line and before the
  Suggested next workflow block, and its summary reads the frontmatter keys
  themselves, with N/A only for a skipped requirements pass; requirements.md
  takes the PRD's path from `prdDoc` and states each rule once (#1201).
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
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
REPORT_UPDATE = SKILL / "scripts" / "skf-report-update.py"
ROLLUP = SKILL / "scripts" / "skf-verdict-rollup.py"
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
# Step 1 records a path a headless run gave and that was not found from a file, since a path can hold
# quotes or `$( )` (#1200).
INPUT_WARNING_RECORD = RECORD_WARNING + '"$(cat "{run_dir}/input-warning.txt")"'


def _input_warning_block() -> str:
    return _section(_read(REFERENCES / "init.md"), "**Record a path that was not found.**", "### 4. ")


def _documented_warnings() -> list[str]:
    """The warnings the stages record in the run sink, in stage order."""
    init = _input_warning_block()
    assert f"```bash\n{INPUT_WARNING_RECORD}\n```" in init
    found = re.findall(r"`([a-z_]+_not_found: <path>)`", init)
    coverage = _read(REFERENCES / "coverage.md")
    assert RECORD_WARNING + "'<the warning to record>'" in coverage
    found += re.findall(r"Record `([a-z_]+: [^`]+)`", coverage)
    for name in ("integrations.md", "report.md"):
        found += re.findall(re.escape(RECORD_WARNING) + r"'([a-z_]+: [^']+)'", _read(REFERENCES / name))
    return found


def test_each_documented_warning_is_a_fixed_code():
    warnings = _documented_warnings()
    assert [w.split(":", 1)[0] for w in warnings] == [
        "prd_not_found", "previous_report_not_found", "no_technology_referenced", "no_live_technology",
        "zero_coverage", "skill_summary_unreadable", "skill_modified_mid_run", "all_pairs_blocked",
        "result_file_write_failed"]
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


def test_a_headless_run_hands_its_line_to_the_health_check():
    """#1113: §4b keeps the emitter's line instead of displaying it, §5's closing message is for interactive runs
    only, §5 binds `{result_envelope_line}` to that line after the on_complete instruction, and the relay's fallback
    for a health check it cannot load displays the bound line after its log line, so a headless run's last line is
    its envelope either way."""
    report = _read(REFERENCES / "report.md")
    contract = _section(report, "### 4b. Result Contract", "### 5. Finish")
    kept = ("When `{headless_mode}` is true, bind `{verify_stack_result_line}` ← the line and do not display it here: "
            "§5 hands it to the shared health check, which displays it verbatim as the run's last line (the line the "
            "retry below prints when the first run printed none).")
    assert kept in contract
    assert contract.index("prints the `SKF_VERIFY_STACK_RESULT_JSON:` line on stdout") < contract.index(kept)
    # An emitter that fails twice still halts here, on its own line, and never reaches the health check.
    assert contract.index(kept) < contract.index(
        'if it fails again, HALT (exit code 4, `halt_reason: "write-failed"`) at phase `report:result-contract`')
    # The on_complete instruction can start a headless workflow that binds `{result_envelope_line}` to its own
    # line, so §4b binds only Verify Stack's own variable.
    assert "`{result_envelope_line}`" not in contract
    assert "display the line verbatim" not in report and "before chaining to step 7" not in report
    finish = _section(report, "### 5. Finish", "the health-check step is the true terminal step")
    assert finish.startswith('### 5. Finish\n\nWhen `{headless_mode}` is false, display:\n\n"**Feasibility report '
                             'saved to:**')
    assert finish.index("When `{headless_mode}` is false, display:") < finish.index("If `{workflow.on_complete}`")
    bind = ("When `{headless_mode}` is true, then bind `{result_envelope_line}` ← `{verify_stack_result_line}`: a "
            "headless workflow the instruction started binds its own result line to `{result_envelope_line}`, so "
            "binding it only now keeps this run's line the one the health check displays last.")
    assert finish.index("If `{workflow.on_complete}`") < finish.index(bind) < finish.index("Then load, read the full")
    relay = _read(REFERENCES / "health-check.md")
    handed = ("In a headless run report.md §5, after the on_complete instruction, bound `{result_envelope_line}` to "
              "the `SKF_VERIFY_STACK_RESULT_JSON` line without displaying it: the shared health check displays that "
              "line verbatim as the run's last line wherever it stops")
    assert handed in relay
    log = "log exactly `health-check unavailable at {path}`"
    shown = ("then display `{result_envelope_line}` verbatim after it when it is bound and not empty, with no code "
             "fence and nothing after it")
    assert relay.index(handed) < relay.index(log) < relay.index(shown) < relay.index("exit cleanly")
    contract = _read(REFERENCES / "invocation-contract.md")
    result = contract[contract.index("## Result Contract (Headless)"):]
    assert ("line on **stdout**, which the shared health check displays as the run's last line, and every HARD HALT "
            "one on **stderr**") in result
    envelope = _section(_read(EXIT_CODES), "## Result Envelope", "## Emitting a Halt")
    assert ("line on **stdout**, which the shared health check (step 7) displays as the run's last line, and every "
            "HARD HALT prints one on **stderr**") in envelope
    assert "before chaining to step 7" not in envelope


def test_the_circuit_breaker_halts_on_a_halt_line(tmp_path):
    run_dir = _run_dir(tmp_path)
    proc = _run([EMITTER, "emit-halt", "--workflow", "skf-verify-stack", "--run-dir", run_dir, "--target", "stderr"],
                stdin=json.dumps(_halt_payload("schema-violation")))
    gate = _run([PIPELINE_GATE, "--code", "VS"], stdin=proc.stderr)
    out = json.loads(gate.stdout)
    assert (out["decision"], out["reason"]) == ("halt", "schema-violation")


# --- -latest is written once, after the check -----------------------------------------


WRITE_FAILED = re.compile(r'\(exit code 4, `halt_reason: "write-failed"`\) at phase `([a-z]+):report`')


REPORT_UPDATE_CALL = re.compile(r"^uv run \{reportUpdateScript\} (set-counts|fill-table|replace-section) (.*)$", re.M)
BASH_BLOCK = re.compile(r"^```bash\n(.*?)^```\n", re.M | re.S)


@pytest.mark.parametrize("name", DRAFTING_STAGES)
def test_stages_1_to_5_write_only_the_timestamped_report(name):
    text = _read(REFERENCES / name)
    assert "--target {outputFileLatest}" not in text
    assert '--target "{outputFileLatest}"' not in text
    frontmatter = text.split("\n---\n", 1)[0]
    if name == "init.md":
        writes = [m.start() for m in re.finditer(re.escape("write --target {outputFile}`"), text)]
        assert writes
        for at in writes:
            # Every write of the report names the write-failed halt right after it.
            halt = WRITE_FAILED.search(text, at, at + 700)
            assert halt, f"{name}: a report write at offset {at} has no write-failed halt"
            assert halt.group(1) == PHASE_PREFIX[name]
        return
    # A stage that no longer writes the -latest copy keeps no path for it.
    assert "outputFileLatest:" not in frontmatter
    # Stages 2 to 5 write their keys, rows and sections through the report-update
    # helper, which edits only its own part: none pipes the whole report by hand.
    assert "{atomicWriteHelper}" not in text and "atomicWriteProbeOrder" not in frontmatter
    assert "reportUpdateScript: 'scripts/skf-report-update.py'" in frontmatter
    calls = REPORT_UPDATE_CALL.findall(text)
    assert calls, name
    for _command, rest in calls:
        assert rest.startswith('--report "{outputFile}" '), rest
    blocks = [m for m in BASH_BLOCK.finditer(text) if "{reportUpdateScript}" in m.group(1)]
    assert sum(len(REPORT_UPDATE_CALL.findall(m.group(1))) for m in blocks) == len(calls)
    phase = f"{PHASE_PREFIX[name]}:report"
    for block in blocks:
        if len(REPORT_UPDATE_CALL.findall(block.group(1))) > 1:
            # A shell that runs the block whole exits with its last call's status, which
            # would hide a refused call before it: the calls run one at a time.
            before = text[:block.start()].rstrip("\n").rsplit("\n", 1)[-1]
            assert before.endswith("Then run the calls in order, stopping at the first that exits non-zero:"), before
        # The paragraph after each block of calls names both halts, at the stage's report phase.
        after = text[block.end():].lstrip("\n").split("\n\n", 1)[0]
        assert ("On exit 1, HALT (exit code 3, `halt_reason: \"resolution-failure\"`) at phase "
                f"`{phase}`. On any other non-zero exit, HALT (exit code 4") in after, after
        halt = WRITE_FAILED.search(after)
        assert halt and halt.group(1) == PHASE_PREFIX[name], after
        assert after.endswith('with `"path": "{outputFile}"`, naming its JSON `error`.'), after


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
    contract = _read(REFERENCES / "invocation-contract.md")
    outputs = next(line for line in contract.splitlines() if line.startswith("| **Outputs** |"))
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

    rows = {"rows": [{"lib_a": "react-query", "lib_b": "zod", "verdict": "Verified", "rationale": "zod cites it"},
                     {"lib_a": "oms-cognee", "lib_b": "react-query", "verdict": "Verified",
                      "rationale": "react-query cites Cognee"},
                     {"lib_a": "oms-cognee", "lib_b": "zod", "verdict": "Verified", "rationale": "oms-cognee cites zod"}]}
    (run_dir / "verdict-rows.json").write_bytes(json.dumps(rows).encode("utf-8"))
    tally = _run([TALLY, "--kind", "integrations", "--cycles", run_dir / "cycles.json", "--stdin"],
                 stdin=json.dumps(rows))
    assert tally.returncode == 0, tally.stdout
    counts = json.loads(tally.stdout)
    assert (counts["pairs_verified"], counts["pairs_risky"], counts["row_count"]) == (3, 1, 4)
    # §6 renders the canonical rows from the same files, as integrations.md calls it.
    write = _section(_read(REFERENCES / "integrations.md"), "### 6. Append to Report", "### 7.")
    [render] = [line.strip() for line in write.splitlines() if line.strip().startswith("uv run {coverageTallyScript}")]
    render, saved = render.split(" > ")
    assert shlex.split(saved) == ["{run_dir}/verdict-table.md"]
    command, source = render.split("uv run {coverageTallyScript}", 1)[1].split(" < ")
    render_args = shlex.split(command.replace("{run_dir}", run_dir.as_posix()))
    assert shlex.split(source) == ["{run_dir}/verdict-rows.json"]
    rendered = _run([TALLY, *render_args], stdin=(run_dir / "verdict-rows.json").read_text(encoding="utf-8"))
    assert rendered.returncode == 0, rendered.stdout
    lines = rendered.stdout.splitlines()
    assert len(lines) == counts["row_count"]
    assert lines[0] == "| react-query | zod | Verified | zod cites it |"
    assert lines[-1].startswith("| cycle | oms-cognee \u2192 zod \u2192 react-query \u2192 oms-cognee | Risky |")

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
TECHNOLOGIES_CALL = ('uv run {comentionHelper} mentions --doc "<architectureDoc>" --skills - '
                     '--technologies "{run_dir}/technologies.json" > "{docMentionsFile}"')


def _run_mentions(call: str, doc: Path, run_dir: Path, skills: list[dict]):
    """Run a coverage.md mentions call as written, for this document and run folder, the skills on stdin."""
    filled = call.split(" > ", 1)[0].replace("<architectureDoc>", doc.as_posix())
    words = shlex.split(filled.replace("{run_dir}", run_dir.as_posix()))
    assert words[:3] == ["uv", "run", "{comentionHelper}"], words
    return _run([COMENTION, *words[3:]], stdin=json.dumps(skills))


def _mentions(call: str, doc: Path, run_dir: Path, skills: list[dict]) -> dict:
    """The JSON of a coverage.md mentions call that succeeds."""
    proc = _run_mentions(call, doc, run_dir, skills)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _write_technologies(run_dir: Path, names: list[str]) -> None:
    """Section 2's `{run_dir}/technologies.json`: the other technologies, as the document writes them."""
    (run_dir / "technologies.json").write_bytes(json.dumps(names).encode("utf-8"))


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
    # The other technologies go to the helper too, by the call the fixture below runs (#1199).
    assert TECHNOLOGIES_CALL in match
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
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    mentions = _mentions(MENTIONS_CALL, doc, run_dir, _mentions_skills(json.loads(enum.stdout)))
    # "Cognee" names oms-cognee by its repository; "React Query" names no skill
    # at a word boundary, so section 2 lists it as another technology.
    assert mentions["mentioned"] == ["oms-cognee"]
    assert mentions["fenced_only"] == ["zod"] and mentions["unmentioned"] == ["react-query"]
    assert [b["info"] for b in mentions["fenced_blocks"]] == ["mermaid"]
    assert mentions["candidates"] == []

    # Section 3's --technologies run: the helper finds "React Query" equal to
    # the react-query skill's name, so the model judges nothing.
    _write_technologies(run_dir, ["React Query"])
    matched = _mentions(TECHNOLOGIES_CALL, doc, run_dir, _mentions_skills(json.loads(enum.stdout)))
    [technology] = matched["technologies"]
    assert technology["name"] == "React Query"
    assert [(c["skill"], c["kind"]) for c in technology["covered_by"]] == [("react-query", "name")]
    assert matched["unverified_technologies"] == []

    # The run again §3 documents: the document's "React Query" is now an
    # alias of react-query, so the skill is named and its pair is a candidate.
    rerun = _with_alias(_mentions_skills(json.loads(enum.stdout)), "react-query", "React Query")
    mentions = _mentions(TECHNOLOGIES_CALL, doc, run_dir, rerun)
    assert mentions["mentioned"] == ["oms-cognee", "react-query"]
    assert [(c["a"], c["b"]) for c in mentions["candidates"]] == [("oms-cognee", "react-query")]


def _with_alias(skills: list[dict], name: str, term: str) -> list[dict]:
    """The --skills array of coverage.md's second run: the model's term added to the skill's aliases."""
    return [{**s, "aliases": [*s["aliases"], term]} if s["name"] == name else s for s in skills]


def test_a_skill_the_model_matches_under_a_common_alias_reaches_the_pairs(tmp_path):
    coverage = _read(REFERENCES / "coverage.md")
    match = _section(coverage, "### 3. Cross-Reference Against Skills", "**Detect a deliberate-removal signal")
    lead = "**Run the mentions helper again when a technology matches a skill that is not `mentioned`.**"
    rerun = _section(match, lead, "\n\n")
    assert "Add the technology's term, as the document writes it, to that skill's `aliases`" in rerun
    assert "run the command above once more with the extended array, overwriting `{docMentionsFile}`" in rerun
    assert "take §2's skill rows from the new file" in rerun
    assert "labelled with its `name`, replaces the technology's" in rerun
    assert "With no such match, skip this run." in rerun
    # The command above is the --technologies one, so the run again keeps one command shape.
    above = match[:match.index("**Run the mentions helper again")]
    assert above.count("uv run {comentionHelper} mentions") == 1 and TECHNOLOGIES_CALL in above
    extras = _section(coverage, "### 4. Detect Extra Skills", "**Subdivide")
    assert "as §3 left it" in extras and "matched by no technology" not in extras
    # The integrations stage reads the same file, so the pair reaches it.
    claims = _section(_read(REFERENCES / "integrations.md"), "### 2. Extract Integration Claims", "### 3.")
    assert "`candidates[]` in `{docMentionsFile}`" in claims

    doc = tmp_path / "architecture.md"
    doc.write_bytes("# App\n\n## Data\n\nPrisma connects to PostgreSQL over TCP.\n".encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    skills = [{"name": "postgres", "aliases": []}, {"name": "prisma", "aliases": []}]
    first_out = _mentions(MENTIONS_CALL, doc, run_dir, skills)
    assert first_out["mentioned"] == ["prisma"] and first_out["unmentioned"] == ["postgres"]
    assert first_out["candidates"] == []
    # "PostgreSQL" is no skill name or alias: the helper leaves it unverified,
    # and only the model's common-alias match finds the postgres skill.
    _write_technologies(run_dir, ["PostgreSQL"])
    matched = _mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    assert [(t["name"], t["covered_by"]) for t in matched["technologies"]] == [("PostgreSQL", [])]
    assert matched["unverified_technologies"] == ["PostgreSQL"]
    second_out = _mentions(TECHNOLOGIES_CALL, doc, run_dir, _with_alias(skills, "postgres", "PostgreSQL"))
    assert second_out["mentioned"] == ["postgres", "prisma"] and second_out["unmentioned"] == []
    [candidate] = second_out["candidates"]
    assert (candidate["a"], candidate["b"]) == ("postgres", "prisma")
    assert "Prisma connects to PostgreSQL" in candidate["evidence"][0]["unit_excerpt"]


def test_coverage_matches_the_other_technologies_by_script(tmp_path):
    """#1199 determinism-3: section 2 writes the other technologies to a file, section 3 hands it to the
    mentions helper (--technologies), whose name and alias matches are Covered, and the model judges only
    the names the helper leaves unverified."""
    coverage = _read(REFERENCES / "coverage.md")
    extract = _section(coverage, "### 2. Extract Technology References", "### 3.")
    assert "write `{run_dir}/technologies.json`, a JSON array" in extract and "(`[]` when there is none)" in extract
    assert "no name from fenced code goes in the file" in extract and "`fenced_only` list" in extract
    for gone in ("**Section-based detection:**", "**Contextual detection:**", "**Build a deduplicated list**"):
        assert gone not in coverage, gone
    match = _section(coverage, "### 3. Cross-Reference Against Skills", "**Detect a deliberate-removal signal")
    assert TECHNOLOGIES_CALL in match
    assert "each `covered_by` entry of kind `name` or `alias`" in match
    assert "Judge only the names in `unverified_technologies`" in match
    assert "A `name-contained` or `alias-contained` entry is no match by itself: React Native is not `react`." in match
    # The folded common aliases and the framework rule.
    for kept in ('"ReactJS" or "react.js" for a `react` skill', '"PostgreSQL" for a `postgres` skill',
                 '"Tauri" encompasses the Tauri ecosystem'):
        assert kept in match, kept
    for gone in ("by the skill's name (case-insensitive)", "coveragePatternsData", "### 1. Load Coverage Patterns",
                 "must be binary", "§2's own detection"):
        assert gone not in coverage, gone
    assert "- Each technology gets exactly one verdict: Covered, Missing or Replaced (§3)\n" in coverage

    # The documented calls on a document naming Tailwind CSS and PostgreSQL in prose.
    doc = tmp_path / "architecture.md"
    doc.write_bytes(("# App\n\n## Styling\n\nThe web app styles its pages with Tailwind CSS.\n\n"
                     "## Data\n\nPrisma connects to PostgreSQL over TCP.\n").encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    skills = [{"name": n, "aliases": []} for n in ("postgres", "prisma", "tailwindcss")]
    first = _mentions(MENTIONS_CALL, doc, run_dir, skills)
    assert first["mentioned"] == ["prisma"] and first["unmentioned"] == ["postgres", "tailwindcss"]
    # Section 2 lists the two other technologies; prisma names a mentioned skill.
    _write_technologies(run_dir, ["Tailwind CSS", "PostgreSQL"])
    matched = _mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    covered = {t["name"]: [(c["skill"], c["kind"]) for c in t["covered_by"]] for t in matched["technologies"]}
    assert covered == {"Tailwind CSS": [("tailwindcss", "name")], "PostgreSQL": []}
    # Tailwind CSS is Covered by script; the model judges PostgreSQL alone, under its common alias.
    assert matched["unverified_technologies"] == ["PostgreSQL"]
    assert matched["mentioned"] == ["prisma"]
    # Both matched skills go unmentioned, so the run again adds both terms.
    rerun = _with_alias(_with_alias(skills, "tailwindcss", "Tailwind CSS"), "postgres", "PostgreSQL")
    final = _mentions(TECHNOLOGIES_CALL, doc, run_dir, rerun)
    assert final["mentioned"] == ["postgres", "prisma", "tailwindcss"] and final["unmentioned"] == []
    assert [(c["a"], c["b"]) for c in final["candidates"]] == [("postgres", "prisma")]
    assert final["unverified_technologies"] == []


def test_a_named_skill_keeps_one_row_and_a_glued_version_stays_in_its_alias(tmp_path):
    """#1199 review: a technology the helper matches to a `mentioned` skill adds no second row, and the
    run again keeps a version written onto a name, since the helper finds a term only at word boundaries."""
    coverage = _read(REFERENCES / "coverage.md")
    match = _section(coverage, "### 3. Cross-Reference Against Skills", "**Detect a deliberate-removal signal")
    assert "- A technology matched to a `mentioned` skill adds no row: that skill's own row stands.\n" in match
    rerun = _section(match, "**Run the mentions helper again", "\n\n")
    assert "Keep a version written onto the name (`Vue3`, not `Vue`)" in rerun

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # "Tailwind CSS" is no word-boundary mention of tailwindcss, yet the helper covers it by that named skill.
    doc = tmp_path / "architecture.md"
    doc.write_bytes(("# App\n\n## Styling\n\nPages use tailwindcss utilities.\n\n"
                     "## Build\n\nTailwind CSS runs in the build.\n").encode("utf-8"))
    skills = [{"name": "tailwindcss", "aliases": []}]
    _write_technologies(run_dir, ["Tailwind CSS"])
    matched = _mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    assert matched["mentioned"] == ["tailwindcss"]
    assert [[c["skill"] for c in t["covered_by"]] for t in matched["technologies"]] == [["tailwindcss"]]

    # "Vue3" with its version stripped is covered by vue, but only the written term names vue in the run again.
    doc.write_bytes("# App\n\n## UI\n\nThe UI keeps its Vue3 state in Pinia.\n".encode("utf-8"))
    skills = [{"name": "pinia", "aliases": []}, {"name": "vue", "aliases": []}]
    _write_technologies(run_dir, ["Vue"])
    matched = _mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    assert matched["mentioned"] == ["pinia"]
    assert [(c["skill"], c["kind"]) for c in matched["technologies"][0]["covered_by"]] == [("vue", "name")]
    stripped = _mentions(TECHNOLOGIES_CALL, doc, run_dir, _with_alias(skills, "vue", "Vue"))
    assert stripped["unmentioned"] == ["vue"]
    written = _mentions(TECHNOLOGIES_CALL, doc, run_dir, _with_alias(skills, "vue", "Vue3"))
    assert written["mentioned"] == ["pinia", "vue"]
    assert [(c["a"], c["b"]) for c in written["candidates"]] == [("pinia", "vue")]


def test_a_contained_name_or_an_empty_list_matches_no_skill(tmp_path):
    """#1199: a skill name found only inside a longer name covers nothing, an empty technologies file
    adds empty lists, and a technologies file the helper rejects fails the call (the coverage:mentions HALT)."""
    coverage = _read(REFERENCES / "coverage.md")
    run = _section(coverage, "**Match the other technologies by script.**", "```bash")
    assert "overwriting `{docMentionsFile}` (the same HALT applies)" in run
    match = _section(coverage, "### 3. Cross-Reference Against Skills", "**Detect a deliberate-removal")
    assert TECHNOLOGIES_CALL in match
    extract = _section(coverage, "### 2. Extract Technology References", "### 3.")
    assert ('If no candidate exists, or the command exits non-zero, HALT (exit code 3, `halt_reason: '
            '"resolution-failure"`) at phase `coverage:mentions`, naming its first stderr line') in extract

    doc = tmp_path / "architecture.md"
    doc.write_bytes("# App\n\n## Mobile\n\nThe mobile app is built with React Native.\n".encode("utf-8"))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    skills = [{"name": "react", "aliases": []}]
    _write_technologies(run_dir, ["React Native"])
    matched = _mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    [technology] = matched["technologies"]
    assert [(c["skill"], c["kind"]) for c in technology["covered_by"]] == [("react", "name-contained")]
    assert matched["unverified_technologies"] == ["React Native"]

    _write_technologies(run_dir, [])
    empty = _mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    assert empty["technologies"] == [] and empty["unverified_technologies"] == []

    # A file the helper rejects exits non-zero with a first stderr line to name.
    (run_dir / "technologies.json").write_bytes(b'{"names": ["React Native"]}')
    proc = _run_mentions(TECHNOLOGIES_CALL, doc, run_dir, skills)
    assert proc.returncode != 0 and proc.stdout == ""
    assert "--technologies" in proc.stderr.splitlines()[0]


def test_coverage_states_each_rule_once():
    """#1199 architecture-5 and leanness-7: coverage-patterns.md is folded into coverage.md, and section 4
    keeps one Extra/Orphan list."""
    assert not (REFERENCES / "coverage-patterns.md").exists()
    suffixes = {".md", ".toml", ".py", ".json", ".yaml"}
    for path in sorted(p for p in SKILL.rglob("*") if p.is_file() and p.suffix in suffixes):
        text = _read(path)
        for gone in ("coverage-patterns.md", "coveragePatternsData", "Verdict Evidence Format", "must be binary",
                     "by the skill's name (case-insensitive)"):
            assert gone not in text, f"{_rel(path)}: {gone}"
    coverage = _read(REFERENCES / "coverage.md")
    extras = _section(coverage, "### 4. Detect Extra Skills", "### 5.")
    assert extras.count("**Subdivide") == 1 and "**For each extra skill:**" not in extras
    assert [line for line in extras.splitlines() if line.startswith("Both are informational")] == [
        "Both are informational: neither affects the coverage verdict."]
    for note in ("exists and has a resolvable `source_repo`, but no architecture reference was found.",
                 "has no resolvable `source_repo`, so it cannot be cross-referenced against the architecture."):
        assert coverage.count(note) == 1, note
    # Section numbers stay put once section 1 goes, so every section reference holds.
    headings = [line for line in coverage.splitlines() if line.startswith("### ")]
    assert [h.split(".", 1)[0] for h in headings] == ["### 2", "### 3", "### 4", "### 5", "### 6", "### 7"]
    # SKILL.md names the rules file and the stage that loads it.
    conventions = _section(_read(SKILL / "SKILL.md"), "## Conventions", "## Role")
    assert "`integrations.md` loads `integration-verification-rules.md`" in conventions
    assert "static reference docs" not in conventions


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
    # The tally's --render owns the row's format: the prose keeps only why it has its own label.
    assert "one more `Risky` row, which §6 renders after the pair rows" in rows
    assert "Its `lib_a`, `cycle`, keeps the row apart from every pair row" in rows
    assert "arrow chain" not in rows and "append a synthetic row" not in rows
    risky = _section(_read(REFERENCES / "synthesize.md"), "**Risky integration (from Step 03):**", "**Plausible integration")
    assert "`cycle` in its `lib_a`, the chain in its `lib_b`" in risky
    # The tally renders that row, with the label and the chain the delta reads.
    spec = importlib.util.spec_from_file_location("skf_coverage_tally_contract", TALLY)
    tally = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tally)
    chain = ["oms-cognee", "zod", "react-query", "oms-cognee"]
    [row] = tally.render_integrations({"rows": []}, {"cycles": [chain]})
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[:3] == ["cycle", "oms-cognee → zod → react-query → oms-cognee", "Risky"]
    # The delta keys rows on their two libraries: the cycle row stays its own row.
    spec = importlib.util.spec_from_file_location("skf_report_delta_contract", REPORT_DELTA)
    delta = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(delta)
    pair = {"libA": "react-query", "libB": "zod", "verdict": "Verified"}
    cycle = {"libA": cells[0], "libB": cells[1], "verdict": cells[2]}
    out = delta.compute({"previous": {"coverage": [], "integration": [pair]},
                         "current": {"coverage": [], "integration": [pair, cycle]}})
    assert out["unchanged"] == ["react-query ↔ zod"]
    assert out["new"] == ["cycle ↔ oms-cognee → zod → react-query → oms-cognee"]
    assert out["regressedCount"] == 0


def test_the_api_surface_reads_have_a_sequential_fallback():
    """enhancement-5: without subagents, the parent reads one SKILL.md at a time and puts each
    summary on disk before the next, so a compaction loses none."""
    surfaces = _section(_read(REFERENCES / "integrations.md"), "### 3. Load Skill API Surfaces", "### 4.")
    [fallback] = [p for p in surfaces.split("\n\n") if p.startswith("**When subagents are unavailable**")]
    for needle in ("one at a time", "compact JSON by the rules above",
                   "to `{run_dir}/summaries/<skill>.json` at once, then go on to the next",
                   "Each summary is on disk as its read ends, so a context compaction loses none."):
        assert needle in fallback, needle
    assert "keep only that JSON" not in fallback and "append it to" not in fallback
    # #1197: each read writes its own file and the merge helper checks them, so
    # no paragraph collects replies or checks their keys by hand.
    assert "**Parent collects all JSON summaries.**" not in surfaces
    assert "**Schema validation (parent):**" not in surfaces
    assert surfaces.index("**When subagents are unavailable**") < surfaces.index("**Merge the summaries.**")
    [budget] = [p for p in surfaces.split("\n\n") if p.startswith("**If `over_budget` is true**")]
    assert "so the fallback never halts here" in budget
    assert "Do not load full SKILL.md content into parent context" not in surfaces
    assert "never load a full SKILL.md into the parent context" in surfaces
    [reread] = [p for p in surfaces.split("\n\n") if p.startswith("**Re-read each rejected skill once.**")]
    assert "Apart from the fallback's reads and these re-reads, never load a full SKILL.md" in reread


def test_a_blocked_recommendation_follows_the_named_candidate_requirement():
    """w3 architecture-3: the report section states the rule itself, since step 5 is not loaded yet."""
    integrations = _read(REFERENCES / "integrations.md")
    assert "H6" not in integrations and "step 5 §2" not in integrations
    write = _section(integrations, "### 6. Append to Report", "### 7.")
    assert ("a Blocked one that proposes a replacement names at least one alternative library with a one-line "
            "justification, or says no named candidate was found and gives the selection criteria") in write
    blocked = _section(_read(REFERENCES / "synthesize.md"), "**Blocked integration (from Step 03):**",
                       "**Not Addressed requirement")
    assert "**Named-candidate requirement:**" in blocked
    # #1201 leanness-2: one line asks for the replacement or the bridge, under that rule, in place of
    # the stock sentences that named neither.
    lines = [line for line in blocked.splitlines() if line.startswith("- ")]
    assert len(lines) == 2 and lines[1].startswith("- **Named-candidate requirement:**"), lines
    for needle in ("a replacement for `{blocked_lib}`", "the bridge that lets it work with `{other_lib}`",
                   "the integration path the architecture document must change",
                   "a replacement follows the Named-candidate requirement below",
                   "and a bridge is named as the Risky line above names one."):
        assert needle in lines[0], needle
    synthesize = _read(REFERENCES / "synthesize.md")
    for stock in ("Consider adding a bridge layer", "Add a serialization/conversion layer",
                  "introduce an IPC/FFI bridge", "with an alternative that is compatible with"):
        assert stock not in synthesize, stock
    assert "- Recommendations must name specific tools, libraries, or actions" in synthesize


def test_a_risky_recommendation_names_the_bridge_for_its_pair():
    """#1201 leanness-2: a protocol, type or language gap gets the bridge for this pair, already in the stack or
    named, and where the architecture document records it or must add it, or a notice that none could be named,
    as a Blocked replacement has; the cycle, mid-run and unreadable lines follow."""
    risky = _section(_read(REFERENCES / "synthesize.md"), "**Risky integration (from Step 03):**",
                     "**Plausible integration")
    lines = [line for line in risky.splitlines() if line.startswith("- ")]
    assert lines[0].startswith("- If a protocol, type or language gap → name the specific bridge for "
                               "`{lib_a}` ↔ `{lib_b}`: "), lines[0]
    for needle in ("one already in the stack", "else a named library, codec or adapter that closes the gap",
                   "and where the architecture document records it, or must add it.",
                   "If no bridge can be named, write \"No named bridge identified: manual research required\" and "
                   "one sentence on the selection criteria the user should apply."):
        assert needle in lines[0], needle
    starts = ["- If circular dependency", "- If a skill changed mid-run", "- If a skill's API surface could not be read"]
    assert [line[:len(start)] for line, start in zip(lines[1:], starts)] == starts and len(lines) == 4, lines


def test_synthesize_alone_writes_the_requirement_recommendations():
    """#1201 architecture-4: requirements.md §5 writes the table and the Partially Fulfilled gaps and no
    recommendation, so `## Recommendations` lists each one once, under synthesize's prioritized list, and their
    number is the rollup's `recommendationCount`."""
    requirements = _read(REFERENCES / "requirements.md")
    assert "Include recommendations for Not Addressed and Partially Fulfilled items" not in requirements
    write = _section(requirements, "### 5. Append to Report", "### 6.")
    bullets = [line for line in write.splitlines() if line.startswith("- ")]
    assert bullets == [
        "- Include the full requirements coverage table, with its **Not read:** lines",
        "- Include the gap §4 shows for each Partially Fulfilled requirement, and no recommendation: synthesize "
        "writes one for each Not Addressed and Partially Fulfilled requirement, in its prioritized list"]
    assert "**Gap:** {what remains unaddressed}" in _section(requirements, "### 4. Display Requirements Results",
                                                             "### 5.")
    synthesize = _read(REFERENCES / "synthesize.md")
    recommendations = _section(synthesize, "### 2. Generate Prescriptive Recommendations", "### 3.")
    assert "**Not Addressed requirement (from Step 04):**" in recommendations
    assert "**Partially Fulfilled requirement (from Step 04):**" in recommendations
    assert ("`{run_dir}/recommendations.md`: the prioritized recommendation list"
            in _section(synthesize, "### 5. Append to Report", "### 6."))
    # R1 Fulfilled, R2 Not Addressed, R3 Partially Fulfilled and no other finding: two items.
    spec = importlib.util.spec_from_file_location("skf_verdict_rollup_contract", ROLLUP)
    rollup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rollup)
    out = rollup.rollup({"coveragePercentage": 100, "coveredCount": 2, "missingCount": 0, "replacedCount": 0,
                         "pairsVerified": 1, "pairsPlausible": 0, "pairsRisky": 0, "pairsBlocked": 0,
                         "requirementsEvaluated": True, "requirementsNotAddressed": 1, "requirementsPartial": 1})
    assert out["recommendationCount"] == 2
    assert {kind: n for kind, n in out["recommendations"].items() if n} == {"notAddressed": 1, "partial": 1}


def test_report_presents_the_recommendations_once():
    """#1201 leanness-3: one pass gives the verdict line, synthesize's list in its order (about 5 of each kind,
    the rest left to the report), then the Suggested next workflow block, the only place the count shows."""
    report = _read(REFERENCES / "report.md")
    assert "Present Detailed Findings" not in report
    assert "There are {recommendationCount} items to address" not in report
    present = _section(report, "### 4. Present Findings and Next Steps", "### 4b. Result Contract")
    order = ["- **`FEASIBLE`:**", "- **`CONDITIONALLY_FEASIBLE`:**", "- **`NOT_FEASIBLE`:**",
             "Then walk the list under `### Prioritized Recommendations`", "**Suggested next workflow**"]
    at = [present.index(token) for token in order]
    assert at == sorted(at), order
    # The list stops at the delta heading synthesize writes after it, and each kind's count is the rollup's.
    for needle in ("in its order, which ends at the `#### Delta from Previous Run` heading",
                   "`{run_dir}/rollup.json`, the verdict rollup synthesize wrote, gives under `recommendations` "
                   "how many items of each kind the list holds, in the list's order",
                   "name about 5 of each kind", "say how many more `{outputFile}` lists, from that count",
                   "as synthesize wrote it, and add no count of your own"):
        assert needle in present, needle
    assert "{recommendationCount}" not in present and "then list the" not in present
    assert "only recommendation list" not in present
    synthesize = _read(REFERENCES / "synthesize.md")
    assert "under a `#### Delta from Previous Run` heading; then the suggested next workflow, last" in synthesize
    assert 'uv run {verdictRollupScript} --report "{outputFile}" > "{run_dir}/rollup.json"' in synthesize
    # §4 reads the rollup before §5 deletes the run folder that holds it.
    assert report.index('rm -rf "{run_dir}"') > report.index("### 5. Finish")
    block = _section(_read(REFERENCES / "synthesize.md"), "**Suggested next workflow**", "### 5.")
    assert "\"Address the {recommendationCount} recommendations above" in block


def test_the_summary_reads_the_frontmatter_keys_and_shows_a_zero_count():
    """#1201 leanness-9: §1 names the keys with no alias and the table reads them, so a completed requirements
    pass that counted 0 shows 0, and only a skipped pass shows N/A (no PRD)."""
    report = _read(REFERENCES / "report.md")
    assert "(as `" not in report
    for alias in ("verified_count", "plausible_count", "risky_count", "blocked_count", "fulfilled_count",
                  "partial_count", "not_addressed_count"):
        assert alias not in report, alias
    assert '"recommendation_count": <recommendationCount>' in _section(report, "### 4b. Result Contract",
                                                                       "### 5. Finish")
    summary = _section(report, "### 2. Present Summary", "### 4.")
    cells = {row.split("|")[1].strip(): row.split("|")[2].strip()
             for row in summary.splitlines() if row.startswith("| **")}
    for metric, key in (("Verified", "pairsVerified"), ("Plausible", "pairsPlausible"), ("Risky", "pairsRisky"),
                        ("Blocked", "pairsBlocked")):
        assert cells[f"**Integrations {metric}**"] == "{" + key + "}"
    for metric, key in (("Fulfilled", "requirementsFulfilled"), ("Partially Fulfilled", "requirementsPartial"),
                        ("Not Addressed", "requirementsNotAddressed")):
        assert cells[f"**Requirements {metric}**"] == (
            "{" + key + ", or 'N/A (no PRD)' when `requirementsPass` is \"skipped\"}")
    # The value each requirements call records is the one the cells test.
    spec = importlib.util.spec_from_file_location("skf_report_update_contract", REPORT_UPDATE)
    update = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(update)
    assert update.KINDS["requirements-skipped"].fixed == (("requirementsPass", "skipped"),)
    assert update.KINDS["requirements"].fixed == (("requirementsPass", "completed"),)


def test_requirements_takes_the_prd_path_from_the_report_and_states_each_rule_once():
    """#1201 architecture-9, leanness-4: §2 opens with where the PRD path comes from, as coverage.md does for
    the architecture document; §3 keeps the summaries rule, the delegation and the three verdict definitions."""
    requirements = _read(REFERENCES / "requirements.md")
    extract = _section(requirements, "### 2. Extract Requirements", "### 3.")
    assert extract.split("\n\n")[1] == ("Take the PRD's path from `prdDoc` in the `{outputFile}` frontmatter, "
                                        "then parse that document for capability requirements.")
    assert ("Take the architecture document's path from `architectureDoc` in the `{outputFile}` frontmatter"
            in _read(REFERENCES / "coverage.md"))
    assert "feature, technical, non-functional, integration, or infrastructure" in extract
    for gone in ("**Look for:**", "**Assessment method:**", "Match each requirement against",
                 "**Each verdict includes:**"):
        assert gone not in requirements, gone
    assess = _section(requirements, "### 3. Assess Stack Coverage", "### 4.")
    paragraphs = assess.split("\n\n")
    assert any(p.startswith("When a verdict turns on a detail no summary holds, delegate it: one subagent reads "
                            "that skill's SKILL.md and returns only") for p in paragraphs)
    [definitions] = [p for p in paragraphs if p.startswith("**Assign verdict per requirement:**")]
    assert [line.split("**")[1] for line in definitions.splitlines()[1:]] == [
        "Fulfilled", "Partially Fulfilled", "Not Addressed"]


def test_requirements_reads_the_step_3_summaries_not_skill_md():
    requirements = _read(REFERENCES / "requirements.md")
    assess = _section(requirements, "### 3. Assess Stack Coverage", "### 4.")
    assert "{skillSummariesFile}" in assess
    assert "never from a SKILL.md read in this context" in assess
    assert "Read each skill's SKILL.md" not in requirements
    assert "skillSummariesFile: '{run_dir}/skill-summaries.json'" in requirements.split("\n---\n", 1)[0]


def test_the_rules_file_says_the_scanner_runs_check_4():
    rules = _read(REFERENCES / "integration-verification-rules.md")
    # Check 4 ends the file: no evidence template follows it (#1199 leanness-1).
    check4 = rules[rules.index("### 4. Documentation Cross-Reference"):]
    assert "Verdict Evidence Format" not in rules and "## Purpose" not in rules and "\n---" not in check4
    assert "Extract: verification checks" not in _read(REFERENCES / "integrations.md")
    assert "**Each verdict includes:**" in _read(REFERENCES / "integrations.md")
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
    # Extra aliases go through persistent_facts, and the comment shows the `!`
    # override that drops the bundled project-context.md entry (#596 decision).
    facts = _section(raw, "# Persistent facts", "\npersistent_facts = [")
    assert "Extra aliases go here" in facts and "as aliases of that skill" in facts
    assert '#   persistent_facts = ["!file:{project-root}/**/project-context.md"]' in facts
    assert "cannot remove it" not in facts and "add a literal fact" not in facts
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


def test_init_checks_the_template_and_the_report_it_creates():
    """#1110: a template override that names no file halts before the Load,
    and a copy that breaks the schema halts once step 1 wrote the report,
    each naming the setting and the path, not at step 6."""
    section = _section(_read(REFERENCES / "init.md"), "### 4. Create Feasibility Report",
                       "### 5. Display Initialization Summary")
    missing = 'HALT (exit code 3, `halt_reason: "resolution-failure"`) at phase `init:report-template`'
    broken = 'HALT (exit code 5, `halt_reason: "schema-violation"`) at phase `init:report-template`'
    assert section.count(missing) == 1 and section.count(broken) == 1
    order = [
        'test -f "{reportTemplatePath}" && test -r "{reportTemplatePath}"',
        missing,
        "**Load** `{reportTemplatePath}`",
        "python3 {atomicWriteHelper} write --target {outputFile}",
        'uv run {validateFeasibilityReportHelper} "{outputFile}" -o "{run_dir}/template-check.json"',
        broken,
    ]
    positions = [section.index(needle) for needle in order]
    assert positions == sorted(positions), order
    flat = " ".join(section.split())
    check = flat[flat.index("**Check the template.**"):flat.index("**Load**")]
    assert '`"path": "{reportTemplatePath}"`' in check
    assert "`report_template_path` names `{reportTemplatePath}`, which is not a readable file." in check
    assert ("Point it at your copy in `{project-root}/_bmad/custom/skf-verify-stack.toml` or `.user.toml`, or "
            "re-install SKF when it is the bundled `assets/feasibility-report-template.md`.") in check
    after = flat[flat.index("**Check the new report.**"):]
    assert '`"report_path": "{outputFile}"`' in after
    for field in ("missingHeadings", "orderViolations", "verdictTableFound", "duplicateVerdictTableLine",
                  "unknownTokens", "schemaVersionFound"):
        assert f"`{field}`" in after, field
    assert "leave `{outputFileLatest}` as it is" in after
    assert "`report_template_path` names `{reportTemplatePath}`, whose report fails the feasibility-report check:" in (
        after)
    rows = _exit_code_rows()
    assert "step 1 §4 (the report template names no readable file, phase `init:report-template`)" in rows[3]
    assert ("step 1 §4 (the report created from the template fails the feasibility-report check, phase "
            "`init:report-template`) → `schema-violation`") in rows[5]
    comment = _section(_read(SKILL / "customize.toml"), "# The template step 1", "report_template_path =")
    flat_comment = " ".join(line.lstrip("#").strip() for line in comment.splitlines())
    for said in ("Step 1 halts (`resolution-failure`) when the path names no readable file",
                 "one verdict table, no unknown verdict token", "step 6 checks the finished report again",
                 "Nothing checks the Evidence Sources table"):
        assert said in flat_comment, said
    skill = " ".join(_read(SKILL / "SKILL.md").split())
    assert ("`{reportTemplatePath}` ← `workflow.report_template_path` if non-empty, else "
            "`assets/feasibility-report-template.md`, bound as the file it names (`{project-root}` replaced, a bare "
            "path taken from `{skill-root}`).") in skill
    assert ("An empty or absent value falls through to that default; init.md §4 checks that it is a readable file "
            "before it loads it, and checks the report it creates from it.") in skill


@pytest.mark.parametrize("case", ["bundled", "lost-heading"])
def test_the_check_of_the_new_report_passes_the_default_and_fails_a_broken_copy(tmp_path, case):
    """The bundled template passes the init.md §4 check, so the halt never
    fires on the default; a copy without `## Recommendations` fails it, and
    the JSON names the heading the halt reports."""
    template = _read(SKILL / "assets" / "feasibility-report-template.md")
    if case == "lost-heading":
        assert template.count("## Recommendations\n") == 1
        template = template.replace("## Recommendations\n", "")
    report = tmp_path / "feasibility-report-app-20261001-101500.md"
    report.write_bytes(template.encode("utf-8"))
    run_dir = _run_dir(tmp_path)
    # The check as init.md §4 writes it, after the report's atomic write.
    section = _section(_read(REFERENCES / "init.md"), "**Check the new report.**", "### 5.")
    command = re.search(r"Run `(uv run \{validateFeasibilityReportHelper\} [^`]+)`", section).group(1)
    words = shlex.split(command)
    assert words[:3] == ["uv", "run", "{validateFeasibilityReportHelper}"], command
    filled = [w.replace("{outputFile}", report.as_posix()).replace("{run_dir}", run_dir.as_posix()) for w in words[3:]]
    proc = _run([SCRIPTS / "skf-validate-feasibility-report.py", *filled])
    out = run_dir / "template-check.json"
    check = json.loads(out.read_text(encoding="utf-8"))
    if case == "bundled":
        assert proc.returncode == 0, proc.stderr
        assert check["status"] == "ok" and check["violation"] is None
    else:
        assert proc.returncode == 1, proc.stderr
        assert check["missingHeadings"] == ["Recommendations"]


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="runs the check through bash")
def test_the_template_check_fails_a_path_that_names_no_file(tmp_path):
    init = _read(REFERENCES / "init.md")
    command = re.search(r'`(test -f "\{reportTemplatePath\}" && test -r "\{reportTemplatePath\}")`', init).group(1)
    for path, readable in ((SKILL / "assets" / "feasibility-report-template.md", True),
                           (tmp_path / "house" / "feasibility.md", False)):
        filled = command.replace('"{reportTemplatePath}"', shlex.quote(path.as_posix()))
        proc = subprocess.run(["bash", "-c", filled], capture_output=True, text=True, check=False)
        assert (proc.returncode == 0) is readable, path


def test_no_stage_reads_a_removed_setting():
    for path in [SKILL / "SKILL.md", *sorted(REFERENCES.glob("*.md"))]:
        text = _read(path)
        for stale in ("{integrationRulesPath}", "{coveragePatternsPath}", "integration_rules_path",
                      "coverage_patterns_path", "output_folder_path"):
            assert stale not in text, f"{_rel(path)}: {stale}"
    # The integrations stage loads the bundled rules file by its path from the skill root;
    # coverage loads no data file, its patterns folded into it (#1199).
    integrations = _frontmatter(_read(REFERENCES / "integrations.md"))
    assert "integrationRulesData: 'references/integration-verification-rules.md'" in integrations
    assert (REFERENCES / "integration-verification-rules.md").is_file()
    assert "Data:" not in _frontmatter(_read(REFERENCES / "coverage.md"))
    assert not (REFERENCES / "coverage-patterns.md").exists()
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
    contract = _read(REFERENCES / "invocation-contract.md")
    bind = next(line for line in skill.splitlines() if "**Bind the inputs**" in line)
    assert "in every mode" in bind
    flags = next(line for line in contract.splitlines() if line.startswith("| **Flags** |"))
    for variable, flag in (("{architecture_doc_path}", "--architecture-doc"), ("{prd_path}", "--prd"),
                           ("{previous_report_path}", "--previous-report")):
        assert f"`{variable}` ← " in bind and f"`{flag}`" in bind, variable
        assert f"`{flag} <path>`" in flags, flag
    assert "`--previous-report none` runs without one" in flags
    inputs = next(line for line in contract.splitlines() if line.startswith("| **Inputs** |"))
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
    # The helper looks for an earlier report only when no path was given, and a given one runs it with --provided.
    found = _section(init, "**Find the previous report first.**", "```bash")
    assert "When `{previous_report_path}` is null, run the previous-report helper without `--provided`" in found
    given = _section(init, "**Resolve a given previous report**", "- `collision`")
    assert "(when `{previous_report_path}` is set)" in given and "with `--provided` set to it" in given
    fill = next(line for line in init.splitlines() if line.startswith("**Fill the per-run frontmatter keys**"))
    assert "`architectureDoc` ← `{architecture_doc_path}`" in fill and "`prdDoc` ← `{prd_path}` (or `none`)" in fill
    # The summary table reads the variables activation and step 1 bind.
    summary = _section(init, "### 5. Display Initialization Summary", "**Skill Inventory:**")
    assert "| **Architecture Doc** | {architecture_doc_path} |" in summary
    assert ("| **PRD Document** | {prd_path, with ' (not found: requirements pass will be skipped)' after it when "
            "prdAvailable is false, or 'Not provided: requirements pass will be skipped'} |") in summary
    assert "{prd_doc" not in init and "{architecture_doc}" not in init


# --- Step 1 asks only what the run needs (#1200) ------------------------------------------


def test_step_1_checks_the_skills_before_any_prompt():
    """A forge with too few skills halts before the user types a path: the skills folder checks, the enumerate
    call and the skill-count halt need no input, so they run in the pre-flight, after the slug is bound."""
    init = _read(REFERENCES / "init.md")
    first_prompt = init.index("### 1. Accept Input Documents")
    bind = init.index("**Bind `{project_slug}`.**")
    checks = ['(exit code 3, `halt_reason: "skills-folder-missing"`) at phase `init:skills-folder`',
              'uv run {enumerateStackSkillsHelper} enumerate {skills_output_folder} --reliability > "{inventoryFile}"',
              '(exit code 3, `halt_reason: "resolution-failure"`) at phase `init:inventory`',
              '(exit code 7, `halt_reason: "inventory-unreliable"`) at phase `init:inventory`',
              '(exit code 5, `halt_reason: "insufficient-skills"`) at phase `init:skill-count`']
    at = [init.index(check) for check in checks]
    assert bind < min(at) and max(at) < first_prompt, at
    assert init.count("at phase `init:skill-count`") == 1 and init.count("at phase `init:skills-folder`") == 2
    # Nothing that waits for the user, nor the previous-report helper, runs before the skill count is checked.
    for later in ("**Verify Stack: Feasibility Analysis**", "uv run {previousReportScript}", "wait for user input"):
        assert init.index(later) > max(at), later
    assert "(used by the skill-count check below, §4, §5," in init
    # The section numbers every reference names stay put: no section 2 or 3 is left to point at.
    headings = [line.split(".", 1)[0] for line in init.splitlines() if line.startswith("### ")]
    assert headings == ["### 1", "### 4", "### 5", "### 6"], headings
    rows = _exit_code_rows()
    assert "step 1 pre-flight (`{skills_output_folder}` does not exist" in rows[3]
    assert "step 1 pre-flight (fewer than 2 valid skills" in rows[5]
    assert "step 1 pre-flight (enumerate-stack-skills warnings" in rows[7]
    for path in _markdown():
        for stale in ("step 1 §2", "step 1 §3", "init.md §2", "init.md §3"):
            assert stale not in _read(path), f"{_rel(path)}: {stale}"


def test_step_4_fills_only_the_per_run_keys():
    init = _read(REFERENCES / "init.md")
    create = _section(init, "### 4. Create Feasibility Report", "### 5. ")
    [fill] = [line for line in create.splitlines() if line.startswith("**Fill the per-run frontmatter keys**")]
    assert fill.startswith("**Fill the per-run frontmatter keys** and keep every other template value: ")
    keys = ["projectName", "projectSlug", "generatedAt", "prdAvailable", "architectureDoc", "prdDoc",
            "previousReport", "skillsAnalyzed", "stepsCompleted"]
    at = [fill.index(f"`{key}`" if key != "stepsCompleted" else f"`{key}: ") for key in keys]
    assert at == sorted(at), keys
    assert "`stepsCompleted: ['init']`" in fill and "`skillsAnalyzed` ← `{skill_count}`" in fill
    for gone in ("**Populate frontmatter", "provisional until step 5", "This skill produces the feasibility report "
                 "schema", "**Populate producer-local bookkeeping keys"):
        assert gone not in init, gone
    # The constants step 1 no longer lists are the template's own values.
    template = _frontmatter(_read(SKILL / "assets" / "feasibility-report-template.md"))
    for constant in ('schemaVersion: "1.0"', "reportType: feasibility", "generatedBy: skf-verify-stack",
                     'overallVerdict: "CONDITIONALLY_FEASIBLE"', "coveragePercentage: 0", "pairsVerified: 0",
                     "pairsPlausible: 0", "pairsRisky: 0", "pairsBlocked: 0", "recommendationCount: 0"):
        assert f"\n{constant}\n" in template, constant
    # The fill line comes after the template is loaded and before the report is written.
    assert create.index("**Load** `{reportTemplatePath}`") < create.index(fill) < create.index("**Atomic write:**")


def test_a_path_that_was_not_found_is_asked_once_and_recorded_when_headless():
    init = _read(REFERENCES / "init.md")
    prd = _section(init, "**Validate the PRD (when `{prd_path}` is set):**", "**Resolve a given previous report**")
    assert ('If missing or unreadable, an interactive run asks once: "PRD not found at `{prd_path}`: give another '
            'path, or press Enter to continue without it." It checks a path given there the same way, with no further '
            'ask.') in prd
    assert ('"PRD document not found at `{prd_path}`. Proceeding without PRD: the requirements pass will be '
            'skipped."') in prd
    # The report names the PRD that was given, so it never reads as if none was.
    assert ("Keep `{prd_path}`, the last path given, so the report's `prdDoc` names it, with "
            "`prdAvailable: false`") in prd
    assert "in headless, record `prd_not_found: <path>` now" in prd
    assert "Set `{prd_path}` to null" not in init
    given = _section(init, "**Resolve a given previous report**", "**Record a path that was not found.**")
    missing = given[given.index("- `not-found`"):given.index("- `provided`")]
    assert ('an interactive run asks once: "Previous report not found at `{provided}`: give another path, press '
            'Enter to compare against the most recent one, or type `none` to skip the comparison."') in missing
    assert "a second `not-found` asks nothing" in missing
    assert "Set `previousReport` to empty; in headless, record `previous_report_not_found: <path>` now" in missing
    # Enter at a re-ask takes the report the helper returns: line 3, which offered it before the prompt, is past.
    assert ("an empty answer runs it without `--provided` and sets `previousReport` to the `previousReport` it "
            "returns") in given
    # Only a headless run records the warning: an interactive user saw the message.
    record = _input_warning_block()
    assert record.startswith("**Record a path that was not found.** In headless, record each warning")
    # One warning per call: two lines in one --warning would reach the envelope as one string.
    assert "as its branch above finds it, one at a time: write it alone to `{run_dir}/input-warning.txt`" in record
    assert "with a file write, never `echo` (a path can hold quotes or `$( )`)" in record
    # The requirements pass and the synthesis say the PRD was not found when a path was given.
    requirements = _read(REFERENCES / "requirements.md")
    assert ("{IF `prdDoc` in the `{outputFile}` frontmatter names a path, not `none`:}The PRD at `{prdDoc}` was not "
            "found.{ELSE:}No PRD or vision document was provided.{END IF}") in requirements
    assert "(no PRD/vision document was provided, or the one given was not found)" in requirements
    synthesize = _read(REFERENCES / "synthesize.md")
    assert ("requirements were not evaluated ({IF `prdDoc` names a path, not `none`:}the PRD at `<prdDoc>` was not "
            "found{ELSE:}no PRD provided{END IF})") in synthesize
    assert "a PRD path (not `none`) whose `prdAvailable` is false marked `(not found)`" in synthesize
    # The report header, the summary and the caller contract name a path that was not found as not found.
    fill = next(line for line in init.splitlines() if line.startswith("**Fill the per-run frontmatter keys**"))
    assert ("The header lines under the title take the same values, with ` (not found)` after `{prdDoc}` when "
            "`prdAvailable` is false and `prdDoc` is not `none`.") in fill
    assert ("| **Previous Report** | {previousReport, or 'Not found: no delta comparison' when the path given was not "
            "found, or 'Not provided: no delta comparison'} |") in init
    assert ("never asked for again, unless an interactive run finds no file there (the validation below then asks "
            "once)") in init
    contract = _read(REFERENCES / "invocation-contract.md")
    headless = next(line for line in contract.splitlines() if line.startswith("| **Headless** |"))
    assert ("A `--prd` or `--previous-report` path that is not found does not halt: the run goes on without it and "
            "lists `prd_not_found: <path>` or `previous_report_not_found: <path>` in the envelope's `warnings`.") in headless


@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="runs the record through bash")
def test_the_input_warning_record_keeps_a_hostile_path_as_text(tmp_path):
    """The path reaches the sink exactly as given: a quote, `$( )` or a backtick in it runs nothing."""
    block = re.search(r"```bash\n(.*?)\n```", _input_warning_block(), re.S).group(1)
    assert block == INPUT_WARNING_RECORD
    run_dir = _run_dir(tmp_path)
    warning = 'prd_not_found: docs/my "prd" $(touch pwned) `touch pwned2`.md'
    (run_dir / "input-warning.txt").write_bytes((warning + "\n").encode("utf-8"))
    filled = (block.replace("uv run {emitEnvelopeHelper}", f'"{sys.executable}" "{EMITTER.as_posix()}"')
              .replace("{run_dir}", run_dir.as_posix()))
    proc = subprocess.run(["bash", "-c", filled], capture_output=True, timeout=60, cwd=run_dir, check=False)
    assert proc.returncode == 0, proc.stderr
    lines = (run_dir / "warnings.jsonl").read_bytes().decode("utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [warning]
    assert not (run_dir / "pwned").exists() and not (run_dir / "pwned2").exists()


def test_skill_md_points_to_the_lifted_invocation_contract():
    skill = _read(SKILL / "SKILL.md")
    contract_section = _section(skill, "## Invocation Contract", "## On Activation")
    assert contract_section.strip().splitlines()[1:] == [
        "", "`references/invocation-contract.md` holds the inputs, flags, gates, outputs and headless rules, and the "
        "`SKF_VERIFY_STACK_RESULT_JSON` result contract; `references/exit-codes.md` the exit codes."]
    assert "| **Flags** |" not in skill and "## Result Contract (Headless)" not in skill
    assert "the caller contract (`invocation-contract.md`)" in _section(skill, "## Conventions", "## Role")
    contract = _read(REFERENCES / "invocation-contract.md")
    rows = [line.split("|")[1].strip() for line in contract.splitlines() if line.startswith("| **")]
    assert rows == ["**Inputs**", "**Flags**", "**Gates**", "**Outputs**", "**Headless**", "**Exit codes**"]
    assert contract.count("## Result Contract (Headless)") == 1
    # No halt lives here: every HALT names its stage's phase in the stage file.
    assert "HALT (exit code" not in contract and not contract.startswith("---\n")


def test_the_hook_runs_after_the_run_folder_is_deleted_and_never_ends_the_run():
    """#1109: §5 deletes `{run_dir}` first, so an instruction that starts another workflow leaves no run folder
    behind; then it carries out the instruction, displays a failure on one line and continues, and chains to the
    health check even when the instruction started another workflow."""
    report = _read(REFERENCES / "report.md")
    finish = _section(report, "### 5. Finish", "the health-check step is the true terminal step")
    order = ['rm -rf "{run_dir}"', "If `{workflow.on_complete}` is non-empty, carry out that instruction now",
             "When it fails, display `on_complete failed: {reason}` on a line of its own and continue",
             "execute `{nextStepFile}`, even when the instruction started another workflow"]
    at = [finish.index(token) for token in order]
    assert at == sorted(at), order
    assert "the hook never fails the run, whose report and result files are written" in finish
    assert "in headless, display one line naming what it did" in finish and "log the action" not in finish
    [line] = [line for line in _read(SKILL / "SKILL.md").splitlines() if "`workflow.on_complete`" in line]
    assert "report.md §5 executes it, if non-empty, at the end of step 6, before the health check." in line
    toml = _read(SKILL / "customize.toml")
    comment = " ".join(line.lstrip("#").strip() for line in
                       toml[: toml.index("\non_complete =")].rsplit("\n\n", 1)[-1].splitlines())
    assert comment.startswith("Instruction executed at the end of step 6, before the health check"), comment
    assert "terminal stage" not in comment
