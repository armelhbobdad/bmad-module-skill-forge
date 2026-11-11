#!/usr/bin/env python3
"""Prose pins: test-skill runs its version lookup, lock, drift guard and scans through shared helpers.

create-skill and create-stack-skill write `provenance-map.json` and
`evidence-report.md` to `{forge_version}`, the skill's version folder in the
forge data, and the flat-to-versioned migration moves an older copy there.
test-skill no longer finds either file by hand (#526, #597): init.md §2 runs
`skf-skill-inventory.py resolve` once and binds `{forge_version}`,
`{forge_provenance_map}` and `{forge_evidence_report}` from it (the
versioned file first, the flat copy an older skill may still keep as the
fallback). These tests keep test-skill's step files on those bindings:
- init.md §2 runs the command and binds every value from a field the
  helper really prints, checked against a real run of the helper, which
  also shows the versioned-first order the prose promises;
- every read site (source access State 2, the coverage State 2 surface and
  the metadata loader behind the denominator, the stack denominator and the
  Cluster-B count, the Migration & Deprecation gate) reads its binding and
  names no path; the external validators no longer reuse an evidence
  report's score (#599: skill-check always runs fresh);
- no test-skill file names a flat artifact path, in either spelling of the
  flat folder, and only the §4c line check names the version folder's map;
- the awk detection contract reads `{forge_evidence_report}`, and the
  command extracts the pinned count from a real evidence report;
- `versionPathsKnowledge` is found by an installed-then-src probe order and
  loaded only for the flat-layout migration, and the report's `skillDir`
  is the package §2 bound.

They keep test-skill's other helper adoptions on the commands the helpers
take, and run each prose command against the real helper:
- the run lock (#542, #588): init.md §6a takes `{forge_version}/.test-skill.lock`
  through skf-run-lock.py and takes the run id from it, report.md §4c renews
  it before the result files are written, every HALT after the lock
  releases it (a rule stated before the first HALT of a step file, or at
  the halt), a run the hard gate blocks ends through report.md instead of
  halting, and both ways report.md §7 ends a run release it with the
  command written out; every step after the lock writes the release
  command out in its Halt envelope paragraph, before its first HALT; the
  runtime check comes before the first helper call, and every HALT names a
  halt_reason the envelope schema lists (#593, #594);
- the workspace drift guard (#588 item 4): init.md §5b runs
  skf-check-workspace-drift.py once per source tree instead of git by hand;
- the Quick-tier scan and the workspace layout (#584): coverage-check.md
  §2 loads coverage-check-tiers.md at Quick tier, which runs
  skf-extract-public-api.py --mode quick on the files by path (for a skill
  quick-skill built); coverage-check.md pipes the payload
  stage-helper-payload.py reads from disk into skf-detect-workspaces.py (the
  tree less what the brief's scope.exclude drops, #780), and the source
  access protocol's monorepo tests read the detector's answer.

They keep the scoring inputs scripted (#613, #540, #596): every script of
the coverage and score steps reads the run files the one before it wrote,
by path, in a run folder init.md creates and report.md removes, and the
prose commands run end to end against the real scripts, from the citation
census to compute-score.py reading every score file, the fallback per-file
scan's commands included; the inventory a subagent returns is validated
from its saved file and re-dispatched once before `inventory-invalid` halts
the run; tooling health is `toolingStatus`, never `analysisConfidence`;
scoring-rules.md, customize.toml and SKILL.md keep no copy of the scoring
rules and no override of them; and coverage-check.md stays under the
single-purpose reference budget (#600), its Quick-tier and fallback scans
carved into coverage-check-tiers.md, loaded only by the branch that needs it,
and the text only a few other branches take (States 2 to 4, the scalar and
stack branches and the Denominator Candidates block) carved into
coverage-check-branches.md, each section loaded only from the sentence of
its branch.

They also keep coherence-check section 5 on the integration entries
create-stack-skill emits (#544): only the cross-cutting and library-pair
entries are integration points, the first criterion accepts the wiring
evidence of the stack's mode (file:line citations and key files in code
mode, a `[from skill: ...]` line citing each constituent's exports in
compose mode, whatever the constituent's type) and needs no fenced code
block, section 5 is the one home of that rule (scoring-rules.md points at
it), and the producer formats the criterion names are pinned, so a change
there fails here.

Every slicer asserts its markers, so a renamed heading fails instead of
passing vacuously.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
TEST_SKILL = SRC / "skf-test-skill"
REFS = TEST_SKILL / "references"
INIT = REFS / "init.md"
MIGRATION = REFS / "migration-section-rules.md"
EXTERNAL = REFS / "external-validators.md"
SOURCE_ACCESS = REFS / "source-access-protocol.md"
COVERAGE = REFS / "coverage-check.md"
# The §2 branches most runs never take, carved out of coverage-check.md (#600).
COVERAGE_TIERS = REFS / "coverage-check-tiers.md"
# The text only some other coverage-check branches take, carved out the same way.
COVERAGE_BRANCHES = REFS / "coverage-check-branches.md"
COHERENCE = REFS / "coherence-check.md"
SCORING = REFS / "scoring-rules.md"
# The rules every signature judge compares by (#827, #835): the overload rule and the `difference` tags live there.
SIGNATURE_RULES = REFS / "signature-comparison-rules.md"
INVENTORY_CONTRACT = REFS / "inventory-contract.md"
INVENTORY = SRC / "shared" / "scripts" / "skf-skill-inventory.py"
CREATE_ARTIFACTS = SRC / "skf-create-skill" / "references" / "generate-artifacts.md"
SKILL_SECTIONS = SRC / "skf-create-skill" / "assets" / "skill-sections.md"
STACK = SRC / "skf-create-stack-skill"
STACK_OUTPUT = STACK / "references" / "generate-output.md"
COMPOSE_RULES = STACK / "references" / "compose-mode-rules.md"
DETECT_INTEGRATIONS = STACK / "references" / "detect-integrations.md"
COMPILE_STACK = STACK / "references" / "compile-stack.md"
STACK_TEMPLATE = STACK / "assets" / "stack-skill-template.md"
VERSION_PATHS = SRC / "knowledge" / "version-paths.md"
SKILL_MD = TEST_SKILL / "SKILL.md"
CONTRACT = REFS / "invocation-contract.md"
REPORT = REFS / "report.md"
HARD_GATE = REFS / "step-hard-gate.md"
SCRIPTS = SRC / "shared" / "scripts"
# The script each prose placeholder names, for running a prose command.
PROSE_SCRIPTS = {
    "{runLockHelper}": SCRIPTS / "skf-run-lock.py",
    "{checkWorkspaceDriftHelper}": SCRIPTS / "skf-check-workspace-drift.py",
    "{extractPublicApiHelper}": SCRIPTS / "skf-extract-public-api.py",
    "{detectWorkspacesHelper}": SCRIPTS / "skf-detect-workspaces.py",
    "{stageHelperPayloadScript}": TEST_SKILL / "scripts" / "stage-helper-payload.py",
    "{validateInventoryScript}": TEST_SKILL / "scripts" / "validate-inventory.py",
    "{coverageInputsScript}": TEST_SKILL / "scripts" / "load-coverage-inputs.py",
    "{scoreSignaturesScript}": TEST_SKILL / "scripts" / "score-signatures.py",
    "{reconcileScript}": TEST_SKILL / "scripts" / "reconcile-coverage.py",
    "{coherenceScript}": TEST_SKILL / "scripts" / "check-metadata-coherence.py",
    "{numeratorVerifyScript}": TEST_SKILL / "scripts" / "verify-declared-numerator.py",
    "{scoringScript}": TEST_SKILL / "scripts" / "compute-score.py",
    "{coherenceAggregationScript}": TEST_SKILL / "scripts" / "aggregate-coherence.py",
    "{externalScoreScript}": TEST_SKILL / "scripts" / "combine-external-scores.py",
    "{locateExportSegmentsScript}": TEST_SKILL / "scripts" / "locate-export-segments.py",
    "{gapLedgerScript}": TEST_SKILL / "scripts" / "gap-ledger.py",
    "{scanSkillMdStructureHelper}": SCRIPTS / "skf-scan-skill-md-structure.py",
    "{resultContextScript}": TEST_SKILL / "scripts" / "build-result-context.py",
    "{emitEnvelopeHelper}": SCRIPTS / "skf-emit-result-envelope.py",
}

PROVENANCE = "provenance-map.json"
EVIDENCE = "evidence-report.md"
BINDING = {PROVENANCE: "{forge_provenance_map}", EVIDENCE: "{forge_evidence_report}"}
BOUND_AT_INIT = "init.md §2 bound"
RESOLVE_CMD = ("uv run {skillInventoryHelper} resolve {skillsOutputFolder} --skill {skill_name} "
               "--forge-data-folder {forge_data_folder}")
# The only file test-skill may read from the flat group folder: the brief
# stays there in the versioned layout (knowledge/version-paths.md).
GROUP_LEVEL = {"skill-brief.yaml"}
# Step files spell the flat folder both ways: `{forge_data_folder}/{skill_name}/`
# and, for the brief, the literal `forge-data/{skill_name}/`.
FLAT_PATH_RE = re.compile(r"(?:\{forge_data_folder\}|forge-data)/\{skill_name\}/([A-Za-z0-9_.{}-]+)")
BINDING_RE = re.compile(r"`(\{[a-z_]+\})` ← `([a-z_.]+)`")

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
    (COVERAGE, "### 2b. Resolve the Denominator and Guard Zero Exports", "### 2c.", PROVENANCE),
    (COVERAGE_BRANCHES, "## States 2 to 4", "## Scalar and Stack Branches", PROVENANCE),
    (MIGRATION, "## Gate Check", "## Scope of Section 4b", EVIDENCE),
]
READ_SITE_IDS = ["state-2", "metadata-loader", "state-2-surface", "migration-gate"]


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


def _init_2() -> str:
    return _slice(_read(INIT), "### 2. Validate Skill Exists (version-aware)", "### 3. Validate Frontmatter")


def _frontmatter(path: Path) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", _read(path), re.S)
    assert match, f"{path.name} has no frontmatter"
    return yaml.safe_load(match.group(1))


def _field(obj, dotted: str):
    for part in dotted.split("."):
        assert isinstance(obj, dict) and part in obj, f"the helper prints no `{dotted}`"
        obj = obj[part]
    return obj


# --------------------------------------------------------------------------
# #526, #597: the provenance map and the evidence report come from the helper
# --------------------------------------------------------------------------


def test_producers_write_both_files_to_the_version_folder():
    create = _read(CREATE_ARTIFACTS)
    stack = _read(STACK_OUTPUT)
    for name in (PROVENANCE, EVIDENCE):
        assert _versioned(name) in create
        # The provenance call quotes its target, the evidence report write does not.
        assert any(f"--target {quote}{{forge_version}}/{name}" in stack for quote in ("", '"')), name
    migration = _slice(_read(VERSION_PATHS), "## Migration: Flat to Versioned", "**Migration preserves all content**")
    assert "Move provenance-map.json, evidence-report.md, extraction-rules.yaml, test-report into `{forge_version}`" \
        in migration


def test_init_binds_the_version_paths_from_the_helper():
    section = _init_2()
    assert RESOLVE_CMD in _fence(section, RESOLVE_CMD)
    bindings = dict(BINDING_RE.findall(section))
    for name, field in {
        "{resolved_version}": "chosen_version",
        "{resolved_skill_package}": "skill_package",
        "{forge_version}": "forge_version",
        BINDING[PROVENANCE]: "paths.provenance_map.path",
        BINDING[EVIDENCE]: "paths.evidence_report.path",
    }.items():
        assert bindings.get(name) == field, name
    # A migrated flat skill now has a version folder: bind again from the helper.
    assert "run the `resolve` command above again and bind its values anew" in _flow(section)
    # The helper walks the manifest and the `active` link: the prose no longer does.
    for hand_walk in (".export-manifest.json", "read the `active` symlink", "{skill_group}/active/"):
        assert hand_walk not in section, hand_walk
    for reason in ("`manifest-and-link`", "`manifest`", "`link`", "`manifest-lags-link`", "`newest-on-disk`",
                   "`flat-layout`", "`missing`", "`SKILL_NOT_FOUND`", "`DIR_NOT_FOUND`"):
        assert reason in section, reason


def _versioned_skill(tmp_path: Path, flat_forge: bool) -> tuple[Path, Path]:
    """A skill `demo` at version 1.0.0 named by the export manifest, and its forge folder."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    package = skills / "demo" / "1.0.0" / "demo"
    package.mkdir(parents=True)
    (package / "SKILL.md").write_bytes(b"---\nname: demo\ndescription: Demo. Use when testing.\n---\n")
    (package / "metadata.json").write_bytes(b'{"generated_by": "create-skill", "version": "1.0.0"}\n')
    manifest = {"schema_version": "2", "exports": {"demo": {"active_version": "1.0.0",
                                                           "versions": {"1.0.0": {"status": "active"}}}}}
    (skills / ".export-manifest.json").write_bytes(json.dumps(manifest).encode("utf-8"))
    folder = forge / "demo" if flat_forge else forge / "demo" / "1.0.0"
    folder.mkdir(parents=True)
    (folder / PROVENANCE).write_bytes(b'{"entries": []}\n')
    (folder / EVIDENCE).write_bytes(b"---\nt2_future_count: 0\n---\n")
    return skills, forge


