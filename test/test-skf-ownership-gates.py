#!/usr/bin/env python3
"""Prose pins for the ownership gate in the step files.

Step prose is not executed by any test, so these checks pin the parts of it
that keep SKF from writing into, moving, renaming or deleting a skill folder
it did not generate: the write check at the three writers (create-skill,
quick-skill and create-stack-skill), the four flat-layout migrate sites, drop
and rename (the skill folder, its forge folder and the rename lock), export
discovery, analyze-source's merge offer, the contract files that list halt
reasons, the docs that describe the gate, and the version-paths and
ccc-bridge knowledge. The helper behind the gate is tested in
test-skf-skill-inventory.py.

They also pin the readers that must see only the skills SKF generated: the
stack rosters of verify-stack, refine-architecture and compose-mode
create-stack-skill (skf-enumerate-stack-skills.py, tested in
test-skf-enumerate-stack-skills.py) and test-skill's discovery catalog.

They also pin where create-skill stages a skill before it writes the version:
under `_bmad-output/.skf-stage/`, never a folder a skills or forge folder
setting can name, so the ownership rules never read SKF's staging as a
skill folder SKF did not generate.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
INVENTORY_PY = SRC / "shared" / "scripts" / "skf-skill-inventory.py"

MIGRATE_SITES = {
    "src/skf-update-skill/references/init.md": "update",
    "src/skf-export-skill/references/load-skill.md": "export",
    "src/skf-audit-skill/references/init.md": "audit",
    "src/skf-test-skill/references/init.md": "test",
}
DROP_SELECT = "src/skf-drop-skill/references/select.md"
DROP_EXECUTE = "src/skf-drop-skill/references/execute.md"
DROP_SKILL = "src/skf-drop-skill/SKILL.md"
RENAME_SELECT = "src/skf-rename-skill/references/select.md"
RENAME_EXECUTE = "src/skf-rename-skill/references/execute.md"
DROP_REPORT = "src/skf-drop-skill/references/report.md"
CS_GENERATE = "src/skf-create-skill/references/generate-artifacts.md"
CS_REPORT = "src/skf-create-skill/references/report.md"
QS_WRITE = "src/skf-quick-skill/references/write-and-validate.md"
QS_HALT_CONTRACT = "src/skf-quick-skill/references/halt-contract.md"
SS_GENERATE = "src/skf-create-stack-skill/references/generate-output.md"
SS_SKILL = "src/skf-create-stack-skill/SKILL.md"
# Each writer step file, with the markers of its first write: the ownership
# check must come before every one of them.
WRITER_SITES = {
    CS_GENERATE: ("create the following directories",),
    QS_WRITE: ("create the skill output directories", "`{skill_package}/metadata.json` exists, confirm with user"),
    SS_GENERATE: ("stage-dir --target {skill_package}", "mkdir -p {forge_version}"),
}
WRITER_SKILLS = ("src/skf-create-skill/SKILL.md", "src/skf-quick-skill/SKILL.md", SS_SKILL)
CONTRACT_FILES = {
    "src/skf-drop-skill/references/headless-contract.md": ("not-skf-output",),
    "src/skf-drop-skill/SKILL.md": ("not-skf-output",),
    "src/skf-rename-skill/SKILL.md": ("not-skf-output", "flat-layout"),
    "src/skf-rename-skill/references/exit-codes.md": ("not-skf-output", "flat-layout"),
    "src/skf-export-skill/references/result-envelope.md": ("not-skf-output",),
    "src/skf-export-skill/SKILL.md": ("not-skf-output",),
    "src/skf-audit-skill/SKILL.md": ("not-skf-output",),
    "src/skf-test-skill/SKILL.md": ("not-skf-output",),
    QS_HALT_CONTRACT: ("not-skf-output", "flat-layout"),
    SS_SKILL: ("not-skf-output", "flat-layout"),
    CS_REPORT: ("not-skf-output", "flat-layout"),
}
PROBE_ORDER = (
    "skillInventoryProbeOrder:\n"
    "  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'\n"
    "  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'\n"
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str | None) -> str:
    """The text from marker `start` up to marker `end` (or the end of the text)."""
    assert start in text, f"marker {start!r} missing"
    body = text[text.index(start):]
    if end is not None:
        assert end in body, f"marker {end!r} missing after {start!r}"
        body = body[:body.index(end)]
    assert body.strip(), f"empty section after {start!r}"
    return body


def _row(text: str, prefix: str) -> str:
    """The first table row that starts with `prefix`."""
    rows = [line for line in text.splitlines() if line.startswith(prefix)]
    assert rows, f"no table row starts with {prefix!r}"
    return rows[0]


def _flat_rung(text: str) -> str:
    """The flat-path fallback rung: from its first line to the next numbered step."""
    start = text.index("If neither: fall back to the flat path")
    rest = text[start:]
    nxt = re.search(r"\n\d+\. ", rest)
    assert nxt, "the flat rung must be followed by the next numbered step"
    return rest[:nxt.start()]


def test_auto_migrate_sites_are_exactly_the_four():
    found = {
        str(p.relative_to(REPO)).replace("\\", "/")
        for p in SRC.glob("skf-*/references/**/*.md")
        if "auto-migrate" in p.read_text(encoding="utf-8")
    }
    assert found == set(MIGRATE_SITES), (
        "a step file that auto-migrates a flat skill must run the ownership gate first; "
        f"update MIGRATE_SITES and gate the new site: {sorted(found ^ set(MIGRATE_SITES))}")


@pytest.mark.parametrize("rel", sorted(MIGRATE_SITES))
def test_migrate_site_gates_before_migrating(rel):
    text = _read(rel)
    frontmatter = text.split("\n---\n", 1)[0] + "\n"
    assert PROBE_ORDER in frontmatter, "installed path first, then the src/ path"
    rung = _flat_rung(text)
    binding = "`{group_flat_skf}` ← `skills[0].flat_skf`"
    assert binding in rung
    assert "--skill" in rung
    assert rung.index(binding) < rung.index("migration rules"), "the gate must come before migrating"
    assert 'halt_reason: "not-skf-output"' in rung or '"halt_reason":"not-skf-output"' in rung
    assert "no helper candidate resolves" in rung, "a missing helper must fail closed"
    assert "`{group_errors}` ← `skills[0].errors`" in rung, "a link is not a missing marker"
    assert "in place of the marker sentence" in rung
    assert "`skills_output_folder`" in rung and "/skf-setup" in rung
    assert f"will not move or {MIGRATE_SITES[rel]} it" in rung


@pytest.mark.parametrize("rel, flags", [
    ("src/skf-update-skill/references/init.md", ("`--detect-only`", "`--dry-run`")),
    ("src/skf-export-skill/references/load-skill.md", ("`--dry-run`",)),
])
def test_read_only_modes_never_migrate(rel, flags):
    rung = _flat_rung(_read(rel))
    for flag in flags:
        assert flag in rung
    assert "do not migrate" in rung
    assert "except the flat-to-versioned migration" in _read(rel)


def test_export_dry_run_reads_the_flat_package_in_place():
    """Every later export step reads {resolved_skill_package}, with flat fallbacks."""
    rung = _flat_rung(_read("src/skf-export-skill/references/load-skill.md"))
    assert "use the flat folder as the resolved path" in rung and "would migrate" in rung


def test_update_read_only_modes_halt_on_a_flat_skill():
    """Update's later steps read {forge_version}, which a flat skill does not have yet."""
    text = _read("src/skf-update-skill/references/init.md")
    rung = _flat_rung(text)
    assert "do not migrate and HALT" in rung
    assert "use the flat folder as the resolved path" not in rung
    assert 'status: "blocked"' in rung and 'phase: "init:read-only-flat-layout"' in rung
    assert "run once without --detect-only or --dry-run" in rung
    assert rung.index("do not migrate and HALT") < rung.index("migration rules")
    assert text.index(rung) < text.index("### 1b. Concurrency Guard")


