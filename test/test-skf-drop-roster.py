"""Tests for skf-drop-skill/scripts/drop-roster.py: the roster select.md section 2
and report.md section 1 read in one call (the export manifest joined with the
on-disk scan, with the version select.md section 7 names to keep and the
versions section 6 [O] Older versions drops), the
managed-section rows, the headless-purge guard SKILL.md On Activation reads
from the resolver JSON, and the final-state check execute.md section 5 runs
(#1158).

The documented calls of SKILL.md, select.md, execute.md and report.md are
filled in as an agent fills them and run against fixtures, so the prose and
the CLI cannot drift.
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
SKILL = DROP / "SKILL.md"
SELECT = DROP / "references" / "select.md"
EXECUTE = DROP / "references" / "execute.md"
REPORT = DROP / "references" / "report.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("drop_roster", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


def _run(*args: str, script: Path = SCRIPT, stdin: bytes | None = None) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, timeout=60)
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
    for name in ("skf-manifest-ops.py", "skf-skill-inventory.py", "skf-rebuild-managed-sections.py",
                 "skf-update-active-symlink.py"):
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
def test_execute_runs_the_final_state_check_it_documents(tmp_path, keep_group):
    """#1158: §5 checks the manifest and the rows in one call; the rows of the dropped version fail it."""
    skills = tmp_path / "skills"
    _manifest(skills, {"cognee": _entry("0.6.0", {"0.6.0": "deprecated", "0.5.0": "deprecated"})})
    claude = tmp_path / "CLAUDE.md"
    _write(claude, _section([("cognee", "0.6.0"), ("cognee", "0.5.0")]))
    assert _documented(EXECUTE, "rows") == [], "the rows check is part of verify"
    [call] = _documented(EXECUTE, "verify")
    argv = _argv(call, {"skills_output_folder": str(skills), "target_skill": "cognee", "drop_mode": "deprecate",
                        "version": "0.5.0", "each_file_in_context_files_updated,_quoted": [str(claude)]}, keep_group)
    code, result = _run(*argv)
    assert code == 0, result
    assert [(f["check"], f["detail"]) for f in result["failures"]] == [
        ("context-rows", f"{claude} still lists `cognee` v{v}") for v in (["0.5.0"] if keep_group else ["0.6.0", "0.5.0"])]


def test_report_reads_the_remaining_versions_it_documents(project):
    """#1158: report.md §1 lists the manifest versions from the roster, never a folder the manifest does not list."""
    skills, forge = project
    (skills / "cognee" / "0.11.0" / "cognee").mkdir(parents=True)  # a stray version folder
    [call] = _documented(REPORT, "skills")
    code, result = _run(*_argv(call, {"skills_output_folder": str(skills), "forge_data_folder": str(forge),
                                      "target_skill": "cognee"}, True))
    assert code == 0, result
    [cognee] = result["skills"]
    shown = [(r["version"], r["status"], r["active"]) for r in cognee["versions"] if r["in_manifest"]]
    assert shown == [("0.10.0", "active", True), ("0.9.0", "archived", False), ("0.1.0", "deprecated", False)]
    report = REPORT.read_text(encoding="utf-8")
    assert "affected-versions" not in report and "{manifestOpsHelper}" not in report
    assert "whose `in_manifest` is true" in report
    assert "(unknown: {the result's error, or its first stderr line})" in report, "a roster that fails is shown"


# --------------------------------------------------------------------------
# keep_candidate: the version select.md section 7 names to keep
# --------------------------------------------------------------------------

def test_keep_candidate_is_the_version_after_the_active_one(project):
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0
    assert {s["name"]: s["keep_candidate"] for s in result["skills"]} == {
        "cognee": "0.9.0", "gone": None, "draft": None}, "no folder on disk, or no active version, keeps nothing"


