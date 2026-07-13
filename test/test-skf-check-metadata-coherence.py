"""Unit tests for src/skf-test-skill/scripts/check-metadata-coherence.py.

Verifies the §4b metadata export-count coherence cross-check (barrel intra-drift,
documented-surface drift, named-export exclusion, cross-cluster info note, stack /
reference-app skips, threshold override, CLI exit codes) that coverage-check.md now
delegates to instead of computing count-drift arithmetic in-prompt.
"""

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
    / "check-metadata-coherence.py"
)

spec = importlib.util.spec_from_file_location("cmc", SCRIPT)
cmc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmc)


def test_cluster_a_intra_divergence_fires():
    # 55 vs 48 → 12.7% → rounds to 13% > 10 → Medium (matches §4b example)
    r = cmc.check({"clusterA": {"exports_public_api": 55, "exports_length": 48}})
    titles = [f["title"] for f in r["findings"]]
    assert "metadata drift — barrel export counts diverge" in titles
    a = next(f for f in r["findings"] if "barrel export counts" in f["title"])
    assert a["severity"] == "Medium"
    assert a["driftPct"] == 13
    assert "stats.exports_public_api=55" in a["detail"]
    assert "exports[].length=48" in a["detail"]


def test_cluster_a_within_threshold_silent():
    # 55 vs 51 → 7.3% ≤ 10 → no barrel finding
    r = cmc.check({"clusterA": {"exports_public_api": 55, "exports_length": 51}})
    assert all("barrel export counts" not in f["title"] for f in r["findings"])


def test_cluster_b_named_export_exclusion():
    # provenance raw has 3 `::` methods that must NOT count; named = 88
    names = [f"n{i}" for i in range(88)] + [f"T::m{i}" for i in range(48)]
    r = cmc.check(
        {
            "clusterB": {"exports_documented": 92},
            "provenanceExportNames": names,
        }
    )
    # 92 vs 88 → 4.3% ≤ 10 → no documented-surface drift
    assert all("documented-surface" not in f["title"] for f in r["findings"])
    assert r["clusterBCounts"]["provenance named-exports"] == 88


def test_cluster_b_raw_count_would_false_positive_but_named_does_not():
    # If the raw 136 were used it would drift ~32% vs 92; named (88) stays clean.
    names = [f"n{i}" for i in range(88)] + [f"T::m{i}" for i in range(48)]
    r = cmc.check(
        {
            "clusterB": {"exports_documented": 92},
            "provenanceExportNames": names,
            "confidenceDistribution": {"t1": 60, "t1_low": 10, "t2": 15, "t3": 7},
        }
    )
    # confidence sum = 92; cluster B = {92, 88, 92} → drift (92-88)/92 = 4.3% ≤ 10
    assert all("documented-surface" not in f["title"] for f in r["findings"])
    assert r["clusterBCounts"]["confidence_distribution sum"] == 92


def test_confidence_distribution_intra_drift_fires():
    # exports_documented 85, confidence sum 100 → (100-85)/100 = 15% > 10 → Medium
    r = cmc.check(
        {
            "clusterB": {"exports_documented": 85},
            "confidenceDistribution": {"t1": 100, "t1_low": 0, "t2": 0, "t3": 0},
        }
    )
    b = next(f for f in r["findings"] if "documented-surface" in f["title"])
    assert b["severity"] == "Medium"
    assert b["driftPct"] == 15


def test_cross_cluster_info_note():
    # barrel repr 55, documented repr 114 → 51.8% > 10 → Info note
    r = cmc.check(
        {
            "clusterA": {"exports_public_api": 55, "exports_length": 55},
            "clusterB": {"exports_documented": 114},
        }
    )
    info = next(f for f in r["findings"] if f["severity"] == "Info")
    assert info["title"] == "multi-denominator reporting — barrel vs documented surface"
    assert info["detail"] == "barrel=55, documented=114"


def test_cross_cluster_within_threshold_silent():
    r = cmc.check(
        {
            "clusterA": {"exports_public_api": 55},
            "clusterB": {"exports_documented": 58},
        }
    )
    assert all(f["severity"] != "Info" for f in r["findings"])


def test_single_count_per_cluster_silent():
    r = cmc.check({"clusterA": {"exports_public_api": 55}})
    assert r["findings"] == []


def test_stack_skipped():
    r = cmc.check(
        {"skillType": "stack", "clusterA": {"exports_public_api": 0, "exports_length": 0}}
    )
    assert r["skipped"] is True
    assert r["findings"] == []
    assert "stack" in r["skipReason"]


def test_reference_app_skipped():
    r = cmc.check(
        {"scopeType": "reference-app", "clusterB": {"exports_documented": 30}}
    )
    assert r["skipped"] is True
    assert r["findings"] == []


def test_invalid_count_type_errors():
    r = cmc.check({"clusterA": {"exports_public_api": "55"}})
    assert r.get("code") == "INVALID_INPUT"


def test_negative_count_errors():
    r = cmc.check({"clusterB": {"exports_documented": -1}})
    assert r.get("code") == "INVALID_INPUT"


def test_custom_threshold():
    # 55 vs 51 → 7.3%; with threshold 5 it now fires
    r = cmc.check(
        {"clusterA": {"exports_public_api": 55, "exports_length": 51}, "driftThresholdPct": 5}
    )
    assert any("barrel export counts" in f["title"] for f in r["findings"])


def test_cli_stdin_roundtrip():
    payload = json.dumps({"clusterA": {"exports_public_api": 55, "exports_length": 48}})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"],
        input=payload,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert any("barrel export counts" in f["title"] for f in out["findings"])


def test_cli_no_input_exit_1():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdin"],
        input="",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_cli_invalid_input_exit_2():
    payload = json.dumps({"clusterB": {"exports_documented": -5}})
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), payload],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
