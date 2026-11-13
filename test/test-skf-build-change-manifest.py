#!/usr/bin/env python3
"""Tests for skf-build-change-manifest.py.

Covers its subcommands:
  - gap-records: a gap-driven repair's drift gate, spot-checks, routing to
    targeted re-extraction, record match and copy, reachability answers and
    records, and its CLI
  - build: aggregate category A/B/C/D into unified manifest, Category D
    typed from the compare and new-file helpers' files (a document-only
    change included)
  - deletion-ratio: §2.2 trigger computation
  - rename-candidates, apply and metadata: Category C by rule, the
    provenance map an update writes and the metadata.json it leaves; a new
    entry's source_library in a map naming several libraries (#808) and
    the signature_source an older map's entries lack (#802)
  - records: step 3's re-extraction records, seeded from the runner's and
    step 2's files, with the workers' patches merged in
  - a public-api skill's public surface: records marks each export by the
    runner's entry-point diff and apply adds only the public ones, listing
    the rest (#685); a moved export takes the runner's labels, and a move
    across files its new file (#686), on cognee's shape through the runner;
    the rule is skf-extraction-inventory.py's, and create-skill's map keeps
    the names update keeps on that shape (#699)
  - baseline-gaps: the map entries of the modified files the runner left
    out that their file still declares (#687), read by step 2 so the diff
    reports no false DELETED_EXPORT, and a verifier that cannot load an
    error
and the helper files build and deletion-ratio take in place of typed
slices: the classify output (Category A and its same-content moves), the
structural diff mapped onto Category B, and Category C's renames taken out
of both.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import shutil
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
# Category D from the compare and new-file helpers' files (step 5b determinism-2)
# --------------------------------------------------------------------------


def _d_map() -> dict:
    return {"entries": [], "file_entries": [
        {"file_name": "scripts/run.sh", "file_type": "script", "source_file": "tools/run.sh", "content_hash": "sha256:a"},
        {"file_name": "assets/schema.json", "file_type": "asset", "source_file": "data/schema.json",
         "content_hash": "sha256:b"},
        {"file_name": "docs/authoritative/AGENTS.md", "file_type": "doc", "source_file": "AGENTS.md",
         "content_hash": "sha256:c"},
        {"file_name": "docs/authoritative/llms.txt", "source_file": "llms.txt", "content_hash": "sha256:d"},
        {"file_name": "assets/old.yaml", "file_type": "asset", "source_file": "data/old.yaml",
         "content_hash": "sha256:e"}]}


def _compare(*rows: tuple) -> dict:
    return {"comparisons": [{"source_file": path, "classification": kind, "stored_hash": "sha256:x",
                             "current_hash": None if kind == "DELETED_FILE" else "sha256:y"} for path, kind in rows]}


class TestCategoryDFromFiles:
    def test_each_row_takes_its_file_type(self) -> None:
        lists = mod.category_d_from_files(
            _compare(("tools/run.sh", "MODIFIED_FILE"), ("./data/schema.json", "UNCHANGED"),
                     ("AGENTS.md", "MODIFIED_FILE"), ("llms.txt", "DELETED_FILE"), ("data/old.yaml", "DELETED_FILE")),
            {"new_files": [{"source_file": "tools/new.py", "kind": "script"},
                           {"source_file": "data/new.json", "kind": "asset"}]},
            _d_map())
        assert lists == {"scripts_modified": ["tools/run.sh"], "scripts_added": ["tools/new.py"],
                         "scripts_deleted": [], "assets_modified": [], "assets_added": ["data/new.json"],
                         "assets_deleted": ["data/old.yaml"], "docs_modified": ["AGENTS.md"],
                         # a row with no file_type takes the type its file_name's folder names
                         "docs_deleted": ["llms.txt"]}

    def test_a_document_only_change_is_a_change(self, tmp_path: Path) -> None:
        """The only change is an authoritative document the skill tracks: the run goes on and records its hash."""
        (tmp_path / "provenance-map.json").write_bytes(json.dumps(_d_map()).encode("utf-8"))
        (tmp_path / "category-d-compare.json").write_bytes(
            json.dumps(_compare(("AGENTS.md", "MODIFIED_FILE"), ("tools/run.sh", "UNCHANGED"))).encode("utf-8"))
        (tmp_path / "new-files.json").write_bytes(json.dumps({"new_files": []}).encode("utf-8"))
        (tmp_path / "categories.json").write_bytes(
            json.dumps({"degraded_mode": False, "update_mode": "normal"}).encode("utf-8"))
        result = _run_cli("build", "--input", str(tmp_path / "categories.json"),
                          "--file-compare", str(tmp_path / "category-d-compare.json"),
                          "--new-files", str(tmp_path / "new-files.json"),
                          "--provenance-map", str(tmp_path / "provenance-map.json"))
        assert result.returncode == 0, result.stderr
        manifest = json.loads(result.stdout)
        assert manifest["no_changes"] is False
        assert (manifest["counts"]["docs_modified"], manifest["counts"]["docs_deleted"]) == (1, 0)
        assert manifest["category_d"]["docs_modified"] == ["AGENTS.md"]
        assert manifest["total_export_changes"] == 0 and manifest["per_file"] == []
        # with nothing changed, the same call reports no change
        (tmp_path / "category-d-compare.json").write_bytes(json.dumps(_compare(("AGENTS.md", "UNCHANGED"))).encode())
        result = _run_cli("build", "--input", str(tmp_path / "categories.json"),
                          "--file-compare", str(tmp_path / "category-d-compare.json"),
                          "--new-files", str(tmp_path / "new-files.json"),
                          "--provenance-map", str(tmp_path / "provenance-map.json"))
        assert json.loads(result.stdout)["no_changes"] is True

    def test_the_files_replace_the_inputs_own_category_d(self, tmp_path: Path) -> None:
        (tmp_path / "new-files.json").write_bytes(
            json.dumps({"new_files": [{"source_file": "tools/x.sh", "kind": "script"}]}).encode("utf-8"))
        result = _run_cli("build", "--new-files", str(tmp_path / "new-files.json"),
                          stdin=json.dumps({"category_d": {"assets_deleted": ["typed/by/hand.yaml"]}}))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["category_d"]["assets_deleted"] == []
        assert json.loads(result.stdout)["counts"]["scripts_added"] == 1

    @pytest.mark.parametrize("args, message", [
        (("--file-compare", "compare.json"), "--file-compare needs --provenance-map"),
        (("--provenance-map", "map.json"), "--provenance-map goes with --file-compare"),
    ], ids=["compare-without-map", "map-without-compare"])
    def test_the_compare_and_the_map_go_together(self, tmp_path: Path, args: tuple, message: str) -> None:
        for name in ("compare.json", "map.json"):
            (tmp_path / name).write_bytes(b'{"comparisons": [], "file_entries": []}')
        argv = [a if not a.endswith(".json") else str(tmp_path / a) for a in args]
        result = _run_cli("build", *argv, stdin="{}")
        assert result.returncode == 1 and message in result.stderr

    def test_doc_hashes_refuses_the_category_d_files(self, tmp_path: Path) -> None:
        (tmp_path / "doc-hashes.json").write_bytes(b'{"changed": []}')
        (tmp_path / "new-files.json").write_bytes(b'{"new_files": []}')
        result = _run_cli("build", "--doc-hashes", str(tmp_path / "doc-hashes.json"),
                          "--new-files", str(tmp_path / "new-files.json"))
        assert result.returncode == 1 and "--doc-hashes takes no other input" in result.stderr


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


# --------------------------------------------------------------------------
# Helper files: classify output, structural diff, Category C renames
# --------------------------------------------------------------------------

DIFF = {
    "removed": [{"name": "old_fn", "file": "pkg/api.py", "line": 10}, {"name": "gone", "file": "pkg/api.py",
                                                                      "line": 30}],
    "added": [{"name": "new_fn", "file": "pkg/api.py", "line": 12}, {"name": "fresh", "file": "pkg/api.py",
                                                                    "line": 40}],
    "changed": [
        {"name": "search", "field": "line", "baseline_value": 5, "current_value": 7, "file": "pkg/api.py",
         "line": 7},
        {"name": "search", "field": "params", "baseline_value": ["q"], "current_value": ["q", "limit: int"],
         "file": "pkg/api.py", "line": 7},
        {"name": "shifted", "field": "line", "baseline_value": 20, "current_value": 22, "file": "pkg/api.py",
         "line": 22},
        {"name": "retyped", "field": "type", "baseline_value": "class", "current_value": "function",
         "file": "pkg/api.py", "line": 50},
    ],
    "moved": [{"name": "relocated", "previous_file": "pkg/a.py", "current_file": "pkg/b.py", "previous_line": 1,
               "line": 3}],
    "signature_unverified": [{"name": "opaque", "file": "pkg/api.py", "baseline": ["params"],
                              "current": ["signature"]}],
    "label_changes": [{"name": "search", "file": "pkg/api.py"}],
}
CLASSIFY = {
    "status": "ok", "mode": "diff",
    "category_a": {"modified": ["pkg/api.py"], "added": ["pkg/new.py", "pkg/renamed.py"],
                   "deleted": ["pkg/gone.py", "pkg/old.py"]},
    "moved_files": [{"old_path": "pkg/m1.py", "new_path": "pkg/m2.py"}],
}


class TestHelperFiles:
    def test_the_diff_maps_onto_category_b(self) -> None:
        b = mod.category_b_from_diff(DIFF)
        assert b["deleted_exports"] == [{"name": "old_fn", "file": "pkg/api.py", "old_line": 10},
                                        {"name": "gone", "file": "pkg/api.py", "old_line": 30}]
        assert b["new_exports"] == [{"name": "new_fn", "file": "pkg/api.py", "line": 12},
                                    {"name": "fresh", "file": "pkg/api.py", "line": 40}]
        # a field other than line, or an unverified signature: modified, with its line in the map and now
        assert b["modified_exports"] == [
            {"name": "search", "file": "pkg/api.py", "old_line": 5, "new_line": 7},
            {"name": "retyped", "file": "pkg/api.py", "old_line": 50, "new_line": 50},
            {"name": "opaque", "file": "pkg/api.py", "old_line": None, "new_line": None},
        ]
        # a line alone, or a move to another modified file: moved, the file it left named for apply to find it
        assert b["moved_exports"] == [
            {"name": "shifted", "file": "pkg/api.py", "old_line": 20, "new_line": 22},
            {"name": "relocated", "file": "pkg/b.py", "old_file": "pkg/a.py", "old_line": 1, "new_line": 3},
        ]

    def test_a_moved_export_that_also_changed_is_modified_only(self) -> None:
        diff = {"removed": [], "added": [], "moved": [
            {"name": "f", "previous_file": "a.py", "current_file": "b.py", "previous_line": 1, "line": 2}],
            "changed": [{"name": "f", "field": "params", "baseline_value": [], "current_value": ["x"],
                         "file": "b.py", "line": 2}]}
        b = mod.category_b_from_diff(diff)
        # it names the file it left, at its line there, for apply to find its entry
        assert b["modified_exports"] == [{"name": "f", "file": "b.py", "old_line": 1, "new_line": 2,
                                          "old_file": "a.py"}]
        assert b["moved_exports"] == []

    def test_assemble_takes_category_a_and_its_moves_from_the_classify_output(self) -> None:
        payload = mod.assemble({"category_a": {"modified": ["typed.py"]}, "degraded_mode": False},
                               category_a_doc=CLASSIFY)
        assert payload["category_a"] == CLASSIFY["category_a"]
        assert payload["category_c"]["renamed_files"] == CLASSIFY["moved_files"]
        assert payload["degraded_mode"] is False

    def test_category_c_renames_leave_the_lists_they_were_found_in(self) -> None:
        payload = mod.assemble(
            {"category_c": {"renamed_files": [{"old_path": "pkg/old.py", "new_path": "pkg/renamed.py"}],
                            "renamed_exports": [{"old_name": "old_fn", "new_name": "new_fn", "file": "pkg/api.py"}]}},
            category_a_doc=CLASSIFY, diff=DIFF)
        assert payload["category_a"] == {"modified": ["pkg/api.py"], "added": ["pkg/new.py"],
                                         "deleted": ["pkg/gone.py"]}
        assert [e["name"] for e in payload["category_b"]["deleted_exports"]] == ["gone"]
        assert [e["name"] for e in payload["category_b"]["new_exports"]] == ["fresh"]
        counts = mod.build_manifest(payload)["counts"]
        assert (counts["files_moved"], counts["exports_renamed"], counts["exports_deleted"]) == (2, 1, 1)

    def test_a_rename_across_files_names_its_old_file(self) -> None:
        payload = mod.assemble({
            "category_b": {"deleted_exports": [{"name": "f", "file": "a.py"}, {"name": "f", "file": "c.py"}],
                           "new_exports": [{"name": "g", "file": "b.py"}]},
            "category_c": {"renamed_exports": [{"old_name": "f", "new_name": "g", "file": "b.py",
                                                "old_file": "c.py"}]}})
        assert payload["category_b"]["deleted_exports"] == [{"name": "f", "file": "a.py"}]
        assert payload["category_b"]["new_exports"] == []

    def test_the_cli_reads_the_helper_files(self, tmp_path: Path) -> None:
        (tmp_path / "category-a.json").write_bytes(json.dumps(CLASSIFY).encode("utf-8"))
        (tmp_path / "category-b-diff.json").write_bytes(json.dumps(DIFF).encode("utf-8"))
        (tmp_path / "categories.json").write_bytes(json.dumps({"update_mode": "normal"}).encode("utf-8"))
        prov = tmp_path / "prov.json"
        prov.write_bytes(json.dumps({"entries": [{"export_name": "x", "source_file": "pkg/gone.py"},
                                                 {"export_name": "y", "source_file": "pkg/api.py"}]}).encode("utf-8"))
        files = ["--input", str(tmp_path / "categories.json"), "--category-a", str(tmp_path / "category-a.json"),
                 "--category-b-diff", str(tmp_path / "category-b-diff.json")]
        build = _run_cli("build", *files)
        assert build.returncode == 0, build.stderr
        counts = json.loads(build.stdout)["counts"]
        assert (counts["files_changed"], counts["files_moved"], counts["exports_new"]) == (1, 1, 2)
        ratio = _run_cli("deletion-ratio", "--provenance-map", str(prov), *files)
        assert ratio.returncode == 0, ratio.stderr
        # gone.py's one export and the diff's two removed ones, of two map entries
        assert json.loads(ratio.stdout)["deleted_export_count"] == 3

    @pytest.mark.parametrize(("flag", "content"), [("--category-a", b"[]"), ("--category-b-diff", b'{"x": 1}'),
                                                    ("--category-a", b"{nope")],
                             ids=["a-not-classify", "b-not-a-diff", "a-invalid-json"])
    def test_a_file_that_is_not_the_helper_output_exits_1(self, tmp_path: Path, flag: str, content: bytes) -> None:
        bad = tmp_path / "bad.json"
        bad.write_bytes(content)
        result = _run_cli("build", flag, str(bad), stdin="{}")
        assert result.returncode == 1
        assert result.stderr.startswith("error: ")


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


# --------------------------------------------------------------------------
# rename-candidates: Category C by fixed rules
# --------------------------------------------------------------------------


def _classify(deleted: list, added: list, moved: list | None = None) -> dict:
    return {"category_a": {"modified": [], "added": added, "deleted": deleted}, "moved_files": moved or []}


OLD_ENTRIES = [
    {"export_name": "connect", "export_type": "function", "source_file": "pkg/old.py", "source_line": 1,
     "params": ["url: str"], "return_type": "Client"},
    {"export_name": "close", "export_type": "function", "source_file": "pkg/old.py", "source_line": 9,
     "params": ["client: Client"], "return_type": "None"},
    {"export_name": "ping", "export_type": "function", "source_file": "pkg/old.py", "source_line": 15,
     "params": [], "return_type": "bool"},
]


def _added(path: str, names: list, *, signature_of=None) -> tuple[dict, dict]:
    """The runner's and the workers' records of an added file's exports."""
    signature_of = signature_of or {e["export_name"]: e for e in OLD_ENTRIES}
    runner = {"exports": [{"export_name": n, "export_type": "function", "source_file": path, "source_line": i + 1,
                           "confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "function_definition"}
                          for i, n in enumerate(names)]}
    details = {"exports": [{"export_name": n, "source_file": path,
                            "params": signature_of.get(n, {}).get("params", []),
                            "return_type": signature_of.get(n, {}).get("return_type")} for n in names]}
    return runner, details


class TestRenameCandidates:
    def test_a_file_moved_with_its_signatures_is_paired_at_forge(self) -> None:
        runner, details = _added("pkg/new.py", ["connect", "close", "ping"])
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/new.py"]), None, {"entries": OLD_ENTRIES},
                                    runner, details, "Forge")
        assert out["category_c"]["renamed_files"] == [{"old_path": "pkg/old.py", "new_path": "pkg/new.py"}]
        assert out["evidence"]["files"][0]["rule"] == "signatures"
        assert out["unpaired"]["deleted_files"] == out["unpaired"]["added_files"] == []

    def test_eighty_percent_is_not_above_the_threshold(self) -> None:
        # 4 of 5 signatures match: 0.80, not above 0.80
        entries = OLD_ENTRIES + [
            {"export_name": "a", "export_type": "function", "source_file": "pkg/old.py", "params": ["x"],
             "return_type": None},
            {"export_name": "b", "export_type": "function", "source_file": "pkg/old.py", "params": ["y"],
             "return_type": None}]
        sigs = {e["export_name"]: e for e in entries}
        sigs["b"] = {**sigs["b"], "params": ["y", "z"]}  # one changed signature
        names = ["connect", "close", "ping", "a", "b"]
        runner, details = _added("pkg/new.py", names, signature_of=sigs)
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/new.py"]), None,
                                    {"entries": [e for e in entries if e["export_name"] != "ping"] +
                                     [OLD_ENTRIES[2]]}, runner, details, "Deep")
        assert out["category_c"]["renamed_files"] == []
        assert out["unpaired"]["deleted_files"] == ["pkg/old.py"]

    def test_a_same_content_move_is_left_to_category_a(self) -> None:
        runner, details = _added("pkg/new.py", ["connect", "close", "ping"])
        move = [{"old_path": "pkg/old.py", "new_path": "pkg/new.py"}]
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/new.py"], move), None,
                                    {"entries": OLD_ENTRIES}, runner, details, "Forge")
        assert out["category_c"]["renamed_files"] == [] and out["unpaired"]["deleted_files"] == []

    def test_quick_tier_pairs_by_names_when_no_size_can_be_read(self, tmp_path: Path) -> None:
        runner, details = _added("pkg/new.py", ["connect", "close", "ping"])
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/new.py"]), None, {"entries": OLD_ENTRIES},
                                    {"exports": []}, details, "Quick", source_root=tmp_path)
        assert out["category_c"]["renamed_files"] == [{"old_path": "pkg/old.py", "new_path": "pkg/new.py"}]
        assert out["evidence"]["files"][0]["rule"] == "names (size not checked)"
        # two shared names of four: 50%, not above 70%
        runner, details = _added("pkg/new.py", ["connect", "close", "other"])
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/new.py"]), None, {"entries": OLD_ENTRIES},
                                    {"exports": []}, details, "Quick")
        assert out["category_c"]["renamed_files"] == []

    @pytest.mark.skipif(subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
                        reason="no git")
    @pytest.mark.parametrize(("new_size", "paired"), [(105, True), (130, False)], ids=["within-20", "outside-20"])
    def test_quick_tier_reads_the_deleted_size_from_git(self, tmp_path: Path, new_size: int, paired: bool) -> None:
        repo = tmp_path / "src"
        (repo / "pkg").mkdir(parents=True)
        (repo / "pkg" / "old.py").write_bytes(b"x" * 100)

        def git(*args):
            return subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                                  capture_output=True, text=True, check=True).stdout.strip()

        git("init", "-q")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        commit = git("rev-parse", "HEAD")
        (repo / "pkg" / "old.py").unlink()
        (repo / "pkg" / "new.py").write_bytes(b"y" * new_size)
        _runner, details = _added("pkg/new.py", ["connect", "close", "ping"])
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/new.py"]), None, {"entries": OLD_ENTRIES},
                                    {"exports": []}, details, "Quick", source_root=repo, sizes_commit=commit)
        assert bool(out["category_c"]["renamed_files"]) is paired
        if paired:
            assert out["evidence"]["files"][0]["rule"] == "size-and-names"

    def test_a_tie_pairs_neither(self) -> None:
        runner_a, details_a = _added("pkg/a.py", ["connect", "close", "ping"])
        runner_b, details_b = _added("pkg/b.py", ["connect", "close", "ping"])
        runner = {"exports": runner_a["exports"] + runner_b["exports"]}
        details = {"exports": details_a["exports"] + details_b["exports"]}
        out = mod.rename_candidates(_classify(["pkg/old.py"], ["pkg/a.py", "pkg/b.py"]), None,
                                    {"entries": OLD_ENTRIES}, runner, details, "Forge")
        assert out["category_c"]["renamed_files"] == []
        assert out["unpaired"]["added_files"] == ["pkg/a.py", "pkg/b.py"]

    def test_an_export_renamed_with_its_signature_is_paired_at_forge(self) -> None:
        diff = {"removed": [{"name": "search", "type": "function", "file": "pkg/api.py", "line": 5,
                             "params": ["q: str"], "return_type": "list"}],
                "added": [{"name": "find", "type": "function", "file": "pkg/api.py", "line": 5,
                           "params": ["q: str"], "return_type": "list"},
                          {"name": "other", "type": "function", "file": "pkg/api.py", "line": 9,
                           "params": [], "return_type": "None"}]}
        out = mod.rename_candidates(_classify([], []), diff, {"entries": []}, None, None, "Forge+")
        assert out["category_c"]["renamed_exports"] == [{"old_name": "search", "new_name": "find",
                                                         "file": "pkg/api.py"}]
        assert out["unpaired"]["added_exports"] == [{"name": "other", "file": "pkg/api.py"}]
        # a second export with the same signature: a tie, so no pair
        diff["added"].append({"name": "lookup", "type": "function", "file": "pkg/b.py", "line": 1,
                              "params": ["q:str"], "return_type": "list"})
        out = mod.rename_candidates(_classify([], []), diff, {"entries": []}, None, None, "Forge+")
        assert out["category_c"]["renamed_exports"] == []

    def test_an_export_moved_to_an_added_file_names_its_old_file(self) -> None:
        diff = {"removed": [{"name": "search", "type": "function", "file": "pkg/api.py", "line": 5,
                             "params": ["q"], "return_type": None}], "added": []}
        runner = {"exports": [{"export_name": "query", "export_type": "function", "source_file": "pkg/query.py",
                               "source_line": 3}]}
        details = {"exports": [{"export_name": "query", "source_file": "pkg/query.py", "params": ["q"]}]}
        out = mod.rename_candidates(_classify([], ["pkg/query.py"]), diff, {"entries": []}, runner, details, "Forge")
        assert out["category_c"]["renamed_exports"] == [
            {"old_name": "search", "new_name": "query", "file": "pkg/query.py", "old_file": "pkg/api.py"}]

    def test_quick_tier_pairs_exports_by_name(self) -> None:
        diff = {"removed": [{"name": "get_user", "type": "function", "file": "a.py", "line": 1},
                            {"name": "Config", "type": "class", "file": "a.py", "line": 5}],
                "added": [{"name": "get_users", "type": "function", "file": "a.py", "line": 1},
                          {"name": "Configs", "type": "function", "file": "a.py", "line": 5}]}
        out = mod.rename_candidates(_classify([], []), diff, {"entries": []}, None, None, "Quick")
        # Config -> Configs is alike enough, but its export type changed: no pair
        assert out["category_c"]["renamed_exports"] == [{"old_name": "get_user", "new_name": "get_users",
                                                         "file": "a.py"}]
        assert out["evidence"]["exports"][0]["rule"] == "name-similarity"

    def test_the_cli_writes_the_output_file(self, tmp_path: Path) -> None:
        runner, details = _added("pkg/new.py", ["connect", "close", "ping"])
        files = {"category-a.json": _classify(["pkg/old.py"], ["pkg/new.py"]),
                 "provenance-map.json": {"entries": OLD_ENTRIES}, "extraction.json": runner,
                 "export-details.json": details}
        for name, value in files.items():
            (tmp_path / name).write_bytes(json.dumps(value).encode("utf-8"))
        out = tmp_path / "category-c.json"
        result = _run_cli("rename-candidates", "--category-a", str(tmp_path / "category-a.json"),
                          "--provenance-map", str(tmp_path / "provenance-map.json"),
                          "--extraction", str(tmp_path / "extraction.json"),
                          "--export-details", str(tmp_path / "export-details.json"),
                          "--tier", "Forge", "-o", str(out))
        assert result.returncode == 0, result.stderr
        assert json.loads(out.read_bytes())["category_c"]["renamed_files"] == [
            {"old_path": "pkg/old.py", "new_path": "pkg/new.py"}]
        bad = _run_cli("rename-candidates", "--category-a", str(tmp_path / "category-a.json"),
                       "--provenance-map", str(tmp_path / "provenance-map.json"), "--tier", "Ultra")
        assert bad.returncode == 2  # argparse choices


# --------------------------------------------------------------------------
# apply: the provenance map an update writes
# --------------------------------------------------------------------------


STATS_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-render-metadata-stats.py"
_stats_spec = importlib.util.spec_from_file_location("skf_render_metadata_stats_apply", STATS_PATH)
stats = importlib.util.module_from_spec(_stats_spec)
_stats_spec.loader.exec_module(stats)

BLOCK = {"generation_date": "2026-10-01T10:00:00Z", "confidence_tier": "Forge", "manual_sections_preserved": 2}


def _entry(name: str, path: str, line: int, **extra) -> dict:
    return {"export_name": name, "export_type": "function", "source_library": "lib", "params": [],
            "return_type": None, "source_file": path, "source_line": line, "confidence": "T1",
            "extraction_method": "ast-grep", "ast_node_type": "function_definition", "signature_source": "T1",
            **extra}


def _old_map() -> dict:
    return {"provenance_version": "2.0", "skill_name": "lib", "skill_type": "single", "source_commit": "aaa",
            "source_ref": "v1", "generated_at": "2026-01-01T00:00:00Z",
            "last_update": {"date": "2026-02-01", "mode": "gap-driven"},
            "update_operations": [{"date": "2026-02-01"}],
            "entries": [_entry("stable", "pkg/a.py", 1), _entry("search", "pkg/a.py", 10, notes="keep me"),
                        _entry("old_fn", "pkg/a.py", 20), _entry("shifted", "pkg/a.py", 30),
                        _entry("gone_a", "pkg/gone.py", 1), _entry("mv", "pkg/old.py", 2, deprecated=True),
                        _entry("renamed_from", "pkg/a.py", 40)],
            "file_entries": [{"file_name": "scripts/run.sh", "file_type": "script", "source_file": "tools/run.sh",
                              "confidence": "T1-low", "extraction_method": "file-copy", "content_hash": "sha256:old"},
                             {"file_name": "docs/authoritative/AGENTS.md", "file_type": "doc",
                              "source_file": "AGENTS.md", "confidence": "T1-low",
                              "extraction_method": "promoted-authoritative", "content_hash": "sha256:doc"}]}


class TestApplyNormal:
    def _inputs(self) -> dict:
        manifest = {"total_export_changes": 5, "per_file": [
            {"file_path": "pkg/a.py", "status": "MODIFIED", "exports_affected": [
                {"name": "search", "change_type": "MODIFIED_EXPORT", "old_line": 10, "new_line": 11},
                {"name": "helper", "change_type": "NEW_EXPORT", "old_line": None, "new_line": 50},
                {"name": "old_fn", "change_type": "DELETED_EXPORT", "old_line": 20, "new_line": None},
                {"name": "shifted", "change_type": "MOVED_EXPORT", "old_line": 30, "new_line": 33}]},
            {"file_path": "pkg/new.py", "status": "ADDED", "exports_affected": []},
            {"file_path": "pkg/gone.py", "status": "DELETED", "exports_affected": []},
            {"file_path": "pkg/moved.py", "status": "MOVED", "old_path": "pkg/old.py", "exports_affected": []}]}
        extraction = {"exports": [
            {"export_name": "search", "export_type": "function", "source_file": "pkg/a.py", "source_line": 11,
             "ast_node_type": "function_definition", "ast_recipe": "py-def", "confidence": "T1",
             "extraction_method": "ast-grep"},
            {"export_name": "helper", "export_type": "function", "source_file": "pkg/a.py", "source_line": 50,
             "ast_node_type": "function_definition", "confidence": "T1", "extraction_method": "ast-grep"},
            {"export_name": "fresh", "export_type": "class", "source_file": "pkg/new.py", "source_line": 3,
             "ast_node_type": "class_definition", "confidence": "T1", "extraction_method": "ast-grep"},
            {"export_name": "mv", "export_type": "function", "source_file": "pkg/moved.py", "source_line": 7,
             "ast_node_type": "function_definition", "confidence": "T1", "extraction_method": "ast-grep"},
            {"export_name": "renamed_to", "export_type": "function", "source_file": "pkg/a.py", "source_line": 41,
             "ast_node_type": "function_definition", "confidence": "T1", "extraction_method": "ast-grep"}]}
        details = {"exports": [
            {"export_name": "search", "source_file": "pkg/a.py", "params": ["q", "limit: int"], "return_type": "list"},
            {"export_name": "by_eye", "export_type": "constant", "source_file": "pkg/new.py", "source_line": 9,
             "params": [], "return_type": None, "confidence": "T1-low", "extraction_method": "source-read"}]}
        records = {"mode": "normal", "files": [{"file_path": "pkg/a.py", "exports": [
            {"name": "helper", "type": "function", "location": "pkg/a.py:50-52", "parameters": ["x"],
             "return_type": "int", "confidence": "T1", "extraction_method": "ast-grep",
             "ast_node_type": "function_definition"}]}]}
        categories = {"category_c": {"renamed_exports": [{"old_name": "renamed_from", "new_name": "renamed_to",
                                                          "file": "pkg/a.py"}]}}
        return {"manifest": manifest, "extraction": extraction, "details": details, "records": records,
                "categories": categories}

    def test_each_file_and_export_change_lands(self) -> None:
        old = _old_map()
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        test_report_run_id=None, source_commit="bbb", source_ref="v2",
                                        **self._inputs(), **BLOCK)
        entries = {(e["export_name"], e["source_file"]): e for e in doc["entries"]}
        # untouched: the exact value
        assert entries[("stable", "pkg/a.py")] == old["entries"][0]
        # modified: the runner's line and labels, the details' signature, its own extra keys kept
        search = entries[("search", "pkg/a.py")]
        assert (search["source_line"], search["params"], search["return_type"], search["notes"]) == \
            (11, ["q", "limit: int"], "list", "keep me")
        # new: the worker's signature where the details have none
        helper = entries[("helper", "pkg/a.py")]
        assert (helper["source_line"], helper["params"], helper["return_type"], helper["signature_source"]) == \
            (50, ["x"], "int", "T1")
        assert ("old_fn", "pkg/a.py") not in entries and ("gone_a", "pkg/gone.py") not in entries
        assert entries[("shifted", "pkg/a.py")]["source_line"] == 33
        # the added file: every fresh record, by tool
        assert entries[("fresh", "pkg/new.py")]["confidence"] == "T1"
        by_eye = entries[("by_eye", "pkg/new.py")]
        assert (by_eye["confidence"], by_eye["extraction_method"], by_eye["ast_node_type"],
                by_eye["signature_source"]) == ("T1-low", "source-read", None, "T1-low")
        # the moved file: re-pointed, the old entry's keys carried
        moved = entries[("mv", "pkg/moved.py")]
        assert (moved["source_line"], moved["deprecated"]) == (7, True) and ("mv", "pkg/old.py") not in entries
        assert ("renamed_to", "pkg/a.py") in entries and ("renamed_from", "pkg/a.py") not in entries
        assert entries[("renamed_to", "pkg/a.py")]["source_line"] == 41
        # the update block, in place of the earlier one, and the older history key kept
        assert doc["last_update"] == "2026-10-01T10:00:00Z" and doc["update_type"] == "incremental"
        assert (doc["files_changed"], doc["exports_affected"], doc["manual_sections_preserved"]) == (4, 5, 2)
        assert doc["test_report_run_id"] is None and doc["update_operations"] == [{"date": "2026-02-01"}]
        assert list(doc).index("last_update") == list(old).index("last_update")
        assert (doc["source_commit"], doc["source_ref"]) == ("bbb", "v2")
        assert stats.check_label_agreement(doc) == []
        assert sorted(summary["entries"]["removed"]) == ["gone_a", "mv", "old_fn"]

    def test_a_new_export_with_no_record_is_named_not_invented(self) -> None:
        inputs = self._inputs()
        inputs["extraction"]["exports"] = [e for e in inputs["extraction"]["exports"] if e["export_name"] != "helper"]
        inputs["records"]["files"] = []
        doc, summary = mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                                        test_report_run_id=None, **inputs, **BLOCK)
        assert "helper" not in {e["export_name"] for e in doc["entries"]}
        assert "provenance: helper in pkg/a.py: no extraction record, entry not added" in summary["warnings"]

    def test_the_map_keeps_its_source_fields_when_none_is_given(self) -> None:
        doc, _ = mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                                  test_report_run_id=None, **BLOCK)
        assert (doc["source_commit"], doc["source_ref"]) == ("aaa", "v1")
        assert doc["entries"] == _old_map()["entries"]


