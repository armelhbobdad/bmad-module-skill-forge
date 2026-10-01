#!/usr/bin/env python3
"""Contract tests for compute-score.py.

Validates that the Python implementation produces identical output for all
test fixtures. Fixtures were originally captured from the JavaScript
implementation and serve as the source of truth for Python parity.
"""
from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
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
    with open(FIXTURES_PATH, encoding="utf-8") as f:
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


class TestReferenceAppSkip:
    """Behavioral tests for the `referenceApp` skip flag.

    A reference-app skill documents wiring patterns, not a library export
    surface, so Signature Accuracy + Type Coverage are skipped — the same
    redistribution path as a stack skill, with a distinct skip reason. See
    scoring-rules.md "Reference-App Skills" and compute-score.py skip set.
    """

    # Mirror of the `suite_u_stack_skill_deep` fixture so the equivalence-class
    # comparison below is anchored on already-validated stack-skill math.
    BASE_INPUT = {
        "mode": "contextual",
        "tier": "Deep",
        "scores": {
            "exportCoverage": 90,
            "signatureAccuracy": None,
            "typeCoverage": None,
            "coherence": 85,
            "externalValidation": 80,
        },
    }

    def test_reference_app_skips_signature_and_type(self):
        out = compute_score({**self.BASE_INPUT, "referenceApp": True})
        assert set(out["skippedCategories"]) >= {"signatureAccuracy", "typeCoverage"}
        assert out["weights"]["signatureAccuracy"] == 0
        assert out["weights"]["typeCoverage"] == 0
        reason = "reference-app (no library export signatures)"
        assert out["skipReasons"]["signatureAccuracy"] == reason
        assert out["skipReasons"]["typeCoverage"] == reason

    def test_reference_app_redistribution_matches_stack_skill(self):
        """`referenceApp` and `stackSkill` share one redistribution equivalence
        class: identical weights/scores/result; only the skipReasons differ."""
        ref = compute_score({**self.BASE_INPUT, "referenceApp": True})
        stack = compute_score({**self.BASE_INPUT, "stackSkill": True})
        for key in (
            "weights", "weightedScores", "totalScore", "result", "weightSum",
            "activeCategories", "skippedCategories",
        ):
            assert ref[key] == stack[key], f"{key} diverged from stack-skill baseline"
        assert ref["skipReasons"]["signatureAccuracy"] == "reference-app (no library export signatures)"
        assert stack["skipReasons"]["signatureAccuracy"] == "stack skill (external type surface)"

    def test_absent_reference_app_keeps_sig_type_active(self):
        """Omitting the flag must not silently skip — proves the change is additive."""
        inp = {
            "mode": "contextual",
            "tier": "Deep",
            "scores": {
                "exportCoverage": 90,
                "signatureAccuracy": 88,
                "typeCoverage": 85,
                "coherence": 85,
                "externalValidation": 80,
            },
        }
        out = compute_score(inp)
        assert "signatureAccuracy" not in out["skippedCategories"]
        assert "typeCoverage" not in out["skippedCategories"]
        assert out.get("skipReasons", {}).get("signatureAccuracy") is None

    @pytest.mark.parametrize("confidence", ["metadata-only", "remote-only"])
    def test_no_local_source_skips_signature_and_type_at_any_tier(self, confidence):
        """States 3 and 4 have no source to compare signatures with, so a Forge+
        run there scores like a stack: no signatures file, nothing refused."""
        out = compute_score({**self.BASE_INPUT, "tier": "Forge+", "analysisConfidence": confidence})
        assert "error" not in out, out
        stack = compute_score({**self.BASE_INPUT, "tier": "Forge+", "stackSkill": True})
        for key in ("weights", "totalScore", "result", "activeCategories", "skippedCategories"):
            assert out[key] == stack[key], key
        assert out["skipReasons"]["typeCoverage"] == "no local source (State 3/4)"

    @pytest.mark.parametrize("confidence", ["full", "provenance-map", None])
    def test_other_source_access_keeps_its_skip_rules(self, confidence):
        inp = {**self.BASE_INPUT, "analysisConfidence": confidence}
        out = compute_score(inp)
        assert out["code"] == "INVALID_INPUT" and "signatureAccuracy is active" in out["error"]


