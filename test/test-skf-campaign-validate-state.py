"""Tests for campaign-validate-state.py — deterministic schema check for state.

This script replaces ~13 per-step "mentally validate the state against the
schema" prose sites. These tests pin its contract: valid state → exit 0, schema
violations → exit 1 with translated errors, load failures → exit 1 with a
halt_reason, and a missing/unreadable schema → exit 2. They also pin two schema
facts step files rely on: overall_verdict takes Verify Stack's verdicts, and an
older state that still holds health_findings_queue validates. Every date-time
field must parse as ISO-8601 with a UTC offset: the schema's `format` is only
an annotation to Draft7Validator, so the script checks it itself.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "skf-campaign" / "scripts" / "campaign-validate-state.py"
SCHEMA = REPO_ROOT / "src" / "skf-campaign" / "assets" / "campaign-state-schema.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("campaign_validate_state", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()

VALID_STATE: dict = {
    "campaign": {
        "name": "test-campaign",
        "started_at": "2026-05-27T00:00:00Z",
        "last_updated": "2026-05-27T00:00:00Z",
        "current_stage": 0,
        "quality_gate": {"hard": "zero-critical-high", "soft_target": 90, "soft_fallback": 80},
    },
    "skills": [],
    "dependency_graph": {"execution_order": [], "circular_deps_detected": False},
}
VERIFY_STACK_VERDICTS = ("FEASIBLE", "CONDITIONALLY_FEASIBLE", "NOT_FEASIBLE")
REMOVED_VERDICTS = ("Verified", "Plausible", "Risky", "Blocked")


def _write_state(tmp_path: pathlib.Path, state: dict) -> pathlib.Path:
    p = tmp_path / "_campaign-state.yaml"
    p.write_text(yaml.dump(state, default_flow_style=False), encoding="utf-8")
    return p


class TestValidateStateFn:
    def test_valid_state_no_errors(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        result = mod.validate_state(VALID_STATE, schema)
        assert result["valid"] is True
        assert result["errors"] == []

    def test_bad_enum_reports_error(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["health_findings_queue"] = "remote"
        result = mod.validate_state(state, schema)
        assert result["valid"] is False
        assert any("health_findings_queue" in e["field"] for e in result["errors"])

    def test_extra_property_reports_error(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["nope"] = 1
        result = mod.validate_state(state, schema)
        assert result["valid"] is False

    @pytest.mark.parametrize("queue", ["local", "improvement"])
    def test_older_state_with_health_findings_queue_still_valid(self, queue):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["health_findings_queue"] = queue
        assert mod.validate_state(state, schema) == {"valid": True, "errors": []}

    @pytest.mark.parametrize("verdict", VERIFY_STACK_VERDICTS + (None,))
    def test_verify_stack_verdicts_valid(self, verdict):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["verification"] = {"report_path": "r.md", "overall_verdict": verdict}
        assert mod.validate_state(state, schema)["valid"] is True

    @pytest.mark.parametrize("verdict", REMOVED_VERDICTS)
    def test_pair_verdict_tokens_rejected(self, verdict):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["verification"] = {"overall_verdict": verdict}
        result = mod.validate_state(state, schema)
        assert result["valid"] is False
        assert [e["field"] for e in result["errors"]] == ["campaign.verification.overall_verdict"]
        assert "FEASIBLE" in result["errors"][0]["message"]


class TestRun:
    def test_valid_exit_0(self, tmp_path, capsys):
        state_file = _write_state(tmp_path, VALID_STATE)
        rc = mod.run(str(state_file))
        assert rc == 0
        out = json.loads(capsys.readouterr().out.strip())
        assert out["valid"] is True
        assert out["halt_reason"] is None

    def test_invalid_exit_1(self, tmp_path, capsys):
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["current_stage"] = 99  # > maximum
        state_file = _write_state(tmp_path, state)
        rc = mod.run(str(state_file))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["valid"] is False
        assert out["halt_reason"] == "state-invalid"
        assert out["errors"]

    def test_missing_required_field(self, tmp_path, capsys):
        state = copy.deepcopy(VALID_STATE)
        del state["campaign"]["name"]
        state_file = _write_state(tmp_path, state)
        rc = mod.run(str(state_file))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert any(e["field"] == "name" for e in out["errors"])

    def test_verified_capstone_state_exit_0(self, tmp_path, capsys):
        # What step-08 writes after a FEASIBLE run: the verdict and a verified capstone.
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["current_stage"] = 7
        state["campaign"]["capstone"] = {"skill_path": "skills/stack/", "quality_score": 91.0, "verified": True}
        state["campaign"]["verification"] = {
            "report_path": "forge-data/feasibility-report-demo-20260930-120000.md",
            "overall_verdict": "FEASIBLE",
            "coverage_percentage": 100,
            "recommendation_count": 0,
        }
        rc = mod.run(str(_write_state(tmp_path, state)))
        assert rc == 0
        assert json.loads(capsys.readouterr().out.strip())["valid"] is True

    def test_removed_verdict_exit_1(self, tmp_path, capsys):
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["verification"] = {"overall_verdict": "Verified"}
        rc = mod.run(str(_write_state(tmp_path, state)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["halt_reason"] == "state-invalid"

    def test_missing_file_exit_1(self, tmp_path, capsys):
        rc = mod.run(str(tmp_path / "nope.yaml"))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["halt_reason"] == "state-missing"

    def test_malformed_yaml_exit_1(self, tmp_path, capsys):
        p = tmp_path / "bad.yaml"
        p.write_text(": : : not yaml [[[", encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["halt_reason"] == "state-malformed"

    def test_non_mapping_state_exit_1(self, tmp_path, capsys):
        p = tmp_path / "list.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["halt_reason"] == "state-malformed"

    def test_missing_schema_exit_2(self, tmp_path, capsys):
        state_file = _write_state(tmp_path, VALID_STATE)
        rc = mod.run(str(state_file), schema_file=str(tmp_path / "no-schema.json"))
        assert rc == 2
        out = json.loads(capsys.readouterr().out.strip())
        assert out["valid"] is False

    def test_explicit_schema_file(self, tmp_path, capsys):
        state_file = _write_state(tmp_path, VALID_STATE)
        rc = mod.run(str(state_file), schema_file=str(SCHEMA))
        assert rc == 0


# Every field the schema marks `format: date-time`, as a path into the state.
DATE_TIME_FIELDS = [
    ("campaign", "started_at"),
    ("campaign", "last_updated"),
    ("campaign", "capstone", "completed_at"),
    ("skills", 0, "started_at"),
    ("skills", 0, "completed_at"),
]
GOOD_STAMPS = ["2026-05-27T00:00:00Z", "2026-05-27T00:00:00+00:00", "2026-05-27T02:00:00.123+02:00",
               "2026-05-27T00:00:00z"]
BAD_STAMPS = ["2026-05-27T00:00:00", "2026-05-27", "yesterday", "2026-13-01T00:00:00Z", "", "now Z"]


def _with_stamp(path, value):
    state = copy.deepcopy(VALID_STATE)
    state["campaign"]["capstone"] = {"skill_path": "s", "completed_at": "2026-05-27T00:00:00Z"}
    state["skills"] = [{"name": "a", "status": "completed", "tier": "A",
                        "started_at": "2026-05-27T00:00:00Z", "completed_at": "2026-05-27T00:00:00Z"}]
    node = state
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return state


class TestDateTimeFields:
    def test_every_date_time_field_is_covered(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        found = []

        def walk(node, where):
            if isinstance(node, dict):
                if node.get("format") == "date-time":
                    found.append(where)
                for key, child in (node.get("properties") or {}).items():
                    walk(child, where + (key,))
                if isinstance(node.get("items"), dict):
                    walk(node["items"], where + (0,))

        walk(schema, ())
        assert sorted(found, key=str) == sorted(DATE_TIME_FIELDS, key=str)

    @pytest.mark.parametrize("path", DATE_TIME_FIELDS, ids=lambda p: ".".join(map(str, p)))
    @pytest.mark.parametrize("stamp", GOOD_STAMPS)
    def test_iso_8601_with_an_offset_is_valid(self, path, stamp):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert mod.validate_state(_with_stamp(path, stamp), schema)["errors"] == []

    @pytest.mark.parametrize("path", DATE_TIME_FIELDS, ids=lambda p: ".".join(map(str, p)))
    @pytest.mark.parametrize("stamp", BAD_STAMPS, ids=["no-offset", "date-only", "word", "month-13", "empty",
                                                       "garbage"])
    def test_anything_else_is_refused(self, path, stamp):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        errors = mod.validate_state(_with_stamp(path, stamp), schema)["errors"]
        field = "".join(f"[{p}]" if isinstance(p, int) else (f".{p}" if i else p) for i, p in enumerate(path))
        assert [e["field"] for e in errors] == [field]
        assert "UTC offset" in errors[0]["message"]

    @pytest.mark.parametrize("path", [("skills", 0, "started_at"), ("campaign", "capstone", "completed_at")])
    def test_a_nullable_stamp_may_be_null(self, path):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        assert mod.validate_state(_with_stamp(path, None), schema)["valid"] is True

    def test_offsetless_stamp_on_disk_exits_1(self, tmp_path, capsys):
        state = copy.deepcopy(VALID_STATE)
        state["campaign"]["last_updated"] = "2026-05-27T00:00:00"
        rc = mod.run(str(_write_state(tmp_path, state)))
        assert rc == 1
        out = json.loads(capsys.readouterr().out.strip())
        assert out["halt_reason"] == "state-invalid"
        assert [e["field"] for e in out["errors"]] == ["campaign.last_updated"]

    def test_unquoted_yaml_timestamp_keeps_its_quote_hint(self, tmp_path, capsys):
        p = tmp_path / "_campaign-state.yaml"
        text = yaml.safe_dump(VALID_STATE).replace("'2026-05-27T00:00:00Z'", "2026-05-27T00:00:00Z")
        p.write_text(text, encoding="utf-8")
        rc = mod.run(str(p))
        assert rc == 1
        messages = [e["message"] for e in json.loads(capsys.readouterr().out.strip())["errors"]]
        assert messages and all("Quote it" in m for m in messages)
