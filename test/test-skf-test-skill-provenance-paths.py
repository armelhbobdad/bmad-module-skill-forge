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
  Cluster-B count, the Migration & Deprecation gate, the external
  validators' reuse check) reads its binding and names no path;
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
  command written out; the runtime check comes before the first helper
  call;
- the workspace drift guard (#588 item 4): init.md §5b runs
  skf-check-workspace-drift.py once per source tree instead of git by hand;
- the Quick-tier scan and the workspace layout (#584): coverage-check.md
  runs skf-extract-public-api.py --mode quick on the files by path (for a
  skill quick-skill built), pipes the payload stage-helper-payload.py reads
  from disk into skf-detect-workspaces.py, and the source access protocol's
  monorepo tests read the detector's answer.

They keep the scoring inputs scripted (#613, #540, #596): every script of
the coverage and score steps reads the run files the one before it wrote,
by path, in a run folder init.md creates and report.md removes, and the
prose commands run end to end against the real scripts, from the citation
census to compute-score.py reading every score file; the inventory a
subagent returns is validated from its saved file and re-dispatched once
before `inventory-invalid` halts the run; tooling health is `toolingStatus`,
never `analysisConfidence`; and scoring-rules.md, customize.toml and SKILL.md
keep no copy of the scoring rules and no override of them.

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
    (EXTERNAL, "### 1b. Check for Recent Validation Results", "**Staleness check:**", EVIDENCE),
]
READ_SITE_IDS = ["state-2", "metadata-loader", "state-2-surface", "migration-gate", "validator-reuse"]


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
    (EXTERNAL, "### 1b. Check for Recent Validation Results", "**Staleness check:**"),
], ids=["migration-gate", "validator-reuse"])
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
    assert "`skillDir`" in _slice(_read(EXTERNAL), "### 1. Resolve Skill Directory", "### 1b.")


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
STEP_RELEASE = "Every HALT in this step releases the run lock first (SKILL.md Workflow Rules)"
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
    assert '"halt_reason":"another-run-active"' in section


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
    assert contract.index(RENEW) < contract.index("write --target {forge_version}/skf-test-skill-result-")
    renewal = _flow(contract[:contract.index("**Resolve `{atomicWriteHelper}`")])
    assert "Exit 3" in renewal and "HALT before writing anything" in renewal
    assert '"halt_reason":"another-run-active"' in renewal

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
    assert "load and execute `{blockedStepFile}`" in block and "HALT" not in block
    assert _frontmatter(HARD_GATE)["blockedStepFile"] == "report.md"
    section7 = _flow(_slice(_read(REPORT), "### 7. Health-Check Dispatch", "load and execute `{nextStepFile}`"))
    bypass = _slice(section7, "**`--no-health-check` flag bypass", "Resolve `{healthCheckFile}`")
    assert bypass.index("mirror `healthCheckDispatched: false`") < bypass.index(RELEASE) \
        < bypass.index("exit the workflow")
    menu = section7[section7.index("Also mirror the boolean into the `healthCheckDispatched` field"):]
    assert menu.index("**Release the run lock:**") < menu.index(RELEASE) \
        < menu.index('Display: "**Test complete.** [C] Finish"')


def test_skill_md_documents_the_lock():
    text = _read(SKILL_MD)
    row = next(line for line in text.splitlines() if line.startswith("| **Concurrency** |"))
    for needle in ("`{forge_version}/.test-skill.lock`", "`skf-run-lock.py`", "report.md §4c renews it",
                   '`halt_reason: "another-run-active"`', "(exit 1)"):
        assert needle in row, needle
    contract = _slice(text, "## Result Contract (Headless)", "## On Activation")
    assert '"another-run-active"' in contract
    run_record = next(line for line in contract.splitlines() if "skf-test-skill-result-{run_id}.json" in line)
    assert "PID" not in run_record and "random suffix" in run_record


def test_skill_md_lists_the_init_halts_without_an_envelope():
    contract = _flow(_slice(_read(SKILL_MD), "## Result Contract (Headless)", "## On Activation"))
    listed = _slice(contract, "without** this envelope", "When threshold fallback occurred")
    for halt in ("init.md §1c", "init.md §2, §3a, §5b, §6a and §6b", "the lock renewal in report.md §4c",
                 "an invalid `--tier` value (init.md §4)", "every HALT in the coverage and coherence steps"):
        assert halt in listed, halt
    assert "now emits" not in contract