class TestPostScoreCapsAndFallback:
    """Behavioral tests for the post-score caps + threshold fallback lifted from
    score.md §3d/§4b into compute-score.py.

    Invariants pinned here:
    - `result` is NEVER mutated — it is always the pre-cap/pre-fallback verdict.
      The final verdict after caps/fallback is `effectiveResult`.
    - The override group (`effectiveResult`, `capReason`, `thresholdFallback`,
      `originalThreshold`) is emitted atomically, and ONLY when a cap or the
      fallback engaged — otherwise `result` stands alone.
    - INCONCLUSIVE (the minimum-evidence floor) is a gate that no cap or
      fallback may override.
    """

    OVERRIDE_KEYS = (
        "effectiveResult",
        "capReason",
        "thresholdFallback",
        "originalThreshold",
    )

    def test_capped_run_stays_fail_above_80(self):
        """Cap 1 (degraded tooling) forces the PASS to FAIL, and the threshold
        fallback no longer re-flips it at the 80 floor (#596): a threshold
        above 80 is a target, never a way past a cap."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "threshold": 90,
            "toolingStatus": "python3-missing",
            "scores": {
                "exportCoverage": 95,
                "signatureAccuracy": 95,
                "typeCoverage": 95,
                "coherence": 95,
                "externalValidation": 95,
            },
        })
        assert out["totalScore"] == 95.0
        assert out["result"] == "PASS"          # pre-cap score-vs-threshold verdict, unchanged
        assert out["effectiveResult"] == "FAIL"  # the cap holds at any threshold
        assert "tooling degraded" in out["capReason"]
        assert out["thresholdFallback"] is False
        assert out["originalThreshold"] is None

    def test_capped_fail_never_falls_back(self):
        """A run that fails on its score AND trips a cap stays FAIL: before
        #596 the fallback passed it at the 80 floor."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "threshold": 90,
            "toolingStatus": "frontmatter-validator-timeout",
            "scores": {
                "exportCoverage": 85,
                "signatureAccuracy": 85,
                "typeCoverage": 85,
                "coherence": 85,
                "externalValidation": 85,
            },
        })
        assert (out["result"], out["effectiveResult"]) == ("FAIL", "FAIL")
        assert out["thresholdFallback"] is False and out["capReason"] is not None

    def test_timeout_fires_cap_at_threshold_80(self):
        """#613 acceptance: a validator timeout (no `missing` in it) with a
        non-degraded analysisConfidence fires Cap 1 and turns a PASS at 80
        into FAIL."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "threshold": 80,
            "analysisConfidence": "full",
            "toolingStatus": "frontmatter-validator-timeout",
            "scores": {
                "exportCoverage": 90,
                "signatureAccuracy": 90,
                "typeCoverage": 90,
                "coherence": 90,
                "externalValidation": 90,
            },
        })
        assert out["result"] == "PASS" and out["effectiveResult"] == "FAIL"
        assert "tooling degraded" in out["capReason"]
        assert "frontmatter-validator-timeout" in out["capReason"]

    def test_ok_tooling_status_fires_no_cap(self):
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "toolingStatus": "ok",
            "analysisConfidence": "full",
            "scores": {"exportCoverage": 90, "signatureAccuracy": 90, "typeCoverage": 90,
                       "coherence": 90, "externalValidation": 90},
        })
        assert out["result"] == "PASS"
        for key in self.OVERRIDE_KEYS:
            assert key not in out

    def test_degraded_is_no_longer_an_analysis_confidence(self):
        """`degraded` moved to toolingStatus: passing it as analysisConfidence
        is refused, so a caller cannot lose the cap by passing the old field."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "analysisConfidence": "degraded",
            "scores": {"exportCoverage": 90, "signatureAccuracy": 90, "typeCoverage": 90,
                       "coherence": 90, "externalValidation": 90},
        })
        assert out.get("code") == "INVALID_INPUT"
        assert "toolingStatus" in out["error"]
        unknown = compute_score({
            "mode": "contextual", "tier": "Deep", "analysisConfidence": "partial",
            "scores": {"exportCoverage": 90, "signatureAccuracy": 90, "typeCoverage": 90,
                       "coherence": 90, "externalValidation": 90},
        })
        assert unknown.get("code") == "INVALID_INPUT"

    def test_tooling_status_missing_marker_fires_cap(self):
        """A toolingStatus '*-missing' marker triggers Cap 1, like any status other than ok."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "threshold": 90,
            "toolingStatus": "frontmatter-validator-missing",
            "scores": {
                "exportCoverage": 95,
                "signatureAccuracy": 95,
                "typeCoverage": 95,
                "coherence": 95,
                "externalValidation": 95,
            },
        })
        assert out["capReason"] is not None
        assert "tooling degraded" in out["capReason"]

    def test_cap2_docs_only_no_ext_forces_fail(self):
        """Cap 2 (docs-only with no external validators) forces a PASS to FAIL;
        with threshold == 80 the fallback cannot fire, so the FAIL stands."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "docsOnly": True,
            "scores": {
                "exportCoverage": 82,
                "signatureAccuracy": None,
                "typeCoverage": None,
                "coherence": 82,
                "externalValidation": None,
            },
        })
        assert out["totalScore"] == 82.0
        assert out["result"] == "PASS"           # would pass at 80 pre-cap
        assert out["effectiveResult"] == "FAIL"  # Cap 2 forces FAIL
        assert "docs-only without external validators" in out["capReason"]
        assert out["thresholdFallback"] is False
        assert out["originalThreshold"] is None

    def test_inconclusive_is_never_overridden_by_cap_or_fallback(self):
        """The minimum-evidence floor wins: degraded tooling on an INCONCLUSIVE
        result emits no override group at all."""
        out = compute_score({
            "mode": "naive",
            "tier": "Quick",
            "toolingStatus": "python3-missing",
            "scores": {
                "exportCoverage": 95,
                "signatureAccuracy": None,
                "typeCoverage": None,
                "coherence": None,
                "externalValidation": None,
            },
        })
        assert out["result"] == "INCONCLUSIVE"
        for key in self.OVERRIDE_KEYS:
            assert key not in out, f"{key} must not be emitted for INCONCLUSIVE"

    def test_plain_fail_fallback_flips_to_pass(self):
        """A plain FAIL (no cap) with totalScore >= 80 and threshold > 80 is
        converted to PASS by the threshold fallback."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "threshold": 90,
            "scores": {
                "exportCoverage": 85,
                "signatureAccuracy": 85,
                "typeCoverage": 85,
                "coherence": 85,
                "externalValidation": 85,
            },
        })
        assert out["totalScore"] == 85.0
        assert out["result"] == "FAIL"           # pre-fallback verdict
        assert out["effectiveResult"] == "PASS"  # fallback at 80 floor
        assert out["capReason"] is None
        assert out["thresholdFallback"] is True
        assert out["originalThreshold"] == 90

    def test_no_cap_no_fallback_omits_override_group(self):
        """A clean PASS with no cap/fallback emits none of the override keys —
        the group is conditional, matching `warnings`/`inconclusiveReasons`."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "scores": {
                "exportCoverage": 92,
                "signatureAccuracy": 85,
                "typeCoverage": 100,
                "coherence": 80,
                "externalValidation": 78,
            },
        })
        assert out["result"] == "PASS"
        for key in self.OVERRIDE_KEYS:
            assert key not in out

    def test_non_string_tooling_status_rejected(self):
        """New string fields are validated: a non-string toolingStatus is an
        INVALID_INPUT error (additive validation, existing inputs unaffected)."""
        out = compute_score({
            "mode": "contextual",
            "tier": "Deep",
            "toolingStatus": 123,
            "scores": {"exportCoverage": 90, "signatureAccuracy": 85,
                       "typeCoverage": 100, "coherence": 80, "externalValidation": 78},
        })
        assert out.get("code") == "INVALID_INPUT"
        assert "toolingStatus" in out.get("error", "")


