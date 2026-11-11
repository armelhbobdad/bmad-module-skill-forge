"""Tests for test-skill's hard gate and the gap ledger that feeds it.

The coverage, coherence and external validation stages record every gap
they find in a JSON ledger through gap-ledger.py, each with the severity and
the category of its Gap Severity table row, and step 4c runs hard-gate.py on
that ledger (#583, #541). These tests pin that wiring and run it:

- the gate command, and each stage's append command, run as written
  against the real scripts: a Critical coverage gap and a High coherence
  gap block the run, a run whose only gaps are missing exports (now Medium)
  passes, a stage that recorded nothing makes the gate refuse, two missing
  exports of one file stay two records, and a High discovery gap recorded
  after the gate is counted apart from the blocking ones;
- a stale name is a fabricated signature only when the documented
  classify-stale call finds no such name in the file the skill cites
  (#583's decision) and no alias of a name that file declares (#886); one
  the source still declares outside the surface is
  a documented extra, an Info `observation` at its declaration, unless a
  brief scoped it out (#678); and each per-export record gap-ledger.py
  writes from the run files, as the prose calls it, names its export;
- a blocked run is not a halt: it writes the Completeness Score section in
  scoring's place and ends through the report step, which gives the report
  its public name only once its checks pass (#587), renders the Gap Report,
  writes the FAIL
  result contract (exit_code 2, the hard gate's own payload, built by
  build-result-context.py), runs on_complete and dispatches the health check
  (#583 item 2, the architecture-2 handoff);
- the Gap Severity table carries the re-rated rows (#583, #545, #543), every
  category is one gap-ledger.py knows, and every severity and category the
  stage prose writes is a row of the table;
- report.md runs its step and section checks before it publishes the
  report, writes the result contract through the shared emitter and runs
  on_complete, with 'report' out of the expected set and recorded once the
  result files are written, and its grep count catches a stage that skipped
  its section (#585, #583 item 4, #587, #593);
- every discovery skip is a counted Info gap, and discovery gaps reach the
  Gap Report totals (#543);
- each stage's closing line names its stepsCompleted token (#585);
- the exit codes and the result envelope live in references/invocation-contract.md
  (#600), and every HALT names its halt_reason and phase (#593, #594);
- an automator reads the exit code from the run's own result line, never from
  skf-test-skill-result-latest.json: a run that printed no line has no result
  to read (it was cut off, or could not write its result), and that copy then
  holds an earlier run's verdict (the 6.0.0 gate run that ended its turn with
  a subagent still in the background).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import shlex
import shutil
import subprocess
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
REFS = TS_DIR / "references"
STEP_FILE = REFS / "step-hard-gate.md"
INIT_FILE = REFS / "init.md"
DETECT_FILE = REFS / "detect-mode.md"
COVERAGE_FILE = REFS / "coverage-check.md"
# The text only some coverage-check branches take, loaded from the sentence that names its section.
COVERAGE_BRANCHES_FILE = REFS / "coverage-check-branches.md"
COHERENCE_FILE = REFS / "coherence-check.md"
EXT_VALIDATORS_FILE = REFS / "external-validators.md"
SCORE_FILE = REFS / "score.md"
REPORT_FILE = REFS / "report.md"
SCORING_FILE = REFS / "scoring-rules.md"
SKILL_MD = TS_DIR / "SKILL.md"
TEMPLATE_FILE = TS_DIR / "templates" / "test-report-template.md"
FORMATS_FILE = TS_DIR / "assets" / "output-section-formats.md"
GAP_LEDGER = TS_DIR / "scripts" / "gap-ledger.py"
HARD_GATE = TS_DIR / "scripts" / "hard-gate.py"
BUILD_CONTEXT = TS_DIR / "scripts" / "build-result-context.py"
CONTRACT_FILE = REFS / "invocation-contract.md"
VERIFY_PROVENANCE = REPO_ROOT / "src" / "shared" / "scripts" / "skf-verify-provenance-completeness.py"

LEDGER_BINDING = "{forge_version}/test-findings-{run_id}.json"
GATE_CMD = (
    'uv run {hardGateScript} check --ledger "{ledgerFile}" --skill-name "{skill_name}" '
    '--report-path "{publishedReportFile}" --require-stage coverage-check --require-stage coherence-check '
    "--require-stage external-validators"
)
# The stages that record their gaps before the gate, each with the file
# whose append command records them.
RECORDING_STAGES = {
    "coverage-check": COVERAGE_FILE,
    "coherence-check": COHERENCE_FILE,
    "external-validators": EXT_VALIDATORS_FILE,
}
SEVERITIES = ("Critical", "High", "Medium", "Low", "Info")
# "a High `split-body-mismatch` gap", "Medium `structural` gaps".
SEVERITY_CATEGORY_RE = re.compile(r"\b(Critical|High|Medium|Low|Info) `([a-z][a-z-]*)` gaps?\b")
TEMPLATE_HEADINGS = [
    "## Test Summary",
    "## Coverage Analysis",
    "## Coherence Analysis",
    "## External Validation",
    "## Completeness Score",
    "## Gap Report",
]
RUN_ID = "20260930T101010Z-ab12cd34"
# The rule each step after the lock states before its first HALT.
HALT_RELEASE = ('It releases the run lock first, whatever the release prints: from `{project-root}`, run '
                '`uv run {runLockHelper} release --lock "{forge_version}/.test-skill.lock" --owner "{run_owner}"`')
PUBLISHED = "{forge_version}/test-report-{skill_name}-{run_id}.md"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gap_ledger = _load("skf_gap_ledger_for_step_test", GAP_LEDGER)
hard_gate = _load("skf_hard_gate_for_step_test", HARD_GATE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _flow(text: str) -> str:
    """The text with each run of whitespace folded to one space."""
    return re.sub(r"\s+", " ", text)


def _body(path: pathlib.Path) -> str:
    text = _read(path)
    return text.split("\n---\n", 1)[1] if text.startswith("---\n") else text


def _frontmatter(path: pathlib.Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", _read(path), re.DOTALL)
    assert m, f"{path.name} has no frontmatter"
    return yaml.safe_load(m.group(1))


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    return text[i:j]


def _fence(text: str, needle: str) -> str:
    """The fenced block that holds `needle`."""
    i = text.index(needle)
    open_ = text.rindex("```", 0, i)
    body = text.index("\n", open_) + 1
    block = text[body:text.index("```", body)]
    assert needle in block, f"{needle!r} is not inside a fenced block"
    return block


def _append_command(path: pathlib.Path, stage: str) -> str:
    """The documented append command of one stage, up to its heredoc marker."""
    needle = f"--stage {stage} <<'SKF_GAPS'"
    block = _fence(_read(path), needle)
    line = next(line for line in block.splitlines() if needle in line)
    assert block.rstrip().endswith("SKF_GAPS"), f"{path.name}: the heredoc must close with SKF_GAPS"
    return line.split(" <<'SKF_GAPS'")[0]


def _run(command: str, values: dict[str, str], stdin: str = "") -> subprocess.CompletedProcess:
    """Run a prose `uv run {script} ...` command with this Python and `values` filled in."""
    m = re.fullmatch(r"uv run \{(gapLedgerScript|hardGateScript)\} (.*)", command)
    assert m, f"not a gap-ledger or hard-gate call: {command!r}"
    rest = m.group(2)
    for key, value in values.items():
        rest = rest.replace(key, value)
    assert not re.search(r"\{\w+\}", rest), f"unfilled placeholder in {rest!r}"
    script = GAP_LEDGER if m.group(1) == "gapLedgerScript" else HARD_GATE
    return subprocess.run(
        [sys.executable, str(script), *shlex.split(rest)],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _gap(severity: str, category: str, title: str, source: str = "SKILL.md:10", **extra: str) -> dict:
    return {"severity": severity, "category": category, "title": title, "source": source,
            "remediation": f"Fix {title} at `{source}`.", **extra}


def _severity_rows() -> list[tuple[str, str, str]]:
    """(severity, category, criteria) for each row of the Gap Severity table."""
    section = _read(SCORING_FILE)[_read(SCORING_FILE).index("## Gap Severity"):]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0] in SEVERITIES:
            m = re.fullmatch(r"`([a-z][a-z-]*)`", cells[1])
            assert m, f"the Category cell must be one backticked slug: {line!r}"
            rows.append((cells[0], m.group(1), cells[2]))
    assert rows, "the Gap Severity table has no rows"
    return rows


@pytest.fixture
def values(tmp_path: pathlib.Path) -> dict[str, str]:
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"
    return {
        "{ledgerFile}": (forge_version / f"test-findings-{RUN_ID}.json").as_posix(),
        "{skill_name}": "demo",
        "{outputFile}": (forge_version / f".skf-test-report-demo-{RUN_ID}.md").as_posix(),
        "{publishedReportFile}": (forge_version / f"test-report-demo-{RUN_ID}.md").as_posix(),
    }


# A bracketed `[--flag ...]` synopsis group of a prose call, repeatable or not.
OPTIONAL_GROUP_RE = re.compile(r" \[(--[a-z-]+[^\]]*)\](?:\.\.\.)?")


def _ledger_call(path: pathlib.Path, needle: str, keep: tuple[str, ...] = ()) -> str:
    """The one fenced command of `path` that holds `needle`, with the bracketed
    groups whose flag `keep` names kept and the others dropped."""
    lines = [line.strip() for line in _fence(_read(path), needle).splitlines() if needle in line]
    assert len(lines) == 1, (path.name, needle, lines)
    return OPTIONAL_GROUP_RE.sub(lambda m: " " + m.group(1) if m.group(1).split()[0] in keep else "", lines[0])


def _write_json(path: pathlib.Path, data) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data).encode("utf-8"))
    return path


def _ledger_records(values: dict[str, str]) -> list[dict]:
    return json.loads(pathlib.Path(values["{ledgerFile}"]).read_bytes())["records"]


def _record(stage: str, records: list[dict], values: dict[str, str]) -> dict:
    proc = _run(_append_command(RECORDING_STAGES.get(stage, REPORT_FILE), stage), values, json.dumps(records))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _gate(values: dict[str, str]) -> subprocess.CompletedProcess:
    return _run(GATE_CMD, values)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


def test_step_file_exists() -> None:
    assert STEP_FILE.exists(), "step-hard-gate.md must exist"


class TestPipelineChain:
    def test_external_validators_points_to_step_hard_gate(self) -> None:
        assert _frontmatter(EXT_VALIDATORS_FILE)["nextStepFile"] == "step-hard-gate.md"

    def test_step_hard_gate_points_to_score(self) -> None:
        assert _frontmatter(STEP_FILE)["nextStepFile"] == "score.md"

    def test_a_blocked_run_goes_to_the_report_step(self) -> None:
        assert _frontmatter(STEP_FILE)["blockedStepFile"] == "report.md"

    @pytest.mark.parametrize("name", ["score.md", "report.md"])
    def test_chain_targets_exist(self, name: str) -> None:
        assert (REFS / name).is_file()


@pytest.mark.parametrize(
    "path",
    [COVERAGE_FILE, COHERENCE_FILE, EXT_VALIDATORS_FILE, STEP_FILE, SCORE_FILE, REPORT_FILE],
    ids=lambda p: p.stem,
)
def test_every_ledger_reader_binds_the_same_ledger(path: pathlib.Path) -> None:
    fm = _frontmatter(path)
    assert fm["ledgerFile"] == LEDGER_BINDING
    assert fm["outputFile"] == "{report_file}"
    if path in (STEP_FILE, REPORT_FILE):
        assert fm["publishedReportFile"] == PUBLISHED
    script = fm.get("hardGateScript") if path == STEP_FILE else fm.get("gapLedgerScript")
    assert script == ("scripts/hard-gate.py" if path == STEP_FILE else "scripts/gap-ledger.py")
    assert (TS_DIR / script).is_file()


class TestStepFileStructure:
    @pytest.fixture
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_has_step_goal_section(self, text: str) -> None:
        assert re.search(r"^##\s+STEP GOAL", text, re.MULTILINE)

    def test_step_title_format(self, text: str) -> None:
        assert re.search(r"^# Step 4c: Hard Gate$", text, re.MULTILINE)

    def test_communication_language_config(self, text: str) -> None:
        assert "{communication_language}" in text

    @pytest.mark.parametrize("section", ["### §1. Run the Gate", "### §2. Evaluate Gate",
                                         "### §3. Block: Critical or High Gaps",
                                         "### §4. Pass: No Critical or High Gaps"],
                             ids=["run", "evaluate", "block", "pass"])
    def test_numbered_sections_present(self, text: str, section: str) -> None:
        assert section in text

    def test_every_halt_releases_the_run_lock(self, text: str) -> None:
        body = _body(STEP_FILE)
        assert HALT_RELEASE in body
        assert body.index(HALT_RELEASE) < body.index("HALT (")


# ---------------------------------------------------------------------------
# The gate reads the ledger (#583 item 3, #541)
# ---------------------------------------------------------------------------


class TestGateReadsTheLedger:
    @pytest.fixture
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_the_gate_command_is_fenced(self, text: str) -> None:
        assert GATE_CMD in _fence(text, GATE_CMD)

    def test_the_gate_requires_every_stage_that_records_before_it(self) -> None:
        required = set(re.findall(r"--require-stage (\S+)", GATE_CMD))
        assert required == set(RECORDING_STAGES)
        for stage, path in RECORDING_STAGES.items():
            assert _append_command(path, stage), stage

    def test_the_gate_no_longer_scans_the_report(self, text: str) -> None:
        for stale in ("**Severity:**", "scan the **Coverage Analysis**", "### GAP-{NNN}"):
            assert stale not in text, stale

    def test_the_gate_refuses_an_unrecorded_stage(self, text: str) -> None:
        section = _flow(_slice(text, "### §2. Evaluate Gate", "### §3."))
        for code in ("`LEDGER_MISSING`", "`STAGE_NOT_RECORDED`", "`missing_stages`"):
            assert code in section, code
            assert code.strip("`") in _read(HARD_GATE) + _read(GAP_LEDGER), code
        assert 'HALT (`halt_reason: "step-completeness-violation"`, phase `hard-gate:check`)' in section
        assert "SKF_TEST_RESULT_JSON" not in section, "the emitter prints the line"
        assert "`gate` is `blocked`" in section and "`gate` is `passed`" in section

    def test_the_gate_is_severity_based(self, text: str) -> None:
        assert gap_ledger.BLOCKING == frozenset({"Critical", "High"})
        goal = _flow(_slice(text, "## STEP GOAL:", "### §1."))
        assert "Any Critical or High gap blocks the run" in goal


class TestRunningTheGate:
    """The documented commands, run against the real scripts."""

    def test_critical_coverage_and_high_coherence_gaps_block(self, values: dict[str, str]) -> None:
        coverage = _record("coverage-check", [
            _gap("Critical", "signature-mismatch", "formatDate signature differs from the source", "src/utils.ts:42"),
            _gap("Medium", "missing-export", "parseConfig is not documented", "src/config.ts", export="parseConfig"),
        ], values)
        coherence = _record("coherence-check", [
            _gap("High", "structural", "naive-coherence: unbalanced code fence (unclosed block)", "SKILL.md"),
        ], values)
        _record("external-validators", [], values)
        assert coverage["appended"] == ["GAP-001", "GAP-002"] and coherence["appended"] == ["GAP-003"]
        proc = _gate(values)
        assert proc.returncode == 0, proc.stdout
        out = json.loads(proc.stdout)
        assert out["gate"] == "blocked"
        assert [(g["id"], g["severity"]) for g in out["blocking"]] == [("GAP-001", "Critical"), ("GAP-003", "High")]
        assert out["non_blocking_count"] == 1
        # The gate names the report the blocked run publishes (the public name, #587).
        assert out["envelope"] == hard_gate.blocked_envelope("demo", values["{publishedReportFile}"])

    def test_a_run_whose_only_gaps_are_missing_exports_passes(self, values: dict[str, str]) -> None:
        _record("coverage-check", [
            _gap("Medium", "missing-export", f"{name} is not documented", "src/index.ts", export=name)
            for name in ("alpha", "beta", "gamma")
        ], values)
        _record("coherence-check", [], values)
        _record("external-validators", [_gap("Low", "external-validator", "skill-check: body-length")], values)
        out = json.loads(_gate(values).stdout)
        assert (out["gate"], out["blocking_count"], out["non_blocking_count"]) == ("passed", 0, 4)
        assert out["envelope"] is None

    def test_a_stage_that_recorded_nothing_is_refused(self, values: dict[str, str]) -> None:
        _record("coverage-check", [], values)
        _record("coherence-check", [], values)
        proc = _gate(values)
        assert proc.returncode == 1
        out = json.loads(proc.stdout)
        assert (out["code"], out["missing_stages"]) == ("STAGE_NOT_RECORDED", ["external-validators"])

    def test_no_ledger_is_refused(self, values: dict[str, str]) -> None:
        proc = _gate(values)
        assert proc.returncode == 1 and json.loads(proc.stdout)["code"] == "LEDGER_MISSING"

    def test_two_missing_names_from_one_file_are_two_records(self, values: dict[str, str],
                                                             tmp_path: pathlib.Path) -> None:
        """§5b's coverage call titles a missing name after it and sets `export`, so two names of one file
        never merge."""
        run = tmp_path / "run"
        _write_json(run / "coverage.json", {"branch": "enumerated", "missing": ["alpha", "beta"], "stale": []})
        _write_json(run / "surface.json", {"inputs": {}, "guards": None, "exports": [
            {"name": name, "kind": "function", "file": "src/index.ts", "line": None} for name in ("alpha", "beta")]})
        _write_json(run / "inventory.json", {"exports": []})
        call = _ledger_call(COVERAGE_FILE, "--from coverage", keep=("--surface",))
        # #1006: §1a always writes the inventory, so the call reads it unbracketed (a stale name's place)
        assert ' --inventory "{run_dir}/inventory.json" ' in call
        proc = _run(call, values | {"{run_dir}": run.as_posix(), "{resolved_skill_package}": tmp_path.as_posix()})
        out = json.loads(proc.stdout)
        assert (out["appended"], out["duplicates"], out["record_count"]) == (["GAP-001", "GAP-002"], [], 2)
        assert [(r["title"], r["source"], r["export"]) for r in _ledger_records(values)] == [
            ("Missing export: alpha", "src/index.ts", "alpha"), ("Missing export: beta", "src/index.ts", "beta")]

    def test_a_rerun_of_a_stage_records_its_gaps_once(self, values: dict[str, str]) -> None:
        records = [_gap("High", "split-body-mismatch", "formatDate differs in references/api.md",
                        "references/api.md:18")]
        first = _record("coverage-check", records, values)
        again = _record("coverage-check", records, values)
        assert (first["appended"], again["appended"], again["duplicates"]) == (["GAP-001"], [], ["GAP-001"])

    @pytest.mark.parametrize("severity, title", [
        ("Info", "Discovery testing not performed: --no-discovery flag set"),
        ("High", "discovery: 2/3 realistic prompts misrouted; description triggers are not pulling the skill"),
    ], ids=["skipped", "fail"])
    def test_discovery_after_the_gate_counts_but_does_not_block(self, values: dict[str, str], severity: str,
                                                                title: str) -> None:
        for stage in RECORDING_STAGES:
            _record(stage, [], values)
        assert json.loads(_gate(values).stdout)["gate"] == "passed"
        _record("report", [_gap(severity, "discovery", title, "SKILL.md frontmatter description")], values)
        report = _read(REPORT_FILE)
        summary_cmd = 'uv run {gapLedgerScript} summary --ledger "{ledgerFile}"'
        render_cmd = 'uv run {gapLedgerScript} render --ledger "{ledgerFile}" --heading'
        assert summary_cmd in report and render_cmd in report
        counts = json.loads(_run(summary_cmd, values).stdout)
        assert (counts["total"], counts["counts"][severity], counts["stages"][-1]) == (1, 1, "report")
        # A PASS run's report never claims a blocking gap the gate did not see.
        assert (counts["blocking"], counts["non_blocking"]) == (0, 1)
        rendered = _run(render_cmd, values).stdout
        assert "**Blocking (Critical + High):** 0" in rendered
        after_gate = "**Found after the hard gate (Critical + High, non-blocking):** 1"
        assert (after_gate in rendered) == (severity == "High")
        assert f"**Non-blocking (Medium + Low + Info):** {1 if severity == 'Info' else 0}" in rendered


# ---------------------------------------------------------------------------
# A blocked run ends through the report step (#583 item 2, architecture-2)
# ---------------------------------------------------------------------------


class TestBlockPath:
    @pytest.fixture
    def block(self) -> str:
        return _slice(_read(STEP_FILE), "### §3. Block", "### §4. Pass")

    def test_sets_the_verdict_in_the_frontmatter(self, block: str) -> None:
        # #823: a blocked run records its source access, as score.md §7 does for a scored one
        for field in ("`hardGate: 'blocked'`", "`testResult: 'fail'`", "`nextWorkflow: 'update-skill'`",
                      "`analysisConfidence: '{analysis_confidence}'`", "Append `'hard-gate'` to `stepsCompleted`"):
            assert field in block, field

    def test_writes_the_completeness_score_in_scorings_place(self, block: str) -> None:
        section = _fence(block, "not scored")
        assert section.startswith("## Completeness Score\n")
        assert "not scored" in section and "{blocking_count}" in section
        assert "in place of the template's `## Completeness Score` heading" in _flow(block)

    def test_goes_to_the_report_step_without_scoring(self, block: str) -> None:
        flow = _flow(block)
        assert "load and execute `{blockedStepFile}`" in flow
        assert "Do not chain to `{nextStepFile}`" in flow
        assert "HALT" not in block, "a blocked run is not a halt: it ends through the report step"
        assert "release" not in block.lower(), "report.md §7 releases the lock of a blocked run"

    def test_a_blocked_run_is_published_by_the_report_step(self, block: str) -> None:
        """#587: a blocked run keeps its in-progress name until report.md §4c's checks pass, so a
        halt in the report step leaves no partial report under the public name."""
        move = 'mv "{report_file}" "{publishedReportFile}"'
        assert "mv " not in block and "{publishedReportFile}" not in block
        assert "keeps its in-progress name until report.md §4c's checks pass" in _flow(block)
        # The gate still names the public path in the blocked payload.
        assert _frontmatter(STEP_FILE)["publishedReportFile"] == PUBLISHED
        assert '--report-path "{publishedReportFile}"' in GATE_CMD
        contract = _slice(_read(REPORT_FILE), "### 4c. Result Contract", "### 5.")
        publish = _flow(contract[contract.index("**Publish the report.**"):contract.index("**Write the result contract.**")])
        assert move in _fence(contract, move) and "a blocked run's included" in publish
        assert "skip the move" not in publish and "took it at the gate" not in contract

    def test_names_update_skill_from_test_report(self, block: str) -> None:
        assert "`@Ferris US {skill_name} --from-test-report`" in block

    def test_report_step_publishes_a_blocked_run(self) -> None:
        text = _read(REPORT_FILE)
        collect = _flow(_slice(text, "### 1. Collect All Issues", "### 2."))
        assert "`hardGate: 'blocked'`" in collect and "skips discovery testing (§4b)" in collect
        contract = _flow(_slice(text, "### 4c. Result Contract", "### 5."))
        assert "A run the hard gate blocked was never scored: its expected set ends at `'hard-gate'`" in contract
        assert "the line that discovery testing did not run" in contract
        for field in ('`status: "error"`', '`verdict: "FAIL"`', "`exit_code` 2",
                      '`halt_reason: "hard-gate-blocked"`'):
            assert field in contract, field
        assert "so after a blocked run `skf-test-skill-result-latest.json` holds its FAIL, never an earlier run's verdict" in contract
        # build-result-context.py's table is the one home of the exit codes: the report step restates none.
        assert _load("skf_build_result_context_gate", BUILD_CONTEXT).VERDICTS["fail"][2] == 2
        assert "{headless_exit_code}" not in text and "The Exit Code" not in text
        assert "→ exit code" not in text

    def test_the_blocked_envelope_is_the_gates(self, tmp_path: pathlib.Path) -> None:
        """The report step's payload for a blocked run is the hard gate's own, built by the script."""
        assert "SKF_TEST_RESULT_JSON: {" not in _read(REPORT_FILE), "no envelope literal is typed"
        report = tmp_path / f"test-report-demo-{RUN_ID}.md"
        report.write_bytes(f"---\nskillName: 'demo'\nrunId: '{RUN_ID}'\nhardGate: 'blocked'\n"
                           "testResult: 'fail'\nanalysisConfidence: 'full'\ntestMode: 'naive'\n---\n# R\n"
                           .encode("utf-8"))
        ledger = tmp_path / f"test-findings-{RUN_ID}.json"
        record = _gap("Critical", "broken-reference", "Broken reference: x")
        subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                        "coherence-check"], input=json.dumps([record]), capture_output=True, text=True,
                       encoding="utf-8", check=True)
        out = tmp_path / "result-context.json"
        proc = subprocess.run([sys.executable, str(BUILD_CONTEXT), "--report", report.as_posix(), "--ledger",
                               ledger.as_posix(), "--output", out.as_posix()],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["target"] == "stderr"
        payload = json.loads(out.read_text(encoding="utf-8"))
        contract = payload.pop("result_contract")
        assert payload == hard_gate.blocked_envelope("demo", report.as_posix())
        assert contract["summary"]["result"] == "FAIL" and contract["summary"]["gapCounts"]["Critical"] == 1

    def test_the_health_check_runs_for_a_blocked_run(self) -> None:
        """§7 dispatches it (or skips it under --no-health-check) and records healthCheckDispatched."""
        text = _read(REPORT_FILE)
        sequence = _flow(_slice(text, "### 4. The Terminal Sequence", "### 4b."))
        assert "a blocked one included" in sequence
        assert "§7 releases the run lock and hands over to the health check" in sequence
        section7 = _flow(_slice(text, "### 7. Health-Check Dispatch", "load and execute `{nextStepFile}`"))
        for needle in ("`--no-health-check` flag bypass", "`healthCheckDispatched: false`",
                       "`health_check_dispatched: false` in the report"):
            assert needle in section7, needle


class TestPassPath:
    @pytest.fixture
    def section(self) -> str:
        return _flow(_read(STEP_FILE)[_read(STEP_FILE).index("### §4. Pass"):])

    def test_records_the_gate_and_chains_to_scoring(self, section: str) -> None:
        assert "`hardGate: 'passed'`" in section
        assert "Append `'hard-gate'` to `stepsCompleted`" in section
        assert "load and execute `{nextStepFile}`" in section

    def test_reports_the_non_blocking_count(self, section: str) -> None:
        assert "`non_blocking_count`" in section


# ---------------------------------------------------------------------------
# The Gap Severity table (#583, #545, #543)
# ---------------------------------------------------------------------------


class TestGapSeverityTable:
    def test_every_category_is_one_the_ledger_knows(self) -> None:
        for severity, category, _ in _severity_rows():
            assert category in gap_ledger.CATEGORIES, (severity, category)

    @pytest.mark.parametrize("severity, category", [
        ("Medium", "missing-export"),
        ("Critical", "signature-mismatch"),
        ("Critical", "fabricated-signature"),
        ("Critical", "broken-reference"),
        ("High", "inaccurate-reference"),
        ("Medium", "integration-pattern"),
        ("High", "discovery"),
        ("Medium", "discovery"),
        ("Info", "discovery"),
    ], ids=lambda v: v if isinstance(v, str) else None)
    def test_the_re_rated_rows(self, severity: str, category: str) -> None:
        assert (severity, category) in {(s, c) for s, c, _ in _severity_rows()}

    def test_a_missing_export_no_longer_blocks(self) -> None:
        rows = _severity_rows()
        assert [s for s, c, _ in rows if c == "missing-export"] == ["Medium"]
        assert not any(s in ("Critical", "High") and "Missing exported" in text for s, _, text in rows)

    def test_a_missing_script_or_asset_is_a_broken_reference(self) -> None:
        broken = next(text for s, c, text in _severity_rows() if c == "broken-reference")
        assert "`scripts/` or `assets/` file" in broken
        assert "references file not found in scripts/ or assets/" not in _read(SCORING_FILE)

    def test_the_table_says_what_blocks(self) -> None:
        intro = _flow(_slice(_read(SCORING_FILE), "## Gap Severity", "| Severity |"))
        assert "blocks a run on any Critical or High gap, before scoring" in intro
        assert "a discovery gap of any severity is counted in the Gap Report and blocks nothing" in intro
        # Many non-blocking gaps lower no score: the threshold decides the verdict.
        assert "A Medium, Low or Info gap never blocks. Scores come from the category metrics" in intro
        assert "it lowers the category score it belongs to" not in intro

    def test_an_unexemplified_function_is_a_medium_structural_gap(self) -> None:
        structural = {s: text for s, c, text in _severity_rows() if c == "structural"}
        assert "§2.4" not in structural["High"] and "§2.4" in structural["Medium"]

    def test_fabricated_and_stale_rows_follow_the_line_check(self) -> None:
        rows = {c: text for _, c, text in _severity_rows()}
        assert "the cited file is missing or defines no such name" in rows["fabricated-signature"]
        assert "not a fabricated signature" in rows["stale-documentation"]
        assert "with no source line cited for it" not in rows["stale-documentation"]

    def test_the_deflation_criterion_is_the_protocols(self) -> None:
        # The row states the percentage, the loader computes the guard with it,
        # and the protocol cites the guard's threshold field instead of a copy.
        criterion = "the re-derived source barrel exceeds `effective_denominator` by"
        drift = next(text for s, c, text in _severity_rows() if c == "metadata-drift")
        # #695, #712: a tier A glob that matches no file, or only files that define no public name, narrows
        # nothing, so the guard counts only the ones that count a name
        assert (f"{criterion} more than 25% and the brief has no `scope.tier_a_include` glob that counts a public "
                "name" in drift)
        rows = {c: text for _, c, text in _severity_rows()}
        assert ("the brief has no `scope.tier_a_include` glob that counts a public name"
                in rows["denominator-inflation"])
        assert ("or a `scope.tier_a_include` glob matches no file in the source tested, so it counts no name"
                in rows["brief-scope-stale"])
        loader = _load("skf_load_coverage_inputs_for_step_test", TS_DIR / "scripts" / "load-coverage-inputs.py")
        assert loader.DEFLATION_PCT == 25
        protocol = _read(REFS / "source-access-protocol.md")
        # v4.0.0 quality gate run 1 review: the loader applies the guard and the row states its criterion, so the
        # protocol names the guard and what the model does with it, never the criterion again
        assert "unless `guards.deflation.fires` (a Medium `metadata-drift` gap" in protocol
        assert criterion not in protocol and "more than 25%" not in protocol

    @pytest.mark.parametrize("path", [COVERAGE_FILE, COVERAGE_BRANCHES_FILE, COHERENCE_FILE, EXT_VALIDATORS_FILE,
                                      REPORT_FILE], ids=lambda p: p.stem)
    def test_every_severity_the_prose_writes_is_a_row(self, path: pathlib.Path) -> None:
        pairs = set(SEVERITY_CATEGORY_RE.findall(_flow(_body(path))))
        assert pairs, f"{path.name} names no severity and category"
        rows = {(s, c) for s, c, _ in _severity_rows()}
        assert pairs <= rows, sorted(pairs - rows)

    def test_every_blocking_row_has_a_writer_before_the_gate(self) -> None:
        written = set()
        for path in (COVERAGE_FILE, COHERENCE_FILE, EXT_VALIDATORS_FILE):
            written |= set(SEVERITY_CATEGORY_RE.findall(_flow(_body(path))))
        blocking = {(s, c) for s, c, _ in _severity_rows() if s in gap_ledger.BLOCKING and c != "discovery"}
        assert blocking <= written, sorted(blocking - written)


# ---------------------------------------------------------------------------
# The stages record their gaps (#541)
# ---------------------------------------------------------------------------


class TestStagesRecordTheirGaps:
    @pytest.mark.parametrize("stage", sorted(RECORDING_STAGES))
    def test_each_stage_appends_even_when_it_found_nothing(self, stage: str) -> None:
        text = _flow(_body(RECORDING_STAGES[stage]))
        assert "Run the command even when the array is empty (`[]`)" in text
        assert "the quoted marker hands them to the script unchanged" in text
        for outcome in ("Exit 0:", "Exit 2 (`INVALID_RECORD` or `INVALID_INPUT`)", "Exit 1: HALT"):
            assert outcome in text, outcome

    def test_coverage_records_what_541_names(self) -> None:
        # §4b's count findings are recorded from the branch section §4b loads
        text = _flow(_body(COVERAGE_FILE)) + " " + _flow(_read(COVERAGE_BRANCHES_FILE))
        for needle in ("High `split-body-mismatch` gap", "High `numerator-inflation` gap",
                       "Medium `metadata-drift` gap", "Info `multi-denominator` gap",
                       "Low `provenance-line` gap", "Info `provenance-unverified` gap"):
            assert needle in text, needle
        for stale in ("gap list (built in section 5)", "feed into the gap report (step 6)"):
            assert stale not in text, stale

    def test_the_provenance_line_gap_keeps_the_title_and_source_update_skill_reads(
            self, values: dict[str, str], tmp_path: pathlib.Path) -> None:
        """update-skill's rule R5 reads the provenance line gap by its title and its bare `file:line` Source."""
        run = tmp_path / "run"
        _write_json(run / "provenance-verify.json", {"stale": [
            {"export_name": "search", "source_file": "src/api.py", "source_line": 25, "reason": "line-not-definition",
             "definition_lines": [26]},
            {"export_name": "fetch", "source_file": "src/api.py", "source_line": 40, "reason": "line-not-definition",
             "definition_lines": []},
            {"export_name": "gone", "source_file": "src/old.py", "source_line": 3, "reason": "file-missing"}]})
        section = _slice(_read(COVERAGE_FILE), "### 4c. Provenance Line Check", "### 5. Write")
        assert '-o "{run_dir}/provenance-verify.json"' in section
        proc = _run(_ledger_call(COVERAGE_FILE, "--from provenance-line"), values | {"{run_dir}": run.as_posix()})
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert [(r["severity"], r["category"], r["title"], r["source"], r["export"])
                for r in _ledger_records(values)] == [
            ("Low", "provenance-line", "Provenance line is not the definition of search", "src/api.py:25", "search"),
            ("Info", "provenance-unverified", "Provenance line not verified for fetch", "src/api.py:40", "fetch"),
            # #832: a citation whose file the pinned source lacks reaches R5 at the map's file:line too
            ("Low", "provenance-line", "Provenance file is missing for gone", "src/old.py:3", "gone")]

    def test_the_provenance_line_gap_of_an_aliased_name_names_the_alias(
            self, values: dict[str, str], tmp_path: pathlib.Path) -> None:
        """#911: §5b's provenance-line call passes classify-stale's result, so the unverified line of a name a
        rename declares names the alias and asks to record the rename, at the same title and Source."""
        run = tmp_path / "run"
        _write_json(run / "provenance-verify.json", {"stale": [
            {"export_name": "Entry", "source_file": "pkg/api.ts", "source_line": 1, "reason": "line-not-definition",
             "definition_lines": []},
            {"export_name": "fetch", "source_file": "src/api.py", "source_line": 40, "reason": "line-not-definition",
             "definition_lines": []}]})
        _write_json(run / "stale.json", [
            {"name": "Entry", "fabricated": False, "source": "pkg/api.ts:1", "defined_at": "pkg/root.ts:2",
             "declared_in": ["pkg/root.ts:2"], "reason": "aliased", "entries": [], "renames": "API_Entry"}])
        call = _ledger_call(COVERAGE_FILE, "--from provenance-line", keep=("--stale",))
        assert '--stale "{run_dir}/stale.json"' in call
        proc = _run(call, values | {"{run_dir}": run.as_posix()})
        assert proc.returncode == 0, proc.stdout + proc.stderr
        entry, fetch = _ledger_records(values)
        assert (entry["severity"], entry["category"], entry["title"], entry["source"], entry["export"]) == (
            "Info", "provenance-unverified", "Provenance line not verified for Entry", "pkg/api.ts:1", "Entry")
        assert entry["remediation"].startswith(
            "`Entry` is an alias of `API_Entry`, which a cited file declares; the source declares the alias at "
            "`pkg/root.ts:2`")
        for needle in ("If no other entry already has `export_name` `API_Entry`, record the rename",
                       "set `export_name` to `API_Entry`", "add `reexported_as` `Entry`"):
            assert needle in entry["remediation"], needle
        assert fetch["remediation"].startswith("Open `src/api.py` and confirm that line 40 defines `fetch`;")

    def test_a_split_body_gap_cites_the_side_the_source_contradicts(self) -> None:
        """#778: §1b no longer makes the body authoritative; §5b, where the pinned source can settle it, cites the
        file the export's one declaration contradicts, inside the package in every case, and falls back to the
        reference line when it cannot or neither side agrees. Each record names its reference file in its title, so
        two references that disagree with one body are two gaps, and its remediation names both files. #841: the
        cross-check also compares two references the body does not settle (it does not document the export, or
        agrees with both), and §5b loads the Source rule from the branch file's Split-Body Sources section.
        #1035 (oms-cognee 1.6.2): `surface.json` records no class member, so every pair of a `method`'s forms
        (`datasets.list_data`, `agents.delete`) fell to "no source settled it" and had update-skill copy SKILL.md's
        form, missing a required parameter, over a reference line the source agrees with; and a root record of the
        bare name (`cognee.delete` for `agents.delete`) could settle a pair against the wrong declaration. A method
        pair gives its `owner`, and the Source reads the member the owner's body declares, or the function a namespace
        object binds it to (`session.add_feedback`, a `types.SimpleNamespace` keyword), never a bare-name record; two
        owners' methods of one name are never a pair.
        #1026: a surface the fallback per-file scan builds never looks for other declarations, yet wrote
        `otherDeclarations` as [], so one recorded declaration settled a pair a full extraction leaves unsettled. It
        now writes null, and the one declaration decides only on a list.
        #1027: a pair nothing decides because the name has two declarations had update-skill copy one side's form
        over the other, though each can be right for its own declaration (core's and the React renderer's
        `composeStory`, #927). When each form agrees with a different declaration, the remediation names no form to
        take and asks for each declaration's citation beside its form, which the next run's reader and §2's `bound`
        read; §1b and the record format no longer say update-skill always copies the other side.
        #1062: a pair of such a name where one form agrees with one or more of its declarations and the other with
        none still fell to the default and had update-skill copy the other side's form, so a reference form the
        source agrees with was overwritten. The source now settles that pair: its Source and Contradicted Side are
        the side that agrees with none, and its remediation edits that side, taking the agreeing form and citing
        each declaration it agrees with; with an `otherDeclarations` of `null`, which no extraction completed, the
        side that agrees with none may document a declaration nobody looked for, so the pair stays unsettled. And a
        member the owner neither declares nor binds is read from its nearest base in the source tree, in method
        resolution order, so a method only a base class declares settles its pair, unless a method of that name is
        declared for the owner outside its body (a Go receiver method, a function assigned to its `prototype`): §2
        compares that one, so no base's member stands in for it and nothing decides. An owner with no record, or a
        member only another package declares, still decides nothing.
        #1088 review: the nearest base in the source tree is not the member Python runs when another package's class
        comes first in method resolution order (`class Session(requests.Session, RetryMixin)`), and in Java, Kotlin,
        C# and Swift a subclass keeps its bases' overloads, so `Client`'s one `send(String s, int retries)` beside
        `Base`'s `send(String s)` settled a pair against SKILL.md's correct `client.send(msg)`. The walk takes the
        first class in method resolution order to declare or bind the member, nothing decides when that class is
        another package's, and a base's overloads in those languages make an overload set, which decides nothing."""
        text = _read(COVERAGE_FILE)
        section1 = _flow(_slice(text, "### 1. Extract Documented Exports", "#### 1a."))
        assert ("For each export two or more of the files it reads document, it compares the SKILL.md body with "
                "each reference file, and two reference files with each other only when the body does not settle "
                "them (it does not document the export, or agrees with both), by the rules of `{signatureRulesFile}`"
                ) in section1
        assert "it compares the two by the rules" not in section1 and "every pair" not in section1
        # the pair's other side, as the contract §1's reader is given writes it
        contract = _flow(_read(REFS / "inventory-contract.md"))
        assert ("A `cross_check_mismatches` entry gives its `export`, `reference_file`, `reference_line` and an "
                "`issue` that names each form by its file's path, and the pair's other side: the SKILL.md body's line "
                "as `skill_md_line`, or, for two references, the one that sorts first in codepoint order, by path and "
                "then line, as `other_file` and `other_line`, with the one that sorts last as `reference_file` and "
                "`reference_line`.") in contract
        assert '"other_file": "references/api-reference.md", "other_line": 40' in contract
        # #1035: a method pair also gives its entries' `owner`, which the Source reads, and the example shows one
        assert ("Each file is its path in the package, such as `references/api-reference.md`. A pair of a "
                "`method`'s forms also gives the `owner` its entries give (`agents` above), so the split-body Source "
                "reads that owner's member, never a same-named declaration elsewhere; `owner` is not validated."
                ) in contract
        # one pair gives one owner, so methods of one name on two owners are never a pair
        assert ("`owner` is not validated. Methods of one name whose entries give different owners (`agents.get`, "
                "`datasets.get`) are two methods, and their forms are never a pair.") in contract
        example = json.loads(re.search(r"```json\n(.*?)\n```", _read(REFS / "inventory-contract.md"),
                                       re.S).group(1))["cross_check_mismatches"]
        assert [(e["export"], e["owner"]) for e in example if "owner" in e] == [("get", "agents")]
        section = _flow(_slice(text, "### 1b. Cross-Check", "### 2. Analyze"))
        assert "The SKILL.md body is authoritative" not in section
        assert "High `split-body-mismatch` gap" in section
        assert ("§5b records it titled `Split-body mismatch: {export} ({reference_file})`, with its `export` and its "
                "Source at the side the source contradicts (`{reference_file}` when no source settles it): "
                "update-skill makes the edits its remediation names, reading no source") in section
        # #1027: a remediation may ask for citations instead of a copy, so §1b no longer says it always copies
        assert "to match the other without reading the source" not in section
        assert ("An entry for two references the body does not settle is titled `Split-body mismatch: {export} "
                "({other_file}, {reference_file})`.") in section
        # §5b keeps the sentence that loads the Source rule; the rule itself is a branch section
        side = _flow(_slice(text, "**A split-body mismatch's Source**", "Then write the records no script wrote"))
        assert side == ("**A split-body mismatch's Source** is a line inside the skill package: when §1b found one, "
                        "load `{coverageBranchesFile}` and follow its **Split-Body Sources** section. ")
        assert text.index("**A split-body mismatch's Source**") > text.index("### 5b. Record the Coverage Gaps")
        rule = _flow(_read(COVERAGE_BRANCHES_FILE).split("\n## Split-Body Sources\n", 1)[1])
        assert rule.lstrip().startswith("The Source is `{reference_file}:{reference_line}`, of two references the one that "
                               "sorts last, unless the pinned source settles it for the other side.")
        for needle in (# only where the pinned source can settle it: no State 2 map strings, no Quick tier, no drift
                       "At State 1 and the Forge tier or above, with `workspaceDrift` not `overridden`",
                       "set the two forms its `issue` gives against the export's declaration at the `file` and "
                       "`line` `surface.json` gives",
                       # #1026: a null list, which no runner extraction looked for, decides nothing
                       "when that one declaration decides (no overload set, no second declaring file, and an "
                       "`otherDeclarations` list, not `null`, with no entry of the export's name; `null` means no "
                       "runner extraction looked for one, as after the fallback per-file scan)",
                       # the other side when only the reference agrees, else the default, the reference that sorts last
                       "when `{reference_file}`'s form agrees and the other side's does not, the Source is the other "
                       "side, `SKILL.md:{skill_md_line}` or `{other_file}:{other_line}`.",
                       "Its remediation names the file to edit and the file and line whose form it takes, citing "
                       "the declaration's `file:line`",
                       "when both forms agree with it, it says so and names what differs",
                       "when neither does, or nothing decides, it says no source settled it and names "
                       "`{reference_file}` to edit, taking the other side's form (`{other_file}`'s, for two "
                       "references)"):
            assert needle in rule, needle
        # #1026: the surface paragraph says what a surface no runner extraction built writes for that list
        assert ("It is `null`, not `[]`, when no runner extraction looked for them: a surface with no extraction, or "
                "one the fallback per-file scan builds, with or without the runner's JSON.") in _flow(
                    _read(REFS / "source-access-protocol.md"))
        # #1035: a method pair is settled by the member its owner's body declares, read from the owner's record, or,
        # for a namespace object such as cognee's `session`, by the function its keyword binds, by the same
        # one-declaration test, before the remediation that cites the declaration's `file:line`
        member = ("A pair that gives an `owner` is a `method`'s (inventory-contract.md): its declaration is the member "
                  "of the method's bare name that the owner's body declares, read from the `file` and `line` of the "
                  "owner's `surface.json` record, or, for an owner that binds the name to a function declared "
                  "elsewhere (a keyword of the `types.SimpleNamespace(...)` call that builds it, a class attribute "
                  "assigned a function), the declaration that binding names, read in the owner's file or through its "
                  "import, or, for an owner that neither declares nor binds it and has no method of that name declared "
                  "for it outside its body (a Go method of its receiver type, one in a Rust `impl` block or a Kotlin "
                  "or Swift extension, a function assigned to its `prototype`), the member the first class in its "
                  "method resolution order to declare or bind it gives, each base read in its subclass's file or "
                  "through that file's import, and it decides when the owner's name has one declaration by the test "
                  "above and the owner, or else that class, declares or binds the member once, with no overload set, "
                  "the overloads of that name the owner and its bases declare counting as one set in Java, Kotlin, "
                  "C# and Swift.")
        # a bare-name record never stands in, nor a base's member for a method declared for the owner outside its
        # body, which §2 compares instead; and a pair the rule cannot place under its owner is settled by nothing:
        # no record of the owner, such a method, a member neither it nor a base in the source tree declares (#1062:
        # one only another package's class declares), or one another package's class gives first
        bare = ("A record of the bare name never stands in for the member, nor a base's member for a method declared "
                "for the owner outside its body, so with no record of the owner, with such a method, with no such "
                "member in the owner or a base in the source tree, with the first class to declare or bind it outside "
                "that tree, or with no `owner` on a pair whose `export` the inventory lists only as a `method`, "
                "nothing decides.")
        for sentence in (member, bare):
            assert rule.count(sentence) == 1, sentence
        # #1062: the owner-only wording is gone, since a base's member decides when the owner's does not
        assert "the owner declares or binds the member once" not in rule
        assert "so with no record of the owner or no such member, or" not in rule
        # #1088 review: the walk follows method resolution order to the first class that declares the member, never
        # past another package's class to an in-tree base, and in Java, Kotlin, C# and Swift a base's overloads make
        # the owner's member an overload set, so neither settles a pair by a member the source does not run or by one
        # overload alone; §2's rules read the same member
        assert "the member its nearest base in the source tree declares or binds" not in rule
        rules = _flow(_read(REFS / "signature-comparison-rules.md"))
        assert "the member the first class in its method resolution order to declare or bind it gives" in rules
        assert "the overloads of that name the owner and its bases declare are one set" in rules
        # the base walk stops at the methods §2 reads for the owner outside its body, listed as §2's rule lists them,
        # so the split-body Source and §2's judge read the same member
        out_of_body = ("(a Go method of its receiver type, one in a Rust `impl` block or a Kotlin or Swift extension, "
                       "a function assigned to its `prototype`)")
        assert out_of_body in member
        assert out_of_body in _flow(_read(REFS / "signature-comparison-rules.md"))
        assert (rule.index("the Source is the other side, `SKILL.md:{skill_md_line}`") < rule.index(member)
                < rule.index(bare) < rule.index("Its remediation names the file to edit")), "before the remediation"
        # #1027: a pair nothing decides because the name has two declarations sets each form against each of them,
        # never for a method pair, whose declarations are members the bare name's records never stand in for. It
        # runs under the State, tier and drift gate alone, so after a fallback scan that records the name in two
        # files too, where each record has no line: the judge finds it by name in its file
        homonyms = ("Under the State, tier and `workspaceDrift` conditions above, when nothing decides because the "
                    "export's name has more than one declaration (a second declaring file, or an `otherDeclarations` "
                    "entry of its name), on a pair that gives no `owner` and whose `export` the inventory does not "
                    "list only as a `method`, set each form against each declaration of the name, its `surface.json` "
                    "records and its `otherDeclarations` entries, read at their `file` and `line`, or found by its "
                    "name in its `file` when its `line` is `null` (a per-file record): when each form agrees with a "
                    "different one, the remediation names no form to take.")
        # it asks for the citation each form's own citations are read from, and a module or owner the reader reads;
        # a declaration with no line is cited by its file, which names every declaration there (form_citations)
        cite = ("For each side it gives the form's file and line and the declaration that form agrees with, and asks "
                "update-skill to add that declaration's citation, `[SRC:{file}:L{line}]`, or `[SRC:{file}]` for one "
                "with no `line`, which names every declaration in its file, on the form's line or, in a fenced block, "
                "on a comment line just above it, and to name the declaration's module or owner beside the form, so a "
                "later run's reader and §2's `bound` keep the two apart.")
        # the Source and the table keep the unsettled side
        unsettled = ("Its Source stays `{reference_file}:{reference_line}` and its **Contradicted Side** "
                     "`not settled`.")
        # #1062: when, of a pair set against the name's declarations, one form agrees with one or more of them and
        # the other with none, the source settles it as one declaration does: the Source and the table name the side
        # that agrees with none, whichever it is, and the remediation edits that side, taking the agreeing form and
        # citing each declaration it agrees with, so a correct `{reference_file}` form is never overwritten. Only a
        # pair of the homonym branch, never a method's, and only over an `otherDeclarations` list: with `null`, no
        # extraction looked for the declaration the other form may document
        one_agrees = ("When a pair set against the name's declarations this way has one form that agrees with one "
                      "or more of them and the other form with none, and `otherDeclarations` is a list, not `null` "
                      "(with `null`, the form that agrees with none may agree with a declaration no extraction "
                      "looked for), the source settles the pair: its Source is the side whose form agrees with none, "
                      "`{reference_file}:{reference_line}` or the other side, `SKILL.md:{skill_md_line}` or "
                      "`{other_file}:{other_line}`, its **Contradicted Side** that side's path, and its remediation "
                      "names that file to edit and the file and line whose form it takes, citing each declaration "
                      "the agreeing form agrees with at the `file` and line it was read at.")
        # and only a pair none of those settles keeps the copy, which ends the rule
        others = "Every other pair keeps the remediation above."
        for sentence in (homonyms, cite, unsettled, one_agrees, others):
            assert rule.count(sentence) == 1, sentence
        assert (rule.index("taking the other side's form (`{other_file}`'s, for two references)") < rule.index(homonyms)
                < rule.index(cite) < rule.index(unsettled) < rule.index(one_agrees) < rule.index(others)
                ), "after the default remediation it narrows"
        assert rule.rstrip().endswith(others)
        assert "`not settled`; every other pair" not in rule
        assert "State 2" not in rule and "`signature_source`" not in rule
        formats = _flow(_read(FORMATS_FILE))
        assert ("Each row is a split-body gap coverage-check recorded. **Other Side** is the other file of its pair, "
                "at its line: `SKILL.md:{skill_md_line}`, or `{other_file}:{other_line}` for two references. Its "
                "Source is at **Other Side** when the pinned source contradicts that side and agrees with "
                "**Reference File**, else at `{Reference File}:{Reference Line}`.") in formats
        assert ("A split-body record, titled `Split-body mismatch: {export} ({reference_file})`, or "
                "`Split-body mismatch: {export} ({other_file}, {reference_file})` for two references, cites the side "
                "the pinned source contradicts: the other side, `SKILL.md:{skill_md_line}` or "
                "`{other_file}:{other_line}`, when `{reference_file}` agrees with the source declaration and the other "
                "side does not, else `{reference_file}:{reference_line}`, also when no source settled it. Its "
                "remediation names the file to edit and the file and line whose form it takes") in formats
        # #1027: or, for forms of two declarations, the citation to add beside each
        assert ("whose form it takes, or, when each form agrees with a different declaration of the name, the "
                "citation to add beside each, and update-skill changes only what it names as contradicting.") in formats
        # the table shows the pair's other side and which side the source contradicts
        assert ("| # | Reference File | Export | Issue | Other Side | Reference Line | Contradicted Side |"
                in formats)
        assert "SKILL.md Line" not in formats
        # a file's path in every case, never the word `reference`
        assert ("**Contradicted Side** is the path of the one file the source contradicts (`SKILL.md` or a "
                "`references/` file's path), `none` when both forms agree with it, or `not settled` when it "
                "contradicts both or no source settled it") in formats
        assert "`reference` for" not in formats

    def test_a_reference_pair_is_one_gap_per_pair_that_blocks_and_records_once(self, values: dict[str, str]
                                                                               ) -> None:
        """#841: a body that matches both references while they contradict each other leaves their pair to find it,
        a High `split-body-mismatch` the hard gate blocks on, beside another export's body pair. The pair's fixed
        order gives it one title, so a rerun of §5b records each gap once."""
        pair = _gap("High", "split-body-mismatch",
                    "Split-body mismatch: run_tasks_parallel (references/a.md, references/b.md)",
                    source="references/b.md:5", export="run_tasks_parallel")
        body = _gap("High", "split-body-mismatch", "Split-body mismatch: fetch (references/b.md)",
                    source="references/b.md:9", export="fetch")
        first = _record("coverage-check", [pair, body], values)
        again = _record("coverage-check", [pair, body], values)
        assert (first["appended"], again["appended"], again["duplicates"]) == (
            ["GAP-001", "GAP-002"], [], ["GAP-001", "GAP-002"])
        assert [r["title"] for r in _ledger_records(values)] == [pair["title"], body["title"]]
        _record("coherence-check", [], values)
        _record("external-validators", [], values)
        out = json.loads(_gate(values).stdout)
        assert out["gate"] == "blocked"
        assert [(g["id"], g["severity"]) for g in out["blocking"]] == [("GAP-001", "High"), ("GAP-002", "High")]

    def test_each_per_export_record_names_its_export(self) -> None:
        """The hand-written split-body record and the script's per-export records name the export in
        `export` and in the title."""
        text = _flow(_body(COVERAGE_FILE))
        assert "titled `Split-body mismatch: {export} ({reference_file})`, with its `export`" in text
        assert "titled `Signature mismatch: {name}`, with `export` `{name}`" in text
        assert "§1b's split-body mismatches, in the Ledger Record Format" in text
        assert "each naming its export in `export` and in its title" in text
        records = gap_ledger.from_coverage(
            {"branch": "enumerated", "missing": ["fetchData", "Options"], "stale": ["ghost", "old"]},
            signatures={"missingTypes": ["Options"]},
            stale=[{"name": "ghost", "fabricated": True, "source": "src/a.ts:3"}])
        records += gap_ledger.from_provenance_line({"stale": [
            {"export_name": n, "source_file": "a.py", "source_line": 1, "reason": "line-not-definition",
             "definition_lines": lines} for n, lines in (("f", [2]), ("g", []))] + [
            {"export_name": n, "source_file": "a.py", "source_line": line, "reason": reason}
            for n, line, reason in (("h", 1, "file-missing"), ("i", 99, "line-out-of-bounds"),
                                    ("j", "x", "line-invalid"))]})
        assert {r["export"] for r in records} >= {"f", "g", "h", "i", "j"}
        assert {r["category"] for r in records} == {"missing-export", "missing-type", "fabricated-signature",
                                                    "stale-documentation", "provenance-line",
                                                    "provenance-unverified"}
        for record in records:
            assert record["export"] and record["title"].endswith(record["export"]), record

    def test_inflated_names_become_missing_exports_update_skill_can_route(self, values: dict[str, str],
                                                                          tmp_path: pathlib.Path) -> None:
        text = _flow(_body(COVERAGE_FILE))
        scalar = _flow(_slice(_read(COVERAGE_BRANCHES_FILE), "## Scalar and Stack Branches", "## Denominator"))
        assert "its `absent[]` names replace this gap, one each" in scalar
        # §5b keeps `--provenance` whenever the map is bound, though no run file holds it: the absent names'
        # Source comes from it, and update-skill takes that line as its `source_citation`.
        assert ("leaving out a bracketed flag whose file does not exist: a run file this run did not write, "
                "or `--provenance` when init.md §2 bound no `{forge_provenance_map}`:") in text
        run = tmp_path / "run"
        _write_json(run / "coverage.json", {"branch": "scalar", "denominator": 4, "documented": 2,
                                            "missing": [], "missingCount": 2, "numeratorSource": "verified"})
        _write_json(run / "numerator.json", {"inflated": True, "declared": 4, "verified": 2,
                                             "absent": ["alpha", "beta"]})
        _write_json(run / "inventory.json", {"exports": []})
        provenance = _write_json(tmp_path / "provenance-map.json", {"entries": [
            {"export_name": "alpha", "source_file": "src/a.ts", "source_line": 7}]})
        call = _ledger_call(COVERAGE_FILE, "--from coverage", keep=("--numerator", "--provenance"))
        proc = _run(call, values | {"{run_dir}": run.as_posix(), "{resolved_skill_package}": "pkg",
                                    "{forge_provenance_map}": provenance.as_posix()})
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert [(r["category"], r["title"], r["source"], r["export"]) for r in _ledger_records(values)] == [
            ("missing-export", "Missing export: alpha", "src/a.ts:7", "alpha"),
            ("missing-export", "Missing export: beta", "pkg/metadata.json", "beta")]

    def test_a_failed_count_check_leaves_no_file_for_5b(self, values: dict[str, str],
                                                        tmp_path: pathlib.Path) -> None:
        """§4b redirects the script into the run file; on a non-zero exit that file holds an error object, which
        §5b's call refuses, so §4b deletes it and §5b skips the call."""
        assert "follow its **Metadata Count Cross-Check** section" in _flow(
            _slice(_read(COVERAGE_FILE), "### 4b. Metadata", "**The numerator ground truth"))
        section = _flow(_read(COVERAGE_BRANCHES_FILE).split("\n## Metadata Count Cross-Check\n", 1)[1])
        assert '> "{run_dir}/metadata-coherence.json"' in section
        assert ("A non-zero exit leaves the script's error, or nothing, in that file: delete it, so §5b skips its "
                "call and records no count finding") in section
        run = tmp_path / "run"
        _write_json(run / "metadata-coherence.json", {"error": "clusterA must be an object", "code": "INVALID_INPUT"})
        proc = _run(_ledger_call(COVERAGE_FILE, "--from metadata-coherence"),
                    values | {"{run_dir}": run.as_posix(), "{resolved_skill_package}": "pkg"})
        assert proc.returncode == 2 and json.loads(proc.stdout)["code"] == "INVALID_INPUT", proc.stdout

    def test_coherence_records_references_patterns_and_structure(self) -> None:
        text = _flow(_body(COHERENCE_FILE))
        for needle in ("Critical `broken-reference` gap", "High `inaccurate-reference` gap",
                       "High `reference-escape` gap", "Medium `integration-pattern` gap",
                       "High `structural` gaps", "Medium `structural` gaps", "Medium `scripts-assets` gap"):
            assert needle in text, needle
        assert "coverage-check §1b recorded them" in text

    def test_a_function_no_example_names_does_not_block(self) -> None:
        text = _flow(_body(COHERENCE_FILE))
        assert "**Zero occurrences across the entire scope → Medium severity** finding" in text
        assert ("the §2.1, §2.2 and §2.5 findings are High `structural` gaps and the §2.3, §2.4 and §2.6 "
                "findings Medium `structural` gaps") in text
        assert '{"type": "export_not_in_usage", "severity": "Medium"' in text

    def test_external_validation_findings_are_recorded(self) -> None:
        section = _flow(_slice(_read(EXT_VALIDATORS_FILE), "### 5b. Record", "### 6. Report Results"))
        for source in ("`skill_check_diagnostics`", "`{tessl_validation}`", "`{tessl_description_suggestions}`",
                       "`{tessl_content_suggestions}`"):
            assert source in section, source