def test_update_gate_runs_before_the_lock_and_emits_blocked():
    text = _read("src/skf-update-skill/references/init.md")
    rung = _flat_rung(text)
    assert 'status: "blocked"' in rung and 'phase: "init:ownership-gate"' in rung
    assert text.index(rung) < text.index("### 1b. Concurrency Guard")


def test_export_discovery_keeps_only_skf_skills():
    text = _read("src/skf-export-skill/references/load-skill.md")
    discovery = _section(text, "**Skill Path Discovery", "**Flag Parsing:**")
    assert "`skf_skill` is true" in discovery
    assert "`flat_skf` is true or `active_version` is not null" in discovery, (
        "a flat SKF skill can have no active_version; filtering on it alone drops the skill silently")
    assert "Skipped (not SKF output)" in discovery
    assert "`{not_skf_output}` ← `not_skf_output`" in discovery
    assert "skip the flat path" in discovery, "without the helper, no flat folder is discovered"
    halt = _section(_read("src/skf-export-skill/references/multi-skill-mode.md"), "## Halt semantics", None)
    assert "not-skf-output" in halt


@pytest.mark.parametrize("rel", [DROP_SELECT, RENAME_SELECT])
def test_drop_and_rename_bind_ownership_and_never_scan_top_level(rel):
    text = _read(rel)
    assert "`{target_ownership}` ← " in text
    assert "`{target_foreign_entries}` ← " in text
    assert "`skf_skill` is true" in text
    assert "Not offered — not SKF output" in text
    assert "top-level directories" not in text, "the in-prompt fallback must not offer unchecked folders"


def test_drop_forced_purge_is_guarded():
    text = _read(DROP_SELECT)
    ask_mode = _section(text, "### 8. Ask Mode", "### 8b. Purge Guard")
    draft = _section(ask_mode, "**If `target_in_manifest = false`:**", "**If `target_in_manifest = true`:**")
    for needle in ('"input-invalid"', '"input-missing"', "{forbidPurgeInHeadless}", "apply §8b",
                   "On-Activation guard"):
        assert needle in draft, needle
    # A headless purge of a draft is reached only with mode=purge or default_mode purge, which the
    # On-Activation guard already checks, so a second forbid HALT here could never run.
    assert '"headless-purge-forbidden"' not in draft
    assert "when `{headless_mode}` is true, no `mode` argument while `{defaultMode}` is `\"deprecate\"`" in draft, (
        "an interactive run confirms the forced purge at §10; only headless refuses a deprecate default")
    assert "leave out **[P]**" in ask_mode


def test_drop_contract_describes_the_draft_purge_guard():
    text = _read(DROP_SKILL)
    exit_6 = next(line for line in text.splitlines() if line.startswith("| 6 "))
    assert "§8" not in exit_6, "select.md §8 no longer raises headless-purge-forbidden"
    assert "cannot see the purge" not in text
    assert "cannot be deprecated" in _section(text, "## On Activation", None)


def test_drop_purge_guard_needs_skf_ownership():
    guard = _section(_read(DROP_SELECT), "### 8b. Purge Guard", "### 9. Compute Affected Directories")
    assert "`{target_ownership}`" in guard and "`{target_foreign_entries}`" in guard
    assert '`"skf"` or `"absent"`: the purge proceeds' in guard
    assert '`"foreign"` or `"unknown"`: refuse every purge' in guard
    assert "with or without a trailing `/`" in guard, "a linked version folder is listed without the slash"
    assert "`{target_errors}`" in guard
    assert 'halt_reason: "not-skf-output"' in guard
    stored = _section(_read(DROP_SELECT), "### 11. Store Decisions in Context", "### 12.")
    assert "`target_ownership`" in stored


