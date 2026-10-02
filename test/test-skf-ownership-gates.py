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

The lifecycle writers (export, drop and rename) write the managed section
through the same helper calls: the lifecycle tests run each skill's documented
commands and check that the three write byte-identical sections.

The last tests pin rename-skill's run: its run lock through skf-run-lock.py
(the documented calls run as separate processes, as each tool call is), the
halt, dry-run and success envelopes the shared emitter builds from the
payloads the step files pass it (run against the emitter, a halt with no run
folder included, and checked with the schema), the exit-code table against
the schema's map, the counts its report takes from helper results, and the
recovery for a rename that stopped after its manifest re-key.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import shlex
import subprocess
import sys
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
DROP_CONTRACT = "src/skf-drop-skill/references/invocation-contract.md"
CS_GENERATE = "src/skf-create-skill/references/generate-artifacts.md"
CS_REPORT = "src/skf-create-skill/references/report.md"
CS_SKILL = "src/skf-create-skill/SKILL.md"
CS_SCHEMA = "src/shared/scripts/schemas/skf-create-skill-result-envelope.v1.json"
QS_WRITE = "src/skf-quick-skill/references/write-and-validate.md"
QS_HALT_CONTRACT = "src/skf-quick-skill/references/halt-contract.md"
SS_GENERATE = "src/skf-create-stack-skill/references/generate-output.md"
SS_SKILL = "src/skf-create-stack-skill/SKILL.md"
SS_CONTRACT = "src/skf-create-stack-skill/references/invocation-contract.md"
# Each writer step file, with the markers of its first write: the ownership
# check must come before every one of them.
WRITER_SITES = {
    CS_GENERATE: ("promote --stage",),
    QS_WRITE: ("create the skill output directories", "`{skill_package}/metadata.json` exists, confirm with user"),
    SS_GENERATE: ("stage-dir --target {skill_package}", "mkdir -p {forge_version}"),
}
WRITER_SKILLS = ("src/skf-create-skill/SKILL.md", "src/skf-quick-skill/SKILL.md", SS_SKILL)
CONTRACT_FILES = {
    "src/skf-drop-skill/references/invocation-contract.md": ("not-skf-output",),
    "src/skf-rename-skill/references/invocation-contract.md": ("not-skf-output", "flat-layout"),
    "src/skf-rename-skill/references/exit-codes.md": ("not-skf-output", "flat-layout"),
    "src/skf-export-skill/references/result-envelope.md": ("not-skf-output",),
    "src/skf-export-skill/references/invocation-contract.md": ("not-skf-output",),
    "src/skf-audit-skill/references/headless-contract.md": ("not-skf-output",),
    "src/skf-test-skill/references/invocation-contract.md": ("not-skf-output",),
    QS_HALT_CONTRACT: ("not-skf-output", "flat-layout"),
    SS_CONTRACT: ("not-skf-output", "flat-layout"),
    CS_SCHEMA: ("not-skf-output", "flat-layout", "description-angle-brackets"),
}
PROBE_ORDER = (
    "skillInventoryProbeOrder:\n"
    "  - '{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py'\n"
    "  - '{project-root}/src/shared/scripts/skf-skill-inventory.py'\n"
)
# A migrate site whose SKILL.md resolves the inventory helper On Activation,
# which halts before any prompt when it is missing.
ACTIVATION_INVENTORY = {"src/skf-export-skill/references/load-skill.md": "src/skf-export-skill/SKILL.md"}


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
    """The flat-path fallback rung: from its first line to the next numbered step.

    Export's rung opens with its `reason` value, as its other rungs do; the
    other sites open with "If neither".
    """
    start = re.search(r"(?:If neither|`flat-layout`): fall back to the flat path", text)
    assert start, "the flat-path fallback rung is missing"
    rest = text[start.start():]
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
    rung = _flat_rung(text)
    if rel in ACTIVATION_INVENTORY:
        assert ("`{skillInventoryHelper}` ← `{project-root}/_bmad/skf/shared/scripts/skf-skill-inventory.py`, "
                "else `{project-root}/src/shared/scripts/skf-skill-inventory.py`") in _read(ACTIVATION_INVENTORY[rel])
        assert "skillInventoryProbeOrder" not in frontmatter and "no helper candidate" not in rung
    else:
        assert PROBE_ORDER in frontmatter, "installed path first, then the src/ path"
        assert "no helper candidate resolves" in rung, "a missing helper must fail closed"
    binding = "`{group_flat_skf}` ← `skills[0].flat_skf`"
    assert binding in rung
    assert "--skill" in rung
    assert rung.index(binding) < rung.index("migration rules"), "the gate must come before migrating"
    assert 'halt_reason: "not-skf-output"' in rung or '"halt_reason":"not-skf-output"' in rung
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
    # On Activation halts when the helper is missing, so discovery has no scan without it.
    assert "no helper candidate" not in discovery and "skip the flat path" not in discovery
    halt = _section(_read("src/skf-export-skill/references/multi-skill-mode.md"), "## Halt semantics", None)
    assert "not-skf-output" in halt


@pytest.mark.parametrize("rel, flag, key", [
    (DROP_SELECT, "--purge-check", "purge_check"),
    (RENAME_SELECT, "--rename-check", "rename_check"),
])
def test_drop_and_rename_take_the_verdict_from_the_helper_and_never_scan_top_level(rel, flag, key):
    text = _read(rel)
    assert f"{flag} " in text and f"From its `{key}`, bind" in text
    assert "never decide by hand whether SKF generated a folder" in text
    assert f"its result has no `{key}`" in text, "an installed helper older than the flag must fail closed"
    for stale in ("`{target_ownership}` ← ", "`{target_foreign_entries}` ← ", "`{target_forge_ownership}` ← "):
        assert stale not in text, "the helper returns the verdict: the prose no longer joins the scan by hand"
    assert "`skf_skill` is true" in text
    assert "Not offered (not SKF output)" in text
    assert "top-level directories" not in text, "the in-prompt fallback must not offer unchecked folders"
    # The roster lists skills; it never predicts the verdict the check returns once one is picked.
    roster = _section(text, "### 3. List Available Skills", "### 4. Ask Which Skill")
    for stale in ("`ownership`", "forge_groups", "same_folder", "cannot rename", "migrate first", "refuses these too"):
        assert stale not in roster, stale


def test_drop_forced_purge_is_guarded():
    text = _read(DROP_SELECT)
    ask_mode = _section(text, "### 8. Ask Mode", "### 8b. Purge Guard")
    draft = _section(ask_mode, "**If `target_in_manifest = false`:**", "**If `target_in_manifest = true`:**")
    for needle in ('"input-invalid"', '"input-missing"', "{forbidPurgeInHeadless}", "apply §8b",
                   "On-Activation guard"):
        assert needle in draft, needle
    # A headless purge of a draft is reached only with mode=purge, which the On-Activation guard
    # already checks, so a second forbid HALT here could never run.
    assert '"headless-purge-forbidden"' not in draft
    assert "1. A `mode` argument other than `purge`: HALT" in draft
    assert "2. `{headless_mode}` is true and no `mode` argument was passed: HALT" in draft, (
        "an interactive run confirms the forced purge at §10; only headless needs the argument")
    assert "{defaultMode}" not in draft and "default_mode" not in draft
    assert "leave out **[P]**" in ask_mode


def test_drop_contract_describes_the_draft_purge_guard():
    text = _read(DROP_SKILL)
    exit_6 = next(line for line in _read(DROP_CONTRACT).splitlines() if line.startswith("| 6 "))
    assert "§8" not in exit_6, "select.md §8 no longer raises headless-purge-forbidden"
    assert "cannot see the purge" not in text
    assert "cannot be deprecated" in _section(text, "## On Activation", None)


def _inventory_reasons(function: str) -> set[str]:
    """The `reason` values an inventory verdict can return, read from its source.

    A reason is the last quoted word a `refuse(...)` call passes before its
    detail, or a `reason = "..."` it assigns first; the verdicts are not reasons.
    """
    source = inspect.getsource(getattr(_inventory_module(), function))
    found = set(re.findall(r'reason = "([a-z-]+)"', source))
    for args in re.findall(r'refuse\(((?:"[a-z-]+", )*"[a-z-]+")', source):
        found.add(re.findall(r'"([a-z-]+)"', args)[-1])
    return found - {"ok", "not-skf-output"}


def test_drop_purge_guard_reads_the_purge_check():
    text = _read(DROP_SELECT)
    guard = _section(text, "### 8b. Purge Guard", "### 9. Compute Affected Directories")
    assert ('uv run {skillInventoryHelper} "{skills_output_folder}" --skill {target_skill} --purge-check '
            '[--purge-version {version}] --forge-data-folder "{forge_data_folder}"') in guard, (
        "a project path with a space must stay one argument")
    for binding in ("`{purge_verdict}` ← `verdict`", "`{purge_reason}` ← `reason`", "`{purge_detail}` ← `detail`",
                    "`{purge_entries}` ← `offending_entries`",
                    "`{affected_directories}` ← `affected_directories`",
                    "`{forge_left_in_place}` ← `forge_left_in_place`", "`{forge_errors}` ← `forge_errors`"):
        assert binding in guard, binding
    reasons = _inventory_reasons("purge_check")
    assert reasons == {"reserved-name", "skill-foreign", "skill-mixed-whole", "skill-version-mixed",
                       "skill-version-not-skf", "forge-mixed-whole", "forge-version-mixed"}
    messages = _section(guard, "**The guard.**", None)
    for reason in reasons | {"unknown"}:
        assert f"`{reason}`" in messages, f"the guard has no message for {reason}"
    assert "with or without a trailing `/`" in guard, "a linked version folder is listed without the slash"
    assert "`0.1.0-rc/` is not version `0.1.0`" in guard
    assert 'halt_reason: "not-skf-output"' in guard
    assert "bind `{purge_verdict}` and `{purge_reason}` to `\"unknown\"`" in guard
    ask = _section(text, "### 8. Ask Mode", "### 8b. Purge Guard")
    assert "run the §8b purge check at the current scope; when `{purge_verdict}` is not `\"ok\"`" in ask
    stored = _section(text, "### 11. Store Decisions in Context", "### 12.")
    for kept in ("`affected_directories`", "`forge_left_in_place`", "`target_context_files`"):
        assert kept in stored, kept
    assert "`target_ownership`" not in stored and "`target_forge_ownership`" not in stored


def test_drop_purge_deletes_through_the_guarded_delete():
    text = _read(DROP_EXECUTE)
    assert PROBE_ORDER in text.split("\n---\n", 1)[0] + "\n"
    delete = _section(text, "### 4. Delete Files (Purge Mode Only)", "### 5. Verify Final State")
    assert ('uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" '
            '--root "{forge_data_folder}" {each path in affected_directories, quoted, space-separated}') in delete
    assert "removes any trailing `/`" in delete
    assert "SKF never deletes through a link" in delete
    for binding in ("`files_deleted` ← `files_deleted`", "`delete_failures` ← `delete_failures`",
                    "`{bytes_freed}` ← `bytes_freed`", "`{purge_status}` ← `purge_status`"):
        assert binding in delete, binding
    assert "uv run {dirSizesHelper} humanize {bytes_freed}" in delete
    assert "delete nothing by hand" in delete, "a missing helper must never fall back to an unchecked delete"
    assert ("On a non-zero exit, or no JSON on stdout, take the `failed` outcome too, with the helper's `error` "
            "(its stderr when stdout holds no JSON) as the error of every path.") in delete, (
        "a failed call binds no purge_status: it must still reach a documented outcome")
    assert "An empty `affected_directories` (a manifest entry whose folders are already gone)" in delete
    for outcome in ("**`failed`**", "**`partial`**", "**`success`**"):
        assert outcome in delete, outcome
    for stale in ("Delete the directory recursively", "path_bytes", "du -sb", "Let `attempted` be"):
        assert stale not in delete, stale


