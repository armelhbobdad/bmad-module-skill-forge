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
  stage-helper-payload.py reads from disk into skf-detect-workspaces.py, and
  the source access protocol's monorepo tests read the detector's answer.

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
carved into coverage-check-tiers.md, loaded only by the branch that needs it.

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
COHERENCE = REFS / "coherence-check.md"
SCORING = REFS / "scoring-rules.md"
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
    (COVERAGE, "**States 2 to 4 (no local source):**", "### 2b.", PROVENANCE),
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
        assert f"--target {{forge_version}}/{name}" in stack
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
                   '`halt_reason: "another-run-active"`', "(exit 1)"):
        assert needle in row, needle
    envelope = _slice(text, "## Result Envelope (Headless)", "## Result Files")
    assert "| `another-run-active` |" in envelope
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
# #584: the Quick-tier scan and the workspace layout
# --------------------------------------------------------------------------


QUICK_CMD = ('uv run {extractPublicApiHelper} --mode quick --language <language> --source-root "{source_path}" '
             '--manifest-file <manifest path> --entry-file <entry path>')
WORKSPACES_CMD = ('uv run {stageHelperPayloadScript} detect-workspaces --source-root "{source_path}" '
                  '| uv run {detectWorkspacesHelper}')


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
    for path in (COVERAGE, COVERAGE_TIERS):
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


