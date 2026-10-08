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
  - rename-candidates and apply: Category C by rule, the provenance map an
    update writes
  - records: step 3's re-extraction records, seeded from the runner's and
    step 2's files, with the workers' patches merged in
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
        # a line alone, or a move to another modified file: moved
        assert b["moved_exports"] == [
            {"name": "shifted", "file": "pkg/api.py", "old_line": 20, "new_line": 22},
            {"name": "relocated", "file": "pkg/b.py", "old_line": 1, "new_line": 3},
        ]

    def test_a_moved_export_that_also_changed_is_modified_only(self) -> None:
        diff = {"removed": [], "added": [], "moved": [
            {"name": "f", "previous_file": "a.py", "current_file": "b.py", "previous_line": 1, "line": 2}],
            "changed": [{"name": "f", "field": "params", "baseline_value": [], "current_value": ["x"],
                         "file": "b.py", "line": 2}]}
        b = mod.category_b_from_diff(diff)
        assert [e["name"] for e in b["modified_exports"]] == ["f"] and b["moved_exports"] == []

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
                          map_entry={"source_file": "pkg/gone.py", "source_line": 1}),
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
        # missing and an unknown MOVED_EXPORT: left as they were, for a person
        assert entries[("gone_a", "pkg/gone.py")] == old["entries"][4]
        assert entries[("shifted", "pkg/a.py")] == old["entries"][3]
        assert summary["warnings"] == ["provenance: gone: missing",
                                       "provenance: shifted: unknown; definition lines per the test report: [31]"]
        assert doc["update_type"] == "gap-driven" and doc["test_report_run_id"] == "20260930T101010Z-2-bbbb"
        assert doc["exports_affected"] == 10
        assert stats.check_label_agreement(doc) == []

    def test_every_warning_names_the_drift_under_the_override(self) -> None:
        records = {"mode": "gap-driven", "verification": [
            _verification("stable", "verified", "MOVED_EXPORT", in_map=True,
                          map_entry={"source_file": "pkg/a.py", "source_line": 1}, pinned_definition_lines=[2]),
            _verification("search", "unknown", "MOVED_EXPORT", in_map=True, unknown_reason="drift-override",
                          pinned_definition_lines=[11]),
            _verification("gone", "missing", "MODIFIED_EXPORT", in_map=True)]}
        _doc, summary = mod.apply_update(update_type="gap-driven", provenance=_old_map(), skill_name="lib",
                                         records=records, test_report_run_id="r", drift=("abc1234", "def5678"),
                                         **BLOCK)
        note = "drift override: HEAD abc1234 is not pinned def5678"
        assert summary["warnings"] == [
            f"provenance: stable: verified at HEAD only ({note}; definition lines per the test report: [2])",
            f"provenance: search: unknown ({note}; no line taken from HEAD; definition lines per the test report: "
            "[11])",
            f"provenance: gone: missing ({note})"]

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
        assert by_name["other"] == old["entries"][2]
        assert (doc["files_changed"], doc["exports_affected"]) == (1, 2)


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
                           "confidence_breakdown": {"T1": 3, "T1-low": 1, "T2": 0}, "warnings": []}

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
# gap-records: update-skill gap-driven.md §3, §4 and §4a
# --------------------------------------------------------------------------

API_SOURCE = b"import os\n\n\n@decorate\ndef search(q):\n    return q\n"


def _found(path: str, line: int, export_type: str = "function") -> dict:
    view = {"source_file": path, "source_line": line, "export_type": export_type}
    return {"status": "found", "entry": view, "candidates": [view]}


NOT_FOUND = {"status": "not-found", "entry": None, "candidates": []}


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
            _gap_entry("GAP-007", None, "metadata update", category="metadata-drift"),
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
        records, summary = _records(entries, tmp_path)
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
            records, _ = _records([entry], tmp_path, judgments={"GAP-001": {"declaring_line": answer}})
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
        ], tmp_path)
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
        assert summary["targeted_reextraction"] == {"resolved_count": 2, "files_scanned": 2, "exports_matched": 2,
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
        assert list(record) == ["export_name", "gap_category", "severity", "verification", "in_map", "map_entry",
                                "provenance_citation", "source_citation", "new_location", "unknown_reason",
                                "pinned_definition_lines", "resolution_source", "reachability", "export_type"]
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
            "resolved_count": 1, "files_scanned": 1, "exports_matched": 1, "tier": "Forge+"}}

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
        # Quick tier, or exit 2 or 3: step 1 writes {"exports": []} and the gaps are every entry still declared
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