def _inventory_call(rel: str, start: str, end: str) -> str:
    """The one fenced `{skillInventoryHelper} guarded-delete` call of a section."""
    [call] = [line.strip() for line in _section(_read(rel), start, end).split("\n")
              if line.strip().startswith("uv run {skillInventoryHelper} guarded-delete")]
    return call


def _run_guarded_delete(call: str, values: dict, paths: list[str]) -> dict:
    """Fill a documented guarded-delete call in as an agent would and run it, without a shell.

    Placeholders become sentinels before the words are split, so a Windows path keeps its
    backslashes; `paths` stands for the path list the call names.
    """
    call = call.replace("{each path in affected_directories, quoted, space-separated}", "@@PATHS@@")
    argv = []
    for word in shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call)):
        if word == "@@PATHS@@":
            argv.extend(paths)
        else:
            argv.append(re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], word))
    assert argv[:3] == ["uv", "run", str(INVENTORY_PY)], argv
    proc = subprocess.run([sys.executable, *argv[2:]], stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    result = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 0 and result["status"] == "ok", result
    return result


def test_drop_purge_with_nothing_on_disk_succeeds(tmp_path):
    """A manifest entry whose folders are gone: the purge check lists no folder, and the drop still succeeds."""
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    _write_bytes(skills / "keep" / "1.0.0" / "keep" / "SKILL.md", "kept\n")
    forge.mkdir()
    values = {"skillInventoryHelper": str(INVENTORY_PY), "skills_output_folder": str(skills),
              "forge_data_folder": str(forge)}
    call = _inventory_call(DROP_EXECUTE, "### 4. Delete Files (Purge Mode Only)", "### 5. Verify Final State")
    out = _run_guarded_delete(call, values, [])
    assert (out["purge_status"], out["files_deleted"], out["bytes_freed"]) == ("success", [], 0)
    _write_bytes(skills / "gone" / "2.0.0" / "gone" / "SKILL.md", "old\n")
    out = _run_guarded_delete(call, values, [str(skills / "gone")])
    assert (out["purge_status"], out["files_deleted"]) == ("success", [str(skills / "gone")])
    assert not (skills / "gone").exists() and (skills / "keep" / "1.0.0" / "keep" / "SKILL.md").is_file()


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
    assert "or an entry inside it, `{version}/<entry>`" in guard
    assert "- `skill-version-mixed`: \"**Purge refused: `{skills_output_folder}/{target_skill}/{version}` also " \
           "holds entries SKF did not generate:** {purge_entries}" in guard


def test_rename_ownership_check_precedes_the_lock():
    text = _read(RENAME_SELECT)
    check = _section(text, "### 4a. Ownership Check", "### 4b. Concurrency Guard")
    assert ('uv run {skillInventoryHelper} "{skills_output_folder}" --skill {old_name} --rename-check '
            '--forge-data-folder "{forge_data_folder}"') in check, "a project path with a space must stay one argument"
    assert "`{forge_move}` and `{forge_left_in_place}` come from the helper" in check
    assert "is SKF output or holds no file of its own" not in check, "the helper owns the forge_move rule"
    assert "`not-skf-output`" in check and "`flat-layout`" in check
    for binding in ("`{rename_verdict}` ← `verdict`", "`{rename_reason}` ← `reason`",
                    "`{rename_detail}` ← `detail`", "`{rename_entries}` ← `offending_entries`"):
        assert binding in check, binding
    assert "`{target_errors}` ← `errors`" in check, "a link is not a missing marker"
    assert "without `{skillInventoryHelper}`" not in check, "§1 halts on a missing helper before §4a runs"
    assert "When the call exits non-zero, or its result has no `rename_check`" in check, "a failed check fails closed"
    reasons = _inventory_reasons("rename_check")
    assert reasons == {"reserved-name", "absent", "foreign", "mixed", "flat-layout", "forge-link",
                       "forge-not-a-folder", "forge-unreadable", "forge-mixed"}
    for reason in reasons:
        assert f"`{reason}`" in check, f"§4a has no message for {reason}"
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
    resolve = _section(execute, "### 0. Resolve Helpers", "### 1. ")
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
    # The halt procedure releases the run lock after the rollback, through the helper.
    assert "Release the lock" not in rollback
    assert '`emit-halt` phase `execute:active-link`' in rollback
    assert 'then rm -f "{new_skill_group}/active"' in fix, "a link is removed as a link, never followed"
    assert 'elif [ -e "{new_skill_group}/active" ]; then rm -rf "{new_skill_group}/active"' in fix
    assert "bind `{active_link_kind}` ← `kind`" in fix and "bind `{flip_error}` ← `message`" in fix
    assert "it refuses to replace an `active` that is a real folder, so remove the copied entry first" in fix
    assert "Never create the link with `ln -s`: Git Bash on Windows without symlink rights writes a copy" in fix
    assert execute.count("Git Bash") == 1, "the ln -s reason is given once"
    for mechanics in ("active.skf-lock", "mklink /J", "temporary name", "os.symlink"):
        assert mechanics not in fix, "the helper's docstring holds how flip-link works"
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
    assert "Release the lock" not in rollback, "the halt procedure releases the run lock after the rollback"
    assert '`halt_reason: "manifest-write-failed"`, `emit-halt` phase `execute:manifest`' in rollback
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
    gate = _read("src/skf-analyze-source/references/step-auto-scope-coexistence.md")
    merge = _section(gate, "- **[M]erge:**", "- **[S]kip:**")
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
    first = _section(_read(CS_GENERATE), "### 1. Check Ownership", "### 2. ")
    refusal = next(p for p in first.split("\n\n") if p.startswith("Each refusal is a **HARD HALT**"))
    assert "leaves out `--result-dir`" in refusal and "--result-dir" not in refusal.split("`)")[0]
    rule = next(line for line in _read(CS_SKILL).splitlines() if "Every HARD HALT in steps 1 to 7" in line)
    assert 'adding `--result-dir "{forge_version}"` once step 7 has created `{forge_version}`' in rule
    assert "ownership halt" in _read("src/skf-quick-skill/references/batch-mode.md")
    assert ('(exit 5, `halt_reason: "not-skf-output"`, or `halt_reason: "flat-layout"` for the flat-layout refusal'
            in _read(SS_GENERATE))


def test_create_skill_gate_uses_the_working_version():
    text = _read(CS_GENERATE)
    for stale in ("Resolve `{version}` from the skill brief's `version` field",
                  "the semver version from the brief", "overwrites existing files)"):
        assert stale not in text, stale
    first = _section(text, "### 1. Check Ownership", "### 2. ")
    assert "`{version}` is the working version" in first


def test_writers_write_metadata_first():
    deliverables = _section(_read(QS_WRITE), "### 2. Write Deliverables", "### 3. ")
    assert "in this order, `metadata.json` first" in deliverables
    assert deliverables.index("1. `{skill_package}/metadata.json`") < deliverables.index("2. `{skill_package}/SKILL.md`")


def test_create_skill_swaps_the_whole_package_in():
    """create-skill builds the package beside its target and swaps it in, so no
    interrupted run leaves a package without its metadata.json marker."""
    promote = _section(_read(CS_GENERATE), "### 3. Promote the Staged Skill", "### 4. ")
    assert "The package is built beside its target and swapped in, so a reader never sees half of it." in promote
    helper = _read("src/shared/scripts/skf-promote-staged.py")
    assert '_atomic(["stage-dir", "--target", str(package)])' in helper
    assert '_atomic(["commit-dir", "--target", str(package)])' in helper


def test_create_skill_batch_advances_past_a_refused_brief():
    """A refused brief ends only itself: the batch helper records it as failed
    and hands out the next brief, so a later batch never refuses it again.
    The SKILL.md Workflow Rule says so for every HARD HALT of steps 1 to 7,
    so the refusal repeats no copy of it."""
    first = _section(_read(CS_GENERATE), "### 1. Check Ownership", "### 2. ")
    assert "--batch" not in first and "batch-state.yaml" not in first
    rules = _read("src/skf-create-skill/SKILL.md")
    assert "under `--batch` the halt ends only its brief: go to `references/batch-mode.md` §3" in rules
    batch = _read("src/skf-create-skill/references/batch-mode.md")
    record = _section(batch, "### 3. Record the Brief", "### 4. ")
    assert "every HARD HALT of steps 1 to 7 returns here after its envelope" in record


def test_stack_gate_runs_in_two_phases():
    text = _read(SS_GENERATE)
    assert "{skills_output_folder}/{project_name}-stack/active/{project_name}-stack/metadata.json" not in text, (
        "prior stack metadata is read only from a version SKF generated")
    assert "`{prior_active_version}` ← `write_check.marked_active_version`" in text
    phase_1 = text.index("--skill {stack_name} --write-check --forge-data-folder")
    assert phase_1 < text.index("{stack_name}/{prior_active_version}/{stack_name}/metadata.json")
    assert phase_1 < text.index("capture its `version` as `{prior_stack_version}`")
    assert text.index("**Pre-flight: ownership, phase 2.**") < text.index("stage-dir --target {skill_package}")
    exit_codes = _section(_read(SS_CONTRACT), "## Exit Codes", "## Result Contract")
    assert "state-conflict" in _row(exit_codes, "| 5 ")


def test_stack_refusals_share_one_message():
    """Every create-stack ownership refusal reads '`<stack>`: nothing was written.', then its reason (#600)."""
    refusals = _section(_read(SS_GENERATE), "**Ownership refusals (both phases).**", "Each refusal is a HARD HALT")
    assert refusals.count('"**`{stack_name}`: nothing was written.** {clause}"') == 1
    clauses = [line for line in refusals.splitlines() if line.startswith("- ")]
    # One clause per verdict: flat layout, not SKF output, an unchecked folder, a missing helper.
    assert [clause.split(":", 1)[0] for clause in clauses] == [
        '- `{write_verdict}` is `"flat-layout"`', '- `{write_verdict}` is `"not-skf-output"`',
        "- The status is not `ok`, or the output has no `write_check` (an older helper with no `--write-check` "
        "reports a new skill as `SKILL_NOT_FOUND`)", "- No helper candidate resolved"]
    assert not [clause for clause in clauses if "nothing was written" in clause], "a clause repeats the template"
    # Every case but the flat layout ends with the one remedy the shared-folder pins read.
    assert [("{remedy}" in clause) for clause in clauses] == [False, True, True, True]
    (remedy,) = [p for p in refusals.split("\n\n") if p.startswith("`{remedy}` is ")]
    assert "SKF leaves the skills it did not generate alone" in remedy and "module's own source" in remedy
    assert "\u2014" not in refusals


@pytest.mark.parametrize("rel", WRITER_SKILLS)
def test_writer_skills_carry_the_ownership_rule(rel):
    assert "Never write into a skill folder SKF did not generate" in _read(rel)


def test_stack_skill_never_decides_ownership_by_hand():
    assert "never decide by hand whether SKF generated a folder" in _read(SS_SKILL)


def test_drop_checks_the_forge_folder_before_any_change():
    text = _read(DROP_SELECT)
    roster = _section(text, "### 3. List Available Skills", "### 4. Ask Which Skill")
    assert "uv run {skillInventoryHelper} {skills_output_folder} --forge-data-folder {forge_data_folder}" in roster
    assert 'The §8b purge check then has no verdict (`"unknown"`)' in roster, "a missing helper must refuse the purge"
    guard = _section(text, "### 8b. Purge Guard", "### 9. Compute Affected Directories")
    assert '--forge-data-folder "{forge_data_folder}"' in guard
    for needle in ("`forge-mixed-whole`", "`forge-version-mixed`", "the purge leaves that folder where it is",
                   "`{forge_left_in_place}` names it", "`{version}/<entry>`", "unless both settings name one folder",
                   "SKF's own `improvement-queue`"):
        assert needle in guard, needle
    affected = _section(text, "### 9. Compute Affected Directories", "#### 9b.")
    assert "/{target_skill}/`" not in affected and "/{version}/`" not in affected, "no trailing `/` on a path"
    assert "without a trailing separator" in affected and "without a trailing `/`" in affected
    assert "Left in place (not SKF output)" in _section(text, "### 10. Confirmation Gate", "### 11. ")
    assert "Left in place (not SKF output)" in _read(DROP_REPORT)
    stored = _section(text, "### 11. Store Decisions in Context", "### 12.")
    assert "`forge_left_in_place`" in stored
    delete = _section(_read(DROP_EXECUTE), "### 4. Delete Files (Purge Mode Only)", "### 5. Verify Final State")
    assert "when `affected_directories` lists it" in delete


def test_rename_checks_the_forge_folder_before_the_lock():
    text = _read(RENAME_SELECT)
    roster = _section(text, "### 3. List Available Skills", "### 4. Ask Which Skill")
    assert "uv run {skillInventoryHelper} {skills_output_folder} --forge-data-folder {forge_data_folder}" in roster
    check = _section(text, "### 4a. Ownership Check", "### 4b. Concurrency Guard")
    for needle in ('--rename-check --forge-data-folder "{forge_data_folder}"', "`{same_folder}` ← `same_folder`",
                   "`{forge_move}` ← `forge_move`", "`{forge_left_in_place}` ← `forge_left_in_place`",
                   "SKF never moves or deletes through a link", "For `forge-link`, add:",
                   "a folder SKF can read"):
        assert needle in check, needle
    lock = _section(text, "### 4b. Concurrency Guard", "### 5. Ask for New Name")
    assert '--lock "{forge_data_folder}/.skf-rename-{old_name}.lock"' in lock
    assert "The helper creates `{forge_data_folder}` when it is missing." in lock


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
    assert 'Only when `{forge_move}` is true, add `"{old_forge_group}"` after `"{old_skill_group}"`' in delete
    update = _section(execute, "### 3. Update File Contents", "### 4. ")
    assert "context-snippet.md, provenance-map.json.\"" not in update, "name only the files rewritten"
    assert "Name only what `files_rewritten` holds, counted from it, never from the version count." in update
    assert "`same_folder`: carried from step 1" in _section(execute, "### 9. Store Results", "### 10. ")
    assert "{if forge_move or same_folder:}- provenance-map.json" in _read("src/skf-rename-skill/references/report.md")


def test_rename_deletes_the_old_folders_through_the_guarded_delete():
    """determinism-2: the checked delete drop uses, resolved in §0 so a missing helper halts before the copy."""
    execute = _read(RENAME_EXECUTE)
    assert PROBE_ORDER in execute.split("\n---\n", 1)[0] + "\n"
    resolve = _section(execute, "### 0. Resolve Helpers", "### 1. ")
    assert "`{skillInventoryHelper}` ← first existing path in `{skillInventoryProbeOrder}` (used in §8" in resolve
    assert 'HALT (exit code 4, `halt_reason: "write-failed"`, `emit-halt` phase `execute:resolve-helpers`)' in resolve
    delete = _section(execute, "### 8. Delete Old Directories", "### 9. ")
    assert _inventory_call(RENAME_EXECUTE, "### 8. Delete Old Directories", "### 9. ") == (
        'uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" --root "{forge_data_folder}" '
        '"{old_skill_group}"')
    assert "never by hand" in delete and "`deletion_errors` ← `delete_failures`" in delete
    assert "On a non-zero exit, or no JSON on stdout, record the helper's `error`" in delete
    assert "Do NOT attempt any rollback" in delete
    for stale in ("rm -rf {old_skill_group}", "rm -rf {old_forge_group}", "Verify deletion succeeded",
                  "is not a link or junction", "Continue attempting the other path"):
        assert stale not in delete, stale


@pytest.mark.parametrize("forge_move", [True, False], ids=["forge-moves", "forge-stays"])
def test_rename_guarded_delete_removes_only_the_old_folders(tmp_path, forge_move):
    skills, forge = tmp_path / "skills", tmp_path / "forge-data"
    for group in (skills / "old" / "1.0.0" / "old", skills / "new" / "1.0.0" / "new"):
        _write_bytes(group / "SKILL.md", "x\n")
    _write_bytes(forge / "old" / "1.0.0" / "provenance-map.json", "{}\n")
    values = {"skillInventoryHelper": str(INVENTORY_PY), "skills_output_folder": str(skills),
              "forge_data_folder": str(forge), "old_skill_group": str(skills / "old"),
              "old_forge_group": str(forge / "old")}
    call = _inventory_call(RENAME_EXECUTE, "### 8. Delete Old Directories", "### 9. ")
    if forge_move:  # "add `"{old_forge_group}"` after `"{old_skill_group}"`"
        call += ' "{old_forge_group}"'
    out = _run_guarded_delete(call, values, [])
    assert (out["purge_status"], out["delete_failures"]) == ("success", [])
    assert not (skills / "old").exists() and (skills / "new" / "1.0.0" / "new" / "SKILL.md").is_file()
    assert (forge / "old").exists() is not forge_move


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
    assert "If `{renameNameValidator}` cannot run" not in ask, "§5 has no in-prompt validator"
    assert "holding nothing a copy of it could not" not in ask


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
    for name in sorted(inventory.FORGE_VERSION_FILES) + ["test-report-", "test-findings-", "drift-report-",
                                                          ".skf-audit/", "-result-", ".skf-rename-"]:
        assert name in tree, f"the forge tree must name {name!r}"


# Each stack roster site: the extra bindings it makes, and whether it keeps a
# helper-less fallback. verify-stack halts when the helper is missing (#599);
# refine-architecture still walks the folder itself.
STACK_ROSTER_SITES = {
    "src/skf-verify-stack/references/init.md": ((), False),
    "src/skf-refine-architecture/references/init.md": (("`{pairs}` ← `pairs`",), True),
}


@pytest.mark.parametrize("rel", sorted(STACK_ROSTER_SITES))
def test_stack_rosters_read_only_skf_output(rel):
    text = _read(rel)
    extra_bindings, has_fallback = STACK_ROSTER_SITES[rel]
    assert "uv run {enumerateStackSkillsHelper}" in text
    assert "python3 {enumerateStackSkillsHelper}" not in text
    bindings = ("`{not_skf_output}` ← `not_skf_output`", "`{inventory_reliable}` ← `inventory_reliable`",
                "`{warning_count}` ← `warning_count`", "`{skill_count}` ← `skill_count`",
                "`{inventory_warnings}` ← `warnings`") + extra_bindings
    for binding in bindings:
        assert binding in text, binding
    assert "Skipped (not SKF output): {not_skf_output}" in text
    # The helper never reads the manifest or emits these fields and warnings.
    for stale in ("export-manifest →", "`skill_name`, `version`, `language`", "non-symlink `active`",
                  "orphan-versions", "maps `confidence_tier`", "{warning_count}/{skill_count + warning_count}",
                  "{exports_documented}", "| {skill_name} | {language}"):
        assert stale not in text, stale
    # The halt counts warnings as warnings.
    for needle in ("warning(s) across {skill_count}", "{exports_source}", "{confidence}"):
        assert needle in text, needle
    if not has_fallback:
        # The helper is required: no subagent fan-out rebuilds the roster by hand.
        assert "**Fallback path" not in text and "subagents concurrently" not in text
        resolve = _section(text, "**Resolve `{enumerateStackSkillsHelper}`**", "uv run {enumerateStackSkillsHelper}")
        assert '(exit code 3, `halt_reason: "resolution-failure"`)' in resolve
        return
    # The helper-less fallback applies the marker rule and binds the counts and
    # warnings the halt, §3 and §5 read.
    for needle in ("without counting a warning", "`generated_by`", "`tool_versions`", "`individual`"):
        assert needle in text, needle
    fallback = _section(text, "**Fallback path", "### 3.")
    assert "bind `{skill_count}` to the number of skills found" in fallback
    assert "`{warning_count}` to the number of warnings counted" in fallback
    assert "`{inventory_warnings}` to those warnings" in fallback


def test_compose_mode_reads_only_confirmed_skf_skills():
    detect = _read("src/skf-create-stack-skill/references/detect-manifests.md")
    assert "(`skill`, `stack`" not in detect, "SKF writes skill_type single, never skill"
    # Explicitly named skills pass the same roster gate as discovered ones: the
    # enumerate helper's candidates mode gates both, and no step joins by hand.
    assert "Use the explicit dependency list directly" not in detect
    assert 'uv run {enumerateStackSkillsHelper} candidates {skills_output_folder} [--explicit "<names>"]' in detect
    for needle in ("`--explicit` with the `explicit_deps` entries as given",
                   "`not_skf_output`", "`excluded[]`", "`stale_manifest_keys`",
                   "`skill_package_path` ← `{skills_output_folder}/{path}`", "one resolution"):
        assert needle in detect, needle
    # The keep rule lives once, in the helper the step renders.
    helper = _read("src/shared/scripts/skf-enumerate-stack-skills.py")
    assert "whose skill_type is single, individual or null (an early Quick Skill" in " ".join(helper.split())
    for stale in ("visited set", "try/except", "*/active/*/SKILL.md", "`{stack_roster}`"):
        assert stale not in detect, stale
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
    """SKILL.md must not promise a `-latest.json` at the ownership halt, which writes nothing:
    it promises none at all and leaves the rule to halt-contract.md, which states it once."""
    text = _read("src/skf-quick-skill/SKILL.md")
    assert "-latest.json" not in text
    assert "| **Exit codes** | See `references/halt-contract.md`" in text
    assert "except the step 5 §1 ownership halt" in _read(QS_HALT_CONTRACT)


RENAME_FORGE_REFUSAL = "is a link, is not a folder, or cannot be listed"
# Each surface that states rename's forge-folder refusal: how often it states
# it, and the narrower wording (links only) it must no longer use.
RENAME_FORGE_SURFACES = {
    "src/knowledge/version-paths.md": (2, ('refuses one that is `"mixed"` or a link',
                                           "entries SKF did not write or is a link.")),
    "src/skf-rename-skill/SKILL.md": (0, ("also holds other files or is a link,",)),
    "src/skf-rename-skill/references/exit-codes.md": (1, ("or a linked forge folder",)),
    "docs/workflows.md": (2, ("also holds other files or is a link",)),
    "docs/troubleshooting.md": (1, ("(rename also refuses one that is a link)",)),
}


@pytest.mark.parametrize("rel", sorted(RENAME_FORGE_SURFACES))
def test_rename_forge_refusal_matches_select(rel):
    """select.md §4a refuses a forge path with `errors` (a link, a non-folder or an unlistable one)."""
    rule = _section(_read(RENAME_SELECT), "5. `forge-link`, `forge-not-a-folder` or `forge-unreadable`", "6. ")
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


# --------------------------------------------------------------------------
# The lifecycle writers: export, drop and rename write the managed section
# through one helper, from one IDE mapping, and nothing else changes it
# --------------------------------------------------------------------------

EXPORT_SKILL = "src/skf-export-skill/SKILL.md"
EXPORT_LOAD = "src/skf-export-skill/references/load-skill.md"
EXPORT_UPDATE = "src/skf-export-skill/references/update-context.md"
EXPORT_SNIPPET = "src/skf-export-skill/references/generate-snippet.md"
RENAME_SKILL = "src/skf-rename-skill/SKILL.md"
REBUILD_PY = SRC / "shared" / "scripts" / "skf-rebuild-managed-sections.py"
OVERRIDE_GROUP = '[--skill-root-override "{snippet_skill_root_override}"]'
LIFECYCLE_SKILLS = ("skf-export-skill", "skf-drop-skill", "skf-rename-skill")


def _lifecycle_files():
    for skill in LIFECYCLE_SKILLS:
        yield from sorted(p for p in (SRC / skill).rglob("*") if p.suffix in (".md", ".toml"))


def test_the_retired_settings_are_gone():
    """unknown_ide_default_* and managed_section_format_path put the writer and the rebuilders out of step."""
    for path in _lifecycle_files():
        text = path.read_text(encoding="utf-8")
        for stale in ("unknown_ide_default", "unknownIdeDefault", "managed_section_format_path",
                      "managedSectionFormatPath", "managedSectionLogic", "managedSectionData"):
            assert stale not in text, f"{path.relative_to(REPO).as_posix()}: {stale}"


@pytest.mark.parametrize("rel, start, end", [
    (EXPORT_LOAD, "**Context File Resolution:**", "### 1b."),
    (DROP_SELECT, "3. **`context_files_count`**", "### 10."),
    (RENAME_EXECUTE, "**7a. Resolve the context files.**", "**7b. Per-file loop.**"),
])
def test_context_files_resolve_through_the_shared_mapping(rel, start, end):
    section = _section(_read(rel), start, end)
    assert 'python3 {rebuildManagedSectionsHelper} resolve-targets --ides "{ides}"' in section
    assert "Store `targets` as `target_context_files`" in section
    assert "each `warnings[]` and `notes[]` line" in section, "the note for an empty `ides` list is shown too"
    assert "IDE → Context File Mapping" not in section and "mapping table" not in section


def test_a_known_context_file_that_no_ide_names_is_checked_with_the_helper():
    """export §3b: a stale section is found by `check`, never by grepping for a closed marker literal."""
    orphaned = _section(_read(EXPORT_UPDATE), "#### 3b. Detect Orphaned Platform Files", "### 4. ")
    assert 'python3 {rebuildManagedSectionsHelper} "{context_path}" check' in orphaned
    assert "with its `{context_path}` as `file_path`" in orphaned
    assert "`{other_context_files}`" in orphaned and "`case` is `regenerate`" in orphaned
    assert "`{other_context_files}` ← `other_context_files`" in _read(EXPORT_LOAD)
    for rel in (EXPORT_UPDATE, DROP_EXECUTE, RENAME_EXECUTE):
        assert "`<!-- SKF:BEGIN -->` marker" not in _read(rel), rel
    # The gate it loads names the sections update-context.md has now.
    gate = _read("src/skf-export-skill/references/orphan-context-detection.md")
    assert "`{rebuildManagedSectionsHelper}` is the path SKILL.md's On Activation resolved" in gate
    assert "§9a" not in gate and gate.count("§4 to §9") == 3
    assert "updated ({case})" in _read("src/skf-export-skill/references/summary.md")


def test_export_records_the_manifest_with_passive_context_off():
    """architecture-3 and leanness-1: one `set` per skill, whatever passive_context says; its own result confirms it."""
    text = _read(EXPORT_UPDATE)
    passive = _section(text, "### 1. Check Passive Context Setting", "### 2. ")
    assert "Run §9b, then auto-proceed to {nextStepFile}." in passive
    manifest = _section(text, "### 9b. Update Export Manifest", "**Dry-run mode:**")
    assert ("python3 {manifestOpsHelper} {skills_output_folder} set {skill-name} {version} "
            "[--ides {ides_written}]") in manifest
    assert "with passive context off `ides_written` is empty" in manifest
    assert "It exits 0 with `status: \"ok\"` only once the manifest is written, so that result confirms the write." \
        in manifest
    # `set` writes atomically before it answers: a read-back would only have the model compare JSON fields.
    for stale in ("rename it to `ides` in place", '"active_version": "{version}"', "re-read the manifest",
                  "confirm the final state matches expectations", "{skills_output_folder} get {skill-name}",
                  "confirmed when `get` returns", "or `get` does not confirm"):
        assert stale not in text, stale
    assert "also when `passive_context` is off" in _read("src/skf-export-skill/references/invocation-contract.md")
    exit_codes = _section(_read("src/skf-export-skill/references/result-envelope.md"), "## Exit Codes", None)
    exit_4 = next(line for line in exit_codes.splitlines() if line.startswith("| 4 "))
    assert "step 4 §9b manifest write → `manifest-write-failed`" in exit_4


def test_export_reads_the_manifest_only_through_the_helper():
    """determinism-3: a raw read misses the v1 migration, so a dropped v1 skill came back in `--all`."""
    for path in sorted((SRC / "skf-export-skill").rglob("*.md")):
        for line in path.read_text(encoding="utf-8").split("\n"):
            assert not re.search(r"\b(?:[Rr]ead|[Ll]oad) `\{skills_output_folder\}/\.export-manifest\.json`", line), (
                f"{path.relative_to(REPO).as_posix()}: {line[:120]}")
    load = _read(EXPORT_LOAD)
    assert "python3 {manifestOpsHelper} {skills_output_folder} read" in load
    assert ('uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {skill-name} '
            '--forge-data-folder "{forge_data_folder}"') in load, "§2 chooses the version through the helper"
    # A run that names its skill reads the manifest first too, so a file that does not parse halts
    # with exit 3 at step 1, before the §1b probe, the §2 `resolve` or step 4 §9c writes a snippet.
    parse = _section(load, "### 1. Parse Export Arguments", "### 1b. ")
    assert "**Read the export manifest** on every run" in parse and "whenever this section needs it" not in parse
    assert parse.index("**Read the export manifest**") < parse.index("**Skill Path Discovery")
    assert 'HALT (exit code 3, `halt_reason: "resolution-failure"`): "**Export manifest is corrupt**' in parse
    assert "`python3 {manifestOpsHelper} {skills_output_folder} get {skill-name}`" in _read(EXPORT_SNIPPET)
    assert "uv run {manifestOpsHelper} {skills_output_folder} read" in _section(
        _read(RENAME_SELECT), "### 2. Read Export Manifest", "### 3. ")
    verify = _section(_read(DROP_EXECUTE), "### 5. Verify Final State", "### 6. ")
    assert "python3 {manifestOpsHelper} {skills_output_folder} get {target_skill}" in verify
    assert "Re-read `{skills_output_folder}/.export-manifest.json`" not in verify


def test_export_measures_the_snippet_ceiling_on_a_staged_draft():
    """determinism-5: the 300-token ceiling is the helper's count of the draft, never an estimate in the prompt."""
    text = _read(EXPORT_SNIPPET)
    count = _section(text, "### 4. Verify Token Count", "### 5. ")
    assert "`{export_stage_dir}/drafts/{skill-name}/context-snippet.md`" in count
    assert 'python3 {countTokensHelper} "{export_stage_dir}/drafts/{skill-name}"' in count
    assert "until `{count}` is 300 or below" in count
    assert "stays in-prompt" not in text
    assert "by hand" not in count, "no count in the prompt: §2.8 already needs Python for the stage folder"
    assert ('When the helper exits non-zero, delete the '
            '`{export_stage_dir}` folder and HALT (exit code 4, `halt_reason: "context-rebuild-failed"`)') in count
    assert "`{countTokensHelper}` ←" in _read(EXPORT_SKILL), "On Activation resolves the counter before any prompt"
    stage = _section(text, "### 2.8. Stage Folder", "### 3. ")
    assert "so a dry run leaves nothing beside a skill package or a context file" in stage
    assert "Step 4 deletes the folder on every exit, cancels and halts included." in stage
    assert 'print(tempfile.mkdtemp(prefix=\'skf-export-\'))' in text, "the stage folder lies outside the project"
    copy = ('cp "{export_stage_dir}/drafts/{skill-name}/context-snippet.md" '
            '"{resolved_skill_package}/context-snippet.md"')
    assert copy not in text, "step 3 only stages the snippet"
    assert copy in _section(_read(EXPORT_UPDATE), "### 9c. Write the Snippets", None), (
        "step 4 section 9c copies the snippet into the package only after its gate")


def test_export_step_4_deletes_the_stage_folder_on_every_exit():
    """A halted or cancelled export leaves no skf-export-* folder behind in the OS temp folder."""
    helpers = _section(_read(EXPORT_UPDATE), "### 2. Stage Folder", "### 3. ")
    assert ("deletes the folder on every exit: the §8 dry run and cancel, the end of §9c, the orphan-row (c) "
            "Cancel and every HALT in this step") in helpers
    cancel = _section(_read("src/skf-export-skill/references/orphan-row-detection.md"), "### (c) Cancel",
                      "## Downstream contract")
    assert "- Delete the `{export_stage_dir}` folder" in cancel


def test_export_halts_on_a_malformed_target_before_the_orphan_gate():
    """assemble lists a malformed target and goes on: a run that halts with exit 5 never asks the orphan question."""
    text = _read(EXPORT_UPDATE)
    assemble = _section(text, "#### 4b. Assemble One Body per Target", "#### 4c. ")
    assert ("When the first result's `malformed_context_files` is not empty, run the §5 `check` on those files now "
            "and take its `malformed` HALT, before §4c.1 asks anything") in assemble
    check = _section(text, "### 5. Check Each Target File", "### 6. ")
    assert "`unreadable`" not in check, "§4b's assemble already halts on a context file SKF cannot read"
    exit_codes = _section(_read("src/skf-export-skill/references/result-envelope.md"), "## Exit Codes", None)
    exit_5 = next(line for line in exit_codes.splitlines() if line.startswith("| 5 "))
    assert "step 4 §4b or §5" in exit_5


def test_rename_rolls_back_only_up_to_the_manifest_rekey():
    """#611: sections 2 to 6 roll back; the context-file rebuild in section 7 is best-effort."""
    text = _read(RENAME_EXECUTE)
    boundary = _section(text, "**Transactional boundary.**", "### 0. ")
    assert "a failure in any of sections 2-6 deletes the new skill folder" in boundary
    assert "Section 7 (context-file rebuild) is best-effort and never rolls back" in boundary
    assert "recorded in `context_files_failed`, `{new_skill_group}` stays" in boundary
    for stale in ("sections 2-7", "sections 2–7", "Any failure before the final delete"):
        assert stale not in text, stale
    rebuild = _section(text, "### 7. Rebuild Context Files", "### 8. ")
    assert "never delete `{new_skill_group}`" in rebuild and "HALT" not in rebuild
    # #611 records rebuild failures: a resolve that fails lands in context_files_failed, which the
    # §7c line and report.md show with the [EX] retry hint, rather than read as a clean run.
    assert ("set `context_files_failed` to the one entry `all context files: resolve-targets failed: {error}`"
            in rebuild)
    assert "as the reason no context file was rebuilt" not in rebuild
    assert "{if context_files_failed is non-empty:}" in _read("src/skf-rename-skill/references/report.md")
    assert "best-effort and never halts" in _read("src/skf-rename-skill/references/exit-codes.md")
    assert "§7 context-file rebuild is best-effort and never halts" in _read(RENAME_CONTRACT)
    assert "If any step fails before the final delete" not in _read(RENAME_SELECT)


# Each skill's documented rebuild: where its resolve-targets, check, assemble and write calls live.
LIFECYCLE_STEPS = {
    "export": {"resolve": (EXPORT_LOAD, "**Context File Resolution:**", "### 1b."),
               "assemble": (EXPORT_UPDATE, "#### 4b. Assemble One Body per Target", "#### 4c. "),
               "check": (EXPORT_UPDATE, "### 5. Check Each Target File", "### 6. "),
               "write": (EXPORT_UPDATE, "### 9. Write and Verify", "### 9b. ")},
    "drop": {"resolve": (DROP_SELECT, "3. **`context_files_count`**", "### 10."),
             "assemble": (DROP_EXECUTE, "### 3. Rebuild Context Files", "### 4. "),
             "check": (DROP_EXECUTE, "### 3. Rebuild Context Files", "### 4. "),
             "write": (DROP_EXECUTE, "### 3. Rebuild Context Files", "### 4. ")},
    "rename": {"resolve": (RENAME_EXECUTE, "### 7. Rebuild Context Files", "### 8. "),
               "assemble": (RENAME_EXECUTE, "### 7. Rebuild Context Files", "### 8. "),
               "check": (RENAME_EXECUTE, "### 7. Rebuild Context Files", "### 8. "),
               "write": (RENAME_EXECUTE, "### 7. Rebuild Context Files", "### 8. ")},
}
# The rows each operation finds before it rebuilds, in CLAUDE.md and AGENTS.md. After it, the
# manifest is the same for all three: alpha 1.0.0 and the stack beta 2.0.0. The export publishes
# alpha, the drop has removed `gone`, the rename has re-keyed `old-beta` to `beta`, and `ext` is a
# skill installed from elsewhere (an orphan row in CLAUDE.md only).
BEFORE_ROWS = {
    "export": ({"alpha": "0.9.0", "beta": "2.0.0", "ext": "1.0"}, None),
    "drop": ({"alpha": "1.0.0", "beta": "2.0.0", "ext": "1.0", "gone": "3.0.0"}, {"gone": "3.0.0", "alpha": "1.0.0"}),
    "rename": ({"alpha": "1.0.0", "ext": "1.0", "old-beta": "2.0.0"}, {"old-beta": "2.0.0"}),
}


def _documented_calls(rel: str, start: str, end: str) -> list[str]:
    """The fenced `{rebuildManagedSectionsHelper}` calls of a section, continuations joined."""
    calls, joined, fence = [], "", False
    for line in _section(_read(rel), start, end).split("\n"):
        if re.match(r"^\s*```", line):
            fence = not fence
            continue
        if not fence:
            continue
        if line.rstrip().endswith("\\"):
            joined += line.rstrip()[:-1].strip() + " "
            continue
        joined += line.strip()
        if "{rebuildManagedSectionsHelper}" in joined:
            calls.append(re.sub(r"\s+", " ", joined))
        joined = ""
    return calls


def _call(skill: str, part: str, word: str) -> str:
    [call] = [c for c in _documented_calls(*LIFECYCLE_STEPS[skill][part]) if f" {word}" in c]
    return call


def _run_documented(call: str, values: dict, override: str | None) -> dict:
    """Fill a documented call in as an agent would and run it, without a shell (so on Windows too).

    Placeholders become sentinels before the words are split, so a Windows path keeps its
    backslashes; a list value (the target paths) becomes one argument per path.
    """
    if override:
        call = call.replace(OVERRIDE_GROUP, OVERRIDE_GROUP[1:-1])
        values = {**values, "snippet_skill_root_override": override}
    else:
        call = call.replace(OVERRIDE_GROUP, "")
    command, _, stdin = call.partition(" < ")
    argv = []
    for word in shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", command)):
        whole = re.fullmatch(r"@@(\w+)@@", word)
        if whole and isinstance(values[whole.group(1)], list):
            argv.extend(values[whole.group(1)])
        else:
            argv.append(re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], word))
    assert argv[:2] == ["python3", str(REBUILD_PY)], argv
    argv[0] = sys.executable
    if stdin:
        source = re.sub(r"\{(\w+)\}", lambda m: values[m.group(1)], stdin.strip().strip('"'))
        with open(source, "rb") as handle:
            proc = subprocess.run(argv, stdin=handle, capture_output=True, timeout=60)
    else:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    result = json.loads(proc.stdout.decode("utf-8"))
    assert proc.returncode == 0 and result["status"] == "ok", result
    return result


