#!/usr/bin/env python3
"""Tests for skf-structural-diff.py."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-structural-diff.py"

spec = importlib.util.spec_from_file_location("skf_diff", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
diff_inventories = mod.diff_inventories
canon_signature = mod.canon_signature
entries_from_data = mod.entries_from_data
extract_reexport_map = mod.extract_reexport_map


def _transform_count(result, name):
    for t in result["applied_transforms"]:
        if t["transform"] == name:
            return t["count"]
    return 0


@pytest.fixture()
def baseline():
    return [
        {"name": "foo", "file": "src/index.ts", "line": 10, "type": "function"},
        {"name": "Bar", "file": "src/index.ts", "line": 20, "type": "class"},
    ]


class TestNoChanges:
    def test_identical_exports_zero_diff(self, baseline):
        r = diff_inventories(baseline, baseline)
        s = r["summary"]
        assert s["added"] == 0 and s["removed"] == 0 and s["changed"] == 0 and s["moved"] == 0

    def test_identical_exports_unchanged_count(self, baseline):
        r = diff_inventories(baseline, baseline)
        assert r["unchanged_count"] == 2


class TestAddedExports:
    def test_one_added(self, baseline):
        current = baseline + [{"name": "baz", "file": "src/utils.ts", "line": 5, "type": "function"}]
        r = diff_inventories(baseline, current)
        assert r["summary"]["added"] == 1

    def test_added_name_is_baz(self, baseline):
        current = baseline + [{"name": "baz", "file": "src/utils.ts", "line": 5, "type": "function"}]
        r = diff_inventories(baseline, current)
        assert r["added"][0]["name"] == "baz"


class TestRemovedExports:
    def test_one_removed(self, baseline):
        current = baseline + [{"name": "baz", "file": "src/utils.ts", "line": 5, "type": "function"}]
        r = diff_inventories(current, baseline)
        assert r["summary"]["removed"] == 1

    def test_removed_name_is_baz(self, baseline):
        current = baseline + [{"name": "baz", "file": "src/utils.ts", "line": 5, "type": "function"}]
        r = diff_inventories(current, baseline)
        assert r["removed"][0]["name"] == "baz"


class TestMovedExport:
    def test_one_moved(self, baseline):
        moved_current = [
            {"name": "foo", "file": "src/new-location.ts", "line": 15, "type": "function"},
            {"name": "Bar", "file": "src/index.ts", "line": 20, "type": "class"},
        ]
        r = diff_inventories(baseline, moved_current)
        assert r["summary"]["moved"] == 1

    def test_moved_previous_file(self, baseline):
        moved_current = [
            {"name": "foo", "file": "src/new-location.ts", "line": 15, "type": "function"},
            {"name": "Bar", "file": "src/index.ts", "line": 20, "type": "class"},
        ]
        r = diff_inventories(baseline, moved_current)
        assert r["moved"][0]["previous_file"] == "src/index.ts"

    def test_moved_new_file(self, baseline):
        moved_current = [
            {"name": "foo", "file": "src/new-location.ts", "line": 15, "type": "function"},
            {"name": "Bar", "file": "src/index.ts", "line": 20, "type": "class"},
        ]
        r = diff_inventories(baseline, moved_current)
        assert r["moved"][0]["current_file"] == "src/new-location.ts"

    def test_pure_move_no_changed(self, baseline):
        """A pure file move (same line) should appear in moved but not changed."""
        moved_current = [
            {"name": "foo", "file": "src/new-location.ts", "line": 10, "type": "function"},
            {"name": "Bar", "file": "src/index.ts", "line": 20, "type": "class"},
        ]
        r = diff_inventories(baseline, moved_current)
        assert r["summary"]["moved"] == 1
        assert r["summary"]["changed"] == 0


class TestChangedSignature:
    def test_one_changed(self):
        base_with_sig = [{"name": "foo", "file": "src/index.ts", "line": 10, "type": "function", "signature": "foo(a: string): void"}]
        curr_with_sig = [{"name": "foo", "file": "src/index.ts", "line": 10, "type": "function", "signature": "foo(a: string, b: number): void"}]
        r = diff_inventories(base_with_sig, curr_with_sig)
        assert r["summary"]["changed"] == 1

    def test_changed_field_is_signature(self):
        base_with_sig = [{"name": "foo", "file": "src/index.ts", "line": 10, "type": "function", "signature": "foo(a: string): void"}]
        curr_with_sig = [{"name": "foo", "file": "src/index.ts", "line": 10, "type": "function", "signature": "foo(a: string, b: number): void"}]
        r = diff_inventories(base_with_sig, curr_with_sig)
        sig_change = [c for c in r["changed"] if c["field"] == "signature"]
        assert len(sig_change) == 1


class TestTypeChanged:
    def test_type_change_detected(self):
        base_type = [{"name": "foo", "file": "src/index.ts", "line": 10, "type": "function"}]
        curr_type = [{"name": "foo", "file": "src/index.ts", "line": 10, "type": "class"}]
        r = diff_inventories(base_type, curr_type)
        assert r["summary"]["changed"] == 1


class TestEmptyBaseline:
    def test_all_added_from_empty(self, baseline):
        current = baseline + [{"name": "baz", "file": "src/utils.ts", "line": 5, "type": "function"}]
        r = diff_inventories([], current)
        assert r["summary"]["added"] == 3

    def test_unchanged_zero(self, baseline):
        current = baseline + [{"name": "baz", "file": "src/utils.ts", "line": 5, "type": "function"}]
        r = diff_inventories([], current)
        assert r["unchanged_count"] == 0


class TestEmptyCurrent:
    def test_all_removed(self, baseline):
        r = diff_inventories(baseline, [])
        assert r["summary"]["removed"] == 2


class TestMixedChanges:
    def test_has_added_and_removed(self):
        base = [
            {"name": "a", "file": "src/a.ts", "line": 1, "type": "function"},
            {"name": "b", "file": "src/b.ts", "line": 1, "type": "function", "signature": "b(): void"},
            {"name": "c", "file": "src/c.ts", "line": 1, "type": "const"},
        ]
        curr = [
            {"name": "a", "file": "src/moved.ts", "line": 5, "type": "function"},  # moved
            {"name": "b", "file": "src/b.ts", "line": 1, "type": "function", "signature": "b(x: number): void"},  # signature changed
            {"name": "d", "file": "src/d.ts", "line": 1, "type": "class"},  # added (c removed)
        ]
        r = diff_inventories(base, curr)
        assert r["summary"]["added"] >= 1 and r["summary"]["removed"] >= 1

    def test_has_moved(self):
        base = [
            {"name": "a", "file": "src/a.ts", "line": 1, "type": "function"},
            {"name": "b", "file": "src/b.ts", "line": 1, "type": "function", "signature": "b(): void"},
            {"name": "c", "file": "src/c.ts", "line": 1, "type": "const"},
        ]
        curr = [
            {"name": "a", "file": "src/moved.ts", "line": 5, "type": "function"},
            {"name": "b", "file": "src/b.ts", "line": 1, "type": "function", "signature": "b(x: number): void"},
            {"name": "d", "file": "src/d.ts", "line": 1, "type": "class"},
        ]
        r = diff_inventories(base, curr)
        assert r["summary"]["moved"] >= 1

    def test_has_changed(self):
        base = [
            {"name": "a", "file": "src/a.ts", "line": 1, "type": "function"},
            {"name": "b", "file": "src/b.ts", "line": 1, "type": "function", "signature": "b(): void"},
            {"name": "c", "file": "src/c.ts", "line": 1, "type": "const"},
        ]
        curr = [
            {"name": "a", "file": "src/moved.ts", "line": 5, "type": "function"},
            {"name": "b", "file": "src/b.ts", "line": 1, "type": "function", "signature": "b(x: number): void"},
            {"name": "d", "file": "src/d.ts", "line": 1, "type": "class"},
        ]
        r = diff_inventories(base, curr)
        assert r["summary"]["changed"] >= 1


class TestQuoteStyleCanonicalization:
    """Quote-style-only signature differences must not surface as changes."""

    def test_double_vs_single_quote_default_no_change(self):
        base = [{"name": "f", "type": "function", "signature": 'f(kind: str = "Hnsw")'}]
        curr = [{"name": "f", "type": "function", "signature": "f(kind: str = 'Hnsw')"}]
        r = diff_inventories(base, curr)
        assert r["summary"]["changed"] == 0
        assert r["unchanged_count"] == 1

    def test_quote_style_transform_recorded(self):
        base = [{"name": "f", "type": "function", "signature": 'f(kind: str = "Hnsw")'}]
        curr = [{"name": "f", "type": "function", "signature": "f(kind: str = 'Hnsw')"}]
        r = diff_inventories(base, curr)
        # Only the baseline side carries a double quote to normalize.
        assert _transform_count(r, "quote-style") == 1

    def test_real_signature_change_still_detected_under_quotes(self):
        base = [{"name": "f", "type": "function", "signature": 'f(kind: str = "Hnsw")'}]
        curr = [{"name": "f", "type": "function", "signature": "f(kind: str = 'Ivf')"}]
        r = diff_inventories(base, curr)
        assert r["summary"]["changed"] == 1


class TestStdlibPrefixCanonicalization:
    """Stdlib module-prefix differences must not surface as changes."""

    def test_typing_optional_prefix_stripped(self):
        base = [{"name": "g", "type": "function", "signature": "g(x: typing.Optional[int])"}]
        curr = [{"name": "g", "type": "function", "signature": "g(x: Optional[int])"}]
        r = diff_inventories(base, curr)
        assert r["summary"]["changed"] == 0

    def test_stdlib_prefix_transform_recorded(self):
        base = [{"name": "g", "type": "function", "signature": "g(x: typing.List[int])"}]
        curr = [{"name": "g", "type": "function", "signature": "g(x: List[int])"}]
        r = diff_inventories(base, curr)
        assert _transform_count(r, "stdlib-prefix") == 1

    def test_dataclasses_and_collections_abc(self):
        assert canon_signature("dataclasses.field(default=1)")[0] == "field(default=1)"
        assert canon_signature("x: collections.abc.Sequence")[0] == "x: Sequence"
        assert canon_signature("x: collections.OrderedDict")[0] == "x: OrderedDict"

    def test_user_namespace_not_collapsed(self):
        # A user-defined namespace that merely ends in `.typing.` must survive.
        assert canon_signature("x: pkg.typing.Foo")[0] == "x: pkg.typing.Foo"
        assert canon_signature("x: mytyping.Foo")[0] == "x: mytyping.Foo"


class TestReexportResolution:
    """A renamed public re-export must match, not split into removed+added."""

    def test_reexport_collapses_removed_added_pair(self):
        base = [{"name": "_Impl", "type": "class", "signature": "class Impl"}]
        curr = [{"name": "Public", "type": "class", "signature": "class Impl"}]
        r = diff_inventories(base, curr, {"_Impl": "Public"})
        assert r["summary"]["removed"] == 0
        assert r["summary"]["added"] == 0
        assert r["summary"]["changed"] == 0
        assert r["unchanged_count"] == 1

    def test_reexport_transform_recorded(self):
        base = [{"name": "_Impl", "type": "class", "signature": "class Impl"}]
        curr = [{"name": "Public", "type": "class", "signature": "class Impl"}]
        r = diff_inventories(base, curr, {"_Impl": "Public"})
        assert _transform_count(r, "reexport-resolution") == 1

    def test_without_map_pair_splits(self):
        base = [{"name": "_Impl", "type": "class", "signature": "class Impl"}]
        curr = [{"name": "Public", "type": "class", "signature": "class Impl"}]
        r = diff_inventories(base, curr)
        assert r["summary"]["removed"] == 1 and r["summary"]["added"] == 1


class TestProvenanceEntriesShape:
    """Baseline provenance-map entries[] shape must diff against snapshot exports[]."""

    def test_entries_field_aliasing_matches_exports(self):
        # Provenance map: entries[] with export_name/export_type/source_file/source_line.
        provenance = {
            "provenance_version": "2.0",
            "entries": [
                {"export_name": "createServer", "export_type": "function",
                 "source_file": "src/server.ts", "source_line": 23, "confidence": "T1"},
            ],
        }
        snapshot = {
            "exports": [
                {"name": "createServer", "type": "function",
                 "file": "src/server.ts", "line": 23, "confidence": "T1"},
            ],
        }
        base_entries, err = entries_from_data(provenance)
        curr_entries, err2 = entries_from_data(snapshot)
        assert err is None and err2 is None
        r = diff_inventories(base_entries, curr_entries)
        assert r["summary"]["added"] == 0 and r["summary"]["removed"] == 0
        assert r["summary"]["changed"] == 0 and r["unchanged_count"] == 1

    def test_entries_type_change_detected(self):
        provenance = {"entries": [
            {"export_name": "x", "export_type": "function", "source_file": "a.ts", "source_line": 1},
        ]}
        snapshot = {"exports": [
            {"name": "x", "type": "class", "file": "a.ts", "line": 1},
        ]}
        r = diff_inventories(entries_from_data(provenance)[0], entries_from_data(snapshot)[0])
        assert r["summary"]["changed"] == 1

    def test_missing_signature_on_one_side_not_flagged(self):
        # Baseline (provenance) has no signature; snapshot does — no false change.
        provenance = {"entries": [
            {"export_name": "x", "export_type": "function", "source_file": "a.ts", "source_line": 1},
        ]}
        snapshot = {"exports": [
            {"name": "x", "type": "function", "file": "a.ts", "line": 1, "signature": "x(): void"},
        ]}
        r = diff_inventories(entries_from_data(provenance)[0], entries_from_data(snapshot)[0])
        assert r["summary"]["changed"] == 0
        assert r["unchanged_count"] == 1

    def test_reexport_map_derived_from_provenance(self):
        # Top-level reexport_map on the provenance map is picked up by
        # extract_reexport_map (the CLI auto-derives it when --reexport-map is absent).
        provenance = {
            "reexport_map": {"_Impl": "Public"},
            "entries": [{"export_name": "_Impl", "export_type": "class",
                         "source_file": "a.ts", "source_line": 1}],
        }
        rmap = extract_reexport_map(provenance)
        assert rmap == {"_Impl": "Public"}
        snapshot = {"exports": [{"name": "Public", "type": "class", "file": "a.ts", "line": 1}]}
        r = diff_inventories(entries_from_data(provenance)[0], entries_from_data(snapshot)[0], rmap)
        assert r["summary"]["added"] == 0 and r["summary"]["removed"] == 0


class TestAppliedTransformsField:
    def test_no_transforms_when_none_fire(self):
        base = [{"name": "a", "type": "function", "signature": "a(): void"}]
        r = diff_inventories(base, base)
        assert r["applied_transforms"] == []

    def test_transforms_sorted_by_name(self):
        base = [{"name": "_Impl", "type": "function", "signature": 'f(x: typing.Optional[str] = "y")'}]
        curr = [{"name": "Public", "type": "function", "signature": "f(x: Optional[str] = 'y')"}]
        r = diff_inventories(base, curr, {"_Impl": "Public"})
        names = [t["transform"] for t in r["applied_transforms"]]
        assert names == sorted(names)
        assert set(names) == {"quote-style", "stdlib-prefix", "reexport-resolution"}


# --------------------------------------------------------------------------
# Provenance labels: a relabel is reported in label_changes[], never as drift
# --------------------------------------------------------------------------


def _prov_entry(**overrides):
    """One provenance-map entries[] row (baseline shape)."""
    entry = {"export_name": "search", "export_type": "async_function",
             "source_file": "cognee/api/v1/search/search.py", "source_line": 27,
             "confidence": "T1-low", "extraction_method": "source-read"}
    entry.update(overrides)
    return entry


def _snap_export(**overrides):
    """One extraction-snapshot exports[] row (current shape)."""
    export = {"name": "search", "type": "async_function",
              "file": "cognee/api/v1/search/search.py", "line": 27,
              "confidence": "T1", "extraction_method": "ast-grep",
              "ast_node_type": "function_definition"}
    export.update(overrides)
    return export


class TestLabelChanges:
    """A provenance label difference is reported, never counted as drift (issue 530).

    Scenarios: relabel only (label_changes, no changed); relabel plus a real
    line change (both lists); case-only difference (nothing); a label missing
    or blank on one side (not compared); stack method spellings (aliases);
    added and removed exports (never label changes).
    """

    def test_confidence_is_not_a_diff_field(self):
        assert "confidence" not in mod.DIFF_FIELDS
        assert mod.DIFF_FIELDS == ["type", "signature", "line"]

    def test_relabel_only_is_a_label_change_not_drift(self):
        r = diff_inventories([_prov_entry()], [_snap_export()])
        assert r["changed"] == []
        assert r["summary"]["changed"] == 0
        assert r["unchanged_count"] == 1 and r["summary"]["unchanged"] == 1
        assert r["summary"]["label_changes"] == 1
        assert r["label_changes"] == [{
            "name": "search",
            "baseline": {"confidence": "T1-low", "extraction_method": "source-read"},
            "current": {"confidence": "T1", "extraction_method": "ast-grep"},
        }]

    def test_label_and_line_change_split(self):
        r = diff_inventories([_prov_entry()], [_snap_export(line=31)])
        assert r["changed"] == [{"name": "search", "field": "line",
                                 "baseline_value": 27, "current_value": 31}]
        assert r["summary"]["changed"] == 1
        assert r["unchanged_count"] == 0
        assert len(r["label_changes"]) == 1
        assert r["label_changes"][0]["name"] == "search"

    def test_case_only_difference_is_no_label_change(self):
        r = diff_inventories(
            [_prov_entry(confidence="t1-low")],
            [_snap_export(confidence="T1-low", extraction_method="Source-Read")],
        )
        assert r["label_changes"] == []
        assert r["summary"]["label_changes"] == 0
        assert r["unchanged_count"] == 1

    def test_method_only_difference_is_a_label_change(self):
        r = diff_inventories(
            [_prov_entry(confidence="T1", extraction_method="source-read")],
            [_snap_export(confidence="T1", extraction_method="ast-grep")],
        )
        assert len(r["label_changes"]) == 1
        assert r["changed"] == []

    def test_one_label_per_export_even_when_both_fields_differ(self):
        r = diff_inventories([_prov_entry()], [_snap_export()])
        assert len(r["label_changes"]) == 1

    @pytest.mark.parametrize("missing", ["extraction_method", "confidence"])
    def test_missing_label_on_one_side_is_not_compared(self, missing):
        base = _prov_entry(confidence="T1", extraction_method="source-read")
        del base[missing]
        curr = _snap_export(confidence="T1-low", extraction_method="ast-grep")
        # The other label still matches case-insensitively when it is the one kept.
        if missing == "extraction_method":
            curr["confidence"] = "t1"
        else:
            curr["extraction_method"] = "SOURCE-READ"
        r = diff_inventories([base], [curr])
        assert r["label_changes"] == []
        assert r["changed"] == []
        assert r["unchanged_count"] == 1

    def test_blank_label_counts_as_missing(self):
        r = diff_inventories(
            [_prov_entry(confidence="", extraction_method="  ")],
            [_snap_export()],
        )
        assert r["label_changes"] == []

    @pytest.mark.parametrize("absent", [None, "", "   "], ids=["none", "empty", "blank"])
    @pytest.mark.parametrize("field", ["confidence", "extraction_method"])
    def test_other_label_still_compared_when_one_is_absent(self, field, absent):
        # The absent label is skipped; the other label still differs and is reported.
        base = _prov_entry(confidence="T1-low", extraction_method="source-read")
        if absent is None:
            del base[field]
        else:
            base[field] = absent
        r = diff_inventories([base], [_snap_export(confidence="T1", extraction_method="ast-grep")])
        assert len(r["label_changes"]) == 1
        assert r["summary"]["label_changes"] == 1
        assert r["changed"] == []
        assert r["unchanged_count"] == 1

    def test_blank_label_is_emitted_as_null(self):
        r = diff_inventories(
            [_prov_entry(confidence="T1-low", extraction_method="  ")],
            [_snap_export(confidence="T1", extraction_method="ast-grep")],
        )
        assert r["label_changes"][0]["baseline"] == {"confidence": "T1-low", "extraction_method": None}

    @pytest.mark.parametrize("stack, library", [
        ("ast_bridge", "ast-grep"),
        ("source_reading", "source-read"),
        ("AST_BRIDGE", "ast-grep"),
    ])
    def test_stack_method_spellings_match_library_ones(self, stack, library):
        confidence = "T1" if library == "ast-grep" else "T1-low"
        r = diff_inventories(
            [_prov_entry(confidence=confidence, extraction_method=stack)],
            [_snap_export(confidence=confidence, extraction_method=library)],
        )
        assert r["label_changes"] == []
        assert r["unchanged_count"] == 1

    def test_stack_alias_keeps_written_spelling_when_reported(self):
        r = diff_inventories(
            [_prov_entry(confidence="T1-low", extraction_method="source_reading")],
            [_snap_export(confidence="T1", extraction_method="ast-grep")],
        )
        assert r["label_changes"][0]["baseline"]["extraction_method"] == "source_reading"

    def test_stack_aliases_do_not_merge_different_tools(self):
        r = diff_inventories(
            [_prov_entry(confidence="T1", extraction_method="ast_bridge")],
            [_snap_export(confidence="T1", extraction_method="source-read")],
        )
        assert len(r["label_changes"]) == 1

    def test_added_and_removed_are_never_label_changes(self):
        base = [_prov_entry(export_name="old_api")]
        curr = [_snap_export(name="new_api")]
        r = diff_inventories(base, curr)
        assert r["summary"]["added"] == 1 and r["summary"]["removed"] == 1
        assert r["label_changes"] == [] and r["summary"]["label_changes"] == 0

    def test_normalized_record_carries_extraction_method(self):
        r = diff_inventories([_prov_entry(export_name="gone")], [_snap_export()])
        assert r["removed"][0]["extraction_method"] == "source-read"
        assert r["added"][0]["extraction_method"] == "ast-grep"

    def test_summary_always_has_label_changes_key(self, baseline):
        r = diff_inventories(baseline, baseline)
        assert r["summary"]["label_changes"] == 0 and r["label_changes"] == []


# --------------------------------------------------------------------------
# CLI exit codes
# --------------------------------------------------------------------------


def _run(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        capture_output=True, text=True, timeout=60,
    )


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class TestCLIExitCodes:
    def test_relabel_only_exits_0(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [_snap_export()]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 0, res.stdout + res.stderr
        out = json.loads(res.stdout)
        assert out["changed"] == []
        assert out["summary"]["label_changes"] == 1

    def test_label_and_line_change_exits_1(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [_snap_export(line=31)]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 1
        out = json.loads(res.stdout)
        assert [c["field"] for c in out["changed"]] == ["line"]
        assert out["summary"]["label_changes"] == 1

    def test_case_only_exits_0(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": [_prov_entry(confidence="t1-low")]})
        curr = _write(tmp_path / "c.json", {"exports": [
            _snap_export(confidence="T1-low", extraction_method="source-read")]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 0
        assert json.loads(res.stdout)["label_changes"] == []

    def test_missing_method_on_one_side_exits_0(self, tmp_path):
        entry = _prov_entry(confidence="T1")
        del entry["extraction_method"]
        base = _write(tmp_path / "b.json", {"entries": [entry]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export()]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 0
        assert json.loads(res.stdout)["label_changes"] == []

    def test_added_and_removed_exit_1(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": [_prov_entry(export_name="old_api")]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export(name="new_api")]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 1
        out = json.loads(res.stdout)
        assert out["label_changes"] == []

    def test_output_file_written(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export()]})
        out_path = tmp_path / "diff.json"
        res = _run([str(base), str(curr), "-o", str(out_path)])
        assert res.returncode == 0
        assert json.loads(out_path.read_text())["summary"]["label_changes"] == 1

    def test_invalid_json_exits_1(self, tmp_path):
        base = tmp_path / "b.json"
        base.write_text("{not json", encoding="utf-8")
        curr = _write(tmp_path / "c.json", {"exports": []})
        res = _run([str(base), str(curr)])
        assert res.returncode == 1
        assert json.loads(res.stdout)["status"] == "error"