class TestApplyFiles:
    def test_compare_rows_new_files_and_promoted_docs(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        (src / "tools").mkdir(parents=True)
        (src / "tools" / "new.py").write_bytes(b"print('x')\n")
        compare = {"comparisons": [
            {"source_file": "tools/run.sh", "classification": "MODIFIED_FILE", "stored_hash": "sha256:old",
             "current_hash": "sha256:new"},
            {"source_file": "AGENTS.md", "classification": "DELETED_FILE", "stored_hash": "sha256:doc",
             "current_hash": None}]}
        new_files = {"new_files": [{"source_file": "tools/new.py", "kind": "script"},
                                   {"source_file": "tools/run.sh", "kind": "script"}]}
        promoted = [{"path": "llms.txt", "heuristic": "llms.txt", "content_hash": "sha256:llms"}]
        doc, summary = mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                                        test_report_run_id=None, compare=compare, new_files=new_files,
                                        promoted=promoted, source_root=src, **BLOCK)
        rows = {r["source_file"]: r for r in doc["file_entries"]}
        assert rows["tools/run.sh"]["content_hash"] == "sha256:new" and "AGENTS.md" not in rows
        import hashlib
        assert rows["tools/new.py"] == {"file_name": "scripts/new.py", "file_type": "script",
                                        "source_file": "tools/new.py", "confidence": "T1-low",
                                        "extraction_method": "file-copy",
                                        "content_hash": "sha256:" + hashlib.sha256(b"print('x')\n").hexdigest()}
        assert rows["llms.txt"]["file_name"] == "docs/authoritative/llms.txt"
        assert rows["llms.txt"]["extraction_method"] == "promoted-authoritative"
        assert summary["file_entries"] == {"added": ["tools/new.py", "llms.txt"], "updated": ["tools/run.sh"],
                                           "removed": ["AGENTS.md"]}

    def test_a_new_file_needs_the_source_root(self) -> None:
        with pytest.raises(ValueError, match="--source-root"):
            mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                             test_report_run_id=None,
                             new_files={"new_files": [{"source_file": "x.py", "kind": "script"}]}, **BLOCK)


def _verification(name, outcome, category, **extra) -> dict:
    return {"export_name": name, "verification": outcome, "gap_category": category, "severity": "High",
            "in_map": False, "map_entry": None, **extra}


class TestApplyGapDriven:
    def _records(self) -> dict:
        return {"mode": "gap-driven", "verification": [
            _verification("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                          map_entry={"source_file": "pkg/a.py", "source_line": 1}),
            _verification("search", "moved", "MOVED_EXPORT", in_map=True,
                          map_entry={"source_file": "pkg/a.py", "source_line": 10}, new_location="pkg/a.py:12"),
            _verification("old_fn", "rescoped", "DELETED_EXPORT", in_map=True,
                          map_entry={"source_file": "pkg/a.py", "source_line": 20}),
            _verification("deep", "re-extracted", "NEW_EXPORT", new_location="pkg/deep.py:4"),
            _verification("cited", "verified", "NEW_EXPORT", source_citation={"file": "pkg/c.py", "line": 8},
                          reachability="public"),
            _verification("cited", "moved", "MODIFIED_EXPORT", source_citation={"file": "pkg/c.py", "line": 7},
                          new_location="pkg/c.py:8", reachability="public"),
            _verification("internal", "verified", "NEW_EXPORT", source_citation={"file": "pkg/i.py", "line": 2},
                          reachability="internal-unreachable"),
            _verification("doc_only", "unknown", "NEW_EXPORT", severity="Medium"),
            _verification("gone", "missing", "MODIFIED_EXPORT", in_map=True,
                          map_entry={"source_file": "pkg/gone.py", "source_line": 1}, gap_id="GAP-009"),
            _verification("shifted", "unknown", "MOVED_EXPORT", in_map=True,
                          pinned_definition_lines=[31]),
        ], "files": [{"file_path": "pkg/deep.py", "exports": [
            {"name": "deep", "type": "function", "location": "pkg/deep.py:4-9", "params": ["a: int"],
             "return_type": "int", "confidence": "T1", "extraction_method": "ast-grep",
             "ast_node_type": "function_definition"}]}]}

    def _merge(self) -> dict:
        return {"exports": [{"export_name": "cited", "export_type": "function", "params": ["z"],
                             "return_type": "str"},
                            {"export_name": "doc_only", "export_type": "class"}]}

    def test_each_outcome_writes_what_it_allows(self) -> None:
        old = _old_map()
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib",
                                        records=self._records(), merge_records=self._merge(),
                                        test_report_run_id="20260930T101010Z-2-bbbb", **BLOCK)
        entries = {(e["export_name"], e.get("source_file")): e for e in doc["entries"]}
        assert entries[("stable", "pkg/a.py")] == old["entries"][0]
        search = entries[("search", "pkg/a.py")]
        assert search["source_line"] == 12 and {k: v for k, v in search.items() if k != "source_line"} == \
            {k: v for k, v in old["entries"][1].items() if k != "source_line"}
        assert ("old_fn", "pkg/a.py") not in entries
        deep = entries[("deep", "pkg/deep.py")]
        assert (deep["source_line"], deep["params"], deep["confidence"], deep["signature_source"]) == \
            (4, ["a: int"], "T1", "T1")
        # two records pin one cited export: one entry, at the first record's line, labelled source-read
        cited = [e for e in doc["entries"] if e["export_name"] == "cited"]
        assert len(cited) == 1 and (cited[0]["source_line"], cited[0]["extraction_method"]) == (8, "source-read")
        assert (cited[0]["export_type"], cited[0]["params"], cited[0]["return_type"]) == ("function", ["z"], "str")
        assert "internal" not in {e["export_name"] for e in doc["entries"]}
        doc_only = entries[("doc_only", None)]
        assert "source_file" not in doc_only and "source_line" not in doc_only
        assert doc_only["export_type"] == "class" and doc_only["signature_source"] == "T1-low"
        # missing and an unknown MOVED_EXPORT: left as they were, for a person; a blocking export the map holds
        # says what to fix (#805)
        assert entries[("gone_a", "pkg/gone.py")] == old["entries"][4]
        assert entries[("shifted", "pkg/a.py")] == old["entries"][3]
        assert summary["warnings"] == [
            "provenance: gone (GAP-009): missing (its map entry's file pkg/gone.py is gone); its entry is left "
            "unchanged. Fix the entry by hand (set its source_file and source_line to the line that defines it), "
            "then re-run update-skill",
            "provenance: shifted: unknown; definition lines per the test report: [31]"]
        assert doc["update_type"] == "gap-driven" and doc["test_report_run_id"] == "20260930T101010Z-2-bbbb"
        assert doc["exports_affected"] == 10
        assert stats.check_label_agreement(doc) == []

    def test_a_moved_export_whose_file_is_gone_names_the_file(self) -> None:
        """#832: rule R5 moves a line, never a file. A provenance-line gap whose map entry's file the pinned source
        lacks keeps its entry, whatever its severity, with a warning that names the file and the hand fix, and
        never prints the definition lines the test report did not list."""
        old = _old_map()
        records = {"mode": "gap-driven", "verification": [
            _verification("gone_a", "missing", "MOVED_EXPORT", severity="Low", in_map=True,
                          map_entry={"source_file": "pkg/gone.py", "source_line": 1}, gap_id="GAP-004",
                          pinned_definition_lines=None),
            _verification("mv", "missing", "MOVED_EXPORT", severity="Low", in_map=True,
                          map_entry={"source_file": "pkg/old.py", "source_line": 2}, pinned_definition_lines=[5]),
            _verification("shifted", "unknown", "MOVED_EXPORT", severity="Low", in_map=True,
                          map_entry={"source_file": "pkg/a.py", "source_line": 30}, unknown_reason="no-definition",
                          pinned_definition_lines=None)]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"]
        fix = ("its entry is left unchanged. Fix the entry by hand (set its source_file and source_line to the line "
               "that defines it), then re-run update-skill")
        assert summary["warnings"] == [
            f"provenance: gone_a (GAP-004): missing (its map entry's file pkg/gone.py is gone); {fix}",
            f"provenance: mv: missing (its map entry's file pkg/old.py is gone; definition lines per the test report: "
            f"[5]); {fix}",
            "provenance: shifted: unknown (no-definition: no line of its file defines it, by the definition-line "
            "rules)"]
        assert not any("None" in w for w in summary["warnings"])

    # #804, #809: an export a spot-check located takes the signature §4a's record gives at its line

    def _signed(self, name: str, outcome: str, category: str, **extra) -> dict:
        return {"mode": "gap-driven", "verification": [_verification(name, outcome, category, **extra)], "files": []}

    def test_a_verified_entry_takes_the_records_signature(self) -> None:
        old = _old_map()
        old["entries"][0]["params"] = ["x"]
        records = self._signed("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 1}, export_type="function",
                               params=["y"], return_type="int", extraction_method="ast-grep")
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        stable = doc["entries"][0]
        assert (stable["params"], stable["return_type"]) == (["y"], "int")
        assert {k: stable[k] for k in ("confidence", "extraction_method", "ast_node_type", "signature_source")} == \
            {"confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "function_definition",
             "signature_source": "T1"}
        assert summary["entries"]["updated"] == ["stable"] and doc["entries"][1:] == old["entries"][1:]
        assert stats.check_label_agreement(doc) == []

    def test_a_moved_entry_takes_its_new_line_and_the_records_signature(self) -> None:
        old = _old_map()
        records = self._signed("search", "moved", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 10}, new_location="pkg/a.py:12",
                               export_type="function", params=["q: str", "limit: int = 10"], return_type="list",
                               extraction_method="ast-grep")
        doc, _ = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                  test_report_run_id="r", **BLOCK)
        search = doc["entries"][1]
        assert (search["source_line"], search["params"], search["return_type"], search["notes"]) == \
            (12, ["q: str", "limit: int = 10"], "list", "keep me")
        assert (search["confidence"], search["extraction_method"]) == ("T1", "ast-grep")

    def test_a_pinned_cited_export_takes_its_records_signature_over_merges(self) -> None:
        records = self._signed("cited", "verified", "NEW_EXPORT", source_citation={"file": "pkg/c.py", "line": 8},
                               reachability="public", export_type="function", params=["a: int"],
                               extraction_method="ast-grep")
        merge = {"exports": [{"export_name": "cited", "export_type": "class", "params": ["z"], "return_type": "str"}]}
        doc, _ = mod.apply_update(update_type="gap-driven", provenance=_old_map(), skill_name="lib",
                                  records=records, merge_records=merge, test_report_run_id="r", **BLOCK)
        [cited] = [e for e in doc["entries"] if e["export_name"] == "cited"]
        # with a record, every part is the record's, its null return type included: merge's prose gives none
        assert (cited["export_type"], cited["params"]) == ("function", ["a: int"]) and "return_type" not in cited
        # a pinned export keeps its source-read labels, whatever its record's tool
        assert {k: cited[k] for k in ("source_line", "confidence", "extraction_method", "ast_node_type",
                                      "signature_source")} == \
            {"source_line": 8, "confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
             "signature_source": "T1-low"}
        assert stats.check_label_agreement(doc) == []

    def test_a_source_read_entry_keeps_its_t1_low_signature_source(self) -> None:
        old = _old_map()
        old["entries"][0].update(params=["x"], confidence="T1-low", extraction_method="source-read",
                                 ast_node_type=None, signature_source="T1-low")
        records = self._signed("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 1}, export_type="function",
                               params=["y"], extraction_method="ast-grep")
        doc, _ = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                  test_report_run_id="r", **BLOCK)
        stable = doc["entries"][0]
        assert stable["params"] == ["y"]
        assert {k: stable[k] for k in ("confidence", "extraction_method", "ast_node_type", "signature_source")} == \
            {"confidence": "T1-low", "extraction_method": "source-read", "ast_node_type": None,
             "signature_source": "T1-low"}
        assert stats.check_label_agreement(doc) == []
        # an ast-grep entry whose record was read by eye takes T1-low too
        records["verification"][0]["extraction_method"] = "source-read"
        doc, _ = mod.apply_update(update_type="gap-driven", provenance=_old_map(), skill_name="lib",
                                  records=records, test_report_run_id="r", **BLOCK)
        assert (doc["entries"][0]["signature_source"], doc["entries"][0]["confidence"]) == ("T1-low", "T1")
        assert stats.check_label_agreement(doc) == []

    def test_an_ast_bridge_entry_repaired_from_a_source_read_record_takes_t1_low(self) -> None:
        old = _old_map()
        old["entries"][0]["extraction_method"] = "ast_bridge"
        records = self._signed("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 1}, export_type="function",
                               params=["y"], extraction_method="source-read")
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        stable = doc["entries"][0]
        assert (stable["params"], stable["signature_source"], stable["extraction_method"]) == \
            (["y"], "T1-low", "ast_bridge")
        # the relabel is announced: apply lists it, and warns
        assert summary["relabeled"] == [{"name": "stable", "file": "pkg/a.py", "from": "T1", "to": "T1-low"}]
        assert summary["warnings"] == ["provenance: stable in pkg/a.py: signature_source T1 relabeled T1-low, from "
                                       "the source-read record of its signature"]
        assert stats.check_label_agreement(doc) == []

    def test_a_null_record_part_clears_the_entrys_old_value(self) -> None:
        old = _old_map()
        old["entries"][0].update(params=["x"], return_type="int")
        records = self._signed("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 1}, export_type="function",
                               params=["y"], return_type=None, extraction_method="ast-grep")
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"][0]["params"] == ["y"] and "return_type" not in doc["entries"][0]
        assert summary["relabeled"] == []

    def test_a_map_held_entry_with_no_record_keeps_its_signature(self) -> None:
        old = _old_map()
        old["entries"][0]["params"] = ["x"]
        records = self._signed("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 1})
        merge = {"exports": [{"export_name": "stable", "export_type": "class", "params": ["z"], "return_type": "str"}]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        merge_records=merge, test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"] and summary["entries"]["updated"] == []

    def test_a_record_of_another_kind_brings_its_node_kind(self) -> None:
        old = _old_map()
        old["entries"][0].update(export_type="variable", ast_node_type="assignment")
        records = self._signed("stable", "verified", "MODIFIED_EXPORT", in_map=True,
                               map_entry={"source_file": "pkg/a.py", "source_line": 1}, export_type="function",
                               params=["y"], extraction_method="ast-grep", ast_node_type="function_definition")
        doc, _ = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                  test_report_run_id="r", **BLOCK)
        assert (doc["entries"][0]["export_type"], doc["entries"][0]["ast_node_type"]) == \
            ("function", "function_definition")

    def test_every_warning_names_the_drift_under_the_override(self) -> None:
        records = {"mode": "gap-driven", "verification": [
            _verification("stable", "verified", "MOVED_EXPORT", in_map=True,
                          map_entry={"source_file": "pkg/a.py", "source_line": 1}, pinned_definition_lines=[2]),
            _verification("search", "unknown", "MOVED_EXPORT", in_map=True, unknown_reason="drift-override",
                          pinned_definition_lines=[11]),
            _verification("gone", "missing", "MODIFIED_EXPORT", in_map=True, severity="Medium"),
            _verification("multi", "unknown", "MOVED_EXPORT", in_map=True, unknown_reason="several-definitions",
                          pinned_definition_lines=[7])]}
        _doc, summary = mod.apply_update(update_type="gap-driven", provenance=_old_map(), skill_name="lib",
                                         records=records, test_report_run_id="r", drift=("abc1234", "def5678"),
                                         **BLOCK)
        note = "drift override: HEAD abc1234 is not pinned def5678"
        assert summary["warnings"] == [
            f"provenance: stable: verified at HEAD only ({note}; definition lines per the test report: [2])",
            f"provenance: search: unknown ({note}; no line taken from HEAD; definition lines per the test report: "
            "[11])",
            f"provenance: gone: missing ({note})",
            # the drift note comes after the cause of an unknown
            "provenance: multi: unknown (several-definitions: several lines of its file define it, none the "
            f"recorded one; {note}; definition lines per the test report: [7])"]

    @pytest.mark.parametrize("severity", ["High", "Critical", None, "urgent"],
                             ids=["high", "critical", "none", "unrecognized"])
    def test_a_blocking_gap_with_no_line_is_refused(self, severity) -> None:
        records = {"mode": "gap-driven", "verification": [
            _verification("lost", "unknown", "NEW_EXPORT", severity=severity)]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=_old_map(), skill_name="lib",
                                        records=records, test_report_run_id="r", **BLOCK)
        assert doc == {} and summary == {"status": "refused",
                                         "blocking_unresolved": [{"export_name": "lost", "severity": severity}]}

    def test_the_cli_refuses_with_exit_3_and_writes_nothing(self, tmp_path: Path) -> None:
        (tmp_path / "map.json").write_bytes(json.dumps(_old_map()).encode("utf-8"))
        (tmp_path / "records.json").write_bytes(json.dumps({"mode": "gap-driven", "verification": [
            _verification("lost", "unknown", "NEW_EXPORT")]}).encode("utf-8"))
        out = tmp_path / "new-map.json"
        args = ["apply", "--update-type", "gap-driven", "--provenance-map", str(tmp_path / "map.json"),
                "--reextract-records", str(tmp_path / "records.json"), "--skill-name", "lib",
                "--generation-date", "2026-10-01T10:00:00Z", "--confidence-tier", "Forge",
                "--manual-sections-preserved", "0", "-o", str(out)]
        result = _run_cli(*args)
        assert result.returncode == 3 and json.loads(result.stdout)["status"] == "refused" and not out.exists()
        (tmp_path / "records.json").write_bytes(json.dumps({"mode": "gap-driven", "verification": [
            _verification("lost", "unknown", "NEW_EXPORT", severity="Low")]}).encode("utf-8"))
        result = _run_cli(*args, "--test-report-run-id", "r1", "--source-commit", "", "--source-ref", "")
        assert result.returncode == 0, result.stderr
        written = json.loads(out.read_bytes())
        assert written["source_commit"] is None and written["test_report_run_id"] == "r1"
        assert json.loads(result.stdout)["map"] == str(out)
        assert out.read_bytes().endswith(b"}\n") and b'\n  "provenance_version"' in out.read_bytes()


class TestApplyOtherModes:
    def test_a_degraded_run_maps_every_fresh_record(self) -> None:
        extraction = {"exports": [{"export_name": "a", "export_type": "function", "source_file": "x.py",
                                   "source_line": 1, "ast_node_type": "function_definition",
                                   "extraction_method": "ast-grep", "confidence": "T1"}]}
        details = {"exports": [{"export_name": "b", "export_type": "constant", "source_file": "y.py",
                                "source_line": 2, "extraction_method": "source-read", "confidence": "T1-low"}]}
        doc, _ = mod.apply_update(update_type="full", provenance=None, skill_name="lib", extraction=extraction,
                                  details=details, test_report_run_id=None, source_commit="ccc", **BLOCK)
        assert (doc["provenance_version"], doc["skill_name"], doc["source_commit"]) == ("2.0", "lib", "ccc")
        assert [(e["export_name"], e["source_library"], e["signature_source"]) for e in doc["entries"]] == [
            ("a", "lib", "T1"), ("b", "lib", "T1-low")]
        assert doc["update_type"] == "full" and stats.check_label_agreement(doc) == []

    def test_a_map_is_required_outside_degraded_mode(self) -> None:
        with pytest.raises(ValueError, match="--provenance-map is required"):
            mod.apply_update(update_type="incremental", provenance=None, skill_name="lib",
                             test_report_run_id=None, **BLOCK)

    def test_a_docs_only_run_replaces_the_entries_of_each_changed_url(self) -> None:
        url, kept = "https://docs.example.com/api", "https://docs.example.com/other"
        old = {"entries": [
            {"export_name": "get", "export_type": "function", "source_file": url, "confidence": "T3",
             "signature_source": "T3", "notes": "n"},
            {"export_name": "gone", "source_file": url, "confidence": "T3"},
            {"export_name": "other", "source_file": kept, "confidence": "T3"}]}
        records = {"mode": "docs-only", "changed_urls": [url], "exports": [
            {"name": "get", "type": "function", "params": ["id"], "return_type": "Item", "url": url},
            {"name": "put", "type": "function", "params": ["item"], "url": url}]}
        doc, _ = mod.apply_update(update_type="incremental", provenance=old, skill_name="docs", records=records,
                                  test_report_run_id=None, **BLOCK)
        by_name = {e["export_name"]: e for e in doc["entries"]}
        assert set(by_name) == {"get", "put", "other"}
        assert (by_name["get"]["params"], by_name["get"]["notes"], by_name["put"]["confidence"]) == \
            (["id"], "n", "T3")
        # an unchanged URL's entry is left alone but for the signature_source it lacked (#802)
        assert by_name["other"] == {**old["entries"][2], "signature_source": "T3"}
        assert (doc["files_changed"], doc["exports_affected"]) == (1, 2)


# #808: a new entry takes the source_library of its file's entries, else its folder's, in a map naming several

STORYBOOK_REACT = "code/renderers/react/src/public-types.ts"
STORYBOOK_CLI = "code/core/src/cli/angular/other.ts"


def _storybook_map(*extra: dict) -> dict:
    """storybook's shape: its first entry names @storybook/react, code/core's entries storybook."""
    return {"provenance_version": "2.0", "skill_name": "storybook", "skill_type": "single", "entries": [
        _entry("Meta", STORYBOOK_REACT, 12, source_library="@storybook/react"),
        _entry("fn", STORYBOOK_CLI, 3, source_library="storybook"), *extra]}


def _runner_export(name: str, path: str, line: int) -> dict:
    return {"export_name": name, "export_type": "function", "source_file": path, "source_line": line,
            "ast_node_type": "function_declaration", "confidence": "T1", "extraction_method": "ast-grep"}


class TestSourceLibrary:
    def _library(self, doc: dict, name: str) -> str:
        [entry] = [e for e in doc["entries"] if e["export_name"] == name]
        return entry["source_library"]

    def _incremental(self, old: dict, per_file: list, exports: list) -> tuple[dict, dict]:
        return mod.apply_update(update_type="incremental", provenance=old, skill_name="storybook",
                                manifest={"total_export_changes": len(exports), "per_file": per_file},
                                extraction={"exports": exports}, test_report_run_id=None, **BLOCK)

    def _new_export(self, old: dict, path: str, name: str, **change) -> tuple[dict, dict]:
        """An incremental NEW_EXPORT of `name` in `path`, the runner's record at line 20."""
        return self._incremental(old, [{"file_path": path, "status": "MODIFIED", "exports_affected": [
            {"name": name, "change_type": "NEW_EXPORT", "old_line": None, "new_line": 20, **change}]}],
            [_runner_export(name, path, 20)])

    @staticmethod
    def _unresolved(named: str, count: int = 1) -> str:
        return (f"provenance: {count} new entr{'y' if count == 1 else 'ies'} took source_library @storybook/react, "
                f"the map's first, as the map names several libraries (@storybook/react, storybook) and each "
                f"entry's file or folder does not settle which: {named}; check each entry's source_library")

    def test_a_re_extracted_export_takes_its_files_library(self) -> None:
        records = {"mode": "gap-driven", "verification": [
            _verification("ANGULAR_JSON_PATH", "re-extracted", "NEW_EXPORT", new_location=f"{STORYBOOK_CLI}:9")],
            "files": [{"file_path": STORYBOOK_CLI, "exports": [
                {"name": "ANGULAR_JSON_PATH", "type": "constant", "location": f"{STORYBOOK_CLI}:9",
                 "confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "lexical_declaration"}]}]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=_storybook_map(), skill_name="storybook",
                                        records=records, test_report_run_id="r", **BLOCK)
        assert self._library(doc, "ANGULAR_JSON_PATH") == "storybook" and summary["warnings"] == []

    def test_an_entry_in_a_new_file_takes_its_folders_library(self) -> None:
        new = "code/core/src/cli/new.ts"
        records = {"mode": "gap-driven", "files": [], "verification": [
            _verification("scaffold", "verified", "NEW_EXPORT", source_citation={"file": new, "line": 4},
                          reachability="public")]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=_storybook_map(), skill_name="storybook",
                                        records=records, test_report_run_id="r", **BLOCK)
        assert self._library(doc, "scaffold") == "storybook" and summary["warnings"] == []

    def test_a_folder_naming_a_library_and_its_subpaths_gives_the_library(self) -> None:
        old = _storybook_map(_entry("expect", "code/core/src/test/expect.ts", 5, source_library="storybook/test"))
        doc, summary = self._incremental(old, [{"file_path": "code/core/src/preview.ts", "status": "ADDED"}],
                                         [_runner_export("definePreview", "code/core/src/preview.ts", 2)])
        assert self._library(doc, "definePreview") == "storybook" and summary["warnings"] == []

    def test_an_incremental_new_export_takes_its_files_library(self) -> None:
        doc, summary = self._new_export(_storybook_map(), STORYBOOK_CLI, "fn2")
        assert self._library(doc, "fn2") == "storybook" and summary["warnings"] == []

    def test_the_files_own_library_beats_an_unrelated_sibling_in_its_folder(self) -> None:
        old = _storybook_map(_entry("builder", "code/core/src/cli/angular/builder.ts", 2,
                                    source_library="@storybook/angular"))
        doc, summary = self._new_export(old, STORYBOOK_CLI, "fn2")
        assert self._library(doc, "fn2") == "storybook" and summary["warnings"] == []

    def test_a_files_own_entries_naming_a_library_and_its_subpath_give_the_library(self) -> None:
        # the folder also names an unrelated library, so only the file's own entries settle it
        expect = "code/core/src/test/expect.ts"
        old = _storybook_map(_entry("expect", expect, 5, source_library="storybook/test"),
                             _entry("spy", expect, 9, source_library="storybook"),
                             _entry("ngTest", "code/core/src/test/angular.ts", 1, source_library="@storybook/angular"))
        doc, summary = self._new_export(old, expect, "assertType")
        assert self._library(doc, "assertType") == "storybook" and summary["warnings"] == []

    def test_a_files_own_entries_naming_two_unrelated_libraries_give_the_first_with_a_warning(self) -> None:
        old = _storybook_map(_entry("docs", STORYBOOK_CLI, 30, source_library="@storybook/addon-docs"))
        doc, summary = self._new_export(old, STORYBOOK_CLI, "fn2")
        assert self._library(doc, "fn2") == "@storybook/react"
        assert summary["warnings"] == [
            "provenance: 1 new entry took source_library @storybook/react, the map's first, as the map names several "
            "libraries (@storybook/react, storybook, @storybook/addon-docs) and each entry's file or folder does not "
            f"settle which: fn2 in {STORYBOOK_CLI}; check each entry's source_library"]

    def test_a_file_whose_folder_names_several_libraries_gets_the_first_with_a_warning(self) -> None:
        doc, summary = self._incremental(_storybook_map(), [{"file_path": "code/new.ts", "status": "ADDED"}],
                                         [_runner_export("setup", "code/new.ts", 1)])
        assert self._library(doc, "setup") == "@storybook/react"
        assert summary["warnings"] == [self._unresolved("setup in code/new.ts")]

    def test_an_export_moved_from_another_file_tries_its_old_file(self) -> None:
        # code/ names both libraries, so the new file settles nothing; its old file's entries name storybook
        doc, summary = self._new_export(_storybook_map(), "code/moved.ts", "relocated", old_file=STORYBOOK_CLI)
        assert self._library(doc, "relocated") == "storybook" and summary["warnings"] == []

    @pytest.mark.parametrize("new_path, library", [
        ("code/legacy.ts", "storybook"),  # code/ names several libraries: the old path's entries settle it
        ("code/frameworks/angular/src/legacy.ts", "@storybook/angular"),  # the new path's folder settles it first
    ])
    def test_a_moved_files_new_export_tries_its_new_path_then_its_old(self, new_path: str, library: str) -> None:
        old_path = "code/core/src/legacy.ts"
        doc, summary = self._incremental(
            _storybook_map(_entry("legacy", old_path, 1, source_library="storybook"),
                           _entry("builder", "code/frameworks/angular/src/builder.ts", 2,
                                  source_library="@storybook/angular")),
            [{"file_path": new_path, "status": "MOVED", "old_path": old_path}],
            [_runner_export("legacy", new_path, 1), _runner_export("added", new_path, 9)])
        assert (self._library(doc, "legacy"), self._library(doc, "added")) == ("storybook", library)
        assert summary["warnings"] == []

    def test_a_docs_only_runs_new_export_takes_its_urls_library(self) -> None:
        react, core = "https://docs.example.com/react/api", "https://docs.example.com/core/api"
        old = {"entries": [
            {"export_name": "render", "source_library": "@storybook/react", "source_file": react, "confidence": "T3",
             "signature_source": "T3"},
            {"export_name": "fn", "source_library": "storybook", "source_file": core, "confidence": "T3",
             "signature_source": "T3"}]}
        records = {"mode": "docs-only", "changed_urls": [core], "exports": [
            {"name": "fn", "type": "function", "url": core}, {"name": "spyOn", "type": "function", "url": core}]}
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="storybook",
                                        records=records, test_report_run_id=None, **BLOCK)
        assert (self._library(doc, "fn"), self._library(doc, "spyOn")) == ("storybook", "storybook")
        assert summary["warnings"] == []

    def test_a_full_update_takes_the_same_rule(self) -> None:
        doc, summary = mod.apply_update(update_type="full", provenance=_storybook_map(), skill_name="storybook",
                                        extraction={"exports": [_runner_export("scaffold", "code/core/src/cli/new.ts",
                                                                               4)]},
                                        test_report_run_id=None, **BLOCK)
        assert self._library(doc, "scaffold") == "storybook" and summary["warnings"] == []

    def test_a_single_library_map_gives_its_library(self) -> None:
        doc, summary = mod.apply_update(
            update_type="incremental", provenance=_old_map(), skill_name="other",
            manifest={"total_export_changes": 1, "per_file": [{"file_path": "elsewhere/new.py", "status": "ADDED"}]},
            extraction={"exports": [_runner_export("brand_new", "elsewhere/new.py", 1)]}, test_report_run_id=None,
            **BLOCK)
        assert self._library(doc, "brand_new") == "lib" and summary["warnings"] == []

    def test_an_entry_with_no_file_takes_the_first_library_with_a_warning(self) -> None:
        records = {"mode": "gap-driven", "files": [], "verification": [
            _verification("Story", "unknown", "NEW_EXPORT", severity="Medium")]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=_storybook_map(), skill_name="storybook",
                                        records=records, merge_records={"exports": [
                                            {"export_name": "Story", "export_type": "type"}]},
                                        test_report_run_id="r", **BLOCK)
        assert self._library(doc, "Story") == "@storybook/react"
        assert summary["warnings"] == [self._unresolved("Story (no file)")]

    def test_the_warning_counts_every_entry_and_lists_the_first_ten(self) -> None:
        records = {"mode": "gap-driven", "files": [], "verification": [
            _verification(f"S{i}", "unknown", "NEW_EXPORT", severity="Low") for i in range(12)]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=_storybook_map(), skill_name="storybook",
                                        records=records, test_report_run_id="r", **BLOCK)
        named = ", ".join(f"S{i} (no file)" for i in range(10)) + ", and 2 more"
        assert summary["warnings"] == [self._unresolved(named, 12)]


# #802: an entry an older map carried without a signature_source takes the one its labels give


def _unsigned(name: str, line: int, path: str = "pkg/old.py", **labels) -> dict:
    entry = _entry(name, path, line, **labels)
    del entry["signature_source"]
    return entry


class TestBackfillSignatureSource:
    def test_the_tiers_are_the_ones_the_stats_helper_bins(self) -> None:
        assert {tier.upper() for tier in mod.SIGNATURE_SOURCES} == set(stats._SIG_MAP)

    def test_an_old_maps_entries_are_backfilled_so_the_stats_helper_bins_them(self) -> None:
        old = {"provenance_version": "2.0", "skill_name": "lib", "skill_type": "single", "entries": [
            _unsigned("matched", 1),
            _unsigned("by_eye", 2, confidence="T1-low", extraction_method="source-read", ast_node_type=None),
            {"export_name": "documented", "export_type": "function", "source_library": "lib",
             "source_file": "https://docs.example.com/api", "confidence": "T3", "extraction_method": "doc-fetch"},
            _unsigned("direct", 4, extraction_method="direct-read", ast_node_type=None),
            _entry("labelled", "pkg/old.py", 5)]}
        judgment = {"exports_public_api": 5, "exports_internal": 0}
        before = stats.coherence_compute(stats.derive_stats(old, judgment), old)
        assert "confidence_distribution" in [v["field"] for v in before["violations"]]
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        manifest={"total_export_changes": 0, "per_file": []},
                                        test_report_run_id=None, **BLOCK)
        assert [e["signature_source"] for e in doc["entries"]] == ["T1", "T1-low", "T3", "T1-low", "T1"]
        assert [{k: v for k, v in e.items() if k != "signature_source"} for e in doc["entries"][:4]] == \
            old["entries"][:4]
        assert doc["entries"][4] == old["entries"][4]
        assert summary["signature_source_backfilled"] == {"T1": 1, "T1-low": 2, "T3": 1}
        assert summary["entries"] == {"added": [], "updated": [], "removed": []}
        assert summary["warnings"] == [
            "provenance: backfilled signature_source on 4 entries that had none or an unrecognized value (a map "
            "written before the key existed), from each one's confidence and extraction_method: 1 T1, 2 T1-low, 1 T3"]
        after = stats.coherence_compute(stats.derive_stats(doc, judgment), doc)
        assert "confidence_distribution" not in [v["field"] for v in after["violations"]]

    @pytest.mark.parametrize("method, confidence, expected", [
        ("ast-grep", "T1", "T1"),
        ("ast_bridge", "T1", "T1"),
        (" AST-Grep ", "T1", "T1"),  # the method compared stripped and case-insensitively
        ("ast-grep", "T1-low", "T1-low"),  # a confidence below T1 wins over the method
        ("AST_BRIDGE", "t2", "T2"),
        ("source-read", "T1", "T1-low"),  # T1 needs an ast-grep match
        ("source_reading", "T3", "T3"),
        ("direct-read", "T1", "T1-low"),
        ("doc-fetch", "T3", "T3"),
        (None, None, "T1-low"),
    ])
    def test_each_entry_takes_its_confidence_else_its_methods_tier(self, method, confidence, expected) -> None:
        entry = {k: v for k, v in _unsigned("e", 1).items() if k not in ("confidence", "extraction_method")}
        entry.update({k: v for k, v in (("confidence", confidence), ("extraction_method", method)) if v is not None})
        doc, summary = mod.apply_update(update_type="incremental", provenance={"entries": [entry]}, skill_name="lib",
                                        test_report_run_id=None, **BLOCK)
        assert doc["entries"][0]["signature_source"] == expected
        assert summary["signature_source_backfilled"] == {expected: 1}

    def test_a_recognized_value_in_any_case_stays_and_an_unrecognized_one_is_listed(self) -> None:
        old = {"entries": [
            _entry("lower", "pkg/a.py", 1, confidence="T1-low", extraction_method="source-read", ast_node_type=None,
                   signature_source="t1-low"),
            _entry("odd", "pkg/a.py", 2, signature_source="high"),
            _entry("numbered", "pkg/a.py", 3, signature_source=1),
            _unsigned("annotated", 4, confidence="t2", extraction_method="source_reading", ast_node_type=None),
            _unsigned("claimed", 5, extraction_method="source-read", ast_node_type=None)]}
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        test_report_run_id=None, **BLOCK)
        assert [e["signature_source"] for e in doc["entries"]] == ["t1-low", "T1", "T1", "T2", "T1-low"]
        assert summary["signature_source_backfilled"] == {"T1": 2, "T1-low": 1, "T2": 1}
        assert summary["warnings"] == [
            "provenance: backfilled signature_source on 4 entries that had none or an unrecognized value (a map "
            "written before the key existed), from each one's confidence and extraction_method: 2 T1, 1 T1-low, "
            "1 T2; unrecognized values replaced: odd: high -> T1, numbered: 1 -> T1"]

    def test_a_moved_export_whose_signature_the_runner_did_not_give_takes_t1_low(self) -> None:
        # the runner matched the export at its new line but gave no params, so the entry keeps the params it held,
        # and its new ast-grep labels say nothing of them: no T1 is derived from them
        old = {"entries": [_unsigned("shifted", 30, "pkg/a.py", params=["x"], confidence="T1-low",
                                     extraction_method="source-read", ast_node_type=None)]}
        manifest = {"total_export_changes": 1, "per_file": [{"file_path": "pkg/a.py", "status": "MODIFIED",
                                                             "exports_affected": [
            {"name": "shifted", "change_type": "MOVED_EXPORT", "old_line": 30, "new_line": 33}]}]}
        extraction = {"exports": [_runner_export("shifted", "pkg/a.py", 33)]}
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib", manifest=manifest,
                                        extraction=extraction, test_report_run_id=None, **BLOCK)
        [entry] = doc["entries"]
        assert (entry["source_line"], entry["params"], entry["extraction_method"], entry["signature_source"]) == \
            (33, ["x"], "ast-grep", "T1-low")
        assert (summary["signature_source_backfilled"], summary["entries"]["updated"]) == ({}, ["shifted"])

    def test_a_map_with_every_signature_source_backfills_nothing(self) -> None:
        doc, summary = mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                                        test_report_run_id=None, **BLOCK)
        assert (summary["signature_source_backfilled"], summary["warnings"]) == ({}, [])
        assert doc["entries"] == _old_map()["entries"]


