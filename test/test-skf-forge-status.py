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
  - #1170: `skill_entry` gives one skill's entry by the same rule for
    pipeline-gate.py and parse-pipeline.py (None when the inventory cannot
    run or lists no SKF skill by that name), with `verdict_time` and
    `audit_on_record` beside it, all without pyyaml
  - #1169: an audit that found drift after the test verdict takes `US <name>`,
    with `--target-ref <upstream_ref>` when it found upstream moved, and
    names its severity as `drift`; an older, CLEAN, untimed or unreadable
    audit leaves the verdict's code. An unfinished campaign, tallied by
    skf-campaign's campaign-status.py, is printed as `campaign` and gives
    its members `CA` (a stopped chain's offer still wins), a finished one
    gives nothing, a status script that fails is named by its `error` or
    its last stderr line, and `--campaign-only` reads it alone, as the On
    Activation step 5 call that runs as written does
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
import yaml

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
SCRIPT = SRC / "skf-forger" / "scripts" / "forge-status.py"
JOURNAL = SRC / "skf-forger" / "scripts" / "pipeline-journal.py"
INVENTORY = SRC / "shared" / "scripts" / "skf-skill-inventory.py"
CAMPAIGN_STATUS = SRC / "skf-campaign" / "scripts" / "campaign-status.py"
CAMPAIGN_STATE_SCRIPT = SRC / "skf-campaign" / "scripts" / "campaign-state.py"
FORGER_SKILL = SRC / "skf-forger" / "SKILL.md"

spec = importlib.util.spec_from_file_location("skf_forge_status", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

OLD_RUN = "20260101T000000Z-0000beef"  # a test run long before any journal these tests start
TESTED = "2026-03-01T12:00:00Z"  # when the test records that carry a timestamp ran


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


def verdict(forge: Path, name: str, version: str | None, result: str, timestamp: str | None = None) -> None:
    folder = forge / name if version is None else forge / name / version
    record = {"runId": OLD_RUN, "summary": {"result": result}}
    if timestamp is not None:
        record["timestamp"] = timestamp
    _write_json(folder / mod.TEST_RESULT, record)


def audit(forge: Path, name: str, version: str | None, severity: str, timestamp: str | None, *,
          upstream_moved=None, upstream_ref=None) -> None:
    """An audit record as the shared emitter writes it: the severity and the upstream check in `summary`, its own
    `timestamp`."""
    folder = forge / name if version is None else forge / name / version
    summary = {"drift_count": 3, "severity": severity, "upstream_moved": upstream_moved, "upstream_ref": upstream_ref}
    record = {"skill": "skf-audit-skill", "status": "success", "summary": summary}
    if timestamp is not None:
        record["timestamp"] = timestamp
    _write_json(folder / mod.AUDIT_RESULT, record)


def brief(forge: Path, name: str) -> None:
    (forge / name).mkdir(parents=True, exist_ok=True)
    (forge / name / mod.BRIEF).write_bytes(f"name: {name}\n".encode("utf-8"))


def export(skills: Path, versions: dict) -> None:
    _write_json(skills / ".export-manifest.json", {
        "schema_version": "2", "updated_at": "2026-01-01T00:00:00Z",
        "exports": {name: {"active_version": v, "versions": {v: {"last_exported": "2026-01-01", "status": "active"}}}
                    for name, v in versions.items()}})


def run(tmp_path: Path, *, inventory: Path | None = INVENTORY, extra: list[str] = ()) -> dict:
    """One call, with `--inventory` unless it is None (then the project-root probe finds it)."""
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(tmp_path), "--skills-output-folder",
         str(tmp_path / "skills"), "--forge-data-folder", str(tmp_path / "forge"),
         *(["--inventory", str(inventory)] if inventory else []),
         "--run-root", str(tmp_path / "runs"), "--result-dir", str(tmp_path / "sidecar"), *extra],
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
    assert (result["skills"], result["recommended"], result["pipeline"], result["campaign"], result["warnings"]) == (
        [], [], None, None, [])


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
# Drift an audit found after the test (#1169)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("verdict_", [None, "INCONCLUSIVE", "PASS_WITH_DRIFT", "FAIL", "PASS"])
def test_drift_on_record_takes_update_skill_whatever_the_verdict(verdict_):
    status = mod.skill_status("x", "1.0.0", verdict_, "1.0.0", "SIGNIFICANT")
    assert (status["next"], status["drift"]) == ("US x", "SIGNIFICANT")
    assert status["stage"] == mod.skill_status("x", "1.0.0", verdict_, "1.0.0")["stage"]
    assert mod.skill_status("x", "1.0.0", verdict_, "1.0.0")["drift"] is None


@pytest.fixture()
def exported_skill(tmp_path):
    """x, compiled at 1.0.0 and exported."""
    (tmp_path / "skills").mkdir()
    make_skill(tmp_path / "skills", "x")
    export(tmp_path / "skills", {"x": "1.0.0"})
    return tmp_path


@pytest.mark.parametrize("verdict_,severity,audited,drift,nxt", [
    pytest.param("PASS", "MINOR", "2026-03-02T09:00:00Z", "MINOR", "US x", id="drift"),
    pytest.param("PASS", "CLEAN", "2026-03-02T09:00:00Z", None, None, id="clean-audit"),
    pytest.param("PASS", "SIGNIFICANT", "2026-02-28T09:00:00Z", None, None, id="old-drift"),
    pytest.param("FAIL", "CRITICAL", "2026-03-02T09:00:00Z", "CRITICAL", "US x", id="fail-then-drift"),
    pytest.param("FAIL", "MINOR", "2026-02-28T09:00:00Z", None, "US x --from-test-report", id="fail-after-drift"),
    pytest.param("PASS", "minor", "2026-03-01T14:00:00+02:00", None, None, id="same-instant-other-zone"),
    pytest.param("PASS", "minor", "2026-03-01T13:00:00+00:00", "MINOR", "US x", id="lower-case-later"),
    pytest.param("PASS", "MINOR", None, None, None, id="audit-with-no-time"),
    pytest.param("PASS", "MINOR", "yesterday", None, None, id="audit-time-unreadable"),
    pytest.param("FAIL", "MINOR", None, None, "US x --from-test-report", id="fail-audit-with-no-time"),
    pytest.param("PASS", "MINOR", "2026-03-01T12:30:00", "MINOR", "US x", id="zone-less-later-read-as-utc"),
    pytest.param("PASS", "MINOR", "2026-03-01T11:30:00", None, None, id="zone-less-earlier-read-as-utc"),
])
def test_an_audit_after_the_test_verdict_takes_update_skill(exported_skill, verdict_, severity, audited, drift, nxt):
    forge = exported_skill / "forge"
    verdict(forge, "x", "1.0.0", verdict_, timestamp=TESTED)
    audit(forge, "x", "1.0.0", severity, audited)
    result = run(exported_skill)
    x = by_name(result)["x"]
    assert (x["drift"], x["next"], result["warnings"]) == (drift, nxt, [])
    assert result["recommended"] == ([nxt] if nxt else [])


@pytest.mark.parametrize("tested", [None, "not a time"], ids=["no-timestamp", "unreadable-timestamp"])
def test_drift_counts_when_no_test_record_carries_a_readable_time(exported_skill, tested):
    """An old audit counts here: with no time on the test record, nothing says the test came after it."""
    forge = exported_skill / "forge"
    verdict(forge, "x", "1.0.0", "PASS", timestamp=tested)
    audit(forge, "x", "1.0.0", "MINOR", "2020-01-01T00:00:00Z")
    assert by_name(run(exported_skill))["x"]["next"] == "US x"


@pytest.mark.parametrize("verdict_,severity,moved,ref,drift,nxt", [
    pytest.param("PASS", "SIGNIFICANT", True, "v2.0.0", "SIGNIFICANT", "US x --target-ref v2.0.0",
                 id="drift-upstream-moved"),
    pytest.param("PASS", "SIGNIFICANT", True, None, "SIGNIFICANT", "US x", id="upstream-moved-no-ref"),
    pytest.param("FAIL", "CRITICAL", True, " v2.0.0\n", "CRITICAL", "US x --target-ref v2.0.0", id="ref-stripped"),
    pytest.param("PASS", "MINOR", True, "   ", "MINOR", "US x", id="blank-ref"),
    pytest.param("PASS", "MINOR", False, "v2.0.0", "MINOR", "US x", id="upstream-not-moved"),
    pytest.param("PASS", "MINOR", "true", "v2.0.0", "MINOR", "US x", id="moved-not-a-boolean"),
    pytest.param("PASS", "CLEAN", True, "v2.0.0", None, None, id="clean-upstream-moved"),
    pytest.param("FAIL", "CLEAN", True, "v2.0.0", None, "US x --from-test-report", id="fail-clean-upstream-moved"),
])
def test_drift_after_upstream_moved_updates_to_the_ref_the_audit_found(exported_skill, verdict_, severity, moved, ref,
                                                                       drift, nxt):
    """Update Skill reads the ref a skill was built from unless given `--target-ref`, so a skill pinned to a tag
    would miss the drift the audit found where upstream moved to; the AS gate hands the ref on the same way."""
    forge = exported_skill / "forge"
    verdict(forge, "x", "1.0.0", verdict_, timestamp=TESTED)
    audit(forge, "x", "1.0.0", severity, "2026-03-02T09:00:00Z", upstream_moved=moved, upstream_ref=ref)
    result = run(exported_skill)
    x = by_name(result)["x"]
    assert (x["drift"], x["next"], result["warnings"]) == (drift, nxt, [])
    assert result["recommended"] == ([nxt] if nxt else [])


def test_drift_counts_for_a_skill_never_tested(exported_skill):
    audit(exported_skill / "forge", "x", "1.0.0", "SIGNIFICANT", "2026-03-02T09:00:00Z")
    x = by_name(run(exported_skill))["x"]
    assert (x["verdict"], x["drift"], x["next"]) == (None, "SIGNIFICANT", "US x")


def test_an_audit_is_read_beside_a_flat_skills_verdict(tmp_path):
    verdict(tmp_path, "flatty", None, "PASS", timestamp=TESTED)
    audit(tmp_path, "flatty", None, "CRITICAL", "2026-03-02T09:00:00Z")
    assert mod.read_drift(tmp_path, "flatty", "flat") == ("CRITICAL", None)
    assert mod.read_drift(tmp_path, "flatty", "1.0.0") == (None, None)
    assert mod.read_drift(tmp_path, "missing", "1.0.0") == (None, None)


def test_an_unreadable_audit_result_is_a_warning(exported_skill):
    forge = exported_skill / "forge"
    verdict(forge, "x", "1.0.0", "PASS", timestamp=TESTED)
    (forge / "x" / "1.0.0" / mod.AUDIT_RESULT).write_bytes(b"{not json")
    result = run(exported_skill)
    [warning] = result["warnings"]
    assert warning.startswith("audit_result_unreadable: ") and "x/1.0.0/audit-skill-result-latest.json" in warning
    x = by_name(result)["x"]
    assert (x["drift"], x["next"]) == (None, None)


def test_an_unreadable_test_record_beside_a_drift_audit_is_one_warning(exported_skill):
    """The test record carries no readable time, so the drift counts; read_verdict alone names the record."""
    forge = exported_skill / "forge"
    audit(forge, "x", "1.0.0", "MINOR", "2026-03-02T09:00:00Z")
    (forge / "x" / "1.0.0" / mod.TEST_RESULT).write_bytes(b"{not json")
    result = run(exported_skill)
    [warning] = result["warnings"]
    assert warning.startswith("test_result_unreadable: ") and "x/1.0.0/skf-test-skill-result-latest.json" in warning
    x = by_name(result)["x"]
    assert (x["verdict"], x["drift"], x["next"]) == (None, "MINOR", "US x")


def test_the_test_and_audit_records_are_read_without_pyyaml(tmp_path):
    """#1170 loads these rules into scripts with no dependencies (pipeline-gate.py, parse-pipeline.py): only the
    campaign source reads YAML."""
    skills = tmp_path / "skills"
    skills.mkdir()
    make_skill(skills, "x")
    export(skills, {"x": "1.0.0"})
    code = (
        "import importlib.util, sys\n"
        "sys.modules['yaml'] = None  # any `import yaml` now raises\n"
        "from pathlib import Path\n"
        f"spec = importlib.util.spec_from_file_location('fs', {str(SCRIPT)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        f"forge = Path({str(tmp_path)!r})\n"
        "assert mod.read_verdict(forge, 'x', '1.0.0') == 'PASS'\n"
        "assert mod.read_drift(forge, 'x', '1.0.0') == ('MINOR', 'v2.0.0')\n"
        f"entry = mod.skill_entry(Path({str(skills)!r}), forge, 'x')\n"
        "assert (entry['active_version'], entry['next']) == ('1.0.0', 'US x --target-ref v2.0.0'), entry\n"
        "assert mod.verdict_time(forge, 'x', '1.0.0').isoformat() == '2026-03-01T12:00:00+00:00'\n"
        "assert mod.audit_on_record(forge, 'x', '1.0.0')\n"
        "assert mod.skill_status('x', '1.0.0', 'PASS', '1.0.0', 'MINOR')['next'] == 'US x'\n"
        "status = mod.skill_status('x', '1.0.0', 'PASS', '1.0.0', 'MINOR', 'v2.0.0')\n"
        "assert status['next'] == 'US x --target-ref v2.0.0'\n"
        "try:\n"
        "    mod.campaign_members(forge / 'state.yaml')\n"
        "except ValueError as e:\n"
        "    assert 'pyyaml' in str(e), e\n"
        "else:\n"
        "    raise AssertionError('campaign_members read YAML without pyyaml')\n"
        "print('ok')\n"
    )
    verdict(tmp_path, "x", "1.0.0", "PASS", timestamp=TESTED)
    audit(tmp_path, "x", "1.0.0", "MINOR", "2026-03-02T09:00:00Z", upstream_moved=True, upstream_ref="v2.0.0")
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0 and p.stdout.strip() == "ok", p.stdout + p.stderr


# --------------------------------------------------------------------------
# One skill, for the gate and the parser (#1170)
# --------------------------------------------------------------------------


def test_skill_entry_is_the_entry_ws_prints_for_one_skill(forge_tree):
    """The gate and the parser read one skill's entry by the WS rule: the same verdict and drift rungs, no campaign
    or offer pass."""
    forge, skills = forge_tree / "forge", forge_tree / "skills"
    export(skills, {"zeta": "1.0.0"})
    ws = by_name(run(forge_tree))
    for name in ("beta", "gamma", "delta", "zeta", "eta", "iota"):
        assert mod.skill_entry(skills, forge, name) == ws[name], name
    assert mod.skill_entry(skills, forge, "zeta")["next"] is None
    assert mod.skill_entry(skills, forge, "iota")["active_version"] == "flat"


def test_skill_entry_runs_the_shared_inventory_beside_the_skill_folder(forge_tree):
    assert mod.SHARED_INVENTORY == INVENTORY.resolve()
    assert mod.skill_entry(forge_tree / "skills", forge_tree / "forge", "gamma", INVENTORY)["next"] == (
        "US gamma --from-test-report")


@pytest.mark.parametrize("name", ["foreign", "alpha", "missing"], ids=["not-skf", "briefed-only", "missing"])
def test_skill_entry_is_none_for_a_skill_the_inventory_does_not_list_as_skf(forge_tree, name):
    assert mod.skill_entry(forge_tree / "skills", forge_tree / "forge", name) is None


def test_skill_entry_is_none_when_the_inventory_cannot_run(forge_tree, tmp_path):
    broken = tmp_path / "inventory.py"
    broken.write_bytes(b"import sys\nsys.stderr.write('boom\\n')\nsys.exit(1)\n")
    forge, skills = forge_tree / "forge", forge_tree / "skills"
    assert mod.skill_entry(skills, forge, "zeta", broken) is None
    assert mod.skill_entry(skills, forge, "zeta", tmp_path / "absent.py") is None
    assert mod.skill_entry(tmp_path / "no-skills-folder", forge, "zeta") is None


def test_verdict_time_is_the_test_records_timestamp(tmp_path):
    verdict(tmp_path, "x", "1.0.0", "PASS", timestamp="2026-03-01T14:00:00+02:00")
    verdict(tmp_path, "flatty", None, "PASS", timestamp=TESTED)
    verdict(tmp_path, "untimed", "1.0.0", "PASS")
    verdict(tmp_path, "garbled", "1.0.0", "PASS", timestamp="yesterday")
    (tmp_path / "broken" / "1.0.0").mkdir(parents=True)
    (tmp_path / "broken" / "1.0.0" / mod.TEST_RESULT).write_bytes(b"{not json")
    assert mod.verdict_time(tmp_path, "x", "1.0.0").isoformat() == "2026-03-01T12:00:00+00:00"
    assert mod.verdict_time(tmp_path, "flatty", "flat").isoformat() == "2026-03-01T12:00:00+00:00"
    for name, version in (("x", "0.9.0"), ("untimed", "1.0.0"), ("garbled", "1.0.0"), ("broken", "1.0.0"),
                          ("missing", "1.0.0")):
        assert mod.verdict_time(tmp_path, name, version) is None, name


def test_audit_on_record_looks_beside_the_active_versions_test_record(tmp_path):
    audit(tmp_path, "x", "1.0.0", "CLEAN", TESTED)
    audit(tmp_path, "flatty", None, "MINOR", TESTED)
    assert mod.audit_on_record(tmp_path, "x", "1.0.0") is True
    assert mod.audit_on_record(tmp_path, "x", "0.9.0") is False  # another version's audit
    assert mod.audit_on_record(tmp_path, "flatty", "flat") is True
    assert mod.audit_on_record(tmp_path, "flatty", "1.0.0") is False
    assert mod.audit_on_record(tmp_path, "missing", "1.0.0") is False


# --------------------------------------------------------------------------
# An unfinished campaign (#1169)
# --------------------------------------------------------------------------


def _install_campaign_status(project_root: Path, probe: str = mod.CAMPAIGN_STATUS_PROBES[1]) -> None:
    target = project_root / probe
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CAMPAIGN_STATUS, target)


