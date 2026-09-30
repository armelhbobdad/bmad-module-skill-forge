"""Structural integration tests for doc-rot correction hooks (step 5c).

Validates step-doc-rot.md exists with correct frontmatter, mandatory grep
patterns, CORRECTION block format, feeder artifact scan targets, graceful
skip logic, step chain from step-auto-shard.md, and Stages table in SKILL.md.
Also checks the temporal feeder: step 3b (sub/fetch-temporal.md) keeps the
files it fetched in the folder step 5c scans, a failed refresh keeps the last
good copy, a correction drawn from it cites the QMD collection, and a missing
feeder reaches the evidence report as a notice.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CS_DIR = REPO_ROOT / "src" / "skf-create-skill"
STEP_DOC_ROT = CS_DIR / "references" / "step-doc-rot.md"
STEP_AUTO_SHARD = CS_DIR / "references" / "step-auto-shard.md"
VALIDATE_FILE = CS_DIR / "references" / "validate.md"
CS_SKILL_MD = CS_DIR / "SKILL.md"
FETCH_TEMPORAL = CS_DIR / "references" / "sub" / "fetch-temporal.md"
GENERATE_ARTIFACTS = CS_DIR / "references" / "generate-artifacts.md"
SKILL_SECTIONS = CS_DIR / "assets" / "skill-sections.md"
SCAN_DOC_ROT_PY = CS_DIR / "scripts" / "scan-doc-rot.py"
INVENTORY_PY = REPO_ROOT / "src" / "shared" / "scripts" / "skf-skill-inventory.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from `start` up to `end`, or to the end of the file."""
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))] if end else text[begin:]