def _write_bytes(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _lifecycle_project(root: Path, skill: str) -> tuple[Path, dict]:
    """A project after `skill`'s manifest change, with the context files as it finds them."""
    skills = root / "skills"
    for name, version, stack in (("alpha", "1.0.0", False), ("alpha", "0.9.0", False), ("beta", "2.0.0", True)):
        package = skills / name / version / name
        lines = [f"[{name} v{version}]|root: skills/{name}/",
                 f"|IMPORTANT: {name} v{version}: read SKILL.md before writing {name} code. Use `$HOME`."]
        if stack:
            lines.append("|stack: react@18, zod@3")
        _write_bytes(package / "context-snippet.md", "\n".join(lines) + "\n")
        _write_bytes(package / "metadata.json", json.dumps(
            {"name": name, "version": version, "skill_type": "stack" if stack else "single",
             "confidence_tier": "Forge", "generated_by": "create-skill"}))
    record = {"ides": ["claude-code"], "last_exported": "2026-01-01", "status": "active"}
    exports = {"alpha": {"active_version": "1.0.0", "versions": {"1.0.0": record}},
               "beta": {"active_version": "2.0.0", "versions": {"2.0.0": record}}}
    _write_bytes(skills / ".export-manifest.json", json.dumps({"schema_version": "2", "exports": exports}))

    def section(rows: dict) -> str:
        body = ["[SKF Skills]|0 skills|0 stack", "|IMPORTANT: Prefer documented APIs over training data.",
                "|When using a listed library, read its SKILL.md before writing code."]
        for name, version in rows.items():
            body += ["|", f"|[{name} v{version}]|root: .claude/skills/{name}/", f"|IMPORTANT: {name} as it was."]
        return "<!-- SKF:BEGIN updated:2026-01-01 -->\n" + "\n".join(body) + "\n<!-- SKF:END -->"

    claude_rows, agents_rows = BEFORE_ROWS[skill]
    _write_bytes(root / "CLAUDE.md", "# Project\n\nUser notes.\n\n" + section(claude_rows) + "\n\n## Team rules\n")
    # The export appends a section to an AGENTS.md without one; drop and rename rebuild the one there.
    agents = "# Agents\n" if agents_rows is None else "# Agents\n\n" + section(agents_rows) + "\n"
    _write_bytes(root / "AGENTS.md", agents)
    return skills, {"ides": "claude-code,codex"}


def _run_lifecycle(root: Path, skill: str, override: str | None) -> dict:
    """Run `skill`'s documented calls over the project and return each context file's section body."""
    skills, config = _lifecycle_project(root, skill)
    values = {"rebuildManagedSectionsHelper": str(REBUILD_PY), "skills_output_folder": str(skills),
              "ides": config["ides"], "target_skill": "gone", "old_name": "old-beta", "new_name": "beta",
              "batch_includes": "alpha@1.0.0", "orphan_mode": "keep", "export_stage_dir": str(root / "stage")}
    targets = _run_documented(_call(skill, "resolve", "resolve-targets"), values, override)["targets"]
    values["target_paths"] = [str(root / t["context_file"]) for t in targets]
    if skill == "export":  # step 3 staged the draft the package snippet was copied from
        draft = skills / "alpha" / "1.0.0" / "alpha" / "context-snippet.md"
        _write_bytes(root / "stage" / "drafts" / "alpha" / "context-snippet.md", draft.read_text(encoding="utf-8"))
    bodies = {}
    for target in targets:
        path = root / target["context_file"]
        values.update(context_path=str(path), context_file=target["context_file"], skill_root=target["skill_root"])
        case = _run_documented(_call(skill, "check", "check"), values, override)["case"]
        assembled = _run_documented(_call(skill, "assemble", "assemble"), values, override)
        values["content_file"] = assembled["content_file"]
        write = "replace" if case == "regenerate" else "insert"
        _run_documented(_call(skill, "write", write), values, override)
        text = path.read_bytes().decode("utf-8")
        bodies[target["context_file"]] = re.search(r"<!-- SKF:BEGIN updated:[^>]*-->\n(.*)\n<!-- SKF:END -->",
                                                   text, re.S).group(1)
        assert text.count("<!-- SKF:BEGIN") == 1 and text.count("<!-- SKF:END") == 1
    return bodies


@pytest.mark.parametrize("override", [None, "skills/"], ids=["ide-roots", "override"])
def test_export_drop_and_rename_write_byte_identical_sections(tmp_path, override):
    """#591: the same manifest and snippets give the same managed section, whichever skill writes it."""
    bodies = {skill: _run_lifecycle(tmp_path / skill, skill, override) for skill in ("export", "drop", "rename")}
    assert bodies["export"] == bodies["drop"] == bodies["rename"]
    for context_file, root in (("CLAUDE.md", ".claude/skills/"), ("AGENTS.md", ".agents/skills/")):
        body = bodies["export"][context_file]
        lines = body.split("\n")
        assert lines[0] == "[SKF Skills]|2 skills|1 stack"
        rows = [line for line in lines if line.startswith("|[")]
        prefix = override or root
        assert rows == [f"|[alpha v1.0.0]|root: {prefix}alpha/", f"|[beta v2.0.0]|root: {prefix}beta/",
                        "|[ext v1.0]|root: .claude/skills/ext/"], context_file
        assert "Use `$HOME`." in body, "the shell never expands a snippet"
        assert "gone" not in body and "old-beta" not in body


def test_drop_and_rename_calls_name_what_the_operation_removed():
    """Without --dropped or --renamed, the removed skill's old rows would stay as orphan rows."""
    assert "--dropped {target_skill}" in _call("drop", "assemble", "assemble")
    assert "--renamed {old_name}:{new_name}" in _call("rename", "assemble", "assemble")
    export = _call("export", "assemble", "assemble")
    assert "--include {batch_includes}" in export and '--out "{export_stage_dir}/previews/' in export


# --------------------------------------------------------------------------
# rename-skill's run: the run lock, the envelopes the shared emitter builds,
# the counts its report states and the recovery after the manifest re-key
# --------------------------------------------------------------------------

RENAME_REPORT = "src/skf-rename-skill/references/report.md"
RENAME_HEALTH = "src/skf-rename-skill/references/health-check.md"
RENAME_EXIT_CODES = "src/skf-rename-skill/references/exit-codes.md"
RENAME_CONTRACT = "src/skf-rename-skill/references/invocation-contract.md"
RUN_LOCK_PY = SRC / "shared" / "scripts" / "skf-run-lock.py"
EMITTER_PY = SRC / "shared" / "scripts" / "skf-emit-result-envelope.py"
VALIDATOR_PY = SRC / "skf-rename-skill" / "scripts" / "skf-validate-rename-name.py"
RENAME_SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-rename-skill-result-envelope.v1.json"
RENAME_RELEASE = ('uv run {runLockHelper} release --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" '
                  '--owner "{lock_owner}"')
RENAME_EMIT_HALT = ('uv run {emitEnvelopeHelper} emit-halt --workflow skf-rename-skill --run-dir "{run_dir}" '
                    "--target stderr <<'SKF_HALT'")
# A HALT site: its exit code, its halt_reason and the phase its emit-halt stages.
RENAME_HALT_RE = re.compile(r'HALT:? \(?exit code (\d+), `halt_reason: "([a-z-]+)"`, `emit-halt` phase `([a-z]+:[a-z-]+)`')


def _rename_markdown():
    return sorted((SRC / "skf-rename-skill").rglob("*.md"))


def _fenced_calls(text: str, helper: str) -> list[str]:
    """The fenced lines of `text` that run `helper`, backslash continuations joined."""
    calls, joined, fence = [], "", False
    for line in text.split("\n"):
        if re.match(r"^\s*```", line):
            fence, joined = not fence, ""
            continue
        if not fence:
            continue
        if line.rstrip().endswith("\\"):
            joined += line.rstrip()[:-1].strip() + " "
            continue
        joined += line.strip()
        if helper in joined:
            calls.append(re.sub(r"\s+", " ", joined))
        joined = ""
    return calls


def _heredoc(text: str, tag: str) -> str:
    """The one line between `<<'TAG'` and `TAG` in `text`."""
    [body] = re.findall(rf"<<'{tag}'\n(.*?)\n\s*{tag}\n", text, re.S)
    return body.strip()


def _run_py(script: Path, args: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, timeout=60)


def _documented_lock_argv(call: str, values: dict) -> list[str]:
    """A documented `uv run {runLockHelper} ...` call as argv after the script, placeholders filled."""
    words = shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call))
    assert words[:3] == ["uv", "run", "@@runLockHelper@@"], words
    return [re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], w) for w in words[3:]]