def campaign_state(workspace: Path, stage: int, skills: list[dict], name: str = "acme-stack") -> None:
    """A campaign state, as campaign-state.py keeps it, with the fields campaign-status.py tallies."""
    workspace.mkdir(parents=True, exist_ok=True)
    state = {"campaign": {"name": name, "current_stage": stage, "last_updated": "2026-03-01T12:00:00Z"},
             "skills": skills}
    (workspace / mod.CAMPAIGN_STATE).write_bytes(yaml.safe_dump(state).encode("utf-8"))


def _member(name: str, status: str, skill_path: str | None = None) -> dict:
    return {"name": name, "tier": "A", "status": status, **({"skill_path": skill_path} if skill_path else {})}


@pytest.fixture()
def campaign_tree(forge_tree):
    """forge_tree with campaign-status.py under the project root and an unfinished campaign at stage 4."""
    _install_campaign_status(forge_tree)
    campaign_state(forge_tree / "forge" / "_campaign", 4, [_member("gamma", "completed"), _member("zeta", "pending")])
    return forge_tree


def test_an_unfinished_campaign_gives_its_members_ca(campaign_tree):
    result = run(campaign_tree)
    assert result["warnings"] == []
    assert result["campaign"] == {"name": "acme-stack", "current_stage": 4, "completed": 1, "total": 2}
    got = {name: s["next"] for name, s in by_name(result).items()}
    assert (got["gamma"], got["zeta"], got["delta"]) == ("CA", "CA", "TS delta")
    assert result["recommended"] == ["CS alpha", "TS beta", "TS delta", "CA"]


