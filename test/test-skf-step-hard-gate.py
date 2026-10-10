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
  (#583's decision); one the source still declares outside the surface is
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
  (#600), and every HALT names its halt_reason and phase (#593, #594).
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
        call = _ledger_call(COVERAGE_FILE, "--from coverage", keep=("--surface",))
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
        assert "never holds an earlier run's verdict" in contract
        # build-result-context.py's table is the one home of the exit codes: the report step restates none.
        assert _load("skf_build_result_context_gate", BUILD_CONTEXT).VERDICTS["fail"][2] == 2
        assert "{headless_exit_code}" not in text and "The Exit Code" not in text
        assert "→ exit code" not in text

    def test_the_blocked_envelope_is_the_gates(self, tmp_path: pathlib.Path) -> None:
        """The report step's payload for a blocked run is the hard gate's own, built by the script."""
        assert "SKF_TEST_RESULT_JSON: {" not in _read(REPORT_FILE), "no envelope literal is typed"
        report = tmp_path / f"test-report-demo-{RUN_ID}.md"
        report.write_bytes(f"---\nskillName: 'demo'\nrunId: '{RUN_ID}'\nhardGate: 'blocked'\n"
                           "testResult: 'fail'\ntestMode: 'naive'\n---\n# R\n".encode("utf-8"))
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
        # #695: a tier A glob that matches no file narrows nothing, so the guard counts only the ones that match
        assert (f"{criterion} more than 25% and the brief has no `scope.tier_a_include` glob that matches a file"
                in drift)
        rows = {c: text for _, c, text in _severity_rows()}
        assert "the brief has no `scope.tier_a_include` glob that matches a file" in rows["denominator-inflation"]
        assert ("or a `scope.tier_a_include` glob matches no file in the source tested, so it counts no name"
                in rows["brief-scope-stale"])
        loader = _load("skf_load_coverage_inputs_for_step_test", TS_DIR / "scripts" / "load-coverage-inputs.py")
        assert loader.DEFLATION_PCT == 25
        protocol = _read(REFS / "source-access-protocol.md")
        assert f"{criterion} more than `guards.thresholds.deflationPct` percent" in protocol
        assert "more than 25%" not in protocol

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
            ("Info", "provenance-unverified", "Provenance line not verified for fetch", "src/api.py:40", "fetch")]

    def test_a_split_body_gap_cites_a_line_inside_the_package(self) -> None:
        section = _flow(_slice(_read(COVERAGE_FILE), "### 1b. Cross-Check", "### 2. Analyze"))
        assert "(`{reference_file}:{reference_line}`), inside the skill package" in section

    def test_each_per_export_record_names_its_export(self) -> None:
        """The hand-written split-body record and the script's per-export records name the export in
        `export` and in the title."""
        text = _flow(_body(COVERAGE_FILE))
        assert "titled `Split-body mismatch: {export}`, with its `export`" in text
        assert "titled `Signature mismatch: {name}`, with `export` `{name}`" in text
        assert "§1b's split-body mismatches, in the Ledger Record Format" in text
        assert "each naming its export in `export` and in its title" in text
        records = gap_ledger.from_coverage(
            {"branch": "enumerated", "missing": ["fetchData", "Options"], "stale": ["ghost", "old"]},
            signatures={"missingTypes": ["Options"]},
            stale=[{"name": "ghost", "fabricated": True, "source": "src/a.ts:3"}])
        records += gap_ledger.from_provenance_line({"stale": [
            {"export_name": n, "source_file": "a.py", "source_line": 1, "reason": "line-not-definition",
             "definition_lines": lines} for n, lines in (("f", [2]), ("g", []))]})
        assert {r["category"] for r in records} == {"missing-export", "missing-type", "fabricated-signature",
                                                    "stale-documentation", "provenance-line",
                                                    "provenance-unverified"}
        for record in records:
            assert record["export"] and record["title"].endswith(record["export"]), record

    def test_inflated_names_become_missing_exports_update_skill_can_route(self, values: dict[str, str],
                                                                          tmp_path: pathlib.Path) -> None:
        text = _flow(_body(COVERAGE_FILE))
        assert "its `absent[]` names replace this gap, one each" in text
        # §5b keeps `--provenance` whenever the map is bound, though no run file holds it: the absent names'
        # Source comes from it, and update-skill takes that line as its `source_citation`.
        assert ("leaving out a bracketed flag whose file does not exist: a run file this run did not write, "
                "or `--provenance` when init.md §2 bound no `{forge_provenance_map}`:") in text
        run = tmp_path / "run"
        _write_json(run / "coverage.json", {"branch": "scalar", "denominator": 4, "documented": 2,
                                            "missing": [], "missingCount": 2, "numeratorSource": "verified"})
        _write_json(run / "numerator.json", {"inflated": True, "declared": 4, "verified": 2,
                                             "absent": ["alpha", "beta"]})
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
        section = _flow(_slice(_read(COVERAGE_FILE), "### 4b. Metadata", "**The numerator ground truth"))
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
    folder right below the package root is never walked."""

    CALL = ('uv run {verifyProvenanceCompletenessHelper} classify-stale --names "{run_dir}/coverage.json" '
            '--provenance "{forge_provenance_map}" --source-root "{source_path}" '
            '--inventory "{run_dir}/inventory.json" -o "{run_dir}/stale.json"')
    SOURCE = '"""Core."""\nimport os\n\n\ndef helper(x):\n    return os.fspath(x)\n'

    @pytest.fixture
    def section(self) -> str:
        text = _read(COVERAGE_FILE)
        return text[text.index("- **Stale names**"):text.index("### 4. Category Scores")]

    def test_the_call_is_fenced_with_its_probe_order(self, section: str) -> None:
        assert self.CALL in _fence(section, self.CALL)
        assert _frontmatter(COVERAGE_FILE)["verifyProvenanceCompletenessProbeOrder"][-1] == \
            "{project-root}/src/shared/scripts/skf-verify-provenance-completeness.py"

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
            "citations on lines naming it cite exactly one, is a documented extra: an Info `observation` gap at "
            "that declaration, when `surface.json` has an `extraction` and its `excluded.outsideScope` does not "
            "list the name",
            "(no `defined_at` and no single cited declaring file, one scoped out, no `extraction`, a dotted name,",
        ):
            assert needle in flow, needle

    def _classify(self, tmp_path: pathlib.Path, files: dict[str, str], stale: list[str],
                  entries: list[dict], kinds: dict[str, str] | None = None) -> list[dict]:
        """The classify-stale call as §2c writes it, over `files` below the source root, with §1a's
        `inventory.json` giving each name of `kinds` its kind."""
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_bytes(text.encode("utf-8"))
        run = tmp_path / "run"
        _write_json(run / "coverage.json", {"branch": "enumerated", "missing": [], "stale": stale})
        _write_json(run / "inventory.json", {"exports": [{"name": n, "kind": k} for n, k in (kinds or {}).items()],
                                             "references": [], "cross_check_mismatches": []})
        provenance = _write_json(tmp_path / "provenance-map.json", {"entries": entries})
        call = self.CALL.replace("uv run {verifyProvenanceCompletenessHelper} ", "")
        for key, value in {"{run_dir}": run.as_posix(), "{forge_provenance_map}": provenance.as_posix(),
                           "{source_path}": tmp_path.as_posix()}.items():
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
            "**Publish the report.**",
            'mv "{report_file}" "{publishedReportFile}"',
            '--output "{run_dir}/result-context.json"',
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
        flow = _flow(check)
        assert "Count them with grep, not by eye" in flow
        assert "Each heading must print 1" in flow and "`placeholders` must print 0" in flow
        assert 'HALT (`halt_reason: "report-anchor-missing"`, phase `report:anchors`)' in check

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
        assert "read `exit_code` from the `SKF_TEST_RESULT_JSON` line or from `skf-test-skill-result-latest.json`" in flow
        for path in (REPORT_FILE, STEP_FILE):
            assert "process-exit" not in _read(path) and "exits with code 2" not in _read(path), path.name
        # The reason is stated once, in the Exit Codes paragraph, and no HALT promises a process exit.
        assert _read(CONTRACT_FILE).count("cannot set the process exit status") == 1
        for path in sorted(REFS.glob("*.md")) + [SKILL_MD]:
            if path != CONTRACT_FILE:
                assert "cannot set the" not in _read(path), path.name
            assert "HALT exits 1" not in _read(path) and "exits 1 and names" not in _read(path), path.name


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