def _documented_emit_argv(call: str, values: dict) -> list[str]:
    """A documented `uv run {emitEnvelopeHelper} ...` call as argv after the script, its heredoc left out."""
    words = shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call))
    assert words[:3] == ["uv", "run", "@@emitEnvelopeHelper@@"], words
    return [re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], w) for w in words[3:] if not w.startswith("<<")]


def _halt_template(procedure: str) -> dict:
    """The halt procedure's payload template, each placeholder filled with a value of its type."""
    body = re.sub(r'<"\{\w+\}", or null [^>]*>', "null", _heredoc(procedure, "SKF_HALT"))
    return json.loads(re.sub(r'"<[^">]*>"', '"x"', body.replace('"{old_name}"', '"x"').replace('"{new_name}"', '"x"')))


def _emitted(proc: subprocess.CompletedProcess, stream: str = "stderr") -> dict:
    """The one envelope line the emitter printed, checked against the rename schema."""
    from jsonschema import Draft202012Validator

    assert proc.returncode == 0, proc.stderr
    [line] = getattr(proc, stream).decode("utf-8").splitlines()
    envelope = json.loads(line.removeprefix("SKF_RENAME_SKILL_RESULT_JSON: "))
    assert not list(Draft202012Validator(_schema()).iter_errors(envelope))
    return envelope