def test_a_member_is_found_by_its_skill_path_too(campaign_tree):
    """Export Skill names a Tier B skill's folder after its library, not its campaign name."""
    campaign_state(campaign_tree / "forge" / "_campaign", 5, [
        _member("delta-lib", "completed", "skills/delta"), _member("beta-lib", "active", "skills\\beta\\")])
    got = {name: s["next"] for name, s in by_name(run(campaign_tree)).items()}
    assert (got["delta"], got["beta"], got["gamma"]) == ("CA", "CA", "US gamma --from-test-report")


@pytest.mark.parametrize("statuses", [("completed", "failed"), ("skipped", "completed")])
def test_a_finished_campaign_gives_back_the_per_skill_codes(campaign_tree, statuses):
    campaign_state(campaign_tree / "forge" / "_campaign", mod.CAMPAIGN_FINAL_STAGE,
                   [_member("gamma", statuses[0]), _member("zeta", statuses[1])])
    result = run(campaign_tree)
    assert (result["campaign"], result["warnings"]) == (None, [])
    got = {name: s["next"] for name, s in by_name(result).items()}
    assert (got["gamma"], got["zeta"]) == ("US gamma --from-test-report", "EX zeta")
    assert "CA" not in result["recommended"]


@pytest.mark.parametrize("stage,open_status", [(10, "pending"), (10, "active"), (9, "completed")])
def test_a_campaign_is_unfinished_until_its_last_stage_leaves_nothing_open(campaign_tree, stage, open_status):
    campaign_state(campaign_tree / "forge" / "_campaign", stage, [_member("gamma", open_status)])
    result = run(campaign_tree)
    assert result["campaign"]["current_stage"] == stage
    assert by_name(result)["gamma"]["next"] == "CA"


