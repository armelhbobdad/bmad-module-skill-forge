"""Unit tests for src/skf-forger/scripts/parse-pipeline.py.

Validates the deterministic pipeline parse/expand/anti-pattern logic that
Pipeline Mode (pipeline-mode.md §1-2) delegates to instead of computing
alias expansion and sequence checks in-prompt.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent
    / "src"
    / "skf-forger"
    / "scripts"
    / "parse-pipeline.py"
)

spec = importlib.util.spec_from_file_location("parse_pipeline", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_simple_sequence():
    r = mod.parse_pipeline("BS CS TS EX")
    assert r["valid"] is True
    assert r["alias"] is None
    assert r["codes"] == ["BS", "CS", "TS", "EX"]
    assert r["anti_patterns"] == []


def test_arrow_separators_equivalent():
    a = mod.parse_pipeline("AN -> CS -> TS -> EX")
    b = mod.parse_pipeline("AN CS TS EX")
    assert a["codes"] == b["codes"] == ["AN", "CS", "TS", "EX"]


def test_forge_auto_expansion():
    r = mod.parse_pipeline("forge-auto")
    assert r["alias"] == "forge-auto"
    assert r["codes"] == ["AN", "BS", "CS", "TS", "EX"]
    assert r["expanded"] == ["AN[auto]", "BS[auto]", "CS", "TS[min:90]", "EX"]
    # TS[min:90] is the non-default circuit-breaker gate.
    ts = next(p for p in r["plan"] if p["code"] == "TS")
    assert ts["min"] == 90
    # [auto] classifies as a mode flag, not a target.
    an = next(p for p in r["plan"] if p["code"] == "AN")
    assert an["mode"] == "auto" and an["target"] is None
    assert r["valid"] is True
    assert r["anti_patterns"] == []


def test_all_aliases_expand():
    assert mod.parse_pipeline("forge")["codes"] == ["BS", "CS", "TS", "EX"]
    assert mod.parse_pipeline("forge-quick")["codes"] == ["QS", "TS", "EX"]
    assert mod.parse_pipeline("maintain")["codes"] == ["AS", "US", "TS", "EX"]


def test_deprecated_alias_deepwiki():
    r = mod.parse_pipeline("deepwiki")
    assert r["deprecated_alias"] == "deepwiki"
    assert r["alias"] == "forge-auto"
    assert r["codes"] == ["AN", "BS", "CS", "TS", "EX"]
    assert r["valid"] is True


def test_removed_alias_onboard():
    r = mod.parse_pipeline("onboard")
    assert r["removed_alias"] == "onboard"
    assert r["valid"] is False
    assert r["codes"] == []


def test_bracket_target_argument():
    r = mod.parse_pipeline("BS CS[cocoindex] TS EX")
    cs = next(p for p in r["plan"] if p["code"] == "CS")
    assert cs["target"] == "cocoindex"
    assert cs["min"] is None and cs["mode"] is None


def test_min_override_on_circuit_breaker_code():
    r = mod.parse_pipeline("CS TS[min:80] EX")
    ts = next(p for p in r["plan"] if p["code"] == "TS")
    assert ts["min"] == 80


def test_min_ignored_on_non_circuit_breaker_code():
    # EX has no circuit breaker; min:N is ignored (recorded as null).
    r = mod.parse_pipeline("BS CS TS EX[min:80]")
    ex = next(p for p in r["plan"] if p["code"] == "EX")
    assert ex["min"] is None


def test_anti_pattern_ex_before_ts():
    r = mod.parse_pipeline("BS CS EX TS")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "ex-before-ts" in patterns
    # anti-patterns are warnings, not invalidating.
    assert r["valid"] is True


def test_anti_pattern_duplicate_codes():
    r = mod.parse_pipeline("BS CS TS TS EX")
    dupe = next(p for p in r["anti_patterns"] if p["pattern"] == "duplicate-codes")
    assert dupe["codes"] == ["TS"]


def test_anti_pattern_cs_without_brief():
    r = mod.parse_pipeline("CS TS EX")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "cs-without-brief" in patterns


def test_cs_with_an_no_anti_pattern():
    r = mod.parse_pipeline("AN CS TS EX")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "cs-without-brief" not in patterns


def test_anti_pattern_us_without_audit():
    r = mod.parse_pipeline("US TS EX")
    patterns = {p["pattern"] for p in r["anti_patterns"]}
    assert "us-without-audit" in patterns


def test_unknown_code_invalidates():
    r = mod.parse_pipeline("BS ZZ EX")
    assert "ZZ" in r["unknown_codes"]
    assert r["valid"] is False


def test_empty_input():
    r = mod.parse_pipeline("")
    assert r["codes"] == []
    assert r["valid"] is False


def test_deterministic_identical_output():
    a = json.dumps(mod.parse_pipeline("forge-auto"), sort_keys=True)
    b = json.dumps(mod.parse_pipeline("forge-auto"), sort_keys=True)
    assert a == b


# --- CLI exit codes ---------------------------------------------------------


def _run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_cli_ok_exit_zero():
    p = _run("BS CS TS EX")
    assert p.returncode == 0
    assert json.loads(p.stdout)["codes"] == ["BS", "CS", "TS", "EX"]


def test_cli_removed_alias_exit_two():
    p = _run("onboard")
    assert p.returncode == 2
    assert json.loads(p.stdout)["removed_alias"] == "onboard"


def test_cli_unknown_exit_three():
    p = _run("ZZ")
    assert p.returncode == 3


def test_cli_no_input_exit_one():
    p = _run()
    assert p.returncode == 1


def test_cli_stdin():
    p = _run("--stdin", stdin="AN -> CS -> TS -> EX")
    assert p.returncode == 0
    assert json.loads(p.stdout)["codes"] == ["AN", "CS", "TS", "EX"]
