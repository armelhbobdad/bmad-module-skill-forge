"""Tests for campaign-validate-state.py — deterministic schema check for state.

This script replaces ~13 per-step "mentally validate the state against the
schema" prose sites. These tests pin its contract: valid state → exit 0, schema
violations → exit 1 with translated errors, load failures → exit 1 with a
halt_reason, and a missing/unreadable schema → exit 2.
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
        "health_findings_queue": "local",
    },
    "skills": [],
    "dependency_graph": {"execution_order": [], "circular_deps_detected": False},
}


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