class TestState2Deduction:
    """#613 item 2: the State 2 undercount deduction and its >5% trigger live
    in compute-score.py, read from the provenance, metadata and union counts."""

    BASE = {
        "mode": "contextual",
        "tier": "Deep",
        "state2": True,
        "scores": {"exportCoverage": 90, "signatureAccuracy": None, "typeCoverage": None,
                   "coherence": 85, "externalValidation": 80},
    }

    def _run(self, counts, **extra):
        return compute_score({**self.BASE, "state2Counts": counts, **extra})

    def test_divergence_above_5_percent_deducts_10_points(self):
        out = self._run({"provenance": 40, "metadata": 45, "union": 48})
        assert out["state2Deduction"] == {"divergencePct": 20.0, "applied": True,
                                          "rawExportCoverage": 90, "exportCoverage": 80}
        assert out["weightedScores"]["exportCoverage"] == round(out["weights"]["exportCoverage"] * 0.8, 2)
        assert out["input"]["scores"]["exportCoverage"] == 90  # the echo keeps the raw score
        assert "10-point deduction" in out["scoringNotes"][0]

    def test_divergence_at_5_percent_deducts_nothing(self):
        out = self._run({"provenance": 100, "metadata": 100, "union": 105})
        assert out["state2Deduction"]["divergencePct"] == 5.0
        assert out["state2Deduction"]["applied"] is False
        assert "scoringNotes" not in out

    def test_the_deduction_never_goes_below_zero(self):
        out = compute_score({**self.BASE, "scores": {**self.BASE["scores"], "exportCoverage": 4},
                             "state2Counts": {"provenance": 10, "metadata": 20, "union": 25}})
        assert out["state2Deduction"]["exportCoverage"] == 0

    def test_a_stack_and_a_run_that_is_not_state_2_are_exempt(self):
        counts = {"provenance": 40, "metadata": 45, "union": 48}
        assert "state2Deduction" not in self._run(counts, stackSkill=True)
        assert "state2Deduction" not in compute_score({**self.BASE, "state2": False, "state2Counts": counts})

    def test_a_missing_source_count_measures_no_divergence(self):
        out = self._run({"provenance": 0, "metadata": 45, "union": 45})
        assert out["state2Deduction"]["applied"] is False

    @pytest.mark.parametrize("counts", [
        "40,45,48", {"provenance": 40, "metadata": 45}, {"provenance": -1, "metadata": 45, "union": 48},
        {"provenance": True, "metadata": 45, "union": 48},
    ], ids=["not-an-object", "no-union", "negative", "boolean"])
    def test_bad_counts_are_refused(self, counts):
        assert self._run(counts).get("code") == "INVALID_INPUT"