class TestStaleNameLineCheck:
    """#583's decision: a fabricated signature is a documented export absent at the
    source line the skill cites, decided only where ast-grep enumerated the exports.
    A stale name alone is outside the barrel set, which an internal symbol or a
    stratified tier_a set also is, so §2c checks the cited line with the verifier.
    #678: a stale name that is not fabricated and that the source still declares at
    column 0 (classify-stale's `defined_at`: a cited file, else the one file of the
    package that declares it) is a documented extra, an Info `observation` at that
    line, when the surface came from an extraction and does not list it in
    `excluded.outsideScope`; everything short of that stays a Medium gap.
    #698: the call passes the documented inventory, so that a module named
    after a name the skill documents as a function, hook, class, interface,
    enum or type does not declare it, and an example, script or migration
    folder right below the package root is never walked.
    #886: a name the cited file does not define, which an export list renames
    to it from a name that file declares, is `aliased`, not fabricated, and so
    a documented extra at the alias.
    #1007: the call passes the brief when the skill has one, so that a file
    the brief scopes out is no second declaration of a name."""

    CALL = ('uv run {verifyProvenanceCompletenessHelper} classify-stale --names "{run_dir}/coverage.json" '
            '--provenance "{forge_provenance_map}" --source-root "{source_path}" '
            '--inventory "{run_dir}/inventory.json" '
            '[--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] -o "{run_dir}/stale.json"')
    BRIEF = ' [--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"]'
    SOURCE = '"""Core."""\nimport os\n\n\ndef helper(x):\n    return os.fspath(x)\n'

    @pytest.fixture
    def section(self) -> str:
        text = _read(COVERAGE_FILE)
        return text[text.index("- **Stale names**"):text.index("### 4. The Denominator Record")]

    def test_the_call_is_fenced_with_its_probe_order(self, section: str) -> None:
        assert self.CALL in _fence(section, self.CALL)
        assert _frontmatter(COVERAGE_FILE)["verifyProvenanceCompletenessProbeOrder"][-1] == \
            "{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py"
        # #1007: the brief's scope narrows the walk, and a skill with no brief runs the call without it
        assert "and run once (leave `--brief` out with no brief):" in _flow(section)

    def test_fabricated_needs_a_cited_file_without_the_name(self, section: str) -> None:
        flow = _flow(section)
        for needle in (
            "Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `workspaceDrift` not `overridden`",
            "A name it marks `fabricated: true` (every map entry of the name cites a missing file or one that "
            "does not define it) is a Critical `fabricated-signature` gap at its `source`",
            "is a Medium `stale-documentation` gap",
            "a helper that does not resolve or exits non-zero",
            "A name with a `defined_at` (the source still declares it there, an import never counting, a module "
            "so named counting unless the name's inventory kind rules it out), or whose `declared_in` lists several "
            "files of which the skill's `[AST:]`/`[SRC:]` "
            "citations on lines naming it cite exactly one (or a package and its same-named module), is a "
            "documented extra: an Info `observation` gap at "
            "that declaration, when `surface.json` has an `extraction` and its `excluded.outsideScope` does not "
            "list the name",
            "(no `defined_at` and no single cited declaring file, one scoped out, no `extraction`, a dotted name,",
        ):
            assert needle in flow, needle

    def test_a_name_cited_at_another_packages_star_is_not_checked_by_script(self, section: str,
                                                                           tmp_path: pathlib.Path) -> None:
        """#1005: a stale name no file declares, which the skill cites at a file holding an `export *` from
        another package, is the Info observation §2c names, before the Medium catch-all, and §5b's coverage call
        records it so: the surface lists the star in `unresolvedStars`."""
        flow = _flow(section)
        # #1005 review: a name the brief scopes out keeps its scoped-out Medium, and the record's title is not
        # the one score-signatures.py records at the Deep tier (#1084)
        rule = ("With no `defined_at`, one cited at an `unresolvedStars` file and not scoped out is an Info "
                "`observation` naming the star.")
        assert rule in flow
        assert flow.index(rule) < flow.index("Any other stale name (")
        medium = next(r for r in _read(SCORING_FILE).splitlines() if r.startswith("| Medium   | `stale-documentation`"))
        assert ("not, with no `defined_at` and not scoped out by the brief, cited at a file holding another "
                "package's `export *` (an Info `observation`)") in medium
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# demo\n\n`Mock` mocks. `[AST:src/test/spy.ts:L1]`\n")
        surface = self._surface() | {"unresolvedStars": [
            {"file": "src/test/spy.ts", "line": None, "statement": "export * from '@vitest/spy'"}]}
        stale = [{"name": "Mock", "fabricated": False, "source": None, "defined_at": None, "declared_in": []}]
        [record] = gap_ledger.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Mock"]},
                                            surface=surface, stale=stale, skill_dir=str(skill))
        assert (record["severity"], record["category"], record["title"], record["source"]) == (
            "Info", "observation", "Not checked by script: Mock (another package's export *)", "SKILL.md:3")
        [record] = gap_ledger.from_coverage({"branch": "enumerated", "missing": [], "stale": ["Mock"]},
                                            surface=self._surface(), stale=stale, skill_dir=str(skill))
        assert (record["severity"], record["category"]) == ("Medium", "stale-documentation")

    def _classify(self, tmp_path: pathlib.Path, files: dict[str, str], stale: list[str],
                  entries: list[dict], kinds: dict[str, str] | None = None, brief: str | None = None) -> list[dict]:
        """The classify-stale call as §2c writes it, over `files` below the source root, with §1a's
        `inventory.json` giving each name of `kinds` its kind, and `--brief` only when the skill has a
        `brief` (its YAML text), as the call's bracket says."""
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_bytes(text.encode("utf-8"))
        run = tmp_path / "run"
        _write_json(run / "coverage.json", {"branch": "enumerated", "missing": [], "stale": stale})
        _write_json(run / "inventory.json", {"exports": [{"name": n, "kind": k} for n, k in (kinds or {}).items()],
                                             "references": [], "cross_check_mismatches": []})
        provenance = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        assert self.BRIEF in self.CALL
        call = self.CALL.replace("uv run {verifyProvenanceCompletenessHelper} ", "")
        # keep the bracketed flag without its brackets, or drop it
        call = call.replace(self.BRIEF, "" if brief is None else " " + self.BRIEF[2:-1])
        forge_data = tmp_path / "forge-data"
        if brief is not None:
            (forge_data / "demo").mkdir(parents=True)
            (forge_data / "demo" / "skill-brief.yaml").write_bytes(brief.encode("utf-8"))
        for key, value in {"{run_dir}": run.as_posix(), "{forge_provenance_map}": provenance.as_posix(),
                           "{source_path}": tmp_path.as_posix(), "{forge_data_folder}": forge_data.as_posix(),
                           "{skill_name}": "demo"}.items():
            call = call.replace(key, value)
        proc = subprocess.run([sys.executable, str(VERIFY_PROVENANCE), *shlex.split(call)],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        return json.loads((run / "stale.json").read_bytes())

    @staticmethod
    def _surface(*outside: str, extraction: bool = True) -> dict:
        """The keys of load-coverage-inputs.py surface's result that §5b's coverage call reads: `extraction`
        is null when no extraction built it, and `excluded.outsideScope` then stays empty."""
        return {"exports": [], "extraction": {"status": "ok"} if extraction else None,
                "excluded": {"outsideScope": [{"name": n, "file": "pkg/old.py"} for n in outside],
                             "nestedEntries": []}}

    @pytest.mark.parametrize("name, cited_file, expected", [
        ("ghost_fn", "pkg/core.py", ("Critical", "fabricated-signature", "pkg/core.py:5")),
        ("helper", "pkg/core.py", ("Info", "observation", "pkg/core.py:5")),
        ("ghost_fn", "pkg/gone.py", ("Critical", "fabricated-signature", "pkg/gone.py:5")),
        ("os", "pkg/core.py", ("Medium", "stale-documentation", "SKILL.md")),
    ], ids=["no-such-name", "defined-outside-the-barrel", "file-missing", "imported-only"])
    def test_the_documented_call_decides(self, tmp_path: pathlib.Path, name: str, cited_file: str,
                                         expected: tuple[str, str, str]) -> None:
        [out] = self._classify(tmp_path, {"pkg/core.py": self.SOURCE}, [name],
                               [{"export_name": name, "source_file": cited_file, "source_line": 5}])
        assert out["fabricated"] is (expected[0] == "Critical"), out
        # §5b's coverage call turns the result into the gap.
        cov = json.loads((tmp_path / "run" / "coverage.json").read_bytes())
        [record] = gap_ledger.from_coverage(cov, surface=self._surface(), stale=[out], skill_dir=None)
        assert (record["severity"], record["category"], record["source"]) == expected, record
        # without the surface, or with one no extraction built, nothing rules a rescope out: a documented
        # extra stays Medium (#678)
        for surface in (None, self._surface(extraction=False)):
            [record] = gap_ledger.from_coverage(cov, surface=surface, stale=[out], skill_dir=None)
            assert record["severity"] == ("Critical" if expected[0] == "Critical" else "Medium"), record

    def test_an_alias_of_the_cited_declaration_is_a_documented_extra(self, tmp_path: pathlib.Path) -> None:
        """#886: oms-storybook documents `Entry`, cited at the `API_Entry` declaration a multi-line
        `export type { ... }` list renames to it. The classify-stale call finds the alias, and §5b's coverage
        call records an Info `observation` at it, never a Critical `fabricated-signature` gap; §4c's line check
        of its citation, which the provenance-line append no longer drops, is an Info `provenance-unverified`
        gap, which names the alias and the rename to record (#911), so nothing blocks the hard gate."""
        files = {"pkg/package.json": "{}\n", "pkg/api.ts": "export interface API_Entry {}\n",
                 "pkg/root.ts": "export type {\n  API_Entry as Entry,\n} from './api';\n"}
        [out] = self._classify(tmp_path, files, ["Entry"],
                               [{"export_name": "Entry", "source_file": "pkg/api.ts", "source_line": 1}],
                               {"Entry": "interface"})
        assert (out["fabricated"], out["reason"], out["defined_at"]) == (False, "aliased", "pkg/root.ts:2"), out
        cov = json.loads((tmp_path / "run" / "coverage.json").read_bytes())
        records = gap_ledger.from_coverage(cov, surface=self._surface(), stale=[out], skill_dir=None)
        assert [(r["severity"], r["category"], r["source"]) for r in records] == [
            ("Info", "observation", "pkg/root.ts:2")], records
        # §4c's verify call over the same map, then the provenance-line append's records
        metadata = _write_json(tmp_path / "metadata.json", {"exports": ["Entry"]})
        verified = tmp_path / "run" / "provenance-verify.json"
        proc = subprocess.run([sys.executable, str(VERIFY_PROVENANCE), "verify", "--metadata", str(metadata),
                               "--provenance", str(tmp_path / "provenance-map.json"), "--source-root",
                               tmp_path.as_posix(), "-o", str(verified)],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode in (0, 1), proc.stderr  # exit 1 means findings
        line = gap_ledger.without_fabricated(
            {"records": records}, gap_ledger.from_provenance_line(json.loads(verified.read_bytes()), stale=[out]))
        assert [(r["severity"], r["category"], r["source"]) for r in line] == [
            ("Info", "provenance-unverified", "pkg/api.ts:1")], line
        # #911: the gap names the alias and the rename to record, not a line of the file that never defines it
        assert line[0]["remediation"].startswith(
            "`Entry` is an alias of `API_Entry`, which a cited file declares; the source declares the alias at "
            "`pkg/root.ts:2`, and no line of `pkg/api.ts` defines `Entry`."), line
        assert "set `export_name` to `API_Entry`, add `reexported_as` `Entry`" in line[0]["remediation"]
        assert not [r for r in records + line if r["severity"] in gap_ledger.BLOCKING]

    def test_each_row_of_the_documented_extra_matrix(self, tmp_path: pathlib.Path) -> None:
        """#678's matrix, through the classify-stale call and §5b's coverage call, over a map whose entries
        are the skill's own (no entry made up for the package root): a name the package declares once, in
        Python or TS/JS, a module so named that the inventory gives no function, hook, class, interface,
        enum or type kind and a homonym the skill cites once are an Info `observation` at the declaration;
        an import, a star import, an indented local, a skipped place (#698: an example folder right below
        the package root included), a sibling package, a homonym the skill cites neither of, a re-export, a
        rescope, a dotted name and a removed function behind a module so named (#698) stay Medium; a
        fabricated name stays Critical."""
        files = {
            "pkg/__init__.py": "from .tasks.task import Task\n",
            "pkg/tasks/task.py": "class Task:\n    pass\n",
            "pkg/models/data_point.py": "import uuid\n\n\nclass DataPoint:\n    pass\n",
            "pkg/web/index.ts": "export function render() {}\n",
            "pkg/web/thing.ts": "import { render } from './index';\n\nexport class WebThing {}\n",
            "pkg/mixins.py": ("from .models import *\nfrom pydantic import BaseModel\n\n\n"
                              "def build():\n    Local = 1\n    return Local\n"),
            "pkg/tests/fixtures.py": "class InTests:\n    pass\n",
            "pkg/vendor/v.py": "class Vendored:\n    pass\n",
            "pkg/_vendor/v.py": "class UnderscoreVendored:\n    pass\n",
            "pkg/examples/e.py": "class InExamples:\n    pass\n",
            "pkg/example/old.py": "class InExample:\n    pass\n",
            "pkg/modules/migrations/runner.py": "class MigrationRunner:\n    pass\n",
            "pkg/client.py": "def other():\n    pass\n",
            "pkg/web/esm/thing.js": "export class InEsm {}\n",
            "pkg/site-packages/dep.py": "class InSitePackages:\n    pass\n",
            "other/__init__.py": "",
            "other/o.py": "class Outside:\n    pass\n",
            "pkg/a/config.py": "class Config:\n    pass\n",
            "pkg/b/config.py": "Config = dict\n",
            "pkg/models/job.py": "from .base import Base\n\n\nclass Job(Base):\n    pass\n",
            "pkg/jobs/job.py": "import asyncio\n\n\nclass Job:\n    pass\n",
            "pkg/low_level.py": "from .models.data_point import DataPoint\n",
            "pkg/reexports.py": "from .impl import ReExported as ReExported\n",
            "pkg/web/legacy.js": "exports.Required = require('./impl');\n",
            "pkg/old/rescoped.py": "class Rescoped:\n    pass\n",
        }
        entries = [
            {"export_name": "Task", "source_file": "pkg/tasks/task.py", "source_line": 1},
            {"export_name": "Starred", "source_file": "pkg/mixins.py", "source_line": 1},
            {"export_name": "Ghost", "source_file": "pkg/tasks/task.py", "source_line": 1},
            {"export_name": "render", "source_file": "pkg/web/index.ts", "source_line": 1},
        ]
        medium = ("Medium", "stale-documentation", "SKILL.md")
        expected = {
            "Task": ("Info", "observation", "pkg/tasks/task.py:1"),              # extra with an entry
            "DataPoint": ("Info", "observation", "pkg/models/data_point.py:4"),  # extra, no entry
            "WebThing": ("Info", "observation", "pkg/web/thing.ts:3"),           # a TS/JS extra
            "Starred": medium, "BaseModel": medium, "Local": medium,             # not a declaration
            "InTests": medium, "Vendored": medium, "UnderscoreVendored": medium,  # a skipped place
            "InExamples": medium, "InEsm": medium, "InSitePackages": medium,
            "InExample": medium,                                                 # right below the package root
            "MigrationRunner": ("Info", "observation", "pkg/modules/migrations/runner.py:1"),  # deeper down
            "client": medium,                                                    # a removed function
            "Outside": medium,                                                   # a sibling package
            "Config": ("Medium", "stale-documentation", "SKILL.md:3"),           # a homonym, cited neither
            "Job": ("Info", "observation", "pkg/jobs/job.py:4"),                 # a cited homonym
            "low_level": ("Info", "observation", "pkg/low_level.py:1"),          # a module, of no callable kind
            "ReExported": medium, "Required": medium,                            # a re-export
            "Rescoped": medium,                                                  # rescoped
            "Task.run": medium,                                                  # dotted
            "Ghost": ("Critical", "fabricated-signature", "pkg/tasks/task.py:1"),  # fabricated
        }
        # the documented inventory: the kinds the skill gives the names (it has no `module` kind)
        kinds = {"Task": "class", "DataPoint": "class", "WebThing": "class", "Job": "class", "Config": "class",
                 "MigrationRunner": "class", "client": "function", "low_level": "constant"}
        out = self._classify(tmp_path, files, list(expected), entries, kinds)
        cov = json.loads((tmp_path / "run" / "coverage.json").read_bytes())
        # the skill package: its own citations decide a homonym, on the lines that name it
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# demo\n\n`Config` holds settings. `[AST:pkg/settings.py:L1]`\n\n"
                                         b"`Job(fn)` wraps a step. `[AST:pkg/jobs/job.py:L4]`\n")
        records = gap_ledger.from_coverage(cov, surface=self._surface("Rescoped"), stale=out, skill_dir=str(skill))
        assert {r["export"]: (r["severity"], r["category"], r["source"]) for r in records} == expected
        assert [r["title"] for r in records if r["category"] == "observation"] == [
            "Documented extra: Task", "Documented extra: DataPoint", "Documented extra: WebThing",
            "Documented extra: MigrationRunner", "Documented extra: Job", "Documented extra: low_level"]
        declared_in = {o["name"]: o["declared_in"] for o in out}
        assert (declared_in["Config"], declared_in["Job"]) == (["pkg/a/config.py:1", "pkg/b/config.py:1"],
                                                               ["pkg/jobs/job.py:4", "pkg/models/job.py:4"])
        assert (declared_in["InExample"], declared_in["client"]) == ([], [])
        defined_at = {o["name"]: o["defined_at"] for o in out}
        # the rescope is declared, and still Medium; the fabricated name is never looked up
        assert (defined_at["Rescoped"], defined_at["Ghost"]) == ("pkg/old/rescoped.py:1", None)

    def test_the_cognee_shape_records_documented_extras(self, tmp_path: pathlib.Path) -> None:
        """#678's acceptance: `Task`, `run_tasks` and `low_level`, documented with no entry, are each one
        Info `observation` at its declaration, while every entry of the map lies under cognee/api/v1/ (the
        walk widens to the cognee/ package): `Task` is declared twice in cognee/modules/pipelines/ and the
        skill cites one of the two, and `low_level` is the one module so named, which the inventory gives no
        function, hook, class, interface, enum or type kind (#698)."""
        files = {
            "cognee/__init__.py": ("from .api.v1.add import add\nfrom .api.v1.search import search\n"
                                   "from .modules.pipelines import Task, run_tasks\n"),
            "cognee/api/__init__.py": "",
            "cognee/api/v1/__init__.py": "",
            "cognee/api/v1/add/__init__.py": "from .add import add\n",
            "cognee/api/v1/add/add.py": "async def add(data):\n    pass\n",
            "cognee/api/v1/search/__init__.py": "from .search import search\n",
            "cognee/api/v1/search/search.py": "async def search(query):\n    pass\n",
            "cognee/api/tests/fakes.py": "class Task:\n    pass\n",  # a test double, never read
            "cognee/modules/pipelines/__init__.py": ("from .tasks.task import Task\n"
                                                     "from .operations.run_tasks import run_tasks\n"),
            "cognee/modules/pipelines/tasks/task.py": "from typing import Any\n\n\nclass Task:\n    pass\n",
            "cognee/modules/pipelines/models/Task.py": ("from sqlalchemy import Column\n\n\n"
                                                        "class Task(Base):\n    __tablename__ = 'tasks'\n"),
            "cognee/low_level.py": "from cognee.infrastructure.engine import Edge\n",
            "cognee/modules/pipelines/operations/run_tasks.py": ("import asyncio\n\nfrom ..tasks.task import Task\n\n\n"
                                                                 "async def run_tasks(tasks, data=None):\n    pass\n"),
            "cognee/tests/unit/test_pipelines.py": "async def run_tasks(tasks):\n    pass\n",
        }
        entries = [{"export_name": "add", "source_file": "cognee/api/v1/add/add.py", "source_line": 1},
                   {"export_name": "search", "source_file": "cognee/api/v1/search/search.py", "source_line": 1}]
        out = self._classify(tmp_path, files, ["Task", "run_tasks", "low_level"], entries,
                             {"Task": "class", "run_tasks": "function", "low_level": "constant"})
        cov = json.loads((tmp_path / "run" / "coverage.json").read_bytes())
        skill = tmp_path / "skill"
        (skill / "references").mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"# cognee\n\nConstructor: `Task(executable, *args)`. "
                                         b"`[AST:cognee/modules/pipelines/tasks/task.py:L4]`\n")
        (skill / "references" / "pipelines.md").write_bytes(b"# Pipelines\n\n`run_tasks(tasks)` runs them.\n\n"
                                                            b"`cognee.low_level` exposes `DataPoint`.\n")
        records = gap_ledger.from_coverage(cov, surface=self._surface(), stale=out, skill_dir=str(skill))
        assert [(r["severity"], r["category"], r["title"], r["source"]) for r in records] == [
            ("Info", "observation", "Documented extra: Task", "cognee/modules/pipelines/tasks/task.py:4"),
            ("Info", "observation", "Documented extra: run_tasks",
             "cognee/modules/pipelines/operations/run_tasks.py:6"),
            ("Info", "observation", "Documented extra: low_level", "cognee/low_level.py:1")]
        assert not [r for r in records if r["category"] == "stale-documentation"]

    def test_a_package_and_its_same_named_module_are_one_documented_extra(self, tmp_path: pathlib.Path) -> None:
        """#1012: classify-stale lists `cognee/exceptions/__init__.py` and the module `exceptions.py` inside it
        as two declaring files of `exceptions`, and a skill line that documents `cognee.exceptions` cites both.
        They are the one module that import path names, so the record is an Info documented extra at the
        package, not a Medium asking to remove documentation of a module that exists."""
        files = {
            "cognee/__init__.py": "from .api.v1.add import add\n",
            "cognee/api/__init__.py": "",
            "cognee/api/v1/__init__.py": "",
            "cognee/api/v1/add/__init__.py": "from .add import add\n",
            "cognee/api/v1/add/add.py": "async def add(data):\n    pass\n",
            "cognee/exceptions/__init__.py": "from .exceptions import CogneeApiError\n",
            "cognee/exceptions/exceptions.py": "class CogneeApiError(Exception):\n    pass\n",
        }
        entries = [{"export_name": "add", "source_file": "cognee/api/v1/add/add.py", "source_line": 1}]
        out = self._classify(tmp_path, files, ["exceptions"], entries)
        assert [(o["defined_at"], o["declared_in"]) for o in out] == [
            (None, ["cognee/exceptions/__init__.py:1", "cognee/exceptions/exceptions.py:1"])]
        cov = json.loads((tmp_path / "run" / "coverage.json").read_bytes())
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# cognee\n\n`cognee.exceptions` `[AST:cognee/exceptions/exceptions.py:L1]` "
                                         b"\xc2\xb7 `[SRC:cognee/exceptions/__init__.py:L1]`\n")
        records = gap_ledger.from_coverage(cov, surface=self._surface(), stale=out, skill_dir=str(skill))
        assert [(r["severity"], r["category"], r["title"], r["source"]) for r in records] == [
            ("Info", "observation", "Documented extra: exceptions", "cognee/exceptions/__init__.py:1")]

    def test_a_copy_the_brief_scopes_out_is_no_second_declaration(self, tmp_path: pathlib.Path) -> None:
        """#1007: oms-uitripled documents `UILibraryContextValue`, declared in scope only in the react-shadcn
        package. Its map's entries span two packages and `packages/` holds no package.json, so the walk reads
        the whole repository, and the docs app keeps a copy of the file that no `scope.include` glob covers.
        With the brief, §2c's call leaves the copy out, and the name is an Info documented extra at its one
        declaration in scope; without one, the copy reads as a second declaration and the gap stays Medium."""
        provider = "packages/components/react-shadcn/src/ui-library-provider.tsx"
        declaration = "export interface UILibraryContextValue {\n  lib: string;\n}\n"
        files = {
            "package.json": "{}\n", "packages/components/react-shadcn/package.json": "{}\n",
            "packages/cli/package.json": "{}\n", "apps/docs/package.json": "{}\n",
            provider: "import React from 'react';\n" + declaration + "export function UILibraryProvider() {}\n",
            "apps/docs/components/ui-library-provider.tsx": "import React from 'react';\n" + declaration,
            "packages/cli/src/add.ts": "export function add() {}\n",
        }
        entries = [{"export_name": "UILibraryProvider", "source_file": provider, "source_line": 5},
                   {"export_name": "add", "source_file": "packages/cli/src/add.ts", "source_line": 1}]
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# uitripled\n\n`UILibraryContextValue` holds the chosen library.\n")
        brief = "name: uitripled\nscope:\n  type: full-library\n  include:\n    - packages/**\n"
        expected = {
            brief: ("Info", "observation", "Documented extra: UILibraryContextValue", f"{provider}:2"),
            None: ("Medium", "stale-documentation", "Stale documentation: UILibraryContextValue", "SKILL.md:3"),
        }
        for given, record in expected.items():
            root = tmp_path / ("with-brief" if given else "without-brief")
            out = self._classify(root, files, ["UILibraryContextValue"], entries,
                                 {"UILibraryContextValue": "interface"}, brief=given)
            cov = json.loads((root / "run" / "coverage.json").read_bytes())
            records = gap_ledger.from_coverage(cov, surface=self._surface(), stale=out, skill_dir=str(skill))
            assert [(r["severity"], r["category"], r["title"], r["source"]) for r in records] == [record], given

    def test_a_name_declared_only_where_the_brief_scopes_out_keeps_its_gap(self, tmp_path: pathlib.Path) -> None:
        """#1007 review: with the brief, a file it scopes out still declares a name no file in its scope declares.
        A function the `start_server` namespace passes on from `pkg/shared/utils.py` (#969, #1031) keeps the
        scoped-out Medium that names the exclude glob, and an internal `Helper` only in `pkg/internal/` stays an
        Info documented extra there, as without the brief."""
        files = {
            "pkg/__init__.py": "from .api.visualize import tools, start_server\n", "pkg/api/__init__.py": "",
            "pkg/api/visualize/__init__.py": "from . import tools\nfrom . import start_server\n",
            "pkg/api/visualize/tools.py": "from pkg.shared.utils import start_server\n",
            "pkg/api/visualize/start_server.py": "from pkg.shared.utils import start_server\n",
            "pkg/shared/__init__.py": "", "pkg/shared/utils.py": "def start_server():\n    pass\n",
            "pkg/internal/__init__.py": "", "pkg/internal/helper.py": "class Helper:\n    pass\n",
        }
        entries = [{"export_name": "tools", "source_file": "pkg/api/visualize/tools.py", "source_line": 1,
                    "export_type": "module"}]
        skill = tmp_path / "skill"
        skill.mkdir()
        (skill / "SKILL.md").write_bytes(b"# pkg\n\n`start_server()` serves.\n\n`Helper` helps.\n")
        surface = self._surface()
        surface["excluded"]["outsideScope"] = [
            {"name": "start_server", "file": "pkg/shared/utils.py", "line": 1, "entry": "pkg/__init__.py",
             "excludeGlob": "pkg/shared/**", "outsideInclude": False, "namespace": "start_server"}]
        brief = "name: pkg\nscope:\n  type: full-library\n  exclude:\n    - pkg/shared/**\n    - pkg/internal/**\n"
        for given in (brief, None):
            root = tmp_path / ("with-brief" if given else "without-brief")
            out = self._classify(root, files, ["start_server", "Helper"], entries,
                                 {"start_server": "function", "Helper": "class"}, brief=given)
            cov = json.loads((root / "run" / "coverage.json").read_bytes())
            records = gap_ledger.from_coverage(cov, surface=surface, stale=out, skill_dir=str(skill))
            assert [(r["severity"], r["title"], r["source"]) for r in records] == [
                ("Medium", "Stale documentation: start_server", "SKILL.md:3"),
                ("Info", "Documented extra: Helper", "pkg/internal/helper.py:1")], given
            assert "scopes out `pkg/shared/utils.py:1`" in records[0]["remediation"], given
            assert "narrow `pkg/shared/**`" in records[0]["remediation"], given


