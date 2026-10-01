"""Structural integration tests for doc-rot correction hooks (step 5c).

Validates step-doc-rot.md exists with correct frontmatter, the judgment pass
over the scan's candidates (and campaign step 5's record of what it kept),
CORRECTION block format, feeder artifact scan targets, graceful skip logic,
step chain from step-auto-shard.md, and Stages table in SKILL.md.
Also checks the temporal feeder: step 3b (sub/fetch-temporal.md) keeps the
files it fetched in the folder step 5c scans, a failed refresh keeps the last
good copy, a correction drawn from it cites the QMD collection, and a missing
feeder reaches the evidence report as a notice.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import shlex
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
# step-doc-rot.md: the scan's candidates and the judgment pass (§2)
# ---------------------------------------------------------------------------

# The lines #582 reproduced. Each holds a correction keyword, so the scan hands
# it over as a candidate, and none is a live correction, so the judgment pass
# names it as a line to drop.
REPRODUCED_NON_CORRECTIONS = {
    "negation": "No breaking changes in this release.",
    "non-breaking": "Non-breaking: parse() accepts a Path.",
    "bug-fix": "Fixed a bug where the deprecated-warning banner was shown twice.",
    "old-history": "Support for Python 2 was removed in 0.3.",
    "pr-template-checkbox": "(non-breaking change which fixes an issue)",
}


def _scan_section() -> str:
    return _section(_read(STEP_DOC_ROT), "### §2.", "### §3.")


def _judgment_pass() -> str:
    return _section(_scan_section(), "**Judgment pass.**", "**IF `correction_matches` is empty**")


class TestCandidateScan:
    """The script lists candidates; the step never greps by hand."""

    def test_scan_runs_in_the_helper(self) -> None:
        scan = _scan_section()
        assert "uv run {scanDocRotHelper}" in _section(scan, "```bash", "\n```")
        assert "do not hand-grep the feeder artifacts" in scan

    def test_the_documented_call_fits_the_script(self) -> None:
        """test-skf-helper-call-contract.py checks only subcommand helpers, so the
        §2 call runs through the script's own parser here: a flag the script
        dropped (the old `--max-corrections`) fails. The call is split the way the
        shell splits it, with the project under a folder whose name holds a space
        (`First Last`, `My Projects`): an unquoted path would split in two, and the
        script would skip both halves as missing and report no candidate at all."""
        root, forge = "/Users/First Last/proj", "/Users/First Last/proj/forge data"
        command = _section(_scan_section(), "```bash", "\n```")[len("```bash"):]
        command = command.replace("{project-root}", root).replace("{forge_data_folder}", forge)
        words = shlex.split(command.replace("\\\n", " "))
        assert words[:3] == ["uv", "run", "{scanDocRotHelper}"]
        parser = _load_script(SCAN_DOC_ROT_PY, "scan_doc_rot_call")._build_parser()
        args = parser.parse_args(words[3:])
        stage = f"{root}/_bmad-output/.skf-stage/{{skill-name}}"
        assert args.skill_md == f"{stage}/SKILL.md"
        assert args.positional_feeders == [
            f"{stage}/evidence-report.md",
            f"{stage}/provenance-map.json",
            f"{forge}/{{skill-name}}/.skf-temporal/*.md",
        ]

    def test_occurrences_count_keyword_hits(self) -> None:
        """`breaking change` and `BREAKING` are one kind, so the reproduced negation
        collapses into one candidate with two occurrences on the same line."""
        scan = _load_script(SCAN_DOC_ROT_PY, "scan_doc_rot_occurrences")
        hits = scan.scan_text("- No breaking changes in this release.", "changelog.md")
        [candidate], _ = scan.collapse_duplicates(hits)
        assert candidate["occurrences"] == 2
        assert candidate["duplicate_of"] == [{"source": "changelog.md", "line_number": 1}]
        assert (
            "- `occurrences` and `duplicate_of`: how many keyword hits collapsed into this "
            "candidate (two keywords of one kind on one line count twice)"
        ) in _scan_section()

    def test_candidates_carry_a_candidate_category(self) -> None:
        assert "- `candidate_category`: " in _scan_section()
        assert "`category`" not in _read(STEP_DOC_ROT)

    def test_no_rule_forbids_judgment(self) -> None:
        text = _read(STEP_DOC_ROT).lower()
        for phrase in ("no ai judgment", "no semantic", "no regex interpretation"):
            assert phrase not in text, phrase


class TestJudgmentPass:
    """#582: a keyword match is only a candidate; the judgment pass decides."""

    def test_keeps_live_corrections_to_inventory_exports(self) -> None:
        judgment = _judgment_pass()
        assert "1. **It announces a change:**" in judgment
        assert "2. **It is live at `{version}`**" in judgment
        assert "3. **It touches an export in the extraction inventory:**" in judgment
        assert "Set the candidate's `affected` to the export it touches" in judgment

    def test_the_inventory_is_the_staged_provenance_map(self) -> None:
        locate = _section(_read(STEP_DOC_ROT), "### §1.", "### §2.")
        item = next(line for line in locate.splitlines() if line.startswith("2. "))
        assert "`entries[].export_name`" in item
        assert "an `export_name` in the staged provenance map (§1 item 2)" in _judgment_pass()

    @pytest.mark.parametrize(
        "line", list(REPRODUCED_NON_CORRECTIONS.values()), ids=list(REPRODUCED_NON_CORRECTIONS)
    )
    def test_reproduced_line_is_a_candidate_the_pass_drops(self, line: str) -> None:
        scan = _load_script(SCAN_DOC_ROT_PY, "scan_doc_rot_reproduced")
        assert scan.scan_text(f"- {line}", "changelog.md"), "the scan must hand the line over"
        assert f"`{line}`" in _judgment_pass(), "the judgment pass must name the line as a drop"

    def test_drops_restatements_of_the_skill_md_own_api_rows(self) -> None:
        assert "a compiled SKILL.md line that only restates its own API row" in _judgment_pass()

    def test_only_the_project_announces_a_change(self) -> None:
        """Anyone can open an issue, and §3 publishes a kept line word for word."""
        judgment = _judgment_pass()
        assert "The announcement must be the project's own: its changelog, release notes" in judgment
        assert (
            "An issue (`issues.md`, `targeted-issues.md`) is a report anyone can open, so it can "
            "only corroborate such an announcement: drop a candidate that comes from one."
        ) in judgment
        for name in ("issues.md", "targeted-issues.md"):
            assert name in _fetch_helper().FEEDER_FILES, f"step 3b no longer writes {name}"

    def test_keeps_one_correction_per_change(self) -> None:
        """A line with keywords of two kinds is a candidate for each, and release
        notes restate the changelog: one change must not fill two of the 10 blocks."""
        scan = _load_script(SCAN_DOC_ROT_PY, "scan_doc_rot_one_change")
        hits = scan.scan_text("- `parse()` is deprecated and will be removed in 3.0.", "changelog.md")
        candidates, _ = scan.collapse_duplicates(hits)
        assert [c["candidate_category"] for c in candidates] == ["Deprecation", "Removal"]
        judgment = _judgment_pass()
        one = _section(judgment, "**One correction per change.**", "\n\n")
        assert "When passing candidates share `source` and `line_number`, keep the one" in one
        assert "When they announce the same change to the same export from different lines" in one
        assert (
            "(the changelog or release notes, then a merged pull request, then the evidence "
            "report or provenance map, then the compiled SKILL.md)"
        ) in one
        assert judgment.index(one) < judgment.index("the number dropped as `corrections_rejected`")

    def test_the_cap_of_10_applies_after_the_pass(self) -> None:
        scan = _scan_section()
        judgment = scan.index("**Judgment pass.**")
        cap = scan.index("Then cap `correction_matches` at 10 corrections")
        assert judgment < cap < scan.index("`corrections_capped`")
        assert judgment < scan.index("`corrections_rejected`") < cap

    def test_the_cap_ranks_the_skill_md_own_corrections_last(self) -> None:
        """The scan puts the compiled SKILL.md's lines last in its pool, and the cut
        to 10 does the same before it ranks the kinds of change."""
        cap = _section(_scan_section(), "Then cap `correction_matches` at 10 corrections", "\n")
        upstream = cap.index("keep the ones from every other feeder before the compiled SKILL.md's own")
        assert upstream < cap.index("within each group removals, renames and signature changes first")

    def test_blocks_come_only_from_kept_corrections(self) -> None:
        text = _read(STEP_DOC_ROT)
        rules = _section(text, "## Rules", "## MANDATORY SEQUENCE")
        assert "Write a block only for a candidate the §2 judgment pass keeps" in rules
        annotate = _section(text, "### §3.", "### §4.")
        assert "For each entry in `correction_matches`" in annotate
        assert "The list holds only the corrections §2 kept, at most 10" in annotate

    def test_log_reports_what_the_pass_dropped(self) -> None:
        log = _section(_read(STEP_DOC_ROT), "### §4.", "### §5.")
        assert "{corrections_rejected} rejected by the judgment pass" in log
        assert "{corrections_capped} over the cap of 10" in log


