"""Structural integration tests for auto-shard at 400-line ceiling (story 3.4).

Validates step-auto-shard.md exists with correct frontmatter, the 400-line
threshold constant, Tier 1 preservation names, Tier 2 heading pattern,
cross-reference link format, step chain from step-doc-sources.md, Stages
table in SKILL.md, §-prefixed sections, context logging variables,
structural contract, prohibition constraints, and safety-net integrity.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CS_DIR = REPO_ROOT / "src" / "skf-create-skill"
STEP_AUTO_SHARD = CS_DIR / "references" / "step-auto-shard.md"
STEP_DOC_SOURCES = CS_DIR / "references" / "step-doc-sources.md"
VALIDATE_FILE = CS_DIR / "references" / "validate.md"
CS_SKILL_MD = CS_DIR / "SKILL.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# step-auto-shard.md — File Exists
# ---------------------------------------------------------------------------


class TestStepAutoShardExists:
    def test_file_exists(self) -> None:
        assert STEP_AUTO_SHARD.exists(), (
            "src/skf-create-skill/references/step-auto-shard.md must exist"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Frontmatter nextStepFile
# ---------------------------------------------------------------------------


class TestStepAutoShardFrontmatter:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_next_step_file_is_validate(self, text: str) -> None:
        assert re.search(r"nextStepFile:\s*['\"]?validate\.md['\"]?", text), (
            "step-auto-shard.md nextStepFile must be validate.md"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — 400-Line Threshold Constant
# ---------------------------------------------------------------------------


class TestThresholdConstant:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_400_threshold_present(self, text: str) -> None:
        assert "400" in text, (
            "step-auto-shard.md must reference the 400-line threshold"
        )

    def test_threshold_in_skip_condition(self, text: str) -> None:
        assert re.search(r"body_line_count.*<=\s*400", text), (
            "step-auto-shard.md must have a skip condition at 400 lines"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Tier 1 Section Names Listed for Preservation
# ---------------------------------------------------------------------------


class TestTier1PreservationNames:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    TIER_1_NAMES = [
        "Overview",
        "Quick Start",
        "Common Workflows",
        "Key API Summary",
        "Key Types",
        "Architecture at a Glance",
    ]

    @pytest.mark.parametrize("name", TIER_1_NAMES)
    def test_tier1_name_listed(self, text: str, name: str) -> None:
        assert name in text, (
            f"step-auto-shard.md must list Tier 1 section '{name}' for preservation"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Tier 2 `## Full` Heading Pattern
# ---------------------------------------------------------------------------


class TestTier2HeadingPattern:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_full_heading_prefix(self, text: str) -> None:
        assert "## Full" in text, (
            "step-auto-shard.md must reference the `## Full` heading prefix for Tier 2"
        )

    TIER_2_HEADINGS = [
        "Full API Reference",
        "Full Type Definitions",
        "Full Integration Patterns",
    ]

    @pytest.mark.parametrize("heading", TIER_2_HEADINGS)
    def test_tier2_heading_listed(self, text: str, heading: str) -> None:
        assert heading in text, (
            f"step-auto-shard.md must list Tier 2 heading '{heading}'"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Cross-Reference Link Format
# ---------------------------------------------------------------------------


class TestCrossReferenceFormat:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_blockquote_cross_reference(self, text: str) -> None:
        assert re.search(
            r">\s*See\s+\[.*\]\(references/.*\.md\)", text
        ), "step-auto-shard.md must show the blockquote cross-reference format"

    def test_kebab_case_filename(self, text: str) -> None:
        assert "full-api-reference.md" in text, (
            "step-auto-shard.md must show kebab-case reference filename example"
        )


# ---------------------------------------------------------------------------
# step-doc-sources.md — Chains to step-auto-shard.md
# ---------------------------------------------------------------------------


class TestDocSourcesChaining:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_SOURCES)

    def test_next_step_is_auto_shard(self, text: str) -> None:
        assert re.search(
            r"nextStepFile:\s*['\"]?step-auto-shard\.md['\"]?", text
        ), "step-doc-sources.md nextStepFile must be step-auto-shard.md"


# ---------------------------------------------------------------------------
# SKILL.md — Stages Table Includes Auto-Shard Row
# ---------------------------------------------------------------------------


class TestSkillMdStagesTable:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(CS_SKILL_MD)

    def test_auto_shard_row_exists(self, text: str) -> None:
        assert re.search(r"\|\s*5b\s*\|.*Auto-Shard", text), (
            "SKILL.md Stages table must include a 5b Auto-Shard row"
        )

    def test_auto_shard_references_file(self, text: str) -> None:
        assert "references/step-auto-shard.md" in text, (
            "SKILL.md Stages table must reference references/step-auto-shard.md"
        )

    def test_auto_shard_between_doc_sources_and_validate(self, text: str) -> None:
        idx_5a = text.find("5a")
        idx_5b = text.find("5b")
        idx_6 = text.find("| 6 ")
        assert idx_5a < idx_5b < idx_6, (
            "Auto-Shard (5b) must appear between Doc Sources (5a) and Validate (6)"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — §-Prefixed Sections
# ---------------------------------------------------------------------------


class TestSectionPrefixedSections:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    EXPECTED_SECTIONS = ["§1", "§2", "§3", "§4", "§5"]

    @pytest.mark.parametrize("section", EXPECTED_SECTIONS)
    def test_section_prefix_exists(self, text: str, section: str) -> None:
        assert section in text, (
            f"step-auto-shard.md must have a {section}-prefixed section"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Context Logging Variables
# ---------------------------------------------------------------------------


class TestContextLoggingVariables:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    CONTEXT_VARS = [
        "auto_shard_triggered",
        "sections_extracted",
        "body_lines_before",
        "body_lines_after",
    ]

    @pytest.mark.parametrize("var", CONTEXT_VARS)
    def test_context_variable_present(self, text: str, var: str) -> None:
        assert var in text, (
            f"step-auto-shard.md must log context variable '{var}'"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Step File Structural Contract
# ---------------------------------------------------------------------------


class TestStepFileStructuralContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_step_heading_matches_stages_numbering(self, text: str) -> None:
        assert re.search(r"^# Step 5b:", text, re.MULTILINE), (
            "step-auto-shard.md heading must be '# Step 5b:' to match Stages table"
        )

    def test_has_step_goal_section(self, text: str) -> None:
        assert re.search(r"^##\s+STEP GOAL", text, re.MULTILINE | re.IGNORECASE), (
            "step-auto-shard.md must have a ## STEP GOAL section"
        )

    def test_has_rules_section(self, text: str) -> None:
        assert re.search(r"^##\s+Rules\b", text, re.MULTILINE | re.IGNORECASE), (
            "step-auto-shard.md must have a ## Rules section"
        )

    def test_has_mandatory_sequence_section(self, text: str) -> None:
        assert re.search(
            r"^##\s+MANDATORY SEQUENCE", text, re.MULTILINE | re.IGNORECASE
        ), "step-auto-shard.md must have a ## MANDATORY SEQUENCE section"


# ---------------------------------------------------------------------------
# step-auto-shard.md — Auto-Proceed and Graceful Skip Rules
# ---------------------------------------------------------------------------


class TestAutoShardRules:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_auto_proceed_rule(self, text: str) -> None:
        assert re.search(r"auto.proceed", text, re.IGNORECASE), (
            "step-auto-shard.md must document auto-proceed (no user interaction)"
        )

    def test_graceful_skip_rule(self, text: str) -> None:
        assert re.search(r"graceful\s+skip", text, re.IGNORECASE), (
            "step-auto-shard.md must document graceful skip when under threshold"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Tier 1 Conditional Sections Listed
# ---------------------------------------------------------------------------


class TestTier1ConditionalSections:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    CONDITIONAL_TIER_1 = [
        "Migration & Deprecation Warnings",
        "CLI",
        "Scripts & Assets",
        "Manual Sections",
    ]

    @pytest.mark.parametrize("name", CONDITIONAL_TIER_1)
    def test_conditional_tier1_listed(self, text: str, name: str) -> None:
        assert name in text, (
            f"step-auto-shard.md must list conditional Tier 1 section '{name}'"
        )

    def test_component_catalog_alternative(self, text: str) -> None:
        assert "Component Catalog" in text, (
            "step-auto-shard.md must list Component Catalog as Key API Summary alternative"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — §6 Auto-Proceed Section
# ---------------------------------------------------------------------------


class TestAutoShardSection6:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_section_6_exists(self, text: str) -> None:
        assert "§6" in text, (
            "step-auto-shard.md must have a §6 Auto-Proceed section"
        )

    def test_next_step_file_reference_in_section_6(self, text: str) -> None:
        assert re.search(r"\{nextStepFile\}", text), (
            "step-auto-shard.md §6 must reference {nextStepFile} for chain continuation"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Extraction Algorithm Ordering
# ---------------------------------------------------------------------------


class TestExtractionAlgorithm:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_sort_by_line_count_descending(self, text: str) -> None:
        assert re.search(r"(largest first|line count desc)", text, re.IGNORECASE), (
            "step-auto-shard.md must specify extraction order: largest sections first"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Prohibition Constraints
# ---------------------------------------------------------------------------


class TestProhibitionConstraints:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_no_split_body_invocation(self, text: str) -> None:
        assert re.search(
            r"(do not|not) invoke.*skill-check split-body", text, re.IGNORECASE
        ), "step-auto-shard.md must prohibit npx skill-check split-body invocation"

    def test_no_description_guard_protocol(self, text: str) -> None:
        assert re.search(
            r"(do not|not) invoke.*Description Guard", text, re.IGNORECASE
        ), "step-auto-shard.md must prohibit Description Guard Protocol invocation"

    def test_no_frontmatter_modification(self, text: str) -> None:
        assert re.search(
            r"(do not|not) modify.*frontmatter", text, re.IGNORECASE
        ), "step-auto-shard.md must prohibit frontmatter modification"


# ---------------------------------------------------------------------------
# Chain Target Resolution — validate.md Exists
# ---------------------------------------------------------------------------


class TestChainTargetResolution:
    def test_validate_file_exists(self) -> None:
        assert VALIDATE_FILE.exists(), (
            "validate.md must exist at the chain target path from step-auto-shard.md"
        )


# ---------------------------------------------------------------------------
# validate.md §4 Safety Net Integrity
# ---------------------------------------------------------------------------


class TestValidateSafetyNet:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(VALIDATE_FILE)

    def test_body_max_lines_reference(self, text: str) -> None:
        assert "body.max_lines" in text, (
            "validate.md must still reference body.max_lines (safety net at 500 lines)"
        )

    def test_tier2_selective_extraction(self, text: str) -> None:
        assert "## Full" in text, (
            "validate.md §4 must still reference Tier 2 ## Full heading pattern"
        )

    def test_tier1_preservation_check(self, text: str) -> None:
        assert re.search(r"Tier 1.*remain inline", text, re.IGNORECASE), (
            "validate.md §4 must still enforce Tier 1 preservation"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — All Kebab-Case Reference Filenames
# ---------------------------------------------------------------------------


class TestKebabCaseFilenames:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    EXPECTED_FILENAMES = [
        "full-api-reference.md",
        "full-type-definitions.md",
        "full-integration-patterns.md",
    ]

    @pytest.mark.parametrize("filename", EXPECTED_FILENAMES)
    def test_kebab_case_filename_present(self, text: str, filename: str) -> None:
        assert filename in text, (
            f"step-auto-shard.md must show kebab-case filename '{filename}'"
        )