# ---------------------------------------------------------------------------
# The report step publishes only a whole report (#585, #583 item 4)
# ---------------------------------------------------------------------------


class TestReportTerminalSequence:
    @pytest.fixture
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_the_expected_set_leaves_report_out(self, text: str) -> None:
        contract = _slice(text, "### 4c. Result Contract", "### 5.")
        expected = re.findall(r"'([a-z-]+)'", _fence(contract, "'external-validators'"))
        assert expected == ["init", "detect-mode", "coverage-check", "coherence-check", "external-validators",
                            "hard-gate", "score"]
        # Recorded only once the result files exist: a halt before them leaves no 'report' behind.
        assert "Once the result files are written, append `'report'` to `stepsCompleted`" in _flow(contract)

    def test_render_and_checks_come_before_the_writes_and_the_hook(self, text: str) -> None:
        order = [
            "--stage report <<'SKF_GAPS'",  # §4b.5 records discovery
            'render --ledger "{ledgerFile}" --heading',
            'summary --ledger "{ledgerFile}"',
            "**Enforce step completeness.**",
            "**Check the report sections.**",
            "**Renew the run lock**",
            # the payload is built, and the verdict checked, before the report takes its public name
            '--output "{run_dir}/result-context.json"',
            "**Publish the report.**",
            'mv "{report_file}" "{publishedReportFile}"',
            "emit --workflow skf-test-skill --run-dir",
            "Once the result files are written, append `'report'`",
            "{onCompleteCommand} --result-path=",
            "### 6. Present Final Report",
            "### 7. Health-Check Dispatch",
        ]
        positions = [text.index(needle) for needle in order]
        assert positions == sorted(positions), [needle for _, needle in sorted(zip(positions, order))]

    def test_the_section_check_catches_a_skipped_stage(self, text: str) -> None:
        check = _slice(text, "**Check the report sections.**", "**Renew the run lock**")
        script = _fence(check, "for heading in")
        assert re.findall(r"'(## [^']+)'", script) == TEMPLATE_HEADINGS
        assert 'grep -cxF "$heading" "{outputFile}"' in script
        assert "grep -c '^<!-- Populated by' \"{outputFile}\"" in script
        # #971: the H1 init.md §6c filled, counted as the exact line.
        assert "printf 'title: '; grep -cxF '# Test Report: {skill_name}' \"{outputFile}\"" in script
        flow = _flow(check)
        assert "Count them with grep, not by eye" in flow
        assert "Each heading must print 1" in flow and "`placeholders` must print 0" in flow
        assert "`title` must print 1" in flow and "a `title` count other than 1, HALT" in flow
        assert "a `title` count of" in flow and "the report does not hold `# Test Report: {skill_name}` once" in flow
        assert 'HALT (`halt_reason: "report-anchor-missing"`, phase `report:anchors`)' in check

    # One case per row of #971's matrix, besides the section cases: the title is the
    # exact line `# Test Report: {skill_name}`, so a placeholder, a wrong name or a
    # second title fails it, and a section that quotes `{{` does not. A title that only
    # starts with the line (`demo (v1)`) fails it too: grep -x counts whole lines.
    @pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="runs the check through bash")
    @pytest.mark.parametrize("case", ["whole", "skipped", "appended", "untitled", "misnamed", "titled-twice",
                                      "quotes-braces", "suffixed"])
    def test_the_section_check_counts_as_written(self, text: str, tmp_path: pathlib.Path, case: str) -> None:
        script = _fence(_slice(text, "**Check the report sections.**", "**Renew the run lock**"), "for heading in")
        report = _read(TEMPLATE_FILE)
        if case != "untitled":
            name = {"misnamed": "other", "suffixed": "demo (v1)"}.get(case, "demo")
            report = report.replace("# Test Report: {{skillName}}", f"# Test Report: {name}")
        written = "Written by its stage: `{{ value }}` is quoted." if case == "quotes-braces" else "Written by its stage."
        for placeholder in re.findall(r"^<!-- Populated by .*-->$", report, re.M):
            if case not in ("skipped", "appended") or "coverage-check" not in placeholder:
                report = report.replace(placeholder, written)
        if case == "appended":
            report += "\n## Coverage Analysis\n\nAppended instead of written in place.\n"
        if case == "titled-twice":
            report += "\n# Test Report: demo\n\nWritten again by a stage.\n"
        path = tmp_path / f"test-report-demo-{RUN_ID}.md"
        path.write_bytes(report.encode("utf-8"))
        command = script.replace("{outputFile}", path.as_posix()).replace("{skill_name}", "demo")
        proc = subprocess.run(["bash", "-c", command], capture_output=True, text=True, encoding="utf-8")
        counts = {k: int(v) for k, v in (line.rsplit(": ", 1) for line in proc.stdout.splitlines())}
        expected = dict.fromkeys(TEMPLATE_HEADINGS, 1) | {"placeholders": 0, "title": 1}
        if case == "skipped":
            expected["placeholders"] = 1
        if case == "appended":
            expected |= {"## Coverage Analysis": 2, "placeholders": 1}
        if case in ("untitled", "misnamed", "suffixed"):
            expected["title"] = 0
        if case == "titled-twice":
            expected["title"] = 2
        assert counts == expected

    def test_the_inconclusive_paragraph_matches_the_order(self, text: str) -> None:
        final = _flow(_slice(text, "### 5. Finalize Output Document", "### 6."))
        assert "§4c wrote the result contract with that verdict and §6 presents it" in final
        assert "have already been written" not in text

    def test_fail_names_update_skill_from_test_report(self, text: str) -> None:
        present = _slice(text, "### 6. Present Final Report", "### 6b.")
        for branch in ("{IF FAIL after scoring:}", "{IF the hard gate blocked the run:}"):
            follow = present[present.index(branch):].split("\n\n", 1)[0]
            assert "`@Ferris US {skill_name} --from-test-report`" in follow, branch
        # #798, #803: Update Skill repairs only the gaps it routes; the two it cannot repair go elsewhere
        follow = present[present.index("{IF FAIL after scoring:}"):].split("\n\n", 1)[0]
        assert "Update Skill repairs the gaps it routes" in follow and "reads this report's gaps and repairs" not in follow
        assert ("A `stale-documentation` or `metadata-drift` gap needs what its remediation names: a person, Create "
                "Skill or the skill brief.") in follow

    def test_counts_come_from_the_ledger(self, text: str) -> None:
        contract = _flow(_slice(text, "### 4c. Result Contract", "### 5."))
        assert "Bind `{gap_counts}` ← `counts`, `{total_gaps}` ← `total` and `{blocking_gaps}` ← `blocking`" in contract
        # The result contract's gap counts come from the ledger too, through the script.
        raw = _slice(text, "### 4c. Result Contract", "### 5.")
        assert '--ledger "{ledgerFile}"' in _fence(raw, "uv run {resultContextScript}")
        present = _slice(text, "### 6. Present Final Report", "### 6b.")
        assert "- Critical: {gap_counts.Critical}" in present

    def test_no_gap_is_classified_from_the_report_markdown(self, text: str) -> None:
        collect = _flow(_slice(text, "### 1. Collect All Issues", "### 2."))
        assert "Do not collect gaps again from the report's sections" in collect
        evidence = _flow(_slice(_read(SCORE_FILE), "#### 4b.1 Generate Evidence Report", "**Evidence report template:**"))
        assert "**Read the gaps from the gap ledger**" in evidence
        assert "extract findings from the Coverage Analysis and Coherence Analysis sections" not in evidence

    def test_the_evidence_report_takes_the_render_output(self) -> None:
        """The script orders and counts the gaps; score.md §4b.1 sorts nothing by hand."""
        section = _slice(_read(SCORE_FILE), "#### 4b.1 Generate Evidence Report", "### 5.")
        command = 'uv run {gapLedgerScript} render --ledger "{ledgerFile}"'
        assert _fence(section, command).strip() == command
        assert "write its output unchanged under **Findings Preventing Higher Threshold**" in _flow(section)
        assert "{the output of the render command above, unchanged}" in section
        for gone in ("{For each gap entry", "{Count: N critical", "in the order the Gap Report uses",
                     "The {N} findings above"):
            assert gone not in section, gone