def test_ca_comes_last_when_no_listed_skill_is_a_member(campaign_tree):
    campaign_state(campaign_tree / "forge" / "_campaign", 2, [_member("omega", "pending")])
    _start_chain(campaign_tree, "QS[cognee] TS EX")
    result = run(campaign_tree)
    assert "CA" not in [s["next"] for s in result["skills"]]
    assert result["recommended"][-2:] == ["resume at QS: QS TS EX", "CA"]


def test_the_offer_outranks_ca_for_the_skill_it_names(campaign_tree):
    _start_chain(campaign_tree, "maintain gamma")
    result = run(campaign_tree)
    got = {name: s["next"] for name, s in by_name(result).items()}
    assert (got["gamma"], got["zeta"]) == ("resume at AS: AS US TS EX", "CA")
    assert result["recommended"].count("CA") == 1 and "resume at AS: AS US TS EX" in result["recommended"]


def test_ca_stays_listed_when_the_offer_names_the_only_member(campaign_tree):
    campaign_state(campaign_tree / "forge" / "_campaign", 4, [_member("gamma", "active")])
    _start_chain(campaign_tree, "maintain gamma")
    result = run(campaign_tree)
    assert by_name(result)["gamma"]["next"] == "resume at AS: AS US TS EX"
    assert result["recommended"][-1] == "CA" and result["recommended"].count("CA") == 1