def test_drop_purge_never_deletes_through_a_link():
    delete = _section(_read(DROP_EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. Verify Final State")
    assert "Remove any trailing `/`" in delete
    assert "SKF never deletes through a link" in delete
    assert "without a trailing `/`" in delete


def test_orphan_row_gate_never_sends_external_skills_to_export():
    text = _read("src/skf-export-skill/references/orphan-row-detection.md")
    assert "against each external skill" not in text
    assert "Run export-skill against each to migrate" not in text
    assert "each of these skills that SKF generated" in text
    assert "Run export-skill on each skill SKF generated" in text


def test_drop_refuses_a_named_folder_skf_did_not_generate():
    ask = _section(_read(DROP_SELECT), "### 4. Ask Which Skill", "### 5. Display Version Details")
    assert "`{not_offered}`" in ask and 'halt_reason: "not-skf-output"' in ask


def test_drop_names_a_foreign_folder_before_the_empty_roster_halt():
    """A module repo with no SKF skill: a named foreign folder is not-skf-output, not nothing-to-drop."""
    roster = _section(_read(DROP_SELECT), "### 3. List Available Skills", "### 4. Ask Which Skill")
    empty = _section(roster, "**If the combined roster is empty**", "Display the combined list")
    refusal = empty.index("is in `{not_offered}`")
    assert refusal < empty.index('"nothing-to-drop"')
    assert 'halt_reason: "not-skf-output"' in empty[refusal:empty.index('"nothing-to-drop"')]
    assert "exit code 5" in empty and 'skill: "{name}"' in empty and "in either mode" in empty
    assert "Left untouched (not SKF output): {not_offered}" in empty


def test_rename_names_a_foreign_folder_before_the_empty_list_halt():
    roster = _section(_read(RENAME_SELECT), "### 3. List Available Skills", "### 4. Ask Which Skill")
    empty = _section(roster, "**If the list to display is empty**", "Display the list")
    assert "`skf_skill` is true" in empty, "the halt must match the filtered list"
    refusal = empty.index("is in `{not_skf_output}`")
    assert refusal < empty.index('"nothing-to-rename"')
    assert "§4a refusal" in empty and "in either mode" in empty
    assert 'old_name: "{old_name}"' in empty
    assert "Left untouched (not SKF output): {not_skf_output}" in empty


def test_drop_version_purge_refuses_foreign_entries_inside_the_version():
    guard = _section(_read(DROP_SELECT), "### 8b. Purge Guard", "### 9. Compute Affected Directories")
    assert "or an entry inside it (`{version}/<entry>`)" in guard
    assert "it also holds entries SKF did not generate" in guard


def test_rename_ownership_check_precedes_the_lock():
    text = _read(RENAME_SELECT)
    check = _section(text, "### 4a. Ownership Check", "### 4b. Concurrency Guard")
    assert "`not-skf-output`" in check and "`flat-layout`" in check
    assert "`{target_flat_skf}` ← `flat_skf`" in check
    assert "`{target_errors}` ← `errors`" in check, "a link is not a missing marker"
    assert "without `{skillInventoryHelper}`" in check, "a missing helper must fail closed"
    ask = _section(text, "### 4. Ask Which Skill", "### 4a. Ownership Check")
    assert 'halt_reason: "input-invalid"' in ask, "a headless no-match must halt, not re-prompt"


def test_rename_treats_verifier_exit_2_as_unclean():
    verify = _section(_read(RENAME_EXECUTE), "### 5. Verify", "### 6. Update Export Manifest")
    assert "exit code of 2 with no JSON" in verify and "rollback" in verify


def test_rename_recreates_active_with_flip_link():
    """§4 recreates `active` with the atomic-write helper's flip-link, the call the writers use."""
    execute = _read(RENAME_EXECUTE)
    # skf-update-active-symlink.py has no flip-link, and rename no longer calls it.
    assert "updateActiveSymlink" not in execute
    resolve = _section(execute, "### 0. Re-read", "### 1. ")
    assert "`{atomicWriteHelper}` ← first existing path in `{atomicWriteProbeOrder}` (used in §4" in resolve
    copy = _section(execute, "### 1. Copy skill_group and forge_group", "### 2. ")
    assert "the copy follows no link;" not in copy
    assert "§4 creates `{new_skill_group}/active` again either way" in copy
    fix = _section(execute, "### 4. Fix the `active` Symlink", "### 5. Verify")
    assert ('uv run {atomicWriteHelper} flip-link \\\n'
            '     --link "{new_skill_group}/active" \\\n'
            '     --target "{target_version}"') in fix
    assert 'basename "$(readlink "{old_skill_group}/active")"' in fix, "an absolute or ../ link points into the old group"
    assert ('   readlink "{old_skill_group}/active"\n'
            '   basename "$(readlink "{old_skill_group}/active")"') in fix, "step 3's fence yields both values it names"
    assert "`{old_active_link}` to what the first line prints" in fix
    assert "`{target_version}` to what the second line prints" in fix
    # The shell tests that pick each branch, verbatim: `[ ! -e ]` alone skips a broken link,
    # and `[ -d ]` follows the link, so it would refuse every skill that has one.
    assert ('If nothing is at `{old_skill_group}/active`, not even a broken link '
            '(`[ ! -e "{old_skill_group}/active" ] && [ ! -L "{old_skill_group}/active" ]`), skip') in fix
    assert 'If `{old_skill_group}/active` is not a link (`[ ! -L "{old_skill_group}/active" ]`), take the rollback' in fix, \
        "a real active folder is refused, never carried over"
    assert "`{target_version}` is not one of `renamed_versions`" in fix, "a broken link is refused, not copied"
    rollback = _section(fix, "**Rollback on a failure in step 2, 4 or 6:**", "Report:")
    assert "- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true" in rollback
    assert '- Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`' in rollback
    assert 'then rm -f "{new_skill_group}/active"' in fix, "a link is removed as a link, never followed"
    assert 'elif [ -e "{new_skill_group}/active" ]; then rm -rf "{new_skill_group}/active"' in fix
    assert "bind `{active_link_kind}` ← `kind`" in fix and "bind `{flip_error}` ← `message`" in fix
    assert "active.skf-lock" in fix and "mklink /J" in fix
    for stale in ("active.lock", "flock", "four cases", "no silent fallback", "{captured stderr}", "python3"):
        assert stale not in fix, stale
    assert fix.count('halt_reason: "write-failed"') == 1
    assert "§3 + §6" not in execute.split("\n---\n", 1)[0]
    drop = _read(DROP_EXECUTE).split("\n---\n", 1)[0]
    assert "skf-rename-skill/references/execute.md" not in drop, "rename no longer uses the symlink helper"
    assert "records the manual repair and continues" in drop, "drop §4 records a missing helper, it does not halt"


def test_rename_restores_the_manifest_with_write_target():
    manifest = _section(_read(RENAME_EXECUTE), "### 6. Update Export Manifest", "### 7. ")
    assert ("uv run {atomicWriteHelper} write --target \"{skills_output_folder}/.export-manifest.json\" "
            "<<'SKF_MANIFEST_BACKUP'") in manifest
    assert "hold its exact text, not a parsed or re-serialized copy" in manifest
    assert "bind `{manifest_error}` ← `error`" in manifest, "manifest-ops reports its errors on stdout"
    assert "`{manifest_status}` ← `status`" in manifest
    assert "when `{manifest_status}` is `not_found`, set `{manifest_error}`" in manifest, "not_found has no `error`"
    for state in ("`unchanged`", "`restored`", "`restore-failed`"):
        assert state in manifest, state
    # Restore only the state this run's re-key leaves; with both names present the helper
    # refused and wrote nothing, and a restore would erase another process's entry.
    rollback = _section(manifest, "**Rollback on helper non-zero exit:**", "Set context flag")
    assert ("Only when `exports.{new_name}` is there and `exports.{old_name}` is gone, restore the backup"
            in rollback), "restore only a landed re-key"
    assert ("In every other state (`exports.{old_name}` still there, `exports.{new_name}` absent, or a manifest "
            "that is missing or does not parse), this run did not change the manifest") in rollback
    assert "set `{manifest_restore}` to `unchanged` and write nothing" in rollback
    assert rollback.index("Only when `exports.{new_name}` is there") < rollback.index("write --target")
    assert "Otherwise restore the backup" not in rollback
    assert "- `rm -rf {new_skill_group}`, plus `rm -rf {new_forge_group}` when `{forge_move}` is true" in rollback
    assert '- Release the lock: `rm -f "{forge_data_folder}/.skf-rename-{old_name}.lock"`' in rollback
    assert 'uv run {manifestOpsHelper} "{skills_output_folder}" rename {new_name} {old_name}' in manifest
    assert "Restored manifest from backup and rolled back" not in manifest, "say what the rollback did"
    assert "section 7 on failure" not in manifest, "§7 never rolls back"
    assert "{captured stderr}" not in manifest


@pytest.mark.parametrize("rel", sorted(CONTRACT_FILES))
def test_contract_files_list_the_reasons(rel):
    text = _read(rel)
    for reason in CONTRACT_FILES[rel]:
        assert reason in text, f"{rel} must list {reason}"


def test_version_paths_migration_names_the_gate():
    text = _read("src/knowledge/version-paths.md")
    migration = _section(text, "## Migration: Flat to Versioned", "## Anti-Patterns")
    for needle in ("Ownership gate", "flat_skf", "generated_by", "tool_versions", "skill_type",
                   "not-skf-output", "--dry-run", "--detect-only", "`1.0.0`", "stays where it is",
                   "init:read-only-flat-layout"):
        assert needle in migration, needle
    assert "update-skill `--dry-run` or `--detect-only`, or export-skill `--dry-run`, the workflow " \
        "reads the flat package in place" not in migration
    ownership = _section(text, "## Ownership", "## Skill Management Operations")
    for field in ("`ownership`", "`skf_skill`", "`flat_skf`", "`foreign_entries`", "`not_skf_output`"):
        assert field in ownership, field
    assert "DS never lists" not in ownership, "DS lists every manifest skill; only a purge needs ownership"
    assert "Setup's ccc exclusions use the same rule" in ownership
    assert "`{version}/<entry>`" in ownership
    assert "only when the manifest lists it" in ownership


REFUSAL_SITES = sorted(MIGRATE_SITES) + [DROP_SELECT, RENAME_SELECT] + sorted(WRITER_SITES)


@pytest.mark.parametrize("rel", REFUSAL_SITES + ["src/knowledge/version-paths.md"])
def test_refusal_remedy_supports_a_shared_skills_folder(rel):
    """A shared skills folder is supported: relocate only a folder holding a module's own source."""
    text = _read(rel)
    assert "folder only SKF uses" not in text
    assert "as the setting to change" not in text
    assert "SKF leaves the skills it did not generate alone" in text
    assert "module's own source" in text


@pytest.mark.parametrize("rel", REFUSAL_SITES)
def test_refusal_remedy_names_the_skill_to_manage(rel):
    text = _read(rel)
    assert re.search(r"so manage `\{[a-z_-]+\}` yourself", text), rel


def test_troubleshooting_entry_matches_the_gate_scope():
    entry = _section(_read("docs/troubleshooting.md"), '### "`<name>` is not SKF output"', "### My campaign")
    assert "folder only SKF uses" not in entry
    assert "SKF leaves the skills it did not generate alone" in entry
    assert "only writes into, migrates, renames or purges" in entry
    assert "updates, renames or deletes" not in entry
    assert "module's own source" in entry
    assert "forge_data_folder" in entry, "drop and rename also check the skill's forge folder"
    assert "Left in place (not SKF output)" in entry
    assert "then rename it" not in entry, "the flat-layout remedy covers the writers too"
    assert "then re-run the workflow that stopped" in entry


def test_analyze_source_merges_only_skf_skills():
    text = _read("src/skf-analyze-source/references/step-auto-scope.md")
    assert '"skf_skill": true | false' in text
    merge = _section(text, "- **[M]erge:**", "- **[S]kip:**")
    assert "`matches[].skf_skill` is true" in merge


@pytest.mark.parametrize("rel", sorted(WRITER_SITES))
def test_writer_sites_check_ownership_before_writing(rel):
    text = _read(rel)
    frontmatter = text.split("\n---\n", 1)[0] + "\n"
    assert PROBE_ORDER in frontmatter, "installed path first, then the src/ path"
    for needle in ("--write-check", "--forge-data-folder {forge_data_folder}", "--write-version {version}",
                   "`{write_verdict}` ← `write_check.verdict`", "`{write_folder}` ← `write_check.folder`",
                   "`{write_detail}` ← `write_check.detail`",
                   "no helper candidate resolves", "not even a broken link", "no `write_check`",
                   'halt_reason: "not-skf-output"', 'halt_reason: "flat-layout"'):
        assert needle in text, needle
    # An older helper has no --write-check and answers a new skill with SKILL_NOT_FOUND:
    # its error must never reach the user without the re-install hint.
    assert "`SKILL_NOT_FOUND`" in text
    assert "re-install SKF if the installed `skf-skill-inventory.py` is out of date" in text
    gate = "**Pre-flight: ownership, phase 2.**" if rel == SS_GENERATE else "**Ownership check.**"
    for marker in WRITER_SITES[rel]:
        assert marker in text, marker
        assert text.index(gate) < text.index(marker), f"the write check must come before {marker!r}"


def test_writer_ownership_halt_writes_nothing_on_disk():
    contract = _read(QS_HALT_CONTRACT)
    assert "except the step 5 §1 ownership halt" in contract
    # A package holding only result files would read as foreign to the next run.
    assert "when `{skill_package}/metadata.json` exists" in contract
    assert "A HALT while `{skill_package}` has no `metadata.json`" in contract
    assert "When `metadata.json` itself failed to write" in _read(QS_WRITE)
    assert "once the skill package holds `metadata.json`" in _read("docs/workflows.md")
    exit_codes = _section(contract, "## Exit Codes", "## Result Contract")
    assert "state-conflict" in _row(exit_codes, "| 9 ")
    assert "writes no result file" in _read(QS_WRITE)
    halt = _section(_read(CS_REPORT), "### Result Contract on HARD HALT", "### 6.")
    assert "the §1 ownership refusal" in halt and "writes no result file" in halt
    assert '`uv run {atomicWriteHelper} write --target "{forge_version}/create-skill-result-latest.json"`' in halt
    assert "ownership halt" in _read("src/skf-quick-skill/references/batch-mode.md")
    assert '"exit_code":5,"halt_reason":"not-skf-output"' in _read(SS_GENERATE)


def test_create_skill_gate_uses_the_working_version():
    text = _read(CS_GENERATE)
    for stale in ("Resolve `{version}` from the skill brief's `version` field",
                  "the semver version from the brief", "overwrites existing files)"):
        assert stale not in text, stale
    first = _section(text, "### 1. Check Ownership", "### 2. ")
    assert "`{version}` is the working version" in first


@pytest.mark.parametrize("rel", [CS_GENERATE, QS_WRITE])
def test_writers_write_metadata_first(rel):
    deliverables = _section(_read(rel), "### 2. Write Deliverables", "### 3. ")
    assert "Write File 3 (`metadata.json`) first" in deliverables


def test_create_skill_batch_advances_past_a_refused_brief():
    first = _section(_read(CS_GENERATE), "### 1. Check Ownership", "### 2. ")
    assert "`refused`" in first and "`current_index` set to the next brief" in first
    batch = _section(_read(CS_REPORT), "### 5. Batch Mode Status", "### Result Contract")
    assert "refused" in batch


def test_stack_gate_runs_in_two_phases():
    text = _read(SS_GENERATE)
    assert "{skills_output_folder}/{project_name}-stack/active/{project_name}-stack/metadata.json" not in text, (
        "prior stack metadata is read only from a version SKF generated")
    assert "`{prior_active_version}` ← `write_check.marked_active_version`" in text
    phase_1 = text.index("--skill {stack_name} --write-check --forge-data-folder")
    assert phase_1 < text.index("{stack_name}/{prior_active_version}/{stack_name}/metadata.json")
    assert phase_1 < text.index("capture its `version` as `{prior_stack_version}`")
    assert text.index("**Pre-flight: ownership, phase 2.**") < text.index("stage-dir --target {skill_package}")
    exit_codes = _section(_read(SS_SKILL), "## Exit Codes", "## Result Contract")
    assert "state-conflict" in _row(exit_codes, "| 5 ")


@pytest.mark.parametrize("rel", WRITER_SKILLS)
def test_writer_skills_carry_the_ownership_rule(rel):
    assert "Never write into a skill folder SKF did not generate" in _read(rel)


def test_stack_skill_never_decides_ownership_by_hand():
    assert "never decide by hand whether SKF generated a folder" in _read(SS_SKILL)


def test_drop_checks_the_forge_folder_before_any_change():
    text = _read(DROP_SELECT)
    roster = _section(text, "### 3. List Available Skills", "### 4. Ask Which Skill")
    assert "uv run {skillInventoryHelper} {skills_output_folder} --forge-data-folder {forge_data_folder}" in roster
    assert "`{target_forge_ownership}` to `\"unknown\"`" in roster, "a missing helper must refuse the purge"
    ask = _section(text, "### 4. Ask Which Skill", "### 5. Display Version Details")
    assert "`{target_forge_ownership}` ← " in ask and "`{same_folder}` ← `same_folder`" in ask
    guard = _section(text, "### 8b. Purge Guard", "### 9. Compute Affected Directories")
    forge = _section(guard, "**Forge folder.**", None)
    for needle in ('`"mixed"`', '`"foreign"` or `"reserved"`', "leaves the forge folder where it is",
                   "does not report `forge_groups`", "`{version}/<entry>`", "`{forge_left_in_place}`",
                   "When `{same_folder}` is true"):
        assert needle in forge, needle
    affected = _section(text, "### 9. Compute Affected Directories", "#### 9b.")
    assert "/{target_skill}/`" not in affected and "/{version}/`" not in affected, "no trailing `/` on a path"
    assert "without a trailing `/`" in affected
    assert "Left in place (not SKF output)" in _section(text, "### 10. Confirmation Gate", "### 11. ")
    assert "Left in place (not SKF output)" in _read(DROP_REPORT)
    stored = _section(text, "### 11. Store Decisions in Context", "### 12.")
    assert "`forge_left_in_place`" in stored and "`target_forge_ownership`" in stored
    delete = _section(_read(DROP_EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. Verify Final State")
    assert "when `affected_directories` lists it" in delete


def test_rename_checks_the_forge_folder_before_the_lock():
    text = _read(RENAME_SELECT)
    roster = _section(text, "### 3. List Available Skills", "### 4. Ask Which Skill")
    assert "uv run {skillInventoryHelper} {skills_output_folder} --forge-data-folder {forge_data_folder}" in roster
    check = _section(text, "### 4a. Ownership Check", "### 4b. Concurrency Guard")
    for needle in ("`{target_forge_ownership}` ← ", "`{same_folder}` ← `same_folder`", "`{forge_move}`",
                   "SKF never moves or deletes through a link", "does not report `forge_groups`",
                   "When `{target_forge_errors}` names a link", "a folder SKF can read"):
        assert needle in check, needle
    lock = _section(text, "### 4b. Concurrency Guard", "### 5. Ask for New Name")
    assert "LOCK={forge_data_folder}/.skf-rename-{old_name}.lock" in lock
    assert 'mkdir -p "{forge_data_folder}"' in lock


def test_rename_lock_never_sits_in_a_forge_folder():
    for path in sorted((SRC / "skf-rename-skill").rglob("*.md")):
        assert "{old_name}/.skf-rename.lock" not in path.read_text(encoding="utf-8"), path
    assert "$(dirname" not in _read(RENAME_SELECT)


def test_rename_moves_only_an_skf_forge_folder():
    text = _read(RENAME_SELECT)
    for start, end in (("### 7. Enumerate Affected Versions", "### 8. Confirmation Gate"),
                       ("### 9. Store Decisions in Context", "### 10. ")):
        paths = _section(text, start, end)
        assert "{old_name}/`" not in paths and "{new_name}/`" not in paths, start
    execute = _read(RENAME_EXECUTE)
    copy = _section(execute, "### 1. Copy skill_group and forge_group", "### 2. ")
    assert "Only when `{forge_move}` is true" in copy and "without a trailing `/`" in copy
    assert "whatever the copy created at `{new_forge_group}`" in copy
    for line in execute.splitlines():
        if "rm -rf {new_forge_group}" in line:
            assert "{forge_move}" in line, line
    delete = _section(execute, "### 8. Delete Old Directories", "### 9. ")
    assert "SKF never deletes through a link" in delete and "Only when `{forge_move}` is true" in delete
    update = _section(execute, "### 3. Update File Contents", "### 4. ")
    assert "context-snippet.md, provenance-map.json.\"" not in update, "name only the files rewritten"
    assert "{if forge_move or same_folder: ', provenance-map.json'}" in update
    assert "`same_folder` — carried from step 1" in _section(execute, "### 9. Store Results", "### 10. ")
    assert "provenance-map.json when `forge_move` or `same_folder`" in _read("src/skf-rename-skill/references/report.md")


def test_rename_verifies_only_the_versions_it_renamed():
    """A version folder with no package (an interrupted run's empty folder) never fails the commit gate."""
    execute = _read(RENAME_EXECUTE)
    inner = _section(execute, "### 2. Rename Inner Version Directories", "### 3. ")
    assert "`renamed_versions`" in inner
    verify = _section(execute, "### 5. Verify", "### 6. ")
    assert "--versions {comma-separated renamed_versions}" in verify
    assert "--versions {comma-separated affected_versions}" not in verify


def test_rename_recovery_deletes_only_a_copy():
    ask = _section(_read(RENAME_SELECT), "### 5. Ask for New Name", "### 6. Source Authority Check")
    assert "only when it holds a copy of" in ask
    assert "rm -rf {skills_output_folder}/{new_name} {forge_data_folder}/{new_name}" not in ask
    assert "**Reserved name.**" in ask
    assert "holding nothing a copy of it could not" in ask, "the fallback fingerprint needs a copy"


def test_getting_started_ownership_sentence():
    [line] = [line for line in _read("docs/getting-started.md").splitlines()
              if "Workflows also write into, move, rename or delete only the skill folders SKF generated" in line]
    assert "`forge_data_folder`" in line


def test_ccc_bridge_names_the_forge_rule():
    text = _read("src/knowledge/ccc-bridge.md")
    assert "before they write into, move or delete a skill" in text
    assert "a file `.gitignore` hides still counts" in text


def test_workflows_doc_quick_skill_codes():
    text = _read("docs/workflows.md")
    assert re.search(r"\|\s*8\s*\|\s*ecosystem-redirect", text)
    assert re.search(r"\|\s*9\s*\|\s*state-conflict", text)
    assert "references/halt-contract.md" in text
    assert "except the exit `9` ownership halt" in text


def test_version_paths_names_writers_and_forge_folders():
    text = _read("src/knowledge/version-paths.md")
    writing = _section(text, "### Writing Workflows", "### Reading Workflows")
    assert "Ownership check (CS, QS, SS)" in writing and "--write-check" in writing
    assert writing.index("Ownership check (CS, QS, SS)") < writing.index("1. Create `{skill_group}` if it does not exist")
    ownership = _section(text, "## Ownership", "## Skill Management Operations")
    for needle in ("`forge_groups`", '`"reserved"`', '`"empty"`', "`same_folder: true`",
                   "Setup's ccc exclusions use the same evidence rule for the forge folder"):
        assert needle in ownership, needle
    spec = importlib.util.spec_from_file_location("skf_skill_inventory_pins", INVENTORY_PY)
    inventory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inventory)
    tree = _section(text, "### forge_data_folder\n", "## Version Resolution")
    for name in sorted(inventory.FORGE_VERSION_FILES) + ["test-report-", "drift-report-", "-result-", ".skf-rename-"]:
        assert name in tree, f"the forge tree must name {name!r}"


STACK_ROSTER_SITES = {
    "src/skf-verify-stack/references/init.md": (),
    "src/skf-refine-architecture/references/init.md": ("`{pairs}` ← `pairs`",),
}


@pytest.mark.parametrize("rel", sorted(STACK_ROSTER_SITES))
def test_stack_rosters_read_only_skf_output(rel):
    text = _read(rel)
    assert "uv run {enumerateStackSkillsHelper}" in text
    assert "python3 {enumerateStackSkillsHelper}" not in text
    bindings = ("`{not_skf_output}` ← `not_skf_output`", "`{inventory_reliable}` ← `inventory_reliable`",
                "`{warning_count}` ← `warning_count`", "`{skill_count}` ← `skill_count`",
                "`{inventory_warnings}` ← `warnings`") + STACK_ROSTER_SITES[rel]
    for binding in bindings:
        assert binding in text, binding
    assert "Skipped (not SKF output): {not_skf_output}" in text
    # The helper never reads the manifest or emits these fields and warnings.
    for stale in ("export-manifest →", "`skill_name`, `version`, `language`", "non-symlink `active`",
                  "orphan-versions", "maps `confidence_tier`", "{warning_count}/{skill_count + warning_count}",
                  "{exports_documented}", "| {skill_name} | {language}"):
        assert stale not in text, stale
    # The halt counts warnings as warnings; the helper-less fallback applies the marker rule
    # and binds the counts and warnings the halt, §3 and §5 read.
    for needle in ("warning(s) across {skill_count}", "without counting a warning", "`generated_by`",
                   "`tool_versions`", "`individual`", "{exports_source}", "{confidence}"):
        assert needle in text, needle
    fallback = _section(text, "**Fallback path", "### 3.")
    assert "bind `{skill_count}` to the number of skills found" in fallback
    assert "`{warning_count}` to the number of warnings counted" in fallback
    assert "`{inventory_warnings}` to those warnings" in fallback


def test_compose_mode_reads_only_confirmed_skf_skills():
    detect = _read("src/skf-create-stack-skill/references/detect-manifests.md")
    assert "(`skill`, `stack`" not in detect, "SKF writes skill_type single, never skill"
    # Explicitly named skills pass the same roster gate as discovered ones.
    assert "Use the explicit dependency list directly" not in detect
    assert "when `explicit_deps` was provided in step 01, each name in it is a candidate" in detect
    assert "a name from `explicit_deps` is excluded with" in detect
    for needle in ("`{stack_roster}` ← `skills`", "`{not_skf_output}` ← `not_skf_output`",
                   "`single` or `individual`", "not SKF output — excluding",
                   "`skill_package_path` ← `{skills_output_folder}/{path}`", "one resolution"):
        assert needle in detect, needle
    extract = _read("src/skf-create-stack-skill/references/parallel-extract.md")
    for needle in ('"not_skf_output"', "Build a `per_library_extractions[]` entry for each confirmed skill",
                   "that name a confirmed skill", "If `cycles[]` names a confirmed skill",
                   "no longer an SKF skill package"):
        assert needle in extract, needle
    for stale in ("via the export-manifest (or symlink fallback)", "null when exports came from references/",
                  "Append every entry in `warnings[]`"):
        assert stale not in extract, stale


def test_test_skill_catalog_counts_folders_that_hold_a_skill():
    text = _read("src/skf-test-skill/references/report.md")
    frontmatter = text.split("\n---\n", 1)[0] + "\n"
    assert PROBE_ORDER in frontmatter, "installed path first, then the src/ path"
    discovery = _section(text, "### 4b. Discovery Testing", "### 4c.")
    assert "ls -1d" not in discovery and "wc -l" not in discovery, "no POSIX-only pipeline, and _batch holds no skill"
    for needle in ("`has_skill_md`", "`{not_skf_output}` ← `not_skf_output`", "`{discovery_catalog}`"):
        assert needle in discovery, needle
    spawn = _section(discovery, "**4b.2 Spawn a discovery subagent:**", "**4b.3")
    assert "`{discovery_catalog}`" in spawn and "the same set §4b.0 counted" in spawn


def test_version_paths_names_the_roster_rule():
    text = _read("src/knowledge/version-paths.md")
    ownership = _section(text, "## Ownership", "## Skill Management Operations")
    assert "VS, RA and SS compose-mode read only the skills SKF generated" in ownership
    assert "a folder whose `metadata.json` it cannot read is named in one warning instead" in ownership
    assert "### Reading Workflows (EX, AS, TS)" in text


def test_workflows_docs_name_the_stack_roster_rule():
    text = _read("docs/workflows.md")
    assert text.count("**Skills read:** Only the skills SKF generated.") == 2, "VS and RA"
    assert text.count("A `metadata.json` SKF cannot read still counts as one warning") == 2
    assert "Compose-mode loads only the skills SKF generated." in text


def test_troubleshooting_explains_inventory_unreliable():
    text = _read("docs/troubleshooting.md")
    heading = '### "Inventory scan unreliable"'
    not_skf = '### "`<name>` is not SKF output"'
    assert heading in text and text.index(heading) < text.index(not_skf)
    entry = _section(text, not_skf, "### My campaign")
    assert "Skipped (not SKF output)" in entry
    unreliable = _section(text, heading, not_skf)
    # A metadata.json SKF cannot read counts even on a skill another tool made.
    assert "counts whoever made the skill" in unreliable
    # Update Skill stops at "no changes" when the source is unchanged, so it
    # cannot restore missing exports; the workflow that made the skill can.
    assert "`@Ferris CS <name>`" in unreliable and "@Ferris US" not in unreliable


def test_quick_skill_writes_the_error_result_only_beside_metadata():
    """SKILL.md must not promise a `-latest.json` at the ownership halt, which writes nothing."""
    text = _read("src/skf-quick-skill/SKILL.md")
    assert "the on-disk `-latest.json` write once `{skill_package}` is known" not in text
    assert ("the on-disk `-latest.json` write once `{skill_package}` holds `metadata.json` "
            "(never at the step 5 §1 ownership halt)") in text


RENAME_FORGE_REFUSAL = "is a link, is not a folder, or cannot be listed"
# Each surface that states rename's forge-folder refusal: how often it states
# it, and the narrower wording (links only) it must no longer use.
RENAME_FORGE_SURFACES = {
    "src/knowledge/version-paths.md": (2, ('refuses one that is `"mixed"` or a link',
                                           "entries SKF did not write or is a link.")),
    "src/skf-rename-skill/SKILL.md": (1, ("also holds other files or is a link,",)),
    "src/skf-rename-skill/references/exit-codes.md": (1, ("or a linked forge folder",)),
    "docs/workflows.md": (2, ("also holds other files or is a link",)),
    "docs/troubleshooting.md": (1, ("(rename also refuses one that is a link)",)),
}


@pytest.mark.parametrize("rel", sorted(RENAME_FORGE_SURFACES))
def test_rename_forge_refusal_matches_select(rel):
    """select.md §4a refuses a forge path with `errors` (a link, a non-folder or an unlistable one)."""
    rule = _section(_read(RENAME_SELECT), "6. `{target_forge_errors}` is non-empty", "7. ")
    assert "the path is not a folder, or SKF cannot list it" in rule
    count, stale = RENAME_FORGE_SURFACES[rel]
    text = _read(rel)
    assert text.count(RENAME_FORGE_REFUSAL) == count, rel
    for phrase in stale:
        assert phrase not in text, phrase


def test_rename_forge_refusal_docs_name_the_remedy():
    row = _row(_read("src/knowledge/version-paths.md"), '| `"foreign"` |')
    assert "SKF cannot list it" in row
    entry = _section(_read("docs/troubleshooting.md"), '### "`<name>` is not SKF output"', "### My campaign")
    assert "for a path that is not a folder or cannot be listed, move it out of the way or fix its permissions" in entry


CS_COMPILE = "src/skf-create-skill/references/compile.md"
CS_STAGING = "_bmad-output/.skf-stage/{skill-name}/"
CS_STAGING_READERS = (
    "src/skf-create-skill/references/validate.md",
    "src/skf-create-skill/references/step-doc-sources.md",
    "src/skf-create-skill/references/step-doc-rot.md",
    "src/shared/health-check.md",
)


def test_create_skill_stages_outside_every_folder_setting():
    """A skills or forge folder set to `_bmad-output` must never be create-skill's staging folder."""
    for root in (SRC, REPO / "docs"):
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in {".md", ".py", ".yaml", ".json", ".csv", ".txt"}:
                assert "_bmad-output/{skill-name}/" not in path.read_text(encoding="utf-8"), path
    text = _read(CS_COMPILE)
    rules = _section(text, "## Rules", "## MANDATORY SEQUENCE")
    assert f"staging directory `{CS_STAGING}`" in rules
    create = _section(text, "### 1a. Create Staging Directory", "### 1b.")
    assert f"Create `{CS_STAGING}` (and `{CS_STAGING}references/`)" in create
    assert "never collides with a `skills_output_folder` or `forge_data_folder` set to `_bmad-output`" in create
    assert f"staging directory `{CS_STAGING}`" in _section(text, "### 8. Auto-Proceed", None)
    # skill-check's frontmatter.name_matches_directory reads the last folder.
    assert f"`<staging-skill-dir>` resolves to `{CS_STAGING}`" in _read(CS_STAGING_READERS[0])
    for rel in CS_STAGING_READERS:
        assert CS_STAGING in _read(rel), rel
    assert "leftovers" in _section(_read("docs/troubleshooting.md"), '### "`<name>` is not SKF output"', "### My campaign")


def _inventory_module():
    spec = importlib.util.spec_from_file_location("skf_skill_inventory_staging", INVENTORY_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stage(folder: Path) -> None:
    marker = '{"name": "mylib", "generated_by": "create-skill", "skill_type": "single"}'
    (folder / "references").mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: mylib\n---\n", encoding="utf-8")
    (folder / "metadata.json").write_text(marker, encoding="utf-8")
    for name in ("context-snippet.md", "evidence-report.md", "references/api.md"):
        (folder / name).write_text("x\n", encoding="utf-8")
    (folder / "provenance-map.json").write_text("{}", encoding="utf-8")


@pytest.mark.parametrize("setting", ["skills_output_folder", "forge_data_folder"])
def test_staging_never_reads_as_a_skill_or_forge_folder(tmp_path, setting):
    """Stage where compile.md §1a says, with one folder setting at `_bmad-output`."""
    create = _section(_read(CS_COMPILE), "### 1a. Create Staging Directory", "### 1b.")
    staged = re.search(r"Create `(_bmad-output/[^`]*)\{skill-name\}/`", create)
    assert staged, "§1a must name the staging folder"
    _stage(tmp_path / (staged.group(1) + "mylib"))
    inventory = _inventory_module()
    bmad_output = tmp_path / "_bmad-output"
    if setting == "skills_output_folder":
        forge = tmp_path / "forge-data"
        check = inventory.write_check(bmad_output, "mylib", "1.0.0", forge)
        assert check["verdict"] == "ok", check
        scan = inventory.scan_inventory(bmad_output, forge_data_folder=forge)
        assert scan["not_skf_output"] == [], scan["not_skf_output"]
        assert [s["name"] for s in scan["skills"] if s["ownership"] != "skf"] == []
    else:
        package = tmp_path / "skills" / "mylib" / "1.0.0" / "mylib"
        package.mkdir(parents=True)
        (package / "metadata.json").write_text('{"generated_by": "create-skill"}', encoding="utf-8")
        forge_group = bmad_output / "mylib"
        (forge_group / "1.0.0").mkdir(parents=True)
        (forge_group / "skill-brief.yaml").write_text("name: mylib\n", encoding="utf-8")
        (forge_group / "1.0.0" / "provenance-map.json").write_text("{}", encoding="utf-8")
        group = inventory.classify_forge_group(forge_group, "mylib")
        assert (group["ownership"], group["foreign_entries"]) == ("skf", []), group
