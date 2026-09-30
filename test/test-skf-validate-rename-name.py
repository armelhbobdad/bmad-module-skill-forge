#!/usr/bin/env python3
"""Tests for skf-validate-rename-name.py — deterministic rename-target gate."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "src"
    / "skf-rename-skill"
    / "scripts"
    / "skf-validate-rename-name.py"
)

spec = importlib.util.spec_from_file_location("skf_validate_rename_name", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
validate_name = mod.validate_name


def make_dirs(tmp_path):
    out = tmp_path / "out"
    forge = tmp_path / "forge"
    out.mkdir()
    forge.mkdir()
    return out, forge


def write_manifest(out, exports):
    (out / ".export-manifest.json").write_text(
        json.dumps({"schema_version": "2", "exports": exports})
    )


def symlinks_supported(tmp: Path) -> bool:
    probe = tmp / "symlink-probe"
    try:
        probe.symlink_to(tmp)
    except (OSError, NotImplementedError):
        return False
    probe.unlink()
    return True


# --- format ---


def test_valid_kebab(tmp_path):
    out, forge = make_dirs(tmp_path)
    r = validate_name("rename", "rename-skill", str(out), str(forge))
    assert r["valid"] is True
    assert r["first_failure"] is None
    assert r["checks"]["format"]["ok"] is True


def test_digit_leading_name_accepted(tmp_path):
    out, forge = make_dirs(tmp_path)
    r = validate_name("old", "3d-tools", str(out), str(forge))
    assert r["valid"] is True


def test_bad_format_uppercase(tmp_path):
    out, forge = make_dirs(tmp_path)
    r = validate_name("old", "Rename-Skill", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "format"


def test_bad_format_trailing_hyphen(tmp_path):
    out, forge = make_dirs(tmp_path)
    r = validate_name("old", "rename-", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "format"


# --- length ---


def test_length_over_64_fails(tmp_path):
    out, forge = make_dirs(tmp_path)
    name = "a" * 65
    r = validate_name("old", name, str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "length"
    assert r["checks"]["length"]["length"] == 65


def test_length_exactly_64_ok(tmp_path):
    out, forge = make_dirs(tmp_path)
    name = "a" * 64
    r = validate_name("old", name, str(out), str(forge))
    assert r["checks"]["length"]["ok"] is True
    assert r["valid"] is True


# --- identity ---


def test_same_as_old_fails(tmp_path):
    out, forge = make_dirs(tmp_path)
    r = validate_name("rename", "rename", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "identity"


# --- collision ---


def test_collision_in_manifest(tmp_path):
    out, forge = make_dirs(tmp_path)
    write_manifest(out, {"taken": {}})
    r = validate_name("old", "taken", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "collision"
    kinds = {loc["kind"] for loc in r["checks"]["collision"]["locations"]}
    assert kinds == {"manifest.exports"}
    assert r["interrupted_rename"] is False


def test_collision_in_skills_dir(tmp_path):
    out, forge = make_dirs(tmp_path)
    (out / "taken").mkdir()
    r = validate_name("old", "taken", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "collision"
    kinds = {loc["kind"] for loc in r["checks"]["collision"]["locations"]}
    assert "skills_output_folder" in kinds


def test_collision_in_forge_dir(tmp_path):
    out, forge = make_dirs(tmp_path)
    (forge / "taken").mkdir()
    r = validate_name("old", "taken", str(out), str(forge))
    assert r["valid"] is False
    assert "forge_data_folder" in {
        loc["kind"] for loc in r["checks"]["collision"]["locations"]
    }


def test_no_collision_when_absent(tmp_path):
    out, forge = make_dirs(tmp_path)
    write_manifest(out, {"other": {}})
    (out / "other").mkdir()
    r = validate_name("old", "fresh-name", str(out), str(forge))
    assert r["checks"]["collision"]["ok"] is True
    assert r["valid"] is True


# --- interrupted-rename fingerprint ---


def test_interrupted_rename_fingerprint(tmp_path):
    out, forge = make_dirs(tmp_path)
    # Staged new dirs exist on disk but NOT in the manifest, and the old dirs
    # are still present -> stranded partial rename.
    (out / "new-name").mkdir()
    (forge / "new-name").mkdir()
    (out / "old-name").mkdir()
    (forge / "old-name").mkdir()
    write_manifest(out, {"old-name": {}})
    r = validate_name("old-name", "new-name", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "collision"
    assert r["interrupted_rename"] is True


def test_manifest_collision_is_not_interrupted(tmp_path):
    out, forge = make_dirs(tmp_path)
    write_manifest(out, {"new-name": {}, "old-name": {}})
    (out / "new-name").mkdir()
    (forge / "new-name").mkdir()
    (out / "old-name").mkdir()
    (forge / "old-name").mkdir()
    r = validate_name("old-name", "new-name", str(out), str(forge))
    # Collides in the manifest too -> a genuine clash, not a stranded rename.
    assert r["interrupted_rename"] is False


def test_disk_collision_without_old_dirs_not_interrupted(tmp_path):
    out, forge = make_dirs(tmp_path)
    (out / "new-name").mkdir()
    (forge / "new-name").mkdir()
    # old-name dirs absent -> not the interrupted fingerprint.
    r = validate_name("old-name", "new-name", str(out), str(forge))
    assert r["interrupted_rename"] is False


def test_interrupted_rename_without_forge_data(tmp_path):
    """A skill with no forge folder (a quick skill) leaves only a skills-side copy."""
    out, forge = make_dirs(tmp_path)
    (out / "new-name").mkdir()
    (out / "old-name").mkdir()
    r = validate_name("old-name", "new-name", str(out), str(forge))
    assert r["first_failure"] == "collision"
    assert r["interrupted_rename"] is True
    # A new forge folder comes only from an old one: without it, a clash.
    (forge / "new-name").mkdir()
    r = validate_name("old-name", "new-name", str(out), str(forge))
    assert r["interrupted_rename"] is False


def test_interrupted_rename_needs_a_copy_of_the_old_skill(tmp_path):
    """Recovery advice fires only when the new skill folder could be a rename's copy."""
    out, forge = make_dirs(tmp_path)
    pkg = out / "a" / "1.0.0" / "a"
    pkg.mkdir(parents=True)
    (pkg / "SKILL.md").write_text("---\nname: a\n---\n", encoding="utf-8")
    (pkg / "metadata.json").write_text('{"generated_by": "quick-skill"}', encoding="utf-8")
    if symlinks_supported(tmp_path):
        (out / "a" / "active").symlink_to("1.0.0", target_is_directory=True)
    # A module's own skill at the new name, and an SKF skill with other versions: clashes.
    (out / "modskill" / "references").mkdir(parents=True)
    (out / "modskill" / "SKILL.md").write_text("---\nname: modskill\n---\n", encoding="utf-8")
    (out / "modskill" / "references" / "guide.md").write_text("# guide\n", encoding="utf-8")
    (out / "b" / "0.1.0" / "b").mkdir(parents=True)
    for new in ("modskill", "b"):
        r = validate_name("a", new, str(out), str(forge))
        assert r["first_failure"] == "collision", new
        assert r["interrupted_rename"] is False, new
    # A copy of `a`, before and after its package was renamed: a stranded rename.
    shutil.copytree(out / "a", out / "new-a", symlinks=True)
    (out / "new-a" / ".DS_Store").write_text("", encoding="utf-8")
    assert validate_name("a", "new-a", str(out), str(forge))["interrupted_rename"] is True
    (out / "new-a" / "1.0.0" / "a").rename(out / "new-a" / "1.0.0" / "new-a")
    (out / "new-a" / "1.0.0" / "new-a" / "SKILL.md.skf-tmp").write_text("x", encoding="utf-8")
    assert validate_name("a", "new-a", str(out), str(forge))["interrupted_rename"] is True
    # A file the copy could not hold makes it a folder to keep.
    (out / "new-a" / "1.0.0" / "new-a" / "NOTES.md").write_text("mine\n", encoding="utf-8")
    assert validate_name("a", "new-a", str(out), str(forge))["interrupted_rename"] is False


