"""Unit tests for src/skf-verify-stack/scripts/skf-verdict-rollup.py.

The deterministic overall-feasibility verdict rollup that verify-stack now
delegates to instead of an in-prompt threshold cascade (zero-coverage
short-circuit, blocked/missing/risky conditions, plausible cap, requirements
gaps, zero-pairs guard, and CLI exit codes).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-verify-stack"
    / "scripts"
    / "skf-verdict-rollup.py"
)
spec = importlib.util.spec_from_file_location("rollup_mod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rollup = mod.rollup


def base(**kw):
    d = {"coveragePercentage": 100, "missingCount": 0, "pairsBlocked": 0,
         "pairsRisky": 0, "pairsPlausible": 0, "pairsVerified": 3}
    d.update(kw)
    return d


def test_feasible_clean():
    r = rollup(base())
    assert r["overallVerdict"] == "FEASIBLE"
    assert r["matchedConditions"] == []
    assert r["zeroPairsGuardFired"] is False


def test_zero_coverage_shortcircuit_wins_over_blocked():
    r = rollup(base(coveragePercentage=0, pairsBlocked=2))
    assert r["overallVerdict"] == "NOT_FEASIBLE"
    assert r["matchedConditions"] == ["zero-coverage"]


def test_blocked_not_feasible_with_cooccurring():
    r = rollup(base(pairsBlocked=1, missingCount=2, pairsRisky=1))
    assert r["overallVerdict"] == "NOT_FEASIBLE"
    assert r["matchedConditions"] == ["blocked-integration", "missing-coverage", "risky-integration"]


def test_missing_conditional():
    r = rollup(base(coveragePercentage=80, missingCount=1))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["matchedConditions"] == ["missing-coverage"]


def test_risky_conditional():
    r = rollup(base(pairsRisky=1, pairsVerified=2))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["matchedConditions"] == ["risky-integration"]


def test_requirements_gaps_only_when_evaluated():
    r = rollup(base(requirementsNotAddressed=3, requirementsPartial=2))
    assert r["overallVerdict"] == "FEASIBLE"
    r2 = rollup(base(requirementsEvaluated=True, requirementsNotAddressed=1, requirementsPartial=2))
    assert r2["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r2["matchedConditions"] == ["requirements-not-addressed", "requirements-partial"]


def test_plausible_cap_downgrades():
    r = rollup(base(pairsPlausible=1, pairsVerified=2))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["matchedConditions"] == ["plausible-cap"]


def test_missing_independent_of_100_pct():
    r = rollup(base(coveragePercentage=100, missingCount=1))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["matchedConditions"] == ["missing-coverage"]


def test_zero_pairs_guard_downgrades_feasible():
    r = rollup(base(pairsVerified=0, continuedPastZeroState=True))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["zeroPairsGuardFired"] is True
    assert "zero-integration-pairs" in r["matchedConditions"]


def test_zero_pairs_no_continue_no_guard():
    r = rollup(base(pairsVerified=0, continuedPastZeroState=False))
    assert r["overallVerdict"] == "FEASIBLE"
    assert r["zeroPairsGuardFired"] is False


def test_zero_pairs_guard_note_even_when_not_feasible():
    r = rollup(base(coveragePercentage=0, pairsVerified=0, continuedPastZeroState=True))
    assert r["overallVerdict"] == "NOT_FEASIBLE"
    assert r["zeroPairsGuardFired"] is True
    assert r["matchedConditions"] == ["zero-coverage", "zero-integration-pairs"]


def test_validation_bad_pct():
    r = rollup(base(coveragePercentage=150))
    assert r.get("code") == "INVALID_INPUT"


def test_validation_bool_as_count():
    r = rollup(base(pairsBlocked=True))
    assert r.get("code") == "INVALID_INPUT"


def test_validation_missing_field():
    d = base()
    del d["pairsVerified"]
    r = rollup(d)
    assert r.get("code") == "INVALID_INPUT"


def test_cli_stdin_and_exit_codes():
    inp = json.dumps(base())
    p = subprocess.run([sys.executable, str(SCRIPT), "--stdin"], input=inp,
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert json.loads(p.stdout)["overallVerdict"] == "FEASIBLE"
    bad = json.dumps(base(coveragePercentage=-1))
    p2 = subprocess.run([sys.executable, str(SCRIPT), "--stdin"], input=bad,
                        capture_output=True, text=True)
    assert p2.returncode == 2
    p3 = subprocess.run([sys.executable, str(SCRIPT), "--stdin"], input="",
                        capture_output=True, text=True)
    assert p3.returncode == 1