@pytest.mark.parametrize("flat_forge", [False, True], ids=["versioned", "flat-fallback"])
def test_every_binding_reads_a_field_the_helper_prints(tmp_path, flat_forge):
    """Run the helper the way init.md §2 does: each bound field exists, versioned first, flat as the fallback."""
    skills, forge = _versioned_skill(tmp_path, flat_forge)
    result = subprocess.run([sys.executable, str(INVENTORY), "resolve", str(skills), "--skill", "demo",
                             "--forge-data-folder", str(forge)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    resolved = json.loads(result.stdout)["resolve"]
    values = {name: _field(resolved, field) for name, field in BINDING_RE.findall(_init_2())}
    assert Path(values["{forge_version}"]).as_posix() == (forge / "demo" / "1.0.0").as_posix()
    assert Path(values["{resolved_skill_package}"]).as_posix() == (skills / "demo" / "1.0.0" / "demo").as_posix()
    expected = forge / "demo" if flat_forge else forge / "demo" / "1.0.0"
    for name in (PROVENANCE, EVIDENCE):
        assert Path(values[BINDING[name]]).as_posix() == (expected / name).as_posix()
    assert _field(resolved, "reason") == "manifest"


@pytest.mark.parametrize("path, start, end, name", READ_SITES, ids=READ_SITE_IDS)
def test_read_site_reads_the_bound_path(path, start, end, name):
    section = _flow(_slice(_read(path), start, end))
    assert BINDING[name] in section, f"{path.name} must read {BINDING[name]}"
    assert BOUND_AT_INIT in section, f"{path.name} must say where {BINDING[name]} comes from"
    assert _versioned(name) not in section and _flat(name) not in section, "the helper chose the path"


def test_no_test_skill_file_names_a_flat_artifact():
    hits = []
    for path in sorted(TEST_SKILL.rglob("*.md")):
        for match in FLAT_PATH_RE.finditer(_flow(_read(path))):
            if match.group(1).rstrip(".,") not in GROUP_LEVEL:
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {match.group(0)}")
    assert hits == []


def test_only_the_line_check_names_the_version_folders_map():
    """§4c reads the version folder's map on purpose: its lines are the ones update-skill moves."""
    sites = []
    for path in sorted(TEST_SKILL.rglob("*.md")):
        text = _read(path)
        for name in (PROVENANCE, EVIDENCE):
            if f"{{forge_version}}/{name}" in text:
                sites.append((path.name, name))
    assert sites == [("coverage-check.md", PROVENANCE)]
    section = _slice(_read(COVERAGE), "### 4c. Provenance Line Check", "### 5. Write the Coverage Analysis Section")
    assert "--provenance {forge_version}/provenance-map.json" in section
    assert "{forge_data_folder}" not in section


@pytest.mark.parametrize("path, start, end", [
    (MIGRATION, "## Gate Check", "## Scope of Section 4b"),
], ids=["migration-gate"])
def test_evidence_readers_read_the_bound_report(path, start, end):
    section = _flow(_slice(_read(path), start, end))
    assert "`{forge_evidence_report}`" in section and BOUND_AT_INIT in section
    assert "Bind `{forge_evidence_report}`" not in section, "init.md §2 binds it once"


def test_awk_detection_contract_reads_the_bound_report():
    text = _read(MIGRATION)
    rules = _slice(text, "## Case Rules", "### Case 1")
    block = _fence(rules, "awk '")
    assert "{forge_evidence_report}" in block
    assert EVIDENCE not in block, "the command reads the report init.md §2 bound, never a literal path"
    assert "{forge_data_folder}" not in block and "{forge_version}" not in block
    assert "the detection contract below reads it" in _flow(_slice(text, "## Gate Check", "## Scope of Section 4b"))


def test_section_4b_is_the_exact_heading():
    """#1000: the Case Rules detect Section 4b by the exact heading create-skill emits and the other gates match,
    so a migration section under another heading is not Section 4b and two runs cannot read it two ways: with
    T2-future = 0 it raises no Case, and with T2-future > 0 and no such heading it is Case 1. It names both
    matchers, skf-shard-body.py and scan-doc-rot.py, and both read the heading the same way (#1069)."""
    heading = "Migration & Deprecation Warnings"
    rules = _flow(_slice(_read(MIGRATION), "## Case Rules", "**Detection contract.**"))
    assert ("Section 4b is present only when SKILL.md's body has a level-2 heading whose text is exactly "
            f"`{heading}`: the heading `skf-create-skill/assets/compile-assembly-rules.md` has create-skill emit "
            "verbatim, and the one `skf-shard-body.py` and `scan-doc-rot.py` match.") in rules
    assert ("A section under any other heading, such as `## Migration from v1`, is not Section 4b, whatever it "
            "holds: with T2-future = 0 it raises no Case, and with T2-future > 0 and no such heading it is "
            "Case 1.") in rules
    assert "field: this is the authoritative count, not the narrative body." in rules
    assert "Check whether SKILL.md contains" not in rules, "the old wording left the heading rule to the reader"
    # The key the rule names is the one create-skill emits verbatim and skf-shard-body.py matches exactly.
    assembly = _flow(_read(SRC / "skf-create-skill" / "assets" / "compile-assembly-rules.md"))
    assert f"Emit the heading verbatim as `## {heading}`. Downstream gates match that exact text" in assembly
    shard = runpy_module(SCRIPTS / "skf-shard-body.py")
    assert heading in shard.TIER1_HEADINGS
    assert shard.present_tier1([f"## {heading}", "## Migration from v1"]) == {heading}
    assert shard.present_tier1([f"## {heading.lower()} (pre-1.0)"]) == set()
    # #1069: scan-doc-rot.py excludes a section from the doc-rot candidates under exactly the headings that
    # skf-shard-body.py counts, so the rule's sentence names both.
    scan = runpy_module(SRC / "skf-create-skill" / "scripts" / "scan-doc-rot.py")
    variants = [
        f"## {heading}", f"## {heading}   ", f"  ## {heading}", f"##\t{heading}", f"##   {heading}",
        # a 4-space indent and a no-break space after `##` open too, which a CommonMark reader would not take
        f"    ## {heading}", f"## {heading}",
        f"## {heading.lower()}", f"## {heading.upper()}", f"## {heading} (pre-1.0)",
        "## Migration&Deprecation Warnings", "## Migration  &  Deprecation Warnings", f"## {heading} ##",
        f"# {heading}", f"### {heading}", "## Migration from v1",
    ]
    for h in variants:
        opens = scan.migration_section_range(f"{h}\n- old renamed to new\n") is not None
        assert opens == (heading in shard.present_tier1([h])), repr(h)
    assert sum(heading in shard.present_tier1([h]) for h in variants) == 7


def test_case_4_is_an_evidence_report_without_the_pinned_count():
    """#784: Case 4 is reached only when the evidence report exists and pins no usable `t2_future_count` (absent,
    not a non-negative integer, or no frontmatter at all, as in every create-stack-skill report), so its note says
    that and points only a create-skill skill at create-skill, never that the file was not found; a missing report
    stops at the gate with no note, and Case 4 raises no gap."""
    text = _read(MIGRATION)
    case4 = _flow(re.sub(r"^> ?", "", _slice(text, "### Case 4", "## Output"), flags=re.M))
    assert case4.startswith("### Case 4: evidence report has no pinned count ")
    assert "absent or not a non-negative integer, or the report has no frontmatter at all" in case4
    assert "Skip the Case Rules and raise no gap." in case4
    assert ('"Section 4b verification skipped: evidence-report.md pins no `t2_future_count`. For a skill '
            'create-skill made, re-run create-skill to regenerate the report with the field (create-stack-skill '
            'does not write it)."') in case4
    for gone in ("not found", "Skip silently", "skip silently", "predates the field"):
        assert gone not in case4, gone
    bullet = _flow(_slice(text, "- **Frontmatter missing, OR `t2_future_count` absent or not a non-negative",
                          "- **`t2_future_count` a non-negative integer**"))
    assert "(empty, `null`, quoted) → treat as Case 4 (see below)" in bullet and "skip silently" not in bullet
    assert "every stack skill: create-stack-skill's evidence report has no frontmatter" in _flow(text)
    gate = _flow(_slice(text, "## Gate Check", "## Scope of Section 4b"))
    assert ("If either condition fails, skip the check with no note and proceed to the next section: a missing "
            "evidence report is not Case 4.") in gate
    assert "Case 4" not in _read(COHERENCE), "coherence-check records a gap for Cases 1 to 3 only"


def test_the_case_4_note_has_a_line_in_each_coherence_format():
    """#784: the note Case 4 records lands on the Coherence Analysis section's **Migration Section:** line, which
    both the naive and the contextual format give, as an optional line."""
    formats = _read(REFS.parent / "assets" / "output-section-formats.md")
    line = ("**Migration Section:** {the note migration-section-rules.md Case 4 records; leave this line out when it "
            "records none}")
    for mode in ("**Mode:** Naive", "**Mode:** Contextual"):
        block = _fence(formats, mode)
        assert block.startswith("## Coherence Analysis\n") and block.count(line) == 1, mode
    case4 = _flow(_slice(_read(MIGRATION), "### Case 4", "## Output"))
    assert ("Record this note on the Coherence Analysis section's **Migration Section:** line (`{outputFormatsFile}` "
            "gives it in both formats)") in case4
    assert _frontmatter(COHERENCE)["outputFormatsFile"] == "assets/output-section-formats.md"


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
    # #784: a CRLF report reads the same, since the command strips a trailing CR before it matches.
    ("---\r\nskill_name: demo\r\nt2_future_count: 4\r\n---\r\n", "4"),
    # #784: a value that is not a non-negative integer reaches the rule as printed, and Case 4 takes it.
    ("---\nt2_future_count:\n---\n", ""),
    ("---\nt2_future_count: null\n---\n", "null"),
    ("---\nt2_future_count: '3'\n---\n", "'3'"),
], ids=["pinned", "pinned-zero", "no-frontmatter", "field-absent", "crlf", "empty", "null", "quoted"])
def test_awk_detection_contract_extracts_the_pinned_count(tmp_path, report, expected):
    path = tmp_path / "1.2.0" / EVIDENCE
    path.parent.mkdir()
    # The bytes as written: write_text would write CRLF on Windows, and the
    # crlf case writes CRLF on every OS. Git's MSYS awk reads bytes as they
    # are, so the command strips each line's trailing CR before `---` can match.
    path.write_bytes(report.encode("utf-8"))
    result = subprocess.run(["awk", _awk_program(), str(path)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected
    # Only digits are a pinned count; anything else is Case 4.
    assert bool(re.fullmatch(r"[0-9]+", expected)) is (expected in ("3", "0", "4"))


def test_version_paths_knowledge_is_probed_and_loaded_only_to_migrate():
    frontmatter = _frontmatter(INIT)
    assert "versionPathsKnowledge" not in frontmatter, "a bare module path does not resolve when installed"
    assert frontmatter["versionPathsKnowledgeProbeOrder"] == [
        "{project-root}/_bmad/skf/knowledge/version-paths.md",
        "{project-root}/src/knowledge/version-paths.md",
    ]
    body = _read(INIT).split("\n---\n", 1)[1]
    uses = [line for line in body.splitlines() if "{versionPathsKnowledge}" in line]
    assert len(uses) == 1 and "auto-migrate" in uses[0]
    assert 'load only its "Migration: Flat to Versioned" section' in uses[0]
    assert "## Migration: Flat to Versioned" in _read(VERSION_PATHS)


def test_report_skill_dir_is_the_package_init_bound():
    """The architecture-4 handoff: external-validators and coherence-check read `skillDir`."""
    template = _fence(_read(INIT), "workflowType: 'test-skill'")
    assert "skillDir: '{resolved_skill_package}'" in template
    for path in sorted(TEST_SKILL.rglob("*.md")):
        assert "{skill_path}" not in _read(path), path.name
    assert "`skillDir`" in _slice(_read(EXTERNAL), "### 1. Resolve Skill Directory", "### 2.")


def test_skill_check_always_runs_fresh():
    """#599: the evidence-report reuse cache is gone; every test runs skill-check itself."""
    text = _read(EXTERNAL)
    for gone in ("### 1b.", "Auto-Reuse", "Staleness check", "reused from create-skill evidence report",
                 "{forge_evidence_report}", "git log -1", "§1b reused"):
        assert gone not in text, gone
    run = _flow(_slice(text, "### 2. Run skill-check", "### 3."))
    assert "Run skill-check fresh on every test" in run


# --------------------------------------------------------------------------
# Running a prose command
# --------------------------------------------------------------------------


def _run(command: str, values: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a prose command against the real scripts.

    Each `uv run {…}` stage runs this Python on the script its placeholder
    names (PROSE_SCRIPTS), with `values` filled in (keys spelled as the prose
    spells them, `{forge_version}` or `<language>`), and a ` | ` pipes one
    stage's stdout into the next. Returns the last stage's process.
    """
    stdin, proc = b"", None
    for stage in command.split(" | "):
        m = re.fullmatch(r"uv run (\{\w+\})(?: (.*))?", stage.strip())
        assert m, f"not a `uv run {{…}}` stage: {stage!r}"
        rest = m.group(2) or ""
        for key, value in values.items():
            rest = rest.replace(key, value)
        assert not re.search(r"\{\w+\}|<[a-z][^>]*>", rest), f"unfilled placeholder in {rest!r}"
        proc = subprocess.run([sys.executable, str(PROSE_SCRIPTS[m.group(1)]), *shlex.split(rest)], cwd=cwd,
                              input=stdin, capture_output=True, check=False)
        stdin = proc.stdout
    return proc


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    return root


# --------------------------------------------------------------------------
# #542, #588: the run lock
# --------------------------------------------------------------------------


LOCK_ARGS = '--lock "{forge_version}/.test-skill.lock"'
ACQUIRE = f'uv run {{runLockHelper}} acquire {LOCK_ARGS} --owner "test-skill:{{skill_name}}"'
RENEW = f'uv run {{runLockHelper}} acquire {LOCK_ARGS} --owner "{{run_owner}}"'
RELEASE = f'uv run {{runLockHelper}} release {LOCK_ARGS} --owner "{{run_owner}}"'
# Each step after the lock writes the release command out before its first HALT.
STEP_RELEASE = f"It releases the run lock first, whatever the release prints: from `{{project-root}}`, run `{RELEASE}`"
# ... and, headless, prints its envelope through the shared emitter.
EMIT_HALT = ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-test-skill --run-dir "{run_dir}" '
             '--target stderr < "{run_dir}/halt.json"')
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
# Step files after init.md §6a, in stage order. health-check.md is loaded
# after report.md §7 released the lock.
AFTER_THE_LOCK = ["detect-mode.md", "coverage-check.md", "coherence-check.md", "external-validators.md",
                  "step-hard-gate.md", "score.md", "report.md"]


def _lock_values(forge_version: Path, **more: str) -> dict[str, str]:
    return {"{forge_version}": forge_version.as_posix(), "{skill_name}": "demo",
            **{"{" + k + "}": v for k, v in more.items()}}


def test_init_takes_the_lock_and_the_run_id_from_the_helper():
    assert _frontmatter(INIT)["runLockProbeOrder"] == [
        "{project-root}/_bmad/skf/shared/scripts/skf-run-lock.py",
        "{project-root}/src/shared/scripts/skf-run-lock.py",
    ]
    section = _slice(_read(INIT), "**6a. Take the run lock and the run id.**", "**6c. Create `{outputFile}`")
    assert ACQUIRE in _fence(section, ACQUIRE)
    flow = _flow(section)
    assert "Bind `{run_id}` ← `run_id`" in flow and "`{run_owner}` ← `owner`" in flow
    # Taken, refused (another-run-active) and a helper failure are each handled.
    for case in ("`acquired` is true", "`acquired` is false (exit 3)", "The helper exits 1 or 2"):
        assert case in flow, case
    assert 'HALT (`halt_reason: "another-run-active"`, phase `init:run-lock`)' in flow


def test_no_step_file_holds_a_process_lock_or_builds_a_run_id():
    for path in sorted(TEST_SKILL.rglob("*.md")):
        text = _read(path)
        for stale in ("flock", "{pid}", "rand4", "kill -0", "$$", "remains held until the end of this step"):
            assert stale not in text, f"{path.name}: {stale}"


def test_the_prose_lock_commands_serialize_two_runs(tmp_path):
    forge_version = tmp_path / "forge" / "demo" / "1.0.0"  # the helper creates the folders
    assert RELEASE in _slice(_read(SKILL_MD), "## Workflow Rules", "## Stages")

    first = _run(ACQUIRE, _lock_values(forge_version), tmp_path)
    assert first.returncode == 0, first.stderr
    taken = json.loads(first.stdout)
    assert taken["acquired"] is True and RUN_ID_RE.match(taken["run_id"])
    assert taken["owner"] == f"test-skill:demo:{taken['run_id']}"

    second = _run(ACQUIRE, _lock_values(forge_version), tmp_path)
    refused = json.loads(second.stdout)
    assert second.returncode == 3 and refused["acquired"] is False and refused["held_by"] == taken["owner"]

    freed = _run(RELEASE, _lock_values(forge_version, run_owner=taken["owner"]), tmp_path)
    assert freed.returncode == 0 and json.loads(freed.stdout)["released"] is True
    assert not (forge_version / ".test-skill.lock").exists()
    # A halt path may always release: a lock already gone changes nothing.
    again = json.loads(_run(RELEASE, _lock_values(forge_version, run_owner=taken["owner"]), tmp_path).stdout)
    assert (again["released"], again["reason"]) == (False, "absent")


def test_a_release_never_removes_another_runs_lock(tmp_path):
    forge_version = tmp_path / "v"
    assert json.loads(_run(ACQUIRE, _lock_values(forge_version), tmp_path).stdout)["acquired"] is True
    other = "test-skill:demo:20000101T000000Z-00000000"
    kept = json.loads(_run(RELEASE, _lock_values(forge_version, run_owner=other), tmp_path).stdout)
    assert (kept["released"], kept["reason"]) == (False, "not-owner")
    assert (forge_version / ".test-skill.lock").exists()


def test_report_renews_the_lock_before_it_writes_the_result_files(tmp_path):
    contract = _slice(_read(REPORT), "### 4c. Result Contract", "### 5. Finalize Output Document")
    assert RENEW in _fence(contract, RENEW)
    assert contract.index(RENEW) < contract.index("**Publish the report.**") \
        < contract.index("emit --workflow skf-test-skill")
    renewal = _flow(contract[:contract.index("**Publish the report.**")])
    assert "Exit 3" in renewal and "HALT before writing anything" in renewal
    assert '(`halt_reason: "another-run-active"`, phase `report:run-lock`)' in renewal

    forge_version = tmp_path / "v"
    owner = json.loads(_run(ACQUIRE, _lock_values(forge_version), tmp_path).stdout)["owner"]
    renewed = _run(RENEW, _lock_values(forge_version, run_owner=owner), tmp_path)
    assert renewed.returncode == 0 and json.loads(renewed.stdout)["refreshed"] is True
    # Another run took the lock over: the renewal is refused and nothing is written.
    _run(RELEASE, _lock_values(forge_version, run_owner=owner), tmp_path)
    assert _run(ACQUIRE, _lock_values(forge_version), tmp_path).returncode == 0
    taken_over = _run(RENEW, _lock_values(forge_version, run_owner=owner), tmp_path)
    assert taken_over.returncode == 3 and json.loads(taken_over.stdout)["acquired"] is False


def test_each_subagent_dispatch_renews_the_lock(tmp_path):
    """#1044: the coverage reader, the signature judges and the discovery subagents
    all run before report.md §4c, and the lock goes stale 60 minutes after it was
    taken or last renewed, so SKILL.md has the run renew it as each dispatch returns
    and before the discovery subagents start, until report.md §7 releases it. A run
    without subagents does that work in the main thread (coverage-check.md §1 and §2,
    coherence-check.md), so it renews as that work ends."""
    rules = _slice(_read(SKILL_MD), "## Workflow Rules", "## Stages")
    rule = _flow(next((line for line in rules.splitlines() if RENEW in line), ""))
    for needle in ("renew the run lock each time a subagent dispatch returns",
                   "(once for parallel calls sent in one message)",
                   "or, without subagents, the main thread finishes the work a step gives a subagent",
                   "before report.md §4b.2 spawns its discovery subagents",
                   "until report.md §7 releases it", "60 minutes after it was taken or last renewed",
                   "Exit 3 (another run took the lock over) HALTs `another-run-active`",
                   "exit 1 or 2, or no JSON, HALTs `helper-failed`",
                   "phase `<step>:run-lock` (`coverage-check:run-lock`, say)"):
        assert needle in rule, needle
    # Its HALTs come after §6a, so the release rule above it covers them.
    assert rules.index(RELEASE) < rules.index(RENEW)
    assert "report.md §4c renews the lock through it" not in _read(INIT)
    assert "goes stale 60 minutes after it was taken or last renewed" in _flow(_read(REPORT))
    docs = _flow(_slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                        "### Test Skill stops with `another-run-active`", "\n### "))
    assert "`coverage-check:run-lock`" in docs and "one of two points" not in docs
    # The report step renews around its discovery subagents too, under the same phase as §4c's renewal.
    assert "`report:run-lock` around its discovery subagents or just before it writes its results" in docs
    assert "or, without subagents, the main thread finishes a subagent's work" in docs
    init_comments = _flow(_read(INIT).replace("\n#", ""))
    assert "or, without subagents, as the main thread finishes a subagent's work" in init_comments

    # A renewal restarts the window even on a lock past it, so a second run is refused.
    forge_version = tmp_path / "v"
    owner = json.loads(_run(ACQUIRE, _lock_values(forge_version), tmp_path).stdout)["owner"]
    lock = forge_version / ".test-skill.lock"
    lock.write_text(json.dumps({"owner": owner, "acquired_at": "2000-01-01T00:00:00Z",
                                "tool": "skf-run-lock"}) + "\n", encoding="utf-8")
    renewed = _run(RENEW, _lock_values(forge_version, run_owner=owner), tmp_path)
    kept = json.loads(renewed.stdout)
    assert renewed.returncode == 0 and kept["refreshed"] is True and kept["held_since"] != "2000-01-01T00:00:00Z"
    second = _run(ACQUIRE, _lock_values(forge_version), tmp_path)
    assert second.returncode == 3 and json.loads(second.stdout)["held_by"] == owner


def test_each_stage_and_each_by_eye_read_renews_the_lock():
    """#1064: between two subagent returns the main thread can work a long time on
    its own: at Quick tier it reads every entry point by eye, then runs coherence,
    the external validators, the gate and the score before report.md §4b.2. So the
    run also renews as each stage from detect-mode.md to report.md starts and after
    each message of by-eye source reads (the Forge tier's `readByEye` files, State 4,
    a split body), with the same command and HALTs as the other renewal points."""
    skill = _read(SKILL_MD)
    rules = _slice(skill, "## Workflow Rules", "## Stages")
    rule = _flow(next((line for line in rules.splitlines() if RENEW in line), ""))
    by_eye = "each time the main thread finishes reading a source file by eye (once for files read in one message)"
    # The rule names the stages it reaches, as its copies do: none after report.md §7's release.
    stage = "as each stage from detect-mode.md to report.md starts, before its first numbered section"
    assert "as each stage after init.md starts" not in rule
    for needle in (by_eye, stage, "Exit 3 (another run took the lock over) HALTs `another-run-active`",
                   "exit 1 or 2, or no JSON, HALTs `helper-failed`", "phase `<step>:run-lock`"):
        assert needle in rule, needle
    # Both points join the list of renewals, before the discovery subagents' renewal and the command.
    assert rule.index(by_eye) < rule.index("before report.md §4b.2 spawns its discovery subagents") \
        < rule.index(RENEW)
    assert rule.index(stage) < rule.index("before report.md §4b.2 spawns its discovery subagents")
    # The stage clause reaches every stage that runs under the lock: init.md takes it in §6a,
    # report.md §7 releases it before health-check.md loads.
    table = _slice(skill, "## Stages", "## Invocation Contract")
    files = [Path(rel).name for rel in re.findall(r"^\|[^|\n]+\|[^|\n]+\| (references/[\w.-]+\.md) \|", table, re.M)]
    assert files[0] == "init.md" and files[-1] == "health-check.md", files
    assert files[1:-1] == AFTER_THE_LOCK
    # A renewal that halts as a stage starts runs under that stage's Halt envelope, so
    # each of them states one, with the release and the emitter, before its first section.
    for name in AFTER_THE_LOCK:
        body = _read(REFS / name)
        first = re.search(r"^### §?\d", body, re.M)
        assert first, name
        head = body[:first.start()]
        assert "**Halt envelope.**" in head and STEP_RELEASE in head, name
        assert EMIT_HALT in head, name
    # The contract, the user docs and the init comment name both points, the stage
    # starts ending at report.md: no renewal retakes the lock once §7 released it.
    row = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Concurrency** |"))
    for needle in ("each time the main thread finishes reading source files by eye",
                   "as each stage from detect-mode.md to report.md starts"):
        assert needle in row, needle
    docs = _flow(_slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                        "### Test Skill stops with `another-run-active`", "\n### "))
    for needle in ("because one subagent ran 180 minutes, or the main thread's own work 60 minutes, past its last renewal",
                   "the run renews its lock as each step before the health check starts, after it reads source "
                   "files by eye,",
                   # A renewal that fails as a step starts halts under that step's phase.
                   "`<step>:run-lock` as a step starts or while it runs"):
        assert needle in docs, needle
    init_comments = _flow(_read(INIT).replace("\n#", ""))
    for needle in ("renew the lock through it as each stage from detect-mode.md to report.md starts",
                   "and after each by-eye read of source files"):
        assert needle in init_comments, needle


def test_each_dispatch_renews_the_lock_for_180_minutes(tmp_path):
    """#1086: the main thread can run nothing while one foreground dispatch is in
    flight, and the coverage-check §1 reader ran 34.4 minutes on a 2,250-line skill,
    its work growing with the skill. So the run renews right before each dispatch (or,
    without subagents, before the main thread starts a subagent's work) with
    `--stale-after 180`, the helper keeps that window in the lock, so a second run's
    default acquire honours it, and the next plain renewal sets it back to 60."""
    rules = _slice(_read(SKILL_MD), "## Workflow Rules", "## Stages")
    rule = _flow(next((line for line in rules.splitlines() if RENEW in line), ""))
    renew_180 = RENEW + " --stale-after 180"
    for needle in ("right before each subagent dispatch (once for parallel calls sent in one message;",
                   "or, without subagents, before the main thread starts the work a step gives a subagent",
                   "since nothing can renew the lock while one dispatch runs",
                   "the next renewal that passes no `--stale-after` sets it back to 60"):
        assert needle in rule, needle
    # The plain renewal stays the rule's first command, the 180 one follows it, and the HALTs cover both.
    commands = re.findall(r"`(uv run \{runLockHelper\} acquire [^`]*)`", rule)
    assert commands == [RENEW, renew_180], commands
    assert rule.index(RENEW) < rule.index(renew_180) < rule.index("Exit 3 (another run took the lock over)")

    forge_version = tmp_path / "v"
    lock = forge_version / ".test-skill.lock"
    stamp = "%Y-%m-%dT%H:%M:%SZ"

    def age_61_minutes() -> datetime:
        """Date the lock back 61 minutes, keeping the window it stores."""
        record = json.loads(lock.read_text(encoding="utf-8"))
        since = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=61)
        record["acquired_at"] = since.strftime(stamp)
        lock.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return since

    owner = json.loads(_run(ACQUIRE, _lock_values(forge_version), tmp_path).stdout)["owner"]
    values = _lock_values(forge_version, run_owner=owner)
    before = _run(renew_180, values, tmp_path)
    renewed = json.loads(before.stdout)
    assert before.returncode == 0 and renewed["refreshed"] is True, before.stderr
    # The renewal reports the window it stored.
    renewed_at = datetime.strptime(renewed["held_since"], stamp).replace(tzinfo=timezone.utc)
    assert renewed["stale_after_minutes"] == 180
    assert renewed["stale_at"] == (renewed_at + timedelta(minutes=180)).strftime(stamp)
    since = age_61_minutes()
    # A second run's init.md §6a acquire (default 60) is refused: the dispatch is still covered.
    second = _run(ACQUIRE, _lock_values(forge_version), tmp_path)
    refused = json.loads(second.stdout)
    assert second.returncode == 3 and refused["held_by"] == owner
    assert refused["stale_after_minutes"] == 180
    held_since = datetime.strptime(refused["held_since"], stamp).replace(tzinfo=timezone.utc)
    assert held_since == since
    assert refused["stale_at"] == (held_since + timedelta(minutes=180)).strftime(stamp)
    # The plain renewal after the dispatch sets the window back to 60.
    after = _run(RENEW, values, tmp_path)
    assert after.returncode == 0 and json.loads(after.stdout)["refreshed"] is True, after.stderr
    age_61_minutes()
    third = _run(ACQUIRE, _lock_values(forge_version), tmp_path)
    taken = json.loads(third.stdout)
    assert third.returncode == 0 and taken["acquired"] is True
    assert taken["stale_replaced"]["held_by"] == owner
    # Another run holds the lock now, so the first run's next 180 renewal exits 3 and HALTs like any renewal.
    over = _run(renew_180, values, tmp_path)
    assert over.returncode == 3 and json.loads(over.stdout)["held_by"] == taken["owner"]

    # The contract, the user docs and the init comment name the 180-minute renewal before a dispatch.
    row = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Concurrency** |"))
    for needle in ("right before each subagent dispatch (report.md §4b.2's discovery subagents among them)",
                   "or, without subagents, before the main thread starts the work a step gives a subagent",
                   "passes `--stale-after 180`, a window the helper keeps in the lock"):
        assert needle in row, needle
    docs = _flow(_slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                        "### Test Skill stops with `another-run-active`", "\n### "))
    for needle in ("(60 minutes after it was taken or renewed, 180 when it was renewed as a subagent started or, "
                   "without subagents, as the main thread started a subagent's work)",
                   "just before each subagent starts or, without subagents, before the main thread starts a "
                   "subagent's work,",
                   "a renewal before a subagent or that work lasts 180 minutes, since nothing renews the lock "
                   "while one runs)",
                   "because one subagent ran 180 minutes, or the main thread's own work 60 minutes, past its last renewal"):
        assert needle in docs, needle
    init_comments = _flow(_read(INIT).replace("\n#", ""))
    assert ("right before each subagent dispatch for 180 minutes (or, without subagents, before the main "
            "thread starts a subagent's work)") in init_comments


@pytest.mark.parametrize("name", AFTER_THE_LOCK)
def test_every_halt_after_the_lock_releases_it(name):
    text = _read(REFS / name)
    body = text.split("\n---\n", 1)[1] if text.startswith("---\n") else text
    halts = [line for line in body.splitlines() if "HALT" in line and STEP_RELEASE not in line]
    if STEP_RELEASE in body:
        assert halts, f"{name}: a release rule with no HALT to cover"
        assert body.index(STEP_RELEASE) < min(body.index(line) for line in halts), \
            f"{name}: the release rule must come before its first HALT"
        return
    unreleased = [line for line in halts if "release the run lock" not in line.lower()]
    assert unreleased == [], f"{name}: a HALT that does not release the run lock"


def test_the_gate_and_both_ends_of_a_run_release_the_lock():
    # A blocked run no longer halts at the gate with the lock in hand: it ends
    # through report.md, whose §7 releases the lock like any other run's.
    block = _flow(_slice(_read(HARD_GATE), "### §3. Block", "### §4. Pass"))
    assert "load and execute `{blockedStepFile}`" in block
    assert "HALT" not in block
    assert _frontmatter(HARD_GATE)["blockedStepFile"] == "report.md"
    section7 = _flow(_slice(_read(REPORT), "### 7. Health-Check Dispatch", "load and execute `{nextStepFile}`"))
    bypass = _slice(section7, "**`--no-health-check` flag bypass", "**Release the run lock:**")
    assert bypass.index("`healthCheckDispatched: false`") < bypass.index(RELEASE) \
        < bypass.index("display `{result_envelope_line}` verbatim as the run's last line")
    main = section7[section7.index("**Release the run lock:**"):]
    assert RELEASE in main
    # Nothing after the result files halts: the health check was found before anything was published,
    # and the local step only hands over to it.
    assert "HALT" not in section7 and "health-check-missing" not in section7
    found = _flow(_slice(_read(REPORT), "**Find the health check**", "**Renew the run lock**"))
    assert 'HALT (`halt_reason: "health-check-missing"`, phase `report:health-check`)' in found
    relay = REFS / "health-check.md"
    assert _frontmatter(relay) == {"nextStepFile": "shared/health-check.md"}
    assert "HALT" not in _read(relay) and "ProbeOrder" not in _read(relay)
    # #599: no one-option menu waits between the report and the health check.
    assert "[C] Finish" not in _read(REPORT) and "with no menu before it" in _flow(_read(REPORT))


def test_the_contract_documents_the_lock():
    text = _read(CONTRACT)
    row = next(line for line in text.splitlines() if line.startswith("| **Concurrency** |"))
    for needle in ("`{forge_version}/.test-skill.lock`", "`skf-run-lock.py`", "report.md §4c renews it",
                   '`halt_reason: "another-run-active"`', "(exit 1)",
                   "SKILL.md Workflow Rules renew it each time a subagent dispatch returns",
                   "or, without subagents, the main thread finishes the work a step gives a subagent"):
        assert needle in row, needle
    envelope = _slice(text, "## Result Envelope (Headless)", "## Result Files")
    assert "| `another-run-active` |" in envelope
    # #1044: both reasons a renewal halts name the renewals SKILL.md asks for.
    for reason in ("another-run-active", "helper-failed"):
        reason_row = next(line for line in envelope.splitlines() if line.startswith(f"| `{reason}` |"))
        assert "the lock renewals of SKILL.md Workflow Rules" in reason_row, reason
    records = _flow(_slice(text, "## Result Files", "## Emitting a Halt"))
    assert "`skf-test-skill-result-{YYYYMMDD-HHmmss}.json` (UTC; it picks the name" in records
    assert "PID" not in records


def test_every_halt_has_an_envelope_and_a_listed_reason():
    """#593, #594: the halts that once exited without an envelope now name a halt_reason the schema lists."""
    schema = json.loads(_read(SCRIPTS / "schemas" / "skf-test-result-envelope.v1.json"))
    reasons = [r for r in schema["properties"]["halt_reason"]["enum"] if r is not None]
    table = _slice(_read(CONTRACT), "| `halt_reason` | Raised by |", "When the emitter itself")
    assert re.findall(r"^\| `([a-z-]+)` \|", table, re.M) == reasons
    assert "without** this envelope" not in _read(CONTRACT) and "without** this envelope" not in _read(SKILL_MD)
    named = set()
    for path in sorted(REFS.glob("*.md")):
        for short, quoted in re.findall(r'HALT[^`\n]{0,40}\(`(?:([a-z-]+)|halt_reason: "([a-z-]+)")`, phase `',
                                        _read(path)):
            named.add(short or quoted)
    assert named == set(reasons) - {"hard-gate-blocked"}, sorted(set(reasons) ^ named)


def test_runtime_is_checked_before_the_first_helper_call():
    body = _read(INIT).split("\n---\n", 1)[1]
    steps = body[body.index("### 0. Resolve the Envelope Emitter"):]
    check = _slice(steps, "### 0b. Check the Runtime", "### 1. Receive the Skill Name")
    assert steps.index("### 0b. Check the Runtime") < steps.index("uv run {")
    assert "command -v uv" in check and 'HALT (`halt_reason: "runtime-missing"`, phase `init:runtime`)' in check
    assert "https://docs.astral.sh/uv/getting-started/installation/" in check, "the HALT names the install link"
    assert body.count("command -v uv") == 1, "one runtime check, before the first helper"
    assert "set `analysis_confidence: degraded`" not in check


# --------------------------------------------------------------------------
# #588 item 4: the workspace drift guard
# --------------------------------------------------------------------------


DRIFT_CMD = ('uv run {checkWorkspaceDriftHelper} "{tree}" --pinned-commit "{pinned_commit}" '
             '[--source-ref "{source_ref}"] [--allow-drift] --workflow test-skill')
GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR",
                     "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE")


def _git(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                          env=env).stdout.strip()


def _repo(path: Path) -> tuple[str, str]:
    """A repository with two commits; returns (first, second)."""
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    shas = []
    for content in ("first\n", "second\n"):
        (path / "file.txt").write_bytes(content.encode("utf-8"))
        _git(path, "add", ".")
        _git(path, "commit", "-q", "-m", content.strip())
        shas.append(_git(path, "rev-parse", "HEAD"))
    return shas[0], shas[1]


def test_drift_guard_runs_through_the_helper():
    assert _frontmatter(INIT)["checkWorkspaceDriftProbeOrder"] == [
        "{project-root}/_bmad/skf/shared/scripts/skf-check-workspace-drift.py",
        "{project-root}/src/shared/scripts/skf-check-workspace-drift.py",
    ]
    section = _slice(_read(INIT), "### 5b. Verify Workspace HEAD Matches Pinned Commit", "### 6. Create Output")
    assert DRIFT_CMD in _fence(section, DRIFT_CMD)
    assert "git -C" not in section and "rev-parse" not in section, "no hand-run git"
    flow = _flow(section)
    assert "one call per entry" in flow and "do not skip stack skills" in flow
    assert 'HALT (`halt_reason: "workspace-drift"`, phase `init:workspace-drift`)' in flow
    assert "`halt_message` of every tree that drifted" in flow
    # #587: the later steps read the override from the report, never from the flag.
    assert "`workspaceDrift: overridden`" in flow and "The later steps read it there, never the flag" in flow


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize("pin, allow, status, code", [
    ("head", False, "ok", 0),
    ("first", False, "mismatch", 2),
    ("first", True, "overridden", 0),
    ("local", False, "skipped", 0),
], ids=["ok", "mismatch", "overridden", "no-pin"])
def test_the_prose_drift_command_runs(tmp_path, pin, allow, status, code):
    first, head = _repo(tmp_path / "src")
    command = DRIFT_CMD.replace(' [--source-ref "{source_ref}"]', ' --source-ref "v1.0.0"')
    command = command.replace(" [--allow-drift]", " --allow-drift" if allow else "")
    pinned = {"head": head, "first": first, "local": "local"}[pin]
    proc = _run(command, {"{tree}": (tmp_path / "src").as_posix(), "{pinned_commit}": pinned}, tmp_path)
    assert proc.returncode == code, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == status
    if status == "mismatch":
        assert "--allow-workspace-drift" in out["halt_message"]


# --------------------------------------------------------------------------
# v4.0.0 quality gate run 2, skf-test-skill architecture-1: the drift guard
# reads the source tree from the metadata.json key the producers write
# --------------------------------------------------------------------------


SOURCE_TREE_BINDING_RE = re.compile(r"bind `\{source_path\}` ← `([a-z_]+)`")
NO_SOURCE_ROOT_LOG = "`workspace_drift_check: skipped (metadata.json records no source_root)`"
QUICK_TEMPLATE = SRC / "skf-quick-skill" / "assets" / "skill-template.md"
QUICK_METADATA = SCRIPTS / "skf-render-quick-metadata.py"
# `source_path` read as a metadata.json key: a bare name in the prose (not the
# `{source_path}` binding), a quoted key in a script.
METADATA_SOURCE_PATH_RE = {
    ".md": re.compile(r"(?<![\w{])source_path(?![\w}])"),
    ".toml": re.compile(r"(?<![\w{])source_path(?![\w}])"),
    ".py": re.compile(r"""["']source_path["']"""),
}


def _init_5() -> str:
    return _slice(_read(INIT), "### 5. Load Skill Metadata", "### 5b.")


def test_init_binds_the_source_tree_from_the_key_the_producers_write():
    """v4.0.0 quality gate run 2 (the clearing run), skf-test-skill
    architecture-1: §5 read a metadata.json `source_path` that no SKF workflow
    writes, so §5b found no tree, ran no drift check and recorded
    `not-checked` on a drifted workspace. Create Skill and Quick Skill write
    `source_root`: §5 binds `{source_path}` from it, names no undeclared
    override, and a skill that records none logs why §5b skipped it."""
    for producer in (SKILL_SECTIONS, QUICK_TEMPLATE, QUICK_METADATA):
        text = _read(producer)
        assert '"source_root"' in text and '"source_path"' not in text, producer.name
    section = _init_5()
    assert SOURCE_TREE_BINDING_RE.findall(section) == ["source_root"]
    assert "`source_path`" not in section and "override" not in section
    one_tree = _flow(_slice(_read(INIT), "- **One tree:**", "- **A stack skill**"))
    assert f"records no `source_root` (null, empty or absent), make no call and log {NO_SOURCE_ROOT_LOG}" in one_tree


def test_no_test_skill_file_reads_a_metadata_source_path_key():
    """Every `source_path` test-skill names is the `{source_path}` binding init.md §5 makes."""
    found = [f"{path.relative_to(REPO_ROOT).as_posix()}:{n}"
             for path in sorted(TEST_SKILL.rglob("*")) if path.suffix in METADATA_SOURCE_PATH_RE
             for n, line in enumerate(_read(path).splitlines(), 1)
             if METADATA_SOURCE_PATH_RE[path.suffix].search(line)]
    assert not found, f"reads a metadata.json `source_path` key, which no producer writes: {found}"


def _producer_metadata(producer: str, tmp_path: Path, repo: Path, pinned: str) -> dict:
    """The metadata.json `producer` writes for a skill extracted from `repo` at `pinned`."""
    if producer == "quick-skill":
        payload = tmp_path / "metadata-input.json"
        payload.write_bytes(json.dumps({
            "name": "demo", "language": "python", "source_repo": "https://github.com/o/demo",
            "source_root": repo.as_posix(), "source_commit": pinned, "exports": ["parse"], "skf_version": "4.0.0",
        }).encode("utf-8"))
        output = tmp_path / "metadata.json"
        proc = subprocess.run([sys.executable, str(QUICK_METADATA), "--input", str(payload), "--output", str(output)],
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        return json.loads(output.read_text(encoding="utf-8"))
    # Create Skill's metadata.json (assets/skill-sections.md) for a Forge run on a local tree.
    return {
        "name": "demo", "version": "1.0.0", "skill_type": "single", "scope_type": "full-library",
        "source_authority": "official", "source_repo": "https://github.com/o/demo", "source_root": repo.as_posix(),
        "source_commit": pinned, "source_ref": "v1.0.0", "confidence_tier": "Forge", "spec_version": "1.3",
        "generation_date": "2026-10-14T00:00:00Z", "description": "Demo.", "language": "python",
        "ast_node_count": 1, "exports": ["parse"],
        "tool_versions": {"ast_grep": "0.45.3", "qmd": None, "skf": "4.0.0"},
        "confidence_distribution": {"t1": 1, "t1_low": 0, "t2": 0, "t3": 0},
        "stats": {"exports_documented": 1, "exports_public_api": 1, "exports_internal": 0, "exports_total": 1,
                  "public_api_coverage": 1.0, "total_coverage": 1.0, "scripts_count": 0, "assets_count": 0},
        "generated_by": "create-skill", "dependencies": [], "compatibility": "",
    }


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
@pytest.mark.parametrize("producer", ["create-skill", "quick-skill"])
@pytest.mark.parametrize("allow, status, code", [(False, "mismatch", 2), (True, "overridden", 0)],
                         ids=["halts", "allow-workspace-drift"])
def test_the_drift_guard_checks_the_tree_the_producer_records(tmp_path, producer, allow, status, code):
    """§5b's command, run on the tree §5 binds from the producer's metadata.json,
    sees a HEAD one commit past the pin: a mismatch halts the run, and
    --allow-workspace-drift records `overridden`, never `not-checked`."""
    pinned, head = _repo(tmp_path / "src")
    metadata = _producer_metadata(producer, tmp_path, tmp_path / "src", pinned)
    key = SOURCE_TREE_BINDING_RE.search(_init_5())
    assert key, "init.md §5 binds `{source_path}` from no metadata.json key"
    tree = metadata.get(key.group(1))
    assert tree and Path(tree).is_dir(), (f"metadata.json holds no tree under `{key.group(1)}`, so §5b makes no call "
                                          "and records `workspaceDrift: not-checked` on a drifted workspace")
    keep = tuple(flag for flag, on in (("--source-ref", bool(metadata.get("source_ref"))), ("--allow-drift", allow)) if on)
    command = _choose(_command(INIT, "uv run {checkWorkspaceDriftHelper}"), keep)
    proc = _run(command, {"{tree}": tree, "{pinned_commit}": metadata.get("source_commit") or "",
                          "{source_ref}": metadata.get("source_ref") or ""}, tmp_path)
    assert proc.returncode == code, proc.stderr
    out = json.loads(proc.stdout)
    assert out["status"] == status
    if status == "mismatch":
        assert pinned in out["halt_message"] and head in out["halt_message"]


# --------------------------------------------------------------------------
# #584: the Quick-tier scan and the workspace layout
# --------------------------------------------------------------------------


QUICK_CMD = ('uv run {extractPublicApiHelper} --mode quick --language <language> --source-root "{source_path}" '
             '--manifest-file <manifest path> --entry-file <entry path>')
# #780: the brief's scope.exclude leaves its paths out of the tree, so a workspace whose members it drops is
# no workspace; the flag is left out when the skill has no brief.
WORKSPACES_BRIEF = '--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"'
WORKSPACES_CMD = ('uv run {stageHelperPayloadScript} detect-workspaces --source-root "{source_path}" '
                  f'{WORKSPACES_BRIEF} | uv run {{detectWorkspacesHelper}}')


def _quick_tier() -> str:
    return _slice(_read(COVERAGE_TIERS), "## Quick Tier", "## Fallback Per-File Scan")


def test_coverage_binds_the_helpers_and_the_payload_script():
    frontmatter = _frontmatter(COVERAGE)
    for key, script in (("extractPublicApiProbeOrder", "skf-extract-public-api.py"),
                        ("detectWorkspacesProbeOrder", "skf-detect-workspaces.py")):
        assert frontmatter[key] == [f"{{project-root}}/_bmad/skf/shared/scripts/{script}",
                                    f"{{project-root}}/src/shared/scripts/{script}"]
    assert frontmatter["stageHelperPayloadScript"] == "scripts/stage-helper-payload.py"
    # The model copies no file text into a payload.
    for path in (COVERAGE, COVERAGE_TIERS, COVERAGE_BRANCHES):
        text = _read(path)
        for by_hand in ("file-write tool", ".skf-quick-exports-", ".skf-workspaces-"):
            assert by_hand not in text, (path.name, by_hand)


def test_quick_tier_parses_a_quick_skill_skill_with_its_parser():
    quick = _quick_tier()
    assert QUICK_CMD in _fence(quick, QUICK_CMD)
    flow = _flow(quick)
    assert "`generated_by` is `quick-skill`" in flow and "**Any other skill**" in flow
    # §2c's script decides documented, missing and stale from `exports_found`.
    assert '`{"file": "<entry path>", "exports_found": [' in flow
    for by_hand in ("exports_documented", "missing_docs", "by name matching", "`kotlin`"):
        assert by_hand not in flow, by_hand
    # The parser's `warnings` name what the entry file alone cannot give, and
    # only that is read by eye. The forms the parser reads, and the ones it
    # warns about, are the parser's to list (#600, w3 leanness-5).
    assert "Its `warnings` name each statement whose names the entry file alone cannot give" in flow
    assert "Read by eye only the statements its warnings name" in flow
    for restated in ("`from ... import`", "`export * as`", "`async def`", "`pub use x::*`",
                     "`module.exports = require(...)`"):
        assert restated not in flow, restated
    assert flow.count("read by eye") + flow.count("read them by eye") >= 2
    # Its output reaches the surface by path.
    assert f'{QUICK_CMD} > "{{run_dir}}/quick-<n>.json"' in flow
    assert QUICK_SURFACE_CMD in flow
    # A name read by eye carries the entry file that holds it, so the brief's
    # scope globs can place it.
    assert "save the names they give as a per-file result for the entry file" in flow
    assert "--name" not in flow


def test_quick_tier_parses_a_python_javascript_or_typescript_skill_with_its_parser(tmp_path):
    """#750: a create-skill skill in Python, JavaScript or TypeScript, from local source, is parsed too: each
    name carries the file that defines it (`defined_in`), so a name the entry file passes on from a file the
    brief scopes out leaves the scope.include set, as at Forge tier. Other languages are still read by eye."""
    flow = _flow(_quick_tier())
    assert ("**A skill quick-skill built** (`metadata.json` `generated_by` is `quick-skill`), or **any skill in "
            "Python, JavaScript or TypeScript**, **from local source** (State 1)") in flow
    assert "it gives each name the file that defines it (`defined_in`)" in flow
    assert "**Any other skill** (create-skill's Quick tier reads the entry points of another language" in flow
    source = _write_tree(tmp_path / "src", {
        "package.json": '{"name": "fx", "version": "1.0.0", "exports": {".": "./src/index.ts"}}\n',
        "src/index.ts": ("export { alpha } from './a';\nexport { beta, gamma } from './b';\n"
                         "export { extra } from '../gen/extra';\n"),
        "src/a.ts": "export function alpha() {}\n",
        "src/b.ts": "export function beta() {}\nexport function gamma() {}\n",
        "gen/extra.ts": "export function extra() {}\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    proc = _run(QUICK_CMD, {"{source_path}": source.as_posix(), "<language>": "typescript",
                            "<manifest path>": "package.json", "<entry path>": "src/index.ts"}, tmp_path)
    assert proc.returncode == 0, proc.stderr
    (run / "quick-1.json").write_bytes(proc.stdout)
    forge = tmp_path / "forge-data"
    _write_tree(forge / "fx", {"skill-brief.yaml": "name: fx\nlanguage: typescript\nscope:\n"
                                                   "  type: specific-modules\n  include: ['src/**']\n"})
    skill = _write_tree(tmp_path / "skill", {
        "metadata.json": json.dumps({"skill_type": "single", "exports": ["alpha", "beta", "gamma"],
                                     "stats": {"effective_denominator": 3}}),
        "provenance-map.json": json.dumps({"entries": [{"export_name": n} for n in ("alpha", "beta", "gamma")]})})
    values = {"{run_dir}": run.as_posix(), "{forge_data_folder}": forge.as_posix(), "{skill_name}": "fx",
              "{resolved_skill_package}": skill.as_posix(),
              "{forge_provenance_map}": (skill / "provenance-map.json").as_posix(), "<n>": "1"}
    surface = _exec(_choose(_command(COVERAGE_TIERS, "surface --quick"), keep=("--brief", "--provenance")), values,
                    tmp_path)
    assert surface["sets"] == {"all": ["alpha", "beta", "extra", "gamma"], "scope.include": ["alpha", "beta", "gamma"]}
    assert (surface["guards"]["deflation"]["fires"], surface["guards"]["inflation"]["fires"]) == (False, False)


QUICK_SURFACE_CMD = ('uv run {coverageInputsScript} surface --quick "{run_dir}/quick-<n>.json" '
                     '[--per-file "{run_dir}/per-file-<n>.json"] '
                     '[--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] '
                     '--metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] '
                     '[--monorepo] [--pattern-reference-intent] [--curated-subset] [--barrel <state>] '
                     '--output "{run_dir}/surface.json"')


def test_the_prose_quick_tier_surface_reads_the_brief(tmp_path):
    """determinism-5: a Quick-tier surface gets its scope sets, candidates and
    deflation guard from the brief, with no extraction."""
    source = _write_tree(tmp_path / "src", {
        "package.json": '{"name": "demo", "version": "1.2.3"}\n',
        "src/index.ts": "export function fetchData(url: string) {}\nexport function helper() {}\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    values = {"{source_path}": source.as_posix(), "<language>": "ts", "<manifest path>": "package.json",
              "<entry path>": "src/index.ts"}
    proc = _run(QUICK_CMD, values, tmp_path)
    assert proc.returncode == 0, proc.stderr
    (run / "quick-1.json").write_bytes(proc.stdout)
    forge = tmp_path / "forge-data"
    _write_tree(forge / "demo", {"skill-brief.yaml": "name: demo\nscope:\n  include: ['src/**']\n"
                                                     "  tier_a_include: ['src/index.ts']\n"})
    skill = _write_tree(tmp_path / "skill", {"metadata.json": json.dumps(
        {"skill_type": "single", "exports": ["fetchData"], "stats": {"effective_denominator": 1}})})
    values = {"{run_dir}": run.as_posix(), "{forge_data_folder}": forge.as_posix(), "{skill_name}": "demo",
              "{resolved_skill_package}": skill.as_posix(), "<n>": "1"}
    command = _choose(_command(COVERAGE_TIERS, "surface --quick"), keep=("--brief",))
    surface = _exec(command, values, tmp_path)
    assert surface["sets"]["all"] == ["fetchData", "helper"], "metadata.json adds no name to a source read"
    assert surface["sets"]["tier_a_include"] == ["fetchData", "helper"]
    assert surface["candidates"]["tierAIncludeUnion"] == 2
    assert surface["guards"]["deflation"]["applicable"] is True


def test_signatures_are_scored_over_the_denominator_set():
    """Type Coverage counts the types of the set the denominator counts, so the
    score runs in §2b, after the clause picks that set."""
    text = _read(COVERAGE)
    section2b = _slice(text, "### 2b. Resolve the Denominator", "### 2c. Reconcile")
    assert section2b.index("**Pick the denominator.**") < section2b.index("**Score the signatures**")
    command = _command(COVERAGE, "uv run {scoreSignaturesScript} score")
    assert "--surface-set <set>" in command and command in section2b
    # #835 follow-up: the local source the judges read checks an annotation-contradicted mismatch's evidence line,
    # a drifted tree included
    assert '[--source-root "{source_path}"]' in command
    assert ("`--source-root` whenever the source is local (State 1, Forge tier or above), under a drift override too, "
            "since the judges read that tree") in _flow(section2b)
    assert "uv run {scoreSignaturesScript} score" not in _slice(text, "### 2. Analyze Source Code", "### 2b.")
    # Its warnings reach the Coverage Analysis section through §5's render, never retyped.
    assert "§5's render lists its `warnings`" in _flow(section2b)
    # The scalar is read from the loader's file, never typed in.
    branches = _read(COVERAGE_BRANCHES)
    assert "--denominator-value" not in text and "--denominator-value" not in branches
    assert '--denominator-source scalar --coverage-inputs "{run_dir}/coverage-inputs.json"' in branches


def test_a_run_with_no_local_source_names_its_skip():
    flags = _flow(_slice(_read(SCORE), "#### 3a. Construct Scoring Input JSON", "#### 3b."))
    assert "`metadata-only` or `remote-only`, States 3 and 4" in flags
    docs_only = _flow(_slice(_read(COVERAGE_BRANCHES), "## Docs-Only Run", "**Docs-only skill detected.**"))
    assert "§4's `Denominator: docs-only completeness` annotation" in docs_only


def test_the_prose_quick_command_runs(tmp_path):
    source = _write_tree(tmp_path / "src", {
        "package.json": '{"name": "demo", "version": "1.2.3"}\n',
        "src/index.ts": "export function fetchData(url: string) {}\n"
                        "export { parse as parseText } from './parse';\nconst note = 'it\\'s \"quoted\"';\n",
    })
    values = {"{source_path}": source.as_posix(), "<language>": "ts", "<manifest path>": "package.json",
              "<entry path>": "src/index.ts"}
    proc = _run(QUICK_CMD, values, tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert [(e["name"], e["source_file"]) for e in out["exports"]] == [
        ("fetchData", "src/index.ts"), ("parseText", "src/index.ts")]


def test_workspace_layout_comes_from_the_detector():
    layout = _slice(_read(COVERAGE), "**Workspace layout.**", "### 1. Extract Documented Exports")
    assert WORKSPACES_CMD in _fence(layout, WORKSPACES_CMD)
    flow = _flow(layout)
    assert "Bind `{source_is_monorepo}` ← `is_monorepo` and `{source_workspace_kind}` ← `manifest_kind`" in flow
    assert "bind `{source_is_monorepo}` ← false" in flow
    assert "leave `--brief` out with no brief" in flow
    assert "A workspace whose members `scope.exclude` drops is no workspace." in flow
    # The detector keeps the list of manifests it reads; the prose repeats none.
    for name in ("`lerna.json`", "`rush.json`", "`build.gradle.kts`"):
        assert name not in layout, name
    assert "**Workspace Layout:** {source_workspace_kind" in _read(COVERAGE)


def test_each_monorepo_test_reads_the_detector():
    """The clause's monorepo test is the detector's `{source_is_monorepo}`, passed as `--monorepo`
    (v4.0.0 quality gate run 1, test-skill determinism-1: `surface` picks the clause), never a layout
    read by eye."""
    protocol = _read(SOURCE_ACCESS)
    pick = _slice(protocol, "The clauses below decide", "Each clause, by its `denominator.clause`")
    assert "`{source_is_monorepo}` (coverage-check.md §0b, passed as `--monorepo`)" in _flow(pick)
    flags = _flow(_slice(_read(COVERAGE), "**Clause flags.**", "### 1. Extract Documented Exports"))
    assert "`--monorepo` when `{source_is_monorepo}` is true" in flags
    for by_eye in ("`packages/` layout", "no `packages/`", "monorepo markers"):
        assert by_eye not in protocol, by_eye


def test_the_flags_left_to_the_model_are_stated_once():
    """v4.0.0 quality gate run 1 review: the clause flags are the protocol's alone (§0b restated two of them);
    `--curated-subset` stands only where the extraction has no `counts.curated_subset`, which `surface` reads
    first, and `--barrel` carries the entry points' state where no extraction or quick output gives it, so the
    empty-barrel and no-barrel triggers still fire on a fallback scan, a Quick-tier read by eye and State 4."""
    flags = _flow(_slice(_read(COVERAGE), "**Clause flags.**", "### 1. Extract Documented Exports"))
    assert "the flags the Source API Surface Definition leaves to you" in flags
    assert "scope.notes" not in flags and "curated subset" not in flags
    protocol = _flow(_slice(_read(SOURCE_ACCESS), "The clauses below decide", "The recipe runner already"))
    for token in ("- **Pattern-reference intent** (`--pattern-reference-intent`):",
                  "- **A curated monorepo subset** (`--curated-subset`), where the extraction has no "
                  "`counts.curated_subset` (Quick tier, the fallback per-file scan, States 2 to 4):",
                  "- **The entry points' state** (`--barrel`), where no complete extraction or quick output gives it "
                  "(the fallback per-file scan when the runner listed entry points, Quick tier read by eye, State 4): "
                  "`none` when no barrel file is at any recognized entry-point path"):
        assert token in protocol, token
    for command in (_command(COVERAGE_TIERS, "surface --quick"), _command(COVERAGE_TIERS, "surface --per-file")):
        assert "[--barrel <state>]" in command, command
    # State 2, 3 and 4's commands, carved with their branch, take the clause flags as §2's do
    assert "Every `surface` command, in §2 or in a branch file it loads, takes `--monorepo`" in flags
    states = _flow(_slice(_read(COVERAGE_BRANCHES), "## States 2 to 4", "## Scalar and Stack Branches"))
    [state3] = re.findall(r"`(surface --metadata [^`]+)`", states)
    [state4] = re.findall(r"`(surface --per-file [^`]+)`", states)
    for command in (_command(COVERAGE_BRANCHES, "surface --provenance"), state3, state4):
        assert "[--monorepo]" in command and "[--curated-subset]" in command, command
    assert "[--barrel <state>]" in state4
    # the audit trail block stays with the two clauses whose candidates it compares
    section4 = _flow(_read(COVERAGE))
    assert ("When `denominator.clause` is `stratified-scope` or `multi-entry`, load `{coverageBranchesFile}` and "
            "append the block of its **Denominator Candidates** section after the `Denominator:` line") in section4
    block = _read(COVERAGE_BRANCHES).split("\n## Denominator Candidates\n", 1)[1]
    assert "**Denominator Candidates** (stratified-scope audit trail):" in _fence(block, "(stratified-scope audit")
    assert "When `denominator.ladderStep` is set" not in section4


# #780: the workspace layouts and briefs Test Skill's detection and the recipe runner's monorepo arm read
# alike, among them a Rust workspace beside the Python package a skill documents.
SCOPE_EXCLUDE = json.loads((REPO_ROOT / "test" / "fixtures" / "workspace-scope-exclude.json").read_text("utf-8"))


@pytest.mark.parametrize("files, excludes, expected", [
    pytest.param({"package.json": '{"name": "root", "workspaces": ["packages/*"]}\n',
                  "packages/a/package.json": "{}\n", "packages/b/package.json": "{}\n"}, None,
                 (True, "npm-workspaces"), id="npm-workspaces"),
    pytest.param({"apps/web/package.json": "{}\n", "libs/ui/package.json": "{}\n"}, None,
                 (True, "generic-folders"), id="generic-folders"),
    pytest.param({"package.json": '{"name": "single"}\n', "node_modules/a/package.json": "{}\n",
                  "node_modules/b/package.json": "{}\n"}, None, (False, None), id="single-package"),
    *[pytest.param(SCOPE_EXCLUDE["trees"][c["tree"]], c["exclude"], (c["is_monorepo"], c["manifest_kind"]),
                   id=c["id"]) for c in SCOPE_EXCLUDE["cases"]],
])
def test_the_prose_workspace_command_runs(tmp_path, files, excludes, expected):
    """With no brief the command runs without `--brief`; with one, a workspace member counts only through
    the files the brief's scope.exclude keeps, so a workspace with no member left is no workspace (#780)."""
    source = _write_tree(tmp_path / "src", files)
    values = {"{source_path}": source.as_posix()}
    command = WORKSPACES_CMD
    if excludes is None:
        assert command.count(" " + WORKSPACES_BRIEF) == 1
        command = command.replace(" " + WORKSPACES_BRIEF, "")
    else:
        forge = _write_tree(tmp_path / "forge", {"pkg/skill-brief.yaml": "name: pkg\nscope:\n  exclude:\n"
                                                 + "".join(f"    - '{g}'\n" for g in excludes)})
        values.update({"{forge_data_folder}": forge.as_posix(), "{skill_name}": "pkg"})
    proc = _run(command, values, tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert (out["is_monorepo"], out["manifest_kind"]) == expected


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
    wiring = _slice(section, "**Wiring evidence (first criterion).**", "Build integration completeness findings")
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


def test_coherence_section_5_is_the_one_home_of_the_rule():
    """The wave-1 leanness-2 handoff: scoring-rules.md no longer restates the
    pattern rule or the coherence split; it points at section 5 and the script."""
    section = _flow(_coherence_5())
    assert "Each Cross-Cutting Patterns entry and each Library Pair Integrations entry" in section
    assert COMPOSE_EVIDENCE in section and "A fenced code block is not required in either mode" in section
    # §5c names the script as the formula's home; with no pattern, coherence is reference validity.
    aggregate = _flow(_slice(_read(COHERENCE), "### 5c. Calculate Coherence Scores", "### 6."))
    assert "is the one home of the formula and its weights" in aggregate
    scoring = _flow(_read(SCORING))
    for gone in ("## Coherence Score Aggregation", "Hub Library Connections", "0.6", "## Category Weights",
                 "## Result Determination", "Pass threshold:** 80%"):
        assert gone not in scoring, gone
    pointers = _slice(scoring, "## Where the Scoring Rules Live", "## Gap Severity")
    for owner in ("`scripts/compute-score.py`", "`scripts/aggregate-coherence.py`", "coherence-check.md §5",
                  "`scripts/reconcile-coverage.py`", "`docsOnly` branch", "`scripts/score-signatures.py`",
                  "`{defaultThreshold}`"):
        assert owner in pointers, owner



# --------------------------------------------------------------------------
# #613, #540, #596: the scoring inputs are scripted and read by path
# --------------------------------------------------------------------------


SCORE = REFS / "score.md"
DETECT = REFS / "detect-mode.md"
CUSTOMIZE = TEST_SKILL / "customize.toml"
SCRIPTS_DIR = TEST_SKILL / "scripts"
RUN_FOLDER = "{project-root}/_bmad-output/.skf-run/skf-test-skill-{run_id}"
OPTIONAL_RE = re.compile(r" \[(--[^\[\]]+)\]")


def _command(path: Path, needle: str) -> str:
    """The one fenced command line of `path` that holds `needle`."""
    lines = [line.strip() for line in _fence(_read(path), needle).splitlines() if needle in line]
    assert len(lines) == 1, (path.name, needle, lines)
    return lines[0]


def _choose(command: str, keep: tuple[str, ...] = ()) -> str:
    """Keep the `[--flag ...]` groups that name a flag in `keep`, drop the others."""
    return OPTIONAL_RE.sub(lambda m: " " + m.group(1) if m.group(1).split()[0] in keep else "", command)


def test_the_run_folder_is_created_at_the_lock_and_removed_at_both_ends():
    lock = _flow(_slice(_read(INIT), "**6b. Act on the result:**", "**6c. Create `{outputFile}`"))
    assert f"bind `{{run_dir}}` ← `{RUN_FOLDER}`" in lock
    assert f'mkdir -p "{RUN_FOLDER}"' in lock
    assert "releasing the run lock first as the **Halt envelope** paragraph says" in lock
    halt_envelope = _flow(_slice(_read(INIT), "**Halt envelope.**", "### 0."))
    assert f"Once §6a took the run lock, it releases the lock first, whatever the release prints: from `{{project-root}}`, run `{RELEASE}`" in halt_envelope
    section7 = _flow(_slice(_read(REPORT), "### 7. Health-Check Dispatch", "load and execute `{nextStepFile}`"))
    assert section7.count(f'rm -rf "{RUN_FOLDER}"') == 2, "both ways a run ends remove it"
    bypass = _slice(section7, "**`--no-health-check` flag bypass", "**Release the run lock:**")
    assert bypass.index(RELEASE) < bypass.index("rm -rf") < bypass.index("{result_envelope_line}")
    row = next(line for line in _read(CONTRACT).splitlines() if line.startswith("| **Outputs** |"))
    assert "`{project-root}/_bmad-output/.skf-run/skf-test-skill-{run_id}/`" in row


def test_no_payload_is_echoed_into_a_scoring_script():
    """determinism-4: a subagent response and every list reach the scripts by path, never in a shell string."""
    for path in (COVERAGE, SCORE):
        text = _read(path)
        for echoed in ("<subagent raw response>", "echo '<JSON>'", "| uv run {reconcileScript}",
                       "| uv run {coherenceScript}", "| uv run {numeratorVerifyScript}", "| uv run {scoringScript}",
                       "| uv run {validateInventoryScript}"):
            assert echoed not in text, (path.name, echoed)
    flow = _flow(_read(COVERAGE))
    assert "`{run_dir}/inventory-response.txt` with the Write tool" in flow
    assert "`{run_dir}/signatures-<n>.txt` with the Write tool" in flow


def test_score_reads_the_category_scores_from_files():
    section2 = _flow(_slice(_read(SCORE), "### 2. The Category Score Files", "### 3. Apply"))
    assert "never read back out of the report" in section2
    for name in ("coverage.json", "signatures.json", "coherence.json", "external.json", "surface.json"):
        assert f"`{name}`" in section2, name
    command = _command(SCORE, "uv run {scoringScript}")
    for flag in ('--coverage "{run_dir}/coverage.json"', '[--signatures "{run_dir}/signatures.json"]',
                 '[--coherence "{run_dir}/coherence.json"]', '--external "{run_dir}/external.json"',
                 '[--surface "{run_dir}/surface.json"]'):
        assert flag in command, flag
    body = _read(SCORE)
    for gone in ('"scores": {', "max(0, exportCoverage - 10)", "calculated manually", "§4b in step 3",
                 "{scoringRulesFile}", "then re-flips to PASS"):
        assert gone not in body, gone


def test_the_inventory_contract_lists_the_validators_kinds():
    validator = runpy_module(SCRIPTS_DIR / "validate-inventory.py")
    assert _frontmatter(COVERAGE)["inventoryContractFile"] == "references/inventory-contract.md"
    section = _flow(_read(INVENTORY_CONTRACT))
    listed = re.search(r"each `kind` is one of (.+?); every entry", section).group(1)
    assert re.findall(r"`([a-z]+)`", listed) == list(validator.VALID_KINDS)
    assert "every entry carries the `description`" in section
    # #1001: the keys an entry may carry, every other one refused
    keys = re.search(r"An entry carries no key but (.+?), and the validator refuses", section).group(1)
    assert re.findall(r"`([a-z_]+)`", keys) == list(validator.ENTRY_KEYS)
    # #841: a cross-check entry's fields and its other side, the body's line or a second reference's path and line
    entry = re.search(r"A `cross_check_mismatches` entry gives (.+?)\.\s*$", section).group(1)
    for field in validator.REQUIRED_MISMATCH_FIELDS + validator.BODY_SIDE + validator.REFERENCE_SIDE:
        assert f"`{field}`" in entry, field
    assert ("for two references, the one that sorts first in codepoint order, by path and then line, as "
            "`other_file` and `other_line`, with the one that sorts last as `reference_file` and `reference_line`"
            ) in entry
    assert "an `issue` that names each form by its file's path" in entry
    # #1033: a mismatch's `export` names an entry, a method's by its bare name, and the validator refuses any other
    assert ("A mismatch's `export` is the `name` of an inventory entry, a `method`'s bare `name`. "
            "`validate-inventory.py` refuses an inventory with a mismatch whose `export` names no entry by its `name` "
            "or, for a `method` that gives an `owner`, by `{owner}.{name}`: an empty string, a number or a name no "
            "entry has would title a split-body gap with an export the inventory does not list.") in section


# The contract's rule for a name documented in several places (#826), and in several forms at one place (#1043).
SEVERAL_PLACES = ("A name documented in several places is listed once per place, each entry with that place's form "
                  "(`Card` above), and once per form at a place that writes several of its forms (two overloads in "
                  "one row), each entry with that place as its `at`, never as one entry whose list `params` gives a "
                  "form per item (the validator refuses a list of two or more items when one item holds several "
                  "parameters or a whole form, or two items name the same parameter), and keeps one `kind` in every "
                  "place.")


def test_the_inventory_contract_gives_a_component_constant_a_usage_signature():
    """#837: a `const` holding a component had no rule, so whether its form was compared depended on how a run
    recorded it. The contract records it as a `constant` with the form the skill writes as `usage_signature` (which
    score-signatures.py plans) and a data constant with no signature field (which it does not). #826: a name
    documented in several places is listed once per place, under one kind, so `plan` offers its forms. The contract's
    example shows both. Both rules live in the contract file §1 loads, and coverage-check.md stays under its
    budget. #1043 (oms-storybook-react-vite): "listed once per place" and an undefined list `params` let a reader
    record both `actions` overloads of one row as one entry, a form per item, which the scripts joined into one
    parameter list that matched neither overload, a Critical gap. A place that writes several forms now lists the
    name once per form at that `at`, and a list `params` holds one parameter list's members, one per item."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    assert ("A `const` holding a component (a `forwardRef`, `memo` or other wrapper call, or an alias like "
            "`const Tabs = TabsPrimitive.Root`) is a `constant` with the declaration or usage form the skill writes as "
            "`usage_signature`; a data constant carries no `usage_signature`, `params` or `return_type`.") in contract
    assert SEVERAL_PLACES in contract
    assert ("a function or method carries `params` (`\"\"` or `[]` when it takes none; any list `params` holds the "
            "members of one parameter list, one per item, never one form per item) and `return_type`") in contract
    example = json.loads(re.search(r"```json\n(.*?)\n```", _read(INVENTORY_CONTRACT), re.S).group(1))["exports"]
    assert {"name": "ComponentName", "kind": "constant", "usage_signature": "<ComponentName prop={value} />",
            "description": "...", "at": "SKILL.md:64"} in example
    assert [(e["kind"], e["params"]) for e in example if e["name"] == "Card"] == [
        ("function", "{ title }"), ("function", "{ title: string; footer?: ReactNode }")]
    section1 = _flow(_slice(_read(COVERAGE), "### 1. Extract Documented Exports", "#### 1a."))
    assert "The JSON's shape and the contract the validator checks are in `{inventoryContractFile}`" in section1
    assert len(_read(COVERAGE)) < COVERAGE_CHAR_BUDGET


def test_an_entry_with_no_form_gives_one_place_as_its_at(tmp_path):
    """Coherence review of #1006 and the oh-my-skills rehearsals: the contract asked for `at` only on an entry
    whose form is compared, and its example gave a type entry none, while #1006 made a stale name's Source, Issue
    and remediation read that `at`. So oms-uitripled's `UILibraryContextValue`, written only as `type
    UILibraryContextValue = {` in a fence, cited `references/setup.md:90` on one run and a bare `SKILL.md` on the
    next. Readers also split on whether a mention, a heading or prose that names a name with no form gives an entry
    beside the ones its other places give, and at which line. An entry with no compared form now gives its place as
    `at`, a return-only form aside (and, until #1088, a `method`); a place that writes a name with no form, members
    or fields gives no entry when another place gives one, the floor's places aside; and of several such places of a
    name the skill documents the first alone gives one. Coherence review: that last clause gives no entry to a name
    the skill writes only at such places (an import and a prose code span, as oms-uitripled's `CardContent`), which
    the rehearsals left for a maintainer decision, so it reaches only a name the skill documents. The example shows a
    class and a type entry with an `at`, and the validator keeps a type entry's `at` on a line that writes the name
    with no warning."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    formless_at = ("That line writes the entry's `name`, or, in a fenced block, the block does. An entry with no "
                   "compared form gives its place as `at` too, a form that writes only a `return_type` (below) aside, "
                   "so a gap about its name, such as a stale name's, cites that line.")
    one_place = ("such as a stale name's, cites that line. A place that writes a name but no form of it, and no "
                 "`methods`, `properties` or `fields` its entry would carry (a mention, a bare code span, an "
                 "import, a heading or prose that names or describes it), gives it no entry when another place gives the name one, "
                 "unless `inventory-floor.json` gives that place; of several such places of a name the skill "
                 "documents and no other place gives an entry, the first alone gives one: in SKILL.md, else the file "
                 "that sorts first by path, at its lowest line.")
    for sentence in (formless_at, one_place):
        assert sentence in contract and contract.count(sentence) == 1, sentence
    assert "of several such places of a name no other place gives an entry" not in contract
    assert "a form that writes only a `return_type` gives no `at`" in contract
    example = json.loads(re.search(r"```json\n(.*?)\n```", _read(INVENTORY_CONTRACT), re.S).group(1))["exports"]
    assert [e.get("at") for e in example if e["name"] in ("ClassName", "TypeName")] == ["SKILL.md:48", "SKILL.md:52"]
    validator = runpy_module(SCRIPTS_DIR / "validate-inventory.py")
    package = tmp_path / "skill"
    (package / "references").mkdir(parents=True)
    (package / "SKILL.md").write_text("# Demo\n\nSee the setup.\n", encoding="utf-8")
    (package / "references" / "setup.md").write_text(
        "# Setup\n\n```ts\ntype UILibraryContextValue = {\n  library: string;\n};\n```\n", encoding="utf-8")
    inventory = {"exports": [{"name": "UILibraryContextValue", "kind": "type", "description": "",
                              "at": "references/setup.md:4"}],
                 "references": ["references/setup.md"], "cross_check_mismatches": []}
    result = validator.validate_inventory(json.dumps(inventory), str(package))
    assert result["valid"] is True and result["warnings"] == [], (result["violations"], result["warnings"])
    assert result["inventory"]["exports"][0]["at"] == "references/setup.md:4"


def test_the_inventory_contract_gives_a_removed_or_earlier_version_form_no_entry():
    """#1038 (oms-cocoindex): a migration row wrote the old call `Settings(database=DatabaseConnectionSpec(url=...))`
    in its "v0.3.37 (gone)" column beside the 1.0.0 form of the same class. "Listed once per place, each entry with
    that place's form" supported recording the old cell, a call passing a keyword the 1.0.0 dataclass lacks (a
    Critical `signature-mismatch` that blocks the hard gate), and only the reader's own judgment left it out. The
    contract now says such a form is no form of the current export and gives no entry, even for a name the covered
    version no longer exports (no Medium `stale-documentation` gap that tells Update Skill to delete an accurate
    historical row), while the current form beside it is that place's entry; a form marked only deprecated stays a
    form, and a floor place keeps its entry and its `signature`. It extends the rule for a name documented in several
    places, which it directly follows, and the contrast clause now names only another current declaration's form.
    The floor exception is a sentence of its own after both, so it holds for a removed form too: an export table's
    row labelled removed is a floor place, which validate-inventory.py refuses an inventory for leaving out."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    several = SEVERAL_PLACES
    removed = ("A form the skill marks as removed, or as the form of a version before the one it covers (a migration "
               "table's old-version column, a cell or row labelled gone, removed, before or old), is not a form of "
               "the current export and gives no entry, whether or not the covered version still exports the name, "
               "so it is never compared and records no gap: the current form beside it is that place's entry.")
    kept = "A form marked only deprecated, and still present in the covered version, stays a form."
    floor = ("Either way, a place `inventory-floor.json` gives the name still gives it an entry, removed or not, and "
             "a `signature` the floor gives there stays that place's form.")
    assert f"{several} {removed} {kept} {floor}" in contract
    assert contract.count(removed) == 1 and contract.count(kept) == 1 and contract.count(floor) == 1
    # a migration row's old cell is no second form of the name, so the place quotes no contrast that unbinds the other
    assert ("a place that writes two of its forms that differ (a row that documents one declaration's form and "
            "quotes another current declaration's form as a contrast) gives none of them a citation") in contract
    assert "quotes another's as a contrast" not in contract
    paragraphs = [_flow(block).strip() for block in re.split(r"\n[ \t]*\n", _read(INVENTORY_CONTRACT))]
    [paragraph] = [p for p in paragraphs if removed in p]
    assert paragraph.startswith("The contract `validate-inventory.py` checks"), paragraph[:80]
    assert "\u2014" not in paragraph and "\u2013" not in paragraph, "no em or en dash"


def test_the_inventory_contract_says_which_names_and_defs_are_entries_and_forms():
    """#967, #970, #973: the contract left three cases to the reader, so one text scored differently between runs. A
    name written only inside another entry's type (`ExceptionContext` in `Callable[[BaseException, ExceptionContext],
    None]`) was documented in one run and a Medium `missing-export` in the next; a `const` whose value is a function
    (storybook's `withActions`, typed in a description cell) was compared in two runs and skipped in a third; a def an
    example writes as the reader's own code (oms-cocoindex's `mount_table_target(db_key, ...)`) was a blocking
    Critical `signature-mismatch` for one reader and nothing for another. One paragraph of its own settles each in one
    sentence: a name written only in a type position is a type mention and no entry, even as a span that is exactly
    the name in a parameter table's Type cell, unless the skill also writes it as an export outside a type position;
    the constant carries its function form as `params` (`[]` when it takes none, as `""` is never bound on a
    constant) and `return_type`, which score-signatures.py plans; and the def is an entry with no form, unless the
    floor pins its signature. It sits after the contract paragraph and before the `cross_check_mismatches` one, whose
    pin reads to the end of the file; coverage-check.md stays under its budget.

    #1008: a code span that is exactly the name still gave an entry to a name the skill's own prose calls a local
    import alias ("which `grid-cell.tsx` imports as `GridCellType`") or says the source does not export, so one reader
    recorded a Medium `stale-documentation` gap for accurate prose and Info documented extras for seven `*Props`
    types, and the next recorded none. The sentence after the type mention gives such a name an entry only from the
    structural places of the type mention's list, never from a code span in prose or a description cell; those places
    cover every origin the floor lists, so validate-inventory.py never refuses an inventory that follows it.

    #1013: the same code span trigger gave an entry to a name the skill writes only in a sentence saying it does not
    cover it (oms-cognee's "`load_env_file`, `describe_resolution` and `setup_logging` are among them but out of scope
    for this skill"), so one reader recorded a Medium `stale-documentation` gap per such name, whose remediation tells
    update-skill to remove the accurate scoping sentence, and the next recorded none. The sentence after the alias one
    says a not-covered sentence documents nothing and gives no entry, in any form; any other place that documents the
    name, prose that describes it or a place the floor gives included, still gives one, so `setup_logging`, which the
    skill also describes elsewhere, keeps its entry and validate-inventory.py still finds every floor name.

    #1010: the own-code sentence had one trigger, a block that also defines names the skill does not document as
    exports, and its words before the colon read as a rule of their own, so a block that defines only the user's
    function under an export's name, decorated by that export (oms-cocoindex's `@coco.lifespan` over
    `async def lifespan(builder: coco.EnvironmentBuilder):`), was left out by one reader and compared by the next with
    lifespan's overloads as a blocking Critical `signature-mismatch`. The sentence now lists its triggers as the only
    ones: the block also defines undocumented names, or, whatever else it defines, decorates the definition with,
    passes it to or registers it through that export itself, never through an attribute of it, so a quoted
    `@x.setter` over `def x` stays a form; a declaration the floor gives a `signature` still stays that place's form.
    A library's declaration is never decorated by its own name, so the decorator trigger cannot strip a quoted one.

    #1019: the function-valued const sentence never said what a const written only as the call that builds its
    function (oms-uitripled's fenced `const badgeVariants = cva(…)`) records, so one strict run compared it as a
    usage and the next recorded no form, and the `[]` reading made it a form that takes no parameter, a false
    Critical when the built function takes one. The sentence after it gives such a place no `params`, `return_type`
    or `usage_signature`: the call is the factory's form. A component keeps the form #837's sentence gives it, and a
    const that writes its own parameter list, function type or return type keeps the function form.

    #1016: a call with arguments and no types in prose or a description cell became a usage for a function, while the
    function-valued const sentence still sent "wherever the skill writes it, a description cell included" to `params`,
    so such a call of a const had two readings. The const sentence now leaves a call expression of its name to the
    call sentence, which records it in `usage_signature` as it does a function's."""
    type_only = (
        "A name the skill writes only in a type position (a parameter type, a return type or a type argument inside "
        "another entry's documented type or signature, or a parameter table's Type cell) is a type mention, not an "
        "export the skill documents, even when its code span is exactly the name, and gets no entry, unless the "
        "skill also writes it as one outside a type position: a place `inventory-floor.json` gives it, a heading, an "
        "export table's first cell, a code span that is the name or the name then `(`, or a fenced declaration.")
    alias_or_unexported = (
        "A name the skill presents only as a local import alias of another name, or says the source does not export, "
        "is not an export the skill documents either: it gets an entry only from a place `inventory-floor.json` "
        "gives it, a heading, an export table's first cell or a fenced declaration of it (an import is not one), "
        "never from a code span in prose or a description cell.")
    not_covered = (
        "A sentence saying the skill does not cover a name (\"out of scope for this skill\", \"not covered here\") "
        "does not document it and gives it no entry, whatever form it writes the name in; any other place that "
        "documents the name (a form, prose or a description cell that calls or describes it, or a place "
        "`inventory-floor.json` gives it) still gives it one.")
    function_constant = (
        "A `const` whose value is a function (annotated with a function type, bound to an arrow, a `function` or a "
        "call that returns one, or written with a parameter list) carries the function form the skill writes for it "
        "as `params` (`[]`, never `\"\"`, when it takes none) and `return_type`, whatever its kind (`constant` for the "
        "skill's `const` label), wherever the skill writes it, a description cell included, except a call "
        "expression of its name, which is recorded in `usage_signature` as a function's is (above); a bare `name()` "
        "there is still a mention; only a constant holding neither a component nor a function is a data constant.")
    factory_constant = (
        "A `const` holding a function, not a component, that a place writes only as the call that builds it "
        "(`const badgeVariants = cva(…)`), with no parameter list, function type or return type of its own, "
        "carries no `params`, `return_type` or `usage_signature` there: that call is the factory's form, not the "
        "const's.")
    own_code = (
        "A function or class an example defines is the reader's own code, not a form of a same-named export, only at "
        "a place `inventory-floor.json` gives no `signature` and only when its fenced block also defines names the "
        "skill does not document as exports or, whatever else the block defines, decorates the definition with, "
        "passes it to or registers it through that export itself, by its name or through a receiver or module path "
        "(`@coco.lifespan` over `async def lifespan(builder: coco.EnvironmentBuilder):`), never through an attribute "
        "of it such as `@x.setter`: its entry there leaves `params`, `return_type` and `usage_signature` out, as a "
        "mention's does, so it is never compared and records no gap; a declaration the floor gives a `signature` "
        "stays that place's form.")
    text = _read(INVENTORY_CONTRACT)
    paragraphs = [_flow(block).strip() for block in re.split(r"\n[ \t]*\n", text) if block.strip()]
    paragraph = f"{type_only} {alias_or_unexported} {not_covered} {function_constant} {factory_constant} {own_code}"
    assert paragraphs.count(paragraph) == 1, "the six sentences are one paragraph of their own"
    # #1019: a const written only as its factory call writes no form there, whatever the built function takes, so no
    # reader records the call as its usage or `[]` as its params; a component and a const with a form of its own
    # stay out of it
    for phrase in ("holding a function, not a component", "a place writes only as the call that builds it",
                   "with no parameter list, function type or return type of its own",
                   "carries no `params`, `return_type` or `usage_signature` there",
                   "that call is the factory's form, not the const's."):
        assert phrase in factory_constant, phrase
    # #1013: the not-covered sentence names both phrasings, takes away every form the sentence writes, and keeps the
    # entry any other place gives, prose that describes the name and a floor place included, so it narrows only that
    # sentence and never drops a name validate-inventory.py requires
    for phrase in ('"out of scope for this skill"', '"not covered here"', "whatever form",
                   "prose or a description cell that calls or describes it",
                   "a place `inventory-floor.json` gives it"):
        assert phrase in not_covered, phrase
    # #1008: the alias sentence keeps the type mention's structural places and drops only its code spans, so a name
    # the floor lists (a table row, a heading or a fenced declaration) keeps the entry validate-inventory.py requires
    for place in ("a place `inventory-floor.json` gives it", "a heading", "an export table's first cell",
                  "a fenced declaration"):
        assert place in type_only and place in alias_or_unexported, place
    assert "a code span that is the name" in type_only and "a code span that is the name" not in alias_or_unexported
    # #1010: the own-code triggers are the only ones, so the words before them never decide alone; a decorated,
    # passed or registered def is the reader's own code whatever else its block defines, the decorator being the
    # export itself (a quoted property setter stays a form), and a floor `signature` still keeps its place's form
    assert "is not a form of a same-named export:" not in paragraph
    for phrase in ("only at a place `inventory-floor.json` gives no `signature` and only when",
                   "its fenced block also defines names the skill does not document as exports or",
                   ("whatever else the block defines, decorates the definition with, passes it to or registers it "
                    "through that export itself"),
                   "(`@coco.lifespan` over `async def lifespan(builder: coco.EnvironmentBuilder):`)",
                   "never through an attribute of it such as `@x.setter`"):
        assert phrase in own_code, phrase
    assert own_code.endswith("a declaration the floor gives a `signature` stays that place's form.")
    at = paragraphs.index(paragraph)
    assert paragraphs[at - 1].startswith("The contract `validate-inventory.py` checks"), paragraphs[at - 1][:80]
    assert paragraphs[at + 1].startswith("A `cross_check_mismatches` entry gives"), paragraphs[at + 1][:80]
    # the pins on the contract paragraph and the cross-check one still find their own text alone
    for pinned in ("A `cross_check_mismatches` entry gives", "Where the skill documents several names",
                   "keeps one `kind` in every place."):
        assert pinned not in paragraph, pinned
    # #837's sentence stays as it was, in the contract paragraph: the new sentence narrows only its data constant
    assert ("A `const` holding a component (a `forwardRef`, `memo` or other wrapper call, or an alias like "
            "`const Tabs = TabsPrimitive.Root`) is a `constant` with the declaration or usage form the skill writes as "
            "`usage_signature`; a data constant carries no `usage_signature`, `params` or `return_type`."
            ) in paragraphs[at - 1]
    assert "\u2014" not in paragraph and "\u2013" not in paragraph, "no em or en dash"
    assert len(_read(COVERAGE)) < COVERAGE_CHAR_BUDGET


def test_a_module_s_function_is_a_function_never_a_method():
    """6.0.0 release gate (oms-cognee): the contract gave a `method` "the class or namespace it is called on" as its
    `owner`, so a reader recorded the module `cognee.tools`'s functions as methods owned by `tools`, and coverage,
    which counts no `method` entry (reconcile-coverage.py), reported them undocumented. A method's owner is a class
    or an object, and a function a module holds is a `function` named bare, even when called through the module."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    assert ("A `method`'s `name` is the bare method name and its `owner` the class or object it is called on "
            "(`agents` for `cognee.agents.get`, where the skill documents `agents` as a class;") in contract
    assert ("A function the skill documents in a module is a `function` named bare, never a `method`, even when it "
            "is called through the module's name (`register_sql_connection` for "
            "`cognee.tools.register_sql_connection`, where the skill documents `tools` as a module).") in contract
    assert "class or namespace" not in contract


def test_the_inventory_contract_keeps_the_members_several_names_share():
    """6.0.0 release gate (oms-cognee): one SKILL.md row documented six models, stating their shared base fields
    (the required `external_id` among them) once and then each model's own fields. The reader recorded each
    model's own fields alone, a form that writes defaults and so claims a complete list, and every model was a
    Critical gap for leaving out `external_id`; two judges given the whole row judged it a match. The contract
    has each name's entry carry, in its `params` (never a `methods` item), the shared text first, then `; `,
    then its own members without its name, as the skill writes them, whether the shared members sit in the same row
    or paragraph or over a table for all its rows, and its example shows one, so the verdict no longer depends on
    how the reader cuts the row. #1034 (oms-cognee): a namespace row listed `.create`, `.get` and the others bare,
    each with an optional `user`, and linked to their signatures; two readers gave each name the shared text alone
    as its form (19 High split-body and 6 Critical gaps) and a third gave none (0). A name such a place lists bare,
    with no form of its own there, is now a mention at that place, and the shared text goes only to names the place
    gives members of their own. A whole form the place writes once for all its names (a Signature cell beside a
    first cell that lists `get` and `head`) is no shared text: it stays each name's form there, still compared, so
    the bare-name case never drops a check on a whole shared signature and no reader can read that row two ways."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    shared = ("Where the skill documents several names and states members they share once, in the same place (a "
              "table row, a paragraph) or over a table for all its rows (a sentence or caption just above it, or its "
              "column header), each name's entry carries that shared text in its `params` (in its `usage_signature`, "
              "for a usage form), never in a `methods` item, which still starts with the method's name: the shared "
              "text first, the members the place states once without the words that introduce them, then `; `, then "
              "the name's own members as the skill writes them, without the name, never "
              "the name's own members alone (`Note` above, from a row that documents `Note` and `Task`, each with the "
              "base fields `id, scope=Scope()`, as `Note(content, title=None)` and `Task(title, done=False)`).")
    bare = ("A name such a place lists bare, with no parameter list, call or signature of its own there (`.get` in a "
            "namespace row that lists `.create`, `.get` and `.delete`, each with an optional `user`, and links to "
            "their signatures), is a mention at that place: its entry leaves `params`, `return_type` and "
            "`usage_signature` out, and the shared text applies only to names the place gives members of their own; "
            "a whole parameter list, call or signature the place writes once for every name it lists (the Signature "
            "cell of a row whose first cell lists `get` and `head`) is no shared text but each of those names' own "
            "form there, recorded as written.")
    # the bare-name case follows the clause whose shared text it withholds, so "such a place" is that clause's place
    assert f"{shared} {bare}" in contract
    assert contract.count(bare) == 1
    # after the rule for a name documented in several places, which it extends to several names in one place
    assert contract.index("A name documented in several places is listed once per place") < contract.index(
        "Where the skill documents several names and states members they share once")
    example = json.loads(re.search(r"```json\n(.*?)\n```", _read(INVENTORY_CONTRACT), re.S).group(1))["exports"]
    [note] = [e for e in example if e["name"] == "Note"]
    shared, own = note["params"].split("; ")
    # coherence review (oh-my-skills cognee): an example whose shared text kept the words that introduce it
    # (`each with the base fields`) had a reader write the skill's prose into `params`, which the judge then reads
    assert (shared, own) == ("id, scope=Scope()", "content, title=None"), (
        "the shared members first, then `; `, then the name's own members, without the name")
    assert "Note" not in note["params"]
    assert len(_read(COVERAGE)) < COVERAGE_CHAR_BUDGET


def test_the_inventory_contract_routes_each_written_form_to_a_field():
    """#916 (oms-cocoindex): a placeholder call such as `await coco.mount([subpath,] process_fn, *args, **kwargs)`
    could be recorded as `params` and read as parameter names, a Critical in Python; the contract records a call
    expression, a function's or a class's, whole as a usage, which the rules read as a call, unless the floor pins its
    place, while a class written as a parameter list or a signature (`Note`) keeps `params`. #917: an own member
    the skill puts before or among the shared ones could not be encoded, since own members always followed `; `;
    the entry now writes the whole list in the skill's order, since #1028 at a place the floor pins too, unless it
    pins a usage form there, which validate-inventory.py still carries only as given or after `; `. #931: a Prop/Type/
    Default table had no encoding, so one table gave a false Critical, a match or no check by how it was flattened;
    it is now an entry of its own, at the heading or caption above it that writes the name, its rows one object type
    with no mark, so it states no optionality. Each sentence sits at its place on the contract's paragraph, and
    coverage-check.md, which loads the contract, does not grow. #1019: the call expression is one of the entry's own
    name, so `const badgeVariants = cva(…)`, a call after an assignment, is a form of `cva`, never of
    `badgeVariants`, while `h = await coco.mount(fn)` stays a form of `mount`. #1014: in running text or a
    description cell the sentence takes only a call that passes an argument, so `await cognee.disconnect()` in prose
    stays the mention the sentence before it makes it, never also a usage. #1016 (oms-uitripled): a call with
    arguments and no prefix in running text or a description cell, such as `add(componentName, options)`, matched
    no listed context, so one reader recorded it as a usage and another as bare-name `params`, whose names a Python
    declaration grades Critical; the sentence now takes such a call with or without a prefix, unless it writes a
    parameter type, a return type or a `?`, which leaves it a signature. Its tail keeps in `params` only a class's
    parameter list or signature that is not such a call, so `Note(content, title=None)`, which a description cell
    would make a usage, is the example's form only because it sits in a Signature cell.
    #1002 (oms-cognee): the contract named only props tables, so a `| Param | Type | Default | Description |` table
    of one function's parameters was compared by one reader and recorded nothing for another; it is now a place of its
    own after the props table, its rows one typed parameter list with no mark, and a partial label in its column
    header, its caption or the nearest heading above it (`### Key parameters`) labels it partial. Under a heading
    that already writes the name's form, the table adds no entry: two forms at one place would bind neither to the
    declaration its citation names, for a name declared more than once."""
    s1 = ("A function's, a method's or a class's form the skill writes as a call expression of its own name (after "
          "`await`, "
          "`new` or an assignment, through a receiver or module path such as `coco.`, or as a statement in a "
          "fenced example; in running text or a description cell, only a call that passes an argument and writes "
          "no parameter type, `?`, bare `*` or `/`, with or without such a prefix, and no return type unless such "
          "a prefix comes before the name, such as `add(componentName, options)` or `await coco.mount(fn) -> "
          "Handle`), at a place `inventory-floor.json` gives no `signature` (below), is recorded whole in "
          "`usage_signature`, as `inventory-floor.json` writes a usage (an assignment, `await`, `new`, a receiver "
          "or module path before the name kept, through the call's closing parenthesis or the element's end, never "
          "an `@`, a `with` or text after the call), never in `params`, whatever names its arguments use, and a "
          "return type the skill writes for it in `return_type`, while a class's form written as a parameter list or a signature that is not such a call "
          "stays in `params` (`Note` above, written in a Signature cell): signature-comparison-rules.md reads a "
          "usage as a call and a list of bare names in `params` as parameter names.")
    s2 = ("When the skill places one of the name's own members before or among the shared ones (`leading`, "
          "`first`), the entry writes the name's whole list in the order the skill gives instead, the shared members "
          "spelled out and no `; `, unless `inventory-floor.json` gives that place a usage form, whose "
          "`usage_signature` then stays after the shared text and `; `.")
    s3 = ("A table that documents one export's props, a row per prop with its type (Create Skill's "
          "`| Prop | Type | Default | Description |`, or one with a Required column), is a place of its own: its "
          "entry, whatever its kind, gives as `at` the nearest heading or caption above the table that writes the "
          "name (a row writes a prop, not the name, and a call or JSX element of the name a row's cell writes is an "
          "example of that prop, never a place of its own) and as `params` one object type of the rows in row order, "
          "`{ prop: Type; ... }`, `prop` alone for an empty Type cell and each `\\|` read as `|`, with no default, `?` "
          "or Required mark, so it states no optionality (signature-comparison-rules.md compares it as a typed props "
          "list); a partial label in its column header still labels it partial.")
    s4 = ("A table that documents one function's, method's or class constructor's parameters, a row per parameter "
          "with its type (`| Param | Type | Default | Description |`, or one with a Required column), is a place of "
          "its own too: its entry, whatever its kind, gives as `at` the nearest heading or caption above the table "
          "that writes the name (a row writes a parameter, not the name) and as `params` one parameter list of the "
          "rows in row order, `param: Type, ...`, `param` alone for an empty Type cell and each `\\|` read as `|`, "
          "with no default, `?` or Required mark, so it states no optionality (signature-comparison-rules.md reads "
          "it as a typed parameter list); a partial label in its column header, its caption or the nearest heading "
          "above it (`### Key parameters`) labels it partial; when that heading or caption writes a form of the name "
          "itself (`### connect(host: str, port: int = 5432)`), the table adds no entry there, so that place keeps "
          "one form and its citations still bind it.")
    [paragraph] = [p for p in _read(INVENTORY_CONTRACT).split("\n\n")
                   if p.startswith("The contract `validate-inventory.py` checks")]
    contract = _flow(paragraph)
    # S1 after the rule that a heading's `name()` is a form, before the methods; S2 after the shared text it
    # extends and the bare-name case beside it (#1034), before the partial label; S3 then S4, the parameter table
    # it extends to functions (#1002), end the paragraph.
    assert f"is a form, recorded as written. {s1} {EXAMPLE_CALL} A `method`'s `name` is the bare method" in contract
    assert (f"is no shared text but each of those names' own form there, recorded as written. {s2} An entry whose "
            "signature the skill labels partial") in contract
    assert contract.endswith(f"copy the label, never judge the form. {s3} {s4}"), contract[-200:]
    for sentence in (s1, s2, s3, s4):
        assert contract.count(sentence) == 1, sentence
    assert "whose `params` then stays after the shared text" not in contract, "#1028: a pinned `params` is in order"
    assert "\u2014" not in paragraph and "\u2013" not in paragraph, "no em or en dash"
    assert len(_read(COVERAGE)) < COVERAGE_CHAR_BUDGET


# #997: a call a fenced example writes is no place of its own beside the name's form elsewhere.
EXAMPLE_CALL = (
    "A call or JSX element of a name that a fenced example writes is not a place of its own when the skill also "
    "writes that name's form at a place that is no example (a heading, a table row, a props table, running text or "
    "a fenced declaration), unless the nearest heading above the example names a usage, its text holding the word "
    "usage whatever qualifies it (`## Usage`, `### Basic usage`, `### Usage pattern`; a bold label line such as "
    "`**Usage:**` is no heading): it gives no entry, so it is never "
    "compared, and a name whose only forms are in fenced examples keeps them.")


def test_the_inventory_contract_gives_an_example_call_beside_a_form_no_entry():
    """#997 decision 1: whether a reader recorded a call a fenced example writes (storybook's `defineMain({ ... })`
    and `withThemeFromJSXProvider({ ... })`) beside the name's documented signature was the reader's choice, so
    three readers recorded different usage forms and a run compared a form the next one did not. The contract now
    says such an example is no place of its own and gives no entry, unless the nearest heading above it names a
    usage, while a name whose only forms are in fenced examples keeps them, so its docs-only coverage still counts
    it. A bold label line such as `**Usage:**` is no heading (review of #997: storybook writes its `defineMain`
    example under one, which one reader could count as a usage heading and the next not). The sentence follows the
    call-expression rule it narrows, in the contract paragraph, and coverage-check.md, which loads the contract,
    does not grow."""
    [paragraph] = [p for p in _read(INVENTORY_CONTRACT).split("\n\n")
                   if p.startswith("The contract `validate-inventory.py` checks")]
    contract = _flow(paragraph)
    assert contract.count(EXAMPLE_CALL) == 1
    assert f"as parameter names. {EXAMPLE_CALL} A `method`'s `name`" in contract
    assert "\u2014" not in EXAMPLE_CALL and "\u2013" not in EXAMPLE_CALL, "no em or en dash"
    assert len(_read(COVERAGE)) < COVERAGE_CHAR_BUDGET


def test_a_method_with_a_form_of_its_own_gets_an_entry_and_no_receiver(tmp_path):
    """Coherence review (oh-my-skills rehearsals): no sentence said whether a method a class's place writes with its
    own form (cognee's GraphSnapshot row, cocoindex's Task body) gets a `method` entry besides its `methods` item, so
    one reader cross-checked all of Task's methods and another none; whether a call through an instance
    (`builder.provide(KEY, value)`) is that method's place; and whether `canvas.getByRole('button')`, read literally
    through the receiver clause, is a usage of the `getByRole` function, a false Critical. Readers also kept or
    dropped a leading `self` in a class's form read from `def __init__(self, ...)`. Each now has one reading.
    Coherence review of that fix (rehearsal of oms-cognee): the call sentence named only a function's or a class's
    form, so for a method written as an untyped call in a methods list or a bullet (Task's `execute(args, kwargs,
    next_batch_size=None)`, cognee's config setters) two readers wrote bare-name `params` and one a usage, where all
    three had written a usage before; it now names a method's form too, and the method
    sentence records such a call in `usage_signature`, a running-text place included. One reader also read a class
    body's `def __init__(self, ...)` as a `method` entry and gave `Task` and `CogneeApiError` no `params`, which left
    the constructor out of the signature check; a class body's constructor is now its class's `params`. Coherence
    review of that fix: it named only a class body, so a constructor a methods list (oms-cocoindex 0.3.37's
    `__init__(fl: Flow, ...)` under `**FlowLiveUpdater**`) or a row's cell (1.0.0's `Environment` row) writes still
    fell under the method sentence, an uncompared `__init__` method entry for a literal reader and the class's
    `params` for one who read by analogy. Every place's constructor is now its class's `params`, at the `class` line
    or else the nearest line of that place that writes the class's name, which the validator keeps with no warning
    where the `__init__` line itself would be dropped."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    methods = ("Each `methods` item starts with the method's name, optionally after `async` (`async "
               "next_uuid(dep=None)`). A method a place writes with a form of its own (a class body, a methods list, "
               "a row's cell, running text) gets a `method` entry there with that form, a call recorded in "
               "`usage_signature` as a function's is (`execute(args, kwargs, next_batch_size=None)` in a methods "
               "list), besides its class's `methods` item, and so does one the skill calls through an instance or the "
               "class it documents with that member (`builder.provide(KEY, value)`, `canvas.getByRole('button')`), "
               "the class as `owner` and the call in `usage_signature`, never a usage of a same-named function. A "
               "constructor a place writes (`def __init__(self, ...)`, `constructor(...)`, in a class body, a methods "
               "list, a row's cell or running text) is its class's form, never a `method` entry: the class's "
               "`params`, at the `class` line in a class body, else at the nearest line of that place that writes the "
               "class's name (a label line such as `**FlowLiveUpdater**`). A class's `params`, a `method`'s and each "
               "`methods` item leave out a leading `self` or `cls`. A `const` holding a component")
    assert contract.count(methods) == 1
    assert "A constructor a class body writes" not in contract
    assert contract.count("A function's, a method's or a class's form the skill writes as a call expression") == 1
    assert "A function's or a class's form the skill writes as a call expression" not in contract
    assert contract.index("A function the skill documents in a module is a `function` named bare") < contract.index(
        methods), "after the module-function rule it sits beside"
    validator = runpy_module(SCRIPTS_DIR / "validate-inventory.py")
    package = tmp_path / "skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "# Demo\n\n**`FlowLiveUpdater`**\n\n- `__init__(fl: Flow, options: FlowLiveUpdaterOptions | None = None)`\n"
        "- `start()`\n", encoding="utf-8")

    def ctor_at(at):
        entry = {"name": "FlowLiveUpdater", "kind": "class", "description": "",
                 "params": "fl: Flow, options: FlowLiveUpdaterOptions | None = None", "at": at}
        inventory = {"exports": [entry], "references": [], "cross_check_mismatches": []}
        return validator.validate_inventory(json.dumps(inventory), str(package))

    label = ctor_at("SKILL.md:3")
    assert label["valid"] is True and label["warnings"] == [], (label["violations"], label["warnings"])
    assert label["inventory"]["exports"][0]["at"] == "SKILL.md:3"
    init_line = ctor_at("SKILL.md:5")
    assert init_line["valid"] is True and "at" not in init_line["inventory"]["exports"][0]
    assert any("does not write `FlowLiveUpdater`" in w for w in init_line["warnings"]), init_line["warnings"]


def test_a_type_alias_carries_no_form_and_an_unlabelled_const_is_a_constant():
    """Coherence review (oh-my-skills storybook): one reader gave `DecoratorFunction`, `ViteFinal` and
    `HandlerFunction`, `type` aliases the skill writes as function types, the type's parameters and return, which
    the signature check then compares with the alias's declaration, and two gave mentions; and with no kind label a
    fenced `export const viteFinal = async (...) =>` was a `function` for two readers and a `constant` for the
    third. A type alias now carries no form, and an unlabelled `const` is a `constant`, while it still carries the
    function form the skill writes for it."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    sentences = ("a data constant carries no `usage_signature`, `params` or `return_type`. A `type` alias carries none "
                 "of them either, even one the skill writes as a function type (`type DecoratorFunction = (fn, c) => "
                 "R`): only a value is called. A name the skill declares with `const`, a fenced `export const` "
                 "included, is a `constant` when the skill gives it no kind label.")
    assert contract.count(sentences) == 1
    assert "carries the function form the skill writes for it as `params`" in contract
    assert "whatever its kind (`constant` for the skill's `const` label)" in contract


def test_a_column_s_partial_label_reaches_every_form_its_cells_write_as_the_floor_reads_it():
    """Coherence review (oh-my-skills rehearsals): "labels each of its rows" left open whether a column's label
    reaches a usage form or another name's form a row's cell writes (cognee's `cognee_network_visualization` inside
    `visualize_graph`'s Key params cell, storybook's `<Meta of={ButtonStories} />` under `Purpose and key params`),
    and a return-only form; whether a header that names key parameters among other words labels at all, which the
    floor reads as no label; and whether `api_key=...`, an argument's value, labels a call partial. The label now
    reaches every form the cells write, only from a whole `Key params` header or one in parentheses after its word,
    never from an argument's value, and a return-only form carries none."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    sentence = ("An entry whose signature the skill labels partial (simplified, key parameters, a `...` standing in "
                "for omitted members as a member or argument of its own, not rest or variadic syntax nor an "
                "argument's value such as `api_key=...`; a label in a table's column header, such as `Props "
                "(simplified)`, labels each of its rows, every form their cells write included, a usage form or "
                "another name's form among them, but only as the whole header, `Key params`, or in parentheses after "
                "its word, as inventory-floor.json reads one, so `Purpose and key params` labels none) carries "
                "`signature_form: \"partial\"`, any other `\"full\"` or no key, and a form that writes only a "
                "`return_type` carries none: copy the label, never judge the form.")
    assert contract.count(sentence) == 1
    floor = runpy_module(SCRIPTS_DIR / "load-coverage-inputs.py")
    assert {"key params", "key parameters"} <= floor.FLOOR_PARTIAL_LABELS
    assert floor._header_label("Purpose and key params")[1] is False
    assert floor._header_label("Props (simplified)")[1] is True


def test_a_qualified_usage_heading_a_props_row_call_and_a_fenced_comment_are_read_one_way():
    """Coherence review (oh-my-skills rehearsals): readers split on whether `### Usage pattern` or
    `### Per-test-file usage` names a usage, so a fenced call under it was a place for one reader and none for
    another; on whether a props table row's `<Canvas of={ButtonStories.Primary} />` is a usage of the component; and
    on whether a comment line in a fenced block, such as storybook's `//   start: ({ ... }: { ... }) => Promise<...>`
    or cognee's `# no return annotation; returns the dataset's PipelineRunInfo`, writes a form or a return type the
    signature check then compares. A heading whose text holds the word usage names one, a call or element a props
    row writes is an example of that prop, and a comment is no place and states no form or return type."""
    contract = _flow(_read(INVENTORY_CONTRACT))
    assert ("its text holding the word usage whatever qualifies it (`## Usage`, `### Basic usage`, "
            "`### Usage pattern`") in EXAMPLE_CALL
    assert ("(a row writes a prop, not the name, and a call or JSX element of the name a row's cell writes is an "
            "example of that prop, never a place of its own)") in contract
    comment = ("A comment in a fenced block is no place of its own and states no form or return type: a form or a "
               "return it writes (`// start: ({ options }: {...}) => Promise<void>`, `# returns the dataset's "
               "PipelineRunInfo`) is a note on the code, not a form of the name.")
    assert contract.count(comment) == 1
    assert contract.index("An entry with no compared form gives its place as `at` too") < contract.index(comment), (
        "beside the rules for a place's line")


def test_the_inventory_subagent_writes_its_own_response():
    """#814: the §1 subagent writes its JSON to the run file with the Write tool, never through a shell, and returns
    the path, or returns the JSON itself when it cannot write files; the parent saves the response with the Write
    tool only when the subagent returned the JSON or the file is absent or empty afterwards. Before the one
    re-dispatch the refused file is deleted, so a stale response is never validated twice. The signature subagents'
    responses are still the parent's to save."""
    text = _read(COVERAGE)
    section1 = _flow(_slice(text, "### 1. Extract Documented Exports", "#### 1a."))
    assert "Delegate the reading of the skill under test to a subagent, given `{run_dir}` and the path" in section1
    # The subagent's side: the Write tool, or the JSON returned.
    assert ("It writes only this JSON, with no prose and no commentary, to `{run_dir}/inventory-response.txt` with "
            "the Write tool, never a shell, and returns that path, or returns the JSON itself when it cannot write "
            "files. The JSON's shape and the contract the validator checks are in `{inventoryContractFile}`, whose "
            "absolute path (under `{skill-root}`) the subagent is given.") in section1
    # The parent's side: a save only when there is no file to validate.
    assert ("When the subagent returned the JSON rather than the path, or the file is absent or empty afterwards, "
            "save its response, as it came back, to `{run_dir}/inventory-response.txt` with the Write tool.") in section1
    assert "Save the subagent's response" not in section1 and "Save the response of a subagent" not in section1
    branches = _read(COVERAGE_BRANCHES)
    rm = 'rm -f "{run_dir}/inventory-response.txt"'
    assert rm in _fence(_slice(branches, "## Inventory Failures", "## States 2 to 4"), rm)
    failures = _flow(_slice(branches, "## Inventory Failures", "## States 2 to 4"))
    assert "delete the response `{validateInventoryScript}` refused, so a stale one is never validated twice" in failures
    assert failures.index(rm) < failures.index("Re-dispatch the §1 subagent once")
    assert ("it writes its new response to that file, or returns it for you to save there, as §1 says. Run the §1a "
            "command again.") in failures
    run_files = _flow(_slice(text, "**Run files.**", "### 0."))
    assert ("A subagent's response is saved there exactly as it came back, fence and all (the subagent writes it to "
            "the path it is given, or the parent saves it, with the Write tool), and passed by path") in run_files
    assert "`{run_dir}/signatures-<n>.txt` with the Write tool" in _flow(text)
    doc = _flow(runpy_module(SCRIPTS_DIR / "validate-inventory.py").__doc__)
    assert ("the coverage-check.md §1 subagent writes its response to the path it is given with the Write tool, and "
            "the parent saves it there with the Write tool when the subagent returned it instead or left the file "
            "absent or empty") in doc


def test_the_inventory_reader_reads_the_skill_alone():
    """#1036: the §1 reader reads only the files §1 hands it, and never an earlier run's folder, test report,
    ledger or result file, which halted runs leave beside `{run_dir}`, so its inventory reads the skill alone and
    copies no earlier run's readings. The rule names those files outright and lives in the contract the reader is
    handed by absolute path and reads itself, so it reaches the reader whatever the parent's prompt says, and
    coverage-check.md stays under its budget."""
    text = _read(INVENTORY_CONTRACT)
    scope = ("The reader in coverage-check.md §1 reads only the files that section hands it: SKILL.md, the "
             "`references/*.md` files, `inventory-floor.json`, this contract and signature-comparison-rules.md. It "
             "never opens another run's folder under `_bmad-output/.skf-run/`, a test report, a "
             "`test-findings-*.json` ledger or a `skf-test-skill-result-*.json` file, so its inventory reads the "
             "skill alone.")
    [paragraph] = [p for p in text.split("\n\n") if p.startswith("The reader in coverage-check.md §1 reads only")]
    assert scope in _flow(paragraph)
    assert text.index(paragraph) < text.index("```json"), "before the JSON shape, the first thing the reader reads"
    assert "\u2014" not in paragraph and "\u2013" not in paragraph, "no em or en dash"
    # The files it may read are the ones §1 hands it; the contract reaches the reader by absolute path, and without
    # subagents the parent loads it and builds the inventory under the same rule.
    coverage = _read(COVERAGE)
    section1 = _flow(_slice(coverage, "### 1. Extract Documented Exports", "#### 1a."))
    for handed in ("given `{run_dir}` and the path to SKILL.md and to its `references/` directory",
                   "It is given `{run_dir}/inventory-floor.json` too",
                   "`{signatureRulesFile}`, whose absolute path (under `{skill-root}`) it is given",
                   "in `{inventoryContractFile}`, whose absolute path (under `{skill-root}`) the subagent is given",
                   "Without subagents, the parent loads `{inventoryContractFile}`"):
        assert handed in section1, handed
    assert f"signatureRulesFile: 'references/{SIGNATURE_RULES.name}'" in coverage
    # The earlier-run files it names are the ones a run leaves: its run folder, report, ledger and result record.
    assert 'mkdir -p "{project-root}/_bmad-output/.skf-run/skf-test-skill-{run_id}"' in _read(INIT)
    assert "ledgerFile: '{forge_version}/test-findings-{run_id}.json'" in coverage
    report = _read(REPORT)
    assert "publishedReportFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'" in report
    assert "It writes `{forge_version}/skf-test-skill-result-{YYYYMMDD-HHmmss}.json`" in report
    assert len(coverage) < COVERAGE_CHAR_BUDGET


def test_the_inventory_reader_runs_no_script_and_writes_one_file():
    """#1046: the §1 reader runs no SKF script, reads no script's code, and writes or deletes no file but its
    response, so it never validates and fixes its own draft out of sight, settles a reading by what the scripts
    accept, or leaves and deletes a file outside `{run_dir}`. Validation is §1a's, with the one re-dispatch
    Inventory Failures allows. The rule joins #1036's in the contract the reader is handed by absolute path and
    reads itself, the file that names `validate-inventory.py` to it, so coverage-check.md stays under its budget."""
    text = _read(INVENTORY_CONTRACT)
    limit = ("It runs no SKF script (coverage-check.md §1a runs `validate-inventory.py` on its response), reads no "
             "script's code, and writes or deletes no file but `{run_dir}/inventory-response.txt`: this contract and "
             "signature-comparison-rules.md alone decide its readings.")
    [paragraph] = [p for p in text.split("\n\n") if p.startswith("The reader in coverage-check.md §1 reads only")]
    assert limit in _flow(paragraph)
    assert _flow(text).count("It runs no SKF script") == 1
    assert text.index(paragraph) < text.index("```json"), "before the JSON shape, the first thing the reader reads"
    assert text.index(paragraph) < text.index("The contract `validate-inventory.py` checks"), "before it names it"
    assert "\u2014" not in paragraph and "\u2013" not in paragraph, "no em or en dash"
    # The script it leaves alone is the one §1a runs on that file, and a refused response gets one re-dispatch.
    coverage = _read(COVERAGE)
    assert "validateInventoryScript: 'scripts/validate-inventory.py'" in coverage
    section1a = _flow(_slice(coverage, "#### 1a.", "### 1b."))
    assert 'uv run {validateInventoryScript} --input "{run_dir}/inventory-response.txt"' in section1a
    failures = _flow(_slice(_read(COVERAGE_BRANCHES), "## Inventory Failures", "## States 2 to 4"))
    assert "Re-dispatch the §1 subagent once" in failures
    # The one file it writes is the one §1 hands it, with the Write tool; run state stays in `{run_dir}`.
    section1 = _flow(_slice(coverage, "### 1. Extract Documented Exports", "#### 1a."))
    assert "to `{run_dir}/inventory-response.txt` with the Write tool, never a shell" in section1
    assert "Run state (the scripts' files, the emitter's payloads) lives in `{run_dir}`" in _read(SKILL_MD)
    assert f"signatureRulesFile: 'references/{SIGNATURE_RULES.name}'" in coverage
    assert len(coverage) < COVERAGE_CHAR_BUDGET


@pytest.mark.parametrize("left", ["absent", "empty"])
def test_an_inventory_file_left_absent_or_empty_is_saved_before_it_is_validated(tmp_path, left):
    """#814: a subagent that returned the JSON, or wrote nothing, leaves no response to validate: the §1a command
    exits 1 on that file and writes no inventory, so the parent's save comes first, and the response saved as it
    came back, fence and all, then validates."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n\n`fetchData(url)` fetches.\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    response = run / "inventory-response.txt"
    if left == "empty":
        response.write_bytes(b"")
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix()}
    _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)
    command = _command(COVERAGE, "uv run {validateInventoryScript}")
    rest = command.split("uv run {validateInventoryScript} ", 1)[1]
    for key, value in values.items():
        rest = rest.replace(key, value)
    proc = subprocess.run([sys.executable, str(PROSE_SCRIPTS["{validateInventoryScript}"]), *shlex.split(rest)],
                          cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert not (run / "inventory.json").exists()
    response.write_bytes(("```json\n" + json.dumps({"exports": [
        {"name": "fetchData", "kind": "function", "params": "url: string", "return_type": "string",
         "description": "Fetches.", "at": "SKILL.md:7"}], "cross_check_mismatches": []}) + "\n```\n").encode("utf-8"))
    assert _exec(command, values, tmp_path)["valid"] is True
    assert (run / "inventory.json").is_file()


def test_an_invalid_inventory_is_redispatched_once_then_halts_with_its_reason():
    section = _flow(_slice(_read(COVERAGE), "#### 1a. Parent-Side Schema Validation", "### 1b."))
    # The failures are a rare branch, carved into the branch file; the halt stays in the step.
    assert ("- `valid` false (exit 2), or exit 1: load `{coverageBranchesFile}` and follow its **Inventory Failures** "
            "section. Invalid a second time: HALT") in section
    failures = _flow(_slice(_read(COVERAGE_BRANCHES), "## Inventory Failures", "## States 2 to 4"))
    assert "Re-dispatch the §1 subagent once, with the script's `violations[]` appended" in failures
    assert "(an absent name as a name the skill does not write, a floor name as one it must keep)" in failures
    assert 'HALT (`halt_reason: "inventory-invalid"`, phase `coverage-check:inventory`)' in section
    assert "failed {schema validation | the ground-truth spot-check | the floor check} twice" in section
    assert "place (`at`) check" not in section, "a missing or bad place is a warning, never a halt (#918)"
    assert "SKF_TEST_RESULT_JSON" not in _read(COVERAGE), "the emitter prints the line"
    table = _flow(_slice(_read(CONTRACT), "| `halt_reason` | Raised by |", "When the emitter itself"))
    assert ("| `inventory-invalid` | coverage-check.md §1a: the documented inventory failed its schema check, "
            "spot-check or floor check twice |") in table


def test_the_spot_check_is_the_scripts():
    """#598 item 5: the §1a sample and the look-up run in validate-inventory.py, never a grep."""
    section = _slice(_read(COVERAGE), "#### 1a. Parent-Side Schema Validation", "### 1b.")
    command = _command(COVERAGE, "uv run {validateInventoryScript}")
    assert '--skill-package "{resolved_skill_package}"' in command
    assert "grep -n" not in section and "[0, len//2, len-1]" not in section
    assert "an export named `$state` or `a.b` is neither a shell variable nor a regex" in _flow(section)


FLOOR_COMMAND = ('uv run {coverageInputsScript} floor --skill-dir "{resolved_skill_package}" '
                 '--output "{run_dir}/inventory-floor.json"')


def test_the_floor_runs_before_the_inventory_subagent():
    """#790: the floor, the names the skill documents in a fixed form, is written before the §1 reader is
    dispatched, and both paths read it: the subagent is given its path, the parent without subagents builds
    from it, and §1a refuses an inventory that leaves one of its names out. Its form rules are the script's.
    #888: an origin's `signature` is that place's entry, kept as given, the contract says so for every kind and
    names the places pinned (a one-span Props, Params or Parameters cell and a usage form too, step 2) and the
    partial label a Signature or Props header pins with the form, and §1a refuses an inventory that changes one.
    #1030: the contract and the script say a header with a Signature part heads a Signature cell, and that a
    compound Props header and an Arguments, Args, Usage, Syntax or Example cell stay the reader's. #1028: a pinned
    `params` may also spell the shared members out among its own, in the skill's order. #1029: an ellipsis item
    labels a pinned form partial too, and the label at a pinned place is the floor's, so the reader adds none.
    #997: a Key params cell on a callable row is a pinned place too, its form partial, and the script says which
    cells it leaves the reader, a prose-qualified one among them."""
    text = _read(COVERAGE)
    section1 = _slice(text, "### 1. Extract Documented Exports", "#### 1a.")
    assert _command(COVERAGE, "uv run {coverageInputsScript} floor") == FLOOR_COMMAND
    assert section1.index(FLOOR_COMMAND) < section1.index("Delegate the reading of the skill under test")
    flow = _flow(section1)
    assert ('Exit 1 printed its error on stderr: HALT with it (`halt_reason: "helper-failed"`, phase '
            '`coverage-check:inventory`).') in flow
    assert ("It is given `{run_dir}/inventory-floor.json` too, and lists each name there with an origin in a file "
            "it reads, choosing its kind from the name's `kindLabel`, the skill's own label, when it has one. "
            "An origin's `signature` is that place's entry, at that place, its non-blank fields kept as given; a "
            "blank one is the reader's.") in flow
    assert ("Without subagents, the parent loads `{inventoryContractFile}` and builds the same JSON from the same files and `inventory-floor.json` and "
            "saves it to that file; §1a's checks still run on it.") in flow
    for rule in ("first cell", "public declaration", "Exports, Symbol"):
        assert rule not in flow, rule
    assert "first cell" in _flow(runpy_module(SCRIPTS_DIR / "load-coverage-inputs.py").__doc__)
    section1a = _flow(_slice(text, "#### 1a. Parent-Side Schema Validation", "### 1b."))
    assert ("refuses it when it leaves out a floor name those files write, or an origin's `signature`.") in section1a
    # #918: a missing or bad place is a warning, its forms named in the Coverage Analysis section's notes: only the
    # warnings that say the validator's UNBOUND text, one per form left unbound (the dropped `at` of a method with no
    # `owner` and a floor origin's own warning do not).
    unbound = runpy_module(SCRIPTS_DIR / "validate-inventory.py").UNBOUND
    assert ("- `valid` true (exit 0): every later command reads `{run_dir}/inventory.json`. Each of its `warnings` "
            f"that says \"{unbound}\" names a form whose place (`at`) is missing or bad, dropped so §2 binds it to no "
            "declaration: list their count and names in §5's notes, the forms left unbound for want of a "
            "place.") in section1a
    assert "{the notes §1a to §4b add to this section}" in text
    contract = _flow(_read(INVENTORY_CONTRACT))
    # after the rule for a name documented in several places and #1038's removed forms, which follow it
    assert ("and a `signature` the floor gives there stays that place's form. An entry whose `params` or "
            "`usage_signature` the signature check compares") in contract
    assert contract.index("and keeps one `kind` in every place.") < contract.index(
        "An entry whose `params` or `usage_signature` the signature check compares")
    assert ("A place `inventory-floor.json` gives a `signature` (a cited function declaration, a Signature cell, a "
            "Props, Params or Parameters cell that is one code span, or a heading or an export table's first cell "
            "that writes one call; a usage form, such as `new Client(opts)`, in `usage_signature`; a Key params "
            "cell that opens with the row's name and its parameter group, on a row whose Kind cell names a function, "
            "method, class, generator or hook, such as `sync fn` or `abstract class`; a header with a "
            "Signature part, such as `Signature / Purpose` or `Props / Signature`, heads a Signature cell, while a "
            "`Props / Usage` or `Props / Type` cell and an Arguments, Args, Usage, Syntax or Example cell are none of "
            "these, so their forms stay the reader's) has that form as its entry, with that place as its `at`, "
            "whatever its kind, its non-blank fields kept as given (a "
            "`params` or `usage_signature` may open with the shared text the next sentence gives, then `; `, and a "
            "`params` may spell the shared members out before, among or after its own, in the order the skill "
            "gives); a "
            "blank one is the reader's, left out when the place writes none, and a form the skill writes only in "
            "prose is an entry of its own; a "
            "`signature` read from a cell under a partial label (`Signature (simplified)`, `Props (simplified)`, "
            "`(partial)`, `(key parameters)`) or from a Key params cell, or whose parameter group holds a `...` or "
            "`…` that is a member of its own, standing in for omitted "
            "members (not one inside a nested type, object or element), also gives `signature_form` `\"partial\"`, "
            "which that entry copies, "
            "and the validator refuses an inventory with no entry there that does. The label at a place "
            "`inventory-floor.json` gives a `signature` is the `signature`'s: an entry that gives its form there or "
            "with no `at` gives `\"partial\"` only when the `signature` does, and the validator refuses one that adds "
            "it (a skill labels such a form partial in its column header, not in words), while another form the "
            "place writes keeps its own label (a second overload in the row whose own `...` labels it partial). "
            "Where the skill documents several names and states members they share once") in contract
    rules = _flow(runpy_module(SCRIPTS_DIR / "load-coverage-inputs.py").__doc__)
    assert ("an origin whose place writes the name's signature in a fixed form that is surely complete also "
            "carries it as `signature`" in rules and "no signature read" not in rules)
    assert "a Props, Params or Parameters cell is never read" not in rules
    assert ("Only then a Props, Params or Parameters cell, when the whole cell is one code span (trailing prose or "
            "several spans leave it the reader's)") in rules
    assert "A span that is no complete form is a usage form" in rules
    assert "`Signature (simplified)`" in rules and "a labelled one is not a Signature column" not in rules
    assert ("holds an ellipsis item, a member that is `...` or `…` alone as score-signatures.py's _parameter reads "
            "one (a rest `...args`, a `*args` and a default `x=...` are none), also carries `signature_form` "
            "\"partial\" (#1029)") in rules
    assert ("a header split at `/` with a part that is one included (`Signature / Purpose`, `Props / Signature`; "
            "#1030)") in rules
    assert ("a compound header with no Signature part (`Props / Usage`, `Props / Type`) and an Arguments, Args, "
            "Usage, Syntax or Example header leave the column unread: its form stays the reader's.") in rules
    assert ("With no such span, last a Key params or Key parameters cell (#997), on a row whose Kind cell names a "
            "callable as a whole word") in rules
    assert ("with `signature_form` \"partial\", as the header labels each row. A table with no Kind column, a row "
            "of another kind (`tuple`, `type alias`)") in rules
    assert ("So does a cell's span that prose qualifies or that sits among other spans") in rules
    assert "a Props, Params or Parameters cell that is one code span" in _flow(_read(INVENTORY_CONTRACT)).split(
        "keeps one `kind` in every place.", 1)[1].split("Where the skill documents several names", 1)[0]
    for rule in ("Signature cell", "Props (simplified)", "leading code span"):
        assert rule not in flow, rule
    assert len(text) < COVERAGE_CHAR_BUDGET
    command = _command(COVERAGE, "uv run {validateInventoryScript}")
    assert command.endswith(' --floor "{run_dir}/inventory-floor.json"'), command


def test_the_floor_and_validator_commands_run_from_the_prose(tmp_path):
    """#790 through the step's own commands: the floor lists the names SKILL.md writes in an export table's first
    column and as a code-only heading; an inventory that drops one fails §1a with exit 2, the name and its origin
    in `violations` and no `inventory.json` left from an earlier attempt; with the name added it validates. #888:
    the row's Signature cell is its origin's `signature`; an inventory whose entry writes another form fails §1a
    with exit 2 too, the origin and the signature in `violations`, and validates once the form is copied."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n\n"
                    "| Export | Kind | Signature | Purpose |\n| --- | --- | --- | --- |\n"
                    "| `fetchData` | function | `(url: string) => Promise<string>` | Fetches. |\n\n"
                    "### `Options`\n\nConfigures.\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix()}
    floor = _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)
    signature = {"params": "url: string", "return_type": "Promise<string>"}
    assert [(n["name"], n["kindLabel"], n["origins"]) for n in floor["names"]] == [
        ("Options", None, [{"file": "SKILL.md", "line": 11, "form": "heading"}]),
        ("fetchData", "function", [{"file": "SKILL.md", "line": 9, "form": "table-row", "signature": signature}]),
    ]
    assert json.loads((run / "inventory-floor.json").read_bytes()) == floor
    entries = [{"name": "fetchData", "kind": "function", "params": "", "return_type": "string",
                "description": "Fetches.", "at": "SKILL.md:9"}]
    response = run / "inventory-response.txt"
    response.write_bytes(json.dumps({"exports": entries, "cross_check_mismatches": []}).encode("utf-8"))
    (run / "inventory.json").write_bytes(b"{}")
    command = _command(COVERAGE, "uv run {validateInventoryScript}")
    proc = _run(command, values, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    form = ('floor: `fetchData` is documented at SKILL.md:9 (table-row) with the signature {"params": "url: string", '
            '"return_type": "Promise<string>"}, but no inventory entry of that name carries it; copy it as given, '
            'with `at` "SKILL.md:9"')
    assert result["violations"] == [
        "floor: `Options` is documented at SKILL.md:11 (heading), but no inventory entry lists it", form]
    assert result["floor"] == {"names": 2, "checked": 2, "absent": ["Options"]}
    assert not (run / "inventory.json").exists()
    entries.append({"name": "Options", "kind": "interface", "description": "Configures."})
    response.write_bytes(json.dumps({"exports": entries, "cross_check_mismatches": []}).encode("utf-8"))
    proc = _run(command, values, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)["violations"] == [form]
    assert not (run / "inventory.json").exists()
    entries[0].update(signature)
    response.write_bytes(json.dumps({"exports": entries, "cross_check_mismatches": []}).encode("utf-8"))
    validated = _exec(command, values, tmp_path)
    assert validated["valid"] is True and validated["floor"] == {"names": 2, "checked": 2, "absent": []}
    assert (run / "inventory.json").is_file()


# The five Denominator annotations with counts, each read from surface.json `candidates` (#822).
CANDIDATE_ANNOTATIONS = {
    "Empty barrel, denominator:": ["scopeIncludeUnion"],
    "Stratified scope, denominator:": ["tierAIncludeFiles", "scopeIncludeFiles", "tierAIncludeUnion",
                                       "scopeIncludeUnion"],
    "Pattern-reference, denominator:": ["tierAIncludeUnion"],
    "Specific-modules subset, denominator:": ["scopeIncludeUnion", "scopeIncludeFiles"],
    "Multi-entry (exports-map), denominator:": ["subpathEntries", "subpathUnion", "rootBarrel"],
}


def test_each_denominator_annotation_reads_a_candidates_field():
    """#822: every Denominator annotation with a count takes it from `surface.json` (`candidates`, or the
    canonicalized count a pattern reference's fold writes), which load-coverage-inputs.py writes; none asks for a
    count no script holds."""
    protocol = _read(SOURCE_ACCESS)
    clauses = _slice(protocol, "Each clause, by its `denominator.clause`", "Internal module symbols are")
    surface = _slice(_read(SCRIPTS_DIR / "load-coverage-inputs.py"), 'out["candidates"] = {', "}")
    for clause, fields in CANDIDATE_ANNOTATIONS.items():
        annotation = clauses[clauses.index(clause):].split("`", 1)[0]
        assert re.findall(r"candidates\.(\w+)", annotation) == fields, annotation
        for gone in ("files matched", "{M} modules", "subpaths resolved", "{N}", "{M}", "{R}"):
            assert gone not in annotation, (clause, gone)
        for field in fields:
            assert f'"{field}":' in surface, field  # a field the script writes
    # a pattern reference's provenance-map count is the fold's canonical count
    pattern = clauses[clauses.index("Pattern-reference, denominator:"):].split("\n", 1)[0]
    assert "canonical.canonical" in pattern and '"canonical": len(canonical)' in _read(
        SCRIPTS_DIR / "load-coverage-inputs.py")
    # on the `all` set no scope set gives the stratified counts
    stratified = _flow(clauses[clauses.index("Stratified scope, denominator:"):].split("\n", 1)[0])
    assert "when `denominator.surfaceSet` is `all` no scope set gives a count, so both read `absent`" in stratified
    intro = _flow(_slice(protocol, "when the tier A globs count no name", "Each clause, by its"))
    assert ("each `{candidates.<field>}` count from `surface.json`, and a null one reads `absent`; a `*Files` "
            "count is the files that define the set's names (at Quick tier, word it as the files its names sit "
            "at)") in intro


def test_the_source_access_is_written_when_it_is_resolved():
    """#823: the protocol writes `analysisConfidence` to the report the moment it resolves it, so the result step's
    check reads a value on disk; when that check refuses one, report.md writes the resolved value and runs it
    again instead of halting."""
    protocol = _flow(_read(SOURCE_ACCESS))
    assert ("and write it at once to the frontmatter of `{report_file}` (init.md §6c created it) as "
            "`analysisConfidence: '{analysis_confidence}'`, again each time a later rule changes it") in protocol
    assert "binds `{report_file}`" in _read(REFS / "init.md")
    contract = _flow(_slice(_read(REPORT), "### 4c. Result Contract", "### 5."))
    assert "checks that `analysisConfidence` names a source access" in contract
    assert ("except when the `error` names `analysisConfidence`: then write `analysisConfidence: "
            "'{analysis_confidence}'`, the value source-access-protocol.md resolved") in contract
    assert "**Source Access:** {analysis_confidence}" in _read(COVERAGE)


def test_the_deep_tier_asks_only_for_what_runs():
    """#828: the Deep tier asks for no check that has no command, run file or ledger record: it names what
    already covers the version and the re-exports. #1084: an import or member error no script checks is no
    hand-written record any more, since the parent never loads the skill: the plan hands each judge the skill's
    import lines and documented members, the judge adds each that differs to its JSON as `doc_errors`, and score
    records it as an Info observation, which never blocks. The plan command's lead says when to pass the flag."""
    deep = _flow(_slice(_read(COVERAGE), "**Deep Tier", "**States 2 to 4"))
    for gone in ("gh CLI", "check type definitions", "trace re-exports", "no coverage check of its own"):
        assert gone not in deep, gone
    assert ("init.md §5b's drift guard checks the local tree against the pinned commit, at any tier, when both "
            "exist") in deep
    assert ("the recipe runner traces each re-export to the file that defines it when it runs (the fallback "
            "per-file scan does not)") in deep
    assert ("Run its plan with `--doc-errors`: each check also carries the skill's import lines of its name "
            "(`imports`) and its documented members (`members`), and a documented name with no form but with either "
            "gets a check with no `documented`.") in deep
    assert ("Its judge compares them with the source by `{signatureRulesFile}` and adds each that differs to the JSON "
            "above as `doc_errors`, which `score` records as an Info `Not checked by script: {name}` observation at "
            "the documenting line.") in deep
    assert "hand-written" not in deep and "§5b" not in deep.replace("init.md §5b", "")
    assert '[--doc-errors]' in _command(COVERAGE, "uv run {scoreSignaturesScript} plan")
    assert ("**Compare the signatures.** A script plans (pass `--doc-errors` at the Deep tier, below); subagents "
            "judge:") in _flow(_read(COVERAGE))
    # §5b writes no such record by hand, the tier branch file sends a Deep run back to the paragraph, which adds
    # nothing to the fallback scan, and the severity table names the script that records them
    records = _flow(_slice(_read(COVERAGE), "Then write the records no script wrote", "```"))
    assert "Not checked by script" not in records
    assert ("Then write the records no script wrote, §1b's split-body mismatches, in the Ledger Record Format of "
            "`{outputFormatsFile}`, each naming its export in `export` and in its title") in records
    assert "its extra checks" not in _read(COVERAGE_TIERS)
    assert ("at Deep tier, its **Deep Tier** paragraph, whose `--doc-errors` adds nothing to this scan's plan, which "
            "has no checks, so leave it out;") in _read(COVERAGE_TIERS)
    observation = next(row for row in _read(SCORING).splitlines() if row.startswith("| Info     | `observation`"))
    assert ("`Not checked by script: {name}`, at the documenting line, recorded by score-signatures.py from a "
            "signature judge's `doc_errors`") in observation
    assert "by hand" not in observation
    # #1005: and written by gap-ledger.py under a title of its own for a name cited at another package's star,
    # so that the record score-signatures.py writes of the name stays its own gap
    assert ("recorded by score-signatures.py from a signature judge's `doc_errors` (coverage-check §2 and §2b). Also "
            "a stale name with no `defined_at`, not scoped out by "
            "the brief (`excluded.outsideScope`), that the skill cites at a file holding another package's "
            "`export *` (`surface.json` `unresolvedStars`): `Not checked by script: {name} (another package's "
            "export *)`, at the documenting line, written by gap-ledger.py and asking no change unless that package "
            "lacks the name (coverage-check §2c)") in observation
    # the drift guard is init.md §5b's helper call, which runs at every tier
    init = _read(REFS / "init.md")
    assert "It runs the workspace drift guard" in _flow(init)
    assert "uv run {checkWorkspaceDriftHelper}" in _slice(init, "### 5b.", "### 6.")
    ledger = runpy_module(TEST_SKILL / "scripts" / "gap-ledger.py")
    record, error = ledger.normalize_record({
        "severity": "Info", "category": "observation", "title": "Not checked by script: fetchData",
        "export": "fetchData", "source": "SKILL.md:12",
        "remediation": "Import fetchData from the module that exports it."})
    assert error is None and record["severity"] not in ledger.BLOCKING


def test_the_forge_tier_extraction_runs_once_without_a_head_cap():
    command = _command(COVERAGE, "uv run {extractPublicApiHelper} --mode full")
    assert command == ('uv run {extractPublicApiHelper} --mode full --source-root "{source_path}" '
                       '--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --tier {detected_tier} '
                       '--head-cap 0 --output "{run_dir}/extract-full.json"')
    forge = _flow(_slice(_read(COVERAGE), "**Forge Tier (ast-grep available):**", "**Deep Tier"))
    # The fallback is decided from the JSON, and a recipe's internal match is never on the surface.
    assert "Decide what to do from the JSON, not from the exit code" in forge
    assert "`extraction.fallback.needed`" in forge and "`extraction.readByEye`" in forge
    assert "the recipes' internal matches are never part of it" in _flow(_read(SOURCE_ACCESS))
    assert "reads the full declaration at `{file}:{line}`" in forge
    # #1022: plan writes a null `line` for a name read by eye alone in its file (as a check, a candidate or a bound
    # declaration); the judge finds the declaration in its file and gives that line on the mismatch, never the null
    # `score` refuses. The candidate and bound sentences read their declarations "as above", so a candidate with a
    # null `line` beside a check that has one is found in the candidate's own file.
    assert ("reads the full declaration at `{file}:{line}` (all of it, not only `signatureLine`'s one physical line; "
            "with `line` null, find it in `{file}` and give its mismatch that line)") in forge
    assert "read in full at its `file` and `line` as above" in forge
    # #781: a check the citations do not settle names each candidate
    assert ("A check with `candidates` reads each as above and reports a mismatch only when the documented signature "
            "matches none: one, at the closest candidate, its `file` and `line` on the mismatch object (the "
            "result's `file` stays its `files[]` entry) and its `difference` tagged against it") in forge
    # #826: a check that offers a name's other documented forms is compared with each, by the rules file
    assert ("A check with `alternatives` (the other forms the skill documents for the name) is compared with each of "
            "them too, as `{signatureRulesFile}` says, each mismatch naming its form as `form`.") in forge
    # an overload set is judged whole, by the rule the judge reads in the rules file whose path it is given (#827)
    assert "delegate one subagent with its checks and the absolute path of `{signatureRulesFile}`" in forge
    assert "is read through its implementation" not in forge, "the overload rule has one copy, in the rules file"
    assert "is read through its implementation" in _read(SIGNATURE_RULES)
    for gone in ("exports_documented", "missing_docs"):
        assert gone not in forge, gone


def test_the_forge_tier_reads_by_eye_every_file_the_surface_names():
    """#789: an `ok` run lists its syntax-error and non-UTF-8 files in `extraction.readByEye` too, so the read-by-eye
    pass keys on that list being non-empty, not on an `incomplete` status. It runs once; its files are listed in the
    Coverage Analysis section as Quick tier and the fallback list theirs, and so are the `extraction.unread` files no
    one could open, whether or not anything is read by eye. The fallback stays the first branch."""
    section = _slice(_read(COVERAGE), "Decide what to do from the JSON, not from the exit code:",
                     "**Compare the signatures.**")
    bullets = [line for line in section.splitlines() if line.startswith("- ")]
    assert bullets[0].startswith("- `extraction.fallback.needed` is true")
    assert bullets[1] == ("- `extraction.readByEye` is non-empty (a file the run could not parse or decode, or a "
                          "failed call left unread): keep the surface, read by eye only the files it names, save a "
                          "per-file result for each, and run `surface` again with them, once (the second call starts "
                          "no new pass).")
    # Whatever the branch, each file read by eye and each file no one could open is listed, never dropped silently.
    assert bullets[2] == ("- In the Coverage Analysis section, list each `readByEye` file as read by eye, each "
                          "`extraction.unread` file as unread.")
    # #1048: no gap is read by eye; the signature plan judges a documented one that has a file (one with none and no
    # bound form gets no check, and score names it as left out of Signature Accuracy, #1061) and §5's render lists
    # them all.
    assert bullets[3] == ("- `extractionGaps[]` names exports no recipe found: on the surface, judged below when "
                          "documented and located; read none by eye.")
    assert "read their signature by eye" not in section
    assert "`extraction.status` is `incomplete`" not in section
    # Quick tier and the fallback per-file scan list theirs the same way.
    assert _flow(_read(COVERAGE_TIERS)).count("in the Coverage Analysis section as read by eye") == 2


def test_the_forge_surface_reads_the_brief_for_a_stale_scope(tmp_path):
    """#677: the Forge surface call passes the brief, whose scope-expansion amendments the stale-scope guard
    reads; a Python top nested in another is no barrel; §4 names the guard's gap; the protocol states both
    rules. The call and §5b's guards append run as written."""
    command = _command(COVERAGE, "surface --extraction")
    assert command == ('uv run {coverageInputsScript} surface --extraction "{run_dir}/extract-full.json" '
                       '--metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] '
                       '[--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] '
                       '[--monorepo] [--pattern-reference-intent] [--curated-subset] --output "{run_dir}/surface.json"')
    forge = _flow(_slice(_read(COVERAGE), "**Forge Tier (ast-grep available):**", "**Deep Tier"))
    assert "The surface holds what `{sourceAccessProtocol}` **What the Surface Holds** says" in forge
    held = _flow(_slice(_read(SOURCE_ACCESS), "### What the Surface Holds", "## Source Access Resolution"))
    # an outer package that exports nothing (a stray source-root __init__.py) nests nothing; the nested names
    # leave the standard barrel and the umbrella ratio, never the scope sets or the signature comparisons
    assert ("nested in the folder of another package that exports a name is no barrel: its names "
            "(`excluded.nestedEntries`) leave only the `all` and `root` sets and the umbrella ratio, and `plan` still "
            "compares their signatures") in held
    assert "When a `scope.include` glob matches no file (`guards.staleScope.fires`" in held
    assert "are back in it (`guards.staleScope.restored`)" in held
    # #913: a restored name takes the kind the provenance map gives it, and Type Coverage names one with none;
    # #1020: so does any name the recipes give no kind at its file, an extraction gap or one found only elsewhere
    assert ("(`guards.staleScope.restored`). Each restored name, and each name no recipe gives a kind at its file "
            "(such as one in `extractionGaps`), takes the kind the provenance map gives its name at its file when the map is given (a dataclass, "
            "NamedTuple or TypedDict is a class, a Protocol an interface, a type alias a type, a TypeVar no type), and "
            "Type Coverage leaves out one still without a kind and says so in its warnings.") in held
    # #1009: a restored name stays only while a glob is stale, so the gap asks for an include glob over its file
    assert ("The restored exports stay only while a `scope.include` glob matches no file: once each glob matches one, "
            "a restored export whose file no glob covers is outside scope again (`excluded.outsideScope`), so the "
            "`brief-scope-stale` gap asks for a `scope.include` glob over each restored file whose exports the skill "
            "documents.") in held
    # #695: a stale tier A glob fires the guard too and counts no name
    assert ("A stale `scope.tier_a_include` glob fires the guard too (`guards.staleScope.unmatchedTierAInclude`) "
            "and counts no name") in held
    # #1087: a documented extra's declarations reach plan and score as its records, never a set, Export Coverage or
    # Type Coverage
    assert ("`internalDeclarations` lists, for each name the extraction finds no entry point exports (its `internal` "
            "names) and that no surface record names, each declaration of it the extraction records in a file the "
            "brief does not exclude, in the fields `otherDeclarations` uses; it is `null` exactly when "
            "`otherDeclarations` is. They add no name to a set either, and neither Export Coverage nor Type Coverage "
            "reads them: `plan` and `score` read them as the records of such a name, so a documented extra's "
            "signature is planned, judged and counted in Signature Accuracy at its declaration.") in held
    internal = _flow(_slice(_read(SOURCE_ACCESS), "Internal module symbols are", "This matches the extraction"))
    assert ("the extraction's `internal` names reach it only as `internalDeclarations` (What the Surface Holds, "
            "below), which add no name to its sets or to the coverage denominator.") in internal
    assert "never reach it" not in internal
    # the report lists every name the surface leaves out of the barrel or puts back in it, and the extraction gaps
    # (#1048), through §5's render
    assert ("§5's render lists `excluded.outsideScope`, `excluded.nestedEntries`, the restored names and "
            "`extractionGaps`") in forge
    section4 = _flow(_slice(_read(COVERAGE), "### 4. The Denominator Record", "### 4b."))
    assert "`guards.staleScope.fires` a Medium `brief-scope-stale` gap at the brief" in section4
    protocol = _flow(_read(SOURCE_ACCESS))
    assert ("is not a second package root when the folder of another package root that exports a name holds it, "
            "unless `scope.include` or `scope.tier_a_include` lists that `__init__.py`: its names stay out of the "
            "`all` and `root` sets (`excluded.nestedEntries`), while the `scope.include` and `tier_a_include` sets "
            "still count them and their signatures are still compared") in protocol
    assert ("unless `scope.exclude` or a `scope-expansion` amendment whose latest action is `skipped` or "
            "`demoted-include` matches the file") in protocol
    # with no tier A glob matching a file there is no tier_a_include set, nor (#712) when the globs match only
    # files that define no name, nor (#725) only files scope.include leaves out: the script's ladder goes on
    # (test-skf-load-coverage-inputs.py pins it)
    assert ("A `scope.tier_a_include` glob counts a name only in a file a `scope.include` glob also matches, and one "
            "that matches no file (`guards.staleScope.unmatchedTierAInclude`, a brief older than the source) counts "
            "none: when the tier A globs count no name, `surface.json` has no `tier_a_include` set.") in protocol
    assert ("The denominator is the `tier_a_include` set when `surface.json` has it, else the canonicalized "
            "provenance map") in protocol
    # the deflation guard's rule (#712: a tier A glob that counts a name turns it off, a stored 0 below any
    # re-derived name fires it) is load-coverage-inputs.py's, which test-skf-load-coverage-inputs.py pins; the
    # protocol keeps what the model does with it (v4.0.0 quality gate run 1 review)
    assert ("the `stats.effective_denominator` Create Skill stored, unless `guards.deflation.fires` (a Medium "
            "`metadata-drift` gap, coverage-check.md §4: a legitimate scope reduction goes in the brief, through "
            "`scope.tier_a_include` or `scope.exclude`, never into `metadata.stats`)") in protocol
    assert "`guards.thresholds.deflationPct`" not in protocol and "`guards.deflation.pct` null" not in protocol

    run = tmp_path / "run"
    run.mkdir()
    entry = {"language": "python", "subpath": None, "resolution": "file", "in_scope": True}
    (run / "extract-full.json").write_bytes(json.dumps({
        "mode": "full", "status": "ok", "files_in_scope": 2, "exports": [],
        "scope": {"include": ["pkg/__init__.py", "pkg/pipelines.py", "pkg/api/**"], "exclude": [],
                  "tier_a_include": None, "unmatched_include": ["pkg/pipelines.py"], "unmatched_tier_a_include": []},
        "entry_points": {"files": [{**entry, "file": "pkg/__init__.py", "package": "pkg"},
                                   {**entry, "file": "pkg/api/routers/__init__.py", "package": "pkg/api/routers"}]},
        "entry_point_diff": {
            "public": [{"name": n, "entry": e, "via": "re-export", "file": f, "line": 1} for n, e, f in (
                ("Task", "pkg/__init__.py", "pkg/pipelines/task.py"),
                ("get_router", "pkg/api/routers/__init__.py", "pkg/api/routers/r.py"),
                ("run_pipeline", "pkg/__init__.py", "pkg/pipelines/run.py"))],
            "outside_scope": [{"name": n, "entry": "pkg/__init__.py", "file": f, "line": 1} for n, f in (
                ("Task", "pkg/pipelines/task.py"), ("run_pipeline", "pkg/pipelines/run.py"))],
            "extraction_gaps": []},
        "warnings": ["scope.include pattern 'pkg/pipelines.py' matches no file"]}).encode("utf-8"))
    _write_tree(tmp_path / "forge-data", {"demo/skill-brief.yaml": (
        "name: demo\nscope:\n  include: ['pkg/__init__.py', 'pkg/pipelines.py', 'pkg/api/**']\n  amendments:\n"
        "    - path: pkg/pipelines/task.py\n      action: skipped\n      category: scope-expansion\n")})
    skill = _write_tree(tmp_path / "skill", {"metadata.json": json.dumps({"skill_type": "single", "exports": []})})
    values = {"{run_dir}": run.as_posix(), "{forge_data_folder}": (tmp_path / "forge-data").as_posix(),
              "{skill_name}": "demo", "{resolved_skill_package}": skill.as_posix(),
              "{ledgerFile}": (tmp_path / "test-findings-20261007T000000Z-abcdef12.json").as_posix()}
    surface = _exec(_choose(command, keep=("--brief",)), values, tmp_path)
    assert surface["sets"]["all"] == ["run_pipeline"], "the skipped amendment keeps task.py out"
    assert [n["names"] for n in surface["excluded"]["nestedEntries"]] == [["get_router"]]
    assert surface["sets"]["scope.include"] == ["get_router"], "a nested top's names stay in the scope sets"
    appended = _exec(_command(COVERAGE, "--from guards"), values, tmp_path)
    assert appended["appended"] == ["GAP-001"]
    record = json.loads(Path(values["{ledgerFile}"]).read_bytes())["records"][0]
    assert (record["category"], record["source"]) == ("brief-scope-stale",
                                                      f"{values['{forge_data_folder}']}/demo/skill-brief.yaml")


def test_a_runner_input_error_halts_and_never_takes_the_fallback_scan():
    """#676: exit 2 is an input error (a 1.x brief the runner could not read, say) or a failure the runner did not
    foresee, named on stderr. Every flag of the call is fixed, so it HALTs with that line before the surface is
    built; the Fallback Per-File Scan stays for what the JSON says the runner cannot do, and for no JSON on another
    exit."""
    raw = _slice(_read(COVERAGE), "**Forge Tier (ast-grep available):**", "**Deep Tier")
    forge = _flow(raw)
    halt = ('Exit 2 is an input error (a brief the runner cannot read, say) or a failure the runner did not '
            'foresee, named in one line on stderr with no JSON: HALT with that line (`halt_reason: "helper-failed"`, '
            'phase `coverage-check:surface`).')
    assert halt in forge
    assert forge.index(halt) < forge.index("Build the surface from it")
    fallback = [line for line in raw.splitlines() if "run its **Fallback Per-File Scan**" in line]
    assert fallback == ["- `extraction.fallback.needed` is true, or the runner printed no JSON on an exit other "
                        "than 2: load `{coverageTiersFile}` and run its **Fallback Per-File Scan** in place of the "
                        "rest of this tier."]
    assert "exited 2" not in forge


def test_tooling_health_is_tooling_status_only():
    for path in sorted(TEST_SKILL.rglob("*.md")):
        text = _read(path)
        assert "analysis_confidence: degraded" not in text, path.name
        assert "degraded|" not in text and "|degraded" not in text, path.name
    template = _fence(_read(INIT), "workflowType: 'test-skill'")
    assert "analysisConfidence: ''" in template
    assert "toolingStatus: '{ok|frontmatter-validator-timeout}'" in template
    timeout = _flow(_slice(_read(INIT), "**3b. Run the validator", "Parse the JSON output."))
    assert "`tooling_status: frontmatter-validator-timeout`" in timeout and "set `tooling_status: ok`" in timeout
    frontmatter = _flow(_slice(_read(SCORE), "### 7. Update Output Frontmatter", "### 8."))
    assert "`analysisConfidence: '{full|provenance-map|metadata-only|remote-only|docs-only}'`" in frontmatter
    # init.md wrote toolingStatus and nothing changes it: score.md reads it back for Cap 1, never rewrites it.
    assert "toolingStatus" not in frontmatter
    scoring_input = _flow(_slice(_read(SCORE), "#### 3a. Construct Scoring Input JSON", "#### 3b."))
    assert "`toolingStatus` from the `{outputFile}` frontmatter (init.md §6c wrote it), never from memory" in scoring_input
    assert '"toolingStatus": "{toolingStatus from the {outputFile} frontmatter' in scoring_input
    assert "tooling_status from init.md" not in _read(SCORE)
    assert "Always pass `toolingStatus`: any value other than `ok` fires Cap 1" in _flow(_read(SCORE))


def test_no_scoring_rule_is_overridable_or_restated():
    toml = _read(CUSTOMIZE)
    assert "output_formats_path" not in toml and "scoring_rules_path" not in toml
    comment = _flow(re.sub(r"(?m)^#\s?", "", toml[toml.index("# Pass threshold"):toml.index("default_threshold = 80")]))
    assert "forge-auto, forge, forge-quick and campaign runs" in comment
    assert "a run a cap forced to FAIL stays FAIL at any threshold" in comment
    for path in sorted(TEST_SKILL.rglob("*.md")):
        text = _read(path)
        assert "{scoringRulesPath}" not in text and "{outputFormatsPath}" not in text, path.name
    detect = _flow(_read(DETECT))
    assert "Tier-Dependent Scoring" not in detect and "set nothing here" in detect
    assert "Quick-tier weight adjustment" not in _read(COVERAGE)


def runpy_module(path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("skf_" + path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A --mode full result for a package whose entry point exports fetchData,
# helper and Options; internalThing is a recipe match no entry point exports.
EXTRACTION = {
    "mode": "full", "status": "ok", "files_in_scope": 2, "truncated": False, "files_without_recipes": {},
    "file_issues": [], "errors": [],
    "scope": {"include": ["src/**"], "exclude": [], "tier_a_include": None},
    "exports": [
        {"export_name": "fetchData", "export_type": "function", "source_file": "src/index.ts", "source_line": 1,
         "signature_line": "export function fetchData(url: string): string {"},
        {"export_name": "Options", "export_type": "interface", "source_file": "src/index.ts", "source_line": 2,
         "signature_line": "export interface Options {"},
        {"export_name": "helper", "export_type": "function", "source_file": "src/helper.ts", "source_line": 1,
         "signature_line": "export function helper(x: number, y?: number): number {"},
        {"export_name": "internalThing", "export_type": "function", "source_file": "src/helper.ts",
         "source_line": 2, "signature_line": "export function internalThing(): void {}"},
    ],
    "entry_points": {"files": [{"language": "typescript", "file": "src/index.ts", "subpath": "."}]},
    "entry_point_diff": {
        "public": [
            {"name": "Options", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 2},
            {"name": "fetchData", "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": 1},
            {"name": "helper", "entry": "src/index.ts", "via": "re-export", "file": "src/helper.ts", "line": 1},
        ],
        "internal": [{"name": "internalThing", "source_file": "src/helper.ts", "source_line": 2}],
        "extraction_gaps": [], "outside_scope": [],
    },
    "counts": {"exports_public_api": 3, "exports_internal": 1, "effective_denominator": 3,
               "effective_denominator_basis": "scope.include"},
    "arms": {"monorepo": False, "specific_modules": False, "multi_subpath_exports": False},
}


# The (script, subcommand) pairs, and the scripts that take no subcommand, that given --output print only a summary
# of the file they write.
SUMMARIZED_COMMANDS = frozenset({("{scoreSignaturesScript}", cmd) for cmd in ("plan", "score")} | {
    ("{coverageInputsScript}", cmd) for cmd in ("census", "floor", "metadata", "surface")})
SUMMARIZED_SCRIPTS = frozenset({"{reconcileScript}", "{numeratorVerifyScript}", "{coherenceAggregationScript}",
                                "{externalScoreScript}"})


def _exec(command: str, values: dict[str, str], cwd: Path) -> dict:
    """Run one prose command (an `echo '<json>' | uv run ...` pipe included) and return its JSON: for a
    SUMMARIZED_COMMANDS or SUMMARIZED_SCRIPTS command, the JSON of the file its --output names."""
    stdin = b""
    if command.startswith("echo '"):
        payload, command = command[len("echo '"):].split("' | ", 1)
        for key, value in values.items():
            payload = payload.replace(key, value)
        stdin = payload.encode("utf-8")
    m = re.fullmatch(r"uv run (\{\w+\}) (.*)", command)
    assert m, command
    rest = m.group(2)
    for key, value in values.items():
        rest = rest.replace(key, value)
    assert not re.search(r"\{\w+\}|<[a-z][^>]*>", rest), f"unfilled placeholder in {rest!r}"
    words = shlex.split(rest)
    redirect = words.index(">") if ">" in words else None  # `... > "<file>"` keeps stdout in a run file
    if redirect is not None:
        words, target = words[:redirect], Path(words[redirect + 1])
    if "<" in words:  # `... < "<file>"` reads the payload from a run file
        source = words.index("<")
        stdin = Path(words[source + 1]).read_bytes()
        words = words[:source] + words[source + 2:]
    proc = subprocess.run([sys.executable, str(PROSE_SCRIPTS[m.group(1)]), *words], cwd=cwd,
                          input=stdin, capture_output=True, check=False)
    assert proc.returncode == 0, (command, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8"))
    if redirect is not None:
        target.write_bytes(proc.stdout)
    summarized = words and ((m.group(1), words[0]) in SUMMARIZED_COMMANDS or m.group(1) in SUMMARIZED_SCRIPTS)
    if summarized and "--output" in words:
        # #1018, #1040, #1063: the command prints a summary that names its --output file; the step reads the file
        written = words[words.index("--output") + 1]
        assert json.loads(proc.stdout)["output"] == written, (command, proc.stdout.decode("utf-8"))
        return json.loads(Path(written).read_bytes())
    return json.loads(proc.stdout)


def test_the_prose_scoring_chain_runs_end_to_end(tmp_path):
    """The coverage step's commands, then the external score and step 5's, as the prose writes them:
    each script reads the run files the one before it wrote, and compute-score.py scores from them."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n\n"
                    "`fetchData(url)` fetches [AST:src/index.ts:L1]. `helper(x)` helps. `Options` configures.\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory-response.txt").write_bytes(("```json\n" + json.dumps({"exports": [
        {"name": "fetchData", "kind": "function", "params": "url: string", "return_type": "string",
         "description": "Fetches the user's data; it's \"cached\".", "at": "SKILL.md:7"},
        {"name": "helper", "kind": "function", "params": "x: number", "return_type": "number", "description": "Helps.",
         "at": "SKILL.md:7"},
        {"name": "Options", "kind": "interface", "description": "Configures."},
    ], "cross_check_mismatches": []}) + "\n```\n").encode("utf-8"))
    (run / "extract-full.json").write_bytes(json.dumps(EXTRACTION).encode("utf-8"))
    metadata = skill / "metadata.json"
    metadata.write_bytes(json.dumps({"skill_type": "single", "exports": ["fetchData", "helper", "Options"],
                                     "stats": {"exports_public_api": 3, "exports_documented": 3,
                                               "effective_denominator": 4}}).encode("utf-8"))
    # The tree the judges read, which §2b's score is given as --source-root: fetchData returns on its own one-line
    # declaration, which the surface records at line 1, before Options at line 2.
    source = _write_tree(tmp_path / "source", {
        "src/index.ts": "export const fetchData = (url: string): Promise<string> => cache.get(url);\n"
                        "export interface Options {}\n",
    })
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(),
              "{source_path}": source.as_posix(),
              "{ledgerFile}": (tmp_path / "test-findings-20260101T000000Z-abcdef12.json").as_posix()}

    census = _exec(_command(COVERAGE, "uv run {coverageInputsScript} census"), values, tmp_path)
    assert census["docsOnly"] is False
    assert _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)["names"] == []
    validated = _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)
    assert validated["valid"] is True and (run / "inventory.json").is_file()
    surface = _exec(_choose(_command(COVERAGE, "surface --extraction")), values, tmp_path)
    assert surface["sets"]["all"] == ["Options", "fetchData", "helper"]
    command = _choose(_command(COVERAGE, "uv run {scoreSignaturesScript} plan"))
    assert '--skill-dir "{resolved_skill_package}"' in command, "#781: the skill's citations pick a declaration"
    plan = _exec(command, values, tmp_path)
    assert [f["file"] for f in plan["files"]] == ["src/helper.ts", "src/index.ts"]
    (run / "signatures-1.txt").write_bytes(json.dumps({"file": "src/helper.ts", "signature_mismatches": [
        {"name": "helper", "line": 1, "source_sig": "(x: number, y?: number) => number",
         "documented_sig": "(x: number) => number", "issue": "missing optional parameter 'y'"}]}).encode("utf-8"))
    # #835 follow-up: a return annotation the body contradicts, checked in the {source_path} file
    (run / "signatures-2.txt").write_bytes(json.dumps({"file": "src/index.ts", "signature_mismatches": [
        {"name": "fetchData", "line": 1, "source_sig": "(url: string) => Promise<string>",
         "documented_sig": "(url: string) => string", "issue": "annotated Promise<string>; the body returns the string",
         "difference": "annotation-contradicted", "evidence_line": 1}]}).encode("utf-8"))
    command = _choose(_command(COVERAGE, "uv run {scoreSignaturesScript} score"), keep=("--source-root",))
    signatures = _exec(command.replace(
        '--results "{run_dir}/signatures-<n>.txt"',
        '--results "{run_dir}/signatures-1.txt" --results "{run_dir}/signatures-2.txt"').replace(
        "<set>", "all"), values, tmp_path)
    assert (signatures["signatureAccuracy"], signatures["typeCoverage"]) == (50.0, 100.0)
    # the source file read, fetchData's contradiction is an Info observation that still matches
    assert [(g["title"], g["severity"]) for g in signatures["gapRecords"]] == [
        ("Signature mismatch: helper", "Critical"), ("Annotation contradicted: fetchData", "Info")]
    appended = _exec(_command(COVERAGE, '--input "{run_dir}/signature-gaps.json"'), values, tmp_path)
    assert appended["appended"] == ["GAP-001", "GAP-002"]
    inputs = _exec(_choose(_command(COVERAGE, "uv run {coverageInputsScript} metadata")), values, tmp_path)
    assert inputs["inflationSignature"] is False
    numerator = _exec(_command(COVERAGE, "uv run {numeratorVerifyScript}"), values, tmp_path)
    assert numerator["skipped"] is True
    scalar = _exec(_command(COVERAGE_BRANCHES, "--denominator-source scalar").replace("<set>", "all"), values,
                   tmp_path)
    assert (scalar["documented"], scalar["denominator"]) == (3, 4), "the scalar comes from coverage-inputs.json"
    # #791, #792: over `all` the lookup counts and no missing name is listed; the stale names are still read.
    assert (scalar["numeratorSource"], scalar["missing"], scalar["missingCount"]) == ("lookup", [], 1)
    assert (scalar["stale"], scalar["staleApplicable"]) == ([], True)
    coverage = _exec(_command(COVERAGE, "--denominator-source barrel").replace("<set>", "all"), values, tmp_path)
    assert (coverage["documented"], coverage["denominator"], coverage["exportCoverage"]) == (3, 3, 100.0)
    coherence = _exec(_command(COVERAGE_BRANCHES, "uv run {coherenceScript}"), values, tmp_path)
    assert coherence["findings"] == []
    external = _exec(_command(EXTERNAL, "uv run {externalScoreScript}").replace(
        "<score or null>", "80", 1).replace("<score or null>", "null"), values, tmp_path)
    assert external["externalScore"] == 80.0

    flags = {"mode": "naive", "tier": "Forge", "docsOnly": False, "state2": False, "stackSkill": False,
             "referenceApp": False, "threshold": 80, "analysisConfidence": "full", "toolingStatus": "ok"}
    command = _choose(_command(SCORE, "uv run {scoringScript}"), keep=("--signatures",))
    command = command.replace("'<the §3a JSON>'", shlex.quote(json.dumps(flags)))
    score = _exec(command, values, tmp_path)
    assert score["input"]["scores"] == {"exportCoverage": 100.0, "signatureAccuracy": 50.0, "typeCoverage": 100.0,
                                        "coherence": None, "externalValidation": 80.0}
    # naive weights 45/25/20/10: 45 + 12.5 + 20 + 8
    assert (score["totalScore"], score["result"]) == (85.5, "PASS")
    assert "effectiveResult" not in score


def test_a_deep_tier_judge_s_doc_error_reaches_the_ledger(tmp_path):
    """#1084, as the step runs it: the skill imports SearchType and run from pkg.search in a Python fence and
    documents run's form and SearchType only by its fields. §2's plan command with `--doc-errors` gives SearchType a
    check with that import line and its members, the score command records the `doc_errors` item a judge returns for
    it at the import line, and §5b's `signature-gaps.json` append writes it to the ledger as an Info observation.
    Signature Accuracy and the compared count are those of the same run without the item."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n\n"
                    "```python\nfrom pkg.search import SearchType, run\n```\n\n"
                    "`run(query: str) -> list` searches; `SearchType` holds `GRAPH_COMPLETION`.\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory.json").write_bytes(json.dumps({"exports": [
        {"name": "run", "kind": "function", "params": "query: str", "return_type": "list", "description": "Searches.",
         "at": "SKILL.md:11"},
        {"name": "SearchType", "kind": "type", "fields": ["GRAPH_COMPLETION"], "description": "The search kinds.",
         "at": "SKILL.md:11"},
    ], "references": [], "cross_check_mismatches": []}).encode("utf-8"))
    (run / "surface.json").write_bytes(json.dumps({"exports": [
        {"name": "SearchType", "kind": "class", "file": "pkg/types.py", "line": 3,
         "signatureLine": "class SearchType(Enum):", "origin": "extraction"},
        {"name": "run", "kind": "function", "file": "pkg/search.py", "line": 10,
         "signatureLine": "def run(query: str) -> list:", "origin": "extraction"},
    ], "sets": {"all": ["SearchType", "run"]}}).encode("utf-8"))
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(),
              "{ledgerFile}": (tmp_path / "test-findings-20261111T000000Z-abcdef12.json").as_posix()}

    plan = _exec(_choose(_command(COVERAGE, "uv run {scoreSignaturesScript} plan"), keep=("--doc-errors",)), values,
                 tmp_path)
    assert plan["compared"] == 1
    [doc_check] = [c for g in plan["files"] if g["file"] == "pkg/types.py" for c in g["checks"]]
    assert doc_check == {"name": "SearchType", "line": 3, "signatureLine": "class SearchType(Enum):",
                         "imports": [{"at": "SKILL.md:8", "statement": "from pkg.search import SearchType, run"}],
                         "members": [{"at": "SKILL.md:11", "fields": ["GRAPH_COMPLETION"]}]}
    command = _choose(_command(COVERAGE, "uv run {scoreSignaturesScript} score")).replace(
        '--results "{run_dir}/signatures-<n>.txt"',
        '--results "{run_dir}/signatures-1.txt" --results "{run_dir}/signatures-2.txt"').replace("<set>", "all")
    (run / "signatures-1.txt").write_bytes(json.dumps(
        {"file": "pkg/search.py", "signature_mismatches": [], "undecided": []}).encode("utf-8"))
    judged = {"file": "pkg/types.py", "signature_mismatches": [], "undecided": []}
    (run / "signatures-2.txt").write_bytes(json.dumps(judged).encode("utf-8"))
    without = _exec(command, values, tmp_path)
    error = {"name": "SearchType", "at": "SKILL.md:8", "source": "pkg/search.py:1",
             "issue": "pkg/search.py does not bind `SearchType`; pkg/types.py declares it"}
    (run / "signatures-2.txt").write_bytes(json.dumps({**judged, "doc_errors": [error]}).encode("utf-8"))
    signatures = _exec(command, values, tmp_path)
    assert (signatures["signatureAccuracy"], signatures["totalDocumented"]) == (
        without["signatureAccuracy"], without["totalDocumented"]) == (100.0, 1)
    appended = _exec(_command(COVERAGE, '--input "{run_dir}/signature-gaps.json"'), values, tmp_path)
    assert appended["appended"] == ["GAP-001"]
    [record] = json.loads(Path(values["{ledgerFile}"]).read_bytes())["records"]
    assert (record["severity"], record["category"], record["title"], record["source"], record["export"]) == (
        "Info", "observation", "Not checked by script: SearchType", "SKILL.md:8", "SearchType")
    assert record["remediation"] == "Correct the documentation to match the source; no script checks this."


# A stratified skill on the scalar branch (#791, #792): the entry point declares five tier A names and re-exports
# helper, a Tier B name, from a file outside the tier A glob.
TIER_A_NAMES = ["alpha", "beta", "gamma", "delta", "epsilon"]
STRATIFIED_EXTRACTION = {
    "mode": "full", "status": "ok", "files_in_scope": 2, "truncated": False, "files_without_recipes": {},
    "file_issues": [], "errors": [],
    "scope": {"type": "public-api", "include": ["src/**"], "exclude": [], "tier_a_include": ["src/index.ts"]},
    "exports": [{"export_name": n, "export_type": "function", "source_file": "src/index.ts", "source_line": i,
                 "signature_line": f"export function {n}(): void {{"} for i, n in enumerate(TIER_A_NAMES, 1)]
               + [{"export_name": "helper", "export_type": "function", "source_file": "src/helper.ts",
                   "source_line": 1, "signature_line": "export function helper(): void {"}],
    "entry_points": {"status": "barrel",
                     "files": [{"language": "typescript", "file": "src/index.ts", "subpath": "."}]},
    "entry_point_diff": {
        "public": [{"name": n, "entry": "src/index.ts", "via": "declaration", "file": "src/index.ts", "line": i}
                   for i, n in enumerate(TIER_A_NAMES, 1)]
                  + [{"name": "helper", "entry": "src/index.ts", "via": "re-export", "file": "src/helper.ts",
                      "line": 1}],
        "internal": [], "extraction_gaps": [], "outside_scope": []},
    "counts": {"exports_public_api": 6, "exports_internal": 0, "effective_denominator": 5,
               "effective_denominator_basis": "tier_a_include", "curated_subset": True},
    "arms": {"monorepo": True, "specific_modules": False, "multi_subpath_exports": False},
}


def test_the_prose_scalar_branch_counts_the_named_set(tmp_path):
    """#791, #792 through the coverage step's own commands: a stratified skill on the scalar branch documents
    three of its five tier A names, two names the source does not export and the Tier B `helper`. The scalar
    command (§2c sends it to coverage-check-branches.md) counts the tier A set §2b picked, which a complete
    extraction lets it count (`setCounted`), so the run reads 60% with the two missing and the two stale names
    (not 100%, two extras offsetting two undocumented exports), and §5b's ledger call records each by name."""
    documented = ["alpha", "beta", "gamma", "phantomOne", "phantomTwo", "helper"]
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo. Use when testing.\n---\n# Demo\n\n"
                    + "".join(f"`{n}()` runs.\n" for n in documented),
    })
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory-response.txt").write_bytes(json.dumps({"exports": [
        {"name": n, "kind": "function", "params": "", "return_type": "void", "description": "Runs.",
         "at": f"SKILL.md:{7 + i}"} for i, n in enumerate(documented)], "cross_check_mismatches": []}).encode("utf-8"))
    (run / "extract-full.json").write_bytes(json.dumps(STRATIFIED_EXTRACTION).encode("utf-8"))
    (skill / "metadata.json").write_bytes(json.dumps({
        "skill_type": "single", "exports": TIER_A_NAMES + ["helper"],
        "stats": {"exports_public_api": 6, "exports_documented": 6, "effective_denominator": 5}}).encode("utf-8"))
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(),
              "{ledgerFile}": (tmp_path / "test-findings-20260101T000000Z-abcdef12.json").as_posix()}

    _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)
    assert _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)["valid"] is True
    surface = _exec(_choose(_command(COVERAGE, "surface --extraction"), keep=("--monorepo", "--curated-subset")),
                    values, tmp_path)
    assert surface["denominator"]["branch"] == "scalar" and surface["guards"]["deflation"]["applicable"] is True
    chosen = surface["denominator"]["surfaceSet"]
    assert (chosen, surface["denominator"]["setCounted"]) == ("tier_a_include", True), "a complete extraction"
    _exec(_choose(_command(COVERAGE, "uv run {coverageInputsScript} metadata")), values, tmp_path)
    _exec(_command(COVERAGE, "uv run {numeratorVerifyScript}"), values, tmp_path)
    command = _command(COVERAGE_BRANCHES, "--denominator-source scalar")
    assert '--surface "{run_dir}/surface.json" --surface-set <set>' in command
    coverage = _exec(command.replace("<set>", chosen), values, tmp_path)
    assert (coverage["denominator"], coverage["documented"], coverage["exportCoverage"]) == (5, 3, 60.0)
    assert (coverage["missing"], coverage["stale"]) == (["delta", "epsilon"], ["phantomOne", "phantomTwo"])
    assert "helper" not in coverage["documentedNames"] + coverage["stale"], "a Tier B name is neither"

    _exec(_choose(_command(COVERAGE, "--from coverage"), keep=("--surface",)), values, tmp_path)
    records = json.loads(Path(values["{ledgerFile}"]).read_bytes())["records"]
    assert [(r["category"], r["title"], r["source"]) for r in records] == [
        ("missing-export", "Missing export: delta", "src/index.ts:4"),
        ("missing-export", "Missing export: epsilon", "src/index.ts:5"),
        ("stale-documentation", "Stale documentation: phantomOne", "SKILL.md:10"),
        ("stale-documentation", "Stale documentation: phantomTwo", "SKILL.md:11"),
    ]
    flow = _flow(_read(COVERAGE))
    assert "- **Stale names** (`stale` when `staleApplicable` is true):" in flow
    assert "- **Missing names** (`missing`, barrel or scalar):" in flow


