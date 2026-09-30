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
- every read site (source access State 2, the coverage stack denominator
  and Cluster-B count, the Migration & Deprecation gate, the external
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
  pipes the payload stage-helper-payload.py reads from disk into
  skf-extract-public-api.py --mode quick (for a skill quick-skill built)
  and into skf-detect-workspaces.py, and the source access protocol's
  monorepo tests read the detector's answer.

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


QUICK_CMD = ('uv run {stageHelperPayloadScript} extract-public-api --source-root "{source_path}" '
             '--language <language> --manifest <manifest path> --entry <entry path> '
             '| uv run {extractPublicApiHelper} --mode quick')
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
    # What the parser skips is read by eye and named in the report.
    for form in ("`from ... import`", "`pub use`", "`export *`", "`async def`"):
        assert form in flow, form
    assert flow.count("read by eye") + flow.count("read them by eye") >= 2


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
    ("- **Stratified-scope monorepo packages", "**Resolution order:**"),
    ("**Trigger (either fires):**", "**Denominator:**"),
    ("- **Multi-entry (exports-map) packages", "**Denominator:**"),
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