CAMPAIGN_SKILL_LOOP = REPO_ROOT / "src" / "skf-campaign" / "references" / "step-05-skill-loop.md"


def _campaign_doc_rot_check() -> str:
    return _section(_read(CAMPAIGN_SKILL_LOOP), "- **Doc-rot check:**", "**Do not hand-grep")


class TestCampaignRecordsKeptCorrections:
    """Campaign step 5 records what step 5c kept, by the fields step 5c writes."""

    def test_reads_the_candidate_category(self) -> None:
        assert "`candidate_category`" in _campaign_doc_rot_check()
        assert "`category`" not in _read(CAMPAIGN_SKILL_LOOP)

    def test_names_only_fields_step_5c_writes(self) -> None:
        fields = re.findall(r"`(\w+)`", _section(_campaign_doc_rot_check(), "each with", ";"))
        assert fields == ["source", "pattern", "candidate_category", "context_line", "affected"]
        scan = _scan_section()
        for field in fields:
            assert f"`{field}`" in scan, field

    def test_records_only_the_kept_corrections(self) -> None:
        check = _campaign_doc_rot_check()
        assert "holds only the corrections step 5c's judgment pass kept" in check
        assert "the candidates the pass rejected are not corrections, so they are never recorded" in check
        assert "`[doc-rot] {affected}: {candidate_category}`" in check


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
        "corrections_rejected",
        "corrections_capped",
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

    MATCH_FIELDS = ["source", "pattern", "candidate_category", "context_line", "affected"]

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
# Temporal feeder: step 3b keeps the files step 5c scans
# ---------------------------------------------------------------------------