# --------------------------------------------------------------------------
# Category C and a docs-only manifest from the helpers' files, never retyped
# --------------------------------------------------------------------------


class TestCategoryCFiles:
    def _files(self, tmp_path: Path) -> list[str]:
        (tmp_path / "category-a.json").write_bytes(json.dumps(CLASSIFY).encode("utf-8"))
        (tmp_path / "category-b-diff.json").write_bytes(json.dumps(DIFF).encode("utf-8"))
        # the rules paired the old.py export with its rename; the CCC check paired gone.py with renamed.py
        (tmp_path / "category-c.json").write_bytes(json.dumps({
            "category_c": {"renamed_files": [], "renamed_exports": [
                {"old_name": "old_fn", "new_name": "new_fn", "file": "pkg/api.py"}]},
            "evidence": {}, "unpaired": {}}).encode("utf-8"))
        (tmp_path / "ccc-pairs.json").write_bytes(json.dumps({
            "renamed_files": [{"old_path": "pkg/gone.py", "new_path": "pkg/renamed.py"}]}).encode("utf-8"))
        (tmp_path / "categories.json").write_bytes(json.dumps({"category_d": {}, "update_mode": "normal"}).encode())
        return ["--input", str(tmp_path / "categories.json"), "--category-a", str(tmp_path / "category-a.json"),
                "--category-b-diff", str(tmp_path / "category-b-diff.json"),
                "--category-c", str(tmp_path / "category-c.json"), "--ccc-pairs", str(tmp_path / "ccc-pairs.json")]

    def test_build_and_deletion_ratio_read_both_files(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        build = _run_cli("build", *files)
        assert build.returncode == 0, build.stderr
        manifest = json.loads(build.stdout)
        # the moved file, the CCC pair and the renamed export, each taken out of the lists it was found in
        assert (manifest["counts"]["files_moved"], manifest["counts"]["exports_renamed"]) == (2, 1)
        assert (manifest["counts"]["files_deleted"], manifest["counts"]["files_added"]) == (1, 1)
        assert manifest["counts"]["exports_deleted"] == 1 and manifest["counts"]["exports_new"] == 1
        prov = tmp_path / "prov.json"
        prov.write_bytes(json.dumps({"entries": [{"export_name": "x", "source_file": "pkg/gone.py"},
                                                 {"export_name": "y", "source_file": "pkg/old.py"},
                                                 {"export_name": "old_fn", "source_file": "pkg/api.py"},
                                                 {"export_name": "gone", "source_file": "pkg/api.py"}]}).encode())
        ratio = _run_cli("deletion-ratio", "--provenance-map", str(prov), *files)
        assert ratio.returncode == 0, ratio.stderr
        out = json.loads(ratio.stdout)
        # old.py's export and `gone` are lost; gone.py and old_fn were renamed, so neither counts as deleted
        # (renamed or moved: the two file pairs, the diff's two moved exports and the renamed export)
        assert (out["deleted_export_count"], out["renamed_or_moved_count"]) == (2, 5)

    def test_the_file_replaces_the_inputs_own_category_c(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        (tmp_path / "categories.json").write_bytes(json.dumps({"category_c": {"renamed_files": [
            {"old_path": "pkg/old.py", "new_path": "pkg/new.py"}]}}).encode("utf-8"))
        manifest = json.loads(_run_cli("build", *files).stdout)
        assert manifest["counts"]["files_moved"] == 2  # moved_files and the CCC pair, not the input's own

    def test_apply_takes_the_renamed_exports_from_the_file(self, tmp_path: Path) -> None:
        files = self._files(tmp_path)
        categories = mod._apply_categories(mod._build_parser().parse_args([
            "apply", "--update-type", "incremental", "--skill-name", "lib", "--generation-date", "d",
            "--confidence-tier", "Forge", "--manual-sections-preserved", "0", "-o", "x", *files[:2], *files[6:]]))
        assert categories["category_d"] == {}
        assert categories["category_c"]["renamed_exports"][0]["new_name"] == "new_fn"
        assert categories["category_c"]["renamed_files"] == [{"old_path": "pkg/gone.py", "new_path": "pkg/renamed.py"}]

    @pytest.mark.parametrize(("name", "content"), [("category-c.json", b'{"unpaired": {}}'),
                                                   ("ccc-pairs.json", b"[]")],
                             ids=["c-not-rename-candidates", "pairs-not-an-object"])
    def test_a_file_that_is_not_the_output_it_names_exits_1(self, tmp_path: Path, name: str,
                                                              content: bytes) -> None:
        files = self._files(tmp_path)
        (tmp_path / name).write_bytes(content)
        result = _run_cli("build", *files)
        assert result.returncode == 1 and result.stderr.startswith("error: ")


class TestDocsOnlyManifest:
    COMPARISON = {"changed": [{"url": "https://d/b", "old_hash": "sha256:1", "new_hash": "sha256:2"},
                              {"url": "https://d/a", "old_hash": "sha256:3", "new_hash": "sha256:4"}],
                  "unchanged": [{"url": "https://d/c"}],
                  "fetch_failed": [{"url": "https://d/e", "old_hash": "sha256:5", "reason": "HTTP 404"}],
                  "skipped_null_hash": [], "stats": {"total_tracked": 4}}

    def test_build_writes_the_manifest_from_the_comparison(self, tmp_path: Path) -> None:
        path = tmp_path / "doc-hashes.json"
        path.write_bytes(json.dumps(self.COMPARISON).encode("utf-8"))
        result = _run_cli("build", "--doc-hashes", str(path))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            "mode": "docs-only", "no_changes": False, "changed_urls": ["https://d/b", "https://d/a"],
            "fetch_failed": ["https://d/e"], "counts": {"docs_changed": 2, "docs_fetch_failed": 1}}

    def test_no_changed_document_is_no_change(self) -> None:
        manifest = mod.docs_only_manifest({**self.COMPARISON, "changed": []})
        assert manifest["no_changes"] is True and manifest["changed_urls"] == []

    def test_doc_hashes_takes_no_other_input(self, tmp_path: Path) -> None:
        path = tmp_path / "doc-hashes.json"
        path.write_bytes(json.dumps(self.COMPARISON).encode("utf-8"))
        result = _run_cli("build", "--doc-hashes", str(path), "--input", str(path))
        assert result.returncode == 1 and "takes no other input" in result.stderr
        path.write_bytes(b'{"stats": {}}')
        assert _run_cli("build", "--doc-hashes", str(path)).returncode == 1  # not compare-hashes output


# --------------------------------------------------------------------------
# records: step 3's re-extraction records, seeded by script (step 5b determinism-3)
# --------------------------------------------------------------------------


INVENTORY_PATH = REPO_ROOT / "src" / "shared" / "scripts" / "skf-extraction-inventory.py"
_inventory_spec = importlib.util.spec_from_file_location("skf_extraction_inventory_records", INVENTORY_PATH)
inventory = importlib.util.module_from_spec(_inventory_spec)
_inventory_spec.loader.exec_module(inventory)


def _runner(name: str, path: str, line: int, *, params=None, return_type=None, language="python",
            export_type="function", node="function_definition") -> dict:
    """One export as the recipe runner records it."""
    return {"export_name": name, "source_file": path, "source_line": line, "signature": f"def {name}():",
            "params": params, "return_type": return_type, "ast_recipe": f"{language}-def", "ast_node_type": node,
            "export_type": export_type, "language": language, "confidence": "T1", "extraction_method": "ast-grep"}


RUNNER_PARAMS = [{"name": "q", "type": "str", "default": None, "optional": False},
                 {"name": "limit", "type": "int", "default": "10", "optional": True},
                 {"name": "*rest", "type": None, "default": None, "optional": True}]


class TestRecords:
    def _inputs(self) -> tuple[dict, dict]:
        extraction = {"exports": [
            _runner("search", "pkg/api.py", 5, params=RUNNER_PARAMS, return_type="list"),
            _runner("Client", "pkg/api.py", 20, export_type="class", node="class_definition"),
            _runner("fetch", "src/a.ts", 3, language="typescript", node="function_declaration",
                    params=[{"name": "url", "type": "string", "default": None, "optional": True}])]}
        details = {"exports": [
            {"export_name": "fetch", "source_file": "src/a.ts", "return_type": "Promise<Response>"},
            {"export_name": "by_eye", "export_type": "constant", "source_file": "pkg/api.py", "source_line": 40,
             "params": None, "return_type": None, "confidence": "T1-low", "extraction_method": "source-read"}]}
        return extraction, details

    def test_the_runner_and_step_2_seed_every_record(self) -> None:
        extraction, details = self._inputs()
        records, summary = mod.build_records(extraction, details, ["pkg/api.py", "src/a.ts", "pkg/empty.py"], [])
        assert records["mode"] == "normal"
        assert [b["file_path"] for b in records["files"]] == ["pkg/api.py", "src/a.ts", "pkg/empty.py"]
        by_key = {(r["name"], b["file_path"]): r for b in records["files"] for r in b["exports"]}
        search = by_key[("search", "pkg/api.py")]
        # every runner-owned field, the params in the map's typed form, as create-skill writes them
        assert search == {"name": "search", "type": "function", "signature": "def search():",
                          "location": "pkg/api.py:5", "params": ["q: str", "limit: int = 10", "*rest"],
                          "return_type": "list", "confidence": "T1", "extraction_method": "ast-grep",
                          "ast_node_type": "function_definition", "ast_recipe": "python-def"}
        assert search["params"] == [inventory.typed_param(p, "python") for p in RUNNER_PARAMS]
        # a JS/TS optional parameter keeps its `?`, and step 2 fills what the runner left null
        assert (by_key[("fetch", "src/a.ts")]["params"], by_key[("fetch", "src/a.ts")]["return_type"]) == \
            (["url?: string"], "Promise<Response>")
        # an export only step 2 read is T1-low, source-read, with no node kind or recipe
        by_eye = by_key[("by_eye", "pkg/api.py")]
        assert (by_eye["confidence"], by_eye["extraction_method"], by_eye["ast_node_type"], by_eye["ast_recipe"],
                by_eye["location"]) == ("T1-low", "source-read", None, None, "pkg/api.py:40")
        assert summary == {"files_extracted": 3, "exports_extracted": 4,
                           "confidence_breakdown": {"T1": 3, "T1-low": 1, "T2": 0}, "marked_not_public": 0,
                           "warnings": []}

    def test_patches_add_only_what_no_tool_recorded(self) -> None:
        extraction, details = self._inputs()
        patches = [
            {"file_path": "pkg/api.py", "exports": [
                {"name": "search", "docstring": "Search.", "params": ["typed: by-hand"], "return_type": "str"},
                {"name": "Client", "signature": "class Client(Base):", "members": ["get()"],
                 "params": ["x"], "return_type": None},
                {"name": "ghost", "docstring": "invented"}]},
            {"file_path": "./src/a.ts", "exports": [{"name": "fetch", "qmd_evidence": "used widely"}]}]
        records, summary = mod.build_records(extraction, details, None, patches)
        by_key = {(r["name"], b["file_path"]): r for b in records["files"] for r in b["exports"]}
        search = by_key[("search", "pkg/api.py")]
        # the runner's params and return type stand; the docstring is the worker's
        assert (search["params"], search["return_type"], search["docstring"]) == \
            (["q: str", "limit: int = 10", "*rest"], "list", "Search.")
        client = by_key[("Client", "pkg/api.py")]
        assert (client["signature"], client["members"], client["params"]) == ("class Client(Base):", ["get()"], ["x"])
        assert by_key[("fetch", "src/a.ts")]["qmd_evidence"] == "used widely"
        assert ("ghost", "pkg/api.py") not in by_key
        assert summary["warnings"] == ["re-extract: a patch names ghost in pkg/api.py, which neither the runner nor "
                                       "step 2 recorded; not added"]
        assert summary["confidence_breakdown"]["T2"] == 1

    def test_a_renamed_reexport_gives_its_public_name_to_the_record(self) -> None:
        """#807: the runner names a record after its declaration; the entry-point diff's `local` pairs it with the
        public name a re-export gives it in that file, which the record carries in `aliases`."""
        extraction = {"exports": [
            _runner("MockUniversalStore", "store/mock.ts", 3, language="typescript", export_type="class",
                    node="class_declaration"),
            _runner("Channel", "./channel/index.ts", 7, language="typescript", export_type="class",
                    node="class_declaration"),
            _runner("plain", "store/mock.ts", 9, language="typescript", node="function_declaration")],
            "entry_point_diff": {"public": [
                {"name": "experimental_MockUniversalStore", "local": "MockUniversalStore", "file": "store/mock.ts",
                 "via": "re-export"},
                # a second public name for one declaration, once each, sorted
                {"name": "MockStore", "local": "MockUniversalStore", "file": "./store/mock.ts", "via": "re-export"},
                {"name": "MockStore", "local": "MockUniversalStore", "file": "store/mock.ts", "via": "re-export"},
                # a namespace's members rename too
                {"name": "channels", "local": None, "file": "channel/index.ts", "via": "namespace", "members": [
                    {"name": "UniversalChannel", "local": "Channel", "file": "channel/index.ts", "line": 7}]},
                # no rename, and a rename of a name the runner did not record there
                {"name": "plain", "local": None, "file": "store/mock.ts", "via": "re-export"},
                {"name": "Other", "local": "plain", "file": "store/other.ts", "via": "re-export"}]}}
        records, summary = mod.build_records(extraction, None, None, [])
        by_key = {(r["name"], b["file_path"]): r for b in records["files"] for r in b["exports"]}
        assert by_key[("MockUniversalStore", "store/mock.ts")]["aliases"] == \
            ["MockStore", "experimental_MockUniversalStore"]
        assert by_key[("Channel", "channel/index.ts")]["aliases"] == ["UniversalChannel"]
        assert "aliases" not in by_key[("plain", "store/mock.ts")]
        assert summary["exports_extracted"] == 3 and summary["warnings"] == []

    def test_an_aliased_other_definition_gives_its_public_name_to_the_record(self) -> None:
        """#830: react's root entry point re-exports `composeReact as composeStories`, an other definition of a name
        core's entry point holds: react's record carries the public name in `aliases`, as a public row's does."""
        extraction = {"exports": [
            _runner("composeStories", "core/portable.ts", 1, language="typescript"),
            _runner("composeReact", "react/portable.ts", 4, language="typescript")],
            "entry_point_diff": {
                "public": [{"name": "composeStories", "local": None, "file": "core/portable.ts", "via": "re-export"}],
                "other_definitions": [{"name": "composeStories", "local": "composeReact", "file": "react/portable.ts",
                                       "via": "re-export", "language": "javascript"}]}}
        records, _ = mod.build_records(extraction, None, None, [])
        by_key = {(r["name"], b["file_path"]): r for b in records["files"] for r in b["exports"]}
        assert by_key[("composeReact", "react/portable.ts")]["aliases"] == ["composeStories"]
        assert "aliases" not in by_key[("composeStories", "core/portable.ts")]

    def test_apply_writes_the_records_into_the_map(self) -> None:
        """The records reach the map through apply, with the labels the stats helper accepts."""
        extraction, details = self._inputs()
        records, _ = mod.build_records(extraction, details, ["pkg/api.py"], [])
        manifest = {"total_export_changes": 1, "per_file": [
            {"file_path": "pkg/api.py", "status": "ADDED", "exports_affected": []}]}
        doc, _ = mod.apply_update(update_type="incremental", provenance={"entries": []}, skill_name="lib",
                                  manifest=manifest, records=records, test_report_run_id=None, **BLOCK)
        entries = {e["export_name"]: e for e in doc["entries"]}
        assert entries["search"]["params"] == ["q: str", "limit: int = 10", "*rest"]
        assert (entries["by_eye"]["signature_source"], entries["search"]["signature_source"]) == ("T1-low", "T1")
        assert stats.check_label_agreement(doc) == []

    def test_the_cli_writes_the_records_and_prints_the_counts(self, tmp_path: Path) -> None:
        extraction, details = self._inputs()
        (tmp_path / "extraction.json").write_bytes(json.dumps(extraction).encode("utf-8"))
        (tmp_path / "export-details.json").write_bytes(json.dumps(details).encode("utf-8"))
        (tmp_path / "extract-files.json").write_bytes(json.dumps(["pkg/api.py", "src/a.ts"]).encode("utf-8"))
        patches = tmp_path / "reextract-patches"
        patches.mkdir()
        (patches / "b.json").write_bytes(json.dumps(
            [{"file_path": "src/a.ts", "exports": [{"name": "fetch", "docstring": "Fetch."}]}]).encode("utf-8"))
        (patches / "a.json").write_bytes(json.dumps(
            {"file_path": "pkg/api.py", "exports": [{"name": "search", "docstring": "Search."}]}).encode("utf-8"))
        out = tmp_path / "reextract-records.json"
        result = _run_cli("records", "--extraction", str(tmp_path / "extraction.json"),
                          "--export-details", str(tmp_path / "export-details.json"),
                          "--files-from", str(tmp_path / "extract-files.json"), "--patches", str(patches),
                          "-o", str(out))
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert (summary["status"], summary["files_extracted"], summary["exports_extracted"]) == ("written", 2, 4)
        assert summary["confidence_breakdown"] == {"T1": 3, "T1-low": 1, "T2": 0}
        docstrings = {r["name"]: r.get("docstring") for b in json.loads(out.read_bytes())["files"] for r in b["exports"]}
        assert (docstrings["search"], docstrings["fetch"]) == ("Search.", "Fetch.")

    @pytest.mark.parametrize("name, content", [
        ("extraction.json", b'{"no": "exports"}'),
        ("extract-files.json", b'{"not": "a list"}'),
        ("patch", b'{"exports": []}'),
    ], ids=["extraction-not-runner-output", "files-not-a-list", "patch-without-file-path"])
    def test_an_input_that_is_not_what_it_names_exits_1(self, tmp_path: Path, name: str, content: bytes) -> None:
        (tmp_path / "extraction.json").write_bytes(b'{"exports": []}')
        (tmp_path / "extract-files.json").write_bytes(b"[]")
        patches = tmp_path / "patches"
        patches.mkdir()
        target = patches / "p.json" if name == "patch" else tmp_path / name
        target.write_bytes(content)
        result = _run_cli("records", "--extraction", str(tmp_path / "extraction.json"),
                          "--files-from", str(tmp_path / "extract-files.json"), "--patches", str(patches),
                          "-o", str(tmp_path / "out.json"))
        assert result.returncode == 1 and result.stderr.startswith("error: ")
        assert not (tmp_path / "out.json").exists()


# --------------------------------------------------------------------------
# a public-api skill's public surface (#685) and a moved export's labels and file (#686)
# --------------------------------------------------------------------------


def _public_api_run(exports: list, public: list, gaps: tuple = (), *, scope_type: str = "public-api",
                    status: str = "barrel") -> dict:
    """The recipe runner's output, the parts records and apply read: its scope type, exports, entry-point statuses
    and entry-point diff, all of one Python package."""
    return {"scope": {"type": scope_type}, "exports": exports,
            "entry_points": {"status": status, "by_language": {"python": status}},
            "entry_point_diff": {"public": [{"language": "python", "local": None, **p} for p in public],
                                 "internal": [], "extraction_gaps": [{"language": "python", **g} for g in gaps],
                                 "outside_scope": []}}


def _break_surface(extraction: dict, change: str) -> None:
    """A run whose public surface the rule cannot take, or no public-api run at all."""
    if change == "no-scope-type":
        extraction["scope"] = {"type": None}
    if change == "no-entry-point-diff":
        extraction["entry_point_diff"] = None  # no ast-grep, or Quick tier: the runner diffed nothing
    if change == "incomplete":
        extraction["status"] = "incomplete"
    if change == "errors":
        extraction["errors"] = [{"reason": "ast-grep-timeout", "files": 1, "first_file": COGNIFY, "detail": "x"}]
    if change == "unresolved":
        extraction["entry_points"]["unresolved"] = [{"entry": "cognee/__init__.py", "name": "x", "from": ".gone",
                                                     "file": "cognee/__init__.py"}]


COGNIFY = "cognee/api/v1/cognify/cognify.py"
# cognee's shape as the runner records it (#703): `from .api.v1.cognify import cognify` is the function
# cognify/__init__.py binds, at the file that defines it; `delete` is defined in its package's __init__.py beside an
# empty delete.py; `tools` is a submodule, a namespace whose member is the function its package re-exports from
# tools.py; `visualize` renames `visualize_graph`
SURFACE = [
    {"name": "cognify", "via": "re-export", "file": COGNIFY, "line": 44},
    {"name": "delete", "via": "re-export", "file": "cognee/api/v1/delete/__init__.py", "line": 11},
    {"name": "tools", "via": "namespace", "file": "cognee/api/v1/tools/__init__.py", "line": None,
     "members": [{"name": "list_tools", "local": None, "file": "cognee/api/v1/tools/tools.py", "line": 1}]},
    {"name": "visualize", "via": "re-export", "local": "visualize_graph",
     "file": "cognee/api/v1/visualize/visualize.py", "line": 3},
    {"name": "search", "via": "re-export", "file": "pkg/a.py", "line": 11},
]


class TestPublicSurface:
    def test_records_marks_each_export_of_a_barrel_family(self) -> None:
        extraction = _public_api_run([
            _runner("cognify", COGNIFY, 44), _runner("get_default_tasks", COGNIFY, 20),
            _runner("delete", "cognee/api/v1/delete/__init__.py", 11),
            _runner("visualize_graph", "cognee/api/v1/visualize/visualize.py", 3),
            _runner("list_tools", "cognee/api/v1/tools/tools.py", 1),
            _runner("fetch", "web/a.ts", 1, language="typescript", node="function_declaration"),
        ], SURFACE, gaps=({"name": "Drop", "entry": "cognee/__init__.py", "file": "cognee/pipelines/types.py",
                           "line": 32},))
        # read by eye: the runner's own gap, and the tools module itself, which its members stand for
        details = {"exports": [
            {"export_name": "Drop", "export_type": "sentinel", "source_file": "cognee/pipelines/types.py",
             "source_line": 32, "confidence": "T1-low", "extraction_method": "source-read"},
            {"export_name": "tools", "export_type": "module", "source_file": "cognee/api/v1/tools/tools.py",
             "source_line": 1, "confidence": "T1-low", "extraction_method": "source-read"}]}
        records, summary = mod.build_records(extraction, details, None, [])
        assert summary["marked_not_public"] == 2
        marks = {(r["name"], b["file_path"]): r.get("public") for b in records["files"] for r in b["exports"]}
        assert marks == {
            ("cognify", COGNIFY): True, ("get_default_tasks", COGNIFY): False,
            ("delete", "cognee/api/v1/delete/__init__.py"): True,
            ("visualize_graph", "cognee/api/v1/visualize/visualize.py"): True,
            ("list_tools", "cognee/api/v1/tools/tools.py"): True,  # `cognee.tools.list_tools`
            ("tools", "cognee/api/v1/tools/tools.py"): False, ("Drop", "cognee/pipelines/types.py"): True,
            ("fetch", "web/a.ts"): None,  # the JavaScript family has no barrel here: no mark
        }

    @pytest.mark.parametrize("change", ["full-library", "no-scope-type", "no-entry-point-diff", "no-barrel",
                                        "incomplete", "errors", "unresolved"])
    def test_records_marks_nothing_outside_a_public_api_barrel(self, change: str) -> None:
        extraction = _public_api_run([_runner("cognify", COGNIFY, 44), _runner("get_default_tasks", COGNIFY, 20)],
                                     SURFACE, scope_type="full-library" if change == "full-library" else "public-api",
                                     status="no-entry-point" if change == "no-barrel" else "barrel")
        _break_surface(extraction, change)
        records, summary = mod.build_records(extraction, None, None, [])
        assert all("public" not in r for b in records["files"] for r in b["exports"])
        assert summary["marked_not_public"] == 0 and summary["warnings"] == []  # apply gives the one warning

    def _inputs(self, scope_type: str = "public-api") -> tuple[dict, dict]:
        """A map whose `old_helper` is an internal entry create-skill kept, a modified file with a public and an
        internal change, an ADDED file with a public and an internal export, and a MOVED file."""
        old = {"entries": [_entry("search", "pkg/a.py", 10), _entry("old_helper", "pkg/a.py", 20),
                           _entry("carried", "pkg/old_home.py", 4, notes="kept")]}
        extraction = _public_api_run([
            _runner("search", "pkg/a.py", 11), _runner("old_helper", "pkg/a.py", 22), _runner("helper", "pkg/a.py", 50),
            _runner("cognify", COGNIFY, 44), _runner("get_default_tasks", COGNIFY, 20),
            _runner("carried", "pkg/new_home.py", 4), _runner("moved_internal", "pkg/new_home.py", 9),
        ], SURFACE, scope_type=scope_type)
        manifest = {"total_export_changes": 3, "per_file": [
            {"file_path": "pkg/a.py", "status": "MODIFIED", "exports_affected": [
                {"name": "search", "change_type": "MODIFIED_EXPORT", "old_line": 10, "new_line": 11},
                {"name": "old_helper", "change_type": "MODIFIED_EXPORT", "old_line": 20, "new_line": 22},
                {"name": "helper", "change_type": "NEW_EXPORT", "old_line": None, "new_line": 50}]},
            {"file_path": COGNIFY, "status": "ADDED", "exports_affected": []},
            {"file_path": "pkg/new_home.py", "status": "MOVED", "old_path": "pkg/old_home.py",
             "exports_affected": []}]}
        records, _ = mod.build_records(extraction, None, ["pkg/a.py", COGNIFY, "pkg/new_home.py"], [])
        return old, {"manifest": manifest, "extraction": extraction, "records": records}

    def test_a_public_api_skill_adds_only_its_public_names(self) -> None:
        old, inputs = self._inputs()
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        test_report_run_id=None, **inputs, **BLOCK)
        entries = {(e["export_name"], e["source_file"]): e for e in doc["entries"]}
        # the public add and the modified public export land; the existing internal entry is still updated, and
        # the MOVED file's carried entry moves with its keys
        assert ("cognify", COGNIFY) in entries and entries[("search", "pkg/a.py")]["source_line"] == 11
        assert entries[("old_helper", "pkg/a.py")]["source_line"] == 22
        assert entries[("carried", "pkg/new_home.py")]["notes"] == "kept"
        # the internal NEW_EXPORT, the ADDED file's internal export and the MOVED file's new internal name: in the
        # summary list only, with one warning for them all
        assert set(entries) == {("search", "pkg/a.py"), ("old_helper", "pkg/a.py"), ("cognify", COGNIFY),
                                ("carried", "pkg/new_home.py")}
        assert summary["entries"]["added"] == ["cognify", "carried"]
        assert summary["not_public"] == [{"name": "helper", "file": "pkg/a.py"},
                                         {"name": "get_default_tasks", "file": COGNIFY},
                                         {"name": "moved_internal", "file": "pkg/new_home.py"}]
        assert summary["warnings"] == [
            "provenance: 3 new export(s) off the public surface of this public-api skill not added (the summary's "
            "not_public lists each with its file): helper, get_default_tasks, moved_internal"]
        assert stats.check_label_agreement(doc) == []

    def test_another_scope_type_adds_every_name_as_before(self) -> None:
        old, inputs = self._inputs("full-library")
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        test_report_run_id=None, **inputs, **BLOCK)
        assert summary["entries"]["added"] == ["helper", "cognify", "get_default_tasks", "carried", "moved_internal"]
        assert summary["not_public"] == [] and summary["warnings"] == []
        assert len(doc["entries"]) == 7

    def test_apply_reads_the_rule_from_the_extraction_when_no_record_marks_the_name(self) -> None:
        # --reextract-records left out, or written by an older `records`: apply reads extraction.json's scope type
        old, inputs = self._inputs()
        inputs["records"] = {"mode": "normal", "files": []}
        _doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                         test_report_run_id=None, **inputs, **BLOCK)
        assert [item["name"] for item in summary["not_public"]] == ["helper", "get_default_tasks", "moved_internal"]

    def test_the_mark_records_wrote_is_followed(self) -> None:
        old, inputs = self._inputs()
        for block in inputs["records"]["files"]:
            for record in block["exports"]:
                if record["name"] == "helper":
                    record["public"] = True  # whatever the extraction says, apply follows the records
        _doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                         test_report_run_id=None, **inputs, **BLOCK)
        assert "helper" in summary["entries"]["added"]
        assert "helper" not in [item["name"] for item in summary["not_public"]]

    @pytest.mark.parametrize("change", ["no-entry-point-diff", "incomplete", "errors", "unresolved"])
    def test_a_surface_the_rule_cannot_read_adds_every_name_with_one_warning(self, change: str) -> None:
        # Quick tier or a failed runner (detect-changes writes the scope type with no exports diff), an incomplete
        # run, one with errors, or an entry point the trace could not follow: the surface is not the whole one
        old, inputs = self._inputs()
        _break_surface(inputs["extraction"], change)
        inputs["records"], _ = mod.build_records(inputs["extraction"], None, ["pkg/a.py", COGNIFY,
                                                                             "pkg/new_home.py"], [])
        _doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                         test_report_run_id=None, **inputs, **BLOCK)
        assert summary["entries"]["added"] == ["helper", "cognify", "get_default_tasks", "carried", "moved_internal"]
        assert summary["not_public"] == []
        [warning] = summary["warnings"]
        assert warning.startswith("provenance: the public surface of this public-api skill could not be applied (")
        assert warning.endswith("): every new export was added")

    def test_a_quick_tier_extraction_names_the_scope_type_only(self) -> None:
        old, inputs = self._inputs()
        inputs["extraction"] = {"exports": [], "scope": {"type": "public-api"}}  # detect-changes' fallback file
        for block in inputs["records"]["files"]:  # step 2's by-eye records, which `records` marks nothing in
            for record in block["exports"]:
                record.pop("public", None)
        _doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                         test_report_run_id=None, **inputs, **BLOCK)
        assert summary["not_public"] == []
        assert summary["warnings"] == [
            "provenance: the public surface of this public-api skill could not be applied (the recipe runner gave "
            "no entry-point diff (Quick tier, or a run that could not read the tree)): every new export was added"]

    @pytest.mark.parametrize("where", ["deleted-export", "deleted-file"])
    def test_a_name_this_run_removes_comes_back_whatever_its_mark(self, where: str) -> None:
        """A held export that moves into an ADDED file reads as removed there and new here: it is re-added, though
        the surface does not name it, so no export the map held is lost."""
        old_file = "pkg/a.py" if where == "deleted-export" else "pkg/gone.py"
        old = {"entries": [_entry("relocated", old_file, 7, notes="n")]}
        removal = ({"file_path": "pkg/a.py", "status": "MODIFIED", "exports_affected": [
            {"name": "relocated", "change_type": "DELETED_EXPORT", "old_line": 7, "new_line": None}]}
            if where == "deleted-export" else {"file_path": "pkg/gone.py", "status": "DELETED", "exports_affected": []})
        # a DELETED file comes after the ADDED one in the manifest's order
        manifest = {"total_export_changes": 1, "per_file": [
            {"file_path": "pkg/c.py", "status": "ADDED", "exports_affected": []}, removal]}
        extraction = _public_api_run([_runner("relocated", "pkg/c.py", 2), _runner("fresh", "pkg/c.py", 9)], SURFACE)
        records, _ = mod.build_records(extraction, None, ["pkg/c.py"], [])
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        manifest=manifest, extraction=extraction, records=records,
                                        test_report_run_id=None, **BLOCK)
        assert [(e["export_name"], e["source_file"]) for e in doc["entries"]] == [("relocated", "pkg/c.py")]
        assert summary["not_public"] == [{"name": "fresh", "file": "pkg/c.py"}]

    def test_the_warning_names_ten_and_the_summary_lists_all(self) -> None:
        names = [f"internal_{i:02d}" for i in range(12)]
        extraction = _public_api_run([_runner(n, "pkg/c.py", i + 1) for i, n in enumerate(names)], SURFACE)
        manifest = {"total_export_changes": 0, "per_file": [{"file_path": "pkg/c.py", "status": "ADDED",
                                                             "exports_affected": []}]}
        _doc, summary = mod.apply_update(update_type="incremental", provenance={"entries": []}, skill_name="lib",
                                         manifest=manifest, extraction=extraction, test_report_run_id=None, **BLOCK)
        assert [item["name"] for item in summary["not_public"]] == names
        assert summary["warnings"] == [
            "provenance: 12 new export(s) off the public surface of this public-api skill not added (the summary's "
            f"not_public lists each with its file): {', '.join(names[:10])} and 2 more"]

    def test_apply_writes_the_not_public_list_to_the_run_folder(self, tmp_path: Path) -> None:
        old, inputs = self._inputs()
        paths = {}
        for key, value in (("map", old), ("manifest", inputs["manifest"]), ("extraction", inputs["extraction"]),
                           ("records", inputs["records"])):
            paths[key] = tmp_path / f"{key}.json"
            paths[key].write_bytes(json.dumps(value).encode("utf-8"))
        out, listed = tmp_path / "new-map.json", tmp_path / "not-public.json"
        result = _run_cli("apply", "--update-type", "incremental", "--provenance-map", str(paths["map"]),
                          "--manifest", str(paths["manifest"]), "--extraction", str(paths["extraction"]),
                          "--reextract-records", str(paths["records"]), "--skill-name", "lib",
                          "--generation-date", "2026-10-01T10:00:00Z", "--confidence-tier", "Forge",
                          "--manual-sections-preserved", "0", "--not-public-out", str(listed), "-o", str(out))
        assert result.returncode == 0, result.stderr
        assert json.loads(listed.read_bytes()) == json.loads(result.stdout)["not_public"] == [
            {"name": "helper", "file": "pkg/a.py"}, {"name": "get_default_tasks", "file": COGNIFY},
            {"name": "moved_internal", "file": "pkg/new_home.py"}]

    def test_a_degraded_run_adds_every_record_whatever_its_mark(self) -> None:
        _old, inputs = self._inputs()
        doc, summary = mod.apply_update(update_type="full", provenance=None, skill_name="lib",
                                        extraction=inputs["extraction"], records=inputs["records"],
                                        test_report_run_id=None, **BLOCK)
        assert len(doc["entries"]) == 7  # every fresh record, the ones records marked public: false included
        assert summary["not_public"] == [] and summary["warnings"] == []

    def test_a_repair_carries_no_mark(self, tmp_path: Path) -> None:
        """gap-driven.md §4a runs `records` over the files it scans: gap-records drops the mark, so merge documents
        and apply maps the re-extracted export, as before."""
        remediation = _remediation(("pkg/b.py", [("fetch", 4, "ast-grep")]))
        remediation["files"][0]["exports"][0]["public"] = False
        entry = _gap_entry("GAP-001", "fetch", "NEW_EXPORT", category="missing-export", resolved=["pkg/b.py"])
        records, _ = _records([entry], tmp_path, remediation=remediation,
                              judgments={"GAP-001": {"reachability": "public", "docstring": None}})
        [record] = records["files"][0]["exports"]
        assert "public" not in record
        doc, summary = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                        records=records, test_report_run_id="r1", **BLOCK)
        assert [e["export_name"] for e in doc["entries"]] == ["fetch"] and summary["not_public"] == []

    def test_a_public_name_no_file_defines_is_public_in_its_family(self) -> None:
        extraction = _public_api_run([_runner("Drop", "cognee/pipelines/types.py", 32),
                                      _runner("Drop", "web/drop.ts", 1, language="typescript",
                                              node="function_declaration")],
                                     [{"name": "Drop", "via": "re-export", "file": None, "line": None}])
        extraction["entry_points"]["by_language"]["javascript"] = "barrel"
        records, _ = mod.build_records(extraction, None, None, [])
        marks = {b["file_path"]: r["public"] for b in records["files"] for r in b["exports"]}
        assert marks == {"cognee/pipelines/types.py": True, "web/drop.ts": False}

    def test_a_namespace_of_another_family_marks_nothing_here(self) -> None:
        extraction = _public_api_run([_runner("tools", "web/tools/tools.py", 1, export_type="module")], [
            {"name": "tools", "language": "javascript", "via": "namespace", "file": "web/tools/index.ts",
             "line": None}])
        extraction["entry_points"]["by_language"]["javascript"] = "barrel"
        records, _ = mod.build_records(extraction, None, None, [])
        assert records["files"][0]["exports"][0]["public"] is False

    def test_the_scope_type_is_read_in_any_case(self) -> None:
        extraction = _public_api_run([_runner("cognify", COGNIFY, 44), _runner("get_default_tasks", COGNIFY, 20)],
                                     SURFACE, scope_type="Public-API")
        records, _ = mod.build_records(extraction, None, None, [])
        assert {r["name"]: r["public"] for r in records["files"][0]["exports"]} == \
            {"cognify": True, "get_default_tasks": False}

    def test_a_rust_barrel_marks_its_exports(self) -> None:
        extraction = _public_api_run([_runner("add", "src/lib.rs", 1, language="rust", node="function_item"),
                                      _runner("helper", "src/util.rs", 3, language="rust", node="function_item")],
                                     [{"name": "add", "language": "rust", "via": "declaration", "file": "src/lib.rs",
                                       "line": 1}])
        extraction["entry_points"]["by_language"] = {"rust": "barrel"}
        records, _ = mod.build_records(extraction, None, None, [])
        assert {r["name"]: r["public"] for b in records["files"] for r in b["exports"]} == \
            {"add": True, "helper": False}

    def test_the_family_tables_match_the_runners(self) -> None:
        """The rule lives in skf-extraction-inventory.py, which create-skill marks its inventory by (#699)."""
        spec = importlib.util.spec_from_file_location("skf_extract_public_api_families", EXTRACT_PUBLIC_API)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        inventory = mod._inventory()
        assert inventory._FAMILY_OF_LANGUAGE == runner.FAMILY_OF
        assert inventory._FAMILY_OF_EXTENSION == {ext: runner.FAMILY_OF[language]
                                                  for ext, language in runner.EXTENSION_LANGUAGES.items()}

    def test_the_path_form_matches_the_inventory_helpers(self) -> None:
        """The rule's pairs go through the inventory helper's _norm_path and the records through this script's: the
        two copies stay one form."""
        assert inspect.getsource(mod._norm_path) == inspect.getsource(mod._inventory()._norm_path)

    def test_the_rule_is_the_inventory_helpers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One rule for create and update: the surface is skf-extraction-inventory.py's, and a run with no
        extraction object (gap-driven, docs-only) loads no helper for it."""
        monkeypatch.setattr(mod, "_INVENTORY", None)
        for nothing in (None, [], "extraction.json"):
            assert mod.public_surface(nothing) == (None, None)
        assert mod._INVENTORY is None
        surface, problem = mod.public_surface(_public_api_run([_runner("cognify", COGNIFY, 44)], SURFACE))
        assert isinstance(surface, mod._inventory()._PublicSurface) and problem is None
        assert not hasattr(mod, "_PublicSurface") and not hasattr(mod, "_FAMILY_OF_LANGUAGE")



# --------------------------------------------------------------------------
# metadata.json after an update: the lists apply writes from the entries and file entries it changed, and the
# `metadata` subcommand that writes the file (v4.0.0 quality gate run 1, skf-update-skill determinism-1)
# --------------------------------------------------------------------------

UPDATE_REFS = REPO_ROOT / "src" / "skf-update-skill" / "references"


class TestApplyExports:
    def _exports(self, update_type: str, metadata: dict, **inputs) -> list:
        _doc, summary = mod.apply_update(update_type=update_type, skill_name="lib", test_report_run_id=None,
                                         metadata=metadata, **inputs, **BLOCK)
        return summary["lists"]["exports"]

    def test_a_normal_update_drops_the_removed_and_renames_in_place(self) -> None:
        """A DELETED_EXPORT and a DELETED file's entry go, a MOVED file's comes back, a rename takes its old name's
        place, a name apply never touched stays, and each name it added an entry for comes after, once."""
        metadata = {"scope_type": "full-library",
                    "exports": ["stable", "search", "old_fn", "shifted", "gone_a", "mv", "renamed_from", "hand_kept"]}
        exports = self._exports("incremental", metadata, provenance=_old_map(), **TestApplyNormal()._inputs())
        assert exports == ["stable", "search", "shifted", "mv", "renamed_to", "hand_kept", "helper", "by_eye", "fresh"]
        # with no metadata.json given, the summary holds no lists
        _doc, summary = mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                                         test_report_run_id=None, **TestApplyNormal()._inputs(), **BLOCK)
        assert "lists" not in summary

    def test_a_public_api_update_adds_no_name_off_the_surface(self) -> None:
        old, inputs = TestPublicSurface()._inputs()
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        test_report_run_id=None, metadata={"exports": ["search", "carried"]},
                                        **inputs, **BLOCK)
        assert summary["lists"]["exports"] == ["search", "carried", "cognify"]
        assert {item["name"] for item in summary["not_public"]} == {"helper", "get_default_tasks", "moved_internal"}
        # exports[] and the map name the same exports (old_helper is an internal entry create-skill kept)
        assert set(summary["lists"]["exports"]) == {e["export_name"] for e in doc["entries"]} - {"old_helper"}

    def test_a_gap_driven_repair_drops_a_rescoped_name_and_adds_what_it_maps(self) -> None:
        records = TestApplyGapDriven()
        exports = self._exports("gap-driven", {"exports": ["stable", "search", "old_fn", "shifted"]},
                                provenance=_old_map(), records=records._records(), merge_records=records._merge())
        assert exports == ["stable", "search", "shifted", "deep", "cited", "doc_only"]

    def test_a_docs_only_update_follows_the_changed_urls(self) -> None:
        url = "https://docs.example.com/api"
        old = {"entries": [{"export_name": "get", "source_file": url, "confidence": "T3"},
                           {"export_name": "gone", "source_file": url, "confidence": "T3"}]}
        records = {"mode": "docs-only", "changed_urls": [url], "exports": [
            {"name": "get", "type": "function", "url": url}, {"name": "put", "type": "function", "url": url}]}
        assert self._exports("incremental", {"exports": ["get", "gone"]}, provenance=old,
                             records=records) == ["get", "put"]

    def test_a_degraded_run_lists_the_rebuilt_map(self) -> None:
        extraction = {"exports": [{"export_name": "a", "export_type": "function", "source_file": "x.py",
                                   "source_line": 1, "ast_node_type": "function_definition",
                                   "extraction_method": "ast-grep", "confidence": "T1"}]}
        assert self._exports("full", {"exports": ["a", "stale"]}, provenance=None, extraction=extraction) == ["a"]

    def test_a_reference_app_keeps_no_exports(self) -> None:
        metadata = {"scope_type": "reference-app", "exports": ["stable"]}
        assert self._exports("incremental", metadata, provenance=_old_map(), **TestApplyNormal()._inputs()) == []


class TestApplyFileRows:
    def test_the_rows_follow_the_file_entries_apply_writes(self, tmp_path: Path) -> None:
        """A row the update keeps stays as metadata.json holds it, a DELETED_FILE's row goes, a doc row is never
        listed, and a new script or asset gets a row whose purpose the detector reads from the file."""
        src = tmp_path / "src"
        (src / "tools").mkdir(parents=True)
        (src / "schemas").mkdir()
        (src / "tools" / "new.py").write_bytes(b"#!/usr/bin/env python3\n# Rebuild the index.\nprint('x')\n")
        (src / "schemas" / "cfg.schema.json").write_bytes(b'{"title": "Config schema", "type": "object"}\n')
        old = _old_map()
        old["file_entries"].append({"file_name": "assets/gone.json", "file_type": "asset", "source_file": "gone.json",
                                    "confidence": "T1-low", "extraction_method": "file-copy",
                                    "content_hash": "sha256:gone"})
        compare = {"comparisons": [{"source_file": "gone.json", "classification": "DELETED_FILE",
                                    "stored_hash": "sha256:gone", "current_hash": None}]}
        new_files = {"new_files": [{"source_file": "schemas/cfg.schema.json", "kind": "asset"},
                                   {"source_file": "tools/new.py", "kind": "script"}]}
        kept = {"file": "scripts/run.sh", "purpose": "Run the demo, as the author wrote it",
                "source_file": "tools/run.sh", "confidence": "T1-low"}
        metadata = {"exports": [], "scripts": [kept],
                    "assets": [{"file": "assets/gone.json", "purpose": "gone", "source_file": "gone.json",
                                "confidence": "T1-low"}]}
        _doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                         test_report_run_id=None, compare=compare, new_files=new_files,
                                         source_root=src, metadata=metadata, **BLOCK)
        assert summary["lists"]["scripts"] == [
            kept, {"file": "scripts/new.py", "purpose": "Rebuild the index.", "source_file": "tools/new.py",
                   "confidence": "T1-low"}]
        assert summary["lists"]["assets"] == [
            {"file": "assets/cfg.schema.json", "purpose": "Config schema", "source_file": "schemas/cfg.schema.json",
             "confidence": "T1-low"}]

    def test_a_row_with_no_file_to_read_takes_its_name(self) -> None:
        """A file entry metadata.json lists no row for, with no source tree to read it in: its file name."""
        _doc, summary = mod.apply_update(update_type="incremental", provenance=_old_map(), skill_name="lib",
                                         test_report_run_id=None, metadata={"exports": []}, **BLOCK)
        assert summary["lists"]["scripts"] == [{"file": "scripts/run.sh", "purpose": "run.sh",
                                                "source_file": "tools/run.sh", "confidence": "T1-low"}]
        assert summary["lists"]["assets"] == []

    def test_apply_writes_the_lists_to_the_run_folder(self, tmp_path: Path) -> None:
        old, inputs = TestPublicSurface()._inputs()
        paths = {}
        for key, value in (("map", old), ("manifest", inputs["manifest"]), ("extraction", inputs["extraction"]),
                           ("records", inputs["records"]), ("metadata", {"exports": ["search", "carried"]})):
            paths[key] = tmp_path / f"{key}.json"
            paths[key].write_bytes(json.dumps(value).encode("utf-8"))
        out, lists = tmp_path / "new-map.json", tmp_path / "metadata-lists.json"
        common = ("apply", "--update-type", "incremental", "--provenance-map", str(paths["map"]),
                  "--manifest", str(paths["manifest"]), "--extraction", str(paths["extraction"]),
                  "--reextract-records", str(paths["records"]), "--skill-name", "lib",
                  "--generation-date", "2026-10-01T10:00:00Z", "--confidence-tier", "Forge",
                  "--manual-sections-preserved", "0", "-o", str(out))
        alone = _run_cli(*common, "--metadata-in", str(paths["metadata"]))
        assert alone.returncode == 1 and "go together" in alone.stderr and not out.exists()
        result = _run_cli(*common, "--metadata-in", str(paths["metadata"]), "--lists-out", str(lists))
        assert result.returncode == 0, result.stderr
        assert json.loads(lists.read_bytes()) == {"exports": ["search", "carried", "cognify"], "scripts": [],
                                                   "assets": []}
        assert "lists" not in json.loads(result.stdout)


LISTS = {"exports": ["search", "fresh"],
         "scripts": [{"file": "scripts/run.sh", "purpose": "run", "source_file": "tools/run.sh",
                      "confidence": "T1-low"}],
         "assets": []}
STATS_OUT = {"stats": {"exports_documented": 2, "exports_public_api": 2, "exports_internal": 0, "exports_total": 2,
                       "public_api_coverage": 1.0, "total_coverage": 1.0, "scripts_count": 1, "assets_count": 0},
             "confidence_distribution": {"t1": 1, "t1_low": 1, "t2": 0, "t3": 0},
             "coherence": {"ok": True, "violations": []}}


def _skill_metadata() -> dict:
    return {"name": "lib", "version": "1.0.0", "skill_type": "single", "scope_type": "component-library",
            "source_root": "https://github.com/o/lib", "source_commit": "aaa", "source_ref": "v1",
            "generation_date": "2026-01-01T00:00:00Z", "description": "Lib.", "exports": ["search", "old"],
            "doc_sources": [{"url": "https://docs", "content_hash": "sha256:x"}],
            "stats": {"exports_documented": 9, "effective_denominator": 4, "components_registered": 3,
                      "notes": "patched"},
            "confidence_distribution": {"t1": 9, "t1_low": 0, "t2": 0, "t3": 0},
            "assets": [{"file": "assets/gone.json", "purpose": "gone", "source_file": "gone.json"}],
            "tool_versions": {"ast_grep": "0.40.0", "qmd": "2.0.1", "skf": "3.0.0"},
            "last_update": "2026-01-01", "update_type": "incremental"}


def _kept_warning(key: str) -> str:
    return f"metadata: stats.{key} kept from an earlier run; check it still describes this run's counts"


def _helper_dropped(key: str) -> str:
    return f"metadata: stats.{key} dropped: this run's stats helper did not write it"


def _note_dropped(key: str) -> str:
    return f"metadata: stats.{key} dropped: it explained an effective_denominator this run changed or removed"


def _metadata_files(tmp_path: Path, metadata: dict | None = None) -> tuple:
    """metadata.json, the lists and the stats a `metadata` call reads, and its argv."""
    target, lists, stats_file = tmp_path / "metadata.json", tmp_path / "lists.json", tmp_path / "stats.json"
    target.write_bytes(json.dumps(metadata or _skill_metadata()).encode("utf-8"))
    lists.write_bytes(json.dumps(LISTS).encode("utf-8"))
    stats_file.write_bytes(json.dumps(STATS_OUT).encode("utf-8"))
    return target, ("metadata", "--metadata", str(target), "--lists", str(lists), "--stats", str(stats_file),
                    "--version", "1.1.0", "--generation-date", "2026-10-01T10:00:00Z")


def _tools_after(tmp_path: Path, extraction: object) -> subprocess.CompletedProcess:
    """A `metadata` call with this --extraction, over a skill whose tool_versions name ast-grep 0.40.0."""
    path = tmp_path / "extraction.json"
    path.write_bytes(json.dumps(extraction).encode("utf-8"))
    _, argv = _metadata_files(tmp_path)
    return _run_cli(*argv, "--extraction", str(path))


# the old stats #815 found: an explanation of an earlier denominator beside a component library's own count and
# a note
DENOMINATED = {"exports_documented": 9, "effective_denominator": 320,
               "effective_denominator_source": "x", "reconciliation_note": "y",
               "components_registered": 3, "notes": "patched"}


def _recount(denominator: int | None, old: dict | None = None) -> tuple[dict, dict]:
    """update_metadata over a component library's `old` stats (DENOMINATED), with this run's stats holding
    `denominator` (None: no denominator)."""
    stats = {**STATS_OUT["stats"], **({} if denominator is None else {"effective_denominator": denominator})}
    return mod.update_metadata({**_skill_metadata(), "stats": DENOMINATED if old is None else old}, LISTS,
                               {**STATS_OUT, "stats": stats}, version="1.1.0",
                               generation_date="2026-10-01T10:00:00Z", skf_version="4.0.0")


class TestUpdateMetadata:
    def test_it_sets_what_the_update_owns_and_keeps_the_rest(self) -> None:
        out, summary = mod.update_metadata(_skill_metadata(), LISTS, STATS_OUT, version="1.1.0",
                                           generation_date="2026-10-01T10:00:00Z", source_commit="bbb",
                                           skf_version="4.0.0")
        assert out == {
            "name": "lib", "version": "1.1.0", "skill_type": "single", "scope_type": "component-library",
            "source_root": "https://github.com/o/lib", "source_commit": "bbb", "source_ref": "v1",
            "generation_date": "2026-10-01T10:00:00Z", "description": "Lib.", "exports": ["search", "fresh"],
            "doc_sources": [{"url": "https://docs", "content_hash": "sha256:x"}],
            # the stats helper's fields, then a component library's own count and a patched note; the
            # effective_denominator this run's stats leave out is gone
            "stats": {**STATS_OUT["stats"], "components_registered": 3, "notes": "patched"},
            "confidence_distribution": STATS_OUT["confidence_distribution"],
            # the running SKF, and the tools this run did not use as they stand
            "tool_versions": {"ast_grep": "0.40.0", "qmd": "2.0.1", "skf": "4.0.0"},
            "scripts": LISTS["scripts"]}
        assert "last_update" not in out and "update_type" not in out and "assets" not in out
        # create-skill writes a component library's own count, not a note
        assert summary == {"dropped_stats": ["effective_denominator"],
                           "warnings": [_helper_dropped("effective_denominator"), _kept_warning("notes")]}

    def test_an_empty_ref_clears_it_and_no_flag_keeps_it(self) -> None:
        out, _ = mod.update_metadata(_skill_metadata(), LISTS, STATS_OUT, version="1.0.0",
                                     generation_date="2026-10-01T10:00:00Z", source_ref="")
        assert (out["source_commit"], out["source_ref"]) == ("aaa", None)

    def test_the_cli_records_a_moved_local_source_root(self, tmp_path: Path) -> None:
        """#1193 enhancement-5: `--source-root` records the folder a run's `--source-root` override read, so the
        next run reads it; an empty one sets null, and a call without it keeps the recorded folder."""
        moved = (tmp_path / "new source").as_posix()
        target, argv = _metadata_files(tmp_path, {**_skill_metadata(), "source_root": "/gone/lib"})
        result = _run_cli(*argv, "--source-root", moved)
        assert result.returncode == 0, result.stderr
        written = json.loads(target.read_bytes())
        assert (written["source_root"], written["source_commit"], written["source_ref"]) == (moved, "aaa", "v1")
        target, argv = _metadata_files(tmp_path, {**_skill_metadata(), "source_root": "/gone/lib"})
        assert _run_cli(*argv, "--source-root", "").returncode == 0
        assert json.loads(target.read_bytes())["source_root"] is None
        target, argv = _metadata_files(tmp_path, {**_skill_metadata(), "source_root": "/gone/lib"})
        assert _run_cli(*argv).returncode == 0
        assert json.loads(target.read_bytes())["source_root"] == "/gone/lib"

    def test_the_cli_stamps_the_tool_versions_this_run_used(self, tmp_path: Path) -> None:
        """#801: tool_versions named the toolchain of the run that created the skill, however many updates later."""
        skf_root, extraction = tmp_path / "skf", tmp_path / "extraction.json"
        skf_root.mkdir()
        (skf_root / "package.json").write_bytes(json.dumps({"name": "skf", "version": "4.0.0"}).encode("utf-8"))
        extraction.write_bytes(json.dumps({"status": "ok", "ast_grep": {"path": "/bin/ast-grep",
                                                                        "version": "0.45.3"},
                                           "exports": []}).encode("utf-8"))
        target, argv = _metadata_files(tmp_path)
        result = _run_cli(*argv, "--skf-root", str(skf_root), "--extraction", str(extraction))
        assert result.returncode == 0, result.stderr
        stamped = {"ast_grep": "0.45.3", "qmd": "2.0.1", "skf": "4.0.0"}
        assert json.loads(target.read_bytes())["tool_versions"] == stamped
        summary = json.loads(result.stdout)
        assert summary["tool_versions"] == stamped
        assert not [w for w in summary["warnings"] if "tool_versions" in w], summary["warnings"]

    def test_an_skf_root_with_no_version_stamps_unknown_never_the_old_one(self, tmp_path: Path) -> None:
        (tmp_path / "skf").mkdir()
        target, argv = _metadata_files(tmp_path)
        result = _run_cli(*argv, "--skf-root", str(tmp_path / "skf"))
        assert result.returncode == 0, result.stderr
        assert json.loads(target.read_bytes())["tool_versions"]["skf"] == "unknown"
        warning = json.loads(result.stdout)["warnings"][0]
        # the folder it read, so the user can see which install holds no version
        assert warning == mod._skf_unknown(tmp_path / "skf") and (tmp_path / "skf").as_posix() in warning

    def test_no_skf_root_says_so(self, tmp_path: Path) -> None:
        target, argv = _metadata_files(tmp_path)
        result = _run_cli(*argv)
        assert result.returncode == 0, result.stderr
        assert json.loads(target.read_bytes())["tool_versions"]["skf"] == "unknown"
        assert json.loads(result.stdout)["warnings"][0] == mod.SKF_NO_ROOT
        assert "no --skf-root was given" in mod.SKF_NO_ROOT and mod.SKF_NO_ROOT != mod._skf_unknown("x")

    @pytest.mark.parametrize("ast_grep,qmd,expected", [
        (None, "2.1.0", {"ast_grep": "0.40.0", "qmd": "2.1.0", "skf": "4.0.0"}),
        ("0.45.3", None, {"ast_grep": "0.45.3", "qmd": "2.0.1", "skf": "4.0.0"}),
        (" ", "", {"ast_grep": "0.40.0", "qmd": "2.0.1", "skf": "4.0.0"}),
        (None, "qmd 2.1.0", {"ast_grep": "0.40.0", "qmd": "2.1.0", "skf": "4.0.0"}),
    ], ids=["qmd-only", "ast-grep-only", "blank-keeps-old", "qmd-prefix-stripped"])
    def test_a_tool_this_run_did_not_use_keeps_its_old_version(self, ast_grep, qmd, expected) -> None:
        out, _ = mod.update_metadata(_skill_metadata(), LISTS, STATS_OUT, version="1.1.0",
                                     generation_date="2026-10-01T10:00:00Z", skf_version="4.0.0",
                                     ast_grep_version=ast_grep, qmd_version=qmd)
        assert out["tool_versions"] == expected

    def test_the_cli_stores_qmd_as_its_bare_version(self, tmp_path: Path) -> None:
        target, argv = _metadata_files(tmp_path)
        result = _run_cli(*argv, "--qmd-version", "qmd 2.1.0")
        assert result.returncode == 0, result.stderr
        assert json.loads(target.read_bytes())["tool_versions"]["qmd"] == "2.1.0"

    @pytest.mark.parametrize("old,warned", [(None, False), ("3.0.0", True), (["skf"], True)],
                             ids=["absent", "a-string", "an-array"])
    def test_a_skill_with_no_tool_versions_object_starts_as_create_skill_does(self, old, warned) -> None:
        metadata = {k: v for k, v in _skill_metadata().items() if k != "tool_versions"}
        if old is not None:
            metadata["tool_versions"] = old
        out, summary = mod.update_metadata(metadata, LISTS, STATS_OUT, version="1.1.0",
                                           generation_date="2026-10-01T10:00:00Z", skf_version="4.0.0",
                                           qmd_version="2.0.1")
        assert out["tool_versions"] == {"ast_grep": None, "qmd": "2.0.1", "skf": "4.0.0"}
        replaced = [w for w in summary["warnings"] if w.startswith("metadata: tool_versions was ")]
        assert len(replaced) == warned and all("not an object; replaced" in w for w in replaced)

    def test_an_extraction_with_no_ast_grep_keeps_the_old_version(self, tmp_path: Path) -> None:
        """What step 2 writes when the runner cannot run: ast-grep did not run, so its old version stands."""
        result = _tools_after(tmp_path, {"exports": [], "scope": {"type": "public-api"}})
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["tool_versions"]["ast_grep"] == "0.40.0"

    def test_an_extraction_ast_grep_matched_with_no_version_stamps_unknown(self, tmp_path: Path) -> None:
        result = _tools_after(tmp_path, {"ast_grep": {"path": None, "version": None},
                                         "exports": [{"name": "search", "extraction_method": "ast-grep"}]})
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert summary["tool_versions"]["ast_grep"] == "unknown" and mod.AST_GREP_UNKNOWN in summary["warnings"]

    def test_an_extraction_that_is_not_an_object_is_refused(self, tmp_path: Path) -> None:
        result = _tools_after(tmp_path, [])
        assert result.returncode == 1 and result.stdout == ""
        assert result.stderr.strip() == ("error: --extraction file must hold a JSON object (the recipe runner's "
                                         "output)")
        assert json.loads((tmp_path / "metadata.json").read_bytes()) == _skill_metadata()

    @pytest.mark.parametrize("sibling", [None, b"def probe_skf_version(:\n", b"import skf_no_such_module\n"],
                             ids=["missing", "syntax-error", "import-error"])
    def test_a_probe_it_cannot_load_exits_1_with_one_line(self, tmp_path: Path, sibling) -> None:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        shutil.copy(SCRIPT_PATH, scripts / SCRIPT_PATH.name)
        if sibling is not None:
            (scripts / "skf-render-quick-metadata.py").write_bytes(sibling)
        target, argv = _metadata_files(tmp_path)
        result = subprocess.run([sys.executable, str(scripts / SCRIPT_PATH.name), *argv, "--skf-root",
                                 str(tmp_path)], capture_output=True, text=True, check=False)
        assert result.returncode == 1 and result.stdout == ""
        lines = result.stderr.splitlines()
        assert len(lines) == 1 and lines[0].startswith("error: cannot load skf-render-quick-metadata.py beside "), \
            result.stderr
        assert "Traceback" not in result.stderr and "cannot write" not in result.stderr
        assert json.loads(target.read_bytes()) == _skill_metadata()

    def test_a_changed_denominator_drops_its_old_explanation_and_flags_the_rest(self) -> None:
        """#815: a recount to 280 kept the explanation of the old 320 without a word."""
        out, summary = _recount(280)
        assert out["stats"] == {**STATS_OUT["stats"], "effective_denominator": 280, "reconciliation_note": "y",
                                "components_registered": 3, "notes": "patched"}
        assert summary == {"dropped_stats": ["effective_denominator_source"],
                           "warnings": [_note_dropped("effective_denominator_source"),
                                        _kept_warning("reconciliation_note"), _kept_warning("notes")]}

    def test_a_dropped_denominator_drops_its_old_explanation(self) -> None:
        out, summary = _recount(None)
        assert "effective_denominator" not in out["stats"] and "effective_denominator_source" not in out["stats"]
        assert summary == {"dropped_stats": ["effective_denominator", "effective_denominator_source"],
                           "warnings": [_helper_dropped("effective_denominator"),
                                        _note_dropped("effective_denominator_source"),
                                        _kept_warning("reconciliation_note"), _kept_warning("notes")]}

    def test_an_added_denominator_drops_an_explanation_of_none(self) -> None:
        old = {k: v for k, v in DENOMINATED.items() if k != "effective_denominator"}
        out, summary = _recount(280, old)
        assert out["stats"]["effective_denominator"] == 280 and "effective_denominator_source" not in out["stats"]
        assert summary["dropped_stats"] == ["effective_denominator_source"]
        assert _note_dropped("effective_denominator_source") in summary["warnings"]

    def test_an_unchanged_denominator_keeps_its_explanation_silently(self) -> None:
        out, summary = _recount(320)
        assert out["stats"]["effective_denominator_source"] == "x"
        assert summary == {"dropped_stats": [], "warnings": [_kept_warning("reconciliation_note"),
                                                             _kept_warning("notes")]}

    def test_an_explanation_with_no_denominator_on_either_side_is_flagged(self) -> None:
        old = {k: v for k, v in DENOMINATED.items() if k != "effective_denominator"}
        out, summary = _recount(None, old)
        assert out["stats"]["effective_denominator_source"] == "x" and summary["dropped_stats"] == []
        assert _kept_warning("effective_denominator_source") in summary["warnings"]

    @pytest.mark.parametrize("scope_type,warned", [
        ("component-library", ["notes"]),
        ("reference-app", ["components_registered"]),
        ("full-library", ["components_registered", "notes"]),
        (None, ["components_registered", "notes"]),
    ], ids=["component-library", "reference-app", "library", "no-scope-type"])
    def test_the_keys_create_skill_writes_follow_the_scope_type(self, scope_type, warned) -> None:
        """create-skill writes a component library's own counts and a reference app's notes, each only for its
        scope: a library skill's patched notes or component count warns."""
        metadata = {**_skill_metadata(), "scope_type": scope_type,
                    "stats": {"components_registered": 3, "notes": "patched"}}
        out, summary = mod.update_metadata(metadata, LISTS, STATS_OUT, version="1.1.0",
                                           generation_date="2026-10-01T10:00:00Z", skf_version="4.0.0")
        assert out["stats"] == {**STATS_OUT["stats"], "components_registered": 3, "notes": "patched"}
        assert summary == {"dropped_stats": [], "warnings": [_kept_warning(key) for key in warned]}

    @pytest.mark.parametrize("change,needle", [
        ({"stats": {**STATS_OUT, "stats": {**STATS_OUT["stats"], "scripts_count": 0}}},
         "the stats count 0 scripts but apply's lists hold 1"),
        ({"generation_date": "2026-10-01"}, "--generation-date must be YYYY-MM-DDTHH:MM:SSZ"),
        ({"lists": {"exports": []}}, "--lists file must hold"),
        ({"stats": {"stats": {}}}, "--stats file must hold"),
        ({"metadata": []}, "--metadata file must hold a JSON object"),
        ({"version": " "}, "--version must not be empty"),
    ], ids=["stats-from-other-lists", "date-not-from-the-clock", "lists-not-apply", "stats-not-the-helpers",
            "metadata-not-an-object", "empty-version"])
    def test_it_refuses_inputs_that_do_not_fit(self, change: dict, needle: str) -> None:
        given = {"metadata": _skill_metadata(), "lists": LISTS, "stats": STATS_OUT, "version": "1.1.0",
                 "generation_date": "2026-10-01T10:00:00Z", **change}
        with pytest.raises(ValueError, match=re.escape(needle)):
            mod.update_metadata(given["metadata"], given["lists"], given["stats"], version=given["version"],
                                generation_date=given["generation_date"])

    def test_the_cli_writes_in_place_or_nothing(self, tmp_path: Path) -> None:
        target, lists, stats_file = tmp_path / "metadata.json", tmp_path / "lists.json", tmp_path / "stats.json"
        target.write_bytes(json.dumps(_skill_metadata()).encode("utf-8"))
        lists.write_bytes(json.dumps(LISTS).encode("utf-8"))
        stats_file.write_bytes(json.dumps({**STATS_OUT, "stats": {**STATS_OUT["stats"], "scripts_count": 2}})
                               .encode("utf-8"))
        argv = ("metadata", "--metadata", str(target), "--lists", str(lists), "--stats", str(stats_file),
                "--version", "1.1.0", "--generation-date", "2026-10-01T10:00:00Z", "--source-commit", "bbb")
        refused = _run_cli(*argv)
        assert refused.returncode == 1 and "the stats count 2 scripts" in refused.stderr
        assert json.loads(target.read_bytes()) == _skill_metadata()
        stats_file.write_bytes(json.dumps(STATS_OUT).encode("utf-8"))
        result = _run_cli(*argv)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"status": "written", "metadata": target.as_posix(), "version": "1.1.0",
                                             "exports": 2, "scripts": 1, "assets": 0,
                                             "tool_versions": {"ast_grep": "0.40.0", "qmd": "2.0.1",
                                                               "skf": "unknown"},
                                             "dropped_stats": ["effective_denominator"],
                                             "warnings": [mod.SKF_NO_ROOT, _helper_dropped("effective_denominator"),
                                                          _kept_warning("notes")]}
        assert json.loads(target.read_bytes())["source_commit"] == "bbb"