def test_rename_run_lock_goes_through_the_shared_helper():
    """#588: no PID guard, no flock and no shell variable from an earlier call holds the lock."""
    for path in _rename_markdown():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        for stale in ('"$$"', "kill -0", "flock", "$LOCK", "LOCK=", "HELD_PID", "live-PID",
                      'rm -f "{forge_data_folder}/.skf-rename-'):
            assert stale not in text, f"{rel}: {stale}"
    select = _read(RENAME_SELECT)
    lock = _section(select, "### 4b. Concurrency Guard", "### 5. Ask for New Name")
    assert _fenced_calls(lock, "{runLockHelper} acquire") == [
        'uv run {runLockHelper} acquire --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" '
        '--owner "rename-skill:{old_name}:{run_id}" --stale-after 60']
    assert "**Skip this section when `--dry-run` is set:**" in lock, "a dry run never blocks a rename"
    assert "bind `{lock_owner}` ← `owner`" in lock
    held = _section(lock, "- **3** (`acquired` false)", "- **Any other exit")
    assert ('HALT (exit code 5, `halt_reason: "halted-for-concurrent-run"`, `emit-halt` phase '
            '`select:concurrency-guard`, with the lock file as `path`)') in held
    assert "This run took no lock, so the halt releases none" in held
    assert "run-lock-replaced: {stale_replaced.held_by} since {stale_replaced.held_since}" in lock
    assert "When `record` exits non-zero, show its message and go on: the warning is advisory." in lock
    # Every release names the lock by its full path and passes the owner acquire printed.
    releases = {rel: _fenced_calls(_read(rel), "{runLockHelper} release")
                for rel in (RENAME_SELECT, RENAME_EXECUTE, RENAME_REPORT)}
    assert releases == {RENAME_SELECT: [RENAME_RELEASE], RENAME_EXECUTE: [RENAME_RELEASE],
                        RENAME_REPORT: [RENAME_RELEASE]}
    # step 2 renews the lock before its first write, and stops when this run lost it.
    execute = _read(RENAME_EXECUTE)
    copy = _section(execute, "### 1. Copy skill_group and forge_group", "### 2. ")
    assert _fenced_calls(copy, "{runLockHelper} acquire") == [
        'uv run {runLockHelper} acquire --lock "{forge_data_folder}/.skf-rename-{old_name}.lock" '
        '--owner "{lock_owner}" --stale-after 60']
    assert copy.index("**Renew the run lock first.**") < copy.index("**Precondition:**")
    renew = _section(copy, "- **Exit 0 with `refreshed` false, or exit 3:**", "- **Any other exit")
    assert '`halt_reason: "halted-for-concurrent-run"`, `emit-halt` phase `execute:run-lock`' in renew
    assert "before anything is copied" in renew


