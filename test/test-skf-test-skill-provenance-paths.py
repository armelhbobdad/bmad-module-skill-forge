#!/usr/bin/env python3
"""Prose pins: test-skill reads the version folder and scores stack wiring evidence.

create-skill and create-stack-skill write `provenance-map.json` and
`evidence-report.md` to `{forge_version}`, the skill's version folder in the
forge data, and the flat-to-versioned migration moves an older copy there.
These tests keep test-skill's step files on that layout (#526):
- every read site (source access State 2, the coverage stack denominator
  and Cluster-B count, the Migration & Deprecation gate, the external
  validators' reuse check) names `{forge_version}` first and the flat
  `{forge_data_folder}/{skill_name}/` path only as the fallback for when
  the versioned file does not exist;
- no test-skill file names either flat path any other way, in either
  spelling of the flat folder;
- the gate and the reuse check bind the same `{forge_evidence_report}`, the
  awk detection contract reads that binding, and the command extracts the
  pinned count from a real evidence report.

They also keep coherence-check section 5 on the integration entries
create-stack-skill emits (#544): only the cross-cutting and library-pair
entries are integration points, the first criterion accepts the wiring
evidence of the stack's mode (file:line citations and key files in code
mode, a `[from skill: ...]` line citing each constituent's exports in
compose mode, whatever the constituent's type) and needs no fenced code
block, scoring-rules.md says the same, and the producer formats the
criterion names are pinned, so a change there fails here.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
TEST_SKILL = SRC / "skf-test-skill"
REFS = TEST_SKILL / "references"
MIGRATION = REFS / "migration-section-rules.md"
EXTERNAL = REFS / "external-validators.md"
SOURCE_ACCESS = REFS / "source-access-protocol.md"
COVERAGE = REFS / "coverage-check.md"
COHERENCE = REFS / "coherence-check.md"
SCORING = REFS / "scoring-rules.md"
CREATE_ARTIFACTS = SRC / "skf-create-skill" / "references" / "generate-artifacts.md"
SKILL_SECTIONS = SRC / "skf-create-skill" / "assets" / "skill-sections.md"
STACK = SRC / "skf-create-stack-skill"
STACK_OUTPUT = STACK / "references" / "generate-output.md"
COMPOSE_RULES = STACK / "references" / "compose-mode-rules.md"
DETECT_INTEGRATIONS = STACK / "references" / "detect-integrations.md"
COMPILE_STACK = STACK / "references" / "compile-stack.md"
STACK_TEMPLATE = STACK / "assets" / "stack-skill-template.md"
VERSION_PATHS = SRC / "knowledge" / "version-paths.md"

PROVENANCE = "provenance-map.json"
EVIDENCE = "evidence-report.md"
FALLBACK = "only when that file does not exist, the flat-layout"
OLDER_SKILL = "where an older skill may still keep it"
BIND_EVIDENCE = "Bind `{forge_evidence_report}` to the first of the two that exists"
# The only file test-skill may read from the flat group folder: the brief
# stays there in the versioned layout (knowledge/version-paths.md).
GROUP_LEVEL = {"skill-brief.yaml"}
# Step files spell the flat folder both ways: `{forge_data_folder}/{skill_name}/`
# and, for the brief, the literal `forge-data/{skill_name}/`.
FLAT_PATH_RE = re.compile(r"(?:\{forge_data_folder\}|forge-data)/\{skill_name\}/([A-Za-z0-9_.{}-]+)")

# The compose-mode evidence rule, word for word in coherence-check section 5
# and scoring-rules.md: it fits every constituent type, since a stack composed
# from reference-app or docs-only skills cites contracts, not signatures.
COMPOSE_EVIDENCE = (
    "one `[from skill: {skill name}]` line for each constituent skill the entry joins, citing something that skill "
    "exports. For a skill that exports functions, that is an exported function signature, the "
    "`[from skill: {skill name}] {exported_function_signature}` line of the Integration Evidence Format in "
    "`skf-create-stack-skill/references/compose-mode-rules.md`. For any other constituent (a skill whose "
    "`scope_type` is `reference-app` or `docs-only`, or whose exports are not functions), it is the export, pattern "
    "surface or documented contract the line quotes. A `[from skill: …]` line that cites nothing the skill "
    "exports does not count."
)

# (file, start marker, end marker, artifact): the sections that read a
# provenance map or an evidence report.
READ_SITES = [
    (SOURCE_ACCESS, "Local absent, provenance-map exists:**", "**Cross-reference with metadata.json:**", PROVENANCE),
    (COVERAGE, "### 2b. Zero-Exports Guard", "### 2c.", PROVENANCE),
    (COVERAGE, "**Cluster B", "**Delegate the drift arithmetic", PROVENANCE),
    (MIGRATION, "## Gate Check", "## Scope of Section 4b", EVIDENCE),
    (EXTERNAL, "### 1b. Check for Recent Validation Results", "**Staleness check:**", EVIDENCE),
]
READ_SITE_IDS = ["state-2", "stack-denominator", "cluster-b", "migration-gate", "validator-reuse"]


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str) -> str:
    assert text.count(start) == 1, f"start marker not found exactly once: {start!r}"
    i = text.index(start)
    j = text.find(end, i + len(start))
    assert j != -1, f"end marker {end!r} not found after {start!r}"
    section = text[i:j]
    assert section.strip(), f"empty slice between {start!r} and {end!r}"
    return section


def _flow(text: str) -> str:
    """The text with each run of whitespace folded to one space, so a hard-wrapped sentence reads as one line."""
    return re.sub(r"\s+", " ", text)


def _versioned(name: str) -> str:
    return f"`{{forge_version}}/{name}`"


def _flat(name: str) -> str:
    return f"`{{forge_data_folder}}/{{skill_name}}/{name}`"


def _fence(text: str, needle: str) -> str:
    """The fenced block that holds `needle`."""
    i = text.index(needle)
    open_ = text.rindex("```", 0, i)
    body = text.index("\n", open_) + 1
    block = text[body:text.index("```", body)]
    assert needle in block, f"{needle!r} is not inside a fenced block"
    return block


def _coherence_5() -> str:
    return _slice(_read(COHERENCE), "### 5. Contextual Mode: Check Integration Pattern Completeness", "### 5b.")


# --------------------------------------------------------------------------
# #526: provenance map and evidence report come from the version folder
# --------------------------------------------------------------------------


def test_producers_write_both_files_to_the_version_folder():
    create = _read(CREATE_ARTIFACTS)
    stack = _read(STACK_OUTPUT)
    for name in (PROVENANCE, EVIDENCE):
        assert _versioned(name) in create
        assert f"--target {{forge_version}}/{name}" in stack
    migration = _slice(_read(VERSION_PATHS), "## Migration: Flat to Versioned", "**Migration preserves all content**")
    assert "Move provenance-map.json, evidence-report.md, extraction-rules.yaml, test-report into `{forge_version}`" \
        in migration


@pytest.mark.parametrize("path, start, end, name", READ_SITES, ids=READ_SITE_IDS)
def test_read_site_names_the_version_folder_first(path, start, end, name):
    section = _flow(_slice(_read(path), start, end))
    versioned, flat = _versioned(name), _flat(name)
    assert section.count(flat) == 1, f"the flat path must appear once, as the fallback: {path.name}"
    assert section.count(versioned) == 1, f"the versioned path must appear once: {path.name}"
    # Versioned first; the flat path only when the versioned file is missing,
    # and every site says why the flat path is still read.
    assert section.index(versioned) < section.index(FALLBACK) < section.index(flat) < section.index(OLDER_SKILL)
    # One sentence carries the whole rule: nothing ends it between the two paths.
    between = section[section.index(versioned):section.index(flat)]
    assert ". " not in between.replace("e.g. ", ""), f"the fallback is not in the versioned path's sentence: {between!r}"


def test_no_test_skill_file_reads_a_flat_artifact_any_other_way():
    """Every flat-layout path in test-skill is a fallback behind its versioned twin."""
    hits = []
    for path in sorted(TEST_SKILL.rglob("*.md")):
        text = _flow(_read(path))
        for match in FLAT_PATH_RE.finditer(text):
            name = match.group(1).rstrip(".,")
            if name in GROUP_LEVEL:
                continue
            before = text[max(0, match.start() - 200):match.start()]
            if name not in (PROVENANCE, EVIDENCE) or _versioned(name) not in before or FALLBACK not in before:
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {match.group(0)}")
    assert hits == []


def test_every_flat_fallback_is_a_listed_read_site():
    """READ_SITES holds every flat path in test-skill, so none escapes the ordering check above."""
    found = Counter()
    for path in sorted(TEST_SKILL.rglob("*.md")):
        for match in FLAT_PATH_RE.finditer(_read(path)):
            found[match.group(1).rstrip(".,")] += 1
    for name in GROUP_LEVEL:
        found.pop(name, None)
    assert found == Counter(name for *_, name in READ_SITES)


@pytest.mark.parametrize("path, start, end", [
    (MIGRATION, "## Gate Check", "## Scope of Section 4b"),
    (EXTERNAL, "### 1b. Check for Recent Validation Results", "**Staleness check:**"),
], ids=["migration-gate", "validator-reuse"])
def test_evidence_readers_bind_one_name(path, start, end):
    section = _flow(_slice(_read(path), start, end))
    assert BIND_EVIDENCE in section
    assert section.index(_flat(EVIDENCE)) < section.index(BIND_EVIDENCE)


def test_awk_detection_contract_reads_the_bound_report():
    text = _read(MIGRATION)
    rules = _slice(text, "## Case Rules", "### Case 1")
    block = _fence(rules, "awk '")
    assert "{forge_evidence_report}" in block
    assert EVIDENCE not in block, "the command reads the report the gate bound, never a literal path"
    assert "{forge_data_folder}" not in block and "{forge_version}" not in block
    assert "the detection contract below reads it" in _flow(_slice(text, "## Gate Check", "## Scope of Section 4b"))


def _awk_program() -> str:
    block = _fence(_read(MIGRATION), "awk '")
    match = re.search(r"awk '([^']+)' \\\n\s*\{forge_evidence_report\}", block)
    assert match, f"awk command shape changed: {block!r}"
    return match.group(1)


@pytest.mark.skipif(shutil.which("awk") is None, reason="awk is not installed")
@pytest.mark.parametrize("report, expected", [
    ("---\nskill_name: demo\nt2_future_count: 3\n---\n\n# Evidence\n", "3"),
    ("---\nt2_future_count: 0\n---\nt2_future_count: 7\n", "0"),
    # No frontmatter: Case 4, never a count read from the body.
    ("# Evidence\n\nt2_future_count: 5\n", ""),
    # Frontmatter without the pinned field: Case 4 as well.
    ("---\nskill_name: demo\n---\nt2_future_count: 2\n", ""),
], ids=["pinned", "pinned-zero", "no-frontmatter", "field-absent"])
def test_awk_detection_contract_extracts_the_pinned_count(tmp_path, report, expected):
    path = tmp_path / "1.2.0" / EVIDENCE
    path.parent.mkdir()
    # LF bytes, as SKF's atomic writer leaves them on every OS. write_text
    # would write CRLF on Windows, where Git's MSYS awk reads bytes as they
    # are, so `---\r` would never match /^---$/ and every count would read "".
    path.write_bytes(report.encode("utf-8"))
    result = subprocess.run(["awk", _awk_program(), str(path)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected


def test_line_check_already_reads_the_version_folder():
    """Section 4c, the other provenance read in the same stage, stays on the version folder."""
    section = _slice(_read(COVERAGE), "### 4c. Provenance Line Check", "### 5. Append Coverage Analysis")
    assert "--provenance {forge_version}/provenance-map.json" in section
    assert "{forge_data_folder}" not in section


# --------------------------------------------------------------------------
# #544: stack integration completeness counts the wiring evidence of its mode
# --------------------------------------------------------------------------


def test_criterion_one_reads_wiring_evidence_not_code_examples():
    section = _coherence_5()
    criteria = re.findall(r"^- \*\*(.+?)\*\*", section.split("**Wiring evidence (first criterion).**")[0], re.M)
    assert criteria == [
        "All documented integration points carry the wiring evidence of the stack's mode",
        "Shared types are consistently used across referenced components",
        "Middleware/plugin chains show complete flow, not fragments",
        "Event handlers reference valid event types",
    ]
    for path in sorted(TEST_SKILL.rglob("*.md")):
        assert "corresponding code examples" not in _read(path), path.name


def test_only_pattern_entries_are_integration_points():
    """The hub summaries repeat the pair entries, so counting them would score one link twice."""
    points = _slice(_flow(_coherence_5()), "**Integration points.**", "**Wiring evidence (first criterion).**")
    assert ("Each Cross-Cutting Patterns entry and each Library Pair Integrations entry in the stack's Integration "
            "Patterns section is one integration point, and `patterns_documented` counts them.") in points
    assert ("The Hub Library Connections list that create-stack-skill adds after them only summarizes each hub "
            "library's partners, so its bullets are not integration points: this section does not score them and "
            "`patterns_documented` does not count them.") in points


def test_criterion_one_defines_the_evidence_of_each_mode():
    section = _flow(_coherence_5())
    wiring = _slice(section, "**Wiring evidence (first criterion).**", "Build integration completeness findings:")
    # The mode comes from the markers create-stack-skill puts on every compose-mode integration.
    for marker in ("`[composed]`", "`[composed, +T2 annotations]`", "`[inferred from shared domain]`"):
        assert marker in wiring
    assert "otherwise it is code-mode" in wiring
    code = _slice(wiring, "- **Code mode:**", "- **Compose mode:**")
    assert "at least one `file:line` citation" in code and "a `**Key files:**` line that names at least one file" in code
    compose = _slice(wiring, "- **Compose mode:**", "A fenced code block")
    assert COMPOSE_EVIDENCE in compose
    assert "A fenced code block is not required in either mode" in wiring
    assert "a code block does not stand in for missing evidence" in wiring
    assert "`incomplete_patterns` issue" in wiring
    assert "`no [from skill: …] line for {skill name}`" in wiring


def test_cited_producer_files_exist():
    wiring = _slice(_flow(_coherence_5()), "**Wiring evidence (first criterion).**", "Build integration completeness")
    cited = re.findall(r"`(skf-[a-z-]+/references/[a-z-]+\.md)`", wiring)
    assert cited == ["skf-create-stack-skill/references/compose-mode-rules.md"]
    assert all((SRC / path).is_file() for path in cited)


def test_producer_formats_match_the_criterion():
    rules = _read(COMPOSE_RULES)
    evidence = _slice(rules, "## Integration Evidence Format", "## Feasibility Report Integration")
    assert "[from skill: {Skill A name}] {exported_function_signature}" in evidence
    assert "[from skill: {Skill B name}] {exported_function_signature}" in evidence
    # The markers section 5 reads, pinned by the rule rather than by an example
    # label: the examples follow the tier matrix, which may change.
    assert "Compose-mode integrations add suffix: `[composed]`" in rules
    assert "`[inferred from shared domain]`" in rules
    assert ("The `[composed]`/`[inferred from shared domain]` suffix from `{composeModeRulesPath}` is appended "
            "after the qualifier in compose-mode.") in _read(DETECT_INTEGRATIONS)
    # The two scope types the compose rule names are values create-skill writes to metadata.json.
    scope_lines = [line for line in _read(SKILL_SECTIONS).splitlines() if '"scope_type":' in line]
    assert len(scope_lines) == 1 and "reference-app" in scope_lines[0] and "docs-only" in scope_lines[0]
    # The entries section 5 scores, and the hub summaries it leaves out.
    compile_3 = _slice(_read(COMPILE_STACK), "### 3. Compile Integration Layer", "### 4.")
    for part in ("**Cross-cutting patterns**", "**Library pair integrations:**", "**Hub library connections:**"):
        assert part in compile_3
    patterns = _slice(_read(STACK_TEMPLATE), "## Integration Patterns", "## Library Reference Index")
    assert "### Cross-Cutting Patterns" in patterns and "### Library Pair Integrations" in patterns
    # Code mode: a pair entry carries citations and key files, and has no code-example slot.
    assert "Pattern description with file:line citations" in compile_3
    assert "Key files demonstrating the integration" in compile_3
    entry = _slice(_read(STACK_TEMPLATE), "#### {LibraryA} + {LibraryB}", "## Library Reference Index")
    for field in ("**Type:** {pattern_type}", "**Pattern:** {description}", "**Key files:** {file_list}",
                  "**Confidence:**"):
        assert field in entry
    assert "```" not in entry


def test_scoring_rules_say_the_same():
    section = _flow(_slice(_read(SCORING), "## Coherence Score Aggregation (Contextual Mode)", "## Result Determination"))
    # "This is the documented contract" still follows the formula it refers to.
    assert ("If no integration patterns exist, combined coherence equals reference validity. "
            "This is the documented contract.") in section
    assert ("A pattern is one entry under Cross-Cutting Patterns or Library Pair Integrations in the stack's "
            "Integration Patterns section; the Hub Library Connections summaries are not patterns.") in section
    assert "integration-completeness criteria in `references/coherence-check.md` §5" in section
    assert "the wiring evidence the stack's mode records, not a code example" in section
    assert "In a code-mode stack, the evidence is `file:line` citations and key files." in section
    assert f"In a compose-mode stack, it is {COMPOSE_EVIDENCE}" in section
    assert "A fenced code block is not required." in section