def test_the_component_library_exemption_is_create_skills_block() -> None:
    """The component-library keys the `metadata` call keeps silently are the ones compile-assembly-rules.md tells
    create-skill to add, so the two cannot drift apart."""
    rules = (REPO_ROOT / "src" / "skf-create-skill" / "assets" / "compile-assembly-rules.md").read_text(
        encoding="utf-8")
    block = rules[rules.index("Component Library stats:**"):]
    block = block[block.index("```json") + len("```json"):]
    block = json.loads(block[:block.index("```")])
    assert set(block["stats"]) == set(mod.STATS_CREATE_FIELDS["component-library"])
    assert len(mod.STATS_CREATE_FIELDS["component-library"]) == len(block["stats"])
    assert mod.STATS_CREATE_FIELDS["reference-app"] == ("notes",)


def test_write_sets_metadata_through_the_helper() -> None:
    """write.md §3 passes the flags and §3b writes metadata.json through `metadata`, keeping no rule of its own,
    and merge.md's Priority 6 leaves the script and asset rows to it."""
    write = (UPDATE_REFS / "write.md").read_text(encoding="utf-8")
    call = write[write.index("uv run {buildChangeManifestHelper} apply"):]
    call = call[:call.index("```")]
    assert '--metadata-in "{skill_package}/metadata.json"' in call
    assert '--lists-out "{run_dir}/metadata-lists.json"' in call
    two = write[write.index("### 2. Prepare the Write Inputs"):write.index("### 3. ")]
    three_b = write[write.index("### 3b. Write Updated metadata.json"):write.index("### 4. ")]
    meta = three_b[three_b.index("uv run {buildChangeManifestHelper} metadata"):]
    meta = meta[:meta.index("```")]
    for flag in ('--metadata "{skill_package}/metadata.json"', '--lists "{run_dir}/metadata-lists.json"',
                 '--stats "{run_dir}/stats.json"', '--version "{new_version}"',
                 '--generation-date "{generation_date}"',
                 # #801: the toolchain this run used, the installed SKF's version always
                 '\n      --skf-root "{project-root}/_bmad/skf" \\\n',
                 '[--extraction "{run_dir}/extraction.json"]', '[--qmd-version "{qmd_version}"]'):
        assert flag in meta, flag
    after = three_b[three_b.index("uv run {buildChangeManifestHelper} metadata"):]
    after = after[after.index("```") + 3:after.index("On exit 1, fix the input its stderr names")]
    for token in ("Pass `--extraction` when step 2 wrote `{run_dir}/extraction.json`",
                  "and `--qmd-version` when re-extract.md §3 queried QMD and bound `{qmd_version}`",
                  "a tool this run did not use keeps the version metadata.json records",
                  "`dropped_stats` lists each key it drops, a stats helper field this run's stats left out included",
                  "On exit 0, add each of its `warnings` to `warnings[]`",
                  "Leave out only a warning that a stats key was `kept from an earlier run` when this run's "
                  "`metadata_patches[]` wrote that key; a dropped key's warning always goes to `warnings[]`"):
        assert token in after, token
    # #815: a patch adds no explanatory stat the next recount would leave standing beside another count, in write,
    # in merge's Priority 8b, which queues it, and in gap-driven's rule R4, which routes it
    assert "add an explanatory stat" not in two + three_b
    # #1192 architecture-5: each patch's outcome is a record the evidence report and the update report list, not a
    # log kept in context: §2 records each field it applies or leaves out, §3b each applied one the call drops
    assert "Log each patch" not in write
    for token in ("append the record `metadata_patch_outcome: {gap_id, field, outcome, why}` to "
                  "`{run_dir}/evidence-records.jsonl` as one JSON line keyed `metadata_patch_outcome`",
                  "`outcome` `applied` with `why` null, or `left-out` with `why` the reason"):
        assert token in two, token
    assert ("whose `<key>` the call's `dropped_stats` names, append one more `metadata_patch_outcome` line to "
            "`{run_dir}/evidence-records.jsonl`, with `outcome` `dropped`") in after
    priority_8b = (UPDATE_REFS / "merge.md").read_text(encoding="utf-8")
    priority_8b = priority_8b[priority_8b.index("**Priority 8b:"):]
    priority_8b = priority_8b[:priority_8b.index("**If no metadata-update entries:**")]
    assert "explanatory stat" not in priority_8b and "`metadata_patches[]`" in priority_8b
    gap = (UPDATE_REFS / "gap-driven.md").read_text(encoding="utf-8")
    r4 = gap[gap.index("- **R4: metadata update.**"):]
    r4 = r4[:r4.index("\n")]
    assert "explanatory stat" not in r4
    assert ("Add no `effective_denominator_*` stats key: the recount drops each one when the denominator changes."
            in r4)
    # #801: the QMD version write passes has a source
    reextract = (UPDATE_REFS / "re-extract.md").read_text(encoding="utf-8")
    qmd = reextract[reextract.index("### 3. Deep Tier QMD Enrichment"):reextract.index("### 4. ")]
    assert "bind `{qmd_version}` ← the version `qmd --version` prints (`qmd 2.0.1` gives `2.0.1`)" in qmd
    assert qmd.index("bind `{qmd_version}`") < qmd.index("**If no matching collection found in registry:**")
    assert three_b.count('-o "{run_dir}/stats.json"') == 2
    for gone in ("Update `exports` array to reflect current export list", "add no name whose record",
                 "Set `exports` to the list", "into `metadata.json` **verbatim**", "Update `generation_date`",
                 "and write the `stats` and `confidence_distribution` it returns"):
        assert gone not in two + three_b, gone
    # a gap-driven patch reaches metadata.json before apply reads it, and never exports[], which apply owns
    assert "set in `{skill_package}/metadata.json`, before §3's `apply` reads it" in two
    assert "and `exports[]`, which §3's `apply` builds from the list it reads" in two
    merge = (UPDATE_REFS / "merge.md").read_text(encoding="utf-8")
    assert "`metadata.json` `scripts[]`/`assets[]`" not in merge
    assert "and `stats.scripts_count`/`stats.assets_count`" not in merge