def test_rename_health_check_only_relays():
    """#588: the lock release moved to step 3, so the local health-check step keeps only the relay."""
    text = _read(RENAME_HEALTH)
    sequence = _section(text, "## MANDATORY SEQUENCE", None)
    assert sequence.strip().splitlines()[1:] == ["", "1. Load `{nextStepFile}`, read it fully, then execute it."]
    for stale in ("lock", "rm -f", "runLockHelper"):
        assert stale not in text, stale
    report = _read(RENAME_REPORT)
    release = _section(report, "### 4. Release the Run Lock and the Run Folder", "### 5. Chain to Health Check")
    assert _fenced_calls(release, "{runLockHelper} release") == [RENAME_RELEASE]
    assert "`reason` `not-owner`" in release and "Never stop on the result" in release


def test_rename_documented_lock_calls_hold_across_processes(tmp_path):
    """Run select §1's run-id, §4b's acquire, execute §1's renewal and the releases as documented.

    Each call is its own process, as each Bash tool call is: the lock a run takes in
    one call still refuses another run in the next, and only its owner releases it.
    """
    select = _read(RENAME_SELECT)
    [run_id_call] = _fenced_calls(_section(select, "### 1. Start the Run", "### 2. "), "{runLockHelper} run-id")
    [acquire] = _fenced_calls(_section(select, "### 4b. Concurrency Guard", "### 5. "), "{runLockHelper} acquire")
    [renew] = _fenced_calls(_section(_read(RENAME_EXECUTE), "### 1. Copy", "### 2. "), "{runLockHelper} acquire")
    forge = tmp_path / "forge data"
    lock = forge / ".skf-rename-demo.lock"

    def run(call, **values):
        proc = _run_py(RUN_LOCK_PY, _documented_lock_argv(call, {"forge_data_folder": str(forge),
                                                                "old_name": "demo", **values}))
        return proc.returncode, json.loads(proc.stdout.decode("utf-8") or "{}")

    code, first = run(run_id_call)
    assert code == 0 and re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", first["run_id"])
    code, taken = run(acquire, run_id=first["run_id"])
    assert (code, taken["acquired"], Path(taken["lock"])) == (0, True, lock)
    owner = taken["owner"]
    assert owner == f"rename-skill:demo:{first['run_id']}"
    # A second run, a later process: refused while the first run's lock is fresh.
    _, second = run(run_id_call)
    code, refused = run(acquire, run_id=second["run_id"])
    assert (code, refused["acquired"], refused["held_by"]) == (3, False, owner)
    assert str(lock) in refused["message"] and refused["stale_at"]
    # Its halt releases nothing it does not hold.
    code, kept = run(RENAME_RELEASE, lock_owner=f"rename-skill:demo:{second['run_id']}")
    assert (code, kept["released"], kept["reason"]) == (0, False, "not-owner") and lock.is_file()
    # The first run renews its lock before step 2 copies, then releases it.
    code, renewed = run(renew, lock_owner=owner)
    assert (code, renewed["refreshed"]) == (0, True)
    code, released = run(RENAME_RELEASE, lock_owner=owner)
    assert (code, released["released"]) == (0, True) and not lock.exists()
    # A crashed run's lock goes stale after the documented 60 minutes, and the next run takes it.
    lock.write_bytes(json.dumps({"owner": owner, "acquired_at": "2000-01-01T00:00:00Z",
                                 "tool": "skf-run-lock"}).encode("utf-8"))
    code, replaced = run(acquire, run_id=second["run_id"])
    assert (code, replaced["acquired"], replaced["stale_replaced"]["held_by"]) == (0, True, owner)
    # This run's lock went stale and another run took it over: the renewal finds it held.
    code, lost = run(renew, lock_owner=owner)
    assert (code, lost["acquired"]) == (3, False)


def test_rename_lock_beside_a_shared_folder_stays_skf_own(tmp_path):
    """#588: skf-skill-inventory.py still counts the rename lock as SKF's, where both settings name one folder."""
    out = tmp_path / "out"
    pkg = out / "demo" / "1.0.0" / "demo"
    _write_bytes(pkg / "SKILL.md", "---\nname: demo\n---\n")
    _write_bytes(pkg / "metadata.json", json.dumps({"name": "demo", "generated_by": "create-skill"}))
    proc = _run_py(RUN_LOCK_PY, ["acquire", "--lock", str(out / ".skf-rename-demo.lock"),
                                 "--owner", "rename-skill:demo", "--stale-after", "60"])
    assert proc.returncode == 0, proc.stderr
    scan = json.loads(_run_py(INVENTORY_PY, [str(out), "--forge-data-folder", str(out)]).stdout)
    assert scan["not_skf_output"] == [] and [s["skf_skill"] for s in scan["skills"]] == [True]
    check = json.loads(_run_py(INVENTORY_PY, [str(out), "--skill", "demo", "--rename-check",
                                              "--forge-data-folder", str(out)]).stdout)
    assert check["rename_check"]["verdict"] == "ok"


def test_rename_halts_emit_through_the_shared_emitter():
    """#593: every HALT names its phase, and each step file passes it to the one emitter call."""
    for rel in (RENAME_SELECT, RENAME_EXECUTE):
        text = _read(rel)
        procedure = _section(text, "**Halt procedure.**", "## MANDATORY SEQUENCE")
        assert _fenced_calls(procedure, "{runLockHelper} release") == [RENAME_RELEASE]
        # The payload goes to the emitter on stdin: a halt stages no file, so it emits its
        # line where it cannot write the run folder too.
        assert _fenced_calls(procedure, "emit-halt") == [RENAME_EMIT_HALT]
        assert "halt.json" not in text, f"{rel}: a halt stages nothing"
        # The halt's own keys and the two names: every one is a field the schema takes.
        assert set(_halt_template(procedure)) == {"phase", "halt_reason", "reason", "path", "old_name", "new_name"}
        assert "escape `\"`, `\\` and control characters, and write every path with `/`" in procedure
        assert ('add `"warnings": ["run-lock-not-released: {forge_data_folder}/.skf-rename-{old_name}.lock"]` '
                "to the payload below") in procedure
        assert ("Only when `{emitEnvelopeHelper}` is missing, or the emitter still fails or prints no line, "
                "display the halt's message alone.") in procedure
        for line in _section(text, "## MANDATORY SEQUENCE", None).split("\n"):
            if re.search(r"\bHALT\b", line) and "exit code" in line:
                assert RENAME_HALT_RE.search(line) or "halt_reason: \"{rename_verdict}\"" in line, (
                    f"{rel}: a HALT names no emit-halt phase: {line[:100]}")
    for path in _rename_markdown():
        text = path.read_text(encoding="utf-8")
        assert "emit the error envelope" not in text, path.name
        assert 'SKF_RENAME_SKILL_RESULT_JSON: {"status":"error"' not in text, "the emitter builds the halt line"


