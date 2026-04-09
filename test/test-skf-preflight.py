#!/usr/bin/env python3
"""Tests for skf-preflight.py."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_preflight",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-preflight.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
run_preflight = mod.run_preflight


def make_project(tmpdir, config=None, sidecar=True, preferences=None, forge_tier=None):
    """Create a mock project structure for testing."""
    import yaml

    root = Path(tmpdir)
    cfg_dir = root / "_bmad" / "skf"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    sidecar_dir = root / "_bmad" / "_memory" / "forger-sidecar"
    if sidecar:
        sidecar_dir.mkdir(parents=True, exist_ok=True)

    if config is None:
        config = {
            "project_name": "test-project",
            "output_folder": str(root / "_bmad-output"),
            "user_name": "TestUser",
            "communication_language": "English",
            "document_output_language": "English",
            "sidecar_path": str(sidecar_dir),
            "skills_output_folder": str(root / "skills"),
            "forge_data_folder": str(root / "forge-data"),
        }

    with open(cfg_dir / "config.yaml", "w") as f:
        yaml.dump(config, f)

    if sidecar and preferences is not None:
        with open(sidecar_dir / "preferences.yaml", "w") as f:
            yaml.dump(preferences, f)

    if sidecar and forge_tier is not None:
        with open(sidecar_dir / "forge-tier.yaml", "w") as f:
            yaml.dump(forge_tier, f)

    return root


class TestPreflightHappyPath:
    """Suite 1: Happy path -- full config + sidecar."""

    def test_status_ok(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_project_name_resolved(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["config"]["project_name"] == "test-project"

    def test_user_name_resolved(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["config"]["user_name"] == "TestUser"

    def test_tier_forge_plus(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier"] == "Forge+"

    def test_compact_greeting(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["compact_greeting"] is True

    def test_not_first_run(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["is_first_run"] is False

    def test_tier_source_detected(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"compact_greeting": True},
            forge_tier={"tier": "Forge+", "tier_detected_at": "2026-04-08"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier_source"] == "detected"


class TestPreflightMissingConfig:
    """Suite 2: Missing config."""

    def test_hard_halt_on_missing_config(self, tmp_path):
        result = run_preflight(str(tmp_path))
        assert result["status"] == "hard-halt"

    def test_code_config_missing(self, tmp_path):
        result = run_preflight(str(tmp_path))
        assert result["code"] == "CONFIG_MISSING"


class TestPreflightMissingSidecar:
    """Suite 3: Missing sidecar directory."""

    def test_hard_halt_on_missing_sidecar(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root))
        assert result["status"] == "hard-halt"

    def test_code_sidecar_missing(self, tmp_path):
        root = make_project(tmp_path, sidecar=False)
        result = run_preflight(str(root))
        assert result["code"] == "SIDECAR_MISSING"


class TestPreflightFirstRun:
    """Suite 4: First run -- no forge-tier."""

    def test_status_ok(self, tmp_path):
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_is_first_run(self, tmp_path):
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["derived"]["is_first_run"] is True

    def test_tier_none(self, tmp_path):
        root = make_project(tmp_path)
        result = run_preflight(str(root))
        assert result["derived"]["tier"] is None


class TestPreflightTierOverride:
    """Suite 5: Tier override."""

    def test_status_ok(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"tier_override": "Deep"},
            forge_tier={"tier": "Quick"},
        )
        result = run_preflight(str(root))
        assert result["status"] == "ok"

    def test_tier_deep_override(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"tier_override": "Deep"},
            forge_tier={"tier": "Quick"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier"] == "Deep"

    def test_tier_source_override(self, tmp_path):
        root = make_project(
            tmp_path,
            preferences={"tier_override": "Deep"},
            forge_tier={"tier": "Quick"},
        )
        result = run_preflight(str(root))
        assert result["derived"]["tier_source"] == "override"


class TestPreflightLiteralSidecarPath:
    """Suite 6: Literal sidecar_path string."""

    def test_hard_halt_on_literal_sidecar_path(self, tmp_path):
        root = make_project(tmp_path, config={
            "project_name": "test",
            "sidecar_path": "{sidecar_path}",
        })
        result = run_preflight(str(root))
        assert result["status"] == "hard-halt"

    def test_code_sidecar_undefined(self, tmp_path):
        root = make_project(tmp_path, config={
            "project_name": "test",
            "sidecar_path": "{sidecar_path}",
        })
        result = run_preflight(str(root))
        assert result["code"] == "SIDECAR_UNDEFINED"