def _make_old_skill(out: Path) -> Path:
    """`a/1.0.0/a/{SKILL.md, references/guide.md}`; returns the package folder."""
    pkg = out / "a" / "1.0.0" / "a"
    (pkg / "references").mkdir(parents=True)
    (pkg / "SKILL.md").write_text("---\nname: a\n---\n", encoding="utf-8")
    (pkg / "references" / "guide.md").write_text("# guide\n", encoding="utf-8")
    return pkg


@pytest.mark.parametrize("shape", ["linked-new-folder", "link-on-one-side", "file-for-a-folder",
                                   "folder-for-a-file"])
def test_interrupted_rename_needs_entries_of_the_same_kind(tmp_path, shape):
    """A copy keeps each entry's kind: a link, a file for a folder or a folder
    for a file is not a copy. Each case differs from a plain copy in one way."""
    out, forge = make_dirs(tmp_path)
    (forge / "a").mkdir()
    _make_old_skill(out)
    copy = tmp_path / "copy"
    shutil.copytree(out / "a", copy)
    shutil.copytree(copy, out / "new-a")
    assert validate_name("a", "new-a", str(out), str(forge))["interrupted_rename"] is True
    shutil.rmtree(out / "new-a")
    new_pkg = copy / "1.0.0" / "a"
    if shape == "file-for-a-folder":
        shutil.rmtree(new_pkg / "references")
        (new_pkg / "references").write_text("# guide\n", encoding="utf-8")
    elif shape == "folder-for-a-file":
        (new_pkg / "SKILL.md").unlink()
        (new_pkg / "SKILL.md").mkdir()
    elif not symlinks_supported(tmp_path):
        pytest.skip("symlinks are not available")
    elif shape == "link-on-one-side":
        shutil.move(str(new_pkg / "references"), str(tmp_path / "user-refs"))
        (new_pkg / "references").symlink_to(tmp_path / "user-refs", target_is_directory=True)
    if shape == "linked-new-folder":
        (out / "new-a").symlink_to(copy, target_is_directory=True)
    else:
        copy.rename(out / "new-a")
    r = validate_name("a", "new-a", str(out), str(forge))
    assert (r["first_failure"], r["interrupted_rename"]) == ("collision", False)