def test_the_prose_numerator_and_stack_count_only_the_inventorys_names(tmp_path):
    """#1068 through the coverage step's own commands: a stack skill whose provenance map cites `connect`, `Client`
    and `legacy`, and whose SKILL.md writes `legacy` only in a sentence saying it does not cover it, so its
    inventory gives `legacy` no entry (inventory-contract.md). §2b's numerator check and the branches file's stack
    command both read the inventory: `legacy` is absent from the verified count and missing from the stack's."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo-stack\ndescription: Demo. Use when testing.\n---\n# Demo stack\n\n"
                    "`connect(url)` opens a session. `Client` wraps it.\n\n`legacy` is not covered here.\n",
        "metadata.json": json.dumps({"skill_type": "stack",
                                     "stats": {"exports_documented": 3, "effective_denominator": 3}}),
    })
    provenance = tmp_path / "provenance-map.json"
    provenance.write_bytes(json.dumps({"skill_type": "stack", "entries": [
        {"export_name": n, "source_library": lib} for n, lib in (("connect", "liba"), ("Client", "liba"),
                                                                 ("legacy", "libb"))]}).encode("utf-8"))
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory-response.txt").write_bytes(json.dumps({"exports": [
        {"name": "connect", "kind": "function", "params": "url", "description": "Opens a session.",
         "at": "SKILL.md:7"},
        {"name": "Client", "kind": "class", "description": "Wraps it.", "at": "SKILL.md:7"},
    ], "cross_check_mismatches": []}).encode("utf-8"))
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(),
              "{forge_provenance_map}": provenance.as_posix()}

    _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)
    assert _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)["valid"] is True
    inputs = _exec(_choose(_command(COVERAGE, "uv run {coverageInputsScript} metadata"), keep=("--provenance",)),
                   values, tmp_path)
    assert inputs["inflationSignature"] is True
    assert inputs["stack"] == {"basis": "provenance", "denominator": 3,
                               "compositionNames": ["Client", "connect", "legacy"]}
    numerator = _exec(_command(COVERAGE, "uv run {numeratorVerifyScript}"), values, tmp_path)
    assert (numerator["declared"], numerator["verified"], numerator["absent"], numerator["inflated"]) == \
        (3, 2, ["legacy"], True)
    assert json.loads((run / "numerator.json").read_bytes()) == numerator
    stack = _exec(_command(COVERAGE_BRANCHES, "--denominator-source stack"), values, tmp_path)
    assert (stack["branch"], stack["documented"], stack["denominator"], stack["missingCount"]) == ("stack", 2, 3, 1)

    assert ("A declared name is `verified` only when the validated inventory gives it an entry and the skill's text "
            "writes it: one the skill writes only where the inventory contract gives it none (such as a type "
            "position in another name's signature, a sentence saying the skill does not cover it, a local import "
            "alias, a name it says the source does not export, a form marked removed or from an earlier version) "
            "is `absent`.") in _flow(_read(COVERAGE))
    assert ("A name a module path qualifies has the entry of its last segment (`cognee.add` that of `add`), and one "
            "the provenance map types `module` or `package`, which the inventory has no kind for, is `verified` when "
            "the text writes it.") in _flow(_read(COVERAGE))
    assert ("With `coverage-inputs.json` `stack.basis` `provenance`, it counts each cited export name that the "
            "validated inventory gives an entry and the skill's text writes, as §2b's numerator check does. With "
            "`composition`, it looks each library and integration pair name up in the text alone: those name no "
            "export, so the inventory never lists them.") in _flow(_read(COVERAGE_BRANCHES))


def test_the_prose_fallback_scan_runs(tmp_path):
    """coverage-check-tiers.md's Fallback Per-File Scan, as written: `plan` without `--surface` maps every
    documented signature, the saved per-file responses (fence and all) build the surface, and §2b's
    `score` reads those same files as its results."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "# Demo\n\n`fetchData(url)` fetches. `Options` configures.\n",
        "metadata.json": json.dumps({"skill_type": "single", "exports": ["fetchData", "Options"]}),
    })
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory-response.txt").write_bytes(json.dumps({"exports": [
        {"name": "fetchData", "kind": "function", "params": "url: string", "return_type": "string",
         "description": "Fetches.", "at": "SKILL.md:3"},
        {"name": "Options", "kind": "interface", "description": "Configures."},
    ], "cross_check_mismatches": []}).encode("utf-8"))
    (run / "per-file-1.txt").write_bytes(("```json\n" + json.dumps({
        "file": "src/index.ts", "exports_found": ["fetchData", "Options"], "types_found": ["Options"],
        "signature_mismatches": [{"name": "fetchData", "line": 1,
                                  "source_sig": "(url: string, init?: object) => string",
                                  "documented_sig": "(url: string) => string",
                                  "issue": "missing optional parameter 'init'"}],
    }) + "\n```\n").encode("utf-8"))
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(), "<n>": "1"}

    _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)
    assert _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)["valid"] is True
    plan = _exec(_command(COVERAGE_TIERS, "uv run {scoreSignaturesScript} plan"), values, tmp_path)
    assert (plan["files"], plan["documentedSignatures"]) == (
        [], {"fetchData": {"params": "url: string", "return_type": "string"}})
    surface = _exec(_choose(_command(COVERAGE_TIERS, "surface --per-file")), values, tmp_path)
    assert surface["sets"]["all"] == ["Options", "fetchData"]
    assert "the fallback scan's `per-file-<n>.txt`" in _flow(_slice(_read(COVERAGE), "**Score the signatures**",
                                                                   "### 2c."))
    # #712: the runner's exit-3 JSON rides along as --extraction: its stale tier A glob counts no name, so the
    # deflation guard runs on the per-file names and the stale-scope guard fires, and it adds no name or set
    forge = tmp_path / "forge-data"
    _write_tree(forge / "demo", {"skill-brief.yaml": (
        "name: demo\nlanguage: typescript\nscope:\n  type: specific-modules\n  include: ['src/**']\n"
        "  tier_a_include: ['src/old/**']\n")})
    (run / "extract-full.json").write_bytes(json.dumps({
        "mode": "full", "status": "no-ast-grep", "files_in_scope": 1, "exports": [], "entry_point_diff": None,
        "counts": None, "files_without_recipes": {}, "file_issues": [], "errors": [],
        "scope": {"include": ["src/**"], "exclude": [], "tier_a_include": ["src/old/**"], "type": "specific-modules",
                  "unmatched_include": [], "unmatched_tier_a_include": ["src/old/**"]},
        "entry_points": {"status": None, "files": [{"language": "typescript", "file": "src/index.ts", "package": ".",
                                                    "subpath": ".", "resolution": "file", "in_scope": True}]},
        "warnings": ["scope.tier_a_include pattern 'src/old/**' matches no file"],
    }).encode("utf-8"))
    (skill / "metadata.json").write_bytes(json.dumps({"skill_type": "single", "exports": ["fetchData", "Options"],
                                                      "stats": {"effective_denominator": 1}}).encode("utf-8"))
    values.update({"{forge_data_folder}": forge.as_posix(), "{skill_name}": "demo"})
    command = _command(COVERAGE_TIERS, "surface --per-file")
    # #733: with no runner JSON, --fallback-scan lets the per-file names decide: no tier A set, so the
    # deflation guard fires, while only the runner can say the glob is stale
    assert "--fallback-scan" in command.split() and "--fallback-scan" not in _read(COVERAGE)
    alone = _exec(_choose(command, keep=("--brief",)), values, tmp_path)["guards"]
    assert (alone["deflation"]["fires"], alone["staleScope"]["applicable"]) == (True, False), "no runner word"
    surface = _exec(_choose(command, keep=("--extraction", "--brief")), values, tmp_path)
    assert surface["sets"] == {"all": ["Options", "fetchData"], "scope.include": ["Options", "fetchData"]}
    assert surface["guards"]["deflation"] == {"applicable": True, "basis": "scope.include", "effectiveDenominator": 1,
                                              "rederived": 2, "pct": 100.0, "fires": True}
    assert (surface["guards"]["staleScope"]["fires"], surface["guards"]["staleScope"]["unmatchedTierAInclude"]) == (
        True, ["src/old/**"])
    assert "only its scope and the globs it lists as matching no file" in _flow(_read(COVERAGE_TIERS))
    command = _choose(_command(COVERAGE, "uv run {scoreSignaturesScript} score")).replace(
        '"{run_dir}/signatures-<n>.txt"', '"{run_dir}/per-file-<n>.txt"').replace("<set>", "all")
    scores = _exec(command, values, tmp_path)
    assert (scores["signatureAccuracy"], scores["typeCoverage"]) == (0.0, 100.0)
    assert [record["title"] for record in json.loads((run / "signature-gaps.json").read_bytes())] == [
        "Signature mismatch: fetchData"]


