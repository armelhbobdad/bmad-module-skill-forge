#!/usr/bin/env python3
"""Tests for skf-manifest-ops.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
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
        manifest_path.write_text(json.dumps(v1_data), encoding="utf-8")
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
        manifest_path.write_text(json.dumps(legacy_v2), encoding="utf-8")
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
        manifest_path.write_text(json.dumps(legacy_v2), encoding="utf-8")
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
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        r = mod.cmd_get(manifest_path, "cocoindex")
        entry = r["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["cursor"]
        assert "platforms" not in entry

    def test_set_with_ides_writes_sorted_deduped(self, manifest_path):
        """S15: cmd_set(ides=...) on a new version records the deduped, sorted list."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0", ides=["cursor", "claude-code", "cursor"])
        r = mod.cmd_get(manifest_path, "cocoindex")
        entry = r["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["claude-code", "cursor"]

    def test_set_with_ides_unions_existing(self, manifest_path):
        """S16: cmd_set(ides=...) unions into the version's existing ides; absence preserves."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0", ides=["claude-code"])
        # Re-set same version with a new IDE → union, deduped + sorted
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0", ides=["cursor", "claude-code"])
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["claude-code", "cursor"]
        # Re-set with no --ides → existing list preserved verbatim (backward-compatible)
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["claude-code", "cursor"]

    def test_set_archives_stranded_active_when_active_version_pre_advanced(self, manifest_path):
        """S18: set archives any *other* still-active version, even when active_version
        was advanced to the new version before set ran. Guards the single-active invariant
        against a pre-advanced active_version (the genuine prior version must not stay active)."""
        data = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "2.1.0",  # advanced to the new version before set ran
                    "versions": {
                        "2.0.0": {
                            "ides": ["claude-code"],
                            "last_exported": "2026-05-01",
                            "status": "active",
                        }
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        mod.cmd_set(manifest_path, "cocoindex", "2.1.0")
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]
        versions = entry["versions"]
        assert entry["active_version"] == "2.1.0"
        assert versions["2.1.0"]["status"] == "active"
        assert versions["2.0.0"]["status"] == "archived"
        # Exactly one active version remains.
        assert [v for v, e in versions.items() if e["status"] == "active"] == ["2.1.0"]

    def test_set_does_not_touch_deprecated_versions(self, manifest_path):
        """S19: archiving other actives leaves deprecated versions untouched."""
        data = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "2.0.0",
                    "versions": {
                        "1.0.0": {"ides": [], "last_exported": "2026-01-01", "status": "deprecated"},
                        "2.0.0": {"ides": [], "last_exported": "2026-04-01", "status": "active"},
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        mod.cmd_set(manifest_path, "cocoindex", "2.1.0")
        versions = mod.cmd_get(manifest_path, "cocoindex")["entry"]["versions"]
        assert versions["1.0.0"]["status"] == "deprecated"
        assert versions["2.0.0"]["status"] == "archived"
        assert versions["2.1.0"]["status"] == "active"

    def test_cli_set_parses_ides_flag(self, manifest_path):
        """S17: the `set ... --ides a,b` CLI dispatch path parses and unions the list."""
        script = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-manifest-ops.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(manifest_path.parent),
             "set", "cocoindex", "2.0.0", "--ides", "cursor,claude-code"],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]["versions"]["2.0.0"]
        assert entry["ides"] == ["claude-code", "cursor"]

    def test_set_archives_double_stranded_active_versions(self, manifest_path):
        """S20: two stranded active versions exist; setting a new version archives both."""
        data = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "3.0.0",
                    "versions": {
                        "1.0.0": {"ides": ["cursor"], "last_exported": "2026-01-01", "status": "active"},
                        "2.0.0": {"ides": ["claude-code"], "last_exported": "2026-03-01", "status": "active"},
                        "3.0.0": {"ides": [], "last_exported": "2026-05-01", "status": "archived"},
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        mod.cmd_set(manifest_path, "cocoindex", "4.0.0")
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]
        versions = entry["versions"]
        assert entry["active_version"] == "4.0.0"
        assert versions["1.0.0"]["status"] == "archived"
        assert versions["2.0.0"]["status"] == "archived"
        assert versions["3.0.0"]["status"] == "archived"
        assert versions["4.0.0"]["status"] == "active"
        active = [v for v, e in versions.items() if e["status"] == "active"]
        assert active == ["4.0.0"]

    def test_set_same_version_idempotent(self, manifest_path):
        """S21: setting the same version twice is idempotent — single active, no state change."""
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]
        versions = entry["versions"]
        assert entry["active_version"] == "2.0.0"
        assert versions["2.0.0"]["status"] == "active"
        active = [v for v, e in versions.items() if e["status"] == "active"]
        assert active == ["2.0.0"]

    def test_set_first_version_on_empty_skill(self, manifest_path):
        """S22: set on a skill with zero prior versions creates the first version correctly."""
        manifest_path.write_text(json.dumps({"schema_version": "2", "exports": {}}), encoding="utf-8")
        mod.cmd_set(manifest_path, "newskill", "1.0.0")
        entry = mod.cmd_get(manifest_path, "newskill")["entry"]
        versions = entry["versions"]
        assert entry["active_version"] == "1.0.0"
        assert len(versions) == 1
        assert versions["1.0.0"]["status"] == "active"

    def test_cli_set_stranded_active_version(self, manifest_path):
        """S23: CLI E2E — subprocess set on pre-advanced manifest archives the stranded version."""
        data = {
            "schema_version": "2",
            "exports": {
                "cocoindex": {
                    "active_version": "2.1.0",
                    "versions": {
                        "2.0.0": {"ides": ["claude-code"], "last_exported": "2026-05-01", "status": "active"},
                    },
                }
            },
        }
        manifest_path.write_text(json.dumps(data), encoding="utf-8")
        script = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-manifest-ops.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(manifest_path.parent), "set", "cocoindex", "2.1.0"],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["status"] == "ok"
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]
        assert entry["active_version"] == "2.1.0"
        assert entry["versions"]["2.0.0"]["status"] == "archived"
        assert entry["versions"]["2.1.0"]["status"] == "active"
        active = [v for v, e in entry["versions"].items() if e["status"] == "active"]
        assert active == ["2.1.0"]

    def test_set_multi_skill_isolation(self, manifest_path):
        """S24: archiving actives in one skill does not affect another skill's versions."""
        mod.cmd_set(manifest_path, "alpha", "1.0.0")
        mod.cmd_set(manifest_path, "beta", "1.0.0")
        mod.cmd_set(manifest_path, "alpha", "2.0.0")
        alpha = mod.cmd_get(manifest_path, "alpha")["entry"]
        beta = mod.cmd_get(manifest_path, "beta")["entry"]
        assert alpha["active_version"] == "2.0.0"
        assert alpha["versions"]["1.0.0"]["status"] == "archived"
        assert alpha["versions"]["2.0.0"]["status"] == "active"
        assert beta["active_version"] == "1.0.0"
        assert beta["versions"]["1.0.0"]["status"] == "active"

    def test_set_after_deprecate_all(self, manifest_path):
        """S25: setting a new version after deprecating all versions activates it correctly."""
        mod.cmd_set(manifest_path, "cocoindex", "1.0.0")
        mod.cmd_deprecate(manifest_path, "cocoindex")
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]
        assert entry["active_version"] == "2.0.0"
        assert entry["versions"]["1.0.0"]["status"] == "deprecated"
        assert entry["versions"]["2.0.0"]["status"] == "active"

    def test_set_on_v1_migrated_manifest(self, manifest_path):
        """S26: set on a freshly-migrated v1 manifest archives the old active correctly."""
        v1_data = {
            "exports": {
                "cocoindex": {
                    "active_version": "1.0.0",
                    "versions": ["1.0.0", "0.9.0"],
                    "deprecated": False,
                }
            },
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        manifest_path.write_text(json.dumps(v1_data), encoding="utf-8")
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        entry = mod.cmd_get(manifest_path, "cocoindex")["entry"]
        assert entry["active_version"] == "2.0.0"
        assert entry["versions"]["1.0.0"]["status"] == "archived"
        assert entry["versions"]["0.9.0"]["status"] == "archived"
        assert entry["versions"]["2.0.0"]["status"] == "active"
        active = [v for v, e in entry["versions"].items() if e["status"] == "active"]
        assert active == ["2.0.0"]

    def test_read_manifest_single_active_invariant(self, manifest_path):
        """S27: full manifest read after multiple operations shows single-active per skill."""
        mod.cmd_set(manifest_path, "alpha", "1.0.0")
        mod.cmd_set(manifest_path, "alpha", "2.0.0")
        mod.cmd_set(manifest_path, "beta", "1.0.0")
        mod.cmd_deprecate(manifest_path, "beta", "1.0.0")
        mod.cmd_set(manifest_path, "beta", "2.0.0")
        result = mod.cmd_read(manifest_path)
        assert result["status"] == "ok"
        for skill_name, entry in result["manifest"]["exports"].items():
            active = [v for v, e in entry["versions"].items() if e["status"] == "active"]
            assert len(active) == 1, f"{skill_name} has {len(active)} active versions: {active}"