@pytest.mark.parametrize("where", ["new-folder", "old-folder", "new-entry", "old-entry"])
def test_a_junction_is_a_link_to_the_copy_check(tmp_path, monkeypatch, where):
    """A Windows junction (Path.is_symlink() False, os.readlink succeeds) is a
    link, as a symlink is: never part of a copy of the old skill folder."""
    if not symlinks_supported(tmp_path):
        pytest.skip("symlinks are not available")
    out, forge = make_dirs(tmp_path)
    _make_old_skill(out)
    (out / "a" / "active").symlink_to("1.0.0", target_is_directory=True)
    shutil.copytree(out / "a", out / "new-a", symlinks=True)
    assert validate_name("a", "new-a", str(out), str(forge))["interrupted_rename"] is True
    side = out / ("new-a" if where.startswith("new") else "a")
    link = side if where.endswith("folder") else side / "1.0.0" / "a" / "references"
    shutil.move(str(link), str(tmp_path / "elsewhere"))
    link.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p != link and real_is_symlink(p))
    assert not link.is_symlink() and os.readlink(link)
    r = validate_name("a", "new-a", str(out), str(forge))
    assert (r["first_failure"], r["interrupted_rename"]) == ("collision", False)


# --- after the manifest re-key ---


def _rekeyed_rename(tmp_path, forge_moved=True, same_folder=False):
    """A rename of `a` to `new-a` that stopped after re-keying the manifest:
    the new copy is complete, the manifest names only `new-a`, and the old
    folders are still on disk."""
    out, forge = make_dirs(tmp_path)
    if same_folder:
        forge = out
    pkg = _make_old_skill(out)
    (pkg / "metadata.json").write_text('{"name": "a"}', encoding="utf-8")
    if symlinks_supported(tmp_path):
        (out / "a" / "active").symlink_to("1.0.0", target_is_directory=True)
    if not same_folder:
        (forge / "a" / "1.0.0").mkdir(parents=True)
        (forge / "a" / "1.0.0" / "provenance-map.json").write_text('{"skill_name": "a"}', encoding="utf-8")
    shutil.copytree(out / "a", out / "new-a", symlinks=True)
    (out / "new-a" / "1.0.0" / "a").rename(out / "new-a" / "1.0.0" / "new-a")
    if forge_moved and not same_folder:
        shutil.copytree(forge / "a", forge / "new-a")
    write_manifest(out, {"new-a": {"active_version": "1.0.0"}})
    return out, forge


