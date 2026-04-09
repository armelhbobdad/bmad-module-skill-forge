#!/usr/bin/env python3
"""Tests for skf-severity-classify.py."""

from __future__ import annotations

import importlib.util

import pytest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "skf_severity",
    Path(__file__).parent.parent / "src" / "shared" / "scripts" / "skf-severity-classify.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
classify_all = mod.classify_all


class TestEmptyFindings:
    """Suite 1: Empty findings."""

    def test_clean_on_empty(self):
        r = classify_all([])
        assert r["drift_score"] == "CLEAN"
        assert r["total_findings"] == 0


class TestCriticalRemovedExport:
    """Suite 2: Critical -- removed export."""

    def test_critical_score(self):
        r = classify_all([
            {"type": "removed", "category": "export", "detail": "function foo() removed"},
        ])
        assert r["drift_score"] == "CRITICAL"
        assert r["findings"][0]["severity"] == "CRITICAL"
        assert r["by_severity"]["CRITICAL"] == 1


class TestCriticalChangedSignature:
    """Suite 3: Changed signature."""

    def test_critical_on_signature_change(self):
        r = classify_all([
            {"type": "changed", "category": "signature", "detail": "param count changed"},
        ])
        assert r["drift_score"] == "CRITICAL"


class TestHighManyAddedExports:
    """Suite 4: HIGH -- >3 added exports."""

    def test_significant_score(self):
        r = classify_all([
            {"type": "added", "category": "export", "detail": "new fn 1"},
            {"type": "added", "category": "export", "detail": "new fn 2"},
            {"type": "added", "category": "export", "detail": "new fn 3"},
            {"type": "added", "category": "export", "detail": "new fn 4"},
        ])
        assert r["drift_score"] == "SIGNIFICANT"
        assert r["by_severity"]["HIGH"] == 4


class TestMediumFewAddedExports:
    """Suite 5: MEDIUM -- 1-3 added exports."""

    def test_medium_threshold(self):
        r = classify_all([
            {"type": "added", "category": "export", "detail": "new fn 1"},
            {"type": "added", "category": "export", "detail": "new fn 2"},
        ])
        assert r["by_severity"]["MEDIUM"] == 2


class TestLowConvention:
    """Suite 6: LOW -- convention changes."""

    def test_minor_score(self):
        r = classify_all([
            {"type": "changed", "category": "convention", "detail": "naming style changed"},
            {"type": "changed", "category": "comment", "detail": "docs updated"},
        ])
        assert r["drift_score"] == "MINOR"
        assert r["by_severity"]["LOW"] == 2


class TestMixedSeverities:
    """Suite 7: Mixed severities."""

    def test_critical_wins(self):
        r = classify_all([
            {"type": "removed", "category": "export", "detail": "critical"},
            {"type": "changed", "category": "implementation", "detail": "medium"},
            {"type": "changed", "category": "style", "detail": "low"},
        ])
        assert r["drift_score"] == "CRITICAL"
        assert r["findings"][0]["severity"] == "CRITICAL"
        assert r["findings"][-1]["severity"] == "LOW"


class TestSemanticFindings:
    """Suite 8: Semantic findings."""

    def test_semantic_medium_default(self):
        r = classify_all([
            {"type": "semantic", "category": "behavior", "detail": "meaning shifted"},
        ])
        assert r["findings"][0]["severity"] == "MEDIUM"


class TestMovedExports:
    """Suite 9: Moved exports."""

    def test_moved_medium(self):
        r = classify_all([
            {"type": "moved", "category": "export", "detail": "foo moved from a.ts to b.ts"},
        ])
        assert r["findings"][0]["severity"] == "MEDIUM"


class TestDeprecatedExport:
    """Suite 10: Deprecated export."""

    def test_deprecated_high(self):
        r = classify_all([
            {"type": "deprecated", "category": "export", "detail": "function bar() deprecated"},
        ])
        assert r["findings"][0]["severity"] == "HIGH"
        assert r["drift_score"] == "SIGNIFICANT"


class TestInvalidInput:
    """Suite 11: Invalid input."""

    def test_error_on_non_array(self):
        r = classify_all("not an array")
        assert r["status"] == "error"