def test_the_fallback_scan_asks_each_file_for_the_names_it_defines():
    """#750: a barrel (or an entry file that defines a name of its own, as cognee's `__init__.py` defines
    `logger`) gets a subagent too, so each subagent leaves out the names its file only passes on from another
    module of the source: the module that defines each one has its own result, and the loader reads every result
    as the defining file's. A name passed on from another package stays, since no other result counts it."""
    scan = _flow(_slice(_read(COVERAGE_TIERS), "## Fallback Per-File Scan", "coverage-check.md §2b scores"))
    assert "It extracts the symbols the file exports, with their full signatures" in scan
    assert ("leaves out a name the file only passes on from another module of the source being tested "
            "(`export { x } from './x'`, `export * from`, an `__init__.py` import, a Rust `pub use`), which that "
            "module's own result counts, keeps a name it passes on from another package (`export { z } from "
            "'zod'`), which no other result counts") in scan
    assert "the file's exported symbols" not in scan


# #926: the one rule every by-eye branch reads, appended to §2's per-file shape.
EXTERNAL_STAR_RULE = ("An `export * from` or `export type * from` another package adds no name: list "
                      "`<line>: <statement>` in `unresolved_stars` and Coverage Analysis.")


def test_a_star_from_another_package_adds_no_name(tmp_path):
    """#926: a per-file result read by eye gives no name for an `export *` or `export type *` from another package
    (a specifier that is no relative path), as the recipe runner's `resolve_js_module` reads no package name and
    leaves that star unresolved, so no run decides alone which of the package's names to count. §2 states it once
    for every by-eye branch; the Quick-tier warning and the fallback scan give the full wording. The result lists
    the statement in `unresolved_stars`, which `score` reads past, and the Coverage Analysis section names it
    unresolved. A named re-export from another package keeps its name; a star from the source is still left to
    that module's own result. #1005: `surface` lists the star in `unresolvedStars` (at Quick tier from the parser's
    `unlisted` record, since a result that lists no name stays out), so §5b's coverage call records a stale name
    the skill cites at that file as an Info `Not checked by script` observation, not a Medium gap."""
    text = _read(COVERAGE)
    section2 = _flow(_slice(text, "### 2. Analyze Source Code", "### 2b."))
    tiers = _read(COVERAGE_TIERS)
    quick = _flow(_quick_tier())
    scan = _flow(_slice(tiers, "## Fallback Per-File Scan", "coverage-check.md §2b scores"))
    # Forge by eye (and every other branch): right after the one per-file shape, in one clause of at most 150
    # characters, with no pointer to the tiers file, so the budget holds.
    assert f"given to `surface` with one `--per-file` each. {EXTERNAL_STAR_RULE}" in section2
    assert len(" " + EXTERNAL_STAR_RULE) <= 150
    assert len(text) < COVERAGE_CHAR_BUDGET, len(text)
    assert text.split("\n---\n", 1)[1].count("{coverageTiersFile}") == 2
    # Quick tier: the parser's warning on such a star gives no name, and the statement is listed unresolved.
    assert ("and list those names in the Coverage Analysis section as read by eye. A warning on an `export *` or "
            "`export type *` from another package (a specifier that is no relative path; the warning writes either "
            "as `export *`) gives no name, as the recipe runner leaves such a star unresolved: list the statement as "
            "the source writes it, `<line>: <statement>`, in the `unresolved_stars` of that entry file's per-file "
            "result, and in the Coverage Analysis section as unresolved.") in quick
    # A result that lists no name stays out of `surface`, so a star alone moves no basis and silences no guard.
    assert "Give `surface` one `--quick` per package, one `--per-file` per saved result that lists a name," in quick
    # Fallback: the subagent gives no name for it and returns it; the main thread lists each response's.
    assert ("keeps a name it passes on from another package (`export { z } from 'zod'`), which no other result "
            "counts, gives no name for an `export * from` or `export type * from` another package (a specifier "
            "that is no relative path; `export * as ns` still gives `ns`), which the recipe runner leaves "
            "unresolved, listing each such statement as `<line>: <statement>` in `unresolved_stars`, compares each "
            "with the map's entry") in scan
    assert '"signature_mismatches": [...], "unresolved_stars": [...], "undecided": [...]}`' in scan
    assert ("List each response's `unresolved_stars` in the Coverage Analysis section as unresolved. Save each "
            "response to `{run_dir}/per-file-<n>.txt`") in scan
    # A star from the source is still left to the module's own result.
    assert ("(`export { x } from './x'`, `export * from`, an `__init__.py` import, a Rust `pub use`), which that "
            "module's own result counts") in scan
    # The unresolved list is no read-by-eye list: each branch still counts that phrase once.
    assert _flow(tiers).count("in the Coverage Analysis section as read by eye") == 2

    # The Quick-tier parser lists no name for the star (it warns, writing `export type *` as `export *`) and keeps
    # the named re-export from another package.
    source = _write_tree(tmp_path / "src", {
        "package.json": '{"name": "fx", "version": "1.0.0", "exports": {".": "./src/index.ts"}}\n',
        "src/index.ts": "export type * from '@vitest/spy';\nexport { z } from 'zod';\nexport function spyOn(o) {}\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    proc = _run(QUICK_CMD, {"{source_path}": source.as_posix(), "<language>": "typescript",
                            "<manifest path>": "package.json", "<entry path>": "src/index.ts"}, tmp_path)
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)
    assert [export["name"] for export in parsed["exports"]] == ["z", "spyOn"]
    [warning] = parsed["warnings"]
    assert "`export * from '@vitest/spy'`" in warning, warning
    (run / "quick-1.json").write_bytes(proc.stdout)
    star = "1: export type * from '@vitest/spy'"
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "# Fx\n\n`spyOn(o)` spies. `z` validates.\n",
        "metadata.json": json.dumps({"skill_type": "single", "exports": ["spyOn", "z"]}),
    })
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(), "<n>": "1"}
    # The by-eye result for the warned statement lists no name, only the statement in `unresolved_stars`, so it
    # stays out of `surface`: the parser's names alone make the surface.
    (run / "per-file-1.json").write_bytes(json.dumps({
        "file": "src/index.ts", "exports_found": [], "signature_mismatches": [], "unresolved_stars": [star],
    }).encode("utf-8"))
    surface = _exec(_choose(_command(COVERAGE_TIERS, "surface --quick")), values, tmp_path)
    assert surface["sets"]["all"] == ["spyOn", "z"] and "violations" not in surface
    assert surface["unresolvedStars"] == [
        {"file": "src/index.ts", "line": 1, "statement": "export * from '@vitest/spy'"}]

    # The fallback scan: a response that carries `unresolved_stars` passes `surface`'s schema check, adds only the
    # names it lists, and `score` reads it as a result.
    (run / "inventory-response.txt").write_bytes(json.dumps({"exports": [
        {"name": "spyOn", "kind": "function", "params": "o", "return_type": "void", "description": "Spies.",
         "at": "SKILL.md:3"},
        {"name": "z", "kind": "constant", "description": "Validates."},
    ], "cross_check_mismatches": []}).encode("utf-8"))
    (run / "per-file-1.txt").write_bytes(("```json\n" + json.dumps({
        "file": "src/index.ts", "exports_found": ["spyOn", "z"], "types_found": [], "signature_mismatches": [],
        "unresolved_stars": [star],
    }) + "\n```\n").encode("utf-8"))
    _exec(_command(COVERAGE, "uv run {coverageInputsScript} floor"), values, tmp_path)
    assert _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)["valid"] is True
    _exec(_command(COVERAGE_TIERS, "uv run {scoreSignaturesScript} plan"), values, tmp_path)
    surface = _exec(_choose(_command(COVERAGE_TIERS, "surface --per-file")), values, tmp_path)
    assert surface["sets"]["all"] == ["spyOn", "z"] and "violations" not in surface
    assert surface["unresolvedStars"] == [{"file": "src/index.ts", "line": 1, "statement": star[3:]}]
    command = _choose(_command(COVERAGE, "uv run {scoreSignaturesScript} score")).replace(
        '"{run_dir}/signatures-<n>.txt"', '"{run_dir}/per-file-<n>.txt"').replace("<set>", "all")
    scores = _exec(command, values, tmp_path)
    assert scores["signatureAccuracy"] == 100.0, scores
    assert json.loads((run / "signature-gaps.json").read_bytes()) == []

    # #1005: a vitest type the skill documents at that file is no name to remove: §5b's coverage call (no
    # classify-stale at these tiers) records it as an Info observation naming the star, at its documenting line.
    with (skill / "SKILL.md").open("ab") as handle:
        handle.write(b"`Mock` mocks a function. `[AST:src/index.ts:L1]`\n")
    (run / "coverage.json").write_bytes(json.dumps(
        {"branch": "enumerated", "missing": [], "stale": ["Mock"]}).encode("utf-8"))
    values["{ledgerFile}"] = (tmp_path / "test-findings-20261108T000000Z-abcdef12.json").as_posix()
    _exec(_choose(_command(COVERAGE, "--from coverage"), keep=("--surface",)), values, tmp_path)
    [record] = json.loads(Path(values["{ledgerFile}"]).read_bytes())["records"]
    assert (record["severity"], record["category"], record["title"], record["source"]) == (
        "Info", "observation", "Not checked by script: Mock (another package's export *)", "SKILL.md:4")
    assert f"through `{star[3:]}` (`src/index.ts:1`)" in record["remediation"], record


