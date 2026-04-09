#!/usr/bin/env python3
"""Contract tests for compute-score.py.

Validates that the Python implementation produces identical output for all
test fixtures. Fixtures were originally captured from the JavaScript
implementation and serve as the source of truth for Python parity.
"""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "compute_score",
    Path(__file__).parent.parent / "src" / "skf-test-skill" / "scripts" / "compute-score.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
compute_score = mod.compute_score

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "compute-score-contract.json"


def normalize_for_comparison(obj):
    """Normalize JSON-serializable object for comparison.

    Handles float/int equivalence (e.g., 0 vs 0.0) by round-tripping
    through JSON serialization -- the same format both implementations
    use for CLI output.
    """
    return json.loads(json.dumps(obj))


def deep_diff(expected, actual, path=""):
    """Find all differences between two nested structures."""
    diffs = []

    if type(expected) != type(actual):
        # Allow int/float equivalence
        if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if expected != actual:
                diffs.append(f"{path}: {expected!r} != {actual!r}")
        else:
            diffs.append(f"{path}: type {type(expected).__name__} != {type(actual).__name__}")
        return diffs

    if isinstance(expected, dict):
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in sorted(all_keys):
            if key not in expected:
                diffs.append(f"{path}.{key}: missing in expected, present in actual = {actual[key]!r}")
            elif key not in actual:
                diffs.append(f"{path}.{key}: present in expected = {expected[key]!r}, missing in actual")
            else:
                diffs.extend(deep_diff(expected[key], actual[key], f"{path}.{key}"))
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append(f"{path}: list length {len(expected)} != {len(actual)}")
        for i in range(min(len(expected), len(actual))):
            diffs.extend(deep_diff(expected[i], actual[i], f"{path}[{i}]"))
    elif expected != actual:
        diffs.append(f"{path}: {expected!r} != {actual!r}")

    return diffs


def _load_fixtures():
    with open(FIXTURES_PATH) as f:
        fixtures = json.load(f)
    return fixtures


def _fixture_ids():
    return [fixture["name"] for fixture in _load_fixtures()]


def _fixture_params():
    return _load_fixtures()


class TestComputeScoreContract:
    @pytest.mark.parametrize("fixture", _fixture_params(), ids=_fixture_ids())
    def test_output_matches_expected(self, fixture):
        expected = normalize_for_comparison(fixture["expected_output"])
        actual = normalize_for_comparison(compute_score(fixture["input"]))
        diffs = deep_diff(expected, actual)
        assert not diffs, (
            f"Python output differs from JS for '{fixture['name']}':\n"
            + "\n".join(diffs[:10])
            + (f"\n... and {len(diffs) - 10} more differences" if len(diffs) > 10 else "")
        )
