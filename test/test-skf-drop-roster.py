"""Tests for skf-drop-skill/scripts/drop-roster.py: the roster select.md section 2
reads in one call (the export manifest joined with the on-disk scan), and the
managed-section rows execute.md section 5 checks for the dropped skill.

The documented calls of select.md and execute.md are filled in as an agent
fills them and run against fixtures, so the prose and the CLI cannot drift.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DROP = REPO / "src" / "skf-drop-skill"
SCRIPT = DROP / "scripts" / "drop-roster.py"
SELECT = DROP / "references" / "select.md"
EXECUTE = DROP / "references" / "execute.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("drop_roster", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _run(*args: str, script: Path = SCRIPT) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(script), *args], capture_output=True, timeout=60)
    stream = proc.stdout if proc.stdout.strip() else proc.stderr
    return proc.returncode, json.loads(stream.decode("utf-8"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _skill(skills: Path, name: str, version: str, generated_by: str | None = "create-skill") -> None:
    """A versioned package; SKF's marker in its metadata.json unless generated_by is None."""
    meta = {"name": name, "version": version}
    if generated_by:
        meta["generated_by"] = generated_by
    _write(skills / name / version / name / "SKILL.md", f"# {name}\n")
    _write(skills / name / version / name / "metadata.json", json.dumps(meta))


def _manifest(skills: Path, exports: dict) -> None:
    _write(skills / ".export-manifest.json", json.dumps({"schema_version": "2", "exports": exports}))


def _entry(active: str | None, statuses: dict) -> dict:
    versions = {v: {"ides": ["claude-code"], "last_exported": f"2026-0{i + 1}-01", "status": s}
                for i, (v, s) in enumerate(statuses.items())}
    return {"active_version": active, "versions": versions}


@pytest.fixture
def project(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in ("0.9.0", "0.10.0", "0.1.0"):
        _skill(skills, "cognee", version)
    _skill(skills, "draft", "0.2.0", generated_by="quick-skill")
    _write(skills / "module-skill" / "SKILL.md", "# a module's own skill\n")
    forge.mkdir()
    _manifest(skills, {"cognee": _entry("0.10.0", {"0.10.0": "active", "0.9.0": "archived",
                                                    "0.1.0": "deprecated"}),
                       "gone": _entry("1.0.0", {"1.0.0": "active"})})
    return skills, forge


def _by_name(result: dict) -> dict:
    return {s["name"]: s for s in result["skills"]}


# --------------------------------------------------------------------------
# skills: the roster
# --------------------------------------------------------------------------

def test_the_roster_joins_the_manifest_and_the_scan(project):
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0 and result["status"] == "ok" and result["inventory"] is True
    roster = _by_name(result)
    assert list(roster) == ["cognee", "gone", "draft"], "manifest skills first, then drafts, each by name"
    assert result["not_offered"] == [{"name": "module-skill", "errors": []}]
    assert result["empty"] is False
    cognee = roster["cognee"]
    assert (cognee["in_manifest"], cognee["purge_only"], cognee["active_version"]) == (True, False, "0.10.0")
    rows = [(r["version"], r["status"], r["active"]) for r in cognee["versions"]]
    assert rows == [("0.10.0", "active", True), ("0.9.0", "archived", False), ("0.1.0", "deprecated", False)], (
        "newest first, numerically: 0.10.0 above 0.9.0")
    assert cognee["versions"][0]["last_exported"] == "2026-01-01" and cognee["versions"][0]["ides"] == ["claude-code"]
    assert cognee["counts"] == {"non_deprecated": 2, "on_disk": 3}
    draft = roster["draft"]
    assert (draft["in_manifest"], draft["purge_only"], draft["active_version"]) == (False, True, None)
    assert [(r["version"], r["status"], r["in_manifest"], r["on_disk"]) for r in draft["versions"]] == [
        ("0.2.0", None, False, True)]
    assert draft["counts"] == {"non_deprecated": 0, "on_disk": 1}
    # A manifest entry whose folders are gone is still offered, with no version on disk.
    gone = roster["gone"]
    assert [(r["version"], r["on_disk"]) for r in gone["versions"]] == [("1.0.0", False)]
    assert gone["counts"] == {"non_deprecated": 1, "on_disk": 0}


def test_a_named_skill_reads_only_that_skill(project):
    """enhancement-4: a run given its target never builds the whole roster."""
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), "--skill", "draft")
    assert code == 0
    assert [s["name"] for s in result["skills"]] == ["draft"]
    assert result["empty"] is False and result["not_offered"] == [{"name": "module-skill", "errors": []}]
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), "--skill", "module-skill")
    assert code == 0 and result["skills"] == [], "a folder SKF did not generate is never offered"
    assert [n["name"] for n in result["not_offered"]] == ["module-skill"]
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), "--skill", "nope")
    assert code == 0 and result["skills"] == [] and result["empty"] is False


