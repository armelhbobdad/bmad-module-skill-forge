"""Structural integration tests for per-pipeline quality thresholds (story 3.2).

Validates the per-pipeline threshold lookup table in init.md §1b, the
four-layer threshold resolution precedence in score.md §1, threshold source
logging in score.md §6/§7, pipeline_alias forwarding in the forger, and
pipeline-contracts.md documentation.  Also confirms hard-gate independence
(AC #4): step-hard-gate.md has no threshold-driven logic.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
INIT_FILE = TS_DIR / "references" / "init.md"
SCORE_FILE = TS_DIR / "references" / "score.md"
HARD_GATE_FILE = TS_DIR / "references" / "step-hard-gate.md"
SKILL_MD = TS_DIR / "SKILL.md"
CUSTOMIZE_TOML = TS_DIR / "customize.toml"
FORGER_MD = REPO_ROOT / "src" / "skf-forger" / "SKILL.md"
PIPELINE_CONTRACTS = REPO_ROOT / "src" / "shared" / "references" / "pipeline-contracts.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# init.md §1b — Per-Pipeline Threshold Lookup Table
# ---------------------------------------------------------------------------


class TestInitPipelineThresholdSection:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

    def test_section_1b_exists(self, text: str) -> None:
        assert re.search(r"###?\s+1b\.", text), (
            "init.md must have a §1b section for per-pipeline threshold resolution"
        )

    def test_section_1b_title(self, text: str) -> None:
        assert re.search(
            r"Resolve Per-Pipeline Quality Threshold", text
        ), "§1b must be titled 'Resolve Per-Pipeline Quality Threshold'"

    def test_pipeline_alias_variable_referenced(self, text: str) -> None:
        assert "{pipeline_alias}" in text, (
            "§1b must reference {pipeline_alias} variable"
        )

    def test_pipeline_default_threshold_variable_set(self, text: str) -> None:
        assert "{pipeline_default_threshold}" in text, (
            "§1b must set {pipeline_default_threshold} variable"
        )

    @pytest.mark.parametrize(
        "alias,threshold",
        [
            ("deepwiki", "90"),
            ("forge", "80"),
            ("forge-quick", "80"),
            ("campaign", "90"),
        ],
    )
    def test_lookup_table_entry(self, text: str, alias: str, threshold: str) -> None:
        assert re.search(
            rf"\|\s*`{alias}`\s*\|\s*{threshold}\s*\|", text
        ), f"§1b lookup table must map {alias} → {threshold}"

    def test_lookup_table_has_header(self, text: str) -> None:
        assert re.search(
            r"\|\s*Pipeline Alias\s*\|\s*Default Threshold\s*\|", text
        ), "§1b lookup table must have Pipeline Alias / Default Threshold headers"

    def test_alias_present_and_found_path(self, text: str) -> None:
        assert re.search(
            r"present AND found in the table.*pipeline_default_threshold",
            text,
            re.DOTALL,
        ), "§1b must document the path where alias is present and found"

    def test_alias_present_but_not_found_path(self, text: str) -> None:
        assert re.search(
            r"present but NOT in the table.*remains unset", text, re.DOTALL
        ), "§1b must document the path where alias is present but not found"

    def test_alias_absent_path(self, text: str) -> None:
        assert re.search(
            r"pipeline_alias.*absent.*remains unset", text, re.DOTALL | re.IGNORECASE
        ), "§1b must document the path where pipeline_alias is absent"

    def test_section_1b_before_section_2(self, text: str) -> None:
        idx_1b = text.find("### 1b.")
        idx_2 = text.find("### 2.")
        assert idx_1b != -1 and idx_2 != -1 and idx_1b < idx_2, (
            "§1b must appear between §1 and §2 in init.md"
        )

    def test_references_score_md(self, text: str) -> None:
        assert re.search(r"score\.md", text), (
            "§1b must reference score.md as the consumer of pipeline_default_threshold"
        )


# ---------------------------------------------------------------------------
# score.md §1 — Four-Layer Threshold Precedence
# ---------------------------------------------------------------------------


class TestScoreThresholdPrecedence:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_precedence_header_mentions_pipeline_default(self, text: str) -> None:
        assert re.search(
            r"CLI\s*>\s*pipeline default\s*>\s*scalar\s*>\s*bundled fallback",
            text,
        ), "score.md §1 precedence header must list all four layers in order"

    def test_layer_1_cli_override(self, text: str) -> None:
        assert re.search(
            r"1\.\s+.*--threshold=<N>.*CLI wins", text
        ), "score.md must document layer 1: CLI override"

    def test_layer_2_pipeline_default(self, text: str) -> None:
        assert re.search(
            r"2\.\s+.*pipeline_default_threshold.*init\.md §1b", text, re.DOTALL
        ), "score.md must document layer 2: pipeline default from init.md §1b"

    def test_layer_3_workflow_scalar(self, text: str) -> None:
        assert re.search(
            r"3\.\s+.*defaultThreshold.*workflow.*scalar", text, re.DOTALL
        ), "score.md must document layer 3: workflow default scalar"

    def test_layer_4_bundled_fallback(self, text: str) -> None:
        assert re.search(
            r"4\.\s+.*fall back to.*80", text
        ), "score.md must document layer 4: bundled fallback 80"


# ---------------------------------------------------------------------------
# score.md §1 — Threshold Source Logging
# ---------------------------------------------------------------------------


class TestScoreThresholdSourceLogging:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_threshold_source_variable_set(self, text: str) -> None:
        assert "threshold_source" in text, (
            "score.md must set threshold_source variable"
        )

    def test_cli_override_source_format(self, text: str) -> None:
        assert re.search(r'CLI override', text), (
            "threshold_source for CLI must include 'CLI override'"
        )

    def test_pipeline_default_source_format(self, text: str) -> None:
        assert re.search(r'pipeline default', text), (
            "threshold_source for pipeline must include 'pipeline default'"
        )

    def test_workflow_default_source_format(self, text: str) -> None:
        assert re.search(r'workflow default', text), (
            "threshold_source for scalar must include 'workflow default'"
        )

    def test_bundled_fallback_source_format(self, text: str) -> None:
        assert re.search(r'bundled fallback', text), (
            "threshold_source for fallback must include 'bundled fallback'"
        )

    def test_threshold_source_stored_in_workflow_context(self, text: str) -> None:
        assert re.search(
            r"Store.*threshold_source.*workflow context", text, re.IGNORECASE
        ), "score.md must instruct storing threshold_source in workflow context"


# ---------------------------------------------------------------------------
# score.md §6 — Threshold Source in Report Output
# ---------------------------------------------------------------------------


class TestScoreReportOutput:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_threshold_source_in_completeness_score_section(self, text: str) -> None:
        score_section = text[text.find("## Completeness Score"):]
        assert "**Threshold Source:**" in score_section, (
            "Completeness Score section must include **Threshold Source:** line"
        )

    def test_threshold_source_line_format(self, text: str) -> None:
        assert re.search(
            r"\*\*Threshold Source:\*\*\s*\{threshold_source\}", text
        ), "Threshold Source line must use {threshold_source} variable"


# ---------------------------------------------------------------------------
# score.md §7 — thresholdSource in Output Frontmatter
# ---------------------------------------------------------------------------


class TestScoreFrontmatter:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SCORE_FILE)

    def test_threshold_source_in_frontmatter(self, text: str) -> None:
        assert re.search(
            r"thresholdSource:.*threshold_source", text
        ), "score.md §7 frontmatter must include thresholdSource field"

    def test_threshold_source_after_threshold_before_confidence(
        self, text: str
    ) -> None:
        fm_section = text[text.find("### 7. Update Output Frontmatter"):]
        threshold_idx = fm_section.find("threshold:")
        ts_idx = fm_section.find("thresholdSource:")
        confidence_idx = fm_section.find("analysisConfidence:")
        assert threshold_idx < ts_idx < confidence_idx, (
            "thresholdSource must appear after threshold and before analysisConfidence"
        )


# ---------------------------------------------------------------------------
# SKILL.md — Invocation Contract references per-pipeline defaults
# ---------------------------------------------------------------------------


class TestSkillMdInvocationContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SKILL_MD)

    def test_threshold_flag_references_per_pipeline_defaults(self, text: str) -> None:
        invocation_match = re.search(
            r"## Invocation Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert invocation_match, "SKILL.md must have an Invocation Contract section"
        section = invocation_match.group(1)
        assert "per-pipeline defaults" in section, (
            "Invocation Contract --threshold description must reference per-pipeline defaults"
        )


class TestSkillMdOnActivation:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(SKILL_MD)

    def test_default_threshold_references_per_pipeline(self, text: str) -> None:
        activation_match = re.search(
            r"## On Activation\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert activation_match, "SKILL.md must have an On Activation section"
        section = activation_match.group(1)
        assert re.search(
            r"per-pipeline defaults.*init\.md §1b", section
        ), (
            "On Activation §3 {defaultThreshold} description must reference "
            "per-pipeline defaults from init.md §1b"
        )


# ---------------------------------------------------------------------------
# customize.toml — default_threshold comment references full precedence
# ---------------------------------------------------------------------------


class TestCustomizeTomlPrecedence:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(CUSTOMIZE_TOML)

    def test_comment_references_per_pipeline(self, text: str) -> None:
        assert "per-pipeline" in text, (
            "customize.toml default_threshold comment must reference per-pipeline defaults"
        )

    def test_comment_references_init_md_1b(self, text: str) -> None:
        assert "init.md §1b" in text, (
            "customize.toml must reference init.md §1b lookup table"
        )

    def test_full_precedence_chain_in_comment(self, text: str) -> None:
        assert re.search(
            r"CLI.*per-pipeline.*scalar.*fallback", text, re.DOTALL
        ), "customize.toml comment must document full precedence chain"

    def test_default_threshold_value_unchanged(self, text: str) -> None:
        assert re.search(
            r"^default_threshold\s*=\s*80\s*$", text, re.MULTILINE
        ), "default_threshold value must remain 80"


# ---------------------------------------------------------------------------
# Forger SKILL.md — Pipeline Mode §4.c forwards pipeline_alias
# ---------------------------------------------------------------------------


class TestForgerPipelineAlias:
    @pytest.fixture(scope="class")
    def pipeline_section(self) -> str:
        text = _read(FORGER_MD)
        m = re.search(
            r"## Pipeline Mode\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert m, "Forger SKILL.md must have a Pipeline Mode section"
        return m.group(1)

    def test_step_4c_mentions_pipeline_alias(self, pipeline_section: str) -> None:
        assert "{pipeline_alias}" in pipeline_section, (
            "Pipeline Mode §4.c must set {pipeline_alias} in workflow data context"
        )

    def test_step_4c_lists_alias_names(self, pipeline_section: str) -> None:
        for alias in ("deepwiki", "forge", "forge-quick", "onboard", "maintain"):
            assert alias in pipeline_section, (
                f"Pipeline Mode §4.c must list '{alias}' as a possible alias value"
            )

    def test_null_for_ad_hoc(self, pipeline_section: str) -> None:
        assert re.search(
            r"null.*ad-hoc", pipeline_section, re.IGNORECASE
        ), "Pipeline Mode §4.c must specify null for ad-hoc sequences"


# ---------------------------------------------------------------------------
# pipeline-contracts.md — pipeline_alias in Pipeline State
# ---------------------------------------------------------------------------


class TestPipelineContractsPipelineAlias:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(PIPELINE_CONTRACTS)

    def test_pipeline_state_has_alias_field(self, text: str) -> None:
        state_match = re.search(
            r"## Pipeline State\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert state_match, "pipeline-contracts.md must have a Pipeline State section"
        section = state_match.group(1)
        assert "pipeline_alias" in section, (
            "Pipeline State must document pipeline_alias in data context"
        )

    def test_pipeline_alias_top_level(self, text: str) -> None:
        assert re.search(r"alias:.*pipeline alias", text, re.IGNORECASE), (
            "Pipeline State must include alias at top level of pipeline state"
        )

    def test_pipeline_alias_in_data_context(self, text: str) -> None:
        assert re.search(
            r"data:.*pipeline_alias:", text, re.DOTALL
        ), "Pipeline State must include pipeline_alias in the data sub-object"

    def test_pipeline_alias_references_init_1b(self, text: str) -> None:
        assert re.search(r"init\.md §1b", text), (
            "pipeline-contracts.md must reference init.md §1b for threshold lookup"
        )


class TestPipelineContractsCircuitBreakers:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(PIPELINE_CONTRACTS)

    def test_ts_circuit_breaker_references_per_pipeline(self, text: str) -> None:
        cb_match = re.search(
            r"## Circuit Breakers\b(.*?)(?=^## |\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert cb_match, "pipeline-contracts.md must have a Circuit Breakers section"
        section = cb_match.group(1)
        assert re.search(r"per-pipeline defaults", section), (
            "TS circuit breaker row must reference per-pipeline defaults"
        )


# ---------------------------------------------------------------------------
# Hard Gate Independence (AC #4)
# ---------------------------------------------------------------------------


class TestHardGateIndependence:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(HARD_GATE_FILE)

    def test_no_threshold_logic(self, text: str) -> None:
        threshold_refs = [
            (i + 1, line)
            for i, line in enumerate(text.splitlines())
            if "threshold" in line.lower()
            and "null" not in line.lower()
        ]
        assert not threshold_refs, (
            f"step-hard-gate.md must not contain threshold logic "
            f"(found at lines: {[r[0] for r in threshold_refs]})"
        )

    def test_no_pipeline_default_threshold(self, text: str) -> None:
        assert "pipeline_default_threshold" not in text, (
            "step-hard-gate.md must not reference pipeline_default_threshold"
        )

    def test_no_effective_threshold(self, text: str) -> None:
        assert "effective_threshold" not in text, (
            "step-hard-gate.md must not reference effective_threshold"
        )

    def test_no_threshold_source(self, text: str) -> None:
        assert "threshold_source" not in text, (
            "step-hard-gate.md must not reference threshold_source"
        )

    def test_severity_based_only(self, text: str) -> None:
        assert "Critical" in text and "High" in text, (
            "step-hard-gate.md must be severity-based (Critical/High), not threshold-based"
        )


# ---------------------------------------------------------------------------
# Cross-File Consistency
# ---------------------------------------------------------------------------


class TestCrossFileConsistency:
    def test_init_threshold_flag_references_1b(self) -> None:
        text = _read(INIT_FILE)
        threshold_line = [
            line for line in text.splitlines() if "--threshold" in line
        ]
        assert any("§1b" in line for line in threshold_line), (
            "init.md --threshold flag description must reference §1b"
        )

    def test_init_threshold_flag_references_per_pipeline(self) -> None:
        text = _read(INIT_FILE)
        threshold_line = [
            line for line in text.splitlines() if "--threshold" in line
        ]
        assert any("per-pipeline" in line for line in threshold_line), (
            "init.md --threshold flag description must reference per-pipeline defaults"
        )

    def test_deepwiki_alias_threshold_matches_lookup_table(self) -> None:
        forger_text = _read(FORGER_MD)
        assert re.search(r"TS\[min:90\]", forger_text), (
            "deepwiki alias expansion must include TS[min:90]"
        )
        init_text = _read(INIT_FILE)
        assert re.search(r"\|\s*`deepwiki`\s*\|\s*90\s*\|", init_text), (
            "init.md lookup table must map deepwiki → 90 matching the forger alias"
        )

    def test_forge_alias_has_no_min_override(self) -> None:
        contracts_text = _read(PIPELINE_CONTRACTS)
        forge_match = re.search(
            r"\|\s*`forge`\s*\|([^|]+)\|", contracts_text
        )
        assert forge_match, "forge alias must exist in the pipeline alias table"
        expansion = forge_match.group(1)
        assert "min:" not in expansion, (
            "forge alias expansion must not include min: override (relies on pipeline default)"
        )

    def test_score_md_references_init_md_1b(self) -> None:
        score_text = _read(SCORE_FILE)
        assert "init.md §1b" in score_text, (
            "score.md must reference init.md §1b as the source of pipeline_default_threshold"
        )

    def test_score_md_mentions_pipeline_alias(self) -> None:
        score_text = _read(SCORE_FILE)
        assert "{pipeline_alias}" in score_text, (
            "score.md must reference {pipeline_alias} in the pipeline default layer"
        )