@pytest.mark.parametrize("active, statuses, on_disk, expected", [
    ("0.6.0", {"0.6.0": "active", "0.5.0": "deprecated", "0.4.0": "archived"}, ("0.6.0", "0.5.0", "0.4.0"), "0.4.0"),
    ("0.6.0", {"0.6.0": "active", "0.5.0": "archived", "0.4.0": "archived"}, ("0.6.0", "0.4.0"), "0.4.0"),
    ("0.6.0", {"0.6.0": "active", "0.5.0": "archived"}, ("0.7.0", "0.6.0", "0.5.0"), "0.5.0"),
    ("0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"}, ("0.6.0", "0.5.0"), None),
], ids=["skips-deprecated", "skips-not-on-disk", "skips-unexported-folder", "none-qualifies"])
def test_keep_candidate_follows_the_one_rule(tmp_path, active, statuses, on_disk, expected):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in on_disk:
        _skill(skills, "demo", version)
    _manifest(skills, {"demo": _entry(active, statuses)})
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), "--skill", "demo")
    assert code == 0
    assert result["skills"][0]["keep_candidate"] == expected


@pytest.mark.parametrize("missing", ["skf-skill-inventory.py", "skf-update-active-symlink.py"])
def test_keep_candidate_is_null_without_its_helpers(tmp_path, project, missing):
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), script=_copy_without(tmp_path, missing))
    assert code == 0
    assert {s["name"]: s["keep_candidate"] for s in result["skills"]}["cognee"] is None


# --------------------------------------------------------------------------
# older_versions: what select.md section 6 [O] Older versions drops (#1160)
# --------------------------------------------------------------------------

def test_older_versions_leave_out_the_active_and_the_deprecated(project):
    skills, forge = project
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge))
    assert code == 0
    assert {s["name"]: s["older_versions"] for s in result["skills"]} == {
        "cognee": ["0.9.0"], "gone": [], "draft": []}, "a draft has no manifest version to drop"


@pytest.mark.parametrize("inventory", [True, False], ids=["with-the-scan", "manifest-rows-alone"])
def test_older_versions_are_the_manifest_versions_newest_first(tmp_path, inventory):
    """Neither the active_version nor a version whose status is "active" or "deprecated"; a manifest version with no
    folder is listed too, and the list is the same when the roster holds the manifest rows alone."""
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in ("0.11.0", "0.10.0", "0.9.0", "0.3.0", "0.1.0"):
        _skill(skills, "demo", version)
    forge.mkdir()
    _manifest(skills, {"demo": _entry("0.10.0", {"0.2.0": "archived", "0.11.0": "archived", "0.10.0": "active",
                                                  "0.9.0": "archived", "0.3.0": "active", "0.1.0": "deprecated"})})
    script = SCRIPT if inventory else _copy_without(tmp_path, "skf-skill-inventory.py")
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), "--skill", "demo", script=script)
    assert code == 0 and result["inventory"] is inventory
    [demo] = result["skills"]
    assert demo["older_versions"] == ["0.11.0", "0.9.0", "0.2.0"]


def test_older_versions_are_empty_when_only_the_active_one_is_left(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    for version in ("0.6.0", "0.5.0"):
        _skill(skills, "demo", version)
    forge.mkdir()
    _manifest(skills, {"demo": _entry("0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"})})
    code, result = _run("skills", str(skills), "--forge-data-folder", str(forge), "--skill", "demo")
    assert code == 0 and result["skills"][0]["older_versions"] == []


# --------------------------------------------------------------------------
# activation: the headless-purge guard, from the resolver JSON
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw, forbidden", [
    ('{"workflow": {"forbid_purge_in_headless": true}}', True),
    ('{"workflow": {"forbid_purge_in_headless": false}}', True),
    ('{"workflow": {"forbid_purge_in_headless": "false"}}', True),
    ('{"workflow": {"forbid_purge_in_headless": "x"}}', True),
    ('{"workflow": {"forbid_purge_in_headless": ""}}', False),
    ('{"workflow": {"on_complete": ""}}', False),
    ("{}", False),
    ('{"workflow.forbid_purge_in_headless": "true"}', True),
    ('{"workflow.forbid_purge_in_headless": ""}', False),
], ids=["true", "false", "string-false", "string-x", "empty", "absent", "no-workflow", "dotted", "dotted-empty"])
def test_activation_reads_any_value_but_the_empty_string_as_on(raw, forbidden):
    code, result = _run("activation", stdin=raw.encode("utf-8"))
    assert (code, result) == (0, {"status": "ok", "purge_forbidden": forbidden})


