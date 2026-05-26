"""Structural integration tests for the step-hard-gate.md step file (story 3.1).

Validates the hard gate step contract: correct pipeline wiring, required
sections, severity-scanning behaviour, blocking/pass-through paths, headless
envelope emission, stages-table positioning, exit code documentation, and
stepsCompleted integration in report.md.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
STEP_FILE = TS_DIR / "references" / "step-hard-gate.md"
EXT_VALIDATORS_FILE = TS_DIR / "references" / "external-validators.md"
SCORE_FILE = TS_DIR / "references" / "score.md"
SKILL_MD = TS_DIR / "SKILL.md"
TEMPLATE_FILE = TS_DIR / "templates" / "test-report-template.md"
REPORT_FILE = TS_DIR / "references" / "report.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: pathlib.Path) -> str | None:
    text = _read(path)
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    return m.group(1) if m else None


def _next_step_value(path: pathlib.Path) -> str | None:
    fm = _frontmatter(path)
    if fm is None:
        return None
    m = re.search(r"^nextStepFile:\s*['\"]?([^'\"\n]+?)['\"]?\s*$", fm, re.MULTILINE)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Step file existence
# ---------------------------------------------------------------------------


def test_step_file_exists() -> None:
    assert STEP_FILE.exists(), "step-hard-gate.md must exist"


# ---------------------------------------------------------------------------
# Pipeline chain values
# ---------------------------------------------------------------------------


class TestPipelineChain:
    def test_external_validators_points_to_step_hard_gate(self) -> None:
        assert _next_step_value(EXT_VALIDATORS_FILE) == "step-hard-gate.md"

    def test_step_hard_gate_points_to_score(self) -> None:
        assert _next_step_value(STEP_FILE) == "score.md"

    def test_score_file_exists(self) -> None:
        target = (STEP_FILE.parent / "score.md").resolve()
        assert target.exists(), "score.md must exist for the chain to complete"


# ---------------------------------------------------------------------------
# Step file frontmatter
# ---------------------------------------------------------------------------


class TestStepFileFrontmatter:
    @pytest.fixture(scope="class")
    def fm(self) -> str:
        result = _frontmatter(STEP_FILE)
        assert result is not None, "step-hard-gate.md must have frontmatter"
        return result

    def test_has_next_step_file(self, fm: str) -> None:
        assert "nextStepFile" in fm

    def test_has_output_file(self, fm: str) -> None:
        assert "outputFile" in fm

    def test_output_file_pattern(self, fm: str) -> None:
        assert re.search(r"outputFile:.*\{forge_version\}", fm), (
            "outputFile must use {forge_version} placeholder"
        )


# ---------------------------------------------------------------------------
# Step file structural contract
# ---------------------------------------------------------------------------


class TestStepFileStructure:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_has_step_goal_section(self, text: str) -> None:
        assert re.search(r"^##\s+STEP GOAL", text, re.MULTILINE | re.IGNORECASE)

    def test_step_title_format(self, text: str) -> None:
        assert re.search(
            r"^# Step 4c: Hard Gate", text, re.MULTILINE
        ), "step must be titled '# Step 4c: Hard Gate'"

    def test_communication_language_config(self, text: str) -> None:
        assert "{communication_language}" in text, (
            "step must include communication_language config directive"
        )

    @pytest.mark.parametrize(
        "section",
        [
            "§1",
            "§2",
            "§3",
            "§4",
        ],
    )
    def test_numbered_sections_present(self, text: str, section: str) -> None:
        assert section in text, f"step must include section {section}"

    def test_steps_completed_contract(self, text: str) -> None:
        assert re.search(r"stepsCompleted.*hard-gate", text, re.DOTALL), (
            "step must update stepsCompleted with 'hard-gate'"
        )


# ---------------------------------------------------------------------------
# Severity scanning contract
# ---------------------------------------------------------------------------


class TestSeverityScanning:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_scans_critical_severity(self, text: str) -> None:
        assert "Critical" in text, "step must scan for Critical severity"

    def test_scans_high_severity(self, text: str) -> None:
        assert "High" in text, "step must scan for High severity"

    def test_references_severity_marker_format(self, text: str) -> None:
        assert "**Severity:**" in text, (
            "step must reference the **Severity:** marker format"
        )

    def test_scans_coverage_analysis(self, text: str) -> None:
        assert "Coverage Analysis" in text, (
            "step must scan the Coverage Analysis section"
        )

    def test_scans_coherence_analysis(self, text: str) -> None:
        assert "Coherence Analysis" in text, (
            "step must scan the Coherence Analysis section"
        )

    def test_references_gap_heading_format(self, text: str) -> None:
        assert re.search(r"GAP-\{?NNN\}?", text), (
            "step must reference the GAP-{NNN} heading format"
        )


# ---------------------------------------------------------------------------
# Block path (§3)
# ---------------------------------------------------------------------------


class TestBlockPath:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_sets_test_result_fail(self, text: str) -> None:
        assert re.search(r"testResult.*fail", text, re.IGNORECASE), (
            "block path must set testResult to 'fail'"
        )

    def test_halt_on_block(self, text: str) -> None:
        assert re.search(r"HALT", text), "block path must HALT the pipeline"

    def test_does_not_chain_on_block(self, text: str) -> None:
        assert re.search(r"do not chain", text, re.IGNORECASE), (
            "block path must not chain to nextStepFile"
        )


# ---------------------------------------------------------------------------
# Pass path (§4)
# ---------------------------------------------------------------------------


class TestPassPath:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_chains_to_next_step(self, text: str) -> None:
        assert re.search(r"\{nextStepFile\}", text), (
            "pass path must chain to {nextStepFile}"
        )

    def test_logs_finding_count(self, text: str) -> None:
        assert re.search(r"medium.*low.*info|finding", text, re.IGNORECASE), (
            "pass path must log the count of non-blocking findings"
        )


# ---------------------------------------------------------------------------
# Headless envelope
# ---------------------------------------------------------------------------


class TestHeadlessEnvelope:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_emits_skf_test_result_json(self, text: str) -> None:
        assert "SKF_TEST_RESULT_JSON" in text, (
            "step must emit SKF_TEST_RESULT_JSON envelope"
        )

    def test_emits_to_stderr(self, text: str) -> None:
        assert "stderr" in text, "headless envelope must be emitted to stderr"

    def test_envelope_has_hard_gate_blocked(self, text: str) -> None:
        assert "hard-gate-blocked" in text, (
            "headless envelope must include halt_reason: hard-gate-blocked"
        )

    def test_envelope_has_exit_code_2(self, text: str) -> None:
        assert re.search(r'"exit_code"\s*:\s*2', text), (
            "headless envelope must include exit_code: 2"
        )

    def test_envelope_has_null_score(self, text: str) -> None:
        assert re.search(r'"score"\s*:\s*null', text), (
            "headless envelope must include score: null (scoring never reached)"
        )

    def test_envelope_has_fail_verdict(self, text: str) -> None:
        assert re.search(r'"verdict"\s*:\s*"FAIL"', text), (
            "headless envelope must include verdict: FAIL"
        )

    def test_envelope_references_headless_mode(self, text: str) -> None:
        assert "{headless_mode}" in text, (
            "envelope emission must be conditional on {headless_mode}"
        )


# ---------------------------------------------------------------------------
# Stages table in SKILL.md
# ---------------------------------------------------------------------------


class TestStagesTable:
    @pytest.fixture(scope="class")
    def stages_section(self) -> str:
        text = _read(SKILL_MD)
        m = re.search(
            r"^## Stages\b(.*?)(?=^## )", text, flags=re.MULTILINE | re.DOTALL
        )
        assert m, "SKILL.md must have a ## Stages section"
        return m.group(1)

    def test_step_4c_present(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*4c\s*\|", stages_section
        ), "Stages table must include step 4c"

    def test_step_4c_name_is_hard_gate(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*4c\s*\|\s*Hard Gate\s*\|", stages_section
        ), "Step 4c must be named 'Hard Gate'"

    def test_step_4c_file_path(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*4c\s*\|.*references/step-hard-gate\.md", stages_section
        ), "Step 4c must reference references/step-hard-gate.md"

    def test_step_4c_between_4b_and_5(self, stages_section: str) -> None:
        rows = [
            line.strip()
            for line in stages_section.splitlines()
            if line.strip().startswith("|") and not line.strip().startswith("|-")
        ]
        step_nums = []
        for row in rows:
            m = re.match(r"\|\s*(\w+)\s*\|", row)
            if m and m.group(1) not in ("#", "---"):
                step_nums.append(m.group(1))
        assert "4c" in step_nums, "Step 4c must be in the stages table"
        idx_4c = step_nums.index("4c")
        idx_4b = step_nums.index("4b") if "4b" in step_nums else None
        idx_5 = step_nums.index("5") if "5" in step_nums else None
        assert idx_4b is not None and idx_4b < idx_4c, (
            "Step 4c must come after step 4b (External Validators)"
        )
        assert idx_5 is not None and idx_4c < idx_5, (
            "Step 4c must come before step 5 (Score)"
        )

    def test_step_4c_is_auto_proceed(self, stages_section: str) -> None:
        for line in stages_section.splitlines():
            if re.search(r"\|\s*4c\s*\|", line):
                assert re.search(r"\|\s*Yes\s*\|", line), (
                    "Step 4c must be marked as auto-proceed (Yes)"
                )
                return
        pytest.fail("Step 4c row not found in stages table")


# ---------------------------------------------------------------------------
# Exit codes in SKILL.md
# ---------------------------------------------------------------------------


class TestExitCodes:
    @pytest.fixture(scope="class")
    def exit_codes_section(self) -> str:
        text = _read(SKILL_MD)
        m = re.search(
            r"^## Exit Codes\b(.*?)(?=^## )", text, flags=re.MULTILINE | re.DOTALL
        )
        assert m, "SKILL.md must have an ## Exit Codes section"
        return m.group(1)

    def test_exit_code_2_references_step_4c(self, exit_codes_section: str) -> None:
        for line in exit_codes_section.splitlines():
            if re.match(r"\|\s*2\s*\|", line):
                assert "4c" in line, (
                    "Exit code 2 row must reference step 4c"
                )
                return
        pytest.fail("Exit code 2 row not found in Exit Codes table")

    def test_exit_code_2_mentions_hard_gate(self, exit_codes_section: str) -> None:
        for line in exit_codes_section.splitlines():
            if re.match(r"\|\s*2\s*\|", line):
                assert "hard-gate-blocked" in line, (
                    "Exit code 2 row must mention hard-gate-blocked"
                )
                return
        pytest.fail("Exit code 2 row not found in Exit Codes table")


# ---------------------------------------------------------------------------
# Result Contract in SKILL.md — halt_reason enum
# ---------------------------------------------------------------------------


class TestResultContract:
    @pytest.fixture(scope="class")
    def result_section(self) -> str:
        text = _read(SKILL_MD)
        m = re.search(
            r"^## Result Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert m, "SKILL.md must have a ## Result Contract section"
        return m.group(1)

    def test_halt_reason_includes_hard_gate_blocked(
        self, result_section: str
    ) -> None:
        assert "hard-gate-blocked" in result_section, (
            "Result Contract halt_reason enum must include hard-gate-blocked"
        )


# ---------------------------------------------------------------------------
# Test report template — anchor comment mentions hard gate
# ---------------------------------------------------------------------------


class TestReportTemplateAnchor:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(TEMPLATE_FILE)

    def test_anchor_comment_mentions_hard_gate(self, text: str) -> None:
        assert "hard gate" in text.lower() or "step-hard-gate" in text, (
            "test-report-template.md anchor comment must mention the hard gate"
        )

    def test_no_hard_gate_report_section(self, text: str) -> None:
        assert not re.search(
            r"^## Hard Gate", text, re.MULTILINE
        ), "hard gate does NOT produce a report section — no ## Hard Gate anchor"


# ---------------------------------------------------------------------------
# report.md stepsCompleted canonical chain
# ---------------------------------------------------------------------------


class TestReportStepsCompleted:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_canonical_chain_includes_hard_gate(self, text: str) -> None:
        assert "'hard-gate'" in text or '"hard-gate"' in text, (
            "report.md canonical stepsCompleted chain must include 'hard-gate'"
        )

    def test_hard_gate_between_external_validators_and_score(
        self, text: str
    ) -> None:
        ev_idx = text.find("external-validators")
        hg_idx = text.find("hard-gate")
        sc_idx = text.find("'score'") if "'score'" in text else text.find('"score"')
        assert ev_idx != -1, "canonical chain must include external-validators"
        assert hg_idx != -1, "canonical chain must include hard-gate"
        assert sc_idx != -1, "canonical chain must include score"
        assert ev_idx < hg_idx < sc_idx, (
            "hard-gate must appear between external-validators and score in the canonical chain"
        )
