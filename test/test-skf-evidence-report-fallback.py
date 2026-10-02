"""Structural integration tests for threshold fallback evidence report (story 3.3).

Validates the threshold fallback compute-score.py applies and the score.md
§4b fields that read it (the prose restates no trigger), evidence report path in the
architecture spec, INCONCLUSIVE guard clause, 80% floor constant, fallback
fields in output frontmatter (§7), fallback notice in score report (§8),
the invocation contract's outputs mention of the evidence report (lifted
out of SKILL.md, #600), the result contract fallback fields, which
build-result-context.py writes for report.md §4c (present only when the
fallback fired, #593), and report.md §6 fallback notice block.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
SCORE_FILE = TS_DIR / "references" / "score.md"
REPORT_FILE = TS_DIR / "references" / "report.md"
SKILL_MD = TS_DIR / "SKILL.md"
CONTRACT_FILE = TS_DIR / "references" / "invocation-contract.md"
BUILD_CONTEXT = TS_DIR / "scripts" / "build-result-context.py"
GAP_LEDGER = TS_DIR / "scripts" / "gap-ledger.py"
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
# Fallback trigger conditions: compute-score.py holds them, score.md reads them
# ---------------------------------------------------------------------------


def _compute_score():
    spec = importlib.util.spec_from_file_location("compute_score_fallback", TS_DIR / "scripts" / "compute-score.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestFallbackTriggerConditions:
    """An uncapped FAIL scoring 80 or more against a threshold above 80 passes
    at the 80 floor. compute-score.py is the one home of the rule."""

    @staticmethod
    def _score(total: float, threshold: float) -> dict:
        categories = ("exportCoverage", "signatureAccuracy", "typeCoverage", "coherence", "externalValidation")
        return _compute_score().compute_score({"mode": "contextual", "tier": "Deep", "threshold": threshold,
                                               "toolingStatus": "ok",
                                               "scores": {c: total for c in categories}})

    def test_fail_condition(self) -> None:
        out = self._score(95, 90)
        assert out["result"] == "PASS" and "thresholdFallback" not in out, "a PASS never falls back"

    def test_score_gte_80(self) -> None:
        fired = self._score(85, 90)
        assert (fired["result"], fired["effectiveResult"], fired["thresholdFallback"]) == ("FAIL", "PASS", True)
        assert fired["originalThreshold"] == 90
        assert "thresholdFallback" not in self._score(79, 90), "below the floor the FAIL stands"

    def test_threshold_gt_80(self) -> None:
        out = self._score(85, 80)
        assert out["result"] == "PASS" and "thresholdFallback" not in out, "at 80 the score passes outright"
        assert _compute_score().FALLBACK_FLOOR == 80

    def test_score_md_reads_the_fields_and_restates_no_rule(self) -> None:
        text = _read(SCORE_FILE)
        section = text[text.find("### 4b."):text.find("### 5.")]
        for field in ("thresholdFallback", "effectiveResult", "originalThreshold"):
            assert field in section, field
        for restated in ("totalScore >= 80", "effective_threshold > 80", 'result == "FAIL"'):
            assert restated not in section, restated


# ---------------------------------------------------------------------------
# score.md §4b — INCONCLUSIVE Guard Clause
# ---------------------------------------------------------------------------


class TestInconclusiveGuard:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_inconclusive_not_triggered(self, text: str) -> None:
        # §4 settles the verdict the §4b fallback reads: INCONCLUSIVE is never overridden.
        verdict_sections = text[text.find("### 4. Determine Result"):text.find("### 5.")]
        assert "INCONCLUSIVE" in verdict_sections and "never overridden" in verdict_sections, (
            "§4 must say INCONCLUSIVE is never overridden by the fallback"
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
        assert re.search(r'effectiveResult.*"PASS"', fallback_section), (
            "§4b must read the script's PASS from effectiveResult on fallback"
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
        score_section = text[text.find("### 6. Write the Completeness Score Section"):]
        assert "**Threshold Fallback:**" in score_section, (
            "§6 must include a **Threshold Fallback:** line when fallback is active"
        )

    def test_fallback_line_after_threshold_source(self, text: str) -> None:
        score_section = text[text.find("### 6. Write the Completeness Score Section"):]
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
# invocation-contract.md: Outputs Mention Evidence Report
# ---------------------------------------------------------------------------


def _contract_section(heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", _read(CONTRACT_FILE),
                  flags=re.MULTILINE | re.DOTALL)
    assert m, f"invocation-contract.md must have a {heading} section"
    return m.group(1)


class TestContractOutputs:
    def test_outputs_mention_evidence_report(self) -> None:
        section = _contract_section("## Invocation Contract")
        assert "evidence-report-fallback.md" in section, (
            "Invocation Contract Outputs must mention evidence-report-fallback.md"
        )

    def test_skill_md_points_at_the_contract(self) -> None:
        text = _read(SKILL_MD)
        assert "## Result Contract" not in text and "`references/invocation-contract.md`" in text


# ---------------------------------------------------------------------------
# invocation-contract.md: Result Contract Includes Fallback Fields
# ---------------------------------------------------------------------------


class TestContractFallbackFields:
    @pytest.fixture
    def section(self) -> str:
        return _contract_section("## Result Envelope (Headless)") + _contract_section("## Result Files")

    @pytest.mark.parametrize("field", ["threshold_fallback", "original_threshold", "evidence_report_path"])
    def test_result_contract_names_the_field(self, section: str, field: str) -> None:
        assert field in section, f"the result contract must include {field}"


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
# report.md §4c: the result contract's fallback fields come from the script
# ---------------------------------------------------------------------------


def _build(tmp_path: pathlib.Path, fallback: bool) -> dict:
    """Run build-result-context.py on a scored report, with or without a fallback."""
    lines = ["---", "skillName: 'demo'", "runId: '20260101T000000Z-ab12cd34'", "testMode: 'naive'",
             "hardGate: 'passed'", "testResult: 'pass'", "score: '84.5%'"]
    if fallback:
        lines += ["threshold: '80%'", "thresholdFallback: true", "originalThreshold: '90%'",
                  "evidenceReportPath: 'forge/demo/1.0.0/evidence-report-fallback.md'"]
    else:
        lines += ["threshold: '80%'"]
    report = tmp_path / "test-report-demo-20260101T000000Z-ab12cd34.md"
    report.write_bytes(("\n".join(lines + ["---", "# Report", ""])).encode("utf-8"))
    ledger = tmp_path / "test-findings-20260101T000000Z-ab12cd34.json"
    subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage", "coverage-check"],
                   input="[]", capture_output=True, text=True, encoding="utf-8", check=True)
    score = tmp_path / "score.json"
    score.write_bytes(json.dumps({"activeCategories": ["exportCoverage", "externalValidation"]}).encode("utf-8"))
    out = tmp_path / "result-context.json"
    proc = subprocess.run([sys.executable, str(BUILD_CONTEXT), "--report", str(report), "--ledger", str(ledger),
                           "--score", str(score), "--output", str(out)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(out.read_text(encoding="utf-8"))


class TestReportResultContract:
    def test_report_builds_the_contract_with_the_script(self) -> None:
        contract_match = re.search(
            r"### 4c\. Result Contract\b(.*?)(?=^### |\Z)",
            _read(REPORT_FILE),
            flags=re.MULTILINE | re.DOTALL,
        )
        assert contract_match, "report.md must have a §4c Result Contract section"
        section = contract_match.group(1)
        assert "uv run {resultContextScript}" in section
        assert "emit --workflow skf-test-skill" in section

    def test_a_fallback_records_its_three_fields(self, tmp_path: pathlib.Path) -> None:
        payload = _build(tmp_path, fallback=True)
        assert (payload["threshold_fallback"], payload["original_threshold"]) == (True, 90)
        summary = payload["result_contract"]["summary"]
        assert (summary["threshold_fallback"], summary["original_threshold"]) == (True, 90)
        assert summary["evidence_report_path"] == "forge/demo/1.0.0/evidence-report-fallback.md"
        assert payload["threshold"] == 80, "the threshold the verdict was settled against"


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
        # The cap interaction is stated once, in §3d, which §4b's fallback follows.
        text = _read(SCORE_FILE)
        caps = text[text.find("### 3d."):text.find("### 4.")]
        assert "a capped run stays FAIL whatever the threshold" in caps, (
            "§3d must say a capped run never falls back"
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
# The contract: Fallback Fields Omitted (Not False/Null) When No Fallback
# ---------------------------------------------------------------------------


class TestContractAbsentSemantics:
    def test_headless_envelope_omits_when_no_fallback(self) -> None:
        section = _contract_section("## Result Envelope (Headless)")
        assert "appear only when the threshold fallback fired" in section, (
            "the contract must state that fallback fields are omitted when no fallback occurred"
        )


# ---------------------------------------------------------------------------
# build-result-context.py: Fallback Fields Absent (Not False/Null) When No Fallback
# ---------------------------------------------------------------------------


class TestReportAbsentSemantics:
    def test_result_contract_absent_not_false(self, tmp_path: pathlib.Path) -> None:
        payload = _build(tmp_path, fallback=False)
        for record in (payload, payload["result_contract"], payload["result_contract"]["summary"]):
            for field in ("threshold_fallback", "original_threshold", "evidence_report_path"):
                assert field not in record, field