class TestDiscoveryGaps:
    """#543: a skipped discovery test is a counted Info gap; WARN and FAIL are Medium and High gaps."""

    @pytest.fixture
    def discovery(self) -> str:
        return _flow(_slice(_read(REPORT_FILE), "### 4b. Discovery Testing", "### 4c."))

    def test_each_skip_branch_records_an_info_gap(self, discovery: str) -> None:
        assert "Each skip branch (the bypass above, §4b.0 and the §4b.2 guard) is one Info `discovery` gap" in discovery
        for reason in ("`--no-discovery flag set`", "`catalog size N={catalog_size}",
                       "`subagents unavailable, routing test requires isolated context`"):
            assert f"with the reason {reason}" in discovery, reason
        assert "Info-severity note" not in discovery
        assert "skip to §4c" not in discovery and "skip directly to §4c" not in discovery

    def test_the_routers_read_no_file(self, discovery: str) -> None:
        """#1039: the run lock and the in-progress report name the skill under test, so a router reads nothing."""
        assert ("spawn an isolated subagent with NO prior context about which skill is under test"
                " and no file or shell tools, since the run lock and the in-progress report in `{forge_version}`"
                " both name that skill") in discovery
        instruction = _slice(discovery, "You are an agent selecting the best skill", "**4b.3")
        assert instruction.count("Return only JSON.") == 1
        assert "Answer from this catalog alone: read no file and use no tool. Return only JSON.\"" in instruction

    def test_a_router_takes_a_type_without_file_or_shell_tools(self, discovery: str) -> None:
        """#1079: a Claude Code Agent call takes no tool list and one without `subagent_type` gets every tool."""
        spawn = _slice(discovery, "**4b.2 Spawn a discovery subagent:**", "**4b.3")
        for needle in ("**Router rule:** a router gets no tool that reads or lists files, runs a command"
                       " or starts another agent",
                       "(Read, Grep, Glob, Bash, PowerShell, Write, Edit, Agent or an MCP tool that reads files, say)",
                       "a tool that only reaches the web, such as WebFetch or WebSearch, is fine",
                       "On Claude Code, where an Agent call takes no tool list, pass a `subagent_type`"
                       " listed for the Agent tool with none of these tools",
                       "(`web-fetch` where it is listed)",
                       "never leave `subagent_type` out: an Agent call without one gets `general-purpose`,"
                       " which carries every tool",
                       "On other hosts, where the spawn call or the agent definition sets a subagent's tools,"
                       " give the router none of these",
                       "The run never writes or edits an agent definition, so a host that offers neither"
                       " falls under the guard above"):
            assert needle in spawn, needle
        assert "(where the platform lets a subagent be spawned without tools, do so)" not in discovery
        guard = _slice(spawn, "**Subagents-unavailable guard (precedes the spawn).**",
                       "For each of the 3 prompts, spawn an isolated subagent")
        assert "or none can be spawned without file or shell tools (the router rule below)" in guard
        assert "do not fall back to answering the routing in the main thread or in a subagent that has those tools" in guard
        assert "such a subagent can read the run lock and the in-progress report, which name that skill" in guard
        assert "with the reason `subagents unavailable, routing test requires isolated context`" in guard
        assert "If subagents cannot be spawned in this environment (e.g. a headless/CI pipeline" in guard
        assert "(do not count it PASS or FAIL), and skip to §4b.5." in guard
        assert spawn.index("**Subagents-unavailable guard") < spawn.index("For each of the 3 prompts, spawn")
        assert spawn.index("For each of the 3 prompts, spawn") < spawn.index("**Router rule:**")
        skip = _slice(discovery, "**Recording a skip.**", "**4b.0")
        assert ("or an environment that can spawn a subagent without file or shell tools (on Claude Code,"
                " an agent type defined in `.claude/agents/` with `name`, `description` and `tools: WebFetch`"
                " in its frontmatter, say)") in skip
        assert "an environment that can spawn subagents." not in skip
        [row] = [r for r in _read(SCORING_FILE).splitlines() if r.startswith("| Info     | `discovery`")]
        assert "Discovery testing not performed" in row
        assert "or no subagent without file or shell tools to route the prompts" in row
        assert "or no subagents to route the prompts" not in row
        [docs] = [line for line in _read(REPO_ROOT / "docs" / "workflows.md").splitlines()
                  if line.startswith("- `--no-discovery` ")]
        for needle in ("the run asks three subagents with no file or shell tools",
                       "or one you define in `.claude/agents/` with `name`, `description` and `tools: WebFetch`",
                       "Where no such subagent can be started, the run skips the test and records an Info gap"):
            assert needle in docs, needle

    def test_no_prompt_names_an_export(self, discovery: str) -> None:
        """#1049: the catalog lists the exports, so a prompt that names one routes on the name."""
        prompts = _slice(discovery, "**4b.1 Extract realistic prompts", "**4b.2")
        assert ("Every prompt, organic or synthesized, describes the task in a user's own words and names no export,"
                " no skill name and no library or package name, since the catalog descriptions list those;"
                " replace any such name with what it does") in prompts
        patterns = _slice(discovery, "Realistic prompt patterns for synthesis", "**4b.5")
        assert ("- Abbreviated: \"run the {task word} thing on this data\" ({task word} is a plain word for the job,"
                " such as memory or indexing, never an export or library name)") in patterns
        assert "{keyword}" not in discovery

    def test_warn_and_fail_are_gaps_and_pass_is_none(self, discovery: str) -> None:
        assert "discovery check PASS: no gap" in discovery
        assert "discovery check WARN: a Medium `discovery` gap" in discovery
        assert "discovery check FAIL: a High `discovery` gap" in discovery

    def test_the_discovery_gap_reaches_the_totals(self, discovery: str) -> None:
        assert _append_command(REPORT_FILE, "report")
        assert "it is counted in the Gap Report's totals and in the counts §6 presents" in discovery


