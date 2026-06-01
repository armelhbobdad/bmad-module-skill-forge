#!/usr/bin/env python3
"""Tests for campaign-deps.py.

Validates topological sort computation, circular dependency detection,
dangling reference detection, and per-skill dependency readiness checks.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "skf-campaign"
    / "scripts"
    / "campaign-deps.py"
)

spec = importlib.util.spec_from_file_location("campaign_deps", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

def _make_skill(name, depends_on=None, tier="A", status="pending"):
    return {
        "name": name,
        "status": status,
        "depends_on": depends_on or [],
        "tier": tier,
        "pin": None,
        "brief_path": None,
        "skill_path": None,
        "quality_score": None,
        "workarounds_applied": [],
        "started_at": None,
        "completed_at": None,
        "commit_sha": None,
    }


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


def _write_yaml(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False)


# --------------------------------------------------------------------------
# Test --compute: linear chain A→B→C
# --------------------------------------------------------------------------

class TestComputeLinearChain:
    def test_linear_chain(self, tmp_path):
        state = _make_state([
            _make_skill("A"),
            _make_skill("B", depends_on=["A"]),
            _make_skill("C", depends_on=["B"]),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["execution_order"] == ["A", "B", "C"]
        assert output["circular_deps_detected"] is False
        assert output["cycle_participants"] is None


# --------------------------------------------------------------------------
# Test --compute: diamond A→{B,C}→D
# --------------------------------------------------------------------------

class TestComputeDiamond:
    def test_diamond_dependency(self, tmp_path):
        state = _make_state([
            _make_skill("A"),
            _make_skill("B", depends_on=["A"]),
            _make_skill("C", depends_on=["A"]),
            _make_skill("D", depends_on=["B", "C"]),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        order = output["execution_order"]
        assert order[0] == "A"
        assert order[-1] == "D"
        assert set(order) == {"A", "B", "C", "D"}
        assert output["circular_deps_detected"] is False


# --------------------------------------------------------------------------
# Test --compute: no dependencies → all skills in order (Tier A before B)
# --------------------------------------------------------------------------

class TestComputeNoDeps:
    def test_no_deps_tier_order(self, tmp_path):
        state = _make_state([
            _make_skill("z-skill", tier="B"),
            _make_skill("a-skill", tier="A"),
            _make_skill("m-skill", tier="A"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        order = output["execution_order"]
        tier_a = [n for n in order if n != "z-skill"]
        assert tier_a == ["a-skill", "m-skill"]
        assert order.index("z-skill") > order.index("a-skill")
        assert order.index("z-skill") > order.index("m-skill")


# --------------------------------------------------------------------------
# Test --compute: circular dependency A→B→A
# --------------------------------------------------------------------------

class TestComputeCircular:
    def test_circular_exit_1(self, tmp_path):
        state = _make_state([
            _make_skill("A", depends_on=["B"]),
            _make_skill("B", depends_on=["A"]),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 1
        output = json.loads(captured.getvalue())
        assert output["circular_deps_detected"] is True
        assert sorted(output["cycle_participants"]) == ["A", "B"]


# --------------------------------------------------------------------------
# Test --compute: dangling dependency reference
# --------------------------------------------------------------------------

class TestComputeDangling:
    def test_dangling_exit_1(self, tmp_path):
        state = _make_state([
            _make_skill("A", depends_on=["nonexistent"]),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured_err = io.StringIO()
        captured_out = io.StringIO()
        with patch("sys.stderr", captured_err), patch("sys.stdout", captured_out):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 1
        err = json.loads(captured_err.getvalue())
        assert err["code"] == "DANGLING_DEPENDENCY"
        assert "nonexistent" in err["error"]


# --------------------------------------------------------------------------
# Test --check: skill with no dependencies → ready
# --------------------------------------------------------------------------

class TestCheckNoDeps:
    def test_no_deps_ready(self, tmp_path):
        state = _make_state([
            _make_skill("standalone"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.check(str(state_file), "standalone")

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["ready"] is True
        assert output["unmet_deps"] == []
        assert output["forced"] is False


# --------------------------------------------------------------------------
# Test --check: all deps completed → ready
# --------------------------------------------------------------------------

class TestCheckReady:
    def test_all_deps_completed(self, tmp_path):
        state = _make_state([
            _make_skill("dep-a", status="completed"),
            _make_skill("target", depends_on=["dep-a"], status="pending"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.check(str(state_file), "target")

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["ready"] is True
        assert output["unmet_deps"] == []
        assert output["forced"] is False


# --------------------------------------------------------------------------
# Test --check: one dep pending → not ready
# --------------------------------------------------------------------------

class TestCheckUnmet:
    def test_one_dep_pending(self, tmp_path):
        state = _make_state([
            _make_skill("dep-a", status="pending"),
            _make_skill("target", depends_on=["dep-a"], status="pending"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.check(str(state_file), "target")

        assert exit_code == 1
        output = json.loads(captured.getvalue())
        assert output["ready"] is False
        assert output["unmet_deps"] == ["dep-a"]


# --------------------------------------------------------------------------
# Test --check --force: unmet deps but force
# --------------------------------------------------------------------------

class TestCheckForce:
    def test_force_override(self, tmp_path):
        state = _make_state([
            _make_skill("dep-a", status="pending"),
            _make_skill("target", depends_on=["dep-a"], status="pending"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.check(str(state_file), "target", force=True)

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["ready"] is False
        assert output["forced"] is True
        assert output["unmet_deps"] == ["dep-a"]

    def test_force_emits_stderr_warning(self, tmp_path):
        state = _make_state([
            _make_skill("dep-a", status="pending"),
            _make_skill("target", depends_on=["dep-a"], status="pending"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured_out = io.StringIO()
        captured_err = io.StringIO()
        with patch("sys.stdout", captured_out), patch("sys.stderr", captured_err):
            mod.check(str(state_file), "target", force=True)

        warning = json.loads(captured_err.getvalue())
        assert "warning" in warning
        assert "target" in warning["warning"]
        assert warning["unmet"] == ["dep-a"]


# --------------------------------------------------------------------------
# Test: missing state file → exit 2
# --------------------------------------------------------------------------

class TestMissingStateFile:
    def test_compute_missing(self, tmp_path):
        captured_err = io.StringIO()
        captured_out = io.StringIO()
        with patch("sys.stderr", captured_err), patch("sys.stdout", captured_out):
            exit_code = mod.compute(str(tmp_path / "nonexistent.yaml"))

        assert exit_code == 2
        err = json.loads(captured_err.getvalue())
        assert err["code"] == "STATE_NOT_FOUND"

    def test_check_missing(self, tmp_path):
        captured_err = io.StringIO()
        captured_out = io.StringIO()
        with patch("sys.stderr", captured_err), patch("sys.stdout", captured_out):
            exit_code = mod.check(str(tmp_path / "nonexistent.yaml"), "any")

        assert exit_code == 2
        err = json.loads(captured_err.getvalue())
        assert err["code"] == "STATE_NOT_FOUND"


# --------------------------------------------------------------------------
# Test --compute: Tier A before Tier B within same dependency level
# --------------------------------------------------------------------------

class TestComputeTierPriority:
    def test_tier_a_before_b_same_level(self, tmp_path):
        state = _make_state([
            _make_skill("root", tier="A"),
            _make_skill("tier-b-child", depends_on=["root"], tier="B"),
            _make_skill("tier-a-child", depends_on=["root"], tier="A"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        order = output["execution_order"]
        assert order[0] == "root"
        assert order.index("tier-a-child") < order.index("tier-b-child")
