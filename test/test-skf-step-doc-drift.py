"""Structural integration tests for the step-doc-drift.md step file (story 1.4).

Validates the doc-drift step contract: correct pipeline wiring, required
sections, graceful failure rules, drift report template positioning, and
stages-table placement in the AS workflow.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
AS_DIR = REPO_ROOT / "src" / "skf-audit-skill"
STEP_FILE = AS_DIR / "references" / "step-doc-drift.md"
SEVERITY_CLASSIFY_FILE = AS_DIR / "references" / "severity-classify.md"
REPORT_FILE = AS_DIR / "references" / "report.md"
SKILL_MD = AS_DIR / "SKILL.md"
DRIFT_REPORT_TEMPLATE = AS_DIR / "assets" / "drift-report-template.md"


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
    assert STEP_FILE.exists(), "step-doc-drift.md must exist"


# ---------------------------------------------------------------------------
# Pipeline chain values
# ---------------------------------------------------------------------------


class TestPipelineChain:
    def test_severity_classify_points_to_step_doc_drift(self) -> None:
        assert _next_step_value(SEVERITY_CLASSIFY_FILE) == "step-doc-drift.md"

    def test_step_doc_drift_points_to_report(self) -> None:
        assert _next_step_value(STEP_FILE) == "report.md"

    def test_report_file_exists(self) -> None:
        target = (STEP_FILE.parent / "report.md").resolve()
        assert target.exists(), "report.md must exist for the chain to complete"


# ---------------------------------------------------------------------------
# Step file structural contract
# ---------------------------------------------------------------------------


class TestStepFileStructure:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_has_step_goal_section(self, text: str) -> None:
        assert re.search(r"^##\s+STEP GOAL", text, re.MULTILINE | re.IGNORECASE)

    def test_has_rules_section(self, text: str) -> None:
        assert re.search(r"^##\s+Rules\b", text, re.MULTILINE | re.IGNORECASE)

    def test_has_mandatory_sequence_section(self, text: str) -> None:
        assert re.search(
            r"^##\s+MANDATORY SEQUENCE", text, re.MULTILINE | re.IGNORECASE
        )

    @pytest.mark.parametrize(
        "substep",
        [
            "Check for doc_sources",
            "Fetch and Hash Each Tracked Doc",
            "Build Drift Findings",
            "Append to Drift Report",
            "Store Context and Auto-Proceed",
        ],
    )
    def test_mandatory_sequence_substeps(self, text: str, substep: str) -> None:
        assert substep in text, f"MANDATORY SEQUENCE must include substep: {substep}"

    def test_graceful_failure_rule(self, text: str) -> None:
        assert "graceful" in text.lower(), (
            "step must document graceful failure behaviour"
        )

    def test_no_user_interaction_rule(self, text: str) -> None:
        assert re.search(r"auto.proceed|no user interaction", text, re.IGNORECASE), (
            "step must be auto-proceed (no user interaction)"
        )

    def test_references_doc_sources(self, text: str) -> None:
        assert "doc_sources" in text, "step must reference doc_sources from metadata"

    def test_references_content_hash(self, text: str) -> None:
        assert "content_hash" in text, "step must reference content_hash for comparison"

    def test_references_sha256_convention(self, text: str) -> None:
        assert "sha256:" in text, "step must use sha256: prefix hash convention"

    def test_references_fetch_failed_status(self, text: str) -> None:
        assert "fetch_failed" in text, "step must handle fetch_failed status"

    def test_references_null_hash_handling(self, text: str) -> None:
        assert "null" in text.lower(), "step must handle null content_hash entries"

    def test_references_doc_drift_summary(self, text: str) -> None:
        assert "doc_drift_summary" in text, (
            "step must store doc_drift_summary in workflow context"
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

    def test_step_5a_present(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|", stages_section
        ), "Stages table must include step 5a"

    def test_step_5a_name_is_doc_drift(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|\s*Doc Drift\s*\|", stages_section
        ), "Step 5a must be named 'Doc Drift'"

    def test_step_5a_file_path(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|.*references/step-doc-drift\.md", stages_section
        ), "Step 5a must reference references/step-doc-drift.md"

    def test_step_5a_between_severity_classify_and_report(
        self, stages_section: str
    ) -> None:
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
        assert "5a" in step_nums, "Step 5a must be in the stages table"
        idx_5a = step_nums.index("5a")
        idx_5 = step_nums.index("5") if "5" in step_nums else None
        idx_6 = step_nums.index("6") if "6" in step_nums else None
        assert idx_5 is not None and idx_5 < idx_5a, (
            "Step 5a must come after step 5 (Severity Classification)"
        )
        assert idx_6 is not None and idx_5a < idx_6, (
            "Step 5a must come before step 6 (Report)"
        )


# ---------------------------------------------------------------------------
# Drift report template
# ---------------------------------------------------------------------------


class TestDriftReportTemplate:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(DRIFT_REPORT_TEMPLATE)

    def test_has_documentation_drift_section(self, text: str) -> None:
        assert re.search(
            r"^## Documentation Drift", text, re.MULTILINE
        ), "drift-report-template.md must include a ## Documentation Drift section"

    def test_doc_drift_after_severity_classification(self, text: str) -> None:
        sev_idx = text.find("## Severity Classification")
        doc_idx = text.find("## Documentation Drift")
        assert sev_idx != -1, "Template must have ## Severity Classification"
        assert doc_idx != -1, "Template must have ## Documentation Drift"
        assert sev_idx < doc_idx, (
            "## Documentation Drift must come after ## Severity Classification"
        )

    def test_doc_drift_before_remediation_suggestions(self, text: str) -> None:
        doc_idx = text.find("## Documentation Drift")
        rem_idx = text.find("## Remediation Suggestions")
        assert doc_idx != -1, "Template must have ## Documentation Drift"
        assert rem_idx != -1, "Template must have ## Remediation Suggestions"
        assert doc_idx < rem_idx, (
            "## Documentation Drift must come before ## Remediation Suggestions"
        )

    def test_full_section_ordering(self, text: str) -> None:
        """All template sections must appear in the canonical order."""
        sections = [
            "## Structural Drift",
            "## Semantic Drift",
            "## Severity Classification",
            "## Documentation Drift",
            "## Remediation Suggestions",
            "## Provenance",
        ]
        indices = []
        for section in sections:
            idx = text.find(section)
            assert idx != -1, f"Template must have {section}"
            indices.append(idx)
        assert indices == sorted(indices), (
            f"Sections out of order: {sections}"
        )

    def test_doc_drift_has_step_comment(self, text: str) -> None:
        assert "step-doc-drift" in text, (
            "Documentation Drift section must reference step-doc-drift"
        )


# ---------------------------------------------------------------------------
# Step file frontmatter completeness
# ---------------------------------------------------------------------------


class TestStepFileFrontmatter:
    @pytest.fixture(scope="class")
    def fm(self) -> str:
        result = _frontmatter(STEP_FILE)
        assert result is not None, "step-doc-drift.md must have frontmatter"
        return result

    def test_has_next_step_file(self, fm: str) -> None:
        assert "nextStepFile" in fm

    def test_has_output_file(self, fm: str) -> None:
        assert "outputFile" in fm

    def test_output_file_pattern(self, fm: str) -> None:
        assert re.search(r"outputFile:.*\{forge_version\}", fm), (
            "outputFile must use {forge_version} placeholder"
        )
        assert re.search(r"outputFile:.*drift-report", fm), (
            "outputFile must reference drift-report"
        )


# ---------------------------------------------------------------------------
# Step file content contract (AC coverage)
# ---------------------------------------------------------------------------


class TestStepContentContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_step_title_format(self, text: str) -> None:
        assert re.search(
            r"^# Step 5a: Documentation Drift", text, re.MULTILINE
        ), "step must be titled '# Step 5a: Documentation Drift'"

    def test_communication_language_config(self, text: str) -> None:
        assert "{communication_language}" in text, (
            "step must include communication_language config directive"
        )

    def test_empty_array_handling(self, text: str) -> None:
        assert "empty" in text.lower(), (
            "step must document handling for empty doc_sources array"
        )

    def test_url_fetching_unavailable_fallback(self, text: str) -> None:
        assert "fetching unavailable" in text.lower() or "fetching is unavailable" in text.lower(), (
            "step must document fallback when URL fetching is unavailable"
        )

    def test_steps_completed_contract(self, text: str) -> None:
        assert re.search(r"stepsCompleted.*doc-drift", text, re.DOTALL), (
            "step must update stepsCompleted with 'doc-drift'"
        )

    def test_critical_step_completion_note(self, text: str) -> None:
        assert re.search(
            r"^##\s+CRITICAL STEP COMPLETION NOTE", text, re.MULTILINE
        ), "step must have a CRITICAL STEP COMPLETION NOTE section"

    def test_sha256_hexdigest_convention(self, text: str) -> None:
        assert "sha256:{hexdigest}" in text or "sha256:` prefix" in text or re.search(
            r"sha256:.*hexdigest", text
        ), "step must document the sha256:{hexdigest} hash convention"

    def test_doc_drift_summary_schema_fields(self, text: str) -> None:
        for field in (
            "total_tracked",
            "changed",
            "unchanged",
            "fetch_failed",
            "skipped_null_hash",
            "skipped_entirely",
        ):
            assert field in text, (
                f"doc_drift_summary must include field: {field}"
            )

    def test_no_severity_classification_of_doc_drift(self, text: str) -> None:
        assert re.search(
            r"do not classify severity|informational", text, re.IGNORECASE
        ), "step must state doc drift is informational, not severity-classified"

    def test_never_abort_pipeline_rule(self, text: str) -> None:
        assert re.search(
            r"never.*abort|must not.*block", text, re.IGNORECASE
        ), "step must have a rule against aborting the pipeline"


# ---------------------------------------------------------------------------
# Stages table auto-proceed flag
# ---------------------------------------------------------------------------


class TestStagesTableAutoProceed:
    @pytest.fixture(scope="class")
    def step_5a_row(self) -> str:
        text = _read(SKILL_MD)
        for line in text.splitlines():
            if re.search(r"\|\s*5a\s*\|", line):
                return line
        pytest.fail("Step 5a row not found in stages table")

    def test_step_5a_is_auto_proceed(self, step_5a_row: str) -> None:
        assert re.search(r"\|\s*Yes\s*\|", step_5a_row), (
            "Step 5a must be marked as auto-proceed (Yes)"
        )


# ---------------------------------------------------------------------------
# report.md integration with doc drift (AC #1, Task 5)
# ---------------------------------------------------------------------------


class TestReportDocDriftIntegration:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(REPORT_FILE)

    def test_report_references_doc_drift_summary(self, text: str) -> None:
        assert "doc_drift_summary" in text, (
            "report.md must reference doc_drift_summary from step 5a"
        )

    def test_report_mentions_doc_drift_changed(self, text: str) -> None:
        assert re.search(r"changed\s*>", text) or "Doc Drift" in text, (
            "report.md must include conditional logic for doc drift changes"
        )

    def test_report_mentions_fetch_failed(self, text: str) -> None:
        assert "fetch_failed" in text, (
            "report.md must mention fetch_failed doc URLs in summary"
        )

    def test_report_mentions_skipped_entirely(self, text: str) -> None:
        assert "skipped_entirely" in text, (
            "report.md must handle skipped_entirely case"
        )
