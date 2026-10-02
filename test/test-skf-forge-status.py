#!/usr/bin/env python3
"""Tests for src/skf-forger/scripts/forge-status.py.

Ferris's WS (#608 determinism-5) reads every skill's stage and next code
from one call of this script instead of globbing the briefs and the test
results by hand:
  - the stage and next-code tables: a brief gets CS, no verdict, INCONCLUSIVE
    and PASS_WITH_DRIFT get TS, FAIL gets US --from-test-report, a PASS whose
    active version is not exported gets EX, and an exported PASS gets none
  - a real skills folder: the inventory's SKF skills (a skill SKF did not
    generate is left out), their active version, the flat layout's verdict
    beside the forge folder, and the export manifest
  - a stopped chain's offer replaces the next code of the skill it names, or
    comes last when it names none; a later test drops the offer
  - the inventory script is found under the project root, installed before
    dev, and one that is missing or cannot run, like a test result that does
    not parse, is a warning, never a crash
  - the call WS documents runs as written, and WS reads only fields the
    script prints and restates none of its rules
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCRIPT = SRC / "skf-forger" / "scripts" / "forge-status.py"
JOURNAL = SRC / "skf-forger" / "scripts" / "pipeline-journal.py"
INVENTORY = SRC / "shared" / "scripts" / "skf-skill-inventory.py"
FORGER_SKILL = SRC / "skf-forger" / "SKILL.md"

spec = importlib.util.spec_from_file_location("skf_forge_status", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OLD_RUN = "20260101T000000Z-0000beef"  # a test run long before any journal these tests start


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value).encode("utf-8"))


def _link_active(active_link: Path, version: str) -> None:
    """active -> version, with the Windows junction fallback test-skf-skill-inventory.py uses."""
    try:
        active_link.symlink_to(version)
        return
    except OSError as e:
        if os.name != "nt" or getattr(e, "winerror", None) not in (1314, 5):
            raise
    abs_target = (active_link.parent / version).resolve()
    done = subprocess.run(["cmd", "/c", "mklink", "/J", str(active_link), str(abs_target)],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr or done.stdout


def make_skill(skills: Path, name: str, version: str = "1.0.0", marked: bool = True) -> None:
    """A versioned skill; `marked` gives its metadata.json the SKF marker."""
    package = skills / name / version / name
    package.mkdir(parents=True)
    package.joinpath("SKILL.md").write_bytes(f"---\nname: {name}\n---\n# {name}\n".encode("utf-8"))
    meta = {"name": name, "version": version, **({"generated_by": "create-skill"} if marked else {})}
    _write_json(package / "metadata.json", meta)
    _link_active(skills / name / "active", version)


def make_flat_skill(skills: Path, name: str) -> None:
    group = skills / name
    group.mkdir(parents=True)
    group.joinpath("SKILL.md").write_bytes(f"---\nname: {name}\n---\n# {name}\n".encode("utf-8"))
    _write_json(group / "metadata.json", {"name": name, "generated_by": "quick-skill"})


def verdict(forge: Path, name: str, version: str | None, result: str) -> None:
    folder = forge / name if version is None else forge / name / version
    _write_json(folder / mod.TEST_RESULT, {"runId": OLD_RUN, "summary": {"result": result}})


def brief(forge: Path, name: str) -> None:
    (forge / name).mkdir(parents=True, exist_ok=True)
    (forge / name / mod.BRIEF).write_bytes(f"name: {name}\n".encode("utf-8"))


def export(skills: Path, versions: dict) -> None:
    _write_json(skills / ".export-manifest.json", {
        "schema_version": "2", "updated_at": "2026-01-01T00:00:00Z",
        "exports": {name: {"active_version": v, "versions": {v: {"last_exported": "2026-01-01", "status": "active"}}}
                    for name, v in versions.items()}})


def run(tmp_path: Path, *, inventory: Path | None = INVENTORY) -> dict:
    """One call, with `--inventory` unless it is None (then the project-root probe finds it)."""
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(tmp_path), "--skills-output-folder",
         str(tmp_path / "skills"), "--forge-data-folder", str(tmp_path / "forge"),
         *(["--inventory", str(inventory)] if inventory else []),
         "--run-root", str(tmp_path / "runs"), "--result-dir", str(tmp_path / "sidecar")],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


def by_name(result: dict) -> dict:
    return {s["name"]: s for s in result["skills"]}


# --------------------------------------------------------------------------
# The stage and next-code tables
# --------------------------------------------------------------------------


@pytest.mark.parametrize("verdict_,exported,stage,nxt", [
    pytest.param(None, None, "compiled", "TS x", id="no-verdict"),
    pytest.param("INCONCLUSIVE", None, "tested", "TS x", id="inconclusive"),
    pytest.param("PASS_WITH_DRIFT", None, "tested", "TS x", id="pass-with-drift"),
    pytest.param("FAIL", None, "tested", "US x --from-test-report", id="fail"),
    pytest.param("FAIL", "1.0.0", "exported", "US x --from-test-report", id="exported-then-failed"),
    pytest.param("PASS", None, "tested", "EX x", id="pass-not-exported"),
    pytest.param("PASS", "0.9.0", "tested", "EX x", id="pass-older-version-exported"),
    pytest.param("PASS", "1.0.0", "exported", None, id="pass-exported"),
    pytest.param(None, "1.0.0", "exported", "TS x", id="exported-untested"),
])
def test_stage_and_next_code(verdict_, exported, stage, nxt):
    status = mod.skill_status("x", "1.0.0", verdict_, exported)
    assert (status["stage"], status["next"]) == (stage, nxt)


def test_a_verdict_reads_in_either_spelling(tmp_path):
    for name, written in (("a", "pass-with-drift"), ("b", "PASS_WITH_DRIFT"), ("c", " fail "), ("d", "maybe")):
        verdict(tmp_path, name, "1.0.0", written)
    assert [mod.read_verdict(tmp_path, n, "1.0.0") for n in "abcd"] == [
        "PASS_WITH_DRIFT", "PASS_WITH_DRIFT", "FAIL", None]
    assert mod.read_verdict(tmp_path, "missing", "1.0.0") is None


# --------------------------------------------------------------------------
# A real skills folder
# --------------------------------------------------------------------------


@pytest.fixture()
def forge_tree(tmp_path):
    skills, forge = tmp_path / "skills", tmp_path / "forge"
    skills.mkdir()
    brief(forge, "alpha")  # briefed only
    for name in ("beta", "gamma", "delta", "zeta", "eta"):
        make_skill(skills, name)
        brief(forge, name)  # a compiled skill keeps its brief: the skill wins
    verdict(forge, "gamma", "1.0.0", "FAIL")
    verdict(forge, "delta", "1.0.0", "INCONCLUSIVE")
    verdict(forge, "zeta", "1.0.0", "PASS")
    verdict(forge, "eta", "1.0.0", "PASS")
    verdict(forge, "beta", "0.9.0", "PASS")  # an older version's verdict is not the active one's
    make_flat_skill(skills, "iota")
    verdict(forge, "iota", None, "PASS")
    make_skill(skills, "foreign", marked=False)
    export(skills, {"eta": "1.0.0", "iota": "flat"})
    return tmp_path


def test_each_skill_gets_its_stage_and_next_code(forge_tree):
    result = run(forge_tree)
    assert result["status"] == "ok" and result["warnings"] == [] and result["pipeline"] is None
    got = {name: (s["stage"], s["next"]) for name, s in by_name(result).items()}
    assert got == {
        "alpha": ("briefed", "CS alpha"),
        "beta": ("compiled", "TS beta"),
        "gamma": ("tested", "US gamma --from-test-report"),
        "delta": ("tested", "TS delta"),
        "zeta": ("tested", "EX zeta"),
        "eta": ("exported", None),
        "iota": ("exported", None),
    }
    assert [s["name"] for s in result["skills"]] == sorted(got)
    assert result["recommended"] == ["CS alpha", "TS beta", "TS delta", "US gamma --from-test-report", "EX zeta"]
    eta = by_name(result)["eta"]
    assert (eta["active_version"], eta["verdict"], eta["exported_version"]) == ("1.0.0", "PASS", "1.0.0")


def test_no_skills_folder_yet_lists_the_briefs(tmp_path):
    brief(tmp_path / "forge", "alpha")
    result = run(tmp_path)
    assert result["warnings"] == []
    assert [(s["name"], s["stage"], s["next"]) for s in result["skills"]] == [("alpha", "briefed", "CS alpha")]


def test_an_empty_project_has_nothing_to_show(tmp_path):
    result = run(tmp_path)
    assert (result["skills"], result["recommended"], result["pipeline"], result["warnings"]) == ([], [], None, [])


# --------------------------------------------------------------------------
# A stopped chain's offer
# --------------------------------------------------------------------------


def _start_chain(tmp_path: Path, invocation: str) -> dict:
    p = subprocess.run([sys.executable, str(JOURNAL), "start", "--run-root", str(tmp_path / "runs")],
                       input=invocation + "\n", capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)


def test_the_offer_replaces_the_next_code_of_the_skill_it_names(forge_tree):
    _start_chain(forge_tree, "maintain gamma")  # killed before AS finished
    result = run(forge_tree)
    gamma = by_name(result)["gamma"]
    assert result["pipeline"]["skill_name"] == "gamma" and result["pipeline"]["offer"] == "resume"
    assert gamma["next"] == result["pipeline"]["route"] == "resume at AS: AS US TS EX"
    assert "US gamma --from-test-report" not in result["recommended"]
    assert result["recommended"].count(gamma["next"]) == 1


def test_an_offer_that_names_no_skill_comes_last(forge_tree):
    _start_chain(forge_tree, "QS[cognee] TS EX")
    result = run(forge_tree)
    assert result["pipeline"]["skill_name"] is None
    assert result["recommended"][-1] == result["pipeline"]["route"] == "resume at QS: QS TS EX"


def test_a_later_test_drops_the_offer(forge_tree):
    _start_chain(forge_tree, "maintain gamma")
    _write_json(forge_tree / "forge" / "gamma" / "1.0.0" / mod.TEST_RESULT,
                {"runId": "20991231T000000Z-0000cafe", "summary": {"result": "PASS"}})
    result = run(forge_tree)
    assert result["pipeline"] is None
    assert by_name(result)["gamma"]["next"] == "EX gamma"


# --------------------------------------------------------------------------
# What it cannot read
# --------------------------------------------------------------------------


def test_an_inventory_that_cannot_run_lists_the_briefs_without_a_stage(forge_tree):
    result = run(forge_tree, inventory=forge_tree / "missing" / "skf-skill-inventory.py")
    [warning] = result["warnings"]
    assert warning.startswith("inventory_unavailable: ") and "not found" in warning
    assert all(s["stage"] is None and s["next"] is None for s in result["skills"])
    assert [s["name"] for s in result["skills"]] == ["alpha", "beta", "delta", "eta", "gamma", "zeta"]


def _install_inventory(project_root: Path, probe: str) -> None:
    target = project_root / probe
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVENTORY, target)


@pytest.mark.parametrize("probes", [
    pytest.param(("src/shared/scripts/skf-skill-inventory.py",), id="dev"),
    pytest.param(("_bmad/skf/shared/scripts/skf-skill-inventory.py",), id="installed"),
])
def test_the_inventory_is_found_under_the_project_root(forge_tree, probes):
    for probe in probes:
        _install_inventory(forge_tree, probe)
    result = run(forge_tree, inventory=None)
    assert result["warnings"] == []
    assert by_name(result)["gamma"]["next"] == "US gamma --from-test-report"


def test_the_installed_inventory_comes_before_the_dev_one(tmp_path):
    for probe in mod.INVENTORY_PROBES:
        _install_inventory(tmp_path, probe)
    assert mod.find_inventory(tmp_path).as_posix() == (tmp_path / mod.INVENTORY_PROBES[0]).as_posix()
    assert mod.INVENTORY_PROBES[0].startswith("_bmad/skf/") and mod.INVENTORY_PROBES[1].startswith("src/")


def test_no_inventory_under_the_project_root_is_a_warning(forge_tree):
    result = run(forge_tree, inventory=None)
    assert result["warnings"] == ["inventory_unavailable: not found"]
    assert all(s["stage"] is None for s in result["skills"])


def test_an_inventory_error_is_a_warning(tmp_path):
    (tmp_path / "skills").write_bytes(b"not a folder")
    broken = tmp_path / "inventory.py"
    broken.write_bytes(b"import sys\nsys.stderr.write('boom\\n')\nsys.exit(1)\n")
    result = run(tmp_path, inventory=broken)
    assert result["warnings"] == ["inventory_unavailable: inventory.py printed no JSON: boom"]


def test_an_unreadable_test_result_is_a_warning(forge_tree):
    (forge_tree / "forge" / "zeta" / "1.0.0" / mod.TEST_RESULT).write_bytes(b"{not json")
    result = run(forge_tree)
    [warning] = result["warnings"]
    assert warning.startswith("test_result_unreadable: ") and "zeta/1.0.0" in warning
    assert by_name(result)["zeta"]["next"] == "TS zeta"


# --------------------------------------------------------------------------
# The script and the prose that calls it
# --------------------------------------------------------------------------


def test_header_and_help():
    text = _read(SCRIPT)
    assert re.search(r'^# requires-python = ">=3\.11"$', text, re.M)
    p = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, encoding="utf-8",
                       timeout=60)
    assert p.returncode == 0 and "--project-root" in p.stdout and "--inventory" in p.stdout


def _ws() -> str:
    return _read(FORGER_SKILL).split("- **WS**:", 1)[1].split("## Pipeline Mode", 1)[0]


def test_the_ws_call_runs_as_written(forge_tree):
    """The call names the project root, and the script finds the inventory under it: WS probes nothing."""
    [call] = re.findall(r"`(uv run scripts/forge-status\.py [^`]+)`", _ws())
    words = shlex.split(call)
    assert words[:3] == ["uv", "run", "scripts/forge-status.py"]
    _install_inventory(forge_tree, mod.INVENTORY_PROBES[1])
    values = {"{skills_output_folder}": str(forge_tree / "skills"), "{forge_data_folder}": str(forge_tree / "forge"),
              "{project-root}": str(forge_tree), "{sidecar_path}": str(forge_tree)}
    argv = []
    for word in words[3:]:
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        assert not re.search(r"[{<][a-z_-]+[}>]", word), word
        argv.append(word)
    p = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True, encoding="utf-8",
                       timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    result = json.loads(p.stdout)
    assert result["warnings"] == [] and by_name(result)["alpha"]["next"] == "CS alpha"
    # The run root is the one the journal writes under, as On Activation reads it.
    assert '--run-root "{project-root}/_bmad-output/.skf-run"' in call
    assert "--inventory" not in call and "skf-skill-inventory.py" not in _ws()


def test_ws_reads_only_fields_the_script_prints_and_restates_no_rule(forge_tree):
    ws = _ws()
    printed = set(run(forge_tree))
    read = set(re.findall(r"`([a-z_]+)(?:\[\])?`", ws.split("prints one JSON object", 1)[1]))
    assert {"skills", "recommended", "warnings", "route"} <= read
    assert read - {"route"} <= printed
    for rule in ("`CS <name>`", "`TS <name>`", "`US <name> --from-test-report`", "`EX <name>`",
                 "skill-brief.yaml", "skf-test-skill-result-latest.json"):
        assert rule not in ws, rule