# --------------------------------------------------------------------------
# CLI exit codes — a rejected input must be distinguishable from a scored run
# --------------------------------------------------------------------------


SCRIPT_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "skf-test-skill"
    / "scripts"
    / "compute-score.py"
)

VALID_INPUT = {
    "mode": "contextual",
    "tier": "Deep",
    "scores": {
        "exportCoverage": 90,
        "signatureAccuracy": 85,
        "typeCoverage": 100,
        "coherence": 80,
        "externalValidation": 78,
    },
}


def _run_cli(payload_text):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--stdin"],
        input=payload_text,
        capture_output=True,
        text=True,
    )


def test_cli_valid_input_exits_0():
    proc = _run_cli(json.dumps(VALID_INPUT))
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["result"] in ("PASS", "FAIL", "INCONCLUSIVE")


def test_cli_unparseable_json_exits_1():
    proc = _run_cli("{not json")
    assert proc.returncode == 1


@pytest.mark.parametrize(
    "mutation,description",
    [
        ({"scores": {"exportCoverage": 125}}, "out-of-range score"),
        ({"scores": {"exportCoverage": None}}, "null required score"),
        ({"mode": "nonsense"}, "invalid mode"),
        ({"toolingStatus": 123}, "non-string field"),
    ],
    ids=["out-of-range", "null-score", "bad-mode", "bad-type"],
)
def test_cli_rejected_input_exits_2(mutation, description):
    """A rejected input exits 2, matching reconcile-coverage.py.

    Exiting 0 made a refused input look like a scored run, so score.md §3c's
    manual-redistribution fallback could be entered with the very numbers the
    script declined to score.
    """
    payload = json.loads(json.dumps(VALID_INPUT))
    for key, value in mutation.items():
        if key == "scores":
            payload["scores"].update(value)
        else:
            payload[key] = value
    proc = _run_cli(json.dumps(payload))
    assert proc.returncode == 2, f"{description}: expected exit 2"
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