def test_the_fallback_scan_reads_an_overload_set_whole():
    """#845, #827: a fallback per-file subagent gets the path of the signature comparison rules every judge reads, so
    a documented signature that matches an overload set's implementation or any of its overloads is no mismatch on
    that path either, and it tags a mismatch's `difference` as §2's judge does. The overload rule has one copy, in
    that file: neither coverage-check.md nor the tiers file repeats it."""
    scan = _flow(_slice(_read(COVERAGE_TIERS), "## Fallback Per-File Scan", "coverage-check.md §2b scores"))
    assert ("delegate a subagent that gets that map with the file and the absolute path of `{signatureRulesFile}` "
            "(under `{skill-root}`)") in scan
    assert ("compares each with the map's entry by the rules of that file (overload sets and `difference` tags "
            "included)") in scan
    rules = _flow(_slice(_read(SIGNATURE_RULES), "## Overload sets", "## Difference tags"))
    assert ("A declaration opening an overload set (Python `@overload` stubs, TS bodiless signatures) is read through "
            "its implementation: a documented signature matching the implementation or any overload is no "
            "mismatch") in rules
    for path in (COVERAGE, COVERAGE_TIERS):
        assert "is read through its implementation" not in _read(path), path.name


def test_the_prose_state_4_surface_runs(tmp_path):
    """State 4 reads no tier branch, so its `surface` call is spelled in the States 2 to 4 section that
    coverage-check.md §2 loads: the names read remotely by eye, saved as a per-file result, are the surface, and
    the metadata adds no name."""
    state4 = _flow(_slice(_read(COVERAGE_BRANCHES), "- **State 4**:", "## Scalar and Stack Branches"))
    calls = re.findall(r"`(surface --per-file [^`]+)`", state4)
    assert len(calls) == 1, state4
    skill = _write_tree(tmp_path / "skill", {
        "metadata.json": json.dumps({"skill_type": "single", "exports": ["fetchData", "Options", "helper"]}),
    })
    run = tmp_path / "run"
    run.mkdir()
    (run / "per-file-1.json").write_bytes(json.dumps({"file": "src/index.ts", "exports_found": ["fetchData", "Options"],
                                                      "signature_mismatches": []}).encode("utf-8"))
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(), "<n>": "1"}
    surface = _exec(_choose("uv run {coverageInputsScript} " + calls[0]), values, tmp_path)
    assert surface["sets"]["all"] == ["Options", "fetchData"]
    assert (run / "surface.json").is_file()