# ---------------------------------------------------------------------------
# Stage closing lines name their stepsCompleted token (#585)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path, token", [
    (INIT_FILE, "init"),
    (DETECT_FILE, "detect-mode"),
    (COVERAGE_FILE, "coverage-check"),
    (COHERENCE_FILE, "coherence-check"),
    (EXT_VALIDATORS_FILE, "external-validators"),
    (STEP_FILE, "hard-gate"),
    (SCORE_FILE, "score"),
], ids=["init", "detect-mode", "coverage-check", "coherence-check", "external-validators", "hard-gate", "score"])
def test_each_stage_closing_line_names_its_token(path: pathlib.Path, token: str) -> None:
    last = [line for line in _read(path).splitlines() if line.strip()][-1]
    assert f"`'{token}'`" in last, last
    assert "load and execute" in last
    assert "Update stepsCompleted, then" not in _read(path)


# ---------------------------------------------------------------------------
# The report template (#583 item 4)
# ---------------------------------------------------------------------------


class TestReportTemplate:
    @pytest.fixture
    def text(self) -> str:
        return _read(TEMPLATE_FILE)

    def test_each_heading_has_a_placeholder(self, text: str) -> None:
        headings = [line for line in text.splitlines() if line.startswith("## ")]
        assert headings == TEMPLATE_HEADINGS
        for heading in TEMPLATE_HEADINGS:
            after = text[text.index(heading) + len(heading):].lstrip("\n")
            assert after.startswith("<!-- Populated by "), heading

    def test_each_placeholder_names_a_real_section(self, text: str) -> None:
        named = re.findall(r"<!-- Populated by ([a-z-]+) §(\d+[a-z]?)", text)
        assert len(named) == len(TEMPLATE_HEADINGS)
        for step, number in named:
            assert re.search(rf"^### {number}\. ", _read(REFS / f"{step}.md"), re.M), (step, number)

    @pytest.mark.parametrize("path, heading", [
        (DETECT_FILE, "## Test Summary"),
        (COVERAGE_FILE, "## Coverage Analysis"),
        (COHERENCE_FILE, "## Coherence Analysis"),
        (EXT_VALIDATORS_FILE, "## External Validation"),
        (SCORE_FILE, "## Completeness Score"),
        (STEP_FILE, "## Completeness Score"),
        (REPORT_FILE, "## Gap Report"),
    ], ids=["detect-mode", "coverage-check", "coherence-check", "external-validators", "score",
            "step-hard-gate", "report"])
    def test_each_stage_writes_in_place_of_its_heading(self, path: pathlib.Path, heading: str) -> None:
        assert f"in place of the template's `{heading}` heading and the placeholder comment under it" \
            in _flow(_read(path))

    @pytest.mark.parametrize("path, heading", [
        (COVERAGE_FILE, "### 5. Write the Coverage Analysis Section"),
        (COHERENCE_FILE, "### 6. Write the Coherence Analysis Section"),
        (EXT_VALIDATORS_FILE, "### 5. Write the External Validation Section"),
        (SCORE_FILE, "### 6. Write the Completeness Score Section"),
    ], ids=["coverage-check", "coherence-check", "external-validators", "score"])
    def test_no_section_heading_says_append(self, path: pathlib.Path, heading: str) -> None:
        """Appending is the failure report.md's section check halts on."""
        text = _read(path)
        assert re.search(rf"^{re.escape(heading)}$", text, re.M), heading
        assert not re.search(r"^#+ .*\bAppend\b.*\bto Output\b", text, re.M)

    def test_frontmatter_records_the_gate(self, text: str) -> None:
        assert "hardGate: ''" in text
        assert "hardGate: ''" in _fence(_read(INIT_FILE), "workflowType: 'test-skill'")

    def test_the_comment_mentions_the_hard_gate(self, text: str) -> None:
        assert "step-hard-gate" in text
        assert not re.search(r"^## Hard Gate", text, re.MULTILINE)

    def test_init_fills_the_title_the_section_check_counts(self, text: str) -> None:
        """#971: init.md §6c fills the H1's placeholder, and report.md §4c greps for the filled line."""
        assert text.count("{{skillName}}") == 1
        titles = [line for line in _body(TEMPLATE_FILE).splitlines() if line.startswith("# ")]
        assert titles == ["# Test Report: {{skillName}}"]
        script = _fence(_slice(_read(REPORT_FILE), "**Check the report sections.**", "**Renew the run lock**"),
                        "for heading in")
        grepped = re.search(r"^printf 'title: '; grep -cxF '([^']+)' \"\{outputFile\}\"$", script, re.M)
        assert grepped, "report.md §4c does not count the title"
        assert grepped.group(1) == titles[0].replace("{{skillName}}", "{skill_name}")
        init = _flow(_slice(_read(INIT_FILE), "**6c. Create `{outputFile}`", "### 7."))
        assert "Replace the template's frontmatter with this block (the two hold the same keys)." in init
        assert ("Then replace `{{skillName}}` in the template's H1 with `{skill_name}`, so the report's title is "
                f"`{grepped.group(1)}`") in init
        assert "that the title above names the skill" in _flow(text)