QUICK_SURFACE_CMD = ('uv run {coverageInputsScript} surface --quick "{run_dir}/quick-<n>.json" '
                     '[--per-file "{run_dir}/per-file-<n>.json"] '
                     '[--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml"] '
                     '--metadata "{resolved_skill_package}/metadata.json" [--provenance "{forge_provenance_map}"] '
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
    assert "uv run {scoreSignaturesScript} score" not in _slice(text, "### 2. Analyze Source Code", "### 2b.")
    summary = _flow(_slice(text, "### Coverage Summary", "### Category Scores"))
    assert "each entry of `signatures.json` `warnings`" in summary
    # The scalar is read from the loader's file, never typed in.
    assert "--denominator-value" not in text
    assert '--denominator-source scalar --coverage-inputs "{run_dir}/coverage-inputs.json"' in text


def test_a_run_with_no_local_source_names_its_skip():
    flags = _flow(_slice(_read(SCORE), "#### 3a. Construct Scoring Input JSON", "#### 3b."))
    assert "`metadata-only` or `remote-only`, States 3 and 4" in flags
    docs_only = _flow(_slice(_read(COVERAGE), "**A docs-only run**", "**Docs-only skill detected.**"))
    assert "§4's Export Coverage line and its `Denominator: docs-only completeness` annotation" in docs_only


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
    # The detector keeps the list of manifests it reads; the prose repeats none.
    for name in ("`lerna.json`", "`rush.json`", "`build.gradle.kts`"):
        assert name not in layout, name
    assert "**Workspace Layout:** {source_workspace_kind" in _read(COVERAGE)


@pytest.mark.parametrize("start, end", [
    ("- **Stratified-scope monorepo packages", "Resolution order:"),
    ("- **Pattern-reference apps", "The denominator is"),
    ("- **Multi-entry (exports-map) packages", "Installers reach"),
], ids=["stratified-scope", "pattern-reference", "multi-entry"])
def test_each_monorepo_test_reads_the_detector(start, end):
    clause = _slice(_read(SOURCE_ACCESS), start, end)
    assert "`{source_is_monorepo}`" in clause
    for by_eye in ("`packages/` layout", "no `packages/`", "monorepo markers"):
        assert by_eye not in clause, by_eye


@pytest.mark.parametrize("files, expected", [
    ({"package.json": '{"name": "root", "workspaces": ["packages/*"]}\n',
      "packages/a/package.json": "{}\n", "packages/b/package.json": "{}\n"}, (True, "npm-workspaces")),
    ({"apps/web/package.json": "{}\n", "libs/ui/package.json": "{}\n"}, (True, "generic-folders")),
    ({"package.json": '{"name": "single"}\n', "node_modules/a/package.json": "{}\n",
      "node_modules/b/package.json": "{}\n"}, (False, None)),
], ids=["npm-workspaces", "generic-folders", "single-package"])
def test_the_prose_workspace_command_runs(tmp_path, files, expected):
    source = _write_tree(tmp_path / "src", files)
    proc = _run(WORKSPACES_CMD, {"{source_path}": source.as_posix()}, tmp_path)
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
    section = _flow(_slice(_read(COVERAGE), "### 1. Extract Documented Exports", "#### 1a."))
    listed = re.search(r"each `kind` is one of (.+?); every entry", section).group(1)
    assert re.findall(r"`([a-z]+)`", listed) == list(validator.VALID_KINDS)
    assert "every entry carries the `description`" in section


def test_an_invalid_inventory_is_redispatched_once_then_halts_with_its_reason():
    section = _flow(_slice(_read(COVERAGE), "#### 1a. Parent-Side Schema Validation", "### 1b."))
    assert "re-dispatch the §1 subagent once, with the script's `violations[]` appended" in section
    assert "(an absent name as a name the skill does not write)" in section
    assert 'HALT (`halt_reason: "inventory-invalid"`, phase `coverage-check:inventory`)' in section
    assert "SKF_TEST_RESULT_JSON" not in _read(COVERAGE), "the emitter prints the line"
    table = _flow(_slice(_read(CONTRACT), "| `halt_reason` | Raised by |", "When the emitter itself"))
    assert "| `inventory-invalid` | coverage-check.md §1a" in table


def test_the_spot_check_is_the_scripts():
    """#598 item 5: the §1a sample and the look-up run in validate-inventory.py, never a grep."""
    section = _slice(_read(COVERAGE), "#### 1a. Parent-Side Schema Validation", "### 1b.")
    command = _command(COVERAGE, "uv run {validateInventoryScript}")
    assert '--skill-package "{resolved_skill_package}"' in command
    assert "grep -n" not in section and "[0, len//2, len-1]" not in section
    assert "an export named `$state` or `a.b` is neither a shell variable nor a regex" in _flow(section)


def test_the_forge_tier_extraction_runs_once_without_a_head_cap():
    command = _command(COVERAGE, "uv run {extractPublicApiHelper} --mode full")
    assert command == ('uv run {extractPublicApiHelper} --mode full --source-root "{source_path}" '
                       '--brief "{forge_data_folder}/{skill_name}/skill-brief.yaml" --tier {detected_tier} '
                       '--head-cap 0 --output "{run_dir}/extract-full.json"')
    forge = _flow(_slice(_read(COVERAGE), "**Forge Tier (ast-grep available):**", "**Deep Tier"))
    # The fallback is decided from the JSON, and a recipe's internal match is never on the surface.
    assert "Decide what to do from the JSON, not from the exit code" in forge
    assert "`extraction.fallback.needed`" in forge and "`extraction.readByEye`" in forge
    assert "the recipes' internal matches are never part of it" in forge
    assert "reads the full declaration at `{file}:{line}`" in forge
    for gone in ("exports_documented", "missing_docs"):
        assert gone not in forge, gone


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


def _exec(command: str, values: dict[str, str], cwd: Path) -> dict:
    """Run one prose command (an `echo '<json>' | uv run ...` pipe included) and return its JSON."""
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
         "description": "Fetches the user's data; it's \"cached\"."},
        {"name": "helper", "kind": "function", "params": "x: number", "return_type": "number", "description": "Helps."},
        {"name": "Options", "kind": "interface", "description": "Configures."},
    ], "cross_check_mismatches": []}) + "\n```\n").encode("utf-8"))
    (run / "extract-full.json").write_bytes(json.dumps(EXTRACTION).encode("utf-8"))
    metadata = skill / "metadata.json"
    metadata.write_bytes(json.dumps({"skill_type": "single", "exports": ["fetchData", "helper", "Options"],
                                     "stats": {"exports_public_api": 3, "exports_documented": 3,
                                               "effective_denominator": 4}}).encode("utf-8"))
    values = {"{run_dir}": run.as_posix(), "{resolved_skill_package}": skill.as_posix(),
              "{ledgerFile}": (tmp_path / "test-findings-20260101T000000Z-abcdef12.json").as_posix()}

    census = _exec(_command(COVERAGE, "uv run {coverageInputsScript} census"), values, tmp_path)
    assert census["docsOnly"] is False
    validated = _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)
    assert validated["valid"] is True and (run / "inventory.json").is_file()
    surface = _exec(_choose(_command(COVERAGE, "surface --extraction")), values, tmp_path)
    assert surface["sets"]["all"] == ["Options", "fetchData", "helper"]
    plan = _exec(_command(COVERAGE, "uv run {scoreSignaturesScript} plan"), values, tmp_path)
    assert [f["file"] for f in plan["files"]] == ["src/helper.ts", "src/index.ts"]
    (run / "signatures-1.txt").write_bytes(json.dumps({"file": "src/helper.ts", "signature_mismatches": [
        {"name": "helper", "line": 1, "source_sig": "(x: number, y?: number) => number",
         "documented_sig": "(x: number) => number", "issue": "missing optional parameter 'y'"}]}).encode("utf-8"))
    (run / "signatures-2.txt").write_bytes(json.dumps({"file": "src/index.ts",
                                                       "signature_mismatches": []}).encode("utf-8"))
    signatures = _exec(_command(COVERAGE, "uv run {scoreSignaturesScript} score").replace(
        '--results "{run_dir}/signatures-<n>.txt"',
        '--results "{run_dir}/signatures-1.txt" --results "{run_dir}/signatures-2.txt"').replace(
        "<set>", "all"), values, tmp_path)
    assert (signatures["signatureAccuracy"], signatures["typeCoverage"]) == (50.0, 100.0)
    appended = _exec(_command(COVERAGE, '--input "{run_dir}/signature-gaps.json"'), values, tmp_path)
    assert appended["appended"] == ["GAP-001"]
    inputs = _exec(_choose(_command(COVERAGE, "uv run {coverageInputsScript} metadata")), values, tmp_path)
    assert inputs["inflationSignature"] is False
    numerator = _exec(_command(COVERAGE, "uv run {numeratorVerifyScript}"), values, tmp_path)
    assert numerator["skipped"] is True
    scalar = _exec(_command(COVERAGE, "--denominator-source scalar"), values, tmp_path)
    assert (scalar["documented"], scalar["denominator"]) == (3, 4), "the scalar comes from coverage-inputs.json"
    coverage = _exec(_command(COVERAGE, "--denominator-source barrel").replace("<set>", "all"), values, tmp_path)
    assert (coverage["documented"], coverage["denominator"], coverage["exportCoverage"]) == (3, 3, 100.0)
    coherence = _exec(_command(COVERAGE, "uv run {coherenceScript}"), values, tmp_path)
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
         "description": "Fetches."},
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

    assert _exec(_command(COVERAGE, "uv run {validateInventoryScript}"), values, tmp_path)["valid"] is True
    plan = _exec(_command(COVERAGE_TIERS, "uv run {scoreSignaturesScript} plan"), values, tmp_path)
    assert (plan["files"], plan["documentedSignatures"]) == (
        [], {"fetchData": {"params": "url: string", "return_type": "string"}})
    surface = _exec(_choose(_command(COVERAGE_TIERS, "surface --per-file")), values, tmp_path)
    assert surface["sets"]["all"] == ["Options", "fetchData"]
    assert "the fallback scan's `per-file-<n>.txt`" in _flow(_slice(_read(COVERAGE), "**Score the signatures**",
                                                                   "### 2c."))
    command = _command(COVERAGE, "uv run {scoreSignaturesScript} score").replace(
        '"{run_dir}/signatures-<n>.txt"', '"{run_dir}/per-file-<n>.txt"').replace("<set>", "all")
    scores = _exec(command, values, tmp_path)
    assert (scores["signatureAccuracy"], scores["typeCoverage"]) == (0.0, 100.0)
    assert [record["title"] for record in json.loads((run / "signature-gaps.json").read_bytes())] == [
        "Signature mismatch: fetchData"]