def test_rename_halt_emits_without_a_run_folder(tmp_path):
    """A halt before §1 binds a run folder, or whose folder could not be created, still prints its line.

    The documented call runs as written: without --run-dir for select §1's start-run halt, with
    the --run-dir of a folder that does not exist for its write-probe halt, and with a run folder
    that holds a decision for a step 2 halt whose lock release failed.
    """
    select = _read(RENAME_SELECT)
    procedure = _section(select, "**Halt procedure.**", "## MANDATORY SEQUENCE")
    [call] = _fenced_calls(procedure, "emit-halt")
    assert 'pass `--run-dir "{run_dir}"` once §1 has bound it, even when the folder could not be created' in procedure
    start = _section(select, "### 1. Start the Run", "### 2. ")
    assert 'With no run id yet, its `emit-halt` leaves out `--run-dir "{run_dir}"`.' in start
    assert "displays its message alone" not in start, "a missing run folder never silences a halt"
    template = _halt_template(procedure)

    def halt(argv_call: str, values: dict, **fields) -> dict:
        payload = {**template, "old_name": None, "new_name": None, **fields}
        if "path" not in fields:
            del payload["path"]
        return _emitted(_run_py(EMITTER_PY, _documented_emit_argv(argv_call, values),
                                json.dumps(payload).encode("utf-8")))

    no_run_dir = call.replace(' --run-dir "{run_dir}"', "")
    started = halt(no_run_dir, {}, phase="select:start-run", halt_reason="write-failed",
                   reason="Rename Skill cannot start: skf-run-lock.py is missing.")
    assert (started["exit_code"], started["run_id"], started["error"]["phase"]) == (4, None, "select:start-run")
    missing = tmp_path / "_bmad-output" / ".skf-run" / "skf-rename-skill-20261001T000000Z-0123abcd"
    probe = halt(call, {"run_dir": str(missing)}, phase="select:write-probe", halt_reason="write-failed",
                 reason=f"Cannot write to {missing.as_posix()}.", path=missing.as_posix())
    assert (probe["run_id"], probe["error"]["path"]) == ("20261001T000000Z-0123abcd", missing.as_posix())
    assert not missing.exists() and not missing.parent.exists(), "the emitter creates no run folder"
    # A step 2 halt whose release failed: the payload's warning and the recorded decision both reach the line.
    [step2_call] = _fenced_calls(_section(_read(RENAME_EXECUTE), "**Halt procedure.**", "## MANDATORY SEQUENCE"),
                                 "emit-halt")
    run_dir = tmp_path / "skf-rename-skill-20261001T000000Z-89abcdef"
    decision = _record_the_override(run_dir)
    lock = f"{(tmp_path / 'forge').as_posix()}/.skf-rename-demo.lock"
    copied = halt(step2_call, {"run_dir": str(run_dir)}, phase="execute:copy", halt_reason="copy-failed",
                  reason="Copy failed.", old_name="demo", new_name="demo-kit",
                  warnings=[f"run-lock-not-released: {lock}"])
    assert copied["headless_decisions"] == [decision]
    assert copied["warnings"] == [f"run-lock-not-released: {lock}"]


def test_rename_exit_code_table_names_every_halt_reason():
    """The emitter reads the schema's exit_codes; the table names each halt_reason in its code's row only."""
    table = _read(RENAME_EXIT_CODES)
    assert "through the schema's `skf-envelope.exit_codes`; this table says where each code is raised" in table
    codes = _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"]
    for reason, code in codes.items():
        assert f"`{reason}`" in _row(table, f"| {code} "), f"exit-codes.md row {code} does not name `{reason}`"
        for other in set(codes.values()) - {code}:
            assert f"`{reason}`" not in _row(table, f"| {other} "), f"exit-codes.md row {other} names `{reason}`"
    description = _schema()["properties"]["exit_code"]["description"]
    assert "skf-envelope.exit_codes" in description and "input-missing" not in description, "one copy of the map"


def _schema() -> dict:
    return json.loads(RENAME_SCHEMA.read_text(encoding="utf-8"))


def _halt_sites() -> list[tuple[str, str, int, str, str]]:
    """(file, line number, exit code, halt_reason, phase) of every documented HALT."""
    sites = []
    for rel in (RENAME_SELECT, RENAME_EXECUTE):
        for number, line in enumerate(_read(rel).split("\n"), 1):
            for m in RENAME_HALT_RE.finditer(line):
                sites.append((rel, number, int(m.group(1)), m.group(2), m.group(3)))
            if 'halt_reason: "{rename_verdict}"' in line:  # §4a: one of the two verdicts
                m = re.search(r"exit code (\d+), `halt_reason: \"\{rename_verdict\}\"`, `emit-halt` phase `([^`]+)`",
                              line)
                sites += [(rel, number, int(m.group(1)), verdict, m.group(2))
                          for verdict in ("not-skf-output", "flat-layout")]
    return sites


def test_rename_every_halt_site_matches_the_schema_exit_code(tmp_path):
    """Each halt's documented exit code is the one the emitter derives, and its envelope validates."""
    codes = _schema()["$defs"]["skf-envelope"]["const"]["exit_codes"]
    sites = _halt_sites()
    assert {reason for _, _, _, reason, _ in sites} == set(codes), "every halt_reason has a documented halt"
    run_dir = tmp_path / "skf-rename-skill-20261001T000000Z-0123abcd"
    run_dir.mkdir()
    argv = _documented_emit_argv(RENAME_EMIT_HALT, {"run_dir": str(run_dir)})
    for rel, number, code, reason, phase in sites:
        assert codes[reason] == code, f"{rel}:{number}: {reason} exits {codes[reason]}, not {code}"
        payload = {"phase": phase, "halt_reason": reason, "reason": "the step halted", "old_name": "demo",
                   "new_name": None}
        envelope = _emitted(_run_py(EMITTER_PY, argv, json.dumps(payload).encode("utf-8")))
        assert (envelope["status"], envelope["exit_code"], envelope["error"]["phase"]) == ("error", code, phase)
        assert envelope["run_id"] == "20261001T000000Z-0123abcd"


def test_rename_contract_lists_the_schema_halt_reasons():
    assert "## Result Contract" not in _read(RENAME_SKILL), "#600: the headless contract lives in one place"
    contract = _section(_read(RENAME_CONTRACT), "## Result Contract (Headless)", None)
    listed = set(re.findall(r'`"([a-z-]+)"`', _section(contract, "`halt_reason` is one of:", "(§7")))
    enum = {r for r in _schema()["properties"]["halt_reason"]["enum"] if r is not None}
    assert listed == enum
    assert "`shared/scripts/schemas/skf-rename-skill-result-envelope.v1.json`" in contract
    assert "The model never types the line" in contract


# Each placeholder the documented payload templates hold, and the JSON value a run fills in.
RENAME_PAYLOAD_VALUES = {
    '"{old_name}"': '"demo"',
    '"{new_name}"': '"demo-kit"',
    "<affected_versions as a JSON array>": '["2.0.0", "1.0.0"]',
    "<renamed_versions as a JSON array>": '["2.0.0"]',
    "<renamed_versions>": '["2.0.0"]',
    "<manifest_rekeyed>": "true",
    "<context_files_updated as a JSON array>": '["CLAUDE.md"]',
    "<context_files_updated>": '["CLAUDE.md"]',
    "<context_files_failed>": "[]",
    "<forge_left_in_place, or null>": "null",
    '<one {"type": "skill", "path": "<path>"} per path in files_rewritten>':
        '[{"type": "skill", "path": "skills/demo-kit/2.0.0/demo-kit/SKILL.md"}]',
}


def _filled(template: str) -> dict:
    for placeholder, value in RENAME_PAYLOAD_VALUES.items():
        template = template.replace(placeholder, value)
    return json.loads(template)