def test_test_skill_claims_no_denominator_source_create_skill_never_writes() -> None:
    """#815: create-skill writes no stats.effective_denominator_source, so test-skill's fold convention stands on its
    own."""
    protocol = (REPO_ROOT / "src" / "skf-test-skill" / "references" / "source-access-protocol.md").read_text(
        encoding="utf-8")
    assert "effective_denominator_source" not in protocol
    assert ("Test-skill defines this fold convention: the base form is authoritative, and the variant is a sibling "
            "record." in protocol)


TRACE = "cognee/modules/observability/trace_context.py"


class TestApplyMovedExport:
    def _apply(self, old: dict, change: dict, *, extraction: dict | None = None, details: dict | None = None,
               path: str = TRACE) -> tuple[dict, dict]:
        manifest = {"total_export_changes": 1, "per_file": [
            {"file_path": path, "status": "MODIFIED", "exports_affected": [{"change_type": "MOVED_EXPORT", **change}]}]}
        return mod.apply_update(update_type="incremental", provenance=old, skill_name="lib", manifest=manifest,
                                extraction=extraction, details=details, test_report_run_id=None, **BLOCK)

    def test_a_runner_record_gives_its_labels_with_the_new_line(self) -> None:
        """oms-cognee's enable_tracing: a legacy source-read entry with T1 labels the runner now matches."""
        legacy = _entry("enable_tracing", TRACE, 16, extraction_method="source-read",
                        params=["console_output: bool = False"], return_type="None", notes="kept")
        old = {"entries": [legacy]}
        assert stats.check_label_agreement(old) != []  # the coherence check the update used to fail
        doc, _ = self._apply(old, {"name": "enable_tracing", "old_line": 16, "new_line": 18},
                             extraction={"exports": [_runner("enable_tracing", TRACE, 18, params=[])]})
        [entry] = doc["entries"]
        assert (entry["source_line"], entry["confidence"], entry["extraction_method"], entry["signature_source"],
                entry["ast_node_type"]) == (18, "T1", "ast-grep", "T1", "function_definition")
        # never the record's signature: the export did not change, only its line
        assert (entry["export_type"], entry["params"], entry["return_type"], entry["notes"]) == \
            ("function", ["console_output: bool = False"], "None", "kept")
        assert stats.check_label_agreement(doc) == []

    def test_a_null_node_kind_keeps_the_entrys_kind(self) -> None:
        old = {"entries": [_entry("clear_traces", TRACE, 85, extraction_method="source-read",
                                  ast_node_type="function_definition")]}
        doc, _ = self._apply(old, {"name": "clear_traces", "old_line": 85, "new_line": 121},
                             extraction={"exports": [_runner("clear_traces", TRACE, 121, node=None)]})
        [entry] = doc["entries"]
        assert (entry["extraction_method"], entry["ast_node_type"]) == ("ast-grep", "function_definition")

    def test_a_record_read_by_eye_moves_the_line_only(self) -> None:
        # an entry the runner labelled before: a by-eye record of its move leaves every label as it was
        labelled = _entry("visualize", TRACE, 6, notes="kept")
        details = {"exports": [{"export_name": "visualize", "export_type": "alias", "source_file": TRACE,
                                "source_line": 8, "params": None, "return_type": None, "confidence": "T1-low",
                                "extraction_method": "source-read"}]}
        doc, _ = self._apply({"entries": [labelled]}, {"name": "visualize", "old_line": 6, "new_line": 8},
                             details=details)
        assert doc["entries"] == [{**labelled, "source_line": 8}]

    @pytest.mark.parametrize("parts, expected", [
        ((None, None), "T1-low"), (([{"name": "x", "type": "int", "default": None, "optional": False}], None),
                                   "T1-low"),
        (([{"name": "x", "type": "int", "default": None, "optional": False}], "None"), "T1"),
    ], ids=["no-params", "no-return-type", "both"])
    def test_its_signature_source_needs_each_part_the_entry_holds(self, parts: tuple, expected: str) -> None:
        # the diff skips a field the runner left null, so a move says nothing of a signature the runner did not read
        held = _entry("enable_tracing", TRACE, 16, extraction_method="source-read", signature_source="T1-low",
                      params=["x: int"], return_type="None")
        runner = _runner("enable_tracing", TRACE, 18, params=parts[0], return_type=parts[1])
        doc, _ = self._apply({"entries": [held]}, {"name": "enable_tracing", "old_line": 16, "new_line": 18},
                             extraction={"exports": [runner]})
        [entry] = doc["entries"]
        assert (entry["extraction_method"], entry["confidence"], entry["signature_source"]) == \
            ("ast-grep", "T1", expected)
        assert (entry["params"], entry["return_type"]) == (["x: int"], "None")

    @pytest.mark.parametrize("runner", [True, False], ids=["fresh-record", "diff-line"])
    def test_a_move_across_files_moves_the_entry(self, runner: bool) -> None:
        diff = {"removed": [], "added": [], "changed": [], "moved": [
            {"name": "relocated", "previous_file": "pkg/a.py", "current_file": "pkg/b.py", "previous_line": 10,
             "line": 5}]}
        manifest = mod.build_manifest(mod.assemble({"category_a": {"modified": ["pkg/a.py", "pkg/b.py"]}}, diff=diff))
        [change] = [c for f in manifest["per_file"] for c in f["exports_affected"]]
        assert change == {"name": "relocated", "change_type": "MOVED_EXPORT", "old_line": 10, "new_line": 5,
                          "old_file": "pkg/a.py"}
        old = {"entries": [_entry("relocated", "pkg/a.py", 10, notes="kept"), _entry("other", "pkg/a.py", 1)]}
        extraction = {"exports": [_runner("relocated", "pkg/b.py", 5)] if runner else []}
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        manifest=manifest, extraction=extraction, test_report_run_id=None, **BLOCK)
        entries = {(e["export_name"], e["source_file"]): e for e in doc["entries"]}
        assert set(entries) == {("relocated", "pkg/b.py"), ("other", "pkg/a.py")}
        assert (entries[("relocated", "pkg/b.py")]["source_line"], entries[("relocated", "pkg/b.py")]["notes"]) == \
            (5, "kept")
        assert summary["entries"]["updated"] == ["relocated"] and summary["entries"]["added"] == []

    @pytest.mark.parametrize("scope_type", ["full-library", "public-api"])
    def test_a_move_across_files_that_also_changed_rewrites_the_entry(self, scope_type: str) -> None:
        """A MODIFIED_EXPORT that also moved names the file it left: one entry, at the new file, with the fresh
        fields and its own keys; under public-api too, though the surface does not name it, since the map holds it."""
        diff = {"removed": [], "added": [], "moved": [
            {"name": "relocated", "previous_file": "pkg/a.py", "current_file": "pkg/b.py", "previous_line": 10,
             "line": 5}],
            "changed": [{"name": "relocated", "field": "params", "baseline_value": [], "current_value": ["x: int"],
                         "file": "pkg/b.py", "line": 5}]}
        manifest = mod.build_manifest(mod.assemble({"category_a": {"modified": ["pkg/a.py", "pkg/b.py"]}}, diff=diff))
        [change] = [c for f in manifest["per_file"] for c in f["exports_affected"]]
        assert (change["change_type"], change["old_file"], change["old_line"]) == ("MODIFIED_EXPORT", "pkg/a.py", 10)
        old = {"entries": [_entry("relocated", "pkg/a.py", 10, notes="kept"), _entry("other", "pkg/a.py", 1)]}
        params = [{"name": "x", "type": "int", "default": None, "optional": False}]
        extraction = _public_api_run([_runner("relocated", "pkg/b.py", 5, params=params)], SURFACE,
                                     scope_type=scope_type)
        records, _ = mod.build_records(extraction, None, ["pkg/a.py", "pkg/b.py"], [])
        doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="lib",
                                        manifest=manifest, extraction=extraction, records=records,
                                        test_report_run_id=None, **BLOCK)
        relocated = [e for e in doc["entries"] if e["export_name"] == "relocated"]
        assert [(e["source_file"], e["source_line"], e["params"], e["notes"]) for e in relocated] == [
            ("pkg/b.py", 5, ["x: int"], "kept")]
        assert summary["entries"]["added"] == [] and summary["not_public"] == []


# --------------------------------------------------------------------------
# the oms-cognee 1.0.0 to v1.6.2 update's shape, through the recipe runner (#685, #686)
# --------------------------------------------------------------------------


EXTRACT_PUBLIC_API = REPO_ROOT / "src" / "shared" / "scripts" / "skf-extract-public-api.py"
REMEMBER = "cognee/api/v1/remember/remember.py"
# the new version: cognee/__init__.py's names, an ADDED file with one public and one internal function, a new
# internal function beside cognify, and trace_context.py's functions two lines down
COGNEE_TREE = {
    "cognee/__init__.py": "from .api.v1.cognify import cognify\nfrom .api.v1.delete import delete\n"
                          "from .api.v1.remember.remember import remember\nfrom .api.v1 import tools\n"
                          "from .modules.observability.trace_context import (\n    enable_tracing,\n"
                          "    disable_tracing,\n    get_all_traces,\n    clear_traces,\n)\n",
    "cognee/api/__init__.py": "", "cognee/api/v1/__init__.py": "",
    "cognee/api/v1/cognify/__init__.py": "from .cognify import cognify\n",
    COGNIFY: "def get_default_tasks():\n    return []\n\n\nasync def cognify():\n    return get_default_tasks()\n",
    "cognee/api/v1/delete/__init__.py": "async def delete():\n    return None\n",
    "cognee/api/v1/delete/delete.py": "",
    "cognee/api/v1/remember/__init__.py": "",
    REMEMBER: "def build_remember_tasks():\n    return []\n\n\nasync def remember():\n    return build_remember_tasks()\n",
    "cognee/api/v1/tools/__init__.py": "from .tools import list_tools\n",
    "cognee/api/v1/tools/tools.py": "def list_tools():\n    return []\n",
    "cognee/modules/__init__.py": "", "cognee/modules/observability/__init__.py": "",
    TRACE: "import os\n\n\ndef enable_tracing():\n    return None\n\n\ndef disable_tracing():\n    return None\n\n\n"
           "def get_last_trace():\n    return None\n\n\ndef get_all_traces():\n    return []\n\n\n"
           "def clear_traces():\n    return None\n",
}
TRACED = ("enable_tracing", "disable_tracing", "get_last_trace", "get_all_traces", "clear_traces")