def test_the_prose_state_4_surface_runs(tmp_path):
    """State 4 reads no tier branch, so its `surface` call is spelled in coverage-check.md itself: the names
    read remotely by eye, saved as a per-file result, are the surface, and the metadata adds no name."""
    state4 = _flow(_slice(_read(COVERAGE), "- **State 4**:", "### 2b."))
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


def test_coverage_check_stays_under_its_budget_and_loads_each_carved_branch():
    """#600, #613 (w3 leanness-5, architecture-6): coverage-check.md keeps each call, its bindings and the
    branch the model takes, under budget. The Quick-tier scan and the fallback per-file scan, which most
    runs never take, live in coverage-check-tiers.md: only the §2 branch that takes one loads it, and it
    has no frontmatter, so no nextStepFile makes it a step a chain must reach."""
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
    # A per-file result has one shape, given once in §2 for every branch that reads names by eye.
    assert '`{"file": "<path>", "exports_found": [<each name>], "signature_mismatches": []}`' in _flow(section2)
    # What a script owns is not restated: no formula or return list around a call, no hand guard
    # after one, and no §3 drafting the table §5 writes (w3 leanness-9).
    for restated in ("documented_set ∩ barrel_set", "max(0,", "do not re-derive", "**do not",
                     "### 3. Build Coverage Results", "Signature Match", "Weight application is deferred"):
        assert restated not in text, restated
    summary = _flow(_slice(text, "### Coverage Summary", "### Category Scores"))
    for field in ("`denominator`", "`documented`", "`exportCoverage`", "`missingCount`", "`staleCount`",
                  "`numeratorSurplus`", "`coverageUncapped`"):
        assert field in summary, field


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
    for start, end in (("### 2. Reflect on Execution", "### 3."), ("### 5c. Local-Queue Path", "## CRITICAL")):
        stop = _flow(_slice(shared, start, end))
        assert "When `{result_envelope_line}` is bound (§0), display it verbatim after that" in stop, start
    report = _flow(_read(REPORT))
    assert "bind `{result_envelope_line}` ← `{result_line}`" in report
    assert "display `{result_envelope_line}` verbatim as the run's last line" in report
    # The stdout/stderr split is explained once, in the contract.
    assert "the split is a label only" in _flow(_read(CONTRACT)) and "the split is a label only" not in report