class TestOutputFormats:
    @pytest.fixture
    def text(self) -> str:
        return _read(FORMATS_FILE)

    def test_the_ledger_record_format_matches_the_script(self, text: str) -> None:
        record = json.loads(_fence(_slice(text, "## Ledger Record Format", "## Gap Report"), '"severity"'))
        assert set(record) == set(gap_ledger.REQUIRED_FIELDS) | set(gap_ledger.OPTIONAL_FIELDS)
        assert "Leave out `id`, `group` and `stage`" in text

    def test_the_gap_report_format_is_the_scripts_alone(self, text: str, tmp_path: pathlib.Path) -> None:
        """The asset names the render and keeps no copy of its format or effort strings to drift."""
        pointer = _flow(_slice(text, "## Gap Report", "## Discovery Quality Subsection"))
        assert "`uv run scripts/gap-ledger.py render --ledger <ledger> --heading` prints the Gap Report" in pointer
        for gone in ("## Gap Entry Format", "## Effort Estimation Guidelines", "**Total Gaps:**", "### GAP-{NNN}"):
            assert gone not in text, gone
        ledger = tmp_path / f"test-findings-{RUN_ID}.json"
        record = _gap("Critical", "signature-mismatch", "Signature mismatch: formatDate", "src/utils.ts:42",
                      issue="missing optional parameter 'format'", export="formatDate")
        proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                               "coverage-check"], input=json.dumps([record]), capture_output=True, text=True,
                              encoding="utf-8")
        assert proc.returncode == 0, proc.stdout
        rendered = subprocess.run([sys.executable, str(GAP_LEDGER), "render", "--ledger", str(ledger), "--heading"],
                                  capture_output=True, text=True, encoding="utf-8").stdout
        assert [line for line in rendered.splitlines() if line] == [
            "## Gap Report",
            "**Total Gaps:** 1",
            "**Blocking (Critical + High):** 1",
            "**Non-blocking (Medium + Low + Info):** 0",
            "### Remediation Summary",
            "| Severity | Count | Estimated Effort |",
            "|----------|-------|------------------|",
            f"| Critical | 1 | signature-mismatch (1): {gap_ledger.ACTIONS['signature-mismatch']} |",
            "| High | 0 | None |",
            "| Medium | 0 | None |",
            "| Low | 0 | None |",
            "| Info | 0 | None |",
            "| **Total** | **1** | |",
            "### GAP-001: Signature mismatch: formatDate",
            "**Severity:** Critical",
            "**Category:** Coverage (signature-mismatch)",
            "**Source:** src/utils.ts:42",
            "**Export:** formatDate",
            "**Issue:** missing optional parameter 'format'",
            f"**Remediation:** {record['remediation']}",
        ]

    def test_exports_cross_checked_is_the_validators_count(self, text: str, tmp_path: pathlib.Path) -> None:
        """#920: the Reference Consistency line read a `{count}` no stage defined and no script wrote, so it was
        counted by hand. It now names `crossChecked.count` in `{run_dir}/inventory.json`, a key validate-inventory.py
        writes into the inventory, and the contract tells the reader it writes none."""
        section = _slice(text, "Only rendered when `references/` directory exists", "## Coherence Analysis")
        block = _fence(section, "**Exports Cross-Checked:**")
        line = re.search(r"^\*\*Exports Cross-Checked:\*\* \{(\w+)\.(\w+)\}$", block, flags=re.MULTILINE)
        assert line and line.group(1, 2) == ("crossChecked", "count")
        assert "{count}" not in line.group(0)
        assert ("**Exports Cross-Checked** is `crossChecked.count` from `{run_dir}/inventory.json`, which "
                "`scripts/validate-inventory.py` writes: the inventory's names that two or more of the files it reads "
                "write, never counted by hand.") in _flow(section)
        contract = _flow(_read(REFS / "inventory-contract.md"))
        assert ('`validate-inventory.py` adds `crossChecked` to the inventory it writes, `{"count": <int>, "names": '
                "[<name>, ...]}`: each inventory name, once, that two or more of the files it reads write (SKILL.md "
                "and each file `references` lists), by the spot-check's name match outside `[AST:]`, `[SRC:]` and "
                "`[EXT:]` citations, so a mention in prose counts. The reader writes no `crossChecked`; the validator "
                "replaces one it finds.") in contract
        # The key the format names is the one the validator writes, on a two-file package.
        validator = _load("skf_validate_inventory_for_step_test", TS_DIR / "scripts" / "validate-inventory.py")
        pkg = tmp_path / "pkg"
        (pkg / "references").mkdir(parents=True)
        (pkg / "SKILL.md").write_text("# Demo\n\n`shared()` and `own()`.\n", encoding="utf-8")
        (pkg / "references" / "api.md").write_text("`shared(n)`\n", encoding="utf-8")
        raw = json.dumps({"exports": [{"name": "own", "kind": "function"}, {"name": "shared", "kind": "function"}],
                          "cross_check_mismatches": [], "references": ["references/api.md"],
                          "crossChecked": {"count": 9, "names": []}})
        result = validator.validate_inventory(raw, str(pkg))
        assert result["valid"] is True, result["violations"]
        key, field = line.group(1, 2)
        assert result["inventory"][key] == {field: 1, "names": ["shared"]}

    def test_mismatches_found_is_the_inventorys_mismatch_count(self, text: str, tmp_path: pathlib.Path) -> None:
        """#1033: the line under Exports Cross-Checked read a bare `{count}` no stage defined and no script wrote. It
        now counts the `cross_check_mismatches` entries of `{run_dir}/inventory.json`, each of which names an
        inventory entry (validate-inventory.py refuses one that does not), so the section writes no bare `{count}`."""
        section = _slice(text, "Only rendered when `references/` directory exists", "## Coherence Analysis")
        assert "{count}" not in section
        block = _fence(section, "**Mismatches Found:**")
        assert re.findall(r"^\*\*Mismatches Found:\*\*.*$", block, flags=re.MULTILINE) == [
            "**Mismatches Found:** {the number of cross_check_mismatches entries}"]
        assert ("**Mismatches Found** is the number of `cross_check_mismatches` entries in `{run_dir}/inventory.json`, "
                "one for each pair of places whose forms disagree, so an export can count more than once, and 0 when "
                "that inventory's `references` is empty, since coverage-check records no split-body gap then."
                ) in _flow(section)
        # Review of #1033: the section renders whenever references/ exists, but coverage-check §1b records the
        # entries as the section's rows only for a non-empty `references`, where `crossChecked` reads SKILL.md alone
        # (0), so the count follows the rows there.
        section1b = _flow(_slice(_read(COVERAGE_FILE), "### 1b. Cross-Check Split-Body Consistency", "### 2."))
        assert section1b.startswith("### 1b. Cross-Check Split-Body Consistency Only when the validated inventory's "
                                    "`references` is non-empty. Each `cross_check_mismatches` entry is a High "
                                    "`split-body-mismatch` gap."), section1b[:200]
        # The key the format names is the inventory's list, kept whole once each `export` names an entry.
        validator = _load("skf_validate_inventory_for_mismatch_test", TS_DIR / "scripts" / "validate-inventory.py")

        def checked(*exports: str) -> dict:
            mismatches = [{"export": export, "skill_md_line": 3 + i, "reference_file": "references/api.md",
                           "reference_line": 1, "issue": "SKILL.md shows (), references/api.md (n)"}
                          for i, export in enumerate(exports)]
            return validator.validate_inventory(json.dumps({
                "exports": [{"name": "shared", "kind": "function"}], "references": ["references/api.md"],
                "cross_check_mismatches": mismatches}))

        result = checked("shared", "shared")
        assert result["valid"] is True, result["violations"]
        assert len(result["inventory"]["cross_check_mismatches"]) == 2
        refused = checked("shared", "Widget")
        assert refused["valid"] is False and refused["inventory"] is None
        assert refused["violations"] == [
            "cross_check_mismatches[1]: `export` must name an inventory entry, by its `name` (a `method`'s bare "
            "`name`, or `{owner}.{name}` for one that gives an `owner`), not \"Widget\""]

    def test_not_cross_checked_says_why_the_count_leaves_a_mismatch_out(self, text: str,
                                                                         tmp_path: pathlib.Path) -> None:
        """#1067: on #1033's package the section showed Exports Cross-Checked 0 beside Mismatches Found 1 and said
        nothing about it, since the validator kept the mismatch with no word. A line under them now names each
        mismatch the count leaves out, and why, from `crossChecked.uncounted`, which the validator writes into
        `{run_dir}/inventory.json`, where coherence-check reads the section's figures."""
        section = _slice(text, "Only rendered when `references/` directory exists", "## Coherence Analysis")
        block = _fence(section, "**Not Cross-Checked:**")
        assert re.findall(r"^\*\*Not Cross-Checked:\*\*.*$", block, flags=re.MULTILINE) == [
            "**Not Cross-Checked:** {each crossChecked.uncounted item as `{export}` ({reference_file}): {why}, "
            "joined by \"; \"; leave this line out when there is none or Mismatches Found is 0}"]
        assert block.index("**Mismatches Found:**") < block.index("**Not Cross-Checked:**")
        assert ("**Not Cross-Checked** gives each mismatch Exports Cross-Checked does not count, from "
                "`crossChecked.uncounted`, which `scripts/validate-inventory.py` writes only when a mismatch's "
                "`export` is not among `crossChecked.names` (one written `{owner}.{name}` counts by its `method` "
                "entry's `name`): its `export`, its `reference_file` and why (its two "
                "places are in one file, a file of its pair is not one the inventory reads, or a file of its pair "
                "does not write it).") in _flow(section)
        contract = _flow(_read(REFS / "inventory-contract.md"))
        assert ("When a `cross_check_mismatches` entry's `export` is not among `names` (one written "
                "`{owner}.{name}` counts by its `method` entry's `name`), `crossChecked` also gives `uncounted`, one "
                "`{\"export\", \"reference_file\", \"why\"}` item per such entry, and the validator warns for each but "
                "never refuses the inventory for it: its two places are in one file, a file of its pair is not one it "
                "reads, or a file of its pair does not write it.") in contract
        # The contract's example lists each file its pairs name, so it teaches no pair the count leaves out.
        example = json.loads(re.search(r"```json\n(.*?)\n```", _read(REFS / "inventory-contract.md"), re.S).group(1))
        named = {e[field] for e in example["cross_check_mismatches"] for field in ("other_file", "reference_file")
                 if field in e}
        assert named <= set(example["references"]), named
        # The key and item fields the line names are the ones the validator writes, on #1033's package.
        validator = _load("skf_validate_inventory_for_uncounted_test", TS_DIR / "scripts" / "validate-inventory.py")
        pkg = tmp_path / "pkg"
        (pkg / "references").mkdir(parents=True)
        (pkg / "SKILL.md").write_text("# Demo\n\nIntro.\n\n`a(x)` runs it.\n", encoding="utf-8")
        (pkg / "references" / "api.md").write_text("# API\n\n`b(y)` runs it.\n", encoding="utf-8")
        result = validator.validate_inventory(json.dumps({
            "exports": [{"name": "a", "kind": "function"}], "references": ["references/api.md"],
            "cross_check_mismatches": [{"export": "a", "skill_md_line": 5, "reference_file": "references/api.md",
                                        "reference_line": 3, "issue": "SKILL.md shows (x), references/api.md (y)"}]}),
            str(pkg))
        assert result["valid"] is True, result["violations"]
        crossed = result["inventory"]["crossChecked"]
        assert (crossed["count"], len(result["inventory"]["cross_check_mismatches"])) == (0, 1)
        fields = re.findall(r"\{(\w+)\}", block.split("**Not Cross-Checked:**", 1)[1].splitlines()[0])
        assert [sorted(item) for item in crossed["uncounted"]] == [sorted(fields)] == [
            ["export", "reference_file", "why"]]
        assert result["warnings"] == ["cross_check_mismatches[0] (`a`): Exports Cross-Checked does not count it, "
                                      "since `references/api.md` does not write it"]