def test_a_state_campaign_status_cannot_read_is_a_warning(campaign_tree):
    (campaign_tree / "forge" / "_campaign" / mod.CAMPAIGN_STATE).write_bytes(b"- not\n- a mapping\n")
    result = run(campaign_tree)
    [warning] = result["warnings"]
    assert warning.startswith("campaign_unavailable: State not readable as a mapping: "), warning
    assert result["campaign"] is None
    assert by_name(result)["gamma"]["next"] == "US gamma --from-test-report"


def test_no_campaign_status_script_is_a_warning(forge_tree):
    campaign_state(forge_tree / "forge" / "_campaign", 4, [_member("gamma", "pending")])
    result = run(forge_tree)
    assert (result["campaign"], result["warnings"]) == (None, ["campaign_unavailable: campaign-status.py not found"])


def test_a_campaign_status_that_fails_names_its_last_stderr_line(campaign_tree):
    script = campaign_tree / mod.CAMPAIGN_STATUS_PROBES[1]
    script.write_bytes(b"import sys\nsys.stderr.write('reading the state\\nboom\\n\\n  \\n')\nsys.exit(1)\n")
    assert run(campaign_tree)["warnings"] == ["campaign_unavailable: boom"]


def test_a_campaign_status_crash_names_the_cause_its_traceback_ends_with(campaign_tree):
    """A Python traceback starts with `Traceback (most recent call last):`, which names no cause; its last line does."""
    script = campaign_tree / mod.CAMPAIGN_STATUS_PROBES[1]
    script.write_bytes(b"def tally(state):\n    return state['skills']\n\n\ntally({})\n")
    result = run(campaign_tree)
    assert result["warnings"] == ["campaign_unavailable: KeyError: 'skills'"]
    assert "Traceback" not in result["warnings"][0] and result["campaign"] is None
    assert by_name(result)["gamma"]["next"] == "US gamma --from-test-report"


