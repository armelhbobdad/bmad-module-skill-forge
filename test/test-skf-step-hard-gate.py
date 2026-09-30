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
- a stale name is a fabricated signature only when the line check the
  documented definition-lines call runs finds no such name in the file the
  skill cites (#583's decision), and each per-export record names its
  export;
- a blocked run is not a halt: it writes the Completeness Score section in
  scoring's place and ends through the report step, which renders the Gap
  Report, writes the FAIL result contract, runs on_complete and dispatches
  the health check before exit 2 (#583 item 2, the architecture-2 handoff);
- the Gap Severity table carries the re-rated rows (#583, #545, #543), every
  category is one gap-ledger.py knows, and every severity and category the
  stage prose writes is a row of the table;
- report.md runs its step and section checks before it writes the result
  contract and runs on_complete, with 'report' out of the expected set and
  recorded once the result files are written, and its grep count catches a
  stage that skipped its section (#585, #583 item 4);
- every discovery skip is a counted Info gap, and discovery gaps reach the
  Gap Report totals (#543);
- each stage's closing line names its stepsCompleted token (#585).
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
VERIFY_PROVENANCE = REPO_ROOT / "src" / "shared" / "scripts" / "skf-verify-provenance-completeness.py"

LEDGER_BINDING = "{forge_version}/test-findings-{run_id}.json"
GATE_CMD = (
    'uv run {hardGateScript} check --ledger "{ledgerFile}" --skill-name "{skill_name}" '
    '--report-path "{outputFile}" --require-stage coverage-check --require-stage coherence-check '
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
        "{outputFile}": (forge_version / f"test-report-demo-{RUN_ID}.md").as_posix(),
    }


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
    assert fm["outputFile"] == "{forge_version}/test-report-{skill_name}-{run_id}.md"
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
        rule = "Every HALT in this step releases the run lock first (SKILL.md Workflow Rules)"
        assert rule in body
        assert body.index(rule) < body.index("HALT with")


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
        assert '"halt_reason":"step-completeness-violation"' in section
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
        assert out["envelope"] == hard_gate.blocked_envelope("demo", values["{outputFile}"])

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

    def test_two_missing_names_from_one_file_are_two_records(self, values: dict[str, str]) -> None:
        """§2c titles a missing name after it and sets `export`, so two names of one file never merge."""
        section = _flow(_slice(_read(COVERAGE_FILE), "**Classify what the script found.**", "### 3. Build"))
        title = re.search(r"`missing-export` gap titled `([^`]+)`", section).group(1)
        assert title == "Missing export: {name}" and "with `export` `{name}`" in section
        out = _record("coverage-check", [
            _gap("Medium", "missing-export", title.format(name=name), "src/index.ts", export=name)
            for name in ("alpha", "beta")
        ], values)
        assert (out["appended"], out["duplicates"], out["record_count"]) == (["GAP-001", "GAP-002"], [], 2)

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
        for field in ("`hardGate: 'blocked'`", "`testResult: 'fail'`", "`nextWorkflow: 'update-skill'`",
                      "Append `'hard-gate'` to `stepsCompleted`"):
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

    def test_names_update_skill_from_test_report(self, block: str) -> None:
        assert "`@Ferris US {skill_name} --from-test-report`" in block

    def test_report_step_publishes_a_blocked_run(self) -> None:
        text = _read(REPORT_FILE)
        collect = _flow(_slice(text, "### 1. Collect All Issues", "### 2."))
        assert "`hardGate: 'blocked'`" in collect and "skips discovery testing (§4b)" in collect
        contract = _flow(_slice(text, "### 4c. Result Contract", "### 5."))
        assert "A run the hard gate blocked was never scored: its expected set ends at `'hard-gate'`" in contract
        assert "the line that discovery testing did not run" in contract
        for field in ('`status: "error"`', '`verdict: "FAIL"`', '`exit_code: 2`',
                      '`halt_reason: "hard-gate-blocked"`', '`next_workflow: "update-skill"`'):
            assert field in contract, field
        assert "never an earlier run's verdict" in contract
        exit_code = _slice(text, "### 6b.", "### 6c.")
        assert "`testResult: 'fail'` → exit code 2, a run the hard gate blocked included" in exit_code

    def test_the_blocked_envelope_is_the_gates(self) -> None:
        section = _slice(_read(REPORT_FILE), "### 6c.", "### 7.")
        blocked = section[section.index("**A run the hard gate blocked**"):]
        assert "**stderr**" in blocked
        line = next(line for line in blocked.splitlines() if line.startswith("SKF_TEST_RESULT_JSON: "))
        envelope = json.loads(line.split(": ", 1)[1])
        assert envelope == hard_gate.blocked_envelope("{skill_name}", "{outputFile}")

    def test_the_health_check_runs_for_a_blocked_run(self) -> None:
        """§7 dispatches it (or skips it under --no-health-check) and records healthCheckDispatched."""
        text = _read(REPORT_FILE)
        sequence = _flow(_slice(text, "### 4. The Terminal Sequence", "### 4b."))
        assert "a blocked one included" in sequence
        assert "§7 hands over to the health check and releases the run lock" in sequence
        section7 = _flow(_slice(text, "### 7. Health-Check Dispatch", "load and execute `{nextStepFile}`"))
        for needle in ("`--no-health-check` flag bypass", "`healthCheckDispatched: false`",
                       "`healthCheckDispatched` field of the result contract"):
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
        criterion = "the re-derived source barrel exceeds `effective_denominator` by"
        drift = next(text for s, c, text in _severity_rows() if c == "metadata-drift")
        assert f"{criterion} more than 25% and the brief has no `scope.tier_a_include`" in drift
        assert f"If {criterion} **more than 25%**" in _read(REFS / "source-access-protocol.md")

    @pytest.mark.parametrize("path", [COVERAGE_FILE, COHERENCE_FILE, EXT_VALIDATORS_FILE, REPORT_FILE],
                             ids=lambda p: p.stem)
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
        text = _flow(_body(COVERAGE_FILE))
        for needle in ("High `split-body-mismatch` gap", "High `numerator-inflation` gap",
                       "Medium `metadata-drift` gap", "Info `multi-denominator` gap",
                       "Low `provenance-line` gap", "Info `provenance-unverified` gap"):
            assert needle in text, needle
        for stale in ("gap list (built in section 5)", "feed into the gap report (step 6)"):
            assert stale not in text, stale
        # update-skill's rule R5 reads the provenance line gap by this title and Source.
        assert "`Provenance line is not the definition of {export_name}`" in text
        assert "- **Source:** `{source_file}:{source_line}`" in _read(COVERAGE_FILE)

    def test_a_split_body_gap_cites_a_line_inside_the_package(self) -> None:
        section = _flow(_slice(_read(COVERAGE_FILE), "### 1b. Cross-Check", "### 2. Analyze"))
        assert "(`{reference_file}:{reference_line}`), inside the skill package" in section

    def test_each_per_export_record_names_its_export(self) -> None:
        text = _flow(_body(COVERAGE_FILE))
        rule = text[text.index("A record about one export ("):]
        listed = set(re.findall(r"`([a-z-]+)`", rule[:rule.index(")")]))
        assert listed == {"missing-export", "missing-type", "signature-mismatch", "fabricated-signature",
                          "stale-documentation", "split-body-mismatch", "provenance-line", "provenance-unverified"}
        assert "names it in `export` and in its title" in rule
        for needle in ("titled `Split-body mismatch: {export}`, with its `export`",
                       "titled `Signature mismatch: {name}`, with `export` `{name}`",
                       "titled `Missing export: {name}`", "titled `Missing type: {name}`",
                       "titled `Fabricated signature: {name}`, with `export` `{name}`",
                       "titled `Stale documentation: {name}`, with `export` `{name}`",
                       "with the same Source and `export`"):
            assert needle in text, needle
        assert "- **Export:** `{export_name}`" in _read(COVERAGE_FILE)

    def test_inflated_names_become_missing_exports_update_skill_can_route(self) -> None:
        text = _flow(_body(COVERAGE_FILE))
        assert "its `absent[]` names replace this gap (§4b)" in text
        assert ("record each `absent[]` name in its place, as a Medium `missing-export` gap titled "
                "`Missing export: {name}` with `export` `{name}`") in text

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
    stratified tier_a set also is, so §2c checks the cited line with the verifier."""

    CALL = ('uv run {verifyProvenanceCompletenessHelper} definition-lines --source-root "{source_path}" '
            '--file "{source_file}" --name "{name}" --line {source_line} [--export-type "{export_type}"]')
    SOURCE = '"""Core."""\nimport os\n\n\ndef helper(x):\n    return os.fspath(x)\n'

    @pytest.fixture
    def section(self) -> str:
        text = _read(COVERAGE_FILE)
        return text[text.index("- **Stale names**"):text.index("### 3. Build Coverage Results")]

    def test_the_call_is_fenced_with_its_probe_order(self, section: str) -> None:
        assert self.CALL in _fence(section, self.CALL)
        assert _frontmatter(COVERAGE_FILE)["verifyProvenanceCompletenessProbeOrder"][-1] == \
            "{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py"

    def test_fabricated_needs_a_cited_file_without_the_name(self, section: str) -> None:
        flow = _flow(section)
        for needle in (
            "Forge, Forge+ or Deep tier, `analysis_confidence` `full`, `allow_workspace_drift` not true",
            "When every entry's `line_check` is `file-missing`, or `checked` with an empty `definition_lines`",
            "a Critical `fabricated-signature` gap titled `Fabricated signature: {name}`",
            "a Medium `stale-documentation` gap titled `Stale documentation: {name}`",
            "or a cited file that defines the name",
        ):
            assert needle in flow, needle

    @pytest.mark.parametrize("name, cited_file, fabricated", [
        ("ghost_fn", "pkg/core.py", True),
        ("helper", "pkg/core.py", False),
        ("ghost_fn", "pkg/gone.py", True),
    ], ids=["no-such-name", "defined-outside-the-barrel", "file-missing"])
    def test_the_documented_call_decides(self, tmp_path: pathlib.Path, name: str, cited_file: str,
                                         fabricated: bool) -> None:
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "core.py").write_bytes(self.SOURCE.encode("utf-8"))
        # The call as §2c writes it, without the optional --export-type group.
        call = self.CALL.split(" [--export-type")[0].replace("uv run {verifyProvenanceCompletenessHelper} ", "")
        for key, value in {"{source_path}": tmp_path.as_posix(), "{source_file}": cited_file, "{name}": name,
                           "{source_line}": "5"}.items():
            call = call.replace(key, value)
        proc = subprocess.run([sys.executable, str(VERIFY_PROVENANCE), *shlex.split(call)],
                              capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        decided = out["line_check"] == "file-missing" or (
            out["line_check"] == "checked" and out["definition_lines"] == [])
        assert decided is fabricated, out


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
        assert "Once both result files are written, append `'report'` to `stepsCompleted`" in _flow(contract)

    def test_render_and_checks_come_before_the_writes_and_the_hook(self, text: str) -> None:
        order = [
            "--stage report <<'SKF_GAPS'",  # §4b.5 records discovery
            'render --ledger "{ledgerFile}" --heading',
            'summary --ledger "{ledgerFile}"',
            "**Enforce step completeness.**",
            "**Check the report sections.**",
            "**Renew the run lock**",
            "write --target {forge_version}/skf-test-skill-result-{run_id}.json",
            "write --target {forge_version}/skf-test-skill-result-latest.json",
            "Once both result files are written, append `'report'`",
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
        flow = _flow(check)
        assert "Count them with grep, not by eye" in flow
        assert "Each heading must print 1" in flow and "`placeholders` must print 0" in flow
        assert '"halt_reason":"report-anchor-missing"' in check

    @pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="runs the check through bash")
    @pytest.mark.parametrize("case", ["whole", "skipped", "appended"])
    def test_the_section_check_counts_as_written(self, text: str, tmp_path: pathlib.Path, case: str) -> None:
        script = _fence(_slice(text, "**Check the report sections.**", "**Renew the run lock**"), "for heading in")
        report = _read(TEMPLATE_FILE)
        for placeholder in re.findall(r"^<!-- Populated by .*-->$", report, re.M):
            if case == "whole" or "coverage-check" not in placeholder:
                report = report.replace(placeholder, "Written by its stage.")
        if case == "appended":
            report += "\n## Coverage Analysis\n\nAppended instead of written in place.\n"
        path = tmp_path / f"test-report-demo-{RUN_ID}.md"
        path.write_bytes(report.encode("utf-8"))
        proc = subprocess.run(["bash", "-c", script.replace("{outputFile}", path.as_posix())],
                              capture_output=True, text=True, encoding="utf-8")
        counts = {k: int(v) for k, v in (line.rsplit(": ", 1) for line in proc.stdout.splitlines())}
        expected = dict.fromkeys(TEMPLATE_HEADINGS, 1) | {"placeholders": 0}
        if case == "skipped":
            expected["placeholders"] = 1
        if case == "appended":
            expected |= {"## Coverage Analysis": 2, "placeholders": 1}
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

    def test_counts_come_from_the_ledger(self, text: str) -> None:
        contract = _flow(_slice(text, "### 4c. Result Contract", "### 5."))
        assert "Bind `{gap_counts}` ← `counts`, `{total_gaps}` ← `total` and `{blocking_gaps}` ← `blocking`" in contract
        assert "`summary.gapCounts`" in contract
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
            f"| Critical | 1 | {gap_ledger.EFFORT['Critical']} |",
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


# ---------------------------------------------------------------------------
# SKILL.md contract
# ---------------------------------------------------------------------------


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}[^\n]*\n(.*?)(?=^## )", text, flags=re.MULTILINE | re.DOTALL)
    assert m, f"SKILL.md must have a {heading} section"
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


class TestExitCodes:
    @pytest.fixture
    def section(self) -> str:
        return _section(_read(SKILL_MD), "## Exit Codes")

    def test_exit_code_2_row(self, section: str) -> None:
        row = next(line for line in section.splitlines() if re.match(r"\|\s*2\s*\|", line))
        assert "step 4c" in row and "hard-gate-blocked" in row and "step 6 publishes it as a FAIL" in row

    def test_every_verdict_exit_leaves_through_the_terminal_sequence(self, section: str) -> None:
        # report.md §4 owns the sequence; the table names the step each verdict exit leaves through.
        for code in ("0", "2", "3", "4"):
            row = next(line for line in section.splitlines() if re.match(rf"\|\s*{code}\s*\|", line))
            assert "step 6 §6b" in row, code
        assert "(after the result contract is written in §4c)" not in section
        sequence = _flow(_slice(_read(REPORT_FILE), "### 4. The Terminal Sequence", "### 4b."))
        assert "Every run that reaches this step, a blocked one included, ends through one sequence" in sequence
        order = ["§4b records the discovery outcome", "§4c renders the Gap Report",
                 "writes the result contract and runs the on_complete hook", "§6 presents the result",
                 "§7 hands over to the health check"]
        positions = [sequence.index(needle) for needle in order]
        assert positions == sorted(positions)


class TestResultContract:
    @pytest.fixture
    def section(self) -> str:
        return _flow(_section(_read(SKILL_MD), "## Result Contract (Headless)"))

    def test_a_blocked_run_emits_on_stderr_and_writes_its_record(self, section: str) -> None:
        assert 'on **stderr** with `status: "error"` and `halt_reason: "hard-gate-blocked"` for a run the hard gate blocked' in section
        assert "A run the hard gate blocked writes it too, as a FAIL record" in section
        assert '`"hard-gate-blocked"` (a run the step 4c hard gate blocked)' in section

    def test_the_outputs_row_names_the_ledger(self) -> None:
        row = next(line for line in _read(SKILL_MD).splitlines() if line.startswith("| **Outputs** |"))
        assert "`test-findings-{run_id}.json`" in row
