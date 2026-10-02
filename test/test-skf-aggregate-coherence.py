#!/usr/bin/env python3
"""Tests for src/skf-test-skill/scripts/aggregate-coherence.py.

The contextual-coherence tally + 0.6/0.4 weighted mean that coherence-check.md
now delegates to instead of computing in-prompt. Runs the module's embedded
doctests plus reference-value and CLI (exit-code) checks, and the
per-reference input (#598): the script counts `valid_references` itself from
the scanner's reference-check output and the judged results, and names each
invalid reference with the status coherence-check classifies.
"""

from __future__ import annotations

import doctest
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

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


# --------------------------------------------------------------------------
# CLI exit codes — a refused input must not look like an aggregated result
# --------------------------------------------------------------------------


AGG_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "skf-test-skill"
    / "scripts"
    / "aggregate-coherence.py"
)


def _run_agg_cli(payload_text):
    return subprocess.run(
        [sys.executable, str(AGG_SCRIPT_PATH), "--stdin"],
        input=payload_text,
        capture_output=True,
        text=True,
    )


def test_cli_rejected_input_exits_2():
    """Matches compute-score.py / reconcile-coverage.py.

    This script produces the coherence percentage score.md feeds to
    compute-score.py, so a silently-rejected run would hand a bogus number to
    the gate one layer downstream.
    """
    proc = _run_agg_cli(json.dumps({"unexpected": "payload"}))
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_unparseable_json_exits_1():
    proc = _run_agg_cli("{not json")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_cli_output_writes_the_score_file(tmp_path):
    """coherence-check §5c writes `{run_dir}/coherence.json`, which compute-score.py --coherence reads."""
    out_path = tmp_path / "run" / "coherence.json"
    proc = subprocess.run(
        [sys.executable, str(AGG_SCRIPT_PATH), "--stdin", "--output", str(out_path)],
        input=json.dumps({"valid_references": 6, "total_references": 7, "patterns_documented": 5,
                          "patterns_complete": 4}),
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert json.loads(out_path.read_text(encoding="utf-8")) == json.loads(proc.stdout)


def test_cli_refused_input_removes_a_stale_score_file(tmp_path):
    out_path = tmp_path / "coherence.json"
    out_path.write_bytes(b'{"combinedCoherence": 100}')
    proc = subprocess.run([sys.executable, str(AGG_SCRIPT_PATH), "--stdin", "--output", str(out_path)],
                          input=json.dumps({"unexpected": "payload"}), capture_output=True, text=True)
    assert proc.returncode == 2 and not out_path.exists()


# --------------------------------------------------------------------------
# Per-reference input: the script counts the valid references itself (#598)
# --------------------------------------------------------------------------


SCANNER = Path(__file__).resolve().parent.parent / "src" / "shared" / "scripts" / "skf-scan-skill-md-structure.py"
SCAN = {"references": [
    {"line": 3, "target": "references/api.md", "status": "ok"},
    {"line": 4, "target": "scripts/run.py", "status": "missing"},
    {"line": 5, "target": "../../etc/passwd", "status": "escapes"},
]}
JUDGED = [
    {"reference": "react", "line": 9, "target_exists": True, "type_match": True, "signature_match": True,
     "issues": []},
    {"reference": "./types", "line": 12, "target_exists": True, "type_match": False, "signature_match": True,
     "issues": ["Props is not exported by ./types"]},
    {"reference": "ghost-skill", "line": 14, "target_exists": False, "type_match": False,
     "signature_match": False, "issues": []},
]


def _files(tmp_path, scan=SCAN, judged=JUDGED, integration=None, fence=True):
    paths = {"--references": tmp_path / "references.json", "--integration": tmp_path / "integration.json"}
    paths["--references"].write_bytes(json.dumps(scan).encode("utf-8"))
    body = json.dumps(integration or {"patterns_documented": 5, "patterns_complete": 4, "incomplete_patterns": []})
    paths["--integration"].write_bytes(body.encode("utf-8"))
    if judged is not None:
        paths["--judged"] = tmp_path / "judged-references.json"
        text = json.dumps(judged)
        paths["--judged"].write_bytes((f"```json\n{text}\n```\n" if fence else text).encode("utf-8"))
    return paths


def _cli_files(paths, *extra):
    args = [str(a) for pair in paths.items() for a in pair]
    return _cli([*args, *extra])


def test_count_references_from_both_kinds(tmp_path):
    proc = _cli_files(_files(tmp_path))
    assert proc.returncode == 0, proc.stdout
    out = json.loads(proc.stdout)
    assert (out["input"]["valid_references"], out["input"]["total_references"]) == (2, 6)
    assert out["referenceValidity"] == 33.33 and out["integrationCompleteness"] == 80.0
    assert [(r["source"], r["target"], r["status"]) for r in out["invalidReferences"]] == [
        ("scan", "scripts/run.py", "missing"), ("scan", "../../etc/passwd", "escapes"),
        ("judged", "./types", "inaccurate"), ("judged", "ghost-skill", "missing")]


def test_each_invalid_reference_carries_what_its_gap_needs(tmp_path):
    """coherence-check §5c titles an escape with `canonical` and an inaccurate one with `issues`,
    reading both from the aggregate alone."""
    scan = {"references": [
        {"line": 4, "target": "scripts/run.py", "status": "missing", "canonical": "/s/scripts/run.py",
         "root": "skill"},
        {"line": 5, "target": "../../etc/passwd", "status": "escapes", "canonical": "/etc/passwd", "root": None},
    ]}
    out = json.loads(_cli_files(_files(tmp_path, scan=scan)).stdout)
    by_target = {r["target"]: r for r in out["invalidReferences"]}
    assert (by_target["scripts/run.py"]["canonical"], by_target["scripts/run.py"]["root"]) == (
        "/s/scripts/run.py", "skill")
    assert (by_target["../../etc/passwd"]["canonical"], by_target["../../etc/passwd"]["issues"]) == ("/etc/passwd", [])
    assert by_target["./types"]["issues"] == ["Props is not exported by ./types"]
    assert by_target["./types"]["canonical"] is None and by_target["./types"]["root"] is None
    # A judged result with no issues of its own names the flags that failed.
    assert by_target["ghost-skill"]["issues"] == ["target_exists: false", "type_match: false",
                                                  "signature_match: false"]
    for entry in out["invalidReferences"]:
        assert set(entry) == {"source", "line", "target", "status", "canonical", "root", "issues"}


def test_no_judged_file_counts_the_scan_alone(tmp_path):
    out = json.loads(_cli_files(_files(tmp_path, judged=None)).stdout)
    assert (out["input"]["valid_references"], out["input"]["total_references"]) == (1, 3)


def test_judged_results_in_an_object_without_a_fence(tmp_path):
    out = json.loads(_cli_files(_files(tmp_path, judged={"references": JUDGED[:1]}, fence=False)).stdout)
    assert (out["input"]["valid_references"], out["input"]["total_references"]) == (2, 4)


def test_no_reference_at_all_is_vacuously_valid(tmp_path):
    paths = _files(tmp_path, scan={"references": []}, judged=None,
                   integration={"patterns_documented": 0, "patterns_complete": 0})
    out = json.loads(_cli_files(paths).stdout)
    assert out["referenceValidity"] == 100.0 and out["combinedCoherence"] == 100.0
    assert out["invalidReferences"] == []


@pytest.mark.parametrize("scan, judged", [
    ({"refs": []}, None),
    ({"references": [{"line": 1, "status": "maybe"}]}, None),
    (SCAN, [{"reference": "x", "line": 1, "target_exists": "yes", "type_match": True, "signature_match": True}]),
    (SCAN, [{"reference": "x", "line": 1, "target_exists": True, "type_match": True, "signature_match": True,
             "issues": "none"}]),
], ids=["no-references-array", "unknown-status", "flag-not-boolean", "issues-not-a-list"])
def test_a_malformed_file_is_refused_and_removes_the_score(tmp_path, scan, judged):
    paths = _files(tmp_path, scan=scan, judged=judged)
    out_file = tmp_path / "coherence.json"
    out_file.write_bytes(b'{"combinedCoherence": 100}')
    proc = _cli_files(paths, "--output", str(out_file))
    assert proc.returncode == 2 and json.loads(proc.stdout)["code"] == "INVALID_INPUT"
    assert not out_file.exists()


def test_a_missing_file_exits_1(tmp_path):
    paths = _files(tmp_path)
    paths["--references"].unlink()
    proc = _cli_files(paths)
    assert proc.returncode == 1 and json.loads(proc.stdout)["code"] == "INVALID_INPUT"


def test_counts_and_files_do_not_mix(tmp_path):
    proc = _cli_files(_files(tmp_path), "--stdin")
    assert proc.returncode == 2 and "not both" in proc.stderr
    paths = _files(tmp_path)
    del paths["--integration"]
    assert _cli_files(paths).returncode == 2


def test_the_scanners_own_output_is_read_as_written(tmp_path):
    """The file coherence-check §3 writes with the scanner's reference-check feeds the script as is."""
    skill = tmp_path / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "references" / "api.md").write_bytes(b"# API\n")
    (skill / "SKILL.md").write_bytes(b"# Demo\n\nSee [API](references/api.md) and [gone](references/gone.md).\n")
    scan = subprocess.run([sys.executable, str(SCANNER), "reference-check", str(skill / "SKILL.md")],
                          capture_output=True, text=True, encoding="utf-8")
    assert scan.returncode == 0, scan.stderr
    paths = _files(tmp_path, scan=json.loads(scan.stdout), judged=None,
                   integration={"patterns_documented": 0, "patterns_complete": 0})
    out = json.loads(_cli_files(paths).stdout)
    assert (out["input"]["valid_references"], out["input"]["total_references"]) == (1, 2)
    assert [(r["target"], r["status"]) for r in out["invalidReferences"]] == [("references/gone.md", "missing")]
    gone = out["invalidReferences"][0]
    assert gone["root"] == "skill" and Path(gone["canonical"]).name == "gone.md"