# --------------------------------------------------------------------------
# Score files: score.md hands the scores to the script by path (#613)
# --------------------------------------------------------------------------


def _write_json(path, payload):
    path.write_bytes((json.dumps(payload) + "\n").encode("utf-8"))
    return str(path)


def _run_files(tmp_path, flags, base=None):
    base = base or {"mode": "contextual", "tier": "Deep", "toolingStatus": "ok"}
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--json-input", json.dumps(base), *flags],
        capture_output=True, text=True,
    )


def test_cli_reads_every_score_from_its_file(tmp_path):
    flags = [
        "--coverage", _write_json(tmp_path / "coverage.json", {"exportCoverage": 90.0, "documented": 9}),
        "--signatures", _write_json(tmp_path / "signatures.json",
                                    {"valid": True, "signatureAccuracy": 85.0, "typeCoverage": 100.0}),
        "--coherence", _write_json(tmp_path / "coherence.json", {"combinedCoherence": 80.0}),
        "--external", _write_json(tmp_path / "external.json", {"externalScore": 78.0, "toolsUsed": ["skill-check"]}),
    ]
    proc = _run_files(tmp_path, flags)
    assert proc.returncode == 0, proc.stdout
    out = json.loads(proc.stdout)
    assert out["input"]["scores"] == {"exportCoverage": 90.0, "signatureAccuracy": 85.0, "typeCoverage": 100.0,
                                      "coherence": 80.0, "externalValidation": 78.0}
    assert out == compute_score({"mode": "contextual", "tier": "Deep", "toolingStatus": "ok",
                                 "scores": out["input"]["scores"]})


def test_cli_reads_the_state_2_counts_from_the_surface(tmp_path):
    flags = [
        "--coverage", _write_json(tmp_path / "coverage.json", {"exportCoverage": 90}),
        "--coherence", _write_json(tmp_path / "coherence.json", {"combinedCoherence": 85}),
        "--external", _write_json(tmp_path / "external.json", {"externalScore": None}),
        "--surface", _write_json(tmp_path / "surface.json", {"state2": {"provenanceCount": 40, "metadataCount": 45,
                                                                       "unionCount": 48}}),
    ]
    base = {"mode": "contextual", "tier": "Deep", "state2": True, "toolingStatus": "ok"}
    out = json.loads(_run_files(tmp_path, flags, base).stdout)
    assert out["state2Deduction"]["applied"] is True
    assert "externalValidation" in out["skippedCategories"]


@pytest.mark.parametrize("payload, needle", [
    ({"error": "barrel_set is empty", "code": "INVALID_INPUT"}, "refused result"),
    ({"documented": 3}, "has no `exportCoverage`"),
], ids=["refused-result", "missing-field"])
def test_cli_refuses_a_score_file_without_its_score(tmp_path, payload, needle):
    proc = _run_files(tmp_path, ["--coverage", _write_json(tmp_path / "coverage.json", payload)])
    assert proc.returncode == 2
    out = json.loads(proc.stdout)
    assert out["code"] == "INVALID_INPUT" and needle in out["error"]


def test_cli_refuses_a_missing_score_file(tmp_path):
    proc = _run_files(tmp_path, ["--coverage", str(tmp_path / "absent.json")])
    assert proc.returncode == 2 and "cannot read --coverage" in json.loads(proc.stdout)["error"]