def test_activation_reads_a_fact_path_that_is_not_utf8():
    raw = b'{"workflow": {"forbid_purge_in_headless": "", "persistent_facts": ["file:/p/caf\xe9.md"]}}'
    code, result = _run("activation", stdin=raw)
    assert (code, result["purge_forbidden"]) == (0, False)


@pytest.mark.parametrize("value, forbidden", [('""', False), ("true", True)], ids=["empty", "true"])
def test_activation_drops_a_leading_bom_as_the_resolver_does(value, forbidden):
    """A file staged with a UTF-8 BOM reads as the JSON after it, not as stdin that is no JSON."""
    raw = b"\xef\xbb\xbf" + f'{{"workflow": {{"forbid_purge_in_headless": {value}}}}}'.encode("utf-8")
    code, result = _run("activation", stdin=raw)
    assert (code, result) == (0, {"status": "ok", "purge_forbidden": forbidden})


@pytest.mark.parametrize("raw", [b"", b"not json", b"[]", b'"true"', b'{"workflow": "true"}'],
                         ids=["empty", "not-json", "list", "string", "workflow-not-object"])
def test_activation_refuses_what_is_not_the_resolver_json(raw):
    """The caller counts a failed call as on: the guard fails closed."""
    code, result = _run("activation", stdin=raw)
    assert code == 1 and result["status"] == "error" and result["code"] == "bad-input"


def test_skill_md_binds_the_guard_from_the_call_it_documents(tmp_path):
    [call] = _documented(SKILL, "activation")
    assert call == 'uv run {dropRosterHelper} activation < "{run_dir}/customization.json"'
    staged = tmp_path / "customization.json"
    staged.write_bytes(b'{"workflow": {"forbid_purge_in_headless": false, "on_complete": ""}}\n')
    code, result = _run("activation", stdin=staged.read_bytes())
    assert (code, result["purge_forbidden"]) == (0, True)
    activation = SKILL.read_text(encoding="utf-8").split("## On Activation", 1)[1]
    assert "Bind `{forbidPurgeInHeadless}` ← its `purge_forbidden`" in activation
    assert "a non-zero exit, or no JSON, counts as on" in activation


# --------------------------------------------------------------------------
# verify: the state a drop should leave
# --------------------------------------------------------------------------

def _verify(skills: Path, mode: str, *args: str, script: Path = SCRIPT) -> tuple[int, dict]:
    return _run("verify", str(skills), "--skill", "cognee", "--mode", mode, *args, script=script)


@pytest.mark.parametrize("mode", ["deprecate", "purge"])
@pytest.mark.parametrize("statuses, failed", [
    ({"0.6.0": "active", "0.5.0": "deprecated"}, None),
    ({"0.6.0": "active", "0.5.0": "archived"}, "the manifest lists `cognee` 0.5.0 as `archived`, not `deprecated`"),
    ({"0.6.0": "active"}, "the manifest's `cognee` entry has no 0.5.0"),
    (None, "the manifest has no `cognee` entry"),
], ids=["met", "not-deprecated", "version-gone", "entry-gone"])
def test_verify_a_version_drop(tmp_path, mode, statuses, failed):
    skills = tmp_path / "skills"
    _manifest(skills, {} if statuses is None else {"cognee": _entry("0.6.0", statuses)})
    code, result = _verify(skills, mode, "--version", "0.5.0")
    assert code == 0 and result["status"] == "ok"
    fix = f"correct the `cognee` entry of `{skills / '.export-manifest.json'}` by hand"
    assert result["failures"] == ([] if failed is None else [{"check": "manifest", "detail": failed, "manual_fix": fix}])