# coverage-check.md's budget as a single-purpose reference (#600): about 9,000
# tiktoken cl100k_base tokens; this prose runs about 4 characters a token, so
# 36,000 characters stand in for it here.
COVERAGE_CHAR_BUDGET = 36_000

# The text coverage-check.md carved into coverage-check-branches.md, byte for byte as the step held it at
# 3ac917ef (the surplus paragraph's guard sentence as #788 and #813 rewrote it; §1a's failures as #814 rewrote
# them, the refused file deleted before the re-dispatch, and as #790 did, a floor name one the skill must keep and
# a floor file exit 1 names written again;
# §2c's scalar and stack commands, the scalar branch's
# counted set and the surplus paragraph's subject as #791 and #792 moved, added and rewrote them; §5b's
# split-body Source as #841 rewrote it, the other side of a pair of references and the default Source
# included): each
# section's blocks, which the step no longer holds.
CARVED_TO_BRANCHES = {
    "Inventory Failures": [(
        "- **`valid` false (exit 2):** delete the response `{validateInventoryScript}` refused, so a stale one is "
        "never validated twice:\n"
        "\n"
        "  ```bash\n"
        "  rm -f \"{run_dir}/inventory-response.txt\"\n"
        "  ```\n"
        "\n"
        "  Re-dispatch the §1 subagent once, with the script's `violations[]` appended to its instructions (an "
        "absent name as a name the skill does not write, a floor name as one it must keep): it writes its new "
        "response to that file, or returns it "
        "for you to save there, as §1 says. Run the §1a command again.\n"
        "- **Exit 1** (no input, a file that cannot be read, or a package with no readable SKILL.md): correct the "
        "file and run it again. An error that names `--floor` (the floor file missing or malformed): run §1's "
        "`floor` command again, whose exit 1 halts the run `helper-failed` as §1 says, then the §1a command."
    )],
    "States 2 to 4": [(
        "- **State 2** (`{forge_provenance_map}`, the provenance map init.md §2 bound): the union of its "
        "named exports and the `metadata.json` `exports[]` names, with `--fold`, `--keep` and "
        "`--fold-prefix` as the Source API Surface Definition's canonicalization says:\n"
        "\n"
        "  ```bash\n"
        "  uv run {coverageInputsScript} surface --provenance \"{forge_provenance_map}\" --metadata "
        "\"{resolved_skill_package}/metadata.json\" [--brief "
        "\"{forge_data_folder}/{skill_name}/skill-brief.yaml\"] [--fold] [--keep <variant>] [--fold-prefix "
        "<prefix>] [--monorepo] [--pattern-reference-intent] [--curated-subset] --output "
        "\"{run_dir}/surface.json\"\n"
        "  ```\n"
        "\n"
        "  Step 5's scoring script reads its `state2` counts, and the report its fold summary, "
        "`canonical.summary`.\n"
        "- **State 3**: the `metadata.json` `exports[]` names: `surface --metadata "
        "\"{resolved_skill_package}/metadata.json\" [--monorepo] [--pattern-reference-intent] "
        "[--curated-subset] --output \"{run_dir}/surface.json\"`.\n"
        "- **State 4**: the names read remotely by eye, as per-file results: `surface --per-file "
        "\"{run_dir}/per-file-<n>.json\" [--brief \"{forge_data_folder}/{skill_name}/skill-brief.yaml\"] "
        "--metadata \"{resolved_skill_package}/metadata.json\" [--monorepo] [--pattern-reference-intent] "
        "[--curated-subset] [--barrel <state>] --output \"{run_dir}/surface.json\"`."
    )],
    "Scalar and Stack Branches": [(
        "Run the command of the branch §2b picked; §2c's exits apply to it:\n"
        "\n"
        "- **Scalar**, over the `coverage-inputs.json` scalar and §2b's set (`denominator.surfaceSet`); "
        "`--verified` makes §2b's `verified` count the numerator when the count was inflated and the branch "
        "counts no set:\n"
        "\n"
        "  ```bash\n"
        "  uv run {reconcileScript} --denominator-source scalar --coverage-inputs "
        "\"{run_dir}/coverage-inputs.json\" --inventory \"{run_dir}/inventory.json\" --surface "
        "\"{run_dir}/surface.json\" --surface-set <set> --skill-dir \"{resolved_skill_package}\" --verified "
        "\"{run_dir}/numerator.json\" --output \"{run_dir}/coverage.json\"\n"
        "  ```\n"
        "\n"
        "- **Stack** (`metadata.json.skill_type == \"stack\"`):\n"
        "\n"
        "  ```bash\n"
        # #1021: the stack command reads the inventory too, so its open readings reach coverage.json.
        "  uv run {reconcileScript} --denominator-source stack --coverage-inputs "
        "\"{run_dir}/coverage-inputs.json\" --inventory \"{run_dir}/inventory.json\" --skill-dir "
        "\"{resolved_skill_package}\" --output \"{run_dir}/coverage.json\"\n"
        "  ```"
    ), (
        "**The scalar branch counts §2b's set** only when `surface.json` `denominator.setCounted` is true: a "
        "scope set (not `all`) whose every name sits at the file that defines it (a complete runner extraction, "
        "the fallback scan, or quick output that traces each name), read whole. Then `numeratorSource` is "
        "`surface`: `documented` counts the documented names the set holds (`documentedNames`), so a documented "
        "name the set lacks never offsets an undocumented one; `missing` lists the set's undocumented names; "
        "§5's render draws the per-export table; and the denominator stays the stored count, so when the set's "
        "size (`surfaceSetSize`) differs from it, `warnings` names both. Otherwise (`all`, a set read by eye or "
        "from an incomplete extraction, or an empty set, which warns) the branch looks each documented name up "
        "in the skill, `--verified` applies, and `missing` lists no name. On any surface read from the source "
        "(`guards.deflation.applicable` true), `stale` lists the documented names the whole surface lacks (the "
        "set, the `all` set and each name on a `surface.json` `exports` record, a nested entry's included: the "
        "barrel branch finds `stale` against the same surface), with `staleApplicable` true, so §2c's Stale "
        "names bullet applies: a documented name outside the set that the source still exports is neither "
        "counted nor stale. §5's render lists each `warnings` entry."
    ), (
        "**A surplus is a signal, not a pass.** Where the numerator and denominator count independent sets (the "
        "stack branch, and the scalar branch when it counts no set), `documented` can exceed `denominator`, as "
        "it can when a counted set holds more names than the stored count: `coverage.json` then reports "
        "`numeratorSurplus` above 0 and `coverageCapped: true`, holds `exportCoverage` at 100 and keeps "
        "the raw ratio in `coverageUncapped`, and §5's render states the surplus beside both counts. A "
        "large surplus is the deflated-denominator signature: check `guards.deflation`, whose `basis` names "
        "the set it measured the stored count against, before accepting the 100."
    ), (
        "- **Missing count** (scalar or stack branch, `missingCount` above 0): one Medium "
        "`missing-export` gap for the count. A scalar result that counts its set records its `missing` names as "
        "§2c's Missing names bullet says instead, plus one gap for the rest when `missingCount` exceeds them. "
        "When §2b's numerator check found the count inflated and the scalar branch counted no set, its "
        "`absent[]` names replace this gap, one each: update-skill documents a named export, not a count."
    )],
    "Denominator Candidates": [(
        "```markdown\n"
        "**Denominator Candidates** (stratified-scope audit trail):\n"
        "- `stats.effective_denominator`: {statsEffectiveDenominator | absent}  {← chosen on the scalar "
        "branch}\n"
        "- `scope.tier_a_include` union: {tierAIncludeUnion | absent}    {← chosen if the barrel "
        "branch's set}\n"
        "- `scope.include` union: {scopeIncludeUnion | absent}           {← chosen if the barrel "
        "branch's set}\n"
        "- exports-map subpath union: {subpathUnion | absent}        {← chosen if the barrel branch's "
        "set}\n"
        "- root barrel: {rootBarrel | absent}                               {secondary candidate: "
        "root-barrel-vs-subpath-union audit}\n"
        "```"
    )],
    "Metadata Count Cross-Check": [(
        "`{coherenceScript}` compares the `coverage-inputs.json` counts and owns every skip (a stack, a "
        "reference app, a cluster with fewer than two counts, drift within its threshold):\n"
        "\n"
        "```bash\n"
        "uv run {coherenceScript} --inputs \"{run_dir}/coverage-inputs.json\" > "
        "\"{run_dir}/metadata-coherence.json\"\n"
        "```\n"
        "\n"
        "A non-zero exit leaves the script's error, or nothing, in that file: delete it, so §5b skips its "
        "call and records no count finding, and note the error in the Coverage Analysis section. §5b records "
        "each `findings[]` entry: a Medium entry as a Medium `metadata-drift` gap and an Info entry as an "
        "Info `multi-denominator` gap. They describe data quality and change no denominator. Record the "
        "denominator of a stack (`Denominator: stack composition ({N} cited contracts)` or `({N} libraries + "
        "integration pairs)`, from `stack.basis`) and of a reference app (`Denominator: pattern-surface "
        "({pattern_surfaces_documented})`)."
    )],
    "Docs-Only Run": [(
        "**A docs-only run** measures documentation completeness as its Export Coverage, with "
        "`analysis_confidence` `docs-only`. It runs only §1, §1a and §1b, the docs-only guard of §2b, §2c's "
        "`docsOnly` branch, §4's `Denominator: docs-only completeness` annotation, §5, §5b and §6. Step 5 "
        "passes `docsOnly: true` to the scoring script, which skips Signature Accuracy and Type Coverage at "
        "any tier.\n"
        "\n"
        "\"**Docs-only skill detected.** Coverage check evaluates documentation completeness rather than "
        "source code coverage.\""
    ), (
        # §2c's docsOnly command runs only on the docs-only branch, which loaded this section at §0
        "§2c's `docsOnly` branch: Export Coverage is the documentation completeness ratio, complete over "
        "documented items, and `incomplete[]` lists each incomplete item with the fields it lacks:\n"
        "\n"
        "```bash\n"
        "uv run {reconcileScript} --denominator-source docsOnly --inventory \"{run_dir}/inventory.json\" "
        "--output \"{run_dir}/coverage.json\"\n"
        "```"
    )],
    "Split-Body Sources": [(
        "The Source is `{reference_file}:{reference_line}`, of two references the one that sorts last, unless the "
        "pinned source settles it for the other side. At State 1 and the Forge tier or above, with `workspaceDrift` "
        "not `overridden`, load `{signatureRulesFile}` and set the two forms its `issue` gives against the export's "
        "declaration at the `file` and `line` `surface.json` gives, by its rules, when that one declaration decides "
        "(no overload set, no second declaring file, and an `otherDeclarations` list, not `null`, with no entry of the "
        "export's name; `null` means no runner extraction looked for one, as after the fallback per-file scan): when "
        "`{reference_file}`'s form agrees and the other side's does not, the Source is the other side, "
        "`SKILL.md:{skill_md_line}` or `{other_file}:{other_line}`. A pair that gives an `owner` is a `method`'s "
        "(inventory-contract.md): its declaration is the member of the method's bare name that the owner's body "
        "declares, read from the `file` and `line` of the owner's `surface.json` record, or, for an owner that binds "
        "the name to a function declared elsewhere (a keyword of the `types.SimpleNamespace(...)` call that builds it, "
        "a class attribute assigned a function), the declaration that binding names, read in the owner's file or "
        "through its import, or, for an owner that neither declares nor binds it and has no method of that name "
        "declared for it outside its body (a Go method of its receiver type, one in a Rust `impl` block or a Kotlin "
        "or Swift extension, a function assigned to its `prototype`), the member the first class in its method "
        "resolution order to declare or bind it gives, each base read in its subclass's file or through that file's "
        "import, and it decides when the owner's name has one declaration by the test above and the owner, or else "
        "that class, declares or binds the member once, with no overload set, the overloads of that name the owner "
        "and its bases declare counting as one set in Java, Kotlin, C# and Swift. A record of the bare name never "
        "stands in for the member, nor a base's member for a method declared for the owner outside its body, so with "
        "no record of the owner, with such a method, with no such member in the owner or a base in the source tree, "
        "with the first class to declare or bind it outside that tree, or with no `owner` on a pair whose `export` "
        "the inventory lists only as a `method`, nothing decides. "
        "Its remediation names the file to edit and the "
        "file and line whose form it takes, citing the declaration's `file:line`; when both forms agree with it, it "
        "says so and names what differs; when neither does, or nothing decides, it says no source settled it and "
        "names `{reference_file}` to edit, taking the other side's form (`{other_file}`'s, for two references). "
        "Under the State, tier and `workspaceDrift` conditions above, when nothing decides because the export's name "
        "has more than one declaration (a second declaring file, or an `otherDeclarations` entry of its name), on a "
        "pair that gives no `owner` and whose `export` the inventory does not list only as a `method`, set each form "
        "against each declaration of the name, its `surface.json` records and its `otherDeclarations` entries, read "
        "at their `file` and `line`, or found by its name in its `file` when its `line` is `null` (a per-file "
        "record): when each form agrees with a different one, the remediation names no form to take. For each side "
        "it gives the form's file and line and the declaration that form agrees with, and asks update-skill to add "
        "that declaration's citation, `[SRC:{file}:L{line}]`, or `[SRC:{file}]` for one with no `line`, which names "
        "every declaration in its file, on the form's line or, in a fenced block, on a comment line just above it, and to name the declaration's module or owner beside the form, so a later run's reader and "
        "§2's `bound` keep the two apart. Its Source stays `{reference_file}:{reference_line}` and its **Contradicted "
        "Side** `not settled`. When a pair set against the name's declarations this way has one form that agrees "
        "with one or more of them and the other form with none, and `otherDeclarations` is a list, not `null` (with "
        "`null`, the form that agrees with none may agree with a declaration no extraction looked for), the source "
        "settles the pair: its Source is the side whose form agrees with none, `{reference_file}:{reference_line}` or "
        "the other side, `SKILL.md:{skill_md_line}` or `{other_file}:{other_line}`, its **Contradicted Side** that "
        "side's path, and its remediation names that file to edit and the file and line whose form it takes, citing "
        "each declaration the agreeing form agrees with at the `file` and line it was read at. Every other pair "
        "keeps the remediation above."
    )],
}


