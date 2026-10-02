"""Tests for campaign-state.py: every write to the campaign state, and the resume point.

The step files no longer re-type _campaign-state.yaml. These tests pin what
the helper promises them: each write validates the state before and after,
rotates .bak only from a primary that validates, stamps times from the clock
and writes atomically; each operation writes what its step used to write by
hand; and the resume point is computed, with the cases that once shipped
wrong (commit 50d0e3bf: an active Tier A skill resumes stage 4 with no +1),
the terminal cap at stage 10 and --from with [N]ext. A fixture interrupted
during the Tier B batch resumes at the batch stage, whose batch script picks
the interrupted skills up again, and completes them. archive moves a campaign
aside for an overwrite, and halt-payload hands the emitter a HARD HALT's
counts; a refused plan, pin or provenance write exits with its stage's code.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "skf-campaign" / "scripts"


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_") + "_helper_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("campaign-state")
batch = _load("campaign-render-batch")

STAMP = "2026-10-01T12:00:00+00:00"
LATER = "2026-10-01T13:30:00+00:00"


def _skill(name: str, tier: str = "A", status: str = "pending", **fields) -> dict:
    skill = {
        "name": name, "status": status, "depends_on": [], "tier": tier, "pin": None,
        "brief_path": None, "skill_path": None, "quality_score": None, "workarounds_applied": [],
        "started_at": None, "completed_at": None, "commit_sha": None,
    }
    skill.update(fields)
    return skill


def _state(stage: int = 0, skills: list | None = None, order: list | None = None) -> dict:
    skills = skills if skills is not None else [_skill("core"), _skill("web", depends_on=["core"]),
                                                 _skill("util", tier="B")]
    return {
        "campaign": {
            "name": "demo",
            "started_at": "2026-10-01T10:00:00Z",
            "last_updated": "2026-10-01T10:00:00Z",
            "current_stage": stage,
            "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80},
        },
        "skills": skills,
        "dependency_graph": {
            "execution_order": order if order is not None else [s["name"] for s in skills],
            "circular_deps_detected": False,
        },
    }


def _write(tmp_path: pathlib.Path, state: dict) -> pathlib.Path:
    path = tmp_path / "_campaign-state.yaml"
    path.write_bytes(yaml.safe_dump(state, sort_keys=False).encode("utf-8"))
    return path


def _read(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _bak(path: pathlib.Path) -> pathlib.Path:
    return path.with_name(path.name + ".bak")


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """The clock the helper reads: STAMP, then LATER for every later call."""
    stamps = iter([STAMP])
    monkeypatch.setattr(mod, "now", lambda: next(stamps, LATER))


def _run(capsys, *argv: str) -> tuple[int, dict]:
    rc = mod.main(list(argv))
    captured = capsys.readouterr()
    text = captured.out if rc == 0 else captured.err
    return rc, json.loads(text) if text.strip() else {}


def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))


# --------------------------------------------------------------------------
# The write cycle: validate, stamp, validate, rotate, write
# --------------------------------------------------------------------------


class TestWriteCycle:
    def test_write_rotates_the_primary_it_read_into_bak(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        before = path.read_bytes()
        rc, out = _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")
        assert rc == 0
        assert _bak(path).read_bytes() == before
        assert out["backup_rotated"] is True
        assert _read(path)["campaign"]["current_stage"] == 1

    def test_last_updated_comes_from_the_clock(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        rc, out = _run(capsys, "set-stage", "--state-file", str(path), "--stage", "2")
        assert rc == 0
        assert out["last_updated"] == STAMP
        assert _read(path)["campaign"]["last_updated"] == STAMP

    def test_the_real_clock_is_utc_with_its_offset(self):
        real = _load("campaign-state").now()  # a fresh copy: the fixture patched this one
        parsed = datetime.fromisoformat(real)
        assert parsed.utcoffset() == timedelta(0)
        assert abs(datetime.now(timezone.utc) - parsed) < timedelta(minutes=5)

    def test_an_invalid_primary_is_never_rotated_into_bak(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")[0] == 0
        good_bak = _bak(path).read_bytes()
        broken = _read(path)
        broken["campaign"]["current_stage"] = "one"
        path.write_bytes(yaml.safe_dump(broken).encode("utf-8"))
        corrupt = path.read_bytes()
        rc, err = _run(capsys, "set-stage", "--state-file", str(path), "--stage", "2")
        assert rc == 3
        assert err["code"] == "state-invalid"
        assert _bak(path).read_bytes() == good_bak
        assert path.read_bytes() == corrupt

    def test_a_change_that_breaks_the_schema_writes_nothing(self, tmp_path, capsys, monkeypatch):
        path = _write(tmp_path, _state(stage=6))
        before = path.read_bytes()
        _stdin(monkeypatch, 'SKF_VERIFY_STACK_RESULT_JSON: {"status":"success","exit_code":0,'
                            '"overall_verdict":"Verified","report_path":"r.md"}\n')
        rc, err = _run(capsys, "set-campaign", "--state-file", str(path), "--verification", "-", "--stage", "7")
        assert rc == 3
        assert err["code"] == "state-change-invalid"
        assert [e["field"] for e in err["errors"]] == ["campaign.verification.overall_verdict"]
        assert path.read_bytes() == before
        assert not _bak(path).exists()

    def test_missing_state_is_exit_3(self, tmp_path, capsys):
        rc, err = _run(capsys, "set-stage", "--state-file", str(tmp_path / "none.yaml"), "--stage", "1")
        assert rc == 3
        assert err["code"] == "state-missing"

    def test_malformed_yaml_is_exit_3(self, tmp_path, capsys):
        path = tmp_path / "_campaign-state.yaml"
        path.write_bytes(b"campaign: [unclosed\n")
        rc, err = _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")
        assert rc == 3
        assert err["code"] == "state-malformed"

    def test_no_temporary_file_is_left_behind(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")[0] == 0
        assert sorted(p.name for p in tmp_path.iterdir()) == ["_campaign-state.yaml", "_campaign-state.yaml.bak"]

    def test_written_timestamps_stay_strings(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--status", "active")[0] == 0
        text = path.read_text(encoding="utf-8")
        assert f"started_at: '{STAMP}'" in text
        assert isinstance(_read(path)["skills"][0]["started_at"], str)

    def test_set_stage_needs_a_stage(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        with pytest.raises(SystemExit) as exc:
            mod.main(["set-stage", "--state-file", str(path)])
        assert exc.value.code == 2

    @pytest.mark.parametrize("stage", ["-1", "11", "x"])
    def test_stage_out_of_range_is_a_usage_error(self, tmp_path, stage):
        path = _write(tmp_path, _state())
        with pytest.raises(SystemExit) as exc:
            mod.main(["set-stage", "--state-file", str(path), "--stage", stage])
        assert exc.value.code == 2


# --------------------------------------------------------------------------
# init (step-01)
# --------------------------------------------------------------------------


TARGETS = {
    "targets": [
        {"name": "core", "repo_url": "https://github.com/acme/core", "tier": "A", "pin": "1.0.0", "depends_on": []},
        {"name": "util", "repo_url": "https://github.com/acme/util", "tier": "B", "pin": None,
         "depends_on": ["core"], "language_hint": "python"},
    ],
    "errors": [],
    "filled_names": [],
    "dangling_depends_on": [],
    "tier_inversions": [],
}


def _init(capsys, path, targets_file, *extra):
    return _run(capsys, "init", "--state-file", str(path), "--targets-file", str(targets_file),
                "--name", "demo", "--hard", "zero-critical-high", "--soft-target", "90",
                "--soft-fallback", "80", *extra)


class TestInit:
    def test_creates_a_valid_state_from_the_parsed_targets(self, tmp_path, capsys):
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps(TARGETS), encoding="utf-8")
        path = tmp_path / "ws" / "_campaign-state.yaml"
        rc, out = _init(capsys, path, targets, "--architecture-doc-path", "docs/architecture.md")
        assert rc == 0
        state = _read(path)
        assert state["campaign"]["started_at"] == state["campaign"]["last_updated"] == STAMP
        assert state["campaign"]["current_stage"] == 0
        assert state["campaign"]["architecture_doc_path"] == "docs/architecture.md"
        assert "directive_path" not in state["campaign"]
        assert state["campaign"]["quality_gate"] == {"hard": "zero-critical-high", "soft_target": 90,
                                                     "soft_fallback": 80}
        assert [s["name"] for s in state["skills"]] == ["core", "util"]
        assert state["skills"][1] == _skill("util", tier="B", depends_on=["core"])
        assert "repo_url" not in json.dumps(state)
        assert mod.validation_errors(state) == []
        assert out["backup_rotated"] is False
        assert not _bak(path).exists()

    def test_reads_the_targets_on_stdin(self, tmp_path, capsys, monkeypatch):
        _stdin(monkeypatch, json.dumps(TARGETS))
        path = tmp_path / "_campaign-state.yaml"
        assert _init(capsys, path, "-")[0] == 0
        assert len(_read(path)["skills"]) == 2

    def test_a_brief_gate_wins_field_by_field(self, tmp_path, capsys):
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps(TARGETS), encoding="utf-8")
        brief = tmp_path / "campaign-brief.yaml"
        brief.write_text("quality_gate:\n  soft_target: 85\n", encoding="utf-8")
        path = tmp_path / "_campaign-state.yaml"
        rc, out = _init(capsys, path, targets, "--brief-file", str(brief))
        assert rc == 0
        assert out["quality_gate"] == {"hard": "zero-critical-high", "soft_target": 85, "soft_fallback": 80}

    def test_a_gate_the_gate_script_rejects_writes_nothing(self, tmp_path, capsys):
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps(TARGETS), encoding="utf-8")
        path = tmp_path / "_campaign-state.yaml"
        rc, err = _run(capsys, "init", "--state-file", str(path), "--targets-file", str(targets), "--name", "d",
                       "--hard", "zero-critical", "--soft-target", "90", "--soft-fallback", "95")
        assert rc == 2
        assert err["code"] == "INVALID_GATE"
        assert not path.exists()

    def test_targets_with_errors_write_nothing(self, tmp_path, capsys):
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps({**TARGETS, "errors": [{"line": 2, "message": "bad tier"}]}), encoding="utf-8")
        path = tmp_path / "_campaign-state.yaml"
        rc, err = _init(capsys, path, targets)
        assert rc == 2
        assert err["code"] == "targets-invalid"
        assert err["errors"] == [{"line": 2, "message": "bad tier"}]
        assert not path.exists()

    def test_no_targets_is_refused(self, tmp_path, capsys):
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps({"targets": [], "errors": []}), encoding="utf-8")
        rc, err = _init(capsys, tmp_path / "_campaign-state.yaml", targets)
        assert (rc, err["code"]) == (2, "no-targets")

    @pytest.mark.parametrize("existing", ["_campaign-state.yaml", "_campaign-state.yaml.bak"])
    def test_never_overwrites_a_state_or_backup(self, tmp_path, capsys, existing):
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps(TARGETS), encoding="utf-8")
        (tmp_path / existing).write_bytes(b"old: campaign\n")
        rc, err = _init(capsys, tmp_path / "_campaign-state.yaml", targets)
        assert (rc, err["code"]) == (2, "state-exists")
        assert (tmp_path / existing).read_bytes() == b"old: campaign\n"

    def test_unreadable_targets_file_is_exit_2(self, tmp_path, capsys):
        rc, err = _init(capsys, tmp_path / "_campaign-state.yaml", tmp_path / "missing.json")
        assert (rc, err["code"]) == (2, "input-unreadable")

    def test_reads_a_utf16_redirect(self, tmp_path, capsys):
        # Windows PowerShell's `>` writes UTF-16 with a byte-order mark.
        targets = tmp_path / "targets.json"
        targets.write_bytes(json.dumps(TARGETS).encode("utf-16"))
        assert _init(capsys, tmp_path / "_campaign-state.yaml", targets)[0] == 0

    def test_takes_the_manifest_scripts_real_output(self, tmp_path, capsys, monkeypatch):
        manifest = _load("campaign-parse-manifest")
        lines = "core,https://github.com/acme/core,A,1.0.0\nweb,acme/web,A,;core\nutil,acme/util,B,\n"
        _stdin(monkeypatch, lines)
        assert manifest.main(["-"]) == 0
        parsed = capsys.readouterr().out
        targets = tmp_path / "targets.json"
        targets.write_text(parsed, encoding="utf-8")
        assert _init(capsys, tmp_path / "_campaign-state.yaml", targets)[0] == 0
        skills = _read(tmp_path / "_campaign-state.yaml")["skills"]
        assert [(s["name"], s["tier"], s["pin"], s["depends_on"]) for s in skills] == [
            ("core", "A", "1.0.0", []), ("web", "A", None, ["core"]), ("util", "B", None, [])]


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


class TestSetSkill:
    def test_active_stamps_started_at_once(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--status", "active")[0] == 0
        assert _read(path)["skills"][0]["started_at"] == STAMP
        # An interrupted skill activated again keeps the start of its run.
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--status", "active")[0] == 0
        assert _read(path)["skills"][0]["started_at"] == STAMP

    def test_completed_stamps_completed_at_and_records_the_result(self, tmp_path, capsys):
        path = _write(tmp_path, _state(skills=[_skill("core", status="active", started_at=STAMP)]))
        rc, _ = _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--status", "completed",
                     "--quality-score", "91.5", "--skill-path", "skills/core/1.0.0/core")
        assert rc == 0
        core = _read(path)["skills"][0]
        assert (core["status"], core["completed_at"], core["quality_score"], core["skill_path"]) == (
            "completed", STAMP, 91.5, "skills/core/1.0.0/core")
        assert core["started_at"] == STAMP

    def test_a_whole_score_is_written_as_an_integer(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--status", "failed",
                    "--quality-score", "72")[0] == 0
        core = _read(path)["skills"][0]
        assert core["quality_score"] == 72 and isinstance(core["quality_score"], int)
        assert core["completed_at"] is None

    def test_pending_resets_a_skill_for_a_rerun(self, tmp_path, capsys):
        done = _skill("core", status="completed", started_at=STAMP, completed_at=STAMP, quality_score=95)
        path = _write(tmp_path, _state(skills=[done]))
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--status", "pending")[0] == 0
        core = _read(path)["skills"][0]
        assert (core["status"], core["started_at"], core["completed_at"]) == ("pending", None, None)

    def test_several_skills_at_once(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core", "--skill", "web",
                    "--status", "skipped")[0] == 0
        assert [s["status"] for s in _read(path)["skills"]] == ["skipped", "skipped", "pending"]

    def test_brief_path_alone(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-skill", "--state-file", str(path), "--skill", "core",
                    "--brief-path", "forge-data/core/skill-brief.yaml")[0] == 0
        core = _read(path)["skills"][0]
        assert (core["status"], core["brief_path"]) == ("pending", "forge-data/core/skill-brief.yaml")

    def test_unknown_skill_writes_nothing(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        before = path.read_bytes()
        rc, err = _run(capsys, "set-skill", "--state-file", str(path), "--skill", "ghost", "--status", "active")
        assert (rc, err["code"]) == (2, "unknown-skill")
        assert path.read_bytes() == before and not _bak(path).exists()


class TestApplyPlan:
    def test_writes_the_order_campaign_deps_computes(self, tmp_path, capsys):
        skills = [_skill("web", depends_on=["core"]), _skill("util", tier="B"), _skill("core")]
        path = _write(tmp_path, _state(skills=skills, order=[]))
        rc, out = _run(capsys, "apply-plan", "--state-file", str(path), "--stage", "1")
        assert rc == 0
        state = _read(path)
        assert state["dependency_graph"] == {"execution_order": ["core", "web", "util"],
                                             "circular_deps_detected": False}
        assert state["campaign"]["current_stage"] == 1
        assert out["execution_order"] == ["core", "web", "util"]

    @pytest.mark.parametrize(
        "skills",
        [
            [_skill("a", depends_on=["b"]), _skill("b", depends_on=["a"])],
            [_skill("a", depends_on=["nope"])],
            [_skill("a", depends_on=["b"]), _skill("b", tier="B")],
        ],
        ids=["cycle", "dangling", "tier-inversion"],
    )
    def test_a_plan_the_stages_cannot_follow_writes_nothing(self, tmp_path, capsys, skills):
        path = _write(tmp_path, _state(skills=skills, order=[]))
        before = path.read_bytes()
        rc, err = _run(capsys, "apply-plan", "--state-file", str(path), "--stage", "1")
        assert (rc, err["code"]) == (4, "plan-unorderable")
        assert err["errors"]
        assert path.read_bytes() == before


class TestApplyPinsAndProvenance:
    def test_resolved_and_retagged_pins_are_written(self, tmp_path, capsys):
        skills = [_skill("core", pin="2.0.0"), _skill("web"), _skill("util", tier="B", pin="main")]
        path = _write(tmp_path, _state(skills=skills))
        results = tmp_path / "_pin-results.json"
        results.write_text(json.dumps({"results": [
            {"name": "core", "status": "valid", "pin": "2.0.0", "resolved_ref": "v2.0.0"},
            {"name": "web", "status": "resolved", "pin": None, "resolved_ref": "v3.1.0"},
            {"name": "util", "status": "valid", "pin": "main", "resolved_ref": "main"},
        ]}), encoding="utf-8")
        rc, _ = _run(capsys, "apply-pins", "--state-file", str(path), "--results-file", str(results), "--stage", "2")
        assert rc == 0
        state = _read(path)
        assert [s["pin"] for s in state["skills"]] == ["v2.0.0", "v3.1.0", "main"]
        assert state["campaign"]["current_stage"] == 2

    def test_an_invalid_pin_writes_nothing(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        results = tmp_path / "_pin-results.json"
        results.write_text(json.dumps({"results": [{"name": "core", "status": "invalid", "suggestions": []}]}),
                           encoding="utf-8")
        before = path.read_bytes()
        rc, err = _run(capsys, "apply-pins", "--state-file", str(path), "--results-file", str(results))
        assert (rc, err["code"]) == (5, "invalid-pin")
        assert path.read_bytes() == before

    def test_commit_shas_are_written(self, tmp_path, capsys):
        path = _write(tmp_path, _state(stage=2))
        results = tmp_path / "_provenance-results.json"
        results.write_text(json.dumps({"results": [
            {"name": n, "status": "accessible", "commit_sha": f"{n}-sha"} for n in ("core", "web", "util")
        ], "all_accessible": True}), encoding="utf-8")
        rc, _ = _run(capsys, "apply-provenance", "--state-file", str(path), "--results-file", str(results),
                     "--stage", "3")
        assert rc == 0
        state = _read(path)
        assert [s["commit_sha"] for s in state["skills"]] == ["core-sha", "web-sha", "util-sha"]
        assert state["campaign"]["current_stage"] == 3

    def test_an_inaccessible_repo_writes_nothing(self, tmp_path, capsys):
        path = _write(tmp_path, _state(stage=2))
        results = tmp_path / "_provenance-results.json"
        results.write_text(json.dumps({"results": [
            {"name": "core", "status": "inaccessible", "commit_sha": None, "error": "gh: Not Found (HTTP 404)"}]}),
            encoding="utf-8")
        rc, err = _run(capsys, "apply-provenance", "--state-file", str(path), "--results-file", str(results))
        assert (rc, err["code"]) == (6, "inaccessible-repo")
        assert _read(path)["skills"][0]["commit_sha"] is None

    def test_results_without_a_list_are_exit_2(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        results = tmp_path / "r.json"
        results.write_text('{"error": "gh missing"}', encoding="utf-8")
        rc, err = _run(capsys, "apply-pins", "--state-file", str(path), "--results-file", str(results))
        assert (rc, err["code"]) == (2, "input-unreadable")


class TestAppendWorkarounds:
    def test_appends_each_entry_once(self, tmp_path, capsys):
        path = _write(tmp_path, _state(skills=[_skill("core", workarounds_applied=["[doc-rot] a: rename"])]))
        rc, out = _run(capsys, "append-workarounds", "--state-file", str(path), "--skill", "core",
                       "--entry", "[doc-rot] a: rename", "--entry", "[doc-rot] b: removal")
        assert rc == 0
        assert out["added"] == ["[doc-rot] b: removal"]
        assert _read(path)["skills"][0]["workarounds_applied"] == ["[doc-rot] a: rename", "[doc-rot] b: removal"]


class TestSetCampaign:
    def test_records_the_capstone_from_its_envelope(self, tmp_path, capsys, monkeypatch):
        path = _write(tmp_path, _state(stage=5))
        _stdin(monkeypatch, 'SKF_STACK_RESULT_JSON: {"status":"success","skill_package":"skills/demo-stack",'
                            '"quality_score":88,"halt_reason":null}\n')
        rc, out = _run(capsys, "set-campaign", "--state-file", str(path), "--capstone", "-", "--stage", "6")
        assert rc == 0
        state = _read(path)
        assert state["campaign"]["capstone"] == {"skill_path": "skills/demo-stack", "quality_score": 88,
                                                 "verified": None, "completed_at": STAMP}
        assert state["campaign"]["current_stage"] == 6
        assert out["recorded"] == ["capstone"]

    def test_an_error_envelope_records_null(self, tmp_path, capsys, monkeypatch):
        path = _write(tmp_path, _state(stage=5))
        _stdin(monkeypatch, 'SKF_STACK_RESULT_JSON: {"status":"error","halt_reason":"no-skills"}\n')
        rc, out = _run(capsys, "set-campaign", "--state-file", str(path), "--capstone", "-", "--stage", "6")
        assert rc == 0
        assert _read(path)["campaign"]["capstone"] is None
        assert out["not_recorded"] == [{"field": "capstone", "status": "error", "halt_reason": "no-skills",
                                        "exit_code": None}]

    @pytest.mark.parametrize("verdict, verified", [("FEASIBLE", True), ("NOT_FEASIBLE", False)])
    def test_verification_sets_the_capstone_verified(self, tmp_path, capsys, verdict, verified):
        state = _state(stage=6)
        state["campaign"]["capstone"] = {"skill_path": "s", "quality_score": 80, "verified": None,
                                         "completed_at": STAMP}
        path = _write(tmp_path, state)
        envelope = tmp_path / "vs.txt"
        envelope.write_text("SKF_VERIFY_STACK_RESULT_JSON: " + json.dumps({
            "status": "success", "report_path": "fr-demo-20261001-120000.md", "report_latest_path": "fr-latest.md",
            "overall_verdict": verdict, "coverage_percentage": 87.5, "recommendation_count": 2,
            "exit_code": 0, "halt_reason": None, "run_id": "20261001-120000", "result_path": None,
        }) + "\n", encoding="utf-8")
        rc, _ = _run(capsys, "set-campaign", "--state-file", str(path), "--verification", str(envelope),
                     "--stage", "7")
        assert rc == 0
        campaign = _read(path)["campaign"]
        assert campaign["verification"] == {"report_path": "fr-demo-20261001-120000.md",
                                            "overall_verdict": verdict, "coverage_percentage": 87.5,
                                            "recommendation_count": 2}
        assert campaign["capstone"]["verified"] is verified

    def test_refinement_and_architecture_doc(self, tmp_path, capsys, monkeypatch):
        path = _write(tmp_path, _state(stage=7))
        _stdin(monkeypatch, json.dumps({"status": "success", "refined_path": "docs/refined.md", "gap_count": 1,
                                        "issue_count": 0, "improvement_count": 3, "exit_code": 0}))
        rc, _ = _run(capsys, "set-campaign", "--state-file", str(path), "--architecture-doc-path",
                     "docs/architecture.md", "--refinement", "-", "--stage", "8")
        assert rc == 0
        campaign = _read(path)["campaign"]
        assert campaign["architecture_doc_path"] == "docs/architecture.md"
        assert campaign["refinement"] == {"refined_path": "docs/refined.md", "gap_count": 1, "issue_count": 0,
                                          "improvement_count": 3}

    def test_no_capstone_records_null(self, tmp_path, capsys):
        state = _state(stage=5)
        state["campaign"]["capstone"] = {"skill_path": "old"}
        path = _write(tmp_path, state)
        assert _run(capsys, "set-campaign", "--state-file", str(path), "--no-capstone", "--stage", "6")[0] == 0
        assert _read(path)["campaign"]["capstone"] is None

    def test_a_line_with_no_envelope_is_exit_2(self, tmp_path, capsys, monkeypatch):
        path = _write(tmp_path, _state(stage=5))
        _stdin(monkeypatch, "\n")
        rc, err = _run(capsys, "set-campaign", "--state-file", str(path), "--capstone", "-")
        assert (rc, err["code"]) == (2, "input-unreadable")


class TestRecoverAndLog:
    def test_recover_copies_a_valid_backup_over_a_corrupt_primary(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")[0] == 0
        good = _bak(path).read_bytes()
        path.write_bytes(b"campaign: [half a wri")
        rc, out = _run(capsys, "recover", "--state-file", str(path))
        assert rc == 0
        assert out["recovered"] is True and out["current_stage"] == 0
        assert path.read_bytes() == good

    def test_recover_restores_a_missing_primary(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")[0] == 0
        path.unlink()
        assert _run(capsys, "recover", "--state-file", str(path))[0] == 0
        assert mod.validation_errors(_read(path)) == []

    @pytest.mark.parametrize("backup", [None, b"campaign: {}\n"], ids=["missing", "invalid"])
    def test_recover_without_a_valid_backup_is_exit_9(self, tmp_path, capsys, backup):
        path = tmp_path / "_campaign-state.yaml"
        path.write_bytes(b"broken: [")
        if backup is not None:
            _bak(path).write_bytes(backup)
        rc, err = _run(capsys, "recover", "--state-file", str(path))
        assert (rc, err["code"]) == (9, "corrupt-state")
        assert path.read_bytes() == b"broken: ["

    def test_log_appends_one_typed_timestamped_line(self, tmp_path, capsys):
        log = tmp_path / "_campaign-decision-log.md"
        assert _run(capsys, "log", "--log-file", str(log), "--type", "auto", "--text",
                    "headless: auto-proceed past plan-confirmation gate")[0] == 0
        assert _run(capsys, "log", "--log-file", str(log), "--type", "event", "--text", "core failed:\n  FAIL")[0] == 0
        assert log.read_text(encoding="utf-8").splitlines() == [
            f"- {STAMP} (auto) headless: auto-proceed past plan-confirmation gate",
            f"- {LATER} (event) core failed: FAIL",
        ]

    def test_log_type_is_closed(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            mod.main(["log", "--log-file", str(tmp_path / "l.md"), "--type", "note", "--text", "x"])
        assert exc.value.code == 2


# --------------------------------------------------------------------------
# Archive (overwrite) and the HARD HALT payload
# --------------------------------------------------------------------------


def _brief(tmp_path: pathlib.Path) -> pathlib.Path:
    brief = tmp_path / "campaign-brief.yaml"
    brief.write_bytes(b"campaign_name: demo\ntargets: []\n")
    return brief


class TestArchive:
    def test_moves_the_state_its_backup_and_the_brief(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")[0] == 0
        brief = _brief(tmp_path)
        rc, out = _run(capsys, "archive", "--state-file", str(path), "--brief-file", str(brief))
        assert rc == 0
        # The set-stage write took STAMP; the archive takes LATER, with no colon.
        folder = tmp_path / "archive" / "demo-2026-10-01T133000Z"
        assert pathlib.Path(out["archive_dir"]).as_posix() == folder.as_posix()
        assert sorted(p.name for p in folder.iterdir()) == [
            "_campaign-state.yaml", "_campaign-state.yaml.bak", "campaign-brief.yaml"]
        assert len(out["moved"]) == 3
        assert not path.exists() and not _bak(path).exists() and not brief.exists()

    def test_init_can_start_again_after_an_archive(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        assert _run(capsys, "set-stage", "--state-file", str(path), "--stage", "1")[0] == 0
        assert _run(capsys, "archive", "--state-file", str(path), "--brief-file", str(_brief(tmp_path)))[0] == 0
        targets = tmp_path / "targets.json"
        targets.write_text(json.dumps(TARGETS), encoding="utf-8")
        assert _init(capsys, path, targets)[0] == 0

    def test_a_corrupt_primary_takes_its_name_from_the_backup(self, tmp_path, capsys):
        path = tmp_path / "_campaign-state.yaml"
        path.write_bytes(b"campaign: [half a wri")
        state = _state()
        state["campaign"]["name"] = "Web Stack: 2026"
        _bak(path).write_bytes(yaml.safe_dump(state).encode("utf-8"))
        rc, out = _run(capsys, "archive", "--state-file", str(path), "--brief-file", str(tmp_path / "none.yaml"))
        assert rc == 0
        assert pathlib.Path(out["archive_dir"]).name == "Web-Stack-2026-2026-10-01T120000Z"
        assert len(out["moved"]) == 2

    def test_an_existing_folder_is_refused(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        (tmp_path / "archive" / "demo-2026-10-01T120000Z").mkdir(parents=True)
        rc, err = _run(capsys, "archive", "--state-file", str(path), "--brief-file", str(_brief(tmp_path)))
        assert (rc, err["code"]) == (2, "archive-exists")
        assert path.is_file()

    def test_nothing_to_archive_is_exit_2(self, tmp_path, capsys):
        rc, err = _run(capsys, "archive", "--state-file", str(tmp_path / "_campaign-state.yaml"),
                       "--brief-file", str(tmp_path / "campaign-brief.yaml"))
        assert (rc, err["code"]) == (2, "nothing-to-archive")


EMITTER = REPO_ROOT / "src" / "shared" / "scripts" / "skf-emit-result-envelope.py"
ENVELOPE_SCHEMA = REPO_ROOT / "src" / "shared" / "scripts" / "schemas" / "skf-campaign-result-envelope.v1.json"


class TestHaltPayload:
    def test_counts_the_state_and_reads_the_message_on_stdin(self, tmp_path, capsys, monkeypatch):
        skills = [_skill("core", status="completed"), _skill("web", status="failed"),
                  _skill("util", tier="B", status="completed")]
        path = _write(tmp_path, _state(stage=4, skills=skills))
        _stdin(monkeypatch, "Skill 'web' has no brief target:\n  `$HOME` stays literal\n")
        rc, out = _run(capsys, "halt-payload", "--state-file", str(path), "--phase", "skill-loop",
                       "--halt-reason", "missing-brief")
        assert rc == 0
        assert out == {
            "phase": "skill-loop",
            "reason": "Skill 'web' has no brief target: `$HOME` stays literal",
            "halt_reason": "missing-brief",
            "skills_completed": 2,
            "skills_failed": 1,
            "decision_log": (tmp_path / "_campaign-decision-log.md").as_posix(),
        }

    def test_before_setup_counts_zero_and_has_no_decision_log(self, tmp_path, capsys, monkeypatch):
        _stdin(monkeypatch, "A campaign needs at least one target.")
        rc, out = _run(capsys, "halt-payload", "--state-file", str(tmp_path / "ws" / "_campaign-state.yaml"),
                       "--phase", "setup", "--halt-reason", "invalid-input")
        assert rc == 0
        assert (out["skills_completed"], out["skills_failed"], out["decision_log"]) == (0, 0, None)

    def test_an_empty_message_is_refused(self, tmp_path, capsys, monkeypatch):
        _stdin(monkeypatch, "  \n")
        rc, err = _run(capsys, "halt-payload", "--state-file", str(tmp_path / "s.yaml"), "--phase", "setup",
                       "--halt-reason", "invalid-input")
        assert (rc, err["code"]) == (2, "input-unreadable")

    def test_the_emitter_builds_the_error_line_from_it(self, tmp_path, capsys, monkeypatch):
        path = _write(tmp_path, _state(stage=1, skills=[_skill("core", status="completed")]))
        _stdin(monkeypatch, "Invalid pin for core: 9.9.9")
        rc, payload = _run(capsys, "halt-payload", "--state-file", str(path), "--phase", "pins",
                           "--halt-reason", "invalid-pin")
        assert rc == 0
        proc = subprocess.run(
            [sys.executable, str(EMITTER), "emit-halt", "--workflow", "skf-campaign", "--target", "stdout"],
            input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert proc.returncode == 0, proc.stderr
        line = proc.stdout.strip().splitlines()[-1]
        assert line.startswith("SKF_CAMPAIGN_RESULT_JSON: ")
        envelope = json.loads(line.split(": ", 1)[1])
        assert (envelope["status"], envelope["exit_code"], envelope["phase"]) == ("error", 5, "pins")
        assert envelope["error"] == {"code": "invalid-pin", "message": "Invalid pin for core: 9.9.9"}
        assert envelope["skills_completed"] == 1


def test_refusal_exit_codes_are_the_campaigns():
    codes = json.loads(ENVELOPE_SCHEMA.read_text(encoding="utf-8"))["$defs"]["skf-envelope"]["const"]["exit_codes"]
    assert (mod.EXIT_INPUT, mod.EXIT_STATE, mod.EXIT_NO_BACKUP) == (
        codes["invalid-input"], codes["invalid-state"], codes["corrupt-state"])
    assert (mod.EXIT_CIRCULAR, mod.EXIT_PIN, mod.EXIT_REPO) == (
        codes["circular-deps"], codes["invalid-pin"], codes["inaccessible-repo"])


# --------------------------------------------------------------------------
# The resume point
# --------------------------------------------------------------------------


def _resume(state: dict, **kwargs) -> dict:
    return mod.resume_point(state, **kwargs)


class TestResumePoint:
    def test_active_tier_a_skill_resumes_the_skill_loop_with_no_plus_one(self):
        # 50d0e3bf: current_stage 3 + 1 would also be 4, so put the loop's last
        # write at 4 as well; an active Tier A skill still goes back to stage 4.
        for stage in (3, 4):
            state = _state(stage=stage, skills=[_skill("core", status="completed"), _skill("web", status="active"),
                                                _skill("util", tier="B")])
            point = _resume(state)
            assert (point["stage"], point["step_file"], point["reason"], point["skill"]) == (
                4, "step-05-skill-loop.md", "active-skill", "web")

    def test_active_tier_b_skill_resumes_the_batch(self):
        state = _state(stage=4, skills=[_skill("core", status="completed"), _skill("util", tier="B", status="active")])
        point = _resume(state)
        assert (point["stage"], point["step_file"], point["reason"]) == (5, "step-06-batch.md", "active-skill")

    def test_an_active_tier_a_skill_comes_before_an_active_tier_b_one(self):
        state = _state(stage=4, skills=[_skill("util", tier="B", status="active"), _skill("core", status="active")])
        assert _resume(state)["stage"] == 4

    @pytest.mark.parametrize("stage", range(0, 10))
    def test_no_active_skill_resumes_the_next_stage(self, stage):
        point = _resume(_state(stage=stage))
        assert (point["stage"], point["step_file"], point["reason"]) == (
            stage + 1, mod.STEP_FILES[stage + 1], "next-stage")

    def test_terminal_cap_reruns_stage_10_never_11(self):
        state = _state(stage=10, skills=[_skill("core", status="completed"), _skill("web", status="pending")])
        point = _resume(state)
        assert (point["stage"], point["step_file"], point["reason"], point["complete"]) == (
            10, "step-11-maintenance.md", "terminal-cap", False)

    def test_finished_campaign_is_complete(self):
        state = _state(stage=10, skills=[_skill("core", status="completed"), _skill("web", status="failed"),
                                         _skill("util", tier="B", status="skipped")])
        point = _resume(state)
        assert point["complete"] is True and point["stage"] is None and point["reason"] == "complete"

    def test_from_an_open_skill_resumes_its_tier_stage(self):
        state = _state(stage=6, skills=[_skill("core", status="completed"), _skill("util", tier="B")])
        point = _resume(state, from_skill="util")
        assert (point["stage"], point["reason"], point["skill"], point["needs_choice"]) == (
            5, "from-skill", "util", False)

    def test_from_a_finished_skill_needs_the_operators_choice(self):
        state = _state(stage=10, skills=[_skill("core", status="completed"), _skill("web")])
        point = _resume(state, from_skill="core")
        assert point["needs_choice"] is True and point["stage"] is None
        assert point["from_status"] == "completed"

    def test_from_next_takes_the_next_open_skill_in_execution_order(self):
        skills = [_skill("core", status="completed"), _skill("web", status="completed"),
                  _skill("util", tier="B", status="pending")]
        state = _state(stage=4, skills=skills, order=["core", "web", "util"])
        point = _resume(state, from_skill="core", take_next=True)
        assert (point["stage"], point["step_file"], point["reason"], point["skill"]) == (
            5, "step-06-batch.md", "from-next", "util")

    def test_from_next_with_nothing_after_is_complete(self):
        skills = [_skill("core", status="completed"), _skill("web", status="failed")]
        point = _resume(_state(stage=10, skills=skills), from_skill="core", take_next=True)
        assert point["complete"] is True and point["reason"] == "nothing-after-from"

    def test_from_warns_about_another_active_skill(self):
        state = _state(stage=4, skills=[_skill("core", status="active"), _skill("web")])
        assert _resume(state, from_skill="web")["active_other"] == "core"

    def test_cli_unknown_from_skill_is_exit_2(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        rc, err = _run(capsys, "resume", "--state-file", str(path), "--from", "ghost")
        assert (rc, err["code"]) == (2, "unknown-skill")
        assert "core, web, util" in err["error"]

    def test_cli_next_needs_from(self, tmp_path, capsys):
        path = _write(tmp_path, _state())
        rc, err = _run(capsys, "resume", "--state-file", str(path), "--next")
        assert (rc, err["code"]) == (2, "input-invalid")

    def test_cli_resume_is_read_only(self, tmp_path, capsys):
        path = _write(tmp_path, _state(stage=3))
        before = path.read_bytes()
        rc, out = _run(capsys, "resume", "--state-file", str(path))
        assert rc == 0 and out["step_file"] == "step-05-skill-loop.md"
        assert path.read_bytes() == before and not _bak(path).exists()

    def test_step_files_match_the_stages_table(self):
        skill_md = (REPO_ROOT / "src" / "skf-campaign" / "SKILL.md").read_text(encoding="utf-8")
        for stage, name in mod.STEP_FILES.items():
            assert f"| {stage} |" in skill_md and f"references/{name}" in skill_md
            assert (REPO_ROOT / "src" / "skf-campaign" / "references" / name).is_file()


# --------------------------------------------------------------------------
# A campaign interrupted during the Tier B batch resumes and completes it
# --------------------------------------------------------------------------


BRIEF = {"targets": [
    {"name": "core", "repo_url": "https://github.com/acme/core"},
    {"name": "util", "repo_url": "https://github.com/acme/util"},
    {"name": "cli", "repo_url": "https://github.com/acme/cli"},
]}


def test_interrupted_tier_b_batch_resumes_and_completes(tmp_path, capsys):
    skills = [_skill("core", status="completed", quality_score=93),
              _skill("util", tier="B", pin="v1.4.0"), _skill("cli", tier="B", pin="main")]
    path = _write(tmp_path, _state(stage=4, skills=skills, order=["core", "util", "cli"]))
    (tmp_path / "campaign-brief.yaml").write_text(yaml.safe_dump(BRIEF), encoding="utf-8")

    # step-06 renders the batch and marks its start; then the session dies
    # while quick-skill runs, before any result is recorded.
    lines, summary = batch.build_batch(_read(path), BRIEF)
    batch_map = tmp_path / "_batch-map.json"
    batch_map.write_text(json.dumps(batch.build_map(lines, summary, "_batch-input.txt")), encoding="utf-8")
    assert _run(capsys, "apply-batch", "--state-file", str(path), "--map-file", str(batch_map), "--start")[0] == 0
    interrupted = _read(path)
    assert [s["status"] for s in interrupted["skills"]] == ["completed", "active", "active"]
    assert interrupted["campaign"]["current_stage"] == 4

    # Resume goes back to the batch stage, with no +1 and no status reset.
    point = _resume(interrupted)
    assert (point["stage"], point["step_file"], point["reason"]) == (5, "step-06-batch.md", "active-skill")

    # The batch script selects the interrupted active skills again.
    lines, summary = batch.build_batch(interrupted, BRIEF)
    assert summary["skills"] == ["util", "cli"]
    assert lines == ["https://github.com/acme/util@v1.4.0", "https://github.com/acme/cli/tree/main"]
    batch_map.write_text(json.dumps(batch.build_map(lines, summary, "_batch-input.txt")), encoding="utf-8")

    # The rerun batch finishes; its results are joined and recorded with the stage.
    qs_summary = {"results": [
        {"batch": 1, "target": lines[0], "status": "success", "skill_package": "skills/util", "quality_score": 84},
        {"batch": 2, "target": lines[1], "status": "error", "error_code": "extraction-failed", "exit_code": 4},
    ]}
    joined = batch.join_results(json.loads(batch_map.read_text(encoding="utf-8")), qs_summary)
    results = tmp_path / "_batch-results.json"
    results.write_text(json.dumps(joined), encoding="utf-8")
    rc, out = _run(capsys, "apply-batch", "--state-file", str(path), "--map-file", str(batch_map),
                   "--results-file", str(results), "--stage", "5")
    assert rc == 0
    assert out["completed"] == ["util"]
    assert out["failed"] == [{"skill": "cli", "error_code": "extraction-failed"}]
    done = _read(path)
    util = done["skills"][1]
    assert (util["status"], util["quality_score"], util["skill_path"]) == ("completed", 84, "skills/util")
    assert util["started_at"] == STAMP and util["completed_at"] == LATER
    assert done["skills"][2]["status"] == "failed"
    assert done["campaign"]["current_stage"] == 5

    # The next resume continues past the batch.
    assert _resume(done)["stage"] == 6


class TestApplyBatchModes:
    def test_start_marks_skip_list_skills_skipped(self, tmp_path, capsys):
        skills = [_skill("util", tier="B"), _skill("cli", tier="B")]
        path = _write(tmp_path, _state(stage=4, skills=skills))
        batch_map = tmp_path / "_batch-map.json"
        batch_map.write_text(json.dumps({"batch_file": "b", "lines": [
            {"batch": 1, "skill": "util", "target": "https://github.com/acme/util", "line": "x"}],
            "skipped_by_directive": [{"name": "cli", "reason": "mid-rewrite"}]}), encoding="utf-8")
        rc, out = _run(capsys, "apply-batch", "--state-file", str(path), "--map-file", str(batch_map), "--start")
        assert rc == 0
        assert out["skipped"] == [{"name": "cli", "reason": "mid-rewrite"}]
        assert [s["status"] for s in _read(path)["skills"]] == ["active", "skipped"]

    def test_empty_batch_completes_the_stage(self, tmp_path, capsys):
        path = _write(tmp_path, _state(stage=4, skills=[_skill("core", status="completed")]))
        batch_map = tmp_path / "_batch-map.json"
        batch_map.write_text(json.dumps({"batch_file": "b", "lines": [], "skipped_by_directive": []}),
                             encoding="utf-8")
        assert _run(capsys, "apply-batch", "--state-file", str(path), "--map-file", str(batch_map), "--start",
                    "--stage", "5")[0] == 0
        assert _read(path)["campaign"]["current_stage"] == 5

    def test_no_results_fails_every_batched_skill(self, tmp_path, capsys):
        skills = [_skill("util", tier="B", status="active"), _skill("cli", tier="B", status="active")]
        path = _write(tmp_path, _state(stage=4, skills=skills))
        batch_map = tmp_path / "_batch-map.json"
        batch_map.write_text(json.dumps({"batch_file": "b", "lines": [
            {"batch": 1, "skill": "util", "target": "u", "line": "u"},
            {"batch": 2, "skill": "cli", "target": "c", "line": "c"}], "skipped_by_directive": []}),
            encoding="utf-8")
        rc, out = _run(capsys, "apply-batch", "--state-file", str(path), "--map-file", str(batch_map),
                       "--no-results", "--stage", "5")
        assert rc == 0
        assert [f["skill"] for f in out["failed"]] == ["util", "cli"]
        assert [s["status"] for s in _read(path)["skills"]] == ["failed", "failed"]

    def test_results_for_a_skill_the_map_does_not_hold_are_refused(self, tmp_path, capsys):
        path = _write(tmp_path, _state(stage=4))
        batch_map = tmp_path / "_batch-map.json"
        batch_map.write_text(json.dumps({"lines": [{"batch": 1, "skill": "util"}]}), encoding="utf-8")
        results = tmp_path / "r.json"
        results.write_text(json.dumps({"results": [{"skill": "core", "status": "completed"}]}), encoding="utf-8")
        rc, err = _run(capsys, "apply-batch", "--state-file", str(path), "--map-file", str(batch_map),
                       "--results-file", str(results))
        assert (rc, err["code"]) == (2, "input-unreadable")

    def test_one_mode_is_required(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            mod.main(["apply-batch", "--state-file", "s", "--map-file", "m"])
        assert exc.value.code == 2


def test_help_lists_every_operation(capsys):
    with pytest.raises(SystemExit) as exc:
        mod.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for op in mod.OPERATIONS:
        assert op in out
    for stage, name in mod.STEP_FILES.items():
        assert name.startswith(f"step-{stage + 1:02d}-")