# ---------------------------------------------------------------------------
# SKILL.md and the invocation contract (#600: the headless sections live in
# references/invocation-contract.md)
# ---------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert m, f"must have a {heading} section"
    return m.group(1)


class TestStagesTable:
    @pytest.fixture
    def rows(self) -> list[str]:
        section = _section(_read(SKILL_MD), "## Stages")
        return [line for line in section.splitlines() if re.match(r"\|\s*\w+\s*\|", line) and "---" not in line]

    def test_step_4c_row(self, rows: list[str]) -> None:
        row = next(line for line in rows if re.match(r"\|\s*4c\s*\|", line))
        assert re.search(r"\|\s*4c\s*\|\s*Hard Gate\s*\|\s*references/step-hard-gate\.md\s*\|\s*Yes\s*\|", row)

    def test_step_4c_between_4b_and_5(self, rows: list[str]) -> None:
        numbers = [re.match(r"\|\s*(\w+)\s*\|", line).group(1) for line in rows]
        assert numbers.index("4b") < numbers.index("4c") < numbers.index("5")

    def test_no_stage_waits_at_a_menu(self, rows: list[str]) -> None:
        """#599: the report step's one-option [C] Finish menu is gone; the run chains to the health check."""
        assert all(re.search(r"\|\s*Yes\s*\|\s*$", row) for row in rows), rows
        assert "[C] Finish" not in _read(REPORT_FILE)


