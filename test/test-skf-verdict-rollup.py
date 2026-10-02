"""Unit tests for src/skf-verify-stack/scripts/skf-verdict-rollup.py.

The deterministic overall-feasibility verdict rollup that verify-stack now
delegates to instead of an in-prompt threshold cascade (zero-coverage
short-circuit, blocked/missing/risky conditions, plausible cap, requirements
gaps, zero-pairs guard, the recommendation count derived from the same
counts, and CLI exit codes), the --report mode that reads those counts from
the report frontmatter itself and fails on a count a stage never wrote or a
stage stepsCompleted does not list (while rollup()'s defaults stay for the
callers that pass JSON), and the one
call synthesize.md makes.
"""

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "src" / "skf-verify-stack"
SCRIPT = SKILL / "scripts" / "skf-verdict-rollup.py"
SYNTHESIZE = SKILL / "references" / "synthesize.md"
TEMPLATE = SKILL / "assets" / "feasibility-report-template.md"
READER_PATH = REPO / "src" / "shared" / "scripts" / "skf-validate-feasibility-report.py"
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


def test_cli_reads_utf8_stdin_under_a_cp1252_console():
    # A Windows console decodes piped input as cp1252, where the second byte of
    # a UTF-8 `\u00c1` is undefined: stdin is read as UTF-8 instead.
    inp = json.dumps({**base(), "note": "R\u00c1"}, ensure_ascii=False).encode("utf-8")
    p = subprocess.run([sys.executable, str(SCRIPT), "--stdin"], input=inp, capture_output=True,
                       env={**os.environ, "PYTHONIOENCODING": "cp1252"}, check=False)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["overallVerdict"] == "FEASIBLE"


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


def _rollup_call():
    section = _synthesize_section("### 1. Calculate Overall Verdict", "### 2.")
    [call] = [line for line in section.splitlines() if line.startswith("uv run {verdictRollupScript} ")]
    return section, call


def test_synthesize_runs_the_rollup_on_the_report():
    section, call = _rollup_call()
    assert call == 'uv run {verdictRollupScript} --report "{outputFile}"'
    args = mod._build_parser().parse_args(shlex.split(call.split("uv run {verdictRollupScript}", 1)[1]))
    assert args.report == "{outputFile}" and not args.stdin
    # The script reads the frontmatter, and --help lists its keys: the stage names
    # the two the workflow-state test pins and the stage list, and assembles no input itself.
    named = set(re.findall(r"`([A-Za-z]+)\b", section))
    for key in ("coverageCovered", "coverageMissing", mod.STEPS_COMPLETED_KEY):
        assert key in named, f"synthesize.md section 1 never names the frontmatter key {key}"
    for key, _ in mod.REPORT_COUNTS:
        assert key in mod.__doc__, key
    assert "`pairsVerified`, `pairsPlausible`" not in section
    for stale in ("echo '<counts JSON>'", "Assemble the counts", "Input keys:", "fix the input and run it again"):
        assert stale not in section, stale
    for code in ("HELPER_MISSING", "INVALID_REPORT", "INVALID_INPUT"):
        assert f"`{code}`" in section and code in mod.__doc__, code
    assert '(exit code 3, `halt_reason: "resolution-failure"`) at phase `synthesize:rollup`' in section
    assert '(exit code 5, `halt_reason: "schema-violation"`) at phase `synthesize:rollup`' in section
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


# --- The recommendation count ---------------------------------------------------


def test_a_clean_run_needs_no_recommendation():
    r = rollup(base())
    assert r["recommendationCount"] == 0
    assert set(r["recommendations"].values()) == {0}


def test_one_recommendation_per_finding():
    r = rollup(base(coveragePercentage=60, missingCount=2, replacedCount=1, pairsBlocked=1, pairsRisky=2,
                    pairsPlausible=3, pairsVerified=1, requirementsEvaluated=True,
                    requirementsNotAddressed=2, requirementsPartial=1))
    assert r["recommendations"] == {"blocked": 1, "missing": 2, "replaced": 1, "risky": 2, "plausible": 3,
                                    "zeroPairs": 0, "notAddressed": 2, "partial": 1}
    assert r["recommendationCount"] == 12
    # The keys follow the order synthesize.md section 4 lists the recommendations in.
    assert list(r["recommendations"]) == ["blocked", "missing", "replaced", "risky", "plausible",
                                          "zeroPairs", "notAddressed", "partial"]


def test_requirement_gaps_count_only_when_the_pass_ran():
    r = rollup(base(requirementsNotAddressed=3, requirementsPartial=2))
    assert (r["recommendations"]["notAddressed"], r["recommendations"]["partial"]) == (0, 0)
    assert r["recommendationCount"] == 0


def test_the_zero_pairs_note_is_one_recommendation():
    r = rollup(base(**NO_PAIRS))
    assert r["recommendations"]["zeroPairs"] == 1
    assert r["recommendationCount"] == 1
    assert rollup(base(coveredCount=1, **NO_PAIRS))["recommendations"]["zeroPairs"] == 0


