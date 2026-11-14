"""Tests for shared/scripts/skf-skill-roster.py: the roster rename-skill's select.md
section 2 reads in one call, the export manifest joined with the on-disk scan (#1180).

test-skf-rename-skill-contract.py runs select.md's documented call; these tests pin
each roster fact, each error code and the CLI.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "src" / "shared" / "scripts"
SCRIPT = SHARED / "skf-skill-roster.py"
MARK = {"generated_by": "create-skill"}


def _load_module():
    spec = importlib.util.spec_from_file_location("skf_skill_roster", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _run(*args: str, script: Path = SCRIPT) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, timeout=60)
    stream = proc.stdout if proc.stdout.strip() else proc.stderr
    return proc.returncode, json.loads(stream.decode("utf-8"))


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def _skill(skills: Path, name: str, *versions: str, marked: bool = True) -> None:
    """A versioned package per version; SKF's marker in its metadata.json unless `marked` is false."""
    for version in versions:
        _write(skills / name / version / name / "SKILL.md", f"# {name}\n")
        _write(skills / name / version / name / "metadata.json", {"name": name, **(MARK if marked else {})})


def _manifest(skills: Path, exports: dict) -> None:
    _write(skills / ".export-manifest.json", {"schema_version": "2", "exports": exports})


@pytest.fixture
def project(tmp_path):
    """An exported SKF skill, an SKF draft, a folder SKF did not generate and a manifest name with no folder."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _skill(skills, "cognee", "0.5.0", "0.6.0")
    _skill(skills, "draft", "1.0.0")
    _write(skills / "module-skill" / "SKILL.md", "# a module's own skill\n")
    forge.mkdir()
    _manifest(skills, {"cognee": {"active_version": "0.6.0", "versions": {"0.6.0": {"status": "active"}}},
                       "gone": {"active_version": "1.0.0", "versions": {"1.0.0": {"status": "active"}}}})
    return skills, forge


def test_the_roster_joins_the_manifest_and_the_scan(project):
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0
    assert result == {
        "status": "ok", "manifest_exists": True, "empty": False, "not_skf_output": ["module-skill"],
        "skills": [{"name": "cognee", "version_count": 2, "active_version": None, "in_manifest": True},
                   {"name": "draft", "version_count": 1, "active_version": None, "in_manifest": False}]}
    assert "manifest" not in result, "the manifest itself never comes back"


def test_active_version_and_version_count_are_the_scans(project):
    skills, forge = project
    try:
        (skills / "cognee" / "active").symlink_to("0.6.0", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    result, code = mod.join(str(skills), str(forge))
    assert code == 0
    scan = mod._load(mod.INVENTORY)[0].scan_inventory(str(skills), forge_data_folder=str(forge))
    expected = {e["name"]: (len(e["versions"]), e["active_version"]) for e in scan["skills"] if e["skf_skill"]}
    assert {s["name"]: (s["version_count"], s["active_version"]) for s in result["skills"]} == expected
    assert expected["cognee"] == (2, "0.6.0")


@pytest.mark.parametrize("manifest", [None, {"schema_version": "2", "exports": {}}],
                         ids=["no-manifest", "no-exports"])
def test_without_an_exported_skill_the_manifest_does_not_exist(tmp_path, manifest):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _skill(skills, "draft", "1.0.0")
    if manifest is not None:
        _write(skills / ".export-manifest.json", manifest)
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0 and (result["manifest_exists"], result["empty"]) == (False, False)
    assert [(s["name"], s["in_manifest"]) for s in result["skills"]] == [("draft", False)]


def test_a_v1_manifest_reads_migrated(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _skill(skills, "old", "1.0.0")
    _write(skills / ".export-manifest.json", {"exports": {"old": {"active_version": "1.0.0",
                                                                  "versions": ["1.0.0", "0.9.0"]}},
                                              "updated_at": "2025-01-01"})
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0 and result["manifest_exists"] is True
    assert [(s["name"], s["in_manifest"]) for s in result["skills"]] == [("old", True)]


@pytest.mark.parametrize("manifest", [
    None,
    {"schema_version": "2", "exports": {"gone": {"active_version": "1.0.0"}}},
    {"exports": {"gone": {"active_version": "1.0.0", "versions": ["1.0.0"]}}, "updated_at": "2025-01-01"},
], ids=["no-manifest", "v2-manifest", "v1-manifest"])
def test_no_skill_skf_generated_is_an_empty_roster(tmp_path, manifest):
    """The §3 halts key on `empty`: a folder SKF did not generate and a manifest name are never offered."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _skill(skills, "foreign", "1.0.0", marked=False)
    _write(skills / "module-skill" / "SKILL.md", "# a module's own skill\n")
    if manifest is not None:
        _write(skills / ".export-manifest.json", manifest)
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0 and (result["skills"], result["empty"]) == ([], True)
    assert result["not_skf_output"] == ["foreign", "module-skill"]
    assert result["manifest_exists"] is (manifest is not None)