class TestExitCodes:
    @pytest.fixture
    def section(self) -> str:
        return _section(_read(CONTRACT_FILE), "## Exit Codes")

    def test_skill_md_points_at_the_contract(self) -> None:
        text = _read(SKILL_MD)
        for gone in ("## Exit Codes", "## Result Contract (Headless)", "| **Outputs** |"):
            assert gone not in text, gone
        assert "`references/invocation-contract.md`" in _section(text, "## Invocation Contract")

    def test_exit_code_2_row(self, section: str) -> None:
        row = next(line for line in section.splitlines() if re.match(r"\|\s*2\s*\|", line))
        assert "step 4c" in row and "hard-gate-blocked" in row and "step 6 publishes it as a FAIL" in row

    def test_every_verdict_exit_leaves_through_the_terminal_sequence(self, section: str) -> None:
        # report.md §4 owns the sequence; the table names the step each verdict exit leaves through.
        for code in ("0", "2", "3", "4"):
            row = next(line for line in section.splitlines() if re.match(rf"\|\s*{code}\s*\|", line))
            assert "step 6: `testResult:" in row, code
        assert "(after the result contract is written in §4c)" not in section
        sequence = _flow(_slice(_read(REPORT_FILE), "### 4. The Terminal Sequence", "### 4b."))
        assert "Every run that reaches this step, a blocked one included, ends through one sequence" in sequence
        order = ["§4b records the discovery outcome", "§4c renders the Gap Report",
                 "writes the result contract and runs the on_complete hook", "§6 presents the result",
                 "§7 releases the run lock and hands over to the health check"]
        positions = [sequence.index(needle) for needle in order]
        assert positions == sorted(positions)

    def test_the_exit_code_travels_in_the_envelope(self, section: str) -> None:
        """A skill run cannot set the agent's exit status (the W3 enhancement-1 handoff)."""
        flow = _flow(section)
        assert "A skill run cannot set the process exit status of the agent that runs it" in flow
        assert "so automators read `exit_code` from the run's own `SKF_TEST_RESULT_JSON` line." in flow
        for path in (REPORT_FILE, STEP_FILE):
            assert "process-exit" not in _read(path) and "exits with code 2" not in _read(path), path.name
        # The reason is stated once, in the Exit Codes paragraph, and no HALT promises a process exit.
        assert _read(CONTRACT_FILE).count("cannot set the process exit status") == 1
        for path in sorted(REFS.glob("*.md")) + [SKILL_MD]:
            if path != CONTRACT_FILE:
                assert "cannot set the" not in _read(path), path.name
            assert "HALT exits 1" not in _read(path) and "exits 1 and names" not in _read(path), path.name

    def test_a_run_with_no_line_did_not_finish(self, section: str) -> None:
        """The 6.0.0 gate run ended its turn with a subagent in the background: `claude -p` exited 0, no line
        was printed, and skf-test-skill-result-latest.json still held an earlier run's verdict."""
        assert ("A run that printed no envelope line has no result to read, whatever the process exit code: it was "
                "cut off, or could not write its result, and `skf-test-skill-result-latest.json` may then describe an "
                "earlier run, so it is never read in its place.") in _flow(section)
        contract = _flow(_read(CONTRACT_FILE))
        assert "or from `skf-test-skill-result-latest.json`" not in contract
        assert "never holds an earlier run's verdict" not in contract
        assert "the stable path pipeline consumers read" not in contract and "did not finish" not in contract
        assert "the record of the last run whose emitter wrote this copy, at a stable path" in contract
        records = _flow(_section(_read(CONTRACT_FILE), "## Result Files"))
        assert ("A HALT writes no result file, and neither does a run cut off before report.md §4c: the copy then "
                "still holds an earlier run's verdict.") in records


class TestResultContract:
    @pytest.fixture
    def section(self) -> str:
        return _flow(_section(_read(CONTRACT_FILE), "## Result Envelope (Headless)"))

    def test_a_blocked_run_emits_on_stderr_and_writes_its_record(self, section: str) -> None:
        assert '`"error"` with `halt_reason: "hard-gate-blocked"` for a run the hard gate blocked' in section
        assert "which still writes the Gap Report and its FAIL result contract" in section
        assert "| `hard-gate-blocked` | step 4c §3" in section
        records = _flow(_section(_read(CONTRACT_FILE), "## Result Files"))
        assert "A run the hard gate blocked writes it too, as a FAIL record" in records

    def test_the_outputs_row_names_the_ledger(self) -> None:
        row = next(line for line in _read(CONTRACT_FILE).splitlines() if line.startswith("| **Outputs** |"))
        assert "`test-findings-{run_id}.json`" in row
        assert "`.skf-test-report-{skill_name}-{run_id}.md`" in row