FEEDER_BINDING_RE = re.compile(
    r"bind `\{temporal_feeder\}` ← `\{forge_data_folder\}/\{skill-name\}/([^`/]+)`"
)
NOTICE_BINDING_RE = re.compile(r"bind `\{temporal_feeder_notice\}` ← `([^`]+)`")
FEEDER_FILES = ("issues.md", "prs.md", "releases.md", "changelog.md", "targeted-issues.md")
FETCH_TEMPORAL_PY = REPO_ROOT / "src" / "shared" / "scripts" / "skf-fetch-temporal.py"
# One issue, as `gh issue list --json` prints it.
ONE_ISSUE = (
    '[{"number": 1, "title": "t", "state": "OPEN", "labels": [], '
    '"createdAt": "2026-01-01T00:00:00Z", "closedAt": null, "body": ""}]'
)


def _feeder_name() -> str:
    """The folder, inside the skill's forge folder, that step 3b keeps as the feeder."""
    names = FEEDER_BINDING_RE.findall(_read(FETCH_TEMPORAL))
    assert len(names) == 1, f"fetch-temporal.md must bind {{temporal_feeder}} once, found {names}"
    return names[0]


def _fetch_helper():
    """skf-fetch-temporal.py, which step 3b fetches through."""
    return _load_script(FETCH_TEMPORAL_PY, "skf_fetch_temporal_feeder")