def _run_runner(root: Path, out: Path, *extra: str) -> dict:
    proc = subprocess.run([sys.executable, str(EXTRACT_PUBLIC_API), "--mode", "full", "--source-root", str(root),
                           "--scope-type", "public-api", "--head-cap", "0", *extra, "-o", str(out)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(out.read_bytes())


@pytest.mark.skipif(shutil.which("ast-grep") is None, reason="no ast-grep on PATH")
def test_the_oms_cognee_update_documents_its_public_surface_and_keeps_its_ast_labels(tmp_path: Path) -> None:
    """The two acceptance checks on cognee's shape: no added entry is off the public surface, so
    public_api_coverage stays at most 1 plus the map's internals; and each moved trace_context.py export the runner
    matched is ast-grep/T1, so the stats helper's coherence check passes."""
    root = tmp_path / "src"
    for rel, text in COGNEE_TREE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    run = tmp_path / "run"
    run.mkdir()
    modified, added = [COGNIFY, TRACE], [REMEMBER]
    (run / "extract-files.json").write_bytes(json.dumps(modified + added).encode("utf-8"))
    (run / "modified-files.json").write_bytes(json.dumps(modified).encode("utf-8"))
    # detect-changes Category B's run: the files to extract, the scope type the brief gives (metadata.json has none)
    extraction = _run_runner(root, run / "extraction.json", "--files-from", str(run / "extract-files.json"))
    assert extraction["scope"]["type"] == "public-api"
    fresh = {e["export_name"]: e for e in extraction["exports"]}
    # the 1.0.0 map: cognify as the runner records it, and trace_context.py's names two lines up, labelled
    # source-read with T1 as SKF 1.0.0 wrote them (get_last_trace is an internal name the map kept)
    old = {"entries": [
        {"export_name": name, "export_type": "function", "source_library": "cognee", "params": [],
         "source_file": fresh[name]["source_file"],
         "source_line": fresh[name]["source_line"] - (2 if name in TRACED else 0), "confidence": "T1",
         "extraction_method": "source-read" if name in TRACED else "ast-grep",
         "ast_node_type": "function_definition", "signature_source": "T1"}
        for name in ("cognify", *TRACED)]}
    assert {v["export_name"] for v in stats.check_label_agreement(old)} == set(TRACED)
    (run / "map.json").write_bytes(json.dumps(old).encode("utf-8"))
    diff = subprocess.run([sys.executable, str(STRUCTURAL_DIFF), str(run / "map.json"), str(run / "extraction.json"),
                           "--files", str(run / "modified-files.json"), "-o", str(run / "diff.json")],
                          capture_output=True, text=True, check=False)
    assert diff.returncode in (0, 1), diff.stderr
    manifest = mod.build_manifest(mod.assemble({"category_a": {"modified": modified, "added": added}},
                                               diff=json.loads((run / "diff.json").read_bytes())))
    assert manifest["counts"]["exports_moved"] == 5 and manifest["counts"]["exports_new"] == 1
    records, _ = mod.build_records(extraction, None, modified + added, [])
    doc, summary = mod.apply_update(update_type="incremental", provenance=old, skill_name="cognee",
                                    manifest=manifest, extraction=extraction, records=records,
                                    test_report_run_id=None, **BLOCK)
    # #685: the public add lands; the new internal names are listed, not added
    assert summary["entries"]["added"] == ["remember"]
    assert sorted(item["name"] for item in summary["not_public"]) == ["build_remember_tasks", "get_default_tasks"]
    # #686: every moved export the runner matched carries its labels, and the coherence check passes
    by_name = {e["export_name"]: e for e in doc["entries"]}
    for name in TRACED:
        assert (by_name[name]["source_line"], by_name[name]["extraction_method"], by_name[name]["confidence"]) == \
            (fresh[name]["source_line"], "ast-grep", "T1"), name
    # write.md §3b's whole-scope count, and the stats helper over the written map
    counts = _run_runner(root, run / "public-api.json")["counts"]
    derived = stats.derive_stats(doc, {"exports_public_api": counts["exports_public_api"],
                                       "exports_internal": counts["exports_internal"]})
    assert stats.coherence_compute(derived, doc)["ok"]
    internals_kept = 1  # get_last_trace, an internal name the 1.0.0 map held
    assert derived["stats"]["exports_documented"] <= counts["exports_public_api"] + internals_kept
    assert derived["stats"]["public_api_coverage"] <= 1 + internals_kept / counts["exports_public_api"]


def _pinned_ast_grep() -> bool:
    """An ast-grep of the version package.json pins, the gate test-skf-extraction-inventory.py's runner tests use."""
    scripts = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    pin = re.search(r"--with ast-grep-cli==([\w.]+)", scripts["test:python"])
    exe = shutil.which("ast-grep")
    if pin is None or exe is None:
        return False
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and out.stdout.split()[-1:] == [pin.group(1)]


@pytest.mark.skipif(not _pinned_ast_grep(), reason="no ast-grep of the version package.json pins")
def test_a_public_api_create_maps_the_names_update_keeps_on_cognees_shape(tmp_path: Path) -> None:
    """The create twin of the oms-cognee update (#699): create-skill's inventory, marked by the rule `records` marks
    an update by, writes a map of exactly the names update keeps from the same runner records, and the stats
    helper's public_api_coverage stays at most 1."""
    root = tmp_path / "src"
    for rel, text in COGNEE_TREE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    extraction = _run_runner(root, tmp_path / "extraction.json")
    inventory = mod._inventory()
    data = inventory.init("cognee", "source", "Deep", extraction)
    entries, _unsigned = inventory.provenance_entries(data)
    mapped = {(e["export_name"], e["source_file"]) for e in entries}
    records, summary = mod.build_records(extraction, None, None, [])
    kept = {(r["name"], b["file_path"]) for b in records["files"] for r in b["exports"] if r.get("public") is True}
    assert mapped == kept
    # #703: `from .api.v1 import tools` is the submodule, whose list_tools users call as `cognee.tools.list_tools`
    assert {name for name, _file in mapped} == {"cognify", "delete", "remember", "enable_tracing", "disable_tracing",
                                                "get_all_traces", "clear_traces", "list_tools"}
    left_out = sorted(e["export_name"] for e in data["exports"] if e.get("public") is False)
    assert left_out == ["build_remember_tasks", "get_default_tasks", "get_last_trace"]
    assert extraction["counts"]["exports_public_api"] == 8 == len(mapped)
    assert summary["marked_not_public"] == len(left_out) == inventory.counts(data)["not_public"]
    assert data["warnings"][-1].endswith(": " + ", ".join(f"{e['export_name']} ({e['source_file']})"
                                                           for e in data["exports"] if e.get("public") is False))
    doc = {"entries": entries}
    derived = stats.derive_stats(doc, {"exports_public_api": extraction["counts"]["exports_public_api"],
                                       "exports_internal": extraction["counts"]["exports_internal"]})
    assert stats.coherence_compute(derived, doc)["ok"]
    assert derived["stats"]["exports_documented"] == len(kept)
    assert derived["stats"]["public_api_coverage"] <= 1


# --------------------------------------------------------------------------
# gap-records: update-skill gap-driven.md §3, §4 and §4a
# --------------------------------------------------------------------------

API_SOURCE = b"import os\n\n\n@decorate\ndef search(q):\n    return q\n"


def _found(path: str, line: int, export_type: str = "function") -> dict:
    view = {"source_file": path, "source_line": line, "export_type": export_type}
    return {"status": "found", "entry": view, "candidates": [view]}


NOT_FOUND = {"status": "not-found", "entry": None, "candidates": []}

_parse_gaps_spec = importlib.util.spec_from_file_location(
    "skf_parse_gaps_for_manifest", REPO_ROOT / "src" / "shared" / "scripts" / "skf-parse-gaps.py")
parse_gaps = importlib.util.module_from_spec(_parse_gaps_spec)
assert _parse_gaps_spec.loader is not None
_parse_gaps_spec.loader.exec_module(parse_gaps)


def _gap_entry(gid: str, name: str | None, change: str, *, category: str = "signature-mismatch",
               severity: str | None = "High", match: dict | None = None, citation: dict | None = None,
               resolved: list | None = None, **extra) -> dict:
    """One change-manifest entry as skf-parse-gaps.py translate writes it."""
    entry = {"name": name, "gap_id": gid, "category": category, "severity": severity}
    if citation:
        entry["source_citation"] = citation
    entry.update({"remediation_paths": list(resolved or []), "resolved_paths": list(resolved or []),
                  "rejected_paths": [], "change_category": change, "remediation": extra.pop("remediation", "Fix."),
                  **extra, "map_match": match or NOT_FOUND})
    return entry


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "src tree"
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "api.py").write_bytes(API_SOURCE)
    (root / "lib.rs").write_bytes(b"pub fn add() {}\n")
    return root


def _remediation(*blocks: tuple) -> dict:
    """`records` output: one block per (file, [(name, line, method)])."""
    return {"mode": "normal", "files": [
        {"file_path": path, "exports": [
            {"name": name, "type": "function", "signature": f"def {name}()", "location": f"{path}:{line}",
             "params": [], "return_type": None, "confidence": "T1" if method == "ast-grep" else "T1-low",
             "extraction_method": method, "ast_node_type": "function_definition" if method == "ast-grep" else None,
             "ast_recipe": "py-def" if method == "ast-grep" else None} for name, line, method in exports]}
        for path, exports in blocks]}


def _records(entries: list, tmp_path: Path | None = None, **kw) -> tuple:
    root = kw.pop("source_root", _tree(tmp_path) if tmp_path is not None else None)
    return mod.gap_records({"mode": "gap-driven", "entries": entries}, kw.pop("provenance", {"entries": []}),
                           source_root=root, **kw)


class TestGapRecords:
    def test_the_drift_gate_lists_every_entry_that_needs_the_tree(self, tmp_path: Path) -> None:
        rescope = {"amendment": {"path": "pkg/x.py"}, "exclude": "pkg/x.py"}
        entries = [
            _gap_entry("GAP-001", "cut", "DELETED_EXPORT", category="missing-export", rescope=rescope),
            _gap_entry("GAP-002", "doc", "NEW_EXPORT", category="provenance-completeness",
                       provenance_completeness=True, match=_found("pkg/api.py", 5)),
            _gap_entry("GAP-003", "fresh", "NEW_EXPORT", category="missing-export", severity="Low"),
            _gap_entry("GAP-004", "search", "MODIFIED_EXPORT", match={**NOT_FOUND, "status": "ambiguous"}),
            _gap_entry("GAP-005", "search", "MOVED_EXPORT", category="provenance-line", match=_found("pkg/api.py", 4)),
            _gap_entry("GAP-006", None, "STRUCTURAL_FIX", category="structural"),
            _gap_entry("GAP-007", None, "metadata update", category="metadata"),
        ]
        records, summary = _records(entries, tmp_path, drift_status="overridden", plan=True)
        assert records is None and summary["status"] == "drift-blocked"
        assert [(b["gap_id"], b["reason"]) for b in summary["drift_blocked"]] == [
            ("GAP-001", mod.DRIFT_RESCOPE), ("GAP-002", mod.DRIFT_COMPLETENESS), ("GAP-003", mod.DRIFT_NOT_IN_MAP),
            ("GAP-004", mod.DRIFT_IN_MAP)]
        # without the new, modified and rescoped entries, the gate passes and the R5 line is checked
        records, summary = _records(entries[4:], tmp_path, drift_status="overridden")
        assert summary["status"] == "written"
        [moved] = records["verification"]
        assert (moved["verification"], moved["unknown_reason"], moved["new_location"]) == \
            ("unknown", "drift-override", None)

    def test_a_rescope_without_its_amendment_is_blocked(self, tmp_path: Path) -> None:
        for rescope in (None, {"exclude": "pkg/x.py"}, {"amendment": {"path": "pkg/x.py"}}):
            entry = _gap_entry("GAP-001", "cut", "DELETED_EXPORT", category="missing-export")
            if rescope is not None:
                entry["rescope"] = rescope
            _, summary = _records([entry], tmp_path)
            assert summary == {"status": "blocked", "rescope_without_amendment": ["cut"]}, rescope

    def test_each_spot_check_maps_to_its_outcome(self, tmp_path: Path) -> None:
        entries = [
            _gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5)),
            _gap_entry("GAP-002", "search", "MODIFIED_EXPORT", match=_found("pkg\\api.py", 4)),
            _gap_entry("GAP-003", "gone", "MODIFIED_EXPORT", match=_found("pkg/gone.py", 5)),
            _gap_entry("GAP-004", "pkg", "MODIFIED_EXPORT", match=_found("pkg/api.py", 1, "module")),
            _gap_entry("GAP-005", "nothing", "MODIFIED_EXPORT", match=_found("pkg/api.py", 1)),
            _gap_entry("GAP-006", "search", "MODIFIED_EXPORT", match={**NOT_FOUND, "status": "ambiguous"}),
        ]
        # each located export (verified or moved) sends its file to §4a for its signature
        _, summary = _records(entries, tmp_path, plan=True)
        assert (summary["reextract"]["entries"], summary["reextract"]["files"]) == ([], ["pkg/api.py"])
        assert [(s["gap_id"], s["file"], s["line"]) for s in summary["reextract"]["signatures"]] == [
            ("GAP-001", "pkg/api.py", 5), ("GAP-002", "pkg/api.py", 5), ("GAP-004", "pkg/api.py", 1)]
        records, summary = _records(entries, tmp_path, remediation=_remediation(("pkg/api.py", [])))
        assert summary["status"] == "written", summary
        assert [(r["verification"], r["new_location"], r["provenance_citation"]) for r in records["verification"]] \
            == [("verified", None, "pkg/api.py:5"), ("moved", "pkg/api.py:5", "pkg/api.py:4"),
                ("missing", None, "pkg/gone.py:5"), ("verified", None, "pkg/api.py:1"),
                ("unknown", None, "unknown"), ("unknown", None, "unknown")]
        assert summary["counts"] == {"verified": 2, "moved": 1, "missing": 1, "re-extracted": 0, "rescoped": 0,
                                     "unknown": 2, "reclassified": 0}

    def test_a_file_no_rule_covers_waits_on_its_declaring_line(self, tmp_path: Path) -> None:
        entry = _gap_entry("GAP-001", "add", "MODIFIED_EXPORT", match=_found("lib.rs", 1))
        records, summary = _records([entry], tmp_path, plan=True)
        assert records is None and summary["needs_judgment"] == [
            {"gap_id": "GAP-001", "name": "add", "needs": ["declaring_line"], "file": "lib.rs", "line": 1}]
        for answer, outcome in ((1, ("verified", None)), (3, ("moved", "lib.rs:3")), (None, ("unknown", None))):
            records, _ = _records([entry], tmp_path, judgments={"GAP-001": {"declaring_line": answer}},
                                  remediation=_remediation(("lib.rs", [])))
            [record] = records["verification"]
            assert (record["verification"], record["new_location"]) == outcome, answer

    def test_without_the_verifier_every_check_is_unknown(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(mod, "_VERIFIER", False)
        records, summary = _records([_gap_entry("GAP-001", "search", "MODIFIED_EXPORT",
                                                match=_found("pkg/api.py", 5))], tmp_path)
        assert records["verification"][0]["verification"] == "unknown"
        assert summary["warnings"] == [mod.VERIFIER_MISSING]

    def test_a_failed_check_is_unknown_for_that_entry_only(self, tmp_path: Path, monkeypatch) -> None:
        """Any verifier error is that entry's `unknown`, with a warning, as a failed definition-lines call was."""
        verifier = mod._verifier()
        real = verifier.definition_lines_report

        def report(path, name, *args):
            if name == "broken":
                raise RuntimeError("cannot parse")
            return real(path, name, *args)

        monkeypatch.setattr(verifier, "definition_lines_report", report)
        records, summary = _records([
            _gap_entry("GAP-001", "broken", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5)),
            _gap_entry("GAP-002", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5)),
        ], tmp_path, remediation=_remediation(("pkg/api.py", [("search", 5, "ast-grep")])))
        assert summary["status"] == "written", summary
        assert [r["verification"] for r in records["verification"]] == ["unknown", "verified"]
        assert summary["warnings"] == ["provenance: spot-check failed for broken: RuntimeError: cannot parse"]

    def test_the_plan_routes_each_uncited_export_by_its_rules(self, tmp_path: Path) -> None:
        entries = [
            # a citation that pins a line never reaches targeted re-extraction
            _gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                       citation={"file": "pkg/api.py", "line": 5}),
            # one that pins none goes on as if it had none: blocking, so re-extracted whatever its paths
            _gap_entry("GAP-002", "absent", "MODIFIED_EXPORT", citation={"file": "pkg/api.py", "line": 2}),
            # rule R3, whatever its severity
            _gap_entry("GAP-003", "doc", "NEW_EXPORT", category="provenance-completeness", severity="Info",
                       provenance_completeness=True, resolved=["pkg/api.py"]),
            # a Medium missing export with a path to scan, and one with none
            _gap_entry("GAP-004", "fresh", "NEW_EXPORT", category="missing-export", severity="Medium",
                       resolved=["pkg/new.py", "pkg/api.py"]),
            _gap_entry("GAP-005", "later", "NEW_EXPORT", category="missing-export", severity="Medium"),
            # any other Medium gap the map lacks
            _gap_entry("GAP-006", "other", "MODIFIED_EXPORT", severity="medium", resolved=["pkg/api.py"]),
        ]
        _, summary = _records(entries, tmp_path, plan=True)
        assert summary["status"] == "planned", summary
        assert [e["gap_id"] for e in summary["reextract"]["entries"]] == ["GAP-002", "GAP-003", "GAP-004"]
        assert summary["reextract"]["files"] == ["pkg/api.py", "pkg/new.py"]
        # with no source root a rule R3 gap is not scanned: nothing proves its line
        _, summary = _records(entries[2:3], source_root=None, plan=True)
        assert summary["reextract"]["entries"] == []

    def test_targeted_reextraction_copies_the_matched_record(self, tmp_path: Path) -> None:
        entries = [
            _gap_entry("GAP-001", "fetch", "NEW_EXPORT", category="missing-export", resolved=["pkg/a.py", "pkg/b.py"]),
            _gap_entry("GAP-002", "store", "MODIFIED_EXPORT", resolved=["pkg/b.py"]),
            _gap_entry("GAP-003", "absent", "NEW_EXPORT", category="missing-export", severity="Low",
                       resolved=["pkg/b.py"]),
        ]
        remediation = _remediation(("pkg/a.py", [("other", 1, "ast-grep")]),
                                   ("pkg/b.py", [("fetch", 4, "ast-grep"), ("store", 9, "source-read")]))
        records, summary = _records(entries, tmp_path, remediation=remediation)
        assert summary["status"] == "needs-judgment"
        assert [(n["gap_id"], n["needs"], n["file"], n["line"]) for n in summary["needs_judgment"]] == [
            ("GAP-001", ["reachability", "docstring"], "pkg/b.py", 4), ("GAP-002", ["docstring"], "pkg/b.py", 9)]
        judgments = {"GAP-001": {"reachability": "public", "docstring": "Fetch."}, "GAP-002": {"docstring": None}}
        records, summary = _records(entries, tmp_path, remediation=remediation, judgments=judgments, tier="Forge")
        assert summary["status"] == "written", summary
        fetch, store, absent = records["verification"]
        assert (fetch["verification"], fetch["new_location"], fetch["resolution_source"], fetch["reachability"]) == \
            ("re-extracted", "pkg/b.py:4", "remediation-paths", "public")
        assert (store["verification"], store["reachability"]) == ("re-extracted", None)
        # a Low missing export found nowhere is unknown, never a halt
        assert absent["verification"] == "unknown"
        [block] = records["files"]
        source = remediation["files"][1]["exports"]
        assert block == {"file_path": "pkg/b.py", "exports": [{**source[0], "docstring": "Fetch."}, source[1]]}
        assert records["files_extracted"] == 2 and records["exports_extracted"] == 3
        assert records["confidence_breakdown"] == {"T1": 1, "T1-low": 1, "unlabeled": 1, "T2": 0}
        assert summary["targeted_reextraction"] == {"resolved_count": 2, "files_scanned": 2,
                                                    "signature_files_scanned": 0, "exports_matched": 2,
                                                    "tier": "Forge"}

    def test_an_unmatched_blocking_entry_is_unresolved(self, tmp_path: Path) -> None:
        entries = [_gap_entry("GAP-001", "absent", "NEW_EXPORT", category="missing-export", resolved=["pkg/b.py"]),
                   _gap_entry("GAP-002", "nothing", "MODIFIED_EXPORT", severity=None)]
        remediation = _remediation(("pkg/b.py", [("fetch", 4, "ast-grep")]))
        records, summary = _records(entries, tmp_path, remediation=remediation)
        assert records is None and summary["status"] == "unresolved"
        assert [(u["gap_id"], u["files_scanned"], u["exports_found_in_scan"]) for u in summary["unresolved"]] == [
            ("GAP-001", 1, 1), ("GAP-002", 0, 0)]

    def test_files_to_match_need_the_remediation_records(self, tmp_path: Path) -> None:
        entry = _gap_entry("GAP-001", "fetch", "NEW_EXPORT", category="missing-export", resolved=["pkg/a.py"])
        with pytest.raises(ValueError, match="--remediation-records"):
            _records([entry], tmp_path)

    def test_an_unreachable_export_is_reclassified(self, tmp_path: Path) -> None:
        entries = [
            _gap_entry("GAP-001", "fetch", "NEW_EXPORT", category="missing-export", resolved=["pkg/b.py"]),
            _gap_entry("GAP-002", "search", "NEW_EXPORT", category="missing-export",
                       citation={"file": "pkg/api.py", "line": 5}),
        ]
        remediation = _remediation(("pkg/b.py", [("fetch", 4, "ast-grep")]))
        judgments = {"GAP-001": {"reachability": "internal-unreachable", "docstring": None},
                     "GAP-002": {"reachability": "public"}}
        records, summary = _records(entries, tmp_path, remediation=remediation, judgments=judgments)
        assert summary["reclassified"] == ["fetch"] and records["files"] == []
        fetch, search = records["verification"]
        assert (fetch["verification"], fetch["reachability"]) == ("re-extracted", "internal-unreachable")
        # §5's summary counts it as reclassified, never as a re-extracted export
        assert (summary["counts"]["re-extracted"], summary["counts"]["verified"], summary["counts"]["reclassified"]) \
            == (0, 1, 1)
        # a pinned cited export the map lacks and the gate passed is T1-low; the reclassified one is unlabeled
        assert (search["verification"], search["provenance_citation"]) == ("verified", "pkg/api.py:5")
        assert records["confidence_breakdown"] == {"T1": 0, "T1-low": 1, "unlabeled": 1, "T2": 0}
        # apply writes the public one and nothing for the internal one
        doc, _ = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                  records=records, test_report_run_id="r", **BLOCK)
        assert [(e["export_name"], e["source_line"]) for e in doc["entries"]] == [("search", 5)]

    # #804, #809: an export a spot-check located goes to §4a's runner for its signature

    @pytest.mark.parametrize("entry", [
        _gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5)),
        _gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                   citation={"file": "pkg/api.py", "line": 5}),
    ], ids=["in-map", "pinned"])
    def test_the_plan_sends_a_located_export_to_4a_for_its_signature(self, tmp_path: Path, entry: dict) -> None:
        _, summary = _records([entry], tmp_path, plan=True, judgments={"GAP-001": {"reachability": "public"}})
        assert summary["status"] == "planned", summary
        assert summary["reextract"] == {"entries": [], "files": ["pkg/api.py"], "signatures": [
            {"gap_id": "GAP-001", "name": "search", "file": "pkg/api.py", "line": 5}]}

    def test_a_located_export_takes_its_signature_from_the_record_at_its_line(self, tmp_path: Path) -> None:
        entries = [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5))]
        remediation = _remediation(("pkg/api.py", [("search", 5, "ast-grep")]))
        remediation["files"][0]["exports"][0].update(params=["q"], public=True)
        records, summary = _records(entries, tmp_path, remediation=remediation)
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert {k: record[k] for k in ("verification", "export_type", "params", "return_type",
                                       "extraction_method")} == \
            {"verification": "verified", "export_type": "function", "params": ["q"], "return_type": None,
             "extraction_method": "ast-grep"}
        # merge documents it from its record, copied less the public mark and with no docstring asked
        source = {k: v for k, v in remediation["files"][0]["exports"][0].items() if k != "public"}
        assert records["files"] == [{"file_path": "pkg/api.py", "exports": [source]}]
        # of several records of its name, the one at its line; an internal export takes none
        remediation = _remediation(("pkg/api.py", [("search", 2, "ast-grep"), ("search", 5, "source-read")]))
        records, _ = _records(entries, tmp_path, remediation=remediation)
        assert records["verification"][0]["extraction_method"] == "source-read"
        internal = [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                               citation={"file": "pkg/api.py", "line": 5})]
        records, summary = _records(internal, tmp_path, remediation=remediation,
                                    judgments={"GAP-001": {"reachability": "internal-unreachable"}})
        assert (records["verification"][0]["export_type"], records["files"]) == (None, [])
        assert summary["reclassified"] == ["search"] and summary["warnings"] == []
        # answered before the plan, it sends no file to §4a
        _, plan = _records(internal, tmp_path, plan=True,
                           judgments={"GAP-001": {"reachability": "internal-unreachable"}})
        assert (plan["reextract"]["files"], plan["reextract"]["signatures"]) == ([], [])

    def test_a_name_the_runner_did_not_report_keeps_a_null_signature(self, tmp_path: Path) -> None:
        entries = [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                              citation={"file": "pkg/api.py", "line": 5})]
        records, summary = _records(entries, tmp_path, remediation=_remediation(("pkg/api.py", [("other", 9,
                                                                                                    "ast-grep")])),
                                    judgments={"GAP-001": {"reachability": "public"}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["export_type"], record.get("params")) == ("verified", None, None)
        assert records["files"] == []
        merge = {"exports": [{"export_name": "search", "export_type": "function", "params": ["z"]}]}
        doc, _ = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                  records=records, merge_records=merge, test_report_run_id="r", **BLOCK)
        [entry] = doc["entries"]
        assert (entry["export_type"], entry["params"], entry["source_line"], entry["signature_source"]) == \
            ("function", ["z"], 5, "T1-low")

    def test_a_citation_of_another_file_than_the_map_entry_takes_no_signature(self, tmp_path: Path) -> None:
        old = {"entries": [_entry("search", "pkg/other.py", 3)]}
        match = {"status": "not-found", "entry": None, "candidates": [
            {"source_file": "pkg/other.py", "source_line": 3, "export_type": "function"}]}
        entries = [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=match,
                              citation={"file": "pkg/api.py", "line": 5})]
        _, plan = _records(entries, tmp_path, provenance=old, plan=True)
        assert (plan["reextract"]["files"], plan["reextract"].get("signatures", [])) == ([], [])
        records, _ = _records(entries, tmp_path, provenance=old)
        [record] = records["verification"]
        assert (record["verification"], record["in_map"], record["export_type"]) == ("verified", True, None)
        merge = {"exports": [{"export_name": "search", "params": ["z"]}]}
        doc, summary = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        merge_records=merge, test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"] and summary["warnings"] == ["provenance: search: verified"]

    def test_a_record_off_its_line_is_not_taken(self, tmp_path: Path) -> None:
        entries = [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5))]
        warning = "provenance: search: located at pkg/api.py:5, but no record of it there; signature not repaired"
        # several records of its name, none at its line; and a lone one at another line (a branch, an overload)
        for found in ([("search", 2, "ast-grep"), ("search", 9, "ast-grep")], [("search", 9, "ast-grep")]):
            records, summary = _records(entries, tmp_path, remediation=_remediation(("pkg/api.py", found)))
            assert (records["verification"][0]["export_type"], records["files"]) == (None, []), found
            assert summary["warnings"] == [warning], found
        # a record with no line is taken
        remediation = _remediation(("pkg/api.py", [("search", 5, "ast-grep")]))
        remediation["files"][0]["exports"][0]["location"] = None
        records, summary = _records(entries, tmp_path, remediation=remediation)
        assert records["verification"][0]["export_type"] == "function" and summary["warnings"] == []

    def test_a_moved_export_takes_the_record_at_its_new_line(self, tmp_path: Path) -> None:
        entries = [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 4))]
        remediation = _remediation(("pkg/api.py", [("search", 4, "ast-grep"), ("search", 5, "ast-grep")]))
        remediation["files"][0]["exports"][0]["params"] = ["old"]
        remediation["files"][0]["exports"][1]["params"] = ["new"]
        records, summary = _records(entries, tmp_path, remediation=remediation, tier="Forge")
        [record] = records["verification"]
        assert (record["verification"], record["new_location"], record["params"]) == ("moved", "pkg/api.py:5", ["new"])
        # §4a's evidence counts the signature file apart from the targeted re-extraction's
        assert summary["targeted_reextraction"] == {"resolved_count": 0, "files_scanned": 0,
                                                    "signature_files_scanned": 1, "exports_matched": 0,
                                                    "tier": "Forge"}

    def test_two_entries_sharing_one_record_leave_one_copy(self, tmp_path: Path) -> None:
        entries = [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5)),
                   _gap_entry("GAP-002", "search", "NEW_EXPORT", category="missing-export", resolved=["pkg/api.py"])]
        remediation = _remediation(("pkg/api.py", [("search", 5, "ast-grep")]))
        judgments = {"GAP-002": {"reachability": "public", "docstring": "Search."}}
        records, summary = _records(entries, tmp_path, remediation=remediation, judgments=judgments)
        assert [r["verification"] for r in records["verification"]] == ["verified", "re-extracted"], summary
        assert records["files"] == [{"file_path": "pkg/api.py", "exports": [
            {**remediation["files"][0]["exports"][0], "docstring": "Search."}]}]

    def test_located_files_need_the_remediation_records(self, tmp_path: Path) -> None:
        entry = _gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5))
        with pytest.raises(ValueError, match="a located export's signature\\): pass --remediation-records"):
            _records([entry], tmp_path)

    def test_an_out_of_root_citation_is_not_located(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        (tmp_path / "outside.py").write_bytes(API_SOURCE)
        for cited in ("../outside.py", str(tmp_path / "outside.py")):
            entries = [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                                  citation={"file": cited, "line": 5})]
            _, plan = _records(entries, source_root=root, plan=True)
            assert (plan["reextract"]["files"], plan["reextract"]["signatures"]) == ([], []), cited
            records, _ = _records(entries, source_root=root, judgments={"GAP-001": {"reachability": "public"}})
            # the verifier reads the file and verifies it; the root guard keeps it from being located
            assert (records["verification"][0]["verification"], records["verification"][0]["export_type"]) == \
                ("verified", None), cited

    # #805: a blocking export the map holds whose entry the rules cannot check stays unchanged, and says what to fix

    HAND_FIX = ("its entry is left unchanged. Fix the entry by hand (set its source_file and source_line to the line "
                "that defines it), then re-run update-skill")
    AMBIGUOUS_FIX = ("its entries are left unchanged. Fix its entries by hand, or give the gap a `file:line` Source at "
                     "its definition when that file holds only one of them, then re-run update-skill")

    @pytest.mark.parametrize("match, outcome, blocking, medium", [
        (_found("pkg/api.py", 1), "unknown",
         f"unknown (no-definition: no line of its file defines it, by the definition-line rules); {HAND_FIX}",
         "unknown (no-definition: no line of its file defines it, by the definition-line rules)"),
        ({"status": "ambiguous", "entry": None, "candidates": [
            {"source_file": "pkg/api.py", "source_line": 1, "export_type": "function"},
            {"source_file": "pkg/other.py", "source_line": 2, "export_type": "function"}]}, "unknown",
         f"unknown (ambiguous: several map entries of its name); {AMBIGUOUS_FIX}",
         "unknown (ambiguous: several map entries of its name)"),
        (_found("pkg/gone.py", 5), "missing", f"missing (its map entry's file pkg/gone.py is gone); {HAND_FIX}",
         "missing"),
    ], ids=["unknown", "ambiguous", "missing"])
    def test_a_blocking_entry_the_rules_cannot_check_is_left_with_what_to_fix(
            self, tmp_path: Path, match: dict, outcome: str, blocking: str, medium: str) -> None:
        old = {"entries": [_entry("nothing", c["source_file"], c["source_line"]) for c in match["candidates"]]}
        entry = _gap_entry("GAP-007", "nothing", "MODIFIED_EXPORT", match=match)
        # no targeted re-extraction and no halt: gap-records writes its outcome and warns nothing itself
        _, plan = _records([entry], tmp_path, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}
        records, summary = _records([entry], tmp_path, provenance=old)
        assert (summary["status"], summary["warnings"]) == ("written", [])
        [record] = records["verification"]
        assert (record["gap_id"], record["verification"]) == ("GAP-007", outcome)
        # apply leaves the map as it was, with one warning: the gap, the export, the outcome, its cause, the fix
        doc, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"] and applied["entries"]["updated"] == []
        assert applied["warnings"] == [f"provenance: nothing (GAP-007): {blocking}"]
        # a Medium gap may stay unknown or missing: its warning names the cause, and no fix
        records, _ = _records([{**entry, "severity": "Medium"}], tmp_path, provenance=old)
        _doc, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                         test_report_run_id="r", **BLOCK)
        assert applied["warnings"] == [f"provenance: nothing: {medium}"]

    def test_each_unknown_records_its_reason(self, tmp_path: Path, monkeypatch) -> None:
        root = _tree(tmp_path)
        (root / "pkg" / "dup.py").write_bytes(b"import os\ndef dup():\n    pass\ndef dup():\n    pass\n")
        no_line = {"status": "found", "entry": {"source_file": "pkg/api.py", "source_line": None,
                                                "export_type": "function"}, "candidates": [{}]}
        entries = [
            _gap_entry("GAP-001", "nothing", "MODIFIED_EXPORT", match=_found("pkg/api.py", 1)),
            _gap_entry("GAP-002", "dup", "MODIFIED_EXPORT", match=_found("pkg/dup.py", 1)),
            _gap_entry("GAP-003", "add", "MODIFIED_EXPORT", match=_found("lib.rs", 3)),
            _gap_entry("GAP-004", "search", "MODIFIED_EXPORT", match=no_line),
            _gap_entry("GAP-005", "search", "MODIFIED_EXPORT", match={**NOT_FOUND, "status": "ambiguous"}),
            _gap_entry("GAP-006", "search", "MODIFIED_EXPORT", match=_found("pkg/api.py", 5)),
        ]
        records, _ = _records(entries, source_root=root, judgments={"GAP-003": {"declaring_line": None}},
                              remediation=_remediation(("pkg/api.py", [("search", 5, "ast-grep")])))
        assert [(r["verification"], r["unknown_reason"]) for r in records["verification"]] == [
            ("unknown", "no-definition"), ("unknown", "several-definitions"), ("unknown", "unchecked-language"),
            ("unknown", "no-line"), ("unknown", "ambiguous"), ("verified", None)]
        records, _ = _records(entries[:1], source_root=None)
        assert records["verification"][0]["unknown_reason"] == "no-source-root"
        monkeypatch.setattr(mod, "_VERIFIER", False)
        records, _ = _records(entries[:1], source_root=root)
        assert records["verification"][0]["unknown_reason"] == "verifier-missing"
        monkeypatch.setattr(mod, "_VERIFIER", None)
        verifier = mod._verifier()
        real = verifier.definition_lines_report

        def broken(*args):
            raise RuntimeError("cannot parse")

        monkeypatch.setattr(verifier, "definition_lines_report", broken)
        records, _ = _records(entries[:1], source_root=root)
        assert records["verification"][0]["unknown_reason"] == "spot-check-failed"
        # a citation check that pins no line routes on: the reason of an outcome it did not keep is not recorded
        monkeypatch.setattr(verifier, "definition_lines_report", real)
        cited = _gap_entry("GAP-007", "fetch", "MODIFIED_EXPORT", citation={"file": "pkg/api.py", "line": 2},
                           resolved=["pkg/b.py"])
        records, _ = _records([cited], source_root=root, judgments={"GAP-007": {"docstring": None}},
                              remediation=_remediation(("pkg/b.py", [("fetch", 4, "ast-grep")])))
        assert (records["verification"][0]["verification"], records["verification"][0]["unknown_reason"]) == \
            ("re-extracted", None)
        # a gap whose only file the brief's scope leaves out
        brief = tmp_path / "skill-brief.yaml"
        brief.write_bytes(b"scope:\n  include:\n    - lib.rs\n")
        records, _ = _records([cited], source_root=root, scope=mod._brief_scope(brief, {"pkg/api.py", "pkg/b.py"}))
        assert (records["verification"][0]["verification"], records["verification"][0]["unknown_reason"]) == \
            ("unknown", "outside-scope")
        assert set(mod.UNKNOWN_REASONS) == {"ambiguous", "no-definition", "several-definitions", "unchecked-language",
                                            "no-line", "spot-check-failed", "verifier-missing", "no-source-root",
                                            "drift-override", "cited-elsewhere", "outside-scope"}

    def test_a_source_at_the_definition_picks_one_of_ambiguous_entries_only_in_a_file_holding_one(
            self, tmp_path: Path) -> None:
        """The ambiguous advice is what a re-run acts on: a `file:line` Source keys skf-parse-gaps' lookup on that
        file, so it picks the one entry the file holds, which the re-run then checks and moves to its definition."""
        old = {"entries": [_entry("search", "pkg/api.py", 1), _entry("search", "pkg/other.py", 2)]}
        cited = {"file": "pkg/api.py", "line": 5}  # API_SOURCE defines search at line 5
        match = parse_gaps.map_match(old["entries"], "search", cited)
        assert match["status"] == "found"
        entry = _gap_entry("GAP-001", "search", "MODIFIED_EXPORT", match=match, citation=cited)
        records, summary = _records([entry], tmp_path, provenance=old,
                                    remediation=_remediation(("pkg/api.py", [("search", 5, "ast-grep")])))
        assert summary["status"] == "written", summary
        assert (records["verification"][0]["verification"], records["verification"][0]["new_location"]) == \
            ("moved", "pkg/api.py:5")
        doc, _ = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                  test_report_run_id="r", **BLOCK)
        assert [(e["source_file"], e["source_line"]) for e in doc["entries"]] == [("pkg/api.py", 5), ("pkg/other.py", 2)]
        # two entries in the cited file, neither at its line: still ambiguous, so only a hand fix helps
        same_file = [_entry("search", "pkg/api.py", 1), _entry("search", "pkg/api.py", 3)]
        assert parse_gaps.map_match(same_file, "search", cited)["status"] == "ambiguous"

    # #807: a gap naming a renamed re-export by its public name matches the record of its declaration, and the map
    # holds it under its declared name, re-exported as the public one

    def test_a_gap_naming_a_renamed_reexport_matches_its_declaration(self, tmp_path: Path) -> None:
        root = _tree(tmp_path)
        (root / "store").mkdir()
        (root / "store" / "mock.ts").write_bytes(b"// a store for tests\n\nexport class MockUniversalStore {}\n")
        extraction = {"exports": [_runner("MockUniversalStore", "store/mock.ts", 3, language="typescript",
                                          export_type="class", node="class_declaration")],
                      "entry_point_diff": {"public": [
                          {"name": "experimental_MockUniversalStore", "local": "MockUniversalStore",
                           "file": "store/mock.ts", "via": "re-export"}]}}
        remediation, _ = mod.build_records(extraction, None, ["store/mock.ts"], [])
        [declared] = remediation["files"][0]["exports"]
        assert (declared["name"], declared["aliases"]) == ("MockUniversalStore", ["experimental_MockUniversalStore"])
        public = "experimental_MockUniversalStore"
        entries = [_gap_entry("GAP-001", public, "NEW_EXPORT", category="missing-type", resolved=["store/mock.ts"])]
        records, summary = _records(entries, source_root=root, remediation=remediation,
                                    judgments={"GAP-001": {"reachability": "public", "docstring": None}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["export_name"], record["verification"], record["new_location"]) == \
            (public, "re-extracted", "store/mock.ts:3")
        # the copy is documented under the public name, its declared one as `local`, and carries no aliases
        [block] = records["files"]
        assert block["file_path"] == "store/mock.ts"
        [copied] = block["exports"]
        assert copied == {"name": public, "local": "MockUniversalStore",
                          **{k: v for k, v in declared.items() if k not in ("name", "aliases")}}
        assert list(copied)[:2] == ["name", "local"]
        # apply maps it as the project records a barrel rename: its declared name at its line, re-exported as the
        # public one, which metadata.json's exports[] lists
        doc, applied = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                        records=records, test_report_run_id="r", metadata={"exports": []}, **BLOCK)
        [entry] = doc["entries"]
        assert {k: entry[k] for k in ("export_name", "reexported_as", "export_type", "source_file", "source_line")} \
            == {"export_name": "MockUniversalStore", "reexported_as": public, "export_type": "class",
                "source_file": "store/mock.ts", "source_line": 3}
        assert list(entry)[:2] == ["export_name", "reexported_as"]
        assert applied["lists"]["exports"] == [public] and applied["warnings"] == []
        assert stats.check_label_agreement(doc) == []
        # Check D passes on the written entry: its line defines its name, and exports[] and the map name one export
        verifier = mod._verifier()
        report = verifier.verify({"exports": [public]}, doc, root)
        assert (report["status"], report["missing"], report["orphaned"], report["stale"]) == ("pass", [], [], [])
        # a second repair of the same gap finds the entry through its reexported_as and checks it `verified`
        match = parse_gaps.map_match(doc["entries"], public, None)
        assert (match["status"], match["entry"]["export_name"]) == ("found", "MockUniversalStore")
        again = [_gap_entry("GAP-001", public, "NEW_EXPORT", category="missing-type", match=match,
                            resolved=["store/mock.ts"])]
        records, summary = _records(again, source_root=root, provenance=doc, remediation=remediation,
                                    judgments={"GAP-001": {"reachability": "public"}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["map_entry"], record["export_type"]) == \
            ("verified", {"source_file": "store/mock.ts", "source_line": 3}, "class")
        assert records["confidence_breakdown"]["T1"] == 1
        redone, applied = mod.apply_update(update_type="gap-driven", provenance=doc, skill_name="lib",
                                           records=records, test_report_run_id="r", **BLOCK)
        assert redone["entries"] == doc["entries"] and applied["warnings"] == []

    def test_an_export_of_the_exact_name_wins_over_an_alias(self, tmp_path: Path) -> None:
        remediation = _remediation(("pkg/a.py", [("Foo", 2, "ast-grep")]),
                                   ("pkg/b.py", [("Baz", 3, "ast-grep"), ("Bar", 4, "ast-grep")]))
        for block in remediation["files"]:
            block["exports"][0]["aliases"] = ["Bar"]  # Foo and Baz are re-exported as Bar, ahead of Bar itself
        remediation["files"][1]["exports"][1]["aliases"] = ["Qux"]
        entries = [_gap_entry("GAP-001", "Bar", "MODIFIED_EXPORT", resolved=["pkg/a.py", "pkg/b.py"])]
        records, summary = _records(entries, tmp_path, remediation=remediation,
                                    judgments={"GAP-001": {"docstring": None}})
        assert summary["status"] == "written", summary
        assert records["verification"][0]["new_location"] == "pkg/b.py:4"
        # the copy of an exact match carries no aliases either
        exact = {k: v for k, v in remediation["files"][1]["exports"][1].items() if k != "aliases"}
        assert records["files"] == [{"file_path": "pkg/b.py", "exports": [exact]}]

    # #824: oms-storybook's GAP-002 cites Angular's `__definePreview`, which its entry points re-export as
    # `definePreview`, while the map holds `definePreview` at react-vite's file: the cited file is another package's,
    # so the gap is never re-extracted there and apply says what to fix

    ANGULAR = "angular/src/client/preview.ts"
    REACT_VITE = "react-vite/src/index.ts"

    def _storybook(self, tmp_path: Path) -> tuple[Path, dict, dict]:
        """(the source root, `records`' output over Angular's file, the citation of its line 45)."""
        root = tmp_path / "storybook"
        (root / "angular" / "src" / "client").mkdir(parents=True)
        (root / "angular" / "src" / "client" / "preview.ts").write_bytes(
            ("// Angular's preview annotations\n" + "\n" * 43
             + "export function __definePreview(input: AngularInput): AngularPreview {\n  return input;\n}\n").encode())
        (root / "react-vite" / "src").mkdir(parents=True)
        (root / "react-vite" / "src" / "index.ts").write_bytes(
            b"// @storybook/react-vite\nexport function definePreview(input: ReactInput): ReactPreview {\n"
            b"  return input;\n}\n")
        extraction = {"exports": [_runner("__definePreview", self.ANGULAR, 45, language="typescript",
                                          node="function_declaration", return_type="AngularPreview")],
                      "entry_point_diff": {"public": [
                          {"name": "definePreview", "local": "__definePreview", "file": self.ANGULAR,
                           "via": "re-export"}]}}
        remediation, _ = mod.build_records(extraction, None, [self.ANGULAR], [])
        assert remediation["files"][0]["exports"][0]["aliases"] == ["definePreview"]
        return root, remediation, {"file": self.ANGULAR, "line": 45}

    def _elsewhere(self, name: str = "definePreview", change: str = "MODIFIED_EXPORT", **extra) -> dict:
        """GAP-002 as translate writes it, its map_match looked up in `old` at `cited`."""
        old, cited = extra.pop("old"), extra.pop("cited")
        return _gap_entry("GAP-002", name, change, match=parse_gaps.map_match(old["entries"], name, cited),
                          citation=cited, **extra)

    FIX = ("When the map is right, re-run Test Skill, since the test compared another file's declaration, and if the "
           "gap comes back, exclude the cited file in the brief's scope when the skill does not cover it; ")

    @pytest.mark.parametrize("severity", ["Critical", "Medium"], ids=["blocking", "non-blocking"])
    @pytest.mark.parametrize("change, category", [("MODIFIED_EXPORT", "signature-mismatch"),
                                                  ("NEW_EXPORT", "missing-export")], ids=["modified", "missing-export"])
    def test_a_gap_citing_another_file_than_the_map_is_never_reextracted(self, tmp_path: Path, change: str,
                                                                         category: str, severity: str) -> None:
        root, remediation, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        match = parse_gaps.map_match(old["entries"], "definePreview", cited)
        assert (match["status"], [c["source_file"] for c in match["candidates"]]) == ("not-found", [self.REACT_VITE])
        entries = [self._elsewhere(change=change, old=old, cited=cited, category=category, severity=severity,
                                   resolved=[self.ANGULAR])]
        # the plan sends nothing to §4a: no entry, no file and no signature
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}
        # the record is unknown for that cause, keeps its check's own and where the map holds the name, and copies no
        # record of Angular's declaration for merge to document
        records, summary = _records(entries, source_root=root, provenance=old, remediation=remediation,
                                    judgments={"GAP-002": {"docstring": None, "reachability": "public"}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["in_map"], record["new_location"]) == \
            ("unknown", "cited-elsewhere", True, None)
        assert (record["citation_check"], record["map_locations"]) == ("no-definition", [f"{self.REACT_VITE}:2"])
        assert (record["export_type"], record["params"], record["extraction_method"]) == (None, None, None)
        assert records["files"] == [] and summary["targeted_reextraction"] is None
        # apply adds no entry and changes none, whatever the severity: it warns with the gap, the cited file and its
        # check's cause, the map's location and the fix for each side that may be wrong
        doc, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"]
        assert (applied["entries"]["added"], applied["entries"]["updated"]) == ([], [])
        assert applied["warnings"] == [
            "provenance: definePreview (GAP-002): unknown (cited-elsewhere: the gap cites another file than the "
            "provenance map's entries of its name; it cites angular/src/client/preview.ts:45; its check there: "
            "no-definition (no line of its file defines it, by the definition-line rules); the map holds it at "
            "react-vite/src/index.ts:2); its entry is left unchanged, and nothing is re-extracted for it. "
            f"{self.FIX}when the export moved, fix the map entry by hand (set its source_file and source_line to the "
            "line that defines it), then re-run update-skill"]

    def test_a_gap_citing_a_gone_file_names_its_check(self, tmp_path: Path) -> None:
        root, _, _ = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        entries = [self._elsewhere(old=old, cited={"file": "angular/src/client/gone.ts", "line": 45},
                                   severity="Critical")]
        records, _ = _records(entries, source_root=root, provenance=old)
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["citation_check"]) == \
            ("unknown", "cited-elsewhere", "missing")
        _, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                      test_report_run_id="r", **BLOCK)
        [warning] = applied["warnings"]
        assert "; it cites angular/src/client/gone.ts:45; its check there: missing (no such file); " in warning
        # a file that is gone takes no scope advice: there is nothing to exclude
        assert "since the test compared another file's declaration; when the export moved" in warning
        assert "exclude the cited file" not in warning

    def test_a_name_the_map_reexports_from_two_files_lists_both(self, tmp_path: Path) -> None:
        root, _, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("__x", self.REACT_VITE, 2, reexported_as="definePreview"),
                           _entry("__x", "vue3-vite/src/index.ts", 7, reexported_as="definePreview")]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical", resolved=[self.ANGULAR])]
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}
        records, _ = _records(entries, source_root=root, provenance=old)
        [record] = records["verification"]
        assert record["map_locations"] == [f"{self.REACT_VITE}:2", "vue3-vite/src/index.ts:7"]
        doc, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"]
        [warning] = applied["warnings"]
        assert "; the map holds it at react-vite/src/index.ts:2, vue3-vite/src/index.ts:7); its entries are left " \
            f"unchanged, and nothing is re-extracted for it. {self.FIX}when an export moved, fix by " \
            "hand whichever of those entries moved (" in warning

    def test_a_placeholder_entry_of_the_name_routes_as_before(self, tmp_path: Path) -> None:
        """A merge-records entry with no file holds the name nowhere: the gap is re-extracted, as before #824."""
        root, remediation, cited = self._storybook(tmp_path)
        old = {"entries": [{"export_name": "definePreview", "export_type": "function", "source_library": "lib",
                            "confidence": "T1-low", "extraction_method": "source-read", "signature_source": "T1-low"}]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical", resolved=[self.ANGULAR])]
        assert (entries[0]["map_match"]["status"], len(entries[0]["map_match"]["candidates"])) == ("not-found", 1)
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert [e["gap_id"] for e in plan["reextract"]["entries"]] == ["GAP-002"]
        records, _ = _records(entries, source_root=root, provenance=old, remediation=remediation,
                              judgments={"GAP-002": {"docstring": None}})
        [record] = records["verification"]
        assert (record["verification"], record.get("citation_check"), record.get("map_locations")) == \
            ("re-extracted", None, None)

    def test_a_map_entry_with_a_file_and_no_line_holds_the_name_at_its_file(self, tmp_path: Path) -> None:
        root, _, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, None)]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical", resolved=[self.ANGULAR])]
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}
        records, _ = _records(entries, source_root=root, provenance=old)
        [record] = records["verification"]
        assert record["map_locations"] == [self.REACT_VITE]
        _, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                      test_report_run_id="r", **BLOCK)
        [warning] = applied["warnings"]
        assert "; the map holds it at react-vite/src/index.ts); its entry is left unchanged" in warning

    def test_a_third_remediation_file_is_not_scanned_either(self, tmp_path: Path) -> None:
        """Re-extraction reads the Remediation's resolved_paths, not the cited file: neither is scanned."""
        root, _, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical", resolved=["shared/src/preview.ts"])]
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}

    def test_a_check_that_read_nothing_says_how_to_read_it(self, tmp_path: Path) -> None:
        """With no source tree nothing was read at the cited file, so the test's comparison is not in question."""
        _, _, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical", resolved=[self.ANGULAR])]
        records, _ = _records(entries, source_root=None, provenance=old)
        [record] = records["verification"]
        assert (record["unknown_reason"], record["citation_check"]) == ("cited-elsewhere", "no-source-root")
        _, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                      test_report_run_id="r", **BLOCK)
        [warning] = applied["warnings"]
        assert warning.endswith("its entry is left unchanged, and nothing is re-extracted for it. Nothing was read at "
                                "the cited file: give update-skill the source tree, then re-run update-skill")
        assert "another file's declaration" not in warning

    def test_the_drift_gate_counts_a_citation_of_another_file_as_held(self, tmp_path: Path) -> None:
        root, _, cited = self._storybook(tmp_path)
        held = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        placeholder = {"entries": [{"export_name": "definePreview", "export_type": "function"}]}
        entries = [self._elsewhere(old=held, cited=cited, severity="Critical"),
                   {**self._elsewhere(old=placeholder, cited=cited, severity="Critical"), "gap_id": "GAP-003"}]
        records, summary = _records(entries, source_root=root, provenance=held, drift_status="overridden", plan=True)
        assert records is None and summary["status"] == "drift-blocked"
        assert [(b["gap_id"], b["reason"]) for b in summary["drift_blocked"]] == [
            ("GAP-002", mod.DRIFT_IN_MAP), ("GAP-003", mod.DRIFT_NOT_IN_MAP)]

    def test_a_provenance_completeness_gap_citing_another_file_is_not_reextracted(self, tmp_path: Path) -> None:
        """Rule R3's exception: the map holds the name at another file, so its provenance is not absent."""
        root, remediation, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        entries = [self._elsewhere(change="NEW_EXPORT", old=old, cited=cited, category="provenance-completeness",
                                   severity="Info", provenance_completeness=True, resolved=[self.ANGULAR])]
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}
        records, _ = _records(entries, source_root=root, provenance=old, remediation=remediation)
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"]) == ("unknown", "cited-elsewhere")

    def test_a_gap_citing_a_file_when_the_map_lacks_its_name_is_still_reextracted(self, tmp_path: Path) -> None:
        root, remediation, cited = self._storybook(tmp_path)
        match = parse_gaps.map_match([], "definePreview", cited)
        assert (match["status"], match["candidates"]) == ("not-found", [])
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical", match=match,
                              citation=cited, resolved=[self.ANGULAR])]
        _, plan = _records(entries, source_root=root, plan=True)
        assert ([e["gap_id"] for e in plan["reextract"]["entries"]], plan["reextract"]["files"]) == \
            (["GAP-002"], [self.ANGULAR])
        records, summary = _records(entries, source_root=root, remediation=remediation,
                                    judgments={"GAP-002": {"docstring": None}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["in_map"], record["new_location"]) == \
            ("re-extracted", False, f"{self.ANGULAR}:45")
        doc, _ = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                  records=records, test_report_run_id="r", **BLOCK)
        [entry] = doc["entries"]
        assert (entry["export_name"], entry["reexported_as"], entry["source_file"], entry["source_line"]) == \
            ("__definePreview", "definePreview", self.ANGULAR, 45)

    def test_a_gap_citing_the_maps_own_line_is_checked_there(self, tmp_path: Path) -> None:
        root, _, _ = self._storybook(tmp_path)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        cited = {"file": self.REACT_VITE, "line": 2}
        match = parse_gaps.map_match(old["entries"], "definePreview", cited)
        assert match["status"] == "found"
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical", match=match,
                              citation=cited, resolved=[self.ANGULAR])]
        _, plan = _records(entries, source_root=root, provenance=old, plan=True)
        assert plan["reextract"] == {"entries": [], "files": [self.REACT_VITE], "signatures": [
            {"gap_id": "GAP-002", "name": "definePreview", "file": self.REACT_VITE, "line": 2}]}
        records, summary = _records(entries, source_root=root, provenance=old, remediation=_remediation(
            (self.REACT_VITE, [("definePreview", 2, "ast-grep")])))
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["map_entry"], record["extraction_method"]) \
            == ("verified", None, {"source_file": self.REACT_VITE, "source_line": 2}, "ast-grep")

    # #824, the rest: the brief's scope is the repair's boundary. oms-storybook's brief takes react-vite's package and
    # not Angular's or Vue's, so a gap citing Vue's own `definePreview`, or naming only Angular's file for a name the map
    # lacks, is never checked, scanned or repaired there; a file the scope takes repairs as before

    VUE = "vue3-vite/src/preview.ts"
    OUTSIDE = ("outside-scope: the brief's scope leaves out a file the gap cites or its Remediation names, so the "
               "export is not read there")

    def _scope(self, tmp_path: Path, include: list, exclude: tuple = (), cited: frozenset = frozenset()):
        """The scope of a skill brief that includes and excludes these patterns, as gap-records loads it."""
        brief = tmp_path / "brief" / "skill-brief.yaml"
        brief.parent.mkdir(exist_ok=True)
        lines = ["name: oms-storybook-react-vite", "scope:", "  include:" + ("" if include else " []"),
                 *[f"    - '{p}'" for p in include], "  exclude:" + ("" if exclude else " []"),
                 *[f"    - '{p}'" for p in exclude]]
        brief.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        return mod._brief_scope(brief, cited)

    def _vue(self, root: Path) -> dict:
        """Vue's own `definePreview`, which declares the name itself: the citation of its line 7."""
        (root / "vue3-vite" / "src").mkdir(parents=True)
        (root / "vue3-vite" / "src" / "preview.ts").write_bytes(
            b"// @storybook/vue3-vite\n" + b"\n" * 5 + b"export function definePreview(input: VueInput): VuePreview {\n"
            b"  return input;\n}\n")
        return {"file": self.VUE, "line": 7}

    def test_a_citation_outside_the_brief_scope_of_a_name_the_map_holds_is_cited_elsewhere(
            self, tmp_path: Path) -> None:
        root, _, _ = self._storybook(tmp_path)
        cited = self._vue(root)
        old = {"entries": [_entry("definePreview", self.REACT_VITE, 2)]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical", resolved=[self.VUE])]
        # with no brief, the check finds Vue's own declaration there: verified, as 5.0.0 did
        records, _ = _records(entries, source_root=root, provenance=old)
        assert (records["verification"][0]["verification"], records["verification"][0]["outside_scope"]) == \
            ("verified", None)
        scope = self._scope(tmp_path, ["react-vite/**"])
        _, plan = _records(entries, source_root=root, provenance=old, plan=True, scope=scope)
        assert plan["reextract"] == {"entries": [], "files": [], "signatures": []}
        records, summary = _records(entries, source_root=root, provenance=old, scope=scope)
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["citation_check"], record["map_locations"],
                record["outside_scope"]) == ("unknown", "cited-elsewhere", "outside-scope", [f"{self.REACT_VITE}:2"],
                                             [self.VUE])
        assert (record["map_entry"], record["extraction_method"], records["files"]) == (None, None, [])
        doc, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"]
        assert (applied["entries"]["added"], applied["entries"]["updated"]) == ([], [])
        assert applied["warnings"] == [
            "provenance: definePreview (GAP-002): unknown (cited-elsewhere: the gap cites another file than the "
            "provenance map's entries of its name; it cites vue3-vite/src/preview.ts:7; its check there: outside-scope "
            "(not run: the brief's scope leaves it out); the map holds it at react-vite/src/index.ts:2); its entry is "
            "left unchanged, and nothing is re-extracted for it. When the map is right, re-run Test Skill, since the "
            "test compared another file's declaration; when the export moved there, change the brief's scope so it "
            "takes that file (its scope.include or scope.exclude) and fix the map entry by hand (set its source_file "
            "and source_line to the line that defines it), then re-run update-skill"]

    def test_a_same_package_citation_in_the_brief_scope_is_still_verified(self, tmp_path: Path) -> None:
        """useParameter: the map holds the re-export at preview-api/index.ts, the gap cites its definition in
        hooks.ts, and the brief's scope takes both, so the check runs and the repair goes on as before."""
        root = tmp_path / "storybook"
        (root / "preview-api" / "modules" / "addons").mkdir(parents=True)
        (root / "preview-api" / "index.ts").write_bytes(b"// preview-api\n" * 10 + b"export { useParameter } from "
                                                        b"'./modules/addons/hooks';\n")
        (root / "preview-api" / "modules" / "addons" / "hooks.ts").write_bytes(
            b"// hooks\n\nexport function useParameter(parameterKey: string, defaultValue?: unknown): unknown {\n"
            b"  return defaultValue;\n}\n")
        old = {"entries": [_entry("useParameter", "preview-api/index.ts", 11)]}
        cited = {"file": "preview-api/modules/addons/hooks.ts", "line": 3}
        entries = [self._elsewhere(name="useParameter", old=old, cited=cited, severity="Critical")]
        assert entries[0]["map_match"]["status"] == "not-found"
        records, summary = _records(entries, source_root=root, provenance=old,
                                    scope=self._scope(tmp_path, ["preview-api/**"]))
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["in_map"], record["outside_scope"]) == \
            ("verified", None, True, None)
        doc, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                        test_report_run_id="r", **BLOCK)
        assert doc["entries"] == old["entries"] and applied["warnings"] == ["provenance: useParameter: verified"]

    @pytest.mark.parametrize("severity", ["Critical", "Medium"], ids=["blocking", "non-blocking"])
    @pytest.mark.parametrize("change, category", [("MODIFIED_EXPORT", "signature-mismatch"),
                                                  ("NEW_EXPORT", "missing-export")], ids=["modified", "missing-export"])
    def test_a_gap_the_map_lacks_is_not_reextracted_outside_the_brief_scope(self, tmp_path: Path, change: str,
                                                                            category: str, severity: str) -> None:
        root, remediation, cited = self._storybook(tmp_path)
        match = parse_gaps.map_match([], "definePreview", cited)
        entries = [_gap_entry("GAP-002", "definePreview", change, category=category, severity=severity, match=match,
                              citation=cited, resolved=[self.ANGULAR])]
        scope = self._scope(tmp_path, ["react-vite/**"])
        # the plan sends nothing to §4a, and the records are written, not unresolved, whatever the severity
        _, plan = _records(entries, source_root=root, plan=True, scope=scope)
        assert (plan["status"], plan["reextract"]) == ("planned", {"entries": [], "files": [], "signatures": []})
        records, summary = _records(entries, source_root=root, remediation=remediation, scope=scope,
                                    judgments={"GAP-002": {"docstring": None, "reachability": "public"}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["in_map"], record["outside_scope"]) == \
            ("unknown", "outside-scope", False, [self.ANGULAR])
        assert (record["citation_check"], record["map_locations"], record["new_location"]) == (None, None, None)
        assert records["files"] == [] and summary["targeted_reextraction"] is None
        # apply never refuses it and adds no entry, a placeholder from merge's records included: one warning
        merge = {"exports": [{"export_name": "definePreview", "export_type": "function", "params": ["input"]}]}
        doc, applied = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                        records=records, merge_records=merge, test_report_run_id="r", **BLOCK)
        assert applied["status"] == "written" and doc["entries"] == [] and applied["entries"]["added"] == []
        assert applied["warnings"] == [
            f"provenance: definePreview (GAP-002): unknown ({self.OUTSIDE}; left out: angular/src/client/preview.ts); "
            "nothing is added or re-extracted for it. When the skill covers that file, change the brief's scope so it "
            "takes it (its scope.include or scope.exclude), then re-run update-skill; otherwise re-run Test Skill, "
            "since the test compared a declaration the skill does not cover"]

    @pytest.mark.parametrize("citation", [False, True], ids=["no-citation", "cited-outside"])
    def test_a_remediation_file_outside_the_scope_is_not_scanned(self, tmp_path: Path, citation: bool) -> None:
        root, angular, cited = self._storybook(tmp_path)
        (root / "react-vite" / "src" / "preview.ts").write_bytes(
            b"// @storybook/react-vite preview\nexport function definePreview(input: ReactInput): ReactPreview {\n"
            b"  return input;\n}\n")
        own = "react-vite/src/preview.ts"
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical",
                              citation=cited if citation else None, resolved=[own, self.ANGULAR])]
        scope = self._scope(tmp_path, ["react-vite/**"])
        _, plan = _records(entries, source_root=root, plan=True, scope=scope)
        assert plan["reextract"]["files"] == [own]
        assert [(e["gap_id"], e["resolved_paths"]) for e in plan["reextract"]["entries"]] == [("GAP-002", [own])]
        # Angular's block, which re-exports its `__definePreview` as `definePreview`, is not matched even when given
        remediation = _remediation((own, [("definePreview", 2, "ast-grep")]))
        remediation["files"] += angular["files"]
        records, summary = _records(entries, source_root=root, remediation=remediation, scope=scope,
                                    judgments={"GAP-002": {"docstring": None}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        # the record still names the file the scope left out, whatever its outcome
        assert (record["verification"], record["new_location"], record["unknown_reason"], record["outside_scope"]) \
            == ("re-extracted", f"{own}:2", None, [self.ANGULAR])
        assert [block["file_path"] for block in records["files"]] == [own]

    @pytest.mark.parametrize("include", [["**"], []], ids=["include-all", "empty-include"])
    def test_an_exclude_puts_a_file_outside_the_scope(self, tmp_path: Path, include: list) -> None:
        root, remediation, cited = self._storybook(tmp_path)
        scope = self._scope(tmp_path, include, ("angular/**",), cited=frozenset({self.ANGULAR, self.REACT_VITE}))
        assert (scope.takes(self.REACT_VITE), scope.takes(self.ANGULAR)) == (True, False)
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical", citation=cited,
                              resolved=[self.ANGULAR])]
        records, summary = _records(entries, source_root=root, remediation=remediation, scope=scope)
        assert summary["status"] == "written", summary
        assert [(r["verification"], r["unknown_reason"], r["outside_scope"]) for r in records["verification"]] == \
            [("unknown", "outside-scope", [self.ANGULAR])]

    @pytest.mark.parametrize("severity, unscoped_status", [("Critical", "unresolved"), ("Medium", "written")],
                             ids=["blocking", "non-blocking"])
    def test_an_in_scope_scan_with_no_match_and_a_left_out_file_is_unknown(self, tmp_path: Path, severity: str,
                                                                          unscoped_status: str) -> None:
        root, _, _ = self._storybook(tmp_path)
        (root / "react-vite" / "src" / "types.ts").write_bytes(b"export type ReactRenderer = unknown;\n")
        types = "react-vite/src/types.ts"
        entries = [_gap_entry("GAP-002", "definePreview", "NEW_EXPORT", category="missing-export", severity=severity,
                              resolved=[types, self.ANGULAR])]
        remediation = _remediation((types, [("ReactRenderer", 1, "ast-grep")]))
        # with no brief, the same scan of both files finds nothing in the given blocks: a Critical gap is unresolved
        # and a Medium one unknown, as before
        _, unscoped = _records(entries, source_root=root, remediation=remediation)
        assert unscoped["status"] == unscoped_status, unscoped
        scope = self._scope(tmp_path, ["react-vite/**"])
        _, plan = _records(entries, source_root=root, plan=True, scope=scope)
        assert plan["reextract"]["files"] == [types]
        records, summary = _records(entries, source_root=root, remediation=remediation, scope=scope)
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["outside_scope"]) == \
            ("unknown", "outside-scope", [self.ANGULAR])
        assert summary["targeted_reextraction"]["files_scanned"] == 1
        # apply adds no entry, a placeholder from merge's records included
        merge = {"exports": [{"export_name": "definePreview", "export_type": "function", "params": ["input"]}]}
        doc, applied = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                        records=records, merge_records=merge, test_report_run_id="r", **BLOCK)
        assert doc["entries"] == [] and applied["entries"]["added"] == [] and len(applied["warnings"]) == 1
        assert applied["warnings"][0].startswith(
            f"provenance: definePreview (GAP-002): unknown ({self.OUTSIDE}; left out: {self.ANGULAR}); ")

    def test_the_warning_names_each_left_out_file(self, tmp_path: Path) -> None:
        root, _, _ = self._storybook(tmp_path)
        self._vue(root)
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical",
                              resolved=[self.ANGULAR, self.VUE])]
        records, _ = _records(entries, source_root=root, scope=self._scope(tmp_path, ["react-vite/**"]))
        _, applied = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                      records=records, test_report_run_id="r", **BLOCK)
        assert applied["warnings"] == [
            f"provenance: definePreview (GAP-002): unknown ({self.OUTSIDE}; left out: {self.ANGULAR}, {self.VUE}); "
            "nothing is added or re-extracted for it. When the skill covers one of those files, change the brief's "
            "scope so it takes it (its scope.include or scope.exclude), then re-run update-skill; otherwise re-run "
            "Test Skill, since the test compared a declaration the skill does not cover"]

    def test_a_citation_outside_the_scope_of_a_name_the_map_holds_at_two_files(self, tmp_path: Path) -> None:
        root, _, _ = self._storybook(tmp_path)
        cited = self._vue(root)
        old = {"entries": [_entry("__x", self.REACT_VITE, 2, reexported_as="definePreview"),
                           _entry("__x", "react/src/index.ts", 7, reexported_as="definePreview")]}
        entries = [self._elsewhere(old=old, cited=cited, severity="Critical")]
        records, _ = _records(entries, source_root=root, provenance=old,
                              scope=self._scope(tmp_path, ["react-vite/**", "react/**"]))
        _, applied = mod.apply_update(update_type="gap-driven", provenance=old, skill_name="lib", records=records,
                                      test_report_run_id="r", **BLOCK)
        assert applied["warnings"] == [
            "provenance: definePreview (GAP-002): unknown (cited-elsewhere: the gap cites another file than the "
            "provenance map's entries of its name; it cites vue3-vite/src/preview.ts:7; its check there: outside-scope "
            "(not run: the brief's scope leaves it out); the map holds it at react-vite/src/index.ts:2, "
            "react/src/index.ts:7); its entries are left unchanged, and nothing is re-extracted for it. When the map is "
            "right, re-run Test Skill, since the test compared another file's declaration; when an export moved there, "
            "change the brief's scope so it takes that file (its scope.include or scope.exclude) and fix by hand "
            "whichever of those entries moved (set its source_file and source_line to the line that defines it), then "
            "re-run update-skill"]

    def test_a_file_the_map_tracks_is_in_scope(self, tmp_path: Path) -> None:
        """Category A takes each file the map tracks whatever the scope says: a gap on a new name there repairs."""
        root, angular, cited = self._storybook(tmp_path)
        old = {"entries": [_entry("__other", self.ANGULAR, 1)]}
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical",
                              match=parse_gaps.map_match(old["entries"], "definePreview", None),
                              resolved=[self.ANGULAR])]
        _, plan = _records(entries, source_root=root, provenance=old, plan=True,
                           scope=self._scope(tmp_path, ["react-vite/**"]))
        assert plan["reextract"]["files"] == [self.ANGULAR]
        records, summary = _records(entries, source_root=root, provenance=old, remediation=angular,
                                    scope=self._scope(tmp_path, ["react-vite/**"]),
                                    judgments={"GAP-002": {"docstring": None}})
        assert summary["status"] == "written", summary
        assert [(r["verification"], r["outside_scope"]) for r in records["verification"]] == [("re-extracted", None)]

    @pytest.mark.parametrize("form", ["dotted", "absolute"])
    def test_a_path_is_read_relative_to_the_source_root(self, tmp_path: Path, form: str) -> None:
        """A `..` part cannot pass a lexical include glob, and an absolute path under the root is tested by its
        relative one."""
        root, _, _ = self._storybook(tmp_path)
        self._vue(root)
        path = "react-vite/../vue3-vite/src/preview.ts" if form == "dotted" else (root / self.REACT_VITE).as_posix()
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical", resolved=[path])]
        _, plan = _records(entries, source_root=root, plan=True, scope=self._scope(tmp_path, ["react-vite/**"]))
        assert plan["reextract"]["files"] == ([] if form == "dotted" else [path])

    def test_a_check_at_an_in_scope_citation_that_read_nothing_says_how_to_read_it(self, tmp_path: Path) -> None:
        """No source tree: the cited file the scope takes was never read, so the warning gives the check's fix, not
        the scope's."""
        root, _, _ = self._storybook(tmp_path)
        cited = {"file": self.REACT_VITE, "line": 2}
        entries = [_gap_entry("GAP-002", "definePreview", "MODIFIED_EXPORT", severity="Critical", citation=cited,
                              resolved=[self.ANGULAR])]
        records, summary = _records(entries, source_root=None, scope=self._scope(tmp_path, ["react-vite/**"]))
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["unknown_reason"], record["citation_check"], record["outside_scope"]) \
            == ("unknown", "outside-scope", "no-source-root", [self.ANGULAR])
        _, applied = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                      records=records, test_report_run_id="r", **BLOCK)
        assert applied["warnings"] == [
            f"provenance: definePreview (GAP-002): unknown ({self.OUTSIDE}; left out: {self.ANGULAR}; it cites "
            "react-vite/src/index.ts:2; its check there: no-source-root (no source tree to check)); nothing is added or "
            "re-extracted for it. Nothing was read at the cited file: give update-skill the source tree, then re-run "
            "update-skill"]
        # a check that read the file and found no definition there keeps its cause beside the scope's fix
        (root / "react-vite" / "src" / "types.ts").write_bytes(b"export type ReactRenderer = unknown;\n")
        entries = [{**entries[0], "source_citation": {"file": "react-vite/src/types.ts", "line": 1}}]
        records, _ = _records(entries, source_root=root, scope=self._scope(tmp_path, ["react-vite/**"]))
        assert records["verification"][0]["citation_check"] == "no-definition"
        _, applied = mod.apply_update(update_type="gap-driven", provenance={"entries": []}, skill_name="lib",
                                      records=records, test_report_run_id="r", **BLOCK)
        [warning] = applied["warnings"]
        assert ("; it cites react-vite/src/types.ts:1; its check there: no-definition (no line of its file defines "
                "it, by the definition-line rules)); nothing is added or re-extracted for it. When the skill covers "
                "that file, change the brief's scope so it takes it") in warning

    def test_a_brief_that_names_no_file_is_an_input_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "forge" / "skill-brief.yaml"
        with pytest.raises(ValueError, match=re.escape(f"brief not found: {missing}")):
            mod._brief_scope(missing)
        bad = tmp_path / "skill-brief.yaml"
        bad.write_bytes(b"scope: [unclosed\n")
        with pytest.raises(ValueError, match="is not valid YAML") as caught:
            mod._brief_scope(bad)
        assert "\n" not in str(caught.value)

    def test_the_records_carry_every_documented_field(self, tmp_path: Path) -> None:
        remediation = ("Set the provenance `source_line` of `search` in `pkg/api.py` to its definition line (5) "
                       "and move its citations to that line.")
        entries = [_gap_entry("GAP-001", "search", "MOVED_EXPORT", category="provenance-line", severity="Low",
                              match=_found("pkg/api.py", 4), citation={"file": "pkg/api.py", "line": 4},
                              remediation=remediation),
                   _gap_entry("GAP-002", None, "STRUCTURAL_FIX", category="structural")]
        records, summary = _records(entries, tmp_path)
        assert list(records) == ["mode", "files_extracted", "exports_extracted", "confidence_breakdown",
                                 "verification", "files"]
        [record] = records["verification"]
        assert list(record) == ["gap_id", "export_name", "gap_category", "severity", "verification", "in_map",
                                "map_entry", "provenance_citation", "source_citation", "new_location",
                                "unknown_reason", "citation_check", "map_locations", "outside_scope",
                                "pinned_definition_lines", "resolution_source", "reachability",
                                "export_type", "params", "return_type", "extraction_method", "ast_node_type"]
        assert record["gap_id"] == "GAP-001"
        assert (record["in_map"], record["map_entry"], record["pinned_definition_lines"]) == \
            (True, {"source_file": "pkg/api.py", "source_line": 4}, [5])
        assert summary["forwarded"] == [{"gap_id": "GAP-002", "change_category": "STRUCTURAL_FIX"}]
        assert summary["targeted_reextraction"] is None and summary["gap_count"] == 2

    @pytest.mark.parametrize("remediation, lines", [
        ("... to its definition line (5) and ...", [5]), ("... to its definition lines (5, 12) ...", [5, 12]),
        ("Fix the line by hand.", None),
    ], ids=["one-line", "several-lines", "none-listed"])
    def test_pinned_definition_lines(self, remediation, lines) -> None:
        assert mod._pinned_lines(remediation) == lines

    def test_rule_r5_checks_a_variant_and_an_unresolved_citation(self, tmp_path: Path) -> None:
        """#847: a bookkeeping variant at a wrong line moves to its base's definition line; #832: a line past the
        file's end moves to the one line that defines the export, and a file the source lacks is missing."""
        root = _tree(tmp_path)
        (root / "code").mkdir()
        (root / "code" / "mock.ts").write_bytes(b"// mock helpers\n\nexport function mockChannel() {\n}\n")
        variant = ("Set the provenance `source_line` of `mockChannel_exact` in `code/mock.ts` to its definition line "
                   "(3) and move its citations to that line.")
        out_of_range = ("Set the provenance `source_line` of `search` in `pkg/api.py` to the line that defines it and "
                        "move its citations to that line.")
        gone = ("Set the provenance `source_file` and `source_line` of `gone` to the file and line that define it in "
                "the pinned source, and move its citations there.")
        entries = [
            _gap_entry("GAP-001", "mockChannel_exact", "MOVED_EXPORT", category="provenance-line", severity="Low",
                       match=_found("code/mock.ts", 1), citation={"file": "code/mock.ts", "line": 1},
                       remediation=variant),
            _gap_entry("GAP-002", "search", "MOVED_EXPORT", category="provenance-line", severity="Low",
                       match=_found("pkg/api.py", 99), citation={"file": "pkg/api.py", "line": 99},
                       remediation=out_of_range),
            _gap_entry("GAP-003", "gone", "MOVED_EXPORT", category="provenance-line", severity="Low",
                       match=_found("pkg/old.py", 3), citation={"file": "pkg/old.py", "line": 3}, remediation=gone)]
        records, summary = _records(entries, source_root=root)
        assert summary["status"] == "written", summary
        assert [(r["export_name"], r["verification"], r["new_location"], r["pinned_definition_lines"])
                for r in records["verification"]] == [
            ("mockChannel_exact", "moved", "code/mock.ts:3", [3]),
            ("search", "moved", "pkg/api.py:5", None),
            ("gone", "missing", None, None)]

    def test_only_rule_r5_folds_a_variant(self, tmp_path: Path) -> None:
        """#847: the fold serves rule R5 alone. A fabricated variant a MODIFIED_EXPORT or NEW_EXPORT gap names, at a
        line that defines its base, is judged as written: unknown (no-definition), its entry unchanged and warned,
        never verified and re-signed from the base's declaration."""
        root = _tree(tmp_path)
        (root / "code").mkdir()
        (root / "code" / "mock.ts").write_bytes(b"// mock helpers\n\nexport function mockChannel() {\n}\n")
        entries = [
            _gap_entry("GAP-001", "mockChannel_def", "MODIFIED_EXPORT", category="fabricated-signature",
                       severity="Critical", match=_found("code/mock.ts", 3)),
            _gap_entry("GAP-002", "a11y_mockChannel", "NEW_EXPORT", category="missing-export",
                       match=_found("code/mock.ts", 3)),
            _gap_entry("GAP-003", "mockChannel_exact", "MOVED_EXPORT", category="provenance-line", severity="Low",
                       match=_found("code/mock.ts", 1), citation={"file": "code/mock.ts", "line": 1},
                       remediation="Set it to its definition line (3).")]
        records, summary = _records(entries, source_root=root, remediation=_remediation(("code/mock.ts", [])))
        assert summary["status"] == "written", summary
        assert [(r["export_name"], r["verification"], r["unknown_reason"], r["new_location"])
                for r in records["verification"]] == [
            ("mockChannel_def", "unknown", "no-definition", None),
            ("a11y_mockChannel", "unknown", "no-definition", None),
            ("mockChannel_exact", "moved", None, "code/mock.ts:3")]
        old = {"provenance_version": "2.0", "skill_name": "lib", "entries": [
            _entry("mockChannel_def", "code/mock.ts", 3), _entry("a11y_mockChannel", "code/mock.ts", 3),
            _entry("mockChannel_exact", "code/mock.ts", 1)]}
        doc, applied = mod.apply_update(update_type="gap-driven", provenance=json.loads(json.dumps(old)),
                                        skill_name="lib", records=records, test_report_run_id="r", **BLOCK)
        assert doc["entries"][:2] == old["entries"][:2]
        assert doc["entries"][2]["source_line"] == 3
        fix = ("its entry is left unchanged. Fix the entry by hand (set its source_file and source_line to the line "
               "that defines it), then re-run update-skill")
        why = "no-definition: no line of its file defines it, by the definition-line rules"
        assert applied["warnings"] == [f"provenance: mockChannel_def (GAP-001): unknown ({why}); {fix}",
                                       f"provenance: a11y_mockChannel (GAP-002): unknown ({why}); {fix}"]


