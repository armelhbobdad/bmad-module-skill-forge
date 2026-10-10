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
        assert mod.DIFF_FIELDS == ["type", "signature", "params", "return_type", "line"]

    def test_relabel_only_is_a_label_change_not_drift(self):
        r = diff_inventories([_prov_entry()], [_snap_export()])
        assert r["changed"] == []
        assert r["summary"]["changed"] == 0
        assert r["unchanged_count"] == 1 and r["summary"]["unchanged"] == 1
        assert r["summary"]["label_changes"] == 1
        assert r["label_changes"] == [{
            "name": "search",
            "file": "cognee/api/v1/search/search.py",
            "baseline": {"confidence": "T1-low", "extraction_method": "source-read"},
            "current": {"confidence": "T1", "extraction_method": "ast-grep"},
        }]

    def test_label_and_line_change_split(self):
        r = diff_inventories([_prov_entry()], [_snap_export(line=31)])
        assert r["changed"] == [{"name": "search", "field": "line",
                                 "baseline_value": 27, "current_value": 31,
                                 "file": "cognee/api/v1/search/search.py", "line": 31,
                                 "confidence": "T1"}]
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
# Export identity: an export is its name and its file together
# --------------------------------------------------------------------------


def _route(name, file, line, **extra):
    return {"name": name, "file": file, "line": line, "type": "function", **extra}


class TestSameNameExports:
    """Matching on the bare name let duplicate names hide a removal and invent
    a move. Keyed on (name, file), and paired as a move only when the name is
    unique on both sides, the diff reports what happened."""

    def test_get_in_two_route_files_with_one_deleted(self):
        base = [_route("GET", "app/users/route.ts", 3), _route("GET", "app/posts/route.ts", 5)]
        curr = [_route("GET", "app/users/route.ts", 3)]
        r = diff_inventories(base, curr)
        assert [(e["name"], e["file"]) for e in r["removed"]] == [("GET", "app/posts/route.ts")]
        assert r["moved"] == [] and r["changed"] == [] and r["added"] == []
        assert r["ambiguous_names"] == []
        assert r["summary"]["removed"] == 1 and r["summary"]["unchanged"] == 1

    def test_two_parse_exports_listed_in_a_different_order(self):
        base = [_route("parse", "src/json.py", 10), _route("parse", "src/yaml.py", 20)]
        r = diff_inventories(base, list(reversed(base)))
        assert r["moved"] == [] and r["changed"] == []
        assert r["added"] == [] and r["removed"] == []
        assert r["unchanged_count"] == 2

    def test_a_change_to_one_of_two_same_name_exports_names_its_file(self):
        base = [_route("parse", "src/json.py", 10, signature="parse(s)"),
                _route("parse", "src/yaml.py", 20, signature="parse(s)")]
        curr = [_route("parse", "src/yaml.py", 20, signature="parse(s, strict)"),
                _route("parse", "src/json.py", 10, signature="parse(s)")]
        r = diff_inventories(base, curr)
        assert [(c["file"], c["field"]) for c in r["changed"]] == [("src/yaml.py", "signature")]
        assert r["summary"]["changed"] == 1 and r["summary"]["unchanged"] == 1

    def test_leftovers_of_a_repeated_name_are_ambiguous_not_moved(self):
        base = [_route("GET", "app/a/route.ts", 3), _route("GET", "app/b/route.ts", 5)]
        curr = [_route("GET", "app/a/route.ts", 3), _route("GET", "app/c/route.ts", 5)]
        r = diff_inventories(base, curr)
        assert r["moved"] == []
        assert [e["file"] for e in r["removed"]] == ["app/b/route.ts"]
        assert [e["file"] for e in r["added"]] == ["app/c/route.ts"]
        assert r["ambiguous_names"] == [{
            "name": "GET",
            "removed": [{"file": "app/b/route.ts", "line": 5}],
            "added": [{"file": "app/c/route.ts", "line": 5}],
        }]
        assert r["summary"]["ambiguous_names"] == 1

    def test_a_name_repeated_on_one_side_only_is_ambiguous(self):
        base = [_route("parse", "src/old.py", 1)]
        curr = [_route("parse", "src/new_a.py", 1), _route("parse", "src/new_b.py", 1)]
        r = diff_inventories(base, curr)
        assert r["moved"] == []
        assert r["summary"]["removed"] == 1 and r["summary"]["added"] == 2
        (item,) = r["ambiguous_names"]
        assert item["name"] == "parse" and len(item["added"]) == 2

    def test_a_name_repeated_in_the_baseline_only_is_ambiguous(self):
        # One GET left on the current side is no move: the baseline had two.
        base = [_route("GET", "app/a/route.ts", 3), _route("GET", "app/b/route.ts", 5)]
        curr = [_route("GET", "app/c/route.ts", 7)]
        r = diff_inventories(base, curr)
        assert r["moved"] == []
        assert [e["file"] for e in r["removed"]] == ["app/a/route.ts", "app/b/route.ts"]
        assert [e["file"] for e in r["added"]] == ["app/c/route.ts"]
        assert r["ambiguous_names"] == [{
            "name": "GET",
            "removed": [{"file": "app/a/route.ts", "line": 3}, {"file": "app/b/route.ts", "line": 5}],
            "added": [{"file": "app/c/route.ts", "line": 7}],
        }]

    def test_a_name_left_on_one_side_only_is_not_ambiguous(self):
        base = [_route("GET", "a.ts", 1), _route("GET", "b.ts", 1)]
        r = diff_inventories(base, [])
        assert r["summary"]["removed"] == 2 and r["ambiguous_names"] == []

    def test_a_unique_name_left_on_both_sides_is_a_move(self):
        r = diff_inventories([_route("helper", "src/a.ts", 4)], [_route("helper", "src/b.ts", 9)])
        assert r["moved"] == [{"name": "helper", "previous_file": "src/a.ts", "current_file": "src/b.ts",
                               "previous_line": 4, "line": 9, "confidence": None}]
        assert r["added"] == [] and r["removed"] == [] and r["ambiguous_names"] == []

    @pytest.mark.parametrize("first_listed", [True, False], ids=["listed-first", "listed-last"])
    def test_one_name_twice_in_one_file_keeps_the_first_line(self, first_listed):
        # Overload signatures repeat a name in one file: the first line wins,
        # whichever order the inventory lists them in.
        first = _route("load", "src/io.ts", 10, signature="load(a: string)")
        later = _route("load", "src/io.ts", 14, signature="load(a: Buffer)")
        curr = [first, later] if first_listed else [later, first]
        r = diff_inventories([dict(first)], curr)
        assert r["changed"] == [] and r["unchanged_count"] == 1

    def test_an_entry_without_a_file_still_matches_by_its_unique_name(self):
        r = diff_inventories([{"name": "f", "type": "function", "line": 1}],
                             [{"name": "f", "type": "function", "file": "a.py", "line": 2}])
        assert r["moved"] == []
        assert [(c["field"], c["current_value"]) for c in r["changed"]] == [("line", 2)]