def _load_script(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_excludes_own_migration_section_from_correction_matches(self, text: str) -> None:
        """§4b guard: corrections compile already authored into the SKILL.md's
        own Migration & Deprecation Warnings section must be discarded, not
        re-emitted as circular ## CORRECTION blocks."""
        assert re.search(r"Migration\s*&\s*Deprecation Warnings", text), (
            "step-doc-rot.md must reference the Migration & Deprecation Warnings section "
            "to exclude compile-authored §4b corrections"
        )
        assert re.search(r"discard|exclu", text, re.IGNORECASE), (
            "step-doc-rot.md must instruct discarding/excluding already-surfaced §4b matches"
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


# ---------------------------------------------------------------------------
# Temporal feeder: step 3b keeps the files step 5c scans
# ---------------------------------------------------------------------------

FEEDER_BINDING_RE = re.compile(
    r"bind `\{temporal_feeder\}` ← `\{forge_data_folder\}/\{skill-name\}/([^`/]+)`"
)
FETCH_BINDING_RE = re.compile(
    r"bind `\{temporal_fetch\}` ← `\{forge_data_folder\}/\{skill-name\}/([^`/]+)`"
)
NOTICE_BINDING_RE = re.compile(r"bind `\{temporal_feeder_notice\}` ← `([^`]+)`")
FEEDER_FILES = ("issues.md", "prs.md", "releases.md", "changelog.md", "targeted-issues.md")
POSIX_SHELL = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell"
)


def _feeder_name() -> str:
    """The folder, inside the skill's forge folder, that step 3b keeps as the feeder."""
    names = FEEDER_BINDING_RE.findall(_read(FETCH_TEMPORAL))
    assert len(names) == 1, f"fetch-temporal.md must bind {{temporal_feeder}} once, found {names}"
    return names[0]


def _fetch_name() -> str:
    """The folder beside the feeder that step 3b fetches into before it replaces the feeder."""
    names = FETCH_BINDING_RE.findall(_read(FETCH_TEMPORAL))
    assert len(names) == 1, f"fetch-temporal.md must bind {{temporal_fetch}} once, found {names}"
    return names[0]


def _write_feeder(group: pathlib.Path, name: str | None = None,
                  files: tuple[str, ...] = FEEDER_FILES) -> pathlib.Path:
    """What a fetch leaves in `group`: the feeder files and the self-ignoring .gitignore."""
    feeder = group / (name or _feeder_name())
    feeder.mkdir(parents=True)
    (feeder / ".gitignore").write_text("*\n", encoding="utf-8")
    for file_name in files:
        (feeder / file_name).write_text(f"# {file_name}\n", encoding="utf-8")
    return feeder


def _run_documented(command: str, forge: pathlib.Path) -> None:
    """Run a fetch-temporal.md command through bash, as an agent would, for skill `mylib`."""
    script = command.replace("{forge_data_folder}", forge.as_posix()).replace("{skill-name}", "mylib")
    proc = subprocess.run(["bash", "-euc", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _write_forge_group(root: pathlib.Path) -> pathlib.Path:
    """A forge folder create-skill wrote: the brief and one version's workspace files."""
    group = root / "mylib"
    (group / "1.0.0").mkdir(parents=True)
    (group / "skill-brief.yaml").write_text("name: mylib\n", encoding="utf-8")
    for name in ("provenance-map.json", "evidence-report.md", "extraction-rules.yaml"):
        (group / "1.0.0" / name).write_text("{}\n", encoding="utf-8")
    return group


class TestTemporalFeederLocation:
    """Step 3b fetches into one persistent folder, and step 5c scans that folder."""

    def test_feeder_folder_has_an_skf_name(self) -> None:
        # SKF's ownership checks count `.skf-` names as its own output, so a
        # folder named otherwise would make drop and rename refuse the skill.
        assert ".skf-" in _feeder_name()

    def test_doc_rot_locates_the_folder_step_3b_keeps(self) -> None:
        locate = _section(_read(STEP_DOC_ROT), "### §1.", "### §2.")
        item = next(line for line in locate.splitlines() if line.startswith("3. "))
        assert f"`{{forge_data_folder}}/{{skill-name}}/{_feeder_name()}/*.md`" in item

    def test_doc_rot_scan_passes_the_same_folder(self) -> None:
        grep = _section(_read(STEP_DOC_ROT), "### §2.", "### §3.")
        command = _section(grep, "```bash", "\n```")
        assert f'"{{forge_data_folder}}/{{skill-name}}/{_feeder_name()}/"*.md' in command

    def test_nothing_reads_the_old_staging_folder(self) -> None:
        for path in sorted((REPO_ROOT / "src").rglob("*")):
            if path.is_file() and path.suffix in {".md", ".py", ".yaml", ".json"}:
                assert "_bmad-output/{skill-name}-temporal" not in _read(path), path

    def test_skipped_step_expects_no_feeder(self) -> None:
        eligibility = _section(_read(FETCH_TEMPORAL), "### 1. Check Eligibility", "### 1b.")
        assert "**If ANY condition fails, leave `{temporal_feeder}` null" in eligibility

    def test_each_brief_starts_without_a_feeder(self) -> None:
        """A --batch run comes back through step 3b for the next brief in the same context."""
        eligibility = _section(_read(FETCH_TEMPORAL), "### 1. Check Eligibility", "### 1b.")
        reset = eligibility.index("Set `{temporal_feeder}` to null first")
        assert "in a `--batch` run one brief's feeder never carries into the next" in eligibility
        assert reset < eligibility.index("1. **Tier is Deep:**")

    def test_cache_hit_needs_the_feeder_files(self) -> None:
        cache = _section(_read(FETCH_TEMPORAL), "### 2. Check Cache", "### 3.")
        assert (
            "If `{temporal_feeder}` holds no `.md` file, continue to section 3 even when that entry is fresh"
        ) in cache

    def test_each_fetch_starts_a_fresh_fetch_folder(self) -> None:
        fetch = _section(_read(FETCH_TEMPORAL), "### 3. Fetch Temporal Context", "### 4.")
        clear = fetch.index(f'rm -rf "{{forge_data_folder}}/{{skill-name}}/{_fetch_name()}"')
        assert clear < fetch.index('mkdir -p "{temporal_fetch}"\n') < fetch.index("gh issue list")
        writes = _section(fetch, "```bash", "**After all fetching,**")
        assert "{temporal_feeder}" not in writes, "every fetch writes the fetch folder, never the feeder"

    def test_fetch_folder_has_an_skf_name_beside_the_feeder(self) -> None:
        assert ".skf-" in _fetch_name() and _fetch_name() != _feeder_name()

    def test_feeder_is_replaced_only_by_a_fetch_that_wrote_a_file(self) -> None:
        after = _section(_read(FETCH_TEMPORAL), "**After all fetching,**", "### 4.")
        assert (
            "check that at least one `.md` file was written to `{temporal_fetch}`. "
            "If one was, replace the feeder with the fetch folder"
        ) in after
        assert "If none was (all fetches failed), delete the fetch folder" in after
        assert "`{temporal_feeder}` stays bound and keeps what the last good fetch left in it" in after

    def test_folder_deletions_spell_out_their_path(self) -> None:
        """A wrongly bound variable must never widen an `rm -rf` of a whole folder."""
        text = _read(FETCH_TEMPORAL)
        assert re.findall(r'rm -rf "\{[^}"]+\}"(?![^\s`])', text) == []
        group = "{forge_data_folder}/{skill-name}"
        assert text.count(f'rm -rf "{group}/{_fetch_name()}"') == 2
        assert text.count(f'rm -rf "{group}/{_feeder_name()}"\n') == 1

    def test_indexing_keeps_the_feeder(self) -> None:
        index = _section(_read(FETCH_TEMPORAL), "### 4. Index Into QMD", "### 5.")
        assert "rm -rf" not in index, "step 3b must not delete the feeder once it is indexed"
        assert 'qmd collection add "{temporal_feeder}" --name {skill-name}-temporal' in index


class TestTemporalFeederOnDisk:
    """The kept folder is SKF output to the ownership checks and stays out of git."""

    def test_forge_folder_stays_skf_output(self, tmp_path: pathlib.Path) -> None:
        inventory = _load_script(INVENTORY_PY, "skf_skill_inventory_feeder")
        group = _write_forge_group(tmp_path / "forge-data")
        _write_feeder(group)
        result = inventory.classify_forge_group(group, "mylib")
        assert (result["ownership"], result["foreign_entries"]) == ("skf", []), result

    def test_one_folder_for_both_settings_stays_skf_output(self, tmp_path: pathlib.Path) -> None:
        inventory = _load_script(INVENTORY_PY, "skf_skill_inventory_feeder_shared")
        out = tmp_path / "skills"
        group = _write_forge_group(out)
        package = group / "1.0.0" / "mylib"
        package.mkdir()
        (package / "SKILL.md").write_text("---\nname: mylib\n---\n", encoding="utf-8")
        (package / "metadata.json").write_text(
            '{"name": "mylib", "generated_by": "create-skill", "skill_type": "single", '
            '"forge_tier": "Deep"}',
            encoding="utf-8",
        )
        _write_feeder(group)
        check = inventory.write_check(out, "mylib", "1.1.0", out)
        assert (check["verdict"], check["foreign_entries"]) == ("ok", []), check
        scan = inventory.scan_inventory(out, forge_data_folder=out)
        assert [(s["name"], s["ownership"]) for s in scan["skills"]] == [("mylib", "skf")]

    def test_feeder_alone_is_never_foreign(self, tmp_path: pathlib.Path) -> None:
        """A first run interrupted after step 3b leaves only the feeder behind."""
        inventory = _load_script(INVENTORY_PY, "skf_skill_inventory_feeder_alone")
        group = tmp_path / "forge-data" / "mylib"
        _write_feeder(group)
        result = inventory.classify_forge_group(group, "mylib")
        assert (result["ownership"], result["foreign_entries"]) == ("empty", []), result

    def test_interrupted_fetch_folder_stays_skf_output(self, tmp_path: pathlib.Path) -> None:
        """A fetch interrupted before the swap leaves its fetch folder beside the feeder."""
        inventory = _load_script(INVENTORY_PY, "skf_skill_inventory_fetch_folder")
        group = _write_forge_group(tmp_path / "forge-data")
        _write_feeder(group)
        _write_feeder(group, _fetch_name(), ("issues.md",))
        result = inventory.classify_forge_group(group, "mylib")
        assert (result["ownership"], result["foreign_entries"]) == ("skf", []), result

    def test_feeder_keeps_itself_out_of_git(self, tmp_path: pathlib.Path) -> None:
        fetch = _section(_read(FETCH_TEMPORAL), "### 3. Fetch Temporal Context", "### 4.")
        assert "printf '*\\n' > \"{temporal_fetch}/.gitignore\"" in fetch
        project = tmp_path / "project"
        group = project / "forge-data" / "mylib"
        group.mkdir(parents=True)
        (group / "skill-brief.yaml").write_text("name: mylib\n", encoding="utf-8")
        _write_feeder(group)
        _write_feeder(group, _fetch_name())
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        status = subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert status.splitlines() == ["?? forge-data/mylib/skill-brief.yaml"], status

    @POSIX_SHELL
    def test_fetch_that_wrote_a_file_replaces_the_feeder(self, tmp_path: pathlib.Path) -> None:
        after = _section(_read(FETCH_TEMPORAL), "**After all fetching,**", "### 4.")
        swap = _section(after, "```bash\n", "\n```")[len("```bash\n"):]
        forge = tmp_path / "forge-data"
        _write_feeder(forge / "mylib", files=("changelog.md", "stale.md"))
        _write_feeder(forge / "mylib", _fetch_name(), ("issues.md",))
        _run_documented(swap, forge)
        feeder = forge / "mylib" / _feeder_name()
        assert sorted(p.name for p in feeder.iterdir()) == [".gitignore", "issues.md"]
        assert not (forge / "mylib" / _fetch_name()).exists()

    @POSIX_SHELL
    def test_failed_refresh_keeps_the_last_good_feeder(self, tmp_path: pathlib.Path) -> None:
        after = _section(_read(FETCH_TEMPORAL), "**After all fetching,**", "### 4.")
        [command] = re.findall(r"`(rm -rf [^`]+)`", _section(after, "If none was", "\n"))
        forge = tmp_path / "forge-data"
        _write_feeder(forge / "mylib")
        _write_feeder(forge / "mylib", _fetch_name(), ())
        _run_documented(command, forge)
        feeder = forge / "mylib" / _feeder_name()
        assert sorted(p.name for p in feeder.iterdir()) == sorted((".gitignore", *FEEDER_FILES))
        assert not (forge / "mylib" / _fetch_name()).exists()


def _feeder_notice() -> str:
    """The notice step 5c binds when step 3b left no feeder files."""
    notices = NOTICE_BINDING_RE.findall(_read(STEP_DOC_ROT))
    assert len(notices) == 1, f"step-doc-rot.md must bind one notice, found {notices}"
    return notices[0]


class TestTemporalFeederNotice:
    """A Deep run whose temporal feeder is missing says so in the evidence report."""

    def test_notice_only_when_step_3b_expected_a_feeder(self) -> None:
        locate = _section(_read(STEP_DOC_ROT), "### §1.", "### §2.")
        assert "When `{temporal_feeder}` is null" in locate
        assert "When it is set but the folder holds no `.md` file" in locate

    def test_each_brief_starts_without_a_notice(self) -> None:
        """A --batch run comes back through step 5c for the next brief in the same context."""
        locate = _section(_read(STEP_DOC_ROT), "### §1.", "### §2.")
        reset = locate.index("set `{temporal_feeder_notice}` to null")
        assert "in a `--batch` run one brief's notice never carries into the next" in locate
        assert reset < locate.index("When `{temporal_feeder}` is null")

    def test_notice_names_the_folder_it_looked_in(self) -> None:
        notice = _feeder_notice()
        assert f"the skill's {_feeder_name()}/ folder" in notice
        # The evidence report is committed: no path resolved on this machine goes in it.
        assert "{" not in notice, notice

    def test_notice_reaches_the_evidence_report(self) -> None:
        file_6 = _section(_read(GENERATE_ARTIFACTS), "**File 6:**", "**File 7:**")
        assert "`## Remaining Warnings`" in file_6
        assert "`{temporal_feeder_notice}`" in file_6

    def test_notice_reads_as_no_correction(self) -> None:
        """Step 7 writes the notice into the evidence report, itself a doc-rot feeder."""
        scan = _load_script(SCAN_DOC_ROT_PY, "scan_doc_rot_feeder_notice")
        assert scan.scan_text(_feeder_notice(), "evidence-report.md") == []


class TestTemporalCorrectionCitation:
    """A correction drawn from the temporal feeder cites the QMD collection, not a local path."""

    def test_temporal_match_cites_in_the_t2_form(self) -> None:
        annotate = _section(_read(STEP_DOC_ROT), "### §3.", "### §4.")
        assert (
            "except for a match from the temporal feeder (item 3 of §1): cite that file the way "
            "step 4 cites it, in the T2 form `[QMD:{skill-name}-temporal:{file name}]`"
        ) in annotate
        assert "`[QMD:{collection}:{doc}]`" in _read(SKILL_SECTIONS)

    def test_citation_names_the_collection_step_3b_indexes(self) -> None:
        index = _section(_read(FETCH_TEMPORAL), "### 4. Index Into QMD", "### 5.")
        collection = re.search(r'qmd collection add "\{temporal_feeder\}" --name (\S+)', index).group(1)
        annotate = _section(_read(STEP_DOC_ROT), "### §3.", "### §4.")
        assert f"`[QMD:{collection}:{{file name}}]`" in annotate
