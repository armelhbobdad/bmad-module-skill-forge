#!/usr/bin/env python3
"""Tests for skf-manifest-ops.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_manifest_ops",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-manifest-ops.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def manifest_path(tmp_path):
    """Provide a manifest path inside a temporary directory."""
    return tmp_path / ".export-manifest.json"


class TestManifestOps:
    """Manifest operations tests (sequential within each test method)."""

    def test_read_empty_manifest(self, manifest_path):
        """S1: Read empty (no file)."""
        r = mod.cmd_read(manifest_path)
        assert r["status"] == "ok"
        assert r["manifest"]["exports"] == {}

    def test_set_and_get_skill(self, manifest_path):
        """S2: Set a skill and verify v2 persistence."""
        r = mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        assert r["status"] == "ok"
        assert r["version"] == "2.0.0"
        # Verify written in v2 format
        r = mod.cmd_get(manifest_path, "cocoindex")
        assert r["entry"]["active_version"] == "2.0.0"
        assert isinstance(r["entry"]["versions"], dict)
        assert "2.0.0" in r["entry"]["versions"]
        assert r["entry"]["versions"]["2.0.0"]["status"] == "active"

    def test_update_version(self, manifest_path):
        """S3: Update version archives old, activates new."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        mod.cmd_set(manifest_path, "cocoindex", "2.1.0")
        r = mod.cmd_get(manifest_path, "cocoindex")
        assert r["entry"]["active_version"] == "2.1.0"
        assert "2.0.0" in r["entry"]["versions"]
        assert "2.1.0" in r["entry"]["versions"]
        assert r["entry"]["versions"]["2.0.0"]["status"] == "archived"
        assert r["entry"]["versions"]["2.1.0"]["status"] == "active"

    def test_get_nonexistent(self, manifest_path):
        """S4: Get nonexistent."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        r = mod.cmd_get(manifest_path, "react")
        assert r["status"] == "not_found"
        assert "cocoindex" in r["available"]

    def test_deprecate_skill(self, manifest_path):
        """S5: Deprecate all versions via v2 status field."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        r = mod.cmd_deprecate(manifest_path, "cocoindex")
        assert r["status"] == "ok"
        r = mod.cmd_get(manifest_path, "cocoindex")
        assert r["entry"]["versions"]["2.0.0"]["status"] == "deprecated"

    def test_deprecate_specific_version(self, manifest_path):
        """S6: Deprecate specific version via v2 status field."""
        mod.cmd_set(manifest_path, "react", "18.0.0")
        r = mod.cmd_deprecate(manifest_path, "react", "18.0.0")
        assert r["status"] == "ok"
        r = mod.cmd_get(manifest_path, "react")
        assert r["entry"]["versions"]["18.0.0"]["status"] == "deprecated"

    def test_rename_skill(self, manifest_path):
        """S7: Rename."""
        mod.cmd_set(manifest_path, "react", "18.0.0")
        r = mod.cmd_rename(manifest_path, "react", "react-dom")
        assert r["status"] == "ok"
        r = mod.cmd_get(manifest_path, "react-dom")
        assert r["status"] == "ok"
        r = mod.cmd_get(manifest_path, "react")
        assert r["status"] == "not_found"

    def test_rename_collision(self, manifest_path):
        """S8: Rename collision."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        mod.cmd_set(manifest_path, "react-dom", "18.0.0")
        r = mod.cmd_rename(manifest_path, "cocoindex", "react-dom")
        assert r["status"] == "error"
        assert "already exists" in r["error"]

    def test_remove_skill(self, manifest_path):
        """S9: Remove."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        r = mod.cmd_remove(manifest_path, "cocoindex")
        assert r["status"] == "ok"
        r = mod.cmd_get(manifest_path, "cocoindex")
        assert r["status"] == "not_found"

    def test_schema_version_written(self, manifest_path):
        """S10: Manifest includes schema_version 2."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        r = mod.cmd_read(manifest_path)
        assert r["manifest"]["schema_version"] == "2"

    def test_v1_migration(self, manifest_path):
        """S11: V1 manifest is migrated to v2 on read."""
        v1_data = {
            "exports": {
                "cocoindex": {
                    "active_version": "1.0.0",
                    "versions": ["1.0.0"],
                    "deprecated": False,
                }
            },
            "updated_at": "2026-04-01T00:00:00+00:00",
        }
        manifest_path.write_text(json.dumps(v1_data))
        r = mod.cmd_get(manifest_path, "cocoindex")
        assert r["status"] == "ok"
        assert isinstance(r["entry"]["versions"], dict)
        assert "1.0.0" in r["entry"]["versions"]
        assert r["entry"]["versions"]["1.0.0"]["status"] == "active"
        assert "ides" in r["entry"]["versions"]["1.0.0"]
        assert "platforms" not in r["entry"]["versions"]["1.0.0"]

    def test_platforms_to_ides_normalization(self, manifest_path):
        """S12: Legacy `platforms` field is renamed to `ides` on read (issue #148)."""
        legacy_v2 = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "2.0.0",
                    "versions": {
                        "2.0.0": {
                            "platforms": ["claude-code", "cursor"],
                            "last_exported": "2026-04-01",
                            "status": "active",
                        }
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(legacy_v2))
        r = mod.cmd_get(manifest_path, "cocoindex")
        assert r["status"] == "ok"
        entry = r["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["claude-code", "cursor"]
        assert "platforms" not in entry

    def test_platforms_to_ides_preserved_on_set(self, manifest_path):
        """S13: cmd_set preserves legacy `platforms` as `ides` when touching a version."""
        legacy_v2 = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "2.0.0",
                    "versions": {
                        "2.0.0": {
                            "platforms": ["claude-code"],
                            "last_exported": "2026-04-01",
                            "status": "active",
                        }
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(legacy_v2))
        # Re-set the same version — should keep the IDE list, rewritten under `ides`
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        r = mod.cmd_get(manifest_path, "cocoindex")
        entry = r["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["claude-code"]
        assert "platforms" not in entry

    def test_ides_and_platforms_both_present_prefers_ides(self, manifest_path):
        """S14: When both keys exist (shouldn't happen, but be safe), `ides` wins."""
        data = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "2.0.0",
                    "versions": {
                        "2.0.0": {
                            "ides": ["cursor"],
                            "platforms": ["claude-code"],
                            "last_exported": "2026-04-01",
                            "status": "active",
                        }
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(data))
        r = mod.cmd_get(manifest_path, "cocoindex")
        entry = r["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["cursor"]
        assert "platforms" not in entry