def _fetch_name() -> str:
    """The folder beside the feeder that step 3b's helper fetches into before it replaces the feeder."""
    helper = _fetch_helper()
    assert helper.FEEDER_NAME == _feeder_name()
    return helper.FEEDER_NAME + helper.FETCH_SUFFIX


def _fetch_into(feeder: pathlib.Path, monkeypatch, issues: bool) -> tuple[dict, int]:
    """Run step 3b's fetch on `feeder` with a gh that lists one issue (or nothing) and fails every other call."""
    helper = _fetch_helper()

    def gh(args: list[str], _timeout: float) -> tuple[str, str, str]:
        if issues and args[:2] == ["issue", "list"]:
            return "ok", ONE_ISSUE, ""
        return "failed", "", "error connecting to api.github.com"

    monkeypatch.setattr(helper, "_gh", gh)
    return helper.fetch("acme/lib", feeder, None, 5.0)


def _write_feeder(group: pathlib.Path, name: str | None = None,
                  files: tuple[str, ...] = FEEDER_FILES) -> pathlib.Path:
    """What a fetch leaves in `group`: the feeder files and the self-ignoring .gitignore."""
    feeder = group / (name or _feeder_name())
    feeder.mkdir(parents=True)
    (feeder / ".gitignore").write_text("*\n", encoding="utf-8")
    for file_name in files:
        (feeder / file_name).write_text(f"# {file_name}\n", encoding="utf-8")
    return feeder


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
        eligibility = _section(_read(FETCH_TEMPORAL), "### 1. Check Eligibility", "### 2.")
        assert "**If ANY condition fails, leave `{temporal_feeder}` null" in eligibility

    def test_each_brief_starts_without_a_feeder(self) -> None:
        """A --batch run comes back through step 3b for the next brief in the same context."""
        eligibility = _section(_read(FETCH_TEMPORAL), "### 1. Check Eligibility", "### 2.")
        reset = eligibility.index("Set `{temporal_feeder}` to null first")
        assert "in a `--batch` run one brief's feeder never carries into the next" in eligibility
        assert reset < eligibility.index("1. **Tier is Deep:**")

    def test_cache_hit_needs_the_feeder_files(self) -> None:
        cache = _section(_read(FETCH_TEMPORAL), "### 2. Check Cache", "### 3.")
        assert (
            "If `{temporal_feeder}` holds no `.md` file, continue to section 3 even when that entry is fresh"
        ) in cache

    def test_each_fetch_starts_a_fresh_fetch_folder(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        """Step 3b hands the feeder to the helper, which fetches into a fresh folder beside it."""
        fetch = _section(_read(FETCH_TEMPORAL), "### 3. Fetch Temporal Context", "### 4.")
        assert '--feeder "{temporal_feeder}"' in fetch
        group = tmp_path / "forge-data" / "mylib"
        _write_feeder(group, _fetch_name(), ("partial.md",))  # left by an interrupted fetch
        result, code = _fetch_into(group / _feeder_name(), monkeypatch, issues=True)
        assert code == 0, result
        assert not (group / _fetch_name()).exists()
        assert sorted(p.name for p in (group / _feeder_name()).iterdir()) == [".gitignore", "issues.md"]

    def test_fetch_folder_has_an_skf_name_beside_the_feeder(self) -> None:
        assert ".skf-" in _fetch_name() and _fetch_name() != _feeder_name()

    def test_feeder_is_replaced_only_by_a_fetch_that_wrote_a_file(self, tmp_path: pathlib.Path,
                                                                   monkeypatch) -> None:
        """A Deep run passes --exports: with every call failing, the "(fetch
        failed)" search sections are no fetched content, so the feeder stays."""
        fetch = " ".join(_section(_read(FETCH_TEMPORAL), "### 3. Fetch Temporal Context", "### 4.").split())
        assert "`{temporal_feeder}` stays bound and keeps what the last good fetch left in it" in fetch
        group = tmp_path / "forge-data" / "mylib"
        feeder = _write_feeder(group)
        before = {p.name: p.read_bytes() for p in feeder.iterdir()}
        helper = _fetch_helper()
        monkeypatch.setattr(helper, "_gh", lambda args, timeout: ("failed", "", "error connecting to api.github.com"))
        result, code = helper.fetch("acme/lib", feeder, ["parse", "draw"], 5.0)
        assert (code, result["status"]) == (3, "kept")
        assert {p.name: p.read_bytes() for p in feeder.iterdir()} == before

    def test_folder_deletions_spell_out_their_path(self, tmp_path: pathlib.Path) -> None:
        """A wrongly bound variable must never widen a deletion: the step deletes
        no folder itself, and the helper deletes only a feeder named
        .skf-temporal and the fetch folder beside it."""
        assert "rm -rf" not in _read(FETCH_TEMPORAL)
        group = tmp_path / "forge-data" / "mylib"
        _write_feeder(group, "temporal")
        assert _fetch_helper().main(["fetch", "--repo", "acme/lib", "--feeder", str(group / "temporal")]) == 2
        assert sorted(p.name for p in (group / "temporal").iterdir()) == sorted((".gitignore", *FEEDER_FILES))

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

    def test_feeder_keeps_itself_out_of_git(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        project = tmp_path / "project"
        group = project / "forge-data" / "mylib"
        _fetch_into(group / _feeder_name(), monkeypatch, issues=True)
        assert (group / _feeder_name() / ".gitignore").read_bytes() == b"*\n"
        (group / "skill-brief.yaml").write_text("name: mylib\n", encoding="utf-8")
        _write_feeder(group, _fetch_name())  # an interrupted fetch starts with the same .gitignore
        subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
        status = subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert status.splitlines() == ["?? forge-data/mylib/skill-brief.yaml"], status

    def test_fetch_that_wrote_a_file_replaces_the_feeder(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        group = tmp_path / "forge-data" / "mylib"
        _write_feeder(group, files=("changelog.md", "stale.md"))
        result, code = _fetch_into(group / _feeder_name(), monkeypatch, issues=True)
        assert (code, result["status"]) == (0, "replaced")
        feeder = group / _feeder_name()
        assert sorted(p.name for p in feeder.iterdir()) == [".gitignore", "issues.md"]
        assert not (group / _fetch_name()).exists()

    def test_failed_refresh_keeps_the_last_good_feeder(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        group = tmp_path / "forge-data" / "mylib"
        _write_feeder(group)
        result, code = _fetch_into(group / _feeder_name(), monkeypatch, issues=False)
        assert (code, result["status"]) == (3, "kept")
        feeder = group / _feeder_name()
        assert sorted(p.name for p in feeder.iterdir()) == sorted((".gitignore", *FEEDER_FILES))
        assert not (group / _fetch_name()).exists()


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
        """Step 7 promotes the staged evidence report as it is, so step 6 writes the notice into it."""
        report = _section(_read(VALIDATE_FILE), "### 8. Update Evidence Report", "```markdown")
        assert "under `## Remaining Warnings`" in report
        assert "`{temporal_feeder_notice}` when step 5c set it" in report
        assert "{temporal_feeder_notice}" not in _read(GENERATE_ARTIFACTS)

    def test_notice_reads_as_no_correction(self) -> None:
        """Step 6 writes the notice into the evidence report, itself a doc-rot feeder."""
        scan = _load_script(SCAN_DOC_ROT_PY, "scan_doc_rot_feeder_notice")
        assert scan.scan_text(_feeder_notice(), "evidence-report.md") == []


class TestTemporalCorrectionCitation:
    """A correction cites its feeder in a form the published skill's reader can
    follow (the QMD collection for the temporal feeder), never a local path."""

    def test_temporal_match_cites_in_the_t2_form(self) -> None:
        annotate = _section(_read(STEP_DOC_ROT), "### §3.", "### §4.")
        assert (
            "**A match from the temporal feeder** (item 3 of §1): cite that file the way "
            "step 4 cites it, in the T2 form `[QMD:{skill-name}-temporal:{file name}]`"
        ) in annotate
        assert "`[QMD:{collection}:{doc}]`" in _read(SKILL_SECTIONS)

    def test_staged_match_cites_its_annotation_or_file_name(self) -> None:
        """The script reports a feeder by the path the §2 call gave it, and the
        call gives the staged feeders their {project-root} path: an absolute
        path on this machine that must never reach a published skill."""
        annotate = _section(_read(STEP_DOC_ROT), "### §3.", "### §4.")
        assert "`{source}` cites the feeder the line came from, never the path in the match's `source`" in annotate
        cite = _section(annotate, "- **A match from a staged feeder** (items 1, 2 and 4 of §1)", "\n")
        assert "cite the `[QMD:...]` or `[DOC:...]` annotation on its line when it has one" in cite
        assert "never its `{project-root}` path" in cite
        call = _section(_scan_section(), "```bash", "\n```")
        staged = re.findall(r'"\{project-root\}/_bmad-output/\.skf-stage/\{skill-name\}/([^"/]+)"', call)
        assert sorted(staged) == ["SKILL.md", "evidence-report.md", "provenance-map.json"]
        for name in staged:
            assert f"`{name}`" in cite, f"no file name to cite for {name}"

    def test_citation_names_the_collection_step_3b_indexes(self) -> None:
        index = _section(_read(FETCH_TEMPORAL), "### 4. Index Into QMD", "### 5.")
        collection = re.search(r'qmd collection add "\{temporal_feeder\}" --name (\S+)', index).group(1)
        annotate = _section(_read(STEP_DOC_ROT), "### §3.", "### §4.")
        assert f"`[QMD:{collection}:{{file name}}]`" in annotate


class TestCitationRule:
    """#605 architecture-4: the always-loaded rule names every citation the
    stages write, so a docs-only skill (T3 only) is citable."""

    FORMS = ("[AST:]", "[SRC:]", "[QMD:]", "[EXT:]")

    def test_overview_states_the_rule_in_provenance_terms(self) -> None:
        overview = _section(_read(CS_SKILL_MD), "## Overview", "\n## ")
        assert "must trace to source code" not in overview
        assert "every statement in the output carries a provenance citation" in overview
        # The forms are listed once, in the Workflow Rules.
        assert not any(f"`{form}`" in overview for form in self.FORMS)

    def test_workflow_rule_matches_compile(self) -> None:
        rules = _section(_read(CS_SKILL_MD), "## Workflow Rules", "\n## ")
        assert "cannot be cited to source code" not in rules
        [rule] = [line for line in rules.splitlines() if "provenance citation" in line]
        assert all(f"`{form}`" in rule for form in self.FORMS), rule
        assert "Do not include any content without a provenance citation" in _read(CS_DIR / "references" / "compile.md")

    def test_every_form_is_one_a_stage_writes(self) -> None:
        """Each form the rule names is a row of the citation table compile
        follows, and the rule names no form that table lacks."""
        rules = _section(_read(CS_SKILL_MD), "## Workflow Rules", "\n## ")
        [rule] = [line for line in rules.splitlines() if "provenance citation" in line]
        table = _section(_read(SKILL_SECTIONS), "### Provenance Citation Format", "\n### ")
        for form in re.findall(r"`(\[[A-Z]+:\])`", rule):
            assert f"`{form[:-1]}" in table, form
        assert sorted(re.findall(r"`(\[[A-Z]+:\])`", rule)) == sorted(self.FORMS)
