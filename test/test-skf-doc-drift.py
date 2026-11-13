"""Structural integration tests for the doc-drift.md step file (story 1.4).

Validates the doc-drift step contract: correct pipeline wiring, required
sections, graceful failure rules, the order each route writes the drift
report's sections in, and stages-table placement in the AS workflow.

The step file was step-doc-drift.md (#600, BMad Builder architecture-9): its
siblings are named by their content, so it is doc-drift.md, and every file,
SKILL.md's Stages row and chain sentence included, points at that name. The
old file is gone.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
AS_DIR = REPO_ROOT / "src" / "skf-audit-skill"
STEP_FILE = AS_DIR / "references" / "doc-drift.md"
SEVERITY_CLASSIFY_FILE = AS_DIR / "references" / "severity-classify.md"
REPORT_FILE = AS_DIR / "references" / "report.md"
SKILL_MD = AS_DIR / "SKILL.md"
DRIFT_REPORT_TEMPLATE = AS_DIR / "assets" / "drift-report-template.md"
INIT_FILE = AS_DIR / "references" / "init.md"


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
    assert STEP_FILE.exists(), "doc-drift.md must exist"
    assert not (AS_DIR / "references" / "step-doc-drift.md").exists(), "the old name is gone"
    for path in sorted(AS_DIR.rglob("*.md")):
        assert "step-doc-drift" not in _read(path), path.name


# ---------------------------------------------------------------------------
# Pipeline chain values
# ---------------------------------------------------------------------------


class TestPipelineChain:
    def test_severity_classify_points_to_doc_drift(self) -> None:
        assert _next_step_value(SEVERITY_CLASSIFY_FILE) == "doc-drift.md"

    def test_doc_drift_points_to_report(self) -> None:
        assert _next_step_value(STEP_FILE) == "report.md"

    def test_a_docs_only_skill_runs_step_5a_then_step_5(self) -> None:
        """A docs-only skill's chain is init, step 5a, step 5, report: each
        step names the file it loads in place of its usual next step."""
        assert re.search(r"^classifyStepFile: 'severity-classify\.md'$", _frontmatter(STEP_FILE), re.M)
        assert re.search(r"^reportStepFile: 'report\.md'$", _frontmatter(SEVERITY_CLASSIFY_FILE), re.M)
        assert "or `{classifyStepFile}` for a docs-only skill (`{docs_only_skill}`)" in _read(STEP_FILE)
        assert "or `{reportStepFile}` for a docs-only skill (`{docs_only_skill}`)" in _read(
            SEVERITY_CLASSIFY_FILE)

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

    def test_step_6_reads_the_saved_counts(self, text: str) -> None:
        # #1129: no context value carries the counts; step 6 reads the saved file.
        assert "doc_drift_summary" not in text
        flat = re.sub(r"\s+", " ", text)
        assert "Step 6 reads the counts from the saved JSON's `stats`" in flat
        assert "no file tells step 6 this check was skipped" in flat
        assert ("Only after the `## Documentation Drift` section is appended and `'doc-drift'` is in "
                "`stepsCompleted`, load and read fully the next step file.") in flat


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
            r"\|\s*5a\s*\|.*references/doc-drift\.md", stages_section
        ), "Step 5a must reference references/doc-drift.md"

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


# Each route's stage files in run order, from init: the frontmatter key a
# stage names its next file by on that route, when it is not nextStepFile.
ROUTE_KEYS = {
    "default": {},
    "compose": {"init.md": "composeStepFile"},
    "docs-only": {"init.md": "docsOnlyStepFile", "doc-drift.md": "classifyStepFile",
                  "severity-classify.md": "reportStepFile"},
}
DRIFT_SECTIONS = ["## Audit Summary", "## Structural Drift", "## Semantic Drift", "## Severity Classification",
                  "## Documentation Drift", "## Remediation Suggestions", "## Provenance"]
ROUTE_SECTIONS = {
    "default": DRIFT_SECTIONS,
    "compose": DRIFT_SECTIONS,
    "docs-only": ["## Audit Summary", "## Documentation Drift", "## Severity Classification",
                  "## Remediation Suggestions", "## Provenance"],
}


def _route(name: str) -> list[pathlib.Path]:
    """The stage files a route runs after init, in run order, to report.md."""
    files, path = [], INIT_FILE
    while path.name != "report.md":
        key = ROUTE_KEYS[name].get(path.name, "nextStepFile")
        m = re.search(rf"^{key}:\s*'([^']+)'\s*$", _frontmatter(path) or "", re.MULTILINE)
        assert m, f"{path.name} names no {key}"
        path = path.parent / m.group(1)
        assert path not in files, f"{name} route loops at {path.name}"
        files.append(path)
    return files


def _fence_headings(path: pathlib.Path) -> list[str]:
    """The `## ` headings of a stage's markdown fences, each once, in order:
    a stage's fences are alternatives (skipped or written), so a run writes
    each heading once."""
    headings: list[str] = []
    for block in re.findall(r"^[ \t]*```markdown\n(.*?)^[ \t]*```", _read(path), re.MULTILINE | re.DOTALL):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("## ") and line not in headings:
                headings.append(line)
    return headings


class TestDriftReportTemplate:
    """#1129: the template holds only the Audit Summary, which step 6 fills
    in; every stage writes its own section, heading included."""

    @pytest.fixture(scope="class")
    def text(self) -> str:
        return _read(DRIFT_REPORT_TEMPLATE)

    def test_the_only_section_is_the_audit_summary(self, text: str) -> None:
        assert re.findall(r"^## .*$", text, re.MULTILINE) == ["## Audit Summary"]
        assert "Appended by" not in text
        assert text.endswith("| **Total** |       |\n")

    @pytest.mark.parametrize("route", list(ROUTE_SECTIONS))
    def test_each_route_writes_each_heading_once_in_run_order(self, text: str, route: str) -> None:
        written = re.findall(r"^## .*$", text, re.MULTILINE)
        for path in _route(route):
            written += _fence_headings(path)
        assert written == ROUTE_SECTIONS[route], (route, written)


# ---------------------------------------------------------------------------
# Step file frontmatter completeness
# ---------------------------------------------------------------------------


class TestStepFileFrontmatter:
    @pytest.fixture(scope="class")
    def fm(self) -> str:
        result = _frontmatter(STEP_FILE)
        assert result is not None, "doc-drift.md must have frontmatter"
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

    def test_a_failed_comparison_skips_or_halts(self, text: str) -> None:
        # SKILL.md On Activation checks uv and the helper, so the only skip
        # left is a comparison that fails: a skill built from source notes it
        # and goes on, a docs-only skill (whose whole audit this is) halts.
        assert "Doc drift check skipped: the comparison failed ({the first stderr line})." in text
        assert "fetching unavailable" not in text.lower()
        flat = re.sub(r"\s+", " ", text)
        assert ('this comparison is its whole audit, so HALT with **exit 3**, phase `doc-drift:compare`'
                in flat)

    def test_one_row_rule(self, text: str) -> None:
        """One rule says which entries get a row (#600): it no longer says
        both 'ALL entries' and 'only drifted entries'."""
        assert "Include rows for ALL entries" not in text
        assert "only drifted entries appear" not in text
        flat = re.sub(r"\s+", " ", text)
        assert ("Rows, in this order: each `changed` entry with its old and new hash; each `fetch_failed` "
                "entry, with `_(fetch failed: {reason})_` as its New Hash; each `skipped_null_hash` entry, "
                "with `_(not recorded)_` as its Old Hash and `n/a` in the last two columns. An unchanged "
                "entry gets no row, and only the `changed` rows count as drift.") in flat

    def test_the_comparison_is_saved_for_step_5(self, text: str) -> None:
        assert ('uv run {compareDocHashesHelper} compare-hashes "{resolved_skill_package}/metadata.json" '
                '> "{auditDataFolder}/doc-drift.json"') in text
        assert "{skill_path}/metadata.json" not in text

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

    def test_the_saved_stats_hold_every_count(self, text: str) -> None:
        store = text.split("### 5. Store Context and Auto-Proceed", 1)[1]
        stats = re.search(r"`stats` \(([^)]*)\)", store)
        assert stats, "§5 must name the counts step 6 reads from `stats`"
        for field in ("total_tracked", "changed", "unchanged", "fetch_failed", "skipped_null_hash"):
            assert f"`{field}`" in stats.group(1), f"`stats` must hold: {field}"
        assert "skipped_entirely" not in text

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

    @pytest.fixture(scope="class")
    def summary(self, text: str) -> str:
        section = text.split("### 1. Complete Audit Summary", 1)[1].split("### 2.", 1)[0]
        return re.sub(r"\s+", " ", section)

    def test_report_reads_the_saved_comparison(self, text: str, summary: str) -> None:
        # #1129: the counts come from the file step 5a saved, not a context value.
        assert "doc_drift_summary" not in text
        assert ("Include the doc drift counts, the `stats` of `{auditDataFolder}/doc-drift.json`, the comparison "
                "step 5a saved:") in summary
        assert "for a docs-only skill (`{docs_only_skill}`, whose score these changes set)" in summary

    def test_report_mentions_doc_drift_changed(self, text: str) -> None:
        assert re.search(r"changed\s*>", text) or "Doc Drift" in text, (
            "report.md must include conditional logic for doc drift changes"
        )

    def test_report_mentions_fetch_failed(self, text: str) -> None:
        assert "fetch_failed" in text, (
            "report.md must mention fetch_failed doc URLs in summary"
        )

    def test_no_saved_comparison_means_skipped(self, text: str, summary: str) -> None:
        assert "skipped_entirely" not in text
        assert ("If the file does not exist, step 5a skipped the check: no mention in the summary (its "
                "Documentation Drift section already says why)") in summary