def _record_the_override(run_dir: Path) -> dict:
    """§6's two commands: stage the decision, then record it in the run sink."""
    source = _section(_read(RENAME_SELECT), "### 6. Source Authority Check", "### 7. ")
    decision = json.loads(_heredoc(source, "SKF_DECISION"))
    assert _fenced_calls(source, "{emitEnvelopeHelper} record") == [
        'uv run {emitEnvelopeHelper} record --workflow skf-rename-skill --run-dir "{run_dir}" --decision '
        '< "{run_dir}/decision.json"']
    proc = _run_py(EMITTER_PY, ["record", "--workflow", "skf-rename-skill", "--run-dir", str(run_dir), "--decision"],
                   json.dumps(decision).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    return decision


def test_rename_dry_run_restates_its_complete_envelope(tmp_path):
    """#585: the dry-run exit states its whole envelope and its stream, and writes no result file."""
    from jsonschema import Draft202012Validator

    confirm = _section(_read(RENAME_SELECT), "### 8. Confirmation Gate", "### 9. ")
    dry = _section(confirm, "**If `--dry-run` was passed**", "- **If `Y`**")
    assert "In `{headless_mode}`, emit the dry-run envelope on **stdout**" in dry
    assert "Without `--result-dir` it writes no result file" in dry
    assert _fenced_calls(dry, "{emitEnvelopeHelper} emit") == [
        'uv run {emitEnvelopeHelper} emit --workflow skf-rename-skill --run-dir "{run_dir}" '
        '< "{run_dir}/result-context.json"']
    assert "The dry run took no lock (§4b), so it releases none" in dry
    run_dir = tmp_path / "skf-rename-skill-20261001T000000Z-0123abcd"
    decision = _record_the_override(run_dir)
    proc = _run_py(EMITTER_PY, ["emit", "--workflow", "skf-rename-skill", "--run-dir", str(run_dir)],
                   json.dumps(_filled(_heredoc(dry, "SKF_RESULT"))).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    [line] = proc.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line.removeprefix("SKF_RENAME_SKILL_RESULT_JSON: "))
    assert not list(Draft202012Validator(_schema()).iter_errors(envelope))
    assert (envelope["status"], envelope["exit_code"], envelope["result_path"]) == ("dry-run", 0, None)
    assert envelope["headless_decisions"] == [decision]
    # The restated line names every field the emitter prints, in its order.
    restated = re.search(r"It prints the complete line, `SKF_RENAME_SKILL_RESULT_JSON: (\{.*?\})`", dry).group(1)
    assert re.findall(r'"(\w+)":', restated) == list(envelope)
    assert _fenced_calls(dry, "rmdir") == [
        'rm -f "{run_dir}/result-context.json" "{run_dir}/decision.json" "{run_dir}/headless-decisions.jsonl" '
        '"{run_dir}/warnings.jsonl" && rmdir "{run_dir}"']
    # When the emitter printed no line, the run folder is the only record of the decisions.
    keep = dry.index("keep `{run_dir}` and say in one line that it holds the run's decisions, its warnings and "
                     "the payload the emitter refused")
    assert keep < dry.index("Otherwise, in both modes, delete the run folder") < dry.index("rmdir")


def test_rename_report_writes_its_result_files_through_the_emitter(tmp_path):
    """#593: step 3's payload validates, the emitter names and writes the result files, and
    the auto-decisions come from the run sink, never from context."""
    from jsonschema import Draft202012Validator

    report = _read(RENAME_REPORT)
    write = _section(report, "### 1. Write the Result Files and the Envelope", "### 2. Render the Report")
    assert _fenced_calls(write, "{emitEnvelopeHelper} emit") == [
        'uv run {emitEnvelopeHelper} emit --workflow skf-rename-skill --run-dir "{run_dir}" '
        '--result-dir "{skills_output_folder}/{new_name}" < "{run_dir}/result-context.json"']
    run_dir = tmp_path / "skf-rename-skill-20261001T000000Z-0123abcd"
    decision = _record_the_override(run_dir)
    group = tmp_path / "skills" / "demo-kit"
    group.mkdir(parents=True)
    payload = _filled(_heredoc(write, "SKF_RESULT"))
    assert "headless_decisions" not in payload and "headless_decisions" not in payload["result_contract"]["summary"]
    proc = _run_py(EMITTER_PY, ["emit", "--workflow", "skf-rename-skill", "--run-dir", str(run_dir),
                                "--result-dir", str(group)], json.dumps(payload).encode("utf-8"))
    assert proc.returncode == 0, proc.stderr
    [line] = proc.stdout.decode("utf-8").splitlines()
    envelope = json.loads(line.removeprefix("SKF_RENAME_SKILL_RESULT_JSON: "))
    assert not list(Draft202012Validator(_schema()).iter_errors(envelope))
    assert (envelope["status"], envelope["exit_code"], envelope["versions_renamed"]) == ("success", 0, ["2.0.0"])
    assert envelope["headless_decisions"] == [decision]
    per_run = Path(envelope["result_path"])
    assert per_run.parent == group and re.fullmatch(r"rename-skill-result-\d{8}-\d{6}\.json", per_run.name)
    latest = json.loads((group / "rename-skill-result-latest.json").read_text(encoding="utf-8"))
    assert latest == json.loads(per_run.read_text(encoding="utf-8"))
    assert latest["headless_decisions"] == [decision] and latest["run_id"] == "20261001T000000Z-0123abcd"
    assert latest["summary"]["versions_renamed"] == ["2.0.0"]
    # The hook reads the file the emitter named, never a timestamp the run typed.
    hook = _section(report, "### 3. Post-Completion Hook (optional)", "### 4. ")
    assert '{onCompleteCommand} --result-path="{result_path}"' in hook
    for path in _rename_markdown():
        assert "{timestamp}" not in path.read_text(encoding="utf-8"), path.name


def test_rename_report_runs_one_terminal_sequence():
    """#585: result files and envelope, report, hook, lock release and run folder, then the health check."""
    report = _read(RENAME_REPORT)
    order = ["### 1. Write the Result Files and the Envelope", "### 2. Render the Report",
             "### 3. Post-Completion Hook (optional)", "### 4. Release the Run Lock and the Run Folder",
             "### 5. Chain to Health Check"]
    assert [report.index(heading) for heading in order] == sorted(report.index(heading) for heading in order)
    assert "When `{headless_mode}` is true, display `{result_line}` verbatim" in report
    release = _section(report, order[3], order[4])
    assert _fenced_calls(release, "rmdir") == [
        'rm -f "{run_dir}/result-context.json" "{run_dir}/decision.json" "{run_dir}/headless-decisions.jsonl" '
        '"{run_dir}/warnings.jsonl" && rmdir "{run_dir}"']
    # The run folder goes only once the emitter printed the line that carries its decisions.
    assert "Then, when §1's emitter printed its line, delete the run folder:" in release
    assert ("When §1's emitter printed no line, keep `{run_dir}` instead and tell the user in one line that it "
            "holds the run's decisions, its warnings and the payload the emitter refused.") in release
    write = _section(report, order[0], order[1])
    assert "No result file was written, and §4 keeps the run folder." in write
    assert "escape `\"`, `\\` and control characters, and write every path with `/`" in write
    for mechanics in ("-latest.json", "`-2`", "a copy, not a symlink"):
        assert mechanics not in write, "output-contract-schema.md owns how the emitter writes the files"
    skill = _read(RENAME_SKILL)
    activation = _section(skill, "## On Activation", None)
    assert "Pre-flight write probe" not in activation and "timestamp" not in activation
    start = _section(_read(RENAME_SELECT), "### 1. Start the Run", "### 2. ")
    assert '`{run_dir}` ← `{project-root}/_bmad-output/.skf-run/skf-rename-skill-{run_id}`' in start
    assert 'for dir in "{run_dir}" "{skills_output_folder}" "{forge_data_folder}"; do' in start
    assert 'halt_reason: "write-failed"`, `emit-halt` phase `select:write-probe`' in start


def test_rename_counts_come_from_the_helper_results():
    """#593: the handoffs carry what the report and the envelope state, tallied from helper results."""
    execute = _read(RENAME_EXECUTE)
    update = _section(execute, "### 3. Update File Contents", "### 4. ")
    assert "when its `wrote` is not null, add `{kind, path}` (the `--kind` and the `wrote` path) to `files_rewritten`" in update
    results = _section(execute, "### 9. Store Results in Context", "### 10. ")
    for bullet in ("- `renamed_versions`:", "- `files_rewritten`:", "- `run_id`, `run_dir` and `lock_owner`:",
                   "- `manifest_rekeyed`: true only when section 6 ran the re-key and the helper exited 0"):
        assert bullet in results, bullet
    decisions = _section(_read(RENAME_SELECT), "### 9. Store Decisions in Context", "### 10. ")
    for bullet in ("- `manifest_exists`: boolean from §2", "- `lock_owner`:", "- `run_id` and `run_dir`:"):
        assert bullet in decisions, bullet
    for section in (results, decisions):
        assert "- `headless_decisions`" not in section, "the run sink holds the decisions"
    report = _read(RENAME_REPORT)
    assert "Versions renamed: {the number of renamed_versions} ({comma-separated renamed_versions})" in report
    for kind in ("skill-frontmatter", "metadata-json", "context-snippet", "provenance-json"):
        assert f"(×{{the files_rewritten entries of kind {kind}}})" in report, kind
    for rel in (RENAME_EXECUTE, RENAME_REPORT):
        text = _read(rel)
        for stale in ("affected_versions_count", "files_updated_per_version"):
            assert stale not in text, f"{rel}: {stale}"
    verify = _section(execute, "### 5. Verify", "### 6. ")
    assert "across the {number of `renamed_versions`} version(s) it checked" in verify
    # §6's flag and report line say whether the re-key ran, as §9's manifest_rekeyed does.
    manifest = _section(execute, "### 6. Update Export Manifest", "### 7. ")
    assert "Set context flag `manifest_rekeyed = true` when the helper ran and exited 0, else `false`" in manifest
    assert "Set `manifest_rekeyed = false` and `manifest_backup = null`" in manifest
    for rel in (RENAME_EXECUTE, RENAME_REPORT):
        assert "manifest_updated" not in _read(rel), f"{rel}: one manifest flag name (#600)"
    assert 'When it skipped the call: "**Manifest unchanged:** it has no `exports.{old_name}` entry."' in manifest


def test_rename_reads_the_version_through_the_inventory_helper(tmp_path):
    """#597: no stage reads version-paths.md; §6 takes the version's metadata.json from `resolve`."""
    for path in _rename_markdown():
        text = path.read_text(encoding="utf-8")
        for stale in ("versionPathsKnowledge", "version-paths.md"):
            assert stale not in text, f"{path.name}: {stale}"
    source = _section(_read(RENAME_SELECT), "### 6. Source Authority Check", "### 7. ")
    [call] = [c for c in _fenced_calls(source, "{skillInventoryHelper}")]
    assert call == ('uv run {skillInventoryHelper} resolve "{skills_output_folder}" --skill {old_name} '
                    '--forge-data-folder "{forge_data_folder}"')
    assert "bind `{source_metadata}` ← `paths.metadata.path`" in source
    # The documented call picks the manifest's version, and the link's when the manifest lags it.
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version, authority in (("1.0.0", "community"), ("2.0.0", "official")):
        _write_bytes(skills / "demo" / version / "demo" / "metadata.json",
                     json.dumps({"name": "demo", "source_authority": authority}))
    _write_bytes(skills / ".export-manifest.json", json.dumps({"schema_version": "2", "exports": {
        "demo": {"active_version": "1.0.0", "versions": {"1.0.0": {"status": "active"}}}}}))
    values = {"skills_output_folder": str(skills), "old_name": "demo", "forge_data_folder": str(forge)}
    argv = [re.sub(r"@@(\w+)@@", lambda m: values[m.group(1)], w)
            for w in shlex.split(re.sub(r"\{(\w+)\}", r"@@\1@@", call))[3:]]

    def metadata_path():
        out = json.loads(_run_py(INVENTORY_PY, argv).stdout)
        return Path(out["resolve"]["paths"]["metadata"]["path"])

    assert metadata_path() == skills / "demo" / "1.0.0" / "demo" / "metadata.json"
    try:
        (skills / "demo" / "active").symlink_to("2.0.0", target_is_directory=True)
    except (OSError, NotImplementedError):
        return
    assert metadata_path() == skills / "demo" / "2.0.0" / "demo" / "metadata.json"


def test_rename_names_the_recovery_after_the_rekey(tmp_path):
    """#587: a rename interrupted after the manifest re-key is named at the next run, with the
    commands that finish it, instead of a dead-end collision that invites a third name."""
    ask = _section(_read(RENAME_SELECT), "### 5. Ask for New Name", "### 6. Source Authority Check")
    recovery = _section(ask, "**Recovery after the manifest re-key.**", None)
    for needle in ("When `interrupted_after_rekey` is true", "`leftover_folders`", "in both modes",
                   'uv run {skillInventoryHelper} guarded-delete --root "{skills_output_folder}" '
                   '--root "{forge_data_folder}" {each path in leftover_folders, quoted}',
                   "`[EX] Export Skill`",
                   'HALT (exit code 5, `halt_reason: "name-collision"`, `emit-halt` phase `select:validate-new-name`)'):
        assert needle in recovery, needle
    assert "When `interrupted_after_rekey` is true, take the recovery halt below the list, in both modes" in ask
    # The fingerprint is the validator's: no in-prompt fallback redoes it.
    assert "the fingerprint after the re-key" not in ask
    assert "stopped after re-keying the export manifest" in _read(RENAME_EXIT_CODES)
    # The documented commands on a rename that stopped after the re-key: the validator names the
    # old folders, and the checked delete removes exactly them.
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for group, name in ((skills / "demo", "demo"), (skills / "demo-kit", "demo-kit")):
        _write_bytes(group / "1.0.0" / name / "SKILL.md", f"---\nname: {name}\n---\n")
    for name in ("demo", "demo-kit"):
        _write_bytes(forge / name / "1.0.0" / "provenance-map.json", json.dumps({"skill_name": name}))
    _write_bytes(skills / ".export-manifest.json", json.dumps({"schema_version": "2", "exports": {
        "demo-kit": {"active_version": "1.0.0"}}}))
    proc = _run_py(VALIDATOR_PY, ["--old-name", "demo", "--new-name", "demo-kit", "--skills-output-folder",
                                  str(skills), "--forge-data-folder", str(forge)])
    verdict = json.loads(proc.stdout)
    assert (proc.returncode, verdict["first_failure"], verdict["interrupted_after_rekey"]) == (2, "collision", True)
    assert verdict["leftover_folders"] == [str(skills / "demo"), str(forge / "demo")]
    deleted = _run_py(INVENTORY_PY, ["guarded-delete", "--root", str(skills), "--root", str(forge),
                                     *verdict["leftover_folders"]])
    assert json.loads(deleted.stdout)["purge_status"] == "success"
    assert not (skills / "demo").exists() and not (forge / "demo").exists()
    assert (skills / "demo-kit" / "1.0.0" / "demo-kit" / "SKILL.md").is_file()
    assert (forge / "demo-kit" / "1.0.0" / "provenance-map.json").is_file()