def test_coverage_check_stays_under_its_budget_and_loads_each_carved_branch():
    """#600, #613 (w3 leanness-5, architecture-6): coverage-check.md stays under budget and keeps its
    bindings, its halts and the branch the model takes. A branch most runs never take lives in a branch file
    with no frontmatter, so no nextStepFile makes it a step a chain must reach, and its own commands move
    with it: the Quick-tier scan and the fallback per-file scan in coverage-check-tiers.md, which only the §2
    branch that takes one loads; §1a's inventory failures (the refused response's `rm` included, #814), States
    2 to 4 (State 2, 3 and 4's `surface` commands included), the scalar and stack branches (§2c's scalar and
    stack commands included, #791 and #792), the Denominator Candidates block, §4b's metadata count cross-check,
    the docs-only run and §5b's split-body Source (#841) in coverage-check-branches.md, byte for byte as the step
    held them, each section loaded only from the sentence of its branch, which names it. Every other call stays in
    the step, §5b's call that records the split-body gaps included."""
    text = _read(COVERAGE)
    assert len(text) < COVERAGE_CHAR_BUDGET, len(text)
    assert _frontmatter(COVERAGE)["coverageTiersFile"] == "references/coverage-check-tiers.md"
    tiers = _read(COVERAGE_TIERS)
    assert not tiers.startswith("---"), "a branch file, not a step file"
    assert re.findall(r"^## (.+)$", tiers, re.M) == ["Quick Tier", "Fallback Per-File Scan"]
    assert "HALT" not in tiers, "§2's Exits halt for the commands it runs"
    assert "§2 **Exits** apply here unchanged" in _flow(tiers)
    section2 = _slice(text, "### 2. Analyze Source Code", "### 2b.")
    body = text.split("\n---\n", 1)[1]
    assert body.count("{coverageTiersFile}") == section2.count("{coverageTiersFile}") == 2
    quick = _flow(_slice(section2, "**Quick Tier (no AST tools):**", "**Forge Tier"))
    assert "load `{coverageTiersFile}` and follow its **Quick Tier** section" in quick
    forge = _flow(_slice(section2, "**Forge Tier (ast-grep available):**", "**Compare the signatures.**"))
    assert "load `{coverageTiersFile}` and run its **Fallback Per-File Scan**" in forge
    assert _frontmatter(COVERAGE)["coverageBranchesFile"] == "references/coverage-check-branches.md"
    branches = _read(COVERAGE_BRANCHES)
    assert not branches.startswith("---"), "a branch file, not a step file"
    assert "HALT" not in branches, "the step halts; a branch section holds no halt"
    opening = _flow(_slice(branches, "Load this file only from", "\n## "))
    assert "When the section is done, continue in coverage-check.md right after the sentence that loaded it" in opening
    assert "§2 **Exits** apply here unchanged" in opening, "State 2, 3 and 4's `surface` calls exit as §2 says"
    # Each section, and the coverage-check.md sections whose branch sentence loads it.
    loads = {
        "Inventory Failures": ["#### 1a. Parent-Side Schema Validation"],
        "States 2 to 4": ["### 2. Analyze Source Code", "### 2b."],
        "Scalar and Stack Branches": ["### 2c."],
        "Denominator Candidates": ["### 4. The Denominator Record"],
        "Metadata Count Cross-Check": ["### 4b. Metadata Export-Count Coherence Cross-Check"],
        "Docs-Only Run": ["### 0. Check for Docs-Only Mode"],
        "Split-Body Sources": ["### 5b. Record the Coverage Gaps"],
    }
    assert re.findall(r"^## (.+)$", branches, re.M) == list(loads) == list(CARVED_TO_BRANCHES)
    heading, fenced, pointers = None, False, []
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6} ", line):
            heading = line
        elif "{coverageBranchesFile}" in line:
            assert heading is not None, f"a pointer before any heading: {line}"
            pointers.append((heading, _flow(line)))
    assert len(pointers) == body.count("{coverageBranchesFile}") == sum(map(len, loads.values()))
    for name, sections in loads.items():
        assert f"**{name}**" in opening, name
        at = [where for where, line in pointers if f"**{name}** section" in line]
        assert len(at) == len(sections) and all(h.startswith(s) for h, s in zip(at, sections)), (name, at)
        assert body.count(f"**{name}**") == len(sections), f"{name} is named only where its branch loads it"
    assert "Load it once: when another sentence names one of its sections, read that section from the copy " \
        "already loaded" in opening
    assert "its run files, its per-file results and its §2 **Exits** apply here unchanged" in opening
    flow = _flow(body)
    for sentence in (
        "**States 2 to 4 (no local source):** the surface is what the skill recorded, so there is no signature to "
        "score: load `{coverageBranchesFile}` and follow its **States 2 to 4** section.",
        # at State 1, which never loaded the section: State 2's command alone, with the flags the rebuild sets
        "When `rebuild` is `provenance-fold`, load `{coverageBranchesFile}` and rerun State 2's command from its "
        "**States 2 to 4** section without `--metadata` and with `--fold` and `--pattern-reference-intent`, running "
        "nothing else from that section",
        # §2c's scalar and stack commands live in the section its branch loads (#791, #792)
        "2. **Scalar or stack**: load `{coverageBranchesFile}` and follow its **Scalar and Stack Branches** "
        "section, which runs the branch's command.",
    ):
        assert sentence in flow, sentence
    # Each carved block is byte for byte the step's old text, in its own section, and the step no longer holds it.
    for name, blocks in CARVED_TO_BRANCHES.items():
        section = branches.split(f"\n## {name}\n", 1)[1].split("\n## ", 1)[0]
        for block in blocks:
            assert block in section and block not in body, (name, block[:60])
    # A per-file result has one shape, given once in §2 for every branch that reads names by eye.
    assert '`{"file": "<path>", "exports_found": [<each name>], "signature_mismatches": []}`' in _flow(section2)
    # What a script owns is not restated: no formula or return list around a call, no hand guard
    # after one, and no §3 drafting the table §5 writes (w3 leanness-9).
    for restated in ("documented_set ∩ barrel_set", "max(0,", "do not re-derive", "**do not",
                     "### 3. Build Coverage Results", "Signature Match", "Weight application is deferred"):
        assert restated not in text, restated
    # The counts, the per-export table and the category scores are the render's (determinism-2).
    section5 = _slice(text, "### 5. Write the Coverage Analysis Section", "### 5b.")
    assert 'uv run {reconcileScript} render --coverage "{run_dir}/coverage.json"' in section5
    assert "### Coverage Summary" not in text and "{the render output}" in section5


