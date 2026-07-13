#!/usr/bin/env python3
"""Tests for skf-validate-rename-name.py — deterministic rename-target gate."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

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