def test_a_rename_stopped_after_the_rekey_names_its_leftovers(tmp_path):
    out, forge = _rekeyed_rename(tmp_path)
    r = validate_name("a", "new-a", str(out), str(forge))
    assert (r["valid"], r["first_failure"]) == (False, "collision")
    assert r["interrupted_after_rekey"] is True
    assert r["leftover_folders"] == [str(out / "a"), str(forge / "a")]
    assert r["interrupted_rename"] is False, "the manifest collision rules out the pre-commit fingerprint"


def test_a_forge_folder_the_rename_left_in_place_is_no_leftover(tmp_path):
    """Without a copy under the new name, that rename never moved the forge folder."""
    out, forge = _rekeyed_rename(tmp_path, forge_moved=False)
    r = validate_name("a", "new-a", str(out), str(forge))
    assert r["interrupted_after_rekey"] is True
    assert r["leftover_folders"] == [str(out / "a")]


def test_one_folder_for_both_settings_lists_the_old_folder_once(tmp_path):
    out, forge = _rekeyed_rename(tmp_path, same_folder=True)
    r = validate_name("a", "new-a", str(out), str(forge))
    assert r["leftover_folders"] == [str(out / "a")]


@pytest.mark.parametrize("shape", ["old-still-in-manifest", "new-not-in-manifest", "old-has-a-version-new-lacks",
                                   "old-has-a-file-new-lacks", "no-old-folder"])
def test_the_rekey_fingerprint_needs_the_whole_state(tmp_path, shape):
    """Each case differs from a rename stopped after the re-key in one way: a clash, or a
    pre-commit leftover, never an old folder to delete."""
    out, forge = _rekeyed_rename(tmp_path)
    if shape == "old-still-in-manifest":
        write_manifest(out, {"new-a": {}, "a": {}})
    elif shape == "new-not-in-manifest":
        write_manifest(out, {"a": {}})
    elif shape == "old-has-a-version-new-lacks":
        (out / "a" / "2.0.0" / "a").mkdir(parents=True)
    elif shape == "old-has-a-file-new-lacks":
        (out / "a" / "1.0.0" / "a" / "NOTES.md").write_text("mine\n", encoding="utf-8")
    else:
        shutil.rmtree(out / "a")
    r = validate_name("a", "new-a", str(out), str(forge))
    assert r["first_failure"] == "collision"
    assert (r["interrupted_after_rekey"], r["leftover_folders"]) == (False, [])


def test_an_old_forge_folder_with_entries_the_copy_lacks_stays(tmp_path):
    out, forge = _rekeyed_rename(tmp_path)
    (forge / "a" / "1.0.0" / "evidence-report.md").write_text("# later\n", encoding="utf-8")
    r = validate_name("a", "new-a", str(out), str(forge))
    assert r["leftover_folders"] == [str(out / "a")], "the old forge folder is not a leftover to delete"