def test_the_installed_campaign_status_comes_before_the_dev_one(tmp_path):
    for probe in mod.CAMPAIGN_STATUS_PROBES:
        _install_campaign_status(tmp_path, probe)
    assert mod.find_campaign_status(tmp_path).as_posix() == (tmp_path / mod.CAMPAIGN_STATUS_PROBES[0]).as_posix()
    assert mod.CAMPAIGN_STATUS_PROBES[0].startswith("_bmad/skf/skf-campaign/")
    assert mod.CAMPAIGN_STATUS_PROBES[1].startswith("src/skf-campaign/")


def test_no_campaign_state_is_no_campaign_and_no_warning(forge_tree):
    _install_campaign_status(forge_tree)
    result = run(forge_tree)
    assert (result["campaign"], result["warnings"]) == (None, [])


def test_the_campaign_workspace_flag_names_another_workspace(campaign_tree):
    moved = campaign_tree / "elsewhere"
    (campaign_tree / "forge" / "_campaign" / mod.CAMPAIGN_STATE).replace(campaign_tree / "moved.yaml")
    moved.mkdir()
    (campaign_tree / "moved.yaml").replace(moved / mod.CAMPAIGN_STATE)
    assert run(campaign_tree)["campaign"] is None
    result = run(campaign_tree, extra=["--campaign-workspace", str(moved)])
    assert result["campaign"]["name"] == "acme-stack" and by_name(result)["zeta"]["next"] == "CA"