def test_a_missing_skills_folder_lists_nothing(tmp_path):
    code, result = _run("skills", str(tmp_path / "nope"), "--forge-data-folder", str(tmp_path / "forge"))
    assert code == 0
    assert result == {"status": "ok", "manifest_exists": False, "empty": True, "not_skf_output": [], "skills": []}


@pytest.mark.parametrize("raw, needle", [
    (b"{not json", "Manifest JSON parse error"),
    (b"[]", "Manifest cannot be read"),
    (b"null", "Manifest cannot be read"),
    (b'{"exports": []}', "Manifest cannot be read"),
    (b'{"schema_version": "2", "exports": []}', "Manifest cannot be read"),
    (b'{"schema_version": "2", "exports": {"demo": "not an entry"}}', "Manifest cannot be read"),
    ('{"schema_version": "2", "exports": {"café": {}}}'.encode("cp1252"), "UnicodeDecodeError"),
], ids=["not-json", "list-root", "null-root", "v1-exports-not-object", "v2-exports-not-object",
        "entry-not-object", "not-utf8"])
def test_a_manifest_that_cannot_be_read_is_manifest_corrupt(tmp_path, raw, needle):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _skill(skills, "cognee", "1.0.0")
    _write(skills / ".export-manifest.json", raw)
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 1 and (result["status"], result["code"]) == ("error", "manifest-corrupt"), result
    assert Path(result["path"]) == skills / ".export-manifest.json"
    assert needle in result["error"]
    assert "skills" not in result


def test_a_scan_that_fails_is_scan_failed(project, monkeypatch):
    skills, forge = project
    inventory, err = mod._load(mod.INVENTORY)
    assert err is None

    def unreadable(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(inventory, "scan_inventory", unreadable)
    load = mod._load
    monkeypatch.setattr(mod, "_load", lambda name: (inventory, None) if name == mod.INVENTORY else load(name))
    result, code = mod.join(str(skills), str(forge))
    assert code == 1 and (result["status"], result["code"]) == ("error", "scan-failed")
    assert "PermissionError: denied" in result["error"]


def _copy_without(tmp_path: Path, missing: str) -> Path:
    """skf-skill-roster.py in a shared folder that lacks `missing`."""
    scripts = tmp_path / "module" / "shared" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("skf-manifest-ops.py", "skf-skill-inventory.py"):
        if name != missing:
            shutil.copy2(SHARED / name, scripts / name)
    shutil.copy2(SCRIPT, scripts / SCRIPT.name)
    return scripts / SCRIPT.name


@pytest.mark.parametrize("missing", ["skf-manifest-ops.py", "skf-skill-inventory.py"])
def test_a_missing_shared_script_is_helper_missing(tmp_path, project, missing):
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge),
                        script=_copy_without(tmp_path, missing))
    assert code == 1 and (result["status"], result["code"]) == ("error", "helper-missing")
    assert missing in result["error"] and "re-install SKF" in result["error"]


def test_the_copy_beside_its_shared_scripts_runs(tmp_path, project):
    """An installed project puts the three scripts in one folder: the roster loads the others from its own."""
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge),
                        script=_copy_without(tmp_path, "none"))
    assert code == 0 and [s["name"] for s in result["skills"]] == ["cognee", "draft"]


@pytest.mark.parametrize("args, needle", [
    ((), "required"),
    (("skills",), "skills-folder"),
    (("skills", "x"), "--forge-data-folder"),
    (("skills", "x", "--forge-data-folder", "y", "--skill", "z"), "unrecognized"),
    (("rows", "x"), "invalid choice"),
], ids=["no-subcommand", "no-folder", "no-forge-folder", "unknown-flag", "unknown-subcommand"])
def test_a_usage_error_is_json_on_stderr_with_exit_2(args, needle):
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, timeout=60)
    assert proc.returncode == 2 and proc.stdout == b""
    result = json.loads(proc.stderr.decode("utf-8"))
    assert result["status"] == "error" and result["error"].startswith("usage error:") and needle in result["error"]


def test_help_runs_in_process(capsys):
    with pytest.raises(SystemExit) as exc:
        mod.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: skf-skill-roster.py") and out.isascii()
