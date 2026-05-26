"""Structural integration tests for doc-rot correction hooks (step 5c).

Validates step-doc-rot.md exists with correct frontmatter, mandatory grep
patterns, CORRECTION block format, feeder artifact scan targets, graceful
skip logic, step chain from step-auto-shard.md, and Stages table in SKILL.md.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CS_DIR = REPO_ROOT / "src" / "skf-create-skill"
STEP_DOC_ROT = CS_DIR / "references" / "step-doc-rot.md"
STEP_AUTO_SHARD = CS_DIR / "references" / "step-auto-shard.md"
VALIDATE_FILE = CS_DIR / "references" / "validate.md"
CS_SKILL_MD = CS_DIR / "SKILL.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# step-doc-rot.md — File Exists
# ---------------------------------------------------------------------------


class TestStepDocRotExists:
    def test_file_exists(self) -> None:
        assert STEP_DOC_ROT.exists(), (
            "src/skf-create-skill/references/step-doc-rot.md must exist"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Frontmatter nextStepFile
# ---------------------------------------------------------------------------


class TestStepDocRotFrontmatter:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_has_frontmatter(self, text: str) -> None:
        assert text.startswith("---"), (
            "step-doc-rot.md must have YAML frontmatter"
        )

    def test_next_step_file_is_validate(self, text: str) -> None:
        assert re.search(r"nextStepFile:\s*['\"]?validate\.md['\"]?", text), (
            "step-doc-rot.md nextStepFile must be validate.md"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Mandatory Grep Patterns (at least 5)
# ---------------------------------------------------------------------------


class TestMandatoryGrepPatterns:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    REQUIRED_PATTERNS = [
        "deprecated",
        "@deprecated",
        "breaking change",
        "BREAKING",
        "removed in",
        "was removed",
        "renamed to",
        "renamed from",
        "superseded by",
        "replaced by",
        "no longer supported",
        "migration required",
        "signature changed",
    ]

    def test_at_least_5_patterns_defined(self, text: str) -> None:
        count = sum(1 for p in self.REQUIRED_PATTERNS if p.lower() in text.lower())
        assert count >= 5, (
            f"step-doc-rot.md must define at least 5 grep patterns, found {count}"
        )

    def test_all_13_patterns_defined(self, text: str) -> None:
        count = sum(1 for p in self.REQUIRED_PATTERNS if p.lower() in text.lower())
        assert count == len(self.REQUIRED_PATTERNS), (
            f"step-doc-rot.md must define all {len(self.REQUIRED_PATTERNS)} grep patterns, found {count}"
        )

    @pytest.mark.parametrize("pattern", REQUIRED_PATTERNS)
    def test_pattern_present(self, text: str, pattern: str) -> None:
        assert pattern.lower() in text.lower(), (
            f"step-doc-rot.md must include grep pattern '{pattern}'"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Deterministic Matching (AC #2)
# ---------------------------------------------------------------------------


class TestDeterministicMatching:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_no_ai_judgment_rule(self, text: str) -> None:
        assert re.search(r"no\s+AI\s+judgment", text, re.IGNORECASE), (
            "step-doc-rot.md must state no AI judgment is used for detection"
        )

    def test_no_semantic_analysis_rule(self, text: str) -> None:
        assert re.search(r"no\s+(semantic|regex)\s+(analysis|interpretation)", text, re.IGNORECASE), (
            "step-doc-rot.md must prohibit semantic analysis and regex interpretation"
        )

    def test_no_regex_interpretation(self, text: str) -> None:
        assert re.search(r"no\s+regex\s+interpretation", text, re.IGNORECASE), (
            "step-doc-rot.md must explicitly prohibit regex interpretation"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — CORRECTION Block Format
# ---------------------------------------------------------------------------


class TestCorrectionBlockFormat:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_correction_heading(self, text: str) -> None:
        assert "## CORRECTION" in text, (
            "step-doc-rot.md must define the ## CORRECTION block heading"
        )

    def test_source_field(self, text: str) -> None:
        assert "**Source:**" in text, (
            "step-doc-rot.md CORRECTION block must include **Source:** field"
        )

    def test_pattern_field(self, text: str) -> None:
        assert "**Pattern:**" in text, (
            "step-doc-rot.md CORRECTION block must include **Pattern:** field"
        )

    def test_affected_field(self, text: str) -> None:
        assert "**Affected:**" in text, (
            "step-doc-rot.md CORRECTION block must include **Affected:** field"
        )

    def test_detail_field(self, text: str) -> None:
        assert "**Detail:**" in text, (
            "step-doc-rot.md CORRECTION block must include **Detail:** field"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Feeder Artifact Scan Targets
# ---------------------------------------------------------------------------


class TestFeederArtifactTargets:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_evidence_report_referenced(self, text: str) -> None:
        assert "evidence-report" in text.lower(), (
            "step-doc-rot.md must reference evidence-report as a scan target"
        )

    def test_provenance_map_referenced(self, text: str) -> None:
        assert "provenance-map" in text.lower(), (
            "step-doc-rot.md must reference provenance-map as a scan target"
        )

    def test_temporal_context_referenced(self, text: str) -> None:
        assert re.search(r"temporal", text, re.IGNORECASE), (
            "step-doc-rot.md must reference temporal context as a scan target"
        )

    def test_compiled_skill_md_as_scan_target(self, text: str) -> None:
        assert re.search(r"compiled\s+SKILL\.md", text, re.IGNORECASE), (
            "step-doc-rot.md must reference the compiled SKILL.md itself as a scan target"
        )

    def test_qmd_doc_annotations_referenced(self, text: str) -> None:
        assert "[QMD:" in text or "[DOC:" in text, (
            "step-doc-rot.md must reference [QMD:...] or [DOC:...] annotations as correction signals"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Graceful Skip Logic
# ---------------------------------------------------------------------------


class TestGracefulSkipLogic:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_graceful_skip_rule(self, text: str) -> None:
        assert re.search(r"graceful\s+skip", text, re.IGNORECASE), (
            "step-doc-rot.md must document graceful skip when no corrections found"
        )

    def test_skip_log_message(self, text: str) -> None:
        assert re.search(r"doc-rot:.*skip", text, re.IGNORECASE), (
            "step-doc-rot.md must include a skip log message"
        )


# ---------------------------------------------------------------------------
# step-auto-shard.md — Chains to step-doc-rot.md
# ---------------------------------------------------------------------------


class TestAutoShardChainsToDocRot:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_AUTO_SHARD)

    def test_next_step_is_doc_rot(self, text: str) -> None:
        assert re.search(
            r"nextStepFile:\s*['\"]?step-doc-rot\.md['\"]?", text
        ), "step-auto-shard.md nextStepFile must be step-doc-rot.md"


# ---------------------------------------------------------------------------
# SKILL.md — Stages Table Includes Doc-Rot Row
# ---------------------------------------------------------------------------


class TestSkillMdStagesTable:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(CS_SKILL_MD)

    def test_doc_rot_row_exists(self, text: str) -> None:
        assert re.search(r"\|\s*5c\s*\|.*Doc-Rot", text), (
            "SKILL.md Stages table must include a 5c Doc-Rot row"
        )

    def test_doc_rot_references_file(self, text: str) -> None:
        assert "references/step-doc-rot.md" in text, (
            "SKILL.md Stages table must reference references/step-doc-rot.md"
        )

    def test_doc_rot_between_auto_shard_and_validate(self, text: str) -> None:
        idx_5b = text.find("5b")
        idx_5c = text.find("5c")
        idx_6 = text.find("| 6 ")
        assert idx_5b < idx_5c < idx_6, (
            "Doc-Rot (5c) must appear between Auto-Shard (5b) and Validate (6)"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Step File Structural Contract
# ---------------------------------------------------------------------------


class TestStepFileStructuralContract:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_step_heading_matches_stages_numbering(self, text: str) -> None:
        assert re.search(r"^# Step 5c:", text, re.MULTILINE), (
            "step-doc-rot.md heading must be '# Step 5c:' to match Stages table"
        )

    def test_has_step_goal_section(self, text: str) -> None:
        assert re.search(r"^##\s+STEP GOAL", text, re.MULTILINE | re.IGNORECASE), (
            "step-doc-rot.md must have a ## STEP GOAL section"
        )

    def test_has_rules_section(self, text: str) -> None:
        assert re.search(r"^##\s+Rules\b", text, re.MULTILINE | re.IGNORECASE), (
            "step-doc-rot.md must have a ## Rules section"
        )

    def test_has_mandatory_sequence_section(self, text: str) -> None:
        assert re.search(
            r"^##\s+MANDATORY SEQUENCE", text, re.MULTILINE | re.IGNORECASE
        ), "step-doc-rot.md must have a ## MANDATORY SEQUENCE section"


# ---------------------------------------------------------------------------
# step-doc-rot.md — Auto-Proceed Rule
# ---------------------------------------------------------------------------


class TestDocRotRules:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_auto_proceed_rule(self, text: str) -> None:
        assert re.search(r"auto.proceed", text, re.IGNORECASE), (
            "step-doc-rot.md must document auto-proceed (no user interaction)"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — §-Prefixed Sections
# ---------------------------------------------------------------------------


class TestSectionPrefixedSections:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    EXPECTED_SECTIONS = ["§1", "§2", "§3", "§4", "§5"]

    @pytest.mark.parametrize("section", EXPECTED_SECTIONS)
    def test_section_prefix_exists(self, text: str, section: str) -> None:
        assert section in text, (
            f"step-doc-rot.md must have a {section}-prefixed section"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Context Logging Variables
# ---------------------------------------------------------------------------


class TestContextLoggingVariables:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    CONTEXT_VARS = [
        "doc_rot_triggered",
        "corrections_added",
        "feeder_artifacts_scanned",
        "correction_matches",
    ]

    @pytest.mark.parametrize("var", CONTEXT_VARS)
    def test_context_variable_present(self, text: str, var: str) -> None:
        assert var in text, (
            f"step-doc-rot.md must log context variable '{var}'"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — nextStepFile Reference in Auto-Proceed
# ---------------------------------------------------------------------------


class TestAutoProceed:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_next_step_file_reference(self, text: str) -> None:
        assert re.search(r"\{nextStepFile\}", text), (
            "step-doc-rot.md must reference {nextStepFile} for chain continuation"
        )


# ---------------------------------------------------------------------------
# Chain Target Resolution — validate.md Exists
# ---------------------------------------------------------------------------


class TestChainTargetResolution:
    def test_validate_file_exists(self) -> None:
        assert VALIDATE_FILE.exists(), (
            "validate.md must exist at the chain target path from step-doc-rot.md"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Case-Insensitive Matching Documented
# ---------------------------------------------------------------------------


class TestCaseInsensitiveMatching:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_case_insensitive_documented(self, text: str) -> None:
        assert re.search(r"case.insensitive", text, re.IGNORECASE), (
            "step-doc-rot.md must document that pattern matching is case-insensitive"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — No Frontmatter Modification Rule
# ---------------------------------------------------------------------------


class TestNoFrontmatterModification:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_body_content_only(self, text: str) -> None:
        assert re.search(
            r"(never|not).*frontmatter", text, re.IGNORECASE
        ), "step-doc-rot.md must state correction blocks are never inside frontmatter"


# ---------------------------------------------------------------------------
# step-doc-rot.md — Insertion Logic Rules (§3)
# ---------------------------------------------------------------------------


class TestInsertionLogicRules:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_after_relevant_section_rule(self, text: str) -> None:
        assert re.search(
            r"after the relevant.*section", text, re.IGNORECASE
        ), "step-doc-rot.md must define insertion after the relevant API section"

    def test_end_of_body_fallback(self, text: str) -> None:
        assert re.search(
            r"(end of|at the end).*body", text, re.IGNORECASE
        ), "step-doc-rot.md must define end-of-body fallback for unmatched sections"

    def test_multiple_blocks_rule(self, text: str) -> None:
        assert re.search(
            r"multiple\s+correct", text, re.IGNORECASE
        ), "step-doc-rot.md must state multiple corrections produce multiple blocks"

    def test_self_contained_blocks(self, text: str) -> None:
        assert re.search(
            r"self.contained", text, re.IGNORECASE
        ), "step-doc-rot.md must state each correction block is self-contained"


# ---------------------------------------------------------------------------
# step-doc-rot.md — Match Record Fields (§2)
# ---------------------------------------------------------------------------


class TestMatchRecordFields:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    MATCH_FIELDS = ["source", "pattern", "category", "context_line", "affected"]

    @pytest.mark.parametrize("field", MATCH_FIELDS)
    def test_match_field_documented(self, text: str, field: str) -> None:
        assert re.search(rf"`{field}`", text), (
            f"step-doc-rot.md §2 must document match record field '{field}'"
        )


# ---------------------------------------------------------------------------
# step-doc-rot.md — Positive-Path Log Format (§4)
# ---------------------------------------------------------------------------


class TestPositivePathLog:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_positive_log_message(self, text: str) -> None:
        assert re.search(
            r"doc-rot:.*correction\s+blocks?\s+added", text, re.IGNORECASE
        ), "step-doc-rot.md must define the positive-path log message format"

    def test_log_references_artifact_count(self, text: str) -> None:
        assert re.search(
            r"feeder.artifact", text, re.IGNORECASE
        ), "step-doc-rot.md positive-path log must reference feeder artifact count"


# ---------------------------------------------------------------------------
# step-doc-rot.md — Read-Only Feeder Artifact Rule
# ---------------------------------------------------------------------------


class TestReadOnlyFeederArtifacts:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    def test_reads_only_rule(self, text: str) -> None:
        assert re.search(
            r"(reads?\s+them\s+only|do not modify.*feeder)", text, re.IGNORECASE
        ), "step-doc-rot.md must state it only reads feeder artifacts, not writes"


# ---------------------------------------------------------------------------
# step-doc-rot.md — Pattern Category Labels
# ---------------------------------------------------------------------------


class TestPatternCategories:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_DOC_ROT)

    CATEGORIES = [
        "Deprecation",
        "Breaking change",
        "Removal",
        "Rename",
        "Supersession",
        "End of life",
        "Migration",
        "Signature change",
    ]

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_category_present(self, text: str, category: str) -> None:
        assert category in text, (
            f"step-doc-rot.md must define category '{category}' for grep patterns"
        )