resolver_spec = importlib.util.spec_from_file_location(
    "skf_resolver_for_diff", SCRIPT_PATH.parent / "skf-resolve-authoritative-files.py"
)
resolver = importlib.util.module_from_spec(resolver_spec)
resolver_spec.loader.exec_module(resolver)

# The path forms the tests below use, and the edges of the rule.
PATH_FORMS = {
    "dot-slash": "./app/users/route.ts",
    "backslashes": "app\\users\\route.ts",
    "padded": " app/posts/route.ts ",
    "dot-slash-file": "./src/io.ts",
    "backslash-file": "src\\io.ts",
    "repeated-dot-slash": "././src/a.ts",
    "dot-backslash": ".\\src\\a.ts",
    "plain": "src/a.ts",
    "dot-slash-only": "./",
    "empty": "",
    "blank": "   ",
}


class TestFilePathForms:
    """A file written with a `./` prefix or with backslashes (a snapshot
    written on Windows) names the same file as the plain path, so it neither
    invents a move nor, for a repeated name, a removal plus an addition."""

    @pytest.mark.parametrize("path", list(PATH_FORMS.values()), ids=list(PATH_FORMS))
    def test_the_file_key_is_normalize_rel_path(self, path):
        # The diff helper stays stdlib-only, so it restates the resolver's
        # rule; this pins the copy to it.
        assert mod._file_key(path) == (resolver.normalize_rel_path(path) or None)

    def test_path_forms_match_for_a_repeated_name(self):
        base = [_route("GET", "./app/users/route.ts", 3), _route("GET", "./app/posts/route.ts", 5)]
        curr = [_route("GET", "app\\users\\route.ts", 3), _route("GET", " app/posts/route.ts ", 5)]
        r = diff_inventories(base, curr)
        assert r["moved"] == [] and r["added"] == [] and r["removed"] == []
        assert r["ambiguous_names"] == [] and r["unchanged_count"] == 2

    def test_items_carry_the_file_as_written(self):
        base = [_route("load", "./src/io.ts", 10), _route("gone", "./src/io.ts", 20)]
        curr = [_route("load", "src\\io.ts", 12), _route("fresh", "src\\new.ts", 1)]
        r = diff_inventories(base, curr)
        assert r["moved"] == []
        assert [(c["name"], c["field"], c["file"]) for c in r["changed"]] == [("load", "line", "src\\io.ts")]
        assert [e["file"] for e in r["removed"]] == ["./src/io.ts"]
        assert [e["file"] for e in r["added"]] == ["src\\new.ts"]

    def test_a_real_move_still_reports_both_files_as_written(self):
        r = diff_inventories([_route("helper", "./src/a.ts", 4)], [_route("helper", "src\\b.ts", 4)])
        assert [(m["previous_file"], m["current_file"]) for m in r["moved"]] == [("./src/a.ts", "src\\b.ts")]


class TestMovedExportLine:
    """A move changes the line, so the diff does not report it again as a
    line change (which would read as a second, location finding)."""

    def test_a_moved_export_reports_no_line_change(self, baseline):
        moved_current = [
            {"name": "foo", "file": "src/new-location.ts", "line": 15, "type": "function"},
            {"name": "Bar", "file": "src/index.ts", "line": 20, "type": "class"},
        ]
        r = diff_inventories(baseline, moved_current)
        assert r["summary"]["moved"] == 1
        assert r["changed"] == [] and r["summary"]["changed"] == 0
        assert r["moved"][0]["previous_line"] == 10 and r["moved"][0]["line"] == 15

    def test_a_moved_export_still_reports_a_signature_change(self):
        base = [_route("foo", "src/a.ts", 10, signature="foo(a)")]
        curr = [_route("foo", "src/b.ts", 30, signature="foo(a, b)")]
        r = diff_inventories(base, curr)
        assert [(c["field"], c["file"], c["line"]) for c in r["changed"]] == [("signature", "src/b.ts", 30)]
        assert r["summary"]["moved"] == 1 and r["summary"]["changed"] == 1


class TestChangedItemLocation:
    def test_changed_items_carry_the_current_file_line_and_confidence(self):
        base = [_route("foo", "src/a.ts", 10, signature="foo(a)", confidence="T1-low")]
        curr = [_route("foo", "src/a.ts", 12, signature="foo(a, b)", confidence="T1")]
        r = diff_inventories(base, curr)
        for item in r["changed"]:
            assert (item["file"], item["line"], item["confidence"]) == ("src/a.ts", 12, "T1")
        assert [c["field"] for c in r["changed"]] == ["signature", "line"]

    def test_the_name_is_the_public_name_after_reexport_resolution(self):
        base = [{"name": "_Impl", "type": "class", "file": "a.py", "line": 1}]
        curr = [{"name": "Public", "type": "class", "file": "a.py", "line": 3}]
        r = diff_inventories(base, curr, {"_Impl": "Public"})
        assert [(c["name"], c["line"]) for c in r["changed"]] == [("Public", 3)]


