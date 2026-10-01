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
# Test --compute: tier_counts payload (strategy view consumes this instead of
# hand-tallying skills[] by tier)
# --------------------------------------------------------------------------

class TestComputeTierCounts:
    def test_tier_counts_on_success(self, tmp_path):
        state = _make_state([
            _make_skill("a", tier="A"),
            _make_skill("b", tier="A"),
            _make_skill("c", tier="B"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 0
        output = json.loads(captured.getvalue())
        assert output["tier_counts"] == {"A": 2, "B": 1}

    def test_tier_counts_present_on_cycle(self, tmp_path):
        state = _make_state([
            _make_skill("A", depends_on=["B"], tier="A"),
            _make_skill("B", depends_on=["A"], tier="B"),
        ])
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, state)

        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = mod.compute(str(state_file))

        assert exit_code == 1
        output = json.loads(captured.getvalue())
        assert output["tier_counts"] == {"A": 1, "B": 1}


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


# --------------------------------------------------------------------------
# Test --compute: a Tier A skill that depends on a Tier B skill is rejected
# at strategy time (Tier B runs after the skill loop, so the gate never opens)
# --------------------------------------------------------------------------

def _compute(tmp_path, skills):
    state_file = tmp_path / "state.yaml"
    _write_yaml(state_file, _make_state(skills))
    out, err = io.StringIO(), io.StringIO()
    with patch("sys.stdout", out), patch("sys.stderr", err):
        exit_code = mod.compute(str(state_file))
    return exit_code, json.loads(out.getvalue()), err.getvalue()


class TestComputeTierInversion:
    def test_tier_a_on_tier_b_is_rejected(self, tmp_path):
        exit_code, output, err = _compute(tmp_path, [
            _make_skill("lib", tier="B"),
            _make_skill("app", depends_on=["lib"], tier="A"),
        ])
        assert exit_code == 1
        assert output["tier_inversions"] == [{"skill": "app", "depends_on": "lib"}]
        assert output["circular_deps_detected"] is False
        error = json.loads(err)
        assert error["code"] == "TIER_INVERSION"
        assert "app depends on lib" in error["error"]

    def test_tier_b_on_tier_a_is_fine(self, tmp_path):
        exit_code, output, err = _compute(tmp_path, [
            _make_skill("core", tier="A"),
            _make_skill("plugin", depends_on=["core"], tier="B"),
        ])
        assert exit_code == 0
        assert output["tier_inversions"] == []
        assert err == ""

    def test_every_inversion_is_named(self, tmp_path):
        exit_code, output, _ = _compute(tmp_path, [
            _make_skill("b1", tier="B"),
            _make_skill("b2", tier="B"),
            _make_skill("a1", depends_on=["b1", "b2"], tier="A"),
            _make_skill("a2", depends_on=["a1", "b2"], tier="A"),
        ])
        assert exit_code == 1
        assert output["tier_inversions"] == [
            {"skill": "a1", "depends_on": "b1"},
            {"skill": "a1", "depends_on": "b2"},
            {"skill": "a2", "depends_on": "b2"},
        ]


# --------------------------------------------------------------------------
# Test --check: the blocked-dependency default (skip when every unmet
# dependency failed or was skipped, halt while one is pending)
# --------------------------------------------------------------------------

def _check(tmp_path, skills, name):
    state_file = tmp_path / "state.yaml"
    _write_yaml(state_file, _make_state(skills))
    out = io.StringIO()
    with patch("sys.stdout", out):
        exit_code = mod.check(str(state_file), name)
    return exit_code, json.loads(out.getvalue())


class TestCheckDefaultAction:
    @pytest.mark.parametrize(
        "statuses, action",
        [
            (["failed"], "skip"),
            (["skipped"], "skip"),
            (["failed", "skipped"], "skip"),
            (["failed", "pending"], "halt"),
            (["active"], "halt"),
            (["pending"], "halt"),
        ],
        ids=["failed", "skipped", "failed-and-skipped", "one-pending", "active", "pending"],
    )
    def test_default_action(self, tmp_path, statuses, action):
        deps = [_make_skill(f"dep{i}", status=st) for i, st in enumerate(statuses)]
        exit_code, output = _check(
            tmp_path, deps + [_make_skill("app", depends_on=[d["name"] for d in deps])], "app"
        )
        assert exit_code == 1
        assert output["ready"] is False
        assert output["default_action"] == action
        assert output["unmet_status"] == {d["name"]: d["status"] for d in deps}

    def test_completed_deps_are_not_unmet(self, tmp_path):
        exit_code, output = _check(tmp_path, [
            _make_skill("done", status="completed"),
            _make_skill("gone", status="failed"),
            _make_skill("app", depends_on=["done", "gone"]),
        ], "app")
        assert exit_code == 1
        assert output["unmet_status"] == {"gone": "failed"}
        assert output["default_action"] == "skip"

    def test_ready_has_no_default(self, tmp_path):
        exit_code, output = _check(tmp_path, [
            _make_skill("done", status="completed"),
            _make_skill("app", depends_on=["done"]),
        ], "app")
        assert exit_code == 0
        assert output["default_action"] is None
        assert output["unmet_status"] == {}


# --------------------------------------------------------------------------
# Setup and Strategy apply one dependency rule: campaign-parse-manifest.py's
# dependency_problems, which --compute imports
# --------------------------------------------------------------------------

MANIFEST_PATH = SCRIPT_PATH.with_name("campaign-parse-manifest.py")
manifest_spec = importlib.util.spec_from_file_location("campaign_parse_manifest", MANIFEST_PATH)
manifest = importlib.util.module_from_spec(manifest_spec)
manifest_spec.loader.exec_module(manifest)


class TestOneDependencyRule:
    MANIFEST = (
        "lib,o/lib,B\n"
        "core,o/core,A\n"
        "app,o/app,A,;core,lib\n"
        "plug,o/plug,B,;app\n"
        "web,o/web,A,;lib\n"
    )

    def test_setup_and_strategy_report_the_same_inversions(self, tmp_path):
        parsed = manifest.parse_manifest_text(self.MANIFEST)
        assert parsed["errors"] == []
        skills = [_make_skill(t["name"], depends_on=t["depends_on"], tier=t["tier"]) for t in parsed["targets"]]
        exit_code, output, _ = _compute(tmp_path, skills)
        assert exit_code == 1
        assert output["tier_inversions"] == parsed["tier_inversions"] == [
            {"skill": "app", "depends_on": "lib"},
            {"skill": "web", "depends_on": "lib"},
        ]

    def test_setup_and_strategy_name_the_same_dangling_reference(self, tmp_path):
        parsed = manifest.parse_manifest_text("app,o/app,A,;ghost\n")
        assert parsed["dangling_depends_on"] == [{"skill": "app", "depends_on": "ghost"}]
        state_file = tmp_path / "state.yaml"
        _write_yaml(state_file, _make_state([_make_skill("app", depends_on=["ghost"])]))
        err = io.StringIO()
        with patch("sys.stdout", io.StringIO()), patch("sys.stderr", err):
            assert mod.compute(str(state_file)) == 1
        assert "app depends on unknown skill 'ghost'" in json.loads(err.getvalue())["error"]
