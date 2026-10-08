#!/usr/bin/env python3
"""Tests for score-signatures.py (skf-test-skill coverage-check.md §2 and §2b; #613 item 1).

Signature Accuracy and Type Coverage used to be divided by hand from
unchecked subagent JSON, with `total_types` defined nowhere. The script:
  - plans the comparisons: each documented signature the source surface
    lists (its `all` set and every name on its export records, so a nested
    Python top's names keep their checks, #677), grouped by file, with its
    source line and documented signature; without a surface, the signature
    map coverage-check-tiers.md's fallback per-file scan hands each subagent
  - schema-checks every subagent result (fence stripped), and refuses one
    that breaks the contract with violations[] and exit 2
  - scores Signature Accuracy (matching over compared, on the whole
    surface) and Type Coverage (documented types over the interfaces, type
    aliases, enums and classes of the denominator set --surface-set picks),
    with compute-score.py's rounding
  - writes each mismatch of a compared name as a Critical
    `signature-mismatch` ledger record, which gap-ledger.py append accepts as
    it is; a mismatch for any other name is a warning, never a gap
The surface fixture is load-coverage-inputs.py surface output built from a
--mode full extraction, so a recipe's internal match is never compared.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "src" / "skf-test-skill" / "scripts"
SCRIPT = SCRIPTS / "score-signatures.py"
GAP_LEDGER = SCRIPTS / "gap-ledger.py"

spec = importlib.util.spec_from_file_location("score_signatures", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

INVENTORY = {"exports": [
    {"name": "fetchData", "kind": "function", "params": "url: string", "return_type": "Promise<string>",
     "description": "Fetches."},
    {"name": "helper", "kind": "function", "params": "x: number", "return_type": "number", "description": "Help."},
    {"name": "Options", "kind": "interface", "description": "Options."},
    {"name": "Mode", "kind": "type", "description": "Mode."},
    {"name": "Client.run", "kind": "method", "params": "", "return_type": "void", "description": "Runs."},
    {"name": "stale", "kind": "function", "params": "", "return_type": "void", "description": "Gone."},
    {"name": "useThing", "kind": "hook", "usage_signature": "useThing(): Thing", "description": "Hook."},
], "cross_check_mismatches": []}

# load-coverage-inputs.py surface output for an extraction: internalThing was
# a recipe match no entry point exports, so the surface never lists it.
SURFACE = {
    "exports": [
        {"name": "Extra", "kind": "class", "file": "src/extra.ts", "line": 1, "signatureLine": "export class Extra {",
         "origin": "extraction"},
        {"name": "Level", "kind": "enum", "file": "src/extra.ts", "line": 2, "signatureLine": "export enum Level {",
         "origin": "extraction"},
        {"name": "Mode", "kind": "type", "file": "src/index.ts", "line": 4, "signatureLine": "export type Mode =",
         "origin": "extraction"},
        {"name": "Options", "kind": "interface", "file": "src/index.ts", "line": 2,
         "signatureLine": "export interface Options {", "origin": "extraction"},
        {"name": "fetchData", "kind": "function", "file": "src/index.ts", "line": 1,
         "signatureLine": "export function fetchData(url: string): Promise<string> {", "origin": "extraction"},
        {"name": "helper", "kind": "function", "file": "src/helper.ts", "line": 1,
         "signatureLine": "export function helper(x: number): number {", "origin": "extraction"},
    ],
    "sets": {"all": ["Extra", "Level", "Mode", "Options", "fetchData", "helper"],
             "root": ["Mode", "Options", "fetchData", "helper"]},
}

MISMATCH = {"name": "helper", "line": 1, "source_sig": "(x: number, y?: number) => number",
            "documented_sig": "(x: number) => number", "issue": "missing optional parameter 'y'"}


def _write(path: Path, payload) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_bytes(text.encode("utf-8"))
    return str(path)


def _files(tmp_path: Path) -> tuple[str, str]:
    return _write(tmp_path / "inventory.json", INVENTORY), _write(tmp_path / "surface.json", SURFACE)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8")


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def test_the_plan_compares_each_documented_signature_on_the_surface(tmp_path):
    inventory, surface = _files(tmp_path)
    out_path = tmp_path / "signature-plan.json"
    proc = _run("plan", "--inventory", inventory, "--surface", surface, "--output", str(out_path))
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(proc.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == plan
    assert plan["compared"] == 2  # stale and useThing are not on the surface; a method never is
    assert plan["files"] == [
        {"file": "src/helper.ts", "checks": [{"name": "helper", "line": 1,
                                              "signatureLine": "export function helper(x: number): number {",
                                              "documented": {"params": "x: number", "return_type": "number"}}]},
        {"file": "src/index.ts", "checks": [{"name": "fetchData", "line": 1,
                                             "signatureLine": "export function fetchData(url: string): Promise<string> {",
                                             "documented": {"params": "url: string",
                                                            "return_type": "Promise<string>"}}]},
    ]
    assert set(plan["documentedSignatures"]) == {"fetchData", "helper", "stale", "useThing"}


def test_the_plan_without_a_surface_is_the_signature_map(tmp_path):
    inventory, _ = _files(tmp_path)
    plan = json.loads(_run("plan", "--inventory", inventory).stdout)
    assert plan["files"] == [] and plan["compared"] == 0
    assert plan["documentedSignatures"]["useThing"] == {"usage_signature": "useThing(): Thing"}


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------


def test_scores_and_gap_records(tmp_path):
    inventory, surface = _files(tmp_path)
    results = _write(tmp_path / "signatures-1.txt",
                     "```json\n" + json.dumps({"file": "src/helper.ts", "signature_mismatches": [MISMATCH]}) + "\n```\n")
    clean = _write(tmp_path / "signatures-2.txt", json.dumps({"file": "src/index.ts", "signature_mismatches": []}))
    out_path, gaps_path = tmp_path / "signatures.json", tmp_path / "signature-gaps.json"
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--results", results, "--results", clean,
                "--output", str(out_path), "--gaps-output", str(gaps_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    out = json.loads(proc.stdout)
    assert json.loads(out_path.read_text(encoding="utf-8")) == out
    assert (out["matchingSignatures"], out["totalDocumented"], out["signatureAccuracy"]) == (1, 2, 50.0)
    # the names compared, which the gap ledger reads (#678)
    assert out["comparedNames"] == ["fetchData", "helper"]
    # Types on the surface: Extra (class), Level (enum), Mode (type), Options (interface).
    assert (out["documentedTypes"], out["totalTypes"], out["typeCoverage"]) == (2, 4, 50.0)
    assert out["missingTypes"] == ["Extra", "Level"]
    assert out["mismatches"] == [{**MISMATCH, "file": "src/helper.ts"}]
    record = json.loads(gaps_path.read_text(encoding="utf-8"))
    assert record == out["gapRecords"] and len(record) == 1
    gap = record[0]
    assert (gap["severity"], gap["category"], gap["title"], gap["source"], gap["export"]) == (
        "Critical", "signature-mismatch", "Signature mismatch: helper", "src/helper.ts:1", "helper")
    assert "(x: number) => number" in gap["remediation"] and "src/helper.ts:1" in gap["remediation"]


def test_the_gap_records_append_to_the_ledger(tmp_path):
    inventory, surface = _files(tmp_path)
    results = _write(tmp_path / "s.txt", json.dumps({"file": "src/helper.ts", "signature_mismatches": [MISMATCH]}))
    gaps = tmp_path / "signature-gaps.json"
    assert _run("score", "--inventory", inventory, "--surface", surface, "--results", results,
                "--gaps-output", str(gaps)).returncode == 0
    ledger = tmp_path / "test-findings-20260101T000000Z-abcdef12.json"
    proc = subprocess.run([sys.executable, str(GAP_LEDGER), "append", "--ledger", str(ledger), "--stage",
                           "coverage-check", "--input", str(gaps)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    assert json.loads(proc.stdout)["appended"] == ["GAP-001"]


def test_a_mismatch_for_a_name_never_compared_is_a_warning_not_a_gap(tmp_path):
    """Only a planned check can block the hard gate: a subagent that reports
    an undocumented name, or one the surface lacks, gets no ledger record."""
    inventory, surface = _files(tmp_path)
    extra = {**MISMATCH, "name": "Extra"}  # on the surface, documented without a signature
    absent = {**MISMATCH, "name": "stale", "line": 9}  # documented, not on the surface
    results = _write(tmp_path / "s.txt", json.dumps({"file": "src/helper.ts",
                                                     "signature_mismatches": [MISMATCH, extra, absent]}))
    gaps = tmp_path / "signature-gaps.json"
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", results,
                          "--gaps-output", str(gaps)).stdout)
    assert [m["name"] for m in out["mismatches"]] == ["helper"]
    assert [g["export"] for g in json.loads(gaps.read_text(encoding="utf-8"))] == ["helper"]
    assert (out["matchingSignatures"], out["totalDocumented"]) == (1, 2)
    assert any("`Extra`" in w for w in out["warnings"]) and any("`stale`" in w for w in out["warnings"])


def test_the_surface_set_picks_the_types_type_coverage_counts(tmp_path):
    """A stratified skill's Tier B types are left out of Type Coverage, as they
    are out of the Export Coverage denominator; signatures still compare on
    the whole surface."""
    inventory, surface = _files(tmp_path)
    results = _write(tmp_path / "s.txt", json.dumps({"file": "src/helper.ts", "signature_mismatches": [MISMATCH]}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--surface-set", "root",
                          "--results", results).stdout)
    # root holds Mode and Options (both documented), not Extra and Level.
    assert (out["documentedTypes"], out["totalTypes"], out["typeCoverage"]) == (2, 2, 100.0)
    assert (out["matchingSignatures"], out["totalDocumented"]) == (1, 2), "helper is not in root, still compared"


def test_a_nested_top_name_off_the_all_set_keeps_its_signature_check(tmp_path):
    """#677: load-coverage-inputs.py keeps a nested Python top's names out of
    `all` but on the export records. A documented one is still planned and
    scored, and its wrong signature is a gap; Type Coverage stays over `all`,
    so a nested class is no missing type."""
    inventory = _write(tmp_path / "inventory.json", {"exports": [
        {"name": "add", "kind": "function", "params": "data", "return_type": "None"},
        {"name": "get_add_router", "kind": "function", "return_type": "Router"},
    ], "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {
        "exports": [
            {"name": "RouterConfig", "kind": "class", "file": "pkg/api/routers/config.py", "line": 1,
             "signatureLine": "class RouterConfig:", "origin": "extraction"},
            {"name": "Task", "kind": "class", "file": "pkg/task.py", "line": 1, "signatureLine": "class Task:",
             "origin": "extraction"},
            {"name": "add", "kind": "function", "file": "pkg/add.py", "line": 1, "signatureLine": "def add(data):",
             "origin": "extraction"},
            {"name": "get_add_router", "kind": "function", "file": "pkg/api/routers/add.py", "line": 3,
             "signatureLine": "def get_add_router():", "origin": "extraction"},
        ],
        "sets": {"all": ["Task", "add"], "root": ["Task", "add"]},
        "excluded": {"outsideScope": [], "nestedEntries": [
            {"entry": "pkg/api/routers/__init__.py", "within": "pkg/__init__.py",
             "names": ["RouterConfig", "get_add_router"]}]},
    })
    plan = json.loads(_run("plan", "--inventory", inventory, "--surface", surface).stdout)
    assert plan["compared"] == 2
    assert plan["files"] == [
        {"file": "pkg/add.py", "checks": [{"name": "add", "line": 1, "signatureLine": "def add(data):",
                                           "documented": {"params": "data", "return_type": "None"}}]},
        {"file": "pkg/api/routers/add.py", "checks": [{"name": "get_add_router", "line": 3,
                                                       "signatureLine": "def get_add_router():",
                                                       "documented": {"return_type": "Router"}}]},
    ]
    mismatch = {"name": "get_add_router", "line": 3, "source_sig": "() -> APIRouter", "documented_sig": "() -> Router",
                "issue": "wrong return type"}
    results = _write(tmp_path / "s.txt", json.dumps({"file": "pkg/api/routers/add.py",
                                                     "signature_mismatches": [mismatch]}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", results).stdout)
    assert (out["matchingSignatures"], out["totalDocumented"]) == (1, 2)
    assert [g["export"] for g in out["gapRecords"]] == ["get_add_router"] and out["warnings"] == []
    assert (out["documentedTypes"], out["totalTypes"], out["missingTypes"]) == (0, 1, ["Task"])
    # A narrower set changes Type Coverage only: the signatures still compare over the whole universe.
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--surface-set", "root",
                          "--results", results).stdout)
    assert (out["matchingSignatures"], out["totalDocumented"], out["totalTypes"]) == (1, 2, 1)


def test_nothing_to_compare_scores_100_with_a_warning(tmp_path):
    inventory = _write(tmp_path / "inventory.json", {"exports": [{"name": "x", "kind": "constant"}],
                                                     "cross_check_mismatches": []})
    surface = _write(tmp_path / "surface.json", {"exports": [], "sets": {"all": ["y"]}})
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface).stdout)
    assert out["signatureAccuracy"] == 100.0 and out["typeCoverage"] == 100.0
    assert len(out["warnings"]) == 2


def test_a_fallback_scan_reports_its_own_names_and_types(tmp_path):
    inventory, _ = _files(tmp_path)
    surface = _write(tmp_path / "surface.json", {"exports": [], "sets": {"all": []}})
    per_file = _write(tmp_path / "per-file-1.txt", json.dumps({
        "file": "src/index.ts", "exports_found": ["fetchData", "Options", "Hidden"], "types_found": ["Options", "Hidden"],
        "signature_mismatches": []}))
    out = json.loads(_run("score", "--inventory", inventory, "--surface", surface, "--results", per_file).stdout)
    assert (out["documentedTypes"], out["totalTypes"]) == (1, 2)
    assert (out["matchingSignatures"], out["totalDocumented"]) == (1, 1)


def test_rounding_matches_compute_score(tmp_path):
    inventory = {"exports": [{"name": f"f{i}", "kind": "function", "params": "", "return_type": "void"}
                             for i in range(3)], "cross_check_mismatches": []}
    surface = {"exports": [{"name": f"f{i}", "kind": "function", "file": "a.ts", "line": i + 1} for i in range(3)],
               "sets": {"all": ["f0", "f1", "f2"]}}
    results = [{"file": "a.ts", "signature_mismatches": [
        {"name": "f0", "line": 1, "source_sig": "(a)", "documented_sig": "()", "issue": "missing a"}]}]
    out = mod.score(inventory["exports"], surface["sets"]["all"], surface["exports"], results)
    assert out["signatureAccuracy"] == 66.67


@pytest.mark.parametrize("payload, needle", [
    ("not json", "not valid JSON"),
    ({"signature_mismatches": []}, "`file` must be a non-empty string"),
    ({"file": "a.ts"}, "`signature_mismatches` must be present"),
    ({"file": "a.ts", "signature_mismatches": [{"name": "x"}]}, "missing field(s)"),
    ({"file": "a.ts", "signature_mismatches": [{**MISMATCH, "line": "1"}]}, "`line` must be a line number"),
    ({"file": "a.ts", "exports_found": "x", "signature_mismatches": []}, "`exports_found` must be a list"),
], ids=["not-json", "no-file", "no-mismatches", "missing-fields", "line-not-int", "exports-not-list"])
def test_a_result_that_breaks_the_schema_exits_2(tmp_path, payload, needle):
    inventory, surface = _files(tmp_path)
    bad = _write(tmp_path / "bad.txt", payload)
    stale = tmp_path / "signatures.json"
    stale.write_bytes(b"{}")
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--results", bad, "--output", str(stale))
    assert proc.returncode == 2
    out = json.loads(proc.stdout)
    assert out["valid"] is False and any(needle in v for v in out["violations"]), out["violations"]
    assert not stale.exists(), "a refused run leaves no score file for step 5 to read"


def test_an_unreadable_input_exits_1(tmp_path):
    _, surface = _files(tmp_path)
    proc = _run("score", "--inventory", str(tmp_path / "absent.json"), "--surface", surface)
    assert proc.returncode == 1 and "cannot read --inventory" in proc.stderr


def test_a_surface_without_the_set_exits_1(tmp_path):
    inventory, surface = _files(tmp_path)
    proc = _run("score", "--inventory", inventory, "--surface", surface, "--surface-set", "subpaths")
    assert proc.returncode == 1 and "no name set `subpaths`" in proc.stderr