class TestParamsAndReturnType:
    """A provenance map records a signature as params[] and return_type."""

    def test_a_parameter_change_is_detected(self):
        base = [_prov_entry(params=["query: str"], return_type="list")]
        curr = [_prov_entry(params=["query: str", "top_k: int = 10"], return_type="list")]
        r = diff_inventories(base, curr)
        assert [(c["field"], c["baseline_value"], c["current_value"]) for c in r["changed"]] == [
            ("params", ["query: str"], ["query: str", "top_k: int = 10"])]

    def test_a_return_type_change_is_detected(self):
        r = diff_inventories([_prov_entry(return_type="list")], [_prov_entry(return_type="dict")])
        assert [c["field"] for c in r["changed"]] == ["return_type"]

    def test_parameters_are_canonicalized_like_a_signature(self):
        base = [_prov_entry(params=['mode: str = "soft"', "user: typing.Optional[User] = None"])]
        curr = [_prov_entry(params=["mode: str = 'soft'", "user: Optional[User] = None"])]
        r = diff_inventories(base, curr)
        assert r["changed"] == []
        assert _transform_count(r, "quote-style") == 1
        assert _transform_count(r, "stdlib-prefix") == 1

    def test_params_on_one_side_only_are_not_compared(self):
        r = diff_inventories([_prov_entry(params=["a"])], [_snap_export(signature="search(a, b)")])
        assert r["changed"] == []
        assert [u["name"] for u in r["signature_unverified"]] == ["search"]

    def test_added_and_removed_records_carry_params_and_return_type(self):
        r = diff_inventories([_prov_entry(export_name="old", params=["x"], return_type="int")], [])
        assert (r["removed"][0]["params"], r["removed"][0]["return_type"]) == (["x"], "int")

    def test_runner_parameter_records_compare_in_the_map_form(self):
        """A recipe runner's {name, type, default, optional} parameters are written in the map's typed form
        first, so an unchanged function is not read as modified (step 5b determinism-3)."""
        base = [_prov_entry(params=["query: str", "limit: int = 10", "opts?: Options"])]
        runner = [{"name": "query", "type": "str", "default": None, "optional": False},
                   {"name": "limit", "type": "int", "default": "10", "optional": True},
                   {"name": "opts", "type": "Options", "default": None, "optional": True}]
        r = diff_inventories(base, [_snap_export(params=runner, language="typescript")])
        assert r["changed"] == []
        dropped = [dict(p) for p in runner[:2]]
        r = diff_inventories(base, [_snap_export(params=dropped, language="typescript")])
        assert [(c["field"], c["current_value"]) for c in r["changed"]] == [
            ("params", ["query: str", "limit: int = 10"])]


class TestSignatureUnverified:
    """A provenance map holds a signature as params and return_type, an
    audit snapshot as signature text. No field holds it on both sides, so
    the diff cannot compare it: it lists the export instead of passing it."""

    def test_a_changed_signature_in_the_other_form_is_listed_not_passed(self):
        base = [_prov_entry(params=["query: str"], return_type="list")]
        curr = [_snap_export(signature="search(query: str, top_k: int) -> dict")]
        r = diff_inventories(base, curr)
        assert r["changed"] == [] and r["unchanged_count"] == 1
        assert r["signature_unverified"] == [{
            "name": "search",
            "file": "cognee/api/v1/search/search.py",
            "baseline": ["params", "return_type"],
            "current": ["signature"],
        }]
        assert r["summary"]["signature_unverified"] == 1

    def test_one_part_left_uncompared_is_listed(self):
        # The return types are compared; the parameters never are.
        base = [_prov_entry(params=["query: str"], return_type="list")]
        curr = [_snap_export(signature="search(query: str, top_k: int)", return_type="list")]
        r = diff_inventories(base, curr)
        assert r["changed"] == []
        assert [(u["baseline"], u["current"]) for u in r["signature_unverified"]] == [
            (["params", "return_type"], ["signature", "return_type"])]

    def test_a_changed_or_moved_export_is_listed_too(self):
        base = [_prov_entry(params=["a"]), _prov_entry(export_name="helper", params=["b"])]
        curr = [_snap_export(signature="search(a)", line=40),
                _snap_export(name="helper", file="src/elsewhere.py", signature="helper(b)")]
        r = diff_inventories(base, curr)
        assert [c["field"] for c in r["changed"]] == ["line"] and len(r["moved"]) == 1
        assert sorted(u["name"] for u in r["signature_unverified"]) == ["helper", "search"]

    @pytest.mark.parametrize("base_fields,curr_fields", [
        ({"params": ["a"], "return_type": "int"}, {"params": ["a"], "return_type": "int"}),
        ({"signature": "f(a)"}, {"signature": "f(a)"}),
        ({"signature": "f(a) -> int", "params": ["a"]}, {"signature": "f(a) -> int"}),
        ({}, {"signature": "f(a)"}),
        ({"return_type": "int"}, {"params": ["a"]}),
    ], ids=["same-fields", "text-both-sides", "text-shared", "nothing-on-one-side", "no-shared-part"])
    def test_a_signature_compared_or_carried_by_one_side_is_not_listed(self, base_fields, curr_fields):
        r = diff_inventories([_route("f", "a.py", 1, **base_fields)], [_route("f", "a.py", 1, **curr_fields)])
        assert r["signature_unverified"] == [] and r["summary"]["signature_unverified"] == 0

    def test_added_and_removed_exports_are_never_listed(self):
        r = diff_inventories([_prov_entry(export_name="old", params=["a"])], [_snap_export(signature="new(a)")])
        assert r["summary"]["added"] == 1 and r["summary"]["removed"] == 1
        assert r["signature_unverified"] == []


