#!/usr/bin/env python3
"""Tests for src/skf-test-skill/scripts/aggregate-coherence.py.

The contextual-coherence tally + 0.6/0.4 weighted mean that coverage-check.md
now delegates to instead of computing in-prompt. Runs the module's embedded
doctests plus reference-value and CLI (exit-code) checks.
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-test-skill"
    / "scripts"
    / "aggregate-coherence.py"
)

spec = importlib.util.spec_from_file_location("aggregate_coherence", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_embedded_doctests_pass():
    results = doctest.testmod(mod, verbose=False)
    assert results.failed == 0, f"{results.failed} doctest(s) failed"


def test_both_patterns_weighted_mean():
    # referenceValidity = 6/7 = 85.71; integrationCompleteness = 4/5 = 80.0
    # combined = 0.6*85.71 + 0.4*80 = 83.43 (2dp)
    out = mod.aggregate_coherence(
        {"valid_references": 6, "total_references": 7, "patterns_documented": 5, "patterns_complete": 4}
    )
    assert out["referenceValidity"] == 85.71
    assert out["integrationCompleteness"] == 80.0
    assert out["combinedCoherence"] == 83.43


def test_single_pattern_no_integrations():
    out = mod.aggregate_coherence(
        {"valid_references": 9, "total_references": 10, "patterns_documented": 0, "patterns_complete": 0}
    )
    assert out["integrationCompleteness"] is None
    assert out["referenceValidity"] == 90.0
    assert out["combinedCoherence"] == 90.0


def test_zero_reference_denominator():
    out = mod.aggregate_coherence(
        {"valid_references": 0, "total_references": 0, "patterns_documented": 2, "patterns_complete": 1}
    )
    assert out["referenceValidity"] == 100.0


def test_invalid_valid_exceeds_total_errors():
    out = mod.aggregate_coherence(
        {"valid_references": 5, "total_references": 3, "patterns_documented": 0, "patterns_complete": 0}
    )
    assert out.get("code") == "INVALID_INPUT"


def _cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True, text=True
    )


def test_cli_json_input_roundtrip():
    payload = json.dumps(
        {"valid_references": 6, "total_references": 7, "patterns_documented": 5, "patterns_complete": 4}
    )
    proc = _cli(["--json-input", payload])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["combinedCoherence"] == 83.43


def test_cli_stdin():
    payload = json.dumps(
        {"valid_references": 9, "total_references": 10, "patterns_documented": 0, "patterns_complete": 0}
    )
    proc = _cli(["--stdin"], stdin=payload)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["referenceValidity"] == 90.0