def test_the_final_stage_is_campaign_states():
    """forge-status.py keeps its own copy of campaign-state.py's FINAL_STAGE, which it does not import."""
    [final] = re.findall(r"^FINAL_STAGE = (\d+)$", _read(CAMPAIGN_STATE_SCRIPT), re.M)
    assert int(final) == mod.CAMPAIGN_FINAL_STAGE


def _campaign_only(tmp_path: Path, *extra: str, rc: int = 0) -> subprocess.CompletedProcess:
    p = subprocess.run([sys.executable, str(SCRIPT), "--campaign-only", "--project-root", str(tmp_path),
                        "--forge-data-folder", str(tmp_path / "forge"), *extra],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert p.returncode == rc, p.stdout + p.stderr
    return p


def test_campaign_only_reads_the_campaign_alone(campaign_tree):
    marker = campaign_tree / "inventory-ran"
    probe = campaign_tree / mod.INVENTORY_PROBES[0]
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_bytes(f"open({str(marker)!r}, 'w').close()\n".encode("utf-8"))
    _start_chain(campaign_tree, "maintain gamma")
    out = json.loads(_campaign_only(campaign_tree).stdout)
    assert out == {"status": "ok", "campaign": {"name": "acme-stack", "current_stage": 4, "completed": 1, "total": 2},
                   "warnings": []}
    assert not marker.exists()


def test_campaign_only_takes_the_workspace_flag(campaign_tree):
    workspace = campaign_tree / "forge" / "_campaign"
    assert json.loads(_campaign_only(campaign_tree, "--campaign-workspace", str(campaign_tree / "none")).stdout) == {
        "status": "ok", "campaign": None, "warnings": []}
    assert json.loads(_campaign_only(campaign_tree, "--campaign-workspace", str(workspace)).stdout)["campaign"]


def test_the_status_flags_stay_required_without_campaign_only(tmp_path):
    p = subprocess.run([sys.executable, str(SCRIPT), "--project-root", str(tmp_path), "--forge-data-folder",
                        str(tmp_path / "forge")], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 2 and p.stdout == ""
    for flag in ("--skills-output-folder", "--run-root", "--result-dir"):
        assert flag in p.stderr, flag


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
    for flag in ("--campaign-only", "--campaign-workspace"):
        assert flag in p.stdout, flag
    # campaign-status.py, which it runs with its own interpreter, imports yaml.
    assert re.search(r'^# dependencies = \["pyyaml"\]$', text, re.M)


def _ws() -> str:
    return _read(FORGER_SKILL).split("- **WS**:", 1)[1].split("## Pipeline Mode", 1)[0]


def _journal_step() -> str:
    text = _read(FORGER_SKILL)
    return text[text.index("5. **Read the pipeline journal**"):text.index("6. **Greet, then dispatch or wait.**")]


def _filled(call: str, values: dict[str, str]) -> list[str]:
    """A documented forge-status.py call's words after the script, its placeholders filled in."""
    words = shlex.split(call)
    assert words[:3] == ["uv", "run", "scripts/forge-status.py"]
    argv = []
    for word in words[3:]:
        for placeholder, value in values.items():
            word = word.replace(placeholder, value)
        assert not re.search(r"[{<][a-z_-]+[}>]", word), word
        argv.append(word)
    return argv


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


def test_ws_reads_only_fields_the_script_prints_and_restates_no_rule(campaign_tree):
    """Each name WS reads is a key the script prints: at the top, in a `skills[]` entry or in `campaign`."""
    ws = _ws()
    result = run(campaign_tree)
    assert result["campaign"] is not None
    printed = set(result) | {key for entry in result["skills"] for key in entry} | set(result["campaign"])
    read = set(re.findall(r"`([a-z_]+)(?:\[\])?`", ws.split("prints one JSON object", 1)[1]))
    assert {"skills", "recommended", "warnings", "route", "drift", "campaign", "current_stage"} <= read
    assert read - {"route"} <= printed
    for rule in ("`CS <name>`", "`TS <name>`", "`US <name> --from-test-report`", "`EX <name>`", "`US <name>`",
                 "skill-brief.yaml", "skf-test-skill-result-latest.json", "audit-skill-result-latest.json",
                 "_campaign-state.yaml", "MINOR", "CLEAN"):
        assert rule not in ws, rule
    for source in ("their test verdicts and latest audits", "an unfinished campaign"):
        assert source in ws, source


def test_the_activation_campaign_call_runs_as_written(campaign_tree):
    """#1169: On Activation step 5 names an unfinished campaign from one forge-status.py call, which runs no
    inventory and reads skf-campaign's default workspace under the forge data folder."""
    step = _journal_step()
    [call] = re.findall(r"^\s*(uv run scripts/forge-status\.py .+)$", step, re.M)
    assert "--campaign-only" in call and '--project-root "{project-root}"' in call
    assert "--campaign-workspace" not in call and "--inventory" not in call
    values = {"{project-root}": str(campaign_tree), "{forge_data_folder}": str(campaign_tree / "forge")}
    p = subprocess.run([sys.executable, str(SCRIPT), *_filled(call, values)], capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout)
    assert out == {"status": "ok", "campaign": {"name": "acme-stack", "current_stage": 4, "completed": 1, "total": 2},
                   "warnings": []}
    after = step.split(call, 1)[1]
    for name in ("campaign", "name", "current_stage", "completed", "total", "warnings"):
        assert f"`{name}`" in after, name
    assert "`CA`" in after


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")
def test_the_activation_campaign_call_runs_under_uv_with_the_dependencies_it_declares(campaign_tree):
    """`uv run` gives the script only the dependencies its header declares, and campaign-status.py, which it runs
    with its own interpreter, imports yaml: without pyyaml there the campaign is a `campaign_unavailable` warning."""
    [call] = re.findall(r"^\s*(uv run scripts/forge-status\.py .+)$", _journal_step(), re.M)
    values = {"{project-root}": str(campaign_tree), "{forge_data_folder}": str(campaign_tree / "forge")}
    p = subprocess.run([shutil.which("uv"), "run", "scripts/forge-status.py", *_filled(call, values)],
                       cwd=SCRIPT.parent.parent, capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout)
    campaign = {"name": "acme-stack", "current_stage": 4, "completed": 1, "total": 2}
    assert (out["campaign"], out["warnings"]) == (campaign, []), p.stderr