# --------------------------------------------------------------------------
# #598: coherence-check takes its usage counts and reference checks from the
# SKILL.md scanner; #587: the report is hidden until its checks pass;
# #593: the result envelope is the run's last line
# --------------------------------------------------------------------------


STAGE_FILES = ["init.md", "detect-mode.md", "coverage-check.md", "coherence-check.md", "external-validators.md",
               "step-hard-gate.md", "score.md", "report.md"]


@pytest.mark.parametrize("name", STAGE_FILES)
def test_every_stage_writes_the_report_it_was_handed(name):
    """init.md creates the report under a `.skf-` name; the others write `{report_file}`."""
    expected = "{forge_version}/.skf-test-report-{skill_name}-{run_id}.md" if name == "init.md" else "{report_file}"
    assert _frontmatter(REFS / name)["outputFile"] == expected


def test_the_report_takes_its_public_name_only_once_its_checks_pass():
    contract = _flow(_slice(_read(REPORT), "### 4c. Result Contract", "### 5. Finalize Output Document"))
    for check in ("**Enforce step completeness.**", "**Check the report sections.**", "**Find the health check**",
                  "**Renew the run lock**"):
        assert contract.index(check) < contract.index("**Publish the report.**"), check
    assert contract.index("**Publish the report.**") < contract.index("**Write the result contract.**")
    init = _flow(_slice(_read(INIT), "**6c. Create `{outputFile}`", "### 7."))
    assert "bind `{report_file}` ← that path" in init and "`skf-skill-inventory.py` counts a `.skf-` name" in init
    for path in (REPORT, HARD_GATE):
        assert _frontmatter(path)["publishedReportFile"] == "{forge_version}/test-report-{skill_name}-{run_id}.md"


def test_the_later_steps_read_the_verdict_inputs_from_the_report():
    """#587 enhancement-2: the threshold and the drift override come from the frontmatter."""
    for path in sorted(REFS.glob("*.md")):
        if path.name != "init.md":
            assert "allow_workspace_drift" not in _read(path), path.name
    drift = _flow(_slice(_read(SCORE), "**IF PASS:**", "**IF FAIL:**"))
    assert "the `{outputFile}` frontmatter's `workspaceDrift` is `overridden`" in drift
    assert "the flag on a clean tree leaves it `ok`" in drift
    assert "`workspaceDrift` is not `overridden`" in _flow(_read(COVERAGE))


def test_the_naive_usage_and_scripts_checks_read_the_scanner():
    section = _slice(_read(COHERENCE), "### 2. Naive Mode", "### 2b.")
    command = _command(COHERENCE, "usage-scope")
    assert command == ('uv run {scanSkillMdStructureHelper} usage-scope "{resolved_skill_package}/SKILL.md" '
                       '--exports "{run_dir}/inventory.json" --kinds function,method [--body single] '
                       '> "{run_dir}/usage-scope.json"')
    for gone in ('grep -c "{export.name}"', "grep -n '^## Scripts'", "grep -n"):
        assert gone not in section, gone
    seven = _flow(_slice(section, "**2.7 Scripts & Assets section.**", "**Hard rule:**"))
    assert "Read `scripts_assets` from the second JSON blob" in seven and "`missing` is true" in seven


def test_the_contextual_reference_checks_read_the_scanner():
    section = _flow(_slice(_read(COHERENCE), "### 3. Contextual Mode", "### 5. Contextual Mode"))
    command = _command(COHERENCE, "reference-check")
    assert command == ('uv run {scanSkillMdStructureHelper} reference-check "{resolved_skill_package}/SKILL.md" '
                       '[--source-root "{source_path}"] [--skills-root "{skills_output_folder}"] '
                       '> "{run_dir}/references.json"')
    assert "Do not check these targets again by hand or through subagents" in section
    assert "For EACH reference found, delegate" not in section and "os.path.realpath`) and require" not in section
    aggregate = _command(COHERENCE, "uv run {coherenceAggregationScript}")
    assert aggregate == ('uv run {coherenceAggregationScript} --references "{run_dir}/references.json" '
                         '[--judged "{run_dir}/judged-references.json"] --integration "{run_dir}/integration.json" '
                         '--output "{run_dir}/coherence.json"')
    assert "echo '{\"valid_references\"" not in _read(COHERENCE), "no count is tallied by hand"


def test_the_coherence_commands_run_against_the_scanner(tmp_path):
    """The usage scope counts `$state` and `a.b` as written, and the reference checks feed the aggregate."""
    skill = _write_tree(tmp_path / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo\n---\n# Demo\n\n## Usage\n\n```js\nlet c = $state(0);\n"
                    "x$state; aXb;\n```\n\nSee [API](references/api.md), [gone](references/gone.md) and "
                    "[escape](../../outside.md).\n",
        "references/api.md": "# API\n",
        "scripts/run.py": "print(1)\n",
    })
    run = tmp_path / "run"
    run.mkdir()
    (run / "inventory.json").write_bytes(json.dumps({"exports": [
        {"name": "$state", "kind": "function"}, {"name": "a.b", "kind": "method"}, {"name": "Cfg", "kind": "type"},
    ]}).encode("utf-8"))
    values = {"{resolved_skill_package}": skill.as_posix(), "{run_dir}": run.as_posix()}

    usage = _exec(_choose(_command(COHERENCE, "usage-scope")), values, tmp_path)
    assert [(e["name"], e["count"]) for e in usage["exports"]] == [("$state", 1), ("a.b", 0)]
    assert [e["name"] for e in usage["zero_usage"]] == ["a.b"]
    assert json.loads((run / "usage-scope.json").read_text(encoding="utf-8")) == usage

    refs = _exec(_choose(_command(COHERENCE, "reference-check")), values, tmp_path)
    assert [(r["target"], r["status"]) for r in refs["references"]] == [
        ("references/api.md", "ok"), ("references/gone.md", "missing"), ("../../outside.md", "escapes")]
    assert refs["scripts_assets"]["missing"] is True, "scripts/ exists and no Scripts heading does"
    (run / "integration.json").write_bytes(b'{"patterns_documented": 2, "patterns_complete": 1}')
    coherence = _exec(_choose(_command(COHERENCE, "uv run {coherenceAggregationScript}")), values, tmp_path)
    assert (coherence["input"]["valid_references"], coherence["input"]["total_references"]) == (1, 3)
    assert [r["status"] for r in coherence["invalidReferences"]] == ["missing", "escapes"]
    assert (run / "coherence.json").is_file()
    # #1063: stdout gives the number of invalid references, so §6 records each one from the file
    doc = _flow(_read(COHERENCE))
    assert ("`{run_dir}/coherence.json` lists each invalid reference with its `status` in `invalidReferences[]`, "
            "which §6 records from that file; stdout gives only their number.") in doc
    assert "Its `invalidReferences[]` lists" not in doc


def test_reference_check_extracts_exactly_the_forms_section_3_names(tmp_path):
    """§3 names what the scanner checks: markdown links and `references/`, `scripts/` and `assets/`
    mentions. A path written outside a link (`../shared/types.ts` in inline code, an import
    specifier) is neither extracted nor handed to a subagent, and §3 says so."""
    section = _flow(_slice(_read(COHERENCE), "### 3. Contextual Mode", "### 4. Contextual Mode"))
    for form in ("`[types](src/types.ts)`", "`[guide](references/guide.md)`", "`references/{file}.md`",
                 "`scripts/{file}`", "`assets/{file}`"):
        assert form in section, form
    assert "Any other path written outside a link (`../shared/types.ts` in inline code, an import specifier) is not checked" in section
    assert '"type": "skill|type-import|integration-pattern"' in section, "the subagent returns no file-path type"
    source = tmp_path / "source"
    skill = _write_tree(tmp_path / "source" / "skill", {
        "SKILL.md": "---\nname: demo\ndescription: Demo\n---\n# Demo\n\n"
                    "See [types](../shared/types.ts), [guide](references/guide.md) and [file](./path/to/file.ts).\n\n"
                    "Bare: `../shared/types.ts`, `./path/to/file.ts` and `import { Props } from './module'`.\n\n"
                    "Mentions: `references/api.md`, scripts/run.py and `assets/logo.png`.\n",
        "references/guide.md": "# Guide\n",
        "references/api.md": "# API\n",
        "scripts/run.py": "print(1)\n",
        "assets/logo.png": "png",
    })
    _write_tree(source, {"shared/types.ts": "export type Props = {};\n"})
    run = tmp_path / "run"
    run.mkdir()
    values = {"{resolved_skill_package}": skill.as_posix(), "{run_dir}": run.as_posix(),
              "{source_path}": source.as_posix()}
    refs = _exec(_choose(_command(COHERENCE, "reference-check"), keep=("--source-root",)), values, tmp_path)
    assert [(r["target"], r["form"], r["type"], r["status"], r["root"]) for r in refs["references"]] == [
        ("../shared/types.ts", "link", "file-path", "ok", "source"),
        ("references/guide.md", "link", "file-path", "ok", "skill"),
        ("./path/to/file.ts", "link", "file-path", "missing", "skill"),
        ("references/api.md", "mention", "file-path", "ok", "skill"),
        ("scripts/run.py", "mention", "script-asset", "ok", "skill"),
        ("assets/logo.png", "mention", "script-asset", "ok", "skill"),
    ]
    # Line 9 writes the same paths outside a link: nothing on it is a reference.
    assert sorted({r["line"] for r in refs["references"]}) == [7, 11]


def test_the_result_envelope_is_the_runs_last_line():
    """The W3 enhancement-1 handoff: the shared health check shows the bound line last."""
    shared = _read(SRC / "shared" / "health-check.md")
    arrival = _flow(_slice(shared, "### 0. Announce Arrival", "**Display in `{communication_language}`:**"))
    assert "may bind `{result_envelope_line}`" in arrival and "In a standalone headless run" in arrival
    # §5c, the local queue, is the file's last section: it runs to the end of the file
    assert shared.count("### 5c. Local-Queue Path") == 1
    for start, end in (("### 2. Reflect on Execution", "### 3."), ("### 5c. Local-Queue Path", None)):
        stop = _flow(_slice(shared, start, end) if end else shared[shared.index(start):])
        assert "When `{result_envelope_line}` is bound (§0), display it verbatim after that" in stop, start
    # nothing follows §5c's envelope line: it is the shared health check's last line
    assert shared.rstrip().endswith("display it verbatim after that block, as the last line.")
    report = _flow(_read(REPORT))
    assert "bind `{result_envelope_line}` ← `{result_line}`" in report
    assert "display `{result_envelope_line}` verbatim as the run's last line" in report
    # The stdout/stderr split is explained once, in the contract.
    assert "the split is a label only" in _flow(_read(CONTRACT)) and "the split is a label only" not in report


def test_the_shared_health_check_states_its_findings_rule_once():
    """v4.0.0 quality gate run 1, skf-create-skill leanness-2: the
    anti-fabrication rule is one reasoned rule in the execution rules, not
    shouted bullets restated in the issue-writing rules and a closing
    checklist."""
    shared = _read(SRC / "shared" / "health-check.md")
    rules = _flow(_slice(shared, "## MANDATORY EXECUTION RULES:", "## MANDATORY SEQUENCE"))
    assert ("Zero findings is the expected outcome of a good run. Report only a bug, friction or gap you hit in this "
            "session, each with the step file and section where it happened, and leave out anything you cannot tell "
            "apart from your own confusion: a finding you invent can become a real GitHub issue filed against the "
            "module.") in rules
    folded = shared.lower()
    assert folded.count("zero findings") == 1 and "zero issues" not in folded
    assert folded.count("your own confusion") == 1
    assert "system failure" not in folded and "fabricat" not in folded