@pytest.mark.parametrize("mode, exports, failed", [
    ("deprecate", {"cognee": _entry("0.6.0", {"0.6.0": "deprecated", "0.5.0": "deprecated"})}, []),
    ("deprecate", {"cognee": _entry("0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"})},
     ["the manifest lists `cognee` 0.6.0 as `active`, not `deprecated`"]),
    ("deprecate", {}, ["the manifest has no `cognee` entry"]),
    ("purge", {"other": _entry("1.0.0", {"1.0.0": "active"})}, []),
    ("purge", {"cognee": _entry("0.6.0", {"0.6.0": "deprecated"})}, ["the manifest still has a `cognee` entry"]),
], ids=["deprecate-met", "deprecate-unmet", "deprecate-entry-gone", "purge-met", "purge-unmet"])
def test_verify_a_whole_skill_drop(tmp_path, mode, exports, failed):
    """A draft purge expects no entry too: the manifest never listed it."""
    skills = tmp_path / "skills"
    _manifest(skills, exports)
    code, result = _verify(skills, mode)
    assert code == 0
    assert [f["detail"] for f in result["failures"]] == failed
    assert {f["check"] for f in result["failures"]} <= {"manifest"}


@pytest.mark.parametrize("raw", [b"{not json", '{"exports": {"caf\u00e9": {}}}'.encode("cp1252")],
                         ids=["not-json", "cp1252"])
def test_verify_a_manifest_it_cannot_read_is_a_failure(tmp_path, raw):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / ".export-manifest.json").write_bytes(raw)
    code, result = _verify(skills, "purge")
    assert code == 0
    [failure] = result["failures"]
    assert failure["check"] == "manifest" and failure["detail"].startswith(f"{skills / '.export-manifest.json'} cannot be read")


def test_verify_lists_each_row_left_and_each_file_it_cannot_check(tmp_path):
    skills = tmp_path / "skills"
    _manifest(skills, {"cognee": _entry("0.6.0", {"0.6.0": "active", "0.5.0": "deprecated"})})
    claude, agents, missing = tmp_path / "CLAUDE.md", tmp_path / "AGENTS.md", tmp_path / ".cursorrules"
    _write(claude, _section([("cognee", "0.6.0"), ("cognee", "0.5.0")]))
    agents.write_bytes("# caf\xe9\n".encode("cp1252"))
    code, result = _verify(skills, "deprecate", "--version", "0.5.0", str(claude), str(agents), str(missing))
    assert code == 0
    left, unchecked = result["failures"]
    assert left == {"check": "context-rows", "detail": f"{claude} still lists `cognee` v0.5.0",
                    "manual_fix": "re-run `[EX] Export Skill`"}
    assert (unchecked["check"], unchecked["manual_fix"]) == ("context-rows", "re-run `[EX] Export Skill`")
    assert unchecked["detail"].startswith(f"{agents} could not be checked: {agents} is not UTF-8 text")
    # The context files may come before the flags as well as after them.
    code, before = _run("verify", str(skills), str(claude), "--skill", "cognee", "--mode", "deprecate", "--version", "0.5.0")
    assert code == 0 and [f["detail"] for f in before["failures"]] == [f"{claude} still lists `cognee` v0.5.0"]


@pytest.mark.parametrize("missing, files", [("skf-manifest-ops.py", False), ("skf-rebuild-managed-sections.py", True)])
def test_verify_without_a_helper_exits_1(tmp_path, project, missing, files):
    skills, _ = project
    claude = tmp_path / "CLAUDE.md"
    _write(claude, _section([("cognee", "0.6.0")]))
    code, result = _verify(skills, "purge", *([str(claude)] if files else []), script=_copy_without(tmp_path, missing))
    assert code == 1 and result["code"] == "helper-missing" and missing in result["error"]


def test_verify_usage_errors_exit_2(tmp_path):
    code, result = _run("verify", str(tmp_path), "--skill", "cognee")
    assert code == 2 and "--mode" in result["error"]
    code, result = _run("verify", str(tmp_path), "--skill", "cognee", "--mode", "remove")
    assert code == 2 and result["error"].startswith("usage error:")
