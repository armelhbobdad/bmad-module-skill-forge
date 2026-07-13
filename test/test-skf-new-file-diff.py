#!/usr/bin/env python3
"""Tests for skf-new-file-diff.py (skf-update-skill detect-changes Category D).

Covers the NEW_FILE set-difference: inventory source_files minus provenance
file_entries, with [MANUAL] paths set aside and kind carried through.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-update-skill" / "scripts" / "skf-new-file-diff.py"

spec = importlib.util.spec_from_file_location("skf_new_file_diff", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def detect(scripts=None, assets=None):
    return {
        "scripts_inventory": [{"source_file": s} for s in (scripts or [])],
        "assets_inventory": [{"source_file": a} for a in (assets or [])],
    }


# --------------------------------------------------------------------------
# diff()
# --------------------------------------------------------------------------


class TestDiff:
    def test_new_file_detected(self) -> None:
        result = mod.diff(detect(scripts=["scripts/gen.py"]), set())
        assert result["new_files"] == [{"source_file": "scripts/gen.py", "kind": "script"}]
        assert result["stats"]["new"] == 1

    def test_asset_kind_carried(self) -> None:
        result = mod.diff(detect(assets=["assets/logo.svg"]), set())
        assert result["new_files"] == [{"source_file": "assets/logo.svg", "kind": "asset"}]

    def test_already_tracked_excluded(self) -> None:
        result = mod.diff(detect(scripts=["scripts/gen.py"]), {"scripts/gen.py"})
        assert result["new_files"] == []
        assert result["already_tracked"] == ["scripts/gen.py"]
        assert result["stats"]["new"] == 0

    def test_manual_paths_skipped(self) -> None:
        result = mod.diff(
            detect(scripts=["scripts/[MANUAL]/keep.py"], assets=["assets/[MANUAL]/x.bin"]),
            set(),
        )
        assert result["new_files"] == []
        assert result["skipped_manual"] == ["assets/[MANUAL]/x.bin", "scripts/[MANUAL]/keep.py"]
        assert result["stats"]["skipped_manual"] == 2

    def test_manual_only_under_scripts_or_assets(self) -> None:
        # A [MANUAL] segment not under scripts/ or assets/ is not skipped.
        result = mod.diff(detect(scripts=["src/[MANUAL]/thing.py"]), set())
        assert result["new_files"] == [
            {"source_file": "src/[MANUAL]/thing.py", "kind": "script"}
        ]

    def test_dedupe_scripts_wins_over_assets(self) -> None:
        d = {
            "scripts_inventory": [{"source_file": "shared/x"}],
            "assets_inventory": [{"source_file": "shared/x"}],
        }
        result = mod.diff(d, set())
        assert result["new_files"] == [{"source_file": "shared/x", "kind": "script"}]
        assert result["stats"]["inventory_total"] == 1

    def test_sorted_output(self) -> None:
        result = mod.diff(detect(scripts=["scripts/z.py", "scripts/a.py"]), set())
        assert [r["source_file"] for r in result["new_files"]] == [
            "scripts/a.py",
            "scripts/z.py",
        ]

    def test_windows_paths_normalized(self) -> None:
        d = {"scripts_inventory": [{"source_file": "scripts\\gen.py"}], "assets_inventory": []}
        result = mod.diff(d, {"scripts/gen.py"})
        assert result["already_tracked"] == ["scripts/gen.py"]
        assert result["new_files"] == []

    def test_empty_inventory(self) -> None:
        result = mod.diff(detect(), set())
        assert result["new_files"] == []
        assert result["stats"] == {
            "inventory_total": 0,
            "new": 0,
            "skipped_manual": 0,
            "already_tracked": 0,
        }

    def test_mixed(self) -> None:
        d = detect(
            scripts=["scripts/new.py", "scripts/tracked.py", "scripts/[MANUAL]/m.py"],
            assets=["assets/new.png"],
        )
        result = mod.diff(d, {"scripts/tracked.py"})
        assert result["stats"] == {
            "inventory_total": 4,
            "new": 2,
            "skipped_manual": 1,
            "already_tracked": 1,
        }


# --------------------------------------------------------------------------
# load_tracked_source_files()
# --------------------------------------------------------------------------


class TestLoadTracked:
    def test_canonical_object(self, tmp_path: Path) -> None:
        p = tmp_path / "prov.json"
        p.write_text(json.dumps({"file_entries": [{"source_file": "scripts/a.py"}]}))
        assert mod.load_tracked_source_files(p) == {"scripts/a.py"}

    def test_bare_array(self, tmp_path: Path) -> None:
        p = tmp_path / "prov.json"
        p.write_text(json.dumps([{"source_file": "scripts/a.py"}, {"source_file": "b"}]))
        assert mod.load_tracked_source_files(p) == {"scripts/a.py", "b"}

    def test_entry_without_source_file_ignored(self, tmp_path: Path) -> None:
        p = tmp_path / "prov.json"
        p.write_text(json.dumps({"file_entries": [{"export_name": "x"}]}))
        assert mod.load_tracked_source_files(p) == set()


# --------------------------------------------------------------------------
# CLI / exit codes
# --------------------------------------------------------------------------


def run_cli(provenance: str, stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), provenance],
        input=stdin,
        capture_output=True,
        text=True,
    )


class TestCli:
    def test_success(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"file_entries": []}))
        detect_json = json.dumps(detect(scripts=["scripts/new.py"]))
        proc = run_cli(str(prov), detect_json)
        assert proc.returncode == 0
        out = json.loads(proc.stdout)
        assert out["new_files"] == [{"source_file": "scripts/new.py", "kind": "script"}]

    def test_missing_provenance_exit_2(self, tmp_path: Path) -> None:
        proc = run_cli(str(tmp_path / "nope.json"), json.dumps(detect()))
        assert proc.returncode == 2

    def test_invalid_stdin_exit_2(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"file_entries": []}))
        proc = run_cli(str(prov), "not json")
        assert proc.returncode == 2

    def test_empty_stdin_exit_2(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"file_entries": []}))
        proc = run_cli(str(prov), "")
        assert proc.returncode == 2

    def test_provenance_missing_file_entries_exit_2(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(json.dumps({"something_else": []}))
        proc = run_cli(str(prov), json.dumps(detect()))
        assert proc.returncode == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