class TestScriptPEP723:
    """gap-records --brief loads skf-classify-changed-files.py, whose resolver reads the brief with PyYAML: under
    `uv run` the header must declare it."""

    def test_pyyaml_dependency(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")
        header = text[: text.index("# ///", text.index("# /// script") + 1)]
        assert '# requires-python = ">=3.11"' in header and 'dependencies = ["pyyaml"]' in header


# gap-records --extraction: the whole-scope runner's entry-point diff answers the reachability gate (#1191
# determinism-6), as a normal update's public surface marks its exports

SURFACE_SOURCE = b"def fetch():\n    pass\n\n\ndef helper():\n    pass\n\n\ndef gap():\n    pass\n\n\ndef other():\n    pass\n"


def _surface_tree(tmp_path: Path) -> Path:
    root = tmp_path / "src tree"
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "api.py").write_bytes(SURFACE_SOURCE)
    (root / "pkg" / "tool.rb").write_bytes(b"def run\nend\n")
    return root


def _surface_runner(**changes) -> dict:
    """The whole-scope recipe runner's JSON: fetch public, helper internal, gap an extraction gap, a Ruby file no
    recipe reads."""
    doc = {"mode": "full", "status": "ok", "errors": [], "scope": {"type": "full-library"},
           "entry_points": {"status": "barrel", "by_language": {"python": "barrel"}, "unresolved": []},
           "entry_point_diff": {
               "public": [{"name": "fetch", "language": "python", "entry": "pkg/__init__.py", "via": "re-export",
                           "from": ".api", "local": None, "file": "pkg/api.py", "line": 1, "members": None}],
               "other_definitions": [],
               "internal": [{"name": "helper", "language": "python", "source_file": "pkg/api.py", "source_line": 5},
                            {"name": "other", "language": "python", "source_file": "pkg/elsewhere.py",
                             "source_line": 13}],
               "extraction_gaps": [{"name": "gap", "language": "python", "entry": "pkg/__init__.py",
                                    "file": "pkg/api.py", "line": 9}],
               "outside_scope": []},
           "files_in_scope_list": ["pkg/api.py"], "files_without_recipes_list": ["pkg/tool.rb"]}
    doc.update(changes)
    return doc