def test_an_on_disk_version_the_manifest_does_not_list(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in ("1.0.0", "2.0.0"):
        _skill(skills, "demo", version)
    (skills / "demo" / ".skf-staging-3.0.0").mkdir()  # an interrupted run's staging folder
    (skills / "demo" / "notes").mkdir()  # holds no package
    _manifest(skills, {"demo": _entry("1.0.0", {"1.0.0": "active"})})
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0
    [demo] = result["skills"]
    assert [(r["version"], r["status"], r["in_manifest"], r["on_disk"]) for r in demo["versions"]] == [
        ("2.0.0", None, False, True), ("1.0.0", "active", True, True)], "no staging or package-less folder"
    assert demo["counts"] == {"non_deprecated": 1, "on_disk": 2}


def test_an_empty_folder_is_an_empty_roster(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    skills.mkdir()
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0 and (result["skills"], result["not_offered"], result["empty"]) == ([], [], True)
    _write(skills / "module-skill" / "SKILL.md", "# a module's own skill\n")
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0 and result["empty"] is True
    assert [n["name"] for n in result["not_offered"]] == ["module-skill"]


def test_a_corrupt_manifest_is_its_own_error(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _write(skills / ".export-manifest.json", "{not json")
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 1 and result["status"] == "error" and result["code"] == "manifest-corrupt"
    assert Path(result["path"]) == skills / ".export-manifest.json"
    assert "Manifest JSON parse error" in result["error"]


@pytest.mark.parametrize("raw", [
    b"[]",
    b"null",
    b'{"schema_version": "2", "exports": {"demo": "not an entry"}}',
    b'{"exports": {"demo": "not an entry"}}',
    b'{"schema_version": "2", "exports": []}',
    '{"schema_version": "2", "exports": {"caf\u00e9": {}}}'.encode("cp1252"),
], ids=["list-root", "null-root", "v2-entry-not-object", "v1-entry-not-object", "exports-not-object", "cp1252"])
def test_a_manifest_of_the_wrong_shape_or_encoding_is_corrupt(tmp_path, raw):
    """A hand-edited manifest that parses as JSON but is no manifest is manifest-corrupt, never a traceback."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    skills.mkdir()
    (skills / ".export-manifest.json").write_bytes(raw)
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 1 and result["status"] == "error" and result["code"] == "manifest-corrupt", result
    assert Path(result["path"]) == skills / ".export-manifest.json"
    assert result["error"]


@pytest.mark.parametrize("fails", ["scan_inventory", "resolve_skill"])
def test_an_inventory_helper_that_raises_offers_the_manifest_skills(project, monkeypatch, fails):
    """A scan or resolve that cannot read the folder is a helper that could not run, never a traceback."""
    skills, forge = project
    inventory, err = mod._load(mod.INVENTORY)
    assert err is None

    def unreadable(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(inventory, fails, unreadable)
    load = mod._load
    monkeypatch.setattr(mod, "_load", lambda name: (inventory, None) if name == mod.INVENTORY else load(name))
    result, code = mod.roster(str(skills), str(forge))
    assert code == 0 and result["inventory"] is False
    assert "PermissionError: denied" in result["inventory_error"]
    assert [s["name"] for s in result["skills"]] == ["cognee", "gone"] and result["not_offered"] == []
    assert [r["version"] for r in result["skills"][0]["versions"]] == ["0.10.0", "0.9.0", "0.1.0"]


def test_a_v1_manifest_reads_migrated(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    _skill(skills, "old", "1.0.0")
    _write(skills / ".export-manifest.json", json.dumps(
        {"exports": {"old": {"active_version": "1.0.0", "versions": ["1.0.0", "0.9.0"]}}, "updated_at": "2025-01-01"}))
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0
    [old] = result["skills"]
    assert [(r["version"], r["status"]) for r in old["versions"]] == [("1.0.0", "active"), ("0.9.0", "archived")]


def _copy_without(tmp_path: Path, missing: str) -> Path:
    """drop-roster.py in a copy of the module tree whose shared folder lacks `missing`."""
    root = tmp_path / "module"
    scripts = root / "shared" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("skf-manifest-ops.py", "skf-skill-inventory.py", "skf-rebuild-managed-sections.py"):
        if name != missing:
            shutil.copy2(REPO / "src" / "shared" / "scripts" / name, scripts / name)
    copy = root / "skf-drop-skill" / "scripts" / "drop-roster.py"
    copy.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT, copy)
    return copy


def test_without_the_inventory_helper_only_manifest_skills_are_offered(tmp_path, project):
    skills, forge = project
    script = _copy_without(tmp_path, "skf-skill-inventory.py")
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), script=script)
    assert code == 0 and result["inventory"] is False and "skf-skill-inventory.py" in result["inventory_error"]
    roster = _by_name(result)
    assert list(roster) == ["cognee", "gone"], "SKF cannot check a folder the manifest does not list"
    assert result["not_offered"] == []
    cognee = roster["cognee"]
    assert [r["version"] for r in cognee["versions"]] == ["0.10.0", "0.9.0", "0.1.0"]
    assert cognee["counts"] == {"non_deprecated": 2, "on_disk": None} and cognee["layout"] is None


@pytest.mark.parametrize("missing, args", [
    ("skf-manifest-ops.py", ["skills", "{skills}", "--forge-data-folder", "{forge}"]),
    ("skf-rebuild-managed-sections.py", ["rows", "--skill", "x", "CLAUDE.md"]),
], ids=["skills", "rows"])
def test_a_missing_shared_script_is_a_helper_error(tmp_path, project, missing, args):
    skills, forge = project
    script = _copy_without(tmp_path, missing)
    args = [a.format(skills=skills, forge=forge) for a in args]
    code, result = _run(*args, script=script)
    assert code == 1 and result["code"] == "helper-missing" and missing in result["error"]


# --------------------------------------------------------------------------
# rows: what the context files still list for the dropped skill
# --------------------------------------------------------------------------

def _section(rows: dict) -> str:
    body = ["[SKF Skills]|2 skills|0 stack", "|IMPORTANT: Prefer documented APIs over training data."]
    for name, version in rows:
        body += ["|", f"|[{name} v{version}]|root: .claude/skills/{name}/", f"|IMPORTANT: {name} secret text."]
    return "<!-- SKF:BEGIN updated:2026-01-01 -->\n" + "\n".join(body) + "\n<!-- SKF:END -->\n"


def test_rows_lists_the_skill_by_file_and_version_without_snippet_text(tmp_path):
    claude, agents = tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md"
    _write(claude, "# Project\n\n" + _section([("cognee", "0.6.0"), ("zod", "3.0.0")]))
    _write(agents, "# Agents\n\n" + _section([("cognee", "0.5.0")]))
    code, result = _run("rows", "--skill", "cognee", str(claude), str(agents), str(tmp_path / "missing.md"))
    assert code == 0 and result["status"] == "ok" and result["versions"] is None
    assert [(Path(r["file"]).name, r["version"]) for r in result["rows"]] == [("CLAUDE.md", "0.6.0"),
                                                                               ("AGENTS.md", "0.5.0")]
    assert result["unchecked"] == [], "a missing file holds no row"
    assert "secret text" not in json.dumps(result), "a row's snippet text never comes back"
    code, result = _run("rows", "--skill", "cognee", "--version", "0.5.0", str(claude), str(agents))
    assert code == 0 and [r["version"] for r in result["rows"]] == ["0.5.0"] and result["versions"] == ["0.5.0"]
    code, result = _run("rows", "--skill", "gone", str(claude))
    assert code == 0 and result["rows"] == []


def test_rows_names_a_file_it_cannot_check(tmp_path):
    malformed, binary = tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md"
    _write(malformed, "# Project\n<!-- SKF:BEGIN updated:2026-01-01 -->\n|[cognee v1.0.0]|root: x/\n")
    binary.write_bytes("# caf\xe9\n".encode("cp1252"))
    code, result = _run("rows", "--skill", "cognee", str(malformed), str(binary))
    assert code == 0 and result["rows"] == []
    [bad, undecodable] = result["unchecked"]
    assert Path(bad["file"]).name == "CLAUDE.md" and bad["error"].startswith("malformed markers:")
    assert Path(undecodable["file"]).name == "AGENTS.md" and "not UTF-8" in undecodable["error"]


# --------------------------------------------------------------------------
# The CLI and the documented calls
# --------------------------------------------------------------------------

def test_a_usage_error_is_json_with_exit_2():
    code, result = _run("skills")
    assert code == 2 and result["status"] == "error" and result["error"].startswith("usage error:")
    code, result = _run("rows", "--skill", "x")
    assert code == 2 and "context-file" in result["error"]


def test_help_runs_in_process(capsys):
    with pytest.raises(SystemExit) as exc:
        mod.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: drop-roster.py") and out.isascii()


def _documented(path: Path, op: str) -> list[str]:
    """The fenced `uv run {dropRosterHelper} <op>` calls of a step file."""
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith(f"uv run {{dropRosterHelper}} {op} ")]


def _argv(call: str, values: dict, keep_group: bool) -> list[str]:
    """A documented call filled in as an agent fills it, its `[...]` group kept or left out."""
    call = call.removeprefix("uv run {dropRosterHelper} ")
    call = re.sub(r"\[([^\[\]]+)\]", lambda m: m.group(1) if keep_group else "", call)
    argv = []
    for word in shlex.split(re.sub(r"\{([^{}]+)\}", lambda m: "@@" + m.group(1).replace(" ", "_") + "@@", call)):
        whole = re.fullmatch(r"@@([^@]+)@@", word)
        value = values[whole.group(1)] if whole else None
        if isinstance(value, list):
            argv.extend(value)
        else:
            argv.append(re.sub(r"@@([^@]+)@@", lambda m: values[m.group(1)], word))
    return argv


@pytest.mark.parametrize("keep_group", [False, True], ids=["whole-roster", "named-skill"])
def test_select_runs_the_roster_it_documents(project, keep_group):
    skills, forge = project
    [call] = _documented(SELECT, "skills")
    argv = _argv(call, {"skills_output_folder": str(skills), "forge_data_folder": str(forge),
                        "skill_name": "cognee"}, keep_group)
    code, result = _run(*argv)
    assert code == 0, result
    assert [s["name"] for s in result["skills"]] == (["cognee"] if keep_group else ["cognee", "gone", "draft"])


@pytest.mark.parametrize("keep_group", [False, True], ids=["skill-level", "version-level"])
def test_execute_runs_the_rows_check_it_documents(tmp_path, keep_group):
    claude = tmp_path / "CLAUDE.md"
    _write(claude, _section([("cognee", "0.6.0"), ("cognee", "0.5.0")]))
    [call] = _documented(EXECUTE, "rows")
    argv = _argv(call, {"target_skill": "cognee", "version": "0.5.0",
                        "each_file_in_context_files_updated,_quoted": [str(claude)]}, keep_group)
    code, result = _run(*argv)
    assert code == 0, result
    assert [r["version"] for r in result["rows"]] == (["0.5.0"] if keep_group else ["0.6.0", "0.5.0"])