def test_replaced_technologies_count_without_touching_the_verdict():
    r = rollup(base(replacedCount=2))
    assert r["overallVerdict"] == "FEASIBLE"
    assert r["recommendations"]["replaced"] == 2 and r["recommendationCount"] == 2
    # Left out, it counts none (an older caller).
    assert rollup(base())["recommendations"]["replaced"] == 0


def test_zero_coverage_still_counts_its_recommendations():
    r = rollup(base(coveragePercentage=0, coveredCount=0, missingCount=3, replacedCount=1, **NO_PAIRS))
    assert r["overallVerdict"] == "NOT_FEASIBLE"
    assert r["recommendationCount"] == 4


def test_validation_replaced_count():
    assert rollup(base(replacedCount=-1)).get("code") == "INVALID_INPUT"
    assert rollup(base(replacedCount=True)).get("code") == "INVALID_INPUT"
    assert rollup(base(replacedCount=None))["recommendations"]["replaced"] == 0


def test_synthesize_takes_the_recommendation_count_from_the_rollup():
    section = _synthesize_section("### 1. Calculate Overall Verdict", "### 2.")
    # --report reads the Replaced count itself; its --help names the key.
    assert ("coverageReplaced", "replacedCount") in mod.REPORT_COUNTS and "coverageReplaced" in mod.__doc__
    assert "`recommendationCount`" in section and "`recommendations`" in section
    compile_section = _synthesize_section("### 4. Compile Synthesis Section", "### 5.")
    assert "count total recommendations" not in compile_section
    assert "the §1 rollup's `recommendationCount`" in compile_section
    write = _synthesize_section("### 5. Append to Report", "### 6.")
    # No circular check of the frontmatter's pair counts against themselves.
    assert "Verify that `pairsVerified`" not in write
    coverage = _synthesize_section("### 6. Append to Report", "### 7.", path=SKILL / "references" / "coverage.md")
    assert "`coverageReplaced` \u2190 `replaced_count`" in coverage
    template = (SKILL / "assets" / "feasibility-report-template.md").read_text(encoding="utf-8")
    assert "\ncoverageReplaced: null\n" in template.split("\n---\n", 1)[0]


def test_synthesize_zero_pairs_recommendation_keys_on_the_guard():
    # The verdict and the recommendation use one condition, so a run is never
    # told to proceed while a zero-pairs item is still open.
    section = _synthesize_section("### 2. Generate Prescriptive Recommendations", "### 3.")
    assert "`zero-integration-pairs`" in section
    assert "2+ technologies" not in section


# --- --report: the counts from the report frontmatter ---------------------------

# The counts each stage persists, as a finished run leaves them.
STAGE_COUNTS = {"coveragePercentage": "75", "coverageCovered": "3", "coverageMissing": "1", "coverageReplaced": "2",
                "pairsVerified": "1", "pairsPlausible": "1", "pairsRisky": "0", "pairsBlocked": "0",
                "requirementsPass": "'completed'", "requirementsNotAddressed": "1", "requirementsPartial": "0",
                "stepsCompleted": "['init', 'coverage', 'integrations', 'requirements']"}


def _report(tmp_path, name="feasibility-report-my-app-20261002-101500.md", drop=(), **values):
    """The report template with its frontmatter keys set as the stages set them."""
    lines = TEMPLATE.read_text(encoding="utf-8").split("\n")
    wanted = {**STAGE_COUNTS, **values}
    end = lines.index("---", 1)
    out = []
    for i, line in enumerate(lines):
        key = line.split(":", 1)[0]
        if 0 < i < end and key in drop:
            continue
        out.append(f"{key}: {wanted[key]}" if 0 < i < end and key in wanted else line)
    path = tmp_path / name
    path.write_bytes("\n".join(out).encode("utf-8"))
    return path


def _run_report(path, script=SCRIPT):
    p = subprocess.run([sys.executable, str(script), "--report", str(path)], capture_output=True, text=True,
                       check=False)
    return p.returncode, json.loads(p.stdout)


def test_the_report_gives_the_rollup_its_counts(tmp_path):
    code, out = _run_report(_report(tmp_path))
    assert code == 0
    assert out == rollup({"coveragePercentage": 75, "coveredCount": 3, "missingCount": 1, "replacedCount": 2,
                          "pairsVerified": 1, "pairsPlausible": 1, "pairsRisky": 0, "pairsBlocked": 0,
                          "requirementsEvaluated": True, "requirementsNotAddressed": 1, "requirementsPartial": 0})
    assert out["overallVerdict"] == "CONDITIONALLY_FEASIBLE"
    assert out["recommendations"] == {"blocked": 0, "missing": 1, "replaced": 2, "risky": 0, "plausible": 1,
                                      "zeroPairs": 0, "notAddressed": 1, "partial": 0}


