#!/usr/bin/env python3
"""update-skill writes each new version into a folder of its own.

Outside gap-driven mode an update names a new version (the source's
version when step 1 found a higher one, else the next patch version).
merge.md §6b stages a copy of the current package with
skf-atomic-write.py stage-dir, copies it, publishes it with commit-dir,
creates the new forge folder with the provenance map, evidence report and
extraction rules, and rebinds {skill_package} and {forge_version}, so
write.md's metadata, provenance and active-link steps all land in the new
version and the previous one stays as it was. It never overwrites a
version folder that already exists, and the read-only modes never reach it.

The prose pins slice merge.md §6b and fail loudly on a renamed heading. The
run test executes the stage-dir and commit-dir commands §6b spells out (the
placeholders filled in) against the real helpers, copies the package as
§6b says, and then runs the active-link flip write.md §5b performs, which
halted with missing-target while the version folder did not exist.
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
REFS = SRC / "skf-update-skill" / "references"
INIT = REFS / "init.md"
MERGE = REFS / "merge.md"
WRITE = REFS / "write.md"
REPORT = REFS / "report.md"
DETECT = REFS / "detect-changes.md"
RE_EXTRACT = REFS / "re-extract.md"
SKILL = SRC / "skf-update-skill" / "SKILL.md"
SCHEMA = SRC / "shared" / "scripts" / "schemas" / "skf-update-result-envelope.v1.json"
SCRIPTS = SRC / "shared" / "scripts"
ATOMIC_WRITE = SCRIPTS / "skf-atomic-write.py"
SYMLINK = SCRIPTS / "skf-update-active-symlink.py"
INVENTORY = SCRIPTS / "skf-skill-inventory.py"
HASH_CONTENT = SCRIPTS / "skf-hash-content.py"
ATOMIC_PATHS = [
    "{project-root}/_bmad/skf/shared/scripts/skf-atomic-write.py",
    "{project-root}/src/shared/scripts/skf-atomic-write.py",
]
CALL_RE = re.compile(r"uv run \{atomicWriteHelper\} (stage-dir|commit-dir) (.+)")


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


def _merge_6b() -> str:
    return _slice(_read(MERGE), "### 6b. Write Merged Files to Disk", "### 7.")


def _step(section: str, number: int) -> str:
    """Numbered step `number` of the version-folder list in merge §6b."""
    start = f"\n{number}. **"
    end = f"\n{number + 1}. **" if f"\n{number + 1}. **" in section else "\n\nIf no `{atomicWriteProbeOrder}`"
    return _slice(section, start, end)


# --------------------------------------------------------------------------
# merge.md §6b
# --------------------------------------------------------------------------


def test_merge_declares_the_atomic_write_helper():
    text = _read(MERGE)
    frontmatter = text[4:text.index("\n---\n", 4) + 1]
    assert yaml.safe_load(frontmatter)["atomicWriteProbeOrder"] == ATOMIC_PATHS
    assert "HALT if neither resolves" in frontmatter


def test_merge_chooses_the_new_version():
    six_b = _merge_6b()
    choose = _slice(six_b, "**Choose the version this update writes**", "**Create the version folder**")
    assert "bind `{new_version}`" in choose
    assert "`{new_version}` is `{source_version_detected}` when step 1 §6c recorded one" in choose
    assert "patch number incremented" in choose
    assert "**Gap-driven mode**" in choose and "the version folder below is skipped" in choose
    assert "(normal, degraded and docs-only)" in choose
    assert "(every mode but gap-driven)" in six_b


def test_merge_never_overwrites_a_version():
    six_b = _merge_6b()
    guard = _step(six_b, 1)
    assert "**Never overwrite a version.**" in guard
    for folder in ("`{skill_group}/{new_version}/`", "`{forge_data_folder}/{skill_name}/{new_version}/`"):
        assert folder in guard, folder
    assert "`halted-for-write-failure` before writing anything" in guard
    assert 'phase: "merge:new-version-folder"' in guard
    assert six_b.index("**Never overwrite a version.**") < six_b.index("stage-dir")


def test_merge_stages_copies_publishes_and_rebinds_in_order():
    six_b = _merge_6b()
    marks = ["**Never overwrite a version.**", "stage-dir --target", "**Copy the current package**",
             "commit-dir --target", "**Create the forge folder**", "**Rebind**", "**Write SKILL.md:**"]
    positions = [six_b.index(m) for m in marks]
    assert positions == sorted(positions), marks
    assert "Bind `{version_staging}` ← `staging`" in _step(six_b, 2)
    copy = _step(six_b, 3)
    assert 'cp -a "{skill_package}" "{version_staging}/{skill_name}"' in copy
    assert "each link copied as a link and never followed" in copy
    forge = _step(six_b, 5)
    for name in ("`provenance-map.json`", "`evidence-report.md`", "`extraction-rules.yaml`"):
        assert name in forge, name
    rebind = _step(six_b, 6)
    assert "`{skill_package}` ← `{skill_group}/{new_version}/{skill_name}`" in rebind
    assert "`{forge_version}` ← `{forge_data_folder}/{skill_name}/{new_version}`" in rebind
    failure = _slice(six_b, "If no `{atomicWriteProbeOrder}` candidate resolves", "**Write SKILL.md:**")
    assert "remove what this section created" in failure and "merge:new-version-folder" in failure
    assert "none of which existed before the first step" in failure


def test_write_names_the_folder_step_4_created():
    two = _slice(_read(WRITE), "### 2. Write Updated metadata.json", "### 3.")
    assert "Update `version` to `{new_version}`, the version step 4 §6b chose" in two
    assert "From here on `{version}` is `{new_version}`" in two
    assert "increment patch version" not in two
    three = _slice(_read(WRITE), "### 3. Write Updated provenance-map.json", "**Every entry this step writes")
    assert "write the whole updated map there" in three


def test_report_and_contract_name_the_new_version():
    report = _read(REPORT)
    files = _slice(report, "### 4. Show Files Updated", "### 5.")
    assert "| `{skill_package}/SKILL.md` | Updated |" in files
    assert "{resolved_skill_package}" not in files
    dry = _slice(report, "### 1b. Handle Dry-Run Mode", "### 2.")
    # --dry-run never reaches merge §6b, which binds {new_version}.
    assert "a new version folder beside the current one" in dry and "{new_version}" not in dry
    assert "`{source_version_detected}` when step 1 §6c recorded one and otherwise the next patch version" in dry
    outputs = _slice(_read(SKILL), "| **Outputs** |", "\n")
    assert "new version folder `{skill_group}/{new_version}/`" in outputs
    status = json.loads(_read(SCHEMA))["properties"]["skf_update"]["properties"]["status"]["description"]
    assert "merge:new-version-folder" in status


def test_init_follows_the_active_link():
    """After an update, `active` names the new version and the manifest still the exported one."""
    paths = _slice(_read(INIT), "**Version-Aware Path Resolution:**", "\n5. Store the resolved path")
    step2 = _slice(paths, "\n2. If found:", "\n3. ")
    assert "**Manifest-lag guard.**" in step2
    assert "bind `{active_version}` to the link's target version instead" in step2
    assert step2.index("**Manifest-lag guard.**") < step2.index("Resolve to `{skill_package}`")
    step3 = _slice(paths, "\n3. If not in manifest:", "\n4. ")
    assert "bind `{active_version}` to the version it names" in step3
    assert "the `{active_version}` steps 1–3 resolved" in _read(INIT)
    us = _slice(_read(SRC / "knowledge" / "version-paths.md"),
                "**Update-skill (US)** writes each new version into a folder of its own", "\n")
    assert "Manifest-lag guard" in us and "a second update before an export builds on the first" in us


def test_version_exists_halt_never_sends_the_user_to_delete_good_work():
    guard = _step(_merge_6b(), 1)
    assert "updates the version the `active` link names, which is not {new_version}" in guard
    assert "Drop Skill removes a single version only when the export manifest lists it" in guard
    assert "for a skill that was never exported it can only drop every version" in guard
    assert "remove it with a hard drop" not in guard
    trouble = _slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                     "### Update Skill stops with `halted-for-write-failure` because the version already exists",
                     "\n### ")
    assert "Never remove the version the `active` link names" in trouble
    assert "only when the export manifest lists it" in trouble and "can only drop every version" in trouble
    assert "remove it with a hard drop" not in trouble


def test_manual_mismatch_recovery_depends_on_mode():
    """A gap-driven repair writes in place: its halt must not name a folder to delete."""
    one = _slice(_read(WRITE), "### 1. Verify SKILL.md Write", "### 2.")
    assert one.count("{manual_recovery}") == 2
    recovery = one[one.index("`{manual_recovery}` depends on the mode:"):]
    outside = _slice(recovery, "- **Outside gap-driven mode**", "\n")
    gap = _slice(recovery, "- **Gap-driven mode**", "\n")
    for folder in ("`{skill_group}/{new_version}/`", "`{forge_data_folder}/{skill_name}/{new_version}/`"):
        assert folder in outside, folder
    assert "delete" not in gap.lower() and "{new_version}" not in gap
    assert "Restore the [MANUAL] blocks" in gap and "Keep the version folder" in gap
    halt = _slice(_merge_6b(), "**Halt-on-tool-failure:**", "\n")
    assert "When this run created `{skill_group}/{new_version}/`" in halt
    assert "In gap-driven mode the skill package may be in a partial state" in halt


def test_read_only_modes_never_reach_merge():
    """--detect-only leaves from step 2 and --dry-run from step 3, before §6b."""
    text = _read(DETECT)
    assert text.count("### 5. Display Change Summary and Route") == 1
    route = text[text.index("### 5. Display Change Summary and Route"):]
    assert "Do not load `{nextStepFile}`" in _slice(route, "**`detect_only_mode == true`**", "\n")
    six = _slice(_read(RE_EXTRACT), "### 6. Route to Next Step", "- **Otherwise**")
    assert "load `report.md` (NOT `{nextStepFile}`)" in _slice(six, "**`dry_run_mode == true`**", "\n")


def test_docs_and_knowledge_describe_version_folders():
    paths = _read(SRC / "knowledge" / "version-paths.md")
    us = _slice(paths, "**Update-skill (US)** writes each new version into a folder of its own", "\n")
    for token in ("`skf-atomic-write.py stage-dir`", "`commit-dir`", "`halted-for-write-failure`",
                  "`--detect-only` and `--dry-run` create nothing"):
        assert token in us, token
    workflows = _slice(_read(REPO_ROOT / "docs" / "workflows.md"), "### Update Skill (US)", "**Agent:**")
    assert "**Versions:**" in workflows and "in a folder of its own" in workflows
    # init.md §6c detects a source version only in a remote skill's private tree.
    remote_only = "for a skill built from a remote repository, the source's version when it is higher"
    assert remote_only in workflows and "the next update starts from it" in workflows
    trouble = _slice(_read(REPO_ROOT / "docs" / "troubleshooting.md"),
                     "### Update Skill stops with `halted-for-write-failure` because the version already exists",
                     "\n### ")
    assert "`merge:new-version-folder`" in trouble and "delete both folders" in trouble
    assert remote_only in trouble


# --------------------------------------------------------------------------
# Run what §6b spells out
# --------------------------------------------------------------------------


def _fill(template: str, values: dict) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    assert "{" not in template, template
    return template


def _run_call(section: str, command: str, values: dict) -> dict:
    calls = {m.group(1): m.group(2).strip() for m in CALL_RE.finditer(section)}
    assert command in calls, f"merge §6b runs no `{command}`"
    argv = shlex.split(_fill(calls[command], values))
    proc = subprocess.run([sys.executable, str(ATOMIC_WRITE), command, *argv], capture_output=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _snapshot(path: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(path):
        for name in [*dirnames, *filenames]:
            p = Path(dirpath) / name
            st = os.lstat(p)
            out[p.relative_to(path).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def test_version_folder_steps_run_against_the_real_helpers(tmp_path):
    six_b = _merge_6b()
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    group, old = skills / "lib", skills / "lib" / "1.0.0" / "lib"
    _write(old / "SKILL.md", "---\nname: lib\n---\n# lib\n")
    _write(old / "metadata.json", json.dumps({"name": "lib", "version": "1.0.0", "skill_type": "single",
                                              "confidence_tier": "Forge", "generated_by": "create-skill"}))
    _write(old / "references" / "api.md", "# api\n")
    _write(old / "scripts" / "build.sh", "echo build\n")
    outside = tmp_path / "outside"
    _write(outside / "secret.txt", "not part of the skill\n")
    linked = False
    try:
        os.symlink(outside, old / "assets", target_is_directory=True)
        linked = True
    except (OSError, NotImplementedError):
        _write(old / "assets" / "logo.txt", "logo\n")
    old_forge = forge / "lib" / "1.0.0"
    for name in ("provenance-map.json", "evidence-report.md", "extraction-rules.yaml", "test-report-lib-x.md"):
        _write(old_forge / name, name + "\n")
    before = _snapshot(group / "1.0.0")
    values = {"skill_group": group.as_posix(), "new_version": "1.0.1"}

    staged = _run_call(six_b, "stage-dir", values)
    staging = Path(staged["staging"])
    assert staging == group / "1.0.1.skf-tmp" and staging.is_dir() and not os.listdir(staging)
    assert "cp -a" in _step(six_b, 3)
    shutil.copytree(old, staging / "lib", symlinks=True)  # what `cp -a` does
    _run_call(six_b, "commit-dir", values)
    new_forge = forge / "lib" / "1.0.1"
    new_forge.mkdir(parents=True)
    for name in re.findall(r"`([\w.-]+\.(?:json|md|yaml))`", _step(six_b, 5)):
        if (old_forge / name).is_file():
            shutil.copy2(old_forge / name, new_forge / name)

    new = group / "1.0.1" / "lib"
    assert sorted(os.listdir(group / "1.0.1")) == ["lib"]
    assert not os.path.lexists(staging)
    assert (new / "references" / "api.md").is_file() and (new / "scripts" / "build.sh").is_file()
    if linked:
        assert os.path.islink(new / "assets"), "the link was followed"
    assert _snapshot(group / "1.0.0") == before, "the previous version changed"
    assert sorted(os.listdir(new_forge)) == ["evidence-report.md", "extraction-rules.yaml", "provenance-map.json"]
    assert (old_forge / "test-report-lib-x.md").is_file()

    inventory = subprocess.run([sys.executable, str(INVENTORY), str(skills), "--skill", "lib"],
                               capture_output=True, encoding="utf-8")
    entry = json.loads(inventory.stdout)["skills"][0]
    assert entry["ownership"] == "skf" and entry["foreign_entries"] == []

    if os.name != "nt":  # write.md §5b; the symlink helper refuses Windows
        os.symlink("1.0.0", group / "active")
        flip = subprocess.run([sys.executable, str(SYMLINK), "update", "--skill-group", str(group),
                               "--version", "1.0.1"], capture_output=True, encoding="utf-8")
        assert flip.returncode == 0, flip.stdout + flip.stderr
        assert json.loads(flip.stdout)["status"] == "flipped"


def test_manual_inventory_stays_out_of_every_version_folder(tmp_path):
    """A live update left `.manual-inventory.json` in the previous version's forge folder, which §6b keeps unchanged.

    init.md §5 runs before merge creates the new version, so its inventory
    goes beside the update lock; the read-only modes write none.
    """
    text = _read(INIT)
    five = _slice(text, "### 5. Load [MANUAL] Section Inventory", "### 6.")
    fence = five[five.index("```bash\n") + len("```bash\n"):]
    fence = fence[:fence.index("```")]
    command, target = (part.strip() for part in fence.replace("\\\n", " ").split(">"))
    assert command == "uv run {hashContentHelper} manual-inventory {resolved_skill_package}/SKILL.md"
    assert target == "{forge_data_folder}/{skill_name}/.skf-update-manual-inventory.json"
    assert "{forge_version}/.manual-inventory.json" not in text
    assert ("When `detect_only_mode` or `dry_run_mode` is true, run the same command without the redirect and "
            "read its output instead") in five
    assert "never in a version folder" in five
    # The knowledge file other workflows read agrees: no inventory in {version}/, the new one among the .skf- names.
    paths = _read(SRC / "knowledge" / "version-paths.md")
    forge_tree = _slice(paths, "### forge_data_folder\n", "`skill-brief.yaml` stays at")
    version_entries = _slice(forge_tree, "    {version}/\n", "  _campaign/")
    assert "provenance-map.json" in version_entries and ".manual-inventory.json" not in version_entries
    assert "update-skill's `.skf-update-manual-inventory.json` beside it" in paths
    assert ("a `.manual-inventory.json` in a version folder, where update-skill once kept the [MANUAL] inventory it "
            "now keeps beside its lock") in paths

    skills, forge = tmp_path / "skills", tmp_path / "forge"
    package, old_forge = skills / "lib" / "1.0.0" / "lib", forge / "lib" / "1.0.0"
    _write(package / "SKILL.md", "---\nname: lib\n---\n# lib\n\n<!-- [MANUAL:notes] -->\nmine\n<!-- [/MANUAL:notes] -->\n")
    _write(package / "metadata.json", json.dumps({"name": "lib", "version": "1.0.0", "skill_type": "single",
                                                  "generated_by": "create-skill"}))
    for name in ("provenance-map.json", "evidence-report.md", "extraction-rules.yaml"):
        _write(old_forge / name, name + "\n")
    _write(forge / "lib" / "skill-brief.yaml", "name: lib\n")
    before = _snapshot(old_forge)
    values = {"resolved_skill_package": package.as_posix(), "forge_data_folder": forge.as_posix(),
              "skill_name": "lib"}
    argv = shlex.split(_fill(command.replace("uv run {hashContentHelper}", ""), values))
    proc = subprocess.run([sys.executable, str(HASH_CONTENT), *argv], capture_output=True)
    assert proc.returncode == 0, proc.stderr
    Path(_fill(target, values)).write_bytes(proc.stdout)
    assert _snapshot(old_forge) == before, "the previous version's forge folder changed"
    assert json.loads((forge / "lib" / ".skf-update-manual-inventory.json").read_bytes())["count"] == 1
    inventory = subprocess.run([sys.executable, str(INVENTORY), str(skills), "--skill", "lib",
                                "--forge-data-folder", str(forge)], capture_output=True, encoding="utf-8")
    group = json.loads(inventory.stdout)["forge_groups"][0]
    assert group["ownership"] == "skf" and group["foreign_entries"] == [], group


@pytest.mark.skipif(os.name == "nt", reason="cp -a is the POSIX spelling §6b gives")
def test_the_copy_command_keeps_links_as_links(tmp_path):
    """The `cp -a` §6b names copies a link as a link on this platform's cp."""
    copy = _step(_merge_6b(), 3)
    match = re.search(r'`(cp [^`]*"\{skill_package\}" "\{version_staging\}/\{skill_name\}")`', copy)
    assert match, "merge §6b names no cp command"
    package, staging = tmp_path / "pkg", tmp_path / "staging"
    _write(package / "SKILL.md", "x\n")
    outside = tmp_path / "outside"
    _write(outside / "secret.txt", "s\n")
    os.symlink(outside, package / "assets", target_is_directory=True)
    staging.mkdir()
    argv = shlex.split(_fill(match.group(1), {"skill_package": str(package), "version_staging": str(staging),
                                              "skill_name": "lib"}))
    subprocess.run(argv, check=True)
    assert os.path.islink(staging / "lib" / "assets")
    assert (staging / "lib" / "SKILL.md").is_file()
