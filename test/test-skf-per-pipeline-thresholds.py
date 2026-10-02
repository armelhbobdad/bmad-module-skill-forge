"""Structural integration tests for per-pipeline quality thresholds (story 3.2).

Validates the per-pipeline threshold lookup table in init.md §1b, the
four-layer threshold resolution precedence, resolved once in init.md §1b and
written into the report frontmatter, which score.md §1 reads back (#587:
later steps read the verdict inputs from the frontmatter), threshold source
logging in score.md §6, pipeline_alias forwarding in the forger, and
pipeline-contracts.md documentation.  Also confirms hard-gate independence
(AC #4): step-hard-gate.md has no threshold-driven logic.

The alias gates come from parse-pipeline.py's ALIASES, the table the forger
runs, not from a prose copy of it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TS_DIR = REPO_ROOT / "src" / "skf-test-skill"
INIT_FILE = TS_DIR / "references" / "init.md"
SCORE_FILE = TS_DIR / "references" / "score.md"
HARD_GATE_FILE = TS_DIR / "references" / "step-hard-gate.md"
SKILL_MD = TS_DIR / "SKILL.md"
CONTRACT_FILE = TS_DIR / "references" / "invocation-contract.md"
CUSTOMIZE_TOML = TS_DIR / "customize.toml"
FORGER_MD = REPO_ROOT / "src" / "skf-forger" / "SKILL.md"
PIPELINE_CONTRACTS = REPO_ROOT / "src" / "shared" / "references" / "pipeline-contracts.md"
PIPELINE_MODE = REPO_ROOT / "src" / "skf-forger" / "references" / "pipeline-mode.md"
PARSE_PIPELINE = REPO_ROOT / "src" / "skf-forger" / "scripts" / "parse-pipeline.py"

_spec = importlib.util.spec_from_file_location("parse_pipeline", PARSE_PIPELINE)
parse_pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parse_pipeline)
ALIASES = parse_pipeline.ALIASES


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
            ("forge-auto", "90"),
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
# init.md §1b: Four-Layer Threshold Precedence, resolved once
# ---------------------------------------------------------------------------


class TestInitThresholdPrecedence:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

    def test_precedence_header_mentions_pipeline_default(self, text: str) -> None:
        assert re.search(
            r"CLI\s*>\s*pipeline default\s*>\s*scalar\s*>\s*bundled fallback",
            text,
        ), "init.md §1b precedence header must list all four layers in order"

    def test_layer_1_cli_override(self, text: str) -> None:
        assert re.search(
            r"1\.\s+.*--threshold=<N>.*CLI wins", text
        ), "init.md §1b must document layer 1: CLI override"

    def test_layer_2_pipeline_default(self, text: str) -> None:
        assert re.search(
            r"2\.\s+.*pipeline_default_threshold.*pipeline default \(\{pipeline_alias\}", text
        ), "init.md §1b must document layer 2: the pipeline default of the lookup table"

    def test_layer_3_workflow_scalar(self, text: str) -> None:
        assert re.search(
            r"3\.\s+.*defaultThreshold.*workflow.*scalar", text, re.DOTALL
        ), "init.md §1b must document layer 3: workflow default scalar"

    def test_layer_4_bundled_fallback(self, text: str) -> None:
        assert re.search(
            r"4\.\s+.*fall back to.*80", text
        ), "init.md §1b must document layer 4: bundled fallback 80"


# ---------------------------------------------------------------------------
# init.md §1b: Threshold Source Logging
# ---------------------------------------------------------------------------


class TestInitThresholdSourceLogging:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

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

    def test_threshold_source_is_written_into_the_report(self, text: str) -> None:
        assert "thresholdSource: '{threshold_source}'" in text, (
            "init.md §6c must write threshold_source into the report frontmatter"
        )
        assert "threshold: '{effective_threshold}%'" in text

    def test_score_reads_the_threshold_back(self) -> None:
        score = _read(SCORE_FILE)
        section = score[score.index("### 1. Read the Pass Threshold"):score.index("### 2.")]
        assert "`effective_threshold` ← `threshold`" in section
        assert "`threshold_source` ← `thresholdSource`" in section
        assert "Never resolve the precedence again here" in section
        assert "--threshold=<N>" not in section, "the precedence lives in init.md §1b alone"


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
# init.md §6c: thresholdSource in the report frontmatter
# ---------------------------------------------------------------------------


class TestReportFrontmatter:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(INIT_FILE)

    def test_threshold_source_in_frontmatter(self, text: str) -> None:
        assert re.search(
            r"thresholdSource:.*threshold_source", text
        ), "init.md §6c frontmatter must include thresholdSource field"

    def test_threshold_source_after_threshold_before_confidence(
        self, text: str
    ) -> None:
        fm_section = text[text.find("workflowType: 'test-skill'"):]
        threshold_idx = fm_section.find("threshold:")
        ts_idx = fm_section.find("thresholdSource:")
        confidence_idx = fm_section.find("analysisConfidence:")
        assert threshold_idx < ts_idx < confidence_idx, (
            "thresholdSource must appear after threshold and before analysisConfidence"
        )


# ---------------------------------------------------------------------------
# references/invocation-contract.md: Invocation Contract references per-pipeline defaults
# ---------------------------------------------------------------------------


class TestInvocationContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(CONTRACT_FILE)

    def test_threshold_flag_references_per_pipeline_defaults(self, text: str) -> None:
        invocation_match = re.search(
            r"## Invocation Contract\b(.*?)(?=^## )",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        assert invocation_match, "invocation-contract.md must have an Invocation Contract section"
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
        section = re.sub(r"\s+", " ", activation_match.group(1))
        # The precedence has one home, init.md §1b, and score.md reads its result from the report.
        assert ("init.md §1b resolves the precedence (CLI, then per-pipeline default, then this scalar) once "
                "and writes `threshold` and `thresholdSource` into the report frontmatter, which score.md §1 reads"
                ) in section, (
            "On Activation §3 {defaultThreshold} description must point at init.md §1b, where the "
            "precedence is resolved once"
        )
        assert "at the usage site in `references/score.md`" not in section


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
    """pipeline-mode.md step 4c is the one home of the {pipeline_alias} rule;
    the forger's SKILL.md only routes a chain there."""

    @pytest.fixture(scope="class")
    def pipeline_section(self) -> str:
        step = next(
            (line for line in _read(PIPELINE_MODE).splitlines() if "**Invoke the workflow**" in line),
            None,
        )
        assert step, "pipeline-mode.md must have step 4c, Invoke the workflow"
        return step

    def test_skill_md_routes_to_the_procedure(self) -> None:
        m = re.search(r"^## Pipeline Mode\s*$(.*?)(?=^## |\Z)", _read(FORGER_MD), re.M | re.S)
        assert m, "Forger SKILL.md must have a Pipeline Mode section"
        assert "`references/pipeline-mode.md`" in m.group(1)
        assert "{pipeline_alias}" not in m.group(1)

    def test_step_4c_mentions_pipeline_alias(self, pipeline_section: str) -> None:
        assert "{pipeline_alias}" in pipeline_section, (
            "Pipeline Mode §4.c must set {pipeline_alias} in workflow data context"
        )

    def test_step_4c_lists_alias_names(self, pipeline_section: str) -> None:
        for alias in ("forge-auto", "forge", "forge-quick", "maintain"):
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
        assert re.search(r"^\| `alias` \|[^\n]*pipeline alias", text, re.IGNORECASE | re.MULTILINE), (
            "Pipeline State must include alias at top level of pipeline state"
        )

    def test_pipeline_alias_in_data_context(self, text: str) -> None:
        assert re.search(
            r"data context carries[^\n]*`pipeline_alias`, the journal's `alias`", text
        ), "Pipeline State must forward the alias as pipeline_alias in each workflow's data context"

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

    @staticmethod
    def _init_thresholds() -> dict[str, int]:
        """init.md §1b's lookup table: pipeline alias -> default threshold."""
        rows = re.findall(r"^\|\s*`([a-z-]+)`\s*\|\s*(\d+)\s*\|", _read(INIT_FILE), re.M)
        return {alias: int(n) for alias, n in rows}

    @staticmethod
    def _ts_min(alias: str) -> int | None:
        plan = parse_pipeline.parse_pipeline(alias)["plan"]
        return next(p["min"] for p in plan if p["code"] == "TS")

    def test_forge_auto_alias_threshold_matches_lookup_table(self) -> None:
        """ALIASES['forge-auto'] gates TS at init.md §1b's forge-auto value."""
        assert "TS[min:90]" in ALIASES["forge-auto"]
        assert self._ts_min("forge-auto") == self._init_thresholds()["forge-auto"] == 90

    def test_alias_gates_agree_with_lookup_table(self) -> None:
        """An alias that pins a TS gate pins the one init.md §1b maps it to;
        the others leave TS to that table (the pipeline default)."""
        table = self._init_thresholds()
        for alias in ALIASES:
            ts_min = self._ts_min(alias)
            if ts_min is not None:
                assert table.get(alias) == ts_min, (alias, ts_min, table.get(alias))

    def test_forge_alias_has_no_min_override(self) -> None:
        assert not any("min:" in token for token in ALIASES["forge"]), (
            "forge alias expansion must not include min: override (relies on pipeline default)"
        )
        assert self._ts_min("forge") is None

    def test_aliases_match_the_contracts_alias_table(self) -> None:
        """pipeline-contracts.md's alias table is the contract a reader sees:
        it must expand every alias as ALIASES, the parser's table, does."""
        rows = re.findall(r"^\|\s*`([a-z-]+)`\s*\|\s*`([^`]+)`\s*\|", _read(PIPELINE_CONTRACTS), re.M)
        assert {alias: expansion.split() for alias, expansion in rows} == ALIASES

    def test_forger_forwards_the_ts_gate_as_threshold(self) -> None:
        """The plan's TS min reaches TS as --threshold, the flag TS takes."""
        invoke = next(line for line in _read(PIPELINE_MODE).splitlines() if "**Invoke the workflow**" in line)
        assert "invoke TS with `--threshold=<min>`" in invoke
        # The flag TS takes is listed in its invocation contract (#600) and read by init.md §1b.
        assert "`--threshold=<N>`" in _read(CONTRACT_FILE) and "`--threshold=<N>`" in _read(INIT_FILE)

    def test_score_md_references_init_md_1b(self) -> None:
        score_text = _read(SCORE_FILE)
        assert "init.md §1b" in score_text, (
            "score.md must reference init.md §1b as the source of pipeline_default_threshold"
        )

    def test_init_md_mentions_pipeline_alias_in_the_pipeline_layer(self) -> None:
        init_text = _read(INIT_FILE)
        assert re.search(r"2\.\s+.*\{pipeline_alias\}", init_text), (
            "init.md §1b must reference {pipeline_alias} in the pipeline default layer"
        )
