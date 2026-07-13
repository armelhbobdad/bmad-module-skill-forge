#!/usr/bin/env python3
"""Tests for skf-report-delta.py (skf-verify-stack synthesize.md §3).

Covers improved/regressed/unchanged/new/dropped classification across the
coverage and integration verdict rankings, unordered integration-pair matching,
Replaced bucketing, confidence-tier downgrade detection, validation, and the
subprocess CLI contract.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "src" / "skf-verify-stack" / "scripts" / "skf-report-delta.py"

spec = importlib.util.spec_from_file_location("skf_report_delta", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
compute = mod.compute


def test_coverage_improved_and_regressed():
    out = compute(
        {
            "previous": {
                "coverage": [
                    {"technology": "react", "verdict": "Missing"},
                    {"technology": "express", "verdict": "Covered"},
                ]
            },
            "current": {
                "coverage": [
                    {"technology": "react", "verdict": "Covered"},   # improved
                    {"technology": "express", "verdict": "Missing"},  # regressed
                ]
            },
        }
    )
    assert out["improvedCount"] == 1
    assert out["regressedCount"] == 1
    assert out["unchangedCount"] == 0
    assert "react" in out["improved"]
    assert "express" in out["regressed"]


def test_integration_ranking():
    out = compute(
        {
            "previous": {
                "integration": [
                    {"libA": "a", "libB": "b", "verdict": "Risky"},
                    {"libA": "c", "libB": "d", "verdict": "Verified"},
                ]
            },
            "current": {
                "integration": [
                    {"libA": "a", "libB": "b", "verdict": "Verified"},  # Risky->Verified improved
                    {"libA": "c", "libB": "d", "verdict": "Blocked"},   # Verified->Blocked regressed
                ]
            },
        }
    )
    assert out["improvedCount"] == 1
    assert out["regressedCount"] == 1


def test_integration_pair_order_independent():
    out = compute(
        {
            "previous": {"integration": [{"libA": "react", "libB": "express", "verdict": "Plausible"}]},
            "current": {"integration": [{"libA": "express", "libB": "react", "verdict": "Verified"}]},
        }
    )
    # Same unordered pair -> matched -> improved, not new+dropped.
    assert out["improvedCount"] == 1
    assert out["newCount"] == 0
    assert out["droppedCount"] == 0


def test_new_and_dropped():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "old", "verdict": "Covered"}]},
            "current": {"coverage": [{"technology": "shiny", "verdict": "Covered"}]},
        }
    )
    assert out["newCount"] == 1 and "shiny" in out["new"]
    assert out["droppedCount"] == 1 and "old" in out["dropped"]


def test_unchanged():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "react", "verdict": "Covered"}]},
            "current": {"coverage": [{"technology": "react", "verdict": "Covered"}]},
        }
    )
    assert out["unchangedCount"] == 1


def test_replaced_bucketed_not_regressed():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "orm", "verdict": "Covered"}]},
            "current": {"coverage": [{"technology": "orm", "verdict": "Replaced"}]},
        }
    )
    # Covered -> Replaced is intentional removal, not a regression.
    assert out["regressedCount"] == 0
    assert out["replacedCount"] == 1


def test_tier_downgrade():
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"react": "T1", "express": "T1-low", "vue": "T2"},
            "currentTiers": {"react": "T2", "express": "T1-low", "vue": "T2"},
        }
    )
    assert out["tierDowngradeCount"] == 1
    assert out["tierDowngrades"][0]["skill"] == "react"
    assert out["tierDowngrades"][0]["from"] == "T1"
    assert out["tierDowngrades"][0]["to"] == "T2"


def test_tier_t1_to_t1low_is_downgrade():
    out = compute(
        {
            "previous": {},
            "current": {},
            "previousTiers": {"x": "T1"},
            "currentTiers": {"x": "T1-low"},
        }
    )
    assert out["tierDowngradeCount"] == 1


def test_no_tiers_no_downgrades():
    out = compute({"previous": {}, "current": {}})
    assert out["tierDowngradeCount"] == 0


def test_invalid_missing_sides():
    assert compute({"previous": {}}).get("code") == "INVALID_INPUT"
    assert compute("nope").get("code") == "INVALID_INPUT"


def test_invalid_verdict_token():
    out = compute(
        {
            "previous": {"coverage": [{"technology": "x", "verdict": "covered"}]},
            "current": {"coverage": []},
        }
    )
    assert out.get("code") == "INVALID_INPUT"


# --- CLI / subprocess contract ---------------------------------------------


def _run(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_success():
    payload = json.dumps(
        {
            "previous": {"coverage": [{"technology": "react", "verdict": "Missing"}]},
            "current": {"coverage": [{"technology": "react", "verdict": "Covered"}]},
        }
    )
    proc = _run(["--stdin"], stdin=payload)
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["improvedCount"] == 1


def test_cli_no_input_exit_1():
    assert _run([]).returncode == 1


def test_cli_bad_json_exit_1():
    proc = _run(["{bad"])
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_invalid_schema_exit_2():
    proc = _run([json.dumps({"previous": {}})])
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
