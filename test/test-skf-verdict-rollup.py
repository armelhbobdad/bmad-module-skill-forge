"""Unit tests for src/skf-verify-stack/scripts/skf-verdict-rollup.py.

The deterministic overall-feasibility verdict rollup that verify-stack now
delegates to instead of an in-prompt threshold cascade (zero-coverage
short-circuit, blocked/missing/risky conditions, plausible cap, requirements
gaps, zero-pairs guard, and CLI exit codes), and the rollup input that
synthesize.md builds for it.
"""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "src" / "skf-verify-stack"
SCRIPT = SKILL / "scripts" / "skf-verdict-rollup.py"
SYNTHESIZE = SKILL / "references" / "synthesize.md"
spec = importlib.util.spec_from_file_location("rollup_mod", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rollup = mod.rollup


def base(**kw):
    d = {"coveragePercentage": 100, "missingCount": 0, "coveredCount": 4, "pairsBlocked": 0,
         "pairsRisky": 0, "pairsPlausible": 0, "pairsVerified": 3}
    d.update(kw)
    return d


NO_PAIRS = {"pairsBlocked": 0, "pairsRisky": 0, "pairsPlausible": 0, "pairsVerified": 0}


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


def test_full_coverage_with_no_pairs_is_conditionally_feasible():
    # Full coverage, two or more live technologies, no integration pair: the
    # integrations were never checked, so they are not known to be compatible.
    r = rollup(base(**NO_PAIRS))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["matchedConditions"] == ["zero-integration-pairs"]
    assert r["zeroPairsGuardFired"] is True


def test_zero_pairs_guard_fires_from_two_covered_technologies():
    fired = rollup(base(coveredCount=2, **NO_PAIRS))
    assert fired["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert fired["zeroPairsGuardFired"] is True
    # One live technology has no partner, so there is no pair to find.
    alone = rollup(base(coveredCount=1, **NO_PAIRS))
    assert alone["overallVerdict"] == "FEASIBLE"
    assert alone["matchedConditions"] == []
    assert alone["zeroPairsGuardFired"] is False


def test_zero_pairs_note_joins_other_conditions():
    r = rollup(base(coveragePercentage=67, missingCount=1, coveredCount=2, **NO_PAIRS))
    assert r["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert r["matchedConditions"] == ["missing-coverage", "zero-integration-pairs"]
    # Zero coverage leaves no Covered technology, so only the short-circuit fires.
    vacuous = rollup(base(coveragePercentage=0, missingCount=3, coveredCount=0, **NO_PAIRS))
    assert vacuous["overallVerdict"] == "NOT_FEASIBLE"
    assert vacuous["matchedConditions"] == ["zero-coverage"]
    assert vacuous["zeroPairsGuardFired"] is False


def test_any_pair_keeps_the_guard_off():
    for pairs in ({"pairsVerified": 1}, {"pairsPlausible": 1}, {"pairsRisky": 1}, {"pairsBlocked": 1}):
        r = rollup(base(**{**NO_PAIRS, **pairs}))
        assert r["zeroPairsGuardFired"] is False, pairs
        assert "zero-integration-pairs" not in r["matchedConditions"], pairs


def test_the_removed_zero_state_flag_decides_nothing():
    # continuedPastZeroState is no longer read: the guard follows coveredCount.
    r = rollup(base(coveredCount=1, continuedPastZeroState=True, **NO_PAIRS))
    assert r["overallVerdict"] == "FEASIBLE"
    assert r["zeroPairsGuardFired"] is False


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


def test_validation_covered_count():
    d = base()
    del d["coveredCount"]
    assert rollup(d) == {"error": "missing required field: coveredCount", "code": "INVALID_INPUT"}
    assert rollup(base(coveredCount=True)).get("code") == "INVALID_INPUT"
    assert rollup(base(coveredCount=-1)).get("code") == "INVALID_INPUT"
    # No Covered technology means 0% coverage: a 0 left in by mistake would
    # switch the zero-pairs guard off, so it is refused.
    r = rollup(base(coveredCount=0, **NO_PAIRS))
    assert r.get("code") == "INVALID_INPUT"
    assert "covered_count" in r["error"]
    # A single Covered technology can still round to 0% (1 of 1000).
    assert rollup(base(coveragePercentage=0, coveredCount=1))["overallVerdict"] == "NOT_FEASIBLE"


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


def test_cli_zero_pairs_repro_from_590():
    # The reproduction from issue #590, which returned FEASIBLE, with the
    # covered count it now takes.
    inp = json.dumps({"coveragePercentage": 100, "missingCount": 0, "coveredCount": 3, **NO_PAIRS})
    p = subprocess.run([sys.executable, str(SCRIPT), "--json-input", inp],
                       capture_output=True, text=True, check=False)
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert out["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert out["matchedConditions"] == ["zero-integration-pairs"]


def test_cli_help_prints_the_ladder_synthesize_points_to():
    p = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, check=False)
    assert p.returncode == 0
    for needle in ("Zero-coverage short-circuit", "zero-integration-pairs", "coveredCount", "plausible-cap"):
        assert needle in p.stdout, needle


# --- The input synthesize.md builds ------------------------------------------


def _synthesize_section(heading, end, path=SYNTHESIZE):
    text = path.read_text(encoding="utf-8")
    start = text.index(heading)
    return text[start:text.index(end, start)]


def test_synthesize_passes_every_input_the_rollup_reads():
    section = _synthesize_section("### 1. Calculate Overall Verdict", "### 2.")
    # A key opens a code span: `coveredCount` or `requirementsEvaluated: true`.
    named = set(re.findall(r"`([A-Za-z]+)\b", section))
    for field in ("coveragePercentage", *mod.REQUIRED_COUNTS, *mod.OPTIONAL_COUNTS, "requirementsEvaluated"):
        assert field in named, f"synthesize.md section 1 never names the rollup input {field}"
    # The two coverage counts come from the frontmatter step 2 wrote, not
    # from a second tally run over the report's rows.
    assert "`coveredCount` \u2190 `coverageCovered`" in section
    assert "`missingCount` \u2190 `coverageMissing`" in section
    synthesize = SYNTHESIZE.read_text(encoding="utf-8")
    assert "coverageTallyScript" not in synthesize
    assert "serialize the Coverage Analysis table" not in synthesize


def test_coverage_persists_the_counts_the_rollup_reads():
    write = _synthesize_section("### 6. Append to Report", "### 7.", path=SKILL / "references" / "coverage.md")
    assert "`coverageCovered` \u2190 `covered_count`" in write
    assert "`coverageMissing` \u2190 `missing_count`" in write
    template = (SKILL / "assets" / "feasibility-report-template.md").read_text(encoding="utf-8")
    frontmatter = template.split("\n---\n", 1)[0]
    assert "\ncoverageCovered: null\n" in frontmatter and "\ncoverageMissing: null\n" in frontmatter


def test_no_verify_stack_file_sets_the_removed_zero_state_flag():
    for path in sorted(SKILL.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".py", ".toml"):
            text = path.read_text(encoding="utf-8")
            assert "continuedPastZeroState" not in text, path.relative_to(REPO).as_posix()


def test_synthesize_zero_pairs_recommendation_keys_on_the_guard():
    # The verdict and the recommendation use one condition, so a run is never
    # told to proceed while a zero-pairs item is still open.
    section = _synthesize_section("### 2. Generate Prescriptive Recommendations", "### 3.")
    assert "`zero-integration-pairs`" in section
    assert "2+ technologies" not in section
