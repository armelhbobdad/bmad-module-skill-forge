#!/usr/bin/env python3
"""Tests for combine-external-scores.py (skf-test-skill external-validators.md §4).

Covers the three §4 branches (both tools -> mean, one tool -> passthrough,
neither -> null), JS-compatible rounding of odd-sum averages, the toolsUsed /
available fields, schema validation, and the subprocess CLI contract.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = (
    REPO_ROOT / "src" / "skf-test-skill" / "scripts" / "combine-external-scores.py"
)

spec = importlib.util.spec_from_file_location("combine_external_scores", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)
combine = mod.combine


# --------------------------------------------------------------------------
# Both tools ran -> mean
# --------------------------------------------------------------------------


def test_both_even_sum_mean():
    out = combine({"skillCheckScore": 73, "tesslReviewScore": 45})
    assert out["externalScore"] == 59.0
    assert out["toolsUsed"] == ["skill-check", "tessl"]
    assert out["available"] is True


def test_both_odd_sum_half_up():
    """(80 + 73) / 2 = 76.5 — the odd-sum case an in-prompt round would swing."""
    out = combine({"skillCheckScore": 80, "tesslReviewScore": 73})
    assert out["externalScore"] == 76.5


# --------------------------------------------------------------------------
# One tool ran -> passthrough
# --------------------------------------------------------------------------


def test_only_skill_check():
    out = combine({"skillCheckScore": 90, "tesslReviewScore": None})
    assert out["externalScore"] == 90.0
    assert out["toolsUsed"] == ["skill-check"]
    assert out["available"] is True


def test_only_tessl_omitted_field():
    out = combine({"tesslReviewScore": 62})
    assert out["externalScore"] == 62.0
    assert out["toolsUsed"] == ["tessl"]


# --------------------------------------------------------------------------
# Neither ran -> null
# --------------------------------------------------------------------------


def test_neither_null():
    out = combine({"skillCheckScore": None, "tesslReviewScore": None})
    assert out["externalScore"] is None
    assert out["toolsUsed"] == []
    assert out["available"] is False


def test_empty_object_null():
    out = combine({})
    assert out["externalScore"] is None
    assert out["available"] is False


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"skillCheckScore": 101},
        {"tesslReviewScore": -1},
        {"skillCheckScore": "80"},
        {"skillCheckScore": True},
        None,
    ],
)
def test_invalid_input(bad):
    out = combine(bad)
    assert out["code"] == "INVALID_INPUT"


# --------------------------------------------------------------------------
# CLI contract (subprocess)
# --------------------------------------------------------------------------


def _run_cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_stdin_ok():
    res = _run_cli(["--stdin"], stdin=json.dumps({"skillCheckScore": 80, "tesslReviewScore": 73}))
    assert res.returncode == 0
    assert json.loads(res.stdout)["externalScore"] == 76.5


def test_cli_positional_ok():
    res = _run_cli([json.dumps({"skillCheckScore": 90})])
    assert res.returncode == 0
    assert json.loads(res.stdout)["externalScore"] == 90.0


def test_cli_no_input_exit_1():
    res = _run_cli(["--stdin"], stdin="")
    assert res.returncode == 1


def test_cli_invalid_schema_exit_2():
    res = _run_cli(["--stdin"], stdin=json.dumps({"skillCheckScore": 200}))
    assert res.returncode == 2
    assert json.loads(res.stdout)["code"] == "INVALID_INPUT"


def test_cli_malformed_json_exit_1():
    res = _run_cli(["--stdin"], stdin="{bad")
    assert res.returncode == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