class TestFileScope:
    """update-skill's Category B re-extracts only the files that changed.
    --files limits the diff to them: an export of any other file is taken as
    unchanged on both sides, never as removed."""

    def test_an_export_in_an_untouched_file_is_neither_removed_nor_unchanged(self):
        base = [_route("load", "src/a.py", 3, signature="load(p)"), _route("keep", "src/b.py", 7)]
        curr = [_route("load", "src/a.py", 3, signature="load(p, mode)")]
        assert [e["name"] for e in diff_inventories(base, curr)["removed"]] == ["keep"]
        r = diff_inventories(base, curr, files=["src/a.py"])
        assert r["removed"] == [] and r["added"] == []
        assert [(c["name"], c["field"]) for c in r["changed"]] == [("load", "signature")]
        assert r["unchanged_count"] == 0 and r["summary"]["unchanged"] == 0
        assert r["file_scope"] == {"files": 1, "baseline_left_out": 1, "current_left_out": 0}

    def test_a_classify_output_names_every_changed_file(self):
        classify = {
            "status": "ok",
            "category_a": {"modified": ["src/a.py"], "added": ["src/new.py"], "deleted": ["src/gone.py"]},
            "moved_files": [{"old_path": "src/old.py", "new_path": "src/renamed.py"}],
        }
        paths, err = mod.files_from_data(classify)
        assert err is None
        assert sorted(paths) == ["src/a.py", "src/gone.py", "src/new.py", "src/old.py", "src/renamed.py"]
        base = [_route("a", "src/a.py", 1), _route("g", "src/gone.py", 1),
                _route("m", "src/old.py", 1), _route("u", "src/untouched.py", 1)]
        curr = [_route("a", "src/a.py", 1), _route("n", "src/new.py", 1), _route("m", "src/renamed.py", 1)]
        r = diff_inventories(base, curr, files=paths)
        assert [e["name"] for e in r["removed"]] == ["g"]
        assert [e["name"] for e in r["added"]] == ["n"]
        assert [(m["name"], m["previous_file"], m["current_file"]) for m in r["moved"]] == [
            ("m", "src/old.py", "src/renamed.py")]
        # a, and m, whose move changed no field; u is left out.
        assert r["unchanged_count"] == 2
        assert r["file_scope"] == {"files": 5, "baseline_left_out": 1, "current_left_out": 0}

    def test_paths_compare_in_normalize_rel_path_form(self):
        base = [_route("a", "src/a.py", 1), _route("b", "src/b.py", 1)]
        r = diff_inventories(base, [_route("a", "src/a.py", 2)], files=[".\\src\\a.py"])
        assert r["removed"] == [] and [c["field"] for c in r["changed"]] == ["line"]

    def test_a_move_needs_the_uniqueness_a_whole_diff_would(self):
        # GET stays in app/a, a file that did not change: the GET that left
        # app/b and the one new in app/c are as ambiguous as in a diff of the
        # whole inventories, where app/a sits on both sides.
        base = [_route("GET", "app/a/route.ts", 1), _route("GET", "app/b/route.ts", 1)]
        curr = [_route("GET", "app/c/route.ts", 1)]
        scoped = diff_inventories(base, curr, files=["app/b/route.ts", "app/c/route.ts"])
        whole = diff_inventories(base, [_route("GET", "app/a/route.ts", 1), *curr])
        for r in (scoped, whole):
            assert r["moved"] == []
            assert r["ambiguous_names"] == [{
                "name": "GET",
                "removed": [{"file": "app/b/route.ts", "line": 1}],
                "added": [{"file": "app/c/route.ts", "line": 1}],
            }]

    def test_a_current_export_outside_the_files_is_left_out(self):
        base = [_route("a", "src/a.py", 1)]
        curr = [_route("a", "src/a.py", 1), _route("extra", "src/other.py", 1)]
        r = diff_inventories(base, curr, files=["src/a.py"])
        assert r["added"] == [] and r["unchanged_count"] == 1
        assert r["file_scope"]["current_left_out"] == 1

    def test_a_transform_outside_the_files_is_not_reported(self):
        base = [_route("a", "src/a.py", 1), _route("b", "src/b.py", 1, signature='b(m="x")')]
        r = diff_inventories(base, [_route("a", "src/a.py", 1)], files=["src/a.py"])
        assert r["applied_transforms"] == []

    def test_an_empty_list_leaves_everything_out(self):
        r = diff_inventories([_route("a", "src/a.py", 1)], [_route("b", "src/b.py", 1)], files=[])
        assert r["summary"]["added"] == r["summary"]["removed"] == r["summary"]["unchanged"] == 0
        assert r["file_scope"] == {"files": 0, "baseline_left_out": 1, "current_left_out": 1}

    def test_without_files_the_shape_is_unchanged(self):
        assert "file_scope" not in diff_inventories([_route("a", "src/a.py", 1)], [])

    @pytest.mark.parametrize("data", [
        {"entries": []},
        ["src/a.py", 3],
        {"category_a": {"modified": "src/a.py"}},
        {"category_a": {}, "moved_files": ["src/a.py"]},
        "src/a.py",
    ], ids=["provenance-map", "not-all-paths", "list-not-a-list", "move-not-an-object", "a-string"])
    def test_a_file_that_is_neither_form_is_refused(self, data):
        paths, err = mod.files_from_data(data, "scope.json")
        assert paths == [] and "scope.json" in err


