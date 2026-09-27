#!/usr/bin/env python3
"""Prose pins for the ownership gate in the step files.

Step prose is not executed by any test, so these checks pin the parts of it
that keep SKF from moving, renaming or deleting a skill it did not generate:
the four flat-layout migrate sites, drop and rename, export discovery,
analyze-source's merge offer, the contract files that list halt reasons, and
the version-paths knowledge. The helper behind the gate is tested in
test-skf-skill-inventory.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"

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
CONTRACT_FILES = {
    "src/skf-drop-skill/references/headless-contract.md": ("not-skf-output",),
    "src/skf-drop-skill/SKILL.md": ("not-skf-output",),
    "src/skf-rename-skill/SKILL.md": ("not-skf-output", "flat-layout"),
    "src/skf-rename-skill/references/exit-codes.md": ("not-skf-output", "flat-layout"),
    "src/skf-export-skill/references/result-envelope.md": ("not-skf-output",),
    "src/skf-export-skill/SKILL.md": ("not-skf-output",),
    "src/skf-audit-skill/SKILL.md": ("not-skf-output",),
    "src/skf-test-skill/SKILL.md": ("not-skf-output",),
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


REFUSAL_SITES = sorted(MIGRATE_SITES) + [DROP_SELECT, RENAME_SELECT]


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
    assert "only migrates, renames or purges" in entry
    assert "updates, renames or deletes" not in entry
    assert "module's own source" in entry


def test_analyze_source_merges_only_skf_skills():
    text = _read("src/skf-analyze-source/references/step-auto-scope.md")
    assert '"skf_skill": true | false' in text
    merge = _section(text, "- **[M]erge:**", "- **[S]kip:**")
    assert "`matches[].skf_skill` is true" in merge
