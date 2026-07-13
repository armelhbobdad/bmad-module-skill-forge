#!/usr/bin/env python3
"""Tests for skf-coverage-tally.py (skf-verify-stack coverage.md §6).

Covers Covered/Missing/Replaced counting, the Replaced-excluded denominator,
half-up percentage rounding, validation (bad tokens, duplicates), and the
subprocess CLI contract (exit codes + JSON-on-stdout).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-verify-stack" / "scripts" / "skf-coverage-tally.py"

spec = importlib.util.spec_from_file_location("skf_coverage_tally", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
tally = mod.tally


def test_basic_counts_and_percentage():
    out = tally(
        {
            "rows": [
                {"technology": "react", "verdict": "Covered"},
                {"technology": "express", "verdict": "Covered"},
                {"technology": "postgres", "verdict": "Missing"},
            ]
        }
    )
    assert out["covered_count"] == 2
    assert out["missing_count"] == 1
    assert out["replaced_count"] == 0
    assert out["live_count"] == 3
    assert out["total_referenced"] == 3
    assert out["coverage_percentage"] == 67  # round-half-up(2/3*100)=66.66..->67


def test_replaced_excluded_from_denominator():
    out = tally(
        {
            "rows": [
                {"technology": "react", "verdict": "Covered"},
                {"technology": "old-orm", "verdict": "Replaced"},
                {"technology": "legacy-ui", "verdict": "Replaced"},
            ]
        }
    )
    # live_count = Covered + Missing only; Replaced never dilutes the percentage.
    assert out["live_count"] == 1
    assert out["replaced_count"] == 2
    assert out["total_referenced"] == 3
    assert out["coverage_percentage"] == 100


def test_all_replaced_is_zero_not_divide_by_zero():
    out = tally({"rows": [{"technology": "x", "verdict": "Replaced"}]})
    assert out["live_count"] == 0
    assert out["coverage_percentage"] == 0


def test_full_coverage():
    out = tally(
        {
            "rows": [
                {"technology": "a", "verdict": "Covered"},
                {"technology": "b", "verdict": "Covered"},
            ]
        }
    )
    assert out["coverage_percentage"] == 100


def test_half_up_rounding():
    # 1/8 covered -> 12.5% -> half-up -> 13
    rows = [{"technology": f"cov{i}", "verdict": "Covered"} for i in range(1)]
    rows += [{"technology": f"miss{i}", "verdict": "Missing"} for i in range(7)]
    out = tally({"rows": rows})
    assert out["live_count"] == 8
    assert out["coverage_percentage"] == 13


def test_empty_rows():
    out = tally({"rows": []})
    assert out["coverage_percentage"] == 0
    assert out["total_referenced"] == 0


def test_invalid_verdict_token():
    out = tally({"rows": [{"technology": "x", "verdict": "covered"}]})  # lowercase
    assert out.get("code") == "INVALID_INPUT"


def test_duplicate_technology_rejected():
    out = tally(
        {
            "rows": [
                {"technology": "React", "verdict": "Covered"},
                {"technology": "react", "verdict": "Missing"},
            ]
        }
    )
    assert out.get("code") == "INVALID_INPUT"


def test_missing_rows_field():
    assert tally({}).get("code") == "INVALID_INPUT"
    assert tally("nope").get("code") == "INVALID_INPUT"


# --- CLI / subprocess contract ---------------------------------------------


def _run(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_success():
    payload = json.dumps({"rows": [{"technology": "react", "verdict": "Covered"}]})
    proc = _run(["--stdin"], stdin=payload)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["coverage_percentage"] == 100


def test_cli_positional_success():
    payload = json.dumps({"rows": [{"technology": "react", "verdict": "Missing"}]})
    proc = _run([payload])
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["coverage_percentage"] == 0


def test_cli_no_input_exit_1():
    proc = _run([])
    assert proc.returncode == 1


def test_cli_bad_json_exit_1():
    proc = _run(["{not json"])
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_invalid_schema_exit_2():
    payload = json.dumps({"rows": [{"technology": "x", "verdict": "Bogus"}]})
    proc = _run([payload])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
