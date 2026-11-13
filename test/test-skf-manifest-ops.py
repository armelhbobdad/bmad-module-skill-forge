#!/usr/bin/env python3
"""Tests for skf-manifest-ops.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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


SCRIPT = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-manifest-ops.py"


def _cli(folder: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), str(folder), *args], capture_output=True, timeout=60)
    return proc.returncode, json.loads(proc.stdout.decode("utf-8"))


def _today() -> set[str]:
    """Today's UTC date, and tomorrow's in case the call runs across midnight."""
    now = datetime.now(timezone.utc)
    return {now.strftime("%Y-%m-%d"), (now + timedelta(days=1)).strftime("%Y-%m-%d")}


class TestDropKeepAndOlderVersions:
    """#1160: Drop Skill's keep (`set --keep-last-exported`) and its one deprecate call over several versions."""

    @pytest.fixture
    def seeded(self, manifest_path):
        manifest_path.write_bytes(json.dumps({"schema_version": "2", "exports": {"cognee": {
            "active_version": "0.6.0", "versions": {
                "0.6.0": {"ides": ["claude-code"], "last_exported": "2026-02-01", "status": "active"},
                "0.5.0": {"ides": ["cursor"], "last_exported": "2025-03-04", "status": "archived"},
                "0.4.0": {"ides": [], "status": "archived"},
                "0.1.0": {"ides": [], "last_exported": "2024-01-01", "status": "deprecated"}}}}}).encode("utf-8"))
        return manifest_path

    def _versions(self, manifest_path) -> dict:
        return mod.cmd_get(manifest_path, "cognee")["entry"]["versions"]

    def test_set_keep_last_exported_keeps_the_date(self, seeded):
        r = mod.cmd_set(seeded, "cognee", "0.5.0", keep_last_exported=True)
        assert r["status"] == "ok"
        assert mod.cmd_get(seeded, "cognee")["entry"]["active_version"] == "0.5.0"
        versions = self._versions(seeded)
        assert versions["0.5.0"] == {"ides": ["cursor"], "last_exported": "2025-03-04", "status": "active"}
        assert (versions["0.6.0"]["status"], versions["0.6.0"]["last_exported"]) == ("archived", "2026-02-01")
        assert versions["0.1.0"]["status"] == "deprecated"

    def test_set_keep_last_exported_stamps_today_on_a_version_with_no_date(self, seeded):
        mod.cmd_set(seeded, "cognee", "0.4.0", keep_last_exported=True)
        assert self._versions(seeded)["0.4.0"]["last_exported"] in _today()

    def test_set_without_the_flag_still_stamps_today(self, seeded):
        mod.cmd_set(seeded, "cognee", "0.5.0")
        assert self._versions(seeded)["0.5.0"]["last_exported"] in _today()

    def test_cli_set_keep_last_exported(self, seeded):
        code, out = _cli(seeded.parent, "set", "cognee", "0.5.0", "--keep-last-exported")
        assert (code, out["status"]) == (0, "ok")
        assert self._versions(seeded)["0.5.0"]["last_exported"] == "2025-03-04"
        code, _ = _cli(seeded.parent, "set", "cognee", "0.5.0", "--ides", "claude-code", "--keep-last-exported")
        assert code == 0
        assert self._versions(seeded)["0.5.0"] == {"ides": ["claude-code", "cursor"], "last_exported": "2025-03-04",
                                                   "status": "active"}

    def test_deprecate_several_versions_in_one_call(self, seeded):
        r = mod.cmd_deprecate(seeded, "cognee", ["0.5.0", "0.4.0"])
        assert (r["status"], r["versions"]) == ("ok", ["0.5.0", "0.4.0"])
        assert {v: e["status"] for v, e in self._versions(seeded).items()} == {
            "0.6.0": "active", "0.5.0": "deprecated", "0.4.0": "deprecated", "0.1.0": "deprecated"}
        assert mod.cmd_get(seeded, "cognee")["entry"]["active_version"] == "0.6.0"

    def test_cli_deprecate_several_versions(self, seeded):
        code, out = _cli(seeded.parent, "deprecate", "cognee", "0.5.0", "0.4.0")
        assert (code, out["versions"]) == (0, ["0.5.0", "0.4.0"])
        assert {v: e["status"] for v, e in self._versions(seeded).items()} == {
            "0.6.0": "active", "0.5.0": "deprecated", "0.4.0": "deprecated", "0.1.0": "deprecated"}
        code, out = _cli(seeded.parent, "deprecate", "cognee", "0.6.0")
        assert (code, out["version"], out["versions"]) == (0, "0.6.0", ["0.6.0"]), "one version reads as before"

    def test_an_unknown_version_fails_before_any_is_marked(self, seeded):
        before = seeded.read_bytes()
        r = mod.cmd_deprecate(seeded, "cognee", ["0.5.0", "9.9.9", "8.8.8"])
        assert r == {"status": "error", "error": "Versions '9.9.9', '8.8.8' not found for 'cognee'"}
        assert seeded.read_bytes() == before, "nothing is written"
        code, out = _cli(seeded.parent, "deprecate", "cognee", "0.4.0", "9.9.9")
        assert (code, out["error"]) == (1, "Version '9.9.9' not found for 'cognee'")
        assert seeded.read_bytes() == before