class TestGroupBySourceLibrary:
    """A stack's libraries are diffed apart: an export never matches one of
    another library, and every item names its library."""

    def _stack(self):
        base = [
            _prov_entry(export_name="parse", source_file="src/index.ts", source_line=1, source_library="lib-a"),
            _prov_entry(export_name="parse", source_file="src/index.ts", source_line=1, source_library="lib-b"),
            _prov_entry(export_name="render", source_file="src/r.ts", source_line=5, source_library="lib-b"),
        ]
        curr = [
            _snap_export(name="parse", file="src/index.ts", line=4, source_library="lib-a"),
            _snap_export(name="render", file="src/r.ts", line=5, source_library="lib-b"),
            _snap_export(name="compile", file="src/c.ts", line=1, source_library="lib-b"),
        ]
        return base, curr

    def test_each_library_is_diffed_on_its_own(self):
        r = diff_inventories(*self._stack(), group_by="source_library")
        assert [(e["source_library"], e["name"]) for e in r["removed"]] == [("lib-b", "parse")]
        assert [(e["source_library"], e["name"]) for e in r["added"]] == [("lib-b", "compile")]
        assert [(c["source_library"], c["name"], c["field"]) for c in r["changed"]] == [
            ("lib-a", "parse", "line")]

    def test_groups_carry_per_library_summaries_that_sum_to_the_total(self):
        r = diff_inventories(*self._stack(), group_by="source_library")
        assert r["group_by"] == "source_library"
        groups = {g["source_library"]: g["summary"] for g in r["groups"]}
        assert groups["lib-a"]["changed"] == 1 and groups["lib-a"]["removed"] == 0
        assert groups["lib-b"]["removed"] == 1 and groups["lib-b"]["added"] == 1
        for key in r["summary"]:
            assert r["summary"][key] == sum(g["summary"][key] for g in r["groups"]), key

    def test_label_changes_are_tagged_and_summed(self):
        r = diff_inventories(*self._stack(), group_by="source_library")
        assert {lc["source_library"] for lc in r["label_changes"]} == {"lib-a", "lib-b"}
        assert r["summary"]["label_changes"] == len(r["label_changes"]) == 2

    def test_an_entry_without_a_library_falls_in_a_null_group(self):
        r = diff_inventories([_prov_entry()], [_snap_export(line=30)], group_by="source_library")
        assert [g["source_library"] for g in r["groups"]] == [None]
        assert r["changed"][0]["source_library"] is None

    @pytest.mark.parametrize("untagged", ["baseline", "current"])
    def test_a_side_with_no_library_against_one_with_libraries_is_an_error(self, untagged):
        # An unchanged stack whose snapshot carries no source_library would
        # otherwise diff every export against nothing: all removed and added.
        base, curr = self._stack()
        if untagged == "baseline":
            base = [{k: v for k, v in e.items() if k != "source_library"} for e in base]
        else:
            curr = [dict(e, source_library="  ") for e in curr]
        with pytest.raises(ValueError, match=(
                f"^--group-by source_library: the {untagged} inventory has no entry with source_library$")):
            diff_inventories(base, curr, group_by="source_library")

    def test_an_empty_side_is_no_error(self):
        base, _ = self._stack()
        r = diff_inventories(base, [], group_by="source_library")
        assert r["summary"]["removed"] == 3 and r["summary"]["added"] == 0

    def test_without_group_by_the_shape_is_unchanged(self):
        r = diff_inventories(*self._stack())
        assert "groups" not in r and "group_by" not in r
        assert all("source_library" not in e for e in r["added"] + r["removed"])


# --------------------------------------------------------------------------
# Public surface: a public-api snapshot's exports off the surface are no addition (#702)
# --------------------------------------------------------------------------


class TestPublicSurface:
    """skf-extraction-snapshot.py build --scope-type public-api marks each export `public`; after the pairing, an
    export marked false that pairs with no map entry goes to not_public[], never added[]. Fixtures hold no
    namespace re-export."""

    def test_an_unpaired_export_marked_false_is_not_public_not_added(self):
        r = diff_inventories([_prov_entry()], [
            _snap_export(), _snap_export(name="helper", file="cognee/api/v1/ui/ui.py", line=3, public=False),
            _snap_export(name="logger", file="cognee/__init__.py", line=34, public=True)])
        assert [(a["name"], a["public"]) for a in r["added"]] == [("logger", True)]
        assert [(n["name"], n["file"], n["public"]) for n in r["not_public"]] == [
            ("helper", "cognee/api/v1/ui/ui.py", False)]
        assert (r["summary"]["added"], r["summary"]["not_public"], r["summary"]["unchanged"]) == (1, 1, 1)
        # the item is the normalized record added[] holds
        assert set(r["not_public"][0]) == set(r["added"][0])

    @pytest.mark.parametrize("line", [27, 31], ids=["unchanged", "changed"])
    def test_a_map_entry_off_the_surface_is_compared_never_removed(self, line):
        """A map written before create-skill kept a public-api map to the surface holds internals: matched, they are
        unchanged or changed, whatever their mark."""
        r = diff_inventories([_prov_entry()], [_snap_export(line=line, public=False)])
        assert r["removed"] == [] and r["added"] == [] and r["not_public"] == []
        assert (r["summary"]["unchanged"], r["summary"]["changed"]) == ((1, 0) if line == 27 else (0, 1))

    def test_a_move_off_the_surface_is_a_move(self):
        r = diff_inventories([_prov_entry()], [_snap_export(file="cognee/modules/search/impl.py", public=False)])
        assert [(m["name"], m["current_file"]) for m in r["moved"]] == [("search", "cognee/modules/search/impl.py")]
        assert r["removed"] == r["added"] == r["not_public"] == []

    def test_an_ambiguous_name_stays_in_added(self):
        """A reviewer judges whether a removed and an added entry of one name are one export that moved, so a
        leftover of an ambiguous name stays in added[] whatever its mark."""
        base = [_route("GET", "routes/a.ts", 1), _route("GET", "routes/b.ts", 1)]
        curr = [_route("GET", "routes/c.ts", 1, public=False)]
        r = diff_inventories(base, curr)
        assert [a["name"] for a in r["ambiguous_names"]] == ["GET"]
        assert [(a["name"], a["file"], a["public"]) for a in r["added"]] == [("GET", "routes/c.ts", False)]
        assert r["not_public"] == [] and r["summary"]["not_public"] == 0

    @pytest.mark.parametrize("mark", [{}, {"public": None}, {"public": "false"}, {"public": 0}],
                             ids=["absent", "null", "a-string", "a-number"])
    def test_an_unmarked_inventory_diffs_as_before(self, mark):
        """An older snapshot, or any other scope type, marks nothing: the export is added, its record carries no
        `public`, and not_public[] is empty. Only true or false is a mark."""
        r = diff_inventories([], [_snap_export(name="helper", file="x.py", **mark)])
        assert [a["name"] for a in r["added"]] == ["helper"] and "public" not in r["added"][0]
        assert (r["not_public"], r["summary"]["not_public"]) == ([], 0)

    def test_not_public_is_tagged_and_summed_by_library(self):
        base = [_prov_entry(source_library="lib-a")]
        curr = [_snap_export(source_library="lib-a"),
                _snap_export(name="inner", file="a/inner.py", source_library="lib-a", public=False),
                _snap_export(name="inner", file="b/inner.py", source_library="lib-b", public=False)]
        r = diff_inventories(base, curr, group_by="source_library")
        assert [(n["source_library"], n["name"]) for n in r["not_public"]] == [("lib-a", "inner"), ("lib-b", "inner")]
        assert {g["source_library"]: g["summary"]["not_public"] for g in r["groups"]} == {"lib-a": 1, "lib-b": 1}
        assert r["summary"]["not_public"] == 2 and r["added"] == []