def _surface_gap(gid: str, name: str, path: str, line: int) -> dict:
    return _gap_entry(gid, name, "NEW_EXPORT", category="missing-export", citation={"file": path, "line": line})


SURFACE_ENTRIES = [_surface_gap("GAP-001", "fetch", "pkg/api.py", 1), _surface_gap("GAP-002", "helper", "pkg/api.py", 5),
                   _surface_gap("GAP-003", "gap", "pkg/api.py", 9), _surface_gap("GAP-004", "run", "pkg/tool.rb", 1),
                   _surface_gap("GAP-005", "other", "pkg/api.py", 13)]
SURFACE_REMEDIATION = _remediation(("pkg/api.py", [("fetch", 1, "ast-grep"), ("helper", 5, "ast-grep"),
                                                   ("gap", 9, "source-read"), ("other", 13, "ast-grep")]),
                                   ("pkg/tool.rb", [("run", 1, "source-read")]))


class TestGapRecordsReachability:
    def _records(self, tmp_path: Path, extraction, judgments: dict | None = None, **kw) -> tuple:
        answers = {"GAP-004": {"declaring_line": 1}}
        for gid, more in (judgments or {}).items():
            answers.setdefault(gid, {}).update(more)
        return _records(SURFACE_ENTRIES, source_root=_surface_tree(tmp_path), extraction=extraction,
                        judgments=answers, **kw)

    def test_one_verdict_per_name(self, tmp_path: Path) -> None:
        # public in the diff: public; internal in the diff: internal-unreachable; an extraction gap, a file no recipe
        # reads, and a pair the diff's internal list does not hold: asked
        _, summary = self._records(tmp_path, _surface_runner(), remediation=SURFACE_REMEDIATION)
        assert summary["status"] == "needs-judgment", summary
        assert [(n["gap_id"], n["needs"]) for n in summary["needs_judgment"]] == [
            ("GAP-003", ["reachability"]), ("GAP-004", ["reachability"]), ("GAP-005", ["reachability"])]
        records, summary = self._records(
            tmp_path, _surface_runner(), remediation=SURFACE_REMEDIATION,
            judgments={g: {"reachability": "public"} for g in ("GAP-003", "GAP-004", "GAP-005")})
        assert summary["status"] == "written", summary
        assert [(r["export_name"], r["verification"], r["reachability"]) for r in records["verification"]] == [
            ("fetch", "verified", "public"), ("helper", "verified", "internal-unreachable"),
            ("gap", "verified", "public"), ("run", "verified", "public"), ("other", "verified", "public")]
        assert summary["reclassified"] == ["helper"] and summary["counts"]["reclassified"] == 1
        assert [b["file_path"] for b in records["files"]] == ["pkg/api.py", "pkg/tool.rb"]
        assert "helper" not in [r["name"] for b in records["files"] for r in b["exports"]]

    def test_the_diff_overrules_a_judgment(self, tmp_path: Path) -> None:
        records, summary = self._records(
            tmp_path, _surface_runner(), remediation=SURFACE_REMEDIATION,
            judgments={"GAP-001": {"reachability": "internal-unreachable"}, "GAP-002": {"reachability": "public"},
                       **{g: {"reachability": "public"} for g in ("GAP-003", "GAP-004", "GAP-005")}})
        assert summary["status"] == "written", summary
        assert [r["reachability"] for r in records["verification"][:2]] == ["public", "internal-unreachable"]

    def test_the_plan_locates_no_export_the_diff_finds_internal(self, tmp_path: Path) -> None:
        _, plan = self._records(tmp_path, _surface_runner(), plan=True)
        assert plan["status"] == "planned", plan
        assert [s["name"] for s in plan["reextract"]["signatures"]] == ["fetch", "gap", "run", "other"]
        _, plan = self._records(tmp_path, None, plan=True)  # without the diff the export is located, as before
        assert "helper" in [s["name"] for s in plan["reextract"]["signatures"]]

    @pytest.mark.parametrize("extraction", [
        None, _surface_runner(status="incomplete"), _surface_runner(errors=[{"reason": "time-limit"}]),
        _surface_runner(entry_point_diff=None, status="no-ast-grep"),
    ], ids=["not-passed", "incomplete", "errors", "no-diff"])
    def test_without_a_usable_diff_every_export_is_asked(self, tmp_path: Path, extraction) -> None:
        _, summary = self._records(tmp_path, extraction, remediation=SURFACE_REMEDIATION)
        assert summary["status"] == "needs-judgment", summary
        assert [n["gap_id"] for n in summary["needs_judgment"]] == [f"GAP-00{i}" for i in range(1, 6)]

    def test_an_untraced_entry_point_asks_all_but_the_public_pairs(self, tmp_path: Path) -> None:
        unresolved = _surface_runner(entry_points={"status": "barrel", "by_language": {"python": "barrel"},
                                           "unresolved": [{"entry": "pkg/__init__.py", "name": "x", "from": ".gone",
                                                           "file": "pkg/__init__.py"}]})
        _, summary = self._records(tmp_path, unresolved, remediation=SURFACE_REMEDIATION)
        assert [n["gap_id"] for n in summary["needs_judgment"]] == ["GAP-002", "GAP-003", "GAP-004", "GAP-005"]

    def test_an_internal_pair_outside_the_scope_list_is_asked(self, tmp_path: Path) -> None:
        _, summary = self._records(tmp_path, _surface_runner(files_in_scope_list=[]), remediation=SURFACE_REMEDIATION)
        assert [n["gap_id"] for n in summary["needs_judgment"]] == ["GAP-002", "GAP-003", "GAP-004", "GAP-005"]

    def test_a_re_extracted_export_is_answered_at_its_records_file(self, tmp_path: Path) -> None:
        entry = _gap_entry("GAP-001", "helper", "NEW_EXPORT", category="missing-export", resolved=["pkg/api.py"])
        records, summary = _records([entry], source_root=_surface_tree(tmp_path), extraction=_surface_runner(),
                                    remediation=SURFACE_REMEDIATION, judgments={"GAP-001": {"docstring": None}})
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["reachability"]) == ("re-extracted", "internal-unreachable")
        assert summary["reclassified"] == ["helper"] and records["files"] == []

    def test_a_moved_export_is_answered_at_its_checked_file(self, tmp_path: Path) -> None:
        # cited at line 4, defined at 5: the spot-check records it moved, and the diff answers it there, unasked
        entry = _surface_gap("GAP-001", "helper", "pkg/api.py", 4)
        records, summary = _records([entry], source_root=_surface_tree(tmp_path), extraction=_surface_runner(),
                                    remediation=SURFACE_REMEDIATION)
        assert summary["status"] == "written", summary
        [record] = records["verification"]
        assert (record["verification"], record["new_location"], record["reachability"]) == (
            "moved", "pkg/api.py:5", "internal-unreachable")
        assert summary["reclassified"] == ["helper"] and not summary.get("needs_judgment")

    def test_a_namespace_member_and_an_unfiled_name_are_public(self, tmp_path: Path) -> None:
        runner = _surface_runner()
        runner["entry_point_diff"]["public"] = [
            {"name": "ns", "language": "python", "via": "namespace", "file": "pkg/ns.py", "local": None,
             "members": [{"name": "gap", "local": None, "file": "pkg/api.py", "line": 9}]},
            {"name": "other", "language": "python", "via": "re-export", "file": None, "local": None}]
        runner["entry_point_diff"]["extraction_gaps"] = []
        _, summary = self._records(tmp_path, runner, remediation=SURFACE_REMEDIATION)
        assert [n["gap_id"] for n in summary["needs_judgment"]] == ["GAP-001", "GAP-004"]

    def test_the_cli_reads_the_runner_json(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        run.mkdir()
        (run / "change-manifest.json").write_bytes(
            json.dumps({"mode": "gap-driven", "entries": SURFACE_ENTRIES[:2]}).encode("utf-8"))
        (run / "public-api.json").write_bytes(json.dumps(_surface_runner()).encode("utf-8"))
        (tmp_path / "provenance-map.json").write_bytes(b'{"entries": []}')
        (run / "remediation-records.json").write_bytes(json.dumps(SURFACE_REMEDIATION).encode("utf-8"))
        result = _run_cli("gap-records", "--manifest", str(run / "change-manifest.json"), "--provenance-map",
                          str(tmp_path / "provenance-map.json"), "--source-root", str(_surface_tree(tmp_path)),
                          "--extraction", str(run / "public-api.json"),
                          "--remediation-records", str(run / "remediation-records.json"),
                          "-o", str(run / "reextract-records.json"))
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert (summary["status"], summary["reclassified"]) == ("written", ["helper"])
        (run / "bad.json").write_bytes(b"[]")
        result = _run_cli("gap-records", "--manifest", str(run / "change-manifest.json"), "--provenance-map",
                          str(tmp_path / "provenance-map.json"), "--extraction", str(run / "bad.json"), "--plan")
        assert result.returncode == 1 and "--extraction must hold a JSON object" in result.stderr


class TestGapRecordsCli:
    def _files(self, tmp_path: Path, entries: list) -> dict:
        run_dir = tmp_path / "run"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "change-manifest.json").write_bytes(
            json.dumps({"mode": "gap-driven", "entries": entries}).encode("utf-8"))
        (tmp_path / "provenance-map.json").write_bytes(b'{"entries": []}')
        return {"run": run_dir, "manifest": str(run_dir / "change-manifest.json"),
                "map": str(tmp_path / "provenance-map.json"), "root": str(_tree(tmp_path))}

    def test_plan_then_record(self, tmp_path: Path) -> None:
        paths = self._files(tmp_path, [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                                                  resolved=["pkg/api.py"])])
        files_out = paths["run"] / "remediation-files.json"
        base = ("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                "--source-root", paths["root"])
        result = _run_cli(*base, "--plan", "--files-out", str(files_out))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "planned"
        assert json.loads(files_out.read_bytes()) == ["pkg/api.py"]
        (paths["run"] / "remediation-records.json").write_bytes(
            json.dumps(_remediation(("pkg/api.py", [("search", 5, "ast-grep")]))).encode("utf-8"))
        (paths["run"] / "gap-judgments.json").write_bytes(
            json.dumps({"GAP-001": {"reachability": "public", "docstring": None}}).encode("utf-8"))
        evidence = paths["run"] / "evidence-records.jsonl"
        out = paths["run"] / "reextract-records.json"
        result = _run_cli(*base, "--judgments", str(paths["run"] / "gap-judgments.json"),
                          "--remediation-records", str(paths["run"] / "remediation-records.json"),
                          "--evidence", str(evidence), "--tier", "Forge+", "-o", str(out))
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert summary["status"] == "written" and summary["output"] == str(out)
        assert json.loads(out.read_bytes())["verification"][0]["verification"] == "re-extracted"
        assert json.loads(evidence.read_bytes()) == {"targeted_reextraction": {
            "resolved_count": 1, "files_scanned": 1, "signature_files_scanned": 0, "exports_matched": 1,
            "tier": "Forge+"}}

    @pytest.mark.parametrize("severity", ["High", "Medium"])
    def test_a_file_a_still_incomplete_run_left_unread_resolves_once_read_by_eye(self, tmp_path: Path,
                                                                                severity) -> None:
        """#710: a second runner run that stops at the time limit leaves the routed file unread. Without by-eye
        records a High gap halts `unresolved` and a Medium `missing-export` ends `unknown`; once gap-driven §4a
        reads the file by eye, in Category B step 2's record shape, the gap is `re-extracted` T1-low."""
        paths = self._files(tmp_path, [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                                                  severity=severity, resolved=["pkg/api.py"])])
        run = paths["run"]
        files = run / "remediation-files.json"
        files.write_bytes(json.dumps(["pkg/api.py"]).encode("utf-8"))
        # the runner's JSON at the time limit (skf-extract-public-api.py's `errors[]`: `unread` for time-limit)
        (run / "remediation-exports.json").write_bytes(json.dumps({
            "status": "incomplete", "exports": [], "file_issues": [], "entry_point_diff": {"extraction_gaps": []},
            "errors": [{"reason": "time-limit", "files": 1, "first_file": "pkg/api.py",
                        "detail": "stopped at the time limit", "unread": ["pkg/api.py"]}]}).encode("utf-8"))
        records = run / "remediation-records.json"
        build = ("records", "--extraction", str(run / "remediation-exports.json"), "--files-from", str(files),
                 "-o", str(records))
        result = _run_cli(*build)
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert (summary["files_extracted"], summary["exports_extracted"], summary["warnings"]) == (1, 0, [])
        out = run / "reextract-records.json"
        match = ("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                 "--source-root", paths["root"], "--remediation-records", str(records))
        result = _run_cli(*match, "-o", str(out))
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        if severity == "High":
            assert summary["status"] == "unresolved" and not out.exists()
            assert [(u["name"], u["files_scanned"], u["exports_found_in_scan"]) for u in summary["unresolved"]] \
                == [("search", 1, 0)]
        else:
            assert (summary["status"], summary["counts"]["unknown"], summary["counts"]["re-extracted"]) \
                == ("written", 1, 0)
            assert summary["targeted_reextraction"]["exports_matched"] == 0 and summary["warnings"] == []
        # the by-eye read of the unread file, as an export the runner did not find
        (run / "remediation-details.json").write_bytes(json.dumps({"exports": [{
            "export_name": "search", "source_file": "pkg/api.py", "source_line": 5, "export_type": "function",
            "params": ["q"], "return_type": None, "confidence": "T1-low",
            "extraction_method": "source-read"}]}).encode("utf-8"))
        result = _run_cli(*build[:3], "--export-details", str(run / "remediation-details.json"), *build[3:])
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert (summary["exports_extracted"], summary["confidence_breakdown"]["T1-low"], summary["warnings"]) \
            == (1, 1, [])
        result = _run_cli(*match, "-o", str(out))
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert summary["status"] == "needs-judgment"
        assert [(n["file"], n["line"]) for n in summary["needs_judgment"]] == [("pkg/api.py", 5)]
        (run / "gap-judgments.json").write_bytes(
            json.dumps({"GAP-001": {"reachability": "public", "docstring": None}}).encode("utf-8"))
        result = _run_cli(*match, "--judgments", str(run / "gap-judgments.json"), "-o", str(out))
        assert result.returncode == 0, result.stderr
        summary = json.loads(result.stdout)
        assert (summary["status"], summary["counts"]["re-extracted"], summary["counts"]["unknown"]) \
            == ("written", 1, 0)
        assert summary["confidence_breakdown"]["T1-low"] == 1
        written = json.loads(out.read_bytes())
        assert written["verification"][0]["verification"] == "re-extracted"
        record = written["files"][0]["exports"][0]
        assert (record["location"], record["confidence"], record["extraction_method"], record["ast_node_type"],
                record["ast_recipe"]) == ("pkg/api.py:5", "T1-low", "source-read", None, None)

    @pytest.mark.parametrize("args, message", [
        (("--plan", "-o", "x.json"), "drop -o"),
        ((), "-o is required without --plan"),
        (("--files-out", "f.json", "-o", "x.json"), "--files-out goes with --plan"),
        (("--plan", "--evidence", "e.jsonl"), "--evidence and --tier go together"),
        (("--plan", "--judgments", "BAD"), "`reachability` must be one of"),
    ], ids=["plan-with-output", "no-output", "files-out-without-plan", "evidence-without-tier", "bad-answer"])
    def test_an_unusable_call_exits_1(self, tmp_path: Path, args, message) -> None:
        paths = self._files(tmp_path, [])
        if "BAD" in args:
            bad = tmp_path / "gap-judgments.json"
            bad.write_bytes(json.dumps({"GAP-001": {"reachability": "maybe"}}).encode("utf-8"))
            args = tuple(str(bad) if a == "BAD" else a for a in args)
        result = _run_cli("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"], *args)
        assert result.returncode == 1 and message in result.stderr, result.stderr

    def test_brief_scopes_the_plan(self, tmp_path: Path) -> None:
        """--brief takes the skill brief: the plan's files leave out each one its scope leaves out (#824)."""
        paths = self._files(tmp_path, [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                                                  severity="Critical", resolved=["pkg/api.py", "lib.rs"])])
        brief = tmp_path / "skill-brief.yaml"
        brief.write_bytes(b"name: lib\nscope:\n  include:\n    - 'pkg/**'\n  exclude: []\n")
        files_out = paths["run"] / "remediation-files.json"
        base = ("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                "--source-root", paths["root"], "--plan", "--files-out", str(files_out))
        result = _run_cli(*base)
        assert result.returncode == 0, result.stderr
        assert json.loads(files_out.read_bytes()) == ["pkg/api.py", "lib.rs"]
        result = _run_cli(*base, "--brief", str(brief))
        assert result.returncode == 0, result.stderr
        assert json.loads(files_out.read_bytes()) == ["pkg/api.py"]
        assert json.loads(result.stdout)["reextract"]["entries"][0]["resolved_paths"] == ["pkg/api.py"]

    def test_an_empty_include_takes_the_brief_languages_files(self, tmp_path: Path) -> None:
        """An empty scope.include takes each file with a suffix of the brief's language (or of a path the gaps or the
        map name): an Elixir skill's gap at its `.ex` file is still scanned."""
        paths = self._files(tmp_path, [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", severity="Critical",
                                                  resolved=["lib/search.ex"])])
        brief = tmp_path / "skill-brief.yaml"
        brief.write_bytes(b"name: lib\nlanguage: elixir\nscope:\n  include: []\n  exclude: []\n")
        files_out = paths["run"] / "remediation-files.json"
        result = _run_cli("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                          "--source-root", paths["root"], "--brief", str(brief), "--plan", "--files-out",
                          str(files_out))
        assert result.returncode == 0, result.stderr
        assert json.loads(files_out.read_bytes()) == ["lib/search.ex"]

    def test_the_drift_gate_passes_a_gap_the_brief_scope_keeps_from_a_repair(self, tmp_path: Path) -> None:
        """Under --allow-workspace-drift nothing is read for a gap whose every file the scope leaves out, so it
        does not halt the run; one with a file the scope takes still does."""
        entries = [_gap_entry("GAP-001", "search", "MODIFIED_EXPORT", severity="Critical", resolved=["lib.rs"]),
                   _gap_entry("GAP-002", "fetch", "MODIFIED_EXPORT", severity="Critical",
                              citation={"file": "lib.rs", "line": 1})]
        paths = self._files(tmp_path, entries)
        brief = tmp_path / "skill-brief.yaml"
        brief.write_bytes(b"name: lib\nscope:\n  include:\n    - 'pkg/**'\n")
        base = ("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                "--source-root", paths["root"], "--drift-status", "overridden")
        result = _run_cli(*base, "--plan")
        assert result.returncode == 0, result.stderr
        assert [b["gap_id"] for b in json.loads(result.stdout)["drift_blocked"]] == ["GAP-001", "GAP-002"]
        out = paths["run"] / "reextract-records.json"
        result = _run_cli(*base, "--brief", str(brief), "-o", str(out))
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["status"] == "written"
        assert [(r["gap_id"], r["unknown_reason"]) for r in json.loads(out.read_bytes())["verification"]] == [
            ("GAP-001", "outside-scope"), ("GAP-002", "outside-scope")]
        # a gap with a file the scope takes still needs the tree
        (paths["run"] / "change-manifest.json").write_bytes(json.dumps({"mode": "gap-driven", "entries": [
            _gap_entry("GAP-003", "search", "MODIFIED_EXPORT", severity="Critical",
                       resolved=["pkg/api.py", "lib.rs"])]}).encode("utf-8"))
        result = _run_cli(*base, "--brief", str(brief), "--plan")
        assert result.returncode == 0, result.stderr
        assert [b["gap_id"] for b in json.loads(result.stdout)["drift_blocked"]] == ["GAP-003"]

    @pytest.mark.parametrize("value, message", [("MISSING", "error: brief not found: "),
                                                ("", "error: --brief is empty")], ids=["no-file", "empty"])
    def test_a_missing_brief_is_an_input_error(self, tmp_path: Path, value: str, message: str) -> None:
        paths = self._files(tmp_path, [_gap_entry("GAP-001", "search", "NEW_EXPORT", category="missing-export",
                                                  resolved=["pkg/api.py"])])
        missing = str(tmp_path / "forge" / "skill-brief.yaml")
        result = _run_cli("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                          "--source-root", paths["root"], "--brief", missing if value == "MISSING" else value, "--plan")
        assert result.returncode == 1 and result.stdout == "", result
        [line] = result.stderr.splitlines()
        assert line.startswith(message), line
        if value == "MISSING":
            assert missing in line

    def test_a_status_that_writes_nothing_exits_0(self, tmp_path: Path) -> None:
        paths = self._files(tmp_path, [_gap_entry("GAP-001", "x", "NEW_EXPORT", category="missing-export")])
        out = paths["run"] / "reextract-records.json"
        result = _run_cli("gap-records", "--manifest", paths["manifest"], "--provenance-map", paths["map"],
                          "--drift-status", "overridden", "-o", str(out))
        assert result.returncode == 0 and json.loads(result.stdout)["status"] == "drift-blocked"
        assert not out.exists()


# --------------------------------------------------------------------------
# baseline-gaps (update-skill detect-changes Category B, #687)
# --------------------------------------------------------------------------


STRUCTURAL_DIFF = REPO_ROOT / "src" / "shared" / "scripts" / "skf-structural-diff.py"

# cognee v1.6.2's shape against oms-cognee 1.0.0's map: the runner reports `add` and none of the four names
# below, and `run_startup_migrations` is gone from cognee/run_migrations.py
COGNEE_162 = {
    "cognee/__init__.py": "from .version import get_cognee_version\nfrom .api.v1 import add\n\n"
                          "__version__ = get_cognee_version()\n",
    "cognee/api/v1/__init__.py": "from .add.add import add\nfrom cognee.api.v1.visualize import visualize_graph as "
                                 "visualize\n",
    "cognee/api/v1/add/add.py": "async def add(data):\n    pass\n",
    "cognee/api/v1/session/session.py": "def get_session():\n    pass\n",
    "cognee/modules/pipelines/__init__.py": "from .tasks import Task\n",
    "cognee/run_migrations.py": "async def run_migrations():\n    pass\n",
}
COGNEE_100_MAP = {"entries": [
    {"export_name": "__version__", "export_type": "variable", "source_file": "cognee/__init__.py", "source_line": 6,
     "params": [], "return_type": "str"},
    {"export_name": "visualize", "export_type": "alias", "source_file": "cognee/api/v1/__init__.py",
     "source_line": 6, "params": [], "return_type": None},
    {"export_name": "add", "export_type": "async_function", "source_file": "cognee/api/v1/add/add.py",
     "source_line": 1, "params": ["data"], "return_type": None},
    {"export_name": "session", "export_type": "module", "source_file": "cognee/api/v1/session/session.py",
     "source_line": 1, "params": ["get_session()"], "return_type": None},
    {"export_name": "pipelines", "export_type": "module", "source_file": "cognee/modules/pipelines/__init__.py",
     "source_line": 1, "params": ["Task"], "return_type": None},
    {"export_name": "run_startup_migrations", "export_type": "async_function",
     "source_file": "cognee/run_migrations.py", "source_line": 80, "params": [], "return_type": None},
]}  # 1.0.0's map has no file_entries
COGNEE_RUNNER = {"status": "ok", "exports": [
    {"export_name": "add", "export_type": "function", "source_file": "cognee/api/v1/add/add.py", "source_line": 1,
     "signature": "async def add(data):", "params": [{"name": "data", "type": None}], "return_type": None,
     "confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "function_definition"},
    {"export_name": "run_migrations", "export_type": "function", "source_file": "cognee/run_migrations.py",
     "source_line": 1, "signature": "async def run_migrations():", "params": [], "return_type": None,
     "confidence": "T1", "extraction_method": "ast-grep", "ast_node_type": "function_definition"},
], "entry_point_diff": {"extraction_gaps": []}}


def _cognee_run(tmp_path: Path, runner: dict | None = None) -> dict:
    root = tmp_path / "src"
    for rel, text in COGNEE_162.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    run = tmp_path / "run"
    run.mkdir()
    paths = {"root": root, "run": run, "map": tmp_path / "provenance-map.json",
             "extraction": run / "extraction.json", "files": run / "modified-files.json",
             "out": run / "baseline-gaps.json"}
    paths["map"].write_bytes(json.dumps(COGNEE_100_MAP).encode("utf-8"))
    paths["extraction"].write_bytes(json.dumps(COGNEE_RUNNER if runner is None else runner).encode("utf-8"))
    paths["files"].write_bytes(json.dumps(sorted(COGNEE_162)).encode("utf-8"))
    return paths


def _baseline_gaps(paths: dict, script: Path = SCRIPT_PATH) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), "baseline-gaps", "--provenance-map", str(paths["map"]),
         "--extraction", str(paths["extraction"]), "--files", str(paths["files"]),
         "--source-root", str(paths["root"]), "-o", str(paths["out"])],
        capture_output=True, text=True, check=False)


class TestBaselineGaps:
    def test_lists_what_the_runner_leaves_out_and_not_a_real_deletion(self, tmp_path: Path) -> None:
        paths = _cognee_run(tmp_path)
        result = _baseline_gaps(paths)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"status": "written", "output": str(paths["out"]), "gaps": 4,
                                             "unchecked": 0}
        gaps = json.loads(paths["out"].read_bytes())
        assert [(g["name"], g["file"], g["line"], g["export_type"]) for g in gaps["gaps"]] == [
            ("__version__", "cognee/__init__.py", 4, "variable"),
            ("visualize", "cognee/api/v1/__init__.py", 2, "alias"),
            ("session", "cognee/api/v1/session/session.py", 1, "module"),
            ("pipelines", "cognee/modules/pipelines/__init__.py", 1, "module"),
        ]
        assert gaps["unchecked"] == []

    def test_category_b_reads_the_gaps_and_reports_only_the_real_deletion(self, tmp_path: Path) -> None:
        """The acceptance check: step 2 records each gap by eye at its line, with its export_type while the
        declaration keeps that kind, and step 3's diff reads none of the four as deleted, while
        run_startup_migrations, which the file declares no more, stays a DELETED_EXPORT."""
        paths = _cognee_run(tmp_path)
        assert _baseline_gaps(paths).returncode == 0
        details = paths["run"] / "export-details.json"

        def diff(extra: list) -> dict:
            details.write_bytes(json.dumps({"exports": extra}).encode("utf-8"))
            out = paths["run"] / "category-b-diff.json"
            proc = subprocess.run([sys.executable, str(STRUCTURAL_DIFF), str(paths["map"]), str(paths["extraction"]),
                                   "--current-extra", str(details), "--files", str(paths["files"]), "-o", str(out)],
                                  capture_output=True, text=True, check=False)
            assert proc.returncode in (0, 1), proc.stderr
            return json.loads(out.read_bytes())

        # before #687: step 2 read only the runner's own gaps, so every name it never reports reads as deleted
        assert sorted(r["name"] for r in diff([])["removed"]) == [
            "__version__", "pipelines", "run_startup_migrations", "session", "visualize"]
        read = [{"export_name": g["name"], "source_file": g["file"], "export_type": g["export_type"],
                 "source_line": g["line"], "params": None, "return_type": None, "confidence": "T1-low",
                 "extraction_method": "source-read"}
                for g in json.loads(paths["out"].read_bytes())["gaps"]]
        result = diff(read)
        assert [r["name"] for r in result["removed"]] == ["run_startup_migrations"]
        manifest = mod.build_manifest({"category_a": {"modified": sorted(COGNEE_162)},
                                       "category_b": mod.category_b_from_diff(result)})
        deleted = [e["name"] for f in manifest["per_file"] for e in f["exports_affected"]
                   if e["change_type"] == "DELETED_EXPORT"]
        assert deleted == ["run_startup_migrations"] and manifest["counts"]["exports_deleted"] == 1

    def test_a_held_or_listed_name_and_another_file_are_left_out(self, tmp_path: Path) -> None:
        runner = {**COGNEE_RUNNER, "exports": COGNEE_RUNNER["exports"] + [
            {"export_name": "__version__", "export_type": "variable", "source_file": "./cognee/__init__.py",
             "source_line": 4}],
            "entry_point_diff": {"extraction_gaps": [
                {"name": "visualize", "language": "python", "entry": "cognee/__init__.py",
                 "file": "cognee/api/v1/__init__.py", "line": 2}]}}
        paths = _cognee_run(tmp_path, runner)
        paths["files"].write_bytes(json.dumps(["cognee/__init__.py", "cognee/api/v1/__init__.py",
                                               "cognee\\api\\v1\\session\\session.py"]).encode("utf-8"))
        assert _baseline_gaps(paths).returncode == 0
        assert [g["name"] for g in json.loads(paths["out"].read_bytes())["gaps"]] == ["session"]

    def test_a_runner_that_could_not_run(self, tmp_path: Path) -> None:
        # Quick tier, exit 3, or no JSON on an exit other than 2 (which HALTs): step 1 writes {"exports": []} and
        # the gaps are every entry still declared
        paths = _cognee_run(tmp_path, {"exports": []})
        assert _baseline_gaps(paths).returncode == 0
        assert [g["name"] for g in json.loads(paths["out"].read_bytes())["gaps"]] == [
            "__version__", "visualize", "add", "session", "pipelines"]

    @pytest.mark.parametrize("verifier", [None, "raise RuntimeError('broken install')\n", "def other():\n    pass\n"],
                             ids=["missing", "raises", "no-baseline-gaps"])
    def test_a_verifier_that_cannot_load_is_an_error(self, tmp_path: Path, verifier: str | None) -> None:
        """Unlike gap-records' spot-checks, baseline-gaps never goes on without the verifier: an empty list would
        read every runner-skipped name as deleted. The step HALTs on its exit 1 (detect-changes:category-b)."""
        alone = tmp_path / "scripts"
        alone.mkdir()
        (alone / SCRIPT_PATH.name).write_bytes(SCRIPT_PATH.read_bytes())
        if verifier is not None:
            (alone / "skf-verify-provenance-completeness.py").write_bytes(verifier.encode("utf-8"))
        paths = _cognee_run(tmp_path)
        result = _baseline_gaps(paths, alone / SCRIPT_PATH.name)
        assert result.returncode == 1 and result.stdout == ""
        assert result.stderr.startswith("error: cannot load skf-verify-provenance-completeness.py beside "
                                        "skf-build-change-manifest.py: ")
        assert "re-install SKF" in result.stderr and "Traceback" not in result.stderr
        assert not paths["out"].exists()

    @pytest.mark.parametrize("bad, content, message", [
        ("files", b'{"nope": 1}', "must hold a JSON array of paths"),
        ("extraction", b'{"nope": 1}', "has no `exports` array"),
        ("extraction", b"null", "has no `exports` array"),
        ("map", b"[]", "must hold a JSON object"),
        ("map", b'{"entries": {"a": 1}}', "provenance `entries` must be an array"),
        ("root", None, "is not a folder"),
    ], ids=["files", "extraction", "extraction-null", "map", "map-entries", "root"])
    def test_an_input_it_cannot_use_exits_1(self, tmp_path: Path, bad: str, content: bytes | None,
                                            message: str) -> None:
        paths = _cognee_run(tmp_path)
        if bad == "root":
            paths["root"] = tmp_path / "missing"
        else:
            paths[bad].write_bytes(content)
        result = _baseline_gaps(paths)
        assert result.returncode == 1 and message in result.stderr, result.stderr
        assert "Traceback" not in result.stderr and not paths["out"].exists()

    @pytest.mark.parametrize("prov", [b'{"entries": null}', b'{"file_entries": []}'], ids=["null", "missing"])
    def test_a_map_with_no_entries_has_no_gap(self, tmp_path: Path, prov: bytes) -> None:
        # #684 reads a null field as empty: so does baseline-gaps
        paths = _cognee_run(tmp_path)
        paths["map"].write_bytes(prov)
        result = _baseline_gaps(paths)
        assert result.returncode == 0, result.stderr
        assert json.loads(paths["out"].read_bytes()) == {"gaps": [], "unchecked": []}

    def test_unchecked_entries_are_objects(self, tmp_path: Path) -> None:
        # a path holding " in " stays one field: each unchecked entry is {name, file, export_type}
        paths = _cognee_run(tmp_path)
        rust = paths["root"] / "docs in rust" / "lib.rs"
        rust.parent.mkdir(parents=True)
        rust.write_bytes(b"pub const _X: u8 = 1;\n")
        paths["map"].write_bytes(json.dumps({"entries": [
            {"export_name": "_X", "export_type": "constant", "source_file": "docs in rust/lib.rs"}]}).encode())
        paths["files"].write_bytes(json.dumps(["docs in rust/lib.rs"]).encode())
        assert _baseline_gaps(paths).returncode == 0
        assert json.loads(paths["out"].read_bytes())["unchecked"] == [
            {"name": "_X", "file": "docs in rust/lib.rs", "export_type": "constant"}]