def test_a_linked_skill_folder_is_never_a_leftover(tmp_path):
    if not symlinks_supported(tmp_path):
        pytest.skip("symlinks are not available")
    out, forge = _rekeyed_rename(tmp_path)
    shutil.move(str(out / "a"), str(tmp_path / "elsewhere"))
    (out / "a").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    r = validate_name("a", "new-a", str(out), str(forge))
    assert (r["interrupted_after_rekey"], r["leftover_folders"]) == (False, [])


def test_a_valid_name_has_no_leftovers(tmp_path):
    out, forge = make_dirs(tmp_path)
    r = validate_name("old", "fresh-name", str(out), str(forge))
    assert (r["interrupted_after_rekey"], r["leftover_folders"]) == (False, [])


def test_forge_only_collision_is_not_interrupted(tmp_path):
    """Another tool's forge folder with the new name is a genuine clash."""
    out, forge = make_dirs(tmp_path)
    (out / "bar").mkdir()
    (forge / "bar").mkdir()
    (forge / "foo").mkdir()
    r = validate_name("bar", "foo", str(out), str(forge))
    assert r["first_failure"] == "collision"
    kinds = {loc["kind"] for loc in r["checks"]["collision"]["locations"]}
    assert kinds == {"forge_data_folder"}
    assert r["interrupted_rename"] is False


@pytest.mark.parametrize("where", ["skills", "forge"])
@pytest.mark.parametrize("shape", ["file", "dangling-link"])
def test_file_or_dangling_link_at_the_new_name_collides(tmp_path, where, shape):
    out, forge = make_dirs(tmp_path)
    target = (out if where == "skills" else forge) / "new-name"
    if shape == "file":
        target.write_text("x", encoding="utf-8")
    else:
        if not symlinks_supported(tmp_path):
            pytest.skip("symlinks are not available")
        target.symlink_to(tmp_path / "nowhere", target_is_directory=True)
    assert os.path.lexists(target) and not target.is_dir()
    r = validate_name("old-name", "new-name", str(out), str(forge))
    assert r["first_failure"] == "collision"
    kind = "skills_output_folder" if where == "skills" else "forge_data_folder"
    assert r["checks"]["collision"]["locations"] == [{"kind": kind, "path": str(target)}]


def test_reserved_name_collides(tmp_path):
    """improvement-queue is SKF's own forge folder, never a skill's name."""
    out, forge = make_dirs(tmp_path)
    (out / "cognee").mkdir()
    r = validate_name("cognee", "improvement-queue", str(out), str(forge))
    assert r["valid"] is False
    assert r["first_failure"] == "collision"
    assert r["checks"]["collision"]["locations"] == [
        {"kind": "reserved", "path": str(forge / "improvement-queue")}]
    assert r["interrupted_rename"] is False
    # Folders with the name on both sides still read as a clash, never a stranded rename.
    (out / "improvement-queue").mkdir()
    (forge / "improvement-queue").mkdir()
    (forge / "cognee").mkdir()
    r = validate_name("cognee", "improvement-queue", str(out), str(forge))
    assert "reserved" in {loc["kind"] for loc in r["checks"]["collision"]["locations"]}
    assert r["interrupted_rename"] is False


# --- exit codes via subprocess ---


def test_exit_code_valid(tmp_path):
    out, forge = make_dirs(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--old-name",
            "old",
            "--new-name",
            "fresh-name",
            "--skills-output-folder",
            str(out),
            "--forge-data-folder",
            str(forge),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["valid"] is True


def test_exit_code_invalid(tmp_path):
    out, forge = make_dirs(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--old-name",
            "old",
            "--new-name",
            "Bad_Name",
            "--skills-output-folder",
            str(out),
            "--forge-data-folder",
            str(forge),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["valid"] is False
    assert payload["first_failure"] == "format"


def test_malformed_manifest_does_not_crash(tmp_path):
    out, forge = make_dirs(tmp_path)
    (out / ".export-manifest.json").write_text("{ not json")
    r = validate_name("old", "fresh-name", str(out), str(forge))
    assert r["valid"] is True
    assert "manifest_error" in r
