"""Structural integration tests for the step-doc-sources.md step file (story 1.3).

Validates the doc-sources step contract: correct pipeline wiring, required
sections, script reference integrity, doc_sources schema completeness in
skill-sections.md, and stages-table positioning.  Chain-reachability tests
cover link resolution; these tests cover the semantic contract.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CS_DIR = REPO_ROOT / "src" / "skf-create-skill"
STEP_FILE = CS_DIR / "references" / "step-doc-sources.md"
COMPILE_FILE = CS_DIR / "references" / "compile.md"
SKILL_MD = CS_DIR / "SKILL.md"
SECTIONS_FILE = CS_DIR / "assets" / "skill-sections.md"
DETECT_DOCS_SCRIPT = REPO_ROOT / "src" / "shared" / "scripts" / "skf-detect-docs.py"


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
    assert STEP_FILE.exists(), "step-doc-sources.md must exist"


# ---------------------------------------------------------------------------
# Pipeline chain values
# ---------------------------------------------------------------------------


class TestPipelineChain:
    def test_compile_points_to_step_doc_sources(self) -> None:
        assert _next_step_value(COMPILE_FILE) == "step-doc-sources.md"

    def test_step_doc_sources_points_to_validate(self) -> None:
        assert _next_step_value(STEP_FILE) == "validate.md"

    def test_validate_exists(self) -> None:
        target = (STEP_FILE.parent / "validate.md").resolve()
        assert target.exists(), "validate.md must exist for the chain to complete"


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
            "Check for Upstream Doc Detection Results",
            "Run Doc Detection",
            "Ensure README Entry",
            "Build doc_sources Array",
            "Update metadata.json",
            "Auto-Proceed",
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


# ---------------------------------------------------------------------------
# Script reference integrity
# ---------------------------------------------------------------------------


class TestScriptReference:
    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(STEP_FILE)

    def test_references_detect_docs_script(self, text: str) -> None:
        assert "skf-detect-docs.py" in text, (
            "step must reference the detect-docs script"
        )

    def test_detect_docs_script_exists(self) -> None:
        assert DETECT_DOCS_SCRIPT.exists(), (
            "skf-detect-docs.py must exist on disk"
        )

    def test_references_uv_run_invocation(self, text: str) -> None:
        assert "uv run" in text, "step must invoke script via uv run"

    def test_documents_exit_codes(self, text: str) -> None:
        for code in ("Exit 0", "Exit 1", "Exit 2"):
            assert code in text, f"step must document {code} handling"


# ---------------------------------------------------------------------------
# doc_sources schema in skill-sections.md
# ---------------------------------------------------------------------------


class TestDocSourcesSchema:
    @pytest.fixture(scope="class")
    def schema_text(self) -> str:
        return _read(SECTIONS_FILE)

    def test_doc_sources_field_present(self, schema_text: str) -> None:
        assert "doc_sources" in schema_text

    @pytest.mark.parametrize(
        "field",
        ["url", "detected_via", "content_hash", "recorded_at"],
    )
    def test_schema_has_required_field(self, schema_text: str, field: str) -> None:
        doc_src_line = [
            line for line in schema_text.splitlines() if "doc_sources" in line
        ]
        assert any(field in line for line in doc_src_line), (
            f"doc_sources schema must include field: {field}"
        )

    def test_detected_via_includes_readme_always(self, schema_text: str) -> None:
        assert "readme_always" in schema_text, (
            "doc_sources schema must include readme_always in detected_via enum"
        )

    _EXPECTED_DETECTED_VIA = [
        "homepageUrl",
        "readme_link",
        "pages_api",
        "docs_folder",
        "readme_always",
    ]

    @pytest.mark.parametrize("value", _EXPECTED_DETECTED_VIA)
    def test_detected_via_enum_coverage(self, schema_text: str, value: str) -> None:
        assert value in schema_text, (
            f"doc_sources schema must list detected_via value: {value}"
        )

    def test_doc_sources_before_generated_by(self, schema_text: str) -> None:
        doc_idx = schema_text.find("doc_sources")
        gen_idx = schema_text.find('"generated_by"')
        assert doc_idx < gen_idx, (
            "doc_sources must appear before generated_by in schema ordering"
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

    def test_step_5a_name_is_doc_sources(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|\s*Doc Sources\s*\|", stages_section
        ), "Step 5a must be named 'Doc Sources'"

    def test_step_5a_file_path(self, stages_section: str) -> None:
        assert re.search(
            r"\|\s*5a\s*\|.*references/step-doc-sources\.md", stages_section
        ), "Step 5a must reference references/step-doc-sources.md"

    def test_step_5a_between_compile_and_validate(self, stages_section: str) -> None:
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
            "Step 5a must come after step 5 (Compile)"
        )
        assert idx_6 is not None and idx_5a < idx_6, (
            "Step 5a must come before step 6 (Validate)"
        )