def test_a_skipped_requirements_pass_reads_no_requirement_count(tmp_path):
    # The requirements stage leaves both counts at the template's null when it skips.
    path = _report(tmp_path, requirementsPass='"skipped"', requirementsNotAddressed="null",
                   requirementsPartial="null")
    code, out = _run_report(path)
    assert code == 0 and out["recommendations"]["notAddressed"] == 0
    assert "requirements-not-addressed" not in out["matchedConditions"]


@pytest.mark.parametrize("key", [key for key, _ in mod.REPORT_COUNTS])
def test_a_count_a_stage_never_wrote_fails(tmp_path, key):
    """A key left at the template's null, or missing, is an error, never a default 0."""
    for path in (_report(tmp_path, **{key: "null"}), _report(tmp_path, name="dropped.md", drop=(key,))):
        code, out = _run_report(path)
        assert (code, out["code"]) == (2, "INVALID_REPORT"), path.name
        assert key in out["error"], out["error"]


@pytest.mark.parametrize("stage", list(mod.REPORT_STAGES))
def test_a_stage_the_report_does_not_list_fails(tmp_path, stage):
    """The template starts coveragePercentage and the pair counts at 0: only a finished stage measured them."""
    steps = [step for step in ("init", *mod.REPORT_STAGES) if step != stage]
    code, out = _run_report(_report(tmp_path, stepsCompleted="[" + ", ".join(steps) + "]"))
    assert (code, out["code"]) == (2, "INVALID_REPORT")
    assert "stepsCompleted" in out["error"] and stage in out["error"], out["error"]


def test_a_block_list_of_the_stages_is_read(tmp_path):
    path = _report(tmp_path, stepsCompleted="\n  - init\n  - coverage\n  - integrations\n  - requirements")
    assert _run_report(path)[0] == 0
    assert _run_report(_report(tmp_path, name="none.md", stepsCompleted="[]"))[1]["code"] == "INVALID_REPORT"


@pytest.mark.parametrize("values", [
    {"requirementsPass": "''"},
    {"requirementsPass": "'partial'"},
    {"requirementsNotAddressed": "null"},
    {"requirementsPartial": "two"},
], ids=["pass-unset", "pass-unknown", "not-addressed-unset", "partial-not-a-count"])
def test_the_requirements_pass_and_its_counts_must_be_recorded(tmp_path, values):
    code, out = _run_report(_report(tmp_path, **values))
    assert (code, out["code"]) == (2, "INVALID_REPORT")
    assert next(iter(values)) in out["error"]


def test_quotes_and_comments_around_a_count_are_read(tmp_path):
    code, out = _run_report(_report(tmp_path, pairsRisky='"2"', coverageMissing="1  # one left"))
    assert code == 0 and out["recommendations"]["risky"] == 2 and out["recommendations"]["missing"] == 1


def test_counts_that_disagree_are_invalid_input(tmp_path):
    code, out = _run_report(_report(tmp_path, coverageCovered="0", coverageMissing="4"))
    assert (code, out["code"]) == (2, "INVALID_INPUT")


def test_a_report_it_cannot_read_is_invalid(tmp_path):
    code, out = _run_report(tmp_path / "missing.md")
    assert (code, out["code"]) == (2, "INVALID_REPORT")
    bad = tmp_path / "latin1.md"
    bad.write_bytes(b"---\ncoveragePercentage: 75\nnote: caf\xe9\n---\n")
    assert _run_report(bad)[1]["code"] == "INVALID_REPORT"


def _install(root, with_reader):
    """The installed layout: _bmad/skf/<skill>/scripts/ beside _bmad/skf/shared/scripts/."""
    script = root / "_bmad" / "skf" / "skf-verify-stack" / "scripts" / SCRIPT.name
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    if with_reader:
        shared = root / "_bmad" / "skf" / "shared" / "scripts"
        shared.mkdir(parents=True)
        (shared / READER_PATH.name).write_bytes(READER_PATH.read_bytes())
    return script


def test_the_installed_layout_reads_the_report(tmp_path):
    script = _install(tmp_path / "project", with_reader=True)
    assert _run_report(_report(tmp_path), script=script)[0] == 0
    assert mod.SHARED_READER == READER_PATH.resolve()


def test_a_missing_shared_reader_exits_1(tmp_path):
    script = _install(tmp_path / "project", with_reader=False)
    code, out = _run_report(_report(tmp_path), script=script)
    assert (code, out["code"]) == (1, "HELPER_MISSING")
    # Counts passed as JSON need no reader.
    p = subprocess.run([sys.executable, str(script), "--stdin"], input=json.dumps(base()), capture_output=True,
                       text=True, check=False)
    assert p.returncode == 0, p.stdout


def test_report_takes_no_second_input():
    p = subprocess.run([sys.executable, str(SCRIPT), "--report", "r.md", "--stdin"], capture_output=True,
                       text=True, check=False)
    assert p.returncode == 2 and p.stdout == ""


def test_rollup_keeps_its_defaults_for_json_callers():
    """The strictness lives in the frontmatter reader only."""
    assert rollup(base())["recommendations"]["replaced"] == 0
    assert rollup(base(requirementsNotAddressed=3))["overallVerdict"] == "FEASIBLE"