def test_runtime_is_checked_before_the_first_helper_call():
    body = _read(INIT).split("\n---\n", 1)[1]
    check = _slice(body, "### 1c. Check the Runtime", "### 2. Validate Skill Exists")
    assert body.index("### 1c. Check the Runtime") < body.index("uv run {")
    assert "command -v uv" in check and "HALT" in check
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
    assert '"halt_reason":"workspace-drift"' in section and "`halt_message` of every tree that drifted" in flow
    assert "`workspaceDrift: overridden`" in flow and "`allow_workspace_drift: true`" in flow


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
    return _slice(_read(COVERAGE), "**Quick Tier (no AST tools):**", "**Forge Tier (ast-grep available):**")


def test_coverage_binds_the_helpers_and_the_payload_script():
    frontmatter = _frontmatter(COVERAGE)
    for key, script in (("extractPublicApiProbeOrder", "skf-extract-public-api.py"),
                        ("detectWorkspacesProbeOrder", "skf-detect-workspaces.py")):
        assert frontmatter[key] == [f"{{project-root}}/_bmad/skf/shared/scripts/{script}",
                                    f"{{project-root}}/src/shared/scripts/{script}"]
    assert frontmatter["stageHelperPayloadScript"] == "scripts/stage-helper-payload.py"
    # The model copies no file text into a payload.
    text = _read(COVERAGE)
    for by_hand in ("file-write tool", ".skf-quick-exports-", ".skf-workspaces-"):
        assert by_hand not in text, by_hand


def test_quick_tier_parses_a_quick_skill_skill_with_its_parser():
    quick = _quick_tier()
    assert QUICK_CMD in _fence(quick, QUICK_CMD)
    flow = _flow(quick)
    assert "`generated_by` is `quick-skill`" in flow and "**Any other skill**" in flow
    # §2c's script decides documented, missing and stale from `exports_found`.
    assert '`{"file": "<entry path>", "exports_found": [' in flow
    for by_hand in ("exports_documented", "missing_docs", "by name matching", "`kotlin`"):
        assert by_hand not in flow, by_hand
    # The parser reads re-exports, async declarations and CommonJS itself; its
    # warnings name what the entry file alone cannot give, read by eye.
    for form in ("`from ... import`", "`pub use`", "`export * as`", "`async def`", "`module.exports`"):
        assert form in flow, form
    for warned in ("`export * from`", "a star import", "a non-literal `__all__` part", "`pub use x::*`",
                   "`module.exports = require(...)`"):
        assert warned in flow, warned
    assert "Read by eye only the statements its warnings name" in flow
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
    command = _choose(_command(COVERAGE, "surface --quick"), keep=("--brief",))
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
    assert f'mkdir -p "{RUN_FOLDER}"' in lock and "release the run lock (SKILL.md Workflow Rules), then HALT" in lock
    section7 = _flow(_slice(_read(REPORT), "### 7. Health-Check Dispatch", "load and execute `{nextStepFile}`"))
    assert section7.count(f'rm -rf "{RUN_FOLDER}"') == 2, "both ways a run ends remove it"
    bypass = _slice(section7, "**`--no-health-check` flag bypass", "Resolve `{healthCheckFile}`")
    assert bypass.index(RELEASE) < bypass.index("rm -rf") < bypass.index("exit the workflow")
    row = next(line for line in _read(SKILL_MD).splitlines() if line.startswith("| **Outputs** |"))
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
    assert "re-dispatch the §1 subagent once, with the absent names appended" in section
    assert 'HALT with `halt_reason: "inventory-invalid"`' in section
    line = next(line for line in _read(COVERAGE).splitlines() if '"halt_reason":"inventory-invalid"' in line)
    envelope = json.loads(line.split(": ", 1)[1])
    assert (envelope["status"], envelope["exit_code"], envelope["report_path"]) == ("error", 1, "{outputFile}")
    contract = _flow(_slice(_read(SKILL_MD), "## Result Contract (Headless)", "## On Activation"))
    assert '`"inventory-invalid"`' in contract
    assert "every HALT in the coverage and coherence steps except `inventory-invalid`" in contract


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
    assert "`toolingStatus: '{ok|frontmatter-validator-timeout}'`" in frontmatter
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
    proc = subprocess.run([sys.executable, str(PROSE_SCRIPTS[m.group(1)]), *shlex.split(rest)], cwd=cwd,
                          input=stdin, capture_output=True, check=False)
    assert proc.returncode == 0, (command, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8"))
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