class TestCurrentExtra:
    """--current-extra adds to a recipe runner's records what the recipes do not record (update-skill Category B)."""

    def _runner(self):
        return {"exports": [{"export_name": "search", "export_type": "function", "source_file": "pkg/api.py",
                             "source_line": 5, "confidence": "T1", "extraction_method": "ast-grep"}]}

    def test_merge_fills_what_an_entry_lacks_and_adds_the_rest(self):
        merged = mod.merge_extra(self._runner()["exports"], [
            {"export_name": "search", "source_file": "./pkg/api.py", "params": ["q: str"], "return_type": None,
             "source_line": 99},
            {"export_name": "by_eye", "export_type": "function", "source_file": "pkg/api.py", "source_line": 20,
             "params": [], "confidence": "T1-low", "extraction_method": "source-read"},
        ])
        assert merged[0]["params"] == ["q: str"] and merged[0]["source_line"] == 5  # filled, never overwritten
        assert "return_type" not in merged[0]
        assert [m["export_name"] for m in merged] == ["search", "by_eye"]

    def test_an_alias_counts_as_the_field(self):
        merged = mod.merge_extra([{"name": "f", "file": "a.py", "line": 3}],
                                 [{"export_name": "f", "source_file": "a.py", "source_line": 8}])
        assert merged == [{"name": "f", "file": "a.py", "line": 3}]

    def test_the_cli_diffs_the_merged_inventory(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [
            {"export_name": "search", "export_type": "function", "source_file": "pkg/api.py", "source_line": 5,
             "params": ["q: str"], "return_type": None},
            {"export_name": "by_eye", "export_type": "function", "source_file": "pkg/api.py", "source_line": 20}]})
        curr = _write(tmp_path / "extraction.json", self._runner())
        extra = _write(tmp_path / "details.json", {"exports": [
            {"export_name": "search", "source_file": "pkg/api.py", "params": ["q: str", "limit: int"]},
            {"export_name": "by_eye", "export_type": "function", "source_file": "pkg/api.py", "source_line": 20}]})
        res = _run([str(base), str(curr), "--current-extra", str(extra)])
        assert res.returncode == 1, res.stdout + res.stderr
        out = json.loads(res.stdout)
        # the params the extra file gave are compared, and the export read by eye is not removed
        assert [(c["name"], c["field"]) for c in out["changed"]] == [("search", "params")]
        assert out["removed"] == [] and out["added"] == []

    def test_an_unreadable_extra_file_exits_2(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": []})
        res = _run([str(base), str(base), "--current-extra", str(tmp_path / "absent.json")])
        assert res.returncode == 2
        assert json.loads(res.stdout)["status"] == "error"


# --------------------------------------------------------------------------
# export-type: a by-eye kind against the runner's base kind (#680)
# --------------------------------------------------------------------------


def _by_eye(name="add", export_type="async_function", **overrides):
    """A provenance-map entry read by eye: its kind, its params, no signature."""
    return _prov_entry(**{"export_name": name, "export_type": export_type, "source_file": f"pkg/{name}.py",
                          "source_line": 10, "params": ["x: int"], **overrides})


def _runner(name="add", export_type="function", signature="async def add(x: int):", **overrides):
    """The recipe runner's snapshot export of the same declaration."""
    return _snap_export(**{"name": name, "type": export_type, "file": f"pkg/{name}.py", "line": 10,
                           "signature": signature, **overrides})


class TestExportTypeCanonicalization:
    """oms-cognee 1.0.0's map records `async_function`, `decorator` and
    `enum` where the runner records `function` and `class`: the two name one
    kind when the runner's signature shows that form, and nothing else
    collapses. `type` is compared pairwise, never rewritten."""

    def test_a_by_eye_async_against_an_async_def_is_unchanged(self):
        r = diff_inventories([_by_eye()], [_runner()])
        assert r["changed"] == [] and r["summary"]["changed"] == 0 and r["unchanged_count"] == 1
        assert _transform_count(r, "export-type") == 1

    @pytest.mark.parametrize("by_eye, base, signature", [
        ("async_function", "function", "export async function add(x: number): Promise<void> {"),
        ("async_function", "function", "export default async function add(x) {"),
        ("async_function", "function", "pub async fn add(x: i32) -> i32 {"),
        ("async_function", "function", "pub(crate) async fn add(x: i32) {"),
        ("async_function", "function", "pub async unsafe fn add(x: i32) {"),
        ("async_function", "function", "export const add = async (x) => x;"),
        ("async_function", "function", "const add: (x: number) => Promise<number> = async (x) => x;"),
        ("async_function", "function", "export let add = async function (x) {"),
        ("decorator", "function", "def add(*, name: str | None = None):"),
        ("decorator", "function", "async def add(fn):"),
        ("enum", "class", "class SearchType(str, Enum):"),
        ("enum", "class", "class Color(enum.IntFlag):"),
        ("enum", "class", "class Level(StrEnum, metaclass=Meta):"),
        ("enum", "class", "class Perm(Flag):"),
        ("enum", "class", "class Mode(ReprEnum):"),
    ], ids=["ts-async", "ts-default-async", "rust-async", "rust-pub-crate", "rust-async-unsafe", "async-arrow",
            "typed-async-arrow", "async-function-expression", "decorator-def", "decorator-async-def", "str-enum",
            "enum-prefix", "str-enum-base", "flag", "repr-enum"])
    def test_each_form_collapses(self, by_eye, base, signature):
        r = diff_inventories([_by_eye(export_type=by_eye)], [_runner(export_type=base, signature=signature)])
        assert r["changed"] == [], signature
        assert _transform_count(r, "export-type") == 1

    @pytest.mark.parametrize("by_eye, base, signature", [
        ("async_function", "function", "def add(x: int):"),
        ("async_function", "function", "export function add(cb = async function () {}) {"),
        ("async_function", "function", "export const add = (x) => async () => x;"),
        ("async_function", "function", None),
        ("decorator", "function", "export function add(target) {"),
        ("decorator", "class", "class add:"),
        ("enum", "class", "export class SearchType {"),
        ("enum", "class", "class SearchType(str, MyEnum):"),
        ("enum", "class", "class SearchType(aenum.Enum):"),
        ("enum", "class", None),
        ("async_function", "class", "class add:"),
        ("const", "variable", "const add = 1"),
        ("namespace", "module", "export namespace add {"),
        ("sentinel", "variable", "add = _Drop()"),
    ], ids=["plain-def", "async-in-a-default", "arrow-returning-async", "no-signature", "ts-decorator", "decorator-class",
            "ts-class", "user-enum-base", "third-party-enum", "enum-no-signature", "async-vs-class", "const",
            "namespace", "sentinel"])
    def test_anything_else_stays_a_type_change(self, by_eye, base, signature):
        r = diff_inventories([_by_eye(export_type=by_eye)], [_runner(export_type=base, signature=signature)])
        assert [(c["field"], c["baseline_value"], c["current_value"]) for c in r["changed"]] == [
            ("type", by_eye, base)]
        assert _transform_count(r, "export-type") == 0

    def test_the_signature_must_be_on_the_base_kind_side(self):
        # an `async def` the by-eye side records proves nothing about the runner's `function`
        base = [_by_eye(signature="async def add(x: int):")]
        r = diff_inventories(base, [_runner(signature=None)])
        assert [c["field"] for c in r["changed"]] == ["type"]

    def test_either_side_may_hold_the_by_eye_kind(self):
        # update-skill diffs a runner-built map against a by-eye re-read too
        base = [_runner(name="add", signature="async def add(x: int):")]
        curr = [_by_eye(export_type="async_function")]
        r = diff_inventories(base, curr)
        assert [c["field"] for c in r["changed"] if c["field"] == "type"] == []
        assert _transform_count(r, "export-type") == 1

    def test_type_is_never_rewritten(self):
        # a collapsed export with a moved line keeps both kinds as written, and so do unmatched exports
        base = [_by_eye(), _by_eye(name="gone", export_type="enum")]
        curr = [_runner(line=39), _runner(name="new", export_type="function", signature="async def new():")]
        r = diff_inventories(base, curr)
        assert [(c["name"], c["field"], c["baseline_value"], c["current_value"]) for c in r["changed"]] == [
            ("add", "line", 10, 39)]
        assert [(e["name"], e["type"]) for e in r["removed"]] == [("gone", "enum")]
        assert [(e["name"], e["type"]) for e in r["added"]] == [("new", "function")]
        assert _transform_count(r, "export-type") == 1

    def test_a_collapse_counts_once_per_export(self):
        base = [_by_eye(name=n) for n in ("add", "cognify")] + [_by_eye(name="SearchType", export_type="enum")]
        curr = [_runner(name="add"), _runner(name="cognify", signature="async def cognify():"),
                _runner(name="SearchType", export_type="class", signature="class SearchType(str, Enum):")]
        r = diff_inventories(base, curr)
        assert r["changed"] == [] and _transform_count(r, "export-type") == 3
        names = [t["transform"] for t in r["applied_transforms"]]
        assert names == sorted(names) and "export-type" in names

    def test_a_moved_export_collapses_too(self):
        r = diff_inventories([_by_eye()], [_runner(file="pkg/new.py", line=3)])
        assert r["summary"]["moved"] == 1 and r["changed"] == []
        assert _transform_count(r, "export-type") == 1

    def test_files_scope_counts_only_the_exports_in_scope(self):
        base = [_by_eye(name="add"), _by_eye(name="keep")]
        curr = [_runner(name="add"), _runner(name="keep", signature="async def keep():")]
        r = diff_inventories(base, curr, files=["pkg/add.py"])
        assert r["changed"] == [] and r["unchanged_count"] == 1
        assert _transform_count(r, "export-type") == 1
        assert r["file_scope"]["baseline_left_out"] == 1

    def test_group_by_collapses_within_each_library(self):
        base = [_by_eye(source_library="lib-a"), _by_eye(name="paint", export_type="enum", source_library="lib-b")]
        curr = [_runner(source_library="lib-a"),
                _runner(name="paint", export_type="class", signature="class paint(IntEnum):", source_library="lib-b"),
                _runner(source_library="lib-b", signature="def add(x: int):")]
        r = diff_inventories(base, curr, group_by="source_library")
        assert r["changed"] == [] and _transform_count(r, "export-type") == 2
        assert [(e["source_library"], e["name"]) for e in r["added"]] == [("lib-b", "add")]
        assert {g["source_library"]: g["summary"]["unchanged"] for g in r["groups"]} == {"lib-a": 1, "lib-b": 1}

    def test_the_cli_exits_0_when_only_kinds_differ(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [
            _by_eye(confidence="T1", extraction_method="ast-grep")]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [_runner(confidence="T1")]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 0, res.stdout + res.stderr
        assert {"transform": "export-type", "count": 1} in json.loads(res.stdout)["applied_transforms"]


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

    def test_invalid_json_exits_2(self, tmp_path):
        # An error has its own exit code: 1 means only "differences found".
        base = tmp_path / "b.json"
        base.write_text("{not json", encoding="utf-8")
        curr = _write(tmp_path / "c.json", {"exports": []})
        res = _run([str(base), str(curr)])
        assert res.returncode == 2
        assert json.loads(res.stdout)["status"] == "error"

    @pytest.mark.parametrize("problem", ["missing-file", "unknown-shape", "bad-reexport-map", "bad-files"])
    def test_every_error_exits_2(self, tmp_path, problem):
        base = _write(tmp_path / "b.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export(line=99)]})
        args = [str(base), str(curr)]
        if problem == "missing-file":
            args = [str(tmp_path / "absent.json"), str(curr)]
        elif problem == "unknown-shape":
            args = [str(base), str(_write(tmp_path / "x.json", "a string"))]
        elif problem == "bad-reexport-map":
            args += ["--reexport-map", str(_write(tmp_path / "m.json", ["not", "an", "object"]))]
        else:
            args += ["--files", str(base)]
        res = _run(args)
        assert res.returncode == 2, res.stdout
        assert json.loads(res.stdout)["status"] == "error"

    def test_files_on_the_cli(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [
            _prov_entry(), _prov_entry(export_name="other", source_file="src/other.py")]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [_snap_export(line=31)]})
        scope = _write(tmp_path / "category-a.json", {
            "status": "ok",
            "category_a": {"modified": ["cognee/api/v1/search/search.py"], "added": [], "deleted": []},
            "moved_files": [],
        })
        res = _run([str(base), str(curr), "--files", str(scope)])
        assert res.returncode == 1, res.stdout + res.stderr
        out = json.loads(res.stdout)
        assert out["removed"] == [] and [c["field"] for c in out["changed"]] == ["line"]
        assert out["file_scope"] == {"files": 1, "baseline_left_out": 1, "current_left_out": 0}

    def test_exports_off_the_public_surface_alone_exit_0(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [
            _snap_export(public=True), _snap_export(name="helper", file="x.py", public=False)]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 0, res.stdout + res.stderr
        out = json.loads(res.stdout)
        assert out["summary"]["not_public"] == 1 and out["summary"]["added"] == 0
        assert [n["name"] for n in out["not_public"]] == ["helper"]

    def test_an_unverified_signature_alone_exits_0(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [_prov_entry(params=["a"])]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [_snap_export(signature="search(a, b)")]})
        res = _run([str(base), str(curr)])
        assert res.returncode == 0, res.stdout + res.stderr
        assert json.loads(res.stdout)["summary"]["signature_unverified"] == 1

    def test_help_prints_the_contract(self):
        res = _run(["--help"])
        assert res.returncode == 0, res.stderr
        for section in ("Matching:", "Public surface:", "File scope (--files FILE):", "ambiguous_names:",
                        "signature_unverified:", "not_public:", "Exit codes:"):
            assert section in res.stdout, section

    def test_output_file_prints_a_summary_line(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export(line=31)]})
        out_path = tmp_path / "structural-diff.json"
        res = _run([str(base), str(curr), "-o", str(out_path)])
        assert res.returncode == 1
        line = json.loads(res.stdout)
        assert line["status"] == "ok"
        assert Path(line["output"]) == out_path
        saved = json.loads(out_path.read_text(encoding="utf-8"))
        assert line["summary"] == saved["summary"]
        assert saved["changed"][0]["field"] == "line"

    def test_unwritable_output_exits_2(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": [_prov_entry()]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export()]})
        res = _run([str(base), str(curr), "-o", str(tmp_path / "no-such-folder" / "diff.json")])
        assert res.returncode == 2
        assert json.loads(res.stdout)["status"] == "error"

    def test_group_by_on_the_cli(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": [
            _prov_entry(source_library="lib-a"), _prov_entry(source_library="lib-b")]})
        curr = _write(tmp_path / "c.json", {"exports": [_snap_export(source_library="lib-a")]})
        res = _run([str(base), str(curr), "--group-by", "source_library"])
        assert res.returncode == 1
        out = json.loads(res.stdout)
        assert out["group_by"] == "source_library"
        assert [g["source_library"] for g in out["groups"]] == ["lib-a", "lib-b"]
        assert [(r["source_library"], r["name"]) for r in out["removed"]] == [("lib-b", "search")]

    def test_group_by_over_a_snapshot_without_libraries_exits_2(self, tmp_path):
        base = _write(tmp_path / "provenance-map.json", {"entries": [
            _prov_entry(source_library="lib-a"), _prov_entry(export_name="render", source_library="lib-b")]})
        curr = _write(tmp_path / "extraction-snapshot.json", {"exports": [
            _snap_export(), _snap_export(name="render")]})
        res = _run([str(base), str(curr), "--group-by", "source_library"])
        assert res.returncode == 2, res.stdout
        assert json.loads(res.stdout) == {
            "status": "error",
            "error": f"--group-by source_library: {curr} has no entry with source_library",
        }

    def test_unknown_group_by_is_a_usage_error(self, tmp_path):
        base = _write(tmp_path / "b.json", {"entries": []})
        res = _run([str(base), str(base), "--group-by", "package"])
        assert res.returncode == 2
        assert "invalid choice" in res.stderr
