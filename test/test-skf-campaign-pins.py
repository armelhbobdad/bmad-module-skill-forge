#!/usr/bin/env python3
"""Tests for campaign-validate-pins.py.

Validates the campaign pin validation wrapper that reads state + brief
YAML files and delegates per-skill validation to the shared
skf-validate-pins.py module.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import io
from unittest.mock import patch

import pytest
import yaml

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "skf-campaign"
    / "scripts"
    / "campaign-validate-pins.py"
)

spec = importlib.util.spec_from_file_location("campaign_validate_pins", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _make_state(skills):
    return {
        "campaign": {
            "name": "test-campaign",
            "started_at": "2026-01-01T00:00:00+00:00",
            "last_updated": "2026-01-01T00:00:00+00:00",
            "current_stage": 1,
            "quality_gate": {
                "hard": "zero-critical-high",
                "soft_target": 90,
                "soft_fallback": 80,
            },
            "health_findings_queue": "local",
        },
        "skills": skills,
        "dependency_graph": {
            "execution_order": [],
            "circular_deps_detected": False,
        },
    }


def _make_brief(targets):
    return {
        "campaign_name": "test-campaign",
        "created_at": "2026-01-01T00:00:00+00:00",
        "targets": targets,
        "quality_gate": {
            "hard": "zero-critical-high",
            "soft_target": 90,
            "soft_fallback": 80,
        },
        "health_findings_queue": "local",
        "notes": "",
    }


def _make_skill(name, pin=None, tier="A"):
    return {
        "name": name,
        "status": "pending",
        "depends_on": [],
        "tier": tier,
        "pin": pin,
        "brief_path": None,
        "skill_path": None,
        "quality_score": None,
        "workarounds_applied": [],
        "started_at": None,
        "completed_at": None,
        "commit_sha": None,
    }


def _make_target(name, repo_url, pin=None, tier="A"):
    return {
        "name": name,
        "repo_url": repo_url,
        "tier": tier,
        "pin": pin,
        "depends_on": [],
    }


def _write_yaml(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)


# --------------------------------------------------------------------------
# Test: all skills with valid tags
# --------------------------------------------------------------------------

class TestAllValid:
    def test_all_valid_exit_0(self, tmp_path):
        state = _make_state([
            _make_skill("skill-a", pin="v1.0.0"),
            _make_skill("skill-b", pin="v2.0.0"),
        ])
        brief = _make_brief([
            _make_target("skill-a", "https://github.com/org/skill-a"),
            _make_target("skill-b", "https://github.com/org/skill-b"),
        ])
        state_file = tmp_path / "state.yaml"
        brief_file = tmp_path / "brief.yaml"
        _write_yaml(state_file, state)
        _write_yaml(brief_file, brief)

        def mock_validate(repo_url, pin=None, **kwargs):
            return {
                "status": "valid",
                "pin": pin,
                "resolved_ref": pin,
                "ref_type": "tag",
                "version": pin.lstrip("v") if pin else None,
                "suggestions": [],
            }

        captured = io.StringIO()
        with patch.object(mod, "_load_validate_pin", return_value=mock_validate):
            with patch("sys.stdout", captured):
                exit_code = mod.run(str(state_file), str(brief_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["all_valid"] is True
        assert output["invalid_count"] == 0
        assert len(output["results"]) == 2


# --------------------------------------------------------------------------
# Test: one skill with invalid pin
# --------------------------------------------------------------------------

class TestOneInvalid:
    def test_invalid_exit_1(self, tmp_path):
        state = _make_state([
            _make_skill("skill-a", pin="v99.0.0"),
        ])
        brief = _make_brief([
            _make_target("skill-a", "https://github.com/org/skill-a"),
        ])
        state_file = tmp_path / "state.yaml"
        brief_file = tmp_path / "brief.yaml"
        _write_yaml(state_file, state)
        _write_yaml(brief_file, brief)

        def mock_validate(repo_url, pin=None, **kwargs):
            return {
                "status": "invalid",
                "pin": pin,
                "resolved_ref": None,
                "ref_type": None,
                "version": None,
                "suggestions": ["v2.0.0", "v1.0.0"],
            }

        captured = io.StringIO()
        with patch.object(mod, "_load_validate_pin", return_value=mock_validate):
            with patch("sys.stdout", captured):
                exit_code = mod.run(str(state_file), str(brief_file))

        assert exit_code == 1
        output = json.loads(captured.getvalue())
        assert output["all_valid"] is False
        assert output["invalid_count"] == 1
        assert output["results"][0]["suggestions"] == ["v2.0.0", "v1.0.0"]


# --------------------------------------------------------------------------
# Test: skill with null pin → resolved
# --------------------------------------------------------------------------

class TestNullPinResolved:
    def test_resolved_exit_0(self, tmp_path):
        state = _make_state([
            _make_skill("skill-a", pin=None),
        ])
        brief = _make_brief([
            _make_target("skill-a", "https://github.com/org/skill-a"),
        ])
        state_file = tmp_path / "state.yaml"
        brief_file = tmp_path / "brief.yaml"
        _write_yaml(state_file, state)
        _write_yaml(brief_file, brief)

        def mock_validate(repo_url, pin=None, **kwargs):
            return {
                "status": "resolved",
                "pin": None,
                "resolved_ref": "v3.1.0",
                "ref_type": "tag",
                "version": "3.1.0",
                "suggestions": [],
            }

        captured = io.StringIO()
        with patch.object(mod, "_load_validate_pin", return_value=mock_validate):
            with patch("sys.stdout", captured):
                exit_code = mod.run(str(state_file), str(brief_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["results"][0]["status"] == "resolved"
        assert output["results"][0]["resolved_ref"] == "v3.1.0"
        assert output["resolved_count"] == 1


# --------------------------------------------------------------------------
# Test: mixed valid + invalid + null
# --------------------------------------------------------------------------

class TestMixed:
    def test_mixed_exit_1(self, tmp_path):
        state = _make_state([
            _make_skill("valid-skill", pin="v1.0.0"),
            _make_skill("invalid-skill", pin="v99.0.0"),
            _make_skill("null-skill", pin=None),
        ])
        brief = _make_brief([
            _make_target("valid-skill", "https://github.com/org/valid"),
            _make_target("invalid-skill", "https://github.com/org/invalid"),
            _make_target("null-skill", "https://github.com/org/null-skill"),
        ])
        state_file = tmp_path / "state.yaml"
        brief_file = tmp_path / "brief.yaml"
        _write_yaml(state_file, state)
        _write_yaml(brief_file, brief)

        responses = {
            "https://github.com/org/valid": {
                "status": "valid", "pin": "v1.0.0", "resolved_ref": "v1.0.0",
                "ref_type": "tag", "version": "1.0.0", "suggestions": [],
            },
            "https://github.com/org/invalid": {
                "status": "invalid", "pin": "v99.0.0", "resolved_ref": None,
                "ref_type": None, "version": None, "suggestions": ["v2.0.0"],
            },
            "https://github.com/org/null-skill": {
                "status": "resolved", "pin": None, "resolved_ref": "v3.0.0",
                "ref_type": "tag", "version": "3.0.0", "suggestions": [],
            },
        }

        def mock_validate(repo_url, pin=None, **kwargs):
            return responses[repo_url]

        captured = io.StringIO()
        with patch.object(mod, "_load_validate_pin", return_value=mock_validate):
            with patch("sys.stdout", captured):
                exit_code = mod.run(str(state_file), str(brief_file))

        assert exit_code == 1
        output = json.loads(captured.getvalue())
        assert output["all_valid"] is False
        assert output["invalid_count"] == 1
        assert output["resolved_count"] == 1
        assert len(output["results"]) == 3


# --------------------------------------------------------------------------
# Test: missing state file → exit 2
# --------------------------------------------------------------------------

class TestMissingState:
    def test_missing_state_exit_2(self, tmp_path):
        brief = _make_brief([])
        brief_file = tmp_path / "brief.yaml"
        _write_yaml(brief_file, brief)

        captured_err = io.StringIO()
        captured_out = io.StringIO()
        with patch("sys.stderr", captured_err), patch("sys.stdout", captured_out):
            exit_code = mod.run(str(tmp_path / "nonexistent.yaml"), str(brief_file))

        assert exit_code == 2
        err_output = json.loads(captured_err.getvalue())
        assert err_output["code"] == "STATE_NOT_FOUND"


# --------------------------------------------------------------------------
# Test: missing brief file → exit 2
# --------------------------------------------------------------------------

class TestMissingBrief:
    def test_missing_brief_exit_2(self, tmp_path):
        state = _make_state([])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured_err = io.StringIO()
        captured_out = io.StringIO()
        with patch("sys.stderr", captured_err), patch("sys.stdout", captured_out):
            exit_code = mod.run(str(state_file), str(tmp_path / "nonexistent.yaml"))

        assert exit_code == 2
        err_output = json.loads(captured_err.getvalue())
        assert err_output["code"] == "BRIEF_NOT_FOUND"


# --------------------------------------------------------------------------
# Test: skill not found in brief → exit 2
# --------------------------------------------------------------------------

class TestSkillNotInBrief:
    def test_skill_not_in_brief_exit_2(self, tmp_path):
        state = _make_state([
            _make_skill("orphan-skill", pin="v1.0.0"),
        ])
        brief = _make_brief([
            _make_target("other-skill", "https://github.com/org/other"),
        ])
        state_file = tmp_path / "state.yaml"
        brief_file = tmp_path / "brief.yaml"
        _write_yaml(state_file, state)
        _write_yaml(brief_file, brief)

        def mock_validate(repo_url, pin=None, **kwargs):
            return {
                "status": "valid", "pin": pin, "resolved_ref": pin,
                "ref_type": "tag", "version": "1.0.0", "suggestions": [],
            }

        captured_err = io.StringIO()
        captured_out = io.StringIO()
        with patch.object(mod, "_load_validate_pin", return_value=mock_validate):
            with patch("sys.stderr", captured_err), patch("sys.stdout", captured_out):
                exit_code = mod.run(str(state_file), str(brief_file))

        assert exit_code == 2
        err_output = json.loads(captured_err.getvalue())
        assert err_output["code"] == "SKILL_NOT_IN_BRIEF"
