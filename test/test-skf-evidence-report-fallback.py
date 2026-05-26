"""Structural integration tests for threshold fallback evidence report (story 3.3).

Validates the §4b fallback logic in score.md, evidence report path in the
architecture spec, INCONCLUSIVE guard clause, 80% floor constant, fallback
fields in output frontmatter (§7), fallback notice in score report (§8),
SKILL.md outputs mention of the evidence report, result contract fallback
fields in report.md, and report.md §6 fallback notice block.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
SCORE_FILE = TS_DIR / "references" / "score.md"
REPORT_FILE = TS_DIR / "references" / "report.md"
SKILL_MD = TS_DIR / "SKILL.md"
PIPELINE_CONTRACTS = REPO_ROOT / "src" / "shared" / "references" / "pipeline-contracts.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# score.md §4b — Threshold Fallback Section Exists
# ---------------------------------------------------------------------------


class TestScoreFallbackSection:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_section_4b_exists(self, text: str) -> None:
        assert re.search(r"###?\s+4b\.", text), (
            "score.md must have a §4b section for threshold fallback"
        )

    def test_section_4b_between_4_and_5(self, text: str) -> None:
        idx_4 = text.find("### 4. Determine Result")
        idx_4b = text.find("### 4b.")
        idx_5 = text.find("### 5. Determine Next Workflow Recommendation")
        assert idx_4 != -1 and idx_4b != -1 and idx_5 != -1, (
            "score.md must have §4, §4b, and §5 sections"
        )
        assert idx_4 < idx_4b < idx_5, (
            "§4b must appear between §4 and §5 in score.md"
        )


# ---------------------------------------------------------------------------
# score.md §4b — Fallback Trigger Conditions
# ---------------------------------------------------------------------------


class TestFallbackTriggerConditions:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_fail_condition(self, text: str) -> None:
        assert re.search(r'result\s*==\s*"FAIL"', text), (
            "§4b must check result == FAIL as a trigger condition"
        )

    def test_score_gte_80(self, text: str) -> None:
        assert re.search(r"totalScore\s*>=\s*80", text), (
            "§4b must check totalScore >= 80 as a trigger condition"
        )

    def test_threshold_gt_80(self, text: str) -> None:
        assert re.search(r"effective_threshold\s*>\s*80", text), (
            "§4b must check effective_threshold > 80 as a trigger condition"
        )


# ---------------------------------------------------------------------------
# score.md §4b — INCONCLUSIVE Guard Clause
# ---------------------------------------------------------------------------


class TestInconclusiveGuard:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_inconclusive_not_triggered(self, text: str) -> None:
        section_4b = text[text.find("### 4b."):]
        section_5 = text[text.find("### 5."):]
        fallback_section = text[text.find("### 4b."):text.find("### 5.")]
        assert "INCONCLUSIVE" in fallback_section, (
            "§4b must explicitly mention INCONCLUSIVE as a non-trigger condition"
        )


# ---------------------------------------------------------------------------
# score.md §4b — 80% Floor Constant
# ---------------------------------------------------------------------------


class TestFloorConstant:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_80_floor_present(self, fallback_section: str) -> None:
        assert "80" in fallback_section, (
            "§4b must reference the 80% floor constant"
        )

    def test_override_result_to_pass(self, fallback_section: str) -> None:
        assert re.search(r'result.*"PASS"', fallback_section), (
            "§4b must override result to PASS on fallback"
        )


# ---------------------------------------------------------------------------
# score.md §4b — Evidence Report Path
# ---------------------------------------------------------------------------


class TestEvidenceReportPath:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_evidence_report_path(self, fallback_section: str) -> None:
        assert "evidence-report-fallback.md" in fallback_section, (
            "§4b must reference evidence-report-fallback.md output path"
        )

    def test_forge_version_prefix(self, fallback_section: str) -> None:
        assert re.search(
            r"\{forge_version\}/evidence-report-fallback\.md", fallback_section
        ), "Evidence report must be under {forge_version}/"


# ---------------------------------------------------------------------------
# score.md §6 — Threshold Fallback Line in Completeness Score
# ---------------------------------------------------------------------------


class TestScoreSection6Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_threshold_fallback_line_in_section_6(self, text: str) -> None:
        score_section = text[text.find("### 6. Append Completeness Score"):]
        assert "**Threshold Fallback:**" in score_section, (
            "§6 must include a **Threshold Fallback:** line when fallback is active"
        )

    def test_fallback_line_after_threshold_source(self, text: str) -> None:
        score_section = text[text.find("### 6. Append Completeness Score"):]
        ts_idx = score_section.find("**Threshold Source:**")
        fb_idx = score_section.find("**Threshold Fallback:**")
        assert ts_idx != -1 and fb_idx != -1 and ts_idx < fb_idx, (
            "**Threshold Fallback:** must appear after **Threshold Source:**"
        )


# ---------------------------------------------------------------------------
# score.md §7 — Fallback Fields in Output Frontmatter
# ---------------------------------------------------------------------------


class TestScoreSection7Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_threshold_fallback_in_frontmatter(self, text: str) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):]
        assert "thresholdFallback" in fm_section, (
            "§7 must include thresholdFallback field in output frontmatter"
        )

    def test_original_threshold_in_frontmatter(self, text: str) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):]
        assert "originalThreshold" in fm_section, (
            "§7 must include originalThreshold field in output frontmatter"
        )

    def test_evidence_report_path_in_frontmatter(self, text: str) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):]
        assert "evidenceReportPath" in fm_section, (
            "§7 must include evidenceReportPath field in output frontmatter"
        )


# ---------------------------------------------------------------------------
# score.md §8 — Fallback Notice in Score Report
# ---------------------------------------------------------------------------


class TestScoreSection8Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_fallback_notice_in_report(self, text: str) -> None:
        report_section = text[text.find("### 8. Report Score"):]
        assert "**Threshold fallback:**" in report_section, (
            "§8 must include a threshold fallback notice in the pipeline output"
        )

    def test_fallback_notice_includes_evidence_path(self, text: str) -> None:
        report_section = text[text.find("### 8. Report Score"):]
        assert re.search(
            r"Evidence report:.*evidence_report_path", report_section
        ), "§8 fallback notice must include the evidence report path"


# ---------------------------------------------------------------------------
# SKILL.md — Outputs Mention Evidence Report
# ---------------------------------------------------------------------------


class TestSkillMdOutputs:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SKILL_MD)

    def test_outputs_mention_evidence_report(self, text: str) -> None:
        invocation_match = re.search(
            r"## Invocation Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert invocation_match, "SKILL.md must have an Invocation Contract section"
        section = invocation_match.group(1)
        assert "evidence-report-fallback.md" in section, (
            "Invocation Contract Outputs must mention evidence-report-fallback.md"
        )


# ---------------------------------------------------------------------------
# SKILL.md — Result Contract Includes Fallback Fields
# ---------------------------------------------------------------------------


class TestSkillMdResultContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SKILL_MD)

    def test_result_contract_threshold_fallback(self, text: str) -> None:
        rc_match = re.search(
            r"## Result Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert rc_match, "SKILL.md must have a Result Contract section"
        section = rc_match.group(1)
        assert "threshold_fallback" in section, (
            "Result Contract must include threshold_fallback field"
        )

    def test_result_contract_original_threshold(self, text: str) -> None:
        rc_match = re.search(
            r"## Result Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert rc_match
        section = rc_match.group(1)
        assert "original_threshold" in section, (
            "Result Contract must include original_threshold field"
        )

    def test_result_contract_evidence_report_path(self, text: str) -> None:
        rc_match = re.search(
            r"## Result Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert rc_match
        section = rc_match.group(1)
        assert "evidence_report_path" in section, (
            "Result Contract must include evidence_report_path field"
        )


# ---------------------------------------------------------------------------
# report.md §6 — Fallback Notice in Final Presentation
# ---------------------------------------------------------------------------


class TestReportSection6Fallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_fallback_notice_in_presentation(self, text: str) -> None:
        presentation_match = re.search(
            r"### 6\. Present Final Report\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert presentation_match, "report.md must have a §6 Present Final Report section"
        section = presentation_match.group(1)
        assert "thresholdFallback" in section, (
            "report.md §6 must reference thresholdFallback from output frontmatter"
        )

    def test_fallback_notice_includes_evidence_path(self, text: str) -> None:
        presentation_match = re.search(
            r"### 6\. Present Final Report\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert presentation_match
        section = presentation_match.group(1)
        assert "evidenceReportPath" in section, (
            "report.md §6 fallback notice must include evidenceReportPath"
        )


# ---------------------------------------------------------------------------
# report.md §4c — Result Contract Includes Fallback Fields
# ---------------------------------------------------------------------------


class TestReportResultContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_result_contract_threshold_fallback(self, text: str) -> None:
        contract_match = re.search(
            r"### 4c\. Result Contract\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert contract_match, "report.md must have a §4c Result Contract section"
        section = contract_match.group(1)
        assert "threshold_fallback" in section, (
            "report.md §4c must include threshold_fallback in result contract"
        )

    def test_result_contract_original_threshold(self, text: str) -> None:
        contract_match = re.search(
            r"### 4c\. Result Contract\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert contract_match
        section = contract_match.group(1)
        assert "original_threshold" in section, (
            "report.md §4c must include original_threshold in result contract"
        )

    def test_result_contract_evidence_report_path(self, text: str) -> None:
        contract_match = re.search(
            r"### 4c\. Result Contract\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert contract_match
        section = contract_match.group(1)
        assert "evidence_report_path" in section, (
            "report.md §4c must include evidence_report_path in result contract"
        )


# ---------------------------------------------------------------------------
# pipeline-contracts.md — Circuit Breaker Fallback Note
# ---------------------------------------------------------------------------


class TestPipelineContractsFallback:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(PIPELINE_CONTRACTS)

    def test_ts_circuit_breaker_mentions_fallback(self, text: str) -> None:
        cb_match = re.search(
            r"## Circuit Breakers\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert cb_match, "pipeline-contracts.md must have a Circuit Breakers section"
        section = cb_match.group(1)
        assert "fallback" in section.lower(), (
            "TS circuit breaker must mention fallback behavior for scores between 80% and threshold"
        )

    def test_ts_circuit_breaker_80_floor(self, text: str) -> None:
        cb_match = re.search(
            r"## Circuit Breakers\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert cb_match
        section = cb_match.group(1)
        assert "80%" in section, (
            "TS circuit breaker must reference the 80% floor in the halt condition"
        )


# ---------------------------------------------------------------------------
# score.md §4b.1 — Evidence Report Subsection Exists
# ---------------------------------------------------------------------------


class TestEvidenceReportSubsection:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_section_4b1_exists(self, fallback_section: str) -> None:
        assert re.search(r"####?\s+4b\.1", fallback_section), (
            "score.md must have a §4b.1 subsection for evidence report generation"
        )


# ---------------------------------------------------------------------------
# score.md §4b.1 — Evidence Report Template Structure
# ---------------------------------------------------------------------------


class TestEvidenceReportTemplateStructure:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_template_has_threshold_summary(self, fallback_section: str) -> None:
        assert "## Threshold Summary" in fallback_section, (
            "Evidence report template must include '## Threshold Summary' heading"
        )

    def test_template_has_findings_heading(self, fallback_section: str) -> None:
        assert "## Findings Preventing Higher Threshold" in fallback_section, (
            "Evidence report template must include '## Findings Preventing Higher Threshold' heading"
        )

    def test_template_has_remediation_context(self, fallback_section: str) -> None:
        assert "## Remediation Context" in fallback_section, (
            "Evidence report template must include '## Remediation Context' heading"
        )

    def test_template_has_conclusion(self, fallback_section: str) -> None:
        assert "## Conclusion" in fallback_section, (
            "Evidence report template must include '## Conclusion' heading"
        )


# ---------------------------------------------------------------------------
# score.md §4b.1 — Evidence Report Template Data Fields
# ---------------------------------------------------------------------------


class TestEvidenceReportTemplateFields:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_template_references_skill_name(self, fallback_section: str) -> None:
        assert "{skill_name}" in fallback_section, (
            "Evidence report template must reference {skill_name}"
        )

    def test_template_references_run_id(self, fallback_section: str) -> None:
        assert "{run_id}" in fallback_section, (
            "Evidence report template must reference {run_id}"
        )

    def test_template_references_original_threshold(self, fallback_section: str) -> None:
        assert "{original_threshold}" in fallback_section, (
            "Evidence report template must reference {original_threshold}"
        )

    def test_template_references_total_score(self, fallback_section: str) -> None:
        assert "{totalScore}" in fallback_section, (
            "Evidence report template must reference {totalScore}"
        )

    def test_template_references_threshold_source(self, fallback_section: str) -> None:
        assert "{threshold_source}" in fallback_section, (
            "Evidence report template must reference {threshold_source}"
        )


# ---------------------------------------------------------------------------
# score.md §4b — Prior Remediation and Post-Score Cap Context
# ---------------------------------------------------------------------------


class TestEvidenceReportRemediationContext:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_prior_test_report_check(self, fallback_section: str) -> None:
        assert "prior test report" in fallback_section.lower() or "prior remediation" in fallback_section.lower(), (
            "§4b must document checking for a prior test report to detect remediation cycles"
        )

    def test_post_score_cap_context(self, fallback_section: str) -> None:
        assert "cap" in fallback_section.lower(), (
            "§4b must reference post-score cap interaction in evidence report context"
        )


# ---------------------------------------------------------------------------
# score.md §4b — Workflow Context Variable Recording
# ---------------------------------------------------------------------------


class TestFallbackWorkflowContext:
    @pytest.fixture(scope="class")
    def fallback_section(self) -> str:
        text = _read(SCORE_FILE)
        start = text.find("### 4b.")
        end = text.find("### 5.")
        return text[start:end]

    def test_records_threshold_fallback(self, fallback_section: str) -> None:
        assert "threshold_fallback: true" in fallback_section, (
            "§4b must document recording threshold_fallback: true in workflow context"
        )

    def test_records_original_threshold(self, fallback_section: str) -> None:
        assert "original_threshold" in fallback_section, (
            "§4b must document recording original_threshold in workflow context"
        )

    def test_records_fallback_threshold_80(self, fallback_section: str) -> None:
        assert "fallback_threshold: 80" in fallback_section, (
            "§4b must document recording fallback_threshold: 80 in workflow context"
        )

    def test_records_evidence_report_path(self, fallback_section: str) -> None:
        assert "evidence_report_path" in fallback_section, (
            "§4b must document recording evidence_report_path in workflow context"
        )


# ---------------------------------------------------------------------------
# SKILL.md — Fallback Fields Omitted (Not False/Null) When No Fallback
# ---------------------------------------------------------------------------


class TestSkillMdAbsentSemantics:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SKILL_MD)

    def test_headless_envelope_omits_when_no_fallback(self, text: str) -> None:
        rc_match = re.search(
            r"## Result Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert rc_match, "SKILL.md must have a Result Contract section"
        section = rc_match.group(1)
        assert "omit" in section.lower(), (
            "Result Contract must state that fallback fields are omitted when no fallback occurred"
        )


# ---------------------------------------------------------------------------
# report.md §4c — Fallback Fields Absent (Not False/Null) When No Fallback
# ---------------------------------------------------------------------------


class TestReportAbsentSemantics:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_result_contract_absent_not_false(self, text: str) -> None:
        contract_match = re.search(
            r"### 4c\. Result Contract\b(.*?)(?=^### |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert contract_match, "report.md must have a §4c Result Contract section"
        section = contract_match.group(1)
        assert "absent" in section.lower(), (
            "report.md §4c must state that fallback fields are absent (not false/null) when no fallback occurred"
        )
