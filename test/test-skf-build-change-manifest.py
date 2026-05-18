#!/usr/bin/env python3
"""Tests for skf-build-change-manifest.py.

Covers two subcommands:
  - build: aggregate category A/B/C/D into unified manifest
  - deletion-ratio: §2.2 trigger computation
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-build-change-manifest.py"

spec = importlib.util.spec_from_file_location("skf_build_change_manifest", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


# --------------------------------------------------------------------------
# build_manifest
# --------------------------------------------------------------------------


class TestBuildManifestCounts:
    def test_empty_payload_no_changes(self) -> None:
        result = mod.build_manifest({})
        assert result["no_changes"] is True
        assert result["counts"]["files_changed"] == 0
        assert result["per_file"] == []

    def test_category_a_counts(self) -> None:
        result = mod.build_manifest({
            "category_a": {
                "modified": ["src/a.py", "src/b.py"],
                "added": ["src/c.py"],
                "deleted": ["src/d.py", "src/e.py", "src/f.py"],
            }
        })
        assert result["counts"]["files_changed"] == 2
        assert result["counts"]["files_added"] == 1
        assert result["counts"]["files_deleted"] == 3
        assert result["no_changes"] is False

    def test_category_b_counts(self) -> None:
        result = mod.build_manifest({
            "category_b": {
                "modified_exports": [
                    {"name": "f1", "file": "src/a.py", "old_line": 10, "new_line": 12},
                    {"name": "f2", "file": "src/a.py", "old_line": 20, "new_line": 22},
                ],
                "new_exports": [{"name": "f3", "file": "src/a.py", "line": 30}],
                "deleted_exports": [],
                "moved_exports": [
                    {"name": "f4", "file": "src/a.py", "old_line": 40, "new_line": 50}
                ],
            }
        })
        assert result["counts"]["exports_modified"] == 2
        assert result["counts"]["exports_new"] == 1
        assert result["counts"]["exports_deleted"] == 0
        assert result["counts"]["exports_moved"] == 1
        assert result["total_export_changes"] == 4

    def test_category_c_counts(self) -> None:
        result = mod.build_manifest({
            "category_c": {
                "renamed_files": [
                    {"old_path": "src/old.py", "new_path": "src/new.py"}
                ],
                "renamed_exports": [
                    {"old_name": "foo", "new_name": "bar", "file": "src/a.py"},
                    {"old_name": "baz", "new_name": "qux", "file": "src/a.py"},
                ],
            }
        })
        assert result["counts"]["files_moved"] == 1
        assert result["counts"]["exports_renamed"] == 2

    def test_category_d_counts(self) -> None:
        result = mod.build_manifest({
            "category_d": {
                "scripts_modified": ["scripts/x.sh"],
                "scripts_added": ["scripts/y.sh", "scripts/z.sh"],
                "scripts_deleted": [],
                "assets_modified": ["assets/a.yaml"],
                "assets_added": [],
                "assets_deleted": ["assets/d.yaml"],
            }
        })
        assert result["counts"]["scripts_modified"] == 1
        assert result["counts"]["scripts_added"] == 2
        assert result["counts"]["scripts_deleted"] == 0
        assert result["counts"]["assets_modified"] == 1
        assert result["counts"]["assets_deleted"] == 1


class TestBuildManifestPerFile:
    def test_modified_file_with_exports(self) -> None:
        result = mod.build_manifest({
            "category_a": {"modified": ["src/a.py"]},
            "category_b": {
                "modified_exports": [
                    {"name": "f1", "file": "src/a.py", "old_line": 10, "new_line": 12}
                ],
                "new_exports": [
                    {"name": "f2", "file": "src/a.py", "line": 30}
                ],
            },
        })
        per_file = result["per_file"]
        assert len(per_file) == 1
        assert per_file[0]["file_path"] == "src/a.py"
        assert per_file[0]["status"] == "MODIFIED"
        exports = per_file[0]["exports_affected"]
        assert {e["name"] for e in exports} == {"f1", "f2"}
        names_to_types = {e["name"]: e["change_type"] for e in exports}
        assert names_to_types["f1"] == "MODIFIED_EXPORT"
        assert names_to_types["f2"] == "NEW_EXPORT"

    def test_per_file_ordering_modified_added_deleted_moved(self) -> None:
        result = mod.build_manifest({
            "category_a": {
                "modified": ["src/zz_mod.py"],
                "added": ["src/aa_add.py"],
                "deleted": ["src/mm_del.py"],
            },
            "category_c": {
                "renamed_files": [{"old_path": "src/old.py", "new_path": "src/bb_moved.py"}]
            },
        })
        statuses = [pf["status"] for pf in result["per_file"]]
        assert statuses == ["MODIFIED", "ADDED", "DELETED", "MOVED"]

    def test_per_file_alpha_sort_within_status(self) -> None:
        result = mod.build_manifest({
            "category_a": {"modified": ["src/zzz.py", "src/aaa.py", "src/mmm.py"]}
        })
        paths = [pf["file_path"] for pf in result["per_file"]]
        assert paths == ["src/aaa.py", "src/mmm.py", "src/zzz.py"]

    def test_moved_record_preserves_old_path(self) -> None:
        result = mod.build_manifest({
            "category_c": {
                "renamed_files": [{"old_path": "src/old.py", "new_path": "src/new.py"}]
            }
        })
        moved = [pf for pf in result["per_file"] if pf["status"] == "MOVED"]
        assert moved[0]["old_path"] == "src/old.py"
        assert moved[0]["file_path"] == "src/new.py"

    def test_export_without_file_dropped(self) -> None:
        # malformed export entry without `file` — silently dropped to avoid
        # crashing on partial subprocess output
        result = mod.build_manifest({
            "category_a": {"modified": ["src/a.py"]},
            "category_b": {
                "modified_exports": [
                    {"name": "f1", "file": "src/a.py", "old_line": 10},
                    {"name": "orphan"},  # no file
                ]
            },
        })
        exports = result["per_file"][0]["exports_affected"]
        assert len(exports) == 1
        assert exports[0]["name"] == "f1"


class TestBuildManifestEdgeCases:
    def test_degraded_mode_flag_propagated(self) -> None:
        result = mod.build_manifest({
            "degraded_mode": True,
            "category_a": {"modified": ["src/a.py"]},
        })
        assert result["degraded_mode"] is True

    def test_missing_category_keys_default_empty(self) -> None:
        result = mod.build_manifest({"category_a": {"modified": ["x.py"]}})
        assert result["counts"]["exports_modified"] == 0
        assert result["counts"]["files_added"] == 0


# --------------------------------------------------------------------------
# compute_deletion_ratio (§2.2)
# --------------------------------------------------------------------------


def _provenance_with(entries: list[dict]) -> dict:
    return {"entries": entries}


class TestDeletionRatioSkips:
    def test_skip_gap_driven(self) -> None:
        result = mod.compute_deletion_ratio(
            {"update_mode": "gap-driven", "category_a": {"deleted": ["a.py"]}},
            _provenance_with([{"name": "f", "source_file": "a.py"}]),
        )
        assert result["skip_reason"] == "gap-driven"
        assert result["should_trigger"] is False

    def test_skip_degraded_mode(self) -> None:
        result = mod.compute_deletion_ratio(
            {"degraded_mode": True, "category_a": {"deleted": ["a.py"]}},
            _provenance_with([{"name": "f", "source_file": "a.py"}]),
        )
        assert result["skip_reason"] == "degraded-mode"

    def test_skip_zero_provenance_entries(self) -> None:
        result = mod.compute_deletion_ratio({}, _provenance_with([]))
        assert result["skip_reason"] == "zero-provenance-exports"

    def test_provenance_must_have_entries_array(self) -> None:
        with pytest.raises(ValueError, match="entries"):
            mod.compute_deletion_ratio({}, {"entries": "not-a-list"})


class TestDeletionRatioComputation:
    def test_under_threshold_no_trigger(self) -> None:
        # 1 deleted export out of 10 = 0.10 → no trigger
        provenance = _provenance_with([
            {"name": f"f{i}", "source_file": f"file{i}.py"} for i in range(10)
        ])
        result = mod.compute_deletion_ratio(
            {"category_b": {"deleted_exports": [{"name": "f0", "file": "file0.py"}]}},
            provenance,
        )
        assert result["deleted_export_count"] == 1
        assert result["total_provenance_exports"] == 10
        assert result["deletion_ratio"] == pytest.approx(0.1)
        assert result["should_trigger"] is False

    def test_over_threshold_triggers(self) -> None:
        # 6 deleted exports out of 10 = 0.60 → triggers
        provenance = _provenance_with([
            {"name": f"f{i}", "source_file": f"file{i}.py"} for i in range(10)
        ])
        deleted = [{"name": f"f{i}", "file": f"file{i}.py"} for i in range(6)]
        result = mod.compute_deletion_ratio(
            {"category_b": {"deleted_exports": deleted}},
            provenance,
        )
        assert result["deletion_ratio"] == pytest.approx(0.6)
        assert result["should_trigger"] is True

    def test_at_exactly_threshold_triggers(self) -> None:
        # 5 of 10 = 0.50, threshold is >= 0.50
        provenance = _provenance_with([
            {"name": f"f{i}", "source_file": f"file{i}.py"} for i in range(10)
        ])
        deleted = [{"name": f"f{i}", "file": f"file{i}.py"} for i in range(5)]
        result = mod.compute_deletion_ratio(
            {"category_b": {"deleted_exports": deleted}},
            provenance,
        )
        assert result["should_trigger"] is True

    def test_deleted_files_contribute_their_exports(self) -> None:
        # Category A deleted file contains 3 provenance exports → they count
        # toward deleted_export_count
        provenance = _provenance_with([
            {"name": "a", "source_file": "doomed.py"},
            {"name": "b", "source_file": "doomed.py"},
            {"name": "c", "source_file": "doomed.py"},
            {"name": "d", "source_file": "kept.py"},
        ])
        result = mod.compute_deletion_ratio(
            {"category_a": {"deleted": ["doomed.py"]}},
            provenance,
        )
        assert result["deleted_export_count"] == 3
        assert result["deletion_ratio"] == pytest.approx(0.75)
        assert result["should_trigger"] is True

    def test_combines_categories_a_and_b(self) -> None:
        provenance = _provenance_with([
            {"name": "x", "source_file": "doomed.py"},
            {"name": "y", "source_file": "doomed.py"},
            {"name": "p", "source_file": "alive.py"},
            {"name": "q", "source_file": "alive.py"},
        ])
        result = mod.compute_deletion_ratio(
            {
                "category_a": {"deleted": ["doomed.py"]},  # 2 exports
                "category_b": {"deleted_exports": [  # 1 export from a non-deleted file
                    {"name": "p", "file": "alive.py"}
                ]},
            },
            provenance,
        )
        assert result["deleted_export_count"] == 3

    def test_renamed_or_moved_count(self) -> None:
        result = mod.compute_deletion_ratio(
            {
                "category_b": {"moved_exports": [{"name": "a", "file": "x.py"}]},
                "category_c": {
                    "renamed_files": [{"old_path": "o.py", "new_path": "n.py"}],
                    "renamed_exports": [{"old_name": "a", "new_name": "b", "file": "x.py"}],
                },
            },
            _provenance_with([{"name": "f", "source_file": "x.py"}]),
        )
        # 1 moved + 1 renamed file + 1 renamed export
        assert result["renamed_or_moved_count"] == 3


# --------------------------------------------------------------------------
# CLI integration
# --------------------------------------------------------------------------


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


class TestCli:
    def test_build_via_stdin(self) -> None:
        payload = json.dumps({"category_a": {"modified": ["src/a.py"]}})
        result = _run_cli("build", stdin=payload)
        assert result.returncode == 0, result.stderr
        manifest = json.loads(result.stdout)
        assert manifest["counts"]["files_changed"] == 1

    def test_build_via_input_file(self, tmp_path: Path) -> None:
        payload_path = tmp_path / "in.json"
        payload_path.write_text(
            json.dumps({"category_a": {"modified": ["src/a.py"]}}),
            encoding="utf-8",
        )
        result = _run_cli("build", "--input", str(payload_path))
        assert result.returncode == 0
        manifest = json.loads(result.stdout)
        assert manifest["no_changes"] is False

    def test_build_malformed_json_exits_1(self) -> None:
        result = _run_cli("build", stdin="not json")
        assert result.returncode == 1
        assert "not valid JSON" in result.stderr

    def test_build_non_object_exits_1(self) -> None:
        result = _run_cli("build", stdin="[1, 2, 3]")
        assert result.returncode == 1
        assert "must be a JSON object" in result.stderr

    def test_deletion_ratio_cli(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text(
            json.dumps({"entries": [
                {"name": f"f{i}", "source_file": f"f{i}.py"} for i in range(4)
            ]}),
            encoding="utf-8",
        )
        payload = json.dumps({
            "category_b": {"deleted_exports": [
                {"name": "f0", "file": "f0.py"},
                {"name": "f1", "file": "f1.py"},
                {"name": "f2", "file": "f2.py"},
            ]}
        })
        result = _run_cli(
            "deletion-ratio", "--provenance-map", str(prov), stdin=payload
        )
        assert result.returncode == 0
        out = json.loads(result.stdout)
        assert out["deletion_ratio"] == pytest.approx(0.75)
        assert out["should_trigger"] is True

    def test_deletion_ratio_missing_provenance_exits_1(self, tmp_path: Path) -> None:
        result = _run_cli(
            "deletion-ratio",
            "--provenance-map", str(tmp_path / "missing.json"),
            stdin="{}",
        )
        assert result.returncode == 1
        assert "provenance-map not found" in result.stderr

    def test_deletion_ratio_malformed_provenance_exits_1(self, tmp_path: Path) -> None:
        prov = tmp_path / "prov.json"
        prov.write_text("{not json", encoding="utf-8")
        result = _run_cli(
            "deletion-ratio", "--provenance-map", str(prov), stdin="{}"
        )
        assert result.returncode == 1
        assert "not valid JSON" in result.stderr

    def test_no_subcommand_exits_2(self) -> None:
        result = _run_cli()
        assert result.returncode == 2  # argparse missing required subparser