class TestVersionSortKey:
    """Semver-descending ordering used by affected-versions."""

    def test_numeric_not_lexical(self):
        vs = ["0.9.0", "0.10.0", "0.1.0"]
        ordered = sorted(vs, key=mod._version_sort_key, reverse=True)
        assert ordered == ["0.10.0", "0.9.0", "0.1.0"]

    def test_release_outranks_prerelease(self):
        vs = ["1.0.0-rc1", "1.0.0"]
        ordered = sorted(vs, key=mod._version_sort_key, reverse=True)
        assert ordered == ["1.0.0", "1.0.0-rc1"]


class TestAffectedVersions:
    """Union of manifest version keys + on-disk version dirs, deduped + sorted."""

    def test_union_manifest_and_on_disk(self, tmp_path):
        manifest_path = tmp_path / ".export-manifest.json"
        # Manifest knows 2.0.0 and 2.1.0 for cocoindex.
        mod.cmd_set(manifest_path, "cocoindex", "2.0.0")
        mod.cmd_set(manifest_path, "cocoindex", "2.1.0")
        # On disk there is an extra orphaned version dir + the active symlink.
        skill_dir = tmp_path / "cocoindex"
        (skill_dir / "2.1.0").mkdir(parents=True)
        (skill_dir / "0.10.0").mkdir(parents=True)  # orphan, not in manifest
        (skill_dir / "0.9.0").mkdir(parents=True)
        try:
            (skill_dir / "active").symlink_to("2.1.0")
        except OSError:
            pass  # symlink unsupported; test still valid without it

        r = mod.cmd_affected_versions(manifest_path, tmp_path, "cocoindex")
        assert r["status"] == "ok"
        # Deduped union, semver-descending, `active` excluded.
        assert r["affected_versions"] == ["2.1.0", "2.0.0", "0.10.0", "0.9.0"]
        assert r["count"] == 4
        assert "active" not in r["affected_versions"]
        assert set(r["sources"]["manifest"]) == {"2.0.0", "2.1.0"}
        assert set(r["sources"]["on_disk"]) == {"2.1.0", "0.10.0", "0.9.0"}

    def test_on_disk_only_no_manifest_entry(self, tmp_path):
        manifest_path = tmp_path / ".export-manifest.json"
        skill_dir = tmp_path / "legacy-helper"
        (skill_dir / "1.0.0").mkdir(parents=True)
        r = mod.cmd_affected_versions(manifest_path, tmp_path, "legacy-helper")
        assert r["status"] == "ok"
        assert r["affected_versions"] == ["1.0.0"]

    def test_empty_when_nothing_found(self, tmp_path):
        manifest_path = tmp_path / ".export-manifest.json"
        r = mod.cmd_affected_versions(manifest_path, tmp_path, "ghost")
        assert r["status"] == "ok"
        assert r["affected_versions"] == []
        assert r["count"] == 0

    def test_cli_affected_versions(self, tmp_path):
        skill_dir = tmp_path / "cocoindex"
        (skill_dir / "2.0.0").mkdir(parents=True)
        (skill_dir / "2.1.0").mkdir(parents=True)
        script = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-manifest-ops.py"
        proc = subprocess.run(
            [sys.executable, str(script), str(tmp_path), "affected-versions", "cocoindex"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["affected_versions"] == ["2.1.0", "2.0.0"]
