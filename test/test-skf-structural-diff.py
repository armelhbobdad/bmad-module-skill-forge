#!/usr/bin/env python3
"""Tests for skf-structural-diff.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "skf_diff",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-structural-diff.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
diff_inventories = mod.diff_inventories


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
