#!/usr/bin/env python3
"""Tests for skf-build-change-manifest.py.

Covers two subcommands:
  - build: aggregate category A/B/C/D into unified manifest
  - deletion-ratio: §2.2 trigger computation
and the helper files both take in place of typed slices: the classify
output (Category A and its same-content moves), the structural diff mapped
onto Category B, and Category C's renames taken out of both.
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
